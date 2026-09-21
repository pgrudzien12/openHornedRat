#!/usr/bin/env python3
"""Dump and verify the static RMYI roster table of WHSHR.EXE (notes/campaign.md 4.5).

Usage: roster_check.py <WARFB dir>   (reads WHSHR.EXE and SAVE/savegame.*)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from whshr.rules import PeImage  # noqa: E402

TABLE_VA, COUNT, STRIDE = 0x5B95F0, 39, 0x34
KEEP = {21, 23, 24, 29, 31, 33}
NOT_HIRE = {2, *range(8, 14), *range(21, 25), 29, 30, 31, *range(33, 38)}
WIZARD, ARTILLERY = {18, 19, 20}, {14, 15, 16, 17, 25}


def records(blob):
    return [struct.unpack_from('<13i', blob, STRIDE * i) for i in range(COUNT)]


def main(game):
    game = Path(game)
    static = records(PeImage(game / 'WHSHR.EXE').read(TABLE_VA, COUNT * STRIDE))
    errors = []
    if any(v != -1 for v in static[-1]):
        errors.append('record 38 is not the -1 terminator')
    for w, r in enumerate(static[:-1]):
        if (r[0] == 1) != (w in KEEP) or (r[1] == 0) != (w in NOT_HIRE):
            errors.append(f'{w}: keep/forHire mismatch')
        if (r[2] == 1) != (w in WIZARD) or (r[3] == 1) != (w in ARTILLERY):
            errors.append(f'{w}: wizard/artillery mismatch')
        print(w, 'price', r[9])
    for save in sorted((game / 'SAVE').glob('savegame.*')):
        d = save.read_bytes()
        p = d.find(b'RMYI')
        saved = records(d[p + 8:p + 8 + COUNT * STRIDE])
        for w in range(COUNT - 1):
            if saved[w][9] != 2 * static[w][9] or saved[w][10] != 2 * static[w][9]:
                errors.append(f'{save.name} {w}: price is not 2x static')
    print('\n'.join(errors) or 'OK: flags and 2x prices verified')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
