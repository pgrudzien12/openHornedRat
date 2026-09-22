# Gap: formation & movement fidelity (turning, reversing)

**Symptom**: units turn and reverse abruptly instead of wheeling — they look like they're snapping to face
their destination every tick rather than swinging around like a rank-and-file block.

## Known facts

This is the rare gap where the research is already fully done and public (`notes/game_rules.md`,
"Turning" and "A turn always moves the unit position to keep the pivot still" — both marked ✅); the current
engine (`whshr/engine.py: Battle._turn_to`/`_advance_toward`) simply doesn't implement it yet:

- **Facing is never snapped to the travel bearing per tick.** The original keeps a goal bearing and a
  remaining-turn amount separately from current facing, and always translates along the *current* facing —
  so a unit whose facing hasn't caught up briefly walks off-axis and re-plans. The current engine instead
  sets `regiment.direction` straight to the bearing to the target every tick (`_advance_toward` calls
  `_turn_to(regiment, atan2(...))` unconditionally), which is exactly the snapping the original avoids.
- **Turn rate** is `s_rlmv × (144 − s²) × 2^(scale − 9)` facing units/tick, where `s` derives from
  frontage/ranks and `scale` depends on state (2 charging, 1 halted-turn/turn-order, 0 wheeling, −1
  closing/redirect); a turn under ≈7.7° is absorbed instantly.
- **Turn-size thresholds** decide the motion: **>45°** required turn → halt and turn on the spot (no
  translation that tick); **7.7°–45°** → wheel while moving at half speed; **<7.7°** → absorbed. A charging
  unit only wheels above 22.5° and re-aims every segment.
- **At the moment a move order is issued** (not every tick), a required turn of 68.2°–135° snaps instantly
  90°, and >135° snaps instantly 180° — this is the *only* place the original snaps, and only once per
  order, with the remainder wheeled normally afterwards. This is presumably the origin of "reversing looks
  like a sudden flip" if implemented as a per-tick snap instead of a one-time order-issue snap.
- **Pivot geometry**: in-place (halted) turns pivot about the block centre — an about-face shifts the unit
  anchor by `(ranks − 1) × 12` backwards along the old facing; a 90° turn moves it to the new front-rank
  centre and swaps ranks/frontage. Wheels pivot about the inner front corner, shifting the anchor by the
  rotated half-frontage vector. Every model's stored slot offset is counter-shifted so soldiers don't
  teleport, and the unit position is *never* held fixed while facing changes (so a turn can't open a gap
  between two touching units). `whshr/engine.py: Battle._turn_to` already calls
  `formation.turn_pivot_shift` for this — the pivot math exists; what's missing is the turn-rate/threshold
  state machine driving *when* and *how fast* facing changes, rather than snapping every tick.

## Open questions

None specific to this gap — the mechanic is fully catalogued. (General open items like the exact `dir` zero
frame and per-action frame timing, tracked as ROADMAP A14, affect animation display only, not this movement
math.)

## Implementation notes

- Give each regiment a turn state (goal bearing, remaining turn, current scale/mode: charging /
  halted-turn / turn-order / wheeling / closing) instead of computing facing fresh each tick from the
  target bearing.
- Apply the documented turn-rate formula per tick, clamped by the size thresholds (halt-and-turn above 45°,
  wheel at half speed between 7.7° and 45°, absorb below), and only apply the one-time 90°/180° snap at
  the moment a *new* order is issued, not continuously.
- Keep `formation.turn_pivot_shift` for the anchor displacement — that part already matches the documented
  pivot rule; it just needs to be driven by the new turn state machine instead of every tick's raw bearing
  change.
