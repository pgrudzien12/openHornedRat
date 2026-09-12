"""Music rendering helpers. Pure Python (stdlib); uses fluidsynth/ffmpeg only if installed.
Description: notes/music.md.

Usage:
  music_render.py selftest <WARFB>                     play key 60 and 72 on each SBK preset, measure the pitch
  music_render.py stem <WARFB> <SONG> <out.wav>        render ONLY the parts that use the game's SBK bank
                  [--rate 22050] [--seconds N]         (CC0=1 + program 52/54/57) with a simple sampler
  music_render.py verify <file.wav> [<file.MID>]       RMS/peak/duration, compared with the MIDI length
  music_render.py commands <WARFB> [<outdir>] [--run]  print (or run, if the tools exist) fluidsynth/ffmpeg
                                                       commands for full renders with a GM soundfont

Example:
  python3 scripts/music_render.py stem ".../WARFB" INTRO3 extracted/music/INTRO3_sbk_stem.wav
  python3 scripts/music_render.py verify extracted/music/INTRO3_sbk_stem.wav ".../WARFB/FILE/BINARY/MUSIC/INTRO3.MID"

The sampler is a verification tool, not a faithful EMU8000 emulation: linear interpolation,
continuous loops (sampleModes=1), attack/release from the volume envelope generators
(SF2 timecents - hypothesis for SF1), no filter, no modulation, mono output.
Everything else in the songs (strings, drums, timpani...) came from the AWE32 1 MB GM ROM
('irom=1MGM'), which is not part of the game, so a full render needs an external GM soundfont.
"""
import array, math, os, shutil, subprocess, sys, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import music_midi, music_sf2  # noqa: E402

SBK_REL = ('BINARY', 'SOUND', 'WARINTR3.SBK')
MUSIC_REL = ('BINARY', 'MUSIC')
SBK_RATE = 44100      # SF1 has no rate field; see notes/music.md
USER_BANK = 1         # AWE32 user bank slot selected by the MIDI files with CC0=1 (hypothesis)
GM_SOUNDFONT_CANDIDATES = ['/usr/share/sounds/sf2/FluidR3_GM.sf2', '/usr/share/soundfonts/FluidR3_GM.sf2',
                           '/usr/share/sounds/sf2/TimGM6mb.sf2', '/usr/share/soundfonts/default.sf2']


def find_ci(base, parts):
    """Case-insensitive path lookup below `base`; returns None when missing."""
    path = base
    for part in parts:
        if not os.path.isdir(path):
            return None
        match = [e for e in os.listdir(path) if e.lower() == part.lower()]
        if not match:
            return None
        path = os.path.join(path, match[0])
    return path


def game_file(install, *parts):
    """UPDATE/<parts> takes priority over FILE/<parts>."""
    for top in ('UPDATE', 'FILE'):
        p = find_ci(install, (top,) + parts)
        if p and os.path.exists(p):
            return p
    return None


def song_path(install, song):
    name = song if song.lower().endswith('.mid') else song + '.MID'
    return game_file(install, *MUSIC_REL, name)


def timecents_to_s(tc, default, cap):
    return default if tc is None else min(cap, 2.0 ** (tc / 1200.0))


class Sampler:
    """Minimal SoundFont zone player for a parsed SBK/SF2 (music_sf2.parse_sf2)."""

    def __init__(self, sf, rate):
        self.sf, self.rate = sf, rate
        self.pcm = {s['id']: array.array('h', music_sf2.sample_pcm(sf, s)) for s in sf['samples']}
        self.presets = {p['program']: p for p in sf['presets']}

    def voices_for(self, program, key, velocity):
        preset = self.presets.get(program)
        if not preset:
            return []
        out = []
        for pz in preset['zones']:
            if 41 not in pz or not (pz.get(43, (0, 127))[0] <= key <= pz.get(43, (0, 127))[1]):
                continue
            for z in self.sf['instruments'][pz[41]]['zones']:
                lo, hi = z.get(43, (0, 127))
                if 53 not in z or not lo <= key <= hi:
                    continue
                s = self.sf['samples'][z[53]]
                rate = s['rate'] or SBK_RATE
                root = z[58] if 58 in z else (z[55] / 100.0 if 55 in z else (s['root_key'] or 60))
                cents = (key - root) * 100 + (z.get(51, 0) + pz.get(51, 0)) * 100 + z.get(52, 0) + pz.get(52, 0)
                ls = s['loop_start'] - s['start'] + z.get(2, 0)
                le = s['loop_end'] - s['start'] + z.get(3, 0)
                atten_cb = z.get(48, 0) + pz.get(48, 0)
                out.append({
                    'pcm': self.pcm[s['id']], 'pos': 0.0,
                    'step': 2.0 ** (cents / 1200.0) * rate / self.rate,
                    'loop': (ls, le) if z.get(54, 0) & 1 and 0 <= ls < le <= len(self.pcm[s['id']]) else None,
                    'gain': (velocity / 127.0) ** 2 * 10 ** (-atten_cb / 200.0),
                    'attack': timecents_to_s(z.get(34), 0.005, 2.0),
                    'release': timecents_to_s(z.get(38), 0.15, 3.0),
                    'age': 0.0, 'released_at': None, 'key': key, 'done': False,
                })
        return out

    @staticmethod
    def render_voice(v, buf, start, n, vol, dt):
        pcm, pos, step, loop = v['pcm'], v['pos'], v['step'], v['loop']
        size = len(pcm) - 1
        age, att, rel, rat = v['age'], v['attack'], v['release'], v['released_at']
        g = v['gain'] * vol / 32768.0
        for i in range(start, start + n):
            if loop and pos >= loop[1]:
                pos -= loop[1] - loop[0]
            idx = int(pos)
            if idx >= size:
                v['done'] = True
                break
            env = age / att if age < att else 1.0
            if rat is not None:
                env *= max(0.0, 1.0 - (age - rat) / rel)
                if age - rat >= rel:
                    v['done'] = True
                    break
            a = pcm[idx]
            buf[i] += (a + (pcm[idx + 1] - a) * (pos - idx)) * env * g
            pos += step
            age += dt
        v['pos'], v['age'] = pos, age


def midi_events(path):
    """All channel events of a MIDI file as (seconds, status kind, channel, a, b), time ordered."""
    m = music_midi.parse_midi(path)
    data = open(path, 'rb').read()
    pos, tracks = 14, []
    while pos + 8 <= len(data):
        cid, ln = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], 'big')
        if cid == b'MTrk':
            tracks.append(music_midi.parse_track(data, pos + 8, pos + 8 + ln, len(tracks))[0])
        pos += 8 + ln
    evs = sorted((t, ti, n, v) for ti, tr in enumerate(tracks) for n, (t, k, v) in enumerate(tr) if k == 'chan')
    cache, out = {}, []
    for t, _, _, v in evs:
        if t not in cache:
            cache[t] = music_midi.tempo_seconds(m['tempo_map'], t, m['division'])
        out.append((cache[t], v[0], v[1], v[2] if len(v) > 2 else 0, v[3] if len(v) > 3 else 0))
    return m, out


def render_stem(sf, mid_path, rate=22050, max_seconds=None):
    """Render only notes whose channel has bank MSB == USER_BANK and a program present in the bank."""
    m, events = midi_events(mid_path)
    length = m['seconds'] + 3.0
    if max_seconds:
        length = min(length, max_seconds)
    total = int(length * rate)
    buf = [0.0] * total
    sampler = Sampler(sf, rate)
    bank, prog, vol, expr = [0] * 16, [0] * 16, [100] * 16, [127] * 16
    active, used_notes, cursor = [], 0, 0
    dt = 1.0 / rate

    def advance(until):
        nonlocal cursor, active
        n = min(until, total) - cursor
        if n <= 0:
            return
        for v in active:
            Sampler.render_voice(v, buf, cursor, n, v['vol'], dt)
        active = [v for v in active if not v['done']]
        cursor += n

    for sec, kind, ch, a, b in events:
        advance(int(sec * rate))
        if cursor >= total:
            break
        if kind == 0xB0:
            if a == 0:
                bank[ch] = b
            elif a == 7:
                vol[ch] = b
            elif a == 11:
                expr[ch] = b
        elif kind == 0xC0:
            prog[ch] = a
        elif kind == 0x90 and b > 0:
            if bank[ch] == USER_BANK and prog[ch] in sampler.presets:
                for v in sampler.voices_for(prog[ch], a, b):
                    v['ch'], v['vol'] = ch, (vol[ch] / 127.0) * (expr[ch] / 127.0)
                    active.append(v)
                used_notes += 1
        elif kind == 0x80 or (kind == 0x90 and b == 0):
            for v in active:
                if v['ch'] == ch and v['key'] == a and v['released_at'] is None:
                    v['released_at'] = v['age']
    advance(total)
    return buf, used_notes, m


def write_wav(path, buf, rate, normalize=0.89):
    peak = max((abs(x) for x in buf), default=0.0)
    scale = normalize / peak if peak > 0 else 1.0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    frames = array.array('h', (max(-32767, min(32767, int(x * scale * 32767))) for x in buf))
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames.tobytes())
    return peak


def wav_stats(path):
    with wave.open(path, 'rb') as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError('only 16-bit WAV is supported')
    a = array.array('h', raw)
    peak = max((abs(x) for x in a), default=0)
    rms = math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0
    # length of the non-silent part (last sample above -60 dBFS)
    thr = 32768 * 10 ** (-60 / 20.0)
    last = max((i for i in range(len(a) - 1, -1, -1) if abs(a[i]) > thr), default=-1) if a else -1
    db = lambda x: 20 * math.log10(x / 32768.0) if x > 0 else float('-inf')
    return {'rate': rate, 'channels': ch, 'seconds': n / rate, 'audible_until': (last + 1) / ch / rate,
            'peak_dbfs': round(db(peak), 2), 'rms_dbfs': round(db(rms), 2), 'silent': peak <= thr}


def estimate_pitch(buf, rate):
    """Fundamental frequency by normalized autocorrelation (first strong peak)."""
    seg = buf[len(buf) // 3: len(buf) // 3 + 4096]
    e0 = sum(x * x for x in seg) or 1.0
    res = []
    for lag in range(int(rate / 2000), int(rate / 40)):
        other = buf[len(buf) // 3 + lag: len(buf) // 3 + lag + 4096]
        res.append((sum(x * y for x, y in zip(seg, other)) / e0, lag))
    best = max(res)[0]
    for i in range(1, len(res) - 1):
        if res[i][0] >= 0.85 * best and res[i][0] >= res[i - 1][0] and res[i][0] >= res[i + 1][0]:
            # parabolic interpolation around the peak
            y0, y1, y2 = res[i - 1][0], res[i][0], res[i + 1][0]
            shift = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) if (y0 - 2 * y1 + y2) else 0.0
            return rate / (res[i][1] + shift)
    return None


def selftest(install):
    sf = music_sf2.parse_sf2(game_file(install, *SBK_REL))
    rate = 44100
    sampler = Sampler(sf, rate)
    print('SBK pitch self-test (sample rate %d assumed, SF1 gen55 = root key in cents):' % SBK_RATE)
    for p in sf['presets']:
        for key in (60, 72):
            buf = [0.0] * int(rate * 1.2)
            for v in sampler.voices_for(p['program'], key, 127):
                v['attack'] = 0.001
                Sampler.render_voice(v, buf, 0, len(buf), 1.0, 1.0 / rate)
            f = estimate_pitch(buf, rate)
            exp = 440.0 * 2 ** ((key - 69) / 12.0)
            print('  prog %3d %-14s key %d: measured %7.1f Hz, expected %6.1f Hz, error %+.0f cents' % (
                p['program'], p['name'], key, f or 0, exp, 1200 * math.log2(f / exp) if f else float('nan')))


def commands(install, outdir, run=False):
    sbk = game_file(install, *SBK_REL)
    music = os.path.dirname(song_path(install, 'INTRO3'))
    sf2 = os.path.join(outdir, 'WARINTR3_bank1.sf2')
    gm = next((p for p in GM_SOUNDFONT_CANDIDATES if os.path.exists(p)), '/usr/share/sounds/sf2/FluidR3_GM.sf2')
    here = os.path.dirname(os.path.abspath(__file__))
    cmds = [['python3', os.path.join(here, 'music_sbk2sf2.py'), sbk, sf2, '--bank', str(USER_BANK)]]
    for song in ('INTRO3', 'TITLE', 'SCRIBE'):
        wav = os.path.join(outdir, song + '.wav')
        cmds.append(['fluidsynth', '-ni', '-g', '0.8', '-r', '44100', '-o', 'synth.midi-bank-select=gs',
                     '-F', wav, gm, sf2, song_path(install, song)])
        cmds.append(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-c:a', 'libvorbis', '-q:a', '6',
                     os.path.join(outdir, song + '.ogg')])
        cmds.append(['python3', os.path.abspath(__file__), 'verify', wav, song_path(install, song)])
    tools = {t: shutil.which(t) for t in ('fluidsynth', 'ffmpeg', 'timidity', 'sox')}
    print('# tools: ' + ', '.join('%s=%s' % (k, v or 'missing') for k, v in tools.items()))
    print('# GM soundfont: %s (%s)' % (gm, 'found' if os.path.exists(gm) else 'missing - install e.g. fluid-soundfont-gm'))
    for c in cmds:
        print(' '.join("'%s'" % x if (' ' in x or '=' in x) else x for x in c))
        if run and (c[0] == 'python3' or tools.get(c[0])):
            subprocess.run(c, check=False)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == 'selftest':
        selftest(argv[1])
    elif cmd == 'stem':
        install, song, out = argv[1], argv[2], argv[3]
        rate = int(argv[argv.index('--rate') + 1]) if '--rate' in argv else 22050
        secs = float(argv[argv.index('--seconds') + 1]) if '--seconds' in argv else None
        sf = music_sf2.parse_sf2(game_file(install, *SBK_REL))
        buf, notes, m = render_stem(sf, song_path(install, song), rate, secs)
        peak = write_wav(out, buf, rate)
        print('%s: %d SBK notes rendered, raw peak %.3f, MIDI length %.2f s -> %s' % (m['file'], notes, peak,
                                                                                  m['seconds'], out))
    elif cmd == 'verify':
        st = wav_stats(argv[1])
        line = '%s: %.2f s (audible until %.2f s), %d Hz x%d, peak %.2f dBFS, RMS %.2f dBFS, %s' % (
            argv[1], st['seconds'], st['audible_until'], st['rate'], st['channels'], st['peak_dbfs'],
            st['rms_dbfs'], 'SILENT' if st['silent'] else 'not silent')
        if len(argv) > 2:
            m = music_midi.parse_midi(argv[2])
            line += '; MIDI %.2f s (last note %.2f s), difference %+.2f s' % (
                m['seconds'], m['seconds_last_note'], st['seconds'] - m['seconds'])
        print(line)
    elif cmd == 'commands':
        outdir = argv[2] if len(argv) > 2 and not argv[2].startswith('--') else 'extracted/music'
        commands(argv[1], outdir, '--run' in argv)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
