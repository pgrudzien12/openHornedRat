# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Convert headless glue bitmaps from ``GlueContent`` into pygame surfaces."""

import re
from collections.abc import Mapping
from typing import Any

import pygame

from ..glue_content import GlueContent
from ..glue_palette import AppPalette

from ..glue_runtime import TENT_POSITIONS as TENT_POSITIONS  # re-exported for the legacy compatibility view


def bitmap_frame_name(spec: Mapping[str, Any], frame: int | None = None) -> str:
    """Resolve a glue [BITMAP] cell-set base to its current resource name."""
    start = spec.get("animstartframe")
    if frame is None:
        frame = start
    if start is None or start == -1 or start == spec.get("animstopframe", start):
        return spec["bitmap"]
    return re.sub(r"\d+$", "", spec["bitmap"]) + str(frame)


def load_bitmap(content: GlueContent, name: str, *, app_palette: AppPalette | None = None) -> pygame.Surface:
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


def load_optional_bitmap(content: GlueContent, name: str, *,
                         app_palette: AppPalette | None = None) -> pygame.Surface | None:
    """Load a glue bitmap, treating an unresolved dynamic base as transparent.

    Window paint uses the stored ``setbitmap`` name before an animation's first
    timer step.  Many animated bases (for example ``Tent4``) are deliberately
    not bitmap resources; their numbered frame is the first drawable image.
    """
    try:
        return load_bitmap(content, name, app_palette=app_palette)
    except FileNotFoundError:
        return None
