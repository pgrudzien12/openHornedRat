"""Pure-Python parsers for MIDI, SoundFont, SFX and WAV game audio formats."""

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
import glob, json, os, struct

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


def midi_summary(m):
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


def midi_main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == '--check':
        print(check(argv[1]))
    elif '--json' in argv:
        print(json.dumps(parse_midi(argv[0]), indent=1, default=list))
    else:
        print(midi_summary(parse_midi(argv[0])))
    return 0



"""Pure-Python SoundFont parser (RIFF 'sfbk', version 1.x = SBK and 2.x = SF2).
Main target: SOUND/WARINTR3.SBK (user bank for the Sound Blaster AWE32 / EMU8000).
Description: notes/music.md.

Usage:
  music_sf2.py <file.SBK|.SF2>                              summary: INFO, presets, instruments, samples
  music_sf2.py <file> --json                                full view as JSON
  music_sf2.py <file> --extract-samples <dir> [--rate N]    write RAM samples as 16-bit mono WAV

Example:
  python3 scripts/music_sf2.py ".../WARFB/FILE/BINARY/SOUND/WARINTR3.SBK"

Layout (SoundFont 2.01 spec; SoundFont 1.0 differences observed in WARINTR3.SBK):
  RIFF sfbk
    LIST INFO  ifil, isng, INAM, irom, iver, ICRD, IENG, IPRD, ICOP, ICMT, ISFT
    LIST sdta  [snam: SF1 only, 20-byte sample names]  smpl (16-bit PCM LE, all samples concatenated)
    LIST pdta  phdr(38) pbag(4) pmod(10) pgen(4) inst(22) ibag(4) imod(10) igen(4)
               shdr: SF2 = 46 B per record + terminal EOS record;
                     SF1 = 16 B per record (start, end, loop start, loop end), no rate/root key,
                           no terminal record, names come from snam
  phdr/inst/bag lists end with a terminal record (EOP/EOI) that is not counted.
  SF1 pmod/imod are 6-byte stubs in WARINTR3.SBK (no modulators), so they are read leniently.
"""
import json, os, struct, sys, wave

# SF2 generator numbers (SF1 uses the same numbers for everything seen here, except 55,
# which is reserved in SF2 - its SF1 meaning is unknown)
GEN_NAMES = {
    0: 'startAddrsOffset', 1: 'endAddrsOffset', 2: 'startloopAddrsOffset', 3: 'endloopAddrsOffset',
    5: 'modLfoToPitch', 8: 'initialFilterFc', 9: 'initialFilterQ', 10: 'modLfoToFilterFc',
    11: 'modEnvToFilterFc', 15: 'chorusEffectsSend', 16: 'reverbEffectsSend', 17: 'pan',
    21: 'delayModLFO', 22: 'freqModLFO', 25: 'delayModEnv', 26: 'attackModEnv', 28: 'decayModEnv',
    29: 'sustainModEnv', 30: 'releaseModEnv', 33: 'delayVolEnv', 34: 'attackVolEnv', 35: 'holdVolEnv',
    36: 'decayVolEnv', 37: 'sustainVolEnv', 38: 'releaseVolEnv', 41: 'instrument', 43: 'keyRange',
    44: 'velRange', 48: 'initialAttenuation', 51: 'coarseTune', 52: 'fineTune', 53: 'sampleID',
    54: 'sampleModes', 56: 'scaleTuning', 57: 'exclusiveClass', 58: 'overridingRootKey',
}
RANGE_GENS = (43, 44)
UNSIGNED_GENS = (41, 53, 54, 57, 58)

# General MIDI program names (0..127), used to describe presets and MIDI programs
GM_PROGRAMS = [
    'Acoustic Grand Piano', 'Bright Acoustic Piano', 'Electric Grand Piano', 'Honky-tonk Piano',
    'Electric Piano 1', 'Electric Piano 2', 'Harpsichord', 'Clavi', 'Celesta', 'Glockenspiel',
    'Music Box', 'Vibraphone', 'Marimba', 'Xylophone', 'Tubular Bells', 'Dulcimer', 'Drawbar Organ',
    'Percussive Organ', 'Rock Organ', 'Church Organ', 'Reed Organ', 'Accordion', 'Harmonica',
    'Tango Accordion', 'Acoustic Guitar (nylon)', 'Acoustic Guitar (steel)', 'Electric Guitar (jazz)',
    'Electric Guitar (clean)', 'Electric Guitar (muted)', 'Overdriven Guitar', 'Distortion Guitar',
    'Guitar harmonics', 'Acoustic Bass', 'Electric Bass (finger)', 'Electric Bass (pick)',
    'Fretless Bass', 'Slap Bass 1', 'Slap Bass 2', 'Synth Bass 1', 'Synth Bass 2', 'Violin', 'Viola',
    'Cello', 'Contrabass', 'Tremolo Strings', 'Pizzicato Strings', 'Orchestral Harp', 'Timpani',
    'String Ensemble 1', 'String Ensemble 2', 'SynthStrings 1', 'SynthStrings 2', 'Choir Aahs',
    'Voice Oohs', 'Synth Voice', 'Orchestra Hit', 'Trumpet', 'Trombone', 'Tuba', 'Muted Trumpet',
    'French Horn', 'Brass Section', 'SynthBrass 1', 'SynthBrass 2', 'Soprano Sax', 'Alto Sax',
    'Tenor Sax', 'Baritone Sax', 'Oboe', 'English Horn', 'Bassoon', 'Clarinet', 'Piccolo', 'Flute',
    'Recorder', 'Pan Flute', 'Blown Bottle', 'Shakuhachi', 'Whistle', 'Ocarina', 'Lead 1 (square)',
    'Lead 2 (sawtooth)', 'Lead 3 (calliope)', 'Lead 4 (chiff)', 'Lead 5 (charang)', 'Lead 6 (voice)',
    'Lead 7 (fifths)', 'Lead 8 (bass + lead)', 'Pad 1 (new age)', 'Pad 2 (warm)', 'Pad 3 (polysynth)',
    'Pad 4 (choir)', 'Pad 5 (bowed)', 'Pad 6 (metallic)', 'Pad 7 (halo)', 'Pad 8 (sweep)',
    'FX 1 (rain)', 'FX 2 (soundtrack)', 'FX 3 (crystal)', 'FX 4 (atmosphere)', 'FX 5 (brightness)',
    'FX 6 (goblins)', 'FX 7 (echoes)', 'FX 8 (sci-fi)', 'Sitar', 'Banjo', 'Shamisen', 'Koto',
    'Kalimba', 'Bag pipe', 'Fiddle', 'Shanai', 'Tinkle Bell', 'Agogo', 'Steel Drums', 'Woodblock',
    'Taiko Drum', 'Melodic Tom', 'Synth Drum', 'Reverse Cymbal', 'Guitar Fret Noise', 'Breath Noise',
    'Seashore', 'Bird Tweet', 'Telephone Ring', 'Helicopter', 'Applause', 'Gunshot',
]

PDTA_RECORDS = {  # chunk id -> (record size, struct format)
    'phdr': (38, '<20sHHHIII'), 'pbag': (4, '<HH'), 'pmod': (10, '<HHhHH'), 'pgen': (4, '<HH'),
    'inst': (22, '<20sH'), 'ibag': (4, '<HH'), 'imod': (10, '<HHhHH'), 'igen': (4, '<HH'),
    'shdr': (46, '<20sIIIIIBbHH'),
}
SF1_SHDR = (16, '<IIII')


def cstr(b):
    return b.split(b'\0', 1)[0].decode('latin-1').rstrip()


def iter_chunks(data, start, end):
    """Yield (id, data offset, size) for consecutive RIFF chunks in [start, end)."""
    pos = start
    while pos + 8 <= end:
        cid, size = struct.unpack_from('<4sI', data, pos)
        yield cid.decode('latin-1'), pos + 8, size
        pos += 8 + size + (size & 1)  # chunks are padded to an even size


def gen_value(oper, raw):
    """Generator amount: ranges as (lo, hi), indices unsigned, everything else signed."""
    if oper in RANGE_GENS:
        return (raw & 0xFF, raw >> 8)
    if oper in UNSIGNED_GENS:
        return raw
    return raw - 0x10000 if raw >= 0x8000 else raw


def parse_sf2(path):
    data = open(path, 'rb').read()
    riff, total, form = struct.unpack_from('<4sI4s', data, 0)
    if riff != b'RIFF' or form != b'sfbk':
        raise ValueError('%s: not a RIFF sfbk file' % path)
    sf = {'file': os.path.basename(path), 'file_size': len(data), 'riff_size_ok': total + 8 == len(data),
          'info': {}, 'smpl_offset': None, 'smpl_bytes': 0, 'warnings': []}
    raw, snam, major = {}, [], 2
    for cid, off, size in iter_chunks(data, 12, len(data)):
        if cid != 'LIST':
            continue
        ltype = data[off:off + 4].decode('latin-1')
        for sid, soff, ssize in iter_chunks(data, off + 4, off + size):
            body = data[soff:soff + ssize]
            if ltype == 'INFO':
                if sid in ('ifil', 'iver'):
                    sf['info'][sid] = '%d.%02d' % struct.unpack('<HH', body)
                    if sid == 'ifil':
                        major = struct.unpack('<H', body[:2])[0]
                else:
                    sf['info'][sid] = cstr(body)
            elif ltype == 'sdta' and sid == 'smpl':
                sf['smpl_offset'], sf['smpl_bytes'] = soff, ssize
            elif ltype == 'sdta' and sid == 'snam':
                snam = [cstr(body[i:i + 20]) for i in range(0, ssize - ssize % 20, 20)]
            elif ltype == 'pdta':
                rsize, fmt = SF1_SHDR if (major == 1 and sid == 'shdr') else PDTA_RECORDS[sid]
                if ssize % rsize:
                    sf['warnings'].append('%s: size %d is not a multiple of %d (read %d records)'
                                          % (sid, ssize, rsize, ssize // rsize))
                raw[sid] = [struct.unpack_from(fmt, body, i) for i in range(0, ssize - rsize + 1, rsize)]
    sf['version_major'] = major

    def zones(bags, gens, lo, hi):
        """Zones (dict generator -> value) for bags [lo, hi)."""
        out = []
        for b in range(lo, hi):
            g0, g1 = bags[b][0], bags[b + 1][0]
            out.append({oper: gen_value(oper, amt) for oper, amt in gens[g0:g1]})
        return out

    samples = []
    if major == 1:
        for i, (start, end, sl, el) in enumerate(raw['shdr']):
            samples.append({'id': i, 'name': snam[i] if i < len(snam) else '', 'start': start, 'end': end,
                            'loop_start': sl, 'loop_end': el, 'rate': None, 'root_key': None,
                            'pitch_correction': 0, 'link': 0, 'type': 0, 'rom': False, 'frames': end - start})
    else:
        for i, (name, start, end, sl, el, rate, pitch, corr, link, stype) in enumerate(raw['shdr'][:-1]):
            samples.append({'id': i, 'name': cstr(name), 'start': start, 'end': end, 'loop_start': sl,
                            'loop_end': el, 'rate': rate, 'root_key': pitch, 'pitch_correction': corr,
                            'link': link, 'type': stype, 'rom': bool(stype & 0x8000), 'frames': end - start})
    for s in samples:
        s['in_smpl'] = 0 <= s['start'] <= s['end'] <= sf['smpl_bytes'] // 2
    instruments = []
    for i in range(len(raw['inst']) - 1):
        name, bag = raw['inst'][i]
        zs = zones(raw['ibag'], raw['igen'], bag, raw['inst'][i + 1][1])
        instruments.append({'id': i, 'name': cstr(name), 'zones': zs,
                            'samples': sorted({z[53] for z in zs if 53 in z})})
    presets = []
    for i in range(len(raw['phdr']) - 1):
        name, prog, bank, bag, lib, genre, morph = raw['phdr'][i]
        zs = zones(raw['pbag'], raw['pgen'], bag, raw['phdr'][i + 1][3])
        presets.append({'name': cstr(name), 'bank': bank, 'program': prog, 'zones': zs,
                        'instruments': sorted({z[41] for z in zs if 41 in z})})
    sf.update(presets=presets, instruments=instruments, samples=samples)
    sf['_data'] = data
    return sf


def gm_name(bank, program):
    if bank == 128:
        return 'Drum kit %d' % program
    return GM_PROGRAMS[program] if 0 <= program < 128 else '?'


def sf2_summary(sf):
    out = ['%s: %d B, RIFF sfbk version %s, RIFF size %s' % (
        sf['file'], sf['file_size'], sf['info'].get('ifil'), 'matches' if sf['riff_size_ok'] else 'MISMATCH')]
    for k, v in sf['info'].items():
        out.append('  INFO %s = %r' % (k, v))
    for w in sf['warnings']:
        out.append('  warning: ' + w)
    rom = sum(1 for s in sf['samples'] if s['rom'])
    out.append('  smpl: %d B = %d 16-bit frames; presets %d, instruments %d, samples %d (ROM: %d)'
               % (sf['smpl_bytes'], sf['smpl_bytes'] // 2, len(sf['presets']), len(sf['instruments']),
                  len(sf['samples']), rom))
    out.append('  Presets:')
    for p in sf['presets']:
        inames = ', '.join('%d:%s' % (i, sf['instruments'][i]['name'] or '?') for i in p['instruments'])
        out.append('    bank %3d prog %3d  %-20s (GM: %s)  instruments: %s'
                   % (p['bank'], p['program'], p['name'], gm_name(p['bank'], p['program']), inames))
    out.append('  Instruments:')
    for ins in sf['instruments']:
        out.append('    %2d %-20r zones %d, samples %s' % (ins['id'], ins['name'], len(ins['zones']), ins['samples']))
        for z in ins['zones']:
            desc = ' '.join('%s=%s' % (GEN_NAMES.get(k, 'gen%d' % k), v) for k, v in sorted(z.items()))
            out.append('         ' + desc)
    out.append('  Samples:')
    for s in sf['samples']:
        out.append('    %2d %-20s %s, %7d frames, loop %d..%d, %s%s'
                   % (s['id'], s['name'], ('%d Hz' % s['rate']) if s['rate'] else 'rate n/a (SF1)',
                      s['frames'], s['loop_start'] - s['start'], s['loop_end'] - s['start'],
                      'inside smpl' if s['in_smpl'] else 'OUTSIDE smpl', ' ROM' if s['rom'] else ''))
    return '\n'.join(out)


def sample_pcm(sf, s):
    """Raw 16-bit little-endian PCM bytes of one sample."""
    base = sf['smpl_offset']
    return sf['_data'][base + 2 * s['start']:base + 2 * s['end']]


def extract_samples(sf, outdir, rate=None):
    """Write RAM samples (not ROM) as WAV. SF1 has no rate field, so `rate` (default 44100) is used."""
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for s in sf['samples']:
        if s['rom'] or not s['in_smpl']:
            continue
        path = os.path.join(outdir, '%02d_%s.wav' % (s['id'], s['name'].replace(' ', '_').replace('.', '_')))
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate or s['rate'] or 44100)
            w.writeframes(sample_pcm(sf, s))
        paths.append(path)
    return paths


def sf2_main(argv):
    if not argv:
        print(__doc__)
        return 1
    sf = parse_sf2(argv[0])
    if '--json' in argv:
        print(json.dumps({k: v for k, v in sf.items() if not k.startswith('_')}, indent=1, default=str))
    elif '--extract-samples' in argv:
        rate = int(argv[argv.index('--rate') + 1]) if '--rate' in argv else None
        for p in extract_samples(sf, argv[argv.index('--extract-samples') + 1], rate):
            print(p)
    else:
        print(sf2_summary(sf))
    return 0



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
    from .script import load_battle
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


def sfx_main(argv):
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


def extract_sfx_effects(root, out_dir):
    """Extract sound effects with pitch applied into out_dir/effects, raw WAVs into out_dir/raw."""
    out_dir_path = os.path.abspath(str(out_dir))
    raw_dir = os.path.join(out_dir_path, "raw")
    eff_dir = os.path.join(out_dir_path, "effects")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(eff_dir, exist_ok=True)

    install_analysis = analyse_install(str(root))
    sound_dir = resolve(str(root), 'file\\binary\\sound') or resolve(str(root), 'binary\\sound')
    if sound_dir and os.path.exists(sound_dir):
        for wpath in glob.glob(os.path.join(sound_dir, '**', '*'), recursive=True):
            if wpath.upper().endswith('.WAV'):
                rel = os.path.relpath(wpath, sound_dir)
                dest = os.path.join(raw_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(wpath, 'rb') as f_in, open(dest, 'wb') as f_out:
                    f_out.write(f_in.read())

    for pk in install_analysis.get('packets', []):
        pname = pk.get('name')
        if not pname or not pk.get('effects'):
            continue
        pk_dir = os.path.join(eff_dir, pname)
        os.makedirs(pk_dir, exist_ok=True)
        for eff in pk['effects']:
            sample_idx = eff.get('sample', 0)
            samples = pk.get('samples', [])
            if sample_idx >= len(samples):
                continue
            s_info = samples[sample_idx]
            wfile = s_info.get('file')
            if not wfile:
                continue
            wpath = os.path.join(str(root), wfile)
            if not os.path.exists(wpath):
                wpath = resolve(str(root), wfile)
            if not wpath or not os.path.exists(wpath):
                continue
            try:
                with wave.open(wpath, 'rb') as r:
                    nch = r.getnchannels()
                    sw = r.getsampwidth()
                    frames = r.readframes(r.getnframes())
                pitch = eff.get('pitch', 11025)
                eff_name = eff.get('name', 'sfx_%d' % eff['index'])
                safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in eff_name)
                out_name = "%02d_%s_%dHz.wav" % (eff['index'], safe_name, pitch)
                out_path = os.path.join(pk_dir, out_name)
                with wave.open(out_path, 'wb') as w:
                    w.setnchannels(nch)
                    w.setsampwidth(sw)
                    w.setframerate(pitch)
                    w.writeframes(frames)
            except Exception:
                pass


def extract_speech(root, out_dir):
    """Extract speech WAV files from REMOTE/BINARY/GLUE/SPEECH/ to out_dir."""
    out_dir_path = os.path.abspath(str(out_dir))
    os.makedirs(out_dir_path, exist_ok=True)
    speech_dir = resolve(str(root), 'remote\\binary\\glue\\speech')
    if not speech_dir:
        speech_dir = find_path_ci(str(root), 'REMOTE/BINARY/GLUE/SPEECH')
    if speech_dir and os.path.exists(speech_dir):
        for fname in os.listdir(speech_dir):
            if fname.upper().endswith('.WAV'):
                src = os.path.join(speech_dir, fname)
                dest = os.path.join(out_dir_path, fname)
                with open(src, 'rb') as f_in, open(dest, 'wb') as f_out:
                    f_out.write(f_in.read())




"""Statistics and validity checks for the game's WAV files (sound effects and speech).

Walks the RIFF chunks by hand (does not trust the RIFF size field) and cross-checks with the
standard `wave` module. Covers FILE/BINARY/SOUND/** and REMOTE/BINARY/GLUE/SPEECH/ (UPDATE/BINARY
too, if it contains any WAV files).

Usage:
  sfx_wavstats.py <WARFB dir>                  summary per group
  sfx_wavstats.py <WARFB dir> --list           plus one line per file
  sfx_wavstats.py <WARFB dir> --json OUT       export per-file data (e.g. extracted/sfx/wavstats.json)

Example:
  python3 scripts/sfx_wavstats.py ".../WARFB" --json extracted/sfx/wavstats.json
"""
import collections, glob, json, os, struct, sys, wave

GROUPS = (('SOUND', ('FILE/BINARY/SOUND', 'UPDATE/BINARY/SOUND')),
          ('SPEECH', ('REMOTE/BINARY/GLUE/SPEECH',)))


def find_path_ci(root, rel):
    cur = root
    for part in rel.split('/'):
        try:
            cur = next((os.path.join(cur, n) for n in os.listdir(cur) if n.lower() == part.lower()), None)
        except OSError:
            return None
        if cur is None:
            return None
    return cur


def analyse(path):
    d = open(path, 'rb').read()
    r = {'bytes': len(d), 'problems': [], 'chunks': []}
    if d[:4] != b'RIFF' or d[8:12] != b'WAVE':
        r['problems'].append('not RIFF WAVE')
        return r
    r['riff_size'] = struct.unpack_from('<I', d, 4)[0]
    o = 12
    while o + 8 <= len(d):
        tag, n = d[o:o + 4], struct.unpack_from('<I', d, o + 4)[0]
        r['chunks'].append((tag.decode('latin-1'), o, n))
        if tag == b'fmt ':
            tagv, ch, rate, avg, align, bits = struct.unpack_from('<HHIIHH', d, o + 8)
            r.update(format_tag=tagv, channels=ch, rate=rate, avg_bytes=avg, block_align=align,
                     bits=bits, fmt_size=n)
            if n > 16:
                r['fmt_extra'] = d[o + 24:o + 8 + n].hex()
        elif tag == b'data':
            r['data_offset'], r['data_size'] = o + 8, n
        elif tag == b'LIST':
            r['list_text'] = d[o + 8:o + 8 + n].decode('latin-1')
        o += 8 + n + (n & 1)
    r['end_of_chunks'] = o
    p = r['problems']
    if 'format_tag' not in r or 'data_size' not in r:
        p.append('missing fmt or data chunk')
        return r
    if r['format_tag'] != 1:
        p.append('format tag %d (not PCM)' % r['format_tag'])
    if r['block_align'] != r['channels'] * r['bits'] // 8:
        p.append('block_align inconsistent')
    if r['avg_bytes'] != r['rate'] * r['block_align']:
        p.append('avg_bytes inconsistent')
    if r['data_offset'] + r['data_size'] > len(d):
        p.append('data chunk runs past end of file')
    if r['data_size'] % r['block_align']:
        p.append('data size not a multiple of block_align')
    if r['riff_size'] + 8 != len(d):
        r['riff_size_note'] = ('riff_size == data_size' if r['riff_size'] == r['data_size']
                               else 'riff_size + 8 - file = %d' % (r['riff_size'] + 8 - len(d)))
    if o not in (len(d), len(d) + 1):
        p.append('chunk walk ends at %d, file has %d bytes' % (o, len(d)))
    r['frames'] = r['data_size'] // r['block_align']
    r['seconds'] = r['frames'] / r['rate']
    try:
        with wave.open(path) as w:
            r['wave_module'] = 'ok'
            if (w.getnchannels(), w.getframerate(), w.getsampwidth() * 8, w.getnframes()) != \
                    (r['channels'], r['rate'], r['bits'], r['frames']):
                p.append('wave module disagrees')
    except Exception as e:
        r['wave_module'] = repr(e)
        p.append('wave module error: %r' % e)
    return r


def wavstats_main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    root = argv[0]
    out = argv[argv.index('--json') + 1] if '--json' in argv else None
    result = {}
    for group, dirs in GROUPS:
        files = []
        for rel in dirs:
            base = find_path_ci(root, rel)
            if base:
                files += sorted(p for p in glob.glob(os.path.join(base, '**', '*'), recursive=True)
                                if p.upper().endswith('.WAV'))
        stats = {os.path.relpath(p, root): analyse(p) for p in files}
        result[group] = stats
        fmt = collections.Counter()
        layout = collections.Counter()
        riff = collections.Counter()
        lists = collections.Counter()
        for s in stats.values():
            fmt[('PCM' if s.get('format_tag') == 1 else s.get('format_tag'), s.get('channels'),
                 s.get('rate'), s.get('bits'), s.get('fmt_size'))] += 1
            layout[' '.join(c[0] for c in s['chunks'])] += 1
            riff[s.get('riff_size_note', 'ok')] += 1
            if 'list_text' in s:
                lists[''.join(ch if 32 <= ord(ch) < 127 else '.' for ch in s['list_text'])] += 1
        secs = [s.get('seconds', 0) for s in stats.values()]
        print('== %s: %d files, %.1f MB, %.1f s total (%.1f min), shortest %.2f s, longest %.2f s'
              % (group, len(stats), sum(s['bytes'] for s in stats.values()) / 1e6, sum(secs),
                 sum(secs) / 60, min(secs or [0]), max(secs or [0])))
        for k, v in sorted(fmt.items(), key=str):
            print('   format %s ch=%s rate=%s bits=%s fmt_chunk=%s: %d' % (k + (v,)))
        for k, v in layout.items():
            print('   chunks [%s]: %d' % (k, v))
        for k, v in riff.items():
            print('   RIFF size field %s: %d' % (k, v))
        for k, v in lists.most_common(5):
            print('   LIST chunk text %r: %d' % (k, v))
        bad = {k: s['problems'] for k, s in stats.items() if s['problems']}
        print('   files with problems: %d %s' % (len(bad), bad if bad else ''))
        print('   wave module errors: %d' % sum(s.get('wave_module') != 'ok' for s in stats.values()))
        if '--list' in argv:
            for k, s in stats.items():
                print('   %-45s %d ch %5d Hz %2d bit %6.2f s %s' % (k, s.get('channels'), s.get('rate'),
                      s.get('bits'), s.get('seconds', 0), s.get('riff_size_note', '')))
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, 'w') as f:
            json.dump(result, f, indent=1)
        print('wrote %s' % out)
