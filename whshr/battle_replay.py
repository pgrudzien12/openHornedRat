# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Deterministic battle replay: rebuild a battle from a `whshr.battle_log` JSON Lines log and compare
it against its recorded snapshots (`python3 -m whshr battle-replay`), stdlib-only.

Replay drives the exact same `whshr.battle_scene.BattleScene` a live battle uses -- `scene.handle` for
each recorded order, `scene.update` for each recorded tick -- rather than a second, parallel
implementation of the rules: recording and replay only ever run one simulation code path
(notes/engine_architecture.md, "Battle logs and replay").
"""
import json
from os import PathLike
from typing import Any

from .assets import AssetId
from .battle_scene import BATTLE_TICK_SECONDS, BattleScene
from .game import scene_context
from .paths import Installation
from .scenes import SceneAssets

Record = dict[str, Any]  # one JSON Lines record of a battle log
PathArg = str | PathLike[str]
Divergence = dict[str, Any]  # {"tick", "regiment", "field", "recorded", "replayed"}

# Numeric snapshot fields compared with a tolerance instead of exact equality, since they accumulate
# floating-point movement every tick; still tight enough that only a genuine divergence trips it.
_TOLERANCE = 1e-6


def read_log(path: PathArg) -> tuple[Record, list[Record], list[Record], Record | None, Record | None]:
    """Parse a JSON Lines battle log into `(header, orders, snapshots, result, end)`.

    Every line must parse as JSON and the header must come first (docs/testing.md, "Given a JSONL log,
    then every line parses and the header comes first").
    """
    header: Record | None = None
    orders: list[Record] = []
    snapshots: list[Record] = []
    result: Record | None = None
    end: Record | None = None
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            record_type = record.get("type")
            if record_type == "header":
                if header is not None:
                    raise ValueError(f"{path}:{line_number}: duplicate header record")
                header = record
            elif header is None:
                raise ValueError(f"{path}:{line_number}: {record_type!r} record before the header")
            elif record_type == "order":
                orders.append(record)
            elif record_type == "snapshot":
                snapshots.append(record)
            elif record_type == "result":
                result = record
            elif record_type == "end":
                end = record
    if header is None:
        raise ValueError(f"{path}: missing header record")
    return header, orders, snapshots, result, end


def _compare_snapshot(recorded: dict[str, Record], replayed: dict[str, Record]) -> Divergence | None:
    """The first mismatching `(regiment, field, recorded, replayed)`, or `None` if they agree."""
    if set(recorded) != set(replayed):
        return {"regiment": None, "field": "regiment set",
                "recorded": sorted(recorded), "replayed": sorted(replayed)}
    for identifier in sorted(recorded):
        expected, actual = recorded[identifier], replayed[identifier]
        for field_name, expected_value in expected.items():
            actual_value = actual.get(field_name)
            if isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                if abs(expected_value - actual_value) > _TOLERANCE:
                    return {"regiment": identifier, "field": field_name,
                            "recorded": expected_value, "replayed": actual_value}
            elif expected_value != actual_value:
                return {"regiment": identifier, "field": field_name,
                        "recorded": expected_value, "replayed": actual_value}
    return None


def replay(installation: Installation | PathArg, log_path: PathArg, until: int | None = None,
           context: SceneAssets | None = None) -> tuple[BattleScene, Record, Divergence | None, list[Record]]:
    """Rebuild the battle from the log's header, apply its recorded orders at their ticks, and compare
    every recorded snapshot as it is reached.

    Returns `(scene, header, divergence, timeline)`: `divergence` is `None` when every recorded
    snapshot matched, else the first mismatch as `{"tick", "regiment", "field", "recorded", "replayed"}`.
    `timeline` is every applied order and emitted event in tick order, for `--timeline`.

    `context` lets tests inject a synthetic `SceneAssets` (a fake "battle-script" loader over a small
    temporary installation, docs/testing.md: "Use a synthetic loader in tests; replay against the real
    installation only in manual verification"); it defaults to `whshr.game.scene_context(installation)`.
    """
    header, orders, snapshots, result, end = read_log(log_path)
    battle_id = AssetId.parse(header["battle_asset"])
    if context is None:
        context = scene_context(installation)
    scene = BattleScene(battle_id, log_dir=None, seed=header["seed"])
    scene.enter(context)

    orders_by_tick: dict[int, list[tuple[Any, ...]]] = {}
    for record in orders:
        orders_by_tick.setdefault(record["tick"], []).append(tuple(record["event"]))
    snapshots_by_tick = {record["tick"]: record for record in snapshots}
    # A recorded result/end tick with no snapshot of its own (the battle resolved between segments)
    # must still be reached, or a truncated replay could look identical just for lacking anything left
    # to compare against.
    known_ticks = [*orders_by_tick, *snapshots_by_tick, 0]
    if result is not None:
        known_ticks.append(result["tick"])
    if end is not None:
        known_ticks.append(end["tick"])
    max_tick = max(known_ticks)
    if until is not None:
        max_tick = min(max_tick, until)

    divergence: Divergence | None = None
    timeline: list[Record] = []
    tick = 0
    while True:
        for event in orders_by_tick.get(tick, []):
            scene.handle(event, context)
            timeline.append({"tick": tick, "kind": "order", "event": list(event)})
        if tick in snapshots_by_tick:
            mismatch = _compare_snapshot(snapshots_by_tick[tick]["regiments"], scene.battle.snapshot())
            if mismatch is not None and divergence is None:
                divergence = {"tick": tick, **mismatch}
        if scene.battle.result is not None or tick >= max_tick:
            break
        scene.update(BATTLE_TICK_SECONDS, context)  # exactly one recorded tick, never wall-clock time
        for battle_event in scene.battle.events:
            timeline.append({"tick": tick, "kind": "event", "text": str(battle_event)})
        tick = scene.battle.update_count
    if divergence is None and result is not None and scene.battle.result != result["result"]:
        divergence = {"tick": tick, "regiment": None, "field": "result",
                      "recorded": result["result"], "replayed": scene.battle.result}
    scene.exit(context)
    return scene, header, divergence, timeline


def main(installation: Installation | PathArg, log_path: PathArg, timeline: bool = False,
         until: int | None = None) -> int:
    scene, header, divergence, events_timeline = replay(installation, log_path, until=until)
    if timeline:
        for entry in events_timeline:
            if entry["kind"] == "order":
                print(f"tick {entry['tick']:>6}  order {entry['event']}")
            else:
                print(f"tick {entry['tick']:>6}  {entry['text']}")
    if divergence is None:
        print(f"replay identical: {header['battle_asset']} ({log_path}), final tick {scene.battle.tick_count}, "
              f"result {scene.battle.result}")
        return 0
    print(f"replay diverged at tick {divergence['tick']}, regiment {divergence['regiment']}, "
          f"field {divergence['field']}: recorded {divergence['recorded']!r}, "
          f"replayed {divergence['replayed']!r}")
    return 1
