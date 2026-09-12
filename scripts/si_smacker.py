"""Minimal pure-Python Smacker (SMK2/SMK4) video decoder: dumps frames to PNG.

Used to verify the films rebuilt by si_omni.py visually without ffmpeg. Video and
palette only (audio is ignored; the .SI films have no audio tracks anyway).
Algorithm follows the public Smacker description (as implemented in ffmpeg/libsmacker).

Usage: si_smacker.py <file.smk> <out prefix> <frame> [<frame> ...] [--sheet N] [--scale S]
e.g.:  si_smacker.py extracted/si/A1/Scene1AnimA1.smk extracted/si/png/A1 0 100 400
       si_smacker.py extracted/si/A1/Scene1AnimA1.smk extracted/si/png/A1 --sheet 12
         (--sheet N: contact sheet of N frames evenly spread over the film, half size)
Frames are deltas, so decoding frame k decodes all frames 0..k.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_sprites import write_png  # noqa: E402

SMK_PAL = [int(i * 255 / 63 + 0.5) for i in range(64)]
BLOCK_RUNS = list(range(1, 60)) + [128, 256, 512, 1024, 2048]
NODE = 0x80000000


class Bits:
    """LSB-first bit reader."""
    def __init__(self, data):
        self.d, self.p = data, 0

    def bit(self):
        b = (self.d[self.p >> 3] >> (self.p & 7)) & 1
        self.p += 1
        return b

    def bits(self, n):
        v = 0
        for i in range(n):
            v |= self.bit() << i
        return v


def read_small_tree(br):
    """8-bit Huffman tree: 1 = node (left, right), 0 = leaf followed by 8-bit value."""
    if not br.bit():
        return None                            # tree absent: values decode as 0
    def rec():
        if br.bit():
            return (rec(), rec())
        return br.bits(8)
    t = rec()
    br.bit()                                   # trailing 0 bit
    return t


def small_decode(tree, br):
    if tree is None:
        return 0
    while isinstance(tree, tuple):
        tree = tree[br.bit()]
    return tree


class BigTree:
    """16-bit Huffman tree with a 3-entry recent-value cache (escape leaves)."""
    def __init__(self, br):
        self.present = br.bit()
        if not self.present:
            return
        low = read_small_tree(br)
        high = read_small_tree(br)
        esc = [br.bits(16) for _ in range(3)]
        self.vals, self.last = [], [-1, -1, -1]

        def rec():
            if not br.bit():                   # leaf
                v = small_decode(low, br) | (small_decode(high, br) << 8)
                idx = len(self.vals)
                for i in range(3):             # sequential ifs, as in ffmpeg
                    if v == esc[i]:
                        self.last[i] = idx
                        v = 0
                self.vals.append(v)
                return 1
            t = len(self.vals)
            self.vals.append(0)
            r = rec()
            self.vals[t] = NODE | r
            return r + 1 + rec()
        rec()
        br.bit()                               # trailing 0 bit
        for i in range(3):
            if self.last[i] == -1:
                self.last[i] = len(self.vals)
                self.vals.append(0)

    def reset(self):
        if self.present:
            for i in range(3):
                self.vals[self.last[i]] = 0

    def get(self, br):
        if not self.present:
            return 0
        vals, i = self.vals, 0
        while vals[i] & NODE:
            if br.bit():
                i += vals[i] & 0x7FFFFFFF
            i += 1
        v = vals[i]
        l0, l1, l2 = self.last
        if v != vals[l0]:
            vals[l2] = vals[l1]
            vals[l1] = vals[l0]
            vals[l0] = v
        return v


class Smacker:
    def __init__(self, data):
        self.d = data
        (sig, self.w, self.h, self.nframes, self.rate,
         self.flags) = struct.unpack_from('<4sIIIiI', data, 0)
        if sig not in (b'SMK2', b'SMK4'):
            raise ValueError('not a Smacker file')
        self.v4 = sig == b'SMK4'
        self.audio_size = struct.unpack_from('<7I', data, 24)
        trees_size = struct.unpack_from('<I', data, 52)[0]
        n = self.nframes + (self.flags & 1)
        self.sizes = struct.unpack_from('<%dI' % n, data, 104)
        self.types = data[104 + 4 * n:104 + 5 * n]
        tp = 104 + 5 * n
        br = Bits(data[tp:tp + trees_size])
        self.mmap, self.mclr, self.full, self.type = (BigTree(br) for _ in range(4))
        self.offsets, o = [], tp + trees_size
        for s in self.sizes:
            self.offsets.append(o)
            o += s & ~3
        self.pal = [0] * 768
        self.img = bytearray(self.w * self.h)
        self.cur = -1

    def _palette(self, chunk):
        old, pal = self.pal[:], self.pal
        p, sz = 0, 0
        while sz < 256 and p < len(chunk):
            t = chunk[p]
            p += 1
            if t & 0x80:                       # skip (keep) entries
                sz += (t & 0x7F) + 1
            elif t & 0x40:                     # copy from old palette
                off = chunk[p] * 3
                p += 1
                j = (t & 0x3F) + 1
                while j and sz < 256:
                    pal[sz * 3:sz * 3 + 3] = old[off:off + 3]
                    sz += 1
                    off += 3
                    j -= 1
            else:                              # new entry (6-bit components)
                pal[sz * 3:sz * 3 + 3] = [SMK_PAL[t], SMK_PAL[chunk[p] & 0x3F],
                                         SMK_PAL[chunk[p + 1] & 0x3F]]
                p += 2
                sz += 1

    def decode_next(self):
        self.cur += 1
        i = self.cur
        o, end = self.offsets[i], self.offsets[i] + (self.sizes[i] & ~3)
        ftype = self.types[i]
        if ftype & 1:
            ln = self.d[o] * 4
            self._palette(self.d[o + 1:o + ln])
            o += ln
        for a in range(7):
            if ftype & (2 << a):
                o += struct.unpack_from('<I', self.d, o)[0]
        self._video(Bits(self.d[o:end]))

    def _video(self, br):
        w, img = self.w, self.img
        bw, bh = self.w // 4, self.h // 4
        for t in (self.mmap, self.mclr, self.full, self.type):
            t.reset()
        blocks, blk = bw * bh, 0
        while blk < blocks:
            typ = self.type.get(br)
            run = BLOCK_RUNS[(typ >> 2) & 0x3F]
            kind = typ & 3                     # 0 mono, 1 full, 2 skip, 3 fill
            if kind == 2:                      # skip: keep previous frame's pixels
                blk += run
                continue
            mode = 0
            if kind == 1 and self.v4:
                if br.bit():
                    mode = 1
                elif br.bit():
                    mode = 2
            while run and blk < blocks:
                base = (blk // bw) * 4 * w + (blk % bw) * 4
                if kind == 0:                  # mono: 2 colours + 16-bit mask
                    clr = self.mclr.get(br)
                    m = self.mmap.get(br)
                    hi, lo = clr >> 8, clr & 0xFF
                    for y in range(4):
                        r = base + y * w
                        for x in range(4):
                            img[r + x] = hi if m & 1 else lo
                            m >>= 1
                elif kind == 1:                # full
                    if mode == 0:
                        for y in range(4):
                            r = base + y * w
                            p = self.full.get(br)
                            img[r + 2], img[r + 3] = p & 0xFF, p >> 8
                            p = self.full.get(br)
                            img[r], img[r + 1] = p & 0xFF, p >> 8
                    elif mode == 1:            # SMK4 double
                        for y in range(2):
                            p = self.full.get(br)
                            a, b = p & 0xFF, p >> 8
                            for yy in range(2):
                                r = base + (2 * y + yy) * w
                                img[r:r + 4] = bytes([a, a, b, b])
                            # upper pixels come first in ffmpeg (a = left pair)
                    else:                      # SMK4 half
                        for y in range(2):
                            p1 = self.full.get(br)
                            p2 = self.full.get(br)
                            r = base + 2 * y * w
                            img[r:r + 4] = bytes([p2 & 0xFF, p2 >> 8, p1 & 0xFF, p1 >> 8])
                            img[r + w:r + w + 4] = img[r:r + 4]
                else:                          # fill
                    c = typ >> 8
                    for y in range(4):
                        r = base + y * w
                        img[r:r + 4] = bytes([c, c, c, c])
                blk += 1
                run -= 1

    def rgb(self, scale_down=1):
        pal, img, w, h = self.pal, self.img, self.w, self.h
        out = bytearray()
        for y in range(0, h, scale_down):
            row = img[y * w:(y + 1) * w:scale_down]
            for c in row:
                out += bytes(pal[c * 3:c * 3 + 3])
        return w // scale_down, h // scale_down, out

    def decode_to(self, k):
        if k < self.cur:
            self.__init__(self.d)
        while self.cur < k:
            self.decode_next()


def main(argv):
    path, prefix = argv[0], argv[1]
    rest = argv[2:]
    sheet = None
    if '--sheet' in rest:
        i = rest.index('--sheet')
        sheet = int(rest[i + 1])
        del rest[i:i + 2]
    smk = Smacker(open(path, 'rb').read())
    print('%s: %dx%d, %d frames, rate %d, flags %d' % (path, smk.w, smk.h, smk.nframes,
                                                        smk.rate, smk.flags))
    os.makedirs(os.path.dirname(prefix) or '.', exist_ok=True)
    for k in sorted(int(x) for x in rest):
        smk.decode_to(k)
        w, h, rgb = smk.rgb()
        out = '%s_f%04d.png' % (prefix, k)
        write_png(out, w, h, rgb)
        print('  frame %d (t = %.3f s at 125 ms/frame) -> %s' % (k, k * 0.125, out))
    if sheet:
        idx = [round(i * (smk.nframes - 1) / max(sheet - 1, 1)) for i in range(sheet)]
        cols = 3
        tiles = []
        for k in idx:
            smk.decode_to(k)
            tiles.append(smk.rgb(2))
        tw, th = tiles[0][0], tiles[0][1]
        rows = (len(tiles) + cols - 1) // cols
        W, H = cols * tw + (cols - 1) * 4, rows * th + (rows - 1) * 4
        canvas = bytearray(b'\x40' * (W * H * 3))
        for n, (_, _, rgb) in enumerate(tiles):
            ox, oy = (n % cols) * (tw + 4), (n // cols) * (th + 4)
            for y in range(th):
                dst = ((oy + y) * W + ox) * 3
                canvas[dst:dst + tw * 3] = rgb[y * tw * 3:(y + 1) * tw * 3]
        out = '%s_sheet.png' % prefix
        write_png(out, W, H, canvas)
        print('  sheet of frames %s -> %s' % (idx, out))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1:])
