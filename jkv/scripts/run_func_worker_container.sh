#!/usr/bin/env sh
set -eu

IMAGE="${JKV_L1_CONTAINER_IMAGE:-faaspe/jkv-func-worker:latest}"
CPUS="${JKV_L1_CPUS:-1}"
MEMORY="${JKV_L1_MEMORY:-128m}"
PIDS="${JKV_L1_PIDS_LIMIT:-64}"

exec docker run \
  --rm \
  -i \
  --network=none \
  --cpus="${CPUS}" \
  --memory="${MEMORY}" \
  --pids-limit="${PIDS}" \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  "${IMAGE}"
