"""Leftover sprite questions: SPRITE3.BTP, legacy .FOL layouts, SPELLS maps 16-42,
orphan ICONSTMP.FOL, the odd .PAL files and FILE vs UPDATE.

Usage: btp_leftovers.py <WARFB dir> [btp|legacy|spells|orphans|pal|patch|all] [out_dir]
e.g.:  python3 scripts/btp_leftovers.py ".../GOG Games/Warhammer - Shadow of the Horned Rat/WARFB" all
       python3 scripts/btp_leftovers.py ".../WARFB" spells extracted/btp_sprite_leftovers

Prints the structural checks and writes PNG renders to out_dir
(default: extracted/btp_sprite_leftovers, game data - do not distribute).
Report: notes/btp_sprite_leftovers.md.
"""
import collections
import os
import sys

from btp_lib import (binary_dir, colormaps, decode_with_map, extended_map_indices, find, fol_layout,
                     gray_palette, listing, load_rgb_palette, map16, nibble_plane, read, read_fol8,
                     read_fol12, read_fol16, save_sheet, segment_ends)


def hexs(values):
    return ' '.join('%02x' % v for v in values)


# ---------------------------------------------------------------- 1. SPRITE3.BTP

def cmd_btp(game, out):
    fb, ub = os.path.join(game, 'FILE', 'BINARY'), binary_dir(game)
    btp = read(ub, 'SPRITE3.BTP')
    print('== SPRITE3.BTP')
    print('size', len(btp), '| FILE == UPDATE:', read(fb, 'SPRITE3.BTP') == btp)
    hist = collections.Counter(btp)
    print('distinct values', len(hist), 'range', min(hist), '..', max(hist),
          '| zero bytes %.1f%%' % (100.0 * hist[0] / len(btp)))
    lut = lambda a, b: btp[a * 256 + b]
    sym = sum(lut(a, b) == lut(b, a) for a in range(256) for b in range(256))
    sym_nz = sum(1 for a in range(256) for b in range(256) if lut(a, b) and lut(a, b) == lut(b, a))
    print('symmetry lut[a][b]==lut[b][a]: %d/65536 (only %d of them non-zero)' % (sym, sym_nz))
    diag = [lut(i, i) for i in range(256)]
    print('diagonal == index:', sum(diag[i] == i for i in range(256)), '/256; distinct diagonal values',
          len(set(diag)))
    print('row 0 non-zero', sum(1 for b in range(256) if lut(0, b)), '| column 0 non-zero',
          sum(1 for a in range(256) if lut(a, 0)))
    sysrows = [a for a in list(range(10)) + list(range(246, 256))]
    print('rows 0-9/246-255 non-zero bytes', sum(1 for a in sysrows for b in range(256) if lut(a, b)))

    # Blend-LUT test against STANDARD.PAL: any real LUT would output indices 10..245
    pal = load_rgb_palette(find(ub, 'STANDARD.PAL'))
    idx = list(range(10, 246))
    cache = {}

    def nearest(c):
        if c not in cache:
            cache[c] = min(idx, key=lambda i: (pal[i][0] - c[0]) ** 2 + (pal[i][1] - c[1]) ** 2
                           + (pal[i][2] - c[2]) ** 2)
        return cache[c]
    half = add = 0
    for a in idx:
        for b in idx:
            if b < a:
                continue
            pa, pb = pal[a], pal[b]
            half += nearest(tuple((pa[k] + pb[k]) // 2 for k in range(3))) == lut(a, b)
            add += nearest(tuple(min(255, pa[k] + pb[k]) for k in range(3))) == lut(a, b)
    print('entries a<=b in 10..245 matching nearest 50%% blend: %d, additive: %d (of %d)'
          % (half, add, 236 * 237 // 2))

    s3 = read(ub, 'SPRITE3.BOP')
    s30 = read(ub, 'SPRITE30.BOP')
    print('SPRITE3.BTP == SPRITE3.BOP[0:65536]:', btp == s3[:65536],
          '(= SPRITE3.FOL frames 0-31, 32x64 each, offsets 0..0xF800)')
    diff = [i for i in range(65536) if s30[i] != btp[i]]
    frames = sorted(set(i // 2048 for i in diff))
    print('SPRITE30.BOP (no .FOL) differs from the BTP in %d bytes, frames %s' % (len(diff), frames))
    for f in frames:
        seg = s30[f * 2048:(f + 1) * 2048]
        nz = [(i // 32, i % 32, v) for i, v in enumerate(seg) if v]
        print('  SPRITE30 frame %d: %d non-zero pixels (BTP: %d); first %s' % (
            f, len(nz), sum(1 for v in btp[f * 2048:(f + 1) * 2048] if v), nz[:3]))

    gray = gray_palette()
    save_sheet(f'{out}/btp_raw_256x256_gray.png', [(256, 256, btp)], gray, 1, 3, show_zero=True, cell=(258, 258))
    as_frames = [(32, 64, btp[k * 2048:(k + 1) * 2048]) for k in range(32)]
    save_sheet(f'{out}/btp_as_32x64_frames_gray.png', as_frames, gray, 8, 3)
    stand_in = stand_in_palette(ub, pal)
    save_sheet(f'{out}/btp_as_32x64_frames_standin_colors.png', as_frames, stand_in, 8, 3)
    cmp = []
    for f in range(2):
        cmp += [(32, 64, btp[f * 2048:(f + 1) * 2048]), (32, 64, s30[f * 2048:(f + 1) * 2048])]
    save_sheet(f'{out}/sprite30_vs_btp_frames01.png', cmp, gray, 4, 4, bg=(0, 0, 90))


def stand_in_palette(bindir, pal):
    """Values 0..15 -> colors through NLNHLB.PAL map 0 (Nuln Halberdiers). NOT verified, only for viewing."""
    m = map16(colormaps(read(bindir, 'NLNHLB.PAL'))[0])
    return [pal[m[v]] if v < 16 else (255, 0, 255) for v in range(256)]


# ---------------------------------------------------------------- 2. legacy .FOL layouts

def cmd_legacy(game, out):
    b = binary_dir(game)
    files = listing(b)
    pal = load_rgb_palette(find(b, 'STANDARD.PAL'))
    print('== .FOL layouts')
    layouts = collections.defaultdict(list)
    for name in sorted(files):
        if not name.endswith('.FOL'):
            continue
        bop = read(b, name[:-4] + '.BOP')
        layouts[fol_layout(read(b, name), len(bop) if bop else None)].append(name[:-4])
    for k, v in layouts.items():
        print('layout %s: %d files%s' % (k, len(v), '' if k == 16 else ' ' + ' '.join(v)))

    for name, reader, rec_len in (('HALBERD', read_fol12, 12), ('SPRITE3', read_fol12, 12), ('ICON2', read_fol8, 8)):
        fol, bop = read(b, name + '.FOL'), read(b, name + '.BOP')
        recs = reader(fol)
        if rec_len == 12:
            dims = [(r[2], r[3], r[4]) for r in recs]
            hot = collections.Counter((r[0], r[1]) for r in recs)
        else:
            dims = [(r[1], r[2], r[3]) for r in recs]
            hot = collections.Counter(r[0] for r in recs)
        end = dims[-1][2] + dims[-1][0] * dims[-1][1]
        print('%s.FOL: %d B / %d = %d records, sizes %s, first field(s) %s, last frame ends at %d, .BOP %d B'
              % (name, len(fol), rec_len, len(recs), dict(collections.Counter((w, h) for w, h, _ in dims)),
                 dict(hot), end, len(bop)))
        frames = [(w, h, bop[o:o + w * h]) for w, h, o in dims]
        ranges = collections.Counter('0..15' if max(p) < 16 else 'uses 16..255' for _, _, p in frames)
        print('  value range per frame:', dict(ranges))
        if name == 'SPRITE3':
            save_sheet(f'{out}/sprite3_frames32-34_8bpp.png', frames[32:], pal, 3, 2)
            save_sheet(f'{out}/sprite3_frames00-31_4bit_standin.png', frames[:32], stand_in_palette(b, pal), 8, 3)
            hb = read(b, 'HALBERD.BOP')
            print('  SPRITE3 frame 32 (16x24) == HALBERD frame 96:', frames[32][2] == hb[96 * 2048:96 * 2048 + 384])
        else:
            save_sheet(f'{out}/{name.lower()}.png', frames, pal, 16 if name == 'HALBERD' else 10, 2)

    # ICON2 vs ICONS: identical frames?
    fol, bop, cms = read(b, 'ICONS.FOL'), read(b, 'ICONS.BOP'), colormaps(read(b, 'ICONS.PAL'))
    recs = read_fol16(fol)
    ends, maps = segment_ends(recs, len(bop)), extended_map_indices(recs)
    icons = {}
    for k, r in enumerate(recs):
        px = decode_with_map(bop, r, ends[k], cms[maps[k]] if maps[k] is not None else None)
        icons.setdefault((r[2], r[3], bytes(px)), k)
    b2 = read(b, 'ICON2.BOP')
    hits = [icons.get((w, h, b2[o:o + w * h])) for _, w, h, o in read_fol8(read(b, 'ICON2.FOL'))]
    print('ICON2 frames byte-identical to a decoded ICONS frame: %d/%d -> %s'
          % (sum(x is not None for x in hits), len(hits), hits))

    # HALBERD vs NLNHLB (compressed Nuln Halberdiers)
    nfol, nbop, ncms = read_fol16(read(b, 'NLNHLB.FOL')), read(b, 'NLNHLB.BOP'), colormaps(read(b, 'NLNHLB.PAL'))
    nends, nmaps = segment_ends(nfol, len(nbop)), extended_map_indices(nfol)
    ndec = [(k, bytes(decode_with_map(nbop, r, nends[k], ncms[nmaps[k]]))) for k, r in enumerate(nfol)
            if (r[2], r[3]) == (32, 64)]
    nnib = [(k, nibble_plane(nbop, r, nends[k])) for k, r in enumerate(nfol) if (r[2], r[3]) == (32, 64)]
    hb, s3 = read(b, 'HALBERD.BOP'), read(b, 'SPRITE3.BOP')
    eq = lambda a, c: sum(x == y for x, y in zip(a, c))
    best_h = [max(eq(hb[k * 2048:(k + 1) * 2048], p) for _, p in ndec) for k in range(96)]
    best_s = [max(eq(s3[k * 2048:(k + 1) * 2048], p) for _, p in nnib) for k in range(32)]
    print('HALBERD 32x64 frames vs NLNHLB decoded: exact %d/96, best pixel agreement %d..%d of 2048'
          % (best_h.count(2048), min(best_h), max(best_h)))
    print('SPRITE3 frames 0-31 (4-bit) vs NLNHLB nibble planes: exact %d/32, best agreement %d..%d of 2048'
          % (best_s.count(2048), min(best_s), max(best_s)))


# ---------------------------------------------------------------- 3. SPELLS color maps

def cmd_spells(game, out):
    b = binary_dir(game)
    files = listing(b)
    pal = load_rgb_palette(find(b, 'STANDARD.PAL'))
    print('== color map index rule over all 16-byte .FOL with a variant B .PAL')
    stats = collections.Counter()
    for name in sorted(files):
        if not name.endswith('.FOL') or name[:-4] + '.PAL' not in files or name[:-4] == 'TESTSPR':
            continue
        cms = colormaps(read(b, name[:-4] + '.PAL'))
        bop = read(b, name[:-4] + '.BOP')
        fol = read(b, name)
        if not cms or not bop or fol_layout(fol, len(bop)) != 16:
            continue
        recs = read_fol16(fol)
        ext = [m for m in extended_map_indices(recs) if m is not None]
        nib = [r[5] >> 4 for r in recs if (r[5] & 15) in (2, 4)]
        if not ext:
            continue
        key = ('max_nibble+1 %s maps' % ('==' if max(nib) + 1 == len(cms) else '<'),
               'max_extended+1 %s maps' % ('==' if max(ext) + 1 == len(cms) else '<'))
        stats[key] += 1
        if max(nib) + 1 != len(cms) or max(ext) + 1 != len(cms):
            print('  %-8s maps=%d max_nibble+1=%d max_extended+1=%d distinct extended=%d'
                  % (name[:-4], len(cms), max(nib) + 1, max(ext) + 1, len(set(ext))))
    for k, v in sorted(stats.items()):
        print('  %3d files: %s, %s' % (v, *k))

    fol, bop, cms = read_fol16(read(b, 'SPELLS.FOL')), read(b, 'SPELLS.BOP'), colormaps(read(b, 'SPELLS.PAL'))
    ends, ext = segment_ends(fol, len(bop)), extended_map_indices(fol)
    print('== SPELLS: %d frames, %d maps' % (len(fol), len(cms)))
    groups = collections.OrderedDict()
    for k, m in enumerate(ext):
        groups.setdefault(m, []).append(k)
    for m, ks in groups.items():
        sizes = sorted(set((fol[k][2], fol[k][3]) for k in ks))
        print('  map %2d (nibble %2d): frames %3d-%3d  %-22s m16=%s'
              % (m, m % 16, ks[0], ks[-1], ','.join('%dx%d' % s for s in sizes), hexs(map16(cms[m]))))
    print('  contiguous groups:', all(ks == list(range(ks[0], ks[-1] + 1)) for ks in groups.values()))
    print('  identical maps:', [(a, c) for a in range(len(cms)) for c in range(a + 1, len(cms)) if cms[a] == cms[c]])

    def fullest(ks, cmap):
        return max(ks, key=lambda k: sum(1 for v in decode_with_map(bop, fol[k], ends[k], cmap) if v))

    def cell(k, cmap):
        r = fol[k]
        px = decode_with_map(bop, r, ends[k], cmap)
        step = 2 if r[2] > 64 or r[3] > 64 else 1           # 128x128 frames shown at half size
        w, h = r[2] // step, r[3] // step
        return (w, h, [px[(y * step) * r[2] + x * step] for y in range(h) for x in range(w)])
    pick = {m: fullest(ks, cms[m]) for m, ks in groups.items()}
    print('  sample frame per map:', pick)
    for part, ms in enumerate((range(16, 30), range(30, 43))):
        cells = [cell(pick[m], cms[m % 16]) for m in ms] + [cell(pick[m], cms[m]) for m in ms]
        save_sheet(f'{out}/spells_maps{ms[0]}-{ms[-1]}_top_nibble_bottom_extended.png', cells, pal,
                   len(ms), 3, cell=(66, 66))
    save_sheet(f'{out}/spells_all_43_maps_extended.png', [cell(pick[m], cms[m]) for m in range(len(cms))],
               pal, 11, 3, cell=(66, 66))
    # one fireball-like frame through all 43 maps: how the palettes look on the same shape
    k = pick[5]
    save_sheet(f'{out}/spells_frame{k}_through_all_43_maps.png', [cell(k, cm) for cm in cms], pal, 11, 2,
               cell=(66, 66))

    # NLNHLB: 8 maps but only 0..3 used; maps 4..7 = same with a few entries changed
    nfol, nbop, ncms = read_fol16(read(b, 'NLNHLB.FOL')), read(b, 'NLNHLB.BOP'), colormaps(read(b, 'NLNHLB.PAL'))
    nends = segment_ends(nfol, len(nbop))
    print('== NLNHLB.PAL maps (16-color form):')
    for m, cm in enumerate(ncms):
        print('  map %d: %s' % (m, hexs(map16(cm))))
    used = collections.Counter(r[5] >> 4 for r in nfol)
    print('  nibbles used:', dict(used))
    sel = [0, 4, 32, 36, 64, 68]
    cells = [(nfol[k][2], nfol[k][3], decode_with_map(nbop, nfol[k], nends[k], ncms[nfol[k][5] >> 4])) for k in sel]
    cells += [(nfol[k][2], nfol[k][3], decode_with_map(nbop, nfol[k], nends[k], ncms[(nfol[k][5] >> 4) + 4]))
              for k in sel]
    save_sheet(f'{out}/nlnhlb_top_maps0-3_bottom_maps4-7.png', cells, pal, len(sel), 3)


# ---------------------------------------------------------------- 4. orphans / type 2 without .PAL

def cmd_orphans(game, out):
    b = binary_dir(game)
    files = listing(b)
    pal = load_rgb_palette(find(b, 'STANDARD.PAL'))
    fols = {n[:-4] for n in files if n.endswith('.FOL')}
    bops = {n[:-4] for n in files if n.endswith('.BOP')}
    print('== pairs: %d .FOL, %d .BOP, pairs %d; .FOL without .BOP %s; .BOP without .FOL %s'
          % (len(fols), len(bops), len(fols & bops), sorted(fols - bops), sorted(bops - fols)))
    print('== files with type 2/4 frames but no own .PAL:')
    for name in sorted(fols):
        fol = read(b, name + '.FOL')
        if len(fol) % 16 or name + '.PAL' in files:
            continue
        c = collections.Counter(r[5] & 15 for r in read_fol16(fol))
        if c.get(2) or c.get(4):
            print('  %s: types %s' % (name, dict(c)))

    icons, tmp = read_fol16(read(b, 'ICONS.FOL')), read_fol16(read(b, 'ICONSTMP.FOL'))
    bop, cms = read(b, 'ICONS.BOP'), colormaps(read(b, 'ICONS.PAL'))

    def implied_end(recs):
        pos, bad = 0, 0
        for r in recs:
            bad += r[4] != pos
            pos = r[4] + (r[2] * r[3] if r[5] & 15 == 1 else (r[2] + 1) // 2 * r[3])
        return pos, bad
    print('ICONS.FOL: %d records, types %s, contiguous end/gaps %s, ICONS.BOP %d B'
          % (len(icons), dict(collections.Counter(r[5] for r in icons)), implied_end(icons), len(bop)))
    print('ICONSTMP.FOL: %d records, types %s, contiguous end/gaps %s'
          % (len(tmp), dict(collections.Counter(r[5] for r in tmp)), implied_end(tmp)))
    same_off = sum(1 for a, c in zip(tmp, icons) if a[2:6] == c[2:6])
    print('  leading records identical to ICONS.FOL (w, h, offset, kind): %d' % same_off)

    # LCS alignment on (w, h, kind), then relink ICONSTMP records to ICONS.BOP offsets
    key = lambda r: (r[2], r[3], r[5])
    n, m = len(tmp), len(icons)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            L[i][j] = L[i + 1][j + 1] + 1 if key(tmp[i]) == key(icons[j]) else max(L[i + 1][j], L[i][j + 1])
    i = j = 0
    pairs = {}
    while i < n and j < m:
        if key(tmp[i]) == key(icons[j]):
            pairs[i] = j
            i, j = i + 1, j + 1
        elif L[i + 1][j] >= L[i][j + 1]:
            i += 1
        else:
            j += 1
    t2 = [k for k, r in enumerate(tmp) if r[5] & 15 == 2]
    print('  aligned records %d/%d; type-2 aligned %d/%d; unaligned: %s'
          % (len(pairs), n, sum(1 for k in t2 if k in pairs), len(t2),
             [(k, tmp[k][2], tmp[k][3], tmp[k][5]) for k in range(n) if k not in pairs]))

    ends = segment_ends(icons, len(bop))
    naive, relinked = [], []
    for k in t2:
        r = tmp[k]
        end = r[4] + (r[2] + 1) // 2 * r[3]
        naive.append((r[2], r[3], decode_with_map(bop, r, end, cms[0]) if end <= len(bop) else [0] * (r[2] * r[3])))
        if k in pairs:
            j = pairs[k]
            relinked.append((r[2], r[3], decode_with_map(bop, icons[j], ends[j], cms[icons[j][5] >> 4])))
        else:
            relinked.append((r[2], r[3], [0] * (r[2] * r[3])))
    big = [(w, h, p) for w, h, p in naive if w <= 60 and h <= 64]
    save_sheet(f'{out}/iconstmp_type2_naive_on_icons_bop.png', big, pal, 14, 2, cell=(62, 66))
    big = [(w, h, p) for w, h, p in relinked if w <= 60 and h <= 64]
    save_sheet(f'{out}/iconstmp_type2_relinked_to_icons.png', big, pal, 14, 2, cell=(62, 66))


# ---------------------------------------------------------------- 5. odd .PAL files

def cmd_pal(game, out):
    b = binary_dir(game)
    files = listing(b)
    std = read(b, 'STANDARD.PAL')
    stdmap = {std[i]: std[i + 1:i + 4] for i in range(0, len(std), 4)}
    print('== .PAL classification')
    cls = collections.defaultdict(list)
    for name in sorted(n for n in files if n.endswith('.PAL')):
        d = read(b, name)
        seq = len(d) % 4 == 0 and all(d[i] == d[0] + i // 4 for i in range(0, len(d), 4))
        inc = len(d) % 4 == 0 and all(d[i] < d[i + 4] for i in range(0, len(d) - 4, 4))
        b512 = len(d) % 512 == 0
        c = ('A sequential' if seq else 'A increasing, gaps' if inc else '?') + (' + multiple of 512' if b512 else '')
        if not seq and not inc and b512:
            c = 'B'
        cls[c].append((name[:-4], len(d)))
    for c, v in cls.items():
        print('  %-35s %3d %s' % (c, len(v), '' if c == 'B' else v))
    for name in ('SYS.PAL', 'HALBERD.PAL', 'TESTSPR.PAL'):
        d = read(b, name)
        e = [(d[i], tuple(d[i + 1:i + 4])) for i in range(0, len(d), 4)]
        runs = []
        for i, rgb in e:
            if runs and runs[-1][2] == rgb and runs[-1][1] == i - 1:
                runs[-1][1] = i
            else:
                runs.append([i, i, rgb])
        short = ['%d-%d:%s' % (a, z, bytes(c).hex()) if a != z else '%d:%s' % (a, bytes(c).hex()) for a, z, c in runs]
        eq = sum(1 for i, rgb in e if stdmap.get(i) == bytes(rgb))
        print('%s: %d entries, indices %s; equal to STANDARD at same index: %d' % (
            name, len(e), 'sequential' if all(e[k][0] == e[0][0] + k for k in range(len(e))) else
            [i for i, _ in e], eq))
        print('  runs:', ' '.join(short[:14]), '...' if len(short) > 14 else '')
    t = read(b, 'TESTSPR.PAL')
    print('TESTSPR.PAL prefix 64 B == HALBERD.PAL:', t[:64] == read(b, 'HALBERD.PAL'))
    diff = [i for i in range(106, 246) if t[i * 4 + 1:i * 4 + 4] != stdmap[i]]
    print('TESTSPR 106..245 entries differing from STANDARD: %d -> %s' % (len(diff), diff))
    has_fol = 'TESTSPR.FOL' in files
    print('TESTSPR has .FOL/.BOP:', has_fol)
    # swatch 16x16 of TESTSPR and SYS over magenta-free background
    for name in ('TESTSPR.PAL', 'SYS.PAL'):
        p = load_rgb_palette(find(b, name))
        cells = [(1, 1, [i]) for i in range(256)]
        d = read(b, name)
        present = {d[i] for i in range(0, len(d), 4)}
        pal = [p[i] if i in present else (20, 20, 20) for i in range(256)]
        save_sheet(f'{out}/{name.lower().replace(".", "_")}_16x16.png', cells, pal, 16, 16, cell=(2, 2),
                   show_zero=True, bg=(0, 0, 0))


# ---------------------------------------------------------------- 6. FILE vs UPDATE

def walk(root):
    out = {}
    for dp, _, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root).upper()] = p
    return out


def cmd_patch(game, out):
    f = walk(os.path.join(game, 'FILE', 'BINARY'))
    u = walk(os.path.join(game, 'UPDATE', 'BINARY'))
    print('== FILE/BINARY %d files, UPDATE/BINARY %d files' % (len(f), len(u)))
    only_f, only_u = sorted(set(f) - set(u)), sorted(set(u) - set(f))
    dirs = collections.Counter(k.split(os.sep)[0] if os.sep in k else '(top level)' for k in only_f)
    print('only in FILE: %d, by directory %s' % (len(only_f), dict(dirs)))
    print('only in UPDATE: %d %s' % (len(only_u), only_u[:10]))
    common = sorted(set(f) & set(u))
    diff = [k for k in common if os.path.getsize(f[k]) != os.path.getsize(u[k])
            or open(f[k], 'rb').read() != open(u[k], 'rb').read()]
    print('common %d, byte-different %d %s' % (len(common), len(diff), diff[:20]))
    exts = collections.Counter(os.path.splitext(k)[1] for k in common)
    print('common by extension:', dict(exts))
    casediff = [k for k in common if os.path.basename(f[k]) != os.path.basename(u[k])]
    print('common names with different letter case: %d %s' % (len(casediff), casediff[:10]))
    r = os.path.join(game, 'REMOTE', 'BINARY')
    if os.path.isdir(r):
        rw = walk(r)
        print('REMOTE/BINARY: %d files, overlap with FILE/BINARY paths: %d' % (len(rw), len(set(rw) & set(f))))


COMMANDS = {'btp': cmd_btp, 'legacy': cmd_legacy, 'spells': cmd_spells, 'orphans': cmd_orphans,
            'pal': cmd_pal, 'patch': cmd_patch}

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    game = a[0]
    which = a[1] if len(a) > 1 else 'all'
    out = a[2] if len(a) > 2 else 'extracted/btp_sprite_leftovers'
    os.makedirs(out, exist_ok=True)
    for name, fn in COMMANDS.items():
        if which in ('all', name):
            fn(game, out)
            print()
