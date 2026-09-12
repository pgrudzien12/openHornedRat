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


def summary(sf):
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


def main(argv):
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
        print(summary(sf))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
