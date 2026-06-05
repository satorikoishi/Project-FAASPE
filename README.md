# Project-FAASPE

Project-FAASPE is a clean monorepo that combines two related projects:

- `faaspe/`: the FAASPE serverless platform, benchmarks, functions, and Python tooling.
- `jkv/`: the J-KV key-value store, cache server, clients, and protobuf definitions.

The original repositories are imported as source directories without preserving their
individual Git histories. Their project-specific usage notes remain in:

- `faaspe/README.md`
- `jkv/README.md`

## Layout

```text
Project-FAASPE/
  faaspe/   # serverless platform, functions, benchmark scripts, tests
  jkv/      # C++ key-value store, cache, clients, protobuf schema
```

## Quick Start

For FAASPE platform usage:

```shell
cd faaspe
./platform/function.py
```

For J-KV build and usage:

```shell
cd jkv
make
./build/jkv_server
```

## Next Optimization Targets

- Unify FAASPE and J-KV configuration.
- Share or regenerate protobuf clients from one source of truth.
- Add top-level scripts for build, test, and local orchestration.
- Document the end-to-end workflow from platform startup to benchmark execution.
