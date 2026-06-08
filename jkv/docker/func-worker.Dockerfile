FROM debian:bookworm-slim

COPY build/jkv_func_worker /usr/local/bin/jkv_func_worker

USER nobody:nogroup
ENTRYPOINT ["/usr/local/bin/jkv_func_worker"]
