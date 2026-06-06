#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_DIR = ROOT / "functions"
LIB_DIR = ROOT / "lib"


WORKLOADS = {
    "list-traversal": [
        {"case_id": "depth1-hot", "params": {"ACCESS": "hot", "DEPTH": 1}},
        {"case_id": "depth2-hot", "params": {"ACCESS": "hot", "DEPTH": 2}},
        {"case_id": "depth4-hot", "params": {"ACCESS": "hot", "DEPTH": 4}},
        {"case_id": "depth8-hot", "params": {"ACCESS": "hot", "DEPTH": 8}},
    ],
    "list-traversal-trace": [
        {"case_id": "mixed-depth-hot", "params": {"ACCESS": "hot"}},
    ],
    "storage-load-trace": [
        {"case_id": "dynamic-load-hot", "params": {"ACCESS": "hot"}},
    ],
    "data-size": [
        {"case_id": "1KB-hot-get", "params": {"VALUE_LEN": 1024, "ACCESS": "hot-get"}},
        {"case_id": "10KB-hot-get", "params": {"VALUE_LEN": 10 * 1024, "ACCESS": "hot-get"}},
        {"case_id": "100KB-hot-get", "params": {"VALUE_LEN": 100 * 1024, "ACCESS": "hot-get"}},
        {"case_id": "1MB-hot-get", "params": {"VALUE_LEN": 1024 * 1024, "ACCESS": "hot-get"}},
    ],
}


ABLATIONS = {
    "CacheOnly": {"strategy": "local", "env": {}},
    "StorageOnly": {"strategy": "remote", "env": {}},
    "StaticOnly": {"strategy": "faaspe", "env": {"FAASPE_PROFILER_ENABLED": "0"}},
    "NoFallback": {"strategy": "faaspe", "env": {"FAASPE_FALLBACK_ENABLED": "0"}},
    "FullFaaSPE": {"strategy": "faaspe", "env": {}},
}


def parse_csv_list(value, cast=str):
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def side_for_variant(variant):
    if variant == "CacheOnly":
        return "compute"
    if variant == "StorageOnly":
        return "storage"
    return ""


def run_worker(
    workload,
    case,
    variant,
    variant_conf,
    rep,
    worker,
    operations,
    args,
    extra_env=None,
):
    run_id = f"{workload}__{case['case_id']}__{variant}__rep{rep}__w{worker}"
    run_dir = Path(args.output_dir) / "raw" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(LIB_DIR),
            "PUSH_ADDR": args.push_addr,
            "PULL_ADDR": args.pull_addr,
            "BENCH_NAME": workload,
            "NUM_OPERATION": str(operations),
            "STRATEGY": variant_conf["strategy"],
            "FAASPE_RANDOM_SEED": str(args.seed + rep * 100000 + worker),
            "FAASPE_RESULT_DIR": str(run_dir),
            "FAASPE_INVOCATION_LOG_ENABLED": "1",
            "FAASPE_INVOCATION_LOG_PATH": str(run_dir / "invocations.jsonl"),
        }
    )
    env.update({key: str(value) for key, value in case["params"].items()})
    env.update(variant_conf.get("env", {}))
    if extra_env:
        env.update({key: str(value) for key, value in extra_env.items()})

    metadata = {
        "run_id": run_id,
        "workload": workload,
        "case_id": case["case_id"],
        "variant": variant,
        "strategy": variant_conf["strategy"],
        "repetition": rep,
        "worker": worker,
        "concurrency": args.concurrency,
        "num_operations": operations,
        "seed": int(env["FAASPE_RANDOM_SEED"]),
        "params": case["params"],
        "env": {
            key: env[key]
            for key in env
            if key.startswith("FAASPE_") or key in {"PUSH_ADDR", "PULL_ADDR", "STRATEGY"}
        },
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True))

    handler_dir = FUNCTIONS_DIR / workload
    cmd = [sys.executable, "handler.py"]
    stdout = open(run_dir / "stdout.txt", "w")
    stderr = open(run_dir / "stderr.txt", "w")
    proc = subprocess.Popen(cmd, cwd=handler_dir, env=env, stdout=stdout, stderr=stderr)
    return proc, stdout, stderr, run_dir


def run_case(workload, case, variant, variant_conf, rep, args, extra_env=None):
    per_worker_ops = math.ceil(args.num_operations / args.concurrency)
    procs = []
    for worker in range(args.concurrency):
        procs.append(
            run_worker(
                workload,
                case,
                variant,
                variant_conf,
                rep,
                worker,
                per_worker_ops,
                args,
                extra_env,
            )
        )

    failed = []
    for proc, stdout, stderr, run_dir in procs:
        rc = proc.wait()
        stdout.close()
        stderr.close()
        if rc != 0:
            failed.append((run_dir, rc))
    if failed:
        details = ", ".join(f"{run_dir}:{rc}" for run_dir, rc in failed)
        raise RuntimeError(f"failed workers: {details}")


def write_experiment_manifest(args, workloads, threshold_multipliers):
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "workloads": workloads,
        "repetitions": args.repetitions,
        "concurrency": args.concurrency,
        "num_operations": args.num_operations,
        "seed": args.seed,
        "threshold_multipliers": threshold_multipliers,
        "push_addr": args.push_addr,
        "pull_addr": args.pull_addr,
    }
    (out / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))


def run_summary(output_dir):
    summary_script = ROOT / "scripts" / "summarize_revision_results.py"
    subprocess.run([sys.executable, str(summary_script), output_dir], check=True)


def main():
    parser = argparse.ArgumentParser(description="Run FaaSPE major-revision experiments.")
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "revision"))
    parser.add_argument("--workloads", default="list-traversal,list-traversal-trace,storage-load-trace,data-size")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--num-operations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260606)
    parser.add_argument("--push-addr", default=os.getenv("PUSH_ADDR", "tcp://10.10.1.1:50053"))
    parser.add_argument("--pull-addr", default=os.getenv("PULL_ADDR", "tcp://10.10.1.1:50054"))
    parser.add_argument("--threshold-multipliers", default="0.5,0.75,1.0,1.25,1.5,2.0")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--skip-threshold-sensitivity", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    args.output_dir = str(Path(args.output_dir).resolve())

    if args.summarize_only:
        run_summary(args.output_dir)
        return

    workloads = parse_csv_list(args.workloads)
    threshold_multipliers = parse_csv_list(args.threshold_multipliers, float)
    write_experiment_manifest(args, workloads, threshold_multipliers)

    if not args.skip_ablation:
        for rep in range(args.repetitions):
            for workload in workloads:
                for case in WORKLOADS[workload]:
                    for variant, variant_conf in ABLATIONS.items():
                        run_case(workload, case, variant, variant_conf, rep, args)
    elif not args.skip_threshold_sensitivity:
        # Threshold sensitivity still needs an oracle. Run only the fixed-side
        # baselines so normalized latency and placement accuracy are defined.
        for rep in range(args.repetitions):
            for workload in workloads:
                for case in WORKLOADS[workload]:
                    for variant in ("CacheOnly", "StorageOnly"):
                        run_case(workload, case, variant, ABLATIONS[variant], rep, args)

    if not args.skip_threshold_sensitivity:
        for rep in range(args.repetitions):
            for workload in workloads:
                for case in WORKLOADS[workload]:
                    for multiplier in threshold_multipliers:
                        variant = f"Threshold{multiplier:g}x"
                        conf = {"strategy": "faaspe", "env": {"FAASPE_PROFILER_ENABLED": "0"}}
                        run_case(
                            workload,
                            case,
                            variant,
                            conf,
                            rep,
                            args,
                            {"FAASPE_THRESHOLD_MULTIPLIER": multiplier},
                        )

    run_summary(args.output_dir)


if __name__ == "__main__":
    main()
