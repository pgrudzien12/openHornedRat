# BF015/BF017 siege gate, node placement, the "carried" script flags, steering arrival and neutral speed

Public implementation report (batch 15 of the interpreter requests, from a BF015 "Grumm's Gate" playtest). Behaviour
only; states by name; numbers only for script operands, event codes, battle-file data and gameplay constants.

Builds on: `battle_end_objectives.md` §5.1 (battle state, H), `movement_formation.md` §1.4 (arrival), §3.1 (point
move), `reform_while_moving.md`, `game_rules.md` "Models chase the unit", "Speed stat", "Mounts",
`hidden_reserves_off_field.md` §4 (teleport), `deployment.md` §1.3 (minimap), `battle_viewer.md` (mesh scale),
`spell_transport_visuals.md` (Flying Bower).

---

## 0. Shared facts

- **Battle state = the control piece's own state.** Gate pieces animate in the **display step**, which runs once per
  displayed frame. In normal play that is exactly **once per battle tick, right after the tick's unit updates** (the
  100 ms timer runs the tick and then repaints at once). 🟡 The display step also runs on extra repaints (window
  exposure) and while the battle is paused, so a gate keeps animating during a pause. An engine should step the gate
  once per tick, after the units.
- **The gate pieces have no footprint.** Gate and door furniture is visual only: no collision, no route obstacle and
  no sight blocker. Blocking around a gate comes only from the battle file's boundaries, and no gate state changes a
  boundary.

---

## Q1. Control pieces

### 1.1 Which piece is which

| Battle | Control piece (`.BTS` `placefurniture`) | Animation |
|---|---|---|
| BF015, BF017, DB015 | `ZhufWallEnt` at (920, 2040), dir 0 | two swinging doors (`ZhufWallDoorL/R`) |
| BF038 | `NiteUnderwayEnt` at (560, 1600), dir 0 | two swinging doors (`NiteUnderwayDrL/R`) |
| BF037 | `PortcullisEnt` at (400, 1760), dir 384 | one sliding portcullis (`PortcullisDoor`) |
| BF040 | `MoleHole0` at (240, 1520), dir 384 | mesh-swap sequence (mole hole opening) |

The door pieces are **not placed by the battle file**. The control piece creates them itself (they only need to be
listed in `loadfurn:`) and attaches them to hinge points fixed to the piece.

### 1.2 Swinging doors (`ZhufWallEnt`, `NiteUnderwayEnt`)

**State machine** (per display step, normally per tick after the units):

| State | Meaning | What the step does |
|---|---|---|
| 1 | closed, idle (set at load by the piece, and again by BF015/BF017 script 1) | nothing |
| 2 | "open" requested (a script's `SetBattleState 2`) | start the opening animation, show its first frame, state := **3** in the same step |
| 3 | opening | advance the animation; when it has ended, state := **4** |
| 4 | open | nothing |
| 5 | "shut" requested (the game's node-14 rule or a script) | start the closing animation, show its first frame, state := **6** in the same step |
| 6 | closing | advance; when ended, state := **7** |
| 7 | shut | nothing |

**(e) For `ZhufWallEnt`, 7 is set at the end of the closing.** The 🟡 in `battle_end_objectives.md` §5.1 is resolved:
the swinging-door gates go 5 → 6 (closing) → 7 (shut). The portcullis is the other way round (§1.3).

**Timing (a, b).** Both animations show 16 frames. Each frame is held for 3 steps, then one extra step reaches the end
marker, then one more step reports the end. With T = the tick in which the script sets 2:
- tick T: scripts that run after the setter in the same tick still read **2**. The display step at the end of tick T
  starts the opening (frame 0) and sets **3**.
- frame k (k = 0…15) is shown from the end of tick T + 3k. Frame 15 is shown at T + 45.
- the end of tick T + 49 sets **4**. Scripts read 4 from tick T + 50: **≈ 49 ticks (4.9 s)**.
- closing is the same with the frames in reverse order. 5 at tick T′ → 6 at the end of T′ → 7 at the end of T′ + 49.
- 🟡 5 set while opening (state 3) starts the closing at once from its first frame (doors snap fully open, then
  close). Not used by the shipped scripts.

**What the doors do (c).** Each door is attached at a **hinge point** fixed to the gate piece (piece model frame, y up,
in mesh units; 1 mesh unit = 8 world units, `battle_viewer.md`):

| Piece | left-door hinge (x, y, z) | right-door hinge (x, y, z) |
|---|---|---|
| `ZhufWallEnt` | (2.5, 0, −5.0) | (17.5, 0, −5.0) |
| `NiteUnderwayEnt` | (−15.0, 0, 2.5) | (15.0, 0, 2.5) |

Each door's mesh hangs from its hinge with no further offset and **rotates about the vertical axis through its
hinge**. The two doors rotate in **opposite senses** (mirror images). The angle is **stepped**, not interpolated:
frame k = k / 63 of a full turn (5.71° per frame). It runs from 0° (closed, frame 0) to 15/63 turn ≈ 85.7° (open,
frame 15), changing every 3 ticks. 🟡 Which sense is "outward" was not checked by eye; the left door turns by −angle
and the right by +angle about the up axis in the piece frame.

**(d) Blocking:** none, before or after opening (§0).

### 1.3 Sliding portcullis (`PortcullisEnt`, BF037)

| State | Step |
|---|---|
| 1 | set at load; nothing |
| 2 | door placed at the start position, state := 3 |
| 3 | each step a counter += 1; while it is below 30 the door moves by one step; at 30 → **4** |
| 5 | door placed at the "closing start" (= open) position, state := **7** at once |
| 7 | as 3, moving back; at 30 → **6** |

The door slides **straight up by 10 mesh units** (80 world units) from the closed position (0, 0, 0) to (0, 10, 0):
linear, 29 equal steps of 10/29, opening ≈ 30 ticks. **Here 7 is set when the closing starts**, and the state is 6
once it is closed. So in BF037 the H rule would see 7 during the closing. (BF037 lists no H; the 7 matters only to
scripts and to the siege Z rule.)

### 1.4 Mole hole (`MoleHole0` / `MoleHole8`, BF040)

A different machine. State 0 at load (idle). A script's 1 starts a sequence that swaps the piece's mesh through the
`MoleHole1…8` shapes (state 2), and the end of the sequence sets **3**. No doors.

### 1.5 BF015 / BF017 test vectors

Scripts 0 (the NPC column) and 1 (the first wagon) in both battles: `IfInNodeArea 12` loop, then
`IfBattleState 1; If; SetBattleState 2; PlaySound 11 0; SendEventToUnitId 24 51; SendEventToEnemySide 55; EndIf`.

| Before | Step | After |
|---|---|---|
| load | piece init | state 1; doors at 0° |
| script 1 reaches node 12 area at tick T, state 1 | its `SetBattleState 2` | state 2. Later units in tick T read 2, so their `IfBattleState 1` is false (only the first arrival opens) |
| end of tick T | display step | state 3, frame 0 (0°) |
| end of tick T + 3 | display step | frame 1 (5.71°) |
| end of tick T + 45 | display step | frame 15 (85.7°) |
| end of tick T + 49 | display step | state 4 |
| state 4, the game's node-14 rule (`script_behaviours.md` 19/20) fires at tick U | — | state 5 |
| end of tick U | display step | state 6, frame 15 of the closing (85.7°) |
| end of tick U + 49 | display step | **state 7**, doors at 0°; H met at the next segment boundary |

---

## Q2. `TeleportToNode` (0x49) and `PlaceAtNode` (0x4A)

Both take a node **list position** (`scatter_models_to_node.md`), and both do nothing (no condition written, next
instruction) if the node is inactive. **Neither uses the node radius** and neither scatters anything.

**Models are stored relative to the unit position** (`game_rules.md` "Models chase the unit"). The two opcodes differ in
exactly that respect:
- `PlaceAtNode` moves the unit position **without** compensation, so every model is **carried instantly** and then
  snapped into its slot. No figure walks from where it was.
- `TeleportToNode` moves the unit position **with** the compensation (every model's stored offset is shifted back by
  the same amount), so every model **keeps its world position**. The figures then walk to their new slots with the
  ordinary catch-up walk.

| | `TeleportToNode n` | `PlaceAtNode n` |
|---|---|---|
| unit position | := node (x, y) | := node (x, y) |
| facing | := node `dir` | := node `dir` |
| models | **stay where they are in the world** (compensated); each model's "settled in its slot" state is cleared, so all of them walk to their slots around the node | carried, then **snapped into their slots** (each model is put on its current slot offset at once, drawn facing := the unit facing, and the rest action is broadcast) |
| re-form | none (scripts follow it with `ReformToScriptRanks`, `movement_formation.md` §3) | it queues a re-form at the current ranks (unless fleeing, held or charging), but its own snap **cancels** it (the re-forming state and the queued re-form are cleared), as `InitUnit` does |
| footprint | rebuilt at the new place; the collision re-check is switched on | rebuilt |
| hidden state | unchanged | unchanged |

**The slot offsets are the ones from the last layout**, built for the facing the unit had then. After `PlaceAtNode`
to a node whose `dir` differs from the old facing, the block stands at the node in the old arrangement until a
re-layout. That is why BF015 script 0 follows it with **`ReformBlock`**, which lays the formation out for the new
facing and walks the models (short distances) into the new slots. `WaitWhileUnitFlags 0x4008` waits for that.

**BF015 script 0.** The NPC units start at (1400–1900, 1830–1980), dir 26. Node 15 is (507, 24), dir 26, radius 137.
After `PlaceAtNode 15` the whole block stands at (507, 24) in formation **on the same tick**, so nothing is seen
walking across the map. Because node 15's dir equals the units' dir, `ReformBlock` changes little. An engine that
walks the figures from the start position to the node is wrong.

| Before | Instruction | After |
|---|---|---|
| unit at (1642, 1826) facing 26, models in slots; node 15 = (507, 24) dir 26 | `PlaceAtNode 15` | unit at (507, 24) facing 26; every model on its slot around (507, 24); not re-forming; footprint at the node |
| same, node dir 128 | `PlaceAtNode n` | unit facing 128; models on the old slot offsets (still arranged for facing 26) until `ReformBlock` |
| unit at (100, 100), models in slots | `TeleportToNode n` (node (500, 500), dir 0) | unit at (500, 500) facing 0; the models still at (≈100, ≈100) in the world, not settled; they walk the ~566 units to their slots (catch-up walk) |
| inactive node | either | nothing |

---

## Q3. Script unit flags 0x10000000 and 0x20000000

Shipped uses: `SetUnitFlags 0x30000000` / `ClearUnitFlags 0x30000000` (BF015 and BF017 script 0: set before
`WaitForBattleStart`, cleared right after `PlaceAtNode 15`); `SetUnitFlags 0x20000000` (BF015/BF017 scripts 0 and 1
before the final `MoveToNode 13`, and library script 170 "leave the battle"); `TestUnitFlags 0x20000000` (BF015
script 30, BF017 script 31: `If; RemoveFromBattle`). `InitUnit` keeps both states.

| Script bit | State name (suggested) | Effect |
|---|---|---|
| **0x10000000** | **not shown / cannot engage** | The unit's models and its banner are **not drawn**: they are taken off the display as for an off-screen unit, and the "drawn this frame" state stays off. So it has no banner to pick in the main view and its barks are silent (React needs "drawn"). In the contact handler the unit can neither engage nor **be engaged** (`script_queries.md` §6 item 1, the cannot-engage state of `game_rules.md` R70). |
| **0x20000000** | **leaving / no minimap marker** | The unit's **minimap marker is not drawn** (`deployment.md` §1.3: either this bit or the "leaving the table" state). Scripts use it as an "on my way out" mark that script 30/31 tests before `RemoveFromBattle`. |
| both together | **carried by a Flying Bower** | This is the state Flying Bower gives its passengers (`spell_transport_visuals.md`). While a Bower transport is in flight, the game moves **every** unit that has both states along with it. 🟡 Quirk: a BF015/BF017 NPC unit waiting off-field with both bits set would be carried too if a Bower flies during that wait. An engine should limit carrying to the real passengers. |

**Not affected** by either bit (no reader exists): spotting and visibility (`IsVisible`), threat and target picking
by enemies, missile and spell targeting, the collision pass and push-apart, route obstacles, HUD previous/next
cycling, and objective counts. An unshown unit is still a solid, targetable unit. In BF015 that does not matter,
because the column waits off-field outside the battle area.

**0x400000** is never touched by shipped scripts (no `SetUnitFlags`/`ClearUnitFlags`/`TestUnitFlags` operand
contains it). It is the game's own **leaving the table** state, set when a fleeing unit reaches the edge (event 0x0E,
`game_rules.md` caller table). Scripts can only see it through a `TestUnitFlags` operand that includes it, and none
does.

---

## Q4. Arrival while steering round an obstruction

**Correction to `movement_formation.md` §1.4.** The arrival test (`d ≤ 32` → next waypoint or halt) and the wheel test
always use **the distance to the current waypoint**. Steering only changes the **re-plan countdown**: while steering,
the countdown is `min(2 × D, 150)` with D = the steer distance, instead of `min(2 × d, 150)`. The distance to the steer
point is never compared with 32.

So in the BF015 case the original **does not halt**. Ceridan, moving from (748, 890) to node 12 (1000, 1940), steers
round the wagon: the steer distance falls to 31, but d to node 12 is still about 1080, so the unit keeps moving and
re-plans sooner (countdown 62 instead of 150). It halts only when it is within 32 of (1000, 1940), which is inside
node 12's radius 47, so the `IfInNodeArea 12` poll succeeds. Nothing needs to restart the move. An engine that halts
on the steer distance leaves script 0 waiting forever.

| Before (plan step) | d (to waypoint) | steering, D | Result |
|---|---|---|---|
| not steering | 33 | — | keep moving, countdown 66 |
| not steering | 32 | — | last waypoint → halt and re-form; otherwise next waypoint |
| steering | 1080 | 31 | keep moving, countdown **62** |
| steering | 30 | 120 | **halt** (or next waypoint), whatever D is |
| follow-a-unit route with one waypoint | 10 | — | keep moving (no arrival by distance) |

---

## Q5. Neutral speed

Confirmed: `s_rlmv = trunc(2.4 × M′) + 4` when the unit's side code is **0x40–0x5F** (neutral/NPC) at the moment the
unit is **created** (battle load or spawn), otherwise `trunc(4.8 × M′ + I) / 2`. M′ follows the same mount rule as for
every unit (the mount's M when the model is marked mounted, otherwise the model's own M). It is computed once at
creation; a later `SetSide` does not recompute it.

All BF015 NPC units have side codes 64–83 (0x40–0x53), Ceridan included (70). Units that the campaign substitutes into
an NPC slot keep whatever side code the slot's unit has at creation.

| Unit | M′ | s_rlmv |
|---|---|---|
| BF015 wagon (`s_move` M = 2), not marked mounted | 2 | trunc(4.8) + 4 = **8** |
| neutral, M′ = 4 | 4 | trunc(9.6) + 4 = 13 |
| neutral, M′ = 5 | 5 | 12 + 4 = 16 |
| player/enemy, M′ = 4, I = 3 | — | trunc(19.2 + 3) / 2 = 11 |

🟡 Whether the BF015 wagons count as mounted (their `s_mount` entry names a pony) follows the general mount rule of
`game_rules.md` "Mounts". Use that rule; if they do, M′ is the mount's M.

## Corrections to existing public notes

- `hidden_reserves_off_field.md` §4 ("It translates every model by the same offset, so the formation is kept") is
  corrected: `TeleportToNode` keeps the models' world positions, and they walk to the node (Q2). For BF008's hidden
  reserves this is invisible, because the walkers are hidden enemy units.

- `battle_end_objectives.md` §5.1: the 🟡 about which piece sets 7 at the start or the end of the closing is resolved
  (swinging-door gates at the end, portcullis at the start).
- `movement_formation.md` §1.4: the arrival distance while steering is corrected (Q4).

## 🟡 Uncertainties

- Gate animation during a pause and on extra repaints (§0).
- The outward swing sense of the doors (§1.2).
- 5 requested while a gate is still opening (§1.2).
- The Flying Bower carrying quirk (Q3).
- Whether the BF015 wagons count as mounted (Q5).
