import csv
import logging
import os

from benchmark import Benchmark
from jkv_client import JKVClient


logging.basicConfig(format="%(message)s", level=logging.INFO)
DEFAULT_KEY_COUNT = 1
DEFAULT_VALUE_LEN = 1024


def load_depth_trace(path):
    depths = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "depth" in reader.fieldnames:
            for row in reader:
                depths.append(int(row["depth"]))
            return depths

    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0].strip().lower() == "depth":
                continue
            depths.append(int(row[0]))
    return depths


class PlacementTrace(Benchmark):
    def __init__(self, client, name, num_operations, strategy, trace_file, access="hot"):
        self.trace_file = trace_file
        self.depths = load_depth_trace(trace_file)
        if not self.depths:
            raise ValueError(f"empty depth trace: {trace_file}")
        super().__init__(client, name, num_operations, strategy, access)
        self.value_len = int(os.getenv("VALUE_LEN", str(DEFAULT_VALUE_LEN)))
        self.key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        self.results["trace_file"] = trace_file
        self.results["value_len"] = self.value_len
        self.results["trace_depths"] = ",".join(str(depth) for depth in sorted(set(self.depths)))

    def init_kvs(self):
        value = "a" * int(os.getenv("VALUE_LEN", str(DEFAULT_VALUE_LEN)))
        key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        prefix = os.getenv("KEY_PREFIX", "placement-trace")
        for idx in range(key_count):
            self.client.put(f"{prefix}-{idx}", value, 1)

    def prepare_input(self, idx):
        prefix = os.getenv("KEY_PREFIX", "placement-trace")
        key = f"{prefix}-{idx % self.key_count}"
        depth = self.depths[idx % len(self.depths)]
        return key, depth

    def arbiter_params(self, op_input):
        _, depth = op_input
        return {
            "depth": depth,
            "object_size": self.value_len,
        }

    def perform(self, op_input, placement):
        key, depth = op_input
        if placement == "native":
            ok = True
            for _ in range(depth):
                _, _, ok = self.client.get(key)
                if not ok:
                    return False
            return ok
        if placement == "func":
            return self.client.func("GET", key)

        ok = self.client.func("NONE", "")
        for _ in range(depth):
            _, _, ok = self.client.get(key)
            if not ok:
                return False
        return ok


def main():
    client = JKVClient(os.getenv("PUSH_ADDR"), os.getenv("PULL_ADDR"))
    workload = PlacementTrace(
        client,
        os.getenv("BENCH_NAME", "placement-trace"),
        int(os.getenv("NUM_OPERATION", "1000")),
        os.getenv("STRATEGY", "local"),
        os.getenv("TRACE_FILE", "/usr/src/app/depth_trace.csv"),
        os.getenv("ACCESS", "hot"),
    )
    workload.measure()


if __name__ == "__main__":
    main()
