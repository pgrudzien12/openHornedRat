"""Deterministic battle-state primitives shared by prototype frontends."""

from dataclasses import dataclass
import math

from . import formation
from .script import load_battle

DEFAULT_TICK_RATE = 60
DEFAULT_MOVE_SPEED = 96.0


@dataclass
class Regiment:
    """A regiment anchor in BTS coordinates; rendering derives its formation from this state."""

    identifier: str
    name: str
    x: float
    y: float
    direction: int
    player: bool
    target_x: float | None = None
    target_y: float | None = None
    models: int = 1
    ranks: int = 1
    sprite: str | None = None  # script troop sprite resource, e.g. "ClanRats"

    @property
    def moving(self):
        return self.target_x is not None

    def model_positions(self, spacing=formation.MODEL_SPACING):
        """Positions of the regiment's models in its block formation (BTS world units)."""
        return formation.place(self.x, self.y, self.direction,
                               formation.block_slots(self.models, self.ranks, spacing))


class Battle:
    """Authoritative fixed-tick state for the initial movement-only prototype."""

    def __init__(self, width, height, regiments, move_speed=DEFAULT_MOVE_SPEED):
        if width <= 0 or height <= 0:
            raise ValueError("battle dimensions must be positive")
        if move_speed <= 0:
            raise ValueError("move speed must be positive")
        self.width = width
        self.height = height
        self.regiments = {regiment.identifier: regiment for regiment in regiments}
        if len(self.regiments) != len(regiments):
            raise ValueError("regiment identifiers must be unique")
        self.move_speed = move_speed
        self.tick_count = 0

    @classmethod
    def from_battle_file(cls, path, move_speed=DEFAULT_MOVE_SPEED):
        return cls.from_script(load_battle(path), move_speed)

    @classmethod
    def from_script(cls, source, move_speed=DEFAULT_MOVE_SPEED):
        """Build the battle from a loaded BTS/MRC script; repeated unit ids get ``#2``, ``#3``... suffixes."""
        field = source["field"]
        regiments, used = [], set()
        armies = [(army, False) for army in source["armies"]]
        armies.extend((army, True) for army in (source["merc"] or {}).get("armies", []))
        for army, player in armies:
            for unit in army["units"]:
                position = unit["set"]
                if "x" not in position or "y" not in position:
                    continue
                identifier, suffix = unit["id"], 2
                while identifier in used:
                    identifier, suffix = f"{unit['id']}#{suffix}", suffix + 1
                used.add(identifier)
                models, ranks = formation.unit_size(unit)
                regiments.append(Regiment(
                    identifier, unit["name"], float(position["x"]), float(position["y"]),
                    int(position.get("dir") or 0) % 512, player, models=models, ranks=ranks,
                    sprite=(unit.get("sprites") or "").split(",", 1)[0].strip() or None,
                ))
        return cls(field["width"], field["height"], regiments, move_speed)

    def order_move(self, identifier, x, y):
        regiment = self.regiments[identifier]
        if not regiment.player:
            raise ValueError(f"{identifier} is not player-controlled")
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        regiment.target_x, regiment.target_y = float(x), float(y)

    def tick(self, seconds=1 / DEFAULT_TICK_RATE):
        if seconds <= 0:
            raise ValueError("tick duration must be positive")
        step = self.move_speed * seconds
        for regiment in self.regiments.values():
            if not regiment.moving:
                continue
            dx, dy = regiment.target_x - regiment.x, regiment.target_y - regiment.y
            distance = math.hypot(dx, dy)
            if distance <= step:
                regiment.x, regiment.y = regiment.target_x, regiment.target_y
                regiment.target_x = regiment.target_y = None
            else:
                regiment.x += dx / distance * step
                regiment.y += dy / distance * step
                # 0 = north/+Y and directions increase clockwise.
                regiment.direction = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        self.tick_count += 1
