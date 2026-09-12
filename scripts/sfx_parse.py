"""Compatibility CLI for the SFX parser in :mod:`whshr.audio`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.audio import (  # noqa: E402,F401
    CHUNK_ORDER, FLAGS, RECORD_FIELDS, RECORD_SIZE, WRITER_OVERHEAD,
    analyse_install, find_ci, flag_names, loadsfx_usage, packet_table, parse_sfx,
    print_check, print_package, resolve, split_names, u32,
)
from whshr.audio import sfx_main as main  # noqa: E402


if __name__ == '__main__':
    main(sys.argv[1:])
