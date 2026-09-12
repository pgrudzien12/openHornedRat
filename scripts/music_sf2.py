"""Compatibility CLI for the SoundFont parser in :mod:`whshr.audio`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.audio import (  # noqa: E402,F401
    GEN_NAMES, GM_PROGRAMS, PDTA_RECORDS, RANGE_GENS, SF1_SHDR, UNSIGNED_GENS,
    cstr, extract_samples, gen_value, gm_name, iter_chunks, parse_sf2, sample_pcm,
)
from whshr.audio import sf2_main as main  # noqa: E402
from whshr.audio import sf2_summary as summary  # noqa: E402


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
