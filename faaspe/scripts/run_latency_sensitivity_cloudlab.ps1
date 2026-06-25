param(
    [string]$RemoteHost = "jinwei@pc765.emulab.net",
    [string]$RemoteProject = "/users/jinwei/projects/Project-FAASPE",
    [int]$Samples = 300,
    [int]$Repeats = 5,
    [string]$Stamp = (Get-Date -Format "yyyyMMdd-HHmmss")
)

$ErrorActionPreference = "Stop"

$depthVariants = "faaspe-cache075,faaspe-cache100,faaspe-cache125"
$sizeVariants = "faaspe-trigger64k,faaspe-trigger100k,faaspe-trigger256k"
$remoteBase = "revision/latency-sensitivity-$Stamp"
$sizePrefix = "$remoteBase/size-repeat"
$depthPrefix = "$remoteBase/depth-repeat"
$remoteSummaryDir = "$remoteBase/summary"
$remoteFaaspe = "$RemoteProject/faaspe"
$localBase = "faaspe\results\revision\latency-sensitivity-$Stamp"

Write-Host "Syncing arbiter sensitivity files to CloudLab..."
scp faaspe\lib\arbiter.py "${RemoteHost}:${remoteFaaspe}/lib/arbiter.py"
scp faaspe\lib\placement_variants.json "${RemoteHost}:${remoteFaaspe}/lib/placement_variants.json"

Write-Host "Recreating placement-matrix container..."
ssh $RemoteHost "cd $remoteFaaspe && python3 ./platform/cli.py delete placement-matrix || true"
ssh $RemoteHost "cd $remoteFaaspe && python3 ./platform/cli.py create placement-matrix"

Write-Host "Running size sensitivity sweep ($Repeats repeats, trigger threshold variants)..."
for ($rep = 1; $rep -le $Repeats; $rep++) {
    $dir = "$sizePrefix$rep"
    ssh $RemoteHost "cd $remoteFaaspe && python3 scripts/run_placement_matrix_direct.py --output-dir $dir --samples $Samples --depths 1 --object-sizes 1024,4096,16384,65536,262144,1048576 --key-count 1 --inject-calibrated-model --variants $sizeVariants"
}

Write-Host "Running depth sensitivity sweep ($Repeats repeats, cache latency scale variants)..."
for ($rep = 1; $rep -le $Repeats; $rep++) {
    $dir = "$depthPrefix$rep"
    ssh $RemoteHost "cd $remoteFaaspe && python3 scripts/run_placement_matrix_direct.py --output-dir $dir --samples $Samples --depths 1,2,4,6,8 --object-sizes 1024 --key-count 1 --inject-calibrated-model --variants $depthVariants"
}

Write-Host "Aggregating remote results..."
$aggregateScript = @"
import csv
import statistics
from pathlib import Path

base = Path("results/$remoteBase")
outdir = Path("results/$remoteSummaryDir")
outdir.mkdir(parents=True, exist_ok=True)

records = []
cases = [
    ("size", "size-repeat", $Repeats),
    ("depth", "depth-repeat", $Repeats),
]

variant_meta = {
    "faaspe-cache075": {"cache_latency_scale": "0.75", "trigger_threshold_bytes": ""},
    "faaspe-cache100": {"cache_latency_scale": "1.0", "trigger_threshold_bytes": ""},
    "faaspe-cache125": {"cache_latency_scale": "1.25", "trigger_threshold_bytes": ""},
    "faaspe-trigger64k": {"cache_latency_scale": "1.0", "trigger_threshold_bytes": "65536"},
    "faaspe-trigger100k": {"cache_latency_scale": "1.0", "trigger_threshold_bytes": "102400"},
    "faaspe-trigger256k": {"cache_latency_scale": "1.0", "trigger_threshold_bytes": "262145"},
}

for sweep, prefix, repeats in cases:
    for rep in range(1, repeats + 1):
        path = base / f"{prefix}{rep}" / "placement_matrix_latency_summary.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                meta = variant_meta.get(row["variant"], {})
                record = {
                    "sweep": sweep,
                    "repeat": rep,
                    "cache_latency_scale": meta.get("cache_latency_scale", ""),
                    "trigger_threshold_bytes": meta.get("trigger_threshold_bytes", ""),
                    **row,
                    "source_dir": str(path.parent),
                }
                records.append(record)

record_fields = [
    "sweep", "repeat", "cache_latency_scale", "trigger_threshold_bytes",
    "depth", "object_size", "variant", "strategy", "median_ms", "p90_ms",
    "p99_ms", "mean_ms", "total_time_s", "num_op", "native_count",
    "func_count", "pushback_count", "profiler_fallback_count",
    "profiler_override", "source_csv", "source_invocation_log", "source_dir",
]
with (outdir / "latency_sensitivity_records.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=record_fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)

groups = {}
for record in records:
    key = (
        record["sweep"],
        record["depth"],
        record["object_size"],
        record["variant"],
        record["cache_latency_scale"],
        record["trigger_threshold_bytes"],
    )
    groups.setdefault(key, []).append(float(record["median_ms"]))

summary_fields = [
    "sweep", "depth", "object_size", "variant", "cache_latency_scale",
    "trigger_threshold_bytes", "runs", "median_of_median_ms",
    "min_median_ms", "max_median_ms", "lower_delta_ms", "upper_delta_ms",
    "range_ms", "lower_delta_pct", "upper_delta_pct", "range_pct",
]
rows = []
for key in sorted(groups, key=lambda item: (item[0], int(item[1]), int(item[2]), item[3])):
    values = sorted(groups[key])
    median = statistics.median(values)
    low = values[0]
    high = values[-1]
    denom = median or 1.0
    rows.append({
        "sweep": key[0],
        "depth": key[1],
        "object_size": key[2],
        "variant": key[3],
        "cache_latency_scale": key[4],
        "trigger_threshold_bytes": key[5],
        "runs": len(values),
        "median_of_median_ms": f"{median:.6f}",
        "min_median_ms": f"{low:.6f}",
        "max_median_ms": f"{high:.6f}",
        "lower_delta_ms": f"{median - low:.6f}",
        "upper_delta_ms": f"{high - median:.6f}",
        "range_ms": f"{high - low:.6f}",
        "lower_delta_pct": f"{(median - low) / denom * 100.0:.2f}",
        "upper_delta_pct": f"{(high - median) / denom * 100.0:.2f}",
        "range_pct": f"{(high - low) / denom * 100.0:.2f}",
    })

with (outdir / "latency_sensitivity_summary.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=summary_fields)
    writer.writeheader()
    writer.writerows(rows)

with (outdir / "REMOTE_MANIFEST.txt").open("w") as f:
    f.write("CloudLab latency sensitivity outputs\n")
    f.write(f"remote_base=results/$remoteBase\n")
    f.write(f"repeats=$Repeats\n")
    f.write("depth_variants=$depthVariants\n")
    f.write("size_variants=$sizeVariants\n")
    f.write("depths=1,2,4,6,8\n")
    f.write("object_sizes=1024,4096,16384,65536,262144,1048576\n")
"@
$encodedScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($aggregateScript))
ssh $RemoteHost "cd $remoteFaaspe && python3 -c `"import base64; exec(base64.b64decode('$encodedScript').decode())`""

Write-Host "Fetching summary results..."
New-Item -ItemType Directory -Force $localBase | Out-Null
scp -r "${RemoteHost}:${remoteFaaspe}/results/$remoteSummaryDir" "$localBase\"

$summaryPath = "$localBase\summary\latency_sensitivity_summary.csv"

@"
CloudLab latency sensitivity complete.

Remote result directories:
  $remoteFaaspe/results/$remoteBase

Local result directory:
  $localBase

Combined summary:
  $summaryPath
"@ | Tee-Object -FilePath "$localBase\README.txt"
