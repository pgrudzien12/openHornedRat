"""PE (Win32 .EXE/.DLL) resource directory parser in pure Python (no pefile needed).

Usage:
  pe_resources.py <file.DLL>            list resources: type / name / language / size
  pe_resources.py <file.DLL> --summary  resource count and bytes per type

e.g.:  pe_resources.py ".../WARFB/FILE/DLL/BKTXT.DLL" --summary

API:
  PE(path).resources()  -> list of Resource(type, name, lang, rva, size, codepage)
  PE(path).data(res)    -> resource bytes (RVA translated to a file offset)
Type and name are an int (numeric ID) or a str (UTF-16 name stored in the directory).
"""
import struct, sys
from collections import namedtuple

RT_NAMES = {
    1: 'RT_CURSOR', 2: 'RT_BITMAP', 3: 'RT_ICON', 4: 'RT_MENU', 5: 'RT_DIALOG',
    6: 'RT_STRING', 7: 'RT_FONTDIR', 8: 'RT_FONT', 9: 'RT_ACCELERATOR', 10: 'RT_RCDATA',
    11: 'RT_MESSAGETABLE', 12: 'RT_GROUP_CURSOR', 14: 'RT_GROUP_ICON', 16: 'RT_VERSION',
    17: 'RT_DLGINCLUDE', 19: 'RT_PLUGPLAY', 20: 'RT_VXD', 21: 'RT_ANICURSOR', 22: 'RT_ANIICON',
    23: 'RT_HTML', 24: 'RT_MANIFEST',
}

Resource = namedtuple('Resource', 'type name lang rva size codepage')


def type_name(t):
    return RT_NAMES.get(t, str(t)) if isinstance(t, int) else repr(t)


class PE:
    def __init__(self, path):
        self.path = path
        self.buf = open(path, 'rb').read()
        b = self.buf
        if b[:2] != b'MZ':
            raise ValueError(f"{path}: no MZ signature")
        pe = struct.unpack_from('<I', b, 0x3C)[0]
        if b[pe:pe + 4] != b'PE\0\0':
            raise ValueError(f"{path}: no PE signature")
        self.machine, nsec, self.timestamp, _, _, opt_size, self.characteristics = \
            struct.unpack_from('<HHIIIHH', b, pe + 4)
        opt = pe + 24
        magic = struct.unpack_from('<H', b, opt)[0]
        if magic != 0x10B:
            raise ValueError(f"{path}: not PE32 (magic {magic:#x})")
        self.image_base = struct.unpack_from('<I', b, opt + 28)[0]
        ndirs = struct.unpack_from('<I', b, opt + 92)[0]
        self.dirs = [struct.unpack_from('<II', b, opt + 96 + 8 * i) for i in range(ndirs)]
        self.sections = []
        for i in range(nsec):
            o = opt + opt_size + 40 * i
            name = b[o:o + 8].rstrip(b'\0').decode('latin-1')
            vsize, va, rsize, rptr = struct.unpack_from('<IIII', b, o + 8)
            self.sections.append((name, va, vsize, rptr, rsize))

    def rva2off(self, rva):
        for name, va, vsize, rptr, rsize in self.sections:
            if va <= rva < va + max(vsize, rsize):
                return rva - va + rptr
        raise ValueError(f"RVA {rva:#x} outside all sections")

    def resources(self):
        """Walks the 3-level directory (type -> name -> language) of data directory #2."""
        if len(self.dirs) < 3 or not self.dirs[2][0]:
            return []
        b, base = self.buf, self.rva2off(self.dirs[2][0])
        out = []

        def entries(off):
            _, _, _, _, nnamed, nid = struct.unpack_from('<IIHHHH', b, base + off)
            for i in range(nnamed + nid):
                name, target = struct.unpack_from('<II', b, base + off + 16 + 8 * i)
                if name & 0x80000000:          # string name: u16 length + UTF-16LE
                    p = base + (name & 0x7FFFFFFF)
                    n = struct.unpack_from('<H', b, p)[0]
                    name = b[p + 2:p + 2 + 2 * n].decode('utf-16-le')
                yield name, target

        for t, t_off in entries(0):
            for n, n_off in entries(t_off & 0x7FFFFFFF):
                for lang, leaf in entries(n_off & 0x7FFFFFFF):
                    rva, size, cp, _ = struct.unpack_from('<IIII', b, base + leaf)
                    out.append(Resource(t, n, lang, rva, size, cp))
        return out

    def data(self, res):
        o = self.rva2off(res.rva)
        return self.buf[o:o + res.size]


def main(path, summary=False):
    pe = PE(path)
    res = pe.resources()
    if summary:
        agg = {}
        for r in res:
            c = agg.setdefault(type_name(r.type), [0, 0])
            c[0] += 1
            c[1] += r.size
        print(f"{path}: {len(res)} resources, sections {[s[0] for s in pe.sections]}")
        for k, (n, s) in sorted(agg.items()):
            print(f"  {k:20s} {n:6d} items {s:10d} B")
        return
    for r in res:
        print(f"{type_name(r.type):16s} {r.name!s:>24s} lang={r.lang:#06x} size={r.size}")


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    else:
        main(a[0], '--summary' in a)
