import csv
import os
import statistics
import time

from jkv_client import JKVClient


DEFAULT_DEPTHS = "1,2,4,8"
DEFAULT_VALUE_SIZES = "1024"
DEFAULT_KEY_COUNT = 128
DEFAULT_RESULT_DIR = "/usr/src/app/results"


def parse_int_list(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()]


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
    started = time.perf_counter()
    ok = fn()
    return (time.perf_counter() - started) * 1e6, ok


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


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def initialize_keys(client, value, key_count, key_prefix):
    for idx in range(key_count):
        key = f"{key_prefix}-{idx}"
        if not client.put(key, value, idx + 1):
            raise RuntimeError(f"failed to initialize key {key}")


def recommend_threshold(depth_rows, func_median_us):
    sorted_rows = sorted(depth_rows, key=lambda row: row["depth"])
    for row in sorted_rows:
        if row["operation"] == "cache_depth" and row["median_us"] >= func_median_us:
            return row["depth"]
    if not sorted_rows:
        return ""
    return f">{max(row['depth'] for row in sorted_rows)}"


def main():
    push_addr = os.getenv("PUSH_ADDR")
    pull_addr = os.getenv("PULL_ADDR")
    samples = int(os.getenv("SAMPLES", os.getenv("NUM_OPERATION", "1000")))
    warmup = int(os.getenv("WARMUP", "100"))
    depths = parse_int_list(os.getenv("DEPTHS", DEFAULT_DEPTHS))
    value_sizes = parse_int_list(os.getenv("VALUE_SIZES", DEFAULT_VALUE_SIZES))
    key_count = int(os.getenv("KEY_COUNT", str(DEFAULT_KEY_COUNT)))
    result_dir = os.getenv("FAASPE_RESULT_DIR", DEFAULT_RESULT_DIR)
    key_prefix = os.getenv("KEY_PREFIX", "placement-calibration")

    client = JKVClient(push_addr, pull_addr)
    rows = []
    recommendations = []

    for value_size in value_sizes:
        value = "a" * value_size
        initialize_keys(client, value, key_count, f"{key_prefix}-{value_size}")
        keys = [f"{key_prefix}-{value_size}-{idx}" for idx in range(key_count)]

        depth_rows = []
        for depth in depths:
            cursor = 0

            def cache_depth():
                nonlocal cursor
                key = keys[cursor % len(keys)]
                cursor += 1
                ok = True
                for _ in range(depth):
                    _, _, ok = client.get(key)
                    if not ok:
                        return False
                return ok

            latencies, success = measure(samples, warmup, cache_depth)
            row = {
                "operation": "cache_depth",
                "value_size": value_size,
                "depth": depth,
                "samples": samples,
                "warmup": warmup,
                "success": success,
            }
            row.update(stats_us(latencies))
            rows.append(row)
            depth_rows.append(row)

        cursor = 0

        def storage_func_get():
            nonlocal cursor
            key = keys[cursor % len(keys)]
            cursor += 1
            return client.func("GET", key)

        latencies, success = measure(samples, warmup, storage_func_get)
        func_row = {
            "operation": "storage_func_get",
            "value_size": value_size,
            "depth": 0,
            "samples": samples,
            "warmup": warmup,
            "success": success,
        }
        func_row.update(stats_us(latencies))
        rows.append(func_row)

        threshold = recommend_threshold(depth_rows, func_row["median_us"])
        recommendations.append(
            {
                "operation": "recommended_storage_depth_threshold",
                "value_size": value_size,
                "depth": threshold,
                "samples": samples,
                "warmup": warmup,
                "success": samples,
                "median_us": func_row["median_us"],
                "mean_us": func_row["mean_us"],
                "p90_us": func_row["p90_us"],
                "p99_us": func_row["p99_us"],
                "min_us": func_row["min_us"],
                "max_us": func_row["max_us"],
            }
        )

    output_path = os.path.join(result_dir, "temp.csv")
    write_csv(output_path, rows + recommendations)
    for rec in recommendations:
        print(
            "value_size={value_size} recommended "
            "FAASPE_STORAGE_DEPTH_THRESHOLD={depth}".format(**rec)
        )
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
