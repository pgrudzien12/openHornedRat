"""Deterministic battle-state primitives shared by prototype frontends."""

from dataclasses import dataclass
import math

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

    @property
    def moving(self):
        return self.target_x is not None


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
        source = load_battle(path)
        field = source["field"]
        regiments = []
        armies = [(army, False) for army in source["armies"]]
        armies.extend((army, True) for army in (source["merc"] or {}).get("armies", []))
        for army, player in armies:
            for unit in army["units"]:
                position = unit["set"]
                if "x" not in position or "y" not in position:
                    continue
                regiments.append(Regiment(
                    unit["id"], unit["name"], float(position["x"]), float(position["y"]),
                    int(position.get("dir") or 0) % 512, player,
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
