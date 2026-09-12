"""Shared helpers for sprite animation analysis: loading .FOL/.BOP/.PAL, an RGB canvas,
a 3x5 pixel font, PNG output (render_sprites.write_png) and animated GIF output
(own LZW encoder, stdlib only).

Usage as a module:
    from anim_lib import find_bindirs, Sprite, Canvas, write_gif
    s = Sprite(find_bindirs(".../WARFB"), "ESHIN")
    idx = s.frame(0)        # list of w*h STANDARD.PAL indices (0 = transparent)

File lookup: UPDATE/BINARY first, then FILE/BINARY (UPDATE takes precedence),
case-insensitive.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_sprites import decode_frame, load_rgb_palette, write_png    # noqa: E402

DIGITS = {
    '0': ('111', '101', '101', '101', '111'), '1': ('010', '110', '010', '010', '111'),
    '2': ('111', '001', '111', '100', '111'), '3': ('111', '001', '111', '001', '111'),
    '4': ('101', '101', '111', '001', '001'), '5': ('111', '100', '111', '001', '111'),
    '6': ('111', '100', '111', '101', '111'), '7': ('111', '001', '001', '001', '001'),
    '8': ('111', '101', '111', '101', '111'), '9': ('111', '101', '111', '001', '111'),
    'A': ('010', '101', '111', '101', '101'), 'B': ('110', '101', '110', '101', '110'),
    'C': ('011', '100', '100', '100', '011'), 'D': ('110', '101', '101', '101', '110'),
    'E': ('111', '100', '110', '100', '111'), 'F': ('111', '100', '110', '100', '100'),
    'G': ('011', '100', '101', '101', '011'), 'H': ('101', '101', '111', '101', '101'),
    'I': ('111', '010', '010', '010', '111'), 'K': ('101', '101', '110', '101', '101'),
    'L': ('100', '100', '100', '100', '111'), 'M': ('101', '111', '111', '101', '101'),
    'N': ('110', '101', '101', '101', '101'), 'O': ('010', '101', '101', '101', '010'),
    'P': ('110', '101', '110', '100', '100'), 'R': ('110', '101', '110', '101', '101'),
    'S': ('011', '100', '010', '001', '110'), 'T': ('111', '010', '010', '010', '010'),
    'U': ('101', '101', '101', '101', '111'), 'W': ('101', '101', '111', '111', '101'),
    'X': ('101', '101', '010', '101', '101'), 'Y': ('101', '101', '010', '010', '010'),
    '-': ('000', '000', '111', '000', '000'), '.': ('000', '000', '000', '000', '010'),
    '/': ('001', '001', '010', '100', '100'), ':': ('000', '010', '000', '010', '000'),
    '=': ('000', '111', '000', '111', '000'), ' ': ('000',) * 5,
}


def find_bindirs(root):
    """BINARY directories in precedence order. root = WARFB or a BINARY directory itself."""
    cands = [os.path.join(root, 'UPDATE', 'BINARY'), os.path.join(root, 'FILE', 'BINARY'), root]
    return [d for d in cands if os.path.isdir(d) and any(f.upper().endswith('.FOL') for f in os.listdir(d))]


def find_file(bindirs, name):
    for d in bindirs:
        for f in os.listdir(d):
            if f.upper() == name.upper():
                return os.path.join(d, f)
    return None


def list_sprites(bindirs):
    """Names (without extension) of all .FOL/.BOP pairs, union over directories."""
    names = set()
    for d in bindirs:
        up = {f.upper() for f in os.listdir(d)}
        names |= {f[:-4] for f in up if f.endswith('.FOL') and f[:-4] + '.BOP' in up}
    return sorted(names)


class Sprite:
    """One sprite set: .FOL/.BOP pair (+ optional .PAL with colour maps)."""

    def __init__(self, bindirs, name):
        self.name = name.upper()
        self.fol = open(find_file(bindirs, self.name + '.FOL'), 'rb').read()
        self.bop = open(find_file(bindirs, self.name + '.BOP'), 'rb').read()
        pal = find_file(bindirs, self.name + '.PAL')
        pd = open(pal, 'rb').read() if pal else b''
        self.cmaps = [pd[i:i + 512] for i in range(0, len(pd), 512)] if pd and len(pd) % 512 == 0 else []
        self.rgb = load_rgb_palette(find_file(bindirs, 'STANDARD.PAL'))
        # record: hx, hy (int16), w, h, bop_offset, bytes 12..15
        self.recs = [struct.unpack_from('<hhhhIBBBB', self.fol, i * 16) for i in range(len(self.fol) // 16)]
        self.raw = [self.fol[i * 16:i * 16 + 16] for i in range(len(self.recs))]
        self.offsets = sorted(set(r[4] for r in self.recs)) + [len(self.bop)]
        self._cache = {}

    def __len__(self):
        return len(self.recs)

    def anchor(self, i):
        """Record bytes 2 and 3 as separate u8 (in unit files bytes 0-1 are 0).
        Hypothesis (see notes/animations.md): b3 = anchor x, b2 = anchor distance from the bottom."""
        b = self.raw[i]
        return b[2], b[3]

    def frame(self, i):
        if i not in self._cache:
            r = self.recs[i]
            end = self.offsets[self.offsets.index(r[4]) + 1]
            self._cache[i] = decode_frame(self.bop, r[:6], end, self.cmaps)
        return self._cache[i]

    def bbox(self, i):
        """Bounding box of opaque pixels (x0, y0, x1, y1), inclusive, or None."""
        w, h = self.recs[i][2], self.recs[i][3]
        px = self.frame(i)
        xs = [x for y in range(h) for x in range(w) if px[y * w + x]]
        ys = [y for y in range(h) for x in range(w) if px[y * w + x]]
        return (min(xs), min(ys), max(xs), max(ys)) if xs else None


class Canvas:
    """RGB canvas with simple drawing operations; saves to PNG."""

    def __init__(self, w, h, bg=(40, 40, 48)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def dot(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def fill(self, x, y, w, h, c):
        for yy in range(max(y, 0), min(y + h, self.h)):
            i = (yy * self.w + max(x, 0)) * 3
            n = min(x + w, self.w) - max(x, 0)
            if n > 0:
                self.px[i:i + 3 * n] = bytes(c) * n

    def text(self, x, y, s, c=(255, 255, 255), k=1, bg=None):
        """Text in the 3x5 font (k = magnification); returns the width in pixels."""
        s = s.upper()
        w = len(s) * 4 * k - k
        if bg:
            self.fill(x - 1, y - 1, w + 2, 5 * k + 2, bg)
        for i, ch in enumerate(s):
            for row, bits in enumerate(DIGITS.get(ch, ('111',) * 5)):
                for col, bit in enumerate(bits):
                    if bit == '1':
                        self.fill(x + i * 4 * k + col * k, y + row * k, k, k, c)
        return w

    def blit(self, sprite, i, x, y, flip=False):
        """Draws frame i of the sprite with its top-left corner at (x, y)."""
        w, h = sprite.recs[i][2], sprite.recs[i][3]
        px = sprite.frame(i)
        for yy in range(h):
            for xx in range(w):
                v = px[yy * w + (w - 1 - xx if flip else xx)]
                if v:
                    self.dot(x + xx, y + yy, sprite.rgb[v])

    def scaled(self, k):
        if k == 1:
            return self
        out = Canvas(self.w * k, self.h * k)
        rows = []
        for y in range(self.h):
            row = bytearray()
            for x in range(self.w):
                row += self.px[(y * self.w + x) * 3:(y * self.w + x) * 3 + 3] * k
            rows.append(bytes(row) * k)
        out.px = bytearray(b''.join(rows))
        return out

    def png(self, path, k=1):
        c = self.scaled(k)
        write_png(path, c.w, c.h, c.px)


# ---------------------------------------------------------------- GIF (LZW, stdlib)

def _lzw(indices, min_code=8):
    """GIF LZW compression (variable-length codes, dictionary reset at 4096)."""
    clear, eoi = 1 << min_code, (1 << min_code) + 1
    out, acc, nbits = bytearray(), 0, 0
    size = min_code + 1

    def emit(code):
        nonlocal acc, nbits
        acc |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(acc & 255)
            acc >>= 8
            nbits -= 8

    table = {bytes([i]): i for i in range(clear)}
    nxt = eoi + 1
    emit(clear)
    cur = b''
    for v in indices:
        cand = cur + bytes([v])
        if cand in table:
            cur = cand
            continue
        emit(table[cur])
        if nxt < 4096:
            table[cand] = nxt
            nxt += 1
            if nxt > (1 << size) and size < 12:
                size += 1
        else:
            emit(clear)
            table = {bytes([i]): i for i in range(clear)}
            nxt, size = eoi + 1, min_code + 1
        cur = bytes([v])
    if cur:
        emit(table[cur])
    emit(eoi)
    if nbits:
        out.append(acc & 255)
    return bytes(out)


def write_gif(path, w, h, frames, palette, delay_cs=12, transparent=None, loop=True):
    """frames = list of lists of w*h indices 0..255, palette = 256 RGB tuples."""
    pal = b''.join(bytes(palette[i]) if i < len(palette) else b'\0\0\0' for i in range(256))
    data = bytearray(b'GIF89a' + struct.pack('<HHBBB', w, h, 0xF7, 0, 0) + pal)
    if loop:
        data += b'\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00'
    for fr in frames:
        flags = 0x09 if transparent is not None else 0x08    # dispose=2 (background), transparency
        data += b'\x21\xF9\x04' + bytes([flags]) + struct.pack('<H', delay_cs) + bytes([transparent or 0, 0])
        data += b'\x2C' + struct.pack('<HHHHB', 0, 0, w, h, 0) + b'\x08'
        comp = _lzw(fr)
        for i in range(0, len(comp), 255):
            data += bytes([len(comp[i:i + 255])]) + comp[i:i + 255]
        data += b'\x00'
    data += b'\x3B'
    open(path, 'wb').write(data)
