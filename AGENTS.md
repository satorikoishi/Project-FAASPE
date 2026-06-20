# AGENTS.md

## Project-specific execution environment

This repository is for the FaaSPE major-revision experiments. The experiment environment is special:

* Do **not** compile, build, benchmark, or run experiments on the local Codex machine.
* The local environment is only for reading files, editing code/scripts, and doing static inspection.
* All real compilation, deployment, benchmarking, profiling, and experiment execution must happen on the CloudLab nodes.
* The CloudLab node list is stored in:

```text
faaspe/nodes.txt
```

Before proposing or changing any experiment workflow, inspect the existing scripts to learn the current CloudLab execution pattern. In particular, search for scripts that:

* read `faaspe/nodes.txt`;
* use `ssh`, `scp`, `rsync`, or remote shell commands;
* activate a Python virtual environment;
* launch benchmarks, profilers, or data collection jobs.

There is a Python virtual environment inside the project directory. Prefer the existing venv used by the scripts rather than the system Python. If the exact venv path is unclear, inspect the scripts first and follow the existing convention.

## Hard rules for Codex

1. Never run local benchmark commands.
2. Never run local build or compile commands unless the task explicitly says local execution is allowed.
3. Never replace CloudLab execution with local mock results.
4. Never assume the current machine is a valid experiment node.
5. Do not edit `faaspe/nodes.txt` unless the task explicitly asks for node-list changes.
6. Do not overwrite raw experiment results unless the task explicitly asks for regeneration.
7. When adding a new experiment script, make it use the same CloudLab conventions as the existing scripts.
8. When adding a new Python script, make it compatible with the repository’s existing venv and dependency style.
9. When asked to “run” or “verify” an experiment, provide the exact CloudLab command sequence or remote execution script changes. Do not silently run anything locally.
10. If a result requires CloudLab execution but the task only asks for code changes, stop after preparing the scripts and clearly state what CloudLab command should be used.

## Expected workflow

For experiment-related tasks:

1. Inspect the relevant existing scripts.
2. Identify how they access CloudLab nodes.
3. Reuse `faaspe/nodes.txt`.
4. Reuse the project venv.
5. Modify or add scripts with minimal changes.
6. Add clear command examples for CloudLab execution.
7. Do not fabricate benchmark numbers.
8. If plots or tables depend on new data, generate plotting scripts but do not invent data.

## Preferred response format

When completing a task, summarize:

* files changed;
* whether local execution was intentionally skipped;
* the CloudLab command or script to run;
* expected output files;
* any assumptions about nodes, venv path, or existing scripts.
