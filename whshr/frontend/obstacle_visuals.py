"""Presentation of the spells that leave battlefield obstacles (notes/spell_obstacle_visuals.md): Wind Blast, Tangling
Thorn, Da Krunch and Flamestorm.

Pure Python (no GPU), so it is unit-testable. The battle owns the gameplay (the gust's position, the trail deposits,
the obstacles, the damage); this module owns the artwork's timing, keyed by effect serial and advanced once per battle
tick with the effects still active after that tick's effect update. An effect that is cancelled is simply not seen
again, so its art goes on that update with no closing sequence (section 1.2). Ages count from the launch tick T.

Random choices here (scatter, flame phases) are presentation-only: they come from this module's own generator and never
from the battle's, so a headless replay and a drawn battle stay identical. Wind Blast's trail jitter is the exception:
it decides where obstacles drop, so the battle draws it (`spell_effects.Effect.trail_jitter`).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import random
from typing import TYPE_CHECKING

from .. import spell_effects
from .spell_visuals import MeshItem, Sprite

if TYPE_CHECKING:
    from ..engine import Battle

Point = tuple[float, float]

# Section 2: Wind Blast.
WIND_FORMING, WIND_LOOP, WIND_HEAD_LAST = 379, 384, spell_effects.GUST_FLIGHT  # 379-383 once, then 384-386
# Section 3: Tangling Thorn.
THORN_FIRST, THORN_FRAMES, THORN_COUNT, THORN_SPREAD = 199, 6, 20, 32
# Section 4: Da Krunch.
KRUNCH_MESH = "dakrunch"
KRUNCH_FALL_HEIGHTS = (120, 106, 93, 80, 66, 53, 40, 26, 13, 0)  # T..T+9
KRUNCH_LIFT_HEIGHTS = (0, 14, 27, 40, 54, 67, 80, 94, 107, 120)  # T+47..T+56
KRUNCH_STAND, KRUNCH_LIFT, KRUNCH_GONE = 10, 47, 57
DUST_FIRST, DUST_FRAMES, DUST_COUNT = 474, 6, 12  # T+10..T+15
# Section 5: Flamestorm.
SPARK_FIRST, SPARK_FRAMES, SPARKS_PER_TICK, SPARK_SPREAD = 121, 4, 3, 16
IGNITION_LAST, COLUMN_START, COLUMN_PERIOD, SPARKS_GONE = 17, 18, 19, 37
COLUMN_NORMAL, COLUMN_SHIFT = 595, 117
COLUMN_RISE = (-40, -37, -35, -33, -31, -28, -26, -24, -22, -20, -17, -15, -13, -11, -8, -6, -4, -2, 0)
FLAMES_FROM, FLAME_HEIGHTS, FLAMES_ON_AIM_GROUND = 19, 64, 38
CATCH_UP = 64  # at most this many missed ticks are replayed for Flamestorm's particles (only the steady state remains)

OBSTACLE_CODES = frozenset({spell_effects.WIND_BLAST, spell_effects.TANGLING_THORN, spell_effects.DA_KRUNCH,
                            spell_effects.FLAMESTORM})


@dataclass(frozen=True)
class ObstacleSpell:
    """One active obstacle spell seen this tick: `age` since launch (0 on T), the aim point, Wind Blast's gust position
    and trail deposits (in deposit order), and the caster's footprint centre (None when the caster is gone)."""
    serial: int
    code: int
    age: int
    aim: Point
    owner: str
    gust: Point = (0.0, 0.0)
    trail: tuple[Point, ...] = ()
    caster: Point | None = None
    trail_jitter: tuple[tuple[int, int], ...] = ()


@dataclass
class _Spark:
    x: float
    y: float
    birth: int
    order: int = 0  # 0, 1, 2: creation order within its birth tick
    frozen: int | None = None  # the frame it keeps from T+18 (holding sparks keep it to the end)


@dataclass
class _Flame:
    x: float
    y: float
    z: float
    phase: int  # 1..4: FIRE1..FIRE4
    on_aim_ground: bool


@dataclass
class _State:
    seen: int = -1  # the last age processed
    births: list[int] = field(default_factory=list[int])  # Wind Blast: birth age of each trail deposit
    points: list[Point] = field(default_factory=list[Point])  # Thorn sprites / Krunch dust
    heading: Point | None = None  # Da Krunch: foot heading for the current stage
    lifting: bool = False
    shift: bool = False  # Flamestorm: the Shift-selected column
    sparks: list[_Spark] = field(default_factory=list[_Spark])
    flames: list[_Flame] = field(default_factory=list[_Flame])
    successors: dict[int, int] = field(default_factory=dict[int, int])  # tick -> first mesh births scheduled then


@dataclass
class ObstacleVisuals:
    """Presentation state of the obstacle spells. `shift_casts` holds the casters whose pending Flamestorm order was
    given with Shift held (section 5.1); the next new Flamestorm of that caster takes the choice for its whole life.
    PROVISIONAL: the key state is read when the target is clicked, not when the effect launches."""
    rng: random.Random = field(default_factory=lambda: random.Random(1995))
    states: dict[int, _State] = field(default_factory=dict[int, _State])
    current: list[ObstacleSpell] = field(default_factory=list[ObstacleSpell])
    shift_casts: set[str] = field(default_factory=set[str])

    def advance(self, seen: Iterable[ObstacleSpell]) -> None:
        self.current = [spell for spell in seen if spell.code in OBSTACLE_CODES]
        alive = {spell.serial for spell in self.current}
        self.states = {serial: state for serial, state in self.states.items() if serial in alive}
        for spell in self.current:
            state = self.states.get(spell.serial)
            if state is None:
                state = self.states[spell.serial] = _State()
                if spell.code == spell_effects.FLAMESTORM and spell.owner in self.shift_casts:
                    self.shift_casts.discard(spell.owner)
                    state.shift = True
            if spell.code == spell_effects.WIND_BLAST:
                self._advance_wind(spell, state)
            elif spell.code == spell_effects.TANGLING_THORN:
                if not state.points:
                    state.points = self._scatter(spell.aim, THORN_SPREAD, THORN_COUNT)
            elif spell.code == spell_effects.DA_KRUNCH:
                self._advance_krunch(spell, state)
            else:
                for age in range(max(state.seen + 1, spell.age - CATCH_UP), spell.age + 1):
                    self._flamestorm_tick(spell, state, age)
            state.seen = spell.age

    # ----- drawing -----

    def sprites(self) -> list[Sprite]:
        drawn: list[Sprite] = []
        for spell in self.current:
            state = self.states[spell.serial]
            age = spell.age
            if spell.code == spell_effects.WIND_BLAST:
                if age <= WIND_HEAD_LAST:
                    frame = WIND_FORMING + age if age < WIND_LOOP - WIND_FORMING else WIND_LOOP + (age - 5) % 3
                    drawn.append(Sprite(frame, *spell.gust, 0.0))
                for (x, y), birth, (jx, jy) in zip(spell.trail, state.births, spell.trail_jitter):
                    drawn.append(Sprite(WIND_LOOP + (age - birth) % 3, x + jx, y + jy, 0.0, ground_at=(x, y)))
            elif spell.code == spell_effects.TANGLING_THORN:
                frame = THORN_FIRST + min(age, THORN_FRAMES - 1)
                drawn += [Sprite(frame, x, y, 0.0) for x, y in state.points]
            elif spell.code == spell_effects.DA_KRUNCH:
                if KRUNCH_STAND <= age < KRUNCH_STAND + DUST_FRAMES:
                    drawn += [Sprite(DUST_FIRST + age - KRUNCH_STAND, x, y, 0.0) for x, y in state.points]
            else:
                drawn += self._flamestorm_sprites(spell, state)
        return drawn

    def meshes(self) -> list[MeshItem]:
        drawn: list[MeshItem] = []
        for spell in self.current:
            state = self.states[spell.serial]
            if spell.code == spell_effects.DA_KRUNCH and spell.age < KRUNCH_GONE and state.heading is not None:
                drawn.append(MeshItem(KRUNCH_MESH, *spell.aim, krunch_height(spell.age), *state.heading))
            elif spell.code == spell_effects.FLAMESTORM:
                drawn += [MeshItem(f"fire{flame.phase}", flame.x, flame.y, flame.z, 0.0, 1.0,
                                   ground_at=spell.aim if flame.on_aim_ground else None,
                                   absolute=not flame.on_aim_ground)
                          for flame in state.flames]
        return drawn

    # ----- per spell -----

    def _scatter(self, centre: Point, spread: int, count: int) -> list[Point]:
        """`count` points, each axis `centre + spread - (r mod 2 spread)`: -(spread - 1) .. +spread (sections 3, 4.2, 5.2)."""
        cx, cy = centre
        return [(cx + spread - self.rng.randrange(2 * spread), cy + spread - self.rng.randrange(2 * spread))
                for _ in range(count)]

    def _advance_wind(self, spell: ObstacleSpell, state: _State) -> None:
        """Section 2.2: a deposit's loop runs from its own birth (the first update it is seen). Its jitter is the
        battle's (`Effect.trail_jitter`): it decides where the next disc may drop (spell_area_effects.md 1.4)."""
        while len(state.births) < len(spell.trail):
            state.births.append(spell.age)

    def _advance_krunch(self, spell: ObstacleSpell, state: _State) -> None:
        """Section 4.1: the foot faces the caster-centre-to-aim bearing taken at launch, taken again when the lift
        starts (the caster may have moved); section 4.2: twelve dust points at T+10."""
        lifting = spell.age >= KRUNCH_LIFT
        if state.heading is None or (lifting and not state.lifting):
            state.heading = _heading(spell.caster, spell.aim) if spell.caster is not None else state.heading or (0.0, 1.0)
        state.lifting = lifting
        if spell.age >= KRUNCH_STAND and not state.points:
            state.points = self._scatter(spell.aim, THORN_SPREAD, DUST_COUNT)

    def _flamestorm_tick(self, spell: ObstacleSpell, state: _State, age: int) -> None:
        """One tick of Flamestorm's particles (sections 5.2, 5.4, 5.5).
        - T..T+17: sparks live four ticks (121-124); three new ones every tick, at aim + 16 - (r mod 32) per axis.
        - T+18: the twelve sparks (born T+14..T+17) keep their position and frame.
        - From T+19 each spark follows `spark_fate`: early-removal tests first (1/2 each), then the advancing sparks
          step and expire, existing mesh flames advance (one past FIRE4 is replaced at once at a new point and phase),
          then the first mesh of each successor sequence is born on its tick. Eight sequences: exactly 8 flames
          from T+23.
        - T+37: every remaining spark goes, after that tick's update.
        Mesh births until T+37 take an absolute height 0..63, later ones 0..63 above the ground at the aim."""
        if age <= IGNITION_LAST:
            state.sparks = [spark for spark in state.sparks if age - spark.birth < SPARK_FRAMES]
            state.sparks += [_Spark(x, y, age, order)
                             for order, (x, y) in enumerate(self._scatter(spell.aim, SPARK_SPREAD, SPARKS_PER_TICK))]
            return
        if age == COLUMN_START:
            for spark in state.sparks:
                spark.frozen = SPARK_FIRST + IGNITION_LAST - spark.birth
            return
        births = state.successors.pop(age, 0)
        kept: list[_Spark] = []
        for spark in state.sparks:
            fate = spark_fate(spark.birth, spark.order)
            removed = age in fate.tests and self.rng.randrange(2) == 0
            if fate.advancing:
                if age == fate.expiry:
                    successor = fate.successor_kept if not removed else fate.successor_removed
                    if successor == age:
                        births += 1
                    elif successor is not None:
                        state.successors[successor] = state.successors.get(successor, 0) + 1
                    continue
                spark.frozen = SPARK_FIRST + (age - 1) - spark.birth
            elif removed:
                continue
            kept.append(spark)
        state.sparks = kept if age < SPARKS_GONE else []
        flames: list[_Flame] = []
        for flame in state.flames:
            flame.phase += 1
            flames.append(flame if flame.phase <= 4 else self._new_flame(spell.aim, age))
        state.flames = flames + [self._new_flame(spell.aim, age) for _ in range(births)]

    def _new_flame(self, aim: Point, age: int) -> _Flame:
        [(x, y)] = self._scatter(aim, SPARK_SPREAD, 1)
        z = float(self.rng.randrange(FLAME_HEIGHTS))
        return _Flame(x, y, z, 1 + self.rng.randrange(4), age >= FLAMES_ON_AIM_GROUND)

    def _flamestorm_sprites(self, spell: ObstacleSpell, state: _State) -> list[Sprite]:
        drawn = [Sprite(spark.frozen if spark.frozen is not None and spell.age >= COLUMN_START
                        else SPARK_FIRST + spell.age - spark.birth,
                        spark.x, spark.y, 0.0) for spark in state.sparks]
        if spell.age >= COLUMN_START:
            phase, height = column_phase(spell.age)
            base = COLUMN_SHIFT if state.shift else COLUMN_NORMAL
            drawn.append(Sprite(base + phase, *spell.aim, height))
        return drawn


@dataclass(frozen=True)
class SparkFate:
    """What one of the last twelve ignition sparks does from T+19 (section 5.5): its early-removal test ticks; an
    advancing spark steps on and expires on `expiry` (its test tick), starting the first mesh of a flame sequence on
    `successor_kept` / `successor_removed` (None: no sequence); a holding spark keeps its frame until removed."""
    tests: tuple[int, ...]
    advancing: bool
    expiry: int | None = None
    successor_kept: int | None = None
    successor_removed: int | None = None


def spark_fate(birth: int, order: int) -> SparkFate:
    """Section 5.5's table, by birth tick (relative to T) and creation order within it."""
    if birth == 14 and order < 2:
        return SparkFate((19,), True, 19, 19, 20)
    if birth == 14:
        return SparkFate((19, 23, 27, 31, 35), False)
    if birth == 15:
        return SparkFate((20, 24, 28, 32, 36), False)
    if birth == 16:
        return SparkFate((21,), True, 21, 21, 21 if order < 2 else 22)
    return SparkFate((22,), True, 22, 22, 22 if order == 0 else 23)


def krunch_height(age: int) -> int:
    """The foot's height above the ground at the aim (section 4.1)."""
    if age < KRUNCH_STAND:
        return KRUNCH_FALL_HEIGHTS[age]
    if age < KRUNCH_LIFT:
        return 0
    return KRUNCH_LIFT_HEIGHTS[min(age - KRUNCH_LIFT, len(KRUNCH_LIFT_HEIGHTS) - 1)]


def column_phase(age: int) -> tuple[int, int]:
    """Flamestorm's column (section 5.3): (phase 0-3, height above the ground at the aim) at `age` >= T+18. Period j
    starts at T+18+19j with phase (2 + 2j) mod 4, shown on its first two ticks, then advancing one per tick; only the
    first period rises from -40."""
    period, offset = divmod(age - COLUMN_START, COLUMN_PERIOD)
    start = (2 + 2 * period) % 4
    phase = start if offset < 2 else (start + offset - 1) % 4
    return phase, COLUMN_RISE[offset] if period == 0 else 0


def _heading(origin: Point, aim: Point) -> Point:
    dx, dy = aim[0] - origin[0], aim[1] - origin[1]
    return (dx, dy) if dx or dy else (0.0, 1.0)


def obstacle_effects(battle: Battle) -> list[ObstacleSpell]:
    """The obstacle spells active after this tick's effect update (`elapsed` counts the updates, the launch tick's
    included)."""
    seen: list[ObstacleSpell] = []
    for effect in battle.spell_effects.active:
        if effect.ended or effect.code not in OBSTACLE_CODES:
            continue
        owner = battle.regiments.get(effect.owner)
        caster = spell_effects.footprint_centre(owner) if owner is not None and owner.active else None
        seen.append(ObstacleSpell(effect.serial, effect.code, max(0, effect.elapsed - 1), effect.aim, effect.owner,
                                  (effect.x, effect.y), tuple(effect.trail), caster, tuple(effect.trail_jitter)))
    return seen
