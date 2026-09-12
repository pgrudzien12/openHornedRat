"""Decodes .FOL/.BOP frames (all 3 types) and assembles them into a PNG sheet.

Usage: render_sprites.py <BINARY dir> <NAME> [first_frame] [count] [out.png]
e.g.:  render_sprites.py ".../WARFB/FILE/BINARY" ESHIN 0 24 eshin.png

RGB colors come from STANDARD.PAL; 4-bit sprites are mapped through <NAME>.PAL (see FORMATS.md).
"""
import os, struct, sys, zlib


def load_rgb_palette(path):
    d = open(path, 'rb').read()
    pal = [(255, 0, 255)] * 256
    for i in range(0, len(d) - 3, 4):
        pal[d[i]] = tuple(d[i + 1:i + 4])
    return pal


def unzero(seg):
    """Zero RLE: 00 NN = NN zero bytes, 00 00 = end, any other byte = literal."""
    out, i = bytearray(), 0
    while True:
        if seg[i] == 0:
            n = seg[i + 1]
            i += 2
            if n == 0:
                return bytes(out), i
            out += bytes(n)
        else:
            out.append(seg[i])
            i += 1


def colormap_indices(recs):
    """Full color map index per record (None for type-1 frames).

    Frames of types 2 and 4 are stored grouped by map in increasing order, and the upper
    nibble of kind is the map number modulo 16: every drop of the nibble adds 16.
    Only matters for SPELLS (43 maps); see FORMATS.md, "Color map".
    """
    out, wraps, prev = [], 0, None
    for r in recs:
        if (r[5] & 0x0F) not in (2, 4):
            out.append(None)
            continue
        n = r[5] >> 4
        if prev is not None and n < prev:
            wraps += 1
        out.append(n + 16 * wraps)
        prev = n
    return out


def decode_frame(bop, rec, seg_end, colormaps, map_index=None):
    """Returns a list of w*h palette indices (0 = transparent).

    map_index: full color map index from colormap_indices(); defaults to the plain nibble,
    which is correct for every file except SPELLS.
    """
    _, _, w, h, off, f0 = rec[:6]
    kind, seg = f0 & 0x0F, bop[off:seg_end]
    if kind == 1:                      # raw 8 bpp
        return list(seg[:w * h])
    bw = (w + 1) // 2
    packed = unzero(seg)[0] if kind == 4 else seg[:bw * h]   # 4: RLE, 2: raw 4 bpp
    m = f0 >> 4 if map_index is None else map_index
    cmap = colormaps[m] if m < len(colormaps) else None
    px = []
    for r in range(h):
        for c in range(w):
            b = packed[r * bw + c // 2]
            if cmap:
                px.append(cmap[b * 2 + (c & 1)])   # byte entry = (left pixel, right pixel)
            else:
                px.append(((b >> 4) if c % 2 == 0 else (b & 15)) * 16)
    return px


def write_png(path, w, h, rgb):
    raw = b''.join(b'\0' + bytes(rgb[r * w * 3:(r + 1) * w * 3]) for r in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n'
                           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main(bindir, name, first=0, count=24, out=None, cols=8, scale=3):
    fol = open(f"{bindir}/{name}.FOL", 'rb').read()
    bop = open(f"{bindir}/{name}.BOP", 'rb').read()
    pal_path = f"{bindir}/{name}.PAL"
    pd = open(pal_path, 'rb').read() if os.path.exists(pal_path) else b''
    colormaps = [pd[i:i + 512] for i in range(0, len(pd), 512)] if pd and len(pd) % 512 == 0 else []
    rgb_pal = load_rgb_palette(f"{bindir}/STANDARD.PAL")

    recs = [struct.unpack_from('<hhhhIB', fol, i * 16) for i in range(len(fol) // 16)]
    maps = colormap_indices(recs)
    offsets = sorted(set(r[4] for r in recs)) + [len(bop)]
    sel = recs[first:first + count]
    cw, ch = max(r[2] for r in sel) + 2, max(r[3] for r in sel) + 2
    W, H = cw * cols, ch * ((len(sel) + cols - 1) // cols)
    img = [(40, 40, 48)] * (W * H)
    for k, r in enumerate(sel):
        px = decode_frame(bop, r, offsets[offsets.index(r[4]) + 1], colormaps, maps[first + k])
        ox, oy = (k % cols) * cw + 1, (k // cols) * ch + 1
        for j in range(r[3]):
            for i in range(r[2]):
                if px[j * r[2] + i]:
                    img[(oy + j) * W + ox + i] = rgb_pal[px[j * r[2] + i]]
    rgb = bytearray()
    for j in range(H * scale):
        for i in range(W * scale):
            rgb += bytes(img[(j // scale) * W + i // scale])
    write_png(out or f"{name.lower()}.png", W * scale, H * scale, rgb)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[1], int(a[2]) if len(a) > 2 else 0, int(a[3]) if len(a) > 3 else 24,
         a[4] if len(a) > 4 else None)
