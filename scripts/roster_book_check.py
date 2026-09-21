#!/usr/bin/env python3
"""Dump and verify the roster-book (Army Records) per-whoami name tables of WHSHR.EXE
(notes/troop_selection.md sections 8-9): regiment picture bitmap name and description text name.

Usage: roster_book_check.py <WARFB dir>   (reads WHSHR.EXE, FILE/DLL/BITMAP.DLL, FILE/DLL/BKTXT.DLL)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from whshr.rules import PeImage  # noqa: E402
from pe_resources import PE  # noqa: E402

PIC_VA, TEXT_VA, COUNT = 0x5B9550, 0x5B9230, 38


def names(exe, va):
    return [exe.cstring(p) if p else None for p in exe.u32(va, COUNT)]


def resource_names(path, kind):
    return {str(r.name).upper() for r in PE(path).resources() if r.type == kind}


def main(game):
    game = Path(game)
    exe = PeImage(game / 'WHSHR.EXE')
    pics, texts = names(exe, PIC_VA), names(exe, TEXT_VA)
    bitmaps = resource_names(game / 'FILE/DLL/BITMAP.DLL', 2)
    rcdata = resource_names(game / 'FILE/DLL/BKTXT.DLL', 10)
    errors = []
    for w in range(COUNT):
        print(w, pics[w], texts[w])
        if pics[w] and pics[w].upper() not in bitmaps:
            errors.append(f'{w}: bitmap {pics[w]} not in BITMAP.DLL')
        if texts[w] and texts[w].upper() not in rcdata:
            errors.append(f'{w}: text {texts[w]} not in BKTXT.DLL')
    print('\n'.join(errors) or 'OK: all names resolve to resources')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
