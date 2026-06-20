# Placement Ablation Variants

These variants are recorded in `faaspe/lib/placement_variants.json`. Experiment
scripts should load that JSON instead of duplicating the environment variables.
Function/runtime variables are passed to the FaaSPE function invocation. JKV
cache variables must be set on the `cache_server` process, or through runner
`_cache_env`.

## Variant 1: static-only

Only the Arbiter is active. Runtime profiler/fallback and cache-side object-size
function trigger are disabled.

Function/runtime env:

```text
FAASPE_PROFILE_ENABLED=0
FAASPE_PROFILER_ENABLED=0
FAASPE_ACCESS_META_ENABLED=1
FAASPE_FALLBACK_ENABLED=0
FAASPE_ARBITER_FORCE_UNKNOWN=0
```

JKV cache env:

```text
JKV_OBJECT_SIZE_TRIGGER_ENABLED=0
```

Expected behavior: placement is decided from the static RPN/access-count model
only. Arbiter does not use object size before execution.

## Variant 2: arbiter-only

Static Arbiter is active and the JKV cache-side object-size trigger is active.
Profiler/fallback remains disabled.

Function/runtime env:

```text
FAASPE_PROFILE_ENABLED=0
FAASPE_PROFILER_ENABLED=0
FAASPE_ACCESS_META_ENABLED=1
FAASPE_FALLBACK_ENABLED=0
FAASPE_ARBITER_FORCE_UNKNOWN=0
```

JKV cache env:

```text
JKV_OBJECT_SIZE_TRIGGER_ENABLED=1
JKV_OBJECT_SIZE_TRIGGER_THRESHOLD_BYTES=<calibrated_threshold>
JKV_OBJECT_SIZE_TRIGGER_FUNC_NAME=NONE
```

Expected behavior: Arbiter still makes the pre-execution decision using only
RPN/access count. If a cache GET observes an object at or above the threshold,
the cache-side trigger can convert that GET into a FUNC request.

## Variant 3: runtime-only

Static analysis is disabled for placement. Arbiter is forced to return
`unsupported_static_analysis`, and Profiler/fallback explores and adapts
placement at runtime.

Function/runtime env:

```text
FAASPE_ARBITER_FORCE_UNKNOWN=1
FAASPE_PROFILE_ENABLED=1
FAASPE_PROFILER_ENABLED=1
FAASPE_FALLBACK_ENABLED=1
FAASPE_PROFILER_EXPLORE_ON_UNKNOWN=1
FAASPE_PROFILER_RECHECK_INTERVAL=100
```

JKV cache env:

```text
JKV_OBJECT_SIZE_TRIGGER_ENABLED=0
```

Expected behavior: Arbiter never uses static RPN profiles. The initial placement
comes from `FAASPE_UNKNOWN_PLACEMENT` if set, otherwise the repository default.
Profiler immediately explores placements for unknown functions, uses the lower
observed-latency side as fallback override, and periodically re-enters
exploration after the configured recheck interval.

## Notes

The full `faaspe` variant enables the JKV cache-side object-size trigger. Use
`static-only` to disable both profiler/fallback and cache trigger, `arbiter-only`
to enable static Arbiter plus cache trigger without profiler/fallback, and
`runtime-only` to force unknown static analysis and rely on runtime fallback
without cache trigger.

`FAASPE_ARBITER_FORCE_UNKNOWN=1` is a global switch for ablation. Without it,
the older workaround was to override each profile in `FAASPE_RPN_PROFILES` with
an invalid expression, which is brittle and workload-specific.

`JKV_OBJECT_SIZE_TRIGGER_ENABLED=0` disables only the cache-side function
trigger. It does not remove the cache server from the data path.
