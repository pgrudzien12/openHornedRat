"""The portrait's reaction line: poke the rat's face and it complains, the way Dietrich does in the caravan.

In the caravan screens, clicking the reaction hotspot over Dietrich's face shows one red line from the game's own
dialogue text table (``BRTXT`` 155; reaction hotspots: notes/native-windows.md §14.9 item 7), typed out like
dialogue and then cleared (notes/briefing_dialogue.md §3.4 colour ``red``, §3.5 timing). The launcher shows the
same line, read from the user's installation at runtime; without a readable installation the face does not react.
Stdlib only, like the rest of the launcher.
"""

from os import PathLike

REACTION_TABLE = "BRTXT"
REACTION_TEXT_ID = 155  # the caravan reaction hotspot over Dietrich's face (notes/native-windows.md §14.9)
REACTION_COLOUR = "#ff0000"  # settextcolor "red" (notes/briefing_dialogue.md §3.4)
CHAR_MILLISECONDS = 50  # one character every two 25 ms ticks (notes/briefing_dialogue.md §3.5)
HOLD_MILLISECONDS = 750  # the finished line stays 30 ticks before it clears (§3.5, no speech)


def load_reaction_text(installation: str | PathLike[str]) -> str | None:
    """The reaction line from ``installation``'s text tables, or None when it cannot be read."""
    from whshr.glue_content import GlueContent  # deferred: only needed once the face is poked

    try:
        text = GlueContent(installation).string(REACTION_TABLE, REACTION_TEXT_ID)
    except Exception:  # a missing, partial or unreadable installation just leaves the face silent
        return None
    return text.strip() or None


class ReactionLine:
    """One line being typed: :meth:`advance` returns the visible text, then None once it has cleared.

    ``hold_ms`` is how long the finished line stays; None keeps it until it is replaced (the launcher's update
    notice uses the same typing for its own line).
    """

    def __init__(self, text: str, hold_ms: float | None = HOLD_MILLISECONDS) -> None:
        self.text = text
        self.hold_ms = hold_ms
        self.elapsed_ms = 0.0

    def advance(self, milliseconds: float) -> str | None:
        self.elapsed_ms += milliseconds
        typing_ms = len(self.text) * CHAR_MILLISECONDS
        if self.hold_ms is not None and self.elapsed_ms >= typing_ms + self.hold_ms:
            return None
        return self.text[:min(len(self.text), int(self.elapsed_ms // CHAR_MILLISECONDS))]
