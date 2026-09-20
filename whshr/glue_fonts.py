"""Verified WHSHR.EXE glue-font slot mapping (notes/fonts_glue.md §2)."""

from .assets import AssetId


GLUE_FONT_FILES = {
    1: "GLUE/MAPTEXT1.FON", 2: "GLUE/PCTEXT.FON", 3: "GLUE/SMAPTEX1.FON",
    4: "GLUE/SUBTEXT.FON", 5: "GLUE/GOTHTEXT.FON", 6: "GLUE/PCTEXTB.FON",
}


def glue_font_asset(slot):
    """Return the catalog identity for a verified glue font slot."""
    if slot not in GLUE_FONT_FILES:
        raise ValueError(f"unknown glue font slot {slot}")
    return AssetId("vanilla", "font", f"glue{slot}")
