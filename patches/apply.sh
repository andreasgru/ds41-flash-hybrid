#!/usr/bin/env bash
set -Eeuo pipefail
script_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/python3 -B "$script_root/apply-series.py" "$@"
