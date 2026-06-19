import argparse
import csv
import json
import os
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPTHS = "1,2,3,4,8"
DEFAULT_OBJECT_SIZES = "1024,10240,102400,1048576"
DEFAULT_CALIBRATION_OBJECT_SIZES = "1024,4096,10240,32768,65536,102400,262144,524288,1048576,2097152"
PUSH_ADDR = os.getenv("PUSH_ADDR", "tcp://10.10.1.1:50053")
PULL_ADDR = os.getenv("PULL_ADDR", "tcp://10.10.1.1:50054")
DEFAULT_MODEL_PATH = ROOT / "lib" / "placement_latency_model.json"
DEFAULT_JKV_DIR = ROOT.parent / "jkv"
VARIANT_CACHE_TRIGGER_THRESHOLD = os.getenv(
    "JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES", "102400"
)


VARIANTS = {
    "local": {
        "strategy": "local",
        "label": "local",
        "function_env": {},
        "cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    },
    "remote": {
        "strategy": "remote",
        "label": "remote",
        "function_env": {},
        "cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    },
    "faaspe": {
        "strategy": "faaspe",
        "label": "faaspe",
        "function_env": {},
        "cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    },
    "static-only": {
        "strategy": "faaspe",
        "label": "static-only",
        "function_env": {
            "FAASPE_PROFILE_ENABLED": "0",
            "FAASPE_PROFILER_ENABLED": "0",
            "FAASPE_ACCESS_META_ENABLED": "1",
            "FAASPE_FALLBACK_ENABLED": "0",
            "FAASPE_ARBITER_FORCE_UNKNOWN": "0",
        },
        "cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    },
    "arbiter-only": {
        "strategy": "faaspe",
        "label": "arbiter-only",
        "function_env": {
            "FAASPE_PROFILE_ENABLED": "0",
            "FAASPE_PROFILER_ENABLED": "0",
            "FAASPE_ACCESS_META_ENABLED": "1",
            "FAASPE_FALLBACK_ENABLED": "0",
            "FAASPE_ARBITER_FORCE_UNKNOWN": "0",
        },
        "cache_env": {
            "JKV_OBJECT_SIZE_TRIGGER_ENABLED": "1",
            "JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES": VARIANT_CACHE_TRIGGER_THRESHOLD,
            "JKV_OBJECT_SIZE_TRIGGER_FUNC_NAME": "NONE",
        },
    },
    "runtime-only": {
        "strategy": "faaspe",
        "label": "runtime-only",
        "function_env": {
            "FAASPE_ARBITER_FORCE_UNKNOWN": "1",
            "FAASPE_PROFILE_ENABLED": "1",
            "FAASPE_PROFILER_ENABLED": "1",
            "FAASPE_FALLBACK_ENABLED": "1",
            "FAASPE_PROFILER_EXPLORE_ON_UNKNOWN": "1",
            "FAASPE_PROFILER_RECHECK_INTERVAL": "0",
        },
        "cache_env": {"JKV_OBJECT_SIZE_TRIGGER_ENABLED": "0"},
    },
}


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


def restart_function_container(function_name):
    subprocess.run(["docker", "restart", f"faaspe-{function_name}"], check=True)
    time.sleep(0.5)


def restart_cache_server(jkv_dir, cache_env, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pkill", "-x", "cache_server"], check=False)
    time.sleep(0.5)
    env = os.environ.copy()
    env.update({key: str(value) for key, value in cache_env.items()})
    with open(log_path, "ab") as log_file:
        subprocess.Popen(
            ["./build/cache_server"],
            cwd=jkv_dir,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(1.0)


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


def load_latency_model(path):
    with open(path) as f:
        return json.load(f)


def fixed_recommendations(model, model_path):
    return {
        "calibration_source": "fixed",
        "placement_latency_model_file": str(model_path),
        "placement_latency_model_env_path": Path(model_path).name,
        "placement_latency_model": model,
    }


def selected_side(row):
    variant = row.get("variant") or row.get("strategy")
    if variant == "local":
        return "local"
    if variant == "remote":
        return "remote"
    native_count = int(float(row.get("native_count") or 0))
    func_count = int(float(row.get("func_count") or 0))
    return "local" if native_count >= func_count else "remote"


def placement_correct_rate(row, oracle_side):
    num_op = int(float(row.get("num_op") or 0))
    if num_op <= 0:
        return ""
    variant = row.get("variant") or row.get("strategy")
    if variant == "local":
        return 1.0 if oracle_side == "local" else 0.0
    if variant == "remote":
        return 1.0 if oracle_side == "remote" else 0.0
    native_count = int(float(row.get("native_count") or 0))
    func_count = int(float(row.get("func_count") or 0))
    if oracle_side == "local":
        return native_count / num_op
    return func_count / num_op


def add_oracle_metrics(rows):
    baselines = {}
    for row in rows:
        if row["variant"] not in ("local", "remote"):
            continue
        key = (int(row["depth"]), int(row["object_size"]))
        baselines.setdefault(key, {})[row["variant"]] = row

    oracle_by_case = {}
    for key, entries in baselines.items():
        local = entries.get("local")
        remote = entries.get("remote")
        if not local or not remote:
            continue
        local_median = float(local["median_ms"])
        remote_median = float(remote["median_ms"])
        if local_median <= remote_median:
            oracle = local
            side = "local"
        else:
            oracle = remote
            side = "remote"
        oracle_by_case[key] = {
            "oracle_side": side,
            "oracle_median_ms": float(oracle["median_ms"]),
            "oracle_total_time_s": float(oracle["total_time_s"]),
        }

    metric_rows = []
    for row in rows:
        key = (int(row["depth"]), int(row["object_size"]))
        oracle = oracle_by_case.get(key)
        metric_row = dict(row)
        if oracle:
            oracle_median = oracle["oracle_median_ms"]
            oracle_total = oracle["oracle_total_time_s"]
            metric_row.update(
                {
                    "oracle_side": oracle["oracle_side"],
                    "selected_side": selected_side(row),
                    "placement_correct_rate": placement_correct_rate(
                        row, oracle["oracle_side"]
                    ),
                    "oracle_median_ms": oracle_median,
                    "oracle_total_time_s": oracle_total,
                    "normalized_median_latency": (
                        float(row["median_ms"]) / oracle_median
                        if oracle_median > 0
                        else ""
                    ),
                    "normalized_total_latency": (
                        float(row["total_time_s"]) / oracle_total
                        if oracle_total > 0
                        else ""
                    ),
                }
            )
        metric_rows.append(metric_row)
    return metric_rows


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
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    for variant in variants:
        if variant not in VARIANTS:
            known = ", ".join(sorted(VARIANTS))
            raise ValueError(f"Unknown variant '{variant}'. Known variants: {known}")

    jkv_dir = Path(args.jkv_dir)
    last_cache_env = None
    for depth in parse_int_list(args.depths):
        for object_size in parse_int_list(args.object_sizes):
            for variant in variants:
                spec = VARIANTS[variant]
                strategy = spec["strategy"]
                cache_env = spec["cache_env"]
                if args.manage_cache_server and cache_env != last_cache_env:
                    restart_cache_server(
                        jkv_dir,
                        cache_env,
                        output_dir / f"cache_{variant}.log",
                    )
                    last_cache_env = dict(cache_env)
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
                params.update(spec["function_env"])
                if strategy == "faaspe" and args.inject_calibrated_model:
                    params["FAASPE_PLACEMENT_LATENCY_MODEL_JSON"] = model_json
                if args.enable_invocation_log:
                    log_name = (
                        f"invocations_depth{depth}_size{object_size}_{variant}.jsonl"
                    )
                    params["FAASPE_INVOCATION_LOG_ENABLED"] = "1"
                    params["FAASPE_INVOCATION_LOG_BACKEND"] = "memory"
                    params["FAASPE_INVOCATION_LOG_PATH"] = (
                        f"{container_result_dir}/{log_name}"
                    )
                if args.restart_function_container:
                    restart_function_container("placement-matrix")
                invoke("placement-matrix", params)
                file_name = f"matrix_depth{depth}_size{object_size}_{variant}.csv"
                result_csv = output_dir / file_name
                docker_cp("placement-matrix", f"{container_result_dir}/temp.csv", result_csv)
                if args.enable_invocation_log:
                    docker_cp(
                        "placement-matrix",
                        f"{container_result_dir}/{log_name}",
                        output_dir / log_name,
                    )
                result = latest_row(result_csv)
                rows.append(
                    {
                        "depth": depth,
                        "object_size": object_size,
                        "variant": variant,
                        "strategy": strategy,
                        "median_ms": result.get("median", ""),
                        "p90_ms": result.get("p90", ""),
                        "p99_ms": result.get("p99", ""),
                        "mean_ms": result.get("mean", ""),
                        "total_time_s": result.get("total_time", ""),
                        "num_op": result.get("num_op", args.samples),
                        "native_count": result.get("native_count", ""),
                        "func_count": result.get("func_count", ""),
                        "pushback_count": result.get("pushback_count", ""),
                        "profiler_fallback_count": result.get(
                            "profiler_fallback_count", ""
                        ),
                        "profiler_override": result.get("profiler_override", ""),
                        "source_csv": file_name,
                    }
                )
    summary_path = output_dir / "placement_matrix_latency_summary.csv"
    write_csv(summary_path, rows)
    metric_rows = add_oracle_metrics(rows)
    metrics_path = output_dir / "placement_matrix_oracle_metrics.csv"
    write_csv(metrics_path, metric_rows)
    return metric_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="placement-matrix-latency-direct")
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--calibration-samples", type=int, default=300)
    parser.add_argument("--calibration-warmup", type=int, default=30)
    parser.add_argument("--depths", default=DEFAULT_DEPTHS)
    parser.add_argument("--object-sizes", default=DEFAULT_OBJECT_SIZES)
    parser.add_argument("--calibration-object-sizes", default=DEFAULT_CALIBRATION_OBJECT_SIZES)
    parser.add_argument("--key-count", type=int, default=1)
    parser.add_argument("--linear-start-depth", type=int, default=4)
    parser.add_argument("--object-size-margin", type=float, default=0.05)
    parser.add_argument("--default-object-size-threshold", type=int, default=102400)
    parser.add_argument("--inject-calibrated-model", action="store_true")
    parser.add_argument("--run-calibration", action="store_true")
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--strategies", default="local,remote,faaspe")
    parser.add_argument(
        "--variants",
        default="local,remote,faaspe,static-only,arbiter-only,runtime-only",
    )
    parser.add_argument("--jkv-dir", default=str(DEFAULT_JKV_DIR))
    parser.add_argument("--manage-cache-server", action="store_true", default=True)
    parser.add_argument("--no-manage-cache-server", dest="manage_cache_server", action="store_false")
    parser.add_argument("--restart-function-container", action="store_true", default=True)
    parser.add_argument("--no-restart-function-container", dest="restart_function_container", action="store_false")
    parser.add_argument("--enable-invocation-log", action="store_true")
    args = parser.parse_args()

    output_dir = ROOT / "results" / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    container_result_dir = f"/usr/src/app/results/{args.output_dir}"
    if args.run_calibration:
        recommendations, model = run_calibration(args, output_dir, container_result_dir)
    else:
        model = load_latency_model(args.model_path)
        recommendations = fixed_recommendations(model, args.model_path)
        rec_path = output_dir / "placement_calibration_recommendations.json"
        with open(rec_path, "w") as f:
            json.dump(recommendations, f, indent=2, sort_keys=True)
            f.write("\n")
        model_path = output_dir / "placement_latency_model.json"
        with open(model_path, "w") as f:
            json.dump(model, f, indent=2, sort_keys=True)
            f.write("\n")
    rows = run_matrix(args, output_dir, container_result_dir, model)
    print("RECOMMENDATIONS_JSON")
    print(json.dumps(recommendations, indent=2, sort_keys=True))
    print("MATRIX_SUMMARY_CSV")
    for row in rows:
        printable = dict(row)
        printable.setdefault("oracle_side", "")
        printable.setdefault("placement_correct_rate", "")
        printable.setdefault("normalized_total_latency", "")
        print(
            "{depth},{object_size},{variant},{median_ms},{native_count},{func_count},{oracle_side},{placement_correct_rate},{normalized_total_latency}".format(
                **printable
            )
        )


if __name__ == "__main__":
    main()
