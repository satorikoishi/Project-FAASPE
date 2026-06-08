#!/usr/bin/env sh
set -eu

IMAGE="${JKV_L1_CONTAINER_IMAGE:-faaspe/jkv-func-worker:latest}"

docker build \
  -f docker/func-worker.Dockerfile \
  -t "${IMAGE}" \
  .
