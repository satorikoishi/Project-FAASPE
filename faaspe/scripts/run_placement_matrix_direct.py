import argparse
import csv
import json
import os
import statistics
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPTHS = "1,2,3,4,8"
DEFAULT_OBJECT_SIZES = "1024,10240,102400,1048576"
DEFAULT_CALIBRATION_OBJECT_SIZES = "1024,4096,10240,32768,65536,102400,262144,524288,1048576,2097152"
PUSH_ADDR = os.getenv("PUSH_ADDR", "tcp://10.10.1.1:50053")
PULL_ADDR = os.getenv("PULL_ADDR", "tcp://10.10.1.1:50054")


def parse_int_list(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def invoke(function_name, params):
    request = urllib.request.Request(
        f"http://127.0.0.1:5000/functions/{function_name}/invoke",
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.loads(response.read().decode("utf-8"))


def docker_cp(function_name, container_path, local_path):
    local_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "docker",
            "cp",
            f"faaspe-{function_name}:{container_path}",
            str(local_path),
        ],
        check=True,
    )


def read_rows(path):
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


def median_float(values):
    values = [float(value) for value in values if value not in ("", None)]
    return statistics.median(values) if values else 0.0


def summarize_object_size(rows, margin):
    by_size = {}
    for row in rows:
        if row.get("operation") == "object_size_get":
            by_size.setdefault(int(row["object_size"]), {})[row["variant"]] = row

    summary = []
    crossover = None
    for object_size in sorted(by_size):
        cache = by_size[object_size].get("cache")
        storage = by_size[object_size].get("storage")
        if not cache or not storage:
            continue
        cache_median = float(cache["median_us"])
        storage_median = float(storage["median_us"])
        storage_better = storage_median <= cache_median * (1.0 - margin)
        summary.append(
            {
                "object_size": object_size,
                "cache_median_us": cache["median_us"],
                "cache_p95_us": cache.get("p95_us", ""),
                "storage_median_us": storage["median_us"],
                "storage_p95_us": storage.get("p95_us", ""),
                "storage_better": int(storage_better),
            }
        )
        if storage_better and crossover is None:
            crossover = object_size
    return crossover, summary


def build_latency_model(depth_rows, object_rows, linear_start_depth):
    by_depth = {}
    for row in depth_rows:
        if row.get("operation") != "cache_depth":
            continue
        depth = int(float(row.get("depth", 0) or 0))
        if 0 < depth < linear_start_depth:
            by_depth.setdefault(depth, []).append(row.get("median_us"))

    object_buckets = []
    for row in object_rows:
        if row.get("operation") == "object_size_get" and row.get("variant") == "cache":
            object_buckets.append(
                {
                    "max_bytes": int(row["object_size"]),
                    "latency_us": float(row["median_us"]),
                }
            )
    object_buckets.sort(key=lambda bucket: bucket["max_bytes"])

    storage_base_candidates = [
        row.get("median_us")
        for row in depth_rows
        if row.get("operation") == "storage_func_get"
    ]
    return {
        "linear_start_depth": int(linear_start_depth),
        "small_depth_cache_latency_us": {
            str(depth): median_float(values) for depth, values in sorted(by_depth.items())
        },
        "cache_object_size_latency_us": object_buckets,
        "storage_base_latency_us": median_float(storage_base_candidates),
    }


def latest_row(path):
    rows = read_rows(path)
    return rows[-1] if rows else {}


def calibration_params(args, result_dir):
    return {
        "BENCH_NAME": "placement-calibration",
        "NUM_OPERATION": args.calibration_samples,
        "STRATEGY": "local",
        "PUSH_ADDR": PUSH_ADDR,
        "PULL_ADDR": PULL_ADDR,
        "SAMPLES": args.calibration_samples,
        "WARMUP": args.calibration_warmup,
        "KEY_COUNT": args.key_count,
        "FAASPE_RESULT_DIR": result_dir,
        "FAASPE_STORAGE_HEARTBEAT_ENABLED": "0",
    }


def run_calibration(args, output_dir, container_result_dir):
    params = calibration_params(args, container_result_dir)
    params.update(
        {
            "DEPTHS": args.depths,
            "VALUE_SIZES": "1024",
            "RUN_DEPTH_CALIBRATION": "1",
            "RUN_OBJECT_SIZE_CALIBRATION": "0",
            "RUN_OBJECT_SIZE_TRIGGER_SANITY": "0",
        }
    )
    invoke("placement-calibration", params)
    depth_csv = output_dir / "depth_calibration.csv"
    docker_cp("placement-calibration", f"{container_result_dir}/temp.csv", depth_csv)
    depth_rows = read_rows(depth_csv)

    params = calibration_params(args, container_result_dir)
    params.update(
        {
            "OBJECT_SIZES": args.calibration_object_sizes,
            "RUN_DEPTH_CALIBRATION": "0",
            "RUN_OBJECT_SIZE_CALIBRATION": "1",
            "RUN_OBJECT_SIZE_TRIGGER_SANITY": "0",
        }
    )
    invoke("placement-calibration", params)
    object_csv = output_dir / "object_size_calibration.csv"
    docker_cp("placement-calibration", f"{container_result_dir}/temp.csv", object_csv)
    object_rows = read_rows(object_csv)

    crossover, object_summary = summarize_object_size(object_rows, args.object_size_margin)
    threshold = crossover or args.default_object_size_threshold
    model = build_latency_model(depth_rows, object_rows, args.linear_start_depth)
    model_path = output_dir / "placement_latency_model.json"
    with open(model_path, "w") as f:
        json.dump(model, f, indent=2, sort_keys=True)
        f.write("\n")

    recommendations = {
        "storage_depth_threshold": next(
            (
                row.get("depth")
                for row in depth_rows
                if row.get("operation") == "recommended_storage_depth_threshold"
            ),
            "",
        ),
        "object_size_trigger_enabled": 1,
        "object_size_trigger_threshold_bytes": threshold,
        "object_size_trigger_func_name": "NONE",
        "object_size_margin": args.object_size_margin,
        "object_size_crossover_found": crossover is not None,
        "object_size_summary": object_summary,
        "placement_latency_model_file": str(model_path),
        "placement_latency_model_env_path": model_path.name,
        "placement_latency_model": model,
    }
    rec_path = output_dir / "placement_calibration_recommendations.json"
    with open(rec_path, "w") as f:
        json.dump(recommendations, f, indent=2, sort_keys=True)
        f.write("\n")
    return recommendations, model


def run_matrix(args, output_dir, container_result_dir, model):
    rows = []
    model_json = json.dumps(model, sort_keys=True)
    for depth in parse_int_list(args.depths):
        for object_size in parse_int_list(args.object_sizes):
            for strategy in ("local", "remote", "faaspe"):
                params = {
                    "BENCH_NAME": "placement-matrix",
                    "NUM_OPERATION": args.samples,
                    "STRATEGY": strategy,
                    "PUSH_ADDR": PUSH_ADDR,
                    "PULL_ADDR": PULL_ADDR,
                    "DEPTH": depth,
                    "VALUE_LEN": object_size,
                    "KEY_COUNT": args.key_count,
                    "ACCESS": "hot",
                    "FAASPE_RESULT_DIR": container_result_dir,
                    "FAASPE_STORAGE_HEARTBEAT_ENABLED": "0",
                }
                if strategy == "faaspe" and args.inject_calibrated_model:
                    params["FAASPE_PLACEMENT_LATENCY_MODEL_JSON"] = model_json
                invoke("placement-matrix", params)
                file_name = f"matrix_depth{depth}_size{object_size}_{strategy}.csv"
                result_csv = output_dir / file_name
                docker_cp("placement-matrix", f"{container_result_dir}/temp.csv", result_csv)
                result = latest_row(result_csv)
                rows.append(
                    {
                        "depth": depth,
                        "object_size": object_size,
                        "strategy": strategy,
                        "median_ms": result.get("median", ""),
                        "p90_ms": result.get("p90", ""),
                        "p99_ms": result.get("p99", ""),
                        "mean_ms": result.get("mean", ""),
                        "native_count": result.get("native_count", ""),
                        "func_count": result.get("func_count", ""),
                        "pushback_count": result.get("pushback_count", ""),
                        "source_csv": file_name,
                    }
                )
    summary_path = output_dir / "placement_matrix_latency_summary.csv"
    write_csv(summary_path, rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="placement-matrix-latency-direct")
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--calibration-samples", type=int, default=300)
    parser.add_argument("--calibration-warmup", type=int, default=30)
    parser.add_argument("--depths", default=DEFAULT_DEPTHS)
    parser.add_argument("--object-sizes", default=DEFAULT_OBJECT_SIZES)
    parser.add_argument("--calibration-object-sizes", default=DEFAULT_CALIBRATION_OBJECT_SIZES)
    parser.add_argument("--key-count", type=int, default=128)
    parser.add_argument("--linear-start-depth", type=int, default=4)
    parser.add_argument("--object-size-margin", type=float, default=0.05)
    parser.add_argument("--default-object-size-threshold", type=int, default=102400)
    parser.add_argument("--inject-calibrated-model", action="store_true")
    args = parser.parse_args()

    output_dir = ROOT / "results" / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    container_result_dir = f"/usr/src/app/results/{args.output_dir}"
    recommendations, model = run_calibration(args, output_dir, container_result_dir)
    rows = run_matrix(args, output_dir, container_result_dir, model)
    print("RECOMMENDATIONS_JSON")
    print(json.dumps(recommendations, indent=2, sort_keys=True))
    print("MATRIX_SUMMARY_CSV")
    for row in rows:
        print(
            "{depth},{object_size},{strategy},{median_ms},{native_count},{func_count}".format(
                **row
            )
        )


if __name__ == "__main__":
    main()
