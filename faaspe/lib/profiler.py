import os
import queue
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field


PLACEMENTS = ("native", "func")


def opposite_placement(placement):
    return "func" if placement == "native" else "native"


@dataclass
class InvocationPlan:
    placement: str
    expected_us: float = 0.0
    fallback_active: bool = False
    reason: str = "normal"
    arbiter_reason: str = "default"
    access_depth: float = None
    object_size: int = None
    compute_latency_us: float = None
    storage_latency_us: float = None
    ast_analysis_us: float = 0.0
    trigger_check_us: float = 0.0


@dataclass
class FunctionProfile:
    invocations: int = 0
    fallback_count: int = 0
    fallback_invocations: int = 0
    recheck_count: int = 0
    override_placement: str = ""
    exploring: bool = False
    explore_next: int = 0
    explore_latencies: dict = field(
        default_factory=lambda: {"native": [], "func": []}
    )
    recent_violations: deque = field(default_factory=deque)
    history: dict = field(default_factory=lambda: {"native": deque(), "func": deque()})


@dataclass
class AsyncBucketState:
    records: deque
    diagnosed_causes: set = field(default_factory=set)
    update_emitted: bool = False


@dataclass
class PolicyUpdate:
    bucket_key: tuple
    func_id: str
    side: str
    median_actual_ns: float
    median_predicted_ns: float
    diagnosis: tuple
    record_count: int


def env_enabled(name, default="0"):
    return os.getenv(name, default) not in {"", "0", "false", "False", "no", "off"}


def profile_enabled():
    if "FAASPE_PROFILE_ENABLED" in os.environ:
        return env_enabled("FAASPE_PROFILE_ENABLED", "1")
    return env_enabled("FAASPE_PROFILER_ENABLED", "1")


def access_depth_bucket(value):
    if value is None:
        return "unknown"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 1:
        return "ad_le1"
    if value <= 2:
        return "ad_le2"
    if value <= 4:
        return "ad_le4"
    if value <= 8:
        return "ad_le8"
    return "ad_gt8"


class Profiler:
    """Runtime feedback and fallback profiler for FAASPE placement.

    Arbiter remains the fast path. Profiler watches observed latency against
    Arbiter's expected latency. If recent invocations exceed expectation too
    often, it explores both placements and selects the lower-median side.
    Periodic recheck is opt-in and only used when Arbiter lacks static
    analysis for the function.
    """

    def __init__(
        self,
        enabled=True,
        violation_factor=1.5,
        violation_window=20,
        violation_limit=3,
        explore_samples=10,
        recheck_interval=0,
        history_limit=200,
        fallback_enabled=True,
    ):
        self.enabled = enabled
        self.fallback_enabled = fallback_enabled
        self.violation_factor = violation_factor
        self.violation_window = violation_window
        self.violation_limit = violation_limit
        self.explore_samples = explore_samples
        self.recheck_interval = recheck_interval
        self.history_limit = history_limit
        self.functions = {}
        self.last_overhead_us = 0.0
        self._last_plan = InvocationPlan("native")

    @classmethod
    def from_env(cls):
        return cls(
            enabled=profile_enabled(),
            violation_factor=float(os.getenv("FAASPE_PROFILER_VIOLATION_FACTOR", 1.5)),
            violation_window=int(os.getenv("FAASPE_PROFILER_VIOLATION_WINDOW", 20)),
            violation_limit=int(os.getenv("FAASPE_PROFILER_VIOLATION_LIMIT", 3)),
            explore_samples=int(os.getenv("FAASPE_PROFILER_EXPLORE_SAMPLES", 10)),
            recheck_interval=int(os.getenv("FAASPE_PROFILER_RECHECK_INTERVAL", 0)),
            history_limit=int(os.getenv("FAASPE_PROFILER_HISTORY_LIMIT", 200)),
            fallback_enabled=os.getenv("FAASPE_FALLBACK_ENABLED", "1") != "0",
        )

    def choose(self, function_name, params, arbiter):
        started = time.perf_counter()
        try:
            plan = self._choose(function_name, params or {}, arbiter)
        finally:
            self.last_overhead_us = (time.perf_counter() - started) * 1e6
        self._last_plan = plan
        return plan

    def _choose(self, function_name, params, arbiter):
        decision = arbiter.explain(function_name, params)
        base_placement = decision.placement
        expected = arbiter.estimate_latency_us(function_name, params, base_placement)
        if not self.enabled or base_placement not in PLACEMENTS:
            return self._plan_from_decision(decision, expected or 0.0)

        profile = self._profile(function_name)
        profile.invocations += 1

        if self.fallback_enabled and profile.exploring:
            placement = self._next_explore_placement(profile)
            expected = arbiter.estimate_latency_us(function_name, params, placement)
            plan = self._plan_from_decision(decision, expected or 0.0)
            plan.placement = placement
            plan.fallback_active = True
            plan.reason = "explore"
            return plan

        if self.fallback_enabled and profile.override_placement:
            placement = profile.override_placement
            reason = "fallback"
            if self._should_recheck(profile, decision):
                placement = opposite_placement(profile.override_placement)
                reason = "recheck"
                profile.recheck_count += 1
            expected = arbiter.estimate_latency_us(function_name, params, placement)
            plan = self._plan_from_decision(decision, expected or 0.0)
            plan.placement = placement
            plan.fallback_active = True
            plan.reason = reason
            return plan

        return self._plan_from_decision(decision, expected or 0.0)

    def record(self, function_name, placement, latency_us, plan=None):
        if not self.enabled or placement not in PLACEMENTS:
            return

        plan = plan or self._last_plan
        profile = self._profile(function_name)
        self._append_history(profile.history[placement], latency_us)

        if profile.exploring:
            profile.explore_latencies[placement].append(latency_us)
            self._finish_explore_if_ready(profile)
            return

        if plan.reason in {"fallback", "recheck"}:
            profile.fallback_invocations += 1
            return

        if plan.expected_us <= 0:
            return

        violation = latency_us > plan.expected_us * self.violation_factor
        profile.recent_violations.append(violation)
        while len(profile.recent_violations) > self.violation_window:
            profile.recent_violations.popleft()

        if self.fallback_enabled and sum(profile.recent_violations) >= self.violation_limit:
            self._start_explore(profile)

    def snapshot(self, function_name):
        profile = self.functions.get(function_name)
        if not profile:
            return {
                "profiler_fallback_count": 0,
                "profiler_fallback_invocations": 0,
                "profiler_recheck_count": 0,
                "profiler_override": "",
            }
        return {
            "profiler_fallback_count": profile.fallback_count,
            "profiler_fallback_invocations": profile.fallback_invocations,
            "profiler_recheck_count": profile.recheck_count,
            "profiler_override": profile.override_placement,
        }

    def last_plan(self):
        return self._last_plan

    def _profile(self, function_name):
        if function_name not in self.functions:
            self.functions[function_name] = FunctionProfile(
                recent_violations=deque(maxlen=self.violation_window),
                history={
                    "native": deque(maxlen=self.history_limit),
                    "func": deque(maxlen=self.history_limit),
                },
            )
        return self.functions[function_name]

    def _next_explore_placement(self, profile):
        native_count = len(profile.explore_latencies["native"])
        func_count = len(profile.explore_latencies["func"])
        if native_count >= self.explore_samples:
            return "func"
        if func_count >= self.explore_samples:
            return "native"
        placement = PLACEMENTS[profile.explore_next % len(PLACEMENTS)]
        profile.explore_next += 1
        return placement

    def _start_explore(self, profile):
        profile.exploring = True
        profile.explore_next = 0
        profile.explore_latencies = {"native": [], "func": []}
        profile.recent_violations.clear()

    def _finish_explore_if_ready(self, profile):
        if any(len(profile.explore_latencies[p]) < self.explore_samples for p in PLACEMENTS):
            return

        medians = {
            placement: statistics.median(profile.explore_latencies[placement])
            for placement in PLACEMENTS
        }
        profile.override_placement = min(medians, key=medians.get)
        profile.exploring = False
        profile.fallback_count += 1
        profile.explore_latencies = {"native": [], "func": []}

    def _append_history(self, history, latency_us):
        history.append(latency_us)

    def _should_recheck(self, profile, decision):
        if self.recheck_interval <= 0:
            return False
        if decision.reason != "unsupported_static_analysis":
            return False
        return profile.invocations % self.recheck_interval == 0

    def _plan_from_decision(self, decision, expected_us):
        return InvocationPlan(
            placement=decision.placement,
            expected_us=expected_us,
            reason="normal",
            arbiter_reason=decision.reason,
            access_depth=decision.access_depth,
            object_size=decision.object_size,
            compute_latency_us=decision.compute_latency_us,
            storage_latency_us=decision.storage_latency_us,
            ast_analysis_us=decision.ast_analysis_us,
            trigger_check_us=decision.trigger_check_us,
        )


_PROFILER = None
_ASYNC_PROFILER = None


def get_profiler():
    global _PROFILER
    if _PROFILER is None:
        _PROFILER = Profiler.from_env()
    return _PROFILER


class AsyncProfiler:
    def __init__(
        self,
        enabled=False,
        queue_size=4096,
        history_limit=10000,
        bucket_limit=64,
        min_records=8,
        residual_factor=1.25,
        residual_min_ns=100000,
        start_worker=True,
    ):
        self.enabled = enabled
        self.queue = queue.Queue(maxsize=queue_size)
        self.records = deque(maxlen=history_limit)
        self.buckets = {}
        self.bucket_limit = bucket_limit
        self.min_records = min_records
        self.residual_factor = residual_factor
        self.residual_min_ns = residual_min_ns
        self.policy_updates = deque(maxlen=1024)
        self.dropped = 0
        self._stop = False
        self._thread = None
        self._policy_callback = None
        if self.enabled and start_worker:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    @classmethod
    def from_env(cls):
        async_enabled = env_enabled(
            "FAASPE_PROFILE_ASYNC_ENABLED",
            os.getenv("FAASPE_ASYNC_PROFILER_ENABLED", "0"),
        )
        return cls(
            enabled=profile_enabled() and async_enabled,
            queue_size=int(os.getenv("FAASPE_PROFILE_ASYNC_QUEUE_SIZE", os.getenv("FAASPE_ASYNC_PROFILER_QUEUE_SIZE", 4096))),
            history_limit=int(os.getenv("FAASPE_PROFILE_ASYNC_HISTORY_LIMIT", os.getenv("FAASPE_ASYNC_PROFILER_HISTORY_LIMIT", 10000))),
            bucket_limit=int(os.getenv("FAASPE_PROFILE_ASYNC_BUCKET_LIMIT", 64)),
            min_records=int(os.getenv("FAASPE_PROFILE_RESIDUAL_MIN_RECORDS", 8)),
            residual_factor=float(os.getenv("FAASPE_PROFILE_RESIDUAL_FACTOR", 1.25)),
            residual_min_ns=int(os.getenv("FAASPE_PROFILE_RESIDUAL_MIN_NS", 100000)),
        )

    def record_fast(self, record):
        if not self.enabled:
            return
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def snapshot(self):
        return list(self.records)

    def bucket_snapshot(self):
        return {
            key: {
                "count": len(state.records),
                "diagnosed_causes": sorted(state.diagnosed_causes),
                "update_emitted": state.update_emitted,
            }
            for key, state in self.buckets.items()
        }

    def policy_update_snapshot(self):
        return list(self.policy_updates)

    def set_policy_callback(self, callback):
        self._policy_callback = callback

    def close(self):
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=0.1)

    def _run(self):
        while not self._stop:
            try:
                record = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self.consume(record)
            self.queue.task_done()

    def consume(self, record):
        self.records.append(record)
        key = self._bucket_key(record)
        state = self.buckets.get(key)
        if state is None:
            state = AsyncBucketState(records=deque(maxlen=self.bucket_limit))
            self.buckets[key] = state
        state.records.append(record)
        for cause in self._diagnose(record):
            state.diagnosed_causes.add(cause)
        self._maybe_emit_policy_update(key, state)

    def _bucket_key(self, record):
        return (
            record.get("func_id") or record.get("function_id") or "",
            record.get("side") or record.get("selected_side") or "",
            access_depth_bucket(
                record.get("estimated_ad", record.get("estimated_access_depth"))
            ),
            record.get("object_size_bucket") or "unknown",
            record.get("cache_state") or "unknown",
        )

    def _diagnose(self, record):
        causes = []
        if int(record.get("cache_misses") or 0) > 0:
            causes.append("cold access or cache locality changed")
        if int(record.get("max_object_size") or -1) > 100 * 1024:
            causes.append("large object transfer")
        estimated_ad = record.get("estimated_ad", record.get("estimated_access_depth"))
        try:
            estimated_ad = int(round(float(estimated_ad)))
        except (TypeError, ValueError):
            estimated_ad = None
        actual_accesses = int(record.get("get_count") or 0) + int(record.get("put_count") or 0)
        if estimated_ad is not None and actual_accesses != estimated_ad:
            causes.append("access-depth prediction error")
        actual_ns = int(record.get("actual_ns") or 0)
        if (
            (record.get("side") or record.get("selected_side")) == "storage"
            and record.get("object_size_bucket", "unknown") == "unknown"
            and actual_ns > 1000000
        ):
            causes.append("possible storage-side load or FUNC queue delay")
        return causes

    def _maybe_emit_policy_update(self, key, state):
        if state.update_emitted or len(state.records) < self.min_records:
            return
        predicted = [int(r.get("predicted_ns") or 0) for r in state.records]
        actual = [int(r.get("actual_ns") or 0) for r in state.records]
        predicted = [value for value in predicted if value > 0]
        actual = [value for value in actual if value > 0]
        if len(predicted) < self.min_records or len(actual) < self.min_records:
            return

        median_predicted = statistics.median(predicted)
        median_actual = statistics.median(actual)
        if (
            median_actual > self.residual_factor * median_predicted
            and median_actual - median_predicted > self.residual_min_ns
        ):
            update = PolicyUpdate(
                bucket_key=key,
                func_id=key[0],
                side=key[1],
                median_actual_ns=median_actual,
                median_predicted_ns=median_predicted,
                diagnosis=tuple(sorted(state.diagnosed_causes)),
                record_count=len(state.records),
            )
            self.policy_updates.append(update)
            state.update_emitted = True
            if self._policy_callback is not None:
                self._policy_callback(update)


def get_async_profiler():
    global _ASYNC_PROFILER
    if _ASYNC_PROFILER is None:
        _ASYNC_PROFILER = AsyncProfiler.from_env()
    return _ASYNC_PROFILER
