# Revision Experiment CloudLab Runbook

This runbook is for running the FaaSPE major-revision experiments on CloudLab and copying the machine-readable results back to a local workstation.

## Default CloudLab Values

Use these defaults unless the CloudLab profile changes:

PowerShell:

```powershell
$env:PUSH_ADDR = "tcp://10.10.1.1:50053"
$env:PULL_ADDR = "tcp://10.10.1.1:50054"
$env:RESULT_DIR = "results/revision-full-manual"
```

Bash:

```bash
export PUSH_ADDR="${PUSH_ADDR:-tcp://10.10.1.1:50053}"
export PULL_ADDR="${PULL_ADDR:-tcp://10.10.1.1:50054}"
export RESULT_DIR="${RESULT_DIR:-$HOME/projects/Project-FAASPE/faaspe/results/revision-full-$(date +%Y%m%d-%H%M%S)}"
```

The Python wrappers can run from Windows or CloudLab Linux. Run them from the repository root or from `faaspe/`.

## Start J-KV and FaaSPE

On the storage/cache node, make sure the current experiment branch is built:

```bash
cd ~/projects/Project-FAASPE/jkv
make -j2
```

Start J-KV and the cache service in two shells, or use your existing Fabric/runner workflow:

```bash
cd ~/projects/Project-FAASPE/jkv
export JKV_ISOLATION_MODE="${JKV_ISOLATION_MODE:-none}"
./build/jkv_server
```

```bash
cd ~/projects/Project-FAASPE/jkv
./build/cache_server
```

The default revision experiments use `JKV_ISOLATION_MODE=none` so the baseline path stays close to the original implementation. Set `JKV_ISOLATION_MODE=lightweight` or `strong` only for isolation-specific experiments.

## Required Environment Variables

The wrappers provide defaults, but these are the important variables:

```powershell
$env:PUSH_ADDR = "tcp://10.10.1.1:50053"
$env:PULL_ADDR = "tcp://10.10.1.1:50054"
$env:RESULT_DIR = "results/revision-full-manual"
$env:JKV_ISOLATION_MODE = "none"
```

Optional knobs:

```powershell
$env:WORKLOADS = "list-traversal,list-traversal-trace,storage-load-trace,data-size"
$env:THRESHOLD_MULTIPLIERS = "0.5,0.75,1.0,1.25,1.5,2.0"
$env:PYTHON_BIN = "python"
```

## Smoke Test

The smoke test runs one repetition, 10 measured operations, and 2 warmup operations. It fails fast if any worker exits non-zero.

```powershell
cd C:\Users\41045\Projects\Project-FAASPE\faaspe
python scripts\cloudlab_revision_smoke.py
```

Override machine-specific values as needed:

```powershell
$env:PUSH_ADDR = "tcp://10.10.1.1:50053"
$env:PULL_ADDR = "tcp://10.10.1.1:50054"
$env:RESULT_DIR = "results/revision-smoke-manual"
python scripts\cloudlab_revision_smoke.py
```

## Full Run

The full wrapper uses the recommended revision defaults:

- `repetitions=5`
- `num_operations=3000`
- `warmup_operations=200`
- `concurrency=1`

```powershell
cd C:\Users\41045\Projects\Project-FAASPE\faaspe
python scripts\cloudlab_revision_full.py
```

By default it writes to a timestamped directory such as:

```text
~/projects/Project-FAASPE/faaspe/results/revision-full-20260612-153000
```

## Resume After Failure

Both wrappers pass `--skip-existing`. A completed run directory is skipped when it already has:

```text
raw/<run_id>/metadata.json
raw/<run_id>/invocations.jsonl
```

To resume, rerun with the same `RESULT_DIR`:

```powershell
$env:RESULT_DIR = "results/revision-full-20260612-153000"
python scripts\cloudlab_revision_full.py
```

If a worker failed, inspect:

```text
raw/<run_id>/stdout.txt
raw/<run_id>/stderr.txt
raw/<run_id>/metadata.json
```

Remove only that failed `raw/<run_id>` directory if it contains partial output that should be rerun.

## Summarize Results

The wrappers summarize automatically at the end. To summarize manually or after a resumed run:

```bash
cd ~/projects/Project-FAASPE/faaspe
python3 scripts/revision_experiments.py \
  --output-dir "$RESULT_DIR" \
  --summarize-only
```

The summary files are written under:

```text
$RESULT_DIR/summary/
```

Key outputs:

```text
summary/placement_accuracy.csv       # oracle side, normalized latency, placement accuracy, fallback frequency
summary/ablation.csv                 # CacheOnly, StorageOnly, StaticOnly, NoFallback, FullFaaSPE
summary/overhead_breakdown.csv       # Arbiter, Profiler, trigger, AST, fallback exploration overhead
summary/threshold_sensitivity.csv    # threshold multiplier sweep
summary/placement_counts.csv         # selected compute/storage counts
```

Raw per-invocation logs are under:

```text
raw/<workload>__<case>__<variant>__rep<r>__w<w>/invocations.jsonl
raw/<workload>__<case>__<variant>__rep<r>__w<w>/temp.csv
```

## Copy Results Back Locally

From the local workstation:

```powershell
scp -r jinwei@pc765.emulab.net:~/projects/Project-FAASPE/faaspe/results/revision-full-20260612-153000 `
  faaspe\results\
```

For faster transfer, copy only machine-readable files:

```bash
ssh jinwei@pc765.emulab.net 'cd ~/projects/Project-FAASPE/faaspe && find results/revision-full-20260612-153000 -type f \( -name "*.csv" -o -name "*.jsonl" -o -name "*.json" -o -name "*.txt" \) | tar -czf /tmp/faaspe-revision-results.tgz -T -'
scp jinwei@pc765.emulab.net:/tmp/faaspe-revision-results.tgz faaspe/results/
```
