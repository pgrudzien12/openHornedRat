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

from dataclasses import dataclass

STAND, IDLE, WALK, FIGHT, WEAPON_READY, DEAD, SHOOT = range(1, 8)


@dataclass
class DyingModel:
    """A model whose wounds have run out but which keeps playing its animation until it collapses
    (game_rules.md "Figure animation", staggered collapse); it no longer takes part in the fight."""

    x: float
    y: float
    model: object  # whshr.engine.ModelState
    ticks_left: int


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
    variants) -- instead of the single `group`. No decoded family uses this yet; it is a data addition.
    `locks_facing` freezes the drawn facing while the script plays (the corpse script).
    """

    group: str  # matches whshr.battlefield.ACTION_GROUPS
    sequence: tuple = ()
    loop: bool = True
    random_entry: int = 0
    random_choice: tuple | None = None
    run_ticks: int = 0
    hold_ticks: int = 0
    next_action: int | None = None
    variant_groups: tuple = ()
    variant_rule: str | None = None
    locks_facing: bool = False


# Standard infantry (notes/game_rules.md "Figure animation" table). Sprite groups per
# notes/animations.md's standard `32+8+32+32+8` unit sets: move, dead, attack, stand, shoot.
STANDARD_INFANTRY = {
    STAND: ActionScript("stand", sequence=(1,)),
    IDLE: ActionScript("stand", sequence=(0, 0, 0, 1, 1, 2, 2, 2, 3, 3)),
    WALK: ActionScript("move", sequence=(0, 0, 1, 1, 2, 2, 3, 3), random_entry=8),
    FIGHT: ActionScript("attack", sequence=(0, 0, 1, 2, 3, 3, 1, 1, 3, 0, 2, 2), random_entry=10),
    WEAPON_READY: ActionScript("attack", random_choice=(0, 2)),
    DEAD: ActionScript("dead", sequence=(0,), loop=False, locks_facing=True),
    SHOOT: ActionScript("shoot", sequence=(0, 1, 2, 3), random_entry=4, hold_ticks=2, next_action=STAND),
}

FAMILY_TABLES = {"standard_infantry": STANDARD_INFANTRY}
DEFAULT_FAMILY = "standard_infantry"


def family_table(family):
    """The 8-slot action table for `family`, or standard infantry's when `family` has none decoded yet."""
    return FAMILY_TABLES.get(family, FAMILY_TABLES[DEFAULT_FAMILY])


def script_group(script, stagger):
    """The sprite group `script` shows for a model with fixed stagger value `stagger` (mechanism 4)."""
    if script.variant_rule == "mod3":
        return script.variant_groups[stagger % 3]
    if script.variant_rule == "bit1":
        return script.variant_groups[(stagger >> 1) & 1]
    return script.group


def death_cry_index(stagger):
    """Which of the three death cries a model plays: chosen by the same stagger value, ``stagger % 3``."""
    return stagger % 3


def collapse_delay_ticks(stagger, in_melee, whole_unit_destroyed=False):
    """Ticks a dying model keeps playing its current animation before falling (mechanism 5).

    ``((stagger & 3) + 1) * 18`` (1.8-7.2 s) in melee, a quarter of that (rounded up, 0.5-1.8 s)
    outside it, and zero when the whole unit was destroyed at once. Special death kinds (instant
    collapse, dedicated death sprite sets) are not modelled: no data for them is decoded yet.
    """
    if whole_unit_destroyed:
        return 0
    delay = ((stagger & 3) + 1) * 18
    return delay if in_melee else (delay + 3) // 4


FULL_TURN = 512
MAX_SLEW = 32  # drawn facing turns at most 32/512 of a turn (one sprite direction) per tick


def slew_facing(current, target):
    """Turn the drawn facing `current` toward `target` (both 0-511) by at most `MAX_SLEW`."""
    if current is None:
        return target % FULL_TURN
    delta = (target - current) % FULL_TURN
    if delta > FULL_TURN // 2:
        delta -= FULL_TURN
    delta = max(-MAX_SLEW, min(MAX_SLEW, delta))
    return (current + delta) % FULL_TURN


def facing_follows_unit(action):
    """True when the drawn facing turns toward the unit's facing (stand, idle, weapon ready, shoot);
    otherwise (walk, fight) it turns toward the model's own heading or opponent."""
    return action in (STAND, IDLE, WEAPON_READY, SHOOT)


def _draw_entry(script, rng):
    if script.random_choice is not None:
        return rng.choice(script.random_choice)
    if script.random_entry:
        return rng.randrange(script.random_entry)
    return 0


def _phase_at(script, pc, entry):
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
    if pc < run:
        index = (entry + pc) % length if script.loop else min(entry + pc, length - 1)
    else:
        index = (entry + run - 1) % length if script.loop else length - 1
    return script.sequence[index]


def current(model, family=DEFAULT_FAMILY):
    """The sprite group and phase a model's already-stepped `action`/`action_pc` currently show."""
    script = family_table(family)[model.action]
    return script_group(script, model.stagger), _phase_at(script, model.action_pc, model.action_entry)


def one_shot_running(model, family=DEFAULT_FAMILY):
    """True while the model plays a one-shot script (one with a `next_action`) that has not finished."""
    script = family_table(family)[model.action]
    if script.next_action is None:
        return False
    return model.action_pc < (script.run_ticks or len(script.sequence)) + script.hold_ticks


def _enter(model, table, action, rng):
    model.action = action
    model.action_entry = _draw_entry(table[action], rng)
    model.action_pc = 0


def step(model, requested_action, rng, family=DEFAULT_FAMILY):
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
    if active.random_choice is None:
        model.action_pc += 1
    return script_group(active, model.stagger), phase
