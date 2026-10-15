"""Per-model figure animation: the seven-action stepper.

notes/game_rules.md, "Figure animation: actions, timing, and why the figures are never in step":
every model runs its own action program, one step per battle tick. Each creature family carries an
8-slot table of action scripts (slot 0 unused, actions 1-7 in use); frame selection stays
``group_base + phase * 8 + direction`` (notes/animations.md, whshr.battlefield.SpriteSheet).

37 creature families / 116 distinct scripts are documented; only standard infantry's is filled in
here. Any other family falls back to it (see `family_table`) until its own scripts are decoded
(notes/engine_gaps/figure_animation.md), so adding a family later is a data addition to
`FAMILY_TABLES`, not a change to the stepper below.
"""

import random
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engine import ModelState

STAND, IDLE, WALK, FIGHT, WEAPON_READY, DEAD, SHOOT = range(1, 8)

# Death kinds: the damage type of the killing wound (notes/game_rules.md "Figure animation", "Death kinds").
DEATH_ORDINARY, DEATH_FIRE, DEATH_MISSILE, DEATH_WARPFIRE = range(4)


@dataclass(frozen=True)
class Corpse:
    """A model that has died and lies where it fell, drawn with the dead frames of its own sprite set
    (notes/leader_figure_sprite.md 2: a leader's corpse uses the leader set)."""

    x: float
    y: float
    direction: int
    sprite: str | None = None  # the figure's troop sprite resource
    group: str | int = "dead"  # the dead script's group: a name, or a first-frame number (machine wrecks)


@dataclass
class DyingModel:
    """A model whose wounds have run out but which keeps playing its animation until it collapses
    (game_rules.md "Figure animation", staggered collapse); it no longer takes part in the fight."""

    x: float
    y: float
    model: "ModelState"
    ticks_left: int
    death_kind: int = 0  # DEATH_* of the killing wound; fire/warpfire kinds burn instead of leaving a corpse
    body: str = "infantry"  # BURN_SEQUENCES key, fixed by the regiment when the model dies
    burns: bool = False  # True when the model will play a burn sequence on collapse


@dataclass(frozen=True)
class ActionScript:
    """One creature family's script for one action id.

    `sequence` is the phase shown on each tick of one run through the script; `loop` wraps the index
    (True) or clamps to the sequence's last entry (False) once the run ends. `random_entry` is an
    exclusive upper bound for a program-counter offset drawn once, only on an action *change*
    (re-issuing the action a model already plays is a no-op). `random_choice`, when set, replaces
    `sequence` entirely: one value is drawn from it on the same action-change event and held as the
    phase forever (action 5's "phase 0 or 2, then held"). `run_ticks` (0 = ``len(sequence)``) is how
    many ticks the sequence plays before `hold_ticks` extra ticks hold its last phase; a script with
    `next_action` set auto-switches into that action once the run and hold finish (action 7's "4
    ticks, fire event, 2 more ticks, then back to action 1").

    Per-model variant selection (game_rules.md mechanism 4): a script with `variant_rule` set draws its
    group from `variant_groups` by the model's fixed stagger value -- rule "mod3" picks
    ``groups[stagger % 3]`` (three variants), rule "bit1" picks ``groups[(stagger >> 1) & 1]`` (two
    variants) -- instead of the single `group`. Peasants, Slaves and Wagons use it (below); when
    `variant_groups` holds ints they are first-frame numbers within the sprite file rather than names.
    `locks_facing` freezes the drawn facing while the script plays (the corpse script). War-machine scripts
    (notes/machine_figure_animation.md 0.3-0.4) set `faces_unit` (the figure always turns to the unit's facing, even
    while fighting or walking), `drops_requests` (a request arriving during the one-shot is dropped, not queued)
    and, on the dead script, `keeps_facing` (the wreck keeps the facing it had instead of a random one). A group may
    be a first-frame number in the sprite file instead of a name.
    """

    group: str | int  # a name from whshr.battlefield.ACTION_GROUPS, or a first-frame number
    sequence: tuple[int, ...] = ()
    loop: bool = True
    random_entry: int = 0
    random_choice: tuple[int, ...] | None = None
    run_ticks: int = 0
    hold_ticks: int = 0
    next_action: int | None = None
    variant_groups: tuple[int, ...] = ()
    variant_rule: str | None = None
    locks_facing: bool = False
    fire_at: int | None = None  # script step (counting the random entry skip) that posts the fire event
    # Steps (counting the skip) that make an extra fire post with no figure, then draw a fresh skip that is added
    # to the entry (the Volley Gun's first two puffs, notes/volley_gun_shot.md 3).
    extra_posts: tuple[int, ...] = ()
    skip_ahead: bool = False  # the random entry skips ahead in ONE fixed-length program (bigger skip = sooner end)
    faces_unit: bool = False
    drops_requests: bool = False
    keeps_facing: bool = False
    wreck_sprite: str | None = None  # the dead script switches to another sprite set's wreck (limbered mortar)
    faces_heading: bool = False  # the drawn facing follows the model's own heading/opponent even in idle or shoot


# Standard infantry (notes/game_rules.md "Figure animation" table). Sprite groups per
# notes/animations.md's standard `32+8+32+32+8` unit sets: move, dead, attack, stand, shoot.
ActionTable = dict[int, ActionScript]

STANDARD_INFANTRY: ActionTable = {
    STAND: ActionScript("stand", sequence=(1,)),
    IDLE: ActionScript("stand", sequence=(0, 0, 0, 1, 1, 2, 2, 2, 3, 3)),
    WALK: ActionScript("move", sequence=(0, 0, 1, 1, 2, 2, 3, 3), random_entry=8),
    FIGHT: ActionScript("attack", sequence=(0, 0, 1, 2, 3, 3, 1, 1, 3, 0, 2, 2), random_entry=10),
    WEAPON_READY: ActionScript("attack", random_choice=(0, 2)),
    DEAD: ActionScript("dead", sequence=(0,), loop=False, locks_facing=True),
    SHOOT: ActionScript("shoot", sequence=(0, 1, 2, 3), random_entry=4, hold_ticks=3, next_action=STAND,
                         fire_at=4, skip_ahead=True),
}

# Per-model costume families (game_rules.md mechanism 4). Groups are first-frame numbers in the sprite
# file. Peasants: three costumes V = stagger % 3, stand/idle/fight/weapon-ready group 120 + 32V, walk
# group 32V (random entry 0-7), dead group 96 + 8V. Slaves: three costumes, stand/fight/weapon-ready
# group 216 + 32V held on one frame, idle and walk share one 10-tick loop with no random entry (the
# group for that shared loop is not stated separately; the stand group is used -- PROVISIONAL), dead
# group 96 + 8V. Wagons: two looks B (group 32B; which model bit picks B is not documented, so bit 1 of
# the stagger value is used -- PROVISIONAL), one held frame that never animates except idle, an 8-tick
# loop 0,0,1,1,2,2,3,3 with no random entry; dead is one no-variant wreck group 64.
_MOD3: dict[str, Any] = dict(variant_rule="mod3")


def _peasant_group(base: int, step: int) -> tuple[int, ...]:
    return tuple(base + step * v for v in range(3))


PEASANTS: ActionTable = {
    STAND: ActionScript("stand", sequence=(1,), variant_groups=_peasant_group(120, 32), **_MOD3),
    IDLE: ActionScript("stand", sequence=(0, 0, 0, 1, 1, 2, 2, 2, 3, 3),
                       variant_groups=_peasant_group(120, 32), **_MOD3),
    WALK: ActionScript("move", sequence=(0, 0, 1, 1, 2, 2, 3, 3), random_entry=8,
                       variant_groups=_peasant_group(0, 32), **_MOD3),
    FIGHT: ActionScript("attack", sequence=(0, 0, 1, 2, 3, 3, 1, 1, 3, 0, 2, 2), random_entry=10,
                        variant_groups=_peasant_group(120, 32), **_MOD3),
    WEAPON_READY: ActionScript("attack", random_choice=(0, 2), variant_groups=_peasant_group(120, 32), **_MOD3),
    DEAD: ActionScript("dead", sequence=(0,), loop=False, locks_facing=True,
                       variant_groups=_peasant_group(96, 8), **_MOD3),
    SHOOT: ActionScript("stand", sequence=(0,), variant_groups=_peasant_group(120, 32), **_MOD3),
}

_SLAVE_HELD: dict[str, Any] = dict(sequence=(0,), variant_groups=_peasant_group(216, 32), **_MOD3)
_SLAVE_LOOP: dict[str, Any] = dict(sequence=(0, 0, 0, 1, 1, 2, 2, 2, 3, 3), variant_groups=_peasant_group(216, 32), **_MOD3)
SLAVES: ActionTable = {
    STAND: ActionScript("stand", **_SLAVE_HELD),
    IDLE: ActionScript("stand", **_SLAVE_LOOP),
    WALK: ActionScript("move", **_SLAVE_LOOP),
    FIGHT: ActionScript("attack", **_SLAVE_HELD),
    WEAPON_READY: ActionScript("attack", **_SLAVE_HELD),
    DEAD: ActionScript("dead", sequence=(0,), loop=False, locks_facing=True,
                       variant_groups=_peasant_group(96, 8), **_MOD3),
    SHOOT: ActionScript("stand", **_SLAVE_HELD),
}

_WAGON_HELD: dict[str, Any] = dict(sequence=(0,), variant_groups=(0, 32), variant_rule="bit1")
WAGONS: ActionTable = {
    STAND: ActionScript("stand", **_WAGON_HELD),
    IDLE: ActionScript("stand", sequence=(0, 0, 1, 1, 2, 2, 3, 3), variant_groups=(0, 32), variant_rule="bit1"),
    # Not the original (game_rules.md: one held frame): the wheels roll while driving, by the owner's request,
    # using the idle loop's phases.
    WALK: ActionScript("move", sequence=(0, 0, 1, 1, 2, 2, 3, 3), variant_groups=(0, 32), variant_rule="bit1"),
    FIGHT: ActionScript("attack", **_WAGON_HELD),
    WEAPON_READY: ActionScript("attack", **_WAGON_HELD),
    DEAD: ActionScript("dead", sequence=(0,), loop=False, locks_facing=True, variant_groups=(64, 64),
                       variant_rule="bit1"),
    SHOOT: ActionScript("stand", **_WAGON_HELD),
}

# Caravan and war-wagon carts have one look (a single 32-frame group), so both costume slots point at group 0.
# PROVISIONAL: they follow the wagon's scripts (wheels roll while idle and driving).
CARTS: ActionTable = {action: replace(script, variant_groups=(0, 0)) if script.variant_groups == (0, 32) else script
                      for action, script in WAGONS.items()}
CARTS[DEAD] = ActionScript("dead", sequence=(0,), loop=False, locks_facing=True)


# Doom Diver crew (notes/machine_figure_animation.md 2.6): 1/4/5 hold group 0 phase 0 facing the unit (no fighting
# pose); 2/3 loop 0,0,0,1,1,2,2,2,3,3 with no random entry; dead burns (kind 1/3, decided by the regiment) else the
# corpse group 32 with a random facing. Action 7 has no program (the figure keeps its frame): PROVISIONAL, shown as
# the held rest frame, since the crew never receives a shot request.
_CREW_HELD = ActionScript(0, sequence=(0,), faces_unit=True)
_CREW_LOOP = ActionScript(0, sequence=(0, 0, 0, 1, 1, 2, 2, 2, 3, 3), faces_heading=True)  # 2.6: faces its own heading
DOOM_DIVER_CREW: ActionTable = {
    STAND: _CREW_HELD, IDLE: _CREW_LOOP, WALK: _CREW_LOOP, FIGHT: _CREW_HELD, WEAPON_READY: _CREW_HELD,
    DEAD: ActionScript(32, sequence=(0,), loop=False, locks_facing=True),
    SHOOT: _CREW_HELD,
}

# Limbered guns (notes/machine_figure_animation.md 2.8). The limbered mortar: 1/4/5 hold group 0 phase 1; idle rolls
# the wheels with the 8-tick loop; dead switches to the Wagon set's wreck (group 64), like the Caravan. Walking
# rolls the wheels as well (the owner's request for all carts, see WAGONS); the report holds the frame.
_MRT_HELD = ActionScript(0, sequence=(1,))
_MRT_ROLL = ActionScript(0, sequence=(0, 0, 1, 1, 2, 2, 3, 3))
LIMBERED_MORTAR: ActionTable = {
    STAND: _MRT_HELD, IDLE: _MRT_ROLL, WALK: _MRT_ROLL, FIGHT: _MRT_HELD, WEAPON_READY: _MRT_HELD,
    DEAD: ActionScript(64, sequence=(0,), loop=False, locks_facing=True, wreck_sprite="Wagon"),
    SHOOT: _MRT_HELD,
}
# The Imperial / Great Cannon / Volley Gun limbers share one table: everything is the one held frame (a single
# 1-phase intact group), dead is group 8 held with the facing frozen. No shoot program.
_GUN_LIMBER_HELD = ActionScript(0, sequence=(0,))
LIMBERED_GUN: ActionTable = {
    **{action: _GUN_LIMBER_HELD for action in (STAND, IDLE, WALK, FIGHT, WEAPON_READY, SHOOT)},
    DEAD: ActionScript(8, sequence=(0,), loop=False, locks_facing=True, keeps_facing=True),
}


def _machine_table(intact: int, wreck: int, shoot: ActionScript) -> ActionTable:
    """A war-machine figure (notes/machine_figure_animation.md 1): actions 1-5 hold the intact group's phase 0
    facing the unit's facing, 6 is the wreck held with its facing kept, 7 the family's locked shot."""
    held = ActionScript(intact, sequence=(0,), faces_unit=True)
    return {STAND: held, IDLE: held, WALK: held, FIGHT: held, WEAPON_READY: held,
            DEAD: ActionScript(wreck, sequence=(0,), loop=False, locks_facing=True, keeps_facing=True),
            SHOOT: shoot}


def _machine_shot(group: int, sequence: tuple[int, ...], fire_at: int) -> ActionScript:
    """A machine's shot: random entry 0-3 skips into the lead-in of one fixed program, the fire event is its own
    step, then back to stand; requests during the shot are dropped (notes/machine_figure_animation.md 0.3, 2)."""
    return ActionScript(group, sequence=sequence, random_entry=4, next_action=STAND, fire_at=fire_at,
                        skip_ahead=True, faces_unit=True, drops_requests=True)


# notes/machine_figure_animation.md 2.1-2.4. Cannon and Great Cannon: intact frames 8-15, wreck 0-7, the gun
# never changes frame while shooting (the muzzle puff shows the shot); fire step on the 7th step.
GUN = _machine_table(8, 0, _machine_shot(8, (0,) * 11, fire_at=6))
# Volley Gun (notes/volley_gun_shot.md 3): the same frames; puffs at steps 6 and 11 are extra posts, each drawing a
# fresh 0-3 skip, and the third puff at step 16 is the ordinary fire step; 4 intact steps, then stand. Puffs come
# 7-r0, +5-r1, +5-r2 ticks apart, the whole shot taking 12 to 21 ticks.
VOLLEY = _machine_table(8, 0, ActionScript(8, sequence=(0,) * 21, random_entry=4, next_action=STAND, fire_at=16,
                                           extra_posts=(6, 11), skip_ahead=True, faces_unit=True,
                                           drops_requests=True))
# Rock Lobber and Doom Diver catapult: the "fire" group's phase 0 is the rest frame; the arm swings only in the
# shot, after the fire step: 0,0,0,0,fire,1,1,2,3,0.
THROWER = _machine_table(0, 32, _machine_shot(0, (0, 0, 0, 0, 0, 1, 1, 2, 3, 0), fire_at=4))
# Mortar: intact frames 40-47, wreck 0-7, the firing smoke 8-39. Addressed from group 8, so 40 is phase 4.
MORTAR = _machine_table(40, 0, _machine_shot(8, (4, 4, 4, 4, 0, 1, 1, 2, 3, 3, 4), fire_at=6))

# Gyrocopter (notes/machine_figure_animation.md 2.9, airborne_units.md A3.2): one flying figure, no random entry, and
# its shoot has no fire step. The take-off and landing laps and the altitude steps are flight_rules'/FlightState's
# (they depend on whether the craft is flying); these are the loops that follow them. Actions 2, 3 and 7 loop the
# fast rotor, 1, 4 and 5 the slow one; the wreck (group 32) is held.
_GYRO_FAST = ActionScript("move", sequence=(0, 1, 2, 3, 1, 2))
_GYRO_SLOW = ActionScript("move", sequence=(0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 1, 1, 1, 2, 2))
GYROCOPTER: ActionTable = {
    STAND: _GYRO_SLOW, IDLE: _GYRO_FAST, WALK: _GYRO_FAST, FIGHT: _GYRO_SLOW, WEAPON_READY: _GYRO_SLOW,
    DEAD: ActionScript(32, sequence=(0,), loop=False, locks_facing=True), SHOOT: _GYRO_FAST,
}

# Doomwheel (notes/machine_figure_animation.md 2.5): group 8 (frames 8-39) is the rolling wheel. Stand and weapon
# ready hold phase 0 facing the unit; idle, walk, fight and shoot share one flat 4-tick loop with no random entry,
# facing the figure's own heading. No fire step: the bolts are not timed by the animation.
_DWHEEL_ROLL = ActionScript(8, sequence=(0, 1, 2, 3), faces_heading=True)
DOOMWHEEL: ActionTable = {
    STAND: ActionScript(8, sequence=(0,), faces_unit=True),
    IDLE: _DWHEEL_ROLL, WALK: _DWHEEL_ROLL, FIGHT: _DWHEEL_ROLL, SHOOT: _DWHEEL_ROLL,
    WEAPON_READY: ActionScript(8, sequence=(0,), faces_unit=True),
    DEAD: ActionScript(0, sequence=(0,), loop=False, locks_facing=True),
}

# Mesh pose numbers, not sprite phases (notes/bf014_dragon_rendering.md §3).
DRAGON_FIGHT = tuple(pose for pose in (1, 2, 1, 3, 1, 4, 1, 2, 1, 4, 1, 3) for _ in range(2))
MESH_DRAGON: ActionTable = {
    action: ActionScript("mesh", sequence=(1,))
    for action in (STAND, IDLE, WALK, WEAPON_READY, DEAD)
}
MESH_DRAGON[FIGHT] = ActionScript("mesh", sequence=DRAGON_FIGHT, random_entry=16)
MESH_DRAGON[SHOOT] = ActionScript("mesh", sequence=(1,) * 10, random_entry=4,
                                 next_action=STAND, skip_ahead=True, drops_requests=True)


def request_mesh_breath(model: "ModelState", sector: int, rng: random.Random) -> None:
    """An accepted weapon shot requests a one-shot; an already frozen breath is not restarted (§3)."""
    if not one_shot_running(model, "mesh_dragon"):
        model.breath_sector = sector
        _enter(model, MESH_DRAGON, SHOOT, rng)
        model.pending_action = None


def mesh_dragon_pose(model: "ModelState") -> int:
    """Read the current discrete pose without advancing simulation or drawing randomness."""
    if model.action == SHOOT and one_shot_running(model, "mesh_dragon"):
        return (3, 2, 4, 2)[model.breath_sector]
    if model.action == SHOOT:
        return 1
    script = MESH_DRAGON[model.action]
    # step() has advanced the counter past the update it just displayed; preserve both updates
    # of each authored fight pose, including the first pair after an action change.
    return _phase_at(script, max(0, model.action_pc - 1), model.action_entry)


FAMILY_TABLES: dict[str, ActionTable] = {"standard_infantry": STANDARD_INFANTRY, "peasants": PEASANTS, "slaves": SLAVES,
                 "mesh_dragon": MESH_DRAGON, "wagons": WAGONS, "carts": CARTS, "gun": GUN, "volley": VOLLEY,
                 "thrower": THROWER, "mortar": MORTAR, "gyrocopter": GYROCOPTER,
                 "doom_diver_crew": DOOM_DIVER_CREW, "limbered_mortar": LIMBERED_MORTAR,
                 "limbered_gun": LIMBERED_GUN, "doomwheel": DOOMWHEEL}
# Script sprite resource names (casefolded) that select a decoded family; anything else is standard.
SPRITE_FAMILIES = {"meshdragon": "mesh_dragon", "peasant": "peasants", "peasants": "peasants",
                   "ratslave": "slaves", "slave": "slaves",
                   "slaves": "slaves", "wagon": "wagons", "caravan": "carts", "mrtwagon": "limbered_mortar",
                   "mrtwag": "limbered_mortar", "impcwagon": "limbered_gun", "impcwag": "limbered_gun",
                   "grtcwagon": "limbered_gun", "grtcwag": "limbered_gun", "vollywagon": "limbered_gun",
                   "vollywag": "limbered_gun", "doomdiver": "doom_diver_crew", "doomdivr": "doom_diver_crew", "packpony": "standard_infantry",
                   # War-machine figures, by the leader block's machine set (notes/machine_figure_animation.md 3).
                   "cannon": "gun", "impcanon": "gun", "grtcannon": "gun", "grtcanon": "gun", "volleygun": "volley",
                   "voleygun": "volley", "rocklobber": "thrower", "rocklob": "thrower", "doomdvrcatapult": "thrower",
                   "ddcatplt": "thrower", "mortar": "mortar",
                   "gyrocopt": "gyrocopter", "gyrocopter": "gyrocopter",
                   "doomwheel": "doomwheel", "dwheel": "doomwheel"}
WAGON_CLASS = 7  # s_race class RollingStock
DEFAULT_FAMILY = "standard_infantry"


def family_table(family: str | None) -> ActionTable:
    """The 8-slot action table for `family`, or standard infantry's when `family` has none decoded yet."""
    return FAMILY_TABLES.get(family or DEFAULT_FAMILY, FAMILY_TABLES[DEFAULT_FAMILY])


def family_for(sprite: str | None, unit_class: int | None = None) -> str:
    """The creature family a regiment's models animate with: chosen by its script sprite resource
    (peasants, slaves, wagons), RollingStock class as a wagon fallback, else standard infantry."""
    family = SPRITE_FAMILIES.get((sprite or "").casefold())
    if family is None and unit_class == WAGON_CLASS:
        family = "wagons"
    return family or DEFAULT_FAMILY


def corpse_of(regiment: Any, model: "ModelState", x: float, y: float, rng: random.Random) -> Corpse:
    """The corpse a collapsing figure leaves: its dead script's group, and a random facing, except a war-machine
    wreck, which keeps the facing it had (notes/machine_figure_animation.md 0.4). `regiment` is the figure's
    whshr.engine.Regiment."""
    script = family_table(regiment.model_family(model))[DEAD]
    if script.keeps_facing:
        direction = int(regiment.direction if model.drawn_facing is None else model.drawn_facing)
    else:
        direction = rng.randrange(FULL_TURN)
    group = script.group if script.variant_rule is None else script_group(script, model.stagger)
    return Corpse(x, y, direction, script.wreck_sprite or regiment.model_sprite(model), group)


def script_group(script: ActionScript, stagger: int) -> str | int:
    """The sprite group `script` shows for a model with fixed stagger value `stagger` (mechanism 4)."""
    if script.variant_rule == "mod3":
        return script.variant_groups[stagger % 3]
    if script.variant_rule == "bit1":
        return script.variant_groups[(stagger >> 1) & 1]
    return script.group


def death_cry_index(stagger: int) -> int:
    """Which of the three death cries a model plays: chosen by the same stagger value, ``stagger % 3``."""
    return stagger % 3


def collapse_delay_ticks(stagger: int, in_melee: bool, death_kind: int = 0) -> int:
    """Ticks a dying model keeps playing its current animation before falling (mechanism 5).

    ``((stagger & 3) + 1) * 18`` (18/36/54/72 ticks) when the model's unit is in close combat;
    otherwise ``(d >> 2) + 1`` (5/10/14/19 ticks). Death kinds 1-3 (fire, missile/slain outright,
    warpfire) always collapse in exactly one tick. There is no zero-delay case: only a destroyed
    building falls with no delay, and the engine has no buildings, so a regiment wiped out in one hit
    gives every model its normal delay. `death_kind` 0 is an ordinary wound; kind plumbing is #101.
    """
    if death_kind in (1, 2, 3):
        return 1
    delay = ((stagger & 3) + 1) * 18
    return delay if in_melee else (delay >> 2) + 1


@dataclass(frozen=True)
class BurnSequence:
    """One body class's burn data (game_rules.md "Figure animation", burn table). The battle-effects
    sprite set is addressed by first-frame number: burning frame = ``orange_or_green + phase`` (burning
    groups are not direction-indexed), charred corpse frame = ``corpse + direction`` (8 directions)."""

    orange: int
    green: int
    phases: int  # phases cycled through while burning
    lead_in: int  # ticks of lead-in the random start offset skips into
    corpse: int


# game_rules.md burn table: infantry and everything else / cavalry (and sheep) / monster. The burn always
# runs `lead_in - r + 40` ticks for a random start offset r in [0, lead_in): five laps of 8 phases or
# ten laps of 4 after the lead-in.
BURN_SEQUENCES: dict[str, BurnSequence] = {
    "infantry": BurnSequence(orange=0, green=16, phases=8, lead_in=16, corpse=32),
    "cavalry": BurnSequence(orange=8, green=24, phases=4, lead_in=8, corpse=40),
    "monster": BurnSequence(orange=12, green=28, phases=4, lead_in=8, corpse=48),
}
BURN_LAP_TICKS = 40  # the full laps that follow the lead-in

# Body-class mapping. s_race classes: 2 Cavalry, 4 Artillery, 6 Monster, 7 RollingStock
# (notes/game_rules.md s_race table). Everything the notes name by unit rather than class is matched
# on the casefolded script sprite resource. PROVISIONAL: the notes list the units but not their sprite
# resource names; these are the sprite file base names (notes/animations.md) plus the obvious long forms.
CAVALRY_CLASS, ARTILLERY_CLASS, MONSTER_CLASS = 2, 4, 6
CAVALRY_SPRITES = frozenset({"sheep"})  # PROVISIONAL: mounts with class Infantry in the data, if any, are not covered
NEVER_BURN_SPRITES = frozenset({  # PROVISIONAL names: wagons, pack ponies, fanatics, mortars, big monsters
    "wagon", "caravan", "mrtwag", "impcwag", "grtcwag", "vollywag", "mrtwagon", "impcwagon", "grtcwagon", "vollywagon", "packpony", "fanatic", "mortar",
    "wyvern", "dragon", "meshdragon", "giant", "gyrocopt", "gyrocopter", "dwheel", "doomwheel"})
BURN_EXCEPTION_SPRITES = frozenset({"warpfire", "doomdivr", "doomdiver"})  # war machines that do burn


def body_class(unit_class: int | None, sprite: str | None = None) -> str:
    """The burn body class of a regiment: "monster" (class Monster), "cavalry" (class Cavalry, sheep) or
    "infantry" (everything else)."""
    if unit_class == MONSTER_CLASS:
        return "monster"
    if unit_class == CAVALRY_CLASS or (sprite or "").casefold() in CAVALRY_SPRITES:
        return "cavalry"
    return "infantry"


def burns_on_death(death_kind: int, unit_class: int | None, sprite: str | None = None) -> bool:
    """True when a model killed with `death_kind` plays a burn sequence: only kinds 1 and 3, and never
    for wagons, pack ponies, fanatics, mortars, war machines (except the Warpfire Thrower and Doom
    Diver), Wyvern, Dragon, Giant, Gyrocopter or Doomwheel, whose dead script ignores the kind."""
    if death_kind not in (DEATH_FIRE, DEATH_WARPFIRE):
        return False
    name = (sprite or "").casefold()
    if name in BURN_EXCEPTION_SPRITES:
        return True
    if name in NEVER_BURN_SPRITES or unit_class in (WAGON_CLASS, ARTILLERY_CLASS):
        return False
    return True


@dataclass
class BurningModel:
    """A model that has left its unit's roster and burns as a free figure on the battle-effects set."""

    x: float
    y: float
    death_kind: int
    body: str
    start: int  # random start offset r into the lead-in
    age: int = 0  # ticks burned so far


def burn_start(body: str, rng: random.Random) -> int:
    """Draw the random start offset r in [0, lead_in) into the lead-in."""
    return rng.randrange(BURN_SEQUENCES[body].lead_in)


def burn_length(body: str, start: int) -> int:
    """Total ticks of a burn that starts `start` ticks into its lead-in: ``lead_in - r + 40``
    (41-56 ticks for infantry, 41-48 for cavalry and monsters)."""
    return BURN_SEQUENCES[body].lead_in - start + BURN_LAP_TICKS


def burning_frame(burning: BurningModel) -> int:
    """Battle-effects frame number a burning model shows now: the orange (kind 1) or green (kind 3)
    group's first frame plus the cycling phase ``(r + age) % phases``."""
    sequence = BURN_SEQUENCES[burning.body]
    base = sequence.green if burning.death_kind == DEATH_WARPFIRE else sequence.orange
    return base + (burning.start + burning.age) % sequence.phases


def burn_finished(burning: BurningModel) -> bool:
    return burning.age >= burn_length(burning.body, burning.start)


def charred_frame(body: str, direction: int) -> int:
    """Battle-effects frame of a charred corpse facing sprite direction `direction` (0-7)."""
    return BURN_SEQUENCES[body].corpse + direction % 8


FULL_TURN = 512
MAX_SLEW = 32  # drawn facing turns at most 32/512 of a turn (one sprite direction) per tick


def slew_facing(current: float | None, target: float) -> float:
    """Turn the drawn facing `current` toward `target` (both 0-511) by at most `MAX_SLEW`."""
    if current is None:
        return target % FULL_TURN
    delta = (target - current) % FULL_TURN
    if delta > FULL_TURN // 2:
        delta -= FULL_TURN
    delta = max(-MAX_SLEW, min(MAX_SLEW, delta))
    return (current + delta) % FULL_TURN


def facing_follows_unit(action: int) -> bool:
    """True when the drawn facing turns toward the unit's facing (stand, idle, weapon ready, shoot);
    otherwise (walk, fight) it turns toward the model's own heading or opponent."""
    return action in (STAND, IDLE, WEAPON_READY, SHOOT)


def _draw_entry(script: ActionScript, rng: random.Random) -> int:
    if script.random_choice is not None:
        return rng.choice(script.random_choice)
    if script.random_entry:
        return rng.randrange(script.random_entry)
    return 0


def _phase_at(script: ActionScript, pc: int, entry: int) -> int:
    """The phase shown `pc` ticks into a run that started at random offset `entry`.

    `entry` only rotates which phase is shown first; it does not shorten a finite run (`pc` counts
    ticks elapsed since the action was entered, always starting at 0). Mirrors mechanism 1 of
    notes/game_rules.md "Figure animation": a model that enters a loop skips `entry` steps ahead
    before its first displayed frame, then advances normally from there. A script with no
    `next_action` (`stand`/`idle`/`walk`/`fight`/`dead`) simply keeps wrapping (or, if `loop` is
    False, holding its last phase) forever; `run_ticks`/`hold_ticks` only bound a one-shot script
    that has a `next_action` to auto-switch into (`shoot`).
    """
    if script.random_choice is not None:
        return entry
    length = len(script.sequence)
    if script.next_action is None:
        index = (entry + pc) % length if script.loop else min(entry + pc, length - 1)
        return script.sequence[index]
    run = script.run_ticks or length
    if script.skip_ahead:
        return script.sequence[min(entry + pc, length - 1)]
    if pc < run:
        index = (entry + pc) % length if script.loop else min(entry + pc, length - 1)
    else:
        index = (entry + run - 1) % length if script.loop else length - 1
    return script.sequence[index]


def current(model: "ModelState", family: str = DEFAULT_FAMILY) -> tuple[str | int, int]:
    """The sprite group and phase a model's already-stepped `action`/`action_pc` currently show."""
    script = family_table(family)[model.action]
    return script_group(script, model.stagger), _phase_at(script, model.action_pc, model.action_entry)


def one_shot_running(model: "ModelState", family: str = DEFAULT_FAMILY) -> bool:
    """True while the model plays a one-shot script (one with a `next_action`) that has not finished."""
    script = family_table(family)[model.action]
    if script.next_action is None:
        return False
    total = (script.run_ticks or len(script.sequence)) + script.hold_ticks
    if script.skip_ahead:
        # One fixed-length program: the entry skip is spent up front, so a bigger skip ends sooner
        # (skip 0 plays 7 ticks, skip 3 plays 4; game_rules.md "Figure animation").
        return model.action_pc + model.action_entry < total
    return model.action_pc < total


def _enter(model: "ModelState", table: ActionTable, action: int, rng: random.Random) -> None:
    model.action = action
    model.action_entry = _draw_entry(table[action], rng)
    model.action_pc = 0


def step(model: "ModelState", requested_action: int, rng: random.Random,
         family: str = DEFAULT_FAMILY) -> tuple[str | int, int]:
    """Advance one model's action program by one battle tick; returns `current(model, family)`.

    `model` carries `action`/`action_pc`/`action_entry`/`pending_action` (whshr.engine.ModelState).
    Re-issuing the action id the model already plays is a no-op (the random offset persists until the
    id actually changes). A different request while a one-shot script is running cannot interrupt it:
    it is queued in `pending_action` (the latest request wins) and applied when the one-shot finishes,
    in place of the script's own `next_action`. A genuine change draws a fresh random entry/choice and
    restarts the program counter at 0.
    """
    table = family_table(family)
    if requested_action == model.action:
        model.pending_action = None
    elif one_shot_running(model, family):
        if not table[model.action].drops_requests:
            model.pending_action = requested_action
    else:
        _enter(model, table, requested_action, rng)
        model.pending_action = None
    active = table[model.action]
    if not one_shot_running(model, family) and active.next_action is not None:
        target = model.pending_action if model.pending_action is not None else active.next_action
        model.pending_action = None
        _enter(model, table, target, rng)
        active = table[model.action]
    phase = _phase_at(active, model.action_pc, model.action_entry)
    # The fire event is posted by the script itself, four steps into the shoot program counting the
    # random entry skip (game_rules.md "Figure animation"), so models entering at 0-3 reach it on
    # different ticks. `fire_event` is true for exactly that one tick.
    model.fire_event = active.fire_at is not None and model.action_pc + model.action_entry == active.fire_at
    model.extra_post = model.action_pc + model.action_entry in active.extra_posts
    if model.extra_post:
        model.action_entry += rng.randrange(active.random_entry)  # drawn on the puff tick, after the post
    if active.random_choice is None:
        model.action_pc += 1
    return script_group(active, model.stagger), phase
