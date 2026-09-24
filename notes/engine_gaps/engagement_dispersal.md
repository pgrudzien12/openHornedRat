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
  side" (e.g. after `_advance_models`/the future catch-up walk moves it off a straight line in). Full
  derivation (direction bins, the offset table, the acceptance rule) below, under "Direction-indexed
  joiner candidate cells — full specification" — this was the piece task #54's implementer flagged as
  missing; it's no longer missing.
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

## Direction-indexed joiner candidate cells — full specification ✅

Answers the hand-off request on [#54](https://github.com/pgrudzien12/openHornedRat/issues/54): the
direction bins, the ordered offsets per bin, and the far/near rule. This is everything needed to replace
a runtime distance sort with the original's fixed table.

### Step 1 — the approach arc (8 bins)

Take the bearing **from the joining unit's position to the defender's footprint centre**, subtract the
**defender's facing**, and wrap into 0…511 (the 1/512-of-a-turn angle unit used throughout). Call it
`rel`. Note that `rel ≈ 256` means the joiner is **in front of** the defender (the defender is facing
it) and `rel ≈ 0` means it is **behind** the defender.

The front and rear cones are **not 45° wide**: their half-width `D` is the **defender's footprint
diagonal half-angle** — the angle to the corner of its collision box, so wider for a wide unit and
narrower for a deep one. The remaining sectors split at the quarter points.

| `rel` range | arc code | meaning |
|---|---|---|
| `256 − D … 256` | **0** | front arc |
| `256 … 256 + D` | **4** | front arc |
| `129 … 256 − D` | **6** | flank A, front half |
| `D … 129` | **2** | flank A, rear half |
| `0 … D` | **1** | rear arc |
| `512 − D … 512` | **5** | rear arc |
| `384 … 512 − D` | **3** | flank B, rear half |
| `256 + D … 384` | **7** | flank B, front half |

Cross-check for an implementation: these are the same eight codes that drive the flank/rear Leadership
test (section 7.8 of `game_rules.md`), which is required for codes **1, 2, 3, 5** — precisely the rear
arc and the rear half of each flank. If your arc function does not reproduce that, it is mis-oriented.

### Step 2 — fold to four, and compose with the defender's code

Drop bit 2 (`code & 3`), collapsing the eight arcs to four: **0 = front, 1 = rear, 2 = flank A,
3 = flank B**. Then:

```
dir = COMBINE[defender_direction_code][arc_code & 3]

COMBINE = [ [1, 0, 3, 2],     # defender code 0
            [0, 1, 2, 3],     # defender code 1
            [3, 2, 0, 1],     # defender code 2
            [2, 3, 1, 0] ]    # defender code 3
```

**A unit that owns a freshly created grid always has direction code 0**, assigned when the grid is
created. So for the ordinary case — one unit charging another that was not already fighting — only the
first row is ever used: approaching the **front** gives `dir 1`, the **rear** `dir 0`, **flank A**
`dir 3`, **flank B** `dir 2`. The other rows apply only in multi-unit fights, where a unit joins against
an opponent that is itself a joiner (or that inherited grid ownership) and so carries a non-zero code.
The joiner stores its resulting `dir` and keeps it for subsequent placements.

### Step 3 — the ordered candidate offsets

`dir` selects one row of four `(Δcolumn, Δrow)` offsets, applied to **the target model's grid cell** and
tried **strictly in the order given**:

| `dir` | 1st | 2nd | 3rd | 4th |
|---|---|---|---|---|
| **0** | `(0, +1)` | `(−1, 0)` | `(+1, 0)` | `(0, −1)` |
| **1** | `(0, −1)` | `(−1, 0)` | `(+1, 0)` | `(0, +1)` |
| **2** | `(+1, 0)` | `(0, +1)` | `(0, −1)` | `(−1, 0)` |
| **3** | `(−1, 0)` | `(0, +1)` | `(0, −1)` | `(+1, 0)` |

The shape of it is **the cell on the side you came from first, then the two perpendicular cells, then
the far side last**. But the perpendicular pair is **not mirrored per direction**: rows 0 and 1 always
try `(−1, 0)` before `(+1, 0)`, and rows 2 and 3 always try `(0, +1)` before `(0, −1)`, regardless of
which side the joiner actually approached from. That fixed bias is what makes wrap-around favour one
shoulder of the defender, and it has to be reproduced verbatim to match cell-for-cell.

Orientation sanity check: the defender's block is written onto the grid with its **front rank at the
lowest row index**, so `dir 1` (a frontal charge) tries `(0, −1)` first — the cell directly in front of
the defender's front rank — and `dir 0` (a rear charge) tries `(0, +1)`, directly behind the rear rank.

Each offset also carries a fixed id used when converting the chosen cell into a world target position:
**0 = `(0, −1)`, 1 = `(0, +1)`, 2 = `(−1, 0)`, 3 = `(+1, 0)`**. It selects the matching one of the four
per-direction world offset vectors stored on the grid record when the grid was created.

### Step 4 — candidate count and acceptance

- **Farther than 18 world units** between the joining model and its target: only the **first two**
  entries of the row are tried, in order.
- **18 or closer**: all **four** are tried, in order.
- A candidate is accepted when its cell is **inside the 17 × 17 grid** (both coordinates 0…16) **and
  empty**. The first acceptable candidate wins.
- If no candidate in the row is acceptable the placement **fails for this tick** — there is no fallback
  to another direction, no widening, and no distance-based re-sort. The model stays put and is retried
  on a later tick, or is queued as a reserve beside an already-placed comrade.
- The model's own current cell is vacated for the duration of the test, so it can never block itself.

## Open questions

Tracked as [epic #53](https://github.com/pgrudzien12/openHornedRat/issues/53) (tasks #54-#56). None
technical — fully specified above.

## Implementation notes

Suggested breakdown (three GitHub tasks):

1. **Direction-indexed joiner candidate cells** ([#54](https://github.com/pgrudzien12/openHornedRat/issues/54)):
   replace `_candidate_cells`'s runtime distance sort with the fixed offset table given in full above
   ("Direction-indexed joiner candidate cells — full specification": direction bins, the `COMBINE`
   composition table, the four ordered offsets per `dir`, and the acceptance rule) — no longer blocked
   on missing detail. Independent of the other two tasks; can land immediately.
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
