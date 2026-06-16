import argparse
import csv
from datetime import datetime

from fabric import Connection

import runner


FUNC_NAME = "placement-calibration"


def latest_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


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

    extra = {
        "DEPTHS": args.depths,
        "VALUE_SIZES": args.value_sizes,
        "SAMPLES": args.samples,
        "WARMUP": args.warmup,
        "KEY_COUNT": args.key_count,
        "FAASPE_RESULT_DIR": container_result_dir,
        "_local_dir": output_name,
        "_container_result_dir": container_result_dir,
    }
    runner.remote_run(FUNC_NAME, args.samples, "local", **extra)
    csv_path = output_dir / f"{FUNC_NAME}.csv"
    rows = latest_rows(csv_path)
    recommendation_rows = [
        row
        for row in rows
        if row["operation"] == "recommended_storage_depth_threshold"
    ]
    print(csv_path)
    for row in recommendation_rows:
        threshold = row["depth"]
        value_size = row["value_size"]
        print(
            f"value_size={value_size}: recommended "
            f"FAASPE_STORAGE_DEPTH_THRESHOLD={threshold}"
        )
    return csv_path


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
