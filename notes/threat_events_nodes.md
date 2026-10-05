# Unit-script threat search, event routing and node areas

Public implementation report, batch 5 of the interpreter requests (GitHub #3). It is a companion to
`unit_script_control.md`, `target_queries.md` and `movement_formation.md`, and describes behaviour only. States are
named (hidden, broken, in melee, ...). Numbers appear only where they are script operands or battle-file data.

## Part A — threat and target search

Public implementation report (batch 5 of the interpreter requests, GitHub #3). Behaviour only. Companion to
`unit_script_control.md` (condition word, LIFO event queue), `target_queries.md` (range/arc tests, `TargetValid`),
`movement_formation.md`, and `game_rules.md`. Script listings come from `python3 -m whshr scripts <installation>`.

**Read in `game_rules.md` rather than re-deriving:**
- "Scripted nearest-enemy search: range and failure rules" (whole-field search, no `SetThreatRange` filter);
- "Routes, collisions and visibility" (`IsVisible`: view cone ±50°, doubled while the looker is in melee, scenery
  rays, `SightEdge`, no range, no height);
- "Unit behaviour scripts and events" (event table, `React N`, `UnitScore`, library scripts);
- §8.1/§8.3 (which missile code a unit uses; weapon range by missile code, e.g. bow 576, crossbow 720);
- §3 `s_race` (class × 8 + race; classes 1 Infantry, 2 Cavalry, 3 Archers, 4 Artillery, 5 Wizard, 6 Monster, …);
- "Player orders and the command panel", row 0x13 (Withdraw).

Opcode lengths are from `whshr/behaviour.py` `LENGTHS`. Counts are uses across all 45 mission DLLs (the shared
library 100–170 counted once per DLL).

### 0. Terms used below

| Term | Meaning |
|---|---|
| **side** | the unit's `s_side` army bits from the `.BTS`/`.MRC`: player army 0x00, allied side 0x40, enemy army 0x80. Buildings/furniture placed from `[OBJECTS]` get pseudo-unit records that belong to no army. |
| **hostile** | one unit is in the enemy army and the other in the player army or the allied side. Player army vs allied side is **not** hostile; buildings are never hostile. |
| **eligible** | an active unit on the battlefield that is **not hidden**, **not broken**, **not leaving the battle** (the escape state of objective G, `game_rules.md` R60) and not a building pseudo-unit. Unless stated, hidden units are never revealed by these opcodes. |
| **class operand** | `class × 8` as in `s_race` (8 Infantry, 16 Cavalry, 24 Archers, 32 Artillery, 40 Wizard, 48 Monster). **0 means "any class"**, so class 0 (notype) can never be singled out. |
| **d** | `trunc(√(Δx² + Δy²))` between regiment positions unless stated (same as `target_queries.md` §1). |
| **weapon range R** | the unit's own range from the §8.3 table (0 when it has no missile weapon). |
| **current target** | the unit's single target slot (also the close-combat opponent). |
| **threat slot** | a **second, separate** per-unit unit slot holding "the enemy I am worried about", with a stored **threat score**. Threat detection (`Query 1/6/10/11`, `DetectThreat`) fills both; `FindThreatNear`/`FindNewThreatNear`/`KeepThreat` fill the slot only. It is distinct from the current target. |
| **unit order** | the order of the battle's unit records (creation order at battle load). Ties are broken by it, as stated per routine. |
| **deployment** | the battle's deployment phase. |

**Engine-model differences (summary).** The implementer's model has `current_target` but no threat slot: add one
(unit or none) plus a stored threat score, separate from `current_target`. `AttackNearest*` and `AttackUnitAtNode`
do **not** write `current_target`: they queue event 0x04 ("attack target", source = chosen unit) to the unit
itself, and the library handler (`TakeEventTarget` 0x3A, then attack script 158) takes it as the target. The `Find*`
and `Target*` opcodes write the current target directly and queue nothing. Searches use three different rankings
(§1–§4); they are not interchangeable with the engine's single `AttackNearestEnemy`.

---

### 1. Threat search: `FindThreatNear` 0x75, `FindNewThreatNear` 0x77 (and `KeepThreat` 0x76)

Length 1 each, no operand. Used only by library script 118 (AI skirmisher "evade threats", 44 uses each).

#### 1.1 Shared search ("nearest facing threat")

1. **Radius** `r = trunc(R × 3 / 8)` (bow 576 → 216, crossbow 720 → 270). A unit without a missile weapon has
   r = 0 and effectively never finds a threat.
2. **Candidates**: every unit except the searcher that is active, not hidden, not leaving the battle, **not broken**,
   and **hostile** to the searcher.
3. **The searcher must see the candidate**: `IsVisible(searcher → candidate)` with the standard view cone (±50°,
   ±100° while the searcher is in melee), scenery and `SightEdge`.
4. **Distance** `d ≤ r` (inclusive). The nearest such candidate wins; ties go to the **first** in unit order.
5. **The winner must see the searcher**: `IsVisible(winner → searcher)`, standard cone of the *winner* (doubled if
   the winner is in melee). If it does not, the result is **none** — the search does **not** fall back to the
   next-nearest candidate.

So a "threat" is the nearest visible hostile within 3/8 of my range **that is facing me**.

#### 1.2 Opcodes

| Opcode | Threat slot | Condition |
|---|---|---|
| `FindThreatNear` 0x75 | := search result (cleared when none) | true iff found |
| `FindNewThreatNear` 0x77 | := result only if found **and** different from the current slot; otherwise unchanged (a failed search does **not** clear it) | true iff it changed |
| `KeepThreat` 0x76 (context) | kept if the slot unit is at `d < trunc(R × 5 / 8)` (**strict**) **and** it sees the searcher (rule 5); otherwise cleared. No hostility/broken/hidden re-check. | true iff kept |

None of them writes the current target, queues events or barks. No deployment check.

#### 1.3 Test vectors (searcher S: bow, R = 576 → r = 216, keep radius 360; at (0, 0), facing 0 = +Y)

| Before | Instruction | After |
|---|---|---|
| Enemy E1 at (0, 200) facing 256 (towards S), not broken; threat slot empty | `FindThreatNear` | slot = E1, cond true |
| E1 at (0, 200) facing 0 (back to S); E2 at (0, 210) facing 256 | `FindThreatNear` | slot = none, cond false (E1 is nearest but blind to S; no fallback to E2) |
| E1 at (0, 216) facing 256 | `FindThreatNear` | slot = E1 (216 ≤ 216), cond true; at (0, 217): none, false |
| Slot = E1; search would return E1 | `FindNewThreatNear` | slot = E1, cond false |
| Slot = E1; E1 has moved to (0, 300) (out of 216); no other candidate | `FindNewThreatNear` | slot = E1 (unchanged), cond false |
| Slot = E1; E3 now nearest facing threat | `FindNewThreatNear` | slot = E3, cond true |
| Slot = E1 at (0, 359) facing S | `KeepThreat` | slot = E1, true; at (0, 360): slot cleared, false |

---

### 2. Weapon-target search: `FindNewTarget` 0x83, `FindTargetAnyRange` 0x7D, `FindTargetOfClass` 0x7C, `FindTargetOfClassAnyRange` 0x7E

(`FindTarget` 0x7B and the unused `FindFriendTarget*` 0x7F–0x82 share it.)

| Opcode | Len | Operand | Uses |
|---|---|---|---|
| `FindTargetOfClass` 0x7C | 2 | class | 12 (BF004_5, BF027, BF034) |
| `FindTargetAnyRange` 0x7D | 1 | – | 56 (library 119 + missions) |
| `FindTargetOfClassAnyRange` 0x7E | 2 | class | 17 |
| `FindNewTarget` 0x83 | 1 | – | 44 (library 119) |

#### 2.1 Shared search ("nearest shootable unit")

1. **Candidates**: unit footprints (not scenery, not buildings) whose unit is active, not hidden, not broken, not
   leaving the battle, of the requested class (if non-zero), and **hostile** to the searcher. (The friendly variants
   take allied-side units only.)
2. **Distance** between regiment positions; candidates at **d = 0 are skipped**.
3. **Range**: range-limited variants require `d ≤ R` (inclusive — note `InRange` later requires `d < R`, so a target
   found at exactly `d = R` fails the next `InArcAndRange`). "AnyRange" variants have no limit. No visibility, arc or
   line-of-sight test.
4. **Independent units only** — friendly-crowding check (the first check of `TargetValid`, `target_queries.md` §3):
   a candidate is skipped if any *other* friendly unit (not the searcher, not the candidate) has its centre within
   `its footprint radius + max(blast radius, 24)` of the aim point. **Quirk**: the aim point used here is
   `(candidate x, searcher y)`, not the candidate's position. Non-independent units skip this check.
5. Nearest wins (`d` strictly smaller); ties go to the **first** in footprint order.

#### 2.2 Opcodes

| Opcode | Limit | Found | Not found |
|---|---|---|---|
| `FindTarget` 0x7B / `FindTargetOfClass` 0x7C | `d ≤ R` | current target := it, cond true | **current target cleared**, cond false |
| `FindTargetAnyRange` 0x7D / `FindTargetOfClassAnyRange` 0x7E | none | same | **cleared**, false |
| `FindNewTarget` 0x83 | `d ≤ R` | if it differs from the current target: store it, true; if it is the current target: false, unchanged | false, **current target unchanged** |

No events, no movement, no barks, no deployment check.

#### 2.3 Test vectors (S: bow R = 576, at (0, 0), not independent unless stated)

| Before | Instruction | After |
|---|---|---|
| Enemy E1 broken at (0, 100), E2 at (0, 3000) facing anywhere; S faces away | `FindTargetAnyRange` | target = E2, true |
| Only enemy E1 exactly at (0, 0) | `FindTargetAnyRange` | target cleared, false |
| Enemy Archers A at (0, 576), enemy Infantry I at (0, 100) | `FindTargetOfClass 24` | target = A, true; A at (0, 577): target cleared, false |
| No enemy Artillery; target was I | `FindTargetOfClassAnyRange 32` | target cleared, false |
| Target = E1 (nearest in range) | `FindNewTarget` | target = E1, false |
| Target = E1; E2 now nearer, in range | `FindNewTarget` | target = E2, true |
| Target = E1; no candidate within 576 | `FindNewTarget` | target = E1 (kept), false |
| S **independent**; E at (0, 400); friendly F (footprint radius 30) at (0, 40) | `FindTargetAnyRange` | aim point (0, 0) is 40 < 54 from F → E skipped → target cleared, false |
| S independent; E at (0, 400); F at (0, 390), no other friend near (0, 0) | `FindTargetAnyRange` | target = E, true (the quirk ignores F next to E) |

---

### 3. Nearest-target pick: `TargetNearestEnemyOfClass` 0xA4, `RetargetNearestEnemy` 0xA7

(`TargetNearestEnemy` 0xA3 and the friendly 0xA5/0xA6 share it; wizard AI target choice uses the same rule.)

| Opcode | Len | Operand | Uses |
|---|---|---|---|
| `TargetNearestEnemyOfClass` 0xA4 | 2 | class | 14 (BF034, BF035, BF038, BF042 …) |
| `RetargetNearestEnemy` 0xA7 | 1 | – | 44 (library 143, wizard advance) |

#### 3.1 Shared search ("nearest enemy, whole field")

Candidates: unit footprints whose unit is active, not hidden, not broken, not leaving the battle, of the class (if
non-zero), hostile. **No range, no visibility, no d = 0 exclusion, no independence check.** Distance is from the
searcher's regiment position to the candidate's **footprint centre** (normally the candidate's regiment position).
Nearest wins (strictly smaller); ties go to the **first** in footprint order.

#### 3.2 Opcodes

| Opcode | Found | Not found |
|---|---|---|
| `TargetNearestEnemy` 0xA3 / `TargetNearestEnemyOfClass` 0xA4 | current target := it, true | false, **target unchanged** |
| `RetargetNearestEnemy` 0xA7 | if different from the current target: store, true; if the same: false | false, unchanged |

No events, movement or barks; no deployment check.

#### 3.3 Test vectors (S at (0, 0))

| Before | Instruction | After |
|---|---|---|
| Enemy Wizard W at (2000, 0), enemy Infantry I at (100, 0); target none | `TargetNearestEnemyOfClass 40` | target = W, true |
| No enemy Wizard; target = I | `TargetNearestEnemyOfClass 40` | target = I, false |
| Target = E1 at (0, 500); E2 at (0, 300) | `RetargetNearestEnemy` | target = E2, true; executed again: false, E2 kept |
| All enemies broken or hidden; target = E1 (broken) | `RetargetNearestEnemy` | target = E1, false |
| E1 at (300, 0) and E2 at (0, 300), E1 earlier in order | `RetargetNearestEnemy` (target none) | target = E1, true |

---

### 4. Attack-the-nearest family: `AttackNearestEnemyOfClass` 0xB4, `AttackNearestEnemyByAxis` 0xB2, `AttackNearestVisibleEnemyByAxis` 0xB3, `AttackNearestMainEnemy` 0xBE, `AttackNearestVisibleMainEnemy` 0xBF

Same routine as `AttackNearestEnemy` 0xB0 (`game_rules.md` "Scripted nearest-enemy search"), which this section
extends.

| Opcode | Len | Operand | Side set | Ranking | Visible | Uses |
|---|---|---|---|---|---|---|
| `AttackNearestEnemyByAxis` 0xB2 | 1 | – | enemy set | axis key | no | 18 (BF012, BF018, BF023, BF028, BF030, BF036 …) |
| `AttackNearestVisibleEnemyByAxis` 0xB3 | 1 | – | enemy set | axis key | yes | 3 (BF007, BF018) |
| `AttackNearestEnemyOfClass` 0xB4 | 2 | class | enemy set | distance | no | 54 |
| `AttackNearestMainEnemy` 0xBE | 1 | – | opposing army only | distance | no | 4 (BF014) |
| `AttackNearestVisibleMainEnemy` 0xBF | 1 | – | opposing army only | distance | yes | 1 (BF014) |

#### 4.1 The routine

1. **Deployment → condition false**, nothing queued.
2. **Side set** (this is not the hostility test):
   - *enemy set* — a searcher in the player army takes **enemy-army units and allied-side units**; a searcher in the
     enemy army takes **player-army and allied-side units**; an allied-side searcher takes enemy-army units only.
     Quirk: for a player-army searcher the allied-side units it accepts are not hostile to it.
   - *opposing army only* ("main") — the enemy army for player-army and allied-side searchers, the **player army**
     for enemy-army searchers (allied-side units excluded).
3. Candidates: active units in the side set, not hidden, not broken, not leaving the battle, not building
   pseudo-units, of the class (if non-zero). **No range limit, no `SetThreatRange`.**
4. Optional visibility: `IsVisible(searcher → candidate)`, standard cone.
5. **Key**: distance `d` (regiment positions) — or, for the **axis** variants,
   `key = min(Sx − Cx, Sy − Cy)` (signed; searcher minus candidate). **The smallest key wins**, so the axis variants
   prefer the candidate lying **furthest towards +X or +Y** from the searcher, regardless of distance — a candidate
   south-west of the searcher has a positive key and loses to anything north or east of it.
6. **Ties go to the last** candidate in unit order (the reverse of §1–§3).
7. Success: event **0x04** ("attack target", source = the chosen unit) is queued to the searcher itself (head of its
   LIFO queue); condition true. `current_target` is **not** written here; the library 0x04 handler takes it
   (`TakeEventTarget`, then approach-and-attack script 158). Failure: condition false, nothing queued.

Keys are kept as 16-bit signed values (irrelevant for real battlefield sizes). At most 31 eligible candidates are
expected; the original's candidate list has no larger capacity.

#### 4.2 Test vectors (searcher S in the enemy army at (0, 0), facing 128 = +X, outside deployment)

| Before | Instruction | After |
|---|---|---|
| Player Cavalry C1 at (0, 800); player Cavalry C2 hidden at (0, 100); player Infantry I at (0, 50) | `AttackNearestEnemyOfClass 16` | event 0x04 (source C1) queued to S; cond true; current target unchanged |
| Same, during deployment | `AttackNearestEnemyOfClass 16` | nothing queued, false |
| Player A at (300, 0), B at (0, −100), C at (−50, −400) | `AttackNearestEnemyByAxis` | keys −300 / 0 / 50 → 0x04 source A, true |
| A at (300, 0), D at (0, 600) | `AttackNearestEnemyByAxis` | keys −300 / −600 → **D** (farther), true |
| A at (300, 0), D at (0, 600); S faces +X so D (90° off) is outside the ±50° cone | `AttackNearestVisibleEnemyByAxis` | → A, true |
| P1 at (200, 0), P2 at (0, 200), P2 later in unit order | `AttackNearestEnemyOfClass 0` | equal d → **P2**, true |
| Player unit P at (900, 0); allied-side unit L at (100, 0) | `AttackNearestMainEnemy` | → P, true (`AttackNearestEnemy` 0xB0 would pick L) |
| Only L (allied side) present | `AttackNearestVisibleMainEnemy` | false, nothing queued |

---

### 5. `AttackUnitAtNode` 0x91 — attack the building at a map node

Length 2: operand = map node n (same node addressing as the other node opcodes). 15 uses, all in BF021, where
raiders walk to nodes and attack the buildings there.

1. A unit that is **anchored** (war machine) or **held** → condition false.
2. Find the nearest **building/furniture pseudo-unit** (only those; regiments at the node are ignored), active, whose
   reference point (its leader model's position) is at a distance `< max(footprint radius, 48)` from the node point;
   nearest wins, ties to the first in unit order. None → false.
3. If that building has already been destroyed/removed → false.
4. Queue event **0x04** (source = the building) to the unit itself; condition = the event was queued (false only if
   the event pool is full). Current target not written; the 0x04 handler takes it, as in §4.

No hidden/broken/hostility test (buildings have none), no deployment check, no bark.

| Before | Instruction | After |
|---|---|---|
| Node 30 at (1000, 1000); building B, footprint radius 60, centre (1030, 1000) | `AttackUnitAtNode 30` | event 0x04 (source B) queued, true |
| Building radius 20 at (1040, 1000) | `AttackUnitAtNode 30` | 40 < 48 → queued, true; at (1050, 1000): 50 ≥ 48 → false |
| Only an enemy regiment stands on the node | `AttackUnitAtNode 30` | false |
| S is an anchored war machine | `AttackUnitAtNode 30` | false |

---

### 6. `ReactToThreat` 0x39

Length 1. 318 uses: library 101–104 and 151 on event **0x03** ("enemy to fight", queued by threat detection), always
followed by `IfSwitchScript 159` (AI threat attack). Player units only run it when **independent** (library 101 tests
the independent state first).

Input: the threat slot and its stored threat score (filled by threat detection, which queues 0x03).

Steps, in order (any failure → condition false, nothing changes):

1. Deployment → false.
2. The unit is **charging, pursuing, broken or braced** → false.
3. Threat slot empty → false.
4. The threat is `CantMelee` (Night Goblin Fanatics) → false.
5. `UnitScore(unit, current target)` (game_rules formula; 0 with no target) must be **less than** the stored threat
   score — i.e. switch only to a strictly more threatening enemy.
6. The unit must see the threat: `IsVisible` with a **wider cone, ±60°** (±120° while the unit is in melee), scenery
   and `SightEdge`.
7. **If the unit is in melee**: it performs **Withdraw** (player order 0x13 rules: disengages only from rolling
   stock/furniture, otherwise **routs**). Condition false; target and threat slot unchanged.
8. Otherwise: current target := threat; threat slot := none; the unit's **last waypoint is replaced** (or the first
   set, if it has none) by an approach point on the threat: for regiment footprints, a point one footprint radius out
   from the threat's centre on the side (front, rear, left or right) from which the unit approaches; otherwise the
   threat's centre. Movement is not started here (script 159 does that).
9. If the threat is **charging and its current target is this unit**: queue event **0x07** ("you are being
   charged", source = threat) to the unit; condition **false** (so the library goes to the fear test and brace,
   script 161, instead of 159). Otherwise condition **true**.

No bark.

| Before | Instruction | After |
|---|---|---|
| S independent, idle, not in melee, no target; slot = T (stored score 120) at 40° off S's facing, visible; T not charging | `ReactToThreat` | target = T, slot = none, last waypoint = approach point at T, cond true |
| Same, T is charging S | `ReactToThreat` | target = T, slot = none, waypoint set, event 0x07 (source T) queued, cond false |
| Same, T at 70° off S's facing | `ReactToThreat` | outside ±60° → nothing changes, false |
| Target E with `UnitScore` 120 = stored score | `ReactToThreat` | nothing changes, false |
| S in melee with living enemies; T visible and scoring higher | `ReactToThreat` | S withdraws → routs; cond false; target and slot unchanged |
| S broken, or T is a Fanatic | `ReactToThreat` | false |

### 7. `ReactEnemySpotted` 0x40

Length 1, 45 uses (library 152 on event **0x1C**). It only plays `React 11` ("Enemy sighted.") for the unit: per the
`React` tables, races Human, Elven and Dwarven have it, and it is shown/heard only for units **not** in the enemy army.
It does **not** write the condition, the target or the threat slot.

Correction to `game_rules.md` "Hidden units": event **0x1C** goes to the **spotter** (source = the revealed unit) and
**0x1D** to the **revealed** unit (source = spotter) — the event table there is right, the bullet has them swapped.
So the bark comes from the unit that spotted a hidden enemy.

| Before | Instruction | After |
|---|---|---|
| Player Human unit, event 0x1C current | `ReactEnemySpotted` | "Enemy sighted." message/speech; condition, target, slot unchanged |
| Enemy-army unit | `ReactEnemySpotted` | nothing |

---

### Summary

- Four distinct search routines: **threat search** (§1: within 3/8 of weapon range, mutual visibility, writes the
  threat slot), **weapon-target search** (§2: within weapon range inclusive or any range, skips d = 0, independent
  crowding check, writes the target), **nearest pick** (§3: whole field, writes the target), and **attack-nearest**
  (§4: whole field, side sets, distance or axis key, queues event 0x04). `AttackUnitAtNode` picks a building at a
  node and also queues 0x04.
- Tie-breaks differ: first in order for §1–§3 and §5, **last** for §4.
- "New"/"Retarget" variants report only a change and never clear on failure; the plain `Find*` variants clear the
  target on failure, the `Target*` variants keep it.
- `ReactToThreat` switches only to a strictly higher-scoring, visible (±60°) threat; in melee it withdraws instead;
  a threat charging this unit turns into event 0x07.
- Engine: add a threat slot + stored score separate from `current_target`; route attack picks through event 0x04.

### 🟡 Uncertainties

- `UnitScore` divisor: the original divides by `trunc(range / 4)`, not `round(range / 4)` as written in
  `game_rules.md`; the results differ when range is not a multiple of 4 (e.g. 250). Worth correcting there.
- Axis key (§4): the "smallest `min(Sx − Cx, Sy − Cy)` wins" rule is what the game does; whether it was intended
  (e.g. a battle with a fixed approach direction) is unknown. Implement as written.
- §2 aim-point quirk `(candidate x, searcher y)` — very probably a defect; matches the shooting note in
  `game_rules.md`.
- Unit order vs footprint order: §1/§4/§5 use unit order, §2/§3 footprint order; assumed identical for ordinary units.
- §3 also accepts one more footprint kind than §2 (not seen on ordinary units).
- §5: the "destroyed/removed" building state, and a lookup mode in which the original uses the unit under the mouse
  pointer instead of the node point (seen only in the original's shared lookup; implement the node point).
- §6 step 8: exact sector boundaries and the sign convention of the "approach side" point; and which footprints are
  "regiment footprints".
- §6 step 6 and §1: the view cone is also widened while the looker is **re-forming** (as well as in melee); the
  public visibility note mentions only melee.
- §4 capacity of 31 candidates: no shipped battle is known to exceed it.

## Part B — event routing, tags and side changes

Public implementation report (interpreter batch 5, group 2). Companion to "Unit behaviour scripts and events" in
`game_rules.md` (event table, library scripts 100–170), `unit_script_control.md` §1 (per-unit state, LIFO
queue) and §4–5, `target_queries.md`. Behaviour only. Script listings come from
`python3 -m whshr scripts <installation> <DLL>`; lengths are those of `whshr/behaviour.py`.

### 0. Shared facts

#### 0.1 Unit identity, tag, parent, `whoami`

| Concept | What it is in the original | Engine model mapping |
|---|---|---|
| **unit** | one entry in the battle's unit table; table order = creation order. Every tick, units step in table order (§0.3) | `Battle.regiments` order |
| **live unit** | a unit still in the battle. A unit stops being live when it is **removed**: all models dead, it left the table (rout off the edge), or a script removed it (`RemoveFromBattle`). Routed-but-still-on-the-table, hidden, not-yet-deployed and off-field-waiting units **are live** | `alive and not removed` |
| **scriptless unit** | pseudo-units created for placed buildings and furniture (side code `0x20`, `game_rules.md` R35). They run no script and **never receive events** | not a regiment |
| **tag** | one 16-bit number per unit, **0 = no tag**. Every new unit starts with 0 (a copy made by `SpawnUnit` also starts with 0; the tag is not copied). It is set **only** by `SetTag` at run time; `.BTS`/`.MRC` files have no tag keyword (the unit keys are `whoami`, `script`, `hired`, `s_*`, ...). Shipped tags are `0xABC0`–`0xABCA`, i.e. "slot numbers" chosen per mission | `unit.tag: int = 0` |
| **parent** | a **stored link to one unit**, not a tag. Set by `SetParentByTag` (to the live unit carrying that tag *at that moment*, or to none) and by `SpawnUnit` (the copy's parent is the unit that spawned it). It is never re-resolved: re-tagging either unit later does not change it. Default: none | `parent_id` — store the unit identity, not the tag |
| **`whoami`** | the unit's `.BTS`/`.MRC` `set:whoami` value, kept as one byte: the persistent campaign regiment id (0–37), 0 for ordinary mission units, 100+ for some mission NPCs (`FORMATS.md`, `notes/campaign.md`) | `unit.whoami` (needed for `SendEventToUnitId`) |

**Tag lookup** ("the unit with tag T"): T = 0 never matches. Otherwise the first **live** unit in unit-table
order whose tag equals T; none if there is no such unit. Because `SetTag` refuses a tag that a live unit already
has, at most one live unit carries a given tag; a removed unit keeps its number but is ignored by every lookup,
so its tag becomes free for reuse.

Related opcodes (already in the catalogue, restated for the model): `SetTag T` (0x34, 2 words) gives the unit tag
T **only if no live unit (itself included) has T yet**, otherwise does nothing (silently); it replaces any older
tag the unit had. `SetParentByTag T` (0x35, 2 words) sets parent := lookup(T), **overwriting the old parent with
none when the lookup fails**. `IfTagExists T` (0x36) condition := lookup(T) found. `IfTag T` (0xD5) condition :=
own tag == T. None of `SetTag`/`SetParentByTag` write the condition.

**Ordering consequence (important for the engine).** Lookups see only tags already set, and units run in table
order, so mission scripts use a two-phase handshake: every unit does `SetTag` in its first step, then `Yield`,
and only in its second step `SetParentByTag` (BF003 scripts 0/1, BF029 script 2, BF010 script 4, ...). An engine
that runs units in a different order, or skips the `Yield`, will get "no parent" for some units.

#### 0.2 Event delivery

An event record has: **recipient, code, source unit, argument, position (x, y)**. All opcodes in this report
write the argument and position as "none"/0. Queuing a record (`unit_script_control.md` §1):

- the record goes to the **head** of the recipient's queue (LIFO): it is the next one `GetEvent` takes;
- it is **silently dropped** when the recipient is not live, is scriptless, or the shared record pool is full
  (`unit_script_control.md` §5; nothing in shipped battles comes close).

There are two delivery paths with one difference:

| Path | Used by | Extra rule |
|---|---|---|
| **checked send** | `SendEventToTag`, `ReacquireEventSource` (and the own/enemy-side broadcasts) | also **refused during the deployment phase** (before the battle starts) and when there is no recipient |
| **direct queue** | `SendEventToParent`, `SendEventToUnitId` | no deployment check |

Shipped scripts only send after `WaitForBattleStart`, so the difference is invisible in shipped data; keep it for
custom scripts.

Nothing in delivery checks the recipient's state beyond "live and scripted": **routed, broken, hidden,
off-field-waiting, engaged or charging units all receive events**; whether they react is up to their handler
script. No delivery opcode checks the side or allegiance of the recipient.

#### 0.3 When the recipient handles it

Interrupt dispatch is pre-emptive (`game_rules.md` "Event dispatch is pre-emptive"): at the **start of each
unit's script step**, a non-empty queue sends the unit into its interrupt (event handler) script. Units step in
table order within a tick, so:

- recipient **after** the sender in table order → handled **in the same tick**;
- recipient **before** the sender → handled at its step in the **next tick**;
- **self**, sent from inside its own event handler (the usual case: `ReacquireEventSource`, `SendEventSelf`,
  a `SendEventToTag` that hits its own tag) → handled **in the same handler pass**: the handler's
  `ConsumeEvent` sets the condition to "queue not empty" and `LoopIfTrue` goes back to `GetEvent`, which takes
  the new record first (LIFO), before any older queued event;
- self, sent from the main script → at the start of its next step (next tick).

### 1. `ReacquireEventSource` 0x3C (60) — 182 uses (library 101 and 152 only)

(a) Two words: `ReacquireEventSource P`, P = **player-style flag** (0 or 1).
(b) Does not read or write the condition.
(c) Works on the **current event** (the one taken by `GetEvent`). Let S = its source unit. If **all** hold:

1. S **is the unit's current target** (the same unit, not merely a unit of the same side);
2. the unit is **not charging** and **not engaged in close combat**;
3. the unit is **not busy with a shooting sequence** (the script flag set with `SetUnitFlags2 4` by the library
   shooting scripts 107–125) and **not busy with a casting sequence** (`SetUnitFlags2 2`, magic scripts 129–135);

then it sends to **itself** (checked send, §0.2) an event with source = S and code:

- **0x39** if P ≠ 0 and the unit is **not independent** (the flag scripts test with `TestUnitFlags 0x8000000`);
- **0x04** ("attack this target") otherwise (P = 0, or an independent unit).

Otherwise nothing happens.

Purpose: it is the reply to events **0x09** (a charge against the unit ended) and **0x1A** (the opponent switched
to another unit) in the library handlers. If the unit was still targeting the unit that sent it, it re-issues the
attack on it: 0x04 → `TakeEventTarget` (target := S, unchanged) → attack script (105 for player units via
`IfSwitchScriptHigh`, 158 for AI). Library **101** (player infantry/cavalry handler) passes P = 1 and handles
**0x39 with `SwitchScript 163`** (rally and re-form): a player unit that is not independent **re-forms instead of
counter-attacking**; an independent one counter-attacks. Library **152** (common layer, used by AI/mission
handlers and by player handlers 102–104 through 153–156) passes P = 0: always 0x04.

(d) Edge cases: no current event — never happens in shipped data (always inside `CaseEvent`); treat as no-op.
An event whose source is "none" never equals a real current target; treat as no-op (🟡 the original compares a
source index, so a sourceless record could in theory match the first unit in the table). During deployment the
send is refused.

(e) Engine model: compare `current_event.source == current_target`; the queued event's source is the target, so
the 0x04 handler's `TakeEventTarget` keeps the same target.

(f)

| Before | Instruction (current event 0x09 from S) | After |
|---|---|---|
| target S; idle; not independent; handler 101 | `ReacquireEventSource 1` | queue head: 0x39 from S → same handler pass: `SwitchScript 163` (re-form) |
| target S; idle; independent (`TestUnitFlags 0x8000000` true); handler 101 | `ReacquireEventSource 1` | queue head: 0x04 from S → same pass: `TakeEventTarget`, `IfSwitchScriptHigh 105`, `DrainEvents` |
| target S; idle; AI unit; handler 152 | `ReacquireEventSource 0` | queue head: 0x04 from S |
| target T ≠ S | either | nothing queued |
| target S, but unit charging / in close combat / shooting / casting | either | nothing queued |

Worked example, library 101 (identical in every DLL):

```
35  CaseEvent 26        opponent switched to another unit (source = old opponent)
37  ReacquireEventSource 1
39  Break -> L69
...
18  CaseEvent 57        0x39
20  SwitchScript 163    rally + re-form
...
69  L69: ConsumeEvent   condition := queue not empty (true: 0x39 or 0x04 was just queued)
71  LoopIfTrue          -> GetEvent takes the new event at once
```

### 2. `SendEventToParent` 0x65 (101) — 134 uses (library 158 + 88 mission)

(a) Two words: `SendEventToParent E`, E = event code.
(b) Does not write the condition.
(c) If the unit has a parent: queue (direct path, §0.2) event E to the parent, **source = this unit**, argument
none. No parent → nothing. The parent is the stored link (§0.1), not looked up again: a parent that has since been
removed is not live, so the record is dropped. A parent that is routed, hidden or of another side still gets it.
(d) Shipped codes: **0x15** (77 uses), **0x14** (52, including library **158**, the AI attack-order script, whose
second instruction tells the parent "I am attacking"), **0x0C** (4: a mission flight script sends **rout** to its
parent, e.g. BF003 script 8 `FleeAhead; SendEventToParent 12`). Mission handlers answer 0x14 with `Query 9` (help
a friend who attacks) and 0x15 with `Query 10`. Most units have no parent, so library 158's send is a no-op for
them. 🟡 If a parent is removed and a later `SpawnUnit` creates a unit in the freed table slot, the original's
link would then point at the new unit; an engine using stable ids will instead drop the event. No shipped script
can trigger this.
(e) Engine: `parent_id` → `queue_event(parent, code, source=self)`; no-op if `parent_id is None` or not live.

(f)

| Before | Instruction | After |
|---|---|---|
| A.parent = B (live) | A: `SendEventToParent 20` | B.queue head = (0x14, source A) |
| A.parent = none | A: `SendEventToParent 20` | nothing |
| A.parent = B, B destroyed | A: `SendEventToParent 12` | nothing (dropped) |

Worked example, BF003 (pairs of Skaven units linked to each other): script 0 `SetTag 0xABC0; ...; Yield;
SetParentByTag 0xABC1`, script 1 `SetTag 0xABC1; ...; Yield; SetParentByTag 0xABC0`. Their shared handler,
script 6:

```
22  CaseEvent 5          message from the unit's own target
24  Query 6
26  If
27    SendEventToParent 21   -> partner gets 0x15 (source = this unit)
...
16  CaseEvent 21         on the partner
18  Query 10
```

When either attacks through library 158, the partner receives 0x14 and runs `Query 9`.

### 3. `SendEventToTag` 0xCC (204) — 26 uses (5 DLLs)

(a) Three words: `SendEventToTag T E`, T = tag, E = event code.
(b) Does not write the condition.
(c) R = lookup(T) (§0.1). If found: checked send (§0.2) of E to R, **source = this unit**, argument none. Not
found (no live unit has T, or T = 0) → nothing. R may be the sender itself, an allied, neutral or enemy unit — no
side test.
(d) Shipped codes: 0x0C (rout), 0x11, 0x14, 0x15. Refused in deployment.
(e) Engine: `r = find_by_tag(T); if r: send(r, E, source=self)`.

(f)

| Before | Instruction | After |
|---|---|---|
| unit X live with tag 0xABC0 | `SendEventToTag 0xABC0 12` | X.queue head = (0x0C, source self) |
| the unit with 0xABC0 was destroyed | `SendEventToTag 0xABC0 12` | nothing |
| the sender itself has tag 0xABC1, inside its handler | `SendEventToTag 0xABC1 17` | own queue head = (0x11, self); handled in the same handler pass |

Worked example, BF010. The NPC character (script 1, side `0x46`) does `SetTag 0xABC0`; two Skaven units do
`SetTag 0xABC1` / `SetTag 0xABC2`. Skaven handler script 7:

```
52  CaseEvent 10              this unit was engaged in close combat
54  SendEventToTag 0xabc0 12  -> the NPC gets "rout"; its handler 8: CaseEvent 12 -> SwitchScript 9
                                 (face node 12, React 4, FleeAhead)
57  SendEventToTag 0xabc1 17  -> both tagged Skaven get 0x11; their handler 7: CaseEvent 17 -> SwitchScript 6
60  SendEventToTag 0xabc2 17     (advance and attack)
63  IfEngagedWithKind 128 ...
68  SwitchScript 165
```

So the first Skaven unit to enter melee makes the NPC flee and the tagged Skaven units commit. If the engaged unit
is itself 0xABC1, it sends 0x11 to itself too (same handler pass).

### 4. `SendEventToUnitId` 0x66 (102) — 4 uses (BF015, BF017)

(a) Three words: `SendEventToUnitId W E`, W = **`whoami`** value, E = event code.
(b) Does not write the condition.
(c) R = the first **live** unit in table order whose `whoami` equals W (compared as one byte). If found: direct
queue (§0.2) of E to R, source = this unit. None → nothing.
(d) The operand is the persistent regiment id from the `.BTS`/`.MRC` (`set:whoami`), not a tag and not a table
index. W = 0 would hit the first ordinary mission unit (no shipped use). If two live units share W, the first in
table order wins (🟡 whether, in BF015/BF017, the NPC-block unit with `whoami` 24 or a player regiment with the same
id comes first depends on load order; in shipped campaign data only the NPC block is known to carry 24).
(e) Engine: `next((u for u in units if u.live and u.whoami == W), None)`.

(f)

| Before | Instruction | After |
|---|---|---|
| live unit U with `whoami` 24 | `SendEventToUnitId 24 51` | U.queue head = (0x33, source self) |
| no live unit with `whoami` 24 | same | nothing |
| U with `whoami` 24 hidden and waiting off-field | same | U receives it (hidden units are live) |

Worked example, BF015 scripts 0/1 (NPC column entering the besieged town; scripts 0 = NPC regiments, 1 = cart):

```
38  IfInNodeArea 12     reached the gate area
40  LoopIfFalse
41  IfBattleState 1     first one to arrive only
43  If
44    SetBattleState 2
46    PlaySound 11 0
49    SendEventToUnitId 24 51   -> regiment 24 gets 0x33; its handler (35 for NPCs, 101 for player units):
                                   CaseEvent 51 -> IfObjective 7 -> React 18 (a shout)
52    SendEventToEnemySide 55   -> every enemy gets 0x37
54  EndIf
55  SendEventSelf 54            -> own 0x36 ("got inside", see §5)
```

### 5. `SetSide` 0xDF (223) — 47 uses (library 152 in every DLL + BF015 script 35 + BF017 script 36)

(a) Two words: `SetSide V`, V = new side code (script data).
(b) Does not write the condition.
(c) The unit's side byte (`s_side`, the first `setstats:s_side` value, `FORMATS.md`) becomes
`V | (old & 0x1F)`: **bits 5–7 are replaced by V's, the unit type code (bits 0–4) is kept**, and V's own bits
0–4, if any, are OR-ed into the type code (no shipped operand has any).

Operand bits (file-data meanings of the side byte):

| V bit | Meaning | Engine `Side` |
|---|---|---|
| none (V = 0) | player side | `PLAYER` |
| `0x40` | neutral / NPC / allied side | `NEUTRAL` |
| `0x80` | enemy side | `ENEMY` |
| `0x20` | building/furniture pseudo-unit (never valid for a script unit) | – |
| `0xC0` | both: not used by any unit; the enemy bit makes it count as enemy for side broadcasts | – |

**Only V = 64 (`0x40`, neutral/allied) is shipped.**

What the change affects — from that moment every rule reads the new value; nothing is recomputed eagerly:

- **Side broadcasts**: `SendEventToOwnSide`/`SendEventToEnemySide` (0x62/0x63) split units by the **enemy bit
  only**, so a neutral unit is on the *same* broadcast side as player units. Moving player → neutral therefore does
  *not* change which broadcasts the unit receives or which side its own broadcasts reach.
- **Who fights whom**: friend/foe tests (threat scoring gives 0 for friends, target searches, contact
  engagement) use the new side. Player and neutral do not fight each other (`engine_gaps/neutral_units.md`).
- **Close-combat grid**: grid cells are pooled per side code (`game_rules.md` §5 "Battle grid"), so the unit uses
  the pool of its new side for any later placement (🟡 a unit already on a grid when it changes side; never happens
  in shipped data — `SetSide` is always followed by removal or teleport).
- **Combat credit**: the enemy bit picks the side a combat result is credited to (`game_rules.md` §3, `s_side`).
- **Player control**: only player-side units get the command panel and can be ordered
  (`deployment.md`: side-64 units "receive no player command"); a unit set to 64 stops being commandable 🟡
  (not observable in shipped data: the unit leaves the field straight away).
- **Objective counting**: objectives that count populations by side count the unit under its new side at their
  next evaluation (objectives Z/G, `game_rules.md` "Missions and objectives") 🟡.
- **Not changed**: the unit's script, current target, parent, tag, `whoami`, colours/sprites (sprites come from
  `troopsprites`, not from the side) 🟡, and **other units' targeting of it** — they keep it as target until told
  otherwise, which is why both shipped uses send "unit removed" (0x16) to the enemy side first.

There is no separate AI controller to hand over: a unit's behaviour is its script, which keeps running.
(The Madness spell changes side through its own rule, `game_rules.md` §8 "Spells", not through this opcode.)

(d) Edge cases: V with low bits (custom data) alters the type code; `0x20` would turn a scripted unit into a
furniture-coded unit for the grid rules — reject or warn in an engine.

(e) Engine: `unit.side = side_of_code(V)`; keep the type code; no other state change.

(f)

| Before (side byte) | Instruction | After |
|---|---|---|
| `0x03` (player, Human Archers) | `SetSide 64` | `0x43` (neutral, type 3) |
| `0x46` (neutral, type 6) | `SetSide 64` | `0x46` (unchanged) |
| `0x87` (enemy, Skaven) | `SetSide 64` | `0x47` (neutral) — now on the player's broadcast side |

Worked example, library 152 (objective G "Inside the gates!", `game_rules.md` "Objective G"): a player unit
reaching the interior node receives 0x36:

```
16  CaseEvent 54
18  IfObjective 7
20  If
21    IfSwitchScriptHigh 170   leave the battle at handler end (teleport to node 24, removed)
23    SendEventToEnemySide 22  sent while still player side: every enemy gets 0x16 "unit removed" -> retarget
25    SetSide 64               player -> neutral/allied
27    SetUnitFlags 256         "inside the walls" state
29  EndIf
```

BF015 script 35 / BF017 script 36 (the NPC column's handler) do the same on 0x36, except that rolling stock
(`IfClass 56`) does not switch to 170 and instead drives on to its exit node, and `DrainEvents` precedes the
broadcast. For those NPC units (side already `0x4x`) `SetSide 64` changes nothing.

### 6. `SetTargetByTag` 0x38 (56) — 5 uses (BF029, BF036)

(a) Two words: `SetTargetByTag T`.
(b) **Writes the condition**: true if found, false otherwise.
(c) R = lookup(T). Found → `current_target := R`, condition true. Not found → **target unchanged**, condition
false. No event is queued, no route is planned, no range/arc/visibility/side/broken test is made (the scripts test
those afterwards, e.g. `TargetInCastArc`). `current_target` is the same slot as the engaged enemy
(`target_queries.md`).
(d) T = 0 → false. A routed or hidden tagged unit is still found.
(e) Engine: `r = find_by_tag(T); if r: unit.current_target = r; cond = r is not None`.

(f)

| Before | Instruction | After |
|---|---|---|
| target X; unit with 0xABC1 = Y live | `SetTargetByTag 0xABC1` | target Y, cond true |
| target X; no live unit with 0xABC1 | `SetTargetByTag 0xABC1` | target X, cond false |
| target none; Y with 0xABC0 routed | `SetTargetByTag 0xABC0` | target Y, cond true |

Worked example, BF029 script 0 (an allied wizard): three enemy units tag themselves `0xABC0`–`0xABC2` (scripts 2–4);
the wizard loops over them:

```
21  PushPC; SetWait 5; Wait; IfCastingAnimation 0; LoopIfTrue   wait until not casting
28  SetTargetByTag 0xabc0
30  If
31    GosubScript 10        turn to face, choose a spell, cast
33  EndIf
48  SetTargetByTag 0xabc1   ... same for 0xabc1, 0xabc2, then Loop
```

A destroyed tagged unit is simply skipped (condition false, target left as it was).

### Summary

- Events carry (recipient, code, source, argument, x, y); all opcodes here set source = the sending unit (except
  `ReacquireEventSource`, which re-sends with source = its current target), argument/position none, and put the
  record at the head of the recipient's LIFO queue. Recipients must be **live** (not removed) and scripted;
  routed, hidden and off-field-waiting units receive normally. Missing recipients → silent no-op. Send ops never
  write the condition; `SetTargetByTag` does.
- `SendEventToTag` and `ReacquireEventSource` are refused during deployment; `SendEventToParent` and
  `SendEventToUnitId` are not.
- Handling time follows unit-table order: same tick if the recipient steps later, next tick otherwise, same handler
  pass for self-sends from a handler.
- Tag = runtime-only 16-bit number (0 = none), unique among live units by `SetTag`'s refusal rule, never in files.
  Parent = stored unit link set by `SetParentByTag` or `SpawnUnit`. `SendEventToUnitId` addresses the `.BTS`
  `whoami`.
- `SetSide V` replaces side bits 5–7 with V's; shipped V = 64 only (player → neutral/allied for objective G).
  Own/enemy broadcasts depend on the enemy bit alone.
- `ReacquireEventSource` resumes the attack on the current target when the event came from it; player handler 101
  turns it into a re-form for non-independent units.

### 🟡 Uncertainties

- `SetSide` side effects on player control, HUD colour/markers and objective population counts are inferred from
  the side's general meaning, not observed (shipped uses remove the unit immediately).
- Grid behaviour of a unit that changes side while on a close-combat grid (no shipped case).
- Unit-table load order between `.BTS` NPC units and the player's army (matters only for `SendEventToUnitId 24` if
  two live units shared `whoami` 24).
- `ReacquireEventSource` with a sourceless current event; stale parent link after slot reuse by `SpawnUnit` (no
  shipped case for either).
- Meaning of `React 18` (the line regiment 24 shouts in BF015/BF017) and of mission event 0x11 beyond the handlers
  shown.
- BF010 script 1 calls `FollowParent` but nothing gives that unit a parent (likely a no-op in the original).

## Part C — node areas

Public implementation report (batch 5, group 3). Behaviour only. Companion to `notes/target_queries.md`
(§1 shared geometry: regiment position, condition word) and `notes/movement_formation.md` (unit states).
Lengths are those of `whshr/behaviour.py` (`LENGTHS`): 0xC9 = 2 words, 0xCA = 2 words, 0xCB = 4 words.

Use counts (mission DLLs only; the shared library 100–170 never uses them): 0xC9 27, 0xCA 136, 0xCB 55 — 218 in
total, in BF004_3, BF004_4, BF008, BF009, BF011, BF014, BF015, BF017, BF019, BF020, BF033, BF035, BF036, BF037.

### 1. What a "node" is here

The node operand is the **0-based index of the node in the order the `[NODES]` section of the mission's `.BTS`
lists them** (the same number as the `; Script Node N` comment, and as `MoveToNode`/`TeleportToNode` use). It is
**not** the node's `id` field: in 1043 of the 1096 shipped nodes `id` differs from the position (it is mostly 0).
Every node number used by these three opcodes in the shipped scripts is below its own `.BTS` node count.

The **node area is a circle**: centre = the node's `x`, `y`, radius = the node's `radius` field (`FORMATS.md`
".BTS", `NODES` row). Nothing else of the node is consulted:
- `dir` is ignored (node 23 of BF020 has `dir` 511 and is a plain circle);
- `status` is ignored: `ns_active`, `ns_startpos`, `ns_artillary`, `NS_END` make no difference — a node without
  `ns_active` would still be tested.

Radii vary a lot: start nodes are typically 16–21, the trigger nodes used by these opcodes range from 10 up to
over 1100 (BF020 node 25: radius 1108), so the circle can cover a large part of the field.

### 2. The membership test (shared by all three opcodes)

A unit is **in** node *n* when its **regiment position** (the unit centre, `target_queries.md` §1) satisfies

    (ux − nx)² + (uy − ny)²  ≤  radius²

- **Euclidean**, centre of the regiment only: no footprint, no model positions, no frontage. A regiment whose
  front rank overlaps the circle but whose centre is outside is **not** in it.
- **Inclusive** boundary (`≤`).
- **No truncation**: unlike the distance of `target_queries.md` §1 (`trunc(√…)`), the exact distance is compared
  with the radius. This matters by one unit: with radius 16, an offset of (16, 1) (d ≈ 16.03) is **outside**,
  although `trunc(d)` = 16. Compare squared values to get it right.
- Unit and node coordinates are in the same battlefield frame as the `.BTS` `x`/`y` of units and nodes (a unit
  placed on a start node gets exactly that node's position).
- A radius of 0 accepts only a unit exactly on the centre.

### 3. Which units are examined

`IfInNodeArea` tests **only the running unit itself**.

`IfAnyUnitInNodeArea` and `IfSideUnitInNodeArea` scan **every unit currently in the battle**, in unit-array order,
and stop at the first one inside. "In the battle" means the unit has not been removed. A unit is removed when:
- its last model is killed (the unit is destroyed);
- it leaves the field (a fleeing unit running off the edge);
- a script removes it (`RemoveFromBattle` 0x8C, e.g. library script 170 of the siege missions).

Everything else counts, in particular:

| Unit state | `IfAnyUnitInNodeArea` | `IfSideUnitInNodeArea` |
|---|---|---|
| the running unit itself | **counts** | counts if its side matches and it has none of the excluded states |
| hidden (ambushers not yet revealed) | counts | counts unless the exclude operand names "hidden" |
| broken / fleeing but still on the field | counts | counts unless the exclude operand names "broken" (all shipped uses do) |
| in melee, charging, re-forming, halted, … | counts | counts unless excluded |
| destroyed, fled off the field, removed by script | not examined | not examined |
| any side (player, allied, enemy) | counts | only the requested side |
| building / furniture pseudo-unit (side code 0x20, `movement_formation.md` "leave the grid") | 🟡 counts if its position is inside | only with side operand 0x20 (never used) |

### 4. Opcodes

#### 4.1 `IfInNodeArea n` — 0xC9, 2 words

| Operand | Meaning |
|---|---|
| `n` | node index (§1) |

Condition := the running unit is in node *n* (§2). Always written (true or false). No side effects.

#### 4.2 `IfAnyUnitInNodeArea n` — 0xCA, 2 words

| Operand | Meaning |
|---|---|
| `n` | node index (§1) |

Condition := at least one unit in the battle (§3, **any side, any state, including the running unit**) is in
node *n*. Always written; false when no unit is inside. No side effects.

#### 4.3 `IfSideUnitInNodeArea side n exclude` — 0xCB, 4 words

| Operand | Meaning |
|---|---|
| `side` | side code to look for. Only the **low byte** is used, and it is compared with the unit's side code (the top three bits of `s_side`'s first byte, i.e. `s_side & 0xE0`). Values: **0 = player**, **64 (0x40) = allied** (the NPC side, e.g. the carts of BF020 or units switched by siege library script 152), **128 (0x80) = enemy**, 32 (0x20) = building/furniture pseudo-units. A value with any of the low five bits set (e.g. 129) never matches. Shipped scripts use only **0** and **64**. |
| `n` | node index (§1) |
| `exclude` | unit-state mask, same bit set as `TestUnitFlags`: a unit that has **any** of these states is skipped. Shipped scripts always pass **0x2000 = broken** (`target_queries.md` "the broken flag"). 0 excludes nothing. Other `TestUnitFlags` states would work the same way (e.g. 0x80000 = hidden). |

Condition := at least one unit in the battle (§3) whose side code equals `side`, that has none of the `exclude`
states, is in node *n*. Always written; false when none. The running unit is examined like any other. No side
effects. The side is an absolute code, **not relative** to the running unit: an enemy script asking for side 0 is
looking for player regiments.

#### 4.4 Node that does not exist

No shipped script uses one. An index at or above the node count but below the node table's capacity (which is at
least 100 entries, or the node count if larger) reads an empty node: radius 0 at the origin of the internal
battlefield frame — so the condition is practically always false. An index beyond the capacity is undefined; an
engine should treat any missing node as **condition false** (and may warn).

### 5. Test vectors

Coordinates are battlefield coordinates (`.BTS` frame). "Cond" is the condition bit before/after.

#### 5.1 `IfInNodeArea`

| Before | Instruction | After |
|---|---|---|
| Node 3 = (920, 540) r 66. Running unit at (899, 572) (d² = 1465 ≤ 4356). Cond false. | `IfInNodeArea 3` | Cond **true**. |
| Node 5 = (100, 100) r 16. Running unit at (116, 101) (d² = 257 > 256; d ≈ 16.03, `trunc` = 16). Cond true. | `IfInNodeArea 5` | Cond **false** (no truncation). |
| Same node. Running unit at (116, 100) (d² = 256, exactly on the boundary). Cond false. | `IfInNodeArea 5` | Cond **true** (inclusive). |

#### 5.2 `IfAnyUnitInNodeArea`

| Before | Instruction | After |
|---|---|---|
| Node 3 = (920, 540) r 66. Only unit inside: an enemy regiment at (899, 572); running unit elsewhere. Cond false. | `IfAnyUnitInNodeArea 3` | Cond **true** (side irrelevant). |
| Node 3 as above. No other unit inside; the **running unit** stands at (920, 540). Cond false. | `IfAnyUnitInNodeArea 3` | Cond **true** (the running unit counts). |
| Node 3 as above. A broken player regiment fled across (930, 560) and has since left the field; no other unit inside. Cond true. | `IfAnyUnitInNodeArea 3` | Cond **false** (removed units are not examined). A broken regiment still on the field at (930, 560) would give **true**. |

#### 5.3 `IfSideUnitInNodeArea`

| Before | Instruction | After |
|---|---|---|
| Node 23 = (1444, 684) r 686. A player regiment (side 0, not broken) at (2000, 800): d² = 322 592 ≤ 470 596. Cond false. | `IfSideUnitInNodeArea 0 23 0x2000` | Cond **true**. |
| Same node. The only unit inside is that player regiment, now **broken** (still on the field). Cond true. | `IfSideUnitInNodeArea 0 23 0x2000` | Cond **false** (excluded state). With `exclude` = 0 it would be true. |
| Same node. Only units inside: an allied cart (side 64) at (2100, 801) (d² = 444 025 ≤ 470 596) and the running enemy unit itself. Cond false. | `IfSideUnitInNodeArea 0 23 0x2000` | Cond **false** (side 0 asked; enemy and allied units ignored). The same state with `IfSideUnitInNodeArea 64 23 0x2000` gives **true**. |

### 6. Worked examples from shipped missions (numbers only)

#### 6.1 BF020 — ambush sprung by the convoy or the player (0xCB)

`BF020.BTS` nodes used: 21 = (30, 802) r 16 and 22 = (−8, 801) r 16 (the convoy's route ends);
23 = (1444, 684) r **686**; 24 = (843, 837) r **845**; 25 = (−23, 1007) r **1108**.
Units: six enemy regiments (side code 0x80), all **hidden**, scripts 1–6; four allied carts (side code 0x40,
script 0) starting at x = 2438…2921, y ≈ 801; the player starts on nodes 0–20 (x ≥ 2438).

Script 0 (the carts): `MoveToNode 21`, wait until halted, `MoveToNode 22`, wait until halted, `RemoveFromBattle`.

Scripts 1–5 (the hidden enemy), every 10 ticks:

    IfSideUnitInNodeArea 0 23 0x2000      ; a non-broken player regiment inside node 23?
    If   GotoScript 7                     ; yes: attack
    Else IfSideUnitInNodeArea 64 23 0x2000 ; no: a non-broken allied cart inside node 23?
         If   GotoScript 7
         Else TestUnitFlags 0x80000       ; still hidden?
              IfNot GotoScript 7          ; revealed some other way: attack
    Loop

(Script 1 watches node 23, scripts 2–3 node 24, scripts 4–5 node 25.)

Trace: at the start the nearest cart is at (2438, 801): d² = 994² + 117² ≈ 1 001 725 > 686² = 470 596, so all
tests are false and the bandits stay hidden. Driving west along y ≈ 801, the leading cart enters node 23 when
(x − 1444)² + 117² ≤ 470 596, i.e. at **x ≤ 2119** (about 676 past the centre). On the next 10-tick check script 1
goes to script 7. Nodes 24 and 25 trigger later in the same way as the convoy (or a player regiment) moves on
west. The hidden bandits themselves never satisfy the test, because they are side 0x80; broken player regiments
do not spring the trap either.

#### 6.2 BF008 — reinforcements wait for a clear entry point (0xCA)

`BF008.BTS` node 3 = (920, 540) r **66**. Enemy units: script 0 at (899, 572) — **inside** node 3 (d ≈ 38) —
and two hidden units with scripts 1 and 2 at (919, 382) and (992, 453), both outside it (d ≈ 158 and 113).

Scripts 1 and 2, after an initial wait (90 and 250 ticks):

    loop: SetWait 10 / Wait / IfAnyUnitInNodeArea 3 / LoopIfTrue
    ScatterModelsToNode 1 / SnapModelsToFormation / TeleportToNode 3 / ReformToScriptRanks / …

They keep polling every 10 ticks while **any** unit — the enemy's own script-0 regiment at first, or any player
regiment fighting there later — has its centre within 66 of (920, 540), and appear at node 3 only once it is clear.
Because they wait off the circle, their own presence does not block them; a unit placed inside its own entry
circle would block itself forever.

### Summary

- 0xC9 `IfInNodeArea n` (2 words), 0xCA `IfAnyUnitInNodeArea n` (2 words), 0xCB `IfSideUnitInNodeArea side n
  exclude` (4 words). `n` = 0-based file-order index in `[NODES]`, not the `id` field.
- Area = circle of the node's `radius` around its `x`,`y`; `dir` and `status` ignored. Test on the regiment centre
  only: `dx² + dy² ≤ r²`, inclusive, no truncation.
- 0xCA/0xCB scan all units still in the battle (destroyed, fled-off and script-removed units are gone); hidden,
  broken, engaged units and the running unit itself all count unless 0xCB's exclude mask names their state.
- 0xCB side codes: 0 player, 64 allied, 128 enemy, 32 building/furniture; absolute, not relative to the caller;
  shipped scripts use 0 and 64 with exclude = 0x2000 (broken).
- The condition is always written; a non-existent node gives false in practice.

### 🟡 Uncertainties

- 🟡 Building/furniture pseudo-units (side code 0x20) are in the same unit array as regiments, so
  `IfAnyUnitInNodeArea` should see one whose position lies inside the circle. Not observed in a shipped mission;
  check before relying on it (an engine without such pseudo-units loses nothing in the shipped scripts unless one
  sits in a polled node).
- 🟡 Units that have not yet entered the battle in a form other than "hidden" (e.g. a copy not yet made by
  `SpawnUnit` 0xD3) are not in the array until they exist; whether any other kind of off-field reserve is kept in
  the array before arrival was not traced.
- 🟡 Out-of-range node index behaviour (§4.4) is only "practically false"; no shipped script exercises it.
- 🟡 The "regiment position" while a unit is re-forming or its models are scattered is the unit centre, not the
  models' mean; for a scattered unit the two can differ (consistent with `target_queries.md` §1, not separately
  observed in play).
