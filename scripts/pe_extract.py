"""Extracts PE resources from the game files into open formats (PNG/JSON/TXT). See notes/pe_resources.md.

Usage:
  pe_extract.py <file.DLL|.EXE> <output_dir>
  pe_extract.py --all <WARFB dir> <output_dir>     every DLL in FILE/DLL + WHSHR.EXE
e.g.:
  pe_extract.py ".../WARFB/FILE/DLL/GMTXT.DLL" extracted/pe_resources/GMTXT
  pe_extract.py --all ".../WARFB" extracted/pe_resources

Output per resource type:
  RT_BITMAP       -> bitmap/<NAME>.png (indexed PNG, palette embedded in the BMP header) + bitmaps.json
  RT_STRING       -> strings.json {id: text} + strings.txt (id<TAB>repr(text))
  RT_RCDATA       -> rcdata/<NAME>.txt (latin-1 text, trailing ESC/EOF bytes stripped)
  RT_DIALOG       -> dialogs.json (classic DIALOG template: style, size, controls with text and ID)
  RT_MENU         -> menus.json
  RT_CURSOR/ICON  -> cursor/<id>.png, icon/<id>.png (RGBA, AND mask -> alpha), icons.json (size, hotspot)
  RT_GROUP_*      -> groups.json (group name -> member IDs)
  RT_ACCELERATOR  -> accelerators.json; anything else -> raw/<type>_<name>.bin
"""
import hashlib, json, os, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe_resources import PE, type_name  # noqa: E402


# ---------------------------------------------------------------- PNG

def _chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))


def write_png_rgba(path, w, h, rows):
    """rows: h rows of bytes, 4*w long each (RGBA), top to bottom."""
    raw = b''.join(b'\0' + r for r in rows)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                           + _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


def write_png_indexed(path, w, h, rows, palette):
    """rows: h rows of 8-bit indices, palette: 256 RGB tuples."""
    raw = b''.join(b'\0' + r for r in rows)
    plte = b''.join(bytes(c) for c in palette)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 3, 0, 0, 0))
                           + _chunk(b'PLTE', plte) + _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


# ---------------------------------------------------------------- BMP (DIB)

def parse_dib(d):
    """DIB without BITMAPFILEHEADER (as stored in RT_BITMAP/RT_ICON/RT_CURSOR).

    Returns (w, h, bpp, RGB palette of 256, pixel offset, row stride, top_down).
    Handles uncompressed 1/4/8 bpp, which covers every resource in the game files.
    """
    hs, w, h, planes, bpp, comp, isz, _, _, clr, _ = struct.unpack_from('<IiiHHIIiiII', d)
    if hs != 40 or comp != 0 or bpp not in (1, 4, 8):
        raise ValueError(f"unsupported DIB: hs={hs} bpp={bpp} comp={comp}")
    ncol = clr or (1 << bpp)
    pal = [(d[hs + 4 * i + 2], d[hs + 4 * i + 1], d[hs + 4 * i]) for i in range(ncol)]
    pal += [(0, 0, 0)] * (256 - len(pal))
    top_down = h < 0
    stride = (w * bpp + 31) // 32 * 4
    return w, abs(h), bpp, pal, hs + 4 * ncol, stride, top_down


def dib_rows(d, w, h, bpp, off, stride, top_down=False):
    """Rows of indices (one byte per pixel), top row first."""
    rows = []
    for r in range(h):
        line = d[off + r * stride: off + (r + 1) * stride]
        if bpp == 8:
            px = line[:w]
        elif bpp == 4:
            px = bytes((line[x // 2] >> (4 - 4 * (x & 1))) & 15 for x in range(w))
        else:
            px = bytes((line[x // 8] >> (7 - x % 8)) & 1 for x in range(w))
        rows.append(bytes(px))
    return rows if top_down else rows[::-1]   # DIBs are stored bottom-up


def bitmap_to_png(d, path):
    w, h, bpp, pal, off, stride, td = parse_dib(d)
    write_png_indexed(path, w, h, dib_rows(d, w, h, bpp, off, stride, td), pal)
    return {'w': w, 'h': h, 'bpp': bpp, 'palette_md5': hashlib.md5(d[40:40 + 1024]).hexdigest()[:8]}


def icon_to_png(d, path, cursor=False):
    """RT_ICON/RT_CURSOR: DIB with doubled height (XOR image + AND mask). Cursors start with a u16 hotspot pair."""
    hot = None
    if cursor:
        hot = list(struct.unpack_from('<HH', d))
        d = d[4:]
    w, h2, bpp, pal, off, stride, _ = parse_dib(d)
    h = h2 // 2
    xor = dib_rows(d, w, h, bpp, off, stride)
    and_ = dib_rows(d, w, h, 1, off + stride * h, (w + 31) // 32 * 4)
    rows = []
    for xr, ar in zip(xor, and_):
        row = bytearray()
        for x in range(w):
            if ar[x] and xr[x] == 0:
                row += b'\0\0\0\0'                        # transparent
            elif ar[x]:
                row += bytes((255, 0, 255, 255))          # "invert screen" pixel: shown as magenta
            else:
                row += bytes(pal[xr[x]]) + b'\xff'
        rows.append(bytes(row))
    write_png_rgba(path, w, h, rows)
    return {'w': w, 'h': h, 'bpp': bpp, 'hotspot': hot}


# ---------------------------------------------------------------- STRING / DIALOG / MENU

def string_block(d, block_id):
    """RT_STRING: block N holds 16 strings with IDs (N-1)*16 .. (N-1)*16+15 (u16 length + UTF-16LE)."""
    out, p = {}, 0
    for i in range(16):
        n = struct.unpack_from('<H', d, p)[0]
        p += 2
        if n:
            out[(block_id - 1) * 16 + i] = d[p:p + 2 * n].decode('utf-16-le')
        p += 2 * n
    return out


def _sz_or_ord(d, p):
    """Template field: 0x0000 = empty, 0xFFFF + u16 = ordinal, otherwise zero-terminated UTF-16."""
    v = struct.unpack_from('<H', d, p)[0]
    if v == 0:
        return '', p + 2
    if v == 0xFFFF:
        return struct.unpack_from('<H', d, p + 2)[0], p + 4
    e = p
    while struct.unpack_from('<H', d, e)[0]:
        e += 2
    return d[p:e].decode('utf-16-le'), e + 2


CTRL_CLASS = {0x80: 'BUTTON', 0x81: 'EDIT', 0x82: 'STATIC', 0x83: 'LISTBOX', 0x84: 'SCROLLBAR', 0x85: 'COMBOBOX'}


def parse_dialog(d):
    """Classic DIALOG template (not DIALOGEX)."""
    style, exstyle, n, x, y, cx, cy = struct.unpack_from('<IIHhhhh', d)
    p = 18
    menu, p = _sz_or_ord(d, p)
    cls, p = _sz_or_ord(d, p)
    title, p = _sz_or_ord(d, p)
    font = None
    if style & 0x40:                                  # DS_SETFONT
        size = struct.unpack_from('<H', d, p)[0]
        name, p = _sz_or_ord(d, p + 2)
        font = [size, name]
    dlg = {'style': f'{style:#010x}', 'x': x, 'y': y, 'cx': cx, 'cy': cy, 'title': title,
           'menu': menu, 'class': cls, 'font': font, 'controls': []}
    for _ in range(n):
        p = (p + 3) & ~3                              # DWORD alignment
        cstyle, cex, x, y, cx, cy, cid = struct.unpack_from('<IIhhhhH', d, p)
        p += 18
        cc, p = _sz_or_ord(d, p)
        text, p = _sz_or_ord(d, p)
        extra = struct.unpack_from('<H', d, p)[0]
        p += 2 + extra
        kind = CTRL_CLASS.get(cc, cc)
        if kind == 'BUTTON':                          # button kind from the low style bits
            kind = {0: 'PUSHBUTTON', 1: 'DEFPUSHBUTTON', 3: 'AUTOCHECKBOX', 7: 'GROUPBOX',
                    9: 'AUTORADIOBUTTON'}.get(cstyle & 0xF, 'BUTTON')
        dlg['controls'].append({'type': kind, 'id': cid, 'text': text, 'x': x, 'y': y, 'cx': cx, 'cy': cy,
                                'style': f'{cstyle:#010x}'})
    return dlg


def parse_menu(d):
    """Classic MENU template (version 0): tree of items {text, id | items, flags}."""
    p = 4

    def items():
        nonlocal p
        out = []
        while True:
            flags = struct.unpack_from('<H', d, p)[0]
            p += 2
            it = {'flags': f'{flags:#06x}'}
            if not flags & 0x10:                      # not MF_POPUP -> has a command ID
                it['id'] = struct.unpack_from('<H', d, p)[0]
                p += 2
            e = p
            while struct.unpack_from('<H', d, e)[0]:
                e += 2
            it['text'] = d[p:e].decode('utf-16-le')
            p = e + 2
            if flags & 0x10:
                it['items'] = items()
            out.append(it)
            if flags & 0x80:                          # MF_END
                return out
    return items()


# ---------------------------------------------------------------- main

def extract(path, out):
    pe = PE(path)
    os.makedirs(out, exist_ok=True)
    strings, dialogs, menus, accels, bitmaps, icons, groups, counts = {}, {}, {}, {}, {}, {}, {}, {}
    for r in pe.resources():
        d, name = pe.data(r), str(r.name)
        counts[type_name(r.type)] = counts.get(type_name(r.type), 0) + 1
        if r.type == 2:
            os.makedirs(f'{out}/bitmap', exist_ok=True)
            bitmaps[name] = bitmap_to_png(d, f'{out}/bitmap/{name}.png')
        elif r.type == 6:
            strings.update(string_block(d, r.name))
        elif r.type == 10:
            os.makedirs(f'{out}/rcdata', exist_ok=True)
            open(f'{out}/rcdata/{name}.txt', 'wb').write(d.rstrip(b'\x1a\x1b\r\n'))
        elif r.type == 5:
            dialogs[name] = parse_dialog(d)
        elif r.type == 4:
            menus[name] = parse_menu(d)
        elif r.type == 9:
            accels[name] = [dict(zip(('flags', 'key', 'cmd'), struct.unpack_from('<HHH', d, i)))
                            for i in range(0, len(d), 8)]
        elif r.type in (1, 3):
            sub = 'cursor' if r.type == 1 else 'icon'
            os.makedirs(f'{out}/{sub}', exist_ok=True)
            icons[f'{sub}/{name}'] = icon_to_png(d, f'{out}/{sub}/{name}.png', r.type == 1)
        elif r.type in (12, 14):
            n = struct.unpack_from('<H', d, 4)[0]      # GRPICONDIR: 6 B header + 14 B entries, ID at +12
            groups[f"{type_name(r.type)}/{name}"] = [struct.unpack_from('<H', d, 6 + i * 14 + 12)[0]
                                                     for i in range(n)]
        else:
            os.makedirs(f'{out}/raw', exist_ok=True)
            open(f'{out}/raw/{type_name(r.type)}_{name}.bin', 'wb').write(d)

    def dump(fname, obj):
        with open(f'{out}/{fname}', 'w') as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
    if strings:
        dump('strings.json', {str(k): strings[k] for k in sorted(strings)})
        with open(f'{out}/strings.txt', 'w') as f:
            for k in sorted(strings):
                f.write(f"{k}\t{strings[k]!r}\n")
    for fname, obj in (('dialogs.json', dialogs), ('menus.json', menus), ('accelerators.json', accels),
                       ('bitmaps.json', bitmaps), ('icons.json', icons), ('groups.json', groups)):
        if obj:
            dump(fname, obj)
    print(f"{os.path.basename(path)} -> {out}: {counts}")


def extract_all(game, out):
    dll = os.path.join(game, 'FILE', 'DLL')
    for f in sorted(os.listdir(dll)):
        if f.upper().endswith('.DLL'):
            extract(os.path.join(dll, f), os.path.join(out, os.path.splitext(f)[0].upper()))
    extract(os.path.join(game, 'WHSHR.EXE'), os.path.join(out, 'WHSHR'))


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
    elif a[0] == '--all':
        extract_all(a[1], a[2])
    else:
        extract(a[0], a[1])
