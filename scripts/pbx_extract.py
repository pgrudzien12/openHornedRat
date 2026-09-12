"""Compatibility CLI for :mod:`whshr.pbx`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.pbx import *  # noqa: F401,F403,E402
from whshr.pbx import main as _main  # noqa: E402


if __name__ == '__main__':
    _main(sys.argv[1:])
