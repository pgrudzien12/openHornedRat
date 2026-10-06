# Unit-script spawned units, parent following, squig hops and movement opcodes

Public implementation report, batch 9 of the interpreter requests (GitHub #3), part 2 of 3 (companions: `script_grid_events.md`, `script_shooting.md`). Behaviour only; states by name, numbers only for script operands, event codes and battle-file data.


Opcodes: `SpawnUnit` 0xD3, `FollowParent` 0xD4, `FanaticJump` 0xD8, `FanaticRelease` 0xD9, `MoveToTarget` 0x3D,
`ReformBlock` 0x45, `ScatterModelsToNode` 0x48. Lengths agree with `whshr/behaviour.py`. None of them yields.

## 0. Corrections to read first

1. **BF039 has no fanatics. It is a Squig Hopper battle.** All seven units in `BF039.BTS` are
   `Goblin_Squig<Hopper` (`troopsprites:SquigHopper`, psy `CantBreak|PsyImmune`, no `CantMelee`). Scripts 7–10 of
   BF039, the only users of `FanaticJump`/`FanaticRelease`, make the **squig hoppers hop**. Night Goblin fanatics
   (BF004_5, BF015, BF034, BF038) never run 0xD8/0xD9. They move with `Query 17` (Wander) and do damage with
   `Query 18` (`script_queries.md` §10). Wrong as a result, and to fix:
   - `game_rules.md` event table row 0x35 ("a fanatic's jump reached its event step") and the line "event 0x35 is
     posted by the fanatics' own walk animation". The event comes from the **squig hopper's** walk animation.
   - `script_animation_sound.md` §2.2 and its consistency list: the animation family with the event step belongs to
     the Squig Hopper sprite, not to the fanatic.
   - `game_rules.md` "Night Goblin Fanatics": the sentence "opcode 0xD8 is a 2D6 × 8 unit jump", and R45 "jump
     opcode 0xD8", are part of the fanatic model. 0xD8 is the squig hop. Fanatic movement is Query 17.
   - The engine model "Fanatics: … Query 18 loop, jump opcode" has the same problem: fanatics need SpawnUnit,
     Query 17 and Query 18. Squig hoppers need 0xD8/0xD9.
2. **The fanatic spawn trigger (open in R45) is event 0x33.** Every parent interrupt script has
   `CaseEvent 51; PlaySoundAtUnit 6 5; SpawnUnit … 0; SpawnUnit … −20; SpawnUnit … 20; SetBehaviour 15|19 29`.
   Event 0x33 ("threat within reach") is posted by the parent's periodic `Query 16`/`Query 20` (the parent's main
   script sets `SetBehaviour 16 n` or `20 n`). After spawning, the parent switches its periodic behaviour to 15 or 19,
   which never posts 0x33, so **the release happens once per parent**.
3. `ScatterModelsToNode` note: the open point about "when a model counts as in formation again" is answered in §7
   below. The engine's provisional rule is the original's rule.

## 1. Shared state

- **Parent link.** One per unit; empty at load. Only two instructions set it: `SetParentByTag` (the unit's own
  parent) and `SpawnUnit` (the copy's parent := the spawner). `FollowParent`, `SendEventToParent`, Query 18 and the
  fanatic "inside the parent" test read it.
- **Anchor shift with models left behind** ("shift"). `FollowParent`, `FanaticJump`, the spawn placement and Query 17
  all move the **unit position** directly and give each model the opposite offset. Every model keeps its world
  position and leaves the *in formation* state. Its slot (target relative to the unit) does not change, so the
  models then walk to their slots around the new position under the ordinary model-walk rule. The footprint (map
  object) is re-centred at once. The script sees no move order: no waypoints, and the halted state is not cleared.
- **Model "in formation" state.** A model enters it when it reaches its slot or target exactly (model-walk
  arrival), or when `SnapModelsToFormation` places it. It leaves the state through any anchor shift (above) or
  through `ScatterModelsToNode`.
- **Hop counter** (one small per-unit counter, used only by 0xD8/0xD9). `FanaticJump n` with n ≠ 0 sets it to n, and
  `FanaticRelease` decrements it. 🟡 Before the first `FanaticJump n` its value is not 0: it shares storage with an
  unrelated per-unit value loaded from the battle file. Shipped scripts always set it first.
- **Facing / bearing convention** as in `movement_formation.md`: 512 steps, 0 = +Y, clockwise (128 = +X). The
  rotation of a (lateral, forward) offset by facing f is
  `x = (COS[f]·lat + SIN[f]·fwd) >> 8`, `y = (COS[f]·fwd − SIN[f]·lat) >> 8`, with an arithmetic shift (floor) and
  `SIN/COS[a] = trunc(256·sin/cos(2πa/512))`. Positive lateral = to the right. The bearing from A to B is
  `trunc(256 − 256·atan2(Bx − Ax, Ay − By)/π)`, in 0…511 (B straight up +Y → 0, +X → 128, −Y → 256, −X → 384,
  B = A → 256).

## 2. `SpawnUnit` 0xD3 (5 words; 12 uses, 4 DLLs)

Operands: `tag, script, place, offset`. Shipped uses are always three copies, each `place` 1:

| DLL / parent script | tag | script | offsets |
|---|---|---|---|
| BF004_5 17 | 0xABC2 | 13 | 0, −20, 20 |
| BF015 32 | 0xABC0 | 28 | 0, −20, 20 |
| BF034 18 | 0xABC0 | 12 | 0, −20, 20 |
| BF038 7 | 0xABC0 | 6 | 0, −20, 20 |

Effect:
1. Find the first **live** unit (any side; hidden counts) whose tag equals `tag`. This is the *template*, the
   `hidden:` `Night_Goblin<Fanatic` unit, whose own script takes the tag. If none is found (or tag 0): condition
   **false**, and nothing else happens (the original prints a debug message).
2. Create a new unit in a free unit slot (🟡 a free slot may be a removed unit's slot). If no slot is free:
   condition **false**. The new unit:
   - copies the template's name/campaign fields, `setstats` block (side, models, stats, weapons), psy flags
     (`CantMelee` included) and leader. It gets **as many models as the template**, laid out in a block at the
     template's position, facing 0;
   - is **not hidden** (the template's hidden state is not copied). It starts halted, with an "independent" state
     🟡 (meaning as in the flag table of `game_rules.md`), **no tag** (so the template keeps being found), no
     target, an empty event queue, no interrupt script and no periodic behaviour;
   - has its derived values (speed etc.) computed as at battle load, and its sprites registered;
   - has **script := `script`**, starting at instruction 0;
   - has **parent := the spawning unit**.
3. If `place` = 1 (always, in shipped data), placement:
   - position := spawner position + rotate(lateral = `trunc(offset / 2)`, forward 0, spawner facing). So the 0/−20/+20
     copies stand at the spawner's centre and 10 units to its left and right. The models come with this position:
     they stand on their slots around it;
   - facing := `offset + bearing(spawner → source unit of the event being handled)`. In shipped data that is the
     threat that caused event 0x33, so the three copies fan out by −20/0/+20 steps (≈ ±14°) towards the threat.
     🟡 The original does **not** wrap this sum (a bearing below 20 with offset −20 gives a negative facing). An
     engine should take it mod 512;
   - then the **Wander step of `script_queries.md` §10, case 17, step 2**: one `rand()`,
     `s = (rand() mod 4 + 4) × 12`, an anchor shift of `s` straight ahead along the new facing (models left behind),
     and the unit enters the **re-forming** state. Visually the fanatics burst 48–84 units out of the parent towards
     the threat;
   - the copy's footprint enters the **"inside its parent / not engageable"** state. This is the state that Query 18
     ends once no parent model is within reach (`game_rules.md` "Night Goblin Fanatics"). It is the same
     footprint state a routing unit has, so enemies cannot engage it. 🟡 A second footprint mark is also set (its
     meaning is not identified; `FanaticJump` sets it too).
4. Condition **true**.

When the spawn is triggered, `place` ≠ 1 is never used: the copy then stays where the template is, facing 0.
🟡 Because the copy may sit in a unit slot after the spawner's, it may run its script in the same tick.

The spawned script (BF015 28 etc.) is `SetInterruptScript n; SetOrder2 64 0; loop { SetWait 5; Wait; Query 18 }`,
and its interrupt script runs Query 17 on event 0x34 (`script_queries.md` §10).

| Before | Instruction | After |
|---|---|---|
| Template tag 0xABC0 alive (hidden, 1 model). Spawner P at (500,1000), facing 128, handling event 0x33 from an enemy at (800,1000) (bearing 128). rand() mod 4 = 0. | `SpawnUnit 0xABC0 28 1 0` | new unit at (548,1000), models still around (500,1000), facing 128, re-forming, inside-parent state, parent P, script 28, visible; condition true |
| same, offset −20, rand() mod 4 = 0 | `SpawnUnit 0xABC0 28 1 -20` | placed (500,1010), facing 108, anchor (546,1021); true |
| same, offset +20, rand() mod 4 = 3 (s = 84) | `SpawnUnit 0xABC0 28 1 20` | placed (500,990), facing 148, anchor (581,969); true |
| no live unit with tag 0xABC0 | `SpawnUnit 0xABC0 28 1 0` | nothing; condition false |
| template present; called again later | `SpawnUnit …` | another copy (the template is not used up) |

## 3. `FollowParent` 0xD4 (2 words; 4 uses)

Operand: forward distance `d` in world units. Shipped uses: BF004_4 scripts 0–2, `FollowParent 72`, every 8 ticks
(NPC slave units tagged to Goblin Stickers parents via `SetParentByTag`). BF010 script 1, `FollowParent 36`, every
6 ticks (NPC Ilmarin). Query 25 does the same with d = 36 (`script_queries.md`).

- No parent → nothing (debug message only). The condition is **not written**. 🟡 In BF010 nothing gives Ilmarin a
  parent: script 1 has no `SetParentByTag`, and no other instruction sets parents. So its `FollowParent 36`
  does nothing in the original.
- With a parent: unit position := parent position + rotate(0, d, parent facing), i.e. `d` units **in front of**
  the parent. This is an anchor shift (§1): the models walk after it. Facing := the parent's facing. The footprint
  shape is refreshed and the **action broadcast is set to 2** (`script_animation_sound.md` §0.1). There is no move
  order, no re-form and no event 0x34. 🟡 Whether the halted state stays set was not traced; this routine does not
  touch it.
- Condition: not written.

| Before | Instruction | After |
|---|---|---|
| parent at (500,1000) facing 128; unit anywhere, facing 0 | `FollowParent 72` | unit at (572,1000), facing 128, models keep their world positions and walk; broadcast 2 |
| parent facing 0 at (500,1000) | `FollowParent 72` | (500,1072) |
| parent facing 64 at (0,0) | `FollowParent 36` | (25,25) |
| no parent | `FollowParent 72` | nothing; condition unchanged |

## 4. `FanaticJump` 0xD8 (2 words; 2 uses, BF039) — the squig hop

Operand: `n`, the hop count (shipped: 4 in script 9, 0 in script 7). If n ≠ 0, then hop counter := n **after** the
hop. 0 leaves the counter alone.

Hop (three `rand()` draws, in this order):
1. `a = rand() mod 6 + 1`, `b = rand() mod 6 + 1`; distance `D = (a + b) × 8` (16…96).
2. Heading h:
   - if `a = b` (a double) **or the unit has no current target**: `h = (facing + rand() mod 512) mod 512`, which is
     uniformly random;
   - otherwise `h = (bearing(unit → target's unit position) + (rand() mod 64) × 2 − 64) mod 512`, i.e. toward the
     target with an even offset −64…+62 (about ±45°). **Contradicts** the private-catalogue "±32"; the public
     notes did not state it.
3. Facing := h (instant).
4. Landing point L = position + rotate(0, D, h).
5. L is moved to the nearest allowed point of any route-blocking boundary it violates (the 0xB0 kinds that routes
   respect, `game_rules.md` "Routes, collisions and visibility"; 🟡 exact projection). It is then pushed out of every
   **non-unit object** (building, furniture, scenery) and every **unit of its own side group** (player + allies, or
   enemy), self excluded. The push applies when the distance to the object's centre is below `R_obj + r_own / 2`
   (`R` = footprint bounding radius). L is moved straight away from that centre by the overlap, with truncation
   toward zero. **Enemy units are not avoided**: a hop can land on the enemy.
6. Anchor shift to L (§1). The models are left behind and walk there; that walk is the hop seen on screen. The hop
   distance is also recorded on the leader model, 🟡 presumably to scale the hop animation. The second footprint
   mark of §2 is set.

There is no damage here. The condition is **not written**, no move order is issued, and the re-form/halted states
are not changed. The script plays the animation itself (`PlayUnitAnimation 3 53 1`, `script_animation_sound.md`),
whose event step posts **event 0x35** back to the unit.

| Before | rand draws | Instruction | After |
|---|---|---|---|
| unit (500,1000), target at (500,1300) (bearing 0) | a=3, b=4, rand mod 64 = 32 | `FanaticJump 4` | D 56, h 0, position (500,1056), facing 0, counter 4 |
| same | 3, 4, rand mod 64 = 0 | `FanaticJump 0` | h 448, position (460,1039), counter unchanged |
| same | 3, 4, rand mod 64 = 63 | `FanaticJump 0` | h 62, position (538,1040) |
| target at (800,1000) (bearing 128) | 3, 4, 32 | `FanaticJump 0` | h 128, (556,1000) |
| facing 0, any target | 6, 6, rand mod 512 = 300 | `FanaticJump 0` | D 96, h 300, position + (−50,−83) |
| no target | 2, 5, rand mod 512 = 0 | `FanaticJump 0` | D 56, h = old facing |
| landing point inside a friendly unit's footprint | – | – | pushed to that footprint's edge + r_own/2 |

## 5. `FanaticRelease` 0xD9 (1 word; 1 use, BF039 script 7) — the hop landing

1. Clear the unit's psy `CantMelee` (no effect on squig hoppers, which lack it).
2. **Landing collision, with armour saves**, at the **leader model's current world position**. 🟡 After a hop the
   models are still walking at the moment event 0x35 arrives, so this point lies between the take-off and the
   landing. It is the collision of `game_rules.md` "Night Goblin Fanatics", with three differences. Saves are
   allowed. The Strength is the hopper's own (for fanatics it happens to be 5). The hopper **never dies** from it:
   the artillery/rolling-stock/building "dies" outcomes count as contact but kill nothing. Every object is
   tested; the scan does not stop at the first. 🟡 A coarse filter runs before the per-model test: the object
   centre must be closer than its bounding radius, ×2 when the target unit is charging, and 204 when it is in melee.
3. Condition:
   - **true** if the landing wounded at least one model, or touched an artillery piece, rolling stock, a special
     unit, a building or scenery (the counter is not changed);
   - otherwise the hop counter is decremented. The condition is **true** if it is still non-zero, **false** if it
     reached 0. 🟡 A counter that was 0 wraps to 255, giving true.
4. If the unit has **no current target**, **event 0x01** is posted to itself (source none), whatever the result.
   This side effect persists when the condition is false.

| Before | Instruction | After |
|---|---|---|
| counter 4, landing wounds 2 enemy models | `FanaticRelease` | counter 4; true |
| counter 4, nothing within reach | `FanaticRelease` | counter 3; true |
| counter 1, nothing within reach | `FanaticRelease` | counter 0; false |
| counter 1, enemy model within reach but the wound roll or save fails | `FanaticRelease` | counter 0; false |
| no target, counter 2, miss | `FanaticRelease` | counter 1; true; event 0x01 queued to self |

### 5.1 Worked example: one BF039 squig hopper, first contact to the second hop

Scripts: main script 0 (`AttackNearestEnemy` every 20 ticks), interrupt script 7, hop scripts 8/9/10.
1. The unit gets an attack target. Event 4 → script 7: `TakeEventTarget`, `SendEventToParent 20`,
   `IfSwitchScript 8`.
2. Script 8: `MoveToTarget` (§6), then every 15 ticks `ApproachTargetInReach`. Once the target is within the threat
   range of 240, `SendEventSelfIfTrue 6`.
3. Event 6 → script 7 `SwitchScript 9`: `ResetStack; HaltAndReform; Yield`. Next tick: `ClearUnitFlags 8` (it drops
   the re-forming state just set), then **`FanaticJump 4`**: counter 4, hop 1 (say a=2, b=5 → 56 units toward the
   target ±45°). Then `PlayUnitAnimation 3 53 1`. Script 9 idles in `Yield; Query 0`.
4. The walk animation reaches its event step → **event 0x35** → script 7 `CaseEvent 53`: **`FanaticRelease`**.
   - It hit someone: true → **`FanaticJump 0`** (hop 2, counter stays 4) and `PlayUnitAnimation 3 53 1` again.
   - It missed: counter 3, true → hop 2 the same way.
5. The cycle repeats on every 0x35. Only misses use up the counter, so four misses in total make `FanaticRelease`
   false → `SwitchScript 10`: `HaltAndReform; ClearUnitFlags 8; TurnToFaceTarget; wait 45 ticks; SendEventSelf 6`.
   That leads back to step 3 (counter reset to 4). A hopper that keeps hitting hops without rest.

## 6. `MoveToTarget` 0x3D (1 word; 547 uses)

`movement_formation.md` §3.1 is correct against the original. Only these additions apply:
- The goal is the current **target unit's** footprint centre only. The target **point** (aim at point,
  `script_magic.md`) is ignored. No target unit → false.
- The refusal "anchored" in §3.1 covers both the anchored war-machine state and the "held" state (Tangling Thorn),
  plus re-forming.
- In the "already there" case (no waypoint planned, the unit halts and re-forms, true) the follow-unit mode is
  **also set**, on a halted unit with no waypoints. This is harmless: `RefreshRouteToTarget` then does nothing.
- Arrival: a follow-unit route never arrives by distance, so this opcode never leads to the "destination reached"
  0x34 from the move itself. 0x34 comes only from the end of a later re-form (after a halt caused by contact, a new
  order or `HaltAndReform`). This matches the engine's "own arrival rule" only if that rule does not fire 0x34 by
  distance for `MoveToTarget` moves.

## 7. `ReformBlock` 0x45 (1 word; 148 uses)

- N = the unit's model count. N = 0 → nothing.
- Requested ranks `r = trunc(N / (√N × 1.15))`. It then goes through the **ranks order** of `game_rules.md`
  "Formations" (the same routine as the player's ranks buttons), so `ranks = max(m, min(r, N div m))` with
  `m = max(1, trunc(0.75·√N))`. The order is **refused** (nothing happens) if the unit is fleeing, held or
  charging.
- On acceptance the unit's ranks setting is changed and a **re-form is queued**. It is not immediate: the
  formation update later in the same tick lays out the new slots, sets the re-forming state, and the end of the
  re-form posts 0x34 (`movement_formation.md` §1.2). If the unit is the one shown in the side panel, the panel is
  refreshed.
- Condition: **not written**.

| N | 1 | 2–5 | 6–11 | 12–21 | 22–32 |
|---|---|---|---|---|---|
| ranks | 1 | 1 | 2 | 3 | 4 |

Spot checks (frontage = ceil(N / ranks)): 8 → 2×4; 16 → 3×6; 18 → 3×6; 20 → 3×7; 24 → 4×6; 32 → 4×8. No N ≤ 32
lies within float error of a boundary (the boundaries are N = 5.29, 11.9, 21.2).

| Before | Instruction | After |
|---|---|---|
| 20 models, idle | `ReformBlock` | ranks 3, re-form queued; condition unchanged |
| 12 models, charging | `ReformBlock` | nothing |
| 22 models | `ReformBlock` | ranks 4 |

## 8. `ScatterModelsToNode` 0x48 — checks against `notes/scatter_models_to_node.md`

The note is correct on operand, node choice, cycling, radius and "stop when no node". Corrections and additions:
1. **Open point answered.** A scattered model gets back the *in formation* state when it **arrives exactly at its
   scatter destination** (ordinary model-walk arrival). The next `ScatterModelsToNode` then scatters it again.
   This is what the shipped loop `PushPC / ScatterModelsToNode / SetWait ~20 / Wait / Loop` relies on: each model
   gets a new destination on the first pass after it arrives. A model still walking is skipped.
2. **`SnapModelsToFormation` places every model at its current target and marks it in formation.** Right after a
   scatter that target is the scatter destination. So the shipped `ScatterModelsToNode; SnapModelsToFormation`
   pair **teleports** the models to their scattered positions at mission start. The next loop pass re-scatters
   them all (they are all "in formation"). The engine's "clear the destinations so the models walk back" is
   **wrong** for this pattern.
3. Random draws per model: first `rand() mod radius` (distance d), then `rand() mod 512` (angle a). Destination =
   node centre + `(COS[a]·d >> 8, −(SIN[a]·d) >> 8)` (floor shifts; note the y term is the floor of the negated
   product). It is stored as the model's target relative to the unit.
4. **Radius 0** would be a division by zero in the original (no guard). No shipped scatter node has radius 0
   (smallest: 4). The note's "treat as the centre" is an engine choice, not original behaviour.
5. Each scattered model also gets its own animation request for action 2 (`script_animation_sound.md` §0.2).
6. The condition is not written.

## Uncertainties (🟡) summary
Free-slot reuse and same-tick script run of a copy. The unwrapped spawn facing. The meaning of the second
footprint mark. The hop-counter initial value. The exact boundary projection of the hop. The collision point while
models are still walking. Whether `FollowParent` leaves the halted state alone. The BF010 Ilmarin parent.
