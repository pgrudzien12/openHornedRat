"""Dekoduje klatki .FOL/.BOP (wszystkie 3 typy) i sklada je w arkusz PNG.

Uzycie: render_sprites.py <katalog BINARY> <NAZWA> [pierwsza_klatka] [liczba] [out.png]
np.:    render_sprites.py ".../WARFB/FILE/BINARY" ESHIN 0 24 eshin.png

Kolory RGB z STANDARD.PAL; sprite'y 4-bitowe mapowane przez <NAZWA>.PAL (patrz FORMATS.md).
"""
import os, struct, sys, zlib


def load_rgb_palette(path):
    d = open(path, 'rb').read()
    pal = [(255, 0, 255)] * 256
    for i in range(0, len(d) - 3, 4):
        pal[d[i]] = tuple(d[i + 1:i + 4])
    return pal


def unzero(seg):
    """RLE zer: 00 NN = NN bajtow zerowych, 00 00 = koniec, inny bajt = literal."""
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


def decode_frame(bop, rec, seg_end, colormaps):
    """Zwraca liste w*h indeksow palety (0 = przezroczysty)."""
    _, _, w, h, off, f0 = rec[:6]
    kind, seg = f0 & 0x0F, bop[off:seg_end]
    if kind == 1:                      # surowe 8 bpp
        return list(seg[:w * h])
    bw = (w + 1) // 2
    packed = unzero(seg)[0] if kind == 4 else seg[:bw * h]   # 4: RLE, 2: surowe 4 bpp
    cmap = colormaps[f0 >> 4] if (f0 >> 4) < len(colormaps) else None
    px = []
    for r in range(h):
        for c in range(w):
            b = packed[r * bw + c // 2]
            if cmap:
                px.append(cmap[b * 2 + (c & 1)])   # wpis bajtu = (lewy piksel, prawy piksel)
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
    offsets = sorted(set(r[4] for r in recs)) + [len(bop)]
    sel = recs[first:first + count]
    cw, ch = max(r[2] for r in sel) + 2, max(r[3] for r in sel) + 2
    W, H = cw * cols, ch * ((len(sel) + cols - 1) // cols)
    img = [(40, 40, 48)] * (W * H)
    for k, r in enumerate(sel):
        px = decode_frame(bop, r, offsets[offsets.index(r[4]) + 1], colormaps)
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
