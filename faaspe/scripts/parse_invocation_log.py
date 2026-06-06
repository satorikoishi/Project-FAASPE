#!/usr/bin/env python3
import argparse
import json
from collections import Counter, defaultdict


def percentile(values, pct):
    if not values:
        return 0.0
    values = sorted(values)
    idx = (len(values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def stats(values):
    if not values:
        return {"count": 0, "median": 0.0, "p99": 0.0}
    return {
        "count": len(values),
        "median": percentile(values, 50),
        "p99": percentile(values, 99),
    }


def parse(path):
    placement_counts = Counter()
    workload_counts = Counter()
    fallback_count = 0
    arbiter_overheads = []
    profiler_overheads = []
    trigger_overheads = []
    latency_groups = defaultdict(list)

    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            side = row.get("selected_side", "")
            workload = row.get("function_name", "")
            placement_counts[side] += 1
            workload_counts[workload] += 1

            if row.get("fallback_triggered"):
                fallback_count += 1

            arbiter_overheads.append(float(row.get("arbiter_decision_us") or 0.0))
            profiler_overheads.append(float(row.get("profiler_update_us") or 0.0))
            trigger_overheads.append(float(row.get("trigger_check_us") or 0.0))

            latency = row.get("actual_execution_latency_us")
            if latency is not None:
                latency_groups[(workload, side)].append(float(latency))

    total = sum(placement_counts.values())
    print(f"total_invocations,{total}")
    print(f"fallback_frequency,{fallback_count / total if total else 0.0:.6f}")

    print("\nplacement_counts")
    for side, count in sorted(placement_counts.items()):
        print(f"{side},{count}")

    print("\noverhead_us")
    for name, values in (
        ("arbiter", arbiter_overheads),
        ("profiler", profiler_overheads),
        ("trigger", trigger_overheads),
    ):
        row = stats(values)
        print(f"{name},median,{row['median']:.6f},p99,{row['p99']:.6f}")

    print("\nlatency_by_workload_and_side_us")
    for (workload, side), values in sorted(latency_groups.items()):
        row = stats(values)
        print(
            f"{workload},{side},count,{row['count']},"
            f"median,{row['median']:.6f},p99,{row['p99']:.6f}"
        )


def main():
    parser = argparse.ArgumentParser(description="Summarize FAASPE invocation JSONL logs.")
    parser.add_argument("path")
    args = parser.parse_args()
    parse(args.path)


if __name__ == "__main__":
    main()
