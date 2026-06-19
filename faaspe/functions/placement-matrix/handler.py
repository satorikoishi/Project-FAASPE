import logging
import os
import random

from benchmark import Benchmark
from jkv_client import JKVClient


logging.basicConfig(format="%(message)s", level=logging.INFO)
DEFAULT_KEY_COUNT = 1


class PlacementMatrix(Benchmark):
    def __init__(self, client, name, num_operations, strategy, depth, value_len, access="hot"):
        super().__init__(client, name, num_operations, strategy, access)
        self.depth = int(depth)
        self.value_len = int(value_len)
        self.key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        self.results["depth"] = self.depth
        self.results["value_len"] = self.value_len

    def init_kvs(self):
        value = "a" * int(os.getenv("VALUE_LEN", "1024"))
        key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
        prefix = os.getenv("KEY_PREFIX", "placement-matrix")
        for idx in range(key_count):
            self.client.put(f"{prefix}-{idx}", value, 1)

    def prepare_input(self, idx):
        prefix = os.getenv("KEY_PREFIX", "placement-matrix")
        return f"{prefix}-{random.randint(0, self.key_count - 1)}"

    def arbiter_params(self, op_input):
        return {
            "depth": self.depth,
            "object_size": self.value_len,
        }

    def perform(self, op_input, placement):
        if placement == "native":
            ok = True
            for _ in range(self.depth):
                _, _, ok = self.client.get(op_input)
                if not ok:
                    return False
            return ok
        if placement == "func":
            return self.client.func("GET", op_input)

        ok = self.client.func("NONE", "")
        for _ in range(self.depth):
            _, _, ok = self.client.get(op_input)
            if not ok:
                return False
        return ok


def main():
    client = JKVClient(os.getenv("PUSH_ADDR"), os.getenv("PULL_ADDR"))
    workload = PlacementMatrix(
        client,
        os.getenv("BENCH_NAME", "placement-matrix"),
        int(os.getenv("NUM_OPERATION", "1000")),
        os.getenv("STRATEGY", "local"),
        int(os.getenv("DEPTH", "1")),
        int(os.getenv("VALUE_LEN", "1024")),
        os.getenv("ACCESS", "hot"),
    )
    workload.measure()


if __name__ == "__main__":
    main()
