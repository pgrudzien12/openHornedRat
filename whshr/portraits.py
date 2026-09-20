"""Runtime compositing for the verified campaign speaker portraits."""

from .battlefield import read_sprite_sheet

# Glue's resident portrait list, notes/glue_portraits.md §1.  Index 36 is
# BACKALL itself and is not a foreground speaker.
PORTRAIT_SPRITES = {
    0: "CER1", 1: "CARL", 2: "COMM", 3: "SKA4", 4: "SCRI", 5: "MER1", 6: "DWA1", 7: "DWA2",
    8: "DWA3", 9: "DWA4", 10: "GOTR", 11: "ELF1", 12: "BRIW", 13: "MER2", 14: "REIK", 15: "ORC2",
    16: "GOB1", 17: "BERN", 18: "CER2", 19: "BERI", 20: "HOLG", 21: "ENGR", 22: "AZGU", 23: "AMBE",
    24: "GINF", 25: "RAMO", 26: "CARO", 27: "ART1", 28: "CELE", 29: "HALB", 30: "KEEL", 31: "XBOW",
    32: "TREE", 33: "HAMM", 34: "IRON", 35: "KING",
}

def load_sprite_sheet(game, name):
    """Decode one installation-resident FOL/BOP sprite set."""
    return read_sprite_sheet(
        name,
        game.binary_file(f"{name}.FOL").read_bytes(),
        game.binary_file(f"{name}.BOP").read_bytes(),
        game.binary_file(f"{name}.PAL").read_bytes() if game.find("FILE", "BINARY", f"{name}.PAL") else b"",
    )


def compose_portrait(palette, background, foreground):
    """Composite one decoded foreground frame over one background frame."""
    if (background.width, background.height) != (foreground.width, foreground.height):
        raise ValueError("speaker portrait and background dimensions do not match")

    rgba = bytearray()
    for back, pixel in zip(background.pixels, foreground.pixels):
        rgba.extend((*palette[pixel or back], 255))
    return background.width, background.height, bytes(rgba)


def speaker_portrait(installation, index, bkindex):
    """Compatibility wrapper around the shared content repository."""
    from .glue_content import GlueContent
    content = installation if isinstance(installation, GlueContent) else GlueContent(installation)
    return content.portrait_data(index, bkindex)


def dietrich_portrait(installation, bkindex=15):
    """Compatibility wrapper for callers that explicitly need index 4 / SCRI."""
    return speaker_portrait(installation, 4, bkindex)
