"""Checks the glue palette rule of notes/palette_selection.md against BITMAP.DLL and WND.DLL.

Usage: glue_palette_check.py <WARFB directory> [--check]

Every 8 bpp bitmap is painted by copying its pixel *indices*; the colours come from the active application palette, so the only
question is which palette is active. This script measures, per bitmap, how many pixels use a palette index (10..245, index 0 is the
transparent key) whose colour in the bitmap's own colour table differs from the colour in a candidate application palette
(STANDARD, or a WIND+GLUE pair). It then reports:
  1. for every window resource with `set:palindex=N` (N >= 1): the mismatch of all bitmaps it draws (own and [INCLUDE]d) against
     the pair N selects;
  2. all bitmaps of BITMAP.DLL grouped by the set of candidate palettes that reproduce them exactly;
  3. which bitmaps use the Windows system-colour slots (indices 1-9 and 246-255).
--check exits non-zero if a palindex window has any mismatch.
"""
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fon_glue_palettes import dib, glue_pals, read_pal  # noqa: E402
from pe_resources import PE  # noqa: E402
from whshr.campaign import load_wnd_rcdata  # noqa: E402
from whshr.glue import WindowDefinition, parse_glue_resources  # noqa: E402

PAIRS = {1: "BOOK", 2: "MAP", 3: "CAR", 4: "MIND", 5: "END", 6: "TITL", 7: "GAME", 8: "OPT", 9: "BK2"}


class Palettes:
    def __init__(self, root):
        self.glue = glue_pals(root)
        standard = glob.glob(os.path.join(root, "FILE", "BINARY", "STANDARD.PAL"))[0]
        self.standard = dict(read_pal(standard)[0])

    def pair(self, name):
        if name == "STANDARD":
            return dict(self.standard)
        merged = dict(self.glue["WIND" + name])
        merged.update(self.glue["GLUE" + name])
        return merged


class Bitmaps:
    def __init__(self, root):
        self.pe = PE(os.path.join(root, "FILE", "DLL", "BITMAP.DLL"))
        self.resources = {str(r.name).upper(): r for r in self.pe.resources() if r.type == 2}
        self._usage = {}

    def usage(self, name):
        """(index histogram, colour table) of an 8 bpp uncompressed bitmap, else None."""
        if name not in self._usage:
            resource = self.resources.get(name)
            result = None
            if resource is not None:
                width, height, bpp, compression, table, pixels = dib(self.pe, resource)
                if bpp == 8 and compression == 0:
                    stride = (width + 3) // 4 * 4
                    result = (collections.Counter(pixels[:stride * abs(height)]), table)
            self._usage[name] = result
        return self._usage[name]

    def names_for(self, base):
        base = base.upper()
        if base in self.resources:
            return [base]
        return sorted(k for k in self.resources if re.fullmatch(re.escape(base) + r"\d+", k))

    def mismatch(self, name, palette):
        """(differing pixels, counted pixels) over indices 10..245."""
        usage = self.usage(name)
        if not usage:
            return None
        histogram, table = usage
        counted = bad = 0
        for index, count in histogram.items():
            if 10 <= index <= 245:
                counted += count
                if (table[index] if index < len(table) else None) != palette.get(index):
                    bad += count
        return bad, counted


def window_bitmaps(resources, bitmaps, name, seen=None):
    seen = seen if seen is not None else set()
    if name in seen:
        return []
    seen.add(name)
    window = resources.get(name.upper())
    if not isinstance(window, WindowDefinition):
        return []
    found = []
    for record in window.records:
        for item in record.fields:
            if item.command == "setbitmap":
                found += bitmaps.names_for(item.argument.strip())
            elif item.command == "script" and record.block_type == "INCLUDE":
                found += window_bitmaps(resources, bitmaps, item.argument.strip(), seen)
    return found


def window_palindex(window):
    for record in window.records:
        for item in record.fields:
            if item.command == "set" and item.argument.lower().startswith("palindex="):
                return int(item.argument.split("=", 1)[1])
    return None


def report(root):
    palettes, bitmaps = Palettes(root), Bitmaps(root)
    resources = parse_glue_resources(load_wnd_rcdata(os.path.join(root, "FILE", "DLL", "WND.DLL")))
    failures = []
    print("== windows with palindex >= 1: mismatch of their bitmaps against the selected pair")
    groups = collections.defaultdict(lambda: [0, 0, 0])
    for name, window in sorted(resources.items()):
        if not isinstance(window, WindowDefinition):
            continue
        index = window_palindex(window)
        if index is None or index < 1:
            continue
        pair = palettes.pair(PAIRS[index])
        bad = counted = 0
        for bitmap in set(window_bitmaps(resources, bitmaps, name)):
            result = bitmaps.mismatch(bitmap, pair)
            if result:
                bad += result[0]
                counted += result[1]
        groups[index][0] += 1
        groups[index][1] += bad
        groups[index][2] += counted
        if bad:
            failures.append(name)
    for index, (windows, bad, counted) in sorted(groups.items()):
        print(f"palindex {index} ({PAIRS[index]}): {windows} windows, {bad} of {counted} used pixels differ")

    print("== BITMAP.DLL bitmaps grouped by the candidate palettes that reproduce them exactly")
    candidates = {"STANDARD": palettes.pair("STANDARD")}
    candidates.update({name: palettes.pair(name) for name in PAIRS.values()})
    rend = dict(palettes.glue["WINDBOOK"])
    rend.update(palettes.glue["GLUEREND"])
    candidates["GLUEREND+WINDBOOK"] = rend
    grouped = collections.defaultdict(list)
    for name in sorted(bitmaps.resources):
        if not bitmaps.usage(name):
            continue
        exact = tuple(c for c, p in candidates.items() if not bitmaps.mismatch(name, p)[0])
        grouped[exact or ("none",)].append(name)
    for key, names in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        print(f"{len(names):4d} {'/'.join(key)}: {', '.join(names[:6])}")

    print("== bitmaps using Windows system-colour slots (indices 1-9, 246-255)")
    users = collections.defaultdict(set)
    for name in bitmaps.resources:
        usage = bitmaps.usage(name)
        if usage:
            for index in usage[0]:
                if 1 <= index <= 9 or index >= 246:
                    users[name].add(index)
    for name, indices in sorted(users.items()):
        print(f"  {name}: {sorted(indices)}")
    return failures


def main(argv):
    root = argv[1]
    failures = report(root)
    if "--check" in argv and failures:
        print("MISMATCH in palindex windows:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
