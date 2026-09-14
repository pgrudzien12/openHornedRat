#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    printf 'Usage: %s <WARFB installation> [engine options...]\n' "$0" >&2
    exit 2
fi

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python="$repository_root/.venv/bin/python"
if [ ! -x "$python" ]; then
    printf 'error: %s not found; create it with:\n' "$python" >&2
    printf '  python3 -m venv "%s/.venv" && "%s" -m pip install --only-binary=:all: -r "%s/requirements-engine.txt"\n' \
        "$repository_root" "$python" "$repository_root" >&2
    exit 1
fi
exec "$python" -m whshr engine "$@"
