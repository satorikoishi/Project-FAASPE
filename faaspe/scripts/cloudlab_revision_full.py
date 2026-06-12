#!/usr/bin/env python3
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def env_default(name, default):
    return os.environ.get(name, default)


def main():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    push_addr = env_default("PUSH_ADDR", "tcp://10.10.1.1:50053")
    pull_addr = env_default("PULL_ADDR", "tcp://10.10.1.1:50054")
    result_dir = env_default("RESULT_DIR", str(ROOT / "results" / f"revision-full-{stamp}"))
    workloads = env_default("WORKLOADS", "list-traversal,list-traversal-trace,storage-load-trace,data-size")
    threshold_multipliers = env_default("THRESHOLD_MULTIPLIERS", "0.5,0.75,1.0,1.25,1.5,2.0")
    repetitions = env_default("REPETITIONS", "5")
    num_operations = env_default("NUM_OPERATIONS", "3000")
    warmup_operations = env_default("WARMUP_OPERATIONS", "200")
    concurrency = env_default("CONCURRENCY", "1")
    python_bin = env_default("PYTHON_BIN", sys.executable)

    env = os.environ.copy()
    env["PUSH_ADDR"] = push_addr
    env["PULL_ADDR"] = pull_addr
    env["FAASPE_WARMUP_OPERATIONS"] = env_default("FAASPE_WARMUP_OPERATIONS", warmup_operations)
    env.setdefault("JKV_ISOLATION_MODE", "none")

    print("CloudLab full revision experiment")
    print(f"  PUSH_ADDR={push_addr}")
    print(f"  PULL_ADDR={pull_addr}")
    print(f"  RESULT_DIR={result_dir}")
    print(f"  WORKLOADS={workloads}")
    print(f"  REPETITIONS={repetitions}")
    print(f"  NUM_OPERATIONS={num_operations}")
    print(f"  FAASPE_WARMUP_OPERATIONS={env['FAASPE_WARMUP_OPERATIONS']}")
    print(f"  CONCURRENCY={concurrency}")

    cmd = [
        python_bin,
        str(ROOT / "scripts" / "revision_experiments.py"),
        "--output-dir",
        result_dir,
        "--push-addr",
        push_addr,
        "--pull-addr",
        pull_addr,
        "--workloads",
        workloads,
        "--repetitions",
        repetitions,
        "--num-operations",
        num_operations,
        "--warmup-operations",
        env["FAASPE_WARMUP_OPERATIONS"],
        "--concurrency",
        concurrency,
        "--threshold-multipliers",
        threshold_multipliers,
        "--skip-existing",
    ]
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    print(f"Full revision results written to {result_dir}")
    print(f"Summary files are in {Path(result_dir) / 'summary'}")


if __name__ == "__main__":
    main()
