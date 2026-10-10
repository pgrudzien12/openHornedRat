"""Per-tick presentation state of a Fireball bolt: head, trail puffs and the closing explosion.

Pure Python (no GPU), so it is unit-testable. The battle only says where each flying bolt is; this module owns
the presentation timing (notes/bf003_playtest_fireball_grid_pursuit.md section 2), keyed by effect identity and
advanced once per battle tick:

- head: frames 125..128 cycling one per update from the launch tick, at the bolt's current position and height;
- trail: a puff at the start point on the launch tick, then one at the previous position each tick the bolt moved; it
  plays frames 125..144, one per tick, then disappears;
- explosion: frames 177..185 from the ending tick (no head then), on the ground at the last tested position.

The other projectile spells (Hunting Spear, the Lightning family, Piercing Bolts, the Burning Head, Pestilent
Breath) follow notes/spell_visuals.md in `ProjectileVisuals` below; the spells drawn on their target's figures (Curse
of Anraheir, Azure Blades, Ere We Go!, Mork Save Uz!) follow notes/spell_attached_visuals.md in `AttachedVisuals`.
"""
from __future__ import annotations

from collections.abc import Iterable
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
# PROVISIONAL (spell_visuals.md 2.3): the storm sprite's cycle was not traced; each run plays once.
STORM_FORMING, STORM_RELEASE = (391, 4), (395, 4)
PROJECTILE_CODES = frozenset({*MESH_SETS, spell_effects.BURNING_HEAD, spell_effects.PESTILENT_BREATH})


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


@dataclass(frozen=True)
class MeshItem:
    """One effect mesh to draw: its SCENERY.PBX name, ground position, height above the ground and heading vector."""
    name: str
    x: float
    y: float
    height: float
    dx: float
    dy: float


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
    newest: tuple[float, float] | None = None  # the newest segment or puff position
    segments: list[list[float]] = field(default_factory=list[list[float]])  # x, y, height, age, dx, dy
    puffs: list[list[float]] = field(default_factory=list[list[float]])  # x, y, height, age
    clouds: list[tuple[float, float, float, int]] = field(default_factory=list[tuple[float, float, float, int]])
    flash: list[float] | None = None  # x, y, age


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
    storms: dict[int, list[float]] = field(default_factory=dict[int, list[float]])  # serial -> x, y, first, count, age

    def advance(self, shots: Iterable[Shot]) -> None:
        for shot in self.shots.values():
            self._age(shot)
        seen: set[tuple[int, int]] = set()
        for shot in shots:
            seen.add(shot.key)
            self._step(self.shots.setdefault(shot.key, _Projectile(shot.code)), shot)
        for key, shot in self.shots.items():
            if key not in seen and shot.flying and shot.flights:
                shot.flying = False  # the effect is gone (a spent spear, a cancelled bolt): the head just stops
        self.shots = {key: shot for key, shot in self.shots.items()
                      if shot.flying or shot.segments or shot.flash is not None or shot.puffs or shot.clouds}
        for storm in self.storms.values():
            storm[4] += 1
        self.storms = {serial: storm for serial, storm in self.storms.items() if storm[4] < storm[3]}

    def storm_sprite(self, serial: int, x: float, y: float, forming: bool) -> None:
        """Start a storm sprite run at the wizard's leader (spell_visuals.md 2.3, PROVISIONAL cycle): the forming run
        when the spell starts, the release run as each bolt leaves."""
        first, count = STORM_FORMING if forming else STORM_RELEASE
        self.storms[serial] = [x, y, first, count, -1]  # aged to 0 by this tick's advance

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
                shot.flash, shot.segments = None, []  # PROVISIONAL (2.2): the segments go when the flash ends
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
        elif code == spell_effects.PESTILENT_BREATH:
            shot.stage = breath_stage(seen.remaining, seen.steps)
            if shot.last is not None and previous[:2] != here[:2]:
                shot.clouds.append((*previous, BREATH_FIRST + shot.stage))
        if seen.ending:
            shot.flying = False
            if code in BEAM_FLASHES:
                end = (seen.x, seen.y)
                if math.dist(end, seen.dest) < BEAM_ARRIVAL:
                    end = seen.dest  # 2.2 step 3: a last segment at the aim point, facing back along the beam
                    shot.segments.append([*end, seen.height, 0, -shot.heading[0], -shot.heading[1]])
                shot.flash = [end[0], end[1], 0]
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
            if shot.flying and shot.last is not None:
                x, y, h = shot.last
                if shot.code == spell_effects.BURNING_HEAD:
                    drawn.append(DirectionalSprite(SKULL_FIRST, x, y, h, bearing(*shot.heading)))
                elif shot.code == spell_effects.PESTILENT_BREATH:
                    drawn.append(Sprite(BREATH_FIRST + shot.stage, x, y, h))
            if shot.flash is not None:
                x, y, age = shot.flash
                drawn.append(Sprite(BEAM_FLASHES[shot.code][0] + int(age), x, y, 0.0))
        for shot in self.shots.values():
            drawn += [Sprite(SKULL_PUFF_FIRST + int(age), x, y, h) for x, y, h, age in shot.puffs]
            drawn += [Sprite(frame, x, y, h) for x, y, h, frame in shot.clouds]
        for x, y, first, _count, age in self.storms.values():
            drawn.append(Sprite(int(first + max(0, age)), x, y, 0.0))
        return drawn


def projectile_shots(effects: Iterable[spell_effects.Effect],
                     memory: dict[int, list[Any]]) -> tuple[list[Shot], list[tuple[int, str, bool]]]:
    """This tick's shots from the battle's active spell effects, and the Storm of Shemtek sprite runs to start as
    (effect serial, caster, forming). `memory` (owned by the caller, per effect serial) remembers which flights
    already reported their ending and numbers the Storm of Shemtek's bolts."""
    shots: list[Shot] = []
    storms: list[tuple[int, str, bool]] = []
    for effect in effects:
        if effect.ended or effect.elapsed == 0:
            continue
        code = effect.code
        if code == spell_effects.STORM:
            if effect.serial not in memory:
                storms.append((effect.serial, effect.owner, True))
            state = memory.setdefault(effect.serial, [0, False])  # bolt number, was flying
            if effect.flying and not state[1]:  # a new bolt leaves (each starts at the caster's leader)
                state[0] += 1
                storms.append((effect.serial, effect.owner, False))
            if effect.flying or state[1]:
                shots.append(Shot((effect.serial, state[0]), spell_effects.LIGHTNING, effect.x, effect.y,
                                  max(0.0, effect.height), effect.start, effect.dest, effect.remaining,
                                  effect.steps, ending=not effect.flying))
            state[1] = effect.flying
            continue
        if code not in PROJECTILE_CODES:
            continue
        flying = effect.tail < 0
        if not flying:
            state = memory.setdefault(effect.serial, [True])
            if not state[0]:
                continue
            state[0] = False  # report the ending once
        height = float(spell_effects.SPEAR.launch_height) if code == spell_effects.HUNTING_SPEAR \
            else max(0.0, effect.height)
        shots.append(Shot((effect.serial, 0), code, effect.x, effect.y, height, effect.start, effect.dest,
                          effect.remaining, effect.steps, ending=not flying))
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
ATTACHED_CODES = frozenset({spell_effects.CURSE, *SPARKLES})


@dataclass(frozen=True)
class Attachment:
    """One active attached effect seen this tick: `age` is the ticks since launch (0 on the launch tick T), `figures`
    the target's current figure positions in figure order, `facing` the target unit's facing (1/512 turn)."""
    serial: int
    code: int
    age: int
    figures: tuple[tuple[float, float], ...]
    facing: int


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
                               tuple(target.model_positions()), int(target.direction)))
    return seen
