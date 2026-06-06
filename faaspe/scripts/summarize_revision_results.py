#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


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


def median(values):
    return percentile(values, 50)


def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_runs(output_dir):
    runs = []
    for meta_path in Path(output_dir, "raw").glob("*/metadata.json"):
        run_dir = meta_path.parent
        metadata = json.loads(meta_path.read_text())
        invocations = read_jsonl(run_dir / "invocations.jsonl")
        runs.append({"metadata": metadata, "invocations": invocations, "run_dir": run_dir})
    return runs


def run_key(metadata):
    return (metadata["workload"], metadata["case_id"], metadata["repetition"])


def variant_key(metadata):
    return (
        metadata["workload"],
        metadata["case_id"],
        metadata["variant"],
        metadata["repetition"],
    )


def side_for_variant(variant):
    if variant == "CacheOnly":
        return "compute"
    if variant == "StorageOnly":
        return "storage"
    return ""


def aggregate_by_variant(runs):
    groups = defaultdict(list)
    for run in runs:
        groups[variant_key(run["metadata"])].extend(run["invocations"])
    return groups


def oracle_by_case(variant_groups):
    cache = {}
    storage = {}
    for (workload, case_id, variant, rep), rows in variant_groups.items():
        latencies = [float(row["actual_execution_latency_us"]) for row in rows]
        if not latencies:
            continue
        if variant == "CacheOnly":
            cache[(workload, case_id, rep)] = median(latencies)
        elif variant == "StorageOnly":
            storage[(workload, case_id, rep)] = median(latencies)

    oracle = {}
    for key in sorted(set(cache) & set(storage)):
        cache_latency = cache[key]
        storage_latency = storage[key]
        if cache_latency <= storage_latency:
            oracle[key] = {"side": "compute", "latency_us": cache_latency}
        else:
            oracle[key] = {"side": "storage", "latency_us": storage_latency}
    return oracle


def placement_accuracy(rows, oracle_side):
    if not rows:
        return 0.0
    correct = sum(1 for row in rows if row.get("selected_side") == oracle_side)
    return correct / len(rows)


def fallback_frequency(rows):
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.get("fallback_triggered")) / len(rows)


def overhead_stats(rows, field):
    values = [float(row.get(field) or 0.0) for row in rows]
    return median(values), percentile(values, 99)


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(output_dir):
    output_dir = Path(output_dir)
    runs = load_runs(output_dir)
    variant_groups = aggregate_by_variant(runs)
    oracle = oracle_by_case(variant_groups)

    placement_rows = []
    overhead_rows = []
    ablation_rows = []
    threshold_rows = []
    counts_rows = []

    for (workload, case_id, variant, rep), rows in sorted(variant_groups.items()):
        latencies = [float(row["actual_execution_latency_us"]) for row in rows]
        if not latencies:
            continue

        oracle_info = oracle.get((workload, case_id, rep), {"side": "", "latency_us": 0.0})
        normalized = median(latencies) / oracle_info["latency_us"] if oracle_info["latency_us"] else 0.0
        accuracy = placement_accuracy(rows, oracle_info["side"]) if oracle_info["side"] else 0.0
        fallback_freq = fallback_frequency(rows)

        placement_counts = Counter(row.get("selected_side", "") for row in rows)
        for side, count in sorted(placement_counts.items()):
            counts_rows.append(
                {
                    "workload": workload,
                    "case_id": case_id,
                    "variant": variant,
                    "repetition": rep,
                    "side": side,
                    "count": count,
                }
            )

        placement_row = {
            "workload": workload,
            "case_id": case_id,
            "variant": variant,
            "repetition": rep,
            "oracle_side": oracle_info["side"],
            "oracle_latency_us": oracle_info["latency_us"],
            "median_latency_us": median(latencies),
            "p99_latency_us": percentile(latencies, 99),
            "placement_accuracy": accuracy,
            "normalized_latency": normalized,
            "fallback_frequency": fallback_freq,
        }
        placement_rows.append(placement_row)

        arb_median, arb_p99 = overhead_stats(rows, "arbiter_decision_us")
        prof_median, prof_p99 = overhead_stats(rows, "profiler_update_us")
        trigger_median, trigger_p99 = overhead_stats(rows, "trigger_check_us")
        ast_median, ast_p99 = overhead_stats(rows, "ast_analysis_us")
        explore_latencies = [
            float(row["actual_execution_latency_us"])
            for row in rows
            if row.get("fallback_phase") == "explore"
        ]
        overhead_rows.append(
            {
                "workload": workload,
                "case_id": case_id,
                "variant": variant,
                "repetition": rep,
                "arbiter_median_us": arb_median,
                "arbiter_p99_us": arb_p99,
                "profiler_median_us": prof_median,
                "profiler_p99_us": prof_p99,
                "trigger_median_us": trigger_median,
                "trigger_p99_us": trigger_p99,
                "ast_analysis_median_us": ast_median,
                "ast_analysis_p99_us": ast_p99,
                "fallback_explore_count": len(explore_latencies),
                "fallback_explore_median_latency_us": median(explore_latencies),
            }
        )

        if variant in {"CacheOnly", "StorageOnly", "StaticOnly", "NoFallback", "FullFaaSPE"}:
            ablation_rows.append(placement_row)
        if variant.startswith("Threshold") and variant.endswith("x"):
            multiplier = variant[len("Threshold") : -1]
            threshold_row = dict(placement_row)
            threshold_row["threshold_multiplier"] = multiplier
            threshold_rows.append(threshold_row)

    summary_dir = output_dir / "summary"
    write_csv(
        summary_dir / "placement_accuracy.csv",
        placement_rows,
        [
            "workload",
            "case_id",
            "variant",
            "repetition",
            "oracle_side",
            "oracle_latency_us",
            "median_latency_us",
            "p99_latency_us",
            "placement_accuracy",
            "normalized_latency",
            "fallback_frequency",
        ],
    )
    write_csv(
        summary_dir / "ablation.csv",
        ablation_rows,
        [
            "workload",
            "case_id",
            "variant",
            "repetition",
            "oracle_side",
            "oracle_latency_us",
            "median_latency_us",
            "p99_latency_us",
            "placement_accuracy",
            "normalized_latency",
            "fallback_frequency",
        ],
    )
    write_csv(
        summary_dir / "overhead_breakdown.csv",
        overhead_rows,
        [
            "workload",
            "case_id",
            "variant",
            "repetition",
            "arbiter_median_us",
            "arbiter_p99_us",
            "profiler_median_us",
            "profiler_p99_us",
            "trigger_median_us",
            "trigger_p99_us",
            "ast_analysis_median_us",
            "ast_analysis_p99_us",
            "fallback_explore_count",
            "fallback_explore_median_latency_us",
        ],
    )
    write_csv(
        summary_dir / "threshold_sensitivity.csv",
        threshold_rows,
        [
            "workload",
            "case_id",
            "variant",
            "threshold_multiplier",
            "repetition",
            "oracle_side",
            "oracle_latency_us",
            "median_latency_us",
            "p99_latency_us",
            "placement_accuracy",
            "normalized_latency",
            "fallback_frequency",
        ],
    )
    write_csv(
        summary_dir / "placement_counts.csv",
        counts_rows,
        ["workload", "case_id", "variant", "repetition", "side", "count"],
    )
    print(f"Wrote revision summaries to {summary_dir}")


def main():
    parser = argparse.ArgumentParser(description="Summarize major-revision experiment logs.")
    parser.add_argument("output_dir")
    args = parser.parse_args()
    summarize(args.output_dir)


if __name__ == "__main__":
    main()
