"""Parser for Windows .FON fonts (NE file with RT_FONTDIR/RT_FONT resources, glyphs in FNT 2.0/3.0 format).

Usage:
  fon_parse.py <file.FON>                              NE header, resources, FNT fields
  fon_parse.py <file.FON> --chart out.png [scale]      character table with hex codes + sample text
  fon_parse.py <file.FON> --text "text" out.png [scale]
  fon_parse.py --check <dir> [<dir> ...]               all *.FON in the directories: consistency + table

e.g.: fon_parse.py ".../WARFB/FILE/BINARY/GLUE/GOTHTEXT.FON" --chart gothtext.png 3
      fon_parse.py --check ".../WARFB/FILE/BINARY" ".../WARFB/UPDATE/BINARY"

API:
  load_fon(path) -> FonFile(path, module, description, resources, fontdir, fonts)
  Font.hdr (dict of FNT fields), Font.face, Font.glyphs {code: Glyph(width, offset, bits)}, Font.pixel(code, x, y)
  Font.render(text) -> (w, h, 0/1 pixels), tiny_text(...) - 3x5 mini font for labels

Supported: FNT 2.0 and 3.0, 1-bit raster fonts (fixed and proportional). Vector fonts
(dfType & 1) and color fonts (dfFlags DFF_16COLOR/256COLOR/RGBCOLOR) are detected and reported
as errors - the game has none, so there is nothing to test such code against.
"""
import glob, hashlib, os, struct, sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_sprites import write_png

NeResource = namedtuple('NeResource', 'type name offset length flags')
Glyph = namedtuple('Glyph', 'width offset bits')   # bits: height * ceil(w/8) raw bitmap bytes
FonFile = namedtuple('FonFile', 'path module description resources fontdir fonts')

RT = {0x8007: 'RT_FONTDIR', 0x8008: 'RT_FONT'}

# FNT 2.0 header (118 bytes), field names as in the Windows SDK documentation
FNT2 = [('dfVersion', 'H'), ('dfSize', 'I'), ('dfCopyright', '60s'), ('dfType', 'H'),
        ('dfPoints', 'H'), ('dfVertRes', 'H'), ('dfHorizRes', 'H'), ('dfAscent', 'H'),
        ('dfInternalLeading', 'H'), ('dfExternalLeading', 'H'), ('dfItalic', 'B'),
        ('dfUnderline', 'B'), ('dfStrikeOut', 'B'), ('dfWeight', 'H'), ('dfCharSet', 'B'),
        ('dfPixWidth', 'H'), ('dfPixHeight', 'H'), ('dfPitchAndFamily', 'B'), ('dfAvgWidth', 'H'),
        ('dfMaxWidth', 'H'), ('dfFirstChar', 'B'), ('dfLastChar', 'B'), ('dfDefaultChar', 'B'),
        ('dfBreakChar', 'B'), ('dfWidthBytes', 'H'), ('dfDevice', 'I'), ('dfFace', 'I'),
        ('dfBitsPointer', 'I'), ('dfBitsOffset', 'I'), ('dfReserved', 'B')]
# extra FNT 3.0 fields (148 bytes in total)
FNT3 = [('dfFlags', 'I'), ('dfAspace', 'H'), ('dfBspace', 'H'), ('dfCspace', 'H'),
        ('dfColorPointer', 'I'), ('dfReserved1', '16s')]
FMT2 = '<' + ''.join(t for _, t in FNT2)
FMT3 = '<' + ''.join(t for _, t in FNT3)
CHARSETS = {0: 'ANSI (cp1252)', 1: 'DEFAULT', 2: 'SYMBOL', 128: 'SHIFTJIS', 161: 'GREEK',
            162: 'TURKISH', 186: 'BALTIC', 204: 'RUSSIAN', 238: 'EASTEUROPE', 255: 'OEM (cp437)'}
FAMILY = {0: 'DONTCARE', 1: 'ROMAN', 2: 'SWISS', 3: 'MODERN', 4: 'SCRIPT', 5: 'DECORATIVE'}


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def pascal(b, o):
    return b[o + 1:o + 1 + b[o]].decode('latin-1')


def cstr(b, o):
    e = b.index(b'\0', o)
    return b[o:e].decode('latin-1')


def parse_ne(b):
    """Returns (module, description, [NeResource]). Resource offsets already shifted by rscAlignShift."""
    if b[:2] != b'MZ':
        raise ValueError('missing MZ signature')
    ne = struct.unpack_from('<I', b, 0x3C)[0]
    if b[ne:ne + 2] != b'NE':
        raise ValueError(f'missing NE header (found {b[ne:ne + 2]!r})')
    restab = ne + u16(b, ne + 0x24)
    resnames = ne + u16(b, ne + 0x26)
    nonres = struct.unpack_from('<I', b, ne + 0x2C)[0]
    module = pascal(b, resnames)                     # first entry of the resident name table
    description = pascal(b, nonres) if nonres else ''  # first entry of the non-resident name table
    shift = u16(b, restab)
    p, out = restab + 2, []
    while u16(b, p):
        t, cnt = struct.unpack_from('<HH', b, p)
        p += 8                                       # type, count, 4 reserved bytes
        tname = RT.get(t, t & 0x7FFF) if t & 0x8000 else pascal(b, restab + t)
        for _ in range(cnt):
            off, ln, fl, rid = struct.unpack_from('<HHHH', b, p)
            p += 12
            name = rid & 0x7FFF if rid & 0x8000 else pascal(b, restab + rid)
            out.append(NeResource(tname, name, off << shift, ln << shift, fl))
    return module, description, out


class Font:
    def __init__(self, data, res_name=None, layout='column'):
        # layout: order of the bitmap bytes, see pixel(); 'column' is what the game fonts use
        self.res_name = res_name
        self.layout = layout
        self.data = data
        self.hdr = dict(zip([n for n, _ in FNT2], struct.unpack_from(FMT2, data, 0)))
        h = self.hdr
        if h['dfVersion'] not in (0x200, 0x300):
            raise ValueError(f"unsupported FNT version {h['dfVersion']:#x}")
        if h['dfVersion'] == 0x300:
            h.update(zip([n for n, _ in FNT3], struct.unpack_from(FMT3, data, 118)))
            table, ent = 148, '<HI'
            if h['dfFlags'] & 0xE0:
                raise NotImplementedError(f"color font (dfFlags={h['dfFlags']:#x})")
        else:
            table, ent = 118, '<HH'
        if h['dfType'] & 1:
            raise NotImplementedError('vector font (dfType & 1)')
        h['dfCopyright'] = h['dfCopyright'].split(b'\0')[0].decode('latin-1')
        self.face = cstr(data, h['dfFace']) if h['dfFace'] else ''
        self.height = h['dfPixHeight']
        es = struct.calcsize(ent)
        self.glyphs = {}
        self.sentinel = None
        n = h['dfLastChar'] - h['dfFirstChar'] + 1
        for i in range(n + 1):                      # +1: "absolute space" entry after the last character
            w, off = struct.unpack_from(ent, data, table + i * es)
            if i == n:
                self.sentinel = (w, off)
                break
            n_bytes = self.height * ((w + 7) // 8)
            self.glyphs[h['dfFirstChar'] + i] = Glyph(w, off, data[off:off + n_bytes])
        self.table_end = table + (n + 1) * es

    def pixel(self, code, x, y):
        """'column': byte-column k (glyph bits 8k..8k+7) stores all rows, then column k+1.
        'row': row y stores its ceil(w/8) bytes, then row y+1. Bits MSB first in both."""
        g = self.glyphs[code]
        if self.layout == 'column':
            b = g.bits[(x >> 3) * self.height + y]
        else:
            b = g.bits[y * ((g.width + 7) // 8) + (x >> 3)]
        return (b >> (7 - (x & 7))) & 1

    def code_for(self, ch):
        c = ch if isinstance(ch, int) else ch.encode('cp1252', 'replace')[0]
        if c not in self.glyphs:
            c = self.hdr['dfFirstChar'] + self.hdr['dfDefaultChar']
        return c

    def render(self, text):
        """Single-line text -> (width, height, list of 0/1). Advance = glyph width."""
        codes = [self.code_for(ch) for ch in text]
        W = sum(self.glyphs[c].width for c in codes)
        px = [0] * (W * self.height)
        x0 = 0
        for c in codes:
            g = self.glyphs[c]
            for y in range(self.height):
                for x in range(g.width):
                    if self.pixel(c, x, y):
                        px[y * W + x0 + x] = 1
            x0 += g.width
        return W, self.height, px


def load_fon(path, layout='column'):
    b = open(path, 'rb').read()
    module, desc, res = parse_ne(b)
    fonts, fontdir = [], None
    for r in res:
        if r.type == 'RT_FONT':
            size = struct.unpack_from('<I', b, r.offset + 2)[0]   # dfSize - exact resource size
            fonts.append(Font(b[r.offset:r.offset + size], r.name, layout))
        elif r.type == 'RT_FONTDIR':
            fontdir = parse_fontdir(b[r.offset:r.offset + r.length])
    return FonFile(path, module, desc, res, fontdir, fonts)


def parse_fontdir(d):
    """RT_FONTDIR: u16 count, then per font u16 ordinal + FONTDIRENTRY (105 B of FNT fields + u32
    + device name + face name, ASCIIZ)."""
    out, p = [], 2
    for _ in range(u16(d, 0)):
        ordinal = u16(d, p)
        head = d[p + 2:p + 2 + 105]
        q = p + 2 + 113
        dev = cstr(d, q)
        q += len(dev) + 1
        face = cstr(d, q)
        q += len(face) + 1
        out.append((ordinal, head, dev, face))
        p = q
    return out


# --- validation  ------------------------------------------------------------------------------

def check_font(fon, f):
    """List of problems (empty = OK)."""
    h, bad = f.hdr, []
    res = [r for r in fon.resources if r.type == 'RT_FONT' and r.name == f.res_name][0]
    if h['dfSize'] > res.length:
        bad.append(f"dfSize {h['dfSize']} > resource length {res.length}")
    expect = f.table_end
    for c, g in sorted(f.glyphs.items()):
        n = f.height * ((g.width + 7) // 8)
        if g.offset != expect:
            bad.append(f"char {c:#x}: offset {g.offset} != {expect} (bitmaps not contiguous)")
        if g.offset + n > h['dfSize']:
            bad.append(f"char {c:#x}: bitmap outside the resource")
        if h['dfPixWidth'] and g.width != h['dfPixWidth']:
            bad.append(f"char {c:#x}: width {g.width} != dfPixWidth")
        expect = g.offset + n
    mw = max(g.width for g in f.glyphs.values())
    if mw > h['dfMaxWidth']:
        bad.append(f"widest glyph {mw} > dfMaxWidth {h['dfMaxWidth']}")
    # note: dfMaxWidth > widest glyph happens in 5 of 6 game fonts (stale header), not an error
    if f.sentinel[1] != expect:
        bad.append(f'sentinel entry offset {f.sentinel[1]} != end of bitmaps {expect}')
    face_end = h['dfFace'] + len(f.face) + 1
    if face_end != h['dfSize']:
        bad.append(f'face name ends at {face_end}, dfSize={h["dfSize"]}')
    if fon.fontdir is not None:
        ents = [e for e in fon.fontdir if e[0] == f.res_name]
        if not ents:
            bad.append('no RT_FONTDIR entry')
        elif ents[0][1] != f.data[:105] or ents[0][3] != f.face:
            bad.append('RT_FONTDIR entry does not match the FNT header')
    return bad


def glyph_hash(f):
    m = hashlib.md5()
    for c, g in sorted(f.glyphs.items()):
        m.update(bytes([c, g.width]) + g.bits)
    return m.hexdigest()[:8]


def check(dirs):
    paths = sorted(p for d in dirs for p in glob.glob(os.path.join(d, '**', '*'), recursive=True)
                   if p.upper().endswith('.FON'))
    print(f"{'file':34s} {'description (nonres name)':32s} {'face':18s} ver pt  h asc il  wght it cs  "
          f"chars    pixW maxW avgW glyphs  hash")
    total_bad = 0
    for p in paths:
        fon = load_fon(p)
        rel = os.path.relpath(p, os.path.commonpath([os.path.abspath(d) for d in dirs]))
        for f in fon.fonts:
            h, bad = f.hdr, check_font(fon, f)
            total_bad += len(bad)
            print(f"{rel:34s} {fon.description[:32]:32s} {f.face[:18]:18s} {h['dfVersion'] >> 8}.{h['dfVersion'] & 255}"
                  f" {h['dfPoints']:2d} {h['dfPixHeight']:2d} {h['dfAscent']:3d} {h['dfInternalLeading']:2d}"
                  f" {h['dfWeight']:4d} {h['dfItalic']:2d} {h['dfCharSet']:3d}"
                  f" {h['dfFirstChar']:02x}-{h['dfLastChar']:02x} {h['dfPixWidth']:4d} {h['dfMaxWidth']:4d}"
                  f" {h['dfAvgWidth']:4d} {len(f.glyphs):5d} {glyph_hash(f)}  {'OK' if not bad else 'ERROR'}")
            for m in bad[:5]:
                print('    ', m)
    print(f"{len(paths)} files, problems: {total_bad}")


def info(path):
    fon = load_fon(path)
    print(f"{path}\n  module: {fon.module!r}  description: {fon.description!r}")
    for r in fon.resources:
        print(f"  resource {r.type!s:10s} name={r.name!s:6s} offset={r.offset:#07x} length={r.length} flags={r.flags:#06x}")
    for o, _, dev, face in fon.fontdir or []:
        print(f"  RT_FONTDIR: font #{o} device={dev!r} face={face!r}")
    for f in fon.fonts:
        print(f"  RT_FONT #{f.res_name}: face {f.face!r}")
        for k, v in f.hdr.items():
            extra = ''
            if k == 'dfCharSet':
                extra = CHARSETS.get(v, '?')
            elif k == 'dfPitchAndFamily':
                extra = f"family {FAMILY.get(v >> 4, '?')}, {'proportional' if v & 1 else 'fixed pitch'}"
            elif k in ('dfFirstChar', 'dfLastChar', 'dfDefaultChar', 'dfBreakChar'):
                extra = f'{v:#04x}'
            print(f"    {k:18s} {v!r} {extra}")
        widths = {c: g.width for c, g in f.glyphs.items()}
        print(f"    widths: {sorted(set(widths.values()))}, sentinel {f.sentinel}")


# --- rendering ------------------------------------------------------------------------------

TINY = {  # 3x5 mini font for labels (rows top to bottom)
    '0': '111101101101111', '1': '010110010010111', '2': '111001111100111', '3': '111001111001111',
    '4': '101101111001001', '5': '111100111001111', '6': '111100111101111', '7': '111001001001001',
    '8': '111101111101111', '9': '111101111001111', 'A': '010101111101101', 'B': '110101110101110',
    'C': '011100100100011', 'D': '110101101101110', 'E': '111100110100111', 'F': '111100110100100',
    'G': '011100101101011', 'H': '101101111101101', 'I': '111010010010111', 'J': '001001001101010',
    'K': '101101110101101', 'L': '100100100100111', 'M': '101111111101101', 'N': '110101101101101',
    'O': '010101101101010', 'P': '110101110100100', 'Q': '010101101110011', 'R': '110101110101101',
    'S': '011100010001110', 'T': '111010010010010', 'U': '101101101101111', 'V': '101101101101010',
    'W': '101101111111101', 'X': '101101010101101', 'Y': '101101010010010', 'Z': '111001010100111',
    '.': '000000000000010', '-': '000000111000000', '_': '000000000000111', ' ': '000000000000000',
    '(': '010100100100010', ')': '010001001001010', ':': '000010000010000', '/': '001001010100100',
    '=': '000111000111000', ',': '000000000010100', '+': '000010111010000', "'": '010010000000000',
    '#': '101111101111101', '?': '111001010000010',
}


def tiny_text(canvas, W, x, y, text, color):
    """Draws text in the 3x5 mini font (4 px per char) onto a flat color buffer."""
    for ch in text.upper():
        bits = TINY.get(ch, TINY['?'])
        for j in range(5):
            for i in range(3):
                if bits[j * 3 + i] == '1' and 0 <= x + i < W:
                    canvas[(y + j) * W + x + i] = color
        x += 4


def to_png(path, W, H, canvas, scale):
    rgb = bytearray()
    for j in range(H):
        row = b''.join(bytes(canvas[j * W + i // scale]) for i in range(W * scale))
        rgb += row * scale
    write_png(path, W * scale, H * scale, rgb)


BG, GRID, LABEL, BOX, INK, TITLE = (28, 28, 36), (70, 70, 84), (150, 150, 165), (48, 48, 62), (255, 250, 230), (230, 200, 120)
SAMPLES = ['Shadow of the Horned Rat 0123', 'AaBbCcXxYyZz 456789 !?.,:;()',
           'Grudgebringers Morgan Bernhardt',
           '\xc4\xd6\xdc\xe4\xf6\xfc\xdf \xe9\xe8\xea\xe0\xe7 \xa9\xab\xbb']


def chart(path, out, scale=3):
    fon = load_fon(path)
    f = fon.fonts[0]
    h = f.hdr
    first, last = h['dfFirstChar'], h['dfLastChar']
    cw = max(h['dfMaxWidth'] + 2, 11)
    chh = f.height + 9                                   # 7 px for the code + glyph + frame
    rows = list(range(first >> 4, (last >> 4) + 1))
    lines = [f.render(s) for s in SAMPLES]
    W = max(16 * cw + 1, max(l[0] for l in lines) + 4, 260)
    H = 18 + len(rows) * chh + 1 + 4 + len(lines) * (f.height + 3)
    cv = [BG] * (W * H)
    tiny_text(cv, W, 2, 2, f"{os.path.basename(path)}  '{fon.description}'", TITLE)
    tiny_text(cv, W, 2, 9, f"FACE '{f.face}' {h['dfPoints']}PT H={f.height} ASC={h['dfAscent']} "
                           f"CHARSET={h['dfCharSet']} {first:02X}-{last:02X} W={h['dfWeight']}"
                           f"{' PROP' if not h['dfPixWidth'] else ' FIXED'}", LABEL)
    y0 = 18
    for ri, hi in enumerate(rows):
        for lo in range(16):
            c, x, y = hi * 16 + lo, lo * cw, y0 + ri * chh
            for i in range(cw + 1):                     # grid
                cv[y * W + x + i] = GRID
            for j in range(chh + 1):
                cv[(y + j) * W + x] = GRID
                cv[(y + j) * W + x + cw] = GRID
            tiny_text(cv, W, x + 2, y + 1, f'{c:02X}', LABEL)
            if c not in f.glyphs:
                continue
            g = f.glyphs[c]
            for j in range(f.height):                   # background = advance width
                for i in range(g.width):
                    cv[(y + 8 + j) * W + x + 1 + i] = INK if f.pixel(c, i, j) else BOX
    for i in range(W):
        cv[(y0 + len(rows) * chh) * W + i] = GRID
    y = y0 + len(rows) * chh + 4
    for lw, lh, px in lines:
        for j in range(lh):
            for i in range(lw):
                if px[j * lw + i]:
                    cv[(y + j) * W + 2 + i] = INK
        y += f.height + 3
    to_png(out, W, H, cv, scale)


def text_png(path, text, out, scale=3):
    f = load_fon(path).fonts[0]
    w, h, px = f.render(text)
    cv = [INK if p else BG for p in px]
    to_png(out, w, h, cv, scale)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == '--check':
        check(a[1:])
    elif len(a) >= 3 and a[1] == '--chart':
        chart(a[0], a[2], int(a[3]) if len(a) > 3 else 3)
    elif len(a) >= 4 and a[1] == '--text':
        text_png(a[0], a[2], a[3], int(a[4]) if len(a) > 4 else 3)
    else:
        info(a[0])
