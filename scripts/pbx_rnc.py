"""Rob Northen ProPack (RNC) decompressor, method 2, in pure Python.

Usage: pbx_rnc.py <file.PBX|RNC file> [out.bin]
       pbx_rnc.py --check <MESH directory>      # all */*.PBX: header CRCs
e.g.:  pbx_rnc.py ".../WARFB/FILE/MESH/BF001/SPRITES.PBX" sprites.bin

RNC header (18 bytes, big-endian):
  0  'RNC'            signature
  3  u8   method      1 = Huffman, 2 = bit stream without trees (the game uses only 2)
  4  u32  unpacked    unpacked size
  8  u32  packed      packed data size (after the header)
  12 u16  crc_unp     CRC-16/ARC of the unpacked data
  14 u16  crc_pack    CRC-16/ARC of the packed data
  16 u8   leeway      extra bytes needed for in-place unpacking (unused here)
  17 u8   chunks      number of chunks in the stream

The game's .PBX files have one 0x01 byte before the header (except
MESH/BF004/GRND.PBX), see notes/pbx_rnc.md.
"""
import glob, os, struct, sys

_CRC_TAB = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xA001 if _c & 1 else _c >> 1
    _CRC_TAB.append(_c)


def crc16(data):
    """CRC-16/ARC (reflected polynomial 0xA001, init 0), as used in the RNC header."""
    c = 0
    for b in data:
        c = (c >> 8) ^ _CRC_TAB[(c ^ b) & 0xFF]
    return c


class RncError(Exception):
    pass


def parse_header(buf, pos=0):
    if buf[pos:pos + 3] != b'RNC':
        raise RncError('no RNC signature at offset %d' % pos)
    method, unp, pk, cu, cp, leeway, chunks = struct.unpack_from('>BIIHHBB', buf, pos + 3)
    return dict(method=method, unpacked=unp, packed=pk, crc_unpacked=cu,
                crc_packed=cp, leeway=leeway, chunks=chunks)


def _unpack_m2(src, out_size):
    """Method 2. Bits are read MSB-first from bytes that are interleaved with raw
    bytes of the same stream (a new bit byte is fetched only when the previous one
    is used up). Returns (data, bytes consumed, chunk end markers seen)."""
    out = bytearray()
    pos = 0
    bitbuf = 0
    bitcnt = 0
    chunks = 0

    def bit():
        nonlocal pos, bitbuf, bitcnt
        if bitcnt == 0:
            bitbuf = src[pos]
            pos += 1
            bitcnt = 8
        bitcnt -= 1
        return (bitbuf >> bitcnt) & 1

    def bits(n):
        v = 0
        for _ in range(n):
            v = (v << 1) | bit()
        return v

    def byte():
        nonlocal pos
        pos += 1
        return src[pos - 1]

    def offset():
        # match distance: high part 0..15 from bits, low byte raw
        hi = 0
        if bit():
            hi = bit()
            if bit():
                hi = ((hi << 1) | bit()) | 4
                if not bit():
                    hi = (hi << 1) | bit()
            elif hi == 0:
                hi = bit() + 2
        return ((hi << 8) | byte()) + 1

    bits(2)                                   # 2 flag bits at the start (lock/key), skipped
    while len(out) < out_size:
        if not bit():                         # 0: one literal byte
            out.append(byte())
            continue
        if not bit():                         # 10: length 4..9 or a literal run
            n = 4 + bit()
            if bit():
                n = ((n - 1) << 1) + bit()    # 6..9
            if n == 9:                        # run of 12..72 literal bytes
                n = (bits(4) << 2) + 12
                out += src[pos:pos + n]
                pos += n
                continue
            dist = offset()
        elif not bit():                       # 110: length 2, short distance (1 byte)
            n = 2
            dist = byte() + 1
        else:                                 # 111
            if not bit():                     # 1110: length 3
                n = 3
            else:                             # 1111 NN: length NN+8, NN=0 -> end of chunk
                n = byte() + 8
                if n == 8:
                    chunks += 1
                    bit()                     # 1 bit: more chunks follow (ignored)
                    continue
            dist = offset()
        if dist > len(out):
            raise RncError('distance %d beyond output (%d)' % (dist, len(out)))
        for _ in range(n):                    # copy may overlap
            out.append(out[-dist])
    return bytes(out[:out_size]), pos, chunks


def rnc_unpack(buf, pos=0, check_crc=True):
    """Unpacks the RNC block starting at buf[pos]. Returns (data, header dict)."""
    h = parse_header(buf, pos)
    src = buf[pos + 18:pos + 18 + h['packed']]
    if len(src) != h['packed']:
        raise RncError('truncated packed data')
    if check_crc and crc16(src) != h['crc_packed']:
        raise RncError('bad CRC of packed data')
    if h['method'] == 2:
        data, used, chunks = _unpack_m2(src, h['unpacked'])
    else:
        # no game file uses method 1 (Huffman), so there is nothing to verify it against
        raise RncError('method %d not supported' % h['method'])
    h['used'], h['chunks_seen'] = used, chunks
    if check_crc and crc16(data) != h['crc_unpacked']:
        raise RncError('bad CRC of unpacked data')
    return data, h


def unpack_pbx(path):
    """Reads a .PBX file: optional 0x01 byte, then one RNC block. Returns (data, header)."""
    raw = open(path, 'rb').read()
    pos = raw.find(b'RNC', 0, 4)
    if pos < 0:
        raise RncError('%s: no RNC header' % path)
    data, h = rnc_unpack(raw, pos)
    h['prefix'] = raw[:pos]
    h['trailing'] = len(raw) - pos - 18 - h['packed']
    return data, h


def main(argv):
    if argv and argv[0] == '--check':
        files = sorted(glob.glob(os.path.join(argv[1], '*', '*.[Pp][Bb][Xx]')))
        ok = 0
        for f in files:
            try:
                data, h = unpack_pbx(f)
                ok += 1
                print('OK  %-24s prefix=%s %7d -> %8d chunks=%d/%d used=%d/%d' % (
                    os.path.relpath(f, argv[1]), h['prefix'].hex() or '-', h['packed'],
                    len(data), h['chunks_seen'], h['chunks'], h['used'], h['packed']))
            except Exception as e:
                print('ERR %-24s %s' % (os.path.relpath(f, argv[1]), e))
        print('%d/%d files unpacked with correct CRCs' % (ok, len(files)))
        return
    data, h = unpack_pbx(argv[0])
    print(h)
    if len(argv) > 1:
        open(argv[1], 'wb').write(data)


if __name__ == '__main__':
    main(sys.argv[1:])
