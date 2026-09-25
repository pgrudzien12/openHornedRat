#!/bin/sh
# Static type check (pyright, configured by pyrightconfig.json). Modules listed under "strict" there are
# fully annotated and held to pyright's strict mode; everything else only gets the basic call/name checks.
# Install once with:  uv tool install pyright
cd "$(dirname "$0")" || exit 1
if ! command -v pyright >/dev/null 2>&1; then
    echo "pyright not found: uv tool install pyright" >&2
    exit 2
fi
exec pyright "$@"
