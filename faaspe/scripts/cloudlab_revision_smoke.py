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
    result_dir = env_default("RESULT_DIR", str(ROOT / "results" / f"revision-smoke-{stamp}"))
    workloads = env_default("WORKLOADS", "list-traversal")
    threshold_multipliers = env_default("THRESHOLD_MULTIPLIERS", "0.5,1.0,1.5")
    python_bin = env_default("PYTHON_BIN", sys.executable)
    warmup_operations = env_default("FAASPE_WARMUP_OPERATIONS", "2")

    env = os.environ.copy()
    env["PUSH_ADDR"] = push_addr
    env["PULL_ADDR"] = pull_addr
    env["FAASPE_WARMUP_OPERATIONS"] = warmup_operations
    env.setdefault("JKV_ISOLATION_MODE", "none")

    print("CloudLab revision smoke")
    print(f"  PUSH_ADDR={push_addr}")
    print(f"  PULL_ADDR={pull_addr}")
    print(f"  RESULT_DIR={result_dir}")
    print(f"  WORKLOADS={workloads}")
    print(f"  FAASPE_WARMUP_OPERATIONS={warmup_operations}")

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
        "1",
        "--num-operations",
        "10",
        "--warmup-operations",
        warmup_operations,
        "--concurrency",
        "1",
        "--threshold-multipliers",
        threshold_multipliers,
        "--skip-existing",
    ]
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    print(f"Smoke results written to {result_dir}")
    print(f"Summary files are in {Path(result_dir) / 'summary'}")


if __name__ == "__main__":
    main()
