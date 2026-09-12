"""Generuje folder z mapami bitew (PNG) i ich opisami (Markdown) dla losowych bitew kampanii.

Uzycie: battle_atlas.py <katalog SCRIPT> <folder wyjsciowy> [liczba=20] [ziarno=1995]

Bitwy kampanii = pliki BFxxx.BTS / BFxxx_N.BTS (pomija pliki testowe tworcow).
W folderze powstaja: README.md (legenda i spis), <BITWA>.png i <BITWA>.md dla kazdej bitwy.
Numery jednostek na obrazkach odpowiadaja kolumnie "Nr" w opisach.
"""
import collections, math, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_battle import BOUNDARY_KINDS, SIDE_STYLE, collect_units, render   # noqa: E402
from whscript import load_battle                                              # noqa: E402


def plural(n, one, few, many):
    """Polska liczba mnoga: 1 oddzial, 2-4 oddzialy, 5+ oddzialow (12-14 tez 'many')."""
    if n == 1:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def oddzialy(n):
    return plural(n, 'oddział', 'oddziały', 'oddziałów')


def end_nodes(battle):
    return [n for n in battle['nodes'] if 'ns_end' in [s.lower() for s in n['status']]]


def on_node(entry, nodes):
    """Czy jednostka stoi na ktoryms z wezlow (w promieniu wezla, min. 8 jednostek swiata)."""
    s = entry['unit']['set']
    x, y = s.get('x'), s.get('y')
    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
        return False
    return any(math.hypot(x - n['x'], y - n['y']) <= max(n['radius'] or 0, 8) for n in nodes)


def campaign_stats(script_dir):
    """Zbiorcze statystyki po wszystkich bitwach kampanii, do legendy w README."""
    st = collections.Counter()
    for fname in campaign_battles(script_dir):
        b = load_battle(os.path.join(script_dir, fname))
        player = [e for e in collect_units(b) if e['side'] == 'player']
        ends = end_nodes(b)
        st['battles'] += 1
        st['ends_eq'] += len(ends) == len(player)
        st['on_ends'] += bool(player) and all(on_node(e, ends) for e in player)
        st['player_units'] += len(player)
        st['hidden_player'] += sum(1 for e in player if e['unit']['hidden'])
    return st

SIDE_NAME = {'enemy': 'wróg', 'npc': 'NPC', 'player': 'gracz'}
KIND_EMOJI = {'battle': '⬜', 'deploy': '🟩', 'nav': '🟨', 'camera': '🟪', 'view': '🟦', 'sight': '🩷', 'terrain': '🟧'}
SIDE_EMOJI = {'enemy': '🔴', 'npc': '🟠', 'player': '🔵'}


def campaign_battles(script_dir):
    return sorted(f for f in os.listdir(script_dir) if re.fullmatch(r'BF\d{3}(_\d)?\.BTS', f, re.I))


def cell(v):
    return '—' if v in (None, '', []) else str(v).replace('|', '\\|')


def battle_bbox(boundaries):
    pts = [(x, y) for bd in boundaries if bd['kind'] == 'battle'
           for x1, y1, x2, y2 in bd['lines'] for x, y in ((x1, y1), (x2, y2))]
    if not pts:
        return None
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def unit_notes(entry, bbox):
    u, s, notes = entry['unit'], entry['unit']['set'], []
    if u['hidden']:
        notes.append('ukryta na starcie (`hidden`)')
    x, y = s.get('x'), s.get('y')
    if bbox and isinstance(x, (int, float)) and isinstance(y, (int, float)):
        if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            notes.append('poza granicą pola')
    script = s.get('script')
    if script == 'PLAYER_SCRIPT':
        notes.append('steruje gracz')
    elif script not in (None, ''):
        notes.append(f'skrypt AI nr {script}')
    if u['spells']:
        notes.append('zaklęcia: ' + ', '.join(u['spells']))
    if u['items']:
        notes.append('przedmioty: ' + ', '.join(u['items']))
    return '; '.join(notes)


def battle_md(name, info):
    b, f = info['battle'], info['battle']['field']
    units, bounds = info['units'], info['boundaries']
    bbox = battle_bbox(bounds)
    by_side = collections.Counter(e['side'] for e in units)
    types = lambda side: ', '.join(f"{t} ×{n}" for t, n in collections.Counter(
        (e['type'] or {}).get('type', '?') for e in units if e['side'] == side).most_common())

    L = [f"# {name}", "", f"![Mapa bitwy {name}]({name}.png)", "",
         "Legenda kolorów i symboli: [README.md](README.md). Numery na mapie = kolumna **Nr** w tabeli jednostek.", ""]

    L += ["## W skrócie", ""]
    L.append(f"- **Wróg:** {oddzialy(by_side['enemy'])} ({types('enemy') or 'brak'})")
    if by_side['npc']:
        L.append(f"- **NPC:** {oddzialy(by_side['npc'])} ({types('npc')})")
    merc_name = os.path.splitext(os.path.basename((f['merc'] or '').replace('\\', '/')))[0].upper()
    other = (f" To armia z pliku innej bitwy ({merc_name}), czyli kontynuacja kampanii; pozycje x/y z tego pliku "
             "mogą nie pasować do tej mapy.") if merc_name and merc_name != name else ''
    L.append(f"- **Gracz:** {oddzialy(by_side['player'])} z pliku `{f['merc']}` ({types('player') or 'brak'}).{other}")
    for side in ('player', 'enemy', 'npc'):
        hidden = [str(e['nr']) for e in units if e['side'] == side and e['unit']['hidden']]
        if hidden:
            L.append(f"- **Ukryte na starcie ({SIDE_NAME[side]}):** {len(hidden)} z {by_side[side]}, nr {', '.join(hidden)}")
    ends = end_nodes(b)
    player = [e for e in units if e['side'] == 'player']
    on = sum(1 for e in player if on_node(e, ends))
    L.append(f"- **Węzły `NS_END` a armia gracza:** węzłów `NS_END`: {len(ends)}, oddziałów gracza: {len(player)} "
             f"({'zgadza się' if len(ends) == len(player) else 'nie zgadza się'}); na węzłach `NS_END` stoi "
             f"{on} z {len(player)} oddziałów gracza")
    outside = [str(e['nr']) for e in units if 'poza granicą' in unit_notes(e, bbox)]
    if outside:
        L.append(f"- **Poza granicą pola:** nr {', '.join(outside)} (hipoteza: posiłki albo jednostki wchodzące później)")
    deploy = [bd['name'] for bd in bounds if bd['kind'] == 'deploy']
    L.append(f"- **Strefa rozstawienia:** {', '.join(deploy) if deploy else 'brak'}; "
             f"`DeployTroops`: {'tak' if b['mission'] and b['mission']['deploy_troops'] else 'nie'}")
    L.append(f"- **Mapa planu w tle:** {'tak' if info['has_map'] else 'nie znaleziono'}")
    L.append("")

    L += ["## Pole bitwy (`[FIELD]`)", "", "| Pole | Wartość | Znaczenie |", "|---|---|---|",
          f"| rozmiar | {f['width']} × {f['height']} | jednostki świata; oś Y rośnie w górę mapy |",
          f"| mapa planu | `{cell(f['planmap'])}` | tło obrazka |",
          f"| teren 3D | `MESH/{cell(f['mesh'])}/` | siatka terenu i spakowane tekstury (niezbadane) |",
          f"| paleta | `{cell(f['palette'])}` | paleta RGB bitwy |",
          f"| skrypt misji | `SCRIPT/{cell(f['script'])}.DLL` | logika misji (kod x86) |",
          f"| armia gracza | `{cell(f['merc'])}` | plik .MRC |",
          f"| tło portretów | `{cell(f['portrait_bg'])}` | |",
          f"| kamera | {cell(f['camera'])} | zapewne początkowy obrót kamery |",
          f"| set:map | {cell(f['map'])} | znaczenie nieznane |", ""]

    L += ["## Cele misji (`Objective`)", ""]
    if b['mission'] and b['mission']['objectives']:
        L.append("Surowe wartości `litera, a, b`, **znaczenie nieznane**: " +
                 ", ".join(f"`{','.join(map(str, o))}`" for o in b['mission']['objectives']))
    else:
        L.append("Brak.")
    L.append("")

    L += ["## Jednostki", "",
          "| Nr | Strona | Nazwa | Typ (kod `s_side`) | Liczebność | Sprite / sztandar | Dowódca | Profil M WS BS S T W I A Ld | Psychologia | Pozycja (x, y) / dir | Uwagi |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in units:
        u, s, t = e['unit'], e['unit']['set'], e['type'] or {}
        leader = f"{u['leader']['name']} ({u['leader']['portrait']})" if u['leader'] else None
        size = f"{t.get('size')}/{t.get('orgsize')}" if t else None
        L.append("| " + " | ".join(cell(v) for v in (
            e['nr'], f"{SIDE_EMOJI[e['side']]} {SIDE_NAME[e['side']]}", u['name'],
            f"{t.get('type')} ({t.get('code')})" if t else None, size,
            f"{u['sprites']} / {u['banner']}", leader,
            ' '.join(map(str, u['stats'].get('s_move', []))), s.get('psy_status'),
            f"({s.get('x')}, {s.get('y')}) / {s.get('dir')}", unit_notes(e, bbox))) + " |")
    L.append("")

    L += ["## Granice (`[BOUNDARIES]`)", "", "| Nazwa | Kolor | Znaczenie | Odcinków |", "|---|---|---|---|"]
    for bd in bounds:
        L.append(f"| {cell(bd['name'])} | {KIND_EMOJI[bd['kind']]} {bd['color_name']} | {bd['meaning']} | {bd['segments']} |")
    L.append("")

    objs = b['objects']
    solid = sum(1 for o in objs if 'os_solid' in [x.lower() for x in o['status']])
    rects = sum(1 for o in objs if o['rects'])
    L += ["## Obiekty kolizji (`[OBJECTS]`)", "",
          f"Obiekty kolizji: **{len(objs)}**. Blokujące (`os_solid`, czerwone okręgi): {solid}; "
          f"nieblokujące (jasnoróżowe): {len(objs) - solid}; z dokładniejszym kształtem "
          f"(`addrectangles`, jasnopomarańczowe prostokąty): {rects}. "
          "Okręgi pokrywają drzewa, skały i budynki z mapy planu.", ""]

    scen = collections.Counter(s['name'] for s in b['scenery'])
    L += ["## Sceneria (`[SCENERY]`)", "",
          f"Elementy scenerii (zielone kropki): **{len(b['scenery'])}**. " +
          (', '.join(f"`{k}` ×{v}" for k, v in scen.most_common()) or 'Brak.'), ""]

    nodes = b['nodes']
    flags = collections.Counter(fl.lower() for n in nodes for fl in n['status'])
    ids = sorted({n['id'] for n in nodes if n['id'] is not None})
    L += ["## Węzły skryptu (`[NODES]`)", "",
          f"Węzły (cyjan): **{len(nodes)}**. Z `ns_startpos` (pełne kwadraty): {flags['ns_startpos']}; "
          f"z `NS_END` (biała obwódka, zwykle mają też `ns_startpos`): {flags['ns_end']}. "
          f"Identyfikatory `id`: {', '.join(map(str, ids)) or '—'}.", "",
          f"Oddziałów gracza: {len(player)}, na węzłach `NS_END` stoi z nich {on}. Hipoteza (patrz README): każdy "
          "węzeł `NS_END` to docelowa pozycja jednego oddziału gracza, a pozostałe `ns_startpos` wyznaczają "
          "trasę albo punkty wejścia armii na pole.", ""]

    L += ["## Dynamicznie wczytywane zasoby (`[DYNAMIC_LOAD]`)", ""]
    for k, v in b['load'].items():
        if isinstance(v, list):
            L.append(f"- `{k}`: " + ', '.join(f"`{x}`" for x in v))
        else:
            L.append(f"- `{k}`")
    L.append("")
    return '\n'.join(L)


README_LEGEND = """\
# Atlas bitew — Warhammer: Shadow of the Horned Rat

Wygenerowane przez `scripts/battle_atlas.py` z plików `.BTS` i `.MRC` legalnie posiadanej
instalacji gry. **Nie dystrybuować**: tło to mapy planu wyciągnięte z plików gry.

{selection}

## Jak czytać mapy

Obrazek to widok z góry na całe pole bitwy. Tłem jest przyciemniona **mapa planu** bitwy
(`loadplanmap`, np. `MAP001`), rozciągnięta na rozmiar pola z `[FIELD]`. Oś Y świata rośnie
w górę obrazka; zweryfikowane tym, że okręgi kolizji leżą na drzewach i skałach z mapy.
Wszystko poza tłem jest narysowane z danych skryptu `.BTS` (i armii gracza z `.MRC`).
Obszar obrazka jest większy od pola, bo niektóre granice i jednostki wychodzą poza nie.

### Granice (`[BOUNDARIES]`): linie

| Kolor | Nazwy w plikach | Znaczenie | Pewność |
|---|---|---|---|
{boundaries}

Pewność: **pewne** = wynika wprost z danych i obrazu; **prawdopodobne** = nazwa i obraz się zgadzają;
**hipoteza** = głównie z nazwy, niezweryfikowane w grze.

### Jednostki (`[UNITS]` w .BTS i armia z .MRC): koła

| Symbol | Znaczenie |
|---|---|
{sides}
| koło pełne | jednostka widoczna na starcie |
| sam pierścień | jednostka z flagą `hidden:`. Ma ją {hidden_player} z {player_units} oddziałów gracza we wszystkich {battles} bitwach kampanii, więc u gracza to raczej „jeszcze nie na polu” (armia wchodzi albo jest rozstawiana). U wroga zapewne posiłki albo zasadzka. Hipoteza |
| kreska z koła | kierunek `dir`; hipoteza: pełny obrót = 512, 0 = w górę mapy, zgodnie z zegarem |
| liczba | numer jednostki = kolumna **Nr** w opisie bitwy |

### Pozostałe symbole

| Symbol | Z danych | Znaczenie | Pewność |
|---|---|---|---|
| 🔴 czerwony okrąg | `addobject` z `os_solid` | przeszkoda blokująca ruch (drzewa, skały, budynki) | pewne |
| jasnoróżowy okrąg | `addobject` bez `os_solid` | obiekt aktywny, ale nieblokujący | hipoteza |
| jasnopomarańczowy prostokąt | `addrectangles` / `rect` w obiekcie | dokładniejszy kształt kolizji, obrócony o `dir` obiektu | prawdopodobne (obrót: hipoteza) |
| 🟢 mała zielona kropka | `placefurniture` w `[SCENERY]` | element scenerii (drzewo, skała, budynek); typy z `loadfurn` | pewne |
| cyjan kwadrat pełny | `addnode` z `ns_startpos` | węzeł trasy wejścia albo rozstawienia armii gracza; zwykle jest ich kilka więcej niż oddziałów gracza | prawdopodobne |
| cyjan kwadrat z białą obwódką | `addnode` z `NS_END` (zwykle razem z `ns_startpos`) | **docelowa pozycja jednego oddziału gracza**. W {ends_eq}/{battles} bitwach kampanii liczba `NS_END` = liczba oddziałów gracza; w {on_ends}/{battles} wszystkie oddziały gracza z `.MRC` stoją dokładnie na tych węzłach | prawdopodobne |
| cyjan kwadrat pusty | `addnode` bez tych flag | inny węzeł skryptu misji | pewne, że to węzeł; rola nieznana |

## Bitwy

| Bitwa | Pole | Mapa planu | Wróg | NPC | Gracz | Armia gracza | Granice |
|---|---|---|---|---|---|---|---|
{index}
"""

CERTAINTY = {'battle': 'pewne', 'deploy': 'prawdopodobne', 'nav': 'prawdopodobne', 'camera': 'hipoteza',
             'view': 'hipoteza', 'sight': 'hipoteza', 'terrain': 'prawdopodobne'}
KIND_NAMES = {'battle': '`BattleEdge`, `Battlefield edge`', 'deploy': '`DeploymentArea`, `Merc Deployment`',
              'nav': '`Nav1` … `NavN`', 'camera': '`CameraEdge`', 'view': '`ViewEdge`', 'sight': '`SightEdge`',
              'terrain': '`CliffsEdge`, `RiverEdge`, `WallsEdge`, `Hedge`, `LakeEdge`, `RockyRidge`…'}


def main(script_dir, out_dir, count=20, seed=1995):
    os.makedirs(out_dir, exist_ok=True)
    battles = campaign_battles(script_dir)
    chosen = sorted(random.Random(seed).sample(battles, min(count, len(battles))))
    rows = []
    for fname in chosen:
        name = os.path.splitext(fname)[0].upper()
        path = os.path.join(script_dir, fname)
        f = load_battle(path, with_merc=False)['field']
        scale = min(0.5, 1100 / max(f['width'] or 1, f['height'] or 1))
        info = render(path, os.path.join(out_dir, name + '.png'), scale)
        with open(os.path.join(out_dir, name + '.md'), 'w', encoding='utf-8') as fh:
            fh.write(battle_md(name, info))
        side = collections.Counter(e['side'] for e in info['units'])
        kinds = sorted({bd['kind'] for bd in info['boundaries']}, key=[k[0] for k in BOUNDARY_KINDS].index)
        rows.append(f"| [{name}]({name}.md) | {f['width']}×{f['height']} | `{f['planmap']}` | {side['enemy']} | "
                    f"{side['npc']} | {side['player']} | `{f['merc']}` | {' '.join(KIND_EMOJI[k] for k in kinds)} |")
        print(f"{name}: {info['size'][0]}x{info['size'][1]} px, jednostek {len(info['units'])}, mapa: {info['has_map']}")

    selection = (f"Wybrano losowo **{len(chosen)}** z {len(battles)} bitew kampanii (`BFxxx.BTS`), "
                 f"ziarno losowania `{seed}`:\n`python3 scripts/battle_atlas.py <SCRIPT> {out_dir} {count} {seed}`")
    boundaries = '\n'.join(f"| {KIND_EMOJI[k]} {cname} | {KIND_NAMES[k]} | {meaning} | {CERTAINTY[k]} |"
                           for k, _, cname, meaning in BOUNDARY_KINDS)
    sides = '\n'.join(f"| {SIDE_EMOJI[k]} {v[1]} | {v[2]} |" for k, v in SIDE_STYLE.items())
    st = campaign_stats(script_dir)
    with open(os.path.join(out_dir, 'README.md'), 'w', encoding='utf-8') as fh:
        fh.write(README_LEGEND.format(selection=selection, boundaries=boundaries, sides=sides, index='\n'.join(rows),
                                      **{k: st[k] for k in ('battles', 'ends_eq', 'on_ends', 'player_units', 'hidden_player')}))
    print(f"statystyki kampanii: {dict(st)}")


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        sys.exit(1)
    main(a[0], a[1], int(a[2]) if len(a) > 2 else 20, int(a[3]) if len(a) > 3 else 1995)
