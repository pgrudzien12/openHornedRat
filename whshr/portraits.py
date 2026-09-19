"""Runtime compositing for the verified campaign speaker portraits."""

from .battlefield import read_sprite_sheet
from .image import load_rgb_palette
from .paths import Installation


def _sprite_sheet(game, name):
    """Decode one installation-resident FOL/BOP sprite set."""
    return read_sprite_sheet(
        name,
        game.binary_file(f"{name}.FOL").read_bytes(),
        game.binary_file(f"{name}.BOP").read_bytes(),
        game.binary_file(f"{name}.PAL").read_bytes() if game.find("FILE", "BINARY", f"{name}.PAL") else b"",
    )


def dietrich_portrait(installation, bkindex=15):
    """Return Dietrich's stopped-pose composite for one data-selected backdrop.

    Glue index 4 is verified as ``SCRI``; ``bkindex`` comes from the
    sub-window's ``[ANIM]`` block. Talking/blink timing remains unimplemented.
    """
    game = installation if isinstance(installation, Installation) else Installation(installation)
    palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    background = _sprite_sheet(game, "BACKALL").frames[bkindex]
    scribe = _sprite_sheet(game, "SCRI").frames[0]
    if (background.width, background.height) != (scribe.width, scribe.height):
        raise ValueError("Dietrich portrait and background dimensions do not match")

    rgba = bytearray()
    for back, foreground in zip(background.pixels, scribe.pixels):
        index = foreground or back
        rgba.extend((*palette[index], 255))
    return background.width, background.height, bytes(rgba)
