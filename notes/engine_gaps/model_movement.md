# Gap: model movement fidelity (per-model catch-up walk vs. the unit anchor)

**Symptom**: every model in a regiment walks straight to its formation slot at the same flat speed
(the unit's own moving-freely rate), capped so it never overshoots. A charging block does not
visibly stretch, does not concertina back together afterwards, has no ragged stagger at the start of
a charge, and its rearmost rank never visibly falls behind.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Models chase the unit, they are
not carried by it" (under "Formations"), marked ✅.

- **Two positions, one driven by the speed stat.** The unit's own reference point (the anchor: front-
  rank centre, what collision/engagement/charge distance are all keyed off) advances at
  `s_rlmv × k / 16` world units/tick. Each model's position is stored independently; the anchor's own
  movement never drags a model — it only moves the model's *target slot*, opening a gap every tick
  that a separate catch-up walk then closes.
- **The catch-up walk has no charge multiplier.** Per model, per tick: a pending start-delay freezes
  it; otherwise `target_speed = min(distance_to_slot, s_rlmv)` (uncapped while broken), and
  `current_speed` ramps toward that target by at most 1/tick (drops to it immediately if the target is
  lower) rather than snapping. `current_speed` is a counter converted to world units via a per-model
  step factor `F = (ranks − rank_index) × 8 + (stagger & 6) + 4`, world units/tick = `F × 2.4 / 256`.
- **The stagger value** is a small fixed per-model number (0–7), contributing 0/2/4/6 to `F`; it also
  sets the model's charge-start freeze length.
- **Charge-start freeze**: `(stagger & 7) + 1` = 1–8 ticks of no movement per model when a charge
  begins, staggered model by model, while the anchor is already moving at full charge speed.
- **Keep-station threshold**: a model holds its slot only while `F ≥ 6.67 × k`. The rearmost rank's
  `F` is always 12–18 regardless of unit depth, which is calibrated to exactly match a normal march
  (`k = 1.8`) but falls behind while charging (`k = 2.5`) — see the note's worked Empire-infantry
  table (M4 I3, 4 ranks: front rank tracks tightly, rear rank trails by ~40 world units over a full
  charge).
- **Stale heading**: a model's target slot is only recomputed when a per-model distance budget (reset
  to half the remaining distance at each recompute) runs out; between recomputes it walks a straight
  line on a stale heading. "Arrived" is within 3 world units of the slot.
- **No speed cap while broken**: fleeing models are not held to `s_rlmv`.

Current engine (`whshr/engine.py: Regiment._advance_models`) implements none of this: every model
walks toward `formation.place(...)`'s freshly computed slot at a single flat `step` (the regiment's own
`speed_per_tick`, same for every rank), settling within `SETTLE_EPSILON` (0.05, not the documented 3
units). No per-model stagger, no ramping, no freeze, no stale-heading budget, no broken-unit uncap.

The "two positions" architecture is not itself missing: `_advance_models` already recomputes the
target slot fresh from the anchor's *current* position every tick and compares it against the
previous absolute model position, so a gap already opens the instant the anchor moves — what's
missing is the speed/step formula and the settle/freeze/stagger details layered on top of it, not a
storage-model rewrite.

## Further known facts (added after the initial plan, see game_rules.md "Formation is what decides
all of this")

- **`s_rlmv` cancels out of `v_model/v_anchor`**: whether a model keeps station depends only on its
  rank index, its unit's rank count, its stagger value and the movement state — never its own speed
  stat. Rank count sets the whole speed gradient; frontage never enters it.
- **The rearmost rank is always `F` = 12–18, whatever the depth.** A deeper unit's back rank doesn't
  lag *worse* — the front ranks get *faster* instead (`F = 8 × ranks + 4 + stagger`), so depth widens
  the internal speed spread rather than worsening the worst case.
- **A one-rank formation trails uniformly** (every model is rank 0, `F` = 12–18) — the whole unit
  trails a charge, not just the back. Only arises for single-model units under rank clamping.
- **Monsters, war machines and wagons all inherit this through their own pseudo-formation layout**:
  2×2 monsters (`ranks`=2) get `F`=12–18 and trail their own charge; 3×3 ones (`ranks`=3) get
  `F`=20–26 and keep up; the Mole Machine's 5×8 layout puts its model at rank 2 of 8 (`F`=52–58,
  tracks almost exactly). War machine crew sit at the back ranks of the 3-/4-deep layout by design
  (machine at rank 0, `F`=28–34) so the crew always re-settle around the machine. Wagons (rank 0 and
  1 of a 4-deep layout, `F`=36–42 and 28–34) never stretch.
- **Turning halves the keep-up requirement** (`F ≥ 3.33 × k` while wheeling, since a wheel halves
  translation but not the models' own step length) and a halted turn stops translation altogether, so
  a charge that has to wheel onto its target arrives visibly tidier than one that runs straight in.
  This should fall out for free of task 1's formula *if* it measures the anchor's actual per-tick
  translation that tick rather than a flat `s_rlmv × k / 16` constant independent of turning state —
  worth a specific wheeling-charge test case in task 3, not a separate implementation task.

**Scope boundary**: `whshr/formation.py` only implements the plain block layout (infantry/cavalry/
archers/special/notype); its own docstring already states "War machine, monster and wagon layouts are
not modelled here." A correct per-model `rank_index` for monsters and war machines depends on those
pseudo-formation layouts existing first — a separate, currently untracked gap, not something task 1
below should silently guess at. Wagons are simple enough (a fixed 2-model, "rank 0 and rank 1 of a
4-deep layout" convention) to fold in directly. Task 1 and task 3 are scoped to the block layout (and
wagons); monster/war-machine catch-up-walk correctness is an explicit follow-up, blocked on that
missing layout work.

## Open questions

Tracked as [epic #49](https://github.com/pgrudzien12/openHornedRat/issues/49) (tasks #50-#52).

None — fully specified above.

## Implementation notes

Suggested breakdown (three GitHub tasks under the epic):

1. **Core catch-up-walk rewrite**: replace `_advance_models`'s flat per-tick step with the documented
   per-model state (`current_speed`, a fixed `stagger` value assigned at model creation/reseed) and
   formula (`F`, ramping, `target_speed = min(distance, s_rlmv)` uncapped while `regiment.routing`),
   the distance-budget/stale-heading slot recompute, and the 3-unit arrival threshold (replacing
   `SETTLE_EPSILON` for this purpose; `battle_grid.ARRIVAL_DISTANCE`'s separate melee-cell arrival
   check is unaffected). This is one coherent per-tick per-model update; splitting it further would
   leave the walk in an inconsistent partial state.
2. **Charge-start freeze**: a per-model freeze countdown of `(stagger & 7) + 1` ticks, set when a
   regiment's charge begins (`attack_target` freshly assigned, or the charge order path once
   closing/charging are distinguished — see `notes/engine_gaps/formation_movement.md` and the
   charge-reach gating in `notes/game_rules.md`'s "Charge"), consumed before a model's catch-up walk
   runs each tick. Builds on task 1's per-model stagger state.
3. **Verification against the documented worked example**: tests asserting the marching-speed parity
   (`rear-rank F × 2.4/256 == moving-freely anchor speed`, i.e. the rear rank exactly keeps pace when
   marching but not when charging), the ~40-world-unit rear-rank lag over a full infantry charge, and
   the post-charge concertina recovery; plus a visual check via the existing battle viewers
   (`whshr/frontend/battle_view.py`, `battle2d.py`) per this project's "verify visually" rule.
