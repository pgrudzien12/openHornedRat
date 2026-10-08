# The player's Attack order: approach walk, charge-reach test, charge run

Public behavioural handoff (follow-up of `convoy_jam_and_melee_obstacles.md`, PR #217). It connects facts spread over
several reports into one flow and adds what was missing: who restarts the approach on a re-click, and which units the
approach ignores. Static research; the original was not run. Main references: `movement_formation.md` §1.4, §3.1, §3.6,
§4 (move opcodes, script idioms); `target_queries.md` §5 (charge reach); `obstacle_steering.md` (route scan and
steering); `script_grid_events.md` §1 (`TakeEventTarget`); `reform_while_moving.md` §4 (orders during a re-form).

## 1. The phases

| Phase | Driven by | Movement | Unit state |
|---|---|---|---|
| order | `ExecuteOrder` (every tick, `game_rules.md` "Player orders"): Attack on a unit → event 0x04 to the selected unit (source = the clicked unit) | — | — |
| take target | player handler 101, case 0x04: `TakeEventTarget` (current target := the unit; braced cleared; **final waypoint := the aim point P**), then `IfSwitchScriptHigh 105` (a **high-priority** switch) | — | — |
| **approach** | library script **105**: `ResetStack; Query 5; WaitWhileUnitFlags 0x4008; React 1; MoveToTarget; Yield; [independent units: ReformBlock]`, then loop { `SetWait 10; IfTargetInChargeReach; IfGotoScript 160; Wait; TestUnitFlags 16; If Restart` } ×2, `RefreshRouteToTarget; Loop` | an **ordinary move** (follow-a-unit mode) with route steering, at the ordinary speed (`game_rules.md` "Unit speed": k = 1.8 while farther than the target's radius) | moving; **not** charging |
| **charge** | script **160**: `ChargeTarget` (charge start; 0x07 to the target), then `Yield; TestUnitFlags 16; LoopIfFalse`, then `GotoScript 163` | a straight charge run (`game_rules.md` "Turning": no steering, one re-aim at the halfway point), k = 2.5, distance budget `12 × (s_rlmv + 1)` | **charging** from `ChargeTarget` on |
| contact | collision pass + contact handler (`script_behaviours.md` §2.2–2.3) | engaged | in melee |

(AI units use 158 and 159 instead of 105. They have the same approach shape but start with a normal-priority switch.)

**Q1, reach test** (`target_queries.md` §5): made by `IfTargetInChargeReach` in 105, **once every 10 ticks**. It also
**rewrites the final waypoint to the aim point P** each time. P is on the far side of a regiment target; a war
machine, monster, wagon or building target uses its centre. It passes only when all of these hold:
- `trunc(distance(unit position, P)) − r_target < 12 × s_rlmv` (strict);
- the route is a single leg and the turn still needed is under 32/512 (22.5°);
- the unit is not steering round anything;
- the unit is not re-forming, not charging, not in melee, has no "friendly unit in the way" mark from the route scan,
  and does not hold the contact latch;
- the target is not itself charging;
- the unit stands outside every `0xB0` area.

The unit is "charging" only from `ChargeTarget` on, and only then does it move at charge speed.

## 2. Q2: the approach route

- `MoveToTarget` plans to the target's **object centre** at that moment. The route is follow-a-unit (no arrival by
  distance). Afterwards the single waypoint is refreshed **only** by `IfTargetInChargeReach` (to P, every 10 ticks)
  and by `RefreshRouteToTarget` (multi-leg routes). The plan itself is not redone every update; live steering runs
  every update (`obstacle_steering.md` §6).
- **What the route scan ignores** (`obstacle_steering.md` §3 item 6, made explicit here): the current target **and
  every unit on the target's combat grid**, of either side. A friendly regiment fighting the target is therefore
  **not an obstacle** to the approach.
- In the collision pass, walking into such a friendly unit is not resisted either: there is no same-army push while
  either unit is in melee. The approacher simply overlaps it.
- Enemy units other than the target block (except during plan trials), as do scenery and buildings.

## 3. Q3: the start-of-move snap and re-clicks

- **Snap**: only when `MoveToTarget` starts a move for a unit that is **not already moving**. The turn it uses is
  the first plan's turn: toward the **steer heading** if that first plan already steers round something, otherwise
  toward the waypoint bearing. A turn of 97–192 snaps 90°, more than 192 snaps 180° (`close_point_move.md` §2). A unit
  that is already moving gets no snap; it wheels or halts and turns.
- **Re-click Attack on the same target during the approach**: the order goes through (the unit is not charging), and
  handler 101 takes the target again: aim point written to the waypoint, `IfSwitchScriptHigh 105`. A
  **high-priority switch always restarts the script at its start**, even when it is the script already running
  (unlike a normal switch, `convoy_jam_and_melee_obstacles.md` A.1). So 105 restarts: `React 1` again, a new
  `MoveToTarget` plan, **no snap** (the unit is moving), and the 10-tick reach cycle starts over.
- **Re-click during the charge**: dropped by the order gate (move, attack, turn, rank, charge and fire orders are
  ignored while charging, in melee, broken, pursuing or braced). Nothing changes.
- **Re-click after the unit has halted** (the charge ended, or a stop): a new 105 run whose `MoveToTarget` starts
  from rest. The snap applies.

## 4. Q4: does steering swing the unit away from the target?

Steering is limited by the scan (`obstacle_steering.md` §3): a footprint blocks only inside the corridor (closer than
the waypoint, within the look-ahead) **and** inside the cone `|ref − b| < trunc(asin(R / d') × 256 / π)` around the
reference heading. A second steer is taken only if the **new** heading's scan finds a blocker. With the target's
grid excluded (§2), the BF005 case has no blocker at all:

Vector: M at (542, 255) facing 96, radius 21. Target T at (685, 254). Friendly F in melee with T at (663, 265),
radius 30. Scenery S at (534, 176), radius 38.

| Step | Value |
|---|---|
| waypoint bearing M → T | ≈ 128 (east) |
| F | on T's grid → **ignored** |
| S | bearing from M ≈ 259 (`dx` −8, `dy` −79), so 131 off the heading; cone half-width with `R` = 59, `d'` ≈ 79 is about 69 → **outside the cone, not blocking** |
| first update | no steering; turn needed 32 (22.5°) → **wheel** toward 128 while walking (no snap: below 97, and M was moving anyway); reach test every 10 ticks as in §1 |

So the original keeps walking east and charges once in reach. Your engine's two steering steps came from treating F
as an obstacle. With F excluded, S does not block a heading of 128.

## 5. Q5: what ends a straight charge run, and what follows

| On the charge line (overlap in the charger's collision pass) | Result |
|---|---|
| the target | contact → engaged (charge counter, flank/rear test) |
| another enemy regiment | **redirect**: the old target gets 0x1A, the new one becomes the target (0x07); still charging; engages on the next contact |
| solid scenery, or a friendly regiment **not** in melee, within ±45° of the facing | the push **ends the charge**: halted, charge sound off, 0x09 to the target |
| the same, outside ±45° | pushed sideways; the charge goes on |
| a friendly regiment in melee | nothing (no push); the charge goes on |
| a building that is not the target | the charge ends; the contact latch stays on (`building_units.md` §5) |
| none, but the distance budget runs out, or the edge correction applies | the charge ends, halted |

After any charge end, script 160 sees the halted state → `GotoScript 163` (stop, re-form, `Restart`). A player unit
then returns to its main script and **waits for orders**. It keeps its target, but nothing re-issues the attack;
the player must click Attack again (§3, halted case).

## 6. Q6: resuming after a pause or a halt

- **The 54-update pause** (`obstacle_steering.md` §6): the move order is kept. When the pause ends the move simply
  continues. A turn of more than 64 needed at the next plan is a halted on-the-spot turn owing half the angle
  (`close_point_move.md` §2). There is **no snap**.
- **Halted inside 105** (blocked by a friendly in front, or a refused move): the loop's `TestUnitFlags 16` →
  `Restart` re-runs 105 from the top. `MoveToTarget` then starts from rest, so the snap applies (≥ 97).
- **After a charge end**: see §5. Nothing resumes by itself.

## 7. Test vectors

| Before | Event | After |
|---|---|---|
| player infantry I (s_rlmv 11) idle; enemy E (block, radius 40) whose P lies 183 away | Attack E | 105 starts; `React 1`; `MoveToTarget` → moving toward E's centre at k = 1.8; reach test: 183 − 40 = 143 ≥ 132 → walk on |
| I walking, 10 ticks later P is 170 away, facing within 22.5°, single leg, not steering | `IfTargetInChargeReach` | 130 < 132 → script 160 → `ChargeTarget`: charging, k = 2.5, budget 144 |
| I walking toward E; friendly cavalry C in melee with E on the line | live updates | C ignored by the scan; I overlaps C without a push; charges when in reach |
| I walking; re-click Attack on E | next tick | handler 101 → 105 restarts (high priority): `React 1`, new plan, no snap, reach cycle restarts |
| I charging; re-click Attack on E | — | order dropped |
| I charging; a friendly regiment D (not in melee) overlaps 20° off I's facing | I's pass | D pushes I; the charge ends → 163 re-form → idle, waiting for orders |
| I halted after that; player clicks Attack on E, E is 100° (142/512) off I's facing | new 105 | `MoveToTarget` from rest: turn 97–192 → snap 90° toward E's side (the first plan's heading), then wheel the rest |
| same, E 150° (213/512) off | new 105 | turn > 192 → snap 180° (about-face) |
