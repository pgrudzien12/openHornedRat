"""Inventory of all .FOL/.BOP pairs and automated check of the directional animation layout.

Usage: anim_inventory.py <WARFB or BINARY dir> [--md] [--verbose]
e.g.:  anim_inventory.py ".../WARFB" --md > /tmp/inventory.md

For each sprite set: frame count, frame types, sizes, flag bytes 13-15, anchor bytes 0-3,
groups (runs of equal colour-map nibble) and a class:
  directional  every frame type 4, flags 02 04 40, bytes 0-1 zero, all groups multiple of 8
  portrait     frame 0 is 120x152 (portrait + mouth/eye overlay frames, int16 hotspots)
  single       one frame (backgrounds, plan maps)
  other        everything else (icons, banners, spells, effects, terrain tiles...)

Layout check for every directional group with >= 2 phases (frame = start + phase*8 + dir):
  d_phase = mean pixel difference between frame i and i+8 (same direction, next phase)
  d_dir   = mean pixel difference between frame i and i+1 (next direction, same phase)
  The layout "phase*8+dir" fits when d_phase < d_dir. Difference = fraction of the union of
  opaque pixels (anchor-aligned) that differ in opacity.
"""
import collections, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim_lib import Sprite, find_bindirs, list_sprites     # noqa: E402
from anim_export import action_names, anchor_xy, groups, is_directional   # noqa: E402

SKIP = {'HALBERD', 'ICON2', 'SPRITE3'}   # different record layout, investigated separately


def mask(sprite, i):
    """Set of opaque pixel coordinates relative to the anchor."""
    ax, ay = anchor_xy(sprite, i)
    w, h = sprite.recs[i][2], sprite.recs[i][3]
    px = sprite.frame(i)
    return {(x - ax, y - ay) for y in range(h) for x in range(w) if px[y * w + x]}


def diff(a, b):
    u = len(a | b)
    return len(a ^ b) / u if u else 0.0


def classify(s):
    if s.name in SKIP:
        return 'skipped'
    if len(s) == 1:
        return 'single'
    if s.recs[0][2:4] == (120, 152) and any(r[2:4] != (120, 152) for r in s.recs[1:]):
        return 'portrait'
    if is_directional(s):
        return 'directional'
    return 'other'


def check_group(s, start, count):
    ph = count // 8
    masks = [mask(s, i) for i in range(start, start + count)]
    dp = [diff(masks[p * 8 + d], masks[(p + 1) % ph * 8 + d]) for p in range(ph) for d in range(8)]
    dd = [diff(masks[p * 8 + d], masks[p * 8 + (d + 1) % 8]) for p in range(ph) for d in range(8)]
    res = {'d_phase': sum(dp) / len(dp), 'd_dir': sum(dd) / len(dd)}
    if ph == 4:   # phases 1 and 3 similar (walk/gallop cycle with two passing poses)?
        d13 = [diff(masks[8 + d], masks[24 + d]) for d in range(8)]
        d02 = [diff(masks[0 + d], masks[16 + d]) for d in range(8)]
        res['d13'], res['d02'] = sum(d13) / 8, sum(d02) / 8
    return res


def main(argv):
    md = '--md' in argv
    verbose = '--verbose' in argv
    bindirs = find_bindirs([a for a in argv if not a.startswith('--')][0])
    classes = collections.defaultdict(list)
    rows = []
    for name in list_sprites(bindirs):
        s = Sprite(bindirs, name)
        cls = classify(s)
        classes[cls].append(name)
        if cls == 'skipped':
            continue
        types = collections.Counter(r[5] & 15 for r in s.recs)
        sizes = collections.Counter('%dx%d' % r[2:4] for r in s.recs)
        flags = collections.Counter(raw[13:16].hex() for raw in s.raw)
        gs = groups(s)
        rows.append((name, cls, len(s), types, sizes, flags, gs, s))
        if verbose:
            print('%-9s %-11s %4d  types %s  sizes %s  flags13-15 %s  groups %s' % (
                name, cls, len(s), dict(types), dict(sizes.most_common(3)), dict(flags),
                ' '.join('%X:%d' % (g, c) for g, _, c in gs)))

    print('\n# Classes')
    for cls, names in sorted(classes.items()):
        print('%-11s %3d  frames %5d  %s' % (cls, len(names),
              sum(r[2] for r in rows if r[1] == cls), ' '.join(names) if cls != 'single' else '(backgrounds/maps)'))

    print('\n# Directional sets: pattern and layout check')
    if md:
        print('| file | frames | groups (frames) | actions (visual labels) | phase<dir in groups '
              '| d_phase / d_dir | d13 / d02 (4-phase groups) | anchor b2,b3 |')
        print('|---|---|---|---|---|---|---|---|')
    patterns = collections.Counter()
    fits = total = 0
    for name, cls, n, types, sizes, flags, gs, s in rows:
        if cls != 'directional':
            continue
        pat = '+'.join(str(c) for _, _, c in gs)
        patterns[pat] += 1
        ok = cnt = 0
        dps, dds, d13s, d02s = [], [], [], []
        for g, start, count in gs:
            if count >= 16:
                r = check_group(s, start, count)
                cnt += 1
                ok += r['d_phase'] < r['d_dir']
                dps.append(r['d_phase'])
                dds.append(r['d_dir'])
                if 'd13' in r:
                    d13s.append(r['d13'])
                    d02s.append(r['d02'])
        fits += ok
        total += cnt
        anchors = sorted({s.anchor(i) for i in range(len(s))})
        anc = ' '.join('%d,%d' % a for a in anchors[:4]) + (' …' if len(anchors) > 4 else '')
        avg = lambda v: sum(v) / len(v) if v else float('nan')
        acts = ', '.join(a.lower() for a in action_names(s))
        line = (name, n, ' '.join('%X:%d' % (g, c) for g, _, c in gs), acts if md else pat, '%d/%d' % (ok, cnt),
                '%.2f / %.2f' % (avg(dps), avg(dds)), '%.2f / %.2f' % (avg(d13s), avg(d02s)) if d13s else '-', anc)
        if md:
            print('| ' + ' | '.join(str(x) for x in line) + ' |')
        else:
            print('%-9s %4d  %-40s %-18s fit %-5s d_ph/d_dir %s  d13/d02 %s  anchors %s' % line)
    print('\nlayout phase*8+dir fits (d_phase < d_dir) in %d of %d groups with >= 2 phases' % (fits, total))
    print('frame-count patterns:', dict(patterns.most_common()))


if __name__ == '__main__':
    main(sys.argv[1:])
