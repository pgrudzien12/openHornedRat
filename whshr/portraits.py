"""Runtime compositing for the verified campaign speaker portraits."""

from .battlefield import read_sprite_sheet
from .image import load_rgb_palette
from .paths import Installation

PORTRAIT_SPRITES = {4: "SCRI"}  # Verified glue-index mapping; extend only with evidence.

def _sprite_sheet(game, name):
    """Decode one installation-resident FOL/BOP sprite set."""
    return read_sprite_sheet(
        name,
        game.binary_file(f"{name}.FOL").read_bytes(),
        game.binary_file(f"{name}.BOP").read_bytes(),
        game.binary_file(f"{name}.PAL").read_bytes() if game.find("FILE", "BINARY", f"{name}.PAL") else b"",
    )


def speaker_portrait(installation, index, bkindex):
    """Return a stopped-pose composite selected by a window ``[ANIM]`` block."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    try:
        sprite_name = PORTRAIT_SPRITES[index]
    except KeyError:
        raise ValueError(f"no verified portrait sprite mapping for glue index {index}") from None
    palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    background = _sprite_sheet(game, "BACKALL").frames[bkindex]
    foreground = _sprite_sheet(game, sprite_name).frames[0]
    if (background.width, background.height) != (foreground.width, foreground.height):
        raise ValueError("speaker portrait and background dimensions do not match")

    rgba = bytearray()
    for back, pixel in zip(background.pixels, foreground.pixels):
        rgba.extend((*palette[pixel or back], 255))
    return background.width, background.height, bytes(rgba)


def dietrich_portrait(installation, bkindex=15):
    """Compatibility wrapper for callers that explicitly need index 4 / SCRI."""
    return speaker_portrait(installation, 4, bkindex)
