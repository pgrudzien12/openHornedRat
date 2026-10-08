# Point moves to a close, off-axis destination (GitHub #183)

Clean-room behavioural handoff for the implementer. It answers how an ordinary point move plans, turns and stops when
its destination is close to the unit and well off its facing, and why some such moves do not end. Static
research; the original was not run. It extends `movement_formation.md` §1.4 ("Arrival of an ordinary move") and
`game_rules.md` "Real time and movement" / "Turning, wheeling and reversing". Conventions: facing in 1/512 turn,
0 = +Y, clockwise; positions in world units.

## 1. Short answers

1. **Measuring point:** the unit position, i.e. the **front-rank centre** (truncated to whole units). The bearing,
   the distance `d` and the 32-unit stop test are all measured from it to the current waypoint. It is not the block
   centre or a corner. Your engine is right.
2. **Order of the plan tests:** as in §1.4. **The turn test comes first**: turn needed > 64 → halted turn, and
   nothing else happens at that plan. The `d ≤ 32` stop is reached only at a plan whose turn is ≤ 64. Your engine is
   right.
3. **Halted turn:** it owes `turn_needed div 2`, fixed at the plan. It turns at the halted-turn rate
   (`game_rules.md`, shift 8) and counts as done on the tick the amount still owed is **≤ 10**. On that same tick the
   unit re-plans. It **does** pivot about the **inner front corner**: the same pivot as every gradual turn, radius
   `6 × (frontage − 1)`, on the side the unit turns towards. A halted turn does not translate the unit and does not
   run down the re-plan countdown. Your engine is right on all three points.
4. **Nothing else ends such a move.** There is no turn or time limit, no "inside my own footprint" test for player
   units and no "already there" test beyond the planner producing no waypoint, which needs `d = 0`.
   Two things your description does not mention change some of your vectors (§3):
   - the **move-start snap** (turn needed ≥ 97 when the move starts from rest → instant 90°; > 192 → instant 180°);
   - the **re-form** that snap queues, during which the halted turn and the wheel are **suspended**
     (`reform_while_moving.md` §5).
   After that, the original's own rules give the **same non-terminating orbit** for destinations inside the pivot
   circle, off-axis by more than 45°. 🟡 A runtime check would settle whether the game really does this. I found no
   rule that prevents it.
5. Test vectors: §5.

## 2. The rules, in order

**At the move start** (a move order or `MoveToTarget` from rest; not on re-plans):
1. The waypoint is planned and the turn needed is computed from the front-rank centre.
2. **Snap**: turn needed **97–192** → instant quarter turn towards the destination's side; **> 192** → instant
   about-face. Both displace the unit position as in `game_rules.md` "Turning" (quarter turn: to the new front-rank
   centre, ranks and frontage swapped; about-face: `(ranks − 1) × 12` backwards). Both queue a re-form. Turn ≤ 96: no
   snap. A unit that is already moving gets no snap.
3. The unit is moving and a plan is due on its next movement update.

**Each movement update** (not in melee):
1. **Halted turn in progress**: if the unit is re-forming, nothing at all happens this tick. Otherwise turn one step
   (rate `s_rlmv × (144 − s²) / 256` per tick, pivot about the inner front corner, no translation). If more than 10
   is still owed, the tick ends. Otherwise the halted turn ends and the unit **plans in this same tick**.
2. **Wheel in progress** (and not re-forming): one wheel step (half the halted-turn rate, same pivot, half
   translation speed). When ≤ 10 is still owed, the wheel ends and the unit plans in this same tick.
3. **Plan**, when due (a turn just ended, or the countdown ran out):
   - bearing and `d` from the front-rank centre to the waypoint; turn needed = the angle from facing to bearing,
     0–256, and its direction;
   - **turn > 64** → halted turn owing `turn div 2`; the tick ends (no translation);
   - else **d > 32**, or the route follows a unit and has a single leg → keep moving; countdown `min(2d, 150)`;
     wheel owing `turn` if `turn ≥ 11` (and `d > 32`), otherwise go straight;
   - else (`d ≤ 32`) → next waypoint (re-plan, no snap) or, with none left, **halt and re-form** (halted state, move
     ended).
4. **Translate** along the current facing (half speed while wheeling or re-forming). Countdown −= `s_rlmv`. When it
   goes negative, a plan is due next tick.

A plan made while the unit is re-forming still runs. Only the turning it orders waits for the re-form to end.

## 3. Why a close, off-axis destination orbits

While a halted turn pivots about the inner front corner `C`, the front-rank centre `P` moves on a circle of radius
`r = 6 × (frontage − 1)` around `C`. The bearing from `P` to the waypoint then changes **as fast as the facing, or
faster**, whenever the waypoint lies inside or near that circle. Each re-plan therefore finds the turn needed still
above 64 (often larger than before), so it orders another halted turn. Because the turn test comes before the
`d ≤ 32` test, the stop is never reached, although `d` stays well under 32. The unit spins and drifts around the
point indefinitely. `r` = 18 for frontage 4, 24 for frontage 5.

It ends only if a plan happens to find the turn ≤ 64 while `d ≤ 32`. That needs the point to be outside the pivot
circle by a margin, or close to the axis to begin with:
- turn needed ≤ 64 at the first plan (destination within 45° of the facing) → halts at once if `d ≤ 32`, else moves;
- destinations far enough out that one or two halted turns bring them within 45° (e.g. B 60°, D 32 below).

The snap rescues some cases (it rotates the unit at once without moving the pivot), but the re-form it queues
delays the following halted turn.

**Engine choice (not original behaviour).** An engine that wants to avoid the orbit should add a safety rule
and document it as a deviation. The least intrusive one: at a plan with `d ≤ 32` **and** turn > 64, halt and
re-form instead of starting a halted turn (the unit is already inside the stop radius). It changes only the cases
that never end under the rules above. The alternative is to keep the original rules and accept the orbit.

## 4. Points to check in your engine

- Snap at the move start (≥ 97 → 90°, > 192 → 180°, from rest only) with its displacement and queued re-form.
- While re-forming: halted turn = no turn and no translation; wheel = no turn, half-speed translation; plans still
  run.
- The re-plan at the end of a turn happens in the **same** tick.
- The halted turn neither translates nor decrements the countdown.
- Halt at `d ≤ 32` still lets the unit translate on that tick in the original (negligible). Halt and re-form
  follows.

## 5. Test vectors

Computed from the rules above (static). Conditions: `s_rlmv` 18, `k` 1.8 (2.025 units/tick), unit at (0, 0)
facing 0, destination at bearing B and distance D from the front-rank centre. The re-form after a snap is
assumed to last 20 ticks (it depends on the figures; `reform_while_moving.md` §3). Positions are the front-rank
centre, rounded.

| Unit | B, D | First plan | Then | End |
|---|---|---|---|---|
| 11 models / 3 ranks (frontage 4, r 18) | 60°, 10 | d 10, turn 86 → halted turn owing 43 | tick 6: facing 37, P (1.8, 7.9), d 8, turn 110 → owing 55; tick 12: facing 83, P (8.6, 15.3), d 10, turn 164; tick 22: facing 159, P (24.7, 16.7), d 18, turn 174 … | **never** (orbits) |
| same | 60°, 18 | turn 85 → halted turn | similar | **never** |
| same | 60°, 32 | d 32, turn 85 → owing 42 | tick 6: facing 37, P (1.8, 7.9), d 28, turn 64 | **halts tick 6** (turn ≤ 64, d ≤ 32) |
| same | 60°, 24 | turn 85 | several halted turns | halts tick 77, facing 65 |
| same | 30°, 10 | d 10, turn 43 | — | **halts at the first plan** (no turn at all) |
| same | 135°, 40 | turn 192 at the start → **snap 90° clockwise**: facing 128, P (18, −12), ranks/frontage swapped, re-form | tick 1 plan: d 18, turn 82 → halted turn, suspended while re-forming | tick 24: facing 165, d 15, turn 64 → **halts** |
| same | 150°, 32 / 40 | turn 213 → **snap 180°**: facing 256, P (0, −24), re-form | halted turns after the re-form | **never** |
| same | 90°, 20 | snap 90° | — | **never** |
| 20 models / 4 ranks (frontage 5, r 24) | 60°, 10 / 20 | halted turn | — | **never** |
| same | 60°, 32 | turn 85 → owing 42 | tick 6: d 27, turn 74; tick 10: d 22, turn 68; tick 14: d 16, turn 61 | **halts tick 14**, facing 86, P (12.2, 20.8) |
| same | 90°, 40 | snap 90° | — | halts tick 23 |
| same | 150°, 60 | snap 180° | — | halts tick 32 |
| same | 150°, 32 | snap 180° | — | **never** |

Single-plan checks:

| Before | Plan | After |
|---|---|---|
| P (0,0), facing 0, waypoint (9, 5) (d 10, B ≈ 60°) | turn 86 > 64 | halted turn owing 43; no translation; countdown unchanged |
| owing 15, rate 7.6/tick | turn step | owing ≈ 7 ≤ 10 → turn over; plan this tick |
| P (0,0), facing 0, waypoint (5, 30) (d 30, turn 13) | turn ≤ 64, d ≤ 32 | halt and re-form (move over) |
| P (0,0), facing 0, waypoint (20, 40) (d 44, turn 38) | turn ≤ 64, d > 32 | keep moving; wheel owing 38; countdown 88 |
| unit re-forming, halted turn owing 40 | movement update | nothing (no turn, no translation) |

## 6. Uncertainties

- 🟡 The orbit is what the original's rules give on a static reading. No terminator was found in the move, plan,
  turn, collision or order paths for player units. A runtime check would show whether the game really spins
  units like this, or whether the interface (e.g. a click that close to a unit) keeps such orders from being
  issued.
- 🟡 Simulated values use exact sin/cos and truncated bearings. Per-tick values may differ by a unit or two from
  the original's table arithmetic, which can move the boundary cases (e.g. D 24 vs 18).
