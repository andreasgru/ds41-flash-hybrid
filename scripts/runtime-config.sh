#!/usr/bin/env bash
# Portable installation defaults. Source this file before build/launch checks.
# License: Apache-2.0. Origin: own implementation.
ds41_configure() {
  local script_dir
  script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || return 2
  : "${DS41_ROOT:=$(dirname -- "$script_dir")}" "${DS41_MODEL_DIR:?DS41_MODEL_DIR is required}"
  : "${DS41_RUN_ROOT:=$DS41_ROOT/runs}" "${DS41_PYTHON:=$DS41_ROOT/venv/bin/python}"
  : "${DS41_CACHE_ROOT:=$DS41_ROOT/cache}" "${DS41_TMP_ROOT:=$DS41_ROOT/tmp}"
  : "${DS41_CUDA_HOME:=/usr/local/cuda-13.3}" "${DS41_GPU_DEVICE:=0}"
  : "${DS41_SERVICE_USER:=$(id -un)}" "${DS41_LOCK_FILE:=$DS41_ROOT/state/GPU.lock}"
  : "${DS41_LOCK_OWNER:=ds41-serving}" "${DS41_PLACEMENT:=$DS41_ROOT/config/expert-placement.json}"
  : "${DS41_ENGRAM_DIR:=$DS41_ROOT/engram}"
  : "${DS41_BIND_HOST:=127.0.0.1}" "${SGLANG_PORT:=18081}"
  local key
  for key in DS41_ROOT DS41_MODEL_DIR DS41_RUN_ROOT DS41_PYTHON DS41_CACHE_ROOT DS41_TMP_ROOT DS41_CUDA_HOME DS41_LOCK_FILE DS41_PLACEMENT DS41_ENGRAM_DIR; do
    [[ ${!key} == /* && ${!key} != *$'\n'* && ${!key} != *$'\r'* ]] || { printf 'CONFIG_ABSOLUTE_PATH_REQUIRED %s\n' "$key" >&2; return 2; }
  done
  [[ "$SGLANG_PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$SGLANG_PORT >= 1 && 10#$SGLANG_PORT <= 65535)) || { echo CONFIG_PORT_INVALID >&2; return 2; }
  local octet1 octet2 octet3 octet4
  if [[ "$DS41_BIND_HOST" == '::1' ]]; then
    :
  elif [[ "$DS41_BIND_HOST" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
    octet1=${BASH_REMATCH[1]} octet2=${BASH_REMATCH[2]}
    octet3=${BASH_REMATCH[3]} octet4=${BASH_REMATCH[4]}
    ((10#$octet1 == 127 && 10#$octet2 <= 255 && 10#$octet3 <= 255 && 10#$octet4 <= 255)) || { echo CONFIG_BIND_HOST_LOOPBACK_REQUIRED >&2; return 2; }
    printf -v DS41_BIND_HOST '127.%d.%d.%d' "$((10#$octet2))" "$((10#$octet3))" "$((10#$octet4))"
  else
    echo CONFIG_BIND_HOST_INVALID >&2; return 2
  fi
  printf -v SGLANG_PORT '%d' "$((10#$SGLANG_PORT))"
  [[ "$DS41_GPU_DEVICE" =~ ^[0-9]+(,[0-9]+)*$ ]] || { echo CONFIG_GPU_DEVICE_INVALID >&2; return 2; }
  [[ "$DS41_LOCK_OWNER" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo CONFIG_LOCK_OWNER_INVALID >&2; return 2; }
  export DS41_ROOT DS41_MODEL_DIR DS41_RUN_ROOT DS41_PYTHON DS41_CACHE_ROOT DS41_TMP_ROOT DS41_CUDA_HOME DS41_GPU_DEVICE DS41_SERVICE_USER DS41_LOCK_FILE DS41_LOCK_OWNER DS41_PLACEMENT DS41_BIND_HOST SGLANG_PORT DS41_ENGRAM_DIR
}
