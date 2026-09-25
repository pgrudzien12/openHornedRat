"""Links the PE text resources with the campaign "glue" scripts (WND.DLL) and the battle scripts (.BTS).

Usage:
  pe_missions.py <WARFB dir>                  campaign missions table + objectives of every .BTS
  pe_missions.py <WARFB dir> --json out.json  same data as JSON
  pe_missions.py <WARFB dir> --check          structural test of the Objective:L,a,b hypotheses on all .BTS

e.g.:  pe_missions.py ".../WARFB" --check

What is combined (see notes/pe_resources.md):
  - WND.DLL RT_RCDATA: text scripts in the glue language; [MISSION] blocks give
    set:res (mission name ID in BRTXT), res:<briefing script>, setbattlescript, setmissionscript, cash;
    mission scripts run battles with playgame*/encounterplaygame*/setbattlescript.
  - Objective:L,a,b -> letter index i = L - 'A':
      GMTXT 33000+i = objective caption, BKTXT 1001+i = failure line, BKTXT 2001+i = success line.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe_resources import PE  # noqa: E402
from pe_extract import string_block  # noqa: E402
import whscript  # noqa: E402

BATTLE_CMDS = ('playgame', 'playgamewithdebrief', 'encounterplaygame', 'encounterplaygamewithdebrief',
               'setbattlescript')


def load_strings(dll):
    pe, out = PE(dll), {}
    for r in pe.resources():
        if r.type == 6:
            out.update(string_block(pe.data(r), r.name))
    return out


def load_rcdata(dll):
    pe = PE(dll)
    return {str(r.name).upper(): pe.data(r).decode('latin-1') for r in pe.resources() if r.type == 10}


def glue_lines(text):
    """Non-comment lines of a glue script as (command, argument); section headers as ('[NAME]', '')."""
    for raw in text.splitlines():
        line = raw.split('//')[0].strip()
        if not line or line.startswith(';') or line[0] in '\x1a\x1b':
            continue
        if line.startswith('['):
            yield line.split(']')[0] + ']', ''
            continue
        key, _, val = line.partition(':')
        yield key.strip().lower(), val.split(';')[0].strip()


def mission_blocks(wnd):
    """All [MISSION] blocks: {window, name_id, brief, battle, mission_script, cash}."""
    out = []
    for name, text in sorted(wnd.items()):
        cur = None
        for cmd, arg in glue_lines(text):
            if cmd == '[MISSION]':
                cur = {'window': name}
            elif cmd == '[END]' and cur is not None:
                out.append(cur)
                cur = None
            elif cur is not None:
                if cmd == 'set' and arg.startswith('res='):
                    cur['name_id'] = int(arg[4:])
                elif cmd == 'res':
                    cur['brief'] = arg.upper()
                elif cmd == 'setbattlescript':
                    cur['battle'] = arg.upper()
                elif cmd == 'setmissionscript':
                    cur['mission_script'] = arg.upper()
                elif cmd == 'cash':
                    cur['cash'] = arg
    return out


def script_battles(text):
    """Battles started by a glue script: [(command, BFxxx, debrief_id or None)] + other interesting commands."""
    battles, extra = [], {'playmovie': [], 'setdebrief': [], 'testobjective': [], 'playtext': [], 'gosub': []}
    for cmd, arg in glue_lines(text):
        if cmd in BATTLE_CMDS:
            parts = arg.split(',')
            battles.append((cmd, parts[0].upper(), int(parts[1]) if len(parts) > 1 and parts[1].strip() else None))
        elif cmd in ('playtext', 'queuetoplaytext'):
            extra['playtext'].append(int(arg.split('=')[1]))
        elif cmd in ('gosub', 'iftruegosub', 'iffalsegosub', 'goto'):
            extra['gosub'].append(arg.upper())
        elif cmd in extra or cmd in ('iftrueplaymovie', 'iffalseplaymovie'):
            extra[cmd if cmd in extra else 'playmovie'].append(arg)
    return battles, extra


def army_counts(units, mask_test):
    sel = [u for u in units if u['stats'].get('s_side') and mask_test(u['stats']['s_side'][0])]
    return sum(u['stats']['s_side'][1] for u in sel), len(sel)


def battle_objectives(script_dir, gmtxt, bktxt):
    rows = []
    for f in sorted(os.listdir(script_dir)):
        if not f.upper().endswith('.BTS'):
            continue
        b = whscript.load_battle(os.path.join(script_dir, f))
        objs = (b['mission'] or {}).get('objectives') or []
        units = [u for a in b['armies'] for u in a['units']]
        merc = [u for a in ((b['merc'] or {}).get('armies') or []) for u in a['units']]
        row = {
            'battle': os.path.splitext(f)[0].upper(),
            'enemy': army_counts(units, lambda c: c & 0x80),          # (men, units)
            'npc': army_counts(units, lambda c: c & 0x40 and not c & 0x80),
            'player': army_counts(merc, lambda c: not c & 0xC0),
            'objectives': [],
        }
        for o in objs:
            letter, a, b_ = (o + [None, None])[:3]
            i = ord(str(letter).upper()) - ord('A')
            row['objectives'].append({
                'letter': letter, 'a': a, 'b': b_, 'caption': gmtxt.get(33000 + i),
                'fail': bktxt.get(1001 + i), 'success': bktxt.get(2001 + i)})
        rows.append(row)
    return rows


def check(rows):
    """Tests the count hypotheses: A = (enemy men, enemy units), Z = (player men, player units), B.b = NPC men."""
    tests = {
        'A: a=enemy men, b=enemy units': ('A', lambda r, o: (o['a'], o['b']) == r['enemy']),
        'A: b=enemy units only': ('A', lambda r, o: o['b'] == r['enemy'][1]),
        'Z: a=player men, b=player units': ('Z', lambda r, o: (o['a'], o['b']) == r['player']),
        'Z: b=player units only': ('Z', lambda r, o: o['b'] == r['player'][1]),
        'B: b=NPC men': ('B', lambda r, o: o['b'] == r['npc'][0]),
        'D: b=NPC units': ('D', lambda r, o: o['b'] == r['npc'][1]),
        'E/F: b or a = enemy men': ('EF', lambda r, o: r['enemy'][0] in (o['a'], o['b'])),
    }
    for label, (letters, fn) in tests.items():
        hits, total, misses = 0, 0, []
        for r in rows:
            for o in r['objectives']:
                if str(o['letter']).upper() in letters:
                    total += 1
                    if fn(r, o):
                        hits += 1
                    else:
                        misses.append(f"{r['battle']}({o['letter']},{o['a']},{o['b']} vs enemy={r['enemy']} "
                                      f"player={r['player']} npc={r['npc']})")
        print(f"{label:34s} {hits}/{total}")
        for m in misses:
            print(f"    miss: {m}")


def main(game, mode=None, out=None):
    dll = os.path.join(game, 'FILE', 'DLL')
    brtxt, gmtxt, bktxt = (load_strings(os.path.join(dll, n)) for n in ('BRTXT.DLL', 'GMTXT.DLL', 'BKTXT.DLL'))
    wnd = load_rcdata(os.path.join(dll, 'WND.DLL'))
    rows = battle_objectives(os.path.join(game, 'FILE', 'SCRIPT'), gmtxt, bktxt)
    if mode == '--check':
        check(rows)
        return
    missions = []
    for m in mission_blocks(wnd):
        m['name'] = brtxt.get(m.get('name_id'))
        ms = wnd.get(m.get('mission_script', ''), '')
        battles, extra = script_battles(ms)
        for sub in extra['gosub']:                     # follow one level of sub-scripts
            b2, _ = script_battles(wnd.get(sub, ''))
            battles += b2
        m['battles'] = sorted({b for _, b, _ in battles} | ({m['battle']} if m.get('battle') else set()))
        m['debrief_ids'] = sorted({d for _, _, d in battles if d is not None} |
                                  {int(x) for x in extra['setdebrief'] if x.lstrip('-').isdigit()})
        m['movies'] = extra['playmovie']
        m['brief_text_ids'] = script_battles(wnd.get(m.get('brief', ''), ''))[1]['playtext']
        missions.append(m)
    if mode == '--json':
        if out is None:
            raise SystemExit('--json needs an output path')
        json.dump({'missions': missions, 'battles': rows}, open(out, 'w'), indent=1, ensure_ascii=False)
        print(f"written {out}")
        return
    print("# Campaign missions ([MISSION] blocks in WND.DLL)")
    seen = set()
    for m in missions:
        key = (m.get('name_id'), m.get('mission_script'))
        if key in seen:
            continue
        seen.add(key)
        ids = m['brief_text_ids']
        print(f"{m.get('name_id')!s:>4} {m['name']!s:30s} brief={m.get('brief')!s:18s} script={m.get('mission_script')!s:14s} "
              f"battles={','.join(m['battles'])} debrief={m['debrief_ids']} movies={m['movies']} "
              f"brief_text={ids[0] if ids else '-'}..{ids[-1] if ids else '-'} cash={m.get('cash')}")
    print("\n# Battle objectives (Objective:L,a,b -> GMTXT 33000+i)")
    for r in rows:
        if r['objectives']:
            objs = '; '.join(f"{o['letter']},{o['a']},{o['b']}={o['caption'].split(')')[-1] if o['caption'] else '?'}"
                             for o in r['objectives'])
            print(f"{r['battle']:8s} enemy={r['enemy']} player={r['player']} npc={r['npc']}  {objs}")


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    else:
        main(a[0], a[1] if len(a) > 1 else None, a[2] if len(a) > 2 else None)
