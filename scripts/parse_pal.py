import sys
import struct

def parse_pal(path):
    data = open(path, 'rb').read()
    print(f"File size: {len(data)} bytes, entries={len(data)/4}")
    entries = []
    for i in range(0, len(data), 4):
        idx, r, g, b = data[i], data[i+1], data[i+2], data[i+3]
        entries.append((idx, r, g, b))
    # check whether the indices are sequential
    indices = [e[0] for e in entries]
    print(f"First index: {indices[0]}, last: {indices[-1]}")
    sequential = all(indices[i] == indices[0] + i for i in range(len(indices)))
    print(f"Sequential indices: {sequential}")
    return entries

if __name__ == "__main__":
    entries = parse_pal(sys.argv[1])
    for e in entries[:20]:
        print(e)
