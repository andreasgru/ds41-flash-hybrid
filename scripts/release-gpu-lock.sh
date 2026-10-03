#!/usr/bin/env bash
# Release entry; service environment identifies the configured reservation.
# Origin: own implementation. Apache-2.0.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec "${DS41_PYTHON:?DS41_PYTHON required}" "$script_dir/gpu_lock.py" release --run-dir "${1:?run directory required}"
