"""Convert the game's SoundFont 1.0 bank (WARINTR3.SBK) into a SoundFont 2.01 file that
FluidSynth / Polyphone can load (FluidSynth only accepts SF2). Pure Python. Description: notes/music.md.

Usage:
  music_sbk2sf2.py <in.SBK> <out.sf2> [--bank N] [--no-envelopes]

  --bank N          bank number written into the presets (default 1 = AWE32 user bank slot the
                    game's MIDI files select with CC0=1; use 0 to keep the bank as stored in the SBK)
  --no-envelopes    also drop the volume envelope generators (33..38)

Example:
  python3 scripts/music_sbk2sf2.py ".../WARFB/FILE/BINARY/SOUND/WARINTR3.SBK" extracted/music/WARINTR3_bank1.sf2

What is converted, and what is a hypothesis:
  - structure (presets, zones, key ranges, sample IDs, loop offsets, tuning): verified by the
    pitch self-test in music_render.py;
  - SF1 shdr has no sample rate: 44100 Hz is written (sample names TRUMPC3..C6 match their
    measured pitch only at 44100 Hz);
  - SF1 generator 55 is taken as "root key in cents" (6000 = key 60, 7200 = key 72) and written
    as overridingRootKey (58) + fineTune; consistent with all 6 zones;
  - filter, modulation envelope and LFO generators (5, 8-11, 21-30) are DROPPED: their SF1 units
    evidently differ from SF2 (e.g. initialFilterFc=0 would close the filter completely in SF2);
  - volume envelope (33-38), attenuation, chorus/reverb sends are kept with SF2 units (hypothesis:
    values such as release 631-2736 timecents = 1.4-4.8 s look plausible). Timbre is approximate.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import music_sf2  # noqa: E402

DROP_ALWAYS = {5, 6, 7, 8, 9, 10, 11, 12, 13, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 55}
VOL_ENV = {33, 34, 35, 36, 37, 38}
SAMPLE_RATE = 44100


def riff_chunk(cid, body):
    pad = b'\0' if len(body) & 1 else b''
    return struct.pack('<4sI', cid.encode(), len(body)) + body + pad


def list_chunk(ltype, chunks):
    return riff_chunk('LIST', ltype.encode() + b''.join(chunks))


def zstr(s, even=True):
    b = s.encode('latin-1', 'replace') + b'\0'
    if even and len(b) & 1:
        b += b'\0'
    return b


def name20(s):
    return s.encode('latin-1', 'replace')[:19].ljust(20, b'\0')


def encode_gen(oper, val):
    if oper in music_sf2.RANGE_GENS:
        return struct.pack('<HBB', oper, val[0], val[1])
    return struct.pack('<Hh' if isinstance(val, int) and val < 0 else '<HH', oper, val)


def zone_gens(zone, is_instrument, keep_env):
    """Ordered generator list for one zone (SF2 requires keyRange, velRange first, link generator last)."""
    z = {k: v for k, v in zone.items() if k not in DROP_ALWAYS and (keep_env or k not in VOL_ENV)}
    if is_instrument and 55 in zone and 58 not in z:
        z[58] = zone[55] // 100
        if zone[55] % 100:
            z[52] = z.get(52, 0) + zone[55] % 100
    last = 53 if is_instrument else 41
    order = [k for k in (43, 44) if k in z] + sorted(k for k in z if k not in (43, 44, last)) + \
            ([last] if last in z else [])
    return [(k, z[k]) for k in order]


def build_list(items, is_instrument, keep_env):
    """items: list of zone lists -> (bag bytes, gen bytes, bag start indices)."""
    bags, gens, starts = b'', b'', []
    ngen = nbag = 0
    for zones in items:
        starts.append(nbag)
        for zone in zones:
            bags += struct.pack('<HH', ngen, 0)
            nbag += 1
            for oper, val in zone_gens(zone, is_instrument, keep_env):
                gens += encode_gen(oper, val)
                ngen += 1
    bags += struct.pack('<HH', ngen, 0)  # terminal bag
    gens += b'\0' * 4  # terminal generator
    return bags, gens, starts, nbag


def convert(sf, bank=1, keep_env=True):
    info = sf['info']
    info_chunks = [riff_chunk('ifil', struct.pack('<HH', 2, 1)),
                   riff_chunk('isng', zstr(info.get('isng', 'EMU8000'))),
                   riff_chunk('INAM', zstr(info.get('INAM', 'converted SBK') + ' (from SBK)'))]
    for key in ('ICRD', 'IENG', 'IPRD', 'ICOP', 'ICMT'):
        if key in info:
            info_chunks.append(riff_chunk(key, zstr(info[key])))
    info_chunks.append(riff_chunk('ISFT', zstr('music_sbk2sf2.py')))

    smpl = sf['_data'][sf['smpl_offset']:sf['smpl_offset'] + sf['smpl_bytes']]
    smpl += b'\0' * (46 * 2)  # SF2 wants at least 46 zero frames after the last sample

    pbag, pgen, pstarts, npbag = build_list([p['zones'] for p in sf['presets']], False, keep_env)
    phdr = b''.join(struct.pack('<20sHHHIII', name20(p['name']), p['program'], bank, pstarts[i], 0, 0, 0)
                    for i, p in enumerate(sf['presets']))
    phdr += struct.pack('<20sHHHIII', name20('EOP'), 0, 0, npbag, 0, 0, 0)

    ibag, igen, istarts, nibag = build_list([ins['zones'] for ins in sf['instruments']], True, keep_env)
    inst = b''.join(struct.pack('<20sH', name20(ins['name'] or 'WarInst%d' % ins['id']), istarts[i])
                    for i, ins in enumerate(sf['instruments']))
    inst += struct.pack('<20sH', name20('EOI'), nibag)

    shdr = b''
    for s in sf['samples']:
        rate = s['rate'] or SAMPLE_RATE
        root = s['root_key'] if s['root_key'] is not None else 60
        shdr += struct.pack('<20sIIIIIBbHH', name20(s['name']), s['start'], s['end'], s['loop_start'],
                            s['loop_end'], rate, root, s['pitch_correction'], 0, 1)
    shdr += b'\0' * 46  # terminal EOS

    pdta = [riff_chunk('phdr', phdr), riff_chunk('pbag', pbag), riff_chunk('pmod', b'\0' * 10),
            riff_chunk('pgen', pgen), riff_chunk('inst', inst), riff_chunk('ibag', ibag),
            riff_chunk('imod', b'\0' * 10), riff_chunk('igen', igen), riff_chunk('shdr', shdr)]
    body = b'sfbk' + list_chunk('INFO', info_chunks) + list_chunk('sdta', [riff_chunk('smpl', smpl)]) + \
        list_chunk('pdta', pdta)
    return struct.pack('<4sI', b'RIFF', len(body)) + body


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    bank = int(argv[argv.index('--bank') + 1]) if '--bank' in argv else 1
    sf = music_sf2.parse_sf2(argv[0])
    data = convert(sf, bank=bank, keep_env='--no-envelopes' not in argv)
    os.makedirs(os.path.dirname(os.path.abspath(argv[1])), exist_ok=True)
    with open(argv[1], 'wb') as f:
        f.write(data)
    back = music_sf2.parse_sf2(argv[1])  # round trip through our own SF2 parser
    print('%s: %d B, SF2 %s, presets %s, instruments %d, samples %d, warnings %s' % (
        argv[1], len(data), back['info']['ifil'],
        ['%d:%d %s' % (p['bank'], p['program'], p['name']) for p in back['presets']],
        len(back['instruments']), len(back['samples']), back['warnings'] or 'none'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
