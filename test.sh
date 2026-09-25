#!/bin/sh
# Runs the test suite with the project's own virtualenv (pygame-ce/zengl live there; the system
# python3 lacks them and reports spurious import errors). Extra arguments go to unittest, e.g.
#   ./test.sh tests.test_combat        ./test.sh -v tests.test_engine
# ResourceWarnings are suppressed; the exit status is unittest's.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "missing .venv: python3 -m venv .venv && .venv/bin/pip install --only-binary=:all: -r requirements-engine.txt" >&2
    exit 2
fi
if [ "$#" -eq 0 ]; then set -- discover -s tests -t .; fi
exec .venv/bin/python -W ignore::ResourceWarning -m unittest "$@"
