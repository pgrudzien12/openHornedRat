"""Parser tekstowych skryptow gry: bitew (.BTS) i armii (.MRC). Opis formatu: FORMATS.md.

Uzycie:
  whscript.py <plik.BTS|plik.MRC>        podsumowanie jednego pliku
  whscript.py <plik> --json              pelny, typowany widok jako JSON
  whscript.py --check <katalog SCRIPT>   parsuje wszystkie pliki i sprawdza liczniki set:count

Warstwy:
  parse()        -> ogolne drzewo wezlow (sekcje [X]...[END] i bloki addX:...endX:)
  load_battle()  -> typowany widok .BTS (pole, cele, obiekty, sceneria, granice, armie, wezly)
  load_army()    -> typowany widok .MRC (lista armii z jednostkami)
"""
import json, os, re, sys

# otwarcie bloku -> zamkniecie (porownanie bez rozrozniania wielkosci liter)
BLOCKS = {
    'addunit': 'endunit', 'addleader': 'endleader', 'addobject': 'endobject',
    'addnode': 'endnode', 'addboundary': 'endboundary', 'addrectangles': 'endrectangles',
}
CLOSERS = {v: k for k, v in BLOCKS.items()}
# 9 wartosci s_move = profil z bitewnego Warhammera
PROFILE = ('M', 'WS', 'BS', 'S', 'T', 'W', 'I', 'A', 'Ld')
# s_side[0] & 0x3F -> typ oddzialu; rozkodowane z komentarzy ';S_RACE is ...' (etykieta dominujaca)
RACE_TYPES = {
    0: 'Monster', 1: 'Human Infantry', 2: 'Human Cavalry', 3: 'Human Archers', 4: 'Dwarven Infantry',
    5: 'Dwarven Archers', 6: 'Elven', 7: 'Skaven', 8: 'Orc Infantry', 9: 'Orc Cavalry', 10: 'Orc Archers',
    11: 'Goblinoid', 12: 'Goblinoid Cavalry', 13: 'Goblinoid Archers', 14: 'Peasant',
    15: 'Human Artillery', 16: 'Human Artillery', 17: 'Human Artillery', 18: 'Orc Artillery', 19: 'Human Wizard',
}


def side_info(s_side):
    """Rozklada setstats:s_side = [typ, liczebnosc, liczebnosc poczatkowa, ?].

    typ: bit 7 = strona wroga, bit 6 = NPC/neutralny (hipoteza), bity 0-5 = typ oddzialu.
    """
    if not s_side:
        return None
    code = s_side[0]
    return {
        'code': code, 'enemy': bool(code & 0x80), 'npc': bool(code & 0x40),
        'type': RACE_TYPES.get(code & 0x3F, f'typ {code & 0x3F}'),
        'size': s_side[1] if len(s_side) > 1 else None,
        'orgsize': s_side[2] if len(s_side) > 2 else None,
        'extra': s_side[3] if len(s_side) > 3 else None,
    }


# komentarze generowane przez edytor, nie nadajace sie na etykiete sekcji
AUTO_COMMENT = re.compile(r';\s*(unit|piece|collision object|script node)\s*\d+', re.I)


class ParseError(Exception):
    pass


def _node(kind, name, line):
    return {'kind': kind, 'name': name, 'line': line, 'label': None,
            'set': {}, 'stats': {}, 'cmds': [], 'children': []}


def parse(path):
    """Zwraca korzen drzewa (sekcja najwyzszego poziomu, np. BATTLESCRIPT albo MERCARMY).

    Wezel: kind ('section' albo nazwa bloku, np. 'addunit'), name, line,
    label (pierwszy komentarz sekcji, np. 'Enemy Army'), set {klucz: tekst},
    stats {klucz: [int]}, cmds [(polecenie, argument)], children [wezly].
    """
    text = open(path, 'rb').read().decode('latin-1')
    root, stack = None, []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        where = f"{os.path.basename(path)}:{no}"
        if line.startswith(';'):
            cur = stack[-1] if stack else None
            if (cur and cur['kind'] == 'section' and cur['label'] is None
                    and not cur['children'] and not AUTO_COMMENT.match(line)):
                cur['label'] = line[1:].strip()
            continue
        if line.startswith('['):
            m = re.match(r'\[(\w+)\]', line)
            if not m:
                raise ParseError(f"{where}: zly naglowek sekcji: {line!r}")
            if m.group(1).upper() == 'END':
                if not stack or stack[-1]['kind'] != 'section':
                    raise ParseError(f"{where}: [END] bez otwartej sekcji (albo w bloku)")
                stack.pop()
                continue
            sec = _node('section', m.group(1).upper(), no)
            if stack:
                stack[-1]['children'].append(sec)
            elif root is None:
                root = sec
            else:
                raise ParseError(f"{where}: druga sekcja najwyzszego poziomu")
            stack.append(sec)
            continue
        if ':' not in line:
            raise ParseError(f"{where}: linia bez ':': {line!r}")
        if not stack:
            raise ParseError(f"{where}: polecenie poza sekcja")
        key, _, value = line.partition(':')
        lk, cur = key.lower(), stack[-1]
        if lk in BLOCKS:
            blk = _node(lk, value, no)
            cur['children'].append(blk)
            stack.append(blk)
        elif lk in CLOSERS:
            if cur['kind'] != CLOSERS[lk]:
                raise ParseError(f"{where}: {key} zamyka {cur['kind']!r}")
            stack.pop()
        elif lk == 'set':
            k, _, v = value.partition('=')
            cur['set'][k] = v
        elif lk == 'setstats':
            k, _, v = value.partition('=')
            cur['stats'][k] = _nums(v)
        else:
            cur['cmds'].append((key, value))
    if stack:
        raise ParseError(f"{os.path.basename(path)}: niezamkniete: {[n['kind'] + ':' + n['name'] for n in stack]}")
    if root is None:
        raise ParseError(f"{os.path.basename(path)}: pusty plik")
    return root


# ---------------------------------------------------------------- pomocnicze

def _num(s):
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


def _nums(s):
    return [_num(x) for x in s.split(',')] if s.strip() else []


def _cmd(node, key, default=None):
    return next((v for k, v in node['cmds'] if k.lower() == key.lower()), default)


def _cmds(node, key):
    return [v for k, v in node['cmds'] if k.lower() == key.lower()]


def _has(node, key):
    return any(k.lower() == key.lower() for k, _ in node['cmds'])


def _sets(node):
    return {k: _num(v) for k, v in node['set'].items()}


def _flags(v):
    return [f for f in str(v).split('|') if f] if v not in (None, '') else []


def _sections(node, name):
    return [c for c in node['children'] if c['kind'] == 'section' and c['name'] == name]


def _section(node, name):
    found = _sections(node, name)
    return found[0] if found else None


def display_name(s):
    """Nazwy w skryptach zamiast spacji maja '<' albo '_' (Grudgebringer<Cavalry)."""
    return s.replace('<', ' ').replace('_', ' ')


def find_ci(directory, name):
    """Szuka pliku bez rozrozniania wielkosci liter (skrypty pisane pod Windows)."""
    name = name.replace('\\', '/').lstrip('/')
    want = os.path.join(directory, name).lower()
    for f in os.listdir(os.path.dirname(want) if os.path.isdir(os.path.dirname(want)) else directory):
        if os.path.join(directory, f).lower() == want:
            return os.path.join(directory, f)
    return None


# ---------------------------------------------------------------- widok typowany

def unit_view(n):
    leader = next((c for c in n['children'] if c['kind'] == 'addleader'), None)
    u = {
        'id': n['name'], 'name': display_name(n['name']),
        'hidden': _has(n, 'hidden'),
        'sprites': _cmd(n, 'troopsprites'), 'banner': _cmd(n, 'banner'),
        'set': _sets(n), 'stats': n['stats'],
        'spells': _cmds(n, 'addspell'), 'items': _cmds(n, 'addmagicitem'),
        'leader': None,
    }
    if 's_move' in n['stats']:
        u['profile'] = dict(zip(PROFILE, n['stats']['s_move']))
    if leader:
        u['leader'] = {
            'id': leader['name'], 'name': display_name(leader['name']),
            'portrait': _cmd(leader, 'leaderportrait'), 'sprites': _cmd(leader, 'troopsprites'),
            'stats': leader['stats'],
            'profile': dict(zip(PROFILE, leader['stats'].get('s_move', []))),
        }
    return u


def army_view(sec):
    return {'label': sec['label'], 'count': _num(sec['set'].get('count', '0')),
            'units': [unit_view(c) for c in sec['children'] if c['kind'] == 'addunit']}


def mission_view(sec):
    if sec is None:
        return None
    return {'deploy_troops': _has(sec, 'DeployTroops'),
            'objectives': [_nums(v) for v in _cmds(sec, 'Objective')]}


def load_army(path):
    root = parse(path)
    return {'file': os.path.basename(path), 'type': root['name'],
            'mission': mission_view(_section(root, 'MISSIONINFO')),
            'armies': [army_view(s) for s in _sections(root, 'UNITS')]}


def load_battle(path, with_merc=True):
    root = parse(path)
    field = _section(root, 'FIELD')
    fs = _sets(field)
    f = {
        'width': fs.get('x'), 'height': fs.get('y'), 'map': fs.get('map'),
        'merc': _cmd(field, 'loadmerc'), 'mesh': _cmd(field, 'loadmesh'),
        'palette': _cmd(field, 'loadpal'), 'script': _cmd(field, 'loadScript'),
        'planmap': _cmd(field, 'loadplanmap'), 'portrait_bg': _cmd(field, 'loadportbg'),
        'ambient_light': _nums(_cmd(field, 'Ambient light color', '')),
        'position': _nums(_cmd(field, 'Position', '')),
        'bank_angle': _nums(_cmd(field, 'Bank angle', '')),
        'camera': _num(_cmd(field, 'Camera', '')) if _has(field, 'Camera') else None,
        'view': {k: fs[k] for k in ('vx', 'vy', 'zoom') if k in fs},
    }
    dyn = _section(root, 'DYNAMIC_LOAD')
    load = {}
    for k, v in (dyn['cmds'] if dyn else []):
        load.setdefault(k.lower(), []).append(v)
    if dyn and _has(dyn, 'NoBirds'):
        load['nobirds'] = True

    objects = []
    for o in (_section(root, 'OBJECTS') or {'children': []})['children']:
        s = _sets(o)
        rects = [_nums(v) for c in o['children'] if c['kind'] == 'addrectangles' for v in _cmds(c, 'rect')]
        objects.append({**{k: s.get(k) for k in ('x', 'y', 'z', 'radius', 'dir')},
                        'status': _flags(s.get('status')), 'rects': rects})

    scen = _section(root, 'SCENERY')
    scenery = []
    for v in _cmds(scen, 'placefurniture') if scen else []:
        name, *xyd = v.split(',')
        x, y, d = (_num(t) for t in xyd)
        scenery.append({'name': name, 'x': x, 'y': y, 'dir': d})

    bnd = _section(root, 'BOUNDARIES')
    boundaries = [{'name': b['name'], 'lines': [_nums(v) for v in _cmds(b, 'AddLine')]}
                  for b in (bnd['children'] if bnd else []) if b['kind'] == 'addboundary']

    nodes = []
    for n in (_section(root, 'NODES') or {'children': []})['children']:
        s = _sets(n)
        nodes.append({**{k: s.get(k) for k in ('x', 'y', 'radius', 'dir', 'id')},
                      'status': _flags(s.get('status'))})

    battle = {
        'file': os.path.basename(path), 'field': f,
        'mission': mission_view(_section(root, 'MISSIONINFO')),
        'load': load, 'objects': objects, 'scenery': scenery,
        'boundaries': boundaries, 'armies': [army_view(s) for s in _sections(root, 'UNITS')],
        'nodes': nodes, 'merc': None,
    }
    if with_merc and f['merc']:
        p = find_ci(os.path.dirname(path) or '.', f['merc'])
        battle['merc'] = load_army(p) if p else {'missing': f['merc']}
    return battle


# ---------------------------------------------------------------- walidacja

def check(root):
    """Zwraca liste niezgodnosci licznikow zapisanych w pliku z faktyczna zawartoscia."""
    issues = []

    def expect(sec, what, actual):
        if 'count' in sec['set'] and _num(sec['set']['count']) != actual:
            issues.append(f"[{sec['name']}] l.{sec['line']}: count={sec['set']['count']}, jest {actual} {what}")

    def walk(sec):
        blocks = lambda kind: sum(1 for c in sec['children'] if c['kind'] == kind)
        # [OBJECTS] set:count celowo pomijany: nigdy nie rowna sie liczbie addobject
        # (w 25/54 plikow = obiekty + jednostki, w reszcie odchyla sie o -8..+9), patrz FORMATS.md
        if sec['name'] == 'NODES':
            expect(sec, 'addnode', blocks('addnode'))
        elif sec['name'] == 'UNITS':
            expect(sec, 'addunit', blocks('addunit'))
        elif sec['name'] == 'SCENERY':
            expect(sec, 'placefurniture', len(_cmds(sec, 'placefurniture')))
        elif sec['name'] == 'BOUNDARIES':
            expect(sec, 'AddBoundary', blocks('addboundary'))
            lines = sum(len(_cmds(c, 'AddLine')) for c in sec['children'] if c['kind'] == 'addboundary')
            if 'Lines' in sec['set'] and _num(sec['set']['Lines']) != lines:
                issues.append(f"[BOUNDARIES] l.{sec['line']}: Lines={sec['set']['Lines']}, jest {lines} AddLine")
        for c in sec['children']:
            if c['kind'] == 'section':
                walk(c)
    walk(root)
    return issues


def check_dir(directory):
    files = sorted(f for f in os.listdir(directory) if f.upper().endswith(('.BTS', '.MRC')))
    ok = 0
    for f in files:
        p = os.path.join(directory, f)
        try:
            issues = check(parse(p))
            (load_battle if f.upper().endswith('.BTS') else load_army)(p)
        except Exception as e:  # noqa: BLE001 - raport zbiorczy
            print(f"BLAD  {f}: {type(e).__name__}: {e}")
            continue
        if issues:
            print(f"UWAGA {f}: " + "; ".join(issues))
        else:
            ok += 1
    print(f"{ok}/{len(files)} plikow bez uwag")


def summary(path):
    if path.upper().endswith('.MRC'):
        a = load_army(path)
        print(f"{a['file']}: [{a['type']}]")
        armies = a['armies']
    else:
        b = load_battle(path)
        f = b['field']
        print(f"{b['file']}: pole {f['width']}x{f['height']}, mesh={f['mesh']}, skrypt DLL={f['script']}, "
              f"mapa={f['planmap']}, armia gracza={f['merc']}")
        if b['mission']:
            print(f"  cele: {b['mission']['objectives']}")
        print(f"  obiekty kolizji: {len(b['objects'])}, sceneria: {len(b['scenery'])}, "
              f"wezly: {len(b['nodes'])}, granice: {[x['name'] for x in b['boundaries']]}")
        armies = b['armies'] + ((b['merc'] or {}).get('armies') or [])
    for army in armies:
        print(f"  armia '{army['label']}': {len(army['units'])} jednostek")
        for u in army['units']:
            s = u['set']
            lead = f" (dowodca: {u['leader']['name']})" if u['leader'] else ''
            print(f"    - {u['name']:28s} sprite={u['sprites']!s:18s} pos=({s.get('x')},{s.get('y')}) "
                  f"dir={s.get('dir')} profil={u.get('profile')}{lead}")
    issues = check(parse(path))
    print("  liczniki: OK" if not issues else "  liczniki: " + "; ".join(issues))


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == '--check':
        check_dir(args[1])
    elif '--json' in args:
        p = next(a for a in args if a != '--json')
        view = load_army(p) if p.upper().endswith('.MRC') else load_battle(p)
        print(json.dumps(view, indent=1, ensure_ascii=False))
    else:
        summary(args[0])
