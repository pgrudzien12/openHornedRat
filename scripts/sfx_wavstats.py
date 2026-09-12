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


def main(argv):
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


if __name__ == '__main__':
    main(sys.argv[1:])
