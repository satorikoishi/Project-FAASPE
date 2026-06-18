import argparse
import csv
import json
from datetime import datetime

from fabric import Connection

import runner
import run_placement_calibration


FUNC_NAME = "placement-matrix"
DEFAULT_DEPTHS = "1,2,3,4,8"
DEFAULT_OBJECT_SIZES = "1024,10240,102400,1048576"


def parse_int_list(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def latest_row(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else {}


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


def create_function(name):
    client = runner.read_nodes()[0].conn_addr()
    with Connection(client) as c:
        with c.cd(runner.REMOTE_FAASPE_DIR):
            c.run(f"python3 ./platform/cli.py create {name}")


def run_calibration(args, output_name):
    calibration_args = argparse.Namespace(
        samples=args.calibration_samples,
        warmup=args.calibration_warmup,
        depths=args.depths,
        value_sizes=args.calibration_value_sizes,
        object_sizes=args.calibration_object_sizes,
        linear_start_depth=args.linear_start_depth,
        object_size_margin=args.object_size_margin,
        default_object_size_threshold=args.default_object_size_threshold,
        trigger_func_name=args.trigger_func_name,
        trigger_sanity_threshold=args.trigger_sanity_threshold,
        sanity_samples=args.sanity_samples,
        sanity_warmup=args.sanity_warmup,
        key_count=args.key_count,
        output_dir=output_name,
        create_function=args.create_functions,
    )
    return run_placement_calibration.run_calibration(calibration_args)


def run_matrix(args, output_name, model_json):
    output_dir = runner.FAASPE_DIR / "results" / output_name
    container_result_dir = f"/usr/src/app/results/{output_name}"
    rows = []
    depths = parse_int_list(args.depths)
    object_sizes = parse_int_list(args.object_sizes)
    strategies = ["local", "remote", "faaspe"]

    for depth in depths:
        for object_size in object_sizes:
            for strategy in strategies:
                local_file_name = (
                    f"matrix_depth{depth}_size{object_size}_{strategy}.csv"
                )
                extra = {
                    "DEPTH": depth,
                    "VALUE_LEN": object_size,
                    "ACCESS": "hot",
                    "KEY_COUNT": args.key_count,
                    "FAASPE_RESULT_DIR": container_result_dir,
                    "FAASPE_STORAGE_HEARTBEAT_ENABLED": "0",
                    "_local_dir": output_name,
                    "_local_file_name": local_file_name,
                    "_container_result_dir": container_result_dir,
                    "_cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
                }
                if strategy == "faaspe":
                    extra["FAASPE_PLACEMENT_LATENCY_MODEL_JSON"] = model_json

                runner.remote_run(FUNC_NAME, args.samples, strategy, **extra)
                result_path = output_dir / local_file_name
                result = latest_row(result_path)
                rows.append(
                    {
                        "depth": depth,
                        "object_size": object_size,
                        "strategy": strategy,
                        "median_ms": result.get("median", ""),
                        "p90_ms": result.get("p90", ""),
                        "p99_ms": result.get("p99", ""),
                        "mean_ms": result.get("mean", ""),
                        "total_time_s": result.get("total_time", ""),
                        "native_count": result.get("native_count", ""),
                        "func_count": result.get("func_count", ""),
                        "pushback_count": result.get("pushback_count", ""),
                        "arbiter_mean_us": result.get("arbiter_mean_us", ""),
                        "storage_heartbeat_samples": result.get(
                            "storage_heartbeat_samples", ""
                        ),
                        "source_csv": local_file_name,
                    }
                )

    summary_path = output_dir / "placement_matrix_latency_summary.csv"
    write_csv(summary_path, rows)
    return summary_path, rows


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run CloudLab placement latency checks across depth and object size."
        )
    )
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--calibration-samples", type=int, default=300)
    parser.add_argument("--calibration-warmup", type=int, default=30)
    parser.add_argument("--sanity-samples", type=int, default=50)
    parser.add_argument("--sanity-warmup", type=int, default=5)
    parser.add_argument("--depths", default=DEFAULT_DEPTHS)
    parser.add_argument("--object-sizes", default=DEFAULT_OBJECT_SIZES)
    parser.add_argument("--calibration-object-sizes", default=run_placement_calibration.DEFAULT_OBJECT_SIZES)
    parser.add_argument("--calibration-value-sizes", default="1024")
    parser.add_argument("--linear-start-depth", type=int, default=4)
    parser.add_argument("--object-size-margin", type=float, default=0.05)
    parser.add_argument("--default-object-size-threshold", type=int, default=102400)
    parser.add_argument("--trigger-func-name", default="NONE")
    parser.add_argument("--trigger-sanity-threshold", type=int, default=0)
    parser.add_argument("--key-count", type=int, default=128)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--skip-calibration", action="store_true")
    parser.add_argument("--calibration-dir", default="")
    parser.add_argument("--create-functions", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_name = args.output_dir or f"placement-matrix-latency-{stamp}"
    output_dir = runner.FAASPE_DIR / "results" / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.create_functions:
        create_function(FUNC_NAME)

    if args.skip_calibration:
        calibration_dir = runner.FAASPE_DIR / "results" / args.calibration_dir
        recommendations_path = calibration_dir / "placement_calibration_recommendations.json"
        model_path = calibration_dir / "placement_latency_model.json"
    else:
        calibration_outputs = run_calibration(args, output_name)
        recommendations_path = calibration_outputs["recommendations_json"]
        model_path = calibration_outputs["placement_latency_model"]

    with open(recommendations_path) as f:
        recommendations = json.load(f)
    with open(model_path) as f:
        model_json = json.dumps(json.load(f), sort_keys=True)

    summary_path, _ = run_matrix(args, output_name, model_json)
    print(recommendations_path)
    print(json.dumps(recommendations, indent=2, sort_keys=True))
    print(summary_path)


if __name__ == "__main__":
    main()
