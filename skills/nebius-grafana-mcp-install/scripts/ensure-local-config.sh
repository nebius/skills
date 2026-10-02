#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || {
  printf '%s\n' 'Python 3.11 or newer is required.' >&2
  exit 1
}
exec python3 -B "$script_dir/setup.py" "$@"
