"""Battle terrain GRND.GD (FILE/MESH/<BATTLE>/GRND.GD): parser, renderer, exporter, checker.

Format (details: notes/terrain_gd.md):
  196608 bytes = 64 x 64 cells x 2 triangles x 24-byte record, no header.
  Cell (cx, cz) -> records 2*(cz*64 + cx) (triangle A) and +1 (triangle B).
  Record = float32 gx, gz, x, h, z + uint32 diag:
    plane h(X, Z) = h + gx*(X - x) + gz*(Z - z);  A is anchored at (cx*10, cz*10),
    B at ((cx+1)*10, (cz+1)*10); diag 1 = cell split along (x,z)-(x+10,z+10),
    diag 2 = split along (x+10,z)-(x,z+10), 0 = unused cell (all 24 bytes zero).
  Only a rectangle nx x nz in the corner (cx < nx, cz < nz) is used.
  1 GD unit = 8 world units (.BTS), GD x -> world x, GD z -> world y (up the plan map).

Usage:
  gd_render.py <BFxxx.BTS | GRND.GD> [out.png] [scale=0.25]
      PNG: [hypsometric tint + hillshade + terrain boundaries | plan map | plan map shaded
      by the terrain with contour lines], cropped to the battlefield (FIELD x/y).
      With a GRND.GD only the first panel is drawn (whole used grid).
  gd_render.py --export <BFxxx.BTS | GRND.GD> <outdir>
      writes <MESH>.obj (world units, Y up, -Z = up the plan map) and <MESH>.json
      (vertex height grid in GD units + diagonal per cell).
  gd_render.py --check <.../FILE>
      checks all MESH/*/GRND.GD against the format above and prints statistics,
      including the relation between the grid size and the .BTS field size.

Example:
  G=".../WARFB/FILE"
  python3 scripts/gd_render.py "$G/SCRIPT/BF009.BTS" extracted/terrain_gd/bf009.png
  python3 scripts/gd_render.py --export "$G/SCRIPT/BF009.BTS" extracted/terrain_gd
  python3 scripts/gd_render.py --check "$G"
"""
import collections, glob, json, math, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from whscript import find_ci, load_battle                 # noqa: E402
from render_battle import boundary_kind, load_planmap     # noqa: E402
from render_sprites import write_png                      # noqa: E402

GRID = 64            # cells per side in the file
CELL = 10.0          # cell size in GD units
REC = struct.Struct('<5fI')
WORLD_PER_GD = 8.0   # world (.BTS) units per GD unit, verified on the plan maps
LIGHT = (-1.0, 1.4, 1.0)   # light from the upper left of the map (x, h, z), z = up the map


class Terrain:
    def __init__(self, path):
        data = open(path, 'rb').read()
        if len(data) != GRID * GRID * 2 * REC.size:
            raise ValueError('%s: unexpected size %d' % (path, len(data)))
        self.path = path
        self.recs = [REC.unpack_from(data, i * REC.size) for i in range(GRID * GRID * 2)]
        used = [(i // 2) % GRID for i, r in enumerate(self.recs) if r[5]]
        used_z = [(i // 2) // GRID for i, r in enumerate(self.recs) if r[5]]
        self.nx, self.nz = max(used) + 1, max(used_z) + 1
        self.raw = data

    def cell(self, cx, cz):
        i = 2 * (cz * GRID + cx)
        return self.recs[i], self.recs[i + 1]

    def triangle(self, x, z):
        """Plane record covering the point (x, z) in GD units, or None outside the used grid."""
        cx, cz = int(x // CELL), int(z // CELL)
        if not (0 <= cx < self.nx and 0 <= cz < self.nz):
            return None
        a, b = self.cell(cx, cz)
        u, v = x - cx * CELL, z - cz * CELL
        if a[5] == 1:
            return a if u >= v else b          # A = (x,z) (x+10,z) (x+10,z+10)
        return a if u + v <= CELL else b       # A = (x,z) (x+10,z) (x,z+10)

    def height(self, x, z):
        t = self.triangle(x, z)
        return None if t is None else t[3] + t[0] * (x - t[2]) + t[1] * (z - t[4])

    def vertex_heights(self):
        """(nz+1) rows x (nx+1) columns of vertex heights (GD units), row 0 = z 0."""
        eps = 1e-3
        rows = []
        for vz in range(self.nz + 1):
            row = []
            for vx in range(self.nx + 1):
                x = min(max(vx * CELL, eps), self.nx * CELL - eps)
                z = min(max(vz * CELL, eps), self.nz * CELL - eps)
                row.append(self.height(x, z))
            rows.append(row)
        return rows

    def diagonals(self):
        return [[self.cell(cx, cz)[0][5] for cx in range(self.nx)] for cz in range(self.nz)]


def mesh_path(arg):
    """(GRND.GD path, battle or None, .BTS path or None) for a .BTS or a GRND.GD argument."""
    if arg.lower().endswith('.bts'):
        battle = load_battle(arg, with_merc=False)
        file_dir = os.path.dirname(os.path.dirname(os.path.abspath(arg)))
        mdir = find_ci(os.path.join(file_dir, 'MESH'), battle['field']['mesh'])
        gd = mdir and find_ci(mdir, 'GRND.GD')
        if not gd:
            raise FileNotFoundError('no GRND.GD for loadmesh:%s' % battle['field']['mesh'])
        return gd, battle, arg
    return arg, None, None


# ---------------------------------------------------------------- rendering

def shade(t):
    gx, gz = t[0], t[1]
    nlen = math.sqrt(gx * gx + 1 + gz * gz)
    llen = math.sqrt(sum(c * c for c in LIGHT))
    d = (-gx * LIGHT[0] + LIGHT[1] - gz * LIGHT[2]) / (nlen * llen)
    return max(0.0, d)


def tint(f):
    """Hypsometric color for f = 0..1: dark blue-green (low) -> olive -> light brown/white (high)."""
    stops = ((0.0, (40, 70, 90)), (0.25, (70, 110, 70)), (0.55, (150, 150, 90)),
             (0.8, (170, 130, 90)), (1.0, (245, 240, 230)))
    for (f0, c0), (f1, c1) in zip(stops, stops[1:]):
        if f <= f1:
            k = (f - f0) / ((f1 - f0) or 1)
            return tuple(c0[i] + (c1[i] - c0[i]) * k for i in range(3))
    return stops[-1][1]


def render(arg, out, scale=0.25, contour=2.0):
    gd, battle, bts = mesh_path(arg)
    ter = Terrain(gd)
    if battle:
        fw, fh = battle['field']['width'], battle['field']['height']
    else:
        fw, fh = ter.nx * CELL * WORLD_PER_GD, ter.nz * CELL * WORLD_PER_GD
    w, h = int(fw * scale), int(fh * scale)
    hs = [r[3] for r in ter.recs if r[5]]
    lo, hi = min(hs), max(hs)

    heights, shades = [None] * (w * h), [0.0] * (w * h)
    for py in range(h):
        z = (fh - (py + 0.5) / scale) / WORLD_PER_GD       # image row 0 = top = max world y
        for px in range(w):
            x = (px + 0.5) / scale / WORLD_PER_GD
            t = ter.triangle(x, z)
            if t is not None:
                heights[py * w + px] = t[3] + t[0] * (x - t[2]) + t[1] * (z - t[4])
                shades[py * w + px] = shade(t)

    relief = bytearray(w * h * 3)
    for i, hv in enumerate(heights):
        if hv is None:
            relief[i * 3:i * 3 + 3] = bytes((255, 0, 255))
            continue
        c = tint((hv - lo) / ((hi - lo) or 1))
        k = 0.35 + 0.9 * shades[i]
        relief[i * 3:i * 3 + 3] = bytes(min(255, int(v * k)) for v in c)

    def put(buf, px, py, c):
        if 0 <= px < w and 0 <= py < h:
            buf[(py * w + px) * 3:(py * w + px) * 3 + 3] = bytes(c)

    panels = [relief]
    if battle:
        for bd in battle['boundaries']:
            kind = boundary_kind(bd['name'])
            if kind[0] not in ('terrain', 'battle'):
                continue
            for x1, y1, x2, y2 in bd['lines']:
                a = ((x1 * scale), ((fh - y1) * scale))
                b = ((x2 * scale), ((fh - y2) * scale))
                n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1))
                for s in range(n + 1):
                    put(relief, int(a[0] + (b[0] - a[0]) * s / n), int(a[1] + (b[1] - a[1]) * s / n), kind[1])
        pm = load_planmap(bts, battle['field']['planmap'], dim=1.0)
        if pm:
            mw, mh, prgb = pm
            plan, over = bytearray(w * h * 3), bytearray(w * h * 3)
            for py in range(h):
                my = min(int(py * mh / h), mh - 1)
                for px in range(w):
                    i = py * w + px
                    c = prgb[my * mw + min(int(px * mw / w), mw - 1)]
                    plan[i * 3:i * 3 + 3] = bytes(c)
                    k = 0.25 + 1.0 * shades[i]
                    over[i * 3:i * 3 + 3] = bytes(min(255, int(v * k)) for v in c)
            # contour lines every `contour` GD units
            for py in range(h):
                for px in range(w):
                    hv = heights[py * w + px]
                    if hv is None:
                        continue
                    for qx, qy in ((px + 1, py), (px, py + 1)):
                        if qx < w and qy < h and heights[qy * w + qx] is not None:
                            if math.floor(hv / contour + 1e-3) != math.floor(heights[qy * w + qx] / contour + 1e-3):
                                put(over, px, py, (255, 40, 40))
            panels += [plan, over]

    gap = 6
    tw = w * len(panels) + gap * (len(panels) - 1)
    img = bytearray()
    for py in range(h):
        for k, p in enumerate(panels):
            if k:
                img += bytes((0, 0, 0)) * gap
            img += p[py * w * 3:(py + 1) * w * 3]
    write_png(out, tw, h, img)
    print('%s: grid %dx%d cells, field %sx%s, height %.1f..%.1f GD units -> %s (%dx%d)'
          % (os.path.basename(os.path.dirname(gd)), ter.nx, ter.nz, fw, fh, lo, hi, out, tw, h))


# ---------------------------------------------------------------- export

def export(arg, outdir):
    gd, battle, _ = mesh_path(arg)
    ter = Terrain(gd)
    name = os.path.basename(os.path.dirname(os.path.abspath(gd))).upper()
    os.makedirs(outdir, exist_ok=True)
    vh = ter.vertex_heights()
    diag = ter.diagonals()
    info = {
        'mesh': name, 'source': os.path.basename(gd),
        'cells_x': ter.nx, 'cells_z': ter.nz, 'cell_size_gd': CELL,
        'world_per_gd': WORLD_PER_GD,
        'field': battle and [battle['field']['width'], battle['field']['height']],
        'note': 'heights[z][x] in GD units at vertex (x*10, z*10); world = GD * world_per_gd; '
                'GD z = world y (up the plan map). diagonal[z][x]: 1 = (x,z)-(x+1,z+1), 2 = (x+1,z)-(x,z+1)',
        'heights': [[round(v, 4) for v in row] for row in vh],
        'diagonal': diag,
    }
    jpath = os.path.join(outdir, name + '.json')
    json.dump(info, open(jpath, 'w'))
    opath = os.path.join(outdir, name + '.obj')
    with open(opath, 'w') as f:
        f.write('# %s terrain from GRND.GD, world units, Y up, -Z = up the plan map\n' % name)
        for vz in range(ter.nz + 1):
            for vx in range(ter.nx + 1):
                s = CELL * WORLD_PER_GD
                f.write('v %g %g %g\n' % (vx * s, vh[vz][vx] * WORLD_PER_GD, -vz * s))
        idx = lambda vx, vz: vz * (ter.nx + 1) + vx + 1
        for cz in range(ter.nz):
            for cx in range(ter.nx):
                p00, p10, p11, p01 = idx(cx, cz), idx(cx + 1, cz), idx(cx + 1, cz + 1), idx(cx, cz + 1)
                if diag[cz][cx] == 1:
                    tris = ((p00, p10, p11), (p11, p01, p00))
                else:
                    tris = ((p00, p10, p01), (p11, p01, p10))
                for t in tris:           # counter-clockwise seen from +Y
                    f.write('f %d %d %d\n' % t)
    print('%s: %s, %s' % (name, opath, jpath))


# ---------------------------------------------------------------- validation

def check(file_dir):
    fields = {}
    for p in sorted(glob.glob(os.path.join(file_dir, 'SCRIPT', '*.[Bb][Tt][Ss]'))):
        b = load_battle(p, with_merc=False)
        mesh = (b['field']['mesh'] or '').upper()
        fields.setdefault(mesh, []).append((os.path.basename(p), b['field']['width'], b['field']['height']))
    paths = sorted(glob.glob(os.path.join(file_dir, 'MESH', '*', 'GRND.GD')))
    total = collections.Counter()
    problems = 0
    print('%-8s %5s %5s %5s %6s %6s %6s %10s %8s  %s' % (
        'mesh', 'nx', 'nz', 'diag2', 'hmin', 'hmax', '|g|max', 'seam err', 'margin', 'field (.BTS)'))
    for p in paths:
        name = os.path.basename(os.path.dirname(p)).upper()
        t = Terrain(p)
        errs = []
        diag2 = 0
        for cz in range(GRID):
            for cx in range(GRID):
                a, b = t.cell(cx, cz)
                inside = cx < t.nx and cz < t.nz
                i = 2 * (cz * GRID + cx)
                if not inside:
                    if t.raw[i * REC.size:(i + 2) * REC.size].strip(b'\0'):
                        errs.append('non-zero record outside grid at %d,%d' % (cx, cz))
                    continue
                if a[5] not in (1, 2) or a[5] != b[5]:
                    errs.append('diag %s/%s at %d,%d' % (a[5], b[5], cx, cz))
                if (a[2], a[4]) != (cx * CELL, cz * CELL) or (b[2], b[4]) != ((cx + 1) * CELL, (cz + 1) * CELL):
                    errs.append('anchor at %d,%d' % (cx, cz))
                diag2 += a[5] == 2
                total[a[5]] += 2
        # seam error: every vertex evaluated from all adjacent triangles
        seam = 0.0
        e = 1e-3
        for vz in range(t.nz + 1):
            for vx in range(t.nx + 1):
                vals = [t.height(vx * CELL + dx, vz * CELL + dz) for dx in (-e, e) for dz in (-e, e)]
                vals = [v for v in vals if v is not None]
                seam = max(seam, max(vals) - min(vals))
        used = [r for r in t.recs if r[5]]
        hs = [r[3] for r in used]
        g = max(max(abs(r[0]), abs(r[1])) for r in used)
        fl = fields.get(name, [])
        margin = ''
        if fl:
            _, fw, fh = fl[0]
            margin = '%+d/%+d' % (t.nx - math.ceil(fw / (CELL * WORLD_PER_GD)), t.nz - math.ceil(fh / (CELL * WORLD_PER_GD)))
        if seam > 0.05:
            errs.append('seam error %.3f' % seam)
        problems += bool(errs)
        print('%-8s %5d %5d %5d %6.1f %6.1f %6.2f %10.4f %8s  %s%s' % (
            name, t.nx, t.nz, diag2, min(hs), max(hs), g, seam, margin,
            ', '.join('%s %sx%s' % f for f in fl) or '-',
            ('  ERRORS: ' + '; '.join(errs[:3])) if errs else ''))
    missing = sorted(m for m in fields if m and not find_ci(os.path.join(file_dir, 'MESH'), m))
    print('\nfiles: %d, with errors: %d; records: diag1 %d, diag2 %d, unused %d'
          % (len(paths), problems, total[1], total[2], len(paths) * GRID * GRID * 2 - total[1] - total[2]))
    print('loadmesh without a MESH directory: %s' % (', '.join('%s (%s)' % (m, ', '.join(f[0] for f in fields[m])) for m in missing) or '-'))
    print('margin = nx - ceil(field_x / 80), nz - ceil(field_y / 80)')


def main(argv):
    if len(argv) >= 2 and argv[0] == '--check':
        check(argv[1])
    elif len(argv) >= 3 and argv[0] == '--export':
        export(argv[1], argv[2])
    elif argv:
        out = argv[1] if len(argv) > 1 else os.path.splitext(os.path.basename(argv[0]))[0].lower() + '_terrain.png'
        render(argv[0], out, float(argv[2]) if len(argv) > 2 else 0.25)
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
