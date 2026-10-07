"""PyInstaller entry point shared by frozen packages.

The standalone GUI launcher (epic #88) does not exist yet, so this freezes
`python -m whshr engine` as-is: it forwards any command-line arguments and
otherwise falls back to the `WARFB` environment variable, exactly like the
`engine` subcommand does when run from source. Once #88 lands, point the
PyInstaller specs' entry point at it instead.
"""
import sys

from whshr.__main__ import main

if __name__ == "__main__":
    sys.exit(main(["engine", *sys.argv[1:]]) or 0)
