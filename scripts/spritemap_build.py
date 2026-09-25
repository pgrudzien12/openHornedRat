"""Builds the map: resource names used in .BTS/.MRC scripts -> sprite / scenery files (ROADMAP 1.4).

Usage: spritemap_build.py <WARFB dir> [out.json] [--pbx CACHE_DIR]
e.g.:  spritemap_build.py ".../WARFB" extracted/sprite_names/map.json --pbx /tmp/pbxcache

The mapping is not in BITMAP.DLL but in two static tables in the .data section of WHSHR.EXE
(an identical copy lives in GAMEF.DLL; only the code pointers in furniture records differ):

  sprite table     64-byte records, 220 entries, record 0 = 'VoidType'
      +0  u32       0 in the file (runtime field)
      +4  char[16]  resource name (CamelCase, as used in scripts)
      +20 char[16]  8.3 base name of the .FOL/.BOP/.PAL triple in BINARY/ ('' = no 2D sprite)
      +36 byte[28]  0 in the file (runtime: loaded pointers, counts)
  furniture table  60-byte records, directly after the sprite table, record 0 = 'VoidFurn'
      +0  u32       0 in the file (runtime field)
      +4  u8        flags (low nibble: object class, high bits: extra flags; meaning is a hypothesis)
      +5  char[16]  resource name
      +21 char[16]  8.3 base name of a 3D object <NAME>.XOF inside MESH/<battle>/SCENERY.PBX
      +37 u8        0
      +38 u16 x4    small numbers (e.g. 4,11,5,5 for Tudor2Stry), only for buildings/bridges
      +46 u16       0
      +48 u32 x3    code pointers (only animated objects: mills, tavern, portcullis, mole holes)

The 64-byte table is split into categories by position (effects, troops, portraits, banners, ...).
Names are unique inside a category but not globally ('Engrol' is both a troop and a portrait),
so every script command resolves in its own category.

With --pbx the script also unpacks MESH/*/SPRITES.PBX and SCENERY.PBX (scripts/pbx_rnc.py) and
checks, for every battle, that the files predicted from the script are the ones packed for it.
"""
import json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import whscript  # noqa: E402

SPRITE_REC, FURN_REC = 64, 60
IDENT = re.compile(r'^[A-Za-z0-9_]+$')

# categories of the sprite table: (category, first name, last name), positions are contiguous
SPRITE_CATEGORIES = [
    ('void', 'VoidType', 'VoidType'),
    ('effects', 'BattleSprites', 'Sparkle'),
    ('troops', 'MercCaptain', 'MoleMachine'),
    ('portraits', 'Ceridan1', 'Iron'),
    ('backgrounds', 'AllBGs', 'AllBGs'),
    ('banners', 'BannerMrcCmdr', 'BannerDragon'),
    ('terrain', 'u_water', 'Beam'),
    ('special', 'PlanMap', 'Portrait'),
]
# script command -> categories searched (in order)
COMMAND_CATEGORIES = {
    'troopsprites': ['void', 'troops'],
    'leaderportrait': ['void', 'portraits'],
    'banner': ['void', 'banners'],
    'loadspr': ['effects', 'troops', 'terrain'],
}


def cstr(b):
    return b.split(b'\0')[0].decode('latin-1')


def pe_info(data):
    """Returns (image_base, [(name, va, vsize, raw_off, raw_size)])."""
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec, optsz = struct.unpack_from('<H', data, pe + 6)[0], struct.unpack_from('<H', data, pe + 20)[0]
    base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
    secs = []
    for i in range(nsec):
        name, vs, va, rs, ra = struct.unpack_from('<8sIIII', data, pe + 24 + optsz + 40 * i)
        secs.append((name.rstrip(b'\0').decode(), va, vs, ra, rs))
    return base, secs


def off_to_va(data, off):
    base, secs = pe_info(data)
    for _, va, vs, ra, rs in secs:
        if ra <= off < ra + rs:
            return base + va + off - ra
    return None


def read_tables(exe):
    """Finds and decodes the sprite and furniture tables. Returns (sprites, furniture, info)."""
    s0 = exe.find(b'VoidType\0') - 4
    f0 = exe.find(b'VoidFurn\0') - 5
    if s0 < 0 or f0 < 0 or (f0 - s0) % SPRITE_REC:
        raise ValueError('sprite/furniture tables not found')
    sprites = []
    for i in range((f0 - s0) // SPRITE_REC):
        r = exe[s0 + i * SPRITE_REC:s0 + (i + 1) * SPRITE_REC]
        sprites.append({'index': i, 'name': cstr(r[4:20]), 'file': cstr(r[20:36]),
                        'runtime_zero': not any(r[:4]) and not any(r[36:])})
    furniture = []
    pos = f0
    while True:
        r = exe[pos:pos + FURN_REC]
        name, fname = cstr(r[5:21]), cstr(r[21:37])
        if not IDENT.match(name) or (fname and not IDENT.match(fname)):
            break
        ptrs = struct.unpack_from('<3I', r, 48)
        furniture.append({'index': len(furniture), 'name': name, 'file': fname, 'flags': r[4],
                          'dims': list(struct.unpack_from('<4H', r, 38)),
                          'code_ptrs': [hex(p) for p in ptrs] if any(ptrs) else []})
        pos += FURN_REC
    # evidence: absolute references to the table starts in .text (pointer immediates)
    s_va, f_va = off_to_va(exe, s0), off_to_va(exe, f0)
    base, secs = pe_info(exe)
    text = next(s for s in secs if s[0] == '.text')
    tbytes = exe[text[3]:text[3] + text[4]]
    info = {'sprite_table': {'file_offset': hex(s0), 'va': hex(s_va), 'records': len(sprites),
                             'record_size': SPRITE_REC,
                             'text_refs': tbytes.count(struct.pack('<I', s_va))},
            'furniture_table': {'file_offset': hex(f0), 'va': hex(f_va), 'records': len(furniture),
                                'record_size': FURN_REC,
                                'text_refs': tbytes.count(struct.pack('<I', f_va))},
            'image_base': hex(base)}
    return sprites, furniture, info


def assign_categories(sprites):
    idx = {s['name']: s['index'] for s in reversed(sprites)}   # first occurrence wins
    for cat, first, last in SPRITE_CATEGORIES:
        a = idx[first]
        b = max(i for i, s in enumerate(sprites) if s['name'] == last and i >= a)
        for s in sprites[a:b + 1]:
            s['category'] = cat
    for s in sprites:
        s.setdefault('category', 'unknown')


def list_ci(directory):
    return {f.upper(): os.path.join(directory, f) for f in os.listdir(directory)} if os.path.isdir(directory) else {}


def fol_summary(binfiles, base):
    """Frame count, frame kinds, typical sizes and colour-map count of <base>.FOL/.PAL."""
    p = binfiles.get(base.upper() + '.FOL')
    if not p:
        return None
    fol = open(p, 'rb').read()
    recs = [struct.unpack_from('<hhhhIB', fol, k) for k in range(0, len(fol) - 15, 16)]
    kinds, sizes = {}, {}
    for r in recs:
        kinds[r[5] & 15] = kinds.get(r[5] & 15, 0) + 1
        sizes['%dx%d' % (r[2], r[3])] = sizes.get('%dx%d' % (r[2], r[3]), 0) + 1
    pal = binfiles.get(base.upper() + '.PAL')
    psize = os.path.getsize(pal) if pal else 0
    return {'frames': len(recs), 'kinds': {str(k): v for k, v in sorted(kinds.items())},
            'sizes': dict(sorted(sizes.items(), key=lambda kv: -kv[1])[:3]),
            'bop': base.upper() + '.BOP' in binfiles, 'pal_bytes': psize,
            'colormaps': psize // 512 if psize and psize % 512 == 0 else 0}


# ---------------------------------------------------------------- script usage

def collect_names(script_dir):
    """Returns {command: {name: {'number': set, 'files': set}}} over all .BTS/.MRC."""
    uses = {}

    def add(cmd, value, fname):
        name, _, num = value.partition(',')
        e = uses.setdefault(cmd, {}).setdefault(name.strip(), {'numbers': set(), 'files': set()})
        e['numbers'].add(num.strip() if num else None)
        e['files'].add(fname)

    def walk(node, fname):
        for k, v in node['cmds']:
            lk = k.lower()
            if lk in ('troopsprites', 'banner', 'leaderportrait', 'loadspr', 'loadfurn',
                      'loadplanmap', 'loadportbg'):
                add(lk, v, fname)
            elif lk == 'placefurniture':
                add(lk, v.split(',')[0], fname)
        for c in node['children']:
            walk(c, fname)

    for f in sorted(os.listdir(script_dir)):
        if f.upper().endswith(('.BTS', '.MRC')):
            walk(whscript.parse(os.path.join(script_dir, f)), f)
    return uses


def resolve(uses, sprites, furniture, binfiles):
    by_cat = {}
    for s in sprites:
        by_cat.setdefault(s['category'], {}).setdefault(s['name'].lower(), s)
    furn = {}
    for f in furniture:
        furn.setdefault(f['name'].lower(), f)
    out, unresolved = {}, []
    for cmd in sorted(uses):
        out[cmd] = {}
        for name in sorted(uses[cmd], key=str.lower):
            u = uses[cmd][name]
            e = {'numbers': sorted(n for n in u['numbers'] if n is not None),
                 'number_missing_in': len([1 for n in u['numbers'] if n is None]),
                 'used_in': len(u['files'])}
            if cmd in COMMAND_CATEGORIES:
                rec = next((by_cat.get(c, {}).get(name.lower()) for c in COMMAND_CATEGORIES[cmd]
                            if by_cat.get(c, {}).get(name.lower())), None)
                if rec is None:
                    e['status'] = 'unresolved'
                elif rec['category'] == 'void':
                    e.update(status='void', index=0)
                elif not rec['file']:
                    e.update(status='no_2d_file', index=rec['index'], category=rec['category'])
                else:
                    e.update(status='ok', index=rec['index'], category=rec['category'],
                             file=rec['file'].upper(), exact_case=rec['name'] == name,
                             fol=fol_summary(binfiles, rec['file']))
                    if e['fol'] is None:
                        e['status'] = 'file_missing'
            elif cmd in ('loadfurn', 'placefurniture'):
                rec = furn.get(name.lower())
                if rec is None:
                    e['status'] = 'unresolved'
                else:
                    e.update(status='ok', index=rec['index'], file=rec['file'].upper() + '.XOF',
                             flags=rec['flags'], exact_case=rec['name'] == name,
                             container='MESH/<battle>/SCENERY.PBX')
            else:                           # loadplanmap / loadportbg: already an 8.3 name
                fs = fol_summary(binfiles, name)
                e.update(status='ok' if fs else 'file_missing', file=name.upper(), fol=fs,
                         via_placeholder='PlanMap' if cmd == 'loadplanmap' else 'PortBG')
            if e['status'] not in ('ok', 'void'):
                unresolved.append((cmd, name, e['status']))
            out[cmd][name] = e
    return out, unresolved


# ---------------------------------------------------------------- PBX cross-check

def pbx_data(path, cache):
    """Unpacked PBX contents, cached in a directory (unpacking in pure Python is slow)."""
    import pbx_rnc
    key = os.path.join(cache, os.path.basename(os.path.dirname(path)).upper() + '_' +
                       os.path.basename(path).upper().replace('.PBX', '.bin'))
    if os.path.exists(key):
        return open(key, 'rb').read()
    data, _ = pbx_rnc.unpack_pbx(path)
    os.makedirs(cache, exist_ok=True)
    open(key, 'wb').write(data)
    return data


def sprites_pbx_names(data):
    """SPRITES.PBX: u32 count at +0x10, entries from +0x20: u32 len, name, u32 size, data."""
    n, pos, names = struct.unpack_from('<I', data, 0x10)[0], 0x20, []
    for _ in range(n):
        ln = struct.unpack_from('<I', data, pos)[0]
        name = data[pos + 4:pos + 4 + ln].rstrip(b'\0').decode('latin-1')
        size = struct.unpack_from('<I', data, pos + 4 + ln)[0]
        names.append(name)
        pos += 8 + ln + size
    return names


def scenery_pbx_objects(data):
    """SCENERY.PBX: object names '<u32 len>NAME.XOF' (name table after the textures)."""
    return [m.group(2).decode('latin-1') for m in
            re.finditer(rb'([\x05-\x0c])\0\0\0([A-Za-z0-9_]{1,8}\.[Xx][Oo][Ff])', data)
            if m.group(1)[0] == len(m.group(2))]


def pbx_crosscheck(root, sprites, furniture, cache):
    script_dir = os.path.join(root, 'FILE', 'SCRIPT')
    mesh_dir = os.path.join(root, 'FILE', 'MESH')
    by_cat = {}
    for s in sprites:
        by_cat.setdefault(s['category'], {}).setdefault(s['name'].lower(), s)
    furn = {f['name'].lower(): f for f in reversed(furniture)}
    always = {f['file'].upper() for f in furniture if f['flags'] == 5 and f['index'] <= 52}
    report = []
    for f in sorted(os.listdir(script_dir)):
        if not f.upper().endswith('.BTS'):
            continue
        b = whscript.load_battle(os.path.join(script_dir, f), with_merc=True)
        mesh = whscript.find_ci(mesh_dir, b['field']['mesh'] or '')
        if not mesh:
            continue
        files = list_ci(mesh)
        row = {'battle': f, 'mesh': os.path.basename(mesh)}

        def look(cmd, value):
            name = value.split(',')[0].strip().lower()
            rec = next((by_cat.get(c, {}).get(name) for c in COMMAND_CATEGORIES[cmd]
                        if by_cat.get(c, {}).get(name)), None)
            return rec['file'].upper() if rec and rec['file'] else None

        pred_script, pred_merc = set(), set()
        for v in b['load'].get('loadspr', []):
            pred_script.add(look('loadspr', v))
        for army in b['armies']:
            for u in army['units']:
                pred_script.add(look('troopsprites', u['sprites'] or 'VoidType'))
                pred_script.add(look('banner', u['banner'] or 'VoidType'))
        for army in (b['merc'] or {}).get('armies') or []:
            for u in army['units']:
                pred_merc.add(look('troopsprites', u['sprites'] or 'VoidType'))
                pred_merc.add(look('banner', u['banner'] or 'VoidType'))
        pred_script.discard(None)
        pred_merc.discard(None)
        if 'SPRITES.PBX' in files:
            packed = {n.rsplit('.', 1)[0].upper() for n in sprites_pbx_names(pbx_data(files['SPRITES.PBX'], cache))}
            row['sprites'] = {'packed': len(packed),
                              'predicted_missing': sorted(pred_script - packed),
                              'packed_not_predicted': sorted(packed - pred_script),
                              'merc_files_packed': sorted(pred_merc & packed)}
        if 'SCENERY.PBX' in files:
            objs = {n.rsplit('.', 1)[0].upper() for n in scenery_pbx_objects(pbx_data(files['SCENERY.PBX'], cache))}
            pred = {furn[v.strip().lower()]['file'].upper() for v in b['load'].get('loadfurn', [])
                    if v.strip().lower() in furn}
            row['scenery'] = {'packed': len(objs), 'predicted_missing': sorted(pred - objs),
                              'packed_not_predicted': sorted(objs - pred - always),
                              'always_loaded_effects_packed': len(objs & always)}
        report.append(row)
    return report


def main(argv):
    args = [a for a in argv]
    cache = None
    if '--pbx' in args:
        i = args.index('--pbx')
        cache = args[i + 1]
        del args[i:i + 2]
    root = args[0]
    out = args[1] if len(args) > 1 else 'map.json'
    exe_path = whscript.find_ci(root, 'WHSHR.EXE')
    if exe_path is None:
        raise SystemExit('WHSHR.EXE not found under %s' % root)
    exe = open(exe_path, 'rb').read()
    sprites, furniture, info = read_tables(exe)
    gamef = whscript.find_ci(root, 'GAMEF.DLL')
    if gamef:
        g = open(gamef, 'rb').read()
        gs, gf, _ = read_tables(g)
        info['gamef_dll_same_tables'] = (
            [(s['name'], s['file']) for s in gs] == [(s['name'], s['file']) for s in sprites] and
            [(f['name'], f['file'], f['flags'], f['dims']) for f in gf] ==
            [(f['name'], f['file'], f['flags'], f['dims']) for f in furniture])
    assign_categories(sprites)

    # UPDATE/BINARY overrides FILE/BINARY
    binfiles = list_ci(os.path.join(root, 'FILE', 'BINARY'))
    binfiles.update(list_ci(os.path.join(root, 'UPDATE', 'BINARY')))
    for s in sprites:
        if s['file']:
            s['fol'] = fol_summary(binfiles, s['file'])

    uses = collect_names(os.path.join(root, 'FILE', 'SCRIPT'))
    names, unresolved = resolve(uses, sprites, furniture, binfiles)
    result = {'tables': info, 'names': names, 'unresolved': [list(u) for u in unresolved],
              'sprite_table': sprites, 'furniture_table': furniture}
    if cache:
        result['pbx_crosscheck'] = pbx_crosscheck(root, sprites, furniture, cache)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(result, open(out, 'w'), indent=1)

    print('sprite table: %(records)d records at %(va)s, furniture table: ' % info['sprite_table']
          + '%(records)d records at %(va)s' % info['furniture_table'])
    print('GAMEF.DLL has the same tables:', info.get('gamef_dll_same_tables'))
    for cmd in sorted(names):
        st = {}
        for e in names[cmd].values():
            st[e['status']] = st.get(e['status'], 0) + 1
        nums = sorted({n for e in names[cmd].values() for n in e['numbers']})
        print('  %-15s %3d names  %s  second numbers: %s' % (cmd, len(names[cmd]), st, nums or '-'))
    print('not resolved to a file (%d):' % len(unresolved))
    for u in unresolved:
        print('  %s:%s -> %s' % u)
    if cache:
        bad_s = [r for r in result['pbx_crosscheck'] if r.get('sprites') and
                 (r['sprites']['predicted_missing'] or r['sprites']['packed_not_predicted'])]
        bad_f = [r for r in result['pbx_crosscheck'] if r.get('scenery') and
                 (r['scenery']['predicted_missing'] or r['scenery']['packed_not_predicted'])]
        n = len(result['pbx_crosscheck'])
        print('PBX cross-check: %d battles; SPRITES.PBX exact match in %d, SCENERY.PBX exact match in %d'
              % (n, n - len(bad_s), n - len(bad_f)))
        for r in bad_s:
            print('  sprites  %-12s missing=%s extra=%s' % (r['battle'], r['sprites']['predicted_missing'],
                                                           r['sprites']['packed_not_predicted']))
        for r in bad_f:
            print('  scenery  %-12s missing=%s extra=%s' % (r['battle'], r['scenery']['predicted_missing'],
                                                           r['scenery']['packed_not_predicted']))
    print('written', out)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1:])
