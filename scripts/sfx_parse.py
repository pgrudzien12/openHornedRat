"""Parser for .SFX sound-effect packages (RIFF 'MSFX') and their links to WAV files and .BTS scripts.

Format description: notes/sfx.md. The package format belongs to the Mindscape sound library
MSNDDS.DLL (ImportSFXpackage/ExportSFXpackage); the packet name -> directory table is in GAMEF.DLL.

Usage:
  sfx_parse.py <file.SFX>                  list the effects of one package (WAVs looked up next to it)
  sfx_parse.py <WARFB dir>                 list all packages known to GAMEF.DLL, with WAV file names
  sfx_parse.py <WARFB dir> --check         structural checks on every .SFX + loadsfx/WAV cross-reference
  sfx_parse.py <WARFB dir> --json OUT      export everything as JSON (e.g. extracted/sfx/sfx.json)

Example:
  python3 scripts/sfx_parse.py ".../WARFB" --check --json extracted/sfx/sfx.json
"""
import glob, hashlib, json, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CHUNK_ORDER = (b'INFO', b'SFX ', b'SMP ', b'LIST', b'NAME', b'SFID')
RECORD_SIZE = 60
# Fixed overhead the writer allocates: RIFF/MSFX (12) + INFO (12) + 5 chunk headers (40)
# + 20 bytes of slack. Pad bytes of odd-sized chunks are taken from that slack.
WRITER_OVERHEAD = 84
# flag bits as stored in the file (ExportSFXpackage/ImportSFXpackage debug strings)
FLAGS = ((0x01, 'INTERRUPTABLE'), (0x02, 'LOOP'), (0x04, 'LIST'), (0x08, 'RANDOM'), (0x10, '3D'))
# 15 x uint32 per record: (offset, name, size); size 2 = uint16
RECORD_FIELDS = (
    (0, 'unk00', 4),         # writer always stores -1; ignored by the importer
    (4, 'priority', 4),
    (8, 'unk08', 4),         # writer stores 0; ignored
    (12, 'unk0c', 4),        # writer stores 0; ignored
    (16, 'flags', 2),
    (18, 'unk12', 2),        # never written by the exporter (uninitialised stack: 0x0040 or 0)
    (20, 'unk14', 4),        # writer stores 0; ignored
    (24, 'pitch', 4),        # playback rate in Hz (11025 = original rate of the samples)
    (28, 'volume', 4),       # 0..127
    (32, 'pan', 4),          # 0..127, 64 = centre
    (36, 'param_a', 2),      # copied to the runtime SFX; overwritten by SoundPlace (3D placement?)
    (38, 'param_b', 2),
    (40, 'unk28', 4),        # writer stores constant 0x38f (911); ignored
    (44, 'unk2c', 4),        # writer stores 0; importer treats non-zero like the LIST flag
    (48, 'unk30', 4),        # writer stores 0; ignored
    (52, 'list_count', 4),   # number of LIST entries (only for LIST effects with > 1 member)
    (56, 'sample', 4),       # 0-based index into NAME (WAV file)
)


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def flag_names(f):
    names = [n for bit, n in FLAGS if f & bit]
    rest = f & ~sum(bit for bit, _ in FLAGS)
    if rest:
        names.append('0x%x' % rest)
    return names


def split_names(body, count):
    """Null-terminated strings stored one after another; returns up to count names."""
    parts = body.split(b'\0')
    names = [p.decode('latin-1') for p in parts[:count]]
    complete = len(parts) > count or (len(parts) == count and body.endswith(b'\0'))
    return names, complete


def parse_sfx(data):
    """Parses a .SFX file image. Returns a dict with chunks, samples, effects and a list of problems."""
    problems, notes = [], []
    pkg = {'size': len(data), 'problems': problems, 'notes': notes}
    if data[:4] != b'RIFF' or data[8:12] != b'MSFX':
        problems.append('not a RIFF MSFX file')
        return pkg
    pkg['riff_size'] = u32(data, 4)
    if pkg['riff_size'] != len(data):
        problems.append('RIFF size %d != file size %d' % (pkg['riff_size'], len(data)))

    chunks, o = [], 12
    while o + 8 <= len(data) and data[o:o + 4] in CHUNK_ORDER:
        tag, n = data[o:o + 4], u32(data, o + 4)
        body = data[o + 8:o + 8 + n]
        chunks.append({'tag': tag.decode(), 'offset': o, 'size': n, 'truncated': len(body) < n})
        if len(body) < n:
            problems.append('%s chunk truncated (%d of %d bytes)' % (tag.decode(), len(body), n))
        o += 8 + n + (n & 1)
    pkg['chunks'] = chunks
    tags = [c['tag'].encode() for c in chunks]
    if tuple(tags) != CHUNK_ORDER:
        problems.append('chunk order %s' % [t.decode() for t in tags])
    body = {c['tag'].encode(): data[c['offset'] + 8:c['offset'] + 8 + c['size']] for c in chunks}
    tail = data[min(o, len(data)):]
    pkg['trailing_bytes'] = len(tail)
    if any(tail):
        problems.append('non-zero trailing bytes')
    expected = WRITER_OVERHEAD + sum(c['size'] for c in chunks if c['tag'] != 'INFO')
    pkg['writer_size_ok'] = expected == len(data)
    if not pkg['writer_size_ok']:
        notes.append('file size %d != writer formula %d (84 + chunk data)' % (len(data), expected))

    info = body.get(b'INFO', b'')
    if len(info) != 4:
        problems.append('INFO size %d' % len(info))
        return pkg
    n_samples, n_sfx = struct.unpack('<HH', info)
    pkg['n_samples'], pkg['n_sfx'] = n_samples, n_sfx

    smp = body.get(b'SMP ', b'')
    if smp:
        notes.append('non-empty SMP chunk (%d B): %s' % (len(smp), smp.hex()))

    names, ok = split_names(body.get(b'NAME', b''), n_samples)
    if len(names) != n_samples or not ok:
        problems.append('NAME has %d of %d sample names' % (len(names), n_samples))
    pkg['samples'] = [{'index': i, 'stored_path': p, 'wav': p.replace('/', '\\').split('\\')[-1]}
                      for i, p in enumerate(names)]

    sfid, ok = split_names(body.get(b'SFID', b''), n_sfx)
    if len(sfid) != n_sfx or not ok:
        problems.append('SFID has %d complete of %d effect names' % (len(sfid) - (not ok), n_sfx))

    raw = body.get(b'SFX ', b'')
    if len(raw) != RECORD_SIZE * n_sfx:
        problems.append('SFX chunk %d B, expected %d x %d' % (len(raw), n_sfx, RECORD_SIZE))
    lst = body.get(b'LIST', b'')
    lvals = [u32(lst, i) for i in range(0, len(lst) - len(lst) % 4, 4)]
    lpos = 0
    effects = []
    for i in range(len(raw) // RECORD_SIZE):
        r = raw[i * RECORD_SIZE:(i + 1) * RECORD_SIZE]
        e = {'index': i, 'name': sfid[i] if i < len(sfid) else None}
        for off, name, size in RECORD_FIELDS:
            e[name] = struct.unpack_from('<H' if size == 2 else '<I', r, off)[0]
        e['flag_names'] = flag_names(e['flags'])
        writer = {'unk00': 0xffffffff, 'unk08': 0, 'unk0c': 0, 'unk14': 0, 'unk28': 0x38f,
                  'unk2c': 0, 'unk30': 0}
        e['writer_constants_ok'] = all(e[k] == v for k, v in writer.items())
        if not 0 <= e['sample'] < n_samples:
            problems.append('effect %d: sample index %d out of range' % (i, e['sample']))
        else:
            e['wav'] = pkg['samples'][e['sample']]['wav']
        if (e['flags'] & 0x04 or e['unk2c']) and e['list_count'] >= 1:
            members = lvals[lpos:lpos + e['list_count']]
            term = lvals[lpos + e['list_count']] if lpos + e['list_count'] < len(lvals) else None
            lpos += e['list_count'] + 1
            e['list'] = [m - 1 for m in members]          # stored 1-based
            e['list_names'] = [sfid[m - 1] if 1 <= m <= len(sfid) else None for m in members]
            if any(not 1 <= m <= n_sfx for m in members):
                problems.append('effect %d: list member out of range %s' % (i, members))
            if term != 0:
                problems.append('effect %d: list not followed by 0 separator' % i)
        elif e['list_count']:
            problems.append('effect %d: list_count %d without LIST flag' % (i, e['list_count']))
        effects.append(e)
    if lpos * 4 != len(lst):
        problems.append('LIST chunk %d B, consumed %d B' % (len(lst), lpos * 4))
    pkg['effects'] = effects
    if effects and not all(e['writer_constants_ok'] for e in effects):
        notes.append('%d/%d records differ from the writer constants'
                     % (sum(not e['writer_constants_ok'] for e in effects), len(effects)))
    used = {e['sample'] for e in effects}
    pkg['unused_samples'] = [s['wav'] for s in pkg['samples'] if s['index'] not in used]
    return pkg


# --- installation layout -----------------------------------------------------------------

def find_ci(directory, name):
    """Case-insensitive lookup of one path component; returns the real path or None."""
    try:
        for n in os.listdir(directory):
            if n.lower() == name.lower():
                return os.path.join(directory, n)
    except OSError:
        pass
    return None


def resolve(root, relpath):
    """Resolves a game path like 'binary\\sound\\race\\x.wav': UPDATE/BINARY first, then FILE/BINARY."""
    parts = [p for p in relpath.replace('\\', '/').split('/') if p]
    for base in ('UPDATE', 'FILE'):
        cur = find_ci(root, base)
        for p in parts:
            cur = cur and find_ci(cur, p)
        if cur:
            return cur
    return None


def packet_table(root):
    """Reads the loadsfx name -> directory table from GAMEF.DLL (84-byte entries: name[9], path[71], int32)."""
    gamef = find_ci(root, 'GAMEF.DLL')
    d = open(gamef, 'rb').read()
    start = d.find(b'buttonfx\0binary\\sound\\')
    if start < 0:
        raise SystemExit('packet table not found in GAMEF.DLL')
    start -= 84  # entry 0 is 'void'
    table = []
    for k in range(64):
        e = d[start + k * 84:start + (k + 1) * 84]
        name, path = e[:9].split(b'\0')[0], e[9:80].split(b'\0')[0]
        if k and not path.startswith(b'binary\\sound'):
            break
        table.append({'slot': k, 'name': name.decode(), 'dir': path.decode(),
                      'tail': struct.unpack_from('<i', e, 80)[0]})
    return table


def loadsfx_usage(root):
    """Map lower-case packet name -> list of .BTS files that load it (via whscript.load_battle)."""
    from whscript import load_battle
    usage, unknown = {}, []
    script = find_ci(find_ci(root, 'FILE'), 'SCRIPT')
    for p in sorted(glob.glob(os.path.join(script, '*'))):
        if not p.upper().endswith('.BTS'):
            continue
        for n in load_battle(p, with_merc=False)['load'].get('loadsfx') or []:
            usage.setdefault(n.lower(), []).append(os.path.basename(p))
    return usage


def analyse_install(root):
    table = packet_table(root)
    usage = loadsfx_usage(root)
    sound = resolve(root, 'binary\\sound')
    all_sfx = sorted(p for p in glob.glob(os.path.join(sound, '**', '*'), recursive=True)
                     if p.upper().endswith('.SFX'))
    all_wav = sorted(p for p in glob.glob(os.path.join(sound, '**', '*'), recursive=True)
                     if p.upper().endswith('.WAV'))
    rel = lambda p: os.path.relpath(p, root)
    wav_users = {rel(p): [] for p in all_wav}
    packets, seen = [], set()
    for t in table[1:]:
        path = resolve(root, t['dir'] + t['name'] + '.sfx')
        pk = {'name': t['name'], 'slot': t['slot'], 'dir': t['dir'], 'file': path and rel(path),
              'loaded_by': usage.get(t['name'].lower(), [])}
        if path:
            seen.add(path)
            pk.update(parse_sfx(open(path, 'rb').read()))
            for s in pk.get('samples', []):
                wav = resolve(root, t['dir'] + s['wav'])
                s['file'] = wav and rel(wav)
                stored_dir = s['stored_path'].lower().replace('/', '\\').rsplit('\\', 2)[-2]
                s['stored_dir_matches'] = t['dir'].lower().rstrip('\\').endswith(stored_dir)
                if not wav:
                    pk['problems'].append('WAV not found: %s' % s['wav'])
            for e in pk.get('effects', []):
                s = pk['samples'][e['sample']] if e['sample'] < len(pk['samples']) else None
                if s and s.get('file'):
                    wav_users.setdefault(s['file'], []).append('%s:%s' % (t['name'], e['name']))
        packets.append(pk)
    extra = []
    for p in all_sfx:
        if p not in seen:
            pk = {'name': None, 'file': rel(p)}
            pk.update(parse_sfx(open(p, 'rb').read()))
            extra.append(pk)
    names = {t['name'].lower() for t in table}
    md5 = {}
    for p in all_wav:
        md5.setdefault(hashlib.md5(open(p, 'rb').read()).hexdigest(), []).append(rel(p))
    return {
        'packets': packets,
        'unlisted_sfx_files': extra,
        'loadsfx_usage': usage,
        'loadsfx_unknown_names': sorted(n for n in usage if n not in names),
        'packets_never_loaded_by_bts': [t['name'] for t in table[1:] if t['name'].lower() not in usage],
        'wav_users': wav_users,
        'unused_wavs': sorted(w for w, u in wav_users.items() if not u),
        'duplicate_wavs': [v for v in md5.values() if len(v) > 1],
    }


# --- output ------------------------------------------------------------------------------

def print_package(pk, title):
    print('== %s  (%s samples, %s effects)' % (title, pk.get('n_samples'), pk.get('n_sfx')))
    for e in pk.get('effects', []):
        extra = ''
        if 'list_names' in e:
            extra = '  list=[%s]' % ', '.join(str(n) for n in e['list_names'])
        print('  %2d %-22s %-9s pri=%-3d vol=%-3d pitch=%-5d pan=%-3d a/b=%04x/%04x %-16s%s'
              % (e['index'], e['name'], e.get('wav', '?'), e['priority'], e['volume'], e['pitch'],
                 e['pan'], e['param_a'], e['param_b'], '|'.join(e['flag_names']) or '-', extra))
    if pk.get('unused_samples'):
        print('  samples not used by any effect: %s' % ', '.join(pk['unused_samples']))
    for p in pk.get('problems', []):
        print('  PROBLEM: %s' % p)
    for n in pk.get('notes', []):
        print('  note: %s' % n)


def print_check(res):
    pk = res['packets'] + res['unlisted_sfx_files']
    print('SFX files parsed: %d (%d in the GAMEF.DLL table, %d not listed)'
          % (len([p for p in pk if p.get('file')]), len(res['packets']), len(res['unlisted_sfx_files'])))
    for p in pk:
        print('  %-36s riff=%-5s writer_size=%-5s trailing=%-2s effects=%-3s problems=%d notes=%d'
              % (p.get('file'), p.get('riff_size') == p.get('size'), p.get('writer_size_ok'),
                 p.get('trailing_bytes'), p.get('n_sfx'), len(p.get('problems', [])), len(p.get('notes', []))))
        for x in p.get('problems', []):
            print('      PROBLEM: %s' % x)
        for x in p.get('notes', []):
            print('      note: %s' % x)
    effects = [e for p in res['packets'] for e in p.get('effects', [])]
    flags = {}
    for e in effects:
        k = '|'.join(e['flag_names']) or '-'
        flags[k] = flags.get(k, 0) + 1
    print('effects in listed packets: %d; flag combinations: %s' % (len(effects), flags))
    print('records matching writer constants: %d/%d' % (sum(e['writer_constants_ok'] for e in effects), len(effects)))
    print('loadsfx names used by .BTS: %s' % {k: len(v) for k, v in sorted(res['loadsfx_usage'].items())})
    print('loadsfx names without a packet: %s' % res['loadsfx_unknown_names'])
    print('packets never loaded by any .BTS: %s' % res['packets_never_loaded_by_bts'])
    mism = ['%s:%s (%s)' % (p['name'], s['wav'], s['stored_path']) for p in res['packets']
            for s in p.get('samples', []) if not s.get('stored_dir_matches', True)]
    print('samples whose stored directory differs from the packet directory: %s' % mism)
    used = len(res['wav_users']) - len(res['unused_wavs'])
    print('WAV files in SOUND: %d, used by listed packets: %d, unused: %s'
          % (len(res['wav_users']), used, res['unused_wavs']))
    print('identical WAV files: %s' % res['duplicate_wavs'])


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    target = argv[0]
    out = argv[argv.index('--json') + 1] if '--json' in argv else None
    if os.path.isfile(target):
        pk = parse_sfx(open(target, 'rb').read())
        here = os.path.dirname(target)
        for s in pk.get('samples', []):
            s['file'] = find_ci(here, s['wav'])
        print_package(pk, target)
        res = pk
    else:
        res = analyse_install(target)
        if '--check' in argv:
            print_check(res)
        else:
            for pk in res['packets'] + res['unlisted_sfx_files']:
                print_package(pk, '%s  %s  loaded by %d .BTS' % (pk['name'], pk['file'], len(pk.get('loaded_by', []))))
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, 'w') as f:
            json.dump(res, f, indent=1)
        print('wrote %s' % out)


if __name__ == '__main__':
    main(sys.argv[1:])
