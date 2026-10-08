# Unit-script movement, facing, formation and grid opcodes

Public implementation report, batch 4 of the interpreter requests (GitHub #3). It is a companion to
`unit_script_control.md` and `target_queries.md`. It describes behaviour only. Part A covers movement and facing,
how scripts learn "done", and the charge aim point (which settles the conflict in `target_queries.md` §5). Part B
covers formation, rally and the close-combat grid. Both parts end with notes on how the original differs from a
single-destination engine model.

## Part A — movement and facing

Public implementation report (batch 4 of the interpreter requests, GitHub #3). Companion to
`unit_script_control.md` (condition word, wait opcodes) and `target_queries.md` (aim point, §5). Behaviour only.

**Read in `game_rules.md` rather than re-deriving:**
- "Real time and movement": unit speed factor `k`, the per-tick turn rate, the 45° / 7.7° thresholds, and the instant
  snap when a move order is issued (68.2°–135° → 90°, > 135° → 180°);
- "Turning, wheeling and reversing": how a turn displaces the unit position, and the slot recomputation;
- "Routes, collisions and visibility": waypoints, obstruction steering (`ObjectsOnPath`), boundary masks, the
  collision pass;
- "Charge": the charge budget `12 × (s_rlmv + 1)` and the halfway re-aim;
- "Scripted target and flight opcodes": `FleeAhead`, which `FleeBackward` mirrors.

Conventions as in `target_queries.md` §1: facing and bearings in 1/512 turn, **0 = +Y, clockwise** (128 = +X);
`bearing(A→B) = trunc(256 − 256 × atan2(Δx, −Δy) / π)` with `Δ = B − A`; `SIN[a]`/`COS[a]` = `trunc(256 × sin/cos(2πa/512))`.
A facing `f` looks along `(SIN[f], COS[f])`. "Regiment position" is the unit's own reference point (front-rank
centre). "Object centre" is the centre of the unit's footprint box, `(ranks − 1) × 6` behind the regiment position
along the facing (for blocks; single models and war machines use the regiment position). `r` is the footprint's
bounding radius `trunc(√((6 × frontage)² + (6 × ranks)²))`.

### 1. State, per-tick order, and how scripts learn "done"

#### 1.1 Movement state labels used below

`move_state` bits (descriptive labels):

| bit | meaning |
|---|---|
| 0x1 | re-form queued (the formation is re-laid next tick, which sets `unit_flags 0x8`) |
| 0x2 | moving to a waypoint (ordinary move) |
| 0x4 | turning: wheel while moving (with 0x2), charge re-aim (with 0x40), or a **turn order** on its own |
| 0x8 | halted turn inside an ordinary move (> 45° owed) |
| 0x10 | steering around an obstruction (see `target_queries.md` §5.3) |
| 0x20 | timed wait |
| 0x40 | charging |
| 0x80 | free charge (no target unit; suppresses the "charge ended" event to a target) |
| 0x100 | fleeing |
| 0x200 | pursuing |
| 0x1000 | **route follows a unit** (set by `MoveToTarget`): the unit never "arrives" by distance |

Relevant `unit_flags`: 0x8 re-forming (models walking to slots), 0x10 **halted / idle**, 0x20 turn direction
(clockwise), 0x80 charging, 0x200 in melee, 0x2000 broken, 0x1000000 contact latch (touching an enemy, engagement
pending). `unit_flags2` 0x1 = anchored war machine, 0x8 = the hold bit (never set by shipped data). Many movement
starts are **refused when `unit_flags2 & 9`** (anchored), shortened below to "anchored".

#### 1.2 Per-tick order (each battle tick, per live unit)

1. Unit speed is recomputed (`game_rules.md`).
2. The unit's **behaviour script** runs (the opcodes of this report execute here).
3. The **formation update**: if a re-form is queued (`move_state 0x1`) the slots are re-laid and `unit_flags 0x8` is
   set; while `0x8` is set the models walk to their slots, and on the tick when every model is at rest `0x8` is cleared
   and the unit sends itself **event 0x34**.
4. If the unit is **not in melee** (`unit_flags 0x200` clear), exactly one movement handler runs, chosen from
   `move_state` in this priority: 0x20 wait → 0x100 flee → 0x200 pursue → 0x2 move → 0x40 charge → 0x4 turn order.
   If **none** of those bits is set, the unit gets **`unit_flags |= 0x10`** (idle) — every tick.
5. The collision pass for units that moved or turned (`game_rules.md`).

Because the script runs **before** the movement and formation updates of the same tick, an opcode that queues a
re-form (instant turns, a move start that snaps) does not set `unit_flags 0x8` until later in that tick. That is why the
shipped idiom is `<turn or move> / Yield / WaitWhileUnitFlags 8`: without the `Yield`, the wait would test the flag
before it is set and fall straight through.

#### 1.3 The "done" signal is `unit_flags 0x10` (halted)

`TestUnitFlags 16`, `WaitUntilUnitFlags 16` and `LoopIfFalse` after `TestUnitFlags 16` all mean "this unit has
stopped". The flag is:

**Set by**
- **every halt-and-re-form**: arrival at the last waypoint of an ordinary move, the end of a turn order, a move order to
  the unit's own position, a refused `ChargeForward`, and the `HaltAndReform` opcode itself;
- the **end of a charge** (budget spent, or a charging unit pushing into something within ±45° of its front);
- every tick while a charging unit holds the contact latch (`unit_flags 0x1000000`);
- every tick by step 4 above while the unit has **no** movement state and is not in melee.

**Cleared by**
- the start of any planned move (`MoveToTarget`, `CircleAroundTarget`, any re-plan that re-issues the route);
- each re-plan of an ordinary move that is still travelling (see 1.4);
- the start of a turn order (`TurnToFaceTarget`);
- the start of a charge (`ChargeTarget`, `ChargeForward`);
- the start of a rout (`FleeBackward`, `FleeAhead`, any rout). A fleeing unit never gets it back from step 4
  (its movement state is "fleeing").

**Not** touched by the instant turns (`QuarterTurnToTarget`, `AboutFace`, `QuarterTurn`): for those the scripts wait on
`unit_flags 0x8` (re-forming) instead.

`unit_flags 0x8` (re-forming) is the second signal: it is set after any instant turn, any halt, and any snap, and cleared
when the models are settled (with event 0x34; `game_rules.md` lists 0x34 as "destination reached" — it is in fact sent at
the end of **every** re-form, which follows every halt).

#### 1.4 Arrival of an ordinary move

An ordinary move (`move_state 0x2`) re-plans only at intervals: after each plan a countdown of
`min(2 × d, 150)` is set (`d` = distance to the current waypoint, or the deflected distance while steering round an
obstruction) and decreased by `s_rlmv` every tick; the next plan happens when it goes negative (or when a turn owed by
the previous plan has finished). At a plan:

- turn needed > 64 → halted turn (`move_state 0x8`), owing **half** the angle; re-plans when done;
- otherwise, if **`d > 32`, or the route follows a unit (`move_state 0x1000`) and has a single waypoint** → keep moving
  (`unit_flags 0x10` cleared), wheel if the turn needed is ≥ 11 and `d > 32`;
- otherwise (`d ≤ 32`): advance to the next waypoint if there is one; with none left, **halt and re-form** →
  `unit_flags 0x10`.

Because the turn test comes first, a destination close to the unit and more than 45° off its facing can keep
producing halted turns that never reach the 32-unit stop (`close_point_move.md`). So a point move stops **within 32 units of the point**, at whatever distance the last plan found (a straight 100-unit
move by an `s_rlmv` 11 unit at k = 1.8 halts after ≈ 57 ticks about 29 units short; 🟡 simulated from the rules above,
not observed). A unit following a unit (after `MoveToTarget`) has no distance arrival at all: it keeps walking at its
waypoint until contact, a script change, or a re-issue.

### 2. Summary

| Opcode | Len | Destination / waypoints | Facing | Flags | Condition | Over ticks |
|---|---|---|---|---|---|---|
| `MoveToTarget` 0x3D | 1 | route to the target's **object centre**; follows-unit mode | snap 90°/180° only if starting from rest | moving, 0x1000; clears 0x10 | true if the move started; false if no target or refused | ordinary move, no distance arrival |
| `RefreshRouteToTarget` 0x3E | 1 | multi-leg route with a clear line → single waypoint at the target's current centre; single leg crossing a boundary → re-routed | none | – | true if the route was changed; **unchanged** if not; false if no target | – |
| `TurnToFaceTarget` 0x4B | 1 | **waypoints cleared** (stops the unit) | gradual turn to the target's regiment position | `move_state = turn`; clears 0x10 | false if within 16; true if started | turn order, then halt → 0x10 |
| `QuarterTurnToTarget` 0x4C | 1 | unchanged (moving bit cleared) | instant 90° (65–192 off) or 180° (> 192 off) | re-form queued | false if ≤ 64 off; else **true** | re-form (0x8) |
| `AboutFace` 0x5C | 1 | unchanged (moving bit cleared) | instant +256 | re-form queued | not written | re-form |
| `QuarterTurn` 0x5D | 2 | unchanged | instant ±128 | re-form queued | not written | re-form |
| `ChargeForward` 0x4F | 1 | one waypoint `12 × s_rlmv` straight ahead | charge turn (none needed) | charging | true / false (then halted) | charge |
| `FleeBackward` 0x52 | 1 | flight heading facing + 256 | **set instantly** to facing + 256 | rout; target cleared | always true | flight |
| `CircleAroundTarget` 0xE4 | 1 | point move to the target-centred circle, +16 | snap if from rest | moving; clears 0x10 | true if the move started; false if no target | ordinary move, arrival → 0x10 |
| `ApproachTargetInReach` 0xD7 | 1 | **final waypoint := charge aim point P** | none | – | octagonal distance < `threat_range` | – |
| `CheckCollisions` 0xC7 | 1 | possibly pushed apart | none | clears the contact latch when false | true if anything was touched/pushed | – |

All lengths agree with `whshr/behaviour.py`. None of these opcodes yields; the script continues with the next word.

### 3. Opcodes

#### 3.1 `MoveToTarget` (0x3D, 547 uses)

1. No current target → condition **false**, nothing else (the original prints a debug message).
2. The move is **refused** (condition false, nothing changes) if the unit is re-forming (`unit_flags 0x8`) or anchored.
   This is why every shipped use is preceded by `WaitWhileUnitFlags 8` / `0x4008`.
3. The goal is the target's **object centre** at this instant (not its regiment position). The waypoint list is
   cleared and rebuilt to the goal: one waypoint if the straight line crosses no `0xB0` boundary, otherwise boundary
   detour points ("Routes, collisions and visibility"). Before this, the goal is pushed out of friendly footprints and
   solid scenery it may lie in. 🟡 For enemy-side (AI) units only, the planner may additionally pull the first waypoint
   back to `r_other + r_own` in front of any unit whose circle contains it, on the line of approach; whether this applies
   depends on a per-unit bit not yet identified, and it looks like an original-program quirk. An engine may skip it.
4. If the planner produces no waypoint ("already there"), the unit **halts and re-forms** and the condition is still
   **true**.
5. Otherwise the move starts: `move_state 0x2` set, 0x4/0x8/0x10 cleared (and 0x400/0x1000 before planning), `unit_flags 0x10`
   cleared, the obstruction detour side chosen (`game_rules.md`), the walk animation started. **If the unit was not already
   moving**, the first plan applies the instant snap: turn needed 97–192 → instant 90° towards the target side, > 192 →
   instant 180° (both queue a re-form). A unit that was already moving gets no snap; it wheels or halts-and-turns per tick.
   If both detour sides are hopeless ("can't find the way") the condition is **false**; 🟡 the moving state set during
   planning is not undone, so the unit still tries the straight leg.
6. On success `move_state |= 0x1000` (route follows a unit) and condition **true**.

Over ticks: the ordinary move of §1.4, except that **a single-leg follow-unit route never arrives by distance**. The
waypoint is **not** updated as the target moves; only `IfTargetInChargeReach`/`ApproachTargetInReach` (which overwrite
the final waypoint with the aim point), `RefreshRouteToTarget` (multi-leg routes only) or a new `MoveToTarget` move it.

| Before | Instruction | After |
|---|---|---|
| Player unit at (0,0), facing 128, at rest, not re-forming. Target object centre (300,0). | `MoveToTarget` | waypoints [(300,0)], `move_state` 0x2 \| 0x1000, `unit_flags 0x10` clear, facing 128, condition true |
| Same, unit facing 0 (target 128 = 90° to the right). | `MoveToTarget` | instant clockwise 90° (facing 128, position displaced as in `game_rules.md`, re-form queued), then moving as above; true |
| Same, `unit_flags 0x8` (re-forming). | `MoveToTarget` | nothing changes, condition false |
| No target. | `MoveToTarget` | nothing changes, condition false |

#### 3.2 `RefreshRouteToTarget` (0x3E, 140 uses)

- No target → condition **false**.
- Acts only while the unit is moving or following a unit (`move_state & (0x2 | 0x1000)`). Goal G = the target's
  **current** object centre.
  - The line from the unit to G crosses **no** `0xB0` boundary **and** more than one waypoint is queued → the route is
    replaced by the single waypoint G and re-planned (no snap); condition **true**.
  - The line **crosses** a boundary **and** exactly one waypoint is queued → re-route to G around the boundary,
    re-plan (no snap); condition **true**.
  - Any other case: nothing; the condition is **left as it was** (not written).
- Never turns the unit, never sets `move_state 0x1000`.

Consequence: in the common open-field case (one leg, clear line) the opcode does nothing. It only shortcuts a detour
route once the way is clear, or reacts to the target having moved behind a boundary.

| Before | Instruction | After |
|---|---|---|
| Moving, waypoints [(300,0)]; target now at centre (320,40); open field. | `RefreshRouteToTarget` | unchanged; condition unchanged |
| Moving, waypoints [(100,50),(200,60),(300,0)] (detour); target centre now (320,40), line clear. | `RefreshRouteToTarget` | waypoints [(320,40)], re-planned; true |
| At rest (no movement state), target present. | `RefreshRouteToTarget` | nothing; condition unchanged |

#### 3.3 `TurnToFaceTarget` (0x4B, 282 uses)

- Point to face: the target's **regiment position**; with no target unit, the target point (if both its coordinates
  are ≥ 0); with neither, the unit's own facing (so nothing happens).
- Needed turn `Δ = |bearing − facing|` folded to 0…256. **Δ ≤ 16** → condition **false**, nothing else.
- Otherwise a **turn order** starts, unless the unit is fleeing (`move_state 0x100`) or anchored (then condition
  false):
  - **waypoints cleared** (count 0): the unit **stops moving**; the face point is stored as the turn goal;
  - `move_state`: 0x2, 0x8, 0x10, 0x1000 cleared, **0x4 set** (turn order);
  - `unit_flags 0x10` cleared; turn direction `unit_flags 0x20` set if clockwise (0 ≤ Δ_signed ≤ 256);
  - turn owed = Δ; condition **true**.
- Over ticks: the turn-order handler (only when no 0x2/0x40 state) turns at the **halted-turn rate** (`game_rules.md`,
  shift 8) with the inner-front-corner pivot, skips ticks while the unit is re-forming, and when **10 or fewer** units
  remain it **halts and re-forms** → `unit_flags 0x10`. The goal is not re-read: a moving target is not tracked, and the
  final facing is up to 10/512 short.

| Before | Instruction | After |
|---|---|---|
| 5×4, `s_rlmv` 11, facing 0 at (0,0); target at (100,100) (bearing 64). | `TurnToFaceTarget` | true; `move_state` = 0x4, waypoints 0, `unit_flags 0x20` set, 0x10 clear. ≈ 14 ticks later facing ≈ 57, halted, `unit_flags 0x10` |
| Facing 0, target at bearing 16. | `TurnToFaceTarget` | false; nothing changes |
| Fleeing unit (`move_state 0x100`), target 90° off. | `TurnToFaceTarget` | false; nothing changes |

#### 3.4 `QuarterTurnToTarget` (0x4C, 225 uses)

- Bearing to the target's regiment position (else target point, else own facing → Δ 0). `Δ` folded to 0…256.
- **Δ ≤ 64** → condition **false**, nothing.
- **65 ≤ Δ ≤ 192** → instant **quarter turn** the shorter way round: anticlockwise (−128) if the target lies
  anticlockwise, else clockwise (+128). Condition **true**.
- **Δ > 192** → instant **about-face**. Condition **true**.
- The condition is true even if the instant turn was refused (fleeing, anchored, or re-forming for the about-face).

Instant quarter turn (also `QuarterTurn`, and the move-start snap): refused if fleeing or anchored. Facing ± 128;
the regiment position moves `(ranks − 1) × 6` back along the old facing and `(frontage − 1) × 6` sideways towards the
turn side (to the right for clockwise), each component `trunc(… / 256)` from the sin/cos tables; the desired rank count
becomes the old frontage; every model is counter-shifted so none teleports; `move_state` 0x2, 0x4, 0x8, 0x20, 0x1000
cleared and a re-form queued. **Waypoints are kept** but the moving bit is gone, so the unit stands; `unit_flags 0x10`
is not touched (set again by the idle rule on the following ticks).

Instant about-face (also `AboutFace`, and the > 135° snap): refused if fleeing, anchored **or re-forming**. Facing + 256;
the regiment position moves `(ranks − 1) × 12` back along the old facing; same counter-shift, same bits cleared,
re-form queued.

| Before | Instruction | After |
|---|---|---|
| 5 wide × 4 deep at (0,0), facing 0; target at (100,10) (bearing 119). | `QuarterTurnToTarget` | true; facing 128; position (24,−18); desired ranks 5; re-form queued |
| Same, target at (−100,10) (bearing 392 → anticlockwise). | `QuarterTurnToTarget` | true; facing 384; position (−24,−18) |
| Same, target at (10,−100) (bearing 247, Δ 247). | `QuarterTurnToTarget` | true; facing 256; position (0,−36) |
| Facing 0, target at bearing 60. | `QuarterTurnToTarget` | false; nothing |

#### 3.5 `AboutFace` (0x5C, 1 use) and `QuarterTurn` (0x5D, unused)

- `AboutFace`: the instant about-face of 3.4. Does not write the condition. The single use (BF009) is
  `AboutFace / WaitWhileUnitFlags 8` when no enemy is visible and some unit is in a node area — the unit reverses and
  waits for its models.
- `QuarterTurn n` (2 words): operand **0x20** → clockwise (+128), **any other value** → anticlockwise (−128); the instant
  quarter turn of 3.4. Does not write the condition. Not used by any shipped script.

Test: 5×4 at (0,0) facing 0, `AboutFace` → facing 256, position (0,−36), re-form queued; with `unit_flags 0x8` set →
nothing changes.

#### 3.6 `ChargeForward` (0x4F, 45 uses — library script 106)

A charge without a target unit (the player's "charge" order with no enemy picked).

1. The unit's position must lie outside every active `0xB0` region; otherwise go to 4.
2. One waypoint at `position + (trunc(SIN[f] × 12·s_rlmv / 256), trunc(COS[f] × 12·s_rlmv / 256))`, count 1.
3. Start the charge (refused if anchored → 4): `move_state` 0x40 set, 0x2/0x4/0x8/0x10/0x80/0x1000 cleared;
   `unit_flags 0x80` set, 0x10 and the hidden bit 0x80000 cleared (charging reveals the unit); models start staggered by
   rank; `move_state 0x4` set again if the unit must turn towards the point; aim and budget as in "Charge" (`12 × (s_rlmv + 1)`, re-aim at the halfway point — at the same stored
   waypoint). Then `move_state |= 0x80` (free charge: no "charge ended" event to a target). Condition **true**.
4. On failure: **halt and re-form** (`unit_flags 0x10`), condition **false**.

The charge ends after its budget even short of the point, or on contact. `EndCharge` sets `unit_flags 0x10`, so script
106's `Yield / TestUnitFlags 16 / LoopIfFalse` loop ends there and goes to re-form script 163.

| Before | Instruction | After |
|---|---|---|
| (0,0), facing 128, `s_rlmv` 11, open ground. | `ChargeForward` | waypoint (132,0); charging; true |
| Same, facing 64. | `ChargeForward` | waypoint (93,93) (SIN[64] = COS[64] = 181) |
| Unit standing inside a `SOLID` area. | `ChargeForward` | halted and re-formed; false |

#### 3.7 `FleeBackward` (0x52, 45 uses — library script 157)

Identical to `FleeAhead` ("Scripted target and flight opcodes" in `game_rules.md`) except for the heading:
**`(facing + 256) mod 512`**. The rout sets the unit's facing to that heading **instantly** (no pivot displacement;
the models pause and scatter as on any break), sets broken, `move_state` = fleeing only (every other movement bit
cleared; independent units also get the automatic-rally bit, see "Rally"), clears `unit_flags` 0x8/0x10/0x80/0x1000000. The target is **cleared** and the condition is **always true**,
even when the rout is refused (anchored war machine: nothing moves but the target is still cleared).

Script 157 is `FleeFromTarget / IfNot FleeBackward / idle loop`. It is the rout script of the war-machine crew handler
(script 154, events 0x0C rout and 0x0D fear), so a crew with no target runs straight away from the machine's front.

Test: facing 100, `FleeBackward` → facing 356, broken, fleeing, target empty, condition true; position then advances
along 356 at `1.5 × s_rlmv / 16` per tick.

#### 3.8 `CircleAroundTarget` (0xE4, 90 uses — library script 169)

- No target → condition **false**.
- `b = bearing(target regiment position → unit regiment position)`, `a = (b + 16) mod 512`,
  `d = trunc(√(Δx² + Δy²))` between the two regiment positions.
- Goal `= target position + (SIN[a] × d >> 8, COS[a] × d >> 8)` — note an **arithmetic shift (floor)**, not the
  truncation used elsewhere.
- An ordinary point move to the goal, exactly as `MoveToTarget` steps 2–5 but **without** follow-unit mode, so it arrives
  (§1.4) and halts with `unit_flags 0x10`. Condition = the move was accepted (false if re-forming, anchored or no way).

The unit thus walks 11.25° clockwise round the target at its current range. Script 169 repeats every 15 ticks: if the
target is visible → script 146 (halt, quarter-turn towards the target if the pending spell would reach it, wait for the
re-form), else another `CircleAroundTarget`, until `unit_flags 0x10`.

| Before | Instruction | After |
|---|---|---|
| Target at (0,0); unit at (0,−200) (south), at rest. | `CircleAroundTarget` | b = 256, a = 272, d = 200, goal (−39,−197) (−9800>>8, −50200>>8); moving; true |
| Same, unit re-forming. | `CircleAroundTarget` | false; nothing |
| No target. | `CircleAroundTarget` | false |

#### 3.9 `ApproachTargetInReach` (0xD7, 1 use — BF039 script 8)

- Condition cleared first. No target → **false**.
- **Side effect:** the unit's **final waypoint is replaced by the charge aim point P** of `target_queries.md` §5.1 (far
  side of a block target, centre of other targets; §5 below settles the direction). With no waypoint queued it becomes
  waypoint 1. Unlike `IfTargetInChargeReach` there is **no** re-forming check and no planner refresh.
- Condition = **octagonal distance** between the two **regiment positions** `< threat_range` (set by
  `SetThreatRange`, 0x31): with `ax = |Δx|`, `ay = |Δy|`, `dist = max + ceil(min / 2)`.

The shipped use (BF039, a fanatic-carrying unit): `MoveToTarget / Yield / loop { ApproachTargetInReach;
SendEventSelfIfTrue 6; wait 15 }` — the walk is re-aimed at P every 15 ticks and the unit sends itself event 6 (which
that mission handles by releasing its fanatics) once inside its threat range.

| Before | Instruction | After |
|---|---|---|
| Unit (0,0), `threat_range` 240; monster target at (200,60). | `ApproachTargetInReach` | final waypoint (200,60); dist 200 + 30 = 230 < 240 → true |
| Same, target at (200,90). | `ApproachTargetInReach` | dist 245 → false; final waypoint (200,90) |
| No target. | `ApproachTargetInReach` | false |

#### 3.10 `CheckCollisions` (0xC7, 45 uses — library script 166)

Runs the per-tick collision pass ("Routes, collisions and visibility") **for this unit immediately**, in **probe mode**:
friendly-unit and scenery push-apart, the battle-edge repel, a charging unit's stop within ±45° and the `INVSOLID`-ahead
event 0x27 all happen as usual, and an enemy footprint overlap is **detected but not engaged** (no contact handler).
🟡 The fear-on-contact test against an overlapping enemy still runs.
Condition = **true if anything was pushed or touched**. If false, the contact latch `unit_flags 0x1000000` is cleared.
A unit flagged as leaving the battle (`unit_flags 0x100`) or with an inactive footprint is skipped (false).

Script 166 ("separate after a collision", `game_rules.md` script table): `Yield / HaltAndReform / every 20 ticks
CheckCollisions while true / Restart` — the unit stands while the push-apart separates it, then restarts its script.

| Before | Instruction | After |
|---|---|---|
| Footprint overlaps a friendly unit by 10. | `CheckCollisions` | both pushed apart; true |
| Nothing overlapping, latch set. | `CheckCollisions` | latch cleared; false |
| An enemy footprint corner inside the unit's box. | `CheckCollisions` | true; no engagement, no event |

### 4. Shipped idioms

| Idiom | Scripts | Ends when |
|---|---|---|
| `WaitWhileUnitFlags 0x4008 / MoveToTarget / Yield / WaitWhileUnitFlags 8` | 105, 158, 159, 9 (missions) | a snap's re-form is over |
| `loop { SetWait 10; IfTargetInChargeReach; IfGotoScript 160; Wait; TestUnitFlags 16; If Restart }` ×2, then `RefreshRouteToTarget; Loop` | 105, 158, 159 | charge reach (→ 160) or halted (→ restart, re-issuing the move) |
| `TurnToFaceTarget / If / WaitUntilUnitFlags 16` | 121, 122, 124, 137, 138, 141 | turn order finished |
| `QuarterTurnToTarget / Yield / WaitWhileUnitFlags 8` | 125, 126, 141, 146, 147 | models re-formed |
| `ChargeTarget`/`ChargeForward`, then `Yield / TestUnitFlags 16 / LoopIfFalse` | 160, 106 | charge ended |
| `MoveToTarget / Yield / loop { …; TestUnitFlags 16; IfNot Wait; LoopIfFalse }` | 119, 120 (shooters closing) | halted |

**Worked example (script 105, an AI regiment attacking).** Tick 0: re-forming finished. `React 1`, `MoveToTarget`:
target is 90° to the right and the unit is at rest → instant quarter turn, re-form queued, moving, follow-unit mode.
`Yield`. Later in tick 0 the formation update sets `unit_flags 0x8`; the move handler runs. Tick 1: the
`TestUnitFlags 0x8000000 / If ReformBlock` part runs, then the loop: `SetWait 10`, `IfTargetInChargeReach` (false:
re-forming, no side effect), `Wait` (10 ticks; the unit keeps walking, its models catch up, `0x8` clears with event 0x34).
Tick 11: `TestUnitFlags 16` false (moving) → next iteration: `IfTargetInChargeReach` now rewrites the single waypoint to
the target's current aim point P each time (re-aiming the walk) and is false while out of reach. After two iterations
`RefreshRouteToTarget` (no-op on one leg) and `Loop`. When the reach test passes (facing within 22.5°, single leg,
unobstructed, `d − r < 12 × s_rlmv`), `IfGotoScript 160` → `ChargeTarget` starts the charge at P; script 160 loops
`Yield / TestUnitFlags 16` until the charge ends or contact, then re-forms (163). If instead the unit halts (contact with a
friendly unit stopping it, or a refused move), `TestUnitFlags 16` → `Restart` re-runs the script from the top.

### 5. The charge aim point: far side (settles the conflict)

**Answer: `target_queries.md` §5.1 is right; the `game_rules.md` sentence ("pushed out … along the target's own
facing", "the rear/flank variants add 0x100/±0x80") has the front and rear cases swapped.** The aim point P always lies on
the **far side** of the target from the charger.

`AttackDirection(charger, target)`:
- `rel = (bearing(charger regiment position → target object centre) − target facing) mod 512`.
- `w = diag_angle = trunc(256 × atan(frontage / ranks) / π)` — the angle between the target's facing axis and its
  centre-to-front-corner diagonal (8×4: 90; 5×4: 73).

| rel | code | the charger is in the target's… | aim angle a | P lies at the target's… |
|---|---|---|---|---|
| `256 − w < rel < 256` | 0 | front arc (left half) | f_t + 256 | rear |
| `256 ≤ rel < 256 + w` | 4 | front arc (right half) | f_t + 256 | rear |
| `rel < w` | 1 | rear arc | f_t | front |
| `rel > 512 − w` | 5 | rear arc | f_t | front |
| `w ≤ rel ≤ 128` | 2 | left flank, rear half | f_t + 128 | right flank |
| `128 < rel ≤ 256 − w` | 6 | left flank, front half | f_t + 128 | right flank |
| `384 ≤ rel ≤ 512 − w` | 3 | right flank, rear half | f_t − 128 | left flank |
| `256 + w ≤ rel < 384` | 7 | right flank, front half | f_t − 128 | left flank |

Why 0/4 is the front: a charger standing in front of the target is looked at by the target, so
`bearing(charger → target) = f_t + 256`, i.e. `rel = 256`. This also agrees with the flank-test table
`[0,1,1,1,0,1,0,0]` of "Charge into the flank or rear" (rear codes 1/5 and rear-flank halves 2/3 test, front 0/4 and
front-flank halves 6/7 do not). The aim offset uses only `code mod 4`. P = `C + (trunc(SIN[a] × r / 256),
trunc(COS[a] × r / 256))` for block targets, P = C otherwise. `ChargeTarget` itself does not compute an aim: the charge
heads for the unit's first waypoint, which `IfTargetInChargeReach` has just set to P.

**Worked example.** Charger at (0,0), facing 128. Target 8 wide × 4 deep, object centre C = (200,0), facing 384 (towards
the charger); r = 53, w = 90. Bearing charger → C = 128; rel = (128 − 384) mod 512 = 256 → code **4** (front);
a = 384 + 256 ≡ 128; **P = (253, 0)**, beyond the target. The reach test gives `d − r = 253 − 53 = 200` = the centre
distance. The charge runs along +X at P; the target's front face is at x = 200 − 24 = 176, so contact (and engagement)
happens there, long before P. The "near side" reading would put P at (147,0), 29 units in front of the face, and a
charge aimed there could stop short; the far-side aim drives the charger through the face. Flank: same target turned to
facing 0 at (0,0), charger at (−150,−10): rel = 122 → code 2 (rear half of the left flank, takes the flank test), a = 128,
P = (53,0) on the target's right. Rear: charger at (−30,−150): rel = 16 → code 1, a = 0, P = (0,53) in front of it.

**Confidence: high.** Both the direction code and the aim offset were read exactly; the codes are consistent with the
independently documented flank-test table and with the bearing convention used by every other query. A runtime
observation is not needed; a Wine session watching a head-on AI charge (charger's path continuing straight through the
target's centre line rather than curving to stop at the face) would be a cheap visual confirmation.
`game_rules.md` ("Contact is resolved by rolling the tick back") has been corrected accordingly: "A charge aims at the target's
object centre pushed out by the target's bounding radius **to the far side**, along the target axis nearest the line of
approach (front charge: facing + 256; rear: facing; flanks: ± 128)."

### 6. Mapping to the implementer's engine model

The engine keeps one destination, an optional `attack_target`, facing in 1/512, a turn state, and flags. Differences from
the original, and how to map:

- **Waypoint list → one destination.** The original has a queue (`MoveToTarget` may build boundary detours). On open
  maps a single destination is enough. "Final waypoint := P" (`IfTargetInChargeReach`, `ApproachTargetInReach`) becomes
  "destination := P". With a single destination, `RefreshRouteToTarget` is a **no-op** in the original (it only acts on
  multi-leg routes or boundary crossings); implement it as a no-op (condition untouched) unless the engine adds a route
  planner. **Do not** track the target per tick: in the original the destination moves only when one of these opcodes
  runs (every 10–15 ticks in the shipped loops).
- **Follow-unit mode** (`move_state 0x1000`): add a flag "destination came from MoveToTarget"; while it is set, never
  arrive by distance.
- **Arrival:** halt when the distance to the destination is ≤ 32 at a re-plan (§1.4). An engine that re-plans every tick
  will stop at 32 units, up to ≈ 7 units farther than the original's typical stop; acceptable.
- **`TurnToFaceTarget` is a turn order that cancels movement** (destination cleared). The instant turns keep the
  destination but stop the unit (no moving state); scripts always re-issue a move afterwards.
- **`halted` (`unit_flags 0x10`)** must be implemented as in §1.3, including "set every tick while idle and not in
  melee" — script loops depend on it.
- **Charge:** `attack_target` + destination P. `ChargeForward` has no target: destination 12 × `s_rlmv` ahead, no event to
  a target at the end.
- **Flight:** `FleeBackward` sets facing instantly (no pivot), unlike the instant turns, which pivot about the block
  centre.

### 7. Open points

- 🟡 The AI-only pull-back of the first waypoint out of unit circles (3.1 step 3): which units it considers.
- 🟡 Whether a move whose detours both fail keeps walking straight (3.1 step 5).
- 🟡 The exact arrival distance in practice (§1.4 is from the rules, not measured).
- 🟡 Fear test during `CheckCollisions` probe mode (3.10).

## Part B — formation, rally and close-combat grid

Public implementation report (batch 4 of the interpreter requests, GitHub #3). Companion to
`unit_script_control.md` (condition word, stack, events, unit-flag opcodes) and `target_queries.md`. Behaviour only.

**Read in `game_rules.md` rather than re-deriving:**
- block shape, rank clamp and slot placement: "Formations" (`frontage = ceil(models / ranks)`, leftovers in front,
  `min = max(1, trunc(0.75 × √models))`, ranks clamped to `[min, models div min]`);
- how a re-form moves the figures (flat `s_rlmv / 8` mover, deceleration, slot swapping, half translation speed,
  war machines and wagons clearing the re-forming flag): "Formation changes: how the figures re-sort themselves";
- the per-model **stagger value** (`29 × n mod 65536`) and the timed-pause flag: "Models chase the unit" and the
  rout pause paragraph that follows it;
- figure actions 1–7 (1 stand, 2 idle/mark time, 3 walk, 5 weapon ready, ...): "Figure animation";
- grid membership, pairing, leaving and every caller of "leave the grid": "Engagement: battle grid and pairing",
  "Battle grid procedure", the model and unit flag list just after it;
- attack direction codes and the flank/rear table: "Charge into the flank or rear" and the direction-bonus paragraph
  of "Close combat";
- the Leadership test (uniform 2–12): "The Leadership test"; rally attempts: "Rally"; pursuit and op 0x53: "Pursuit";
- event codes: the event table in section 4 ("Event | Sent by | Meaning | Default handling").

### 0. Names used here

| Name | Meaning |
|---|---|
| `unit_flags 0x8` | **re-forming**: models are walking to new slots |
| `unit_flags 0x10` | **halted** (set by halt-and-reform, `Rally`, `InitUnit`; scripts wait for it with `WaitUntilUnitFlags 16`) |
| `unit_flags 0x80` / `0x2000` / `0x8000` | charging / broken / pursuing |
| `unit_flags 0x200` / `0x400` / `0x800` / `0x1000` | in melee / owner pairing mode / has a grid / grid owner (`game_rules.md` flag list) |
| `unit_flags 0x4000` | **re-form by walking**: while set together with 0x8, the re-form uses the ordinary rank-dependent catch-up walk instead of the flat re-form mover (see §9) |
| `unit_flags 0x20000` | a collision re-check is requested (🟡 exact use) |
| `unit_flags 0x100000` | braced against a charge |
| `unit_flags 0x1000000` | the one-tick contact latch of the engagement handshake (`game_rules.md` "What triggers engagement") |
| `unit_flags2 0x8` | **held** (Tangling Thorn: halted, cannot move, charge, turn, start a rout or pursuit, shoot, cast or change ranks; still fights; `notes/spell_area_effects.md` §3.3) |
| `move_state 0x1` | a re-form is pending; it is carried out at the unit's next movement update |
| `move_state 0x40` / `0x100` / `0x200` | charge movement / rout movement / pursuit movement |
| `move_state 0x800` | rally attempts enabled (`game_rules.md` "Rally") |
| `current ranks` / `s_rnks` | the rank count the block is laid out with / the script's rank count of the unit (from the battle file) |
| model "timed pause" | model flag `0x4` with a tick countdown: the model does not walk until the countdown reaches 0 |

**`current_target` and `engaged_enemy` are one field in the original.** Every opcode below that "changes the
opponent" changes the unit's current target. An engine that keeps them apart must update both.

**Condition**: "untouched" means bit 2 of the condition word keeps its previous value (see `unit_script_control.md`
§1). None of these opcodes yield except `Rally` on refusal (§4).

### 1. `ReformToScriptRanks` 0x46 (401 uses)

(a) 1 word, no operand.

(b) Asks for `s_rnks` ranks through the **same check and clamp as the player's rank orders**: refused (nothing at
all happens) if the unit is in rout movement (`move_state 0x100`), held (`unit_flags2 0x8`) or charging
(`unit_flags 0x80`). Otherwise `current ranks := clamp(s_rnks, min, models div min)` and the re-form is carried out
**at once**:
- the pending re-form request is consumed;
- if the unit **has a grid** (`unit_flags 0x800`) or has no models, nothing else happens: the new rank count is
  stored, but no slots are recomputed and no flag is raised (the block re-forms at the next re-form after it
  leaves the grid);
- otherwise the formation-kind layout runs (block, war machine, monster, wagon, `game_rules.md` "Formations"):
  `frontage` is recomputed, every slot is reassigned to the nearest model, and a block or monster raises
  `unit_flags 0x8` (re-forming). War machines and wagons clear it instead.

Facing, position, destination, target, `engaged_enemy`, grid membership: unchanged. It does **not** halt the unit:
a unit that is moving keeps moving (at half speed while re-forming). Condition untouched.

(c) The layout is immediate; the models then walk to the new slots over the following ticks; `unit_flags 0x8`
clears when the last one settles (§9).

(d) No target: irrelevant. In a grid: ranks stored, no layout (see above).

(e)

| Before | Instruction | After |
|---|---|---|
| block, 18 models, `s_rnks` 4, current ranks 6, not in a grid, not charging | `ReformToScriptRanks` | current ranks 4, frontage 5 (rows 5, 5, 4, 4), `unit_flags \|= 0x8`, slots reassigned, condition unchanged |
| block, 18 models, `s_rnks` 8 | `ReformToScriptRanks` | current ranks 6 (clamped to 18 div 3), frontage 3 |
| block in a grid (`unit_flags 0x800`), 24 models, `s_rnks` 4, current ranks 3 | `ReformToScriptRanks` | current ranks 4, slots and flags unchanged |
| charging unit (`unit_flags 0x80`) | `ReformToScriptRanks` | no change |

### 2. `SetRanks n` 0xE6 (2 uses, both in BF004_3)

(a) 2 words; operand `n` = rank count (shipped: 6).

(b) Acts only if the unit has models and is not in rout movement, not held and not charging (the same three
refusals as §1). Then `current ranks := n` **without the clamp** (an engine may clamp to 1–8, the range battle
files allow; shipped scripts only use 6), and a re-form is requested (`move_state 0x1`). The layout itself is
done at the unit's **next movement update**, exactly as in §1 (skipped while the unit has a grid). Nothing else
changes; condition untouched.

(c) Deferred: the re-forming flag rises only after the movement update. Both shipped uses are
`SetRanks 6; Yield; WaitWhileUnitFlags 8` — the `Yield` lets the update raise the flag before the wait reads it.
An engine that runs the re-form immediately is equivalent for these scripts.

(d) No target: irrelevant. Refused: no change.

(e)

| Before | Instruction | After |
|---|---|---|
| block, 16 models, current ranks 4, idle | `SetRanks 6` | current ranks 6, re-form pending; after the next movement update frontage 3 (rows 3, 3, 3, 3, 2, 2) and `unit_flags 0x8` |
| block, 16 models, held (`unit_flags2 0x8`) | `SetRanks 6` | no change |
| unit with 0 models | `SetRanks 6` | no change |

### 3. `ResetModelAnimations` 0x47 (83 uses)

(a) 1 word, no operand. (The name is historical: the opcode staggers the models, it does not choose an animation.)

(b) Every model of the unit gets the **timed pause**: model flag `0x4` set and a countdown of
`(stagger value & 15) × 2 + 2` ticks — **2 to 32 ticks**, even values, different for neighbouring models. While the
countdown runs the model does not walk. When it reaches 0 the flag clears and the model's action is set to
**3 (walk)** under the ordinary catch-up walk, or **2 (idle / mark time)** under the flat re-form mover. A model
still pausing counts as "not settled", so `unit_flags 0x8` (and 0x4000) cannot clear before every pause has run out.
No unit flag, formation, facing or grid change; condition untouched.

Side effect worth keeping: models with flag `0x4` are not "fleeing" for a pursuer's automatic hits
(`game_rules.md` "Pursuit": automatic hits on models that lack `0x4`).

A later halt-and-reform (and therefore `Rally`) cancels all pauses (flag and countdown cleared).

(c) Immediate set-up, effect over 2–32 ticks.

(d) No target / in a grid: same effect (🟡 whether the close-combat model mover honours the pause; no shipped
script uses it in melee).

(e) Shipped idiom (38 mission uses, plus library script 170): `TeleportToNode n; ReformToScriptRanks;
ResetModelAnimations; [Yield;] WaitWhileUnitFlags 8` — reinforcements appear at a node and fall into line one by one.

| Before | Instruction | After |
|---|---|---|
| model with stagger value 0x0007 | `ResetModelAnimations` | flag `0x4`, countdown 16 |
| model with stagger value 0x001D | `ResetModelAnimations` | flag `0x4`, countdown 28 (29 & 15 = 13) |
| model with stagger value 0x0010, re-forming | `ResetModelAnimations` | countdown 2; on tick 2 the flag clears and the model starts the flat re-form walk with action 2 |

### 4. `Rally` 0x5A (180 uses, all library: 154, 163, 170)

(a) 1 word, no operand.

(b) In this order:
1. `unit_flags` loses charging `0x80`, broken `0x2000`, pursuing `0x8000`, braced `0x100000` and the contact latch
   `0x1000000`; gains halted `0x10`, re-form-by-walking `0x4000` and collision re-check `0x20000`.
2. `move_state` loses charge movement `0x40`, `0x80` (🟡), rout movement `0x100`, pursuit movement `0x200` and
   rally attempts `0x800`.
3. **Halt and re-form**: the unit stops (destination and route cleared — in the engine model, clear the single
   destination), every model loses its timed pause and its "at rest" flag (so all of them re-check their slots),
   and the other movement states (`move_state` 0x2, 0x4, 0x8, 0x400, 0x1000; turning, wheeling, ...) are cleared,
   as are `unit_flags2` bits 0x2 and 0x4 (🟡 meaning).
4. `current ranks := clamp(s_rnks, ...)` as in §1. If that is accepted, the layout runs at once (block/monster raise
   `unit_flags 0x8`, so with step 1 the unit is now `0x4008`), and the unit's looping sound effect, if one is
   playing, is stopped.
5. If step 4 is **refused** (only possible while held, `unit_flags2 0x8`, because steps 1–2 removed the other two
   reasons): the script **yields without advancing**, so `Rally` runs again from step 1 next tick, until the hold
   ends. In the original the current rank count is left at 0 meanwhile; an engine should keep the old count (no
   layout uses it while held).

It does **not** leave the grid, change the target / `engaged_enemy`, change facing, or touch the condition. A broken
unit has already left its grid when it routed; library script 154 calls `LeaveSharedGrid` first where the unit may
still be on one.

(c) Flags immediate; the re-form takes the following ticks. Because `0x4000` is set, the figures walk to their
slots with the **ordinary catch-up walk** (rank-dependent speed with ramp-up, `game_rules.md` "Models chase the
unit"), not the flat re-form shuffle, and the unit's speed is not halved. When every model has settled, `0x8` and
`0x4000` clear together and event 0x34 is sent to the unit (§9).

(d) No target: irrelevant. Not broken: the same steps (it is also used as "stop, forget charging/bracing and
re-form" by library 154 after an enemy routs, and by 170).

(e)

| Before | Instruction | After |
|---|---|---|
| block, 16 models, `unit_flags` 0x2000 (broken), `move_state` 0x900 (rout movement + rally attempts), `s_rnks` 4, fleeing | `Rally` | `unit_flags` = 0x24018 (halted, re-forming, re-form by walking, collision re-check; broken clear); `move_state` 0; no destination; current ranks 4, frontage 4; models walk back into the block; pc + 1 |
| same unit but held (`unit_flags2 0x8`) | `Rally` | flags as above, no layout, tick ends, **pc unchanged** |
| unit in melee after its enemy routed (library 154: `LeaveSharedGrid; Rally`) | `Rally` | grid already left; braced/charging cleared; halted; re-forms to `s_rnks` |

### 5. `FlankRearTest` 0x5B (45 uses, library 152 on event 0x08)

(a) 1 word, no operand. Must run inside an event handler: it reads the **current event's sender**.

(b) Computes the attack direction code of the sender (the charger) against this unit **now** (charger position
against the unit's facing, as in "Charge into the flank or rear"; not the stored `attack_dir`). Codes 1, 5 (rear
arc) and 2, 3 (rear half of either flank) require a Leadership test at modifier 0; codes 0, 4, 6, 7 do not.
- no test needed, or test passed → condition **true**, nothing else;
- test failed → event **0x0C** (rout) is queued to the unit itself and condition **false**. The rout happens when that
  event is handled (library 151/153/154: `RoutAllowed` — not broken, not `CantBreak` — then the rout script).

No formation, facing, flag or grid change by the opcode itself.

(c) Immediate (one random number only when a test is required).

(d) No event sender: not reachable in shipped scripts (only `CaseEvent 8`); an engine should treat it as "no test,
condition true". Not in a grid: no difference (event 0x08 is sent at contact, before or as the grid is joined).

(e)

| Before | Instruction | After |
|---|---|---|
| event 0x08 from a charger at direction code 0 | `FlankRearTest` | condition true, no roll |
| code 1, leader Ld 7, roll 9 | `FlankRearTest` | event 0x0C queued to self, condition false |
| code 2, Ld 7, roll 5 | `FlankRearTest` | condition true |

### 6. `LeaveSharedGrid` 0x57 (506 uses) and `LeaveGrid` 0x59 (1 use)

(a) 1 word each, no operand.

(b) Both run the ordinary **leave the grid** procedure of `game_rules.md` ("Leaving"); the name "shared" is
historical — any grid is left:
- every model of the unit is unpaired: its cell is released, it loses "has an opponent", "reserve",
  "in hand-to-hand" and "on the grid" (`0x4000`, `0x8000`, `0x10000`, `0x20000`) and its opponent link; an enemy
  model that was paired with it loses its own pairing flags and switches to action 5 (weapon ready);
- the unit loses in melee `0x200`, owner pairing `0x400`, has a grid `0x800` (and grid owner `0x1000`); the grid's unit
  count drops by one;
- if the unit owned the grid, ownership passes to the first unit (in unit-array order, any side) still on it; if
  none is left the grid record is freed;
- if exactly one unit is left and it is a placed building / furniture pseudo-unit (side code 0x20), it leaves too.

Then both clear the contact latch `0x1000000`, so a later overlap can start a fresh engagement handshake.

**Not done:** no event to anyone, no re-form, no facing change, `current_target`/`engaged_enemy` kept, `attack_dir`
kept. The opponent learns through the **per-tick pairing**: when it has no enemy left on the grid it leaves too
and gets event 0x19 ("opponent gone") — `game_rules.md` caller table. The leaving unit's models are no longer
driven by the grid; with no re-form pending they walk back to their old slots under the catch-up walk. Shipped
scripts therefore follow the opcode with `ReformToScriptRanks` or `Rally`, or switch to 163.

Difference between the two:

| | in a grid (`unit_flags 0x800`) | not in a grid |
|---|---|---|
| `LeaveSharedGrid` | leave, **condition true** | nothing, **condition false** |
| `LeaveGrid` | leave, condition untouched | only the latch is cleared; condition untouched |

(c) Immediate.

(d) No target: irrelevant (the target is not read). Not in a grid: see the table.

(e)

| Before | Instruction | After |
|---|---|---|
| A and enemy B alone on grid G, B owner | A: `LeaveSharedGrid` | A: `0x200/0x400/0x800` clear, models unpaired, target still B, condition true; G holds B only; on the next pairing pass B finds no enemy, leaves G (freed) and receives event 0x19 |
| A owner of G with enemy B and furniture F | A: `LeaveSharedGrid` | ownership passes to whichever of B/F comes first in the unit array; G count 2, nobody else leaves |
| A not on a grid | `LeaveSharedGrid` | no change, condition false |
| A owner of G, only furniture F left after A | A: `LeaveGrid` | F becomes owner, is alone and is furniture → F leaves too, G freed; condition unchanged |

### 7. `SwitchOpponentInGrid` 0x55 (94 uses)

(a) 1 word, no operand.

(b) Only for a unit **in melee** (`unit_flags 0x200`). It looks for another enemy unit on the same grid: the
**first in unit-array order** that is alive, is not the current target, has a grid and it is this grid, is on the
opposite side (side bit 7 differs) and is not a furniture pseudo-unit (side code 0x20). No distance, threat or
strength tiebreak; broken units are not excluded.
- Found: the unit's models that were paired with models of the old target are unpaired (lose `0x1000`, `0x4000`,
  `0x10000`; those still holding a cell become **reserves** `0x8000`); `attack_dir := 0`; owner pairing mode `0x400`
  is cleared (joiner pairing); `current_target`/`engaged_enemy :=` the new unit; **condition true**. The old
  target's own models are left to the per-tick pairing, which re-pairs everyone (`game_rules.md` "Battle grid
  procedure"). No event is sent.
- Not found: nothing changes, **condition false**.
- Not in melee: nothing changes and the **condition is untouched**.

This is the same switch that op 0x53 makes when the unit's opponent routs (`game_rules.md` "Pursuit").

(c) Immediate; the actual re-pairing of models happens on the following pairing passes.

(d) No target: the search still runs (it just excludes nothing). Not in a grid: no-op, condition untouched.

(e)

| Before | Instruction | After |
|---|---|---|
| A in melee with building F (target F); enemy regiment C also on the grid | `SwitchOpponentInGrid` | target C, `attack_dir` 0, `0x400` clear, A's models that fought F unpaired/reserve, condition true |
| A in melee with B, nobody else on the grid | `SwitchOpponentInGrid` | no change, condition false |
| A not in melee, condition true from an earlier test | `SwitchOpponentInGrid` | no change, condition still true |

### 8. `IfEngagedWithKind mask` 0xE0 (94 uses)

(a) 2 words; operand = map-object footprint flag mask. Every shipped use passes **128 (0x80 = building / furniture
footprint)**.

(b) Condition := the unit is in melee (`unit_flags 0x200`) **and** has a current target **and** the target's map
object footprint flags share a bit with the mask. It writes false first, so every path sets the condition. No
other effect.

(c) Immediate. (d) No target or not in melee → false.

(e)

| Before | Instruction | After |
|---|---|---|
| in melee, target = a placed building | `IfEngagedWithKind 128` | condition true |
| in melee, target = an enemy regiment | `IfEngagedWithKind 128` | condition false |
| not in melee, target = a building | `IfEngagedWithKind 128` | condition false |

Idiom (library 152/155 on event 0x0A "engaged", 4 mission copies): `IfEngagedWithKind 128; If;
SwitchOpponentInGrid; EndIf; SwitchScript 165` — a unit that bumped into a building fights a real enemy on the same
grid instead, if there is one.

### 9. How scripts learn "re-formed", "rallied", "left combat"

None of the opcodes above waits. Scripts poll unit flags with the unit-flag opcodes of `unit_script_control.md` §7, which test **any** bit of the mask, and with events.

**Re-formed.**
- Set: `unit_flags 0x8` rises when a block or monster layout runs — at once for `ReformToScriptRanks` and `Rally`,
  at the unit's next movement update for `SetRanks` (and any other queued re-form request). `Rally` also sets
  `0x4000`.
- Cleared: each tick the re-form movers walk the models. With `0x8` alone (flat mover), `0x8` clears on the first
  tick on which no model moved and no model is still pausing. With `0x8 | 0x4000` (catch-up walk), both clear together
  on the first tick on which every model is settled. In both cases event **0x34** is then sent to the unit (the same
  code as "destination reached"; the library ignores it, 4 mission scripts handle it).
- Never set: war machines and wagons (their layout clears `0x8`) and units in a grid (no layout), so a wait passes at
  once for them.
- Idioms: `WaitWhileUnitFlags 8` (559 uses) and `WaitWhileUnitFlags 0x4008` (135, after `Rally` or before an order is
  accepted). Typical placement: right after the restart point (`SetRestartPoint; WaitWhileUnitFlags 8`), after
  `HaltAndReform`, and after a re-form opcode — with a `Yield` in between when the re-form is deferred (`SetRanks`).

**Halted.** `unit_flags 0x10` is set by halt-and-reform, `Rally` and `InitUnit`. Movement loops end with
`WaitUntilUnitFlags 16` (364 uses) or `TestUnitFlags 16; LoopIfFalse` (555 `TestUnitFlags 16`).

**Rallied.** The game's rally attempt (`game_rules.md` "Rally") sends event **0x10**; library 152 handles it with
`React 17` (the "Re-group!" bark) and `SwitchScript 163`. Broken `0x2000` is cleared by the `Rally` opcode in 163,
not by the event, so a script that tests `TestUnitFlags 0x2000` sees "rallied" from the tick 163 starts. Library
handlers use `TestUnitFlags 0xa000` (broken **or** pursuing, 44 uses) to choose between re-forming and keeping on.

**Left combat.**
- Self-initiated: `LeaveSharedGrid` gives the condition directly (true = "I was on a grid and have left it").
  `unit_flags 0x200`/`0x800` are clear from that instruction on.
- Initiated by the game: event **0x19** (opponent gone; the game has already removed the unit from the grid) and event
  **0x30** (alone on a grid / disengaged after a withdraw). Library 152: on 0x19 `DropTarget; If; [TestUnitFlags 0x8000; If; React 17; EndIf]; SwitchScript 163; EndIf` —
  whenever a target was actually dropped (the unit is not broken) it switches to 163 and re-forms; only the bark
  depends on pursuing (see the correction below); on 0x30 `LeaveSharedGrid; TestUnitFlags 0xa000; IfNotSwitchScript 163` (re-form unless
  broken or pursuing). Rout leaves the grid by itself.
- In melee a unit runs script 165, `PushPC; Yield; Loop` — an endless idle loop: **leaving combat is always
  event-driven**, never detected by polling.

#### Worked example: rally (library script 163)

```
163:  0 Rally
      1 Yield
      2 WaitWhileUnitFlags 8
      4 ReformToScriptRanks
      5 Restart
```

A 16-model block (`s_rnks` 4) routed, has `move_state 0x800` (rally attempts on) and no enemy within 160.

| Tick | What happens | Unit state after |
|---|---|---|
| T | rally test passes; event 0x10 queued | broken, fleeing |
| T (events) | handler 152: `React 17`, `SwitchScript 163` (applied at `ReturnInterrupt`) | script 163, pc 0 |
| T+1 | `Rally`: flags and movement states cleared, halted, ranks 4, block laid out; `Yield` | `unit_flags` 0x10, 0x4000, 0x20000, 0x8; not broken; no destination |
| T+2 … T+k | `WaitWhileUnitFlags 8` holds; models walk back with the catch-up walk | `0x8 \| 0x4000` |
| T+k | last model settles: `0x8`, `0x4000` clear, event 0x34 | |
| T+k+1 | wait passes; `ReformToScriptRanks` re-lays the block at the current facing (flat mover, models almost on their slots); `Restart` | back in the unit's main script at its restart point, which normally starts with `WaitWhileUnitFlags 8` |

#### Other shipped idioms

- **Pursuit start (164)**: `LeaveSharedGrid; ReformToScriptRanks; React 3; ...; StartPursuit` — leave, re-form (now
  possible because the grid is gone), then pursue.
- **Static unit whose enemy routed (154, events 0x0F and 0x09)**: `EnemyRoutedStatic; If; LeaveSharedGrid; Rally; EndIf`.
- **Mission watchdog (BF021)**: every 60 ticks `IfEngagedWithKind 128; If; SwitchOpponentInGrid; IfNot; LeaveGrid;
  SendEventSelf 16; EndIf; EndIf` — a unit stuck fighting a building switches to a real enemy, or leaves the grid and
  sends itself the rally event so 152 switches it to 163 to re-form.
- **Reinforcement entry (BF008 and 37 others)**: `ScatterModelsToNode; SnapModelsToFormation; TeleportToNode n;
  ReformToScriptRanks; ResetModelAnimations; WaitWhileUnitFlags 8`.
- **Scripted rank change (BF004_3)**: `TeleportToNode 12; SetRanks 6; Yield; WaitWhileUnitFlags 8`.

### 10. Notes for the engine model

- **One destination**: halt-and-reform (inside `Rally`) clears it. The other opcodes leave it alone — a moving unit
  keeps its destination through `ReformToScriptRanks`.
- **`reforming`** = `unit_flags 0x8`. Add a second bit (or an enum) for "re-form by walking" (`0x4000`): set by `Rally`,
  cleared together with `reforming`. Without it a rallied unit re-forms with the flat shuffle and half speed, which is
  visibly different but harmless for script flow.
- **`routing`** = broken `0x2000`; **`braced`** = `0x100000`; **`in_melee`** = `0x200`. Grid membership (`0x800`) is a
  separate fact; `LeaveSharedGrid`/`LeaveGrid` test and clear it, `SwitchOpponentInGrid`/`IfEngagedWithKind` test
  `in_melee`.
- Keep **two rank counts**: the current one (laid out) and the script's `s_rnks` (what `ReformToScriptRanks` and `Rally`
  restore).
- `current_target` and `engaged_enemy` must be the same value after `SwitchOpponentInGrid`.
- `whshr/battle_grid.py` should expose the public "leave" procedure once and let both opcodes call it; the opponent's
  departure and its event 0x19 come from the ordinary per-tick pairing, not from the opcode.

### Correction to `game_rules.md` (applied)

The `DropTarget` paragraph of `game_rules.md` says that on event 0x19 "a unit that was not pursuing just carries on
with no target". The library handler (152, words 37–49; `If` is nesting-aware) is
`DropTarget; If; TestUnitFlags 0x8000; If; React 17; EndIf; SwitchScript 163; EndIf`: the `SwitchScript 163` is
outside the inner `If`, so **every** non-broken unit that loses its opponent (and had a target) switches to the rally
/ re-form script 163 — halt, clear charging/bracing, re-form to `s_rnks`, then `Restart`. Only the "Re-group!" bark
is limited to pursuers. This matches the event table's "0x19 ... clear target, re-form".

### Uncertainties

- 🟡 `move_state 0x80` cleared by `Rally` (name unknown); `unit_flags 0x20000` exact use.
- 🟡 whether the close-combat model mover counts down `ResetModelAnimations` pauses (no shipped use in melee).
- 🟡 tick ordering of the deferred `SetRanks` re-form relative to the script in the same tick (shipped scripts are
  insensitive to it because they `Yield` first).
