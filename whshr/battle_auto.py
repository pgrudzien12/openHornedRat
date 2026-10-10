"""Small, stdlib-only protocol helpers for an automated battle session."""

from typing import Any

from .battle_scene import BattleScene


ORDER_ARITY = {
    "start_battle": 0, "select": 1, "deselect": 0, "move_to": 2,
    "attack": 1, "fire": 2, "halt": 0, "pause": 0,
    "ranks_up": 0, "ranks_down": 0, "turn_left": 0,
    "turn_right": 0, "about_face": 0, "face_point": 2,
    "charge": 0, "rally": 0, "fight_harder": 0,
    "independent": 0, "leave_battle": 0,
}


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
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in event[1:]):
        raise ValueError("world coordinates must be numbers")
    return tuple(event)


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
