"""Compatibility CLI for :mod:`whshr.script`."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.script import *  # noqa: F401,F403,E402
from whshr.script import main as _main  # noqa: E402


if __name__ == '__main__':
    _main()
