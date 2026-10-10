"""Active spell effects: the engine's effect list, the magical hit, bolts and beams, lasting, area and channelled
spells, dispel and the winds of magic.

Public sources, cited as "A x.y" etc. in the docstrings:
- A: notes/spell_effects.md (active effects, the magical hit, bolts and beams);
- B: notes/spell_lasting_effects.md (Madness, Skitterleap, Ere We Go, Mork Save Uz, Fists of Gork, dispel, winds);
- C1: notes/spell_area_effects.md (Wind Blast, Flamestorm, Tangling Thorn, Da Krunch, Conflagration of Doom);
- C2: notes/spell_channelled_effects.md (Storm of Shemtek, Flying Bower, Sapphire Arch, Curse of Anraheir);
- C3: notes/spell_blades_flock_items.md (radius blasts, Azure Blades, Flock of Doom, items, the Doomwheel aim).
Every random draw is taken in the order the reports give, from the battle's own generator.

Engine design (not the original's): active effects live in an unbounded list in launch order, each with a serial id
and an "ended" flag; area objects are kept in a list of their own owned by the effect. There is no fixed effect
capacity, so no launch fails for lack of room, and effects update in launch order.

Not modelled: the per-quarter casualty panic of game_rules.md 7.2 (the engine has it for no damage source yet);
presentation-only draws other than
those the reports say matter for replays.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import animation, combat, magic
from .battle_events import BattleEvent
from .rules import Side, wfb_to_wound

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .engine import Battle, Regiment

TAIL_TICKS = 8  # PROVISIONAL: the visual tail that keeps a finished bolt in the list (A 1.5 suggests ~8)
UNIT_HEIGHT = 24  # engine choice for every unit object's height (A 4.1, the original's per-type heights are open)
FLYING_ELEVATION = 72  # an airborne unit's elevation, as the ordinary missiles use it
UNDISPELLABLE_MARKER = 512  # B 5.1: the script's +512 marker on a launched code
BEAM_STEP = 20  # A 2.3: beams fly N = 1 + trunc(d / 20) ticks
BEAM_TERMINAL = 40  # A 2.4: the terminal impact fires at d < 40 from the destination
FIXED_FLIGHT = 18  # A 2.3: every other bolt
DISPEL_REACH = 80  # B 5.1
UNDER_POINT_MIN = 48  # B 0.1
FISTS_REACH = 16  # B 4
LASTING = 180  # B 1.3, 3, 4, 5.2; C3 2.1
SKITTER_FRAMES = 4  # B 2
WIND_TICKS = 500  # B 7: winds at the start of ticks 501, 1001, ... (first tick = 1) at 10 ticks/s
RANK_DEPTH = 6  # C3 conventions: the footprint centre lies (ranks - 1) x 6 behind the unit position
STORM_WINDUP = 4  # C2 1.3, PROVISIONAL (the original is inconsistent)
STORM_FLASH = 7  # C2 1.3: the next bolt leaves 7 ticks after the previous one ended
STORM_CLOSE = 1  # C2 1.3, PROVISIONAL closing animation
STORM_REACH = 80  # C2 1.2 step 1
STORM_FALLBACK = 576  # C2 1.2 step 2
GUST_FLIGHT = 54  # C1 1.3
TRAIL_RADIUS, TRAIL_HEIGHT, TRAIL_SPACING, TRAIL_MAX, TRAIL_START = 16, 16, 16, 30, 5  # C1 1.4
BOWER_LIFT, BOWER_FLIGHT = 19, 54  # C2 2.2: lifted at T+19, lands at T+74
ARCH_RELEASE, ARCH_SWALLOW, ARCH_REACH, ARCH_EXPIRY = 20, 161, 48, 900  # C2 3
FLOCK_STRIKES, FLOCK_END, FLOCK_RADIUS = (10, 18, 26), 38, 32  # C3 3.2
KRUNCH_FALL, KRUNCH_STAND, KRUNCH_LIFT, KRUNCH_END, KRUNCH_REACH = 9, 10, 47, 57, 32  # C1 4.1
FLAME_START, FLAME_COLUMN, FLAME_RADIUS = 18, 19, 16  # C1 2.3
THORN_RADIUS, THORN_RELEASE = 32, 64  # C1 3.1, 3.4

WIND_BLAST, AZURE_BLADES, STORM, SAPPHIRE_ARCH = 1, 2, 3, 4
LIGHTNING, PIERCING, BURNING_HEAD, CONFLAGRATION, FLAMESTORM, FIREBALL = 5, 6, 7, 8, 9, 10
FLYING_BOWER, TANGLING_THORN, HUNTING_SPEAR, CURSE, FLOCK = 11, 12, 13, 14, 15
DISPEL_MAGIC, GAZE, ERE_WE_GO, DA_KRUNCH = 16, 17, 18, 19
FISTS, MORK_SAVE_UZ, WARP_LIGHTNING, SKITTERLEAP = 20, 21, 22, 23
PESTILENT_BREATH, MADNESS = 24, 25

GMTXT_DIRECT_HIT = 2004
GMTXT_MARGIN_HIT = 2005
GMTXT_DISPELLED = 2006
GMTXT_CAST_FAILED = 2021
EVENT_ROUTED = 0x0F  # C2 2.2: a melee caster lifting away is an "opponent routed" to the other side
EVENT_MADDENED = 0x31  # B 1.1
EVENT_MADNESS_ENDED = 0x32  # B 1.3
MADDENED_SCRIPT_FLAG = 64  # the script's SetUnitFlags2 64 "maddened" behaviour bit, cleared at the end (B 1.3)
BUILDING_CLASSES = (8, 9)
AREA_KEY = "spell_area"  # marks a battle object that mirrors an area object (the owning effect's serial)

ITEM_AURAS = {"ItemBannerOfArcaneProtection": 50, "ItemTalismanOfObsidian": 100}  # B 5.2


@dataclass(frozen=True)
class Bolt:
    """One bolt spell's row of A 3.0. `start`: "origin" (the origin model, else the unit position), "unit" (always
    the unit position) or "reverse" (Lightning's quirk, A 2.1). Heights are the launch height L and the aim-height
    floor; `beam` = the 1 + d/20 flight with the 40-unit terminal rule, else 18 ticks."""
    start: str
    launch_height: int
    aim_floor: int
    beam: bool
    stops: bool
    strength: int
    wound_die: int
    save: bool
    fire: bool
    panic: bool = False


BOLTS: dict[int, Bolt] = {
    LIGHTNING: Bolt("reverse", 4, 4, True, True, 6, 3, False, False),
    GAZE: Bolt("origin", 4, 4, True, False, 6, 1, True, False),
    WARP_LIGHTNING: Bolt("origin", 0, 4, True, True, 5, 6, False, False),
    PIERCING: Bolt("origin", 8, 8, False, True, 4, 1, False, True),
    BURNING_HEAD: Bolt("origin", 8, 8, False, False, 4, 1, True, True, panic=True),
    FIREBALL: Bolt("origin", 0, 0, False, True, 4, 1, False, True),
    PESTILENT_BREATH: Bolt("origin", 8, 8, False, False, 3, 1, False, False),
}
SPEAR = Bolt("unit", 8, 8, False, True, 6, 3, False, False)  # A 3.5: 8 above the ground everywhere
STORM_BOLT = BOLTS[LIGHTNING]  # C2 1.3: each Storm bolt is a Lightning-type beam
GUST = Bolt("origin", 0, 0, False, False, 3, 1, True, False)  # C1 1.3: height 0, S3, 1 wound, save
UNIT_TARGET = frozenset({AZURE_BLADES, HUNTING_SPEAR, CURSE, ERE_WE_GO, MORK_SAVE_UZ, MADNESS})  # B 0.1
REPLACING = frozenset({WIND_BLAST, FLAMESTORM, TANGLING_THORN})  # C1 6 (Curse replaces only with a target, C2 4.1)
PROJECTILE_POSITION = frozenset({*BOLTS, WIND_BLAST, FLYING_BOWER})  # B 5.1: dispelled where the projectile is


@dataclass
class Area:
    """An area object (C1 0): an invisible solid circle owned by an effect, blocking movement, sight and projectiles
    up to its height."""
    owner: int  # the owning effect's serial
    x: float
    y: float
    radius: int
    height: int


@dataclass
class Effect:
    """One active effect (A 1.1). `x, y` is the projectile's current position, `aim` the launch point; `elapsed` counts
    the effect's updates (0 on the launch tick)."""
    serial: int
    code: int
    owner: str
    innate: bool
    undispellable: bool
    aim: tuple[float, float]
    target: str | None = None
    timer: int = 0
    elapsed: int = 0
    ended: bool = False
    tail: int = -1  # ticks of visual tail left; >= 0 once the decisive part is over
    counts_active: bool = True  # feeds the caster's "spell active" entry state (A 1.3, B 5.3 Mork Save Uz quirk)
    # Projectile (A 2): start, scattered destination, aim height, remaining steps r of N.
    start: tuple[float, float] = (0.0, 0.0)
    dest: tuple[float, float] = (0.0, 0.0)
    aim_height: float = 0.0
    terminal_height: float = 0.0  # a flying unit's aim height at the destination, else 0 (A 2.4: height 0)
    steps: int = 0
    remaining: int = 0
    flying: bool = False
    arched: bool = False
    x: float = 0.0
    y: float = 0.0
    arc: int = 0
    strength: int = 0
    value: int = 0  # Storm: bolts left; Conflagration: k
    stopped: bool = False  # Hunting Spear: its leg stopped on a hit last tick
    leg_clock: int = 0
    previous: tuple[float, float] | None = None  # Wind Blast: last tick's position; Bower: the unit's next centre
    trail: list[tuple[float, float]] = field(default_factory=list[tuple[float, float]])
    saved_side: Side | None = None
    saved_initiative: int = 0
    saved_speed: float = 0.0


@dataclass
class EffectTable:
    """The battle's active effects in launch order, their area objects, and the per-unit spell states: Dispel Magic
    used (B 5.4), lifted by a Flying Bower (C2 2.3), inside a Sapphire Arch with its transport stamp (C2 3.2)."""
    active: list[Effect] = field(default_factory=list[Effect])
    next_serial: int = 0
    dispel_used: set[str] = field(default_factory=set[str])
    areas: list[Area] = field(default_factory=list[Area])
    flying: set[str] = field(default_factory=set[str])
    in_arch: set[str] = field(default_factory=set[str])
    stamps: dict[str, tuple[int, tuple[float, float]]] = field(default_factory=dict[str, tuple[int, tuple[float, float]]])

    def effects(self) -> list[Effect]:
        """A snapshot of the effects not yet ended, in launch order."""
        return [effect for effect in self.active if not effect.ended]

    def add(self, effect: Effect) -> None:
        self.active.append(effect)

    def remove(self, effect: Effect) -> None:
        effect.ended = True
        self.active = [other for other in self.active if other is not effect]


def table(battle: Battle) -> EffectTable:
    return battle.spell_effects


# ===== Queries the scripts, the AI and the engine read =====

def spell_active(battle: Battle, caster: str, code: int) -> bool:
    """The caster's spell entry for `code` holds an active effect, visual tail included (A 1.3, B 0.2)."""
    return any(effect.owner == caster and effect.code == code and not effect.innate and effect.counts_active
               for effect in table(battle).effects())


def maddened(battle: Battle, unit_id: str) -> bool:
    """An active Madness effect targets the unit (B 1.4)."""
    return any(effect.code == MADNESS and effect.target == unit_id for effect in table(battle).effects())


def channelling(battle: Battle, unit_id: str) -> bool:
    """The unit owns an active Storm of Shemtek or Flying Bower effect (B 6, C2 1.4)."""
    return any(effect.owner == unit_id and effect.code in (STORM, FLYING_BOWER) for effect in table(battle).effects())


def lifted(battle: Battle, unit_id: str) -> bool:
    """In a Flying Bower flight or inside a Sapphire Arch: not drawn and unable to engage or be engaged; everything
    else still sees the unit (C2 2.3, 3.2)."""
    effects = table(battle)
    return unit_id in effects.flying or unit_id in effects.in_arch


def _sync_lifted(battle: Battle, unit: Regiment) -> None:
    unit.lifted = lifted(battle, unit.identifier)


def dispel_selected(battle: Battle, caster: str) -> bool:
    """The caster has launched Dispel Magic this battle: its entry stays selected (B 5.4)."""
    return caster in table(battle).dispel_used


def solid_areas(battle: Battle) -> list[Area]:
    """The live area objects (C1 0), for movement, collisions, sight lines and impacts."""
    return list(table(battle).areas)


# ===== Geometry helpers =====

def _d(ax: float, ay: float, bx: float, by: float) -> int:
    return int(math.hypot(ax - bx, ay - by))


def footprint_centre(unit: Regiment) -> tuple[float, float]:
    """The footprint centre, (ranks - 1) x 6 behind the unit position (front-rank centre) along the facing (C3)."""
    back = (unit.ranks - 1) * RANK_DEPTH
    angle = unit.direction * math.tau / 512
    return unit.x - back * math.sin(angle), unit.y - back * math.cos(angle)


def _centre_d(unit: Regiment, x: float, y: float) -> int:
    cx, cy = footprint_centre(unit)
    return _d(cx, cy, x, y)


def reference_figure(unit: Regiment) -> tuple[float, float]:
    """The leader model, or without one the roster entry frontage - 1 (entry 0 when that is past the unit's size)
    (A 2.1). The leader is `Regiment.leader_model_index`. PROVISIONAL: without a leader, entry frontage - 1 is
    taken in the engine's own model order."""
    positions = unit.model_positions()
    if not positions:
        return unit.x, unit.y
    leader_index = unit.leader_model_index
    if leader_index is not None and leader_index < len(positions):
        return positions[leader_index]
    index = unit.frontage - 1
    return positions[index] if 0 <= index < len(positions) else positions[0]


def unit_under_point(battle: Battle, x: float, y: float) -> Regiment | None:
    """B 0.1: among active units of any side and state, the one whose reference figure is nearest the point with
    trunc(d) < max(footprint, 48); ties go to the earlier unit."""
    best: Regiment | None = None
    best_d = 0
    for unit in battle.regiments.values():
        if not unit.active:
            continue
        fx, fy = reference_figure(unit)
        d = _d(fx, fy, x, y)
        if d < max(unit.bounding_radius(), UNDER_POINT_MIN) and (best is None or d < best_d):
            best, best_d = unit, d
    return best


def _hostile(a: Regiment, b: Regiment) -> bool:
    """One in the enemy army, the other in the player army or allied (B 1.1); neutral counts as allied here, as in
    the interpreter's own hostility test."""
    return (a.side == Side.ENEMY) != (b.side == Side.ENEMY)


def _leaving(battle: Battle, unit: Regiment) -> bool:
    from .interpreter import LEAVING_BATTLE_FLAG
    state = battle.event_bus.unit_states.get(unit.identifier)
    return state is not None and bool(state.unit_flags & LEAVING_BATTLE_FLAG)


def _building(unit: Regiment) -> bool:
    return unit.unit_class in BUILDING_CLASSES


def _message(battle: Battle, unit: Regiment, text_id: int) -> None:
    battle.events.append(BattleEvent(f"{unit.name}: message {text_id}", "message",
                                     regiment=unit.identifier, text_id=text_id))


def _move_unit(unit: Regiment, x: float, y: float) -> None:
    """Place the unit position at (x, y), its models carried along (no checks: Skitterleap, Bower, Arch)."""
    dx, dy = x - unit.x, y - unit.y
    unit.x, unit.y = x, y
    unit.positions = [(px + dx, py + dy) for px, py in unit.positions]


def _place_centre(unit: Regiment, x: float, y: float) -> None:
    cx, cy = footprint_centre(unit)
    _move_unit(unit, unit.x + x - cx, unit.y + y - cy)


def _queue(battle: Battle, unit_id: str, code: int, source: str | None = None) -> None:
    from .interpreter import Event
    battle.event_bus.queue_event(unit_id, Event(code=code, source=source))


def _sin(angle: int) -> int:
    """SIN[a] = trunc(256 sin(2 pi a / 512)) (C3 conventions)."""
    return int(256 * math.sin(math.tau * angle / 512))


def _cos(angle: int) -> int:
    return int(256 * math.cos(math.tau * angle / 512))


# ===== Launch =====

def launch(battle: Battle, code: int, caster: Regiment, origin_model: int, x: float, y: float,
           innate: bool = False) -> bool:
    """Create the effect of a launch that already passed the caster, range and arc checks (script_magic.md 0.4).

    Fails when a unit-target spell finds no unit under the point (B 0.1; Madness: no hostile, not-maddened unit,
    B 1.1); a failed launch of a player-army caster shows message 2021. Success un-hides the caster (A 1.6), replaces
    the caster's previous Wind Blast, Flamestorm, Tangling Thorn or Curse (C1 6, C2 4.1) and, for Dispel Magic, sets
    the once-per-battle selection (B 5.4)."""
    effects = table(battle)
    spell = code % UNDISPELLABLE_MARKER
    target: Regiment | None = None
    ok = True
    if spell in UNIT_TARGET:
        target = unit_under_point(battle, x, y)
        ok = target is not None and (spell != MADNESS or (_hostile(caster, target)
                                                           and not maddened(battle, target.identifier)))
    if not ok:
        if caster.side == Side.PLAYER:
            _message(battle, caster, GMTXT_CAST_FAILED)
        return False
    if spell in REPLACING or spell == CURSE:
        for old in effects.effects():
            if old.owner == caster.identifier and old.code == spell and not old.innate:
                cancel(battle, old)
    effect = Effect(effects.next_serial, spell, caster.identifier, innate, code >= UNDISPELLABLE_MARKER, (x, y),
                    target=target.identifier if target is not None else None)
    effects.next_serial += 1
    caster.hidden = False
    if spell == DISPEL_MAGIC:
        effects.dispel_used.add(caster.identifier)
    battle.events.append(BattleEvent(f"{caster.name} casts spell {spell}", "spell", regiment=caster.identifier,
                                     spell=spell, x=x, y=y))
    _start(battle, effect, caster, origin_model, target)
    effects.add(effect)
    return True


def _start(battle: Battle, effect: Effect, caster: Regiment, origin_model: int, target: Regiment | None) -> None:
    """Per-spell launch state."""
    spell, rng = effect.code, battle.rng
    if spell in BOLTS:
        bolt = BOLTS[spell]
        _start_projectile(battle, effect, _origin(caster, origin_model, bolt.start), effect.aim, bolt, caster.bs,
                          magic.SPELLS[spell].range or 1, beam=bolt.beam)
    elif spell == HUNTING_SPEAR:
        _start_spear(effect, caster)
    elif spell == MADNESS and target is not None:
        _start_madness(battle, effect, target)
    elif spell == ERE_WE_GO and target is not None:
        effect.timer = LASTING
        effect.saved_initiative = target.initiative
        target.toughness += 1
        target.initiative = 20
    elif spell == CURSE and target is not None:
        # C2 4.1: speed and I saved, then halved. PROVISIONAL: the engine's per-tick speed stands in for s_rlmv.
        effect.saved_speed, effect.saved_initiative = target.speed_per_tick, target.initiative
        target.speed_per_tick = target.speed_per_tick / 2
        target.initiative = target.initiative // 2
    elif spell in (MORK_SAVE_UZ, FISTS, DISPEL_MAGIC, AZURE_BLADES):
        effect.timer = LASTING
    elif spell == SKITTERLEAP:
        effect.timer = SKITTER_FRAMES
    elif spell == STORM:
        effect.value = rng.randrange(6) + rng.randrange(6) + 2 + 1  # C2 1.1: 2D6 + 1 bolts, first die first
        effect.timer = STORM_WINDUP
    elif spell == WIND_BLAST:
        reach = magic.spell_range(WIND_BLAST, rng) or 1  # C1 1.2 step 2: a second, independent range draw
        _start_projectile(battle, effect, _origin(caster, origin_model, "origin"), effect.aim, GUST, caster.bs,
                          reach, beam=False, steps=GUST_FLIGHT)
    elif spell == FLAMESTORM:
        _add_area(battle, effect, FLAME_RADIUS, 80)
    elif spell == TANGLING_THORN:
        _add_area(battle, effect, THORN_RADIUS, 16)
        _entangle(battle, effect)
    elif spell == DA_KRUNCH:
        for _ in range(4):  # C1 4.1: the original still makes the four scatter draws
            rng.randrange(2)
    elif spell == CONFLAGRATION:
        effect.value = 1 + rng.randrange(6)  # C1 5.1: one D6 sets the radius 8k + 8 and the fuse 9k
    elif spell == FLOCK:
        for _ in range(40):  # C3 3.1: the birds' positions, which matter for replays
            rng.randrange(64)
    elif spell == SAPPHIRE_ARCH:
        effect.timer = LASTING
        for _ in range(18):  # C2 3.1: 54 particle draws
            rng.randrange(96)
            rng.randrange(96)
            rng.randrange(32)
    elif spell == FLYING_BOWER:
        effect.aim = _nudge(battle, caster, *effect.aim)
        for _ in range(4):  # C2 2.2: the take-off projectile's scatter draws (offsets all 0)
            rng.randrange(2)


def _origin(caster: Regiment, origin_model: int, kind: str) -> tuple[float, float]:
    """A 2.1: the origin model's position, else the unit position; Lightning does the reverse with the leader."""
    positions = caster.model_positions()
    has_origin = 0 <= origin_model < len(positions)
    if kind == "unit":
        return caster.x, caster.y
    if kind == "reverse":
        return (caster.x, caster.y) if has_origin else reference_figure(caster)
    return positions[origin_model] if has_origin else (caster.x, caster.y)


def _flying_aim_height(battle: Battle, x: float, y: float) -> float:
    """A 2.1: half the height plus the elevation of a flying unit standing at the point, else none."""
    for unit in battle.regiments.values():
        if unit.active and unit.airborne and _centre_d(unit, x, y) < unit.bounding_radius():
            return FLYING_ELEVATION + UNIT_HEIGHT / 2
    return 0.0


def _scatter(rng: random.Random, start: tuple[float, float], aim: tuple[float, float], bs: int,
             reach: float, step: int | None = None) -> tuple[float, float]:
    """A 2.2: step = trunc(8 d / range) unless given; per axis a magnitude 0..10 - min(BS, 10) then a sign draw."""
    if step is None:
        step = int(8 * _d(*start, *aim) / reach)
    span = 11 - min(bs, 10)
    offsets: list[int] = []
    for _ in range(2):
        magnitude = rng.randrange(span)
        sign = 1 if rng.randrange(2) == 0 else -1
        offsets.append(magnitude * sign * step)
    return aim[0] + offsets[0], aim[1] + offsets[1]


def _start_projectile(battle: Battle, effect: Effect, start: tuple[float, float], aim: tuple[float, float],
                      bolt: Bolt, bs: int, reach: float, beam: bool, steps: int | None = None,
                      arched: bool = False) -> None:
    """Start point, scatter and flight length (A 2.1-2.3)."""
    dest = _scatter(battle.rng, start, aim, bs, reach)
    effect.start, effect.dest = start, dest
    effect.x, effect.y = start
    effect.terminal_height = _flying_aim_height(battle, *dest)
    effect.aim_height = max(effect.terminal_height, float(bolt.aim_floor))
    effect.steps = steps if steps is not None else 1 + _d(*start, *dest) // BEAM_STEP if beam else FIXED_FLIGHT
    effect.remaining = effect.steps
    effect.strength = bolt.strength
    effect.flying = True
    effect.arched = arched
    effect.arc = 0
    battle.events.append(BattleEvent(
        f"spell {effect.code} bolt launched", "spell_bolt_launch", regiment=effect.owner, spell=effect.code,
        serial=effect.serial, start=list(start), aim=list(aim), dest=list(dest), steps=effect.steps))


def _start_spear(effect: Effect, caster: Regiment) -> None:
    """A 3.5: S 6, at most 180 ticks, the first 9-tick leg from the unit position to the aim point."""
    effect.timer = LASTING
    effect.strength = SPEAR.strength
    effect.start = effect.dest = (caster.x, caster.y)
    effect.x, effect.y = caster.x, caster.y
    _new_leg(effect, effect.aim)


def _start_madness(battle: Battle, effect: Effect, target: Regiment) -> None:
    """B 1.1: event 0x31 to the target, its side saved and swapped (player or allied -> enemy, enemy -> allied)."""
    effect.timer = LASTING
    effect.saved_side = target.side
    target.side = Side.ENEMY if target.side != Side.ENEMY else Side.NEUTRAL
    _queue(battle, target.identifier, EVENT_MADDENED)


def _add_area(battle: Battle, effect: Effect, radius: int, height: int, at: tuple[float, float] | None = None) -> None:
    """An area object, mirrored as a solid active map object into the battle's object lists so that movement,
    collisions (and the charge stop), sight lines and missiles treat it as scenery (C1 0)."""
    x, y = at if at is not None else effect.aim
    table(battle).areas.append(Area(effect.serial, x, y, radius, height))
    view = {"x": x, "y": y, "radius": radius, "height": height, "status": ["os_active", "os_solid"],
            AREA_KEY: effect.serial}
    battle.objects.append(view)
    battle.shooting_objects.append(view)


def _remove_areas(battle: Battle, effect: Effect) -> None:
    effects = table(battle)
    effects.areas = [area for area in effects.areas if area.owner != effect.serial]
    battle.objects = [obj for obj in battle.objects if obj.get(AREA_KEY) != effect.serial]
    battle.shooting_objects = [obj for obj in battle.shooting_objects if obj.get(AREA_KEY) != effect.serial]


# ===== The magical hit (A 4, C3 1) =====

@dataclass(frozen=True)
class Impact:
    caster: str | None
    strength: int
    wound_die: int
    save: bool
    fire: bool


def _height_ok(unit: Regiment, height: float) -> bool:
    """A 4.1 with the engine's unit height: ground units up to it, flying units inside their band."""
    if unit.airborne:
        return FLYING_ELEVATION <= height <= FLYING_ELEVATION + UNIT_HEIGHT
    return height <= UNIT_HEIGHT


def _units_at(battle: Battle, x: float, y: float, height: float, excluded: str | None) -> list[Regiment]:
    """Units struck by an impact test at the point: trunc(d) < footprint from the footprint centre, height test
    passed (A 4.1)."""
    return [unit for unit in battle.regiments.values()
            if unit.active and unit.identifier != excluded and unit.models > 0
            and _centre_d(unit, x, y) < unit.bounding_radius() and _height_ok(unit, height)]


def _solid_at(battle: Battle, x: float, y: float, height: float) -> bool:
    """A solid map object containing the point at a height it reaches (A 2.3): scenery uses the unit height, area
    objects their own (C1 0)."""
    for obj in battle.shooting_objects:
        status = {str(value).casefold() for value in obj.get("status") or ()}
        if "os_solid" not in status:
            continue
        ox, oy = float(obj.get("x") or 0), float(obj.get("y") or 0)
        if _d(ox, oy, x, y) < float(obj.get("radius") or 8) and height <= float(obj.get("height") or UNIT_HEIGHT):
            return True
    return False


def _wound_roll(battle: Battle, unit: Regiment, strength: int, save: bool, fire: bool,
                index: int, trace: dict[str, Any] | None = None) -> bool:
    """To-wound with the unit's T, then the save when allowed (a regenerator's 4+ roll for damage type 0, never
    wounded by fire with a save), then MagicResistent (an even draw ignores the hit). True = wounded."""
    rng = battle.rng
    model = unit.melee_models[index]
    trace = trace if trace is not None else {}
    trace["wound_roll"] = roll = rng.randrange(6) + 1
    trace["wound_needed"] = wfb_to_wound(strength, unit.model_toughness(model))
    if roll < trace["wound_needed"]:
        trace["outcome"] = "no_wound"
        return False
    if save:
        armour = unit.model_armour(model)
        if armour == 6:  # regeneration (game_rules.md "Regeneration by damage source")
            if fire:
                trace["outcome"] = "saved"
                return False
            trace["save_roll"] = save_roll = rng.randrange(6) + 1
            if save_roll >= 4:
                trace["outcome"] = "saved"
                return False
        else:
            trace["save_roll"] = save_roll = rng.randrange(6) + 1
            if save_roll >= combat.armour_threshold(armour, strength):
                trace["outcome"] = "saved"
                return False
    if "MagicResistent" in unit.psychology:
        trace["resist_draw"] = draw = rng.randrange(2)
        if draw == 0:
            trace["outcome"] = "resisted"
            return False
    trace["outcome"] = "wounded"
    return True


def _wound(unit: Regiment, index: int, wounds: int, dead: set[int]) -> None:
    model = unit.melee_models[index]
    model.wounds_taken += wounds
    if model.wounds_taken >= unit.model_wounds(model):
        dead.add(index)


def _kill(battle: Battle, unit: Regiment, dead: Iterable[int], impact: Impact) -> None:
    kind = animation.DEATH_FIRE if impact.fire else animation.DEATH_ORDINARY
    combat.kill_models(unit, dead, battle, kind, killer=impact.caster)


def magical_hit(battle: Battle, unit: Regiment, impact: Impact, trace: dict[str, Any] | None = None) -> None:
    """One hit on one unit (A 4.2): a uniform random model, the wound roll, then 1..die wounds on that model only;
    a lethal wound credits the caster. Buildings (A 4.3): the first model, no save, no MagicResistent. `trace`, when
    given, receives the rolls and outcome for the battle log (bf003_playtest 3.1)."""
    rng = battle.rng
    trace = trace if trace is not None else {}
    unit.model_positions()
    building = _building(unit)
    index = 0 if building else rng.randrange(unit.models)
    trace["model"] = index
    if building:
        trace["wound_roll"] = roll = rng.randrange(6) + 1
        trace["wound_needed"] = wfb_to_wound(impact.strength, unit.toughness)
        if roll < trace["wound_needed"]:
            trace["outcome"] = "no_wound"
            return
        trace["outcome"] = "wounded"
    elif not _wound_roll(battle, unit, impact.strength, impact.save, impact.fire, index, trace):
        return
    dead: set[int] = set()
    trace["wounds"] = wounds = rng.randrange(impact.wound_die) + 1
    _wound(unit, index, wounds, dead)
    _kill(battle, unit, dead, impact)
    trace["killed"] = len(dead)


def impact_test(battle: Battle, x: float, y: float, height: float, impact: Impact, excluded: str | None,
                messages: bool, source: Effect | None = None) -> bool:
    """One impact test with radius 0 (A 4): each struck unit takes one magical hit; True when anything (unit or
    solid object) was struck. Terminal impacts (messages on) show message 2004 for every unit struck. With a
    `source` effect every struck unit also yields a "spell_strike" battle event (rolls, wounds, deaths)."""
    struck = _units_at(battle, x, y, height, excluded)
    for unit in struck:
        if messages:
            _message(battle, unit, GMTXT_DIRECT_HIT)
        trace: dict[str, Any] = {}
        before = unit.models
        magical_hit(battle, unit, impact, trace)
        if source is not None:
            battle.events.append(BattleEvent(
                f"{unit.name}: struck by spell {source.code} ({trace.get('outcome')})", "spell_strike",
                regiment=unit.identifier, caster=impact.caster, spell=source.code, serial=source.serial,
                x=x, y=y, height=height, terminal=messages, models_before=before, models_after=unit.models,
                **trace))
    return bool(struck) or _solid_at(battle, x, y, height)


def blast(battle: Battle, x: float, y: float, radius: int, impact: Impact, excluded: str | None,
          messages: bool) -> None:
    """A radius > 0 magical impact at height 0 (C3 1): units whose footprint contains the point roll every model
    (wound die), units within footprint + radius take k = trunc((r + R - d) n / (r + R)) picks (at least 1) at S/2
    with 1 wound and the save at S/2. Units in the air are never struck. Buildings: the first model."""
    rng = battle.rng
    for unit in list(battle.regiments.values()):
        if not unit.active or unit.identifier == excluded or unit.models <= 0 or unit.airborne:
            continue
        unit.model_positions()
        d = _centre_d(unit, x, y)
        r = int(unit.bounding_radius())
        core = d < r
        if not core and not d < r + radius:
            continue
        if messages:
            _message(battle, unit, GMTXT_DIRECT_HIT if core else GMTXT_MARGIN_HIT)
        dead: set[int] = set()
        half = impact.strength // 2
        if _building(unit):
            strength = impact.strength if core else half
            if rng.randrange(6) + 1 >= wfb_to_wound(strength, unit.toughness):
                _wound(unit, 0, rng.randrange(impact.wound_die) + 1 if core else 1, dead)
        elif core:
            for index in range(unit.models):
                if _wound_roll(battle, unit, impact.strength, impact.save, impact.fire, index):
                    _wound(unit, index, rng.randrange(impact.wound_die) + 1, dead)
        else:
            picks = int((r + radius - d) * unit.models / (r + radius))
            for _ in range(picks if picks >= 2 else 1):
                index = rng.randrange(unit.models)
                if _wound_roll(battle, unit, half, impact.save, impact.fire, index):
                    _wound(unit, index, 1, dead)
        _kill(battle, unit, dead, impact)


def slay(battle: Battle, unit: Regiment, count: int | None, kind: int, caster: str | None) -> None:
    """Lethal wounds without any roll on the first `count` models (all for None), credited to the caster (C1 4.2,
    5.3). PROVISIONAL: "first" is the engine's model order."""
    unit.model_positions()
    number = unit.models if count is None else min(count, unit.models)
    combat.kill_models(unit, range(number), battle, kind, killer=caster, clear_credit=caster is None)


def _panic(battle: Battle, unit: Regiment) -> bool:
    """A panic test at modifier 0 (game_rules.md 7.1); failure routs. True when it failed. PROVISIONAL: a routing
    or CantBreak unit does not test, a held unit cannot start a rout (C1 3.3)."""
    if not unit.active or unit.routing or "CantBreak" in unit.psychology:
        return False
    if combat.leadership_test(unit.effective_leadership, battle.rng):
        return False
    if not unit.held:
        combat.start_rout(unit, battle)
    return True


def _panic_inside(battle: Battle, x: float, y: float) -> None:
    """Burning Head (A 3.6): every unit whose footprint contains the point inclusively, any side, the caster's own
    too, tests panic at modifier 0."""
    for unit in list(battle.regiments.values()):
        if unit.active and _centre_d(unit, x, y) <= unit.bounding_radius():
            _panic(battle, unit)


# ===== Per-tick update (A 1.7, B 5.2) =====

def tick(battle: Battle) -> None:
    """The effect step, after units and ordinary missiles: removal cancellations (A 1.4), item auras, Dispel Magic
    and Mork Save Uz passes, then every effect in launch order. Nothing of the passes runs with no effect active."""
    effects = table(battle)
    for effect in effects.effects():
        owner = battle.regiments.get(effect.owner)
        target = battle.regiments.get(effect.target) if effect.target is not None else None
        owner_gone = (owner is None or not owner.active) and not effect.innate and _wizard(owner)
        if owner_gone or (effect.target is not None and (target is None or not target.active)):
            cancel(battle, effect)
    if effects.effects():
        for unit in list(battle.regiments.values()):
            if unit.active and unit.living_leader_index is not None:
                for item in unit.items:
                    if item in ITEM_AURAS:
                        dispel_pass(battle, unit, ITEM_AURAS[item], None)
        for effect in effects.effects():
            if effect.ended:
                continue
            if effect.code == DISPEL_MAGIC and effect.timer > 0 and effect.timer % 3 == 0:
                owner = battle.regiments.get(effect.owner)
                if owner is not None and dispel_pass(battle, owner, 50, effect):
                    _end(battle, effect)
            elif effect.code == MORK_SAVE_UZ and effect.target is not None:
                protected = battle.regiments.get(effect.target)
                if protected is not None:
                    dispel_pass(battle, protected, 50, effect)
    for effect in effects.effects():
        if not effect.ended:
            _update(battle, effect)
            effect.elapsed += 1


def _wizard(unit: Regiment | None) -> bool:
    """Only a Wizard-class caster's removal cancels its effects (A 1.4)."""
    from .interpreter import WIZARD_CLASS
    return unit is None or unit.unit_class == WIZARD_CLASS


def _update(battle: Battle, effect: Effect) -> None:
    if effect.tail >= 0:
        effect.tail -= 1
        if effect.tail < 0:
            _end(battle, effect)
        return
    code = effect.code
    updates: dict[int, Callable[[Battle, Effect], None]] = {
        HUNTING_SPEAR: _update_spear, FISTS: _update_fists, SKITTERLEAP: _update_skitter, STORM: _update_storm,
        AZURE_BLADES: _update_azure, FLOCK: _update_flock, FLAMESTORM: _update_flamestorm,
        WIND_BLAST: _update_wind_blast, DA_KRUNCH: _update_krunch, CONFLAGRATION: _update_conflagration,
        CURSE: _update_curse, FLYING_BOWER: _update_bower, SAPPHIRE_ARCH: _update_arch,
    }
    if code in BOLTS:
        if _fly(battle, effect, BOLTS[code]):
            _finish(effect)
    elif code in updates:
        updates[code](battle, effect)
    elif code == TANGLING_THORN:
        pass  # C1 3.2: no natural end
    elif effect.timer == 0:  # Madness, Ere We Go, Mork Save Uz, Dispel Magic: the update finding 0 ends it
        _end(battle, effect)
    else:
        effect.timer -= 1


def _finish(effect: Effect) -> None:
    """The decisive part is over: the effect stays in the list for its visual tail (A 1.5)."""
    effect.tail = TAIL_TICKS


# ===== Projectiles (A 2) =====

def _height_above_ground(battle: Battle, effect: Effect, bolt: Bolt, x: float, y: float) -> float:
    """A 2.1: L + line(t) - ground(here), the line running from ground(start) + L to ground(destination) + A."""
    t = 1 - effect.remaining / effect.steps if effect.steps else 1.0
    start_level = battle.ground_height(*effect.start) + bolt.launch_height
    end_level = battle.ground_height(*effect.dest) + effect.aim_height
    return bolt.launch_height + start_level + (end_level - start_level) * t - battle.ground_height(x, y)


def _fly(battle: Battle, effect: Effect, bolt: Bolt) -> bool:
    """One flight step (A 2.3-2.5, bf003_playtest 3.2); True when the projectile is over. In this order: position
    dest + trunc((start - dest) r / N), exactly the start point on the first tick; the arc step (Fireball and arched
    Storm bolts, C2 1.3: +1 while 2r > N, else -1); the height with the arc included; the silent in-flight test, which
    always runs, even at a negative height; then removal after the test when the bolt hit and stops, or when the
    height is below 0 (exactly 0 survives); then the terminal impact: beams once within 40 of the destination (also
    on the tick they stop), others at r = 0. Fireball's arc ends at -1, so a ground shot makes its last in-flight
    test and no terminal impact (A 3.4). The end reason is logged."""
    r = effect.remaining
    sx, sy = effect.start
    dx, dy = effect.dest
    if r == effect.steps:
        x, y = sx, sy
    else:
        x = dx + int((sx - dx) * r / effect.steps)
        y = dy + int((sy - dy) * r / effect.steps)
    effect.x, effect.y = x, y
    if effect.code == FIREBALL or effect.arched:
        effect.arc += 1 if 2 * r > effect.steps else -1
    height = _height_above_ground(battle, effect, bolt, x, y) + effect.arc
    impact = Impact(effect.owner, bolt.strength, bolt.wound_die, bolt.save, bolt.fire)
    hit = impact_test(battle, x, y, height, impact, effect.owner, messages=False, source=effect)
    if hit:
        _after_hit(battle, effect, bolt, x, y)
    effect.remaining -= 1
    if height < 0:
        _log_end(battle, effect, "below_ground", x, y, height)
        return True
    terminal = (_d(x, y, dx, dy) < BEAM_TERMINAL) if bolt.beam else r == 0
    if terminal:
        if impact_test(battle, dx, dy, effect.terminal_height, impact, None, messages=True, source=effect):
            _after_hit(battle, effect, bolt, dx, dy)
        _log_end(battle, effect, "terminal", dx, dy, effect.terminal_height)
        return True
    if hit and bolt.stops:
        _log_end(battle, effect, "hit", x, y, height)
        return True
    return False


def _log_end(battle: Battle, effect: Effect, reason: str, x: float, y: float, height: float) -> None:
    """The flight's end reason for the battle log (bf003_playtest 3.1; an engine choice): "hit", "below_ground",
    "terminal" or "cancelled" (dispelled, or the caster was removed)."""
    battle.events.append(BattleEvent(f"spell {effect.code} flight ends: {reason}", "spell_bolt_end",
                                     regiment=effect.owner, spell=effect.code, serial=effect.serial,
                                     reason=reason, x=x, y=y, height=height))


def _after_hit(battle: Battle, effect: Effect, bolt: Bolt, x: float, y: float) -> None:
    """Burning Head's panic (A 3.6) and Fireball's thorn burning: every Tangling Thorn whose cast point is closer
    than 32 to the impact is cancelled (A 3.4)."""
    if bolt.panic:
        _panic_inside(battle, x, y)
    if effect.code == FIREBALL:
        for thorn in table(battle).effects():
            if thorn.code == TANGLING_THORN and _d(*thorn.aim, x, y) < THORN_RADIUS:
                cancel(battle, thorn)


def _new_leg(effect: Effect, point: tuple[float, float]) -> None:
    """A 3.5 step 5: a 9-tick leg from the spear's position to `point`. PROVISIONAL: the obstacle scan's steer
    point is not used (straight legs)."""
    effect.start, effect.dest = (effect.x, effect.y), point
    effect.steps = effect.remaining = 9
    effect.leg_clock = 9


def _spear_step(battle: Battle, effect: Effect) -> None:
    """Advance one step of the leg and run the silent in-flight test; a hit stops the leg."""
    sx, sy = effect.start
    dx, dy = effect.dest
    r = effect.remaining
    effect.x = dx + int((sx - dx) * r / 9)
    effect.y = dy + int((sy - dy) * r / 9)
    effect.remaining -= 1
    impact = Impact(effect.owner, effect.strength, SPEAR.wound_die, False, False)
    if impact_test(battle, effect.x, effect.y, SPEAR.launch_height, impact, effect.owner, messages=False):
        effect.stopped = True


def _update_spear(battle: Battle, effect: Effect) -> None:
    """Hunting Spear (A 3.5): re-aimed every third tick at the target's centre, a stop on a hit, then either the
    strike chain S, S-1 .. 1 inside the target's footprint or one strength lost. The chain is tested at the spear's
    absolute height (ground + 8), so it misses on raised ground (the report's high-ground quirk)."""
    target = battle.regiments.get(effect.target or "")
    if effect.timer == 0 or target is None:
        _end(battle, effect)
        return
    effect.timer -= 1
    centre = footprint_centre(target)
    if effect.stopped:
        effect.stopped = False
        d = _d(effect.x, effect.y, *centre)
        radius = target.bounding_radius()
        if d < radius:
            height = battle.ground_height(effect.x, effect.y) + SPEAR.launch_height
            for strength in range(effect.strength, 0, -1):
                impact_test(battle, effect.x, effect.y, height,
                            Impact(effect.owner, strength, SPEAR.wound_die, False, False), None, messages=False)
            _end(battle, effect)
            return
        if d == radius:
            _end(battle, effect)
            return
        effect.strength -= 1
        if effect.strength == 0:
            _end(battle, effect)
            return
        _new_leg(effect, centre)
        _spear_step(battle, effect)
        return
    effect.leg_clock -= 1
    if effect.leg_clock % 3 == 0:
        _new_leg(effect, centre)
    _spear_step(battle, effect)


# ===== Lasting spells (B) =====

def _update_fists(battle: Battle, effect: Effect) -> None:
    """Fists of Gork (B 4): 45 strikes on timer values 180, 176 .. 4 at the fixed aim point."""
    if effect.timer == 0:
        _end(battle, effect)
        return
    if effect.timer % 4 == 0:
        _fists_strike(battle, effect)
    effect.timer -= 1


def _fists_strike(battle: Battle, effect: Effect) -> None:
    """The nearest unit whose centre is within 16 (inclusive) of the aim point, any side but the caster's own,
    not hidden or leaving; D6 >= to-wound(S6, T) gives a wound to a random model, and each further consecutive 6
    after a first 6 one more. No save, no MagicResistent, no kill credit written (B 4)."""
    victim: Regiment | None = None
    best = 0
    for unit in battle.regiments.values():
        if (not unit.active or unit.hidden or unit.identifier == effect.owner or unit.models <= 0
                or _leaving(battle, unit)):
            continue
        d = _centre_d(unit, *effect.aim)
        if d <= FISTS_REACH and (victim is None or d < best):
            victim, best = unit, d
    if victim is None:
        return
    rng = battle.rng
    roll = rng.randrange(6) + 1
    if roll < wfb_to_wound(6, victim.toughness):
        return
    dead: set[int] = set()
    victim.model_positions()
    while True:
        _wound(victim, rng.randrange(victim.models), 1, dead)
        if roll != 6:
            break
        roll = rng.randrange(6) + 1
        if roll != 6:
            break
    combat.kill_models(victim, dead, battle, animation.DEATH_ORDINARY)


def _update_skitter(battle: Battle, effect: Effect) -> None:
    """Skitterleap (B 2): the caster's unit position is placed at the aim point on tick T+4, its models moved with
    it; facing, formation, orders, target and melee state untouched, no destination checks."""
    if effect.timer:
        effect.timer -= 1
        return
    unit = battle.regiments.get(effect.owner)
    if unit is not None and unit.active:
        _move_unit(unit, *effect.aim)
    _end(battle, effect)


# ===== Radius spells (C3) =====

def _update_azure(battle: Battle, effect: Effect) -> None:
    """Azure Blades (C3 2.2): 180 strikes, each a blast centred on the target's current unit position with its
    bounding radius, the target excluded: S4, 1 wound, save, messages on."""
    target = battle.regiments.get(effect.target or "")
    if effect.timer == 0 or target is None:
        _end(battle, effect)
        return
    effect.timer -= 1
    blast(battle, target.x, target.y, int(target.bounding_radius()), Impact(effect.owner, 4, 1, True, False),
          target.identifier, messages=True)


def _update_flock(battle: Battle, effect: Effect) -> None:
    """The Flock of Doom (C3 3.2): strikes at the fixed aim point on T+10, T+18, T+26 (radius 32, S3, D6 wounds,
    save, nobody excluded); the effect ends on T+38."""
    if effect.elapsed in FLOCK_STRIKES:
        blast(battle, *effect.aim, FLOCK_RADIUS, Impact(effect.owner, 3, 6, True, False), None, messages=True)
    elif effect.elapsed >= FLOCK_END:
        _end(battle, effect)


# ===== Area spells (C1) =====

def _update_flamestorm(battle: Battle, effect: Effect) -> None:
    """Flamestorm (C1 2.3): from T+18 a radius-16 blast every tick (S4, 1 wound, no save, fire, the caster not
    spared), plus a messaged terminal blast on the last tick of every 19-tick column. No natural end."""
    if effect.elapsed < FLAME_START:
        return
    impact = Impact(effect.owner, 4, 1, False, True)
    blast(battle, *effect.aim, FLAME_RADIUS, impact, None, messages=False)
    if (effect.elapsed - FLAME_START) % FLAME_COLUMN == FLAME_COLUMN - 1:
        blast(battle, *effect.aim, FLAME_RADIUS, impact, None, messages=True)


def _update_wind_blast(battle: Battle, effect: Effect) -> None:
    """Wind Blast (C1 1.3-1.5): a 54-step gust with a 0..7 jitter towards +x/+y each tick, height 0, passing through
    (S3, 1 wound, save, caster's unit excluded), a terminal impact at the destination; from T+5 a trail disc at the
    previous tick's point when none is within 16 of it (up to 30). Afterwards the effect stays, never ending."""
    if effect.flying:
        r = effect.remaining
        sx, sy = effect.start
        dx, dy = effect.dest
        x = dx + int((sx - dx) * r / effect.steps) + battle.rng.randrange(8)
        y = dy + int((sy - dy) * r / effect.steps) + battle.rng.randrange(8)
        effect.x, effect.y = x, y
        impact = Impact(effect.owner, GUST.strength, GUST.wound_die, GUST.save, GUST.fire)
        impact_test(battle, x, y, 0, impact, effect.owner, messages=False)
        effect.remaining -= 1
        if r == 0:
            impact_test(battle, dx, dy, 0, impact, None, messages=True)
            effect.flying = False
    if effect.elapsed >= TRAIL_START and effect.previous is not None and len(effect.trail) < TRAIL_MAX:
        last = effect.trail[-1] if effect.trail else None
        if last is None or _d(*last, *effect.previous) > TRAIL_SPACING:
            effect.trail.append(effect.previous)
            _add_area(battle, effect, TRAIL_RADIUS, TRAIL_HEIGHT, at=effect.previous)
    effect.previous = (effect.x, effect.y) if effect.flying or effect.elapsed <= GUST_FLIGHT else None


def _entangle(battle: Battle, effect: Effect) -> None:
    """Tangling Thorn (C1 3.1): every ground unit (not a building) whose centre is strictly within 32 of the point is
    halted (unless broken or pursuing) and held."""
    for unit in battle.regiments.values():
        if (unit.active and not unit.airborne and not _building(unit)
                and _centre_d(unit, *effect.aim) < THORN_RADIUS):
            if not unit.routing and not unit.pursuing:
                unit.target_x = unit.target_y = None
                unit.waypoints = []
                unit.attack_target = None
            unit.held = True


def _update_krunch(battle: Battle, effect: Effect) -> None:
    """Da Krunch (C1 4): on T..T+9 the foot falls (height trunc(120 r / 9)); every unit reaching within 32 of the
    point (d < footprint + 32) whose top is at least the foot's height is slain outright (death kind 2, credited to
    the caster). The foot stands as an area object (radius 32, height 40) on T+10..T+46; the effect ends on T+57.
    PROVISIONAL: the lift (T+47..T+56) is treated as harmless (C1 4.3 allows it)."""
    e = effect.elapsed
    if e <= KRUNCH_FALL:
        height = 120 * (KRUNCH_FALL - e) // KRUNCH_FALL
        for unit in list(battle.regiments.values()):
            top = FLYING_ELEVATION + UNIT_HEIGHT if unit.airborne else UNIT_HEIGHT
            if (unit.active and unit.models > 0 and top >= height
                    and _centre_d(unit, *effect.aim) < unit.bounding_radius() + KRUNCH_REACH):
                slay(battle, unit, None, animation.DEATH_MISSILE, effect.owner)
    elif e == KRUNCH_STAND:
        _add_area(battle, effect, KRUNCH_REACH, 40)
    elif e == KRUNCH_LIFT:
        _remove_areas(battle, effect)
    elif e >= KRUNCH_END:
        _end(battle, effect)


def _update_conflagration(battle: Battle, effect: Effect) -> None:
    """Conflagration of Doom (C1 5): R = 8k + 8; panic tests on T, T+9 .. T+9(k-1) for every unit whose centre is
    within R (inclusive); a 10-tick fall from T+9k slaying the first max(1, trunc(n (R - d) / R)) models of units
    whose footprint contains the point, then the finale on its last tick; all fire, credited to the caster."""
    k, e = effect.value, effect.elapsed
    reach = 8 * k + 8
    x, y = effect.aim
    if e < 9 * k:
        if e % 9 == 0:
            for unit in list(battle.regiments.values()):
                if unit.active and _centre_d(unit, x, y) <= reach:
                    _panic(battle, unit)
        return
    for unit in list(battle.regiments.values()):
        d, fp = _centre_d(unit, x, y), int(unit.bounding_radius())
        if unit.active and unit.models > 0 and d < fp:
            slay(battle, unit, 1 if _building(unit) else max(1, unit.models * (reach - d) // reach),
                 animation.DEATH_FIRE, effect.owner)
    if e == 9 * k + 9:
        for unit in list(battle.regiments.values()):
            d, fp = _centre_d(unit, x, y), int(unit.bounding_radius())
            if not unit.active or unit.models <= 0 or not d < fp + reach:
                continue
            if _building(unit):
                count: int | None = 1
            elif d + fp < reach:
                count = None
            else:
                count = max(1, unit.models * (reach - d + fp) // (2 * fp))
            slay(battle, unit, count, animation.DEATH_FIRE, effect.owner)
        _finish(effect)


# ===== Channelled, flight, portal and curse spells (C2) =====

def _update_storm(battle: Battle, effect: Effect) -> None:
    """Storm of Shemtek (C2 1): after the wind-up, value bolts, each a scattered Lightning-type beam from the
    caster's first model (bolts 2+ arched), the next one 7 ticks after the previous ended; the effect ends one
    closing tick after the last flash. PROVISIONAL: the caster's model freeze is not modelled."""
    caster = battle.regiments.get(effect.owner)
    if effect.flying:
        if _fly(battle, effect, STORM_BOLT):
            effect.flying = False
            effect.value -= 1
            effect.timer = STORM_FLASH - 1 + (STORM_CLOSE if effect.value == 0 else 0)
        return
    if effect.timer:
        effect.timer -= 1
        return
    if effect.value == 0 or caster is None:
        _end(battle, effect)
        return
    first_bolt = effect.strength == 0
    target = _storm_target(battle, effect, caster)
    effect.target = target.identifier if target is not None else None
    aim = footprint_centre(target) if target is not None else effect.aim
    positions = caster.model_positions()
    start = positions[0] if positions else (caster.x, caster.y)
    _start_projectile(battle, effect, start, aim, STORM_BOLT, caster.bs, STORM_FALLBACK, beam=True,
                      arched=not first_bolt)


def _storm_target(battle: Battle, effect: Effect, caster: Regiment) -> Regiment | None:
    """C2 1.2: the nearest hostile within 80 of the aim point (unless the point is inside the caster's footprint),
    else within 576 of the caster's centre; never the caster, the previous target, hidden or leaving units."""
    def nearest(x: float, y: float, reach: int) -> Regiment | None:
        best: Regiment | None = None
        best_d = 0
        for unit in battle.regiments.values():
            if (not unit.active or unit is caster or unit.identifier == effect.target or unit.hidden
                    or not _hostile(caster, unit) or _leaving(battle, unit)):
                continue
            d = _centre_d(unit, x, y)
            if d <= reach and (best is None or d < best_d):
                best, best_d = unit, d
        return best
    found = None
    if _centre_d(caster, *effect.aim) > caster.bounding_radius():
        found = nearest(*effect.aim, STORM_REACH)
    return found or nearest(*footprint_centre(caster), STORM_FALLBACK)


def _update_curse(battle: Battle, effect: Effect) -> None:
    """The Curse of Anraheir (C2 4.2): a mounted target takes a panic test on every tick of segment 10; a failure
    ends the Curse in the same step. No other natural end."""
    target = battle.regiments.get(effect.target or "")
    if target is None or not target.mount:
        return
    if combat.segment_state(battle.tick_count)[2] != combat.SEGMENTS_PER_TURN:
        return
    if not combat.leadership_test(target.effective_leadership, battle.rng):
        if not target.held and not target.routing:
            combat.start_rout(target, battle)
        _end(battle, effect)


def _nudge(battle: Battle, caster: Regiment, x: float, y: float) -> tuple[float, float]:
    """Flying Bower's landing point (C2 2.1 step 2): pushed directly away from each scenery object, area object and
    friendly unit footprint it overlaps by footprint - d + trunc(caster footprint / 2). Enemies never push.
    PROVISIONAL: the snap out of solid and edge areas (step 1) is not modelled."""
    half = int(caster.bounding_radius()) // 2
    circles: list[tuple[float, float, float]] = []
    for obj in battle.shooting_objects:  # scenery and the area objects mirrored into it
        circles.append((float(obj.get("x") or 0), float(obj.get("y") or 0), float(obj.get("radius") or 8)))
    for unit in battle.regiments.values():
        if unit.active and unit is not caster and (unit.side == Side.ENEMY) == (caster.side == Side.ENEMY):
            circles.append((*footprint_centre(unit), unit.bounding_radius()))
    for cx, cy, radius in circles:
        overlap = radius - _d(cx, cy, x, y) + half
        if overlap <= 0:
            continue
        if x == cx and y == cy:
            y += overlap
            continue
        angle = math.atan2(x - cx, y - cy)
        x += int(int(256 * math.sin(angle)) * overlap / 256)
        y += int(int(256 * math.cos(angle)) * overlap / 256)
    return int(x), int(y)


def _update_bower(battle: Battle, effect: Effect) -> None:
    """The Flying Bower (C2 2.2): take-off T..T+18 (two wobble draws a step until T+17), lift at T+19 (scattered
    flight from the unit's centre, fixed step 8, 54 steps; a caster in melee leaves its grid and the other side hears
    0x0F), the unit following one step behind the projectile with a 0..7 wobble, landing exactly on the aim point at
    T+74. Lifted: not drawn, cannot engage."""
    unit = battle.regiments.get(effect.owner)
    e, rng = effect.elapsed, battle.rng
    if unit is None:
        _end(battle, effect)
        return
    if e < BOWER_LIFT - 1:
        rng.randrange(4)
        rng.randrange(4)
    elif e == BOWER_LIFT:
        start = footprint_centre(unit)
        effect.start, effect.dest = start, _scatter(rng, start, effect.aim, unit.bs, 1, step=8)
        effect.steps = effect.remaining = BOWER_FLIGHT
        effect.flying = True
        table(battle).flying.add(unit.identifier)
        _sync_lifted(battle, unit)
        if unit.in_melee:
            combat.leave_grid(battle, unit)
            for other in battle.regiments.values():
                if other.active and _hostile(unit, other):
                    _queue(battle, other.identifier, EVENT_ROUTED, source=unit.identifier)
        unit.braced = False
        _bower_step(battle, effect)
    elif BOWER_LIFT < e < BOWER_LIFT + BOWER_FLIGHT + 1:
        _place_centre(unit, effect.x, effect.y)  # the projectile's position of the previous step
        _bower_step(battle, effect)
    elif e == BOWER_LIFT + BOWER_FLIGHT + 1:
        _place_centre(unit, *effect.aim)
        table(battle).flying.discard(unit.identifier)
        _sync_lifted(battle, unit)
        effect.flying = False
        _finish(effect)


def _bower_step(battle: Battle, effect: Effect) -> None:
    r = effect.remaining
    sx, sy = effect.start
    dx, dy = effect.dest
    effect.x = dx + int((sx - dx) * r / effect.steps) + battle.rng.randrange(8)
    effect.y = dy + int((sy - dy) * r / effect.steps) + battle.rng.randrange(8)
    effect.remaining = max(0, r - 1)


def arch_clock(tick_count: int) -> int:
    """C2 3.3: the battle clock advances by one on every tick except segment-boundary ticks."""
    return tick_count - tick_count // combat.SEGMENT_TICKS


def _update_arch(battle: Battle, effect: Effect) -> None:
    """Sapphire Arch (C2 3): releases every unit in an arch at T+20 (placed at this arch's point plus its offset,
    killed without credit when its stamp is more than 900 clock ticks old), swallows at T+161 (every active unit
    with its centre within 48, except the caster's and stamped units, whose stamp is erased instead), ends at T+180."""
    effects = table(battle)
    if effect.elapsed == ARCH_RELEASE:
        now = arch_clock(battle.tick_count)
        for unit in list(battle.regiments.values()):
            if unit.identifier not in effects.in_arch or not unit.active:
                continue
            stamp, offset = effects.stamps.get(unit.identifier, (0, (0.0, 0.0)))
            _place_centre(unit, effect.aim[0] + offset[0], effect.aim[1] + offset[1])
            effects.in_arch.discard(unit.identifier)
            _sync_lifted(battle, unit)
            if now - stamp > ARCH_EXPIRY:
                slay(battle, unit, None, animation.DEATH_MISSILE, None)
    elif effect.elapsed == ARCH_SWALLOW:
        for unit in list(battle.regiments.values()):
            if not unit.active:
                continue
            if unit.identifier == effect.owner or unit.identifier in effects.stamps:
                effects.stamps.pop(unit.identifier, None)
                continue
            cx, cy = footprint_centre(unit)
            if _d(cx, cy, *effect.aim) <= ARCH_REACH:
                offset = (cx - effect.aim[0], cy - effect.aim[1])
                radius = int(unit.bounding_radius())
                _place_centre(unit, -radius, -radius)
                effects.in_arch.add(unit.identifier)
                _sync_lifted(battle, unit)
                effects.stamps[unit.identifier] = (arch_clock(battle.tick_count), offset)
    elif effect.elapsed >= LASTING:
        _end(battle, effect)


# ===== The Doomwheel (C3 5) =====

def doomwheel_volley(battle: Battle, unit: Regiment) -> None:
    """Three bolts at headings facing, facing + 128, facing + 384. Per bolt: D = D6 x D6 x D6 x 12; the nearest unit
    (by unit position, inclusive within D of the point D along the heading; any side, not the Doomwheel, hidden or
    leaving units) or a fallback 96 ahead with +-40 jitter (y drawn first); then the 1-in-6 failure roll (message
    2021 for the player army); a fired bolt is an innate Warp Lightning from the unit position."""
    rng = battle.rng
    facing = int(unit.direction) % 512
    for heading in (facing, (facing + 128) % 512, (facing + 384) % 512):
        reach = (rng.randrange(6) + 1) * (rng.randrange(6) + 1) * (rng.randrange(6) + 1) * 12
        qx = unit.x + math.floor(_sin(heading) * reach / 256)
        qy = unit.y + math.floor(_cos(heading) * reach / 256)
        found: Regiment | None = None
        best = 0
        for other in battle.regiments.values():
            if not other.active or other is unit or other.hidden or _leaving(battle, other):
                continue
            d = _d(other.x, other.y, qx, qy)
            if d <= reach and (found is None or d < best):
                found, best = other, d
        if found is not None:
            aim: tuple[float, float] = (found.x, found.y)
        else:
            jitter_y = rng.randrange(80) - 40
            jitter_x = rng.randrange(80) - 40
            aim = (unit.x + math.floor(_sin(heading) * 96 / 256) + jitter_x,
                   unit.y + math.floor(_cos(heading) * 96 / 256) + jitter_y)
        if rng.randrange(6) == 5:
            if unit.side == Side.PLAYER:
                _message(battle, unit, GMTXT_CAST_FAILED)
            continue
        launch(battle, WARP_LIGHTNING, unit, -1, *aim, innate=True)


# ===== Ending, cancelling and dispelling =====

def _end(battle: Battle, effect: Effect) -> None:
    """The end step (B 5.3, C1 6, C2 5); the effect and its area objects leave the list."""
    if effect.ended:
        return
    effects = table(battle)
    effects.remove(effect)
    _remove_areas(battle, effect)
    target = battle.regiments.get(effect.target) if effect.target is not None else None
    if effect.code == MADNESS and target is not None and effect.saved_side is not None:
        target.side = effect.saved_side
        state = battle.event_bus.unit_states.get(target.identifier)
        if state is not None:
            state.unit_flags2 &= ~MADDENED_SCRIPT_FLAG
        if target.active:
            _queue(battle, target.identifier, EVENT_MADNESS_ENDED)
    elif effect.code == ERE_WE_GO and target is not None:
        target.toughness -= 1
        target.initiative = effect.saved_initiative
    elif effect.code == CURSE and target is not None:
        target.speed_per_tick, target.initiative = effect.saved_speed, effect.saved_initiative
    elif effect.code == TANGLING_THORN:
        for unit in battle.regiments.values():
            if not unit.airborne and _centre_d(unit, *effect.aim) < THORN_RELEASE:
                unit.held = False
    elif effect.code == FLYING_BOWER and effect.owner in effects.flying:
        effects.flying.discard(effect.owner)  # C2 2.4: put down where it is now
        owner = battle.regiments.get(effect.owner)
        if owner is not None:
            _sync_lifted(battle, owner)


def cancel(battle: Battle, effect: Effect) -> None:
    """Immediate removal through the end step: no impact, projectile and area objects gone (A 1.4)."""
    if effect.code in BOLTS and effect.flying and not effect.ended and effect.tail < 0:
        _log_end(battle, effect, "cancelled", effect.x, effect.y, 0.0)
    _end(battle, effect)


def _position(battle: Battle, effect: Effect) -> tuple[float, float]:
    """B 5.1, C2 2.4: a projectile's current position, the aim point for every other effect. PROVISIONAL: during a
    Flying Bower's take-off its harmless projectile is taken to be at the caster's centre."""
    if effect.code == FLYING_BOWER and not effect.steps:
        owner = battle.regiments.get(effect.owner)
        return footprint_centre(owner) if owner is not None else effect.aim
    return (effect.x, effect.y) if effect.code in PROJECTILE_POSITION else effect.aim


def dispel_pass(battle: Battle, protected: Regiment, chance: int, source: Effect | None) -> bool:
    """One dispel pass around `protected` (B 5.1): for every eligible effect in launch order (not innate, not Dispel
    Magic, not undispellable, not owned by or aimed at the protected unit) a percentage roll first, then
    trunc(d) < 80 from its position; a dispelled effect is cancelled with message 2006. A Mork Save Uz pass that
    dispels anything clears its own entry's active state (B 5.3). True when anything was dispelled."""
    dispelled = False
    effects = table(battle)
    for effect in effects.effects():
        if effect.ended:
            continue  # cancelled earlier in this pass
        if (effect.innate or effect.code == DISPEL_MAGIC or effect.undispellable
                or effect.owner == protected.identifier or effect.target == protected.identifier):
            continue
        if not battle.rng.randrange(100) < chance:
            continue
        x, y = _position(battle, effect)
        if _d(x, y, protected.x, protected.y) < DISPEL_REACH:
            cancel(battle, effect)
            _message(battle, protected, GMTXT_DISPELLED)
            dispelled = True
    if dispelled and source is not None and source.code == MORK_SAVE_UZ:
        for effect in effects.effects():
            if effect.owner == source.owner and effect.code == MORK_SAVE_UZ:
                effect.counts_active = False
    return dispelled


def dispel_choice(battle: Battle, wizard: Regiment, sees: Callable[[Regiment, Regiment], bool]) -> bool:
    """The AI's Dispel rule beyond the pool (B 5.5): the entry not selected, no own active Dispel Magic, and the first
    active effect in launch order owned by a hostile unit and not a Dispel Magic has a visible owner that sees the
    wizard. Only that first effect is examined."""
    if dispel_selected(battle, wizard.identifier):
        return False
    effects = table(battle).effects()
    if any(effect.code == DISPEL_MAGIC and effect.owner == wizard.identifier for effect in effects):
        return False
    for effect in effects:
        owner = battle.regiments.get(effect.owner)
        if owner is None or effect.code == DISPEL_MAGIC or not _hostile(owner, wizard):
            continue
        return not owner.hidden and sees(owner, wizard)
    return False


# ===== The wind (B 7) =====

def wind(current: int, rng: random.Random) -> int:
    """Wind(cur): 0 -> R mod 8; 1-3 -> cur + R mod 4; >= 4 -> cur - 4 + R mod 8; then clamped to 1..8."""
    if current == 0:
        new = rng.randrange(8)
    elif current < 4:
        new = current + rng.randrange(4)
    else:
        new = current - 4 + rng.randrange(8)
    return max(1, min(magic.MAX_POWER, new))


def blow_wind(battle: Battle) -> None:
    """At the start of ticks 501, 1001, ... (tick_count 500, 1000, ...): the player pool, then the enemy pool.
    The reusable activated items are re-armed for both sides. The real-time clock under frame lag is not modelled."""
    if battle.tick_count <= 0 or battle.tick_count % WIND_TICKS:
        return
    power = battle.event_bus.power
    power.player = wind(power.player, battle.rng)
    for unit in battle.regiments.values():
        unit.used_items.difference_update({"ItemBannerOfWrath", "ItemGrudgeBringer"})
    power.enemy = wind(power.enemy, battle.rng)
