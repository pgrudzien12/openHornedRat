"""Per-tick presentation state of a Fireball bolt: head, trail puffs and the closing explosion.

Pure Python (no GPU), so it is unit-testable. The battle only says where each flying bolt is; this module owns
the presentation timing (notes/bf003_playtest_fireball_grid_pursuit.md section 2), keyed by effect identity and
advanced once per battle tick:

- head: frames 125..128 cycling one per tick at the bolt's current position and height;
- trail: every tick the bolt moved, a puff is left at the previous position and height; it plays frames
  125..144, one per tick, then disappears;
- explosion: frames 177..185, one per tick, on the ground at the last position, whatever ended the flight.

Only the Fireball visuals are mapped; other spells' SPELLS frames are an open item and draw nothing.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

HEAD_FIRST, HEAD_COUNT = 125, 4
PUFF_FIRST, PUFF_FRAMES = 125, 20
EXPLOSION_FIRST, EXPLOSION_FRAMES = 177, 9


@dataclass(frozen=True)
class Flight:
    """One bolt seen this tick: its identity, position and height above the ground. Only flying bolts are
    reported; a bolt that stops being reported has ended."""
    serial: int
    x: float
    y: float
    height: float


@dataclass(frozen=True)
class Sprite:
    """One sprite to draw: the frame number in the SPELLS set, the ground position and height above it."""
    frame: int
    x: float
    y: float
    height: float


@dataclass
class _Bolt:
    flights: int = 0
    last: tuple[float, float, float] | None = None
    flying: bool = True
    puffs: list[list[float]] = field(default_factory=list[list[float]])  # x, y, height, age
    explosion: list[float] | None = None  # x, y, age


@dataclass
class FireballVisuals:
    bolts: dict[int, _Bolt] = field(default_factory=dict[int, _Bolt])

    def advance(self, flights: Iterable[Flight]) -> None:
        """Step all bolt presentation state by one battle tick, given the bolts still flying this tick."""
        seen = {flight.serial: flight for flight in flights}
        for bolt in self.bolts.values():
            for puff in bolt.puffs:
                puff[3] += 1
            bolt.puffs = [puff for puff in bolt.puffs if puff[3] < PUFF_FRAMES]
            if bolt.explosion is not None:
                bolt.explosion[2] += 1
                if bolt.explosion[2] >= EXPLOSION_FRAMES:
                    bolt.explosion = None
        for serial, flight in seen.items():
            bolt = self.bolts.setdefault(serial, _Bolt())
            here = (flight.x, flight.y, flight.height)
            if bolt.last is not None and bolt.last != here:
                bolt.puffs.append([*bolt.last, 0])
            bolt.last = here
            bolt.flights += 1
        for serial, bolt in self.bolts.items():
            if serial not in seen and bolt.flying:
                bolt.flying = False
                if bolt.last is not None:
                    bolt.explosion = [bolt.last[0], bolt.last[1], 0]
        self.bolts = {serial: bolt for serial, bolt in self.bolts.items()
                      if bolt.flying or bolt.puffs or bolt.explosion is not None}

    def sprites(self) -> list[Sprite]:
        """Everything to draw now: trail puffs, then explosions, then heads (heads on top)."""
        drawn: list[Sprite] = []
        for bolt in self.bolts.values():
            drawn += [Sprite(PUFF_FIRST + int(age), x, y, h) for x, y, h, age in bolt.puffs]
        for bolt in self.bolts.values():
            if bolt.explosion is not None:
                x, y, age = bolt.explosion
                drawn.append(Sprite(EXPLOSION_FIRST + int(age), x, y, 0.0))
        for bolt in self.bolts.values():
            if bolt.flying and bolt.last is not None:
                x, y, h = bolt.last
                drawn.append(Sprite(HEAD_FIRST + (bolt.flights - 1) % HEAD_COUNT, x, y, h))
        return drawn
