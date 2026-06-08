#!/usr/bin/env python3
import argparse
import csv
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
JKV_DIR = REPO / "jkv"
LIB_DIR = ROOT / "lib"

MODE_ALIASES = {
    "none": "none",
    "l0": "none",
    "lightweight": "lightweight",
    "l1": "lightweight",
    "strong": "strong",
    "l2": "strong",
}

MODE_META = {
    "none": ("L0", "No isolation / trusted inline"),
    "lightweight": ("L1", "Lightweight isolation"),
    "strong": ("L2", "Strong isolation"),
}


def normalize_mode(mode):
    normalized = MODE_ALIASES.get(mode.strip().lower())
    if not normalized:
        raise ValueError(f"unknown isolation mode: {mode}")
    return normalized


def percentile(values, pct):
    values = sorted(values)
    idx = (len(values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def write_config(mode, timeout_ms):
    config = f'''base_port = 50050
isolation_mode = "{mode}"
func_timeout_ms = {timeout_ms}
kvs: {{
    ip = "127.0.0.1"
    recv_port = 1
    send_port = 2
}}
cache_kvs: {{
    ip = "127.0.0.1"
}}
cache_client: {{
    ip = "127.0.0.1"
    recv_port = 3
    send_port = 4
}}
client: {{
    ip = "127.0.0.1"
}}
'''
    (JKV_DIR / "config" / "config.ini").write_text(config)


def start_process(cmd, log_path, env=None):
    log = open(log_path, "w")
    proc = subprocess.Popen(
        cmd,
        cwd=JKV_DIR,
        env=env,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
    )
    return proc, log


def stop_process(proc, log):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    log.close()


def start_servers(mode, timeout_ms, output_dir):
    write_config(mode, timeout_ms)
    env = os.environ.copy()
    env["JKV_ISOLATION_MODE"] = mode
    env["JKV_FUNC_TIMEOUT_MS"] = str(timeout_ms)
    kvs, kvs_log = start_process(["./build/jkv_server"], output_dir / f"{mode}-kvs.log", env)
    time.sleep(0.5)
    cache, cache_log = start_process(["./build/cache_server"], output_dir / f"{mode}-cache.log", env)
    time.sleep(0.5)
    return (kvs, kvs_log), (cache, cache_log)


def time_us(fn):
    started = time.perf_counter()
    ok = fn()
    return (time.perf_counter() - started) * 1e6, ok


def measure(samples, fn):
    rows = []
    for _ in range(samples):
        latency, ok = time_us(fn)
        rows.append((latency, ok))
    return rows


def summarize(mode, workload, rows):
    latencies = [latency for latency, ok in rows if ok]
    level, name = MODE_META[mode]
    return {
        "mode": mode,
        "isolation_level": level,
        "isolation_name": name,
        "workload": workload,
        "samples": len(rows),
        "success": len(latencies),
        "cold_start_us": rows[0][0] if rows else 0.0,
        "median_us": percentile(latencies, 50) if latencies else 0.0,
        "p99_us": percentile(latencies, 99) if latencies else 0.0,
    }


def run_mode(mode, args, output_dir):
    sys.path.insert(0, str(LIB_DIR))
    from jkv_client import JKVClient

    servers = start_servers(mode, args.timeout_ms, output_dir)
    try:
        client = JKVClient("tcp://127.0.0.1:50053", "tcp://127.0.0.1:50054")
        value_1kb = "a" * 1024
        client.put("bench-key", value_1kb, 1)
        for idx in range(16):
            client.put(str(idx), str((idx + 1) % 16), 1)

        results = []
        results.append(
            summarize(mode, "empty_func", measure(args.samples, lambda: client.func("NONE", "", "tenantA")))
        )
        results.append(
            summarize(mode, "func_get_1kb", measure(args.samples, lambda: client.func("GET", "bench-key", "tenantA")))
        )
        results.append(
            summarize(mode, "list_traversal_depth8", measure(args.samples, lambda: client.func("TRAVERSE", "0 8", "tenantA")))
        )

        bg_latency, bg_ok = time_us(lambda: client.func("CPU_LOOP", str(args.interference_us), "tenantA"))
        get_put_rows = []
        for idx in range(args.samples):
            latency, ok = time_us(lambda idx=idx: client.put(f"interfere-{idx}", "x", idx + 1))
            get_put_rows.append((latency, ok and bg_ok))
        interference = summarize(mode, "background_get_put_during_cpu_func", get_put_rows)
        interference["background_cpu_func_us"] = bg_latency
        results.append(interference)
        return results
    finally:
        stop_process(*servers[1])
        stop_process(*servers[0])


def main():
    parser = argparse.ArgumentParser(description="Compare J-KV FUNC isolation modes.")
    parser.add_argument("--modes", default="none,lightweight,strong")
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--interference-us", type=int, default=200000)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "isolation-bench"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for mode in [normalize_mode(m) for m in args.modes.split(",") if m.strip()]:
        rows.extend(run_mode(mode, args, output_dir))

    fieldnames = [
        "mode",
        "isolation_level",
        "isolation_name",
        "workload",
        "samples",
        "success",
        "cold_start_us",
        "median_us",
        "p99_us",
        "background_cpu_func_us",
    ]
    out_path = output_dir / "summary.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
