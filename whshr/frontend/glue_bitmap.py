"""Convert headless glue bitmaps from ``GlueContent`` into pygame surfaces."""

import re

import pygame


# Glue's gettentpos position table; notes/campaign_tent.md §3.
TENT_POSITIONS = ((405, 332), (405, 332), (405, 332), (452, 316), (405, 332), (410, 346), (415, 349),
                  (367, 288), (367, 288), (508, 215), (351, 309), (416, 243), (462, 209), (493, 194),
                  (505, 195), (285, 187), (261, 159), (285, 187), (276, 238), (192, 214), (244, 269))


def bitmap_frame_name(spec, frame=None):
    """Resolve a glue [BITMAP] cell-set base to its current resource name."""
    start = spec.get("animstartframe")
    if frame is None:
        frame = start
    if start is None or start == -1 or start == spec.get("animstopframe", start):
        return spec["bitmap"]
    return re.sub(r"\d+$", "", spec["bitmap"]) + str(frame)


def load_bitmap(content, name, *, app_palette=None):
    """Return an RGBA surface for a bitmap already owned by ``GlueContent``.

    Existing compatibility views retain the bitmap's embedded table until they
    opt into an ``AppPalette``.  The generic glue view will pass that palette,
    which maps every source index through one application-wide colour table
    and makes index zero transparent.
    """
    bitmap = content.bitmap_data(name)
    if app_palette is not None:
        rgba = app_palette.rgba(bitmap.pixels)
    else:
        rgba = bytearray(bitmap.width * bitmap.height * 4)
        for offset, palette_index in enumerate(bitmap.pixels):
            red, green, blue = bitmap.palette[palette_index]
            rgba[offset * 4:offset * 4 + 4] = bytes((red, green, blue, 255))
    return pygame.image.frombuffer(rgba, (bitmap.width, bitmap.height), "RGBA").copy()
