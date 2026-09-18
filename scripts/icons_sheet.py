"""Render a labelled contact sheet for the general-purpose ICONS.FOL UI sheet.

Usage: python3 scripts/icons_sheet.py <WARFB> extracted/icons_sheet.png [--cols=15] [--scale=2]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim_lib import Canvas  # noqa: E402

from whshr.battlefield import read_sprite_sheet
from whshr.image import load_rgb_palette
from whshr.paths import Installation


def render(sheet, palette, cols=15):
    """Return a labelled contact sheet made with the runtime FOL/BOP decoder."""
    cell_width = max(frame.width for frame in sheet.frames) + 4
    cell_height = max(frame.height for frame in sheet.frames) + 10
    rows = (len(sheet.frames) + cols - 1) // cols
    canvas = Canvas(cell_width * cols, cell_height * rows)
    for index, frame in enumerate(sheet.frames):
        left, top = (index % cols) * cell_width + 2, (index // cols) * cell_height + 8
        canvas.fill(left, top, frame.width, frame.height, (56, 56, 66))
        for y in range(frame.height):
            for x in range(frame.width):
                color_index = frame.pixels[y * frame.width + x]
                if color_index:
                    canvas.dot(left + x, top + y, palette[color_index])
        canvas.text(left, top - 7, str(index), (255, 255, 255))
    return canvas


def main(argv):
    options = {arg[2:].split("=", 1)[0]: arg.split("=", 1)[1] if "=" in arg else True
               for arg in argv if arg.startswith("--")}
    args = [arg for arg in argv if not arg.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    game = Installation(args[0])
    sheet = read_sprite_sheet("ICONS", game.binary_file("ICONS.FOL").read_bytes(),
                              game.binary_file("ICONS.BOP").read_bytes(),
                              game.binary_file("ICONS.PAL").read_bytes())
    palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    canvas = render(sheet, palette, int(options.get("cols", 15)))
    canvas.png(args[1], int(options.get("scale", 2)))
    print(f"{args[1]}: {len(sheet.frames)} frames, {canvas.w}x{canvas.h}")


if __name__ == "__main__":
    main(sys.argv[1:])
