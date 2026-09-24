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
    """

    group: str  # matches whshr.battlefield.ACTION_GROUPS
    sequence: tuple = ()
    loop: bool = True
    random_entry: int = 0
    random_choice: tuple | None = None
    run_ticks: int = 0
    hold_ticks: int = 0
    next_action: int | None = None


# Standard infantry (notes/game_rules.md "Figure animation" table). Sprite groups per
# notes/animations.md's standard `32+8+32+32+8` unit sets: move, dead, attack, stand, shoot.
STANDARD_INFANTRY = {
    STAND: ActionScript("stand", sequence=(1,)),
    IDLE: ActionScript("stand", sequence=(0, 0, 0, 1, 1, 2, 2, 2, 3, 3)),
    WALK: ActionScript("move", sequence=(0, 0, 1, 1, 2, 2, 3, 3), random_entry=8),
    FIGHT: ActionScript("attack", sequence=(0, 0, 1, 2, 3, 3, 1, 1, 3, 0, 2, 2), random_entry=10),
    WEAPON_READY: ActionScript("attack", random_choice=(0, 2)),
    DEAD: ActionScript("dead", sequence=(0,), loop=False),
    SHOOT: ActionScript("shoot", sequence=(0, 1, 2, 3), random_entry=4, hold_ticks=2, next_action=STAND),
}

FAMILY_TABLES = {"standard_infantry": STANDARD_INFANTRY}
DEFAULT_FAMILY = "standard_infantry"


def family_table(family):
    """The 8-slot action table for `family`, or standard infantry's when `family` has none decoded yet."""
    return FAMILY_TABLES.get(family, FAMILY_TABLES[DEFAULT_FAMILY])


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
    return script.group, _phase_at(script, model.action_pc, model.action_entry)


def step(model, requested_action, rng, family=DEFAULT_FAMILY):
    """Advance one model's action program by one battle tick; returns `current(model, family)`.

    `model` carries `action`/`action_pc`/`action_entry` (whshr.engine.ModelState). Re-issuing the
    action id the model already plays is a no-op; a genuine change -- including a one-shot script's
    own auto-transition into `next_action` once it finishes -- draws a fresh random entry/choice and
    restarts the program counter at 0.
    """
    table = family_table(family)
    if requested_action != model.action:
        model.action = requested_action
        model.action_entry = _draw_entry(table[requested_action], rng)
        model.action_pc = 0
    active = table[model.action]
    run = active.run_ticks or len(active.sequence)
    if active.next_action is not None and model.action_pc >= run + active.hold_ticks:
        model.action = active.next_action
        active = table[model.action]
        model.action_entry = _draw_entry(active, rng)
        model.action_pc = 0
    phase = _phase_at(active, model.action_pc, model.action_entry)
    if active.random_choice is None:
        model.action_pc += 1
    return active.group, phase
