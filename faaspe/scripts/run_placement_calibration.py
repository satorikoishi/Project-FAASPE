import argparse
import csv
import json
from datetime import datetime

from fabric import Connection

import runner


FUNC_NAME = "placement-calibration"
DEFAULT_OBJECT_SIZES = "1024,4096,10240,32768,65536,102400,262144,524288,1048576,2097152"


def latest_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        return
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_int_list(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def summarize_object_size(rows, margin):
    by_size = {}
    for row in rows:
        if row.get("operation") != "object_size_get":
            continue
        object_size = int(row["object_size"])
        by_size.setdefault(object_size, {})[row["variant"]] = row

    summary_rows = []
    recommended = None
    for object_size in sorted(by_size):
        pair = by_size[object_size]
        cache = pair.get("cache")
        storage = pair.get("storage")
        if not cache or not storage:
            continue
        cache_median = float(cache["median_us"])
        storage_median = float(storage["median_us"])
        storage_better = storage_median <= cache_median * (1.0 - margin)
        summary_rows.append(
            {
                "object_size": object_size,
                "cache_median_us": cache["median_us"],
                "cache_p95_us": cache.get("p95_us", ""),
                "storage_median_us": storage["median_us"],
                "storage_p95_us": storage.get("p95_us", ""),
                "storage_better": int(storage_better),
            }
        )
        if storage_better and recommended is None:
            recommended = object_size
    return recommended, summary_rows


def summarize_trigger_effect(object_summary_rows, sanity_rows):
    sanity_by_size = {}
    for row in sanity_rows:
        if row.get("operation") != "object_size_trigger_sanity":
            continue
        object_size = int(row["object_size"])
        sanity_by_size.setdefault(object_size, {})[row["variant"]] = row

    summary = []
    for row in object_summary_rows:
        object_size = int(row["object_size"])
        disabled = sanity_by_size.get(object_size, {}).get("trigger_disabled", {})
        enabled = sanity_by_size.get(object_size, {}).get("trigger_enabled", {})
        expected = "storage" if int(row["storage_better"]) else "cache"
        summary.append(
            {
                "object_size": object_size,
                "expected_faster_side": expected,
                "cache_median_us": row["cache_median_us"],
                "storage_median_us": row["storage_median_us"],
                "faaspe_placement_trigger_disabled": disabled.get("observed_placement", ""),
                "median_trigger_disabled_us": disabled.get("median_us", ""),
                "faaspe_placement_trigger_enabled": enabled.get("observed_placement", ""),
                "median_trigger_enabled_us": enabled.get("median_us", ""),
                "trigger_used_observed": enabled.get("trigger_used", ""),
                "trigger_count_enabled": enabled.get("trigger_count", ""),
            }
        )
    return summary


def first_depth_threshold(rows):
    for row in rows:
        if row.get("operation") == "recommended_storage_depth_threshold":
            return row.get("depth", "")
    return ""


def write_recommendations(output_dir, recommendations):
    json_path = output_dir / "placement_calibration_recommendations.json"
    env_path = output_dir / "placement_calibration_recommendations.env"
    with open(json_path, "w") as f:
        json.dump(recommendations, f, indent=2, sort_keys=True)
        f.write("\n")

    lines = []
    depth = recommendations.get("storage_depth_threshold")
    if depth:
        lines.append(f"FAASPE_STORAGE_DEPTH_THRESHOLD={depth}")
    lines.extend(
        [
            "JKV_OBJECT_SIZE_TRIGGER_ENABLED=1",
            "JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES="
            f"{recommendations['object_size_trigger_threshold_bytes']}",
            f"JKV_OBJECT_SIZE_TRIGGER_FUNC_NAME={recommendations['object_size_trigger_func_name']}",
        ]
    )
    with open(env_path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")


def create_function():
    client = runner.read_nodes()[0].conn_addr()
    with Connection(client) as c:
        with c.cd(runner.REMOTE_FAASPE_DIR):
            c.run(f"python3 ./platform/cli.py create {FUNC_NAME}")


def run_calibration(args):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_name = args.output_dir or f"placement-calibration-{stamp}"
    output_dir = runner.FAASPE_DIR / "results" / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    container_result_dir = f"/usr/src/app/results/{output_name}"

    if args.create_function:
        create_function()

    depth_extra = {
        "DEPTHS": args.depths,
        "VALUE_SIZES": args.value_sizes,
        "SAMPLES": args.samples,
        "WARMUP": args.warmup,
        "KEY_COUNT": args.key_count,
        "RUN_DEPTH_CALIBRATION": "1",
        "RUN_OBJECT_SIZE_CALIBRATION": "0",
        "RUN_OBJECT_SIZE_TRIGGER_SANITY": "0",
        "FAASPE_RESULT_DIR": container_result_dir,
        "_local_dir": output_name,
        "_local_file_name": "depth_calibration.csv",
        "_container_result_dir": container_result_dir,
        "_cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    }
    runner.remote_run(FUNC_NAME, args.samples, "local", **depth_extra)
    depth_csv_path = output_dir / "depth_calibration.csv"
    depth_rows = latest_rows(depth_csv_path)
    recommendation_rows = [
        row
        for row in depth_rows
        if row["operation"] == "recommended_storage_depth_threshold"
    ]
    print(depth_csv_path)
    for row in recommendation_rows:
        threshold = row["depth"]
        value_size = row["value_size"]
        print(
            f"value_size={value_size}: recommended "
            f"FAASPE_STORAGE_DEPTH_THRESHOLD={threshold}"
        )

    object_extra = {
        "OBJECT_SIZES": args.object_sizes,
        "SAMPLES": args.samples,
        "WARMUP": args.warmup,
        "KEY_COUNT": args.key_count,
        "RUN_DEPTH_CALIBRATION": "0",
        "RUN_OBJECT_SIZE_CALIBRATION": "1",
        "RUN_OBJECT_SIZE_TRIGGER_SANITY": "0",
        "FAASPE_RESULT_DIR": container_result_dir,
        "_local_dir": output_name,
        "_local_file_name": "object_size_calibration.csv",
        "_container_result_dir": container_result_dir,
        "_cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    }
    runner.remote_run(FUNC_NAME, args.samples, "local", **object_extra)
    object_csv_path = output_dir / "object_size_calibration.csv"
    object_rows = latest_rows(object_csv_path)
    crossover, object_summary_rows = summarize_object_size(object_rows, args.object_size_margin)

    threshold = crossover
    if threshold is None:
        threshold = args.default_object_size_threshold
        print(
            "No object-size crossover found; keeping default "
            f"JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES={threshold}"
        )
    else:
        print(f"recommended JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES={threshold}")

    object_sizes = parse_int_list(args.object_sizes)
    sanity_threshold = args.trigger_sanity_threshold or threshold
    sanity_rows = []
    for label, enabled in (("trigger_disabled", "0"), ("trigger_enabled", "1")):
        local_file_name = f"object_size_trigger_sanity_{label}.csv"
        sanity_extra = {
            "OBJECT_SIZES": args.object_sizes,
            "OBJECT_SIZE_TRIGGER_SANITY_SIZES": args.object_sizes,
            "OBJECT_SIZE_TRIGGER_SANITY_LABEL": label,
            "SAMPLES": args.sanity_samples,
            "WARMUP": args.sanity_warmup,
            "KEY_COUNT": args.key_count,
            "RUN_DEPTH_CALIBRATION": "0",
            "RUN_OBJECT_SIZE_CALIBRATION": "0",
            "RUN_OBJECT_SIZE_TRIGGER_SANITY": "1",
            "FAASPE_RESULT_DIR": container_result_dir,
            "_local_dir": output_name,
            "_local_file_name": local_file_name,
            "_container_result_dir": container_result_dir,
            "_cache_env": {
                "JKV_OBJECT_SIZE_TRIGGER_ENABLED": enabled,
                "JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES": str(sanity_threshold),
                "JKV_OBJECT_SIZE_TRIGGER_FUNC_NAME": args.trigger_func_name,
            },
        }
        runner.remote_run(FUNC_NAME, args.sanity_samples, "local", **sanity_extra)
        sanity_rows.extend(latest_rows(output_dir / local_file_name))
    sanity_csv_path = output_dir / "object_size_trigger_sanity.csv"
    write_csv(sanity_csv_path, sanity_rows)
    trigger_effect_rows = summarize_trigger_effect(object_summary_rows, sanity_rows)
    trigger_effect_csv_path = output_dir / "object_size_trigger_effect_summary.csv"
    write_csv(trigger_effect_csv_path, trigger_effect_rows)

    recommendations = {
        "storage_depth_threshold": first_depth_threshold(depth_rows),
        "object_size_trigger_enabled": 1,
        "object_size_trigger_threshold_bytes": threshold,
        "object_size_trigger_func_name": args.trigger_func_name,
        "object_size_margin": args.object_size_margin,
        "object_size_crossover_found": crossover is not None,
        "object_size_summary": object_summary_rows,
        "trigger_effect_summary_csv": str(trigger_effect_csv_path),
    }
    write_recommendations(output_dir, recommendations)
    return {
        "depth": depth_csv_path,
        "object_size": object_csv_path,
        "sanity": sanity_csv_path,
        "trigger_effect_summary": trigger_effect_csv_path,
        "recommendations_json": output_dir / "placement_calibration_recommendations.json",
        "recommendations_env": output_dir / "placement_calibration_recommendations.env",
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Measure cache-depth latency and storage FUNC latency on CloudLab, "
            "then recommend FAASPE_STORAGE_DEPTH_THRESHOLD."
        )
    )
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--depths", default="1,2,4,8")
    parser.add_argument("--value-sizes", default="1024")
    parser.add_argument("--object-sizes", default=DEFAULT_OBJECT_SIZES)
    parser.add_argument("--object-size-margin", type=float, default=0.05)
    parser.add_argument("--default-object-size-threshold", type=int, default=1024 * 1024)
    parser.add_argument("--trigger-func-name", default="NONE")
    parser.add_argument("--trigger-sanity-threshold", type=int, default=0)
    parser.add_argument("--sanity-samples", type=int, default=100)
    parser.add_argument("--sanity-warmup", type=int, default=10)
    parser.add_argument("--key-count", type=int, default=128)
    parser.add_argument("--output-dir", default="")
    parser.add_argument(
        "--create-function",
        action="store_true",
        help="Rebuild/recreate the placement-calibration function container first.",
    )
    args = parser.parse_args()
    run_calibration(args)


if __name__ == "__main__":
    main()
