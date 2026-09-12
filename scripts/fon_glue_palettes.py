"""Analyzes and renders the front-end ("glue") palettes FILE/BINARY/GLUE/*.PAL.

Usage: fon_glue_palettes.py <WARFB directory> [out.png] [cell_px]
       fon_glue_palettes.py <WARFB directory> --dib
       fon_glue_palettes.py <WARFB directory> --render <BITMAP name> <screen> out.png ["text"]
e.g.:  fon_glue_palettes.py ".../WARFB" extracted/fonts_glue/glue_palettes.png 4
       fon_glue_palettes.py ".../WARFB" --render TITLESCREEN TITL title.png "Shadow of the Horned Rat"

--dib groups the bitmaps of FILE/DLL/BITMAP.DLL by color table and prints the best-matching
GLUE*/WIND* palette. --render draws one 8 bpp bitmap using ONLY STANDARD + GLUE<screen> +
WIND<screen> (screen = BOOK, MAP, CAR, MIND, END, TITL, GAME, OPT, BK2, REND), with optional
text in GOTHTEXT.FON.

Prints one line per palette (size, index range, sequential or not, identical files, mean color,
agreement with STANDARD.PAL / PANEL.PAL) and renders all palettes as 256-cell strips with labels.
Indices a file does not define are drawn as a dark checkerboard. Extra rows at the bottom show
each GLUExxx.PAL + WINDxxx.PAL pair merged over STANDARD.PAL (the full 10..245 range).
All .PAL files here are variant A (records [index, R, G, B]), see FORMATS.md.
"""
import glob, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_sprites import write_png
from fon_parse import tiny_text

# order in which WHSHR.EXE lists the palettes (both tables: windxxx.pal and gluexxx.pal)
EXE_ORDER = ['BOOK', 'MAP', 'CAR', 'MIND', 'END', 'TITL', 'GAME', 'OPT', 'BK2']


def find(d, name):
    """Case-insensitive lookup of a file in a directory."""
    for f in os.listdir(d):
        if f.upper() == name.upper():
            return os.path.join(d, f)
    return None


def read_pal(path):
    """Variant A: returns (dict index -> (r,g,b), list of indices in file order)."""
    d = open(path, 'rb').read()
    if len(d) % 4:
        raise ValueError(f'{path}: size {len(d)} is not a multiple of 4')
    idx = [d[i] for i in range(0, len(d), 4)]
    return {d[i]: tuple(d[i + 1:i + 4]) for i in range(0, len(d), 4)}, idx


def main(root, out=None, cell=4):
    glue = os.path.join(root, 'FILE', 'BINARY', 'GLUE')
    std_path = find(os.path.join(root, 'UPDATE', 'BINARY'), 'STANDARD.PAL') or \
        find(os.path.join(root, 'FILE', 'BINARY'), 'STANDARD.PAL')
    panel_path = find(os.path.join(root, 'UPDATE', 'BINARY'), 'PANEL.PAL') or \
        find(os.path.join(root, 'FILE', 'BINARY'), 'PANEL.PAL')
    std, _ = read_pal(std_path)
    panel, _ = read_pal(panel_path)
    paths = sorted(glob.glob(os.path.join(glue, '*.PAL')) + glob.glob(os.path.join(glue, '*.pal')))
    pals, raw = {}, {}
    print(f"{'file':13s} {'bytes':>5s} {'n':>4s} range    seq  mean RGB        =STANDARD =PANEL  identical to")
    for p in paths:
        name = os.path.basename(p).upper()[:-4]
        pal, idx = read_pal(p)
        pals[name], raw[name] = pal, open(p, 'rb').read()
    for name, pal in pals.items():
        idx = sorted(pal)
        seq = idx == list(range(idx[0], idx[0] + len(idx)))
        mean = tuple(sum(c[k] for c in pal.values()) // len(pal) for k in range(3))
        same_std = sum(1 for i, c in pal.items() if std.get(i) == c)
        same_panel = sum(1 for i, c in pal.items() if panel.get(i) == c)
        twins = [n for n in pals if n != name and raw[n] == raw[name]]
        print(f"{name:13s} {len(raw[name]):5d} {len(pal):4d} {idx[0]:3d}-{idx[-1]:3d}  {'yes' if seq else 'NO '}"
              f"  ({mean[0]:3d},{mean[1]:3d},{mean[2]:3d})  {same_std:5d}     {same_panel:5d}   {' '.join(twins)}")
    # shared entries between palettes of the same family
    for fam in ('GLUE', 'WIND'):
        names = [n for n in pals if n.startswith(fam)]
        common = [i for i in sorted(pals[names[0]]) if len({pals[n].get(i) for n in names}) == 1]
        print(f"{fam}*: {len(common)} indices identical in all {len(names)} files: "
              f"{common[:12]}{'...' if len(common) > 12 else ''}")
    missing = [s for s in EXE_ORDER if f'GLUE{s}' not in pals or f'WIND{s}' not in pals]
    extra = [n for n in pals if n[4:] not in EXE_ORDER]
    print(f"not referenced by WHSHR.EXE: {extra}; referenced but missing: {missing}")

    if not out:
        return
    rows = [(n, pals[n]) for n in sorted(pals)]
    rows += [('STANDARD', std), ('PANEL', panel)]
    for s in EXE_ORDER:
        merged = dict(std)
        merged.update(pals[f'GLUE{s}'])
        merged.update(pals[f'WIND{s}'])
        rows.append((f'GLUE{s}+WIND{s}', merged))
    label_w, rh = 72, cell * 3 + 2
    W = label_w + 256 * cell
    H = 10 + len(rows) * rh
    cv = [(24, 24, 30)] * (W * H)
    for k in range(0, 256, 16):                      # index ruler
        tiny_text(cv, W, label_w + k * cell, 2, f'{k:02X}', (150, 150, 165))
    for r, (name, pal) in enumerate(rows):
        y0 = 10 + r * rh
        tiny_text(cv, W, 2, y0 + (rh - 5) // 2, name, (230, 200, 120))
        for i in range(256):
            for j in range(rh - 2):
                for x in range(cell):
                    if i in pal:
                        c = pal[i]
                    else:
                        c = (44, 44, 52) if ((x + j) // 2) % 2 else (30, 30, 36)
                    cv[(y0 + j) * W + label_w + i * cell + x] = c
    rgb = bytearray()
    for c in cv:
        rgb += bytes(c)
    write_png(out, W, H, rgb)


def dib(pe, res):
    """RT_BITMAP resource -> (w, h, bpp, compression, color table [(r,g,b)], pixel bytes)."""
    d = pe.data(res)
    hs, w, h, _, bpp, comp, _, _, _, used, _ = struct.unpack_from('<IiiHHIIiiII', d, 0)
    n = (used or (1 << bpp)) if bpp <= 8 else 0
    ct = [tuple(d[hs + 4 * i:hs + 4 * i + 3][::-1]) for i in range(n)]   # RGBQUAD = B,G,R,0
    return w, h, bpp, comp, ct, d[hs + 4 * n:]


def glue_pals(root):
    glue = os.path.join(root, 'FILE', 'BINARY', 'GLUE')
    return {os.path.basename(p).upper()[:-4]: read_pal(p)[0]
            for p in glob.glob(os.path.join(glue, '*.[Pp][Aa][Ll]'))}


def share(pal, ct):
    """Fraction of the .PAL entries equal to the same index in a DIB color table."""
    return sum(1 for i, c in pal.items() if i < len(ct) and ct[i] == c) / len(pal)


def dib_report(root):
    """Groups BITMAP.DLL bitmaps by identical color table and finds the best GLUE*/WIND* match."""
    from pe_resources import PE
    pe = PE(os.path.join(root, 'FILE', 'DLL', 'BITMAP.DLL'))
    pals = glue_pals(root)
    groups = {}
    for r in pe.resources():
        if r.type != 2:
            continue
        w, h, bpp, comp, ct, _ = dib(pe, r)
        groups.setdefault(tuple(ct), []).append((r.name, w, h))
    print(f"{'bitmaps':>7s}  {'best GLUE (share)':22s} {'best WIND (share)':22s} examples (largest first)")
    for ct, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        best = {}
        for fam in ('GLUE', 'WIND'):
            best[fam] = max((share(p, ct), n) for n, p in pals.items() if n.startswith(fam))
        ex = ', '.join(f'{n} {w}x{h}' for n, w, h in sorted(items, key=lambda t: -t[1] * t[2])[:4])
        print(f"{len(items):7d}  {best['GLUE'][1]:13s} {best['GLUE'][0]:5.0%}   "
              f"{best['WIND'][1]:13s} {best['WIND'][0]:5.0%}   {ex}")


def render_dib(root, name, screen, out, text=None, scale=1):
    """Draws an 8 bpp DIB from BITMAP.DLL with colors taken ONLY from STANDARD.PAL +
    GLUE<screen>.PAL + WIND<screen>.PAL (the DIB's own color table is ignored), optionally
    with a line of text in GOTHTEXT.FON on top - a visual check of the palettes and fonts."""
    from pe_resources import PE
    from fon_parse import load_fon
    pe = PE(os.path.join(root, 'FILE', 'DLL', 'BITMAP.DLL'))
    res = [r for r in pe.resources() if r.type == 2 and str(r.name).upper() == name.upper()][0]
    w, h, bpp, comp, _, px = dib(pe, res)
    if bpp != 8 or comp != 0:
        raise ValueError(f'{name}: only uncompressed 8 bpp DIBs are supported ({bpp} bpp, comp {comp})')
    pals = glue_pals(root)
    std_path = find(os.path.join(root, 'UPDATE', 'BINARY'), 'STANDARD.PAL')
    pal = dict(read_pal(std_path)[0])
    pal.update(pals[f'GLUE{screen.upper()}'])
    pal.update(pals[f'WIND{screen.upper()}'])
    stride = (w + 3) & ~3                           # DIB rows padded to 4 bytes, stored bottom-up
    img = [pal.get(px[(h - 1 - y) * stride + x], (255, 0, 255)) for y in range(h) for x in range(w)]
    if text:
        f = load_fon(find(os.path.join(root, 'FILE', 'BINARY', 'GLUE'), 'GOTHTEXT.FON')).fonts[0]
        tw, th, bits = f.render(text)
        ox, oy = max(0, (w - tw) // 2), h - th - 12
        for j in range(th):
            for i in range(min(tw, w - ox)):
                if bits[j * tw + i]:
                    img[(oy + j + 2) * w + ox + i + 2] = (0, 0, 0)      # shadow
        for j in range(th):
            for i in range(min(tw, w - ox)):
                if bits[j * tw + i]:
                    img[(oy + j) * w + ox + i] = (255, 230, 150)
    rgb = bytearray()
    for y in range(h * scale):
        for x in range(w * scale):
            rgb += bytes(img[(y // scale) * w + x // scale])
    write_png(out, w * scale, h * scale, rgb)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif len(a) > 1 and a[1] == '--dib':
        dib_report(a[0])
    elif len(a) > 4 and a[1] == '--render':
        render_dib(a[0], a[2], a[3], a[4], a[5] if len(a) > 5 else None)
    else:
        main(a[0], a[1] if len(a) > 1 else None, int(a[2]) if len(a) > 2 else 4)
