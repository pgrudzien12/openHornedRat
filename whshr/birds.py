"""Ambient battlefield birds (notes/battle_birds.md).

Decoration only: nothing in the rules reads the birds. Up to four birds appear at the battle's 1st, 9th, 17th and
25th deaths and from then on circle a corpse. Each bird follows one of four "every 32nd death" sequences: the bird
born at death number ``n`` (counted from 0) always flies around the most recent death whose number is ``n`` plus a
multiple of 32 (report section 0), which is what draws the birds toward wherever the killing is.

The flight is a fixed 52-tick program of aims, flaps and a glide (section 3). Headings are 1/512 of a turn, 0 = +Y,
clockwise; heights are world units above the terrain under the bird (the view adds the terrain).

Engine choices (named so they can be found):
- The birds draw from their own random stream, not the battle's, so a battle with birds replays the same gameplay as
  one without (section 4 calls this a harmless deviation).
- PROVISIONAL: an aim tick does not steer; the velocity of the previous tick still applies on it (section 3 "Birth":
  the first, aiming tick does not move).
- PROVISIONAL: of the two calling draws out of ten, the first plays sound 10 and the second sound 11 (section 3 "Call").
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

FULL_TURN = 512
FOLLOWED_DEATHS = 32  # a bird moves on to a newer corpse every 32 deaths (section 0)
BIRTH_DEATHS = (0, 8, 16, 24)  # death numbers (from 0) that create a bird (section 1)
ANTICLOCKWISE_BIRTHS = (0, 8)  # birds born at these deaths always turn anticlockwise, the others clockwise
BIRTH_HEIGHT = 160  # above the terrain (section 1)
CRUISE_HEIGHT = 68  # the height the birds sink to (section 3)
TURN_STEP = 8  # heading change per steering tick, also the dead zone around the wanted bearing
ROUND_TICKS = 52
FIRST_FRAME = 74  # GENBATT: frame = FIRST_FRAME + 8 * wing phase + camera-relative octant (section 2)
CALL_PACKET = 2  # the Battle2 sound bank (notes/sfx.md)
CALL_EFFECTS = (10, 11)
CALL_CHANCES = 10  # one draw out of ten per round; draws 0 and 1 call


def _round_step(tick: int) -> tuple[int, bool, bool]:
    """(wing phase, aims, calls) on tick ``tick`` (0-51) of a round (section 3 table)."""
    if tick < 16:
        return tick % 4, tick == 0, False
    if tick < 33:
        return 0, tick == 16, False  # aim, then a 16-tick glide on phase 0
    if tick < 36:
        return tick - 32, False, False  # phases 1, 2, 3
    return (tick - 36) % 4, tick == 36, tick == 36


def bearing(x: float, y: float, to_x: float, to_y: float) -> int:
    """Bearing from (x, y) to (to_x, to_y), truncated (section 3 "Aim")."""
    return int(256 - 256 * math.atan2(to_x - x, y - to_y) / math.pi) % FULL_TURN


def velocity(heading: int) -> tuple[float, float]:
    """Per-tick (dx, dy) of a bird flying along ``heading``: the 256-scaled sine and cosine truncated toward zero,
    then floor-divided by 32 and quartered (section 3 "Steer")."""
    angle = 2 * math.pi * (heading % FULL_TURN) / FULL_TURN
    return (int(256 * math.sin(angle)) >> 5) / 4, (int(256 * math.cos(angle)) >> 5) / 4


def climb(height: float) -> float:
    """Per-tick height change toward CRUISE_HEIGHT from the integer part of ``height`` (section 3)."""
    return ((CRUISE_HEIGHT - int(height)) >> 4) / 4


@dataclass
class Bird:
    birth: int  # the death number (0, 8, 16 or 24) that created it; it follows every 32nd death from there
    x: float
    y: float
    height: float  # above the terrain
    heading: int
    goal_x: float
    goal_y: float
    wanted: int = 0  # bearing to the goal at the last aim
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    tick: int = 0  # position in the 52-tick round
    phase: int = 0  # wing phase 0-3 shown this tick

    @property
    def clockwise(self) -> bool:
        return self.birth not in ANTICLOCKWISE_BIRTHS

    def steer(self) -> None:
        """Turn by TURN_STEP in the bird's own sense when off the wanted bearing by more than TURN_STEP (shortest
        difference), never the short way round; then set the velocity from the heading."""
        difference = (self.heading - self.wanted) % FULL_TURN
        if min(difference, FULL_TURN - difference) > TURN_STEP:
            self.heading = (self.heading + (TURN_STEP if self.clockwise else -TURN_STEP)) % FULL_TURN
        self.dx, self.dy = velocity(self.heading)
        self.dz = climb(self.height)


@dataclass
class Call:
    x: float
    y: float
    effect: int


@dataclass
class Flock:
    enabled: bool = True  # False when the battle file says NoBirds
    seed: int = 0
    deaths: int = 0
    birds: list[Bird] = field(default_factory=list[Bird])

    def __post_init__(self) -> None:
        self.rng = random.Random(f"birds-{self.seed}")

    def record_death(self, x: float, y: float) -> None:
        """A model was killed at (x, y): a new bird at the 1st, 9th, 17th or 25th death, and the bird following this
        death's sequence takes it as its new goal (picked up at its next aim)."""
        if not self.enabled:
            return
        number = self.deaths
        self.deaths += 1
        if number in BIRTH_DEATHS:
            self.birds.append(Bird(number, x, y, BIRTH_HEIGHT, self.rng.randrange(FULL_TURN), x, y))
            return
        for bird in self.birds:
            if (number - bird.birth) % FOLLOWED_DEATHS == 0:
                bird.goal_x, bird.goal_y = x, y

    def tick(self) -> list[Call]:
        """Advance every bird one battle tick; returns the calls to sound."""
        calls: list[Call] = []
        for bird in self.birds:
            bird.phase, aims, calls_now = _round_step(bird.tick)
            if aims:
                bird.wanted = bearing(bird.x, bird.y, bird.goal_x, bird.goal_y)
            else:
                bird.steer()
            if calls_now:
                draw = self.rng.randrange(CALL_CHANCES)
                if draw < len(CALL_EFFECTS):
                    calls.append(Call(bird.x, bird.y, CALL_EFFECTS[draw]))
            bird.x += bird.dx
            bird.y += bird.dy
            bird.height += bird.dz
            bird.tick = (bird.tick + 1) % ROUND_TICKS
        return calls
