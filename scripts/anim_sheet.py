"""Analysis sheet: all (or selected) frames of a sprite in a grid, labelled with the frame
number, the group number (colour-map nibble) and the anchor point from bytes 2-3 of the
.FOL record.

Usage: anim_sheet.py <WARFB or BINARY dir> <NAME> [out.png] [--first=0] [--count=N]
                     [--cols=8] [--scale=2] [--no-marks]
e.g.:  anim_sheet.py ".../WARFB" ESHIN extracted/animations/eshin_raw.png --cols=8

Cell markings:
  top-left: frame number; top-right: group (kind >> 4)
  yellow vertical line: x = record byte 3; red horizontal line: y = h - 1 - byte 2
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim_lib import Canvas, Sprite, find_bindirs    # noqa: E402


def render_sheet(sprite, frames, cols=8, marks=True):
    cw = max(sprite.recs[i][2] for i in frames) + 4
    ch = max(sprite.recs[i][3] for i in frames) + 10
    rows = (len(frames) + cols - 1) // cols
    cv = Canvas(cw * cols, ch * rows)
    for k, i in enumerate(frames):
        hx, hy, w, h, off, f0, f1, f2, f3 = sprite.recs[i]
        ox, oy = (k % cols) * cw + 2, (k // cols) * ch + 8
        cv.fill(ox, oy, w, h, (56, 56, 66))
        cv.blit(sprite, i, ox, oy)
        if marks:
            b2, b3 = sprite.anchor(i)
            for y in range(oy, oy + h, 2):
                cv.dot(ox + b3, y, (255, 220, 0))
            for x in range(ox, ox + w, 2):
                cv.dot(x, oy + h - 1 - b2, (255, 60, 60))
        cv.text(ox, oy - 7, str(i), (255, 255, 255))
        cv.text(ox + w - 4, oy - 7, '%X' % (f0 >> 4), (120, 200, 255))
    return cv


def main(argv):
    opts = {a[2:].split('=')[0]: (a.split('=', 1)[1] if '=' in a else True) for a in argv if a.startswith('--')}
    args = [a for a in argv if not a.startswith('--')]
    s = Sprite(find_bindirs(args[0]), args[1])
    out = args[2] if len(args) > 2 else s.name.lower() + '_raw.png'
    first = int(opts.get('first', 0))
    count = int(opts.get('count', len(s) - first))
    cv = render_sheet(s, list(range(first, min(first + count, len(s)))), int(opts.get('cols', 8)),
                      not opts.get('no-marks'))
    cv.png(out, int(opts.get('scale', 2)))
    print(out, cv.w, cv.h)


if __name__ == '__main__':
    main(sys.argv[1:])
