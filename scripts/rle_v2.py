import struct

def decode_rowwise_triples(data, w, h):
    """kazdy wiersz: trojki (skip,count,color), koniec wiersza gdy suma >= w"""
    i, n = 0, len(data)
    row = 0
    x = 0
    while i + 3 <= n and row < h:
        skip, count, color = data[i], data[i+1], data[i+2]
        i += 3
        x += skip + count
        if x >= w:
            row += 1
            x = 0
    return i, row

def decode_rowwise_AB(data, w, h):
    """kazdy wiersz: skip,count -> highbit(count)=FILL+color, else COPY literal"""
    i, n = 0, len(data)
    row = 0
    x = 0
    while i < n and row < h:
        skip = data[i]; i += 1
        x += skip
        if x >= w:
            row += 1; x = 0
            continue
        if i >= n: break
        count = data[i]; i += 1
        if count & 0x80:
            run = count & 0x7f
            if i >= n: break
            i += 1
        else:
            run = count
            if i + run > n: break
            i += run
        x += run
        if x >= w:
            row += 1; x = 0
    return i, row

def test(name, fn, fol_path, bop_path):
    fol = open(fol_path, 'rb').read()
    bop = open(bop_path, 'rb').read()
    n_frames = len(fol)//16
    recs = [struct.unpack_from('<hhhhI', fol, f*16) for f in range(n_frames)]
    offsets = [r[4] for r in recs] + [len(bop)]
    ok = 0
    for f in range(n_frames):
        seg = bop[offsets[f]:offsets[f+1]]
        w, h = recs[f][2], recs[f][3]
        used, rows = fn(seg, w, h)
        match = used == len(seg)
        print(f"  frame{f}: w={w} h={h} seglen={len(seg)} used={used} rows_done={rows}/{h} match={match}")
        if match: ok += 1
    print(f"{name}: {ok}/{n_frames} pasuje\n")

DIR = "/home/pawel/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/FILE/BINARY"
test("rowwise triples", decode_rowwise_triples, DIR+"/SPARKLE.FOL", DIR+"/SPARKLE.BOP")
test("rowwise A/B", decode_rowwise_AB, DIR+"/SPARKLE.FOL", DIR+"/SPARKLE.BOP")

print("=== sprawdzam druga warstwe (kontynuacja po pierwszym przebiegu) ===")
DIR = "/home/pawel/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/FILE/BINARY"
fol = open(DIR+"/SPARKLE.FOL", 'rb').read()
bop = open(DIR+"/SPARKLE.BOP", 'rb').read()
n_frames = len(fol)//16
recs = [struct.unpack_from('<hhhhI', fol, f*16) for f in range(n_frames)]
offsets = [r[4] for r in recs] + [len(bop)]
for f in [5,6,7,8,9,10,11,12]:
    seg = bop[offsets[f]:offsets[f+1]]
    w, h = recs[f][2], recs[f][3]
    used1, rows1 = decode_rowwise_triples(seg, w, h)
    rest = seg[used1:]
    used2, rows2 = decode_rowwise_triples(rest, w, h)
    print(f"frame{f}: seglen={len(seg)} warstwa1 used={used1} rows={rows1} | warstwa2 used={used2}/{len(rest)} rows={rows2}")
