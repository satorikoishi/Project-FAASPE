import csv
import logging
import os

from benchmark import Benchmark
from jkv_client import JKVClient


logging.basicConfig(format="%(message)s", level=logging.INFO)
DEFAULT_KEY_COUNT = 1
DEFAULT_VALUE_LEN = 1024


def load_depth_trace(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "depth" in reader.fieldnames:
            for row in reader:
                rows.append(
                    {
                        "depth": int(row["depth"]),
                        "size": int(row["size"]) if row.get("size") else None,
                    }
                )
            return rows

    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0].strip().lower() == "depth":
                continue
            rows.append({"depth": int(row[0]), "size": None})
    return rows


class PlacementTrace(Benchmark):
    def __init__(self, client, name, num_operations, strategy, trace_file, access="hot"):
        self.trace_file = trace_file
        self.trace = load_depth_trace(trace_file)
        if not self.trace:
            raise ValueError(f"empty depth trace: {trace_file}")
        self.trace_sizes = sorted({row["size"] for row in self.trace if row["size"]})
        super().__init__(client, name, num_operations, strategy, access)
        self.value_len = int(os.getenv("VALUE_LEN", str(DEFAULT_VALUE_LEN)))
        self.key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        self.results["trace_file"] = trace_file
        self.results["value_len"] = self.value_len
        self.results["trace_depths"] = ",".join(
            str(depth) for depth in sorted({row["depth"] for row in self.trace})
        )
        self.results["trace_sizes"] = ",".join(str(size) for size in self.trace_sizes)

    def init_kvs(self):
        default_size = int(os.getenv("VALUE_LEN", str(DEFAULT_VALUE_LEN)))
        sizes = self.trace_sizes or [default_size]
        key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        prefix = os.getenv("KEY_PREFIX", "placement-trace")
        for size in sizes:
            value = "a" * size
            for idx in range(key_count):
                self.client.put(f"{prefix}-{size}-{idx}", value, 1)

    def prepare_input(self, idx):
        prefix = os.getenv("KEY_PREFIX", "placement-trace")
        row = self.trace[idx % len(self.trace)]
        depth = row["depth"]
        size = row["size"] or self.value_len
        key = f"{prefix}-{size}-{idx % self.key_count}"
        return key, depth, size

    def arbiter_params(self, op_input):
        _, depth, size = op_input
        return {
            "depth": depth,
            "object_size": size,
        }

    def perform(self, op_input, placement):
        key, depth, _ = op_input
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
