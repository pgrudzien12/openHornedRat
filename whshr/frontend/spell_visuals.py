"""Per-tick presentation state of a Fireball bolt: head, trail puffs and the closing explosion.

Pure Python (no GPU), so it is unit-testable. The battle only says where each flying bolt is; this module owns
the presentation timing (notes/bf003_playtest_fireball_grid_pursuit.md section 2), keyed by effect identity and
advanced once per battle tick:

- head: frames 125..128 cycling one per update from the launch tick, at the bolt's current position and height;
- trail: a puff at the start point on the launch tick, then one at the previous position each tick the bolt moved; it
  plays frames 125..144, one per tick, then disappears;
- explosion: frames 177..185 from the ending tick (no head then), on the ground at the last tested position;
- the ending tick also leaves a closing puff at that position, so the trail runs from the start to the end point
  (owner's decision; the original's last puff is one step short).

The other projectile spells (Hunting Spear, the Lightning family, Piercing Bolts, the Burning Head, Pestilent
Breath) follow notes/spell_visuals.md in `ProjectileVisuals` below; the spells drawn on their target's figures (Curse
of Anraheir, Azure Blades, Ere We Go!, Mork Save Uz!) follow notes/spell_attached_visuals.md in `AttachedVisuals`.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import math
import random
from typing import TYPE_CHECKING, Any

from .. import spell_effects

if TYPE_CHECKING:
    from ..engine import Battle

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
    """One sprite to draw: the frame number in the SPELLS set, the position and height above the ground; the ground
    is sampled at `ground_at` when given (a jittered sprite keeps its fixed point's ground), else at the position."""
    frame: int
    x: float
    y: float
    height: float
    ground_at: tuple[float, float] | None = None


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
                if bolt.newest != (flight.x, flight.y):
                    # Owner's decision, not original parity (bf003_playtest 8.4 stops one step short): the trail
                    # reaches the flight's end point, where the explosion starts, so it runs origin to target.
                    bolt.puffs.append([flight.x, flight.y, max(0.0, flight.height), 0])
                    bolt.newest = (flight.x, flight.y)
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


def breath_display_height(effect: spell_effects.Effect) -> float:
    """Where a Dragon breath flame is drawn: on a straight line from its launch height down to the ground at its
    destination (owner's decision, not original parity: the flame itself flies 40 -> 20 on flat ground and is tested
    at those heights, notes/bf014_dragon_mission_audit.md 7.2). The line drops the launch elevation linearly with the
    flown fraction of the path."""
    total = math.dist(effect.start, effect.dest)
    flown = 1.0 if total == 0 else min(1.0, math.dist(effect.start, (effect.x, effect.y)) / total)
    return max(0.0, effect.height - spell_effects.BREATH_FLAME.launch_height * flown)


# ===== The other projectile spells (notes/spell_visuals.md) =====
#
# Two kinds of art: effect meshes of the battle's SCENERY.PBX (named sets of four, cycled one per tick and turned to
# the flight's bearing, level) and SPELLS sprite frames drawn with their .FOL anchor like the Fireball. The colour-map
# banks the report gives (+16 for frames 293-528, +32 from 529) are the maps the SPELLS frames already decode with.

MESH_SETS: dict[int, str] = {  # spell_visuals.md 0: the head mesh set per effect code
    spell_effects.HUNTING_SPEAR: "spear", spell_effects.PIERCING: "boltbur", spell_effects.LIGHTNING: "light",
    spell_effects.WARP_LIGHTNING: "wlight", spell_effects.GAZE: "gaze",
}
BEAM_FLASHES: dict[int, tuple[int, int]] = {  # spell_visuals.md 2.2: (first SPELLS frame, count) of the end flash
    spell_effects.LIGHTNING: (433, 7), spell_effects.WARP_LIGHTNING: (522, 4), spell_effects.GAZE: (464, 6),
}
SEGMENT_SPACING = 32  # a beam segment is left when the head's previous position is more than this from the newest
BEAM_ARRIVAL = 40  # spell_effects.md 2.3: the beam's terminal impact distance
SKULL_FIRST = 32  # the Burning Head: directional frames 32 + d
SKULL_PUFF_FIRST, SKULL_PUFF_FRAMES = 40, 20
BREATH_FIRST = 533  # Pestilent Breath: 533 + flight stage
# The cloud spells (spell_visuals.md 2.6): Pestilent Breath and the Gyrocopter's steam gun, which is drawn the same way
# with its own grey puffs 591 + stage (notes/gyrocopter_steam_gun.md 6.1; frames from 529 decode with bank +32).
CLOUD_FIRST: dict[int, int] = {spell_effects.PESTILENT_BREATH: BREATH_FIRST, spell_effects.STEAM_GUN: 591}
# spell_storm_visuals.md 3: 391-394 once (T..T+3), 395-398 looping from T+4 through every bolt and flash, then the
# closing 399, 400 on the last two ticks before the effect ends.
STORM_FORMING, STORM_LOOP, STORM_CLOSING = 391, 395, 399
STORM_WINDUP_FRAMES = STORM_LOOP - STORM_FORMING  # 4 ticks of 391-394
PROJECTILE_CODES = frozenset({*MESH_SETS, spell_effects.BURNING_HEAD, *CLOUD_FIRST})


@dataclass(frozen=True)
class Shot:
    """One projectile seen this tick (a Storm of Shemtek bolt is one shot per bolt). `start`/`dest` are the current
    leg's ends, `remaining`/`steps` the flight's r and N after this tick's step; `ending` is the tick the flight
    ended (no head then)."""
    key: tuple[int, int]
    code: int
    x: float
    y: float
    height: float
    start: tuple[float, float]
    dest: tuple[float, float]
    remaining: int = 0
    steps: int = 0
    ending: bool = False
    aim_height: float = 0.0  # a beam's flash height above the ground at its destination (spell_visuals.md 2.2)
    hidden: bool = False  # a cloud that went below the ground on its last flight tick: stepped but not drawn


@dataclass(frozen=True)
class MeshItem:
    """One effect mesh to draw: its SCENERY.PBX name, ground position, height above the ground and heading vector.
    The ground is sampled at `ground_at` when given, else at the position; `absolute` makes the height a battle
    height (no ground added); `scale` sizes the mesh uniformly about its origin."""
    name: str
    x: float
    y: float
    height: float
    dx: float
    dy: float
    ground_at: tuple[float, float] | None = None
    absolute: bool = False
    scale: float = 1.0  # uniform size about the mesh's own origin (the Sapphire Arch's growth and shrink)


@dataclass(frozen=True)
class DirectionalSprite:
    """A SPELLS sprite with 8 directional frames from `first`; `bearing` is the flight's direction as a 1/512-turn
    script dir, turned into a frame by the viewer like a figure's facing."""
    first: int
    x: float
    y: float
    height: float
    bearing: int


@dataclass
class _Projectile:
    code: int
    flights: int = 0
    flying: bool = True
    last: tuple[float, float, float] | None = None
    heading: tuple[float, float] = (0.0, 1.0)
    stage: int = 0
    hidden: bool = False
    newest: tuple[float, float] | None = None  # the newest segment or puff position
    segments: list[list[float]] = field(default_factory=list[list[float]])  # x, y, height, age, dx, dy
    puffs: list[list[float]] = field(default_factory=list[list[float]])  # x, y, height, age
    clouds: list[tuple[float, float, float, int]] = field(default_factory=list[tuple[float, float, float, int]])
    flash: list[float] | None = None  # x, y, age, height; the age starts below 0 while the flash waits a tick
    stopped_at: tuple[float, float, float] | None = None  # an early stop's point: one last segment goes there


def breath_stage(remaining: int, steps: int) -> int:
    """Pestilent Breath's growth stage (spell_visuals.md 2.6): r is this tick's ticks left (the effect's remaining
    count before the step, i.e. after it + 1); the stage rises when 4(N - r) is strictly greater than N, 2N, 3N."""
    r = remaining + 1
    grown = 4 * (steps - r)
    return sum(1 for limit in (steps, 2 * steps, 3 * steps) if grown > limit)


def bearing(dx: float, dy: float) -> int:
    """A heading vector as a script dir: 1/512 turns, 0 = +Y, clockwise."""
    return math.trunc(256 - 256 * math.atan2(dx, -dy) / math.pi) % 512


@dataclass
class ProjectileVisuals:
    """Presentation state of every non-Fireball projectile spell, keyed by shot and advanced once per battle tick."""
    shots: dict[tuple[int, int], _Projectile] = field(default_factory=dict[tuple[int, int], _Projectile])
    storm_points: dict[int, tuple[float, float]] = field(default_factory=dict[int, tuple[float, float]])  # fixed at launch
    storm_frames: dict[int, int] = field(default_factory=dict[int, int])  # effect serial -> this tick's frame

    def advance(self, shots: Iterable[Shot]) -> None:
        for shot in self.shots.values():
            self._age(shot)
        seen: set[tuple[int, int]] = set()
        for shot in shots:
            seen.add(shot.key)
            self._step(self.shots.setdefault(shot.key, _Projectile(shot.code)), shot)
        for key, shot in self.shots.items():
            if key not in seen and shot.flying and shot.flights:
                # The effect is gone without an ending (a spent spear, a bolt cancelled by a dispel or its caster's
                # removal): the head stops and a beam's segments go with it, with no flash (spell_effects.md 1.4).
                shot.flying = False
                shot.segments = []
                shot.clouds = []  # spell_plague_monk_breath_visuals.md 4.1: a cancelled cloud leaves no tail
        self.shots = {key: shot for key, shot in self.shots.items()
                      if shot.flying or shot.segments or shot.flash is not None or shot.puffs or shot.clouds}

    def set_storms(self, storms: Iterable[StormFrame], first_figure: Callable[[str], tuple[float, float] | None]) -> None:
        """This tick's Storm sprites (spell_storm_visuals.md 2-4). A Storm that is no longer running (ended, dispelled,
        cancelled, caster or target removed) loses its sprite in the same update. The sprite stands on the ground at
        the caster's first figure as it was when first seen (the launch) and never follows the wizard;
        `first_figure(owner)` gives that point."""
        frames: dict[int, int] = {}
        for serial, owner, frame in storms:
            if serial not in self.storm_points:
                point = first_figure(owner)
                if point is None:
                    continue
                self.storm_points[serial] = point
            frames[serial] = frame
        self.storm_frames = frames
        self.storm_points = {serial: point for serial, point in self.storm_points.items() if serial in frames}

    @staticmethod
    def _age(shot: _Projectile) -> None:
        for segment in shot.segments:
            segment[3] += 1
        for puff in shot.puffs:
            puff[3] += 1
        shot.puffs = [puff for puff in shot.puffs if puff[3] < SKULL_PUFF_FRAMES]
        if shot.flash is not None:
            shot.flash[2] += 1
            if shot.flash[2] >= BEAM_FLASHES[shot.code][1]:
                shot.flash, shot.segments = None, []  # 2.2 step 4: the segments go with the flash
            elif shot.flash[2] == 0 and shot.stopped_at is not None:
                # 2.2 step 5: one tick after an early stop a segment may still be left at the stop point.
                x, y, height = shot.stopped_at
                shot.stopped_at = None
                if shot.newest is None or math.dist((x, y), shot.newest) > SEGMENT_SPACING:
                    shot.segments.append([x, y, height, 0, *shot.heading])
                    shot.newest = (x, y)
        if not shot.flying and shot.clouds:
            shot.clouds.pop(0)  # 2.6: after the flight, one cloud per tick, oldest first

    def _step(self, shot: _Projectile, seen: Shot) -> None:
        here = (seen.x, seen.y, seen.height)
        previous = here if shot.last is None else shot.last
        dx, dy = seen.dest[0] - seen.start[0], seen.dest[1] - seen.start[1]
        if dx or dy:
            shot.heading = (dx, dy)
        code = seen.code
        if code in BEAM_FLASHES:
            if shot.newest is None or math.dist(previous[:2], shot.newest) > SEGMENT_SPACING:
                shot.segments.append([*previous, 0, *shot.heading])
                shot.newest = (previous[0], previous[1])
        elif code == spell_effects.BURNING_HEAD:
            if shot.newest is None or previous[:2] != shot.newest:
                shot.puffs.append([*previous, 0])
                shot.newest = (previous[0], previous[1])
        elif code in CLOUD_FIRST:
            # spell_plague_monk_breath_visuals.md 3: the puff takes the head's frame of this tick, is left at the
            # head's previous position (the start on the first tick) and is skipped when that is the newest puff's
            # point (always on the second tick).
            shot.stage = breath_stage(seen.remaining, seen.steps)
            shot.hidden = seen.hidden
            if shot.newest is None or math.dist(previous[:2], shot.newest) >= 1:
                shot.clouds.append((*previous, CLOUD_FIRST[code] + shot.stage))
                shot.newest = (previous[0], previous[1])
        if seen.ending:
            shot.flying = False
            if code in CLOUD_FIRST and shot.clouds:
                shot.clouds.pop(0)  # section 4.1: the oldest puff goes in the same update the head does
            if code in BEAM_FLASHES:
                end = seen.dest  # the flash is always at the scattered destination, at its aim height
                if math.dist((seen.x, seen.y), seen.dest) < BEAM_ARRIVAL:
                    # 2.2 step 3: a last segment at the aim point, facing back along the beam; the flash starts now
                    shot.segments.append([*end, seen.aim_height, 0, -shot.heading[0], -shot.heading[1]])
                    shot.flash = [end[0], end[1], 0, seen.aim_height]
                else:
                    # 2.2 step 5: stopped early or under the ground; the flash starts one tick later
                    shot.stopped_at = (seen.x, seen.y, seen.height)
                    shot.flash = [end[0], end[1], -1, seen.aim_height]
        shot.last = here
        shot.flights += 1

    def meshes(self) -> list[MeshItem]:
        drawn: list[MeshItem] = []
        for shot in self.shots.values():
            base = MESH_SETS.get(shot.code)
            if base is None:
                continue
            if shot.flying and shot.last is not None:
                x, y, h = shot.last
                drawn.append(MeshItem(f"{base}{1 + (shot.flights - 1) % 4}", x, y, h, *shot.heading))
            for x, y, h, age, dx, dy in shot.segments:
                drawn.append(MeshItem(f"{base}{1 + int(age) % 4}", x, y, h, dx, dy))
        return drawn

    def sprites(self) -> list[Sprite | DirectionalSprite]:
        drawn: list[Sprite | DirectionalSprite] = []
        for shot in self.shots.values():
            if shot.flying and shot.last is not None and not shot.hidden:
                x, y, h = shot.last
                if shot.code == spell_effects.BURNING_HEAD:
                    drawn.append(DirectionalSprite(SKULL_FIRST, x, y, h, bearing(*shot.heading)))
                elif shot.code in CLOUD_FIRST:
                    drawn.append(Sprite(CLOUD_FIRST[shot.code] + shot.stage, x, y, h))
            if shot.flash is not None and shot.flash[2] >= 0:
                x, y, age, height = shot.flash
                drawn.append(Sprite(BEAM_FLASHES[shot.code][0] + int(age), x, y, height))
        for shot in self.shots.values():
            drawn += [Sprite(SKULL_PUFF_FIRST + int(age), x, y, h) for x, y, h, age in shot.puffs]
            drawn += [Sprite(frame, x, y, h) for x, y, h, frame in shot.clouds]
        for serial, frame in self.storm_frames.items():
            drawn.append(Sprite(frame, *self.storm_points[serial], 0.0))
        return drawn


StormFrame = tuple[int, str, int]  # effect serial, caster, SPELLS frame


def storm_frame(age: int, finished: bool, closing_left: int) -> int:
    """The Storm sprite's frame at `age` ticks since the launch (spell_storm_visuals.md 3): 391-394, then 395 + (age mod
    4) without a break; once the last bolt's flash is over (`finished`) the closing 399 and 400 on the last two ticks,
    `closing_left` being the ticks still to wait before the effect ends (1 -> 399, 0 -> 400)."""
    if age < STORM_WINDUP_FRAMES:
        return STORM_FORMING + age
    if finished and closing_left <= 1:
        return STORM_CLOSING + (1 - closing_left)
    return STORM_LOOP + age % 4


def projectile_shots(effects: Iterable[spell_effects.Effect],
                     memory: dict[int, list[Any]]) -> tuple[list[Shot], list[StormFrame]]:
    """This tick's shots from the battle's active spell effects, and each running Storm of Shemtek's sprite frame as
    (effect serial, caster, frame). `memory` (owned by the caller, per effect serial) remembers which flights
    already reported their ending and numbers the Storm of Shemtek's bolts."""
    shots: list[Shot] = []
    storms: list[StormFrame] = []
    for effect in effects:
        if effect.ended or effect.elapsed == 0:
            continue
        code = effect.code
        if code == spell_effects.STORM:
            storms.append((effect.serial, effect.owner, storm_frame(
                effect.elapsed - 1, effect.value == 0 and not effect.flying, effect.timer)))
            state = memory.setdefault(effect.serial, [0, False])  # bolt number, was flying
            if effect.flying and not state[1]:  # a new bolt leaves
                state[0] += 1
            if effect.flying or state[1]:
                shots.append(Shot((effect.serial, state[0]), spell_effects.LIGHTNING, effect.x, effect.y,
                                  max(0.0, effect.height), effect.start, effect.dest, effect.remaining,
                                  effect.steps, ending=not effect.flying, aim_height=effect.aim_height))
            state[1] = effect.flying
            continue
        if code not in PROJECTILE_CODES:
            continue
        flying = effect.tail < 0
        if not flying and code in CLOUD_FIRST:
            # spell_plague_monk_breath_visuals.md 4.1: the head is still drawn on the tick the flight finishes
            # (not when it went below the ground) and gone on the next, which is the cloud's reported ending.
            state = memory.setdefault(effect.serial, [True, False])
            if not state[0]:
                continue
            if not state[1]:
                state[1] = True
                shots.append(Shot((effect.serial, 0), code, effect.x, effect.y, max(0.0, effect.height),
                                  effect.start, effect.dest, effect.remaining, effect.steps,
                                  hidden=effect.height < 0))
                continue
            state[0] = False
            shots.append(Shot((effect.serial, 0), code, effect.x, effect.y, max(0.0, effect.height), effect.start,
                              effect.dest, effect.remaining, effect.steps, ending=True))
            continue
        if not flying:
            state = memory.setdefault(effect.serial, [True])
            if not state[0]:
                continue
            state[0] = False  # report the ending once
        height = float(spell_effects.SPEAR.launch_height) if code == spell_effects.HUNTING_SPEAR \
            else max(0.0, effect.height)
        shots.append(Shot((effect.serial, 0), code, effect.x, effect.y, height, effect.start, effect.dest,
                          effect.remaining, effect.steps, ending=not flying, aim_height=effect.aim_height))
    return shots, storms


# ===== Spells drawn on their target's figures (notes/spell_attached_visuals.md) =====
#
# One sprite per current figure of the target unit, at the figure's ground point (Azure Blades 16 units above it),
# following the figures as they move; gone on the update the effect ends. Dispel Magic and Fists of Gork have no
# effect art at all (section 5), so they are simply not listed here. The colour banks of section 1 are the maps the
# SPELLS frames already decode with (frames 229-292 bank 0, 293-528 bank +16).

CURSE_APPEARANCE, CURSE_LOOP, CURSE_APPEARANCE_TICKS = 229, 261, 4  # section 3.1: 4 phases x 8 directions each
SPARKLES: dict[int, tuple[int, float]] = {  # section 1, 4: first of a 4-frame loop, height above local ground
    spell_effects.AZURE_BLADES: (387, 16.0), spell_effects.ERE_WE_GO: (470, 0.0), spell_effects.MORK_SAVE_UZ: (486, 0.0),
}
# notes/spell_madness_visuals.md: Madness is one horned head per maddened *unit*, not per figure, at the unit's position
# 48 above the local ground, frames 537-540 one per tick from 537 (they already decode with map 34, section 1.1).
MADNESS_FIRST, MADNESS_HEIGHT = 537, 48.0
ATTACHED_CODES = frozenset({spell_effects.CURSE, spell_effects.MADNESS, *SPARKLES})


@dataclass(frozen=True)
class Attachment:
    """One active attached effect seen this tick: `age` is the ticks since launch (0 on the launch tick T), `figures`
    the target's current figure positions in figure order, `facing` the target unit's facing (1/512 turn), `position`
    the target unit's own position."""
    serial: int
    code: int
    age: int
    figures: tuple[tuple[float, float], ...]
    facing: int
    position: tuple[float, float] = (0.0, 0.0)


@dataclass
class AttachedVisuals:
    """Presentation state of the attached spells, advanced once per battle tick with the effects active after the
    tick's effect update. Frames follow from the age alone, so they keep advancing off-screen and while several
    battle ticks pass between two drawn frames; only the Curse's loop phases are remembered.

    The Curse (section 3): appearance phase `age` (all figures together) for ticks T..T+3, then the loop; at its start
    each figure draws r and starts at loop phase 3 - r mod 4, then advances one phase per tick. Direction is the
    camera-relative octant of the unit's facing. Sparkles (section 4): every figure shows frame `first + age mod 4`.
    PROVISIONAL: the loop-start draws come from this presentation generator, not the battle's, so a headless replay
    and a drawn battle stay identical. Not specified, and so not modelled specially: figures added to a cursed unit
    (one beyond the remembered phases loops as if it had drawn r = 3)."""
    rng: random.Random = field(default_factory=lambda: random.Random(1995))
    phases: dict[int, list[int]] = field(default_factory=dict[int, list[int]])
    current: list[Attachment] = field(default_factory=list[Attachment])

    def advance(self, seen: Iterable[Attachment]) -> None:
        self.current = [attachment for attachment in seen if attachment.code in ATTACHED_CODES]
        alive = {attachment.serial for attachment in self.current}
        self.phases = {serial: phases for serial, phases in self.phases.items() if serial in alive}
        for attachment in self.current:
            if (attachment.code == spell_effects.CURSE and attachment.age >= CURSE_APPEARANCE_TICKS
                    and attachment.serial not in self.phases):
                self.phases[attachment.serial] = [3 - self.rng.randrange(4) for _ in attachment.figures]

    def sprites(self) -> list[Sprite | DirectionalSprite]:
        drawn: list[Sprite | DirectionalSprite] = []
        for attachment in self.current:
            if attachment.code == spell_effects.CURSE:
                drawn += [DirectionalSprite(self._curse_first(attachment, index), x, y, 0.0, attachment.facing)
                          for index, (x, y) in enumerate(attachment.figures)]
            elif attachment.code == spell_effects.MADNESS:
                x, y = attachment.position
                drawn.append(Sprite(MADNESS_FIRST + attachment.age % 4, x, y, MADNESS_HEIGHT))
            else:
                first, height = SPARKLES[attachment.code]
                drawn += [Sprite(first + attachment.age % 4, x, y, height) for x, y in attachment.figures]
        return drawn

    def _curse_first(self, attachment: Attachment, index: int) -> int:
        """The first of the 8 directional frames for figure `index` this tick."""
        if attachment.age < CURSE_APPEARANCE_TICKS:
            return CURSE_APPEARANCE + 8 * attachment.age
        phases = self.phases.get(attachment.serial, [])
        start = phases[index] if index < len(phases) else 0
        return CURSE_LOOP + 8 * ((start + attachment.age - CURSE_APPEARANCE_TICKS) % 4)


def attached_effects(battle: Battle) -> list[Attachment]:
    """The attached spells active after this tick's effect update (notes/spell_attached_visuals.md 2): an effect that
    ended, or whose target is gone, draws nothing. The age counts from the launch tick, whose update has already run
    (`elapsed` counts the updates)."""
    seen: list[Attachment] = []
    for effect in battle.spell_effects.active:
        if effect.ended or effect.code not in ATTACHED_CODES or effect.target is None:
            continue
        target = battle.regiments.get(effect.target)
        if target is None or not target.active:
            continue
        seen.append(Attachment(effect.serial, effect.code, max(0, effect.elapsed - 1),
                               tuple(target.model_positions()), int(target.direction), (target.x, target.y)))
    return seen
