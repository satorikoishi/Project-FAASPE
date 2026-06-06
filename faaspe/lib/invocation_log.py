import json
import os
import time


FALSE_VALUES = {"", "0", "false", "False", "no", "off"}
DEFAULT_PATH = "./results/invocations.jsonl"


class InvocationLogger:
    def __init__(self):
        self.enabled = os.getenv("FAASPE_INVOCATION_LOG_ENABLED", "0") not in FALSE_VALUES
        self.path = os.getenv("FAASPE_INVOCATION_LOG_PATH", DEFAULT_PATH)
        self._file = None

    def is_enabled(self):
        return self.enabled

    def write(self, record):
        if not self.enabled:
            return
        if self._file is None:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._file = open(self.path, "a", buffering=1)
        self._file.write(json.dumps(record, sort_keys=True) + "\n")


_LOGGER = None


def get_invocation_logger():
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = InvocationLogger()
    return _LOGGER


def now_us():
    return time.perf_counter() * 1e6
