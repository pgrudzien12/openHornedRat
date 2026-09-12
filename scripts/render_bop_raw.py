import sys

def load_pal(path):
    data = open(path, 'rb').read()
    entries = {}
    for i in range(0, len(data), 4):
        idx, r, g, b = data[i], data[i+1], data[i+2], data[i+3]
        entries[idx] = (r, g, b)
    return entries

def main():
    fol_path, bop_path, pal_path, out_path = sys.argv[1:5]
    fol = open(fol_path, 'rb').read()
    bop = open(bop_path, 'rb').read()
    pal = load_pal(pal_path)

    # first FOL record
    hx, hy, w, h, off, flags = None, None, None, None, None, None
    import struct
    hx, hy, w, h, off = struct.unpack_from('<hhhhI', fol, 0)
    flags = fol[12:16]
    print(f"hotspot=({hx},{hy}) w={w} h={h} offset={off} flags={flags.hex()}")

    pixels = bop[off:off + w*h]
    print(f"pixel bytes needed={w*h}, available={len(pixels)}")

    with open(out_path, 'wb') as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        for p in pixels:
            r, g, b = pal.get(p, (0, 0, 0))
            f.write(bytes([r, g, b]))
    print("saved", out_path)

main()
