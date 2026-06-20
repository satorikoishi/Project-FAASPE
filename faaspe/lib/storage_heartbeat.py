import csv
import os
import threading
import time

from jkv_client import JKVClient


def env_enabled(name, default="0"):
    return os.getenv(name, default) not in {"", "0", "false", "False", "no", "off"}


def load_trace(path):
    if not path:
        return [(0, 0)]
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            duration_ms = int(float(row.get("duration_ms", 0) or 0))
            extra_load_us = int(float(row.get("extra_load_us", 0) or 0))
            if duration_ms > 0:
                rows.append((duration_ms, max(0, extra_load_us)))
    return rows or [(0, 0)]


class StorageHeartbeatMonitor:
    def __init__(
        self,
        push_addr,
        pull_addr,
        enabled=False,
        interval_ms=500,
        trace_path="",
        manual=False,
    ):
        self.push_addr = push_addr
        self.pull_addr = pull_addr
        self.enabled = enabled
        self.interval_ms = max(1, int(interval_ms))
        self.trace = load_trace(trace_path)
        self.trace_path = trace_path
        self.manual = manual
        self._lock = threading.Lock()
        self._latest_load_us = 0.0
        self._latest_requested_load_us = 0
        self._latest_observed_latency_us = 0.0
        self._baseline_latency_us = None
        self._sample_count = 0
        self._sequence = 0
        self._client = None
        self._thread = None
        self._stop = False

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("PUSH_ADDR", ""),
            os.getenv("PULL_ADDR", ""),
            enabled=env_enabled("FAASPE_STORAGE_HEARTBEAT_ENABLED", "0"),
            interval_ms=int(os.getenv("FAASPE_STORAGE_HEARTBEAT_INTERVAL_MS", "500")),
            trace_path=os.getenv("FAASPE_STORAGE_HEARTBEAT_TRACE", ""),
            manual=env_enabled("FAASPE_STORAGE_HEARTBEAT_MANUAL", "0"),
        )

    def start(self):
        if not self.enabled or self.manual or self._thread is not None:
            return
        if self._client is None and (not self.push_addr or not self.pull_addr):
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def attach_client(self, client):
        """Use the workload JKV client so heartbeat responses cannot be stolen."""
        if client is None:
            return
        with self._lock:
            if self._client is None:
                self._client = client
        self.start()

    def latest_load_us(self):
        self.start()
        with self._lock:
            return self._latest_load_us

    def latest_requested_load_us(self):
        self.start()
        with self._lock:
            return self._latest_requested_load_us

    def latest_observed_latency_us(self):
        self.start()
        with self._lock:
            return self._latest_observed_latency_us

    def sample_count(self):
        self.start()
        with self._lock:
            return self._sample_count

    def sample_once(self, extra_load_us):
        if not self.enabled:
            return False
        client = self._client
        if client is None:
            if not self.push_addr or not self.pull_addr:
                return False
            client = JKVClient(self.push_addr, self.pull_addr)
            with self._lock:
                if self._client is None:
                    self._client = client
        self._sequence += 1
        started = time.perf_counter()
        ok = False
        try:
            ok, _ = client.heartbeat(self._sequence, extra_load_us)
        except Exception:
            ok = False
        observed_us = (time.perf_counter() - started) * 1e6
        self._record_sample(extra_load_us, observed_us, ok)
        return ok

    def snapshot(self):
        self.start()
        with self._lock:
            return {
                "storage_heartbeat_enabled": int(self.enabled),
                "storage_heartbeat_interval_ms": self.interval_ms if self.enabled else 0,
                "storage_heartbeat_trace": self.trace_path,
                "storage_heartbeat_requested_load_us": self._latest_requested_load_us,
                "storage_heartbeat_observed_latency_us": self._latest_observed_latency_us,
                "storage_heartbeat_estimated_load_us": self._latest_load_us,
                "storage_heartbeat_samples": self._sample_count,
            }

    def _run(self):
        client = self._client or JKVClient(self.push_addr, self.pull_addr)
        trace_start = time.monotonic()
        while not self._stop:
            requested = self._current_extra_load_us(trace_start)
            self._sequence += 1
            started = time.perf_counter()
            ok = False
            try:
                ok, _ = client.heartbeat(self._sequence, requested)
            except Exception:
                ok = False
            observed_us = (time.perf_counter() - started) * 1e6
            self._record_sample(requested, observed_us, ok)
            time.sleep(self.interval_ms / 1000.0)

    def _current_extra_load_us(self, trace_start):
        if len(self.trace) == 1 and self.trace[0][0] == 0:
            return self.trace[0][1]
        elapsed_ms = (time.monotonic() - trace_start) * 1000.0
        total_ms = sum(duration for duration, _ in self.trace)
        if total_ms <= 0:
            return self.trace[-1][1]
        cursor = elapsed_ms % total_ms
        for duration_ms, extra_load_us in self.trace:
            if cursor < duration_ms:
                return extra_load_us
            cursor -= duration_ms
        return self.trace[-1][1]

    def _record_sample(self, requested_load_us, observed_us, ok):
        with self._lock:
            if ok:
                if self._baseline_latency_us is None or observed_us < self._baseline_latency_us:
                    self._baseline_latency_us = observed_us
                self._latest_observed_latency_us = observed_us
                self._latest_load_us = max(0.0, observed_us - self._baseline_latency_us)
                self._latest_requested_load_us = requested_load_us
                self._sample_count += 1


_MONITOR = None


def get_storage_heartbeat_monitor():
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = StorageHeartbeatMonitor.from_env()
    return _MONITOR
