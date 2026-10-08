"""Allied NPC regiments in battles that define objective G or I (notes/allied_npc_merge.md).

Pure helpers on script unit views (`whshr.script.unit_view`): the army merge of objective G rebuilds an allied NPC
from the company's regiment; objective I's artillery swap is applied by the battle builder on the finished
regiments (`Battle.from_script`).
"""
import copy
from collections.abc import Mapping, Sequence
from typing import Any

from .rules import Side, side_of_code

View = dict[str, Any]

REGIMENT_LIMIT = 50  # NPCs with a whoami at or above this are story units: never merged, never written back
NPC_SIDE_BITS = 0xC0
TYPE_BITS = 0x3F


def objective_value(objectives: Sequence[Sequence[Any]] | None, letter: str) -> int | None:
    """The first value of objective `letter` in a battle's list, or None when the letter is not defined."""
    for entry in objectives or ():
        if entry and str(entry[0]).upper() == letter:
            try:
                return int(entry[1]) if len(entry) > 1 else 0
            except (TypeError, ValueError):
                return 0
    return None


def numbered_regiment(unit: Mapping[str, Any]) -> int | None:
    """The roster number a script unit carries, whatever its side, or None when it has none (no `set:whoami` line,
    which counts as having no regiment: notes/allied_npc_merge.md section 4) or is a story unit (50 and up)."""
    whoami = (unit.get("set") or {}).get("whoami")
    if whoami is None:
        return None
    whoami = int(whoami) & 0xFF
    return whoami if whoami < REGIMENT_LIMIT else None


def npc_regiment(unit: Mapping[str, Any]) -> int | None:
    """The roster number of an allied NPC unit (side code `0x40` at battle start) that can be merged, else None."""
    side_byte = (unit.get("stats") or {}).get("s_side", [None])[0]
    if side_of_code(side_byte) != Side.NEUTRAL:
        return None
    return numbered_regiment(unit)


def _models(unit: Mapping[str, Any]) -> int:
    stats = (unit.get("stats") or {}).get("s_side", [])
    return int(stats[2] if len(stats) > 2 else stats[1] if len(stats) > 1 else 1)


def merge_npc(unit: View, marching: Sequence[int] | set[int], company: Mapping[int, View]) -> View | None:
    """Objective G's army merge for one allied NPC unit (section 3.1): None when the NPC is deleted (its regiment
    marches, is not in the company, or has no men left), else the unit rebuilt from the company's regiment.

    From the company: name, stat line with the current model count, leader profile, psychology (inside the stat
    line), experience, spells and items. From the script: id, hidden state, sprites, position, facing,
    behaviour script, whoami, `hired`, the casualty counters, and the NPC side bits."""
    whoami = npc_regiment(unit)
    if whoami is None:
        return unit
    source = company.get(whoami)
    if whoami in marching or source is None or _models(source) <= 0:
        return None
    merged = copy.deepcopy(source)
    for key in ("id", "hidden", "sprites"):
        merged[key] = copy.deepcopy(unit.get(key))
    merged["set"] = {**copy.deepcopy(unit["set"])}
    for key in ("s_Exp", "psy_status"):  # experience and psychology come from the company, even when it has none
        if key in source.get("set", {}):
            merged["set"][key] = source["set"][key]
        else:
            merged["set"].pop(key, None)
    side = list(merged["stats"].get("s_side", [0]))
    side[0] = (int(unit["stats"]["s_side"][0]) & NPC_SIDE_BITS) | (int(side[0]) & TYPE_BITS)
    merged["stats"]["s_side"] = side
    leader, script_leader = merged.get("leader"), unit.get("leader")
    if leader and script_leader:
        leader["portrait"] = copy.deepcopy(script_leader.get("portrait"))
        leader["sprites"] = copy.deepcopy(script_leader.get("sprites"))
    return merged
