#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path


MODE_LABELS = {
    "none": "No isolation",
    "lightweight": "Lightweight",
    "strong": "Strong",
}


def load_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def find(rows, mode, workload):
    for row in rows:
        if row["mode"] == mode and row["workload"] == workload:
            return row
    return None


def fmt_us(value):
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return ""


def main():
    parser = argparse.ArgumentParser(description="Render the isolation-mode comparison table used in the revision.")
    parser.add_argument("summary_csv")
    parser.add_argument("--out-csv")
    parser.add_argument("--out-md")
    args = parser.parse_args()

    rows = load_rows(args.summary_csv)
    table = []
    for mode in ["none", "lightweight", "strong"]:
        empty = find(rows, mode, "empty_func")
        traversal = find(rows, mode, "list_traversal_depth8")
        background = find(rows, mode, "background_get_under_cpu_func")
        table.append({
            "Mode": MODE_LABELS[mode],
            "Empty FUNC median us": fmt_us(empty["median_us"]) if empty else "",
            "Empty FUNC p99 us": fmt_us(empty["p99_us"]) if empty else "",
            "List-traversal median us": fmt_us(traversal["median_us"]) if traversal else "",
            "Background GET p99 under CPU-loop us": fmt_us(background["p99_us"]) if background else "",
        })

    fieldnames = list(table[0].keys())
    if args.out_csv:
        with open(args.out_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(table)
    if args.out_md:
        with open(args.out_md, "w") as f:
            f.write("| " + " | ".join(fieldnames) + " |\n")
            f.write("| " + " | ".join(["---"] * len(fieldnames)) + " |\n")
            for row in table:
                f.write("| " + " | ".join(row[name] for name in fieldnames) + " |\n")
    if not args.out_csv and not args.out_md:
        print(",".join(fieldnames))
        for row in table:
            print(",".join(row[name] for name in fieldnames))


if __name__ == "__main__":
    main()
