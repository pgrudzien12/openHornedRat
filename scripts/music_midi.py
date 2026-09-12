"""Pure-Python Standard MIDI File (SMF, format 0/1) parser. Target: FILE/BINARY/MUSIC/*.MID.
Description: notes/music.md.

Usage:
  music_midi.py <file.MID>            summary of one file (tracks, tempo, channels, programs, texts)
  music_midi.py <file.MID> --json     full view as JSON
  music_midi.py --check <dir>         all *.MID in a directory: table + structural consistency check

Example:
  python3 scripts/music_midi.py --check ".../WARFB/FILE/BINARY/MUSIC"

What is computed:
  - length in seconds from the tempo map (meta 0x51 from all tracks), up to the last event
    and up to the last note-on;
  - per channel: note count, note range, program changes together with the bank select
    state (CC0 = MSB, CC32 = LSB) at the moment of the change;
  - controllers used (CC), NRPN (CC99/98 - the AWE32 uses NRPN with MSB 127), SysEx;
  - meta texts: track name (0x03), text (0x01), copyright (0x02), instrument (0x04),
    lyric (0x05), marker (0x06), cue (0x07).
"""
import glob, json, os, struct, sys

META_TEXT = {1: 'text', 2: 'copyright', 3: 'track_name', 4: 'instrument', 5: 'lyric', 6: 'marker', 7: 'cue'}


def read_vlq(d, pos):
    val = 0
    while True:
        b = d[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            return val, pos


def parse_track(d, start, end, idx):
    """Return (events, end position) of one MTrk; event = (tick, kind, data)."""
    events, pos, tick, status = [], start, 0, None
    while pos < end:
        delta, pos = read_vlq(d, pos)
        tick += delta
        b = d[pos]
        if b & 0x80:
            pos += 1
            if b < 0xF0:
                status = b  # running status applies to channel messages only
        else:
            if status is None:
                raise ValueError('track %d: data byte without status at offset %d' % (idx, pos))
            b = status
        if b == 0xFF:
            mtype = d[pos]
            ln, pos = read_vlq(d, pos + 1)
            events.append((tick, 'meta', (mtype, d[pos:pos + ln])))
            pos += ln
            if mtype == 0x2F:
                break
        elif b in (0xF0, 0xF7):
            ln, pos = read_vlq(d, pos)
            events.append((tick, 'sysex', bytes([b]) + d[pos:pos + ln]))
            pos += ln
        else:
            kind, ch = b & 0xF0, b & 0x0F
            n = 1 if kind in (0xC0, 0xD0) else 2
            args = tuple(d[pos:pos + n])
            pos += n
            events.append((tick, 'chan', (kind, ch) + args))
    return events, pos


def tempo_seconds(tempo_map, tick, division):
    """Seconds at `tick`; tempo_map = sorted list of (tick, microseconds per quarter note)."""
    if division & 0x8000:  # SMPTE: -fps, ticks per frame
        fps = 256 - (division >> 8)
        return tick / (fps * (division & 0xFF))
    sec, last_tick, uspq = 0.0, 0, 500000
    for t, u in tempo_map:
        if t >= tick:
            break
        sec += (t - last_tick) * uspq / 1e6 / division
        last_tick, uspq = t, u
    return sec + (tick - last_tick) * uspq / 1e6 / division


def parse_midi(path):
    d = open(path, 'rb').read()
    if d[:4] != b'MThd':
        raise ValueError('%s: no MThd' % path)
    hlen, fmt, ntrks, division = struct.unpack_from('>IHHH', d, 4)
    pos = 8 + hlen
    tracks = []
    while pos + 8 <= len(d):
        cid, ln = struct.unpack_from('>4sI', d, pos)
        if cid != b'MTrk':
            pos += 8 + ln
            continue
        evs, endpos = parse_track(d, pos + 8, pos + 8 + ln, len(tracks))
        tracks.append({'events': evs, 'declared_len': ln, 'parsed_len': endpos - pos - 8,
                       'end_of_track': bool(evs) and evs[-1][1] == 'meta' and evs[-1][2][0] == 0x2F})
        pos += 8 + ln
    tempo_map = sorted((t, int.from_bytes(v[1], 'big')) for tr in tracks for t, k, v in tr['events']
                       if k == 'meta' and v[0] == 0x51)
    last_tick = max((tr['events'][-1][0] for tr in tracks if tr['events']), default=0)
    last_note_tick = 0
    channels, texts, sysex, timesigs = {}, [], [], []
    bank = {}  # channel -> [msb, lsb]; controller state is per channel, shared by all tracks
    # merge events of all tracks in time order so bank select state is correct across tracks
    merged = sorted(((t, ti, n, k, v) for ti, tr in enumerate(tracks) for n, (t, k, v) in enumerate(tr['events'])),
                    key=lambda e: (e[0], e[1], e[2]))
    for tr in tracks:
        tr['names'] = []
    for tick, ti, _, kind, v in merged:
        if kind == 'meta':
            mtype, body = v
            if mtype in META_TEXT:
                txt = body.decode('latin-1')
                texts.append({'track': ti, 'tick': tick, 'type': META_TEXT[mtype], 'text': txt})
                if mtype == 3:
                    tracks[ti]['names'].append(txt)
            elif mtype == 0x58:
                timesigs.append((tick, body[0], 2 ** body[1]))
            continue
        if kind == 'sysex':
            sysex.append({'track': ti, 'tick': tick, 'hex': v.hex()})
            continue
        k, ch = v[0], v[1]
        c = channels.setdefault(ch, {'notes': 0, 'lo': 127, 'hi': 0, 'programs': [], 'ccs': {},
                                     'nrpn': set(), 'tracks': set(), '_nrpn': [None, None]})
        c['tracks'].add(ti)
        b = bank.setdefault(ch, [0, 0])
        if k == 0x90 and v[3] > 0:
            c['notes'] += 1
            c['lo'], c['hi'] = min(c['lo'], v[2]), max(c['hi'], v[2])
            last_note_tick = max(last_note_tick, tick)
        elif k == 0xB0:
            cc, val = v[2], v[3]
            c['ccs'][cc] = c['ccs'].get(cc, 0) + 1
            if cc == 0:
                b[0] = val
            elif cc == 32:
                b[1] = val
            elif cc == 99:
                c['_nrpn'][0] = val
            elif cc == 98:
                c['_nrpn'][1] = val
            elif cc == 6 and None not in c['_nrpn']:
                c['nrpn'].add(tuple(c['_nrpn']))
        elif k == 0xC0:
            c['programs'].append({'tick': tick, 'bank_msb': b[0], 'bank_lsb': b[1], 'program': v[2], 'track': ti})
    for c in channels.values():
        del c['_nrpn']
        c['tracks'] = sorted(c['tracks'])
        c['nrpn'] = sorted(c['nrpn'])
    return {
        'file': os.path.basename(path), 'size': len(d), 'format': fmt, 'ntrks_header': ntrks,
        'ntrks_found': len(tracks), 'division': division,
        'tracks_ok': len(tracks) == ntrks and all(t['end_of_track'] and t['parsed_len'] == t['declared_len']
                                                  for t in tracks),
        'tempo_map': tempo_map, 'time_signatures': timesigs,
        'initial_bpm': round(60e6 / tempo_map[0][1], 2) if tempo_map else 120.0,
        'last_tick': last_tick, 'seconds': round(tempo_seconds(tempo_map, last_tick, division), 2),
        'seconds_last_note': round(tempo_seconds(tempo_map, last_note_tick, division), 2),
        'channels': {ch: channels[ch] for ch in sorted(channels)},
        'track_names': [t['names'] for t in tracks], 'texts': texts, 'sysex': sysex,
    }


def programs_used(m):
    """Set of (bank_msb, bank_lsb, program, channel) actually sounding notes.
    Channel index 9 (MIDI channel 10) is the GM drum channel. Channels with notes but no
    program change are reported with program None (default program 0 / standard kit)."""
    out = set()
    for ch, c in m['channels'].items():
        if not c['notes']:
            continue
        for p in c['programs']:
            out.add((p['bank_msb'], p['bank_lsb'], p['program'], ch))
        if not c['programs']:
            out.add((0, 0, None, ch))
    return out


def summary(m):
    out = ['%s: SMF format %d, tracks %d/%d, PPQN %d, initial tempo %.1f BPM (%d tempo events), '
           'length %.2f s (last note %.2f s), track structure %s'
           % (m['file'], m['format'], m['ntrks_found'], m['ntrks_header'], m['division'], m['initial_bpm'],
              len(m['tempo_map']), m['seconds'], m['seconds_last_note'], 'OK' if m['tracks_ok'] else 'ERROR')]
    if m['time_signatures']:
        out.append('  time signature: %s' % ', '.join('%d/%d@%d' % (n, dd, t) for t, n, dd in m['time_signatures'][:4]))
    for ch, c in m['channels'].items():
        progs = sorted({(p['bank_msb'], p['bank_lsb'], p['program']) for p in c['programs']})
        out.append('  channel %2d: notes %5d, range %3d-%3d, programs (msb/lsb:prog) %s, CC %s%s' % (
            ch + 1, c['notes'], c['lo'], c['hi'],
            ' '.join('%d/%d:%d' % p for p in progs) or '-',
            ','.join(str(k) for k in sorted(c['ccs'])),
            (', NRPN %s' % c['nrpn']) if c['nrpn'] else ''))
    for t in m['texts']:
        out.append('  [trk %d @%d] %s: %r' % (t['track'], t['tick'], t['type'], t['text']))
    for s in m['sysex']:
        out.append('  [trk %d @%d] sysex %s' % (s['track'], s['tick'], s['hex']))
    return '\n'.join(out)


def find_midis(directory):
    return sorted(p for p in glob.glob(os.path.join(directory, '*')) if p.lower().endswith('.mid'))


def check(directory):
    rows, bad = [], 0
    for p in find_midis(directory):
        m = parse_midi(p)
        bad += not m['tracks_ok']
        chans = [ch + 1 for ch, c in m['channels'].items() if c['notes']]
        rows.append('%-13s fmt %d trk %2d ppqn %4d bpm %6.1f %7.2f s  channels %s' % (
            m['file'], m['format'], m['ntrks_found'], m['division'], m['initial_bpm'], m['seconds'],
            ','.join(map(str, chans))))
    rows.append('files: %d, structural errors: %d' % (len(rows), bad))
    return '\n'.join(rows)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == '--check':
        print(check(argv[1]))
    elif '--json' in argv:
        print(json.dumps(parse_midi(argv[0]), indent=1, default=list))
    else:
        print(summary(parse_midi(argv[0])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
