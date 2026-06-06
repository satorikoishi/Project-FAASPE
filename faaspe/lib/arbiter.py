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
    "storage-load-trace": {"rpn": "depth"},
    "ycsb": {"rpn": "1"},
    "ycsb-t": {"rpn": "2"},
}

PROFILE_MANIFEST = "faaspe_rpn.json"


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
    ):
        self.profiles = profiles or DEFAULT_PROFILES
        self.local_base_us = float(os.getenv("FAASPE_LOCAL_BASE_US", local_base_us))
        self.local_access_us = float(os.getenv("FAASPE_LOCAL_ACCESS_US", local_access_us))
        self.storage_func_us = float(os.getenv("FAASPE_STORAGE_FUNC_US", storage_func_us))
        self.object_size_threshold = int(
            os.getenv("FAASPE_OBJECT_SIZE_THRESHOLD", object_size_threshold)
        )
        self.unknown_default = os.getenv("FAASPE_UNKNOWN_PLACEMENT", unknown_default)
        self.last_overhead_us = 0.0

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

        return cls(profiles=profiles)

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
        profile = self.profiles.get(function_name)
        if profile is None:
            return PlacementDecision(
                self.unknown_default,
                "unsupported_static_analysis",
                object_size=self._object_size(params),
            )

        object_size = self._object_size(params)
        if object_size >= self.object_size_threshold:
            return PlacementDecision(
                "func",
                "large_object_trigger",
                object_size=object_size,
                storage_latency_us=self.storage_func_us
                + float(params.get("storage_load_us", 0) or 0),
            )

        try:
            access_depth = RPNExpression(profile.get("rpn", "")).evaluate(params)
        except RPNError:
            return PlacementDecision(
                self.unknown_default,
                "unsupported_static_analysis",
                object_size=object_size,
            )

        local_latency = self.local_base_us + access_depth * self.local_access_us
        storage_latency = self.storage_func_us + float(params.get("storage_load_us", 0) or 0)
        if float(params.get("storage_load_us", 0) or 0) > 0 and local_latency <= storage_latency:
            reason = "storage_load"
        else:
            reason = "access_depth_threshold"
        return PlacementDecision(
            "native" if local_latency <= storage_latency else "func",
            reason,
            access_depth=access_depth,
            object_size=object_size,
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

    def estimate_latency_us(self, function_name, params=None, placement=None):
        params = params or {}
        placement = placement or self._decide(function_name, params)

        if placement == "native":
            access_depth = self.access_depth(function_name, params)
            if access_depth is None:
                return None
            return self.local_base_us + access_depth * self.local_access_us
        if placement == "func":
            return self.storage_func_us + float(params.get("storage_load_us", 0) or 0)
        return None

    def _object_size(self, params):
        return int(float(params.get("object_size", 0) or 0))


_ARBITER = None


def get_arbiter():
    global _ARBITER
    if _ARBITER is None:
        _ARBITER = Arbiter.from_env()
    return _ARBITER
