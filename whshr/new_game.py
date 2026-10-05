"""New Game: the commander-name rules (notes/native-windows.md §7).

A new campaign is a fresh ``CampaignState`` built from the installation's shipped templates; the engine
keeps campaign state only in its JSON save slots, so the original's working-file reset needs no files.
"""

NAME_LIMIT = 15  # notes/native-windows.md §7.3.2: buffer of 16 -> 15 typed characters
NAME_PUNCTUATION = "!\"'(),.:;?"
PROMPT_CAPTION = "Enter your name"  # the original's caption is fixed English text with no string id (§7.5)

def accepts_character(char: str) -> bool:
    """Only ASCII letters, digits, space and ``! " ' ( ) , . : ; ?`` are typed; ``_`` and ``<`` (the file
    encodings of a space), ``-``, ``/`` and non-ASCII are refused (§7.3.4)."""
    return len(char) == 1 and char.isascii() and (char.isalnum() or char == " " or char in NAME_PUNCTUATION)


def filter_name(text: str) -> str:
    """``text`` reduced to the accepted characters and to the length limit."""
    return "".join(char for char in text if accepts_character(char))[:NAME_LIMIT]
