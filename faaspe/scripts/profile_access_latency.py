#!/usr/bin/env python3
import argparse
import csv
import os
import statistics
import sys
import time


DEFAULT_PUSH_ADDR = "tcp://127.0.0.1:50053"
DEFAULT_PULL_ADDR = "tcp://127.0.0.1:50054"


def percentile(values, pct):
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = (len(sorted_values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    if lo == hi:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def stats_us(samples):
    return {
        "median_us": statistics.median(samples),
        "mean_us": statistics.fmean(samples),
        "p90_us": percentile(samples, 90),
        "p99_us": percentile(samples, 99),
        "min_us": min(samples),
        "max_us": max(samples),
    }


def time_us(fn):
    start = time.perf_counter()
    ok = fn()
    elapsed = (time.perf_counter() - start) * 1e6
    return elapsed, ok


def measure(samples, warmup, fn):
    for _ in range(warmup):
        fn()

    latencies = []
    success = 0
    for _ in range(samples):
        elapsed, ok = time_us(fn)
        latencies.append(elapsed)
        if ok:
            success += 1
    return latencies, success


def estimate_native_access_us(depth_results):
    if 1 in depth_results and 8 in depth_results:
        return (depth_results[8]["median_us"] - depth_results[1]["median_us"]) / 7.0
    if 1 in depth_results and 4 in depth_results:
        return (depth_results[4]["median_us"] - depth_results[1]["median_us"]) / 3.0
    if 1 in depth_results:
        return depth_results[1]["median_us"]
    return 0.0


def within_tolerance(measured, expected, tolerance_pct):
    if expected == 0:
        return measured == 0
    return abs(measured - expected) / expected * 100.0 <= tolerance_pct


def verdict(measured, expected, tolerance_pct):
    if within_tolerance(measured, expected, tolerance_pct):
        return "ok"
    if measured < expected:
        return "lower"
    return "higher"


def write_csv(path, rows):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def run_profile(args):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
    from jkv_client import JKVClient

    client = JKVClient(args.push_addr, args.pull_addr)
    value = "a" * args.value_size
    keys = [f"{args.key_prefix}-{i}" for i in range(args.key_count)]

    for idx, key in enumerate(keys):
        if not client.put(key, value, idx + 1):
            raise RuntimeError(f"failed to initialize key {key}")

    depth_results = {}
    rows = []
    for depth in args.depths:
        cursor = 0

        def native_depth():
            nonlocal cursor
            key = keys[cursor % len(keys)]
            cursor += 1
            ok = True
            for _ in range(depth):
                _, _, ok = client.get(key)
                if not ok:
                    return False
            return ok

        latencies, success = measure(args.samples, args.warmup, native_depth)
        result = stats_us(latencies)
        result.update(
            {
                "operation": f"native_depth_{depth}",
                "samples": args.samples,
                "success": success,
            }
        )
        depth_results[depth] = result
        rows.append(result)

    cursor = 0

    def storage_func_get():
        nonlocal cursor
        key = keys[cursor % len(keys)]
        cursor += 1
        return client.func("GET", key)

    latencies, success = measure(args.samples, args.warmup, storage_func_get)
    func_result = stats_us(latencies)
    func_result.update(
        {
            "operation": "storage_func_get",
            "samples": args.samples,
            "success": success,
        }
    )
    rows.append(func_result)

    native_access_us = max(0.0, estimate_native_access_us(depth_results))
    storage_func_us = func_result["median_us"]
    threshold = storage_func_us / native_access_us if native_access_us else float("inf")

    summary = [
        {
            "operation": "estimated_native_access",
            "samples": args.samples,
            "success": args.samples,
            "median_us": native_access_us,
            "mean_us": native_access_us,
            "p90_us": native_access_us,
            "p99_us": native_access_us,
            "min_us": native_access_us,
            "max_us": native_access_us,
        },
        {
            "operation": "estimated_threshold_depth",
            "samples": args.samples,
            "success": args.samples,
            "median_us": threshold,
            "mean_us": threshold,
            "p90_us": threshold,
            "p99_us": threshold,
            "min_us": threshold,
            "max_us": threshold,
        },
    ]
    rows.extend(summary)

    if args.output:
        write_csv(args.output, rows)

    print("Access latency profile")
    print(f"  push_addr: {args.push_addr}")
    print(f"  pull_addr: {args.pull_addr}")
    print(f"  samples: {args.samples}, warmup: {args.warmup}, value_size: {args.value_size}")
    for depth in args.depths:
        row = depth_results[depth]
        print(
            f"  native depth {depth}: median={row['median_us']:.2f} us, "
            f"p99={row['p99_us']:.2f} us"
        )
    print(f"  storage FUNC GET: median={storage_func_us:.2f} us, p99={func_result['p99_us']:.2f} us")
    print(f"  estimated native access: {native_access_us:.2f} us")
    print(f"  estimated threshold depth: {threshold:.2f}")
    print(
        f"  expected native access {args.expected_local_access_us:.2f} us: "
        f"{verdict(native_access_us, args.expected_local_access_us, args.tolerance_pct)}"
    )
    print(
        f"  expected storage FUNC {args.expected_storage_func_us:.2f} us: "
        f"{verdict(storage_func_us, args.expected_storage_func_us, args.tolerance_pct)}"
    )
    if args.output:
        print(f"  wrote: {args.output}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Profile cache-side GET and storage-side FUNC latency for FAASPE placement."
    )
    parser.add_argument("--push-addr", default=os.getenv("PUSH_ADDR", DEFAULT_PUSH_ADDR))
    parser.add_argument("--pull-addr", default=os.getenv("PULL_ADDR", DEFAULT_PULL_ADDR))
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--value-size", type=int, default=1024)
    parser.add_argument("--key-count", type=int, default=128)
    parser.add_argument("--key-prefix", default="profile")
    parser.add_argument("--depths", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--expected-local-access-us", type=float, default=200.0)
    parser.add_argument("--expected-storage-func-us", type=float, default=900.0)
    parser.add_argument("--tolerance-pct", type=float, default=25.0)
    parser.add_argument("--output", default="")
    return parser.parse_args()


if __name__ == "__main__":
    run_profile(parse_args())
