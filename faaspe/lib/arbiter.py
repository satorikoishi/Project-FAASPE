import json
import os
import time
from dataclasses import dataclass


DEFAULT_PROFILES = {
    "auth": {"rpn": "1"},
    "calc-avg": {"rpn": "1"},
    "compute-emulate": {"rpn": "dependent_access"},
    "data-size": {"rpn": "1"},
    "list-traversal": {"rpn": "depth"},
    "list-traversal-trace": {"rpn": "depth"},
    "placement-matrix": {"rpn": "depth"},
    "storage-load-trace": {"rpn": "depth"},
    "ycsb": {"rpn": "1"},
    "ycsb-t": {"rpn": "2"},
}

PROFILE_MANIFEST = "faaspe_rpn.json"
LATENCY_MODEL_MANIFEST = "placement_latency_model.json"


@dataclass
class PlacementDecision:
    placement: str
    reason: str
    access_depth: float = None
    object_size: int = None
    compute_latency_us: float = None
    storage_latency_us: float = None
    ast_analysis_us: float = 0.0
    trigger_check_us: float = 0.0


class RPNError(ValueError):
    pass


class RPNExpression:
    def __init__(self, expr):
        self.expr = expr or ""
        self.tokens = self.expr.split()

    def evaluate(self, params=None):
        params = params or {}
        stack = []
        for token in self.tokens:
            if token in {"+", "-", "*", "/"}:
                if len(stack) < 2:
                    raise RPNError(f"operator {token} has too few operands")
                rhs = stack.pop()
                lhs = stack.pop()
                if token == "+":
                    stack.append(lhs + rhs)
                elif token == "-":
                    stack.append(lhs - rhs)
                elif token == "*":
                    stack.append(lhs * rhs)
                else:
                    if rhs == 0:
                        raise RPNError("division by zero")
                    stack.append(lhs / rhs)
            else:
                stack.append(self._value(token, params))

        if len(stack) != 1:
            raise RPNError(f"invalid RPN expression: {self.expr}")
        return stack[0]

    def _value(self, token, params):
        try:
            return float(token)
        except ValueError:
            pass

        if token not in params:
            raise RPNError(f"missing RPN parameter: {token}")
        try:
            return float(params[token])
        except (TypeError, ValueError) as exc:
            raise RPNError(f"invalid RPN parameter {token}: {params[token]}") from exc


class PlacementLatencyModel:
    def __init__(
        self,
        linear_start_depth=4,
        small_depth_cache_latency_us=None,
        cache_object_size_latency_us=None,
        storage_base_latency_us=900.0,
    ):
        self.linear_start_depth = int(linear_start_depth)
        self.small_depth_cache_latency_us = {
            int(depth): float(latency)
            for depth, latency in (small_depth_cache_latency_us or {}).items()
        }
        self.cache_object_size_latency_us = sorted(
            [
                {
                    "max_bytes": int(bucket["max_bytes"]),
                    "latency_us": float(bucket["latency_us"]),
                }
                for bucket in (cache_object_size_latency_us or [])
                if "max_bytes" in bucket and "latency_us" in bucket
            ],
            key=lambda bucket: bucket["max_bytes"],
        )
        self.storage_base_latency_us = float(storage_base_latency_us)

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            linear_start_depth=data.get("linear_start_depth", 4),
            small_depth_cache_latency_us=data.get("small_depth_cache_latency_us", {}),
            cache_object_size_latency_us=data.get("cache_object_size_latency_us", []),
            storage_base_latency_us=data.get("storage_base_latency_us", 900.0),
        )

    @classmethod
    def default(cls, local_access_us=200.0, storage_base_latency_us=900.0):
        return cls(
            linear_start_depth=int(os.getenv("FAASPE_LINEAR_START_DEPTH", "4")),
            small_depth_cache_latency_us={},
            cache_object_size_latency_us=[
                {
                    "max_bytes": int(os.getenv("FAASPE_DEFAULT_OBJECT_SIZE_BYTES", str(1024 * 1024))),
                    "latency_us": float(local_access_us),
                }
            ],
            storage_base_latency_us=storage_base_latency_us,
        )

    def cache_object_latency_us(self, object_size):
        object_size = int(object_size or 0)
        if not self.cache_object_size_latency_us:
            return 0.0
        for bucket in self.cache_object_size_latency_us:
            if object_size <= bucket["max_bytes"]:
                return bucket["latency_us"]
        return self.cache_object_size_latency_us[-1]["latency_us"]

    def cache_latency_us(self, depth, object_size):
        depth = float(depth or 0.0)
        depth_key = int(depth)
        if depth == depth_key and depth_key < self.linear_start_depth:
            small_latency = self.small_depth_cache_latency_us.get(depth_key)
            if small_latency is not None:
                return small_latency
        return depth * self.cache_object_latency_us(object_size)

    def storage_latency_us(self, storage_load_us=0.0):
        return self.storage_base_latency_us + float(storage_load_us or 0.0)

    def default_object_size_bytes(self):
        if not self.cache_object_size_latency_us:
            return int(os.getenv("FAASPE_DEFAULT_OBJECT_SIZE_BYTES", "1024"))
        return self.cache_object_size_latency_us[0]["max_bytes"]


class Arbiter:
    """Low-overhead placement arbiter driven by registered RPN profiles.

    The AST analyzer runs offline when a function is registered and stores an
    RPN expression for the function's dependent access count. At invocation
    time the arbiter only evaluates that RPN and compares simple latency
    estimates for compute-side and storage-side execution.
    """

    def __init__(
        self,
        profiles=None,
        local_base_us=0.0,
        local_access_us=200.0,
        storage_func_us=900.0,
        object_size_threshold=1024 * 1024,
        unknown_default="func",
        latency_model=None,
    ):
        self.profiles = profiles or DEFAULT_PROFILES
        self.local_base_us = float(os.getenv("FAASPE_LOCAL_BASE_US", local_base_us))
        self.local_access_us = float(os.getenv("FAASPE_LOCAL_ACCESS_US", local_access_us))
        threshold_multiplier = float(os.getenv("FAASPE_THRESHOLD_MULTIPLIER", 1.0))
        self.storage_func_us = (
            float(os.getenv("FAASPE_STORAGE_FUNC_US", storage_func_us)) * threshold_multiplier
        )
        threshold = os.getenv("FAASPE_STORAGE_DEPTH_THRESHOLD", "")
        self.storage_depth_threshold = float(threshold) if threshold else None
        self.object_size_threshold = int(
            os.getenv("FAASPE_OBJECT_SIZE_THRESHOLD", object_size_threshold)
        )
        self.latency_model = latency_model or PlacementLatencyModel.default(
            local_access_us=self.local_access_us,
            storage_base_latency_us=self.storage_func_us,
        )
        self.unknown_default = os.getenv("FAASPE_UNKNOWN_PLACEMENT", unknown_default)
        self.last_overhead_us = 0.0
        self.policy_updates = []

    @classmethod
    def from_env(cls, manifest_path=None):
        profiles = dict(DEFAULT_PROFILES)
        env_profiles = os.getenv("FAASPE_RPN_PROFILES")
        if env_profiles:
            profiles.update(json.loads(env_profiles))

        manifest_candidates = []
        manifest_path = manifest_path or os.getenv("FAASPE_RPN_MANIFEST")
        if manifest_path:
            manifest_candidates.append(manifest_path)
        manifest_candidates.append(PROFILE_MANIFEST)

        for candidate in manifest_candidates:
            if candidate and os.path.exists(candidate):
                with open(candidate, "r") as f:
                    profiles.update(json.load(f))

        latency_model = cls._load_latency_model()
        return cls(profiles=profiles, latency_model=latency_model)

    @staticmethod
    def _load_latency_model():
        env_json = os.getenv("FAASPE_PLACEMENT_LATENCY_MODEL_JSON")
        if env_json:
            return PlacementLatencyModel.from_dict(json.loads(env_json))

        candidates = []
        env_path = os.getenv("FAASPE_PLACEMENT_LATENCY_MODEL")
        if env_path:
            candidates.append(env_path)
        candidates.append(LATENCY_MODEL_MANIFEST)
        candidates.append(
            os.path.join(os.path.dirname(__file__), LATENCY_MODEL_MANIFEST)
        )

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                with open(candidate, "r") as f:
                    return PlacementLatencyModel.from_dict(json.load(f))
        return None

    def decide(self, function_name, params=None):
        started = time.perf_counter()
        try:
            placement = self._explain(function_name, params or {}).placement
        finally:
            self.last_overhead_us = (time.perf_counter() - started) * 1e6
        return placement

    def _decide(self, function_name, params):
        return self.explain(function_name, params).placement

    def explain(self, function_name, params=None):
        started = time.perf_counter()
        try:
            return self._explain(function_name, params or {})
        finally:
            self.last_overhead_us = (time.perf_counter() - started) * 1e6

    def _explain(self, function_name, params=None):
        params = params or {}
        if os.getenv("FAASPE_ARBITER_FORCE_UNKNOWN", "0") not in {
            "",
            "0",
            "false",
            "False",
            "no",
            "off",
        }:
            return PlacementDecision(
                self.unknown_default,
                "unsupported_static_analysis",
            )
        profile = self.profiles.get(function_name)
        if profile is None:
            return PlacementDecision(
                self.unknown_default,
                "unsupported_static_analysis",
            )

        try:
            access_depth = RPNExpression(profile.get("rpn", "")).evaluate(params)
        except RPNError:
            return PlacementDecision(
                self.unknown_default,
                "unsupported_static_analysis",
            )

        storage_load_us = float(params.get("storage_load_us", 0) or 0)
        assumed_object_size = self.latency_model.default_object_size_bytes()
        local_latency = self.latency_model.cache_latency_us(
            access_depth,
            assumed_object_size,
        )
        storage_latency = self.latency_model.storage_latency_us(storage_load_us)
        if storage_load_us > 0 and local_latency <= storage_latency:
            reason = "storage_load"
        else:
            reason = "latency_model_depth"
        return PlacementDecision(
            "native" if local_latency <= storage_latency else "func",
            reason,
            access_depth=access_depth,
            object_size=None,
            compute_latency_us=local_latency,
            storage_latency_us=storage_latency,
        )

    def access_depth(self, function_name, params=None):
        profile = self.profiles.get(function_name)
        if profile is None:
            return None
        try:
            return RPNExpression(profile.get("rpn", "")).evaluate(params or {})
        except RPNError:
            return None

    def estimate_latency_us(
        self,
        function_name,
        params=None,
        placement=None,
        observed_object_size=None,
    ):
        params = params or {}
        placement = placement or self._decide(function_name, params)

        if placement == "native":
            access_depth = self.access_depth(function_name, params)
            if access_depth is None:
                return None
            object_size = (
                int(observed_object_size)
                if observed_object_size is not None and int(observed_object_size) >= 0
                else self.latency_model.default_object_size_bytes()
            )
            return self.latency_model.cache_latency_us(
                access_depth,
                object_size,
            )
        if placement == "func":
            return self.latency_model.storage_latency_us(params.get("storage_load_us", 0))
        return None

    def receive_policy_update(self, update):
        self.policy_updates.append(update)

    def policy_update_snapshot(self):
        return list(self.policy_updates)

    def _object_size(self, params):
        return int(float(params.get("object_size", 0) or 0))


_ARBITER = None


def get_arbiter():
    global _ARBITER
    if _ARBITER is None:
        _ARBITER = Arbiter.from_env()
    return _ARBITER
