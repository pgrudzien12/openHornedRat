# Gap: formation & movement fidelity (turning, reversing)

**Symptom**: units turn and reverse abruptly instead of wheeling — they look like they're snapping to
face their destination every tick rather than swinging around like a rank-and-file block. Wide
formations should turn much slower than deep ones and this has no effect at all today.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Real time and movement" and
"Turning, wheeling and reversing" (marked ✅). The current engine (`whshr/engine.py: Battle._turn_to`/
`_advance_toward`) doesn't implement any of the gradual-turn mechanism yet — facing is set straight to
the bearing to the target every tick.

**The per-tick turn step and its formula:**

```
step  = s_rlmv × (144 − s²) / 2^(16 − shift)      units of 1/512 turn
s     = frontage + ranks − min(frontage, ranks) / 2
shift = 9 charge re-aim · 8 halted turn / turn order · 7 wheel · 6 closing redirect
```

- Facing is a fixed-point value whose integer part is 0…511 (1/512 of a turn); the turn always goes
  **the shorter way round** (decided once at turn setup, recorded as a direction flag the step reads
  every tick), and it **ends once ≤10/512 (≈7°) of the required turn remains**.
- **Wide units turn dramatically slower** — the `(144 − s²)` term. Worked example (20 models,
  `s_rlmv` 11): a 5×4 deep column does a 90° turn in ~3.1s and a full reverse in ~6.2s; a 10×2 wide
  line takes ~13s and ~26s for the same turns — over a full game turn just to reverse. 10 cavalry
  (`s_rlmv` 18, 5×2) turn a 90° in ~1.7s. 🟡 For `s ≥ 12` the term goes to zero/negative and the turn
  would never finish; no formation in the campaign data reaches it (max observed `s` = 10).
- **Which `shift` applies is a state, not an angle threshold read in isolation** — though in practice
  the four states line up with angle ranges too (also documented in "Real time and movement"): a
  required turn **>45°** halts and turns on the spot (no translation that tick — halted-turn/turn-order/
  charge-re-aim/closing-redirect all zero translation), **7.7°–45°** wheels while moving at **half**
  speed, **<7.7°** is absorbed instantly. A charge re-aims every segment and only wheels above 22.5°.
- **At the moment a move order is issued** (not every tick) a required turn of 68.2°–135° snaps
  instantly 90°, and >135° snaps instantly 180° — the only place the original snaps, and only once per
  order; the remainder is then wheeled normally. This is a *separate* mechanism from the per-tick
  gradual turn above ("Real time and movement" calls out these as two entirely different paths).

**What the formation does, every tick that actually rotates the block:**

- The reference point ("anchor") is displaced by the rotation applied to the half-frontage vector
  `6 × (frontage − 1)`, holding the **inner front corner** still (a true wheel, not a spin about the
  anchor) — uniformly, for every kind of gradual turn, not only wheels. A frontage of 1 inverts the
  side. (In-place halted turns pivot about the **block centre** instead — an about-face shifts the
  anchor by `(ranks − 1) × 12` backwards along the old facing; a 90° order-issue snap moves it to the
  new front-rank centre and swaps ranks/frontage. `whshr/engine.py: Battle._turn_to` already calls
  `formation.turn_pivot_shift` for this — the pivot math exists.)
- Translation speed for that tick: a wheel keeps moving at **half speed**; every other kind of turn —
  halted turn, turn order, charge re-aim, closing redirect — **sets speed to zero**. Only a wheel turns
  and travels at once.
- Every model's slot is recomputed from the new facing (`rotate(12 × column − 6 × (frontage − 1), −12 ×
  rank)`; short ranks offset by a further half spacing).
- A re-form is queued; a turn order ends by halting and re-forming to the script's rank count.

**What the individual figures do**: never rotated into place. The slot lattice rotates under them, and
every model's stored position is counter-shifted by exactly the reference point's displacement (no
teleporting) — it then walks to its new slot under the ordinary rank-dependent catch-up walk of
"Models chase the unit, they are not carried by it" (epic #49/task #50: front ranks fastest, rear rank
slowest, each ramping up by one speed unit per tick). **This turning gap therefore has a real
dependency on #50** for the figures to look right while turning, even though the anchor-level
turn-rate/pivot mechanism itself does not.

**Differences by formation** (previously untracked — new):

- **Blocks** (infantry, cavalry, archers, wizards, special) get all of the above; rate and pivot both
  scale with frontage and depth.
- **Single-model units (monsters) turn on the spot with none of the pivot/slot/speed-penalty
  machinery** — the whole block guarded on "more than one model" is skipped entirely: no
  reference-point displacement, no slot recomputation, and **no speed penalty at all** (translates at
  full speed while turning). Their pseudo-formation `s` is small (3 for 2×2, 5 for 3×3), so they also
  turn very fast — monsters are deliberately the most agile things on the field.
- **Units currently re-forming** are skipped by the same guard (don't additionally drag the reference
  point around mid-reform).
- **Wagons** snap facing to **45° steps** instead of turning smoothly (on top of their existing layout
  restriction).
- **War machines** have a small `s` (≈4–5, quick turn) but are usually anchored by a separate flag and
  rarely turn in practice.

**Break-and-turn pause on rout** (previously untracked — new): when a unit breaks, every model
currently at rest gets a pause of `(stagger value & 7) × 3 + 6` = **6–27 ticks** with its timed-pause
flag set, and is scattered slightly from its position, before it turns to run. **If the unit was in
melee, each model's *opponent* gets the same pause** — both sides visibly hesitate together at the
moment of the break, before the routers turn about. This depends on the same per-model stagger value
introduced by epic #49/task #50.

## Open questions

None specific to the core mechanism — fully catalogued, including the worked verification table
above. (General open items like the exact `dir` zero frame and per-action frame timing, tracked as
ROADMAP A14, affect animation display only, not this movement math.)

Tracked as [epic #16](https://github.com/pgrudzien12/openHornedRat/issues/16).

## Implementation notes

Three GitHub tasks (one already existed, #17, now rewritten to the corrected/expanded spec; two new):

1. **Core turn-rate and threshold state machine** (#17): give each regiment a turn state (goal
   bearing, remaining turn, current shift/mode) instead of computing facing fresh each tick from the
   target bearing; apply the per-tick formula above, clamped by the angle thresholds (half speed while
   wheeling, zero otherwise, absorbed below ~7°); apply the one-time 90°/180° snap only at the moment a
   *new* order is issued, not continuously. Keep `formation.turn_pivot_shift` for the anchor
   displacement — already matches the documented pivot rule. The model-follows-slot part of this
   depends on epic #49/#50 to look right (front ranks fastest, rear slowest) but the anchor-level state
   machine itself does not.
2. **Per-formation-type turn differences**: monsters skip the whole pivot/slot/speed-penalty block
   (full-speed on-the-spot turning); units mid-reform skip it too; wagons snap facing to 45° steps;
   war machines get the same small-`s` fast turn as anyone else (their "usually anchored" behaviour is
   a mission/AI choice, not a distinct movement rule, so nothing extra to implement there beyond
   correct `s` for their layout — cross-reference `notes/engine_gaps/model_movement.md`'s scope
   boundary on war-machine/monster pseudo-formation layouts not existing in `whshr/formation.py` yet).
3. **Break-and-turn stagger pause**: on `combat._start_rout`, give every currently-at-rest model of the
   breaking unit (and, if it was in melee, every model of its opponent) a pause of
   `(stagger & 7) × 3 + 6` ticks before it may turn/move, plus a small scatter from its current
   position. Depends on epic #49/#50's per-model stagger value existing.
