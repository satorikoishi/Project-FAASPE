param(
    [string]$RemoteHost = "jinwei@pc765.emulab.net",
    [string]$RemoteProject = "/users/jinwei/projects/Project-FAASPE",
    [int]$Samples = 300,
    [string]$Stamp = (Get-Date -Format "yyyyMMdd-HHmmss")
)

$ErrorActionPreference = "Stop"

$variants = "faaspe-cache075,faaspe-cache100,faaspe-cache125"
$sizeDir = "revision-performance/latency-sensitivity-size-$Stamp"
$depthDir = "revision-performance/latency-sensitivity-depth-$Stamp"
$remoteFaaspe = "$RemoteProject/faaspe"
$localBase = "faaspe\results\revision-performance\latency-sensitivity-$Stamp"

Write-Host "Syncing arbiter sensitivity files to CloudLab..."
scp faaspe\lib\arbiter.py "${RemoteHost}:${remoteFaaspe}/lib/arbiter.py"
scp faaspe\lib\placement_variants.json "${RemoteHost}:${remoteFaaspe}/lib/placement_variants.json"

Write-Host "Recreating placement-matrix container..."
ssh $RemoteHost "cd $remoteFaaspe && python3 ./platform/cli.py delete placement-matrix || true"
ssh $RemoteHost "cd $remoteFaaspe && python3 ./platform/cli.py create placement-matrix"

Write-Host "Running size sensitivity sweep..."
ssh $RemoteHost "cd $remoteFaaspe && python3 scripts/run_placement_matrix_direct.py --output-dir $sizeDir --samples $Samples --depths 1 --object-sizes 1024,4096,16384,65536,262144,1048576 --key-count 1 --inject-calibrated-model --enable-invocation-log --variants $variants"

Write-Host "Running depth sensitivity sweep..."
ssh $RemoteHost "cd $remoteFaaspe && python3 scripts/run_placement_matrix_direct.py --output-dir $depthDir --samples $Samples --depths 1,2,8 --object-sizes 1024 --key-count 1 --inject-calibrated-model --enable-invocation-log --variants $variants"

Write-Host "Fetching results..."
New-Item -ItemType Directory -Force $localBase | Out-Null
scp -r "${RemoteHost}:${remoteFaaspe}/results/$sizeDir" "$localBase\"
scp -r "${RemoteHost}:${remoteFaaspe}/results/$depthDir" "$localBase\"

Write-Host "Writing combined summary..."
$summary = @()
$scaleByVariant = @{
    "faaspe-cache075" = "0.75"
    "faaspe-cache100" = "1.0"
    "faaspe-cache125" = "1.25"
}

foreach ($case in @(
    @{ Sweep = "size"; Path = "$localBase\latency-sensitivity-size-$Stamp\placement_matrix_latency_summary.csv" },
    @{ Sweep = "depth"; Path = "$localBase\latency-sensitivity-depth-$Stamp\placement_matrix_latency_summary.csv" }
)) {
    Import-Csv $case.Path | ForEach-Object {
        $summary += [PSCustomObject]@{
            sweep = $case.Sweep
            cache_latency_scale = $scaleByVariant[$_.variant]
            variant = $_.variant
            depth = $_.depth
            object_size = $_.object_size
            median_ms = $_.median_ms
            p90_ms = $_.p90_ms
            p99_ms = $_.p99_ms
            mean_ms = $_.mean_ms
            total_time_s = $_.total_time_s
            num_op = $_.num_op
            native_count = $_.native_count
            func_count = $_.func_count
            pushback_count = $_.pushback_count
            profiler_fallback_count = $_.profiler_fallback_count
            profiler_override = $_.profiler_override
            source_csv = $_.source_csv
            source_invocation_log = $_.source_invocation_log
        }
    }
}

$summaryPath = "$localBase\latency_sensitivity_summary.csv"
$summary | Export-Csv -NoTypeInformation $summaryPath

@"
CloudLab latency sensitivity complete.

Remote result directories:
  $remoteFaaspe/results/$sizeDir
  $remoteFaaspe/results/$depthDir

Local result directory:
  $localBase

Combined summary:
  $summaryPath
"@ | Tee-Object -FilePath "$localBase\README.txt"
