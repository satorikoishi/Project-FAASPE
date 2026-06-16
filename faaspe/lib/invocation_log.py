import json
import os
import time
from collections import deque


FALSE_VALUES = {"", "0", "false", "False", "no", "off"}
DEFAULT_PATH = "./results/invocations.jsonl"
DEFAULT_MAX_RECORDS = 100000
BACKEND_MEMORY = "memory"
BACKEND_FILE = "file"


class InvocationLogger:
    def __init__(self):
        self.enabled = os.getenv("FAASPE_INVOCATION_LOG_ENABLED", "0") not in FALSE_VALUES
        self.path = os.getenv("FAASPE_INVOCATION_LOG_PATH", DEFAULT_PATH)
        self.backend = os.getenv("FAASPE_INVOCATION_LOG_BACKEND", BACKEND_MEMORY).lower()
        if self.backend not in {BACKEND_MEMORY, BACKEND_FILE}:
            self.backend = BACKEND_MEMORY
        self.max_records = int(
            os.getenv("FAASPE_INVOCATION_LOG_MAX_RECORDS", DEFAULT_MAX_RECORDS)
        )
        self.records = deque(maxlen=self.max_records)
        self._file = None

    def is_enabled(self):
        return self.enabled

    def write(self, record):
        if not self.enabled:
            return
        if self.backend == BACKEND_MEMORY:
            self.records.append(record)
            return

        if self._file is None:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._file = open(self.path, "a")
        self._file.write(json.dumps(record) + "\n")

    def snapshot(self):
        return list(self.records)

    def clear(self):
        self.records.clear()

    def flush_to_file(self, path=None):
        if not self.enabled or self.backend != BACKEND_MEMORY:
            return
        output_path = path or self.path
        directory = os.path.dirname(output_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(output_path, "w") as f:
            for record in self.records:
                f.write(json.dumps(record) + "\n")

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None


_LOGGER = None


def get_invocation_logger():
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = InvocationLogger()
    return _LOGGER


def now_us():
    return time.perf_counter() * 1e6
