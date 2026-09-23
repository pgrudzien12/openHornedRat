# Gap: engagement asymmetry (why the charger disperses, the charged unit stands still)

**Symptom**: on contact, the real game's charger visibly loses formation cohesion and streams outward
around the defender's edge while the defender appears to freeze — an asymmetry, not two units settling
symmetrically into a shared fight. Most of this is already implemented in `whshr/battle_grid.py`
(apparently built from an earlier pass at the same underlying 5.7/5.8 spec), but three specific,
previously-unconfirmed details are missing.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Why the charger disperses and the
charged unit stands still" (under close combat / the battle grid), marked ✅.

- **The grid is anchored on the defender, not the charger.** `create()`/`_pick_owner` already do this:
  the grid owner is whichever regiment has no `attack_target` of its own, ties broken by identifier.
- **The defender's own formation is transcribed directly onto the grid** (`grid.seed(owner)`): each
  model's cell comes straight from its existing rank/file, offset to the grid centre. Since the grid's
  world-space anchor is the owner's own position/facing, a cell's world position coincides exactly with
  the model's own formation slot — nothing to walk to. `_sync_arrival` already reflects this (a
  defender model is `arrived` immediately, without moving).
- **The charger is the "joiner"**: it does not get the owner-pairing bit; `_pair_joiner` relocates its
  free models into cells taken from the *defender's* block outline, nearest-enemy-model first, with
  overflow becoming reserves placed on later ticks (already implemented, `battle_grid._pair_joiner`).
- **Missing #1 — candidate cells are a fixed per-direction table, not a runtime distance sort.** The
  note: "The joiner's candidate cells come from a small per-direction offset table selected by the
  attack direction, so where it wraps depends on which side it came in from." Current
  `_candidate_cells` instead sorts `_NEIGHBOURS`' four fixed offsets by literal Euclidean distance from
  the joining model's current position every call — not wrong-looking in the common case, but not the
  documented mechanism, and diverges once a model's actual position doesn't correspond to its "approach
  side" (e.g. after `_advance_models`/the future catch-up walk moves it off a straight line in).
- **Missing #2 — placement must force an immediate re-aim, and defender models must be skipped, not
  merely coincide.** The note: committing a placement "clears the model's 'at rest' flag and zeroes its
  step budget, which forces an immediate re-aim", and separately, "a model that is at rest is skipped
  outright while its unit is in melee, which is what holds the defender's models motionless: they are
  never given a new target". These are properties of the per-model catch-up walk (`current_speed`,
  distance budget/stale heading, an "at rest" flag) specified in "Models chase the unit, they are not
  carried by it" and tracked as epic #49/task #50 — **that state doesn't exist in the engine yet**, so
  today's defender stillness is coincidental (the grid cell and the formation slot happen to be the
  same point, recomputed fresh every tick) rather than the documented mechanism (an explicit "don't even
  look at this model" skip). Blocked on #50 landing.
- **Not new, but worth restating**: this mechanical stillness is a *separate* cause from the Braced flag
  (`notes/engine_gaps/model_movement.md`'s sibling epic is unrelated to this one) — a defender stands
  still here regardless of whether it braced first; Braced only governs what orders it may be *given*.

## Open questions

Tracked as [epic #53](https://github.com/pgrudzien12/openHornedRat/issues/53) (tasks #54-#56). None
technical — fully specified above.

## Implementation notes

Suggested breakdown (three GitHub tasks):

1. **Direction-indexed joiner candidate cells**: replace `_candidate_cells`'s runtime distance sort
   with a fixed offset table indexed by the attacker's discretized approach direction (relative to the
   defender's facing), matching "a small per-direction offset table selected by the attack direction".
   Independent of the other two tasks; can land immediately.
2. **Wire the catch-up walk into engagement placement** (blocked on #50): once the per-model `current_
   speed`/distance-budget/"at rest" state exists, `_place_next_to_enemy` must clear "at rest" and zero
   the distance budget on every fresh placement (forcing an immediate re-aim instead of a stale
   heading), and the catch-up walk must skip any model that is "at rest" while its unit is `in_melee`
   outright — replacing today's coincidental stillness (recomputing the same target every tick) with
   the documented mechanism.
3. **Verification**: tests confirming the asymmetry end-to-end against this specific subsection (not
   just the general 5.7/5.8 behaviour the existing `test_combat.py`/`test_battle_grid.py` tests already
   cover) — a defender never moves on contact regardless of tick count, a joiner's freshly-placed
   models re-aim immediately rather than sliding in on a stale heading once task 2 lands, and the
   direction-dependent wrap-around from task 1 (charging from different sides produces different cell
   assignment order).
