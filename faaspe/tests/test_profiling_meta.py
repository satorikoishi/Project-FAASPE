import os
import sys
import time
from types import SimpleNamespace


LIB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from access_meta import (  # noqa: E402
    InvocationAccessMeta,
    JKVAccessMeta,
    object_size_bucket,
    reset_invocation_access_meta,
    snapshot_invocation_access_meta,
)
from arbiter import Arbiter  # noqa: E402
from benchmark import Benchmark  # noqa: E402
from profiler import AsyncProfiler, Profiler  # noqa: E402


def test_get_hit_updates_cache_hits_and_object_size():
    meta = InvocationAccessMeta()
    size = 128
    meta.add_jkv_meta(
        JKVAccessMeta(
            op="get",
            cache_hit=True,
            object_size=size,
            object_size_bucket=object_size_bucket(size),
        )
    )
    assert meta.get_count == 1
    assert meta.cache_hits == 1
    assert meta.cache_misses == 0
    assert meta.max_object_size == size
    assert meta.total_object_size == size
    assert meta.cache_state == "hit"


def test_get_miss_updates_cache_misses_and_object_size():
    meta = InvocationAccessMeta()
    size = 2048
    meta.add_jkv_meta(
        JKVAccessMeta(
            op="get",
            cache_hit=False,
            object_size=size,
            object_size_bucket=object_size_bucket(size),
        )
    )
    assert meta.get_count == 1
    assert meta.cache_hits == 0
    assert meta.cache_misses == 1
    assert meta.max_object_size == size
    assert meta.object_size_bucket == "10KB"
    assert meta.cache_state == "miss"


def test_put_updates_put_count_and_object_size():
    meta = InvocationAccessMeta()
    size = 12
    meta.add_jkv_meta(
        JKVAccessMeta(
            op="put",
            object_size=size,
            object_size_bucket=object_size_bucket(size),
        )
    )
    assert meta.put_count == 1
    assert meta.get_count == 0
    assert meta.max_object_size == size
    assert meta.total_object_size == size


def test_invocation_record_includes_access_metadata(monkeypatch):
    records = []

    class DummyLogger:
        def is_enabled(self):
            return True

        def write(self, record):
            records.append(record)

    bench = Benchmark.__new__(Benchmark)
    bench.name = "list-traversal"
    bench.strategy = "local"
    bench.invocation_logger = DummyLogger()

    access_meta = InvocationAccessMeta(get_count=1, cache_hits=1, max_object_size=3)
    access_meta.total_object_size = 3
    access_meta.object_size_bucket = "1KB"
    access_meta.cache_state = "hit"
    plan = SimpleNamespace(
        reason="normal",
        arbiter_reason="default",
        fallback_active=False,
        access_depth=1,
        object_size=0,
        compute_latency_us=200,
        storage_latency_us=900,
        trigger_check_us=0.0,
        ast_analysis_us=0.0,
        expected_us=200,
    )

    monkeypatch.setattr("bench_util.async_profiler_enabled", lambda: False)
    bench.log_invocation(0, {"depth": 1}, "native", plan, 0.0002, access_meta, 123)
    assert records
    assert records[0]["get_count"] == 1
    assert records[0]["cache_hits"] == 1
    assert records[0]["max_object_size"] == 3
    assert records[0]["object_size_bucket"] == "1KB"


def test_async_profiler_record_fast_drops_without_blocking_when_queue_full():
    profiler = AsyncProfiler(enabled=True, queue_size=1, start_worker=False)
    profiler.record_fast({"func_id": "f", "actual_ns": 1})
    started = time.perf_counter()
    profiler.record_fast({"func_id": "f", "actual_ns": 2})
    elapsed = time.perf_counter() - started
    assert elapsed < 0.01
    assert profiler.dropped == 1


def test_async_profiler_emits_policy_update_and_arbiter_receives_it():
    arbiter = Arbiter()
    profiler = AsyncProfiler(
        enabled=True,
        start_worker=False,
        min_records=2,
        residual_factor=1.25,
        residual_min_ns=100000,
    )
    profiler.set_policy_callback(arbiter.receive_policy_update)
    record = {
        "func_id": "list-traversal",
        "side": "compute",
        "estimated_ad": 1,
        "object_size_bucket": "1KB",
        "cache_state": "hit",
        "predicted_ns": 200000,
        "actual_ns": 500000,
        "get_count": 1,
        "put_count": 0,
        "cache_misses": 0,
        "max_object_size": 3,
    }
    profiler.consume(dict(record))
    profiler.consume(dict(record))
    assert len(profiler.policy_update_snapshot()) == 1
    assert len(arbiter.policy_update_snapshot()) == 1


def test_existing_placement_behavior_unchanged_when_profiling_disabled(monkeypatch):
    monkeypatch.setenv("FAASPE_PROFILE_ENABLED", "0")
    arbiter = Arbiter()
    profiler = Profiler.from_env()
    plan = profiler.choose("list-traversal", {"depth": 8}, arbiter)
    assert plan.placement == arbiter.explain("list-traversal", {"depth": 8}).placement


def test_arbiter_storage_depth_threshold_can_include_depth_four(monkeypatch):
    monkeypatch.delenv("FAASPE_STORAGE_DEPTH_THRESHOLD", raising=False)
    assert Arbiter().explain("list-traversal", {"depth": 4}).placement == "native"

    monkeypatch.setenv("FAASPE_STORAGE_DEPTH_THRESHOLD", "4")
    decision = Arbiter().explain("list-traversal", {"depth": 4})
    assert decision.placement == "func"
    assert decision.reason == "calibrated_depth_threshold"
