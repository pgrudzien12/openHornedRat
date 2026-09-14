"""CLI wrapper around whshr.smacker: dumps decoded Smacker frames to PNG.

Used to verify the films rebuilt by si_omni.py visually without ffmpeg. Video and
palette only (audio is ignored; the .SI films have no audio tracks anyway).
The decoder itself lives in whshr/smacker.py, reused by the real-time engine.

Usage: si_smacker.py <file.smk> <out prefix> <frame> [<frame> ...] [--sheet N] [--scale S]
e.g.:  si_smacker.py extracted/si/A1/Scene1AnimA1.smk extracted/si/png/A1 0 100 400
       si_smacker.py extracted/si/A1/Scene1AnimA1.smk extracted/si/png/A1 --sheet 12
         (--sheet N: contact sheet of N frames evenly spread over the film, half size)
Frames are deltas, so decoding frame k decodes all frames 0..k.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from render_sprites import write_png  # noqa: E402
from whshr.smacker import Smacker  # noqa: E402


def main(argv):
    path, prefix = argv[0], argv[1]
    rest = argv[2:]
    sheet = None
    if '--sheet' in rest:
        i = rest.index('--sheet')
        sheet = int(rest[i + 1])
        del rest[i:i + 2]
    smk = Smacker(open(path, 'rb').read())
    print('%s: %dx%d, %d frames, rate %d, flags %d' % (path, smk.w, smk.h, smk.nframes,
                                                        smk.rate, smk.flags))
    os.makedirs(os.path.dirname(prefix) or '.', exist_ok=True)
    for k in sorted(int(x) for x in rest):
        smk.decode_to(k)
        w, h, rgb = smk.rgb()
        out = '%s_f%04d.png' % (prefix, k)
        write_png(out, w, h, rgb)
        print('  frame %d (t = %.3f s at 125 ms/frame) -> %s' % (k, k * 0.125, out))
    if sheet:
        idx = [round(i * (smk.nframes - 1) / max(sheet - 1, 1)) for i in range(sheet)]
        cols = 3
        tiles = []
        for k in idx:
            smk.decode_to(k)
            tiles.append(smk.rgb(2))
        tw, th = tiles[0][0], tiles[0][1]
        rows = (len(tiles) + cols - 1) // cols
        W, H = cols * tw + (cols - 1) * 4, rows * th + (rows - 1) * 4
        canvas = bytearray(b'\x40' * (W * H * 3))
        for n, (_, _, rgb) in enumerate(tiles):
            ox, oy = (n % cols) * (tw + 4), (n // cols) * (th + 4)
            for y in range(th):
                dst = ((oy + y) * W + ox) * 3
                canvas[dst:dst + tw * 3] = rgb[y * tw * 3:(y + 1) * tw * 3]
        out = '%s_sheet.png' % prefix
        write_png(out, W, H, canvas)
        print('  sheet of frames %s -> %s' % (idx, out))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1:])
