import argparse
import csv
from datetime import datetime

import runner


FUNC_NAME = "list-traversal"


MODES = {
    "disabled": {
        "FAASPE_PROFILE_ENABLED": "0",
        "FAASPE_PROFILE_ASYNC_ENABLED": "0",
        "FAASPE_INVOCATION_LOG_ENABLED": "0",
    },
    "metadata": {
        "FAASPE_PROFILE_ENABLED": "1",
        "FAASPE_PROFILE_SAMPLE_RATE": "1.0",
        "FAASPE_PROFILE_ASYNC_ENABLED": "0",
        "FAASPE_INVOCATION_LOG_ENABLED": "0",
    },
    "metadata_async": {
        "FAASPE_PROFILE_ENABLED": "1",
        "FAASPE_PROFILE_SAMPLE_RATE": "1.0",
        "FAASPE_PROFILE_ASYNC_ENABLED": "1",
        "FAASPE_INVOCATION_LOG_ENABLED": "0",
    },
    "memory_logger": {
        "FAASPE_PROFILE_ENABLED": "1",
        "FAASPE_PROFILE_SAMPLE_RATE": "1.0",
        "FAASPE_PROFILE_ASYNC_ENABLED": "0",
        "FAASPE_INVOCATION_LOG_ENABLED": "1",
        "FAASPE_INVOCATION_LOG_BACKEND": "memory",
    },
}


def latest_row(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))[-1]


def run_mode(args, output_dir, mode):
    run_id = f"profile-overhead-{mode}-depth{args.depth}"
    container_result_dir = f"/usr/src/app/results/{run_id}"
    suffix = f"-{mode}"
    extra = {
        "ACCESS": args.access,
        "DEPTH": args.depth,
        "FAASPE_RESULT_DIR": container_result_dir,
        "FAASPE_RANDOM_SEED": args.seed,
        "_local_dir": output_dir.name,
        "_local_suffix": suffix,
        "_container_result_dir": container_result_dir,
    }
    extra.update(MODES[mode])
    if extra.get("FAASPE_INVOCATION_LOG_ENABLED") == "1":
        extra["FAASPE_INVOCATION_LOG_PATH"] = f"{container_result_dir}/invocations.jsonl"
        extra["_fetch_invocations"] = True

    print(f"running {mode}", flush=True)
    runner.remote_run(FUNC_NAME, args.num_operations, args.strategy, **extra)
    row = latest_row(output_dir / f"{FUNC_NAME}{suffix}.csv")
    return {
        "mode": mode,
        "strategy": args.strategy,
        "depth": args.depth,
        "num_operations": args.num_operations,
        "p50_ms": row["median"],
        "p99_ms": row["p99"],
        "mean_ms": row["mean"],
        "success_tput": row["success tput"],
        "arbiter_mean_us": row.get("arbiter_mean_us", "0"),
        "profiler_mean_us": row.get("profiler_mean_us", "0"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compare profile metadata critical-path overhead on CloudLab."
    )
    parser.add_argument("--num-operations", type=int, default=1000)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--strategy", default="local", choices=["local", "faaspe"])
    parser.add_argument("--access", default="hot")
    parser.add_argument("--seed", type=int, default=20260616)
    parser.add_argument("--modes", default="disabled,metadata,metadata_async,memory_logger")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = f"profile-overhead-micro-{stamp}"
    output_dir = runner.FAASPE_DIR / "results" / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for mode in [item.strip() for item in args.modes.split(",") if item.strip()]:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        rows.append(run_mode(args, output_dir, mode))

    summary_path = output_dir / "profile_overhead_summary.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(summary_path)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
