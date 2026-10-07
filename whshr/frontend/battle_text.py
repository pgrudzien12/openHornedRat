"""Turn GMTXT battle formatting into plain text for the HUD log."""

import re

_STYLE = re.compile(r"@@\([fc]\d+\)")


def display_text(value: str) -> str:
    """Remove font/colour commands and render the game's underscore spaces."""
    return _STYLE.sub("", value).replace("_", " ")


def reaction_text(value: str) -> str:
    """The HUD draws the `%s:` regiment label separately in bold."""
    return display_text(value).removeprefix("%s:").lstrip()
