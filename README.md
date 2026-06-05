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

## CloudLab Notes

The existing CloudLab flow is driven from `faaspe/` with Fabric.

1. Create a CloudLab experiment with at least two Ubuntu nodes.
2. Put the node SSH commands in `faaspe/nodes.txt`, one per line, for example:

```text
ssh username@pc001.emulab.net
ssh username@pc002.emulab.net
```

3. Give the CloudLab nodes access to this private GitHub repository. Either:

- create `faaspe/token` with a GitHub token that can read the repo; or
- configure an SSH key on the CloudLab nodes that can clone `git@github.com:satorikoishi/Project-FAASPE.git`.

4. Initialize the nodes:

```shell
cd faaspe
fab init
```

5. Run a benchmark:

```shell
fab run ycsb
```

The initialization script clones this monorepo to `~/projects/Project-FAASPE`
on each CloudLab node and creates compatibility symlinks at `~/projects/faaspe`
and `~/projects/jkv`.
