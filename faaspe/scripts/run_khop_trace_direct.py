import argparse
import json
import shutil
from pathlib import Path

from run_placement_matrix_direct import (
    DEFAULT_JKV_DIR,
    DEFAULT_MODEL_PATH,
    DEFAULT_VARIANT_CONFIG_PATH,
    PUSH_ADDR,
    PULL_ADDR,
    docker_cp,
    fixed_recommendations,
    invoke,
    load_latency_model,
    load_variant_config,
    read_jsonl,
    read_rows,
    record_latency_us,
    record_side,
    restart_cache_server,
    restart_function_container,
    write_csv,
    write_variant_config_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
FUNC_NAME = "k-hop"
DEFAULT_TRACE_PATH = ROOT / "functions" / FUNC_NAME / "khop_trace.csv"
DEFAULT_VARIANTS = "local,remote,faaspe,static-only,arbiter-only,runtime-only,khop-oracle"
KHOP_FAASPE_RECHECK_INTERVAL = "100"


def resolve_trace_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def docker_cp_to_container(function_name, local_path, container_path):
    import subprocess

    subprocess.run(
        [
            "docker",
            "cp",
            str(local_path),
            f"faaspe-{function_name}:{container_path}",
        ],
        check=True,
    )


def latest_row(path):
    rows = read_rows(path)
    return rows[-1] if rows else {}


def selected_side_from_counts(row):
    native_count = int(float(row.get("native_count") or 0))
    func_count = int(float(row.get("func_count") or 0))
    return "local" if native_count >= func_count else "remote"


def add_oracle_metrics(rows, output_dir):
    oracle = next((row for row in rows if row["variant"] == "khop-oracle"), None)
    if oracle is None:
        return rows

    oracle_records = read_jsonl(output_dir / oracle.get("source_invocation_log", ""))
    oracle_total = float(oracle.get("total_time_s") or 0)
    metric_rows = []
    for row in rows:
        metric = dict(row)
        metric["oracle_variant"] = "khop-oracle"
        metric["selected_side"] = selected_side_from_counts(row)
        metric["oracle_total_time_s"] = oracle_total
        metric["normalized_total_latency"] = (
            float(row["total_time_s"]) / oracle_total if oracle_total > 0 else ""
        )

        row_records = read_jsonl(output_dir / row.get("source_invocation_log", ""))
        count = min(len(row_records), len(oracle_records))
        correct = 0
        regret_cost_us = 0.0
        oracle_cost_us = 0.0
        for idx in range(count):
            oracle_side = record_side(oracle_records[idx], "khop-oracle")
            row_side = record_side(row_records[idx], row.get("variant", ""))
            oracle_latency_us = record_latency_us(oracle_records[idx])
            row_latency_us = record_latency_us(row_records[idx])
            if oracle_latency_us <= 0:
                continue
            oracle_cost_us += oracle_latency_us
            if row_side == oracle_side:
                correct += 1
                regret_cost_us += oracle_latency_us
            else:
                regret_cost_us += max(row_latency_us, oracle_latency_us)
        metric["placement_correct_rate"] = correct / count if count > 0 else ""
        metric["normalized_regret"] = (
            regret_cost_us / oracle_cost_us if oracle_cost_us > 0 else ""
        )
        metric_rows.append(metric)
    return metric_rows


def run_trace(args, output_dir, container_result_dir, model):
    rows = []
    model_json = json.dumps(model, sort_keys=True)
    variant_config = load_variant_config(args.variant_config)
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    for variant in variants:
        if variant not in variant_config:
            known = ", ".join(sorted(variant_config))
            raise ValueError(f"Unknown variant '{variant}'. Known variants: {known}")

    trace_path = resolve_trace_path(args.trace_file)
    if not trace_path.exists():
        raise FileNotFoundError(f"trace file not found: {trace_path}")
    output_trace_path = output_dir / "khop_trace.csv"
    shutil.copyfile(trace_path, output_trace_path)
    docker_cp_to_container(FUNC_NAME, output_trace_path, "/usr/src/app/khop_trace.csv")

    jkv_dir = Path(args.jkv_dir)
    last_cache_env = None
    for variant in variants:
        spec = variant_config[variant]
        strategy = spec["strategy"]
        cache_env = spec.get("cache_env", {})
        if args.manage_cache_server and cache_env != last_cache_env:
            restart_cache_server(
                jkv_dir,
                cache_env,
                output_dir / f"cache_{variant}.log",
            )
            last_cache_env = dict(cache_env)

        log_name = f"invocations_khop_{variant}.jsonl"
        params = {
            "BENCH_NAME": FUNC_NAME,
            "NUM_OPERATION": args.samples,
            "STRATEGY": strategy,
            "PUSH_ADDR": PUSH_ADDR,
            "PULL_ADDR": PULL_ADDR,
            "ACCESS": "hot",
            "TRACE_FILE": "/usr/src/app/khop_trace.csv",
            "FAASPE_RESULT_DIR": container_result_dir,
            "FAASPE_STORAGE_HEARTBEAT_ENABLED": "0",
            "FAASPE_INVOCATION_LOG_ENABLED": "1",
            "FAASPE_INVOCATION_LOG_BACKEND": "memory",
            "FAASPE_INVOCATION_LOG_PATH": f"{container_result_dir}/{log_name}",
        }
        params.update(spec.get("function_env", {}))
        if variant == "faaspe":
            params.setdefault(
                "FAASPE_PROFILER_RECHECK_INTERVAL",
                KHOP_FAASPE_RECHECK_INTERVAL,
            )
        if strategy == "faaspe" and args.inject_calibrated_model:
            params["FAASPE_PLACEMENT_LATENCY_MODEL_JSON"] = model_json

        if args.restart_function_container:
            restart_function_container(FUNC_NAME)
            docker_cp_to_container(FUNC_NAME, output_trace_path, "/usr/src/app/khop_trace.csv")

        invoke(FUNC_NAME, params)
        file_name = f"khop_trace_{variant}.csv"
        result_csv = output_dir / file_name
        docker_cp(FUNC_NAME, f"{container_result_dir}/temp.csv", result_csv)
        docker_cp(FUNC_NAME, f"{container_result_dir}/{log_name}", output_dir / log_name)
        result = latest_row(result_csv)
        rows.append(
            {
                "variant": variant,
                "strategy": strategy,
                "trace_file": str(trace_path),
                "median_ms": result.get("median", ""),
                "p90_ms": result.get("p90", ""),
                "p99_ms": result.get("p99", ""),
                "mean_ms": result.get("mean", ""),
                "total_time_s": result.get("total_time", ""),
                "num_op": result.get("num_op", args.samples),
                "native_count": result.get("native_count", ""),
                "func_count": result.get("func_count", ""),
                "pushback_count": result.get("pushback_count", ""),
                "profiler_fallback_count": result.get("profiler_fallback_count", ""),
                "profiler_override": result.get("profiler_override", ""),
                "source_csv": file_name,
                "source_invocation_log": log_name,
            }
        )

    write_csv(output_dir / "khop_trace_latency_summary.csv", rows)
    metric_rows = add_oracle_metrics(rows, output_dir)
    write_csv(output_dir / "khop_trace_oracle_metrics.csv", metric_rows)
    return metric_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="khop-trace-direct")
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--trace-file", default=str(DEFAULT_TRACE_PATH))
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--variant-config", default=str(DEFAULT_VARIANT_CONFIG_PATH))
    parser.add_argument("--variants", default=DEFAULT_VARIANTS)
    parser.add_argument("--jkv-dir", default=str(DEFAULT_JKV_DIR))
    parser.add_argument("--inject-calibrated-model", action="store_true")
    parser.add_argument("--manage-cache-server", action="store_true", default=True)
    parser.add_argument("--no-manage-cache-server", dest="manage_cache_server", action="store_false")
    parser.add_argument("--restart-function-container", action="store_true", default=True)
    parser.add_argument("--no-restart-function-container", dest="restart_function_container", action="store_false")
    args = parser.parse_args()

    output_dir = ROOT / "results" / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    container_result_dir = f"/usr/src/app/results/{args.output_dir}"
    model = load_latency_model(args.model_path)
    recommendations = fixed_recommendations(model, args.model_path)
    with open(output_dir / "placement_calibration_recommendations.json", "w") as f:
        json.dump(recommendations, f, indent=2, sort_keys=True)
        f.write("\n")
    write_variant_config_snapshot(
        output_dir / "placement_variants.json",
        load_variant_config(args.variant_config),
    )

    rows = run_trace(args, output_dir, container_result_dir, model)
    print("KHOP_TRACE_SUMMARY_CSV")
    for row in rows:
        print(
            "{variant},{median_ms},{native_count},{func_count},{placement_correct_rate},{normalized_total_latency},{normalized_regret}".format(
                **row
            )
        )


if __name__ == "__main__":
    main()
