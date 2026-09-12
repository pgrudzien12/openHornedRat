"""Compatibility CLI for the MIDI parser in :mod:`whshr.audio`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.audio import (  # noqa: E402,F401
    META_TEXT, find_midis, parse_midi, parse_track, programs_used, read_vlq,
    tempo_seconds,
)
from whshr.audio import midi_main as main  # noqa: E402
from whshr.audio import midi_summary as summary  # noqa: E402


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
