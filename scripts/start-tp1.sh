#!/usr/bin/env bash
# Portable live r3 entry. Origin: own implementation. Apache-2.0.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$script_dir/runtime-config.sh"
ds41_configure
source "$script_dir/standard-env.sh"
ds41_standard_env
case "${1:---print-command}" in
  --print-command|--resolve) exec "$DS41_PYTHON" "$script_dir/resolve_launcher.py" --print-command;;
  --run|--supervise) exec "$DS41_PYTHON" "$script_dir/supervisor.py" "$1";;
  --start-standard) exec "$DS41_PYTHON" "$script_dir/standard_start.py";;
  *) echo LAUNCHER_MODE_INVALID >&2; exit 2;;
esac
