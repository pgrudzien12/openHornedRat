# Wagon convoys (event 0x27 + script 166) and friendly units in melee as route obstacles

Public behavioural handoff for two BF005 playtest findings. Static research; the original was not run. Read with
`script_behaviours.md` §2.2 (collision pass, "Push apart, exactly"), `fanatic_collisions.md` §4–5 (wagon 0x27,
re-check throttle), `unit_script_control.md` §1 (event entry), `obstacle_steering.md` §3 item 6 and §6.

## A. Wagon convoys

### A.1 Short answers

1. **A switch to the script the unit is already running is ignored.** When the event handler ends and a
   normal-priority switch is pending to the script that was interrupted, the unit simply **resumes that script
   where it was interrupted**, in the same tick. Only a switch to a *different* script, or a high-priority switch
   (`IfSwitchScriptHigh`), starts the requested script at its first instruction. So a cart already in 166 that gets
   0x27 again carries on with 166: the `Yield` is not repeated, and the cart reaches `HaltAndReform`.
   Restarting 166 at pc 0 on every 0x27 is the engine bug behind the jam.
2. **Yes, 0x27 reaches the rear cart on every update** while two same-army wagons overlap with the front one within
   ±45° of the rear one's facing. The same-army war-machine/wagon row switches **both** re-check states on in every
   pass, even though the wagon is not moved by the push. The rear cart's own pass therefore runs every update, and
   the every-4th-update throttle (`fanatic_collisions.md` §5) only delays the **first** detection.
3. **A halted wagon gets 0x27 only from footprints within ±45° of its own facing.** A cart touching it from behind
   does not raise 0x27 for it, although that cart's pass keeps switching its re-check on.
4. **Nothing else stops a wagon.** A rolling-stock mover is never blocked by units in route steering, and never
   pushed. The convoy keeps its spacing **only** through 0x27 → 166: halt, wait while still touching, then restart.

### A.2 What script 166 does for a cart, step by step

`166: Yield; HaltAndReform; PushPC; SetWait 20; Wait; CheckCollisions; LoopIfTrue; Restart`

- `CheckCollisions` runs the cart's collision pass in probe mode. The 0x27 test is part of that pass, so while the
  cart ahead is still within ±45° and the circles overlap, the probe **queues another 0x27**, but it **returns false**:
  the same-army push that follows does not move the cart, and that "no" is the answer (corrected October 2026,
  `collision_probe_result.md`).
- Each further 0x27 enters the handler at the start of the next tick. Its `SwitchScript 166` is ignored (A.1 #1), so
  the cart goes back into its 20-tick wait. The timer keeps counting (`unit_script_control.md` §1, nested handlers).
- When the probe finds no footprint ahead (the cart in front has moved on), `LoopIfTrue` falls through to
  `Restart`. The cart's main script restarts at its restart point and issues `MoveToNode 2` again, so it drives on.

### A.3 Test vector: W2 following W1 on the same heading

Both carts are same-army rolling stock, facing 0 (+Y), circle radius `r` each (overlap when the centre distance is
under `2r`). W1 is halted ahead; W2 is moving at `v` per tick under `MoveToNode 2`, with handler 6 and no re-form in
progress. Tick numbers start at W2's first pass that finds the overlap.

| Tick | W2 | W1 |
|---|---|---|
| 0 (movement) | its own pass runs (on its every-4th update): W1 within ±45° and overlapping → **0x27 queued**; both re-check states on | — |
| 0 (W1's turn) | — | its pass runs (re-check on): W2 is behind (180°) → no 0x27 |
| 1 (start) | event 0x27 → handler 6 → `SwitchScript 166` (different script) → 166 starts at pc 0: `Yield` | — |
| 1 (movement) | still under `MoveToNode`: advances `v` more; pass → 0x27 queued again | its pass: nothing |
| 2 (start) | 0x27 → handler → `SwitchScript 166` **ignored** → resumes at `HaltAndReform`: **halted**; `SetWait 20`; `Wait` | — |
| 3 … 22 | each tick: 0x27 (from the mutual re-check) → handler → switch ignored → back in the wait | stands |
| 22 | wait over → `CheckCollisions`: overlap ahead → another 0x27 queued, but the answer is **false** → `Restart` → main script, `MoveToNode 2`, W2 moves | stands |
| 23 | 0x27 → handler → switch to 166 (a different script now) → 166 from `Yield`; W2 still moving | stands |
| 24 | `HaltAndReform`: halted; 20-tick wait again (W2 crept about 2–3 × `v`) | stands |
| W1 moves on, centre distance ≥ `2r` | next `CheckCollisions` → false → `Restart` → main script → `MoveToNode 2` | — |
| after | W2 drives on; if it closes in again, the cycle repeats from tick 0 | — |

W2 stops after travelling at most about `(3 + 2) × v` into the overlap: up to 3 updates of throttle before the
first pass, then the `Yield` tick. If W1 then halts, W2 **creeps** (about 2–3 ticks of movement every ~22 ticks, rows
22–24) instead of standing still 🟡 (whether it can eventually drive into a long-halted W1 is open),
re-testing every 20 ticks.

## B. Friendly units in melee as route obstacles

### B.1 Short answers (Q5)

**Effective speed** (`obstacle_steering.md` §3 item 6) is **0** unless the unit
- has a move-type order (move, flight, pursuit or follow-a-unit) and is not in a timed pause, **or**
- is charging, broken or pursuing.

Then it is the unit's current speed for its state. Consequences:

| Unit | Effective speed |
|---|---|
| **in melee** | **0**: engagement clears the unit's movement orders and its charging state, and holding an attack target does not count |
| **braced** against a charge | **0**: bracing halts the unit and it is not charging |
| charging, its target starts to rout before contact | **charge speed**: still charging; it becomes a pursuer (pursuit speed) if its script starts the pursuit |
| in melee, its opponent routs, pursuit not started yet | **0** until `StartPursuit`, then pursuit speed |

So a friendly regiment fighting in melee is an **ordinary obstacle**. The mover is faster than 0, so it detours
round it and never takes the 54-update pause. The engine's "charge speed whenever it has an attack target" is the
bug.

Two further facts that matter here:
- **A real charge does not steer.** Once a unit is charging (script 160/106), its movement is a straight run with
  one re-aim at the halfway point. Route steering, the relationship filter and the 54-update pause do not apply.
  The filter applies only to the **approach** (script 158's `MoveToTarget` walk before the charge-reach test
  passes), where the mover's effective speed is its walking speed.
- **Overlapping a friendly unit in melee does nothing.** The same-army push-apart is skipped when either unit is in
  melee, so the charger is neither pushed nor stopped. A push ahead of a charging unit would end its charge
  (`script_behaviours.md` §2.2), but that push does not happen here.

### B.2 Test vectors (Q6)

| Before | Update | After |
|---|---|---|
| M approaching its target (walking, script 158, speed s > 0); friendly F **in melee** 40 units ahead across M's path, route headings 90° apart, inside M's scan corridor | live update | F's effective speed 0 < s → F is an **ordinary obstacle**: M steers round it on its remembered or natural side; **no pause** |
| same, F **moving** (move order) at speed ≥ s, octagonal distance < 16 × M's `s_rlmv` | live update | **pause 54 updates** (unchanged rule) |
| same, F braced | live update | obstacle, detour, no pause |
| M **charging** (script 160), F in melee on the charge line | movement | no steering: M runs straight; overlapping F → no push, no charge end; M carries on to its target |
| M charging, a friendly unit **not** in melee overlaps within ±45° of M's facing | M's pass | the friendly push moves M, and since the footprint is ahead **M's charge ends** (halt, 0x09 to its target) |
| F in melee, its opponent routs, F's script starts the pursuit | after `StartPursuit` | F's effective speed = pursuit speed; for a mover with headings ≥ 45° apart and F at least as fast and near → pause 54 |
