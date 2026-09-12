"""Helpers for the btp_* scripts: file lookup, .FOL layouts, color map index, sheets.

Not a CLI; imported by scripts/btp_leftovers.py. Example:
    from btp_lib import binary_dir, read_fol16, extended_map_indices
    b = binary_dir(".../WARFB")             # UPDATE/BINARY if present, else FILE/BINARY
    recs = read_fol16(open(find(b, "SPELLS.FOL"), "rb").read())
    maps = extended_map_indices(recs)       # 0..42 for SPELLS (see notes/btp_sprite_leftovers.md)

Python 3 stdlib only. Reuses decode_frame/unzero/write_png/load_rgb_palette from render_sprites.py.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_sprites import decode_frame, load_rgb_palette, unzero, write_png  # noqa: E402,F401

BG = (40, 40, 48)


def find(directory, name):
    """Case-insensitive lookup of a file name in a directory; None if missing."""
    want = name.upper()
    for f in os.listdir(directory):
        if f.upper() == want:
            return os.path.join(directory, f)
    return None


def read(directory, name):
    p = find(directory, name)
    return open(p, 'rb').read() if p else None


def binary_dir(game, prefer_update=True):
    """WARFB/UPDATE/BINARY (takes precedence) or WARFB/FILE/BINARY."""
    for sub in (('UPDATE', 'BINARY'), ('FILE', 'BINARY')) if prefer_update else (('FILE', 'BINARY'),):
        d = os.path.join(game, *sub)
        if os.path.isdir(d):
            return d
    raise SystemExit(f"no BINARY directory under {game}")


def listing(directory):
    """Map UPPERCASE name -> real name for plain files in a directory."""
    return {f.upper(): f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))}


# ---------------------------------------------------------------- .FOL layouts

def read_fol16(fol):
    """Standard 16-byte records: (hx, hy, w, h, bop_offset, f0, f1, f2, f3)."""
    return [struct.unpack_from('<hhhhI4B', fol, i) for i in range(0, len(fol) - 15, 16)]


def read_fol12(fol):
    """Legacy 12-byte records (HALBERD, SPRITE3): (hx, hy, w, h, bop_offset), raw 8 bpp frames."""
    return [struct.unpack_from('<hhhhI', fol, i) for i in range(0, len(fol) - 11, 12)]


def read_fol8(fol):
    """Legacy 8-byte records (ICON2): (unk16, w, h, bop_offset) with w/h as u8, raw 8 bpp frames."""
    return [struct.unpack_from('<HBBI', fol, i) for i in range(0, len(fol) - 7, 8)]


def contiguous_raw(frames, bop_len):
    """frames = [(w, h, off)]; True if the raw 8 bpp frames tile the .BOP exactly, in order."""
    pos = 0
    for w, h, off in frames:
        if off != pos or w <= 0 or h <= 0:
            return False
        pos = off + w * h
    return pos == bop_len


def fol_layout(fol, bop_len):
    """Detect the record layout: 16 (standard), 12 or 8 (legacy raw 8 bpp), or None."""
    if len(fol) % 16 == 0 and fol:
        recs = read_fol16(fol)
        if all(r[8] == 0x40 and (r[5] & 15) in (1, 2, 4) for r in recs):
            return 16
    if len(fol) % 12 == 0 and bop_len is not None:
        if contiguous_raw([(r[2], r[3], r[4]) for r in read_fol12(fol)], bop_len):
            return 12
    if len(fol) % 8 == 0 and bop_len is not None:
        if contiguous_raw([(r[1], r[2], r[3]) for r in read_fol8(fol)], bop_len):
            return 8
    return None


# ---------------------------------------------------------------- color maps

def colormaps(pal):
    """Variant B .PAL -> list of 512-byte maps (empty if not a multiple of 512)."""
    return [pal[i:i + 512] for i in range(0, len(pal), 512)] if pal and len(pal) % 512 == 0 else []


def map16(cm):
    """The 16-color map m[0..15] behind a 512-byte expanded map (entry[n*16].left = m[n])."""
    return [cm[n * 16 * 2] for n in range(16)]


def extended_map_indices(recs):
    """Map index per record: kind>>4 plus 16 for every earlier drop of that nibble.

    Frames with color maps (types 2 and 4) are stored grouped by map in file order,
    so the 4-bit field is the map number modulo 16. None for type-1 frames.
    """
    out, wraps, prev = [], 0, None
    for r in recs:
        if (r[5] & 15) not in (2, 4):
            out.append(None)
            continue
        n = r[5] >> 4
        if prev is not None and n < prev:
            wraps += 1
        out.append(n + 16 * wraps)
        prev = n
    return out


def segment_ends(recs, bop_len):
    offs = sorted(set(r[4] for r in recs)) + [bop_len]
    nxt = {o: offs[i + 1] for i, o in enumerate(offs[:-1])}
    return [nxt[r[4]] for r in recs]


def decode_with_map(bop, rec, end, cmap):
    """decode_frame with an explicit 512-byte map (ignores the nibble in kind)."""
    r = rec[:5] + (rec[5] & 15,)
    return decode_frame(bop, r, end, [cmap] if cmap is not None else [])


def nibble_plane(bop, rec, end):
    """Types 2/4: the raw 4-bit values (0..15) of every pixel, before the color map."""
    w, h, off, kind = rec[2], rec[3], rec[4], rec[5] & 15
    bw = (w + 1) // 2
    seg = bop[off:end]
    packed = unzero(seg)[0] if kind == 4 else seg[:bw * h]
    return bytes((packed[y * bw + x // 2] >> 4) if x % 2 == 0 else (packed[y * bw + x // 2] & 15)
                 for y in range(h) for x in range(w))


# ---------------------------------------------------------------- images

def gray_palette(levels=16):
    """Index v -> gray; with levels=16 the values 0..15 span the whole ramp."""
    step = 255 // (levels - 1)
    return [(min(255, v * step),) * 3 for v in range(256)]


def save_sheet(path, frames, pal, cols=8, scale=2, cell=None, bg=BG, show_zero=False):
    """frames = [(w, h, pixels)] with palette indices; index 0 is transparent unless show_zero."""
    if not frames:
        return
    cw = cell[0] if cell else max(f[0] for f in frames) + 2
    ch = cell[1] if cell else max(f[1] for f in frames) + 2
    rows = (len(frames) + cols - 1) // cols
    W, H = cw * cols, ch * rows
    img = [bg] * (W * H)
    for k, (w, h, px) in enumerate(frames):
        ox, oy = (k % cols) * cw + 1, (k // cols) * ch + 1
        for y in range(min(h, ch - 1)):
            for x in range(min(w, cw - 1)):
                v = px[y * w + x]
                if v or show_zero:
                    img[(oy + y) * W + ox + x] = pal[v]
    rgb = bytearray()
    for y in range(H * scale):
        row = img[(y // scale) * W:(y // scale + 1) * W]
        rgb += b''.join(bytes(c) * scale for c in row)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write_png(path, W * scale, H * scale, rgb)
