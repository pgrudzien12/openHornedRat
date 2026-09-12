"""Rysuje mape bitwy z .BTS (+ armia gracza z .MRC) z gory, do PNG. Sluzy do wizualnej weryfikacji.

Uzycie: render_battle.py <plik.BTS> [out.png] [skala=0.5] [--no-map]

Tlo: przyciemniona mapa planu (loadplanmap, np. MAP001.FOL/.BOP) rozciagnieta na pole
bitwy (FIELD x/y). Szukana w UPDATE/BINARY, potem FILE/BINARY obok katalogu SCRIPT.
Os Y swiata rosnie w gore mapy planu (zweryfikowane), wiec na obrazku jest odwrocona.

Legenda (pelny opis znaczen: battles/README.md, generowany przez battle_atlas.py):
  linie      granice z [BOUNDARIES], kolor wg rodzaju (BOUNDARY_KINDS)
  okregi     obiekty kolizji: czerwone = os_solid, jasnorozowe = bez os_solid;
             jasnopomaranczowe prostokaty = addrectangles (obrocone o dir)
  kropki     sceneria (placefurniture), zielone
  kwadraty   wezly skryptu, cyjan: pelny = ns_startpos, z biala obwodka = NS_END, pusty = inny
  kola       jednostki (SIDE_STYLE): pelne = widoczne, pierscien = hidden; kreska = dir; numer = nr w opisie
"""
import math, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from whscript import find_ci, load_battle, side_info                    # noqa: E402
from render_sprites import decode_frame, load_rgb_palette, write_png    # noqa: E402

DIR_UNITS = 512

# (rodzaj, kolor, nazwa koloru, znaczenie); dopasowanie nazwy w boundary_kind()
BOUNDARY_KINDS = (
    ('battle', (255, 255, 255), 'biały', 'granica pola bitwy'),
    ('deploy', (90, 230, 90), 'zielony', 'strefa rozstawienia wojsk gracza'),
    ('nav', (255, 215, 0), 'żółty', 'linia przeszkody dla nawigacji jednostek (hipoteza)'),
    ('camera', (185, 120, 255), 'fioletowy', 'obszar, po którym może poruszać się kamera (hipoteza z nazwy)'),
    ('view', (100, 185, 255), 'błękitny', 'granica widocznego obszaru mapy (hipoteza z nazwy)'),
    ('sight', (255, 120, 200), 'różowy', 'granica linii wzroku (hipoteza z nazwy)'),
    ('terrain', (255, 140, 40), 'pomarańczowy', 'krawędź przeszkody terenowej: klif, rzeka, mur, żywopłot…'),
)

# strona -> (kolor, nazwa koloru, opis)
SIDE_STYLE = {
    'enemy': ((235, 60, 60), 'czerwony', 'wróg (sekcja „Enemy Army” w .BTS)'),
    'npc': ((255, 160, 50), 'pomarańczowy', 'jednostki NPC (sekcja „NPC units” w .BTS)'),
    'player': ((70, 140, 255), 'niebieski', 'armia gracza (plik .MRC z loadmerc)'),
}

OBJ_SOLID, OBJ_SOFT, OBJ_RECT = (255, 60, 60), (255, 175, 190), (255, 205, 130)
SCENERY, NODE = (90, 225, 110), (60, 230, 230)

DIGITS = {
    '0': ('111', '101', '101', '101', '111'), '1': ('010', '110', '010', '010', '111'),
    '2': ('111', '001', '111', '100', '111'), '3': ('111', '001', '111', '001', '111'),
    '4': ('101', '101', '111', '001', '001'), '5': ('111', '100', '111', '001', '111'),
    '6': ('111', '100', '111', '101', '111'), '7': ('111', '001', '001', '001', '001'),
    '8': ('111', '101', '111', '101', '111'), '9': ('111', '101', '111', '001', '111'),
}


def boundary_kind(name):
    n = name.lower().replace(' ', '')
    if n.startswith('battle'):
        key = 'battle'
    elif 'deploy' in n:
        key = 'deploy'
    else:
        key = next((k for k in ('nav', 'camera', 'view', 'sight') if n.startswith(k)), 'terrain')
    return next(kind for kind in BOUNDARY_KINDS if kind[0] == key)


def load_planmap(bts_path, name, dim=0.55):
    """Zwraca (w, h, [rgb]) pierwszej klatki mapy planu albo None, gdy nie ma plikow."""
    file_dir = os.path.dirname(os.path.dirname(os.path.abspath(bts_path)))   # .../FILE
    bin_dirs = [os.path.join(os.path.dirname(file_dir), 'UPDATE', 'BINARY'), os.path.join(file_dir, 'BINARY')]
    bin_dirs = [d for d in bin_dirs if os.path.isdir(d)]
    fol = next((p for p in (find_ci(d, name + '.FOL') for d in bin_dirs) if p), None)
    bop = fol and find_ci(os.path.dirname(fol), name + '.BOP')
    std = next((p for p in (find_ci(d, 'STANDARD.PAL') for d in bin_dirs) if p), None)
    if not (fol and bop and std):
        return None
    fd, bd = open(fol, 'rb').read(), open(bop, 'rb').read()
    recs = [struct.unpack_from('<hhhhIB', fd, i * 16) for i in range(len(fd) // 16)]
    offsets = sorted(set(r[4] for r in recs)) + [len(bd)]
    rec = recs[0]
    pal_path = find_ci(os.path.dirname(fol), name + '.PAL')
    pd = open(pal_path, 'rb').read() if pal_path else b''
    cmaps = [pd[i:i + 512] for i in range(0, len(pd), 512)] if pd and len(pd) % 512 == 0 else []
    px = decode_frame(bd, rec, offsets[offsets.index(rec[4]) + 1], cmaps)
    pal = load_rgb_palette(std)
    return rec[2], rec[3], [tuple(int(c * dim) for c in pal[i]) for i in px]


class Canvas:
    """Os Y swiata rosnie w gore mapy planu, wiec na obrazku jest odwrocona (y1 na gorze)."""

    def __init__(self, x0, y0, x1, y1, scale):
        self.x0, self.y1, self.s = x0, y1, scale
        self.w, self.h = int((x1 - x0) * scale) + 1, int((y1 - y0) * scale) + 1
        self.px = bytearray(bytes((24, 26, 32)) * (self.w * self.h))

    def _xy(self, x, y):
        return int(round((x - self.x0) * self.s)), int(round((self.y1 - y) * self.s))

    def dot(self, sx, sy, c):
        if 0 <= sx < self.w and 0 <= sy < self.h:
            i = (sy * self.w + sx) * 3
            self.px[i:i + 3] = bytes(c)

    def fill(self, sx, sy, w, h, c):
        for y in range(sy, sy + h):
            for x in range(sx, sx + w):
                self.dot(x, y, c)

    def line(self, x1, y1, x2, y2, c, width=1):
        (ax, ay), (bx, by) = self._xy(x1, y1), self._xy(x2, y2)
        n = max(abs(bx - ax), abs(by - ay), 1)
        for t in range(n + 1):
            px, py = ax + (bx - ax) * t // n, ay + (by - ay) * t // n
            self.dot(px, py, c)
            if width > 1:
                self.dot(px + 1, py, c)
                self.dot(px, py + 1, c)

    def circle(self, x, y, r, c, fill=False, ring=0.6):
        cx, cy = self._xy(x, y)
        rr = max(r * self.s, 1)
        for sy in range(int(-rr) - 2, int(rr) + 3):
            for sx in range(int(-rr) - 2, int(rr) + 3):
                d = math.hypot(sx, sy)
                if (d <= rr) if fill else (abs(d - rr) < ring):
                    self.dot(cx + sx, cy + sy, c)

    def square(self, x, y, half, c, hollow=False):
        cx, cy = self._xy(x, y)
        for sy in range(-half, half + 1):
            for sx in range(-half, half + 1):
                if not hollow or max(abs(sx), abs(sy)) == half:
                    self.dot(cx + sx, cy + sy, c)

    def text(self, sx, sy, s, c, k=2):
        """Cyfry czcionka 3x5 (powiekszona k razy) na czarnym tle, w pikselach obrazka."""
        w = len(s) * 4 * k - k
        self.fill(sx - 1, sy - 1, w + 2, 5 * k + 2, (0, 0, 0))
        for i, ch in enumerate(s):
            for row, bits in enumerate(DIGITS.get(ch, ('000',) * 5)):
                for col, bit in enumerate(bits):
                    if bit == '1':
                        self.fill(sx + i * 4 * k + col * k, sy + row * k, k, k, c)

    def background(self, img, world_w, world_h):
        """Rozciaga obraz (w, h, [rgb]) na prostokat swiata (0,0)-(world_w,world_h)."""
        mw, mh, rgb = img
        for sy in range(self.h):
            wy = self.y1 - sy / self.s
            if not 0 < wy <= world_h:
                continue
            my = min(int((world_h - wy) * mh / world_h), mh - 1)   # wiersz 0 obrazka = gora = y swiata max
            for sx in range(self.w):
                wx = self.x0 + sx / self.s
                if 0 <= wx < world_w:
                    self.dot(sx, sy, rgb[my * mw + int(wx * mw / world_w)])

    def png(self, path):
        write_png(path, self.w, self.h, self.px)


def heading(x, y, d, length):
    """Hipoteza: dir 0 = w gore mapy (+y), rosnie zgodnie z ruchem wskazowek zegara."""
    a = (d or 0) * 2 * math.pi / DIR_UNITS
    return x + math.sin(a) * length, y + math.cos(a) * length


def collect_units(battle):
    """Wszystkie jednostki bitwy z numeracja (jak na obrazku) i strona: enemy / npc / player."""
    units = []
    for army in battle['armies']:
        label = (army['label'] or '').lower()
        for u in army['units']:
            info = side_info(u['stats'].get('s_side'))
            if 'npc' in label:
                side = 'npc'
            elif 'enemy' in label:
                side = 'enemy'
            else:
                side = 'npc' if info and info['npc'] and not info['enemy'] else 'enemy'
            units.append({'side': side, 'army': army['label'], 'unit': u, 'type': info})
    for army in (battle['merc'] or {}).get('armies') or []:
        for u in army['units']:
            units.append({'side': 'player', 'army': army['label'], 'unit': u,
                          'type': side_info(u['stats'].get('s_side'))})
    for nr, entry in enumerate(units, 1):
        entry['nr'] = nr
    return units


def render(bts, out, scale=0.5, with_map=True):
    """Rysuje bitwe i zwraca dane potrzebne do opisu: bitwa, jednostki z numerami, granice z kolorami."""
    b = load_battle(bts)
    f = b['field']
    units = collect_units(b)
    xs, ys = [0, f['width'] or 0], [0, f['height'] or 0]
    for bd in b['boundaries']:
        for x1, y1, x2, y2 in bd['lines']:
            xs += [x1, x2]
            ys += [y1, y2]
    for p in [e['unit']['set'] for e in units] + b['nodes'] + b['objects']:
        if isinstance(p.get('x'), (int, float)) and isinstance(p.get('y'), (int, float)):
            xs.append(p['x'])
            ys.append(p['y'])
    m = 48
    cv = Canvas(min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m, scale)

    has_map = False
    if with_map and f['planmap'] and f['width'] and f['height']:
        img = load_planmap(bts, f['planmap'])
        if img:
            cv.background(img, f['width'], f['height'])
            has_map = True

    for s in b['scenery']:
        cv.square(s['x'], s['y'], 1, SCENERY)

    boundaries = []
    for bd in b['boundaries']:
        kind = boundary_kind(bd['name'])
        boundaries.append({'name': bd['name'], 'kind': kind[0], 'color': kind[1], 'color_name': kind[2],
                           'meaning': kind[3], 'segments': len(bd['lines']), 'lines': bd['lines']})
    order = [k[0] for k in BOUNDARY_KINDS]
    for bd in sorted(boundaries, key=lambda x: -order.index(x['kind'])):   # granica pola na wierzchu
        for x1, y1, x2, y2 in bd['lines']:
            cv.line(x1, y1, x2, y2, bd['color'], width=2)

    for o in b['objects']:
        solid = 'os_solid' in [s.lower() for s in o['status']]
        cv.circle(o['x'], o['y'], o['radius'] or 4, OBJ_SOLID if solid else OBJ_SOFT)
        a = (o['dir'] or 0) * 2 * math.pi / DIR_UNITS
        ca, sa = math.cos(a), math.sin(a)
        for x1, y1, x2, y2 in o['rects']:
            pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            pts = [(o['x'] + px * ca - py * sa, o['y'] + px * sa + py * ca) for px, py in pts]
            for i in range(4):
                cv.line(*pts[i], *pts[(i + 1) % 4], OBJ_RECT)

    for n in b['nodes']:
        flags = [s.lower() for s in n['status']]
        if 'ns_end' in flags:
            cv.square(n['x'], n['y'], 4, (255, 255, 255))
            cv.square(n['x'], n['y'], 2, NODE)
        elif 'ns_startpos' in flags:
            cv.square(n['x'], n['y'], 3, NODE)
        else:
            cv.square(n['x'], n['y'], 3, NODE, hollow=True)

    for e in units:
        s = e['unit']['set']
        if not (isinstance(s.get('x'), (int, float)) and isinstance(s.get('y'), (int, float))):
            continue
        color = SIDE_STYLE[e['side']][0]
        hx, hy = heading(s['x'], s['y'], s.get('dir'), 48)
        cv.line(s['x'], s['y'], hx, hy, color, width=2)
        if e['unit']['hidden']:
            cv.circle(s['x'], s['y'], 16, color, ring=1.2)
        else:
            cv.circle(s['x'], s['y'], 16, color, fill=True)
        sx, sy = cv._xy(s['x'], s['y'])
        cv.text(sx + 8, sy - 16, str(e['nr']), color)

    cv.png(out)
    return {'battle': b, 'units': units, 'boundaries': boundaries, 'has_map': has_map, 'size': (cv.w, cv.h)}


if __name__ == '__main__':
    flags = [x for x in sys.argv[1:] if x.startswith('--')]
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    out = a[1] if len(a) > 1 else os.path.splitext(os.path.basename(a[0]))[0].lower() + '.png'
    info = render(a[0], out, float(a[2]) if len(a) > 2 else 0.5, with_map='--no-map' not in flags)
    print(f"{out}: {info['size'][0]}x{info['size'][1]}, jednostek {len(info['units'])}, mapa planu: {info['has_map']}")
