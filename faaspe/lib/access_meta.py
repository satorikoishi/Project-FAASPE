from contextvars import ContextVar


UNKNOWN_BUCKET = "unknown"


class JKVAccessMeta:
    __slots__ = ("op", "cache_hit", "object_size", "object_size_bucket")

    def __init__(
        self,
        op="none",
        cache_hit=None,
        object_size=-1,
        object_size_bucket=UNKNOWN_BUCKET,
    ):
        self.op = op
        self.cache_hit = cache_hit
        self.object_size = object_size
        self.object_size_bucket = object_size_bucket

    def __repr__(self):
        return (
            "JKVAccessMeta("
            f"op={self.op!r}, cache_hit={self.cache_hit!r}, "
            f"object_size={self.object_size!r}, "
            f"object_size_bucket={self.object_size_bucket!r})"
        )


class InvocationAccessMeta:
    __slots__ = (
        "get_count",
        "put_count",
        "cache_hits",
        "cache_misses",
        "max_object_size",
        "total_object_size",
        "object_size_bucket",
        "cache_state",
    )

    def __init__(
        self,
        get_count=0,
        put_count=0,
        cache_hits=0,
        cache_misses=0,
        max_object_size=-1,
        total_object_size=0,
        object_size_bucket=UNKNOWN_BUCKET,
        cache_state=UNKNOWN_BUCKET,
    ):
        self.get_count = get_count
        self.put_count = put_count
        self.cache_hits = cache_hits
        self.cache_misses = cache_misses
        self.max_object_size = max_object_size
        self.total_object_size = total_object_size
        self.object_size_bucket = object_size_bucket
        self.cache_state = cache_state

    def add_jkv_meta(self, meta):
        if meta.op == "get":
            self.get_count += 1
            if meta.cache_hit is True:
                self.cache_hits += 1
            elif meta.cache_hit is False:
                self.cache_misses += 1
        elif meta.op == "put":
            self.put_count += 1

        if meta.object_size >= 0:
            self.total_object_size += meta.object_size
            if meta.object_size > self.max_object_size:
                self.max_object_size = meta.object_size
                self.object_size_bucket = meta.object_size_bucket
        self.cache_state = cache_state(self.cache_hits, self.cache_misses)

    def as_dict(self):
        return {
            "get_count": self.get_count,
            "put_count": self.put_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "max_object_size": self.max_object_size,
            "total_object_size": self.total_object_size,
            "object_size_bucket": self.object_size_bucket,
            "cache_state": self.cache_state,
        }


_CURRENT_ACCESS_META = ContextVar("faaspe_invocation_access_meta", default=None)


def estimate_object_size(value):
    if value is None:
        return 0
    if isinstance(value, (bytes, bytearray, memoryview, str)):
        return len(value)
    cheap_size = getattr(value, "size", None)
    if isinstance(cheap_size, int):
        return cheap_size
    return -1


def object_size_bucket(size):
    if size < 0:
        return UNKNOWN_BUCKET
    if size == 0:
        return "empty"
    if size <= 1024:
        return "1KB"
    if size <= 10 * 1024:
        return "10KB"
    if size <= 100 * 1024:
        return "100KB"
    if size <= 1024 * 1024:
        return "1MB"
    return "gt1MB"


def cache_state(cache_hits, cache_misses):
    if cache_hits == 0 and cache_misses == 0:
        return UNKNOWN_BUCKET
    if cache_hits > 0 and cache_misses == 0:
        return "hit"
    if cache_hits == 0 and cache_misses > 0:
        return "miss"
    return "mixed"


def reset_invocation_access_meta():
    meta = InvocationAccessMeta()
    _CURRENT_ACCESS_META.set(meta)
    return meta


def current_invocation_access_meta():
    return _CURRENT_ACCESS_META.get()


def record_jkv_access(meta):
    collector = current_invocation_access_meta()
    if collector is not None:
        collector.add_jkv_meta(meta)


def snapshot_invocation_access_meta():
    collector = current_invocation_access_meta()
    if collector is None:
        return InvocationAccessMeta()
    return collector
