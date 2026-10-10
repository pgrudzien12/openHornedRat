"""Per-tick presentation state of a Fireball bolt: head, trail puffs and the closing explosion.

Pure Python (no GPU), so it is unit-testable. The battle only says where each flying bolt is; this module owns
the presentation timing (notes/bf003_playtest_fireball_grid_pursuit.md section 2), keyed by effect identity and
advanced once per battle tick:

- head: frames 125..128 cycling one per update from the launch tick, at the bolt's current position and height;
- trail: a puff at the start point on the launch tick, then one at the previous position each tick the bolt moved; it
  plays frames 125..144, one per tick, then disappears;
- explosion: frames 177..185 from the ending tick (no head then), on the ground at the last tested position.

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
    """One bolt seen this tick: its identity, position and height above the ground at its last in-flight test.
    `ending` marks the tick of the final test: the head is not drawn then and the explosion starts."""
    serial: int
    x: float
    y: float
    height: float
    ending: bool = False


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
    newest: tuple[float, float] | None = None  # position of the newest puff left, even after it expired
    puffs: list[list[float]] = field(default_factory=list[list[float]])  # x, y, height, age
    explosion: list[float] | None = None  # x, y, age


@dataclass
class FireballVisuals:
    bolts: dict[int, _Bolt] = field(default_factory=dict[int, _Bolt])

    def advance(self, flights: Iterable[Flight]) -> None:
        """Step all bolt presentation state by one battle tick, given the bolts updated this tick (bf003_playtest
        8.3): the launch tick shows the head and the first puff at the start point; later ticks leave a puff at the
        previous position when it differs from the newest puff's; the ending tick has no head and starts the explosion."""
        for bolt in self.bolts.values():
            for puff in bolt.puffs:
                puff[3] += 1
            bolt.puffs = [puff for puff in bolt.puffs if puff[3] < PUFF_FRAMES]
            if bolt.explosion is not None:
                bolt.explosion[2] += 1
                if bolt.explosion[2] >= EXPLOSION_FRAMES:
                    bolt.explosion = None
        for flight in flights:
            bolt = self.bolts.setdefault(flight.serial, _Bolt())
            here = (flight.x, flight.y, flight.height)
            previous = here if bolt.last is None else bolt.last  # on the launch tick the previous position is the start
            if bolt.newest is None or previous[:2] != bolt.newest:
                bolt.puffs.append([*previous, 0])  # bf003_playtest 8.4: compared with the newest puff, not "moved"
                bolt.newest = (previous[0], previous[1])
            if flight.ending:
                bolt.flying = False
                bolt.explosion = [flight.x, flight.y, 0]
            bolt.last = here
            bolt.flights += 1
        self.bolts = {serial: bolt for serial, bolt in self.bolts.items()
                      if bolt.flying or bolt.puffs or bolt.explosion is not None}

    def sprites(self) -> list[Sprite]:
        """Everything to draw now. Heads first, then explosions, then puffs: with a strict depth test the first
        sprite emitted wins ties."""
        drawn: list[Sprite] = []
        for bolt in self.bolts.values():
            if bolt.flying and bolt.last is not None:
                x, y, h = bolt.last
                drawn.append(Sprite(HEAD_FIRST + (bolt.flights - 1) % HEAD_COUNT, x, y, h))
        for bolt in self.bolts.values():
            if bolt.explosion is not None:
                x, y, age = bolt.explosion
                drawn.append(Sprite(EXPLOSION_FIRST + int(age), x, y, 0.0))
        for bolt in self.bolts.values():
            drawn += [Sprite(PUFF_FIRST + int(age), x, y, h) for x, y, h, age in bolt.puffs]
        return drawn
