"""Visual verification of the name -> file map produced by spritemap_build.py (ROADMAP 1.4).

Usage: spritemap_verify.py <WARFB dir> <map.json> <out dir> --pbx CACHE_DIR [name ...]
e.g.:  spritemap_verify.py ".../WARFB" extracted/sprite_names/map.json extracted/sprite_names \
           --pbx /tmp/pbxcache ClanRats BannerSkaven3 Commander SnwPineLrg Rock1

- 2D names (troopsprites/banner/leaderportrait/loadspr): sheet of the first frames of the mapped
  .FOL/.BOP (scripts/render_sprites.py), file verify_<name>_<FILE>.png.
- Furniture names (loadfurn/placefurniture) map to <FILE>.XOF objects inside SCENERY.PBX. The .XOF
  format is not decoded yet, so the link object -> texture is taken from co-occurrence over all
  battles: textures present in every SCENERY.PBX that contains the object and in as few others
  as possible. Those textures are rendered to verify_<name>_<FILE>.png.

SCENERY.PBX layout used here (unpacked RNC data, little-endian):
  +0x0c u32 object count, +0x14 u32 texture count, textures start at +0x20:
  u32 name_len, name (with NUL), 9 x u32 (pixel_bytes, palette_bytes, w, h, 1, 1, bpp=8, 0, colours),
  pixel_bytes of 8-bit indices, palette_bytes of palette (256 x 4), 38 bytes of trailer.
"""
import json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_sprites  # noqa: E402
import spritemap_build  # noqa: E402
import whscript  # noqa: E402

TRAILER = 38


def scenery_textures(data):
    """Returns [{'name', 'w', 'h', 'pixels', 'palette', 'colours'}] from unpacked SCENERY.PBX."""
    count = struct.unpack_from('<I', data, 0x14)[0]
    pos, out = 0x20, []
    for _ in range(count):
        ln = struct.unpack_from('<I', data, pos)[0]
        name = data[pos + 4:pos + 4 + ln].rstrip(b'\0').decode('latin-1')
        h = struct.unpack_from('<9I', data, pos + 4 + ln)
        p = pos + 4 + ln + 36
        out.append({'name': name.lower(), 'w': h[2], 'h': h[3], 'colours': h[8],
                    'pixels': data[p:p + h[0]], 'palette': data[p + h[0]:p + h[0] + h[1]]})
        pos = p + h[0] + h[1] + TRAILER
    return out


def texture_rgb(tex, std_pal, mode):
    """mode 'std': indices into STANDARD.PAL; 'emb0'/'emb1': embedded 4-byte palette, entry = x,R,G,B
    starting at byte 0 / 1 of the palette block (the alignment is one of the things being tested)."""
    rgb = []
    for i in tex['pixels'][:tex['w'] * tex['h']]:
        if mode == 'std':
            rgb.append(std_pal[i])
        else:
            o = i * 4 + (1 if mode == 'emb1' else 0)
            e = tex['palette'][o:o + 4]
            rgb.append(tuple(e[1:4]) if len(e) == 4 else (255, 0, 255))
    return rgb


def compose(images, scale=3, gap=4, bg=(40, 40, 48)):
    """images: [(w, h, [rgb tuples])] placed side by side."""
    W = sum(w for w, _, _ in images) + gap * (len(images) + 1)
    H = max(h for _, h, _ in images) + 2 * gap
    img = [bg] * (W * H)
    x = gap
    for w, h, px in images:
        for j in range(h):
            for i in range(w):
                img[(gap + j) * W + x + i] = px[j * w + i]
        x += w + gap
    rgb = bytearray()
    for j in range(H * scale):
        row = img[(j // scale) * W:(j // scale + 1) * W]
        for i in range(W * scale):
            rgb += bytes(row[i // scale])
    return W * scale, H * scale, rgb


def cooccurrence(root, cache):
    """{object: (battles_with_object, {texture: (with_obj, total_with_texture)})} over all SCENERY.PBX."""
    mesh_dir = os.path.join(root, 'FILE', 'MESH')
    per_battle, textures = {}, {}
    for d in sorted(os.listdir(mesh_dir)):
        files = spritemap_build.list_ci(os.path.join(mesh_dir, d))
        if 'SCENERY.PBX' not in files:
            continue
        data = spritemap_build.pbx_data(files['SCENERY.PBX'], cache)
        objs = {n.rsplit('.', 1)[0].upper() for n in spritemap_build.scenery_pbx_objects(data)}
        texs = scenery_textures(data)
        per_battle[d] = (objs, {t['name'] for t in texs})
        for t in texs:
            textures.setdefault(t['name'], t)
    return per_battle, textures


def candidate_textures(obj, per_battle):
    with_obj = [t for o, t in per_battle.values() if obj in o]
    if not with_obj:
        return [], 0
    common = set.intersection(*with_obj)
    total = {tx: sum(1 for _, t in per_battle.values() if tx in t) for tx in common}
    # textures that occur only where the object occurs are the strongest candidates
    ranked = sorted(common, key=lambda tx: (total[tx] - len(with_obj), tx))
    return [(tx, len(with_obj), total[tx]) for tx in ranked], len(with_obj)


def main(argv):
    args = list(argv)
    i = args.index('--pbx')
    cache = args[i + 1]
    del args[i:i + 2]
    root, map_path, out_dir, names = args[0], args[1], args[2], args[3:]
    m = json.load(open(map_path))
    os.makedirs(out_dir, exist_ok=True)
    binfiles = spritemap_build.list_ci(os.path.join(root, 'FILE', 'BINARY'))
    binfiles.update(spritemap_build.list_ci(os.path.join(root, 'UPDATE', 'BINARY')))
    bindir = os.path.dirname(binfiles['STANDARD.PAL'])
    std_pal = render_sprites.load_rgb_palette(binfiles['STANDARD.PAL'])
    per_battle = textures = None
    for name in names:
        hit = next(((cmd, e) for cmd, entries in m['names'].items() for n, e in entries.items()
                    if n.lower() == name.lower() and e.get('file')), None)
        if not hit:
            print('%s: not in map' % name)
            continue
        cmd, e = hit
        if cmd in ('loadfurn', 'placefurniture'):
            if per_battle is None:
                per_battle, textures = cooccurrence(root, cache)
            obj = e['file'].rsplit('.', 1)[0]
            cands, n = candidate_textures(obj, per_battle)
            strong = [c for c in cands if c[2] == c[1]] or cands[:3]
            print('%s -> %s in %d SCENERY.PBX; textures always present with it: %s'
                  % (name, e['file'], n, ['%s (%d/%d)' % c for c in cands[:8]]))
            if not strong:
                continue
            imgs = []
            for tx, _, _ in strong[:6]:
                t = textures[tx]
                for mode in ('std', 'emb0', 'emb1'):
                    imgs.append((t['w'], t['h'], texture_rgb(t, std_pal, mode)))
            w, h, rgb = compose(imgs, scale=3)
            path = os.path.join(out_dir, 'verify_%s_%s.png' % (name, obj))
            render_sprites.write_png(path, w, h, rgb)
            print('   wrote %s (per texture: STANDARD.PAL | embedded palette +0 | +1): %s'
                  % (path, [tx for tx, _, _ in strong[:6]]))
        else:
            fs = e['fol'] or {}
            count = min(16, fs.get('frames', 16))
            path = os.path.join(out_dir, 'verify_%s_%s.png' % (name, e['file']))
            render_sprites.main(bindir, os.path.basename(binfiles[e['file'] + '.FOL'])[:-4], 0, count,
                                path, cols=8, scale=2)
            print('%s (%s) -> %s, %d frames, wrote %s' % (name, cmd, e['file'], fs.get('frames', 0), path))


if __name__ == '__main__':
    if len(sys.argv) < 5:
        print(__doc__)
    else:
        main(sys.argv[1:])
