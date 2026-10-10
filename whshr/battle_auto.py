"""Small, stdlib-only protocol helpers for an automated battle session."""

import math
from typing import Any

from .battle_scene import BattleScene
from .camera import MAX_DISTANCE, MAX_PITCH, MIN_DISTANCE, MIN_PITCH


ORDER_ARITY = {
    "start_battle": 0, "select": 1, "deselect": 0, "move_to": 2,
    "attack": 1, "fire": 2, "halt": 0, "pause": 0,
    "ranks_up": 0, "ranks_down": 0, "turn_left": 0,
    "turn_right": 0, "about_face": 0, "face_point": 2,
    "charge": 0, "rally": 0, "fight_harder": 0,
    "independent": 0, "leave_battle": 0,
}


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def parse_order(command: dict[str, Any]) -> tuple[Any, ...]:
    event = command.get("event")
    if not isinstance(event, list) or not event or not isinstance(event[0], str):
        raise ValueError("order needs an event array beginning with an order name")
    arity = ORDER_ARITY.get(event[0])
    if arity is None or len(event) != arity + 1:
        raise ValueError(f"unsupported order or wrong argument count: {event[0]}")
    if event[0] in {"select", "attack"} and not isinstance(event[1], str):
        raise ValueError("regiment identifiers must be strings")
    if event[0] in {"move_to", "face_point"} and not all(
            _finite_number(value) for value in event[1:]):
        raise ValueError("world coordinates must be finite numbers")
    if event[0] == "fire":
        target, point = event[1:]
        if target is not None and not isinstance(target, str):
            raise ValueError("fire target must be a regiment identifier or null")
        if point is not None and (not isinstance(point, (list, tuple)) or len(point) != 2
                                  or not all(_finite_number(value) for value in point)):
            raise ValueError("fire point must be two finite world coordinates or null")
    return tuple(event)


def camera_values(values: Any) -> tuple[float, float, float]:
    """Validate camera arguments before they can enter a persistent projection."""
    if not isinstance(values, (list, tuple)) or len(values) != 3 or not all(
            _finite_number(value) for value in values):
        raise ValueError("camera needs three finite numbers: yaw, pitch, distance")
    yaw, pitch, distance = map(float, values)
    if not MIN_PITCH <= pitch <= MAX_PITCH or not MIN_DISTANCE <= distance <= MAX_DISTANCE:
        raise ValueError(f"camera pitch must be {MIN_PITCH:g}..{MAX_PITCH:g} and distance "
                         f"{MIN_DISTANCE:g}..{MAX_DISTANCE:g}")
    return yaw % 360, pitch, distance


def target_values(values: Any) -> tuple[float, float]:
    if not isinstance(values, list) or len(values) != 2 or not all(
            _finite_number(value) for value in values):
        raise ValueError("target needs two finite world coordinates")
    return float(values[0]), float(values[1])


def describe(scene: BattleScene) -> dict[str, Any]:
    battle = scene.battle
    merc = scene.field.script.get("merc") or {}
    return {
        "battle": scene.battle_id.name,
        "tick": battle.tick_count,
        "update": battle.update_count,
        "phase": battle.phase,
        "paused": battle.paused,
        "result": battle.result,
        "selected": scene.selected_id,
        "player_army": {
            "source": "campaign_marching_army" if scene.player_army is not None else "battle_loadmerc",
            "file": merc.get("file"),
            "units": [unit.get("id") for army in merc.get("armies", ()) for unit in army.get("units", ())],
        },
        "regiments": {
            identifier: {
                "name": regiment.name,
                "side": regiment.side.value,
                **state,
            }
            for identifier, state in battle.snapshot().items()
            for regiment in (battle.regiments[identifier],)
        },
    }
