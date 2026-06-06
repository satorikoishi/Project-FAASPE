import os
import statistics
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


class Profiler:
    """Runtime feedback and fallback profiler for FAASPE placement.

    Arbiter remains the fast path. Profiler watches observed latency against
    Arbiter's expected latency. If recent invocations exceed expectation too
    often, it explores both placements, selects the lower-median side, and
    periodically rechecks the other side.
    """

    def __init__(
        self,
        enabled=True,
        violation_factor=1.5,
        violation_window=20,
        violation_limit=3,
        explore_samples=10,
        recheck_interval=100,
        history_limit=200,
    ):
        self.enabled = enabled
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
            enabled=os.getenv("FAASPE_PROFILER_ENABLED", "1") != "0",
            violation_factor=float(os.getenv("FAASPE_PROFILER_VIOLATION_FACTOR", 1.5)),
            violation_window=int(os.getenv("FAASPE_PROFILER_VIOLATION_WINDOW", 20)),
            violation_limit=int(os.getenv("FAASPE_PROFILER_VIOLATION_LIMIT", 3)),
            explore_samples=int(os.getenv("FAASPE_PROFILER_EXPLORE_SAMPLES", 10)),
            recheck_interval=int(os.getenv("FAASPE_PROFILER_RECHECK_INTERVAL", 100)),
            history_limit=int(os.getenv("FAASPE_PROFILER_HISTORY_LIMIT", 200)),
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
        base_placement = arbiter.decide(function_name, params)
        expected = arbiter.estimate_latency_us(function_name, params, base_placement)
        if not self.enabled or base_placement not in PLACEMENTS:
            return InvocationPlan(base_placement, expected or 0.0)

        profile = self._profile(function_name)
        profile.invocations += 1

        if profile.exploring:
            placement = self._next_explore_placement(profile)
            expected = arbiter.estimate_latency_us(function_name, params, placement)
            return InvocationPlan(placement, expected or 0.0, True, "explore")

        if profile.override_placement:
            placement = profile.override_placement
            reason = "fallback"
            if (
                self.recheck_interval > 0
                and profile.invocations % self.recheck_interval == 0
            ):
                placement = opposite_placement(profile.override_placement)
                reason = "recheck"
                profile.recheck_count += 1
            expected = arbiter.estimate_latency_us(function_name, params, placement)
            return InvocationPlan(placement, expected or 0.0, True, reason)

        return InvocationPlan(base_placement, expected or 0.0)

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

        if sum(profile.recent_violations) >= self.violation_limit:
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


_PROFILER = None


def get_profiler():
    global _PROFILER
    if _PROFILER is None:
        _PROFILER = Profiler.from_env()
    return _PROFILER
