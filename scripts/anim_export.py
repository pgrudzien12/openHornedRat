"""Exports directional sprite animations (units, monsters, artillery) as anchor-aligned sheets
(row = direction, columns = animation phases) and animated GIFs.

Usage: anim_export.py <WARFB or BINARY dir> [NAME ...] [--out=extracted/animations]
                      [--scale=2] [--delay=15] [--no-gif] [--marks]
e.g.:  anim_export.py ".../WARFB" ESHIN GIANT          # two sprite sets
       anim_export.py ".../WARFB"                      # every directional sprite set

Output per sprite set NAME (in <out>/<name>/):
  <name>_sheet.png   all groups stacked; each group = 8 rows (directions) x phases
  <name>_gK.gif      group K animated: the 8 directions side by side, one GIF frame per phase

Layout (see notes/animations.md):
  - a group = a maximal run of consecutive frames with the same colour-map nibble (kind >> 4);
    each group has its own 16-colour map in <NAME>.PAL
  - inside a group: frame = group_start + phase * 8 + direction
  - direction 0 = facing away from the viewer (up the screen), then clockwise on screen:
    1 = up-right, 2 = right, 3 = down-right, 4 = towards the viewer, 5 = down-left, 6 = left, 7 = up-left
  - anchor (hypothesis): x = record byte 3, y = height - record byte 2
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim_lib import Canvas, Sprite, find_bindirs, list_sprites, write_gif    # noqa: E402

DIRECTIONS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')   # screen directions, 0 = away from viewer

# Action names per group, identified visually (see notes/animations.md). They are labels for
# humans, not data from the game. Key = frame counts of the groups ("32+8+32+32" etc.).
PATTERN_ACTIONS = {
    '32+8+32+32': ('MOVE', 'DEAD', 'ATTACK', 'STAND'),
    '32+8+32+32+8': ('MOVE', 'DEAD', 'ATTACK', 'STAND', 'SHOOT/CAST'),
    '32+8+32+32+8+8': ('MOVE', 'DEAD', 'ATTACK', 'STAND', 'CAST', 'CAST2'),
    '32+8+32+32+8+32': ('MOVE', 'DEAD', 'ATTACK', 'STAND', 'CAST', 'CAST FX'),
    '32+8+32': ('MOVE', 'DEAD', 'STAND'),
    '32+8+8+32': ('MOVE', 'DEAD', 'SHOOT', 'STAND'),
    '32+8+8+8+8': ('FLY', 'POSE?', 'POSE?', 'POSE?', 'POSE?'),
    '32+32+8': ('MOVE A', 'MOVE B', 'WRECK'),
    '8+32+8': ('READY', 'FIRE', 'POSE?'),
    '8+32': ('WRECK', 'MOVE'),
    '32': ('MOVE',),
}
NAME_ACTIONS = {   # sets whose pattern is shared by different kinds of objects
    'PEASANT': tuple(a + ' ' + ch for a in ('MOVE', 'DEAD', 'ATTACK?', 'STAND?') for ch in 'ABC'),
    'GYROCOPT': ('FLY', 'WRECK'), 'ROCKLOB': ('FIRE', 'WRECK'), 'DDCATPLT': ('FIRE', 'WRECK'),
    'FANATIC': ('SPIN', 'DEAD'), 'DRAGON': ('IDLE?',),
}


def action_names(sprite):
    """Hypothetical action label for every group (list parallel to groups())."""
    gs = groups(sprite)
    counts = [c for _, _, c in gs]
    names = NAME_ACTIONS.get(sprite.name) or PATTERN_ACTIONS.get('+'.join(map(str, counts)))
    if not names and counts == [8, 8]:
        # artillery: nibble 1 is always the wreck (xxxCANON: 1+2, xxxWAG: 0+1)
        names = tuple('WRECK' if g == 1 else 'INTACT' for g, _, _ in gs)
    return list(names) if names else ['?'] * len(counts)


def groups(sprite):
    """Maximal runs of equal colour-map nibble: list of (nibble, start, count)."""
    out = []
    for i, r in enumerate(sprite.recs):
        g = r[5] >> 4
        if out and out[-1][0] == g and out[-1][1] + out[-1][2] == i:
            out[-1][2] += 1
        else:
            out.append([g, i, 1])
    return [tuple(x) for x in out]


def is_directional(sprite):
    """Directional sprite set: every frame is type 4 with flag bytes 02 04 40, bytes 0-1 zero,
    and every group has a multiple of 8 frames."""
    if len(sprite) < 8:
        return False
    for raw in sprite.raw:
        if raw[12] & 15 != 4 or raw[13:16] != b'\x02\x04\x40' or raw[0] or raw[1]:
            return False
    return all(c % 8 == 0 for _, _, c in groups(sprite))


def anchor_xy(sprite, i):
    b2, b3 = sprite.anchor(i)
    return b3, sprite.recs[i][3] - b2


def cell_extent(sprite, frames):
    """(left, up, right, down) extents around the anchor that fit all given frames."""
    le = up = ri = dn = 0
    for i in frames:
        ax, ay = anchor_xy(sprite, i)
        w, h = sprite.recs[i][2], sprite.recs[i][3]
        le, up, ri, dn = max(le, ax), max(up, ay), max(ri, w - ax), max(dn, h - ay)
    return le, up, ri, dn


def draw_anchored(cv, sprite, i, cx, cy, marks=False):
    ax, ay = anchor_xy(sprite, i)
    cv.blit(sprite, i, cx - ax, cy - ay)
    if marks:
        for d in range(-2, 3):
            cv.dot(cx + d, cy, (255, 60, 60))
            cv.dot(cx, cy + d, (255, 60, 60))


def render_sheet(sprite, marks=False):
    """Rows = 8 directions; columns = the phases of all groups side by side, each group
    separated by a gap and titled 'G<nibble> <first>-<last>'. All cells share one anchor point."""
    gs = groups(sprite)
    le, up, ri, dn = cell_extent(sprite, range(len(sprite)))
    cw, ch = le + ri + 4, up + dn + 8
    label_w, title_h, gap = 14, 18, 6
    W = label_w + sum(max(c // 8, 1) * cw + gap for _, _, c in gs)
    cv = Canvas(W, title_h + 8 * ch)
    cv.text(1, 1, '%s  %d FRAMES = 8 DIRS X %d PHASES' % (sprite.name, len(sprite), len(sprite) // 8),
            (255, 255, 255))
    for d in range(8):
        cv.text(1, title_h + d * ch + ch // 2 - 2, DIRECTIONS[d], (200, 200, 200))
    x = label_w
    for (g, start, count), act in zip(gs, action_names(sprite)):
        ph = count // 8
        cv.fill(x, 9, ph * cw, 7, (20, 20, 26))
        cv.text(x + 1, 10, 'G%X %d-%d %s' % (g, start, start + count - 1, act), (120, 200, 255))
        for p in range(ph):
            for d in range(8):
                i = start + p * 8 + d
                x0, y0 = x + p * cw, title_h + d * ch
                cv.fill(x0 + 1, y0 + 1, cw - 2, ch - 2, (52, 52, 62))
                cv.text(x0 + 2, y0 + 2, str(i), (150, 150, 150))
                draw_anchored(cv, sprite, i, x0 + 2 + le, y0 + 6 + up, marks)
        x += ph * cw + gap
    return cv


def export_gifs(sprite, outdir, scale=2, delay=15):
    """One GIF per group: the 8 directions side by side, one GIF frame per phase."""
    pal = list(sprite.rgb)
    pal[0], pal[255] = (40, 40, 48), (220, 220, 220)
    paths = []
    for g, start, count in groups(sprite):
        ph = count // 8
        frames_idx = range(start, start + count)
        le, up, ri, dn = cell_extent(sprite, frames_idx)
        cw, ch = le + ri + 2, up + dn + 2
        W, H = cw * 8 * scale, (ch + 8) * scale
        gif_frames = []
        for p in range(ph):
            buf = [0] * ((ch + 8) * cw * 8)
            Wl = cw * 8
            for d in range(8):
                i = start + p * 8 + d
                ax, ay = anchor_xy(sprite, i)
                w, h = sprite.recs[i][2], sprite.recs[i][3]
                px = sprite.frame(i)
                ox, oy = d * cw + 1 + le - ax, 8 + 1 + up - ay
                for yy in range(h):
                    for xx in range(w):
                        v = px[yy * w + xx]
                        if v:
                            buf[(oy + yy) * Wl + ox + xx] = v
                # direction label in the 3x5 font, colour 255
                lab = Canvas(16, 6, (0, 0, 0))
                lab.text(0, 0, DIRECTIONS[d], (255, 255, 255))
                for yy in range(5):
                    for xx in range(16):
                        if lab.px[(yy * 16 + xx) * 3]:
                            buf[(1 + yy) * Wl + d * cw + 2 + xx] = 255
            if scale > 1:
                rows = [buf[r * Wl:(r + 1) * Wl] for r in range(ch + 8)]
                buf = [v for row in rows for _ in range(scale) for v in
                       [c for c in row for _ in range(scale)]]
            gif_frames.append(buf)
        path = os.path.join(outdir, '%s_g%X.gif' % (sprite.name.lower(), g))
        write_gif(path, W, H, gif_frames, pal, delay_cs=delay)
        paths.append(path)
    return paths


def main(argv):
    opts = {a[2:].split('=')[0]: (a.split('=', 1)[1] if '=' in a else True) for a in argv if a.startswith('--')}
    args = [a for a in argv if not a.startswith('--')]
    bindirs = find_bindirs(args[0])
    names = [n.upper() for n in args[1:]] or list_sprites(bindirs)
    root = opts.get('out', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        'extracted', 'animations'))
    scale, delay = int(opts.get('scale', 2)), int(opts.get('delay', 15))
    done = 0
    for name in names:
        s = Sprite(bindirs, name)
        if not is_directional(s):
            if args[1:]:
                print('%s: not a directional sprite set, skipped' % name)
            continue
        outdir = os.path.join(root, name.lower())
        os.makedirs(outdir, exist_ok=True)
        render_sheet(s, bool(opts.get('marks'))).png(os.path.join(outdir, name.lower() + '_sheet.png'), scale)
        gifs = [] if opts.get('no-gif') else export_gifs(s, outdir, scale, delay)
        print('%-9s %4d frames, groups %s -> %s (%d GIFs)' % (
            name, len(s), ' '.join('%X:%d' % (g, c) for g, _, c in groups(s)), outdir, len(gifs)))
        done += 1
    print('exported %d sprite sets' % done)


if __name__ == '__main__':
    main(sys.argv[1:])
