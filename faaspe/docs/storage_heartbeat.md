# Storage-Load Heartbeat

The storage-load detector is a simulated-load mechanism for revision
experiments. It is not a production queue-depth or storage scheduler metric.

When enabled, the FaaSPE runtime starts a background heartbeat thread. The
thread periodically sends a lightweight `PING` request with key
`HEARTBEAT:<sequence>` through the cache to the JKV server. The request payload
contains an emulated extra delay in microseconds. The JKV server sleeps for that
delay and returns a small response without reading or writing object data.

## Configuration

Enable heartbeat collection in the function container environment:

```text
FAASPE_STORAGE_HEARTBEAT_ENABLED=1
FAASPE_STORAGE_HEARTBEAT_INTERVAL_MS=500
FAASPE_STORAGE_HEARTBEAT_TRACE=/usr/src/app/storage_load_trace.csv
```

If `FAASPE_STORAGE_HEARTBEAT_TRACE` is unset, the heartbeat uses constant
`0` us extra load.

The trace CSV format is:

```csv
duration_ms,extra_load_us
1000,0
1000,2000
1000,0
```

Rows are advanced by elapsed wall-clock time and repeat cyclically. Each
heartbeat attaches the current row's `extra_load_us`.

## Arbiter Consumption

The heartbeat thread records the latest requested load, observed heartbeat
latency, and an estimated storage-load value. The estimate is the latest
heartbeat latency minus the minimum observed heartbeat latency in the current
run.

For `strategy=faaspe`, `bench_util` injects the latest estimate into placement
parameters as `storage_load_us`. The arbiter already adds this value to the
storage-side latency estimate and can therefore avoid storage placement when
the simulated load makes storage slower.

Benchmark summary CSVs include:

```text
storage_heartbeat_enabled
storage_heartbeat_interval_ms
storage_heartbeat_trace
storage_heartbeat_requested_load_us
storage_heartbeat_observed_latency_us
storage_heartbeat_estimated_load_us
storage_heartbeat_samples
```

Per-invocation latency logging is unchanged.
