import csv
import logging
import os

import bench_util
from benchmark import Benchmark
from jkv_client import JKVClient


logging.basicConfig(format="%(message)s", level=logging.INFO)
DEFAULT_KEY_COUNT = 1
DEFAULT_VALUE_LEN = 1024


def load_trace(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "depth": int(row["depth"]),
                    "storage_load_us": int(float(row.get("storage_load_us", 0) or 0)),
                }
            )
    if not rows:
        raise ValueError(f"empty dynamic storage load trace: {path}")
    return rows


class DynamicStorageLoad(Benchmark):
    def __init__(self, client, name, num_operations, strategy, trace_file, access="hot"):
        self.trace_file = trace_file
        self.trace = load_trace(trace_file)
        self.heartbeat_step = int(os.getenv("STORAGE_LOAD_HEARTBEAT_STEP", "5"))
        super().__init__(client, name, num_operations, strategy, access)
        self.value_len = int(os.getenv("VALUE_LEN", str(DEFAULT_VALUE_LEN)))
        self.key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        self.results["trace_file"] = trace_file
        self.results["value_len"] = self.value_len
        self.results["heartbeat_step"] = self.heartbeat_step

    def init_kvs(self):
        value = "a" * int(os.getenv("VALUE_LEN", str(DEFAULT_VALUE_LEN)))
        key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        prefix = os.getenv("KEY_PREFIX", "dynamic-storage-load")
        for idx in range(key_count):
            self.client.put(f"{prefix}-{idx}", value, 1)

    def prepare_input(self, idx):
        row = self.trace[idx % len(self.trace)]
        if self.heartbeat_step > 0 and idx % self.heartbeat_step == 0:
            bench_util.sample_storage_heartbeat(row["storage_load_us"])
        prefix = os.getenv("KEY_PREFIX", "dynamic-storage-load")
        key = f"{prefix}-{idx % self.key_count}"
        return key, row["depth"], row["storage_load_us"]

    def arbiter_params(self, op_input):
        _, depth, storage_load_us = op_input
        return {
            "depth": depth,
            "object_size": self.value_len,
            "trace_storage_load_us": storage_load_us,
        }

    def perform(self, op_input, placement):
        key, depth, storage_load_us = op_input
        if placement == "native":
            ok = True
            for _ in range(depth):
                _, _, ok = self.client.get(key)
                if not ok:
                    return False
            return ok
        if placement == "func":
            if storage_load_us > 0:
                return self.client.func("EMULATE", str(storage_load_us))
            return self.client.func("GET", key)

        ok = self.client.func("NONE", "")
        for _ in range(depth):
            _, _, ok = self.client.get(key)
            if not ok:
                return False
        return ok


def main():
    client = JKVClient(os.getenv("PUSH_ADDR"), os.getenv("PULL_ADDR"))
    workload = DynamicStorageLoad(
        client,
        os.getenv("BENCH_NAME", "dynamic-storage-load"),
        int(os.getenv("NUM_OPERATION", "1000")),
        os.getenv("STRATEGY", "local"),
        os.getenv("TRACE_FILE", "/usr/src/app/dynamic_storage_load_trace.csv"),
        os.getenv("ACCESS", "hot"),
    )
    workload.measure()


if __name__ == "__main__":
    main()
