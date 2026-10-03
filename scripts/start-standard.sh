#!/usr/bin/env bash
# Explicit standard-start entry. Origin: own implementation. Apache-2.0.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
case "${1:-}" in
  --print-command) exec /bin/bash "$script_dir/start-tp1.sh" --print-command;;
  --start-standard) exec /bin/bash "$script_dir/start-tp1.sh" --start-standard;;
  *) echo 'Usage: start-standard.sh --print-command|--start-standard' >&2;exit 2;;
esac
