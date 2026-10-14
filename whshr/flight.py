"""Airborne units: who can fly, the elevation, and take-off and landing (notes/airborne_units.md Part A).

A unit is in the flying state exactly while its elevation is above 0 (A2). The elevation is measured above the
terrain under the unit, moves in steps of 4 and is held to 0..32. It changes only through the figure's take-off and
landing programs, which its animation action starts (A3). The action is the public numbering of
notes/script_animation_sound.md 0 (whshr.animation STAND .. SHOOT).
"""

import math
from dataclasses import dataclass

from .animation import FIGHT, IDLE, SHOOT, STAND, WALK, WEAPON_READY

STEP, CEILING = 4, 32  # A2


@dataclass(frozen=True)
class FlightProfile:
    """One flying sprite set's programs (A3.1, A3.2, A3.3)."""

    program_ticks: int  # a whole take-off or landing program
    step_every: int  # an elevation step on every n-th tick of the program
    take_off: frozenset[int]  # actions whose program takes off when grounded
    land: frozenset[int]  # actions whose program lands when flying
    hovers: bool  # the Gyrocopter: a rest action straight after a flying program hovers instead of landing
    keeps_flying_after_cast: bool  # the Wyvern: a cast that started in the air returns to action 2 (A3.1)
    # Tick-by-tick phases of the stand group during one 10-tick lap of the Wyvern's program (A3.1), or the
    # rotor group during one 16-tick lap of the Gyrocopter's (A3.2); a step tick repeats the frame before it.
    program_phases: tuple[int, ...]
    program_group: str  # the group of the program laps
    air_phases: tuple[int, ...]  # the flying loop on the program group after a 2/3/7 program, one tick each
    rest_phases: tuple[int, ...]  # the slow loop on the program group after a 1/4/5 program (Wyvern: 1 and 5)


WYVERN = FlightProfile(
    program_ticks=40, step_every=5, take_off=frozenset({IDLE}), land=frozenset({STAND, WALK, WEAPON_READY}),
    hovers=False, keeps_flying_after_cast=True, program_phases=(0, 0, 1, 1, 1, 2, 2, 3, 3, 3),
    program_group="stand", air_phases=(0, 1, 2, 3), rest_phases=(0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3))
GYROCOPTER = FlightProfile(
    program_ticks=32, step_every=4, take_off=frozenset({IDLE, WALK, SHOOT}),
    land=frozenset({STAND, FIGHT, WEAPON_READY}), hovers=True, keeps_flying_after_cast=False,
    program_phases=(0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 1, 1, 1, 2, 2, 2),
    program_group="move", air_phases=(0, 1, 2, 3, 1, 2),
    rest_phases=(0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 1, 1, 1, 2, 2))

# A1: flying is a property of the figure's sprite set (troopsprites name, casefolded).
PROFILES: dict[str, FlightProfile] = {"wyvern": WYVERN, "gyrocopter": GYROCOPTER, "gyrocopt": GYROCOPTER}


def profile_for(sprite: str | None) -> FlightProfile | None:
    return PROFILES.get((sprite or "").casefold())


@dataclass
class FlightState:
    """A flying-capable unit's elevation and the program that is changing it. Every flier starts grounded (A1)."""

    profile: FlightProfile
    elevation: int = 0
    request: int = 0  # the last action request seen (a repeat of it is no change)
    action: int = 0  # the action whose program runs (after the Wyvern's cast rule)
    program: int = 0  # +1 climbing, -1 descending, 0 none
    tick: int = 0  # ticks into the current action's program
    from_flying_program: bool = False  # the Gyrocopter: the last program was its 2/3/7 one
    hovering: bool = False
    repeat: bool = False  # a script re-requested an action (it restarts the program of the same action, A3.2)

    @property
    def airborne(self) -> bool:
        return self.elevation > 0

    @property
    def in_program(self) -> bool:
        return self.program != 0

    def take_request(self, action: int) -> None:
        """Start the program of `action` when the request changes (or a script repeats it while hovering)."""
        repeat, self.repeat = self.repeat, False
        if action == self.request and not (repeat and self.hovering):
            return
        previous, self.request = self.action, action
        profile = self.profile
        if (profile.keeps_flying_after_cast and previous == SHOOT and action in profile.land and self.airborne):
            action = IDLE  # A3.1: after a cast in the air, back to action 2 without a new take-off
        self.action, self.tick = action, 0
        if action in profile.take_off:
            self.program = 1 if not self.airborne else 0
            self.from_flying_program, self.hovering = True, False
        elif action in profile.land:
            if profile.hovers and self.from_flying_program:
                self.program, self.hovering = 0, True
            else:
                self.program, self.hovering = (-1 if self.airborne else 0), False
            self.from_flying_program = False
        else:
            self.program = 0  # the Wyvern's fight and cast keep the elevation (A3.1)

    def step(self) -> None:
        """One tick of the running program: an elevation step on every `step_every`-th tick (A3.3)."""
        self.tick += 1
        if not self.program:
            return
        if self.tick % self.profile.step_every == 0:
            self.elevation = max(0, min(CEILING, self.elevation + STEP * self.program))
        if self.tick >= self.profile.program_ticks:
            self.program = 0

    def frame(self) -> tuple[str, int] | None:
        """The group and phase the figure shows, or None for its family's ordinary script: the program laps, then
        the flying loop after a take-off action or the slow rest loop after a resting one (A3.1, A3.2). The
        Wyvern's walk, fight and cast use its ordinary groups."""
        profile = self.profile
        if self.program:
            phases = profile.program_phases
        elif self.action in profile.take_off and (self.airborne or profile is GYROCOPTER):
            phases = profile.air_phases
        elif self.action in (STAND, WEAPON_READY) or (profile is GYROCOPTER and self.action == FIGHT):
            phases = profile.rest_phases
        else:
            return None
        return profile.program_group, phases[max(0, self.tick - 1) % len(phases)]


def flight_request(action: int, charging_or_routing: bool) -> int:
    """The action the original would have requested: the engine walks figures to their slots with action 3 during
    any move, where the original requests 2 unless the unit charges, pursues or routs (script_animation_sound.md 0.1)."""
    return IDLE if action == WALK and not charging_or_routing else action


GLIDE = 2  # world units per tick along the falling figure's random facing (A5.1, A5.2)
CRASH_RADIUS, CRASH_STRENGTH, CRASH_WOUNDS = 72, 5, 6  # A5.4: S5, D6 wounds on a direct hit
WRECK_GROUP = 32  # the corpse (Wyvern) or wreck (Gyrocopter) group, first-frame number (A5.1, A5.2)


@dataclass
class FallingFlier:
    """A flier killed in the air (A5): its unit is already destroyed, and the figure falls on its own. During the
    program's ticks it glides `GLIDE` units per tick along `facing` while the elevation steps down, then it lies
    down on tick N + 1 and crashes on tick N + 2 (N = the program length). Engine choice (A5.3 allows it): the figure
    is drawn at the stepped elevation, not on the ground. Not modelled: the Gyrocopter's eight smoke puffs."""

    x: float
    y: float
    facing: int  # 0..511, 0 = +Y, clockwise
    elevation: int
    profile: FlightProfile
    sprite: str | None
    tick: int = 0

    def step(self) -> str | None:
        """One tick of the fall; returns "corpse" on the tick the corpse frame appears, "crash" on the tick after."""
        self.tick += 1
        ticks = self.profile.program_ticks
        if self.tick <= ticks:
            angle = self.facing * math.tau / 512
            self.x += GLIDE * math.sin(angle)
            self.y += GLIDE * math.cos(angle)
            if self.tick % self.profile.step_every == 0:
                self.elevation = max(0, self.elevation - STEP)
            return None
        return "corpse" if self.tick == ticks + 1 else "crash" if self.tick == ticks + 2 else None

    def frame(self) -> tuple[str, int]:
        phases = self.profile.program_phases
        return self.profile.program_group, phases[(self.tick - 1) % len(phases)]
