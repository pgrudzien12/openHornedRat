"""Compatibility CLI for :mod:`whshr.sprites`.

Usage: render_sprites.py <BINARY dir> <NAME> [first_frame] [count] [out.png]
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.image import load_rgb_palette, write_png  # noqa: E402,F401
from whshr.sprites import (  # noqa: E402,F401
    colormap_indices, decode_frame, main, unzero,
)


if __name__ == '__main__':
    args = sys.argv[1:]
    main(
        args[0], args[1],
        int(args[2]) if len(args) > 2 else 0,
        int(args[3]) if len(args) > 3 else 24,
        args[4] if len(args) > 4 else None,
    )
