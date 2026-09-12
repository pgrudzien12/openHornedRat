"""Generates a folder with battle maps (PNG) and their descriptions (Markdown) for random campaign battles.

Usage: battle_atlas.py <SCRIPT dir> <output dir> [count=20] [seed=1995]

Campaign battles = BFxxx.BTS / BFxxx_N.BTS files (developer test files are skipped).
The output folder gets README.md (legend and index), plus <BATTLE>.png and <BATTLE>.md for each battle.
Unit numbers in the images match the "No." column in the descriptions.
"""
import collections, math, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_battle import BOUNDARY_KINDS, SIDE_STYLE, collect_units, render   # noqa: E402
from whscript import load_battle                                              # noqa: E402


def units_count(n):
    return f"{n} unit" if n == 1 else f"{n} units"


def end_nodes(battle):
    return [n for n in battle['nodes'] if 'ns_end' in [s.lower() for s in n['status']]]


def on_node(entry, nodes):
    """Whether the unit stands on one of the nodes (within the node radius, at least 8 world units)."""
    s = entry['unit']['set']
    x, y = s.get('x'), s.get('y')
    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
        return False
    return any(math.hypot(x - n['x'], y - n['y']) <= max(n['radius'] or 0, 8) for n in nodes)


def campaign_stats(script_dir):
    """Aggregate statistics over all campaign battles, for the legend in README."""
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

SIDE_NAME = {'enemy': 'enemy', 'npc': 'NPC', 'player': 'player'}
KIND_EMOJI = {'battle': '⬜', 'deploy': '🟩', 'nav': '🟨', 'camera': '🟪', 'view': '🟦', 'sight': '🩷', 'terrain': '🟧'}
SIDE_EMOJI = {'enemy': '🔴', 'npc': '🟠', 'player': '🔵'}
OUTSIDE = 'outside the battlefield boundary'


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
        notes.append('hidden at start (`hidden`)')
    x, y = s.get('x'), s.get('y')
    if bbox and isinstance(x, (int, float)) and isinstance(y, (int, float)):
        if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            notes.append(OUTSIDE)
    script = s.get('script')
    if script == 'PLAYER_SCRIPT':
        notes.append('controlled by the player')
    elif script not in (None, ''):
        notes.append(f'AI script no. {script}')
    if u['spells']:
        notes.append('spells: ' + ', '.join(u['spells']))
    if u['items']:
        notes.append('items: ' + ', '.join(u['items']))
    return '; '.join(notes)


def battle_md(name, info):
    b, f = info['battle'], info['battle']['field']
    units, bounds = info['units'], info['boundaries']
    bbox = battle_bbox(bounds)
    by_side = collections.Counter(e['side'] for e in units)
    types = lambda side: ', '.join(f"{t} ×{n}" for t, n in collections.Counter(
        (e['type'] or {}).get('type', '?') for e in units if e['side'] == side).most_common())

    L = [f"# {name}", "", f"![Battle map {name}]({name}.png)", "",
         "Color and symbol legend: [README.md](README.md). Numbers on the map = **No.** column in the unit table.", ""]

    L += ["## At a glance", ""]
    L.append(f"- **Enemy:** {units_count(by_side['enemy'])} ({types('enemy') or 'none'})")
    if by_side['npc']:
        L.append(f"- **NPC:** {units_count(by_side['npc'])} ({types('npc')})")
    merc_name = os.path.splitext(os.path.basename((f['merc'] or '').replace('\\', '/')))[0].upper()
    other = (f" This is the army from another battle's file ({merc_name}), i.e. a campaign continuation; "
             "the x/y positions from that file may not fit this map.") if merc_name and merc_name != name else ''
    L.append(f"- **Player:** {units_count(by_side['player'])} from `{f['merc']}` ({types('player') or 'none'}).{other}")
    for side in ('player', 'enemy', 'npc'):
        hidden = [str(e['nr']) for e in units if e['side'] == side and e['unit']['hidden']]
        if hidden:
            L.append(f"- **Hidden at start ({SIDE_NAME[side]}):** {len(hidden)} of {by_side[side]}, no. {', '.join(hidden)}")
    ends = end_nodes(b)
    player = [e for e in units if e['side'] == 'player']
    on = sum(1 for e in player if on_node(e, ends))
    L.append(f"- **`NS_END` nodes vs. the player army:** `NS_END` nodes: {len(ends)}, player units: {len(player)} "
             f"({'match' if len(ends) == len(player) else 'no match'}); "
             f"{on} of {len(player)} player units stand on `NS_END` nodes")
    outside = [str(e['nr']) for e in units if OUTSIDE in unit_notes(e, bbox)]
    if outside:
        L.append(f"- **Outside the battlefield boundary:** no. {', '.join(outside)} "
                 "(hypothesis: reinforcements or units entering later)")
    deploy = [bd['name'] for bd in bounds if bd['kind'] == 'deploy']
    L.append(f"- **Deployment zone:** {', '.join(deploy) if deploy else 'none'}; "
             f"`DeployTroops`: {'yes' if b['mission'] and b['mission']['deploy_troops'] else 'no'}")
    L.append(f"- **Plan map in the background:** {'yes' if info['has_map'] else 'not found'}")
    L.append("")

    L += ["## Battlefield (`[FIELD]`)", "", "| Field | Value | Meaning |", "|---|---|---|",
          f"| size | {f['width']} × {f['height']} | world units; the Y axis grows up the map |",
          f"| plan map | `{cell(f['planmap'])}` | image background |",
          f"| 3D terrain | `MESH/{cell(f['mesh'])}/` | terrain mesh and packed textures (unexplored) |",
          f"| palette | `{cell(f['palette'])}` | battle RGB palette |",
          f"| mission script | `SCRIPT/{cell(f['script'])}.DLL` | mission logic (x86 code) |",
          f"| player army | `{cell(f['merc'])}` | .MRC file |",
          f"| portrait background | `{cell(f['portrait_bg'])}` | |",
          f"| camera | {cell(f['camera'])} | presumably the initial camera rotation |",
          f"| set:map | {cell(f['map'])} | meaning unknown |", ""]

    L += ["## Mission objectives (`Objective`)", ""]
    if b['mission'] and b['mission']['objectives']:
        L.append("Raw `letter, a, b` values, **meaning unknown**: " +
                 ", ".join(f"`{','.join(map(str, o))}`" for o in b['mission']['objectives']))
    else:
        L.append("None.")
    L.append("")

    L += ["## Units", "",
          "| No. | Side | Name | Type (`s_side` code) | Strength | Sprite / banner | Leader | Profile M WS BS S T W I A Ld | Psychology | Position (x, y) / dir | Notes |",
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

    L += ["## Boundaries (`[BOUNDARIES]`)", "", "| Name | Color | Meaning | Segments |", "|---|---|---|---|"]
    for bd in bounds:
        L.append(f"| {cell(bd['name'])} | {KIND_EMOJI[bd['kind']]} {bd['color_name']} | {bd['meaning']} | {bd['segments']} |")
    L.append("")

    objs = b['objects']
    solid = sum(1 for o in objs if 'os_solid' in [x.lower() for x in o['status']])
    rects = sum(1 for o in objs if o['rects'])
    L += ["## Collision objects (`[OBJECTS]`)", "",
          f"Collision objects: **{len(objs)}**. Blocking (`os_solid`, red circles): {solid}; "
          f"non-blocking (light pink): {len(objs) - solid}; with a more precise shape "
          f"(`addrectangles`, light orange rectangles): {rects}. "
          "The circles cover the trees, rocks and buildings of the plan map.", ""]

    scen = collections.Counter(s['name'] for s in b['scenery'])
    L += ["## Scenery (`[SCENERY]`)", "",
          f"Scenery elements (green dots): **{len(b['scenery'])}**. " +
          (', '.join(f"`{k}` ×{v}" for k, v in scen.most_common()) or 'None.'), ""]

    nodes = b['nodes']
    flags = collections.Counter(fl.lower() for n in nodes for fl in n['status'])
    ids = sorted({n['id'] for n in nodes if n['id'] is not None})
    L += ["## Script nodes (`[NODES]`)", "",
          f"Nodes (cyan): **{len(nodes)}**. With `ns_startpos` (filled squares): {flags['ns_startpos']}; "
          f"with `NS_END` (white outline, usually also `ns_startpos`): {flags['ns_end']}. "
          f"`id` values: {', '.join(map(str, ids)) or '—'}.", "",
          f"Player units: {len(player)}, of which {on} stand on `NS_END` nodes. Hypothesis (see README): each "
          "`NS_END` node is the target position of one player unit, and the remaining `ns_startpos` nodes mark "
          "the route or the entry points of the army onto the field.", ""]

    L += ["## Dynamically loaded resources (`[DYNAMIC_LOAD]`)", ""]
    for k, v in b['load'].items():
        if isinstance(v, list):
            L.append(f"- `{k}`: " + ', '.join(f"`{x}`" for x in v))
        else:
            L.append(f"- `{k}`")
    L.append("")
    return '\n'.join(L)


README_LEGEND = """\
# Battle atlas — Warhammer: Shadow of the Horned Rat

Generated by `scripts/battle_atlas.py` from the `.BTS` and `.MRC` files of a legally owned
game installation. **Do not distribute**: the backgrounds are plan maps extracted from the game files.

{selection}

## How to read the maps

Each image is a top-down view of the whole battlefield. The background is the battle's dimmed **plan map**
(`loadplanmap`, e.g. `MAP001`), stretched to the field size from `[FIELD]`. The world Y axis grows
up the image; verified by the collision circles lying on the trees and rocks of the map.
Everything except the background is drawn from the `.BTS` script data (and the player army from `.MRC`).
The image area is larger than the field, because some boundaries and units extend beyond it.

### Boundaries (`[BOUNDARIES]`): lines

| Color | Names in the files | Meaning | Certainty |
|---|---|---|---|
{boundaries}

Certainty: **certain** = follows directly from the data and the image; **probable** = the name and the image agree;
**hypothesis** = mostly from the name, not verified in the game.

### Units (`[UNITS]` in .BTS and the army from .MRC): discs

| Symbol | Meaning |
|---|---|
{sides}
| filled disc | unit visible at start |
| ring only | unit with the `hidden:` flag. {hidden_player} of {player_units} player units across all {battles} campaign battles have it, so for the player it most likely means "not on the field yet" (the army enters or is deployed). For the enemy presumably reinforcements or an ambush. Hypothesis |
| line from the disc | `dir` direction; hypothesis: full turn = 512, 0 = up the map, clockwise |
| number | unit number = **No.** column in the battle description |

### Other symbols

| Symbol | From the data | Meaning | Certainty |
|---|---|---|---|
| 🔴 red circle | `addobject` with `os_solid` | obstacle blocking movement (trees, rocks, buildings) | certain |
| light pink circle | `addobject` without `os_solid` | active but non-blocking object | hypothesis |
| light orange rectangle | `addrectangles` / `rect` in an object | more precise collision shape, rotated by the object's `dir` | probable (rotation: hypothesis) |
| 🟢 small green dot | `placefurniture` in `[SCENERY]` | scenery element (tree, rock, building); types from `loadfurn` | certain |
| filled cyan square | `addnode` with `ns_startpos` | node of the player army's entry or deployment route; usually a few more of them than player units | probable |
| cyan square with a white outline | `addnode` with `NS_END` (usually together with `ns_startpos`) | **target position of one player unit**. In {ends_eq}/{battles} campaign battles the number of `NS_END` nodes = the number of player units; in {on_ends}/{battles} all player units from `.MRC` stand exactly on these nodes | probable |
| hollow cyan square | `addnode` without these flags | other mission script node | certain that it is a node; role unknown |

## Battles

| Battle | Field | Plan map | Enemy | NPC | Player | Player army | Boundaries |
|---|---|---|---|---|---|---|---|
{index}
"""

CERTAINTY = {'battle': 'certain', 'deploy': 'probable', 'nav': 'probable', 'camera': 'hypothesis',
             'view': 'hypothesis', 'sight': 'hypothesis', 'terrain': 'probable'}
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
        print(f"{name}: {info['size'][0]}x{info['size'][1]} px, units {len(info['units'])}, map: {info['has_map']}")

    selection = (f"**{len(chosen)}** of {len(battles)} campaign battles (`BFxxx.BTS`) chosen at random, "
                 f"seed `{seed}`:\n`python3 scripts/battle_atlas.py <SCRIPT> {out_dir} {count} {seed}`")
    boundaries = '\n'.join(f"| {KIND_EMOJI[k]} {cname} | {KIND_NAMES[k]} | {meaning} | {CERTAINTY[k]} |"
                           for k, _, cname, meaning in BOUNDARY_KINDS)
    sides = '\n'.join(f"| {SIDE_EMOJI[k]} {v[1]} | {v[2]} |" for k, v in SIDE_STYLE.items())
    st = campaign_stats(script_dir)
    with open(os.path.join(out_dir, 'README.md'), 'w', encoding='utf-8') as fh:
        fh.write(README_LEGEND.format(selection=selection, boundaries=boundaries, sides=sides, index='\n'.join(rows),
                                      **{k: st[k] for k in ('battles', 'ends_eq', 'on_ends', 'player_units', 'hidden_player')}))
    print(f"campaign statistics: {dict(st)}")


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        sys.exit(1)
    main(a[0], a[1], int(a[2]) if len(a) > 2 else 20, int(a[3]) if len(a) > 3 else 1995)
