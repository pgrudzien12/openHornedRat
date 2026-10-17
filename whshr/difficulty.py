"""Engine difficulty levels: an engine extension, not original parity (the original has no difficulty setting).

The original's rules are the hardest level, Commander. The two easier levels change only what the owner chose, never
a unit's characteristics or a mission's payments (briefings quote the mission pay):

| Level | Regiment prices | Reinforcements | A regiment that would be lost | Fight skill | Player power |
|---|---|---|---|---|---|
| Commander | as the campaign rules | as granted | disbanded | as the profile | 0-8, starts 1-8 |
| Sergeant | 90 % | 140 % | disbanded | as the profile | starts at 10, at most 10 |
| Soldier | 80 % | 200 % | kept if it had wounded; sits out the next battle | +1 WS, +1 BS | starts at 12, at most 12 |

The level is a player setting saved beside the audio levels and read at the moment a rule applies: prices when the
troop selection or the hire book opens, reinforcements when a script grants them, the wounded rule at the debrief and
the battle rules when a battle starts. Changing it in the caravan's Options therefore reprices the next mission.

A new player (an engine save directory without a saved, readable level) starts on Soldier. A run without a save
directory (tests, replays, tools) keeps Commander, the original rules.
"""

import json
from dataclasses import dataclass
from os import PathLike
from pathlib import Path


@dataclass(frozen=True)
class Difficulty:
    name: str  # the saved identifier
    label: str  # the Options window's text
    price_percent: int  # of every regiment's price (deployment, retainer, hiring)
    reinforcement_percent: int  # of every reinforcement grant, rounded half up
    wounded_keep: bool  # a regiment with wounded is never disbanded; a saved one sits out the next battle
    skill_bonus: int  # added to the player's WS and BS in close combat and shooting, not to the profile
    player_power: int | None  # the player's pool starts at and is capped by this; None: the original's rules

    def price(self, price: int) -> int:
        return price * self.price_percent // 100

    def reinforcements(self, count: int) -> int:
        return (count * self.reinforcement_percent + 50) // 100 if count > 0 else count


SOLDIER = Difficulty("soldier", "Soldier", 80, 200, True, 1, 12)
SERGEANT = Difficulty("sergeant", "Sergeant", 90, 140, False, 0, 10)
COMMANDER = Difficulty("commander", "Commander", 100, 100, False, 0, None)
LEVELS = (SOLDIER, SERGEANT, COMMANDER)
BY_NAME = {level.name: level for level in LEVELS}
NEW_PLAYER_LEVEL = SOLDIER  # until the player picks a level in Options


class DifficultySetting:
    """The current level, persisted as ``difficulty.json`` in the engine's save directory."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.level = COMMANDER

    def configure(self, save_dir: str | PathLike[str] | None) -> None:
        self.path = Path(save_dir) / "difficulty.json" if save_dir is not None else None
        self.level = COMMANDER
        if self.path is None:
            return
        self.level = NEW_PLAYER_LEVEL
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.level = BY_NAME.get(raw.get("difficulty"), NEW_PLAYER_LEVEL)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self, level: Difficulty) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"difficulty": level.name}) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        self.level = level


difficulty_setting = DifficultySetting()


def current() -> Difficulty:
    return difficulty_setting.level
