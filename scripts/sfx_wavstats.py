"""Compatibility CLI for WAV statistics in :mod:`whshr.audio`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.audio import (  # noqa: E402,F401
    GROUPS, analyse, find_path_ci,
)
from whshr.audio import wavstats_main as main  # noqa: E402


if __name__ == '__main__':
    main(sys.argv[1:])
