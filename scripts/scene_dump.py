"""Parser for the cutscene side files REMOTE/BINARY/ANIM/*.SN, *.SM, *.SR. See notes/scene_scripts.md.

Every cutscene <NAME> (A1..A27, A12B, A16A, DEATH01...) is a Mindscape Omni container <NAME>.SI
(RIFF MxSt, Smacker video + WAV + MIDI + event objects) plus three small binary side files
written by the SI build tool:

  .SN  object name table      id -> name            (ids are the SI object ids)
  .SM  SI index / chunk map   (object id, time ms, file offset of the MxOb/MxCh header in .SI)
  .SR  build/interleave list  source file path, file index, sequence number (-2/-1/-3 markers)

Usage:
  scene_dump.py <WARFB dir> <scene>                 human-readable structure of one scene (e.g. A9)
  scene_dump.py <WARFB dir> <scene> --json          the same as JSON on stdout
  scene_dump.py <WARFB dir> --json-all <out_dir>    one JSON per scene (e.g. extracted/scene_scripts)
  scene_dump.py <WARFB dir> --check                 verify all scenes byte by byte (+ SI headers)
  scene_dump.py <WARFB dir> --table                 Markdown summary table of all scenes
e.g.:
  scene_dump.py ".../WARFB" A9
  scene_dump.py ".../WARFB" --json-all extracted/scene_scripts

The .SI file is only touched to read the 4-byte tag and the fixed header fields (object name/id,
chunk flags/object id/time/length) at offsets given by .SM; payloads are not read or extracted.
Optional links use files produced by scripts/pe_extract.py (if present):
  extracted/pe_resources/ANTXT/strings.json   subtitle/speech texts (string id == speech number)
  extracted/pe_resources/WND/rcdata/*.txt     campaign glue scripts (playmovie:A9 ...)
"""
import collections, json, os, re, struct, sys, wave

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PE_DIR = os.path.join(REPO, 'extracted', 'pe_resources')

UNUSED = 0xDDDDDDDD            # MSVC debug heap "dead land" fill: struct fields never written
T_OBJECT, T_HEADER, T_END = -2, -1, -3   # special time/sequence values
CHUNK_SPLIT, CHUNK_END = 0x10, 0x02      # MxCh flag bits (observed meaning, see notes)
SI_BLOCK = 0x10000                        # .SI is written in 64 KB blocks


class SceneError(Exception):
    pass


def find_ci(directory, name):
    """Case-insensitive lookup of one path component."""
    for n in os.listdir(directory):
        if n.lower() == name.lower():
            return os.path.join(directory, n)
    return None


def game_dir(warfb, *parts):
    p = warfb
    for part in parts:
        q = find_ci(p, part)
        if q is None:
            raise SceneError(f"{os.path.join(p, part)} not found")
        p = q
    return p


def scene_names(anim_dir):
    names = {os.path.splitext(n)[0].upper() for n in os.listdir(anim_dir)
             if os.path.splitext(n)[1].upper() in ('.SN', '.SM', '.SR')}
    key = lambda s: (not s.startswith('A'), int(re.sub(r'\D', '', s) or 0), s)
    return sorted(names, key=key)


def _u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def _i32(d, o):
    return struct.unpack_from('<i', d, o)[0]


# ---------------------------------------------------------------- the three formats

def read_sn(path):
    """.SN: u32 count, then count x {u32 id, u32 len, char name[len] (NUL included)}."""
    d = open(path, 'rb').read()
    count, o, out = _u32(d, 0), 4, []
    for _ in range(count):
        oid, ln = struct.unpack_from('<II', d, o)
        raw = d[o + 8:o + 8 + ln]
        if len(raw) != ln or not raw.endswith(b'\0') or b'\0' in raw[:-1]:
            raise SceneError(f"{path}: bad name at {o:#x}")
        out.append({'id': oid, 'name': raw[:-1].decode('latin-1')})
        o += 8 + ln
    if o != len(d):
        raise SceneError(f"{path}: {len(d) - o} trailing bytes")
    return out


def read_sm(path):
    """.SM: u32 count, then count x {u32 object_id, i32 time_ms, u32 si_offset} (12 B)."""
    d = open(path, 'rb').read()
    count = _u32(d, 0)
    if 4 + 12 * count != len(d):
        raise SceneError(f"{path}: size {len(d)} != 4 + 12 * {count}")
    return [dict(zip(('id', 'time', 'offset'), struct.unpack_from('<Iii', d, 4 + 12 * k)))
            for k in range(count)]


def read_sr(path):
    """.SR: u32 count, then count x {char path[] NUL-padded to 4, u32 file, i32 seq, u32 a, u32 b}.

    seq == -2: object declaration, a = SI object id, b = 0xfffffffe
    seq == -1: header chunk of the file, seq == -3: end of the file, seq >= 0: n-th data chunk;
    in those a = b = 0xdddddddd (unused).
    """
    d = open(path, 'rb').read()
    count, o, out = _u32(d, 0), 4, []
    for _ in range(count):
        e = d.index(b'\0', o)
        padded = (e - o + 1 + 3) // 4 * 4
        if any(d[e:o + padded]):
            raise SceneError(f"{path}: non-zero padding at {e:#x}")
        rec = {'path': d[o:e].decode('latin-1')}
        o += padded
        rec['file'], rec['seq'], rec['a'], rec['b'] = struct.unpack_from('<IiII', d, o)
        o += 16
        out.append(rec)
    if o != len(d):
        raise SceneError(f"{path}: {len(d) - o} trailing bytes")
    return out


# ---------------------------------------------------------------- SI header peeks

def si_header(si, off):
    """Tag and fixed header fields at an .SM offset (no payload is read)."""
    tag = si[off:off + 4]
    if tag == b'MxOb':
        # MxOb: u32 size, u16 type, 6 bytes (not analysed here), char name[] , u32 id
        otype = struct.unpack_from('<H', si, off + 8)[0]
        e = si.index(b'\0', off + 16)
        return {'tag': 'MxOb', 'type': otype, 'name': si[off + 16:e].decode('latin-1'),
                'id': _u32(si, e + 1)}
    if tag == b'MxCh':
        # MxCh: u32 size, u16 flags, u32 object id, i32 time, u32 data length
        fl, oid, t, ln = struct.unpack_from('<HIiI', si, off + 8)
        return {'tag': 'MxCh', 'flags': fl, 'id': oid, 'time': t, 'length': ln}
    return {'tag': tag.decode('latin-1')}


# ---------------------------------------------------------------- linking helpers

def object_kind(name, path):
    ext = os.path.splitext(path)[1].lower() if path else ''
    if name.endswith('_Stream'):
        return 'stream'
    if ext == '.smk':
        return 'video'
    if not path and re.match(r'Music_.*_MID$', name):
        return 'music-group'
    if ext == '.mid':
        return 'music-awe' if path.lower().startswith('musicawe') else 'music-fm'
    speech = speech_number(path)
    if ext == '.wav':
        return 'speech' if speech or 'SPK' in name else 'sound'
    if ext == '.evt':
        base = os.path.splitext(os.path.basename(path.replace('\\', '/')))[0].lower()
        return base if base in ('animdone', 'fade') else ('subtitle' if speech else 'event')
    return 'other'


def speech_number(path):
    """'scene01\\a1010.wav' -> ('A', 1010). Subtitle events use the prefix a or e (e1010.evt),
    speech WAVs a (scene lines) or b (battle/glue line reused in A23); e is normalised to A."""
    m = re.match(r'([abe])(\d+)$', os.path.splitext(os.path.basename(path.replace('\\', '/')))[0], re.I)
    if not m:
        return None
    return ('B' if m.group(1).lower() == 'b' else 'A', int(m.group(2)))


_texts, _glue = None, None


def anim_texts():
    global _texts
    if _texts is None:
        p = os.path.join(PE_DIR, 'ANTXT', 'strings.json')
        _texts = {int(k): v for k, v in json.load(open(p)).items()} if os.path.exists(p) else {}
    return _texts


def glue_refs():
    """scene name (upper) -> list of 'FILE.txt:line command' from the extracted glue scripts."""
    global _glue
    if _glue is None:
        _glue = collections.defaultdict(list)
        d = os.path.join(PE_DIR, 'WND', 'rcdata')
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                for i, line in enumerate(open(os.path.join(d, n), encoding='latin-1'), 1):
                    m = re.match(r'\s*((?:if(?:true|false))?playmovie(?:withfade)?):(\w+)', line, re.I)
                    if m:
                        _glue[m.group(2).upper()].append(f"{n}:{i} {m.group(1)}")
    return _glue


def wav_info(path):
    try:
        w = wave.open(path)
        return {'duration_s': round(w.getnframes() / w.getframerate(), 3),
                'rate': w.getframerate(), 'bits': 8 * w.getsampwidth(), 'channels': w.getnchannels()}
    except (wave.Error, EOFError) as e:
        return {'error': str(e)}


# ---------------------------------------------------------------- scene model

def load_scene(warfb, name):
    anim = game_dir(warfb, 'REMOTE', 'BINARY', 'ANIM')
    files = {ext: find_ci(anim, f"{name}.{ext}") for ext in ('SN', 'SM', 'SR', 'SI')}
    sn, sm, sr = read_sn(files['SN']), read_sm(files['SM']), read_sr(files['SR'])
    si = open(files['SI'], 'rb').read() if files['SI'] else None
    try:
        speech_dir = game_dir(warfb, 'REMOTE', 'BINARY', 'GLUE', 'SPEECH')
    except SceneError:
        speech_dir = None

    decl = {r['file']: r for r in sr if r['seq'] == T_OBJECT}
    by_id = {r['a']: r for r in decl.values()}
    objs = []
    for o in sn:
        r = by_id.get(o['id'])
        path = r['path'] if r else None
        objs.append({'id': o['id'], 'name': o['name'], 'file_index': r['file'] if r else None,
                     'path': path, 'kind': object_kind(o['name'], path),
                     'si_offset': None, 'si_type': None, 'first_data_ms': None, 'last_data_ms': None,
                     'end_ms': None, 'data_chunks': 0, 'split_parts': 0})
    ob = {o['id']: o for o in objs}
    for e in sm:
        o = ob[e['id']]
        h = si_header(si, e['offset']) if si else {}
        if e['time'] == T_OBJECT:
            o['si_offset'] = e['offset']
            o['si_type'] = h.get('type')
            continue
        fl = h.get('flags', 0)
        if fl & CHUNK_SPLIT and e['offset'] % SI_BLOCK == 0:
            o['split_parts'] += 1          # continuation of a chunk cut at a 64 KB block boundary
        elif fl & CHUNK_END:
            o['end_ms'] = e['time']
        elif e['time'] >= 0:
            o['data_chunks'] += 1
            o['first_data_ms'] = e['time'] if o['first_data_ms'] is None else o['first_data_ms']
            o['last_data_ms'] = e['time']

    speech = []
    texts = anim_texts()
    for o in objs:
        num = speech_number(o['path']) if o['path'] else None
        if not num:
            continue
        o['speech_id'] = f"{num[0]}{num[1]}"
        if num[0] == 'A' and num[1] in texts:
            o['text'] = texts[num[1]]
        if o['kind'] == 'speech' and speech_dir:
            wp = find_ci(speech_dir, os.path.basename(o['path'].replace('\\', '/')))
            o['speech_file'] = f"GLUE/SPEECH/{os.path.basename(wp)}" if wp else None
            if wp:
                o['speech_wav'] = wav_info(wp)
            speech.append(o['speech_id'])
    video = next((o for o in objs if o['kind'] == 'video'), None)
    stream = ob[0]
    # narrator captions: ANTXT ids N*1000+100.. (N = scene number; A16A and A16B share group 16)
    num = _scene_number(name)
    captions = {k: v for k, v in texts.items() if num and k // 1000 == num and k % 1000 >= 100}
    return {
        'scene': name,
        'files': {k: os.path.basename(v) if v else None for k, v in files.items()},
        'counts': {'SN': len(sn), 'SM': len(sm), 'SR': len(sr)},
        'stream_end_ms': stream['end_ms'],
        'video': video['path'] if video else None,
        'video_frames': video['data_chunks'] if video else 0,
        'objects': objs,
        'speech': speech,
        'captions': {str(k): v for k, v in sorted(captions.items())},
        'glue': glue_refs().get(name.upper(), []),
        'sr': sr, 'sm': sm,
    }


def _scene_number(name):
    m = re.match(r'A(\d+)', name, re.I)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- verification

def check_scene(warfb, name):
    """Returns (list of errors, list of notes). Errors = broken hypothesis, notes = known deviations."""
    errs, notes = [], []
    sc = load_scene(warfb, name)       # read_* already enforce exact byte accounting
    sn_ids = [o['id'] for o in sc['objects']]
    if sn_ids != list(range(len(sn_ids))):
        errs.append('SN ids are not 0..n-1')
    sr, sm = sc['sr'], sc['sm']
    decl = [r for r in sr if r['seq'] == T_OBJECT]
    if [r['file'] for r in decl] != list(range(len(decl))):
        errs.append('SR declarations not in file order 0..n-1')
    paths = {r['file']: r['path'] for r in decl}
    seqs = collections.defaultdict(list)
    for r in sr:
        if r['seq'] == T_OBJECT:
            if r['b'] != 0xFFFFFFFE or r['a'] >= len(sn_ids):
                errs.append(f"SR declaration fields {r}")
        else:
            if r['a'] != UNUSED or r['b'] != UNUSED:
                errs.append(f"SR record with used a/b fields {r}")
            if r['seq'] < T_END:
                errs.append(f"SR unknown seq {r}")
            seqs[r['file']].append(r['seq'])
        if paths.get(r['file']) != r['path']:
            errs.append(f"SR path mismatch for file {r['file']}")
    for f, s in seqs.items():
        data = [x for x in s if x >= 0]
        if s.count(T_HEADER) != 1 or s.count(T_END) != 1 or s[0] != T_HEADER:
            errs.append(f"SR file {f}: markers {s.count(T_HEADER)}x-1 {s.count(T_END)}x-3 first {s[0]}")
        if data != list(range(len(data))):
            errs.append(f"SR file {f}: data sequence not 0..n-1")
    offs = [e['offset'] for e in sm]
    if offs != sorted(offs):
        errs.append('SM not sorted by offset')
    if sorted(e['id'] for e in sm if e['time'] == T_OBJECT) != sn_ids:
        errs.append('SM object records != SN ids')
    si_path = find_ci(game_dir(warfb, 'REMOTE', 'BINARY', 'ANIM'), f"{name}.SI")
    if si_path:
        si = open(si_path, 'rb').read()
        for e in sm:
            h = si_header(si, e['offset'])
            if e['time'] == T_OBJECT:
                if h['tag'] != 'MxOb' or h['id'] != e['id'] or h['name'] != sc['objects'][e['id']]['name']:
                    errs.append(f"SM {e} -> SI {h}")
            elif h['tag'] != 'MxCh' or h['id'] != e['id'] or h['time'] != e['time']:
                errs.append(f"SM {e} -> SI {h}")
    # SR data records vs SI data chunks per object
    for o in sc['objects']:
        if o['file_index'] is None:
            continue
        n_sr = sum(1 for x in seqs[o['file_index']] if x >= 0)
        if n_sr != o['data_chunks']:
            notes.append(f"{name} {o['path']}: SR lists {n_sr} data chunks, SI has {o['data_chunks']}")
    return errs, notes, sc


def check_all(warfb):
    anim = game_dir(warfb, 'REMOTE', 'BINARY', 'ANIM')
    tot = collections.Counter()
    bad = 0
    spans = []
    for name in scene_names(anim):
        try:
            errs, notes, sc = check_scene(warfb, name)
        except SceneError as e:
            errs, notes, sc = [str(e)], [], None
        if sc:
            for k, v in sc['counts'].items():
                tot[k] += v
            for o in sc['objects']:
                w = o.get('speech_wav', {})
                if 'duration_s' in w and o['first_data_ms'] is not None:
                    spans.append(w['duration_s'] - (o['last_data_ms'] - o['first_data_ms']) / 1000)
        status = 'OK' if not errs else f"{len(errs)} ERRORS"
        print(f"{name:8} {status:10} SN {sc['counts']['SN'] if sc else '?':>3}  SM {sc['counts']['SM'] if sc else '?':>5}"
              f"  SR {sc['counts']['SR'] if sc else '?':>5}")
        for e in errs[:10]:
            print('   error:', e)
        for n in notes:
            print('   note: ', n)
        bad += bool(errs)
    print(f"\n{len(scene_names(anim))} scenes, {bad} with errors; records: {dict(tot)}")
    if spans:
        print(f"speech WAV duration minus SI chunk time span: {min(spans):.2f} .. {max(spans):.2f} s "
              f"({len(spans)} speech objects with a GLUE/SPEECH file)")
    return bad == 0


# ---------------------------------------------------------------- output

def dump_text(sc):
    print(f"Scene {sc['scene']}: {sc['counts']}  stream end {sc['stream_end_ms']} ms, "
          f"video {sc['video']} ({sc['video_frames']} frames)")
    for g in sc['glue']:
        print(f"  glue: {g}")
    print(f"  {'id':>3} {'name':30} {'kind':12} {'file':4} {'path':26} {'SI type':7} {'chunks':>6} {'first..last ms':>15} end")
    for o in sc['objects']:
        span = f"{o['first_data_ms']}..{o['last_data_ms']}" if o['first_data_ms'] is not None else ''
        print(f"  {o['id']:3} {o['name']:30} {o['kind']:12} {'' if o['file_index'] is None else o['file_index']:>4} "
              f"{o['path'] or '-':26} {o['si_type'] if o['si_type'] is not None else '':>7} {o['data_chunks']:6} {span:>15} {o['end_ms']}")
        if 'speech_wav' in o:
            print(f"        speech {o['speech_file']} {o['speech_wav'].get('duration_s')} s")
        if 'text' in o:
            print(f"        text {o['speech_id'][1:]}: {o['text'][:100]}")
    for k, v in sc['captions'].items():
        print(f"  caption {k}: {v}")


def table(warfb):
    anim = game_dir(warfb, 'REMOTE', 'BINARY', 'ANIM')
    print('| Scene | SN/SM/SR records | Length | Video frames | Objects (video/sound/music/speech/subtitle/other evt) | Speech (GLUE/SPEECH) | Glue scripts |')
    print('|---|---|---|---|---|---|---|')
    for name in scene_names(anim):
        sc = load_scene(warfb, name)
        k = collections.Counter(o['kind'] for o in sc['objects'])
        music = k['music-fm'] + k['music-awe']
        other = k['animdone'] + k['fade'] + k['event']
        sp = []
        for o in sc['objects']:
            if o['kind'] == 'speech' and 'speech_id' in o:
                d = o.get('speech_wav', {}).get('duration_s')
                sp.append(f"{o['speech_id']} ({d:.1f}s)" if d else f"{o['speech_id']} (no file)")
            elif o['kind'] == 'sound' and 'SPK' in o['name']:
                sp.append(f"{os.path.basename(o['path'])} (not in SPEECH)")
        glue = ', '.join(sorted({g.split(':')[0].replace('.txt', '') for g in sc['glue']}))
        c = sc['counts']
        print(f"| {name} | {c['SN']}/{c['SM']}/{c['SR']} | {sc['stream_end_ms'] / 1000:.1f} s | {sc['video_frames']} | "
              f"{k['video']}/{k['sound']}/{music}/{k['speech']}/{k['subtitle']}/{other} | {', '.join(sp) or '-'} | {glue or '-'} |")


def to_json(sc):
    out = dict(sc)
    out['sr'] = [dict(r, a=f"{r['a']:#x}", b=f"{r['b']:#x}") for r in sc['sr']]
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    warfb = argv[1]
    if '--check' in argv:
        return 0 if check_all(warfb) else 1
    if '--table' in argv:
        table(warfb)
        return 0
    if '--json-all' in argv:
        out = argv[argv.index('--json-all') + 1]
        os.makedirs(out, exist_ok=True)
        for name in scene_names(game_dir(warfb, 'REMOTE', 'BINARY', 'ANIM')):
            with open(os.path.join(out, f"{name}.json"), 'w') as f:
                json.dump(to_json(load_scene(warfb, name)), f, indent=1)
        print(f"written to {out}")
        return 0
    sc = load_scene(warfb, argv[2].upper())
    if '--json' in argv:
        json.dump(to_json(sc), sys.stdout, indent=1)
        print()
    else:
        dump_text(sc)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
