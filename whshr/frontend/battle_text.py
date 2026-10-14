"""Turn GMTXT battle formatting into plain text for the HUD log."""

import re
from collections.abc import Callable, Mapping, Sequence
from typing import cast

from .. import magic
from ..objectives import ITEM_NUMBERS

_STYLE = re.compile(r"@@\([fc]\d+\)")

ITEM_NAME_TEXT_BASE = 31000  # GMTXT name id = 31000 + item number (31007 Potion of Strength, game_rules.md)
SPELL_NAME_TEXT_BASE = 30003  # GMTXT name id = 30003 + spell code (30004 Wind Blast, notes/player_magic_panel.md 1.1)


def display_text(value: str) -> str:
    """Remove font/colour commands and render the game's underscore spaces."""
    return _STYLE.sub("", value).replace("_", " ")


def reaction_text(value: str) -> str:
    """The HUD draws the `%s:` regiment label separately in bold."""
    return display_text(value).removeprefix("%s:").lstrip()


def spell_name(texts: Mapping[int, str], code: int) -> str:
    """The spell's GMTXT name, else its catalogue name, else its code."""
    name = texts.get(SPELL_NAME_TEXT_BASE + code)
    if name:
        return display_text(name)
    spell = magic.SPELLS.get(code)
    return spell.name if spell is not None else str(code)


def item_name(texts: Mapping[int, str], item: str) -> str:
    """The item's GMTXT name (31000 + its item number, notes/game_rules.md magic item effects), else its id."""
    name = texts.get(ITEM_NAME_TEXT_BASE + ITEM_NUMBERS.index(item)) if item in ITEM_NUMBERS else None
    if name:
        return display_text(name)
    return item.removeprefix("Item").replace("Of", " of ").replace("The", " the ")


def message_arguments(texts: Mapping[int, str], arguments: Sequence[Sequence[object]],
                      unit_name: Callable[[str], str | None]) -> tuple[str, ...]:
    """Resolve an event's `text_args` -- ("unit", id), ("spell", code) or ("item", item id) pairs, in the order of
    the message's `%s` slots -- to display names. A unit no longer in the battle shows its id."""
    names: list[str] = []
    for kind, value in arguments:
        if kind == "spell" and isinstance(value, int):
            names.append(spell_name(texts, value))
        elif kind == "item" and isinstance(value, str):
            names.append(item_name(texts, value))
        else:
            names.append(unit_name(str(value)) or str(value))
    return tuple(names)


def fill_message(message: str, data: Mapping[str, object], texts: Mapping[int, str],
                 unit_name: Callable[[str], str | None]) -> str:
    """Fill a battle message's `%s` slots from its event data: every slot from `text_args` when the event carries
    them (a cast failure names the caster and the spell), else the one slot from `target_name`, or the name of the
    `target` or `regiment` unit. A message whose slots cannot all be filled is returned unchanged."""
    if "%s" not in message:
        return message
    arguments = data.get("text_args")
    names: tuple[str, ...]
    if isinstance(arguments, (list, tuple)):
        names = message_arguments(texts, cast(Sequence[Sequence[object]], arguments), unit_name)
    else:
        named = data.get("target") or data.get("regiment")
        display_name = data.get("target_name") or (unit_name(named) if isinstance(named, str) else None)
        if not isinstance(display_name, str):
            return message
        names = (display_name,)
    try:
        return message % names
    except (TypeError, ValueError):
        return message
