"""Render the three banner variants used by a battle into a labelled contact sheet.

Usage: python3 scripts/banners_sheet.py <WARFB> <BFxxx.BTS> extracted/banners.png [--scale=2]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim_lib import Canvas  # noqa: E402

from whshr.battlefield import read_sprite_sheet, resource_files, script_units
from whshr.image import load_rgb_palette
from whshr.paths import Installation
from whshr.script import load_battle, resource_name


FRAME_ROLES = ("HUD 72X104", "MAP 16X24", "TROOP 32X32")


def banner_sheets(game, battle_name):
    """Return each distinct script banner in battle order, decoded through the runtime path."""
    script = load_battle(str(game.file_dir("SCRIPT", battle_name)))
    bases = resource_files(game, {"banners"})
    resources = dict.fromkeys(resource_name(unit.get("banner")) for unit in script_units(script)
                              if unit.get("banner"))
    sheets = []
    for resource in resources:
        base = bases.get(resource.casefold())
        if base is None:
            continue
        sheet = read_sprite_sheet(base, game.binary_file(base + ".FOL").read_bytes(),
                                  game.binary_file(base + ".BOP").read_bytes(),
                                  game.binary_file(base + ".PAL").read_bytes())
        sheets.append((resource, sheet))
    return sheets


def render(sheets, palette):
    """Render one 72×104, 16×24 and 32×32 frame per distinct banner."""
    cell_width, row_height = 80, 124
    canvas = Canvas(cell_width * 3, max(1, len(sheets)) * row_height)
    for row, (resource, sheet) in enumerate(sheets):
        top = row * row_height
        canvas.text(1, top + 1, resource[:18], (180, 210, 255))
        for index, frame in enumerate(sheet.frames[:3]):
            left = index * cell_width + 2
            canvas.fill(left, top + 12, frame.width, frame.height, (56, 56, 66))
            for y in range(frame.height):
                for x in range(frame.width):
                    color_index = frame.pixels[y * frame.width + x]
                    if color_index:
                        canvas.dot(left + x, top + 12 + y, palette[color_index])
            canvas.text(left, top + 116, FRAME_ROLES[index], (255, 255, 255))
    return canvas


def main(argv):
    options = {arg[2:].split("=", 1)[0]: arg.split("=", 1)[1] if "=" in arg else True
               for arg in argv if arg.startswith("--")}
    args = [arg for arg in argv if not arg.startswith("--")]
    if len(args) != 3:
        raise SystemExit(__doc__)
    game = Installation(args[0])
    canvas = render(banner_sheets(game, args[1]), load_rgb_palette(game.binary_file("STANDARD.PAL")))
    canvas.png(args[2], int(options.get("scale", 2)))
    print(f"{args[2]}: {canvas.w}x{canvas.h}")


if __name__ == "__main__":
    main(sys.argv[1:])
