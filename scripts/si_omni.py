"""Parser and extractor for Mindscape Omni '.SI' containers (RIFF 'MxSt', version 1.0).

The .SI files in REMOTE/BINARY/ANIM hold the cutscenes: one Smacker video, sound effects,
speech, MIDI music (as Microsoft 'MIDS' streams) and event tracks, interleaved in 64 KB
buffers. Same engine family as LEGO Island (1997, Omni SI version 2.2); see notes/si_omni.md.

Usage:
  si_omni.py --check   <ANIM dir>                  # parse all .SI, verify coverage/streams
  si_omni.py --list    <file.SI>                   # object tree + stream summary
  si_omni.py --extract <ANIM dir | file.SI> <out>  # rebuild .smk/.wav/.mid/.evt.json + index
e.g.:
  si_omni.py --extract ".../WARFB/REMOTE/BINARY/ANIM" extracted/si

Container layout (verified on all 30 files):
  RIFF 'MxSt'
    LIST 'MxSt'
      MxHd (8 B)                 u32 version 0x00010000, u32 0x100 (unknown)
      MxSt
        MxOb                     root object (tree of nested MxOb in LIST 'MxCh')
        LIST 'MxDa'              MxCh data chunks + 'pad ' chunks, 64 KB buffers
      pad                        fills the file up to a multiple of 64 KB
"""
import glob, hashlib, json, os, struct, sys

BUFFER = 0x10000          # buffer size: files and 'pad ' chunks align to 64 KB

# Object types (numbers as in the LEGO Island SI format; confirmed by usage here)
TYPE_NAMES = {0: 'Object', 1: 'Action', 2: 'MediaAction', 3: 'Anim', 4: 'Sound',
              5: 'MultiAction', 6: 'SerialAction', 7: 'ParallelAction', 8: 'Event',
              9: 'SelectAction', 10: 'Still', 11: 'ObjectAction'}
CONTAINER_TYPES = (5, 6, 7, 9)

# MxCh flags (as in LEGO Island MxDSChunk)
CH_END = 0x02             # end of stream marker (no data, time = end time)
CH_SPLIT = 0x10           # piece of a chunk split across a buffer boundary


def u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def cstr(d, o):
    e = d.index(b'\0', o)
    return d[o:e].decode('latin-1'), e + 1


# ---------------------------------------------------------------------------
# MxOb: object tree
# ---------------------------------------------------------------------------

def parse_object(d, o, end):
    """Parses one MxOb payload d[o:end]. Returns a dict (recursive for containers)."""
    ob = {'type': struct.unpack_from('<H', d, o)[0]}
    ob['type_name'] = TYPE_NAMES.get(ob['type'], '?')
    o += 2
    # LEGO Island: sourceName (cstr), u32 unk14. v1.0 has one more byte; parsed as an
    # empty cstr (always "" here). unk14 = 1 for all Event objects and one Sound.
    ob['source_name'], o = cstr(d, o)
    ob['unk14'] = u32(d, o)
    o += 4
    ob['extra_name'], o = cstr(d, o)
    ob['name'], o = cstr(d, o)
    (ob['id'], ob['flags'], ob['start'], ob['duration'],
     ob['loops']) = struct.unpack_from('<IIiiI', d, o)
    o += 20
    # v1.0 has no location/direction/up vectors and no extra data (LEGO 2.2 has them)
    if ob['type'] in CONTAINER_TYPES:
        assert d[o:o + 4] == b'LIST' and d[o + 8:o + 12] == b'MxCh', 'container without LIST MxCh'
        lsize = u32(d, o + 4)
        lend = o + 8 + lsize
        p = o + 12
        if ob['type'] == 9:                    # SelectAction: variable + choice strings
            var, p = cstr(d, p)
            n = u32(d, p)
            p += 4
            choices = []
            for _ in range(n):
                c, p = cstr(d, p)
                choices.append(c)
            ob['select_variable'], ob['select_choices'] = var, choices
        else:
            n = u32(d, p)
            p += 4
        ob['children'] = []
        for _ in range(n):
            assert d[p:p + 4] == b'MxOb', 'expected MxOb in child list'
            s = u32(d, p + 4)
            ob['children'].append(parse_object(d, p + 8, p + 8 + s))
            p += 8 + s + (s & 1)
        assert p == lend, 'child list size mismatch'
        o = lend + (lsize & 1)
    else:
        ob['file'], o = cstr(d, o)
        # LEGO MediaAction: unk0, unk4, framesPerSecond, mediaFormat, paletteManagement,
        # sustainTime. v1.0 has one extra u32 in front: the index of the leaf object.
        (ob['leaf_index'], ob['unk_a'], ob['unk_b'], ob['fps'], fmt,
         ob['palette_mgmt'], ob['sustain']) = struct.unpack_from('<IIII4sIi', d, o)
        ob['format'] = fmt.decode('latin-1').strip()
        o += 28
        if ob['type'] == 4:                    # Sound: volume
            ob['volume'] = u32(d, o)
            o += 4
    assert o == end, 'MxOb %s: %d unparsed bytes' % (ob.get('name'), end - o)
    return ob


def walk_objects(ob):
    yield ob
    for c in ob.get('children', []):
        yield from walk_objects(c)


# ---------------------------------------------------------------------------
# RIFF structure + chunks
# ---------------------------------------------------------------------------

def load_si(path):
    """Parses a .SI file. Returns a dict with header, root object, chunks and coverage stats."""
    d = open(path, 'rb').read()
    si = {'path': path, 'size': len(d), 'unknown_chunks': [], 'gaps': [], 'pads': 0,
          'pad_bytes': 0, 'chunks': []}
    covered = 0

    def fail(msg):
        raise ValueError('%s: %s' % (os.path.basename(path), msg))

    if d[:4] != b'RIFF' or d[8:12] != b'MxSt':
        fail('not RIFF MxSt')
    if u32(d, 4) + 8 != len(d):
        fail('RIFF size != file size')
    if d[12:16] != b'LIST' or d[20:24] != b'MxSt' or u32(d, 16) + 20 != len(d):
        fail('bad LIST MxSt')
    o, end = 24, len(d)
    covered += 24
    while o < end:
        t, s = d[o:o + 4], u32(d, o + 4)
        if o + 8 + s > end:
            fail('chunk %r at 0x%x overruns' % (t, o))
        if t == b'MxHd':
            si['version'], si['hd_unk'] = struct.unpack_from('<II', d, o + 8)
            covered += 8 + s
        elif t == b'pad ':
            si['pads'] += 1
            si['pad_bytes'] += 8 + s
            covered += 8 + s
        elif t == b'MxSt':
            covered += 8
            p, send = o + 8, o + 8 + s
            while p < send:
                t2, s2 = d[p:p + 4], u32(d, p + 4)
                if t2 == b'MxOb':
                    si['root'] = parse_object(d, p + 8, p + 8 + s2)
                    covered += 8 + s2 + (s2 & 1)
                elif t2 == b'LIST' and d[p + 8:p + 12] == b'MxDa':
                    covered += 12
                    covered += parse_data_list(d, p + 12, p + 8 + s2, si) + (s2 & 1)
                else:
                    si['unknown_chunks'].append((p, t2))
                    covered += 8 + s2 + (s2 & 1)
                p += 8 + s2 + (s2 & 1)
        else:
            si['unknown_chunks'].append((o, t))
            covered += 8 + s
        o += 8 + s + (s & 1)
        covered += s & 1
    si['covered'] = covered
    return si


def parse_data_list(d, o, end, si):
    """Parses LIST 'MxDa' contents. Returns number of bytes covered."""
    covered = 0
    while o < end:
        t = d[o:o + 4]
        room = BUFFER - o % BUFFER
        if t not in (b'MxCh', b'pad '):
            # Fewer than 8 bytes left in a buffer: no room for a chunk header, the writer
            # leaves old buffer contents (garbage) and continues at the next buffer.
            if room < 8:
                si['gaps'].append((o, room))
                covered += room
                o += room
                continue
            raise ValueError('%s: unknown chunk %r at 0x%x' % (os.path.basename(si['path']), t, o))
        s = u32(d, o + 4)
        if t == b'MxCh':
            flags, oid, time, length = struct.unpack_from('<HIiI', d, o + 8)
            si['chunks'].append({'offset': o, 'flags': flags, 'id': oid, 'time': time,
                                 'length': length, 'data': d[o + 22:o + 8 + s]})
        else:
            si['pads'] += 1
            si['pad_bytes'] += 8 + s
        covered += 8 + s + (s & 1)
        o += 8 + s + (s & 1)
    return covered


def assemble_streams(si):
    """Joins split chunks. Returns {id: {'header': bytes|None, 'frames': [(time, data)],
    'end': time|None, 'pieces': n}}."""
    streams, pending = {}, {}
    for ch in si['chunks']:
        st = streams.setdefault(ch['id'], {'header': None, 'frames': [], 'end': None,
                                           'split_chunks': 0})
        oid = ch['id']
        if oid in pending:                     # continuation of a split chunk
            pc = pending[oid]
            assert ch['flags'] & CH_SPLIT, 'split continuation without flag'
            pc['data'] += ch['data']
            if len(pc['data']) < pc['length']:
                continue
            assert len(pc['data']) == pc['length'], 'split pieces overshoot'
            del pending[oid]
            ch = dict(pc, data=bytes(pc['data']))
            st['split_chunks'] += 1
        elif ch['flags'] & CH_SPLIT and ch['length'] != len(ch['data']):
            # first piece: 'length' is the length of the whole chunk
            pending[oid] = dict(ch, data=bytearray(ch['data']))
            continue
        assert ch['length'] == len(ch['data']), 'chunk length mismatch'
        if ch['flags'] & CH_END:
            assert not ch['data'] and st['end'] is None
            st['end'] = ch['time']
        elif ch['time'] == -1:
            assert st['header'] is None, 'two header chunks'
            st['header'] = ch['data']
        else:
            st['frames'].append((ch['time'], ch['data']))
    assert not pending, 'unfinished split chunks'
    return streams


# ---------------------------------------------------------------------------
# Rebuilding media files
# ---------------------------------------------------------------------------

def smk_info(header):
    sig, w, h, nf, rate, flags = struct.unpack_from('<4sIIIiI', header, 0)
    trees = u32(header, 52)
    n = nf + (flags & 1)                       # ring frame adds one entry
    sizes = struct.unpack_from('<%dI' % n, header, 104)
    fps = 1000 / rate if rate > 0 else (100000 / -rate if rate < 0 else 10)
    return {'signature': sig.decode(), 'width': w, 'height': h, 'frames': nf, 'ring': flags & 1,
            'flags': flags, 'rate': rate, 'smk_fps': round(fps, 2),
            'audio_rates': list(struct.unpack_from('<7I', header, 72)),
            'header_len_expected': 104 + 5 * n + trees, 'frame_sizes': sizes}


def build_smk(ob, st):
    """Header chunk = Smacker header + frame size/type tables + Huffman trees; each data
    chunk = one frame. Looped films (loops > 1) store the frames again for every loop:
    f0..f(n-1), then (ring, f1..f(n-1)) per extra loop. Only the first pass is written."""
    info = smk_info(st['header'])
    if info['signature'] not in ('SMK2', 'SMK4'):
        raise ValueError('not a Smacker header')
    if len(st['header']) != info['header_len_expected']:
        raise ValueError('Smacker header length mismatch')
    n = info['frames'] + info['ring']
    frames = [f[1] for f in st['frames']]
    for i, size in enumerate(info['frame_sizes']):
        if size & ~3 != len(frames[i]):
            raise ValueError('frame %d size mismatch' % i)
    nf = info['frames']
    if ob['loops'] > 1:                        # verify the loop layout
        for i in range(nf, len(frames)):
            k = (i - nf) % nf
            ref = frames[nf] if k == 0 else frames[k]
            if frames[i] != ref:
                raise ValueError('loop copy mismatch at chunk %d' % i)
        info['loop_layout_ok'] = len(frames) == nf * ob['loops']
    elif len(frames) != n:
        raise ValueError('frame count mismatch')
    info['chunk_frames'] = len(frames)
    info['frame_times_ms'] = [st['frames'][0][0], st['frames'][-1][0]]
    del info['frame_sizes']
    return st['header'] + b''.join(frames[:n]), info


def build_wav(ob, st):
    """Header chunk (24 B) = PCM WAVEFORMAT (16 B) + u32 data size of the original file
    + u32 44 (hypothesis: original WAV header size). Data chunks = raw PCM, 1 s each."""
    h = st['header']
    tag, ch, rate, bps, align, bits = struct.unpack_from('<HHIIHH', h, 0)
    orig_size, unk = struct.unpack_from('<II', h, 16)
    pcm = b''.join(f[1] for f in st['frames'])
    fmt = h[:16]
    wav = (b'RIFF' + struct.pack('<I', 4 + 8 + len(fmt) + 8 + len(pcm) + (len(pcm) & 1)) + b'WAVE'
           + b'fmt ' + struct.pack('<I', len(fmt)) + fmt
           + b'data' + struct.pack('<I', len(pcm)) + pcm + b'\0' * (len(pcm) & 1))
    info = {'format_tag': tag, 'channels': ch, 'rate': rate, 'bits': bits,
            'pcm_bytes': len(pcm), 'header_data_size': orig_size, 'header_unk': unk,
            'seconds': round(len(pcm) / bps, 3) if bps else None}
    return wav, info


def mids_to_smf(blob):
    """Converts a RIFF 'MIDS' (MCI MIDI stream buffers) to a format-0 Standard MIDI File.
    Returns (smf_bytes, info)."""
    if blob[:4] != b'RIFF' or blob[8:12] != b'MIDS':
        raise ValueError('not RIFF MIDS')
    o, events, fmt = 12, [], None
    while o + 8 <= len(blob):
        t, s = struct.unpack_from('<4sI', blob, o)
        if t == b'fmt ':
            fmt = struct.unpack_from('<III', blob, o + 8)      # time format, max buffer, flags
        elif t == b'data':
            nblocks = u32(blob, o + 8)
            p, tick = o + 12, None
            for _ in range(nblocks):
                tk_start, cb = struct.unpack_from('<II', blob, p)
                p += 8
                bend = p + cb
                tick = tk_start if tick is None else tick
                while p < bend:
                    if fmt[2] & 1:                              # MDS_F_NOSTREAMID
                        dt, ev = struct.unpack_from('<II', blob, p)
                        p += 8
                    else:
                        dt, _sid, ev = struct.unpack_from('<III', blob, p)
                        p += 12
                    tick += dt
                    kind = ev >> 24
                    if kind & 0x80:                             # MEVT_F_LONG (sysex etc.)
                        ln = ev & 0xFFFFFF
                        events.append((tick, 'long', blob[p:p + ln]))
                        p += (ln + 3) & ~3
                    elif kind == 0:
                        events.append((tick, 'short', ev & 0xFFFFFF))
                    elif kind == 1:
                        events.append((tick, 'tempo', ev & 0xFFFFFF))
                    # kind 2 = MEVT_NOP: skipped
                p = bend
        o += 8 + s + (s & 1)
    if fmt is None:
        raise ValueError('MIDS without fmt')

    def vlq(v):
        out = [v & 0x7F]
        v >>= 7
        while v:
            out.append(0x80 | (v & 0x7F))
            v >>= 7
        return bytes(reversed(out))

    trk, last = bytearray(), 0
    for tick, kind, v in events:
        trk += vlq(tick - last)
        last = tick
        if kind == 'short':
            st = v & 0xFF
            n = 1 if st >> 4 in (0xC, 0xD) else 2
            trk += bytes([st, (v >> 8) & 0x7F, (v >> 16) & 0x7F][:1 + n])
        elif kind == 'tempo':
            trk += b'\xff\x51\x03' + v.to_bytes(3, 'big')
        else:
            data = v[1:] if v[:1] == b'\xf0' else v
            trk += b'\xf0' + vlq(len(data)) + data
    trk += b'\x00\xff\x2f\x00'
    smf = (b'MThd' + struct.pack('>IHHH', 6, 0, 1, fmt[0] & 0x7FFF)
           + b'MTrk' + struct.pack('>I', len(trk)) + trk)
    notes = sum(1 for t, k, v in events if k == 'short' and v & 0xF0 == 0x90 and v >> 16 & 0x7F)
    return smf, {'division': fmt[0], 'mids_flags': fmt[2], 'events': len(events), 'note_ons': notes,
                 'ticks': last}


def build_evt(ob, st):
    """Header chunk (12 B) = u32 record count, u32 fields per record, u32 fps (8).
    Every data chunk = one record of u32 fields, one per tick (125 ms)."""
    count, nfields, fps = struct.unpack('<III', st['header'])
    rows = [[t] + list(struct.unpack('<%dI' % nfields, d)) for t, d in st['frames']]
    if count != len(rows):
        raise ValueError('EVT count mismatch')
    return {'count': count, 'fields': nfields, 'fps': fps,
            'columns': ['time_ms'] + ['f%d' % i for i in range(nfields)], 'rows': rows}


def safe(name):
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in name)


def process_si(path, outdir=None):
    """Parses + rebuilds all objects of one .SI. Writes files if outdir is given.
    Returns a summary dict (also used by --check)."""
    si = load_si(path)
    streams = assemble_streams(si)
    base = os.path.splitext(os.path.basename(path))[0]
    objs = {o['id']: o for o in walk_objects(si['root'])}
    problems = []
    if si['covered'] != si['size']:
        problems.append('coverage %d != size %d' % (si['covered'], si['size']))
    if si['unknown_chunks']:
        problems.append('unknown chunks %r' % si['unknown_chunks'])
    if set(streams) - set(objs):
        problems.append('streams without object: %r' % sorted(set(streams) - set(objs)))
    if si['size'] % BUFFER:
        problems.append('file size not a multiple of 64 KB')
    if outdir:
        od = os.path.join(outdir, base)
        os.makedirs(od, exist_ok=True)
    written, seen = {}, {}
    for oid, ob in sorted(objs.items()):
        st = streams.get(oid)
        entry = {k: v for k, v in ob.items() if k != 'children'}
        if 'children' in ob:
            entry['children'] = [c['id'] for c in ob['children']]
        if st is None:
            if ob['type'] not in (9,):             # only SelectAction has no chunks at all
                problems.append('object %d %s has no stream' % (oid, ob['name']))
            written[oid] = entry
            continue
        entry['stream'] = {'chunks': len(st['frames']), 'split_chunks': st['split_chunks'],
                           'end_time': st['end'],
                           'bytes': sum(len(f[1]) for f in st['frames'])}
        if st['end'] is None:
            problems.append('object %d %s has no end-of-stream chunk' % (oid, ob['name']))
        try:
            fmt, blob, ext = ob.get('format'), None, None
            if ob['type'] in CONTAINER_TYPES:
                if st['frames'] or st['header'] is not None:
                    problems.append('container %d has data' % oid)
            elif fmt == 'SMK':
                blob, entry['smk'] = build_smk(ob, st)
                ext = '.smk'
            elif fmt == 'WAV':
                blob, entry['wav'] = build_wav(ob, st)
                ext = '.wav'
            elif fmt == 'MID':
                if st['header'] != b'' or len(st['frames']) != 1:
                    problems.append('MID %d: unexpected layout' % oid)
                raw = st['frames'][0][1]
                blob, entry['midi'] = mids_to_smf(raw)
                ext = '.mid'
                if outdir:
                    open(os.path.join(od, safe(ob['name']) + '.mids'), 'wb').write(raw)
            elif fmt == 'EVT':
                entry['evt'] = build_evt(ob, st)
                blob = json.dumps(entry['evt']).encode()
                ext = '.evt.json'
            else:
                problems.append('object %d: unknown format %r' % (oid, fmt))
        except (ValueError, AssertionError, struct.error) as e:
            problems.append('object %d %s: %s' % (oid, ob['name'], e))
            blob = None
        if blob is not None:
            h = hashlib.sha1(blob).hexdigest()
            if h in seen:                        # identical content already written
                entry['output'] = seen[h]
                entry['duplicate_of'] = seen[h]
            else:
                src = os.path.basename(ob['file'].replace('\\', '/'))
                fname = safe(ob['name']) + ext
                if ext == '.mid':
                    fname = safe(ob['name']) + '_' + safe(os.path.splitext(src)[0]) + ext
                seen[h] = fname
                entry['output'] = fname
                if outdir:
                    open(os.path.join(od, fname), 'wb').write(blob)
        written[oid] = entry
    summary = {'file': os.path.basename(path), 'size': si['size'], 'version': si['version'],
               'hd_unk': si['hd_unk'], 'chunks': len(si['chunks']), 'pads': si['pads'],
               'pad_bytes': si['pad_bytes'], 'gaps': si['gaps'], 'objects': written,
               'problems': problems}
    if outdir:
        s2 = dict(summary)
        for e in s2['objects'].values():
            e.get('evt', {}).pop('rows', None)
        open(os.path.join(od, 'objects.json'), 'w').write(json.dumps(s2, indent=1))
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def si_files(p):
    if os.path.isdir(p):
        return sorted(f for f in glob.glob(os.path.join(p, '*')) if f.upper().endswith('.SI'))
    return [p]


def describe(e):
    """One-line description of an object for listings and the index."""
    if 'smk' in e:
        s = e['smk']
        return '%s %dx%d, %d frames%s, header %.2f fps, played every 125 ms, loops %d' % (
            s['signature'], s['width'], s['height'], s['frames'], ' +ring' if s['ring'] else '',
            s['smk_fps'], e['loops'])
    if 'wav' in e:
        w = e['wav']
        return 'PCM %d Hz %d-bit %s, %.2f s, vol %d' % (w['rate'], w['bits'],
                                                       'mono' if w['channels'] == 1 else 'stereo',
                                                       w['seconds'], e['volume'])
    if 'midi' in e:
        m = e['midi']
        return 'MIDS->SMF, %d events, %d notes, div %d, vol %d%s' % (
            m['events'], m['note_ons'], m['division'], e['volume'], ', loops forever' if e['loops'] == 0 else '')
    if 'evt' in e:
        v = e['evt']
        return 'EVT %d records x %d fields' % (v['count'], v['fields'])
    if 'select_variable' in e:
        return 'select on %s: %s' % (e['select_variable'], ' / '.join(e['select_choices']))
    if 'children' in e:
        return '%d children' % len(e['children'])
    return ''


def cmd_list(path):
    s = process_si(path)
    objs = s['objects']
    print('%s: %d B, version 0x%08x, MxHd unk 0x%x, %d MxCh, %d pad chunks (%d B), gaps %r' % (
        s['file'], s['size'], s['version'], s['hd_unk'], s['chunks'], s['pads'], s['pad_bytes'],
        s['gaps']))

    def show(oid, depth):
        e = objs[oid]
        print('%s[%d] %-14s %-26s %-28s start %6d dur %6d  %s' % (
            '  ' * depth, oid, e['type_name'], e['name'], e.get('file', ''), e['start'],
            e['duration'], describe(e)))
        for c in e.get('children', []):
            show(c, depth + 1)
    root = [o for o in objs.values() if o['id'] == 0][0]
    show(root['id'], 0)
    for p in s['problems']:
        print('PROBLEM:', p)


def cmd_check(anim):
    files = si_files(anim)
    totals, bad = {}, 0
    for f in files:
        s = process_si(f)
        for e in s['objects'].values():
            k = e['type_name'] + ('/' + e['format'] if 'format' in e else '')
            totals[k] = totals.get(k, 0) + 1
        mark = 'OK ' if not s['problems'] else 'BAD'
        bad += bool(s['problems'])
        smk = [e for e in s['objects'].values() if 'smk' in e]
        print('%s %-12s %9d B  %4d MxCh  %2d objects  gaps %d  %s' % (
            mark, s['file'], s['size'], s['chunks'], len(s['objects']), len(s['gaps']),
            describe(smk[0]) if smk else ''))
        for p in s['problems']:
            print('    ', p)
    print('files: %d, with problems: %d' % (len(files), bad))
    print('objects by type:', ', '.join('%s %d' % kv for kv in sorted(totals.items())))
    return bad == 0


def cmd_extract(src, out):
    os.makedirs(out, exist_ok=True)
    lines = ['# .SI index (generated by scripts/si_omni.py)', '',
             '| SI | id | type | name | source file | start ms | dur ms | output | details |',
             '|---|---|---|---|---|---|---|---|---|']
    for f in si_files(src):
        s = process_si(f, out)
        for oid, e in sorted(s['objects'].items()):
            out_name = e.get('output', '')
            if 'duplicate_of' in e:
                out_name = '= ' + out_name
            lines.append('| %s | %d | %s | %s | %s | %d | %d | %s | %s |' % (
                s['file'], oid, e['type_name'], e['name'], e.get('file', '').replace('\\', '\\\\'),
                e['start'], e['duration'], out_name, describe(e)))
        print('%-12s -> %s  (%d objects%s)' % (s['file'], os.path.join(out, s['file'][:-3]),
                                              len(s['objects']),
                                              ', PROBLEMS: %r' % s['problems'] if s['problems'] else ''))
    open(os.path.join(out, 'INDEX.md'), 'w').write('\n'.join(lines) + '\n')
    print('index:', os.path.join(out, 'INDEX.md'))


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == '--check':
        sys.exit(0 if cmd_check(a[1]) else 1)
    elif len(a) == 2 and a[0] == '--list':
        cmd_list(a[1])
    elif len(a) == 3 and a[0] == '--extract':
        cmd_extract(a[1], a[2])
    else:
        print(__doc__)
        sys.exit(2)
