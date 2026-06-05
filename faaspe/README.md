# FAASPE

## Dependency

- protobuf 5.28.1
- pyzmq 26.2.0
- python fabric

## Usage

1. Run platform

```shell
# Start Platform Server
$ ./platform/function.py

# Commands
$ ./platform/cli.py --help
$ ./platform/cli.py create hello-world
$ ./platform/cli.py invoke hello-world
$ ./platform/cli.py delete hello-world
```

2. Run bench

- (Optional) If run on cloudlab, fulfill nodes.txt and

```shell
$ fab init
```

- First start plarform and create function

```shell
$ fab run {function_name}
```

## TODO

- ~~Python built-in cache, let function be long-running server (Normal consistency, not causal)~~