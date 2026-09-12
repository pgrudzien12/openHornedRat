"""Cross-reference report for the game music: SBK presets vs. programs used by every MIDI file,
GM/FM file pairs, and where each track is referenced in the game (strings only, no disassembly).
Prints Markdown tables (used for notes/music.md). Pure Python.

Usage:
  music_report.py <WARFB>            Markdown report on stdout

Example:
  python3 scripts/music_report.py ".../GOG Games/Warhammer - Shadow of the Horned Rat/WARFB"

Sources scanned for track names:
  - WHSHR.EXE / GAMEF.DLL : literal 'binary\\music\\<name>.mid' strings (+ neighbouring strings)
  - FILE/DLL/WND.DLL      : campaign "glue" scripts embedded as resources:
                            'playmidi:<name>', 'addmidiobject:<name>', '[MIDI] name:<name>'
  - REMOTE/BINARY/ANIM/*.SR : cutscene scripts with 'music\\<name>fm.mid' + 'musicawe\\<name>.mid'
"""
import collections, glob, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import music_midi, music_sf2  # noqa: E402
from music_render import game_file, find_ci, SBK_REL, MUSIC_REL, USER_BANK  # noqa: E402


def fm_name(gm):
    """Observed 8.3 naming rule: FM variant = first 6 characters + 'FM'."""
    stem = os.path.splitext(gm)[0].upper()
    return stem[:6] + 'FM'


def strings_near(data, offset, before=2, after=2):
    """Printable ASCII strings around an offset (like `strings`, for context)."""
    lo, hi = max(0, offset - 300), min(len(data), offset + 300)
    parts = [(m.start() + lo, m.group().decode()) for m in re.finditer(rb'[\x20-\x7e]{4,}', data[lo:hi])]
    idx = next((i for i, (o, _) in enumerate(parts) if o <= offset < o + len(_) + 1), None)
    if idx is None:
        return []
    return [s for _, s in parts[max(0, idx - before):idx]] + [s for _, s in parts[idx + 1:idx + 1 + after]]


def scan_locations(install):
    loc = collections.defaultdict(list)
    for exe in ('WHSHR.EXE', 'GAMEF.DLL'):
        p = find_ci(install, (exe,))
        if not p:
            continue
        d = open(p, 'rb').read()
        # 'binary\music\win.mid' in WHSHR.EXE, but also bare 'battle.mid' in GAMEF.DLL
        for m in re.finditer(rb'(?i)(?<![\w\\%])(?:binary\\music\\)?([a-z]\w*)\.mid', d):
            ctx = [s for s in strings_near(d, m.start()) if 'music' not in s.lower()]
            loc[m.group(1).decode().upper()].append('%s: `%s` (next to: %s)' % (
                exe, m.group().decode(), ', '.join('`%s`' % c for c in ctx)))
    wnd = game_file(install, 'DLL', 'WND.DLL')
    if wnd:
        d = open(wnd, 'rb').read()
        counts = collections.Counter()
        for m in re.finditer(rb'(?i)(playmidi|addmidiobject):(\w+)|\[MIDI\]\s*name:(\w+)', d):
            cmd = (m.group(1) or b'[MIDI] name').decode().lower()
            counts[((m.group(2) or m.group(3)).decode().upper(), cmd)] += 1
        for (name, cmd), n in sorted(counts.items()):
            loc[name].append('WND.DLL glue: `%s:%s` x%d' % (cmd, name.lower(), n))
    anim = find_ci(install, ('REMOTE', 'BINARY', 'ANIM'))
    scenes = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(anim or '', '*'))):
        if not p.upper().endswith('.SR'):
            continue
        d = open(p, 'rb').read()
        for m in sorted(set(re.findall(rb'(?i)musicawe\\(\w+)\.mid', d))):
            scenes[m.decode().upper()].append(os.path.splitext(os.path.basename(p))[0].upper())
    for name, sc in scenes.items():
        loc[name].append('cutscenes (ANIM/*.SR): %s' % ', '.join(sc))
    return loc


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    install = argv[0]
    sf = music_sf2.parse_sf2(game_file(install, *SBK_REL))
    music_dir = os.path.dirname(game_file(install, *MUSIC_REL, 'INTRO3.MID'))
    midis = {os.path.basename(p).upper(): music_midi.parse_midi(p) for p in music_midi.find_midis(music_dir)}
    sbk_progs = {p['program']: p for p in sf['presets']}

    print('## SBK presets (%s)\n' % sf['file'])
    print('| Bank in file | Bank in game (hyp.) | Program | GM name of that slot | Preset name | '
          'Zones: key range -> sample (recorded pitch as MIDI key = root - tuning) |')
    print('|---|---|---|---|---|---|')
    for p in sf['presets']:
        zdesc = []
        for pz in p['zones']:
            for z in sf['instruments'][pz[41]]['zones']:
                root = z.get(58, z.get(55, 0) / 100.0)
                eff = root - z.get(51, 0) - z.get(52, 0) / 100.0
                zdesc.append('%d-%d -> %s (%g)' % (z[43][0], z[43][1], sf['samples'][z[53]]['name'], round(eff, 2)))
        print('| %d | %d | %d | %s | `%s` | %s |' % (p['bank'], USER_BANK, p['program'],
                                                  music_sf2.gm_name(0, p['program']), p['name'], '; '.join(zdesc)))

    loc = scan_locations(install)
    print('\n## Tracks\n')
    print('| Track | FM file | SMF fmt/tracks | PPQN | BPM | Length s (GM / FM) | Channels (GM) | SBK presets (bank %d) | Programs from GM ROM |' % USER_BANK)
    print('|---|---|---|---|---|---|---|---|---|')
    gm_names = sorted(n for n in midis if not n.endswith('FM.MID'))
    fm_used = set()
    rom_usage = collections.defaultdict(set)
    unknown_bank = []
    for name in gm_names:
        m = midis[name]
        fm = fm_name(name) + '.MID'
        fmm = midis.get(fm)
        if fmm:
            fm_used.add(fm)
        sbk, rom = set(), set()
        for fname, mm in ((name, m), (fm, fmm)):
            if not mm:
                continue
            for msb, lsb, prog, ch in music_midi.programs_used(mm):
                if msb == USER_BANK:
                    (sbk if prog in sbk_progs else unknown_bank.append((fname, msb, lsb, prog, ch)) or set()).add(prog)
                else:
                    key = ('kit %s' % (prog if prog is not None else 0)) if ch == 9 else (prog if prog is not None else 0)
                    rom_usage[key].add(fname)
                    if fname == name:
                        rom.add(key)
        chans = ','.join(str(ch + 1) for ch, c in m['channels'].items() if c['notes'])
        print('| `%s` | %s | %d/%d | %d | %g | %.1f / %s | %s | %s | %s |' % (
            name[:-4], '`%s`' % fm[:-4] if fmm else '**none**', m['format'], m['ntrks_found'], m['division'],
            m['initial_bpm'], m['seconds'], ('%.1f' % fmm['seconds']) if fmm else '-', chans,
            ', '.join('%d %s' % (p, sbk_progs[p]['name']) for p in sorted(sbk)) or '-',
            ', '.join(str(x) for x in sorted(rom, key=str))))
    orphans = sorted(set(n for n in midis if n.endswith('FM.MID')) - fm_used)
    print('\nFM files without a GM partner under the 6+FM rule: %s' % (orphans or 'none'))
    print('Program changes on bank %d that are NOT in the SBK: %s' % (USER_BANK, unknown_bank or 'none'))

    print('\n## GM ROM programs used (bank MSB != %d)\n' % USER_BANK)
    print('| Program | GM name | Files |')
    print('|---|---|---|')
    for key in sorted(rom_usage, key=lambda k: (isinstance(k, str), k if isinstance(k, int) else int(k.split()[1]))):
        label = ('GM drum channel, program %s' % key.split()[1]) if isinstance(key, str) else music_sf2.GM_PROGRAMS[key]
        print('| %s | %s | %d |' % (key, label, len(rom_usage[key])))

    print('\n## Where the tracks are referenced\n')
    for name in gm_names:
        stem = name[:-4]
        refs = loc.get(stem, [])
        print('- `%s`: %s' % (stem, '; '.join(refs) if refs else '**no reference found**'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
