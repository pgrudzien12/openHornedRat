import sys
data = open(sys.argv[1], 'rb').read()
entries = {}
for i in range(0, len(data), 4):
    idx, r, g, b = data[i], data[i+1], data[i+2], data[i+3]
    entries[idx] = (r, g, b)

# PPM image: 256 columns x 40 rows, one column per palette index 0..255
w, h = 256, 40
with open(sys.argv[2], 'wb') as f:
    f.write(f"P6\n{w} {h}\n255\n".encode())
    for y in range(h):
        for x in range(w):
            r, g, b = entries.get(x, (0, 0, 0))
            f.write(bytes([r, g, b]))
print("zapisano", sys.argv[2])
