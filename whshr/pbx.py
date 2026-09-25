# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Parses unpacked .PBX containers (textures, meshes, embedded sprite files) and extracts them.

Usage: pbx_extract.py <WARFB dir> <out dir> [BATTLE ...]   # writes <out>/<BATTLE>/<GRND|SCENERY|SPRITES>/
       pbx_extract.py --check <WARFB dir>                   # parse everything, print summary, write nothing
e.g.:  pbx_extract.py ".../WARFB" extracted/pbx BF001 BF005

Output per PBX: files/ (embedded .bop/.fol/.pal, byte-exact), textures/*.png, meshes/*.obj
+ materials.mtl, index.json and preview sheets (textures.png, meshes_front.png, meshes_top.png,
sprites/<NAME>.png). Container layout: see notes/pbx_rnc.md.
"""
import glob, json, os, struct, sys
from collections.abc import Sequence
from os import PathLike
from typing import Any

from . import rnc as pbx_rnc
from .image import load_rgb_palette, write_png
from .sprites import decode_frame

MAGIC = b'\x60\x75\x45\xc8'

Mesh = dict[str, Any]  # parse_mesh's result: nv, nn, verts, normals, faces, ftex, uv, offset, end (+ name)
Texture = dict[str, Any]  # name, w, h, palette, pixels, palette_size, trailer
Cell = tuple[int, int, bytes | None]  # (width, height, rgb bytes)


class PbxError(Exception):
    pass


def u32s(d: bytes, o: int, n: int = 1) -> tuple[int, ...]:
    return struct.unpack_from('<%dI' % n, d, o)


def parse_mesh(d: bytes, o: int, version: int) -> Mesh:
    """Mesh blob. v2 faces: u32 k, u32 k, k*(u32 vertex, u32 normal); v1 faces: u32 k, k pairs."""
    nv, nn = u32s(d, o, 2)
    p = o + 8
    verts = struct.unpack_from('<%df' % (3 * nv), d, p); p += 12 * nv
    normals = struct.unpack_from('<%df' % (3 * nn), d, p); p += 12 * nn
    nf, nref = u32s(d, p, 2); p += 8
    faces: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    refs = 0
    for _ in range(nf):
        if version == 2:
            k, k2 = u32s(d, p, 2); p += 8
            if k != k2:
                raise PbxError('face counts differ at %d' % p)
        else:
            k = u32s(d, p)[0]; p += 4
        pairs = u32s(d, p, 2 * k); p += 8 * k
        vs, ns = pairs[0::2], pairs[1::2]
        if max(vs) >= nv or max(ns) >= nn:
            raise PbxError('face index out of range at %d' % p)
        faces.append((vs, ns))
        refs += k
    if refs != nref:
        raise PbxError('face reference count mismatch at %d' % o)
    ftex = u32s(d, p, nf); p += 4 * nf
    uv = struct.unpack_from('<%df' % (2 * nv), d, p); p += 8 * nv
    return dict(nv=nv, nn=nn, verts=verts, normals=normals, faces=faces, ftex=ftex, uv=uv,
                offset=o, end=p)


def parse_container(d: bytes) -> dict[str, Any]:
    if d[:4] != MAGIC:
        raise PbxError('bad container magic %s' % d[:4].hex())
    res: dict[str, Any] = dict(files=[], textures=[], meshes=[], mesh_raw=b'')
    if u32s(d, 4)[0] == 207:
        version = 2
        ver, zero, nmesh, nfile, ntex, pix_total, pal_total = u32s(d, 4, 7)
        res['header'] = dict(version=ver, unk8=zero, meshes=nmesh, files=nfile, textures=ntex,
                             texture_pixel_bytes=pix_total, texture_palette_bytes=pal_total)
        o = 32
    else:
        version = 1                                   # only MESH/BF004/GRND.PBX (unused by scripts)
        unk4, unk8, ntex, pix_total, pal_total = u32s(d, 4, 5)
        nmesh, nfile = 0, 0
        res['header'] = dict(version=0, unk4=unk4, unk8=unk8, textures=ntex,
                             texture_pixel_bytes=pix_total, texture_palette_bytes=pal_total)
        o = 24
    res['version'] = version

    for _ in range(nfile):                            # embedded files: name, size, data
        nl = u32s(d, o)[0]
        name = d[o + 4:o + 4 + nl].decode('latin-1')
        size = u32s(d, o + 4 + nl)[0]
        res['files'].append((name, d[o + 8 + nl:o + 8 + nl + size]))
        o += 8 + nl + size

    pix_sum = pal_sum = 0
    for _ in range(ntex):                             # serialized D3DRMIMAGE structures
        nl = u32s(d, o)[0]
        name = d[o + 4:o + 4 + nl].split(b'\0')[0].decode('latin-1')
        p = o + 4 + nl
        if version == 2:
            pix_size, pal_size, w, h, aspx, aspy, depth, rgb, bpl = u32s(d, p, 9); p += 36
        else:
            pix_size, pal_size, w, h, depth, rgb, bpl = u32s(d, p, 7); p += 28
            aspx = aspy = None
        if d[p] != 0x31 or w * h != pix_size or bpl != w or depth != 8:
            raise PbxError('texture %s: unexpected header at %d' % (name, o))
        pixels = d[p + 1:p + 1 + pix_size]; p += 1 + pix_size
        if d[p] != 0x30:
            raise PbxError('texture %s: no buffer2 marker' % name)
        p += 1
        masks = u32s(d, p, 4); pal_count = u32s(d, p + 16)[0]; p += 20
        pal = d[p:p + pal_size]; p += pal_size
        ntrail = 4 if version == 2 else 3
        trailer = u32s(d, p, ntrail); p += 4 * ntrail
        res['textures'].append(dict(name=name, w=w, h=h, aspect=(aspx, aspy), rgb=rgb, masks=masks,
                                    palette_size=pal_count, pixels=pixels,
                                    palette=[tuple(pal[i:i + 3]) for i in range(0, pal_size, 4)],
                                    trailer=trailer))
        pix_sum += pix_size; pal_sum += pal_size
        o = p
    if pix_sum != pix_total or pal_sum != pal_total:
        raise PbxError('texture byte totals do not match header')

    if version == 1:
        res['mesh_raw'] = d[o:]
        res['data_end'] = o
        return res

    # directory at the end: 4 u32 = distances from EOF to 4 offset arrays
    t = u32s(d, len(d) - 16, 4)
    fname_offs = u32s(d, len(d) - t[0], nfile)
    fdata_offs = u32s(d, len(d) - t[1], nfile)
    mname_offs = u32s(d, len(d) - t[2], nmesh)
    mdata_offs = u32s(d, len(d) - t[3], nmesh)
    starts = {}
    fo = 32
    for name, blob in res['files']:
        starts[fo] = name
        fo += 8 + len(name) + len(blob)
    for a, b in zip(fname_offs, fdata_offs):
        nl = u32s(d, a)[0]
        if a not in starts or b != a + 4 + nl:
            raise PbxError('file directory entry does not match data')
    names_in_dir = [d[a + 4:a + 4 + u32s(d, a)[0]].decode('latin-1') for a in fname_offs]
    mesh_names = [d[a + 4:a + 4 + u32s(d, a)[0]].decode('latin-1') for a in mname_offs]
    res['dir_sorted'] = (names_in_dir == sorted(names_in_dir, key=str.lower)
                         and mesh_names == sorted(mesh_names, key=str.lower))
    order = sorted(range(nmesh), key=lambda i: mdata_offs[i])
    if nmesh and mdata_offs[order[0]] != o:
        raise PbxError('first mesh not right after textures')
    names_start = min(mname_offs) if nmesh else o
    for j, i in enumerate(order):
        m = parse_mesh(d, mdata_offs[i], 2)
        nxt = mdata_offs[order[j + 1]] if j + 1 < nmesh else names_start
        if m['end'] != nxt:
            raise PbxError('mesh %s size mismatch' % mesh_names[i])
        if m['ftex'] and max(m['ftex']) >= ntex:
            raise PbxError('mesh %s texture index out of range' % mesh_names[i])
        m['name'] = mesh_names[i]
        res['meshes'].append(m)
    res['data_end'] = names_start
    return res


# ---------------------------------------------------------------- rendering helpers

def texture_rgb(tex: Texture) -> bytes:
    pal = tex['palette']
    return b''.join(bytes(pal[i]) for i in tex['pixels'])


def sheet(cells: Sequence[Cell], cell_w: int, cell_h: int, cols: int,
          bg: tuple[int, int, int] = (40, 40, 48)) -> tuple[int, int, bytes]:
    """cells: list of (w, h, rgb bytes or None). Returns (W, H, rgb)."""
    rows = max(1, (len(cells) + cols - 1) // cols)
    W, H = cols * (cell_w + 2), rows * (cell_h + 2)
    img = bytearray(bytes(bg) * (W * H))
    for k, (w, h, rgb) in enumerate(cells):
        if rgb is None:
            continue
        ox, oy = (k % cols) * (cell_w + 2) + 1, (k // cols) * (cell_h + 2) + 1
        for y in range(min(h, cell_h)):
            row = rgb[y * w * 3:(y * w + min(w, cell_w)) * 3]
            s = ((oy + y) * W + ox) * 3
            img[s:s + len(row)] = row
    return W, H, bytes(img)


def scale_rgb(w: int, h: int, rgb: bytes, f: int) -> tuple[int, int, bytes]:
    out = bytearray()
    for y in range(h * f):
        src = rgb[(y // f) * w * 3:((y // f) + 1) * w * 3]
        out += b''.join(src[x * 3:x * 3 + 3] * f for x in range(w))
    return w * f, h * f, bytes(out)


def render_mesh(mesh: Mesh, textures: Sequence[Texture], size: int, view: str) -> bytes:
    """Orthographic textured render. view 'front': screen x=X, y=Y (up); 'top': x=X, y=Z.
    Black texels (RGB 0,0,0) are treated as transparent when the texture trailer flag
    (v2 trailer[2]) is 1 - a hypothesis (D3DRM decal transparency), checked only visually."""
    V = mesh['verts']
    ax, ay, az = (0, 1, 2) if view == 'front' else (0, 2, 1)
    xs, ys, zs = V[ax::3], V[ay::3], V[az::3]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny) or 1.0
    k = (size - 4) / span
    offx = (size - (maxx - minx) * k) / 2
    offy = (size - (maxy - miny) * k) / 2
    sx = [(x - minx) * k + offx for x in xs]
    sy = [size - ((y - miny) * k + offy) for y in ys]
    zbuf = [float('-inf')] * (size * size)
    img = bytearray(b'\x28\x28\x30' * (size * size))
    uv = mesh['uv']
    for (vs, _), ti in zip(mesh['faces'], mesh['ftex']):
        tex = textures[ti] if ti < len(textures) else None
        transparent = tex is not None and len(tex['trailer']) == 4 and tex['trailer'][2] == 1
        for t in range(1, len(vs) - 1):              # fan triangulation (faces are triangles anyway)
            a, b, c = vs[0], vs[t], vs[t + 1]
            x0, y0, x1, y1, x2, y2 = sx[a], sy[a], sx[b], sy[b], sx[c], sy[c]
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-9:
                continue
            for py in range(max(0, int(min(y0, y1, y2))), min(size, int(max(y0, y1, y2)) + 1)):
                for px in range(max(0, int(min(x0, x1, x2))), min(size, int(max(x0, x1, x2)) + 1)):
                    cx, cy = px + 0.5, py + 0.5
                    l0 = ((y1 - y2) * (cx - x2) + (x2 - x1) * (cy - y2)) / den
                    l1 = ((y2 - y0) * (cx - x2) + (x0 - x2) * (cy - y2)) / den
                    l2 = 1 - l0 - l1
                    if l0 < 0 or l1 < 0 or l2 < 0:
                        continue
                    z = l0 * zs[a] + l1 * zs[b] + l2 * zs[c]
                    i = py * size + px
                    if z <= zbuf[i]:
                        continue
                    if tex:
                        tu = l0 * uv[2 * a] + l1 * uv[2 * b] + l2 * uv[2 * c]
                        tv = l0 * uv[2 * a + 1] + l1 * uv[2 * b + 1] + l2 * uv[2 * c + 1]
                        idx = tex['pixels'][(int(tv * tex['h']) % tex['h']) * tex['w'] + int(tu * tex['w']) % tex['w']]
                        col = tex['palette'][idx]
                        if transparent and col == (0, 0, 0):
                            continue
                    else:
                        col = (200, 0, 200)
                    zbuf[i] = z
                    img[i * 3:i * 3 + 3] = bytes(col)
    return bytes(img)


def write_obj(path: str | PathLike[str], mesh: Mesh, textures: Sequence[Texture], mtl_name: str) -> None:
    V, N, UV = mesh['verts'], mesh['normals'], mesh['uv']
    out = ['# %s (from .PBX)' % mesh['name'], 'mtllib %s' % mtl_name]
    out += ['v %g %g %g' % V[i:i + 3] for i in range(0, len(V), 3)]
    out += ['vt %g %g' % (UV[i], 1 - UV[i + 1]) for i in range(0, len(UV), 2)]
    out += ['vn %g %g %g' % N[i:i + 3] for i in range(0, len(N), 3)]
    cur = None
    for (vs, ns), ti in zip(mesh['faces'], mesh['ftex']):
        if ti != cur:
            out.append('usemtl %s' % mtl_ident(textures[ti]['name'], ti))
            cur = ti
        out.append('f ' + ' '.join('%d/%d/%d' % (v + 1, v + 1, n + 1) for v, n in zip(vs, ns)))
    open(path, 'w').write('\n'.join(out) + '\n')


def mtl_ident(name: str, i: int) -> str:
    return 't%02d_%s' % (i, os.path.splitext(name)[0])


# ---------------------------------------------------------------- extraction

def find_ci(root: str, *parts: str) -> str | None:
    """Case-insensitive path lookup."""
    cur = root
    for part in parts:
        if not os.path.isdir(cur):
            return None
        hit = [e for e in os.listdir(cur) if e.lower() == part.lower()]
        if not hit:
            return None
        cur = os.path.join(cur, hit[0])
    return cur


def decode_sprite_sets(files: Sequence[tuple[str, bytes]], rgb_pal: Sequence[tuple[int, int, int]],
                       outdir: str | None = None, max_frames: int = 16, scale: int = 2) -> tuple[int, int, int]:
    """Decodes all frames of every .fol/.bop pair. Returns (sets, frames_ok, frames_err)."""
    by = {n.lower(): b for n, b in files}
    sets = ok = err = 0
    for name, fol in files:
        if not name.lower().endswith('.fol'):
            continue
        stem = name[:-4]
        bop = by.get(stem.lower() + '.bop')
        pd = by.get(stem.lower() + '.pal', b'')
        if bop is None:
            continue
        cmaps = [pd[i:i + 512] for i in range(0, len(pd), 512)] if pd and len(pd) % 512 == 0 else []
        recs = [struct.unpack_from('<hhhhIB', fol, i * 16) for i in range(len(fol) // 16)]
        offs = sorted(set(r[4] for r in recs)) + [len(bop)]
        cells: list[Cell] = []
        for fi, r in enumerate(recs):
            try:
                px = decode_frame(bop, r, offs[offs.index(r[4]) + 1], cmaps)
                if len(px) != r[2] * r[3]:
                    raise ValueError('size')
                ok += 1
                if fi < max_frames:
                    rgb = b''.join(bytes(rgb_pal[c]) if c else b'\x28\x28\x30' for c in px)
                    cells.append((r[2], r[3], rgb))
            except Exception:
                err += 1
        sets += 1
        if outdir and cells:
            cw, ch = max(c[0] for c in cells), max(c[1] for c in cells)
            W, H, rgb = sheet(cells, cw, ch, 8)
            write_png(os.path.join(outdir, stem.upper() + '.png'), *scale_rgb(W, H, rgb, scale))
    return sets, ok, err


def extract_pbx(path: str, outdir: str | None, rgb_pal: Any, write: bool = True) -> dict[str, Any]:
    outdir = outdir or ''  # only used when `write` is set
    data, rh = pbx_rnc.unpack_pbx(path)
    c = parse_container(data)
    st: dict[str, Any] = dict(rnc_ok=1, version=c['version'], files=len(c['files']), textures=len(c['textures']),
              meshes=len(c['meshes']), faces=sum(len(m['faces']) for m in c['meshes']),
              ext={}, png=0, dir_sorted=c.get('dir_sorted'), mesh_raw=len(c['mesh_raw']))
    for n, _ in c['files']:
        e = os.path.splitext(n)[1].lower()
        st['ext'][e] = st['ext'].get(e, 0) + 1
    if write:
        os.makedirs(outdir, exist_ok=True)
        index = dict(source=os.path.basename(path), rnc=dict((k, v) for k, v in rh.items() if k != 'prefix'),
                     prefix=rh['prefix'].hex(), container=c['header'],
                     files=[dict(name=n, size=len(b)) for n, b in c['files']],
                     textures=[dict(name=t['name'], w=t['w'], h=t['h'], palette_size=t['palette_size'],
                                    trailer=t['trailer']) for t in c['textures']],
                     meshes=[dict(name=m['name'], vertices=m['nv'], normals=m['nn'], faces=len(m['faces']),
                                  textures=sorted(set(c['textures'][i]['name'] for i in m['ftex'])))
                             for m in c['meshes']])
        json.dump(index, open(os.path.join(outdir, 'index.json'), 'w'), indent=1)
    if c['files'] and write:
        fd = os.path.join(outdir, 'files')
        os.makedirs(fd, exist_ok=True)
        for n, b in c['files']:
            open(os.path.join(fd, n), 'wb').write(b)
    if c['textures'] and write:
        td = os.path.join(outdir, 'textures')
        os.makedirs(td, exist_ok=True)
        cells = []
        for i, t in enumerate(c['textures']):
            rgb = texture_rgb(t)
            write_png(os.path.join(td, '%02d_%s.png' % (i, os.path.splitext(t['name'])[0])), t['w'], t['h'], rgb)
            st['png'] += 1
            cells.append(scale_rgb(t['w'], t['h'], rgb, 2))
        W, H, rgb = sheet(cells, 128, 128, 10)
        write_png(os.path.join(outdir, 'textures.png'), W, H, rgb)
        with open(os.path.join(outdir, 'materials.mtl'), 'w') as f:
            for i, t in enumerate(c['textures']):
                f.write('newmtl %s\nKd 1 1 1\nmap_Kd textures/%02d_%s.png\n\n'
                        % (mtl_ident(t['name'], i), i, os.path.splitext(t['name'])[0]))
    if c['meshes'] and write:
        md = os.path.join(outdir, 'meshes')
        os.makedirs(md, exist_ok=True)
        size = 512 if len(c['meshes']) == 1 else 128
        for view in ('front', 'top'):
            cells = []
            for m in c['meshes']:
                cells.append((size, size, render_mesh(m, c['textures'], size, view)))
            sheet_w, sheet_h, sheet_rgb = sheet(cells, size, size, min(8, len(cells)))
            write_png(os.path.join(outdir, 'meshes_%s.png' % view), sheet_w, sheet_h, sheet_rgb)
            st['png'] += 1
        for m in c['meshes']:
            write_obj(os.path.join(md, os.path.splitext(m['name'])[0] + '.obj'), m, c['textures'],
                      '../materials.mtl')
    if c['mesh_raw'] and write:
        open(os.path.join(outdir, 'mesh_section_v1.bin'), 'wb').write(c['mesh_raw'])
    if c['files']:
        sd = os.path.join(outdir, 'sprites') if write else None
        if sd:
            os.makedirs(sd, exist_ok=True)
        st['sets'], st['frames_ok'], st['frames_err'] = decode_sprite_sets(c['files'], rgb_pal, sd)
        if write:
            st['png'] += st['sets']
    return st


def main(argv: list[str]) -> None:
    check = argv[0] == '--check'
    if check:
        argv = argv[1:]
    warfb = argv[0]
    out = '' if check else argv[1]
    only = set(a.upper() for a in argv[1 if check else 2:])
    pal_path = find_ci(warfb, 'UPDATE', 'BINARY', 'STANDARD.PAL') or find_ci(warfb, 'FILE', 'BINARY', 'STANDARD.PAL')
    if pal_path is None:
        raise FileNotFoundError('no STANDARD.PAL under %s' % warfb)
    rgb_pal = load_rgb_palette(pal_path)
    mesh_dir = find_ci(warfb, 'FILE', 'MESH')
    if mesh_dir is None:
        raise FileNotFoundError('no FILE/MESH directory under %s' % warfb)
    files = sorted(glob.glob(os.path.join(mesh_dir, '*', '*.[Pp][Bb][Xx]')))
    tot = {}
    for f in files:
        battle = os.path.basename(os.path.dirname(f))
        if only and battle.upper() not in only:
            continue
        kind = os.path.splitext(os.path.basename(f))[0].upper()
        try:
            st = extract_pbx(f, None if check else os.path.join(out, battle, kind), rgb_pal, not check)
        except Exception as e:
            print('ERR %s/%s: %s' % (battle, kind, e))
            st = dict(rnc_ok=0, err=1)
        else:
            print('OK  %-8s %-7s v%d files=%-3d tex=%-3d meshes=%-3d faces=%-6d frames=%d/%d png=%d' % (
                battle, kind, st['version'], st['files'], st['textures'], st['meshes'], st['faces'],
                st.get('frames_ok', 0), st.get('frames_ok', 0) + st.get('frames_err', 0), st['png']))
        t = tot.setdefault(kind, {})
        t['pbx'] = t.get('pbx', 0) + 1
        for k, v in st.items():
            if isinstance(v, bool) or k == 'version':
                continue
            if isinstance(v, dict):
                for e, n in v.items():
                    t[e] = t.get(e, 0) + n
            elif isinstance(v, int):
                t[k] = t.get(k, 0) + v
    print('\nSummary per PBX kind:')
    for kind, t in sorted(tot.items()):
        print('  %-8s %s' % (kind, ', '.join('%s=%d' % kv for kv in sorted(t.items()))))


if __name__ == '__main__':
    main(sys.argv[1:])
