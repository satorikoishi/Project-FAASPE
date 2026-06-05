# J-KV

## Dependency

- protobuf 5.28.1
- libzmq3-dev
- libspdlog-dev
- libfmt-dev
- libconfig++-dev

## Quick Start

1. Config setting

```shell
cp config/config.example config/config.ini
```

Modify config.ini to desired address

2. Run server

```shell
make
./build/jkv_server
```

3. Run cache (In separate terminal)

```shell
make
./build/cache_server
```

4. Run client (In separate terminal)

```shell
./build/ping_client
```

Or

```shell
python3 pyclient/client.py
```

## TODO

- ~~Check pingpong latency with cpp client~~
- ~~Try zmq~~
- LWW Cache
- OCC Serializable Cache
- Cache doc
- Separate thread for cache