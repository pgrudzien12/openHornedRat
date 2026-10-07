# Unit-script AI queries and unit tests

Public implementation report (batch 8 of the interpreter requests, GitHub #3). Behaviour only. Companion to
`threat_events_nodes.md` (terms of §0: side, hostile, threat slot, unit order; event delivery Part B §0.2/§0.3),
`unit_script_control.md` (condition word, LIFO event queue), `target_queries.md`, `movement_formation.md`,
`deployment.md` §5.3 (periodic behaviour countdown) and `game_rules.md` ("Unit behaviour scripts and events",
"Routes, collisions and visibility" → "AI decisions", "Engagement: battle grid and pairing", "Night Goblin
Fanatics", "Scripted target and flight opcodes").

Part A covers `Query N` (0x16); Part B the class, machine, objective and target tests (`IfClass`, `SetClass`,
`IfMachineDestroyed`, `IfObjective`, `TargetGone`, `TargetValid`).

## Part A — `Query N` (0x16)

`Query N` is 2 words (opcode + case number N). The same case numbers are also the **behaviour codes** of
`SetBehaviour code period` (0x33), run periodically before the unit's script step (`deployment.md` §5.3). In shipped
scripts the two uses do not overlap: `Query` uses cases 0, 1, 3, 5–10, 17, 18, 22–24; `SetBehaviour` uses 0, 11–16,
19–21, 26, 27 (only 15 is described here, for the worked example).

Uses across all 45 script DLLs (the 44 `BFxxx.DLL` plus `NULL.DLL`; the library 100–170 is counted once per DLL):

| N | Uses | Library | Mission uses | Typical context |
|---|---|---|---|---|
| 0 | 1 | – | BF039 script 9 | fanatic idle loop |
| 1 | 152 | 127, 148, 164 (3 × 45) | 17 (BF003, BF004_2, BF021) | `Query 1; IfThreatOutweighsWorth; SendEventSelfIfTrue 3` |
| 3 | 3 | – | BF003 s1, BF004_1 s3, BF004_2 s4 | `Query 3; IfNot …` |
| 5 | 96 | 105, 158 (2 × 45) | 6 copies of 158 | first instruction of an attack script |
| 6 | 137 | 152 on event 0x05 | 92, all on event 0x05 | often `If; SendEventToParent 21` |
| 7 | 45 | 161 | – | brace |
| 8 | 45 | 152 on event 0x0B | – | contact |
| 9 | 225 | 151 on event 0x13 | 92 on 0x13, 88 on 0x14 | assist a friend |
| 10 | 76 | – | 76, all on event 0x15 | assist a friend's threat |
| 17 | 4 | – | fanatic interrupt scripts, on event 0x34 | wander |
| 18 | 4 | – | fanatic main loops | fanatic update |
| 22 | 52 | 152 on event 0x16 | 6 on 0x16, 1 on 0x1B | drop a removed unit |
| 23 | 45 | 152 on event 0x0E | – | same as 22 |
| 24 | 90 | 106, 160 (2 × 45) | – | charge sound |

---

## 0. Shared state first

### 0.1 The condition

`Query N` **always writes the condition**: true when the case reports success, false otherwise — including every
case that has nothing to report. Cases that can return true: **1, 3, 6, 7, 9, 10**. Cases that **always** leave the
condition false: **0, 5, 8, 17, 18, 22, 23, 24** (and any unknown N). There is no case that leaves the condition
unchanged.

Engine-model difference: "Query N writes false with no side effects" is right only for case 0.

### 0.2 State touched by the cases

| State | Written by | Read by |
|---|---|---|
| **threat slot** (unit or none) + **stored threat score** | 1 (always, outside deployment: best or none / best score or 0); 6 (only when it switches); 22/23 clear the slot only (the stored score is left as it was) | 6 (recomputes the slot's score — the stored score is not used); 10 (the **friend's** slot); `IfThreatOutweighsWorth` (recomputes); `ReactToThreat` (uses the stored score) |
| **current target** | 7 (the remembered charger); 22/23 (switch to another opponent in contact); 8 (via the contact handler) | 5 (recipient); 9 (self must have none; the friend must have one); 10 (self must have none); 22/23; 8 |
| **parent** link | 22/23 clear it when the parent is the removed unit | 18 (fanatic) |
| **remembered event** (`StoreEventInfo`, game_rules) | 7 clears its code | 7 |
| **braced** state | 7 sets it | 7 (refuses when already braced) |
| **current event's source** | – | 6, 9, 10, 22/23 — these must run inside an event handler; the original has no guard for "no current event" (🟡 treat as false / no-op) |
| unit position / facing / re-forming | 17 | – |
| charge sound handle | 24 | 24 |

**Events queued** (delivery paths of `threat_events_nodes.md` Part B §0.2):

| Case | Event | Recipient | Source | Path |
|---|---|---|---|---|
| 3, 9, 10 | 0x04 "attack target" | the unit itself | the chosen unit | **checked** (refused during deployment) |
| 5 | 0x05 | the unit's current target | the unit | **direct** (no deployment check) |
| 8 | 0x07, 0x09, 0x1A, 0x0C | various (§6) | the unit | checked |
| 22/23 | 0x19 "current opponent gone" | the unit itself | none (0) | direct |

Cases 3, 9 and 10 report true **after the send attempt**, whether or not the event was actually queued (so during
deployment they can return true with nothing queued).

### 0.3 Distance and score used by the cases

- **Distance** `d` in every case here (and in `UnitScore`) is the octagonal distance between unit positions,
  **integer, half rounded up**: `d = max(|dx|, |dy|) + ceil(min(|dx|, |dy|) / 2)`. (`game_rules.md` writes
  `max + min/2`; with an odd `min` the original is one larger than a floor, e.g. dx = 31, dy = 100 → 116, not 115 or
  115.5.) Correction worth making in `game_rules.md`.
- **Range** `R` is the searching unit's own **threat range** (`SetThreatRange`). Every range test here is
  **strict**: `d < R`.
- **`UnitScore(S, U)`** (game_rules formula, restated with the exact exclusions): 0 when U is none, U is **not
  hostile** to S (same army bit: player army vs allied side is not hostile), U is **in melee**, **broken** or
  **pursuing**, or `R − d ≤ 0`. Otherwise `base = trunc(worth(U) × (R − d) / trunc(R / 4))`; if U's current target is
  S the score is `base × 4`, and if U is also **charging** it is `base × 32` instead. **Hidden is not an exclusion of
  the score itself** (correction to game_rules' "0 for … CantMelee or hidden units": the exclusions are in melee,
  broken and pursuing; hidden units are kept out by the candidate filters of the searches, §1). No visibility test.
- 🟡 **16-bit arithmetic quirk.** The score is a signed 16-bit value and the ×4/×32 multiplications wrap. A charging
  threat with `base > 1023` (possible when its worth exceeds 255 and it is close) gets a **negative** score: it then
  never wins a search and never "outweighs" anyone. Example: worth 300, R = 240, d = 10 → base 1150 → ×32 = 36 800 →
  stored as −28 736. Implement the wrap if exact parity matters; it was not observed in play.

### 0.4 Deployment

- Case 1 does nothing during deployment (condition false, slot and score unchanged).
- The checked sends of cases 3, 9, 10 and the contact handler are refused during deployment (see §0.2).
- Cases 5, 6, 7, 17, 22/23, 24 behave the same in deployment. Periodic behaviours do not run during deployment
  (`deployment.md` §5.3). Shipped scripts reach every `Query` only after `WaitForBattleStart` or from event handlers.

---

## 1. Case 1 — pick the best threat

Scans every live unit in **unit order** and keeps the one with the highest `UnitScore(self, U)`.

- **Candidates**: live units that are **not hidden**, **not marked** (the state set by `SetUnitFlags 256`, see note)
  and **not scriptless** (buildings/furniture). Broken, in-melee and pursuing units and non-hostile units score 0
  and therefore never win.
- **Ranking**: strictly greater score replaces (start value 0), so ties go to the **first** unit in unit order, and a
  unit must score **> 0** to be picked. No visibility, arc or line-of-sight test; no class filter.
- **Writes**: threat slot := winner (or **none**), stored score := its score (or 0). Query 1 **clears** the slot when
  nothing qualifies.
- **Condition**: true iff a winner exists (score ≠ 0).
- **Deployment**: nothing written, false.
- No event, no bark, no current-target change. Immediate (one call).

Note on **marked**: `threat_events_nodes.md` §0 names this state "leaving the battle" (library 152 sets it with
`SetUnitFlags 256` on event 0x36 in objective-G battles). Mission scripts also set it at the start on their own
non-combatant units (BF003 scripts 2–4, BF004_1/2/3/4, BF004_5 script 12), so a neutral name such as "marked" fits
better; the rules are the same.

| Before (S at (0,0), R = 240, divisor 60) | Instruction | After |
|---|---|---|
| E1 worth 100 at (0,100), E2 worth 100 at (31,100); slot empty | `Query 1` | E1: d = 100 → 233; E2: d = 116 → trunc(100×124/60) = 206; slot = E1, score 233, cond true |
| E1 at (0,239) | `Query 1` | score trunc(100×1/60) = 1 → slot E1, true; at (0,240): score 0 → slot none, score 0, false |
| E1 and E2 both worth 100 at (0,100) and (100,0), E1 first in unit order | `Query 1` | tie 233 = 233 → slot = E1 |
| E1 at (0,100) whose target is S | `Query 1` | 233 × 4 = 932; if E1 is also charging: 233 × 32 = 7456 |
| Only enemy E1 is in melee (or broken, pursuing, hidden, marked) | `Query 1` | slot none, score 0, false |
| slot = E1 (stale), no candidate scores > 0 | `Query 1` | slot cleared, false |
| Deployment, slot = E1 | `Query 1` | unchanged, false |

## 2. Case 3 — attack the nearest marked enemy

- **Candidates**: live units of the **opposite army** (army bit differs), **not broken**, **marked** and **not
  scriptless**. **Hidden units are not excluded.** No range limit (whole field), no visibility test, no class filter.
- **Ranking**: smallest octagonal `d`, strictly smaller replaces → first in unit order on ties.
- **Found**: queue event **0x04** to self, source = the chosen unit (checked send); condition **true**. The current
  target and threat slot are **not** written here (the 0x04 handler, `TakeEventTarget` then script 158, does that).
- **None**: condition false, nothing else.

Shipped use: BF003 script 1 (the attackers) and BF004_1/2: `Query 3; IfNot { Query 1; IfThreatOutweighsWorth;
SendEventSelfIfTrue 3; … }` — attack the nearest marked unit (the villagers/convoy), otherwise fall back to the threat
logic.

| Before (S enemy army at (0,0)) | Instruction | After |
|---|---|---|
| Allied marked V1 at (0,300), marked V2 at (100,250) | `Query 3` | d(V1) = 300, d(V2) = 250 + 50 = 300 → tie → V1 (first); 0x04 (source V1) to S; true |
| V1 marked but broken; no other | `Query 3` | false, nothing queued |
| V1 marked and hidden | `Query 3` | V1 chosen (hidden is not a filter here) |
| During deployment, V1 marked | `Query 3` | event refused, **true** |

## 3. Case 5 — tell my target I am attacking it

- Queues event **0x05** to the unit's **current target**, source = the unit, by the **direct** path (no deployment
  check; dropped only if the recipient is not live or is scriptless).
- Condition always **false**. Nothing else changes.
- 🟡 No current target: the original does not guard this (it would fail); shipped uses are only at the top of attack
  scripts 105/158 (and mission copies of 158), entered after the target was set. Engine: do nothing, false.

The recipient's default handling is library 152 → `Query 6` (§4): the attacked unit considers its attacker as a threat.

## 4. Case 6 — prefer the event's source as threat

Inside an event handler (shipped: always event **0x05**). Let A = the source of the current event.

1. If A is **hidden** → false, nothing changes.
2. `new = UnitScore(self, A)`; `old = UnitScore(self, threat slot)` **recomputed now** (0 if the slot is empty) — the
   stored score is not used.
3. If `old < new` (**strict**): threat slot := A, stored score := new, condition **true**.
4. Otherwise false, nothing changes.

No hostility check beyond `UnitScore` (a friend scores 0 and never wins). No event, no target change. Works in
deployment too.

Typical mission use: `CaseEvent 5; Query 6; If; SendEventToParent 21; EndIf` → the parent receives 0x15 and runs
`Query 10` (§8) — "my attacker becomes my parent's target".

| Before (S, R = 240) | Event / instruction | After |
|---|---|---|
| slot empty; event 0x05 from E (worth 100 at (0,100), E's target = S) | `Query 6` | new = 932, old 0 → slot E, score 932, true |
| slot = E1 now scoring 932; event from E2 also scoring 932 | `Query 6` | not strictly greater → unchanged, false |
| slot = E1 whose score has dropped to 0 (now in melee); event from E2 scoring 1 | `Query 6` | slot E2, score 1, true |
| event from hidden E2 | `Query 6` | false |

## 5. Case 7 — brace against the remembered charger

Already described in `game_rules.md` "`StoreEventInfo` (0x61)", with **one correction**: the precondition is
"the unit is **not already braced**", not "not broken".

- If the unit is not braced and the remembered event code is **0x07**: clear the remembered code (one bracing per
  stored event), current target := the remembered sender (no validity check), set the **braced** state, and reset
  every model's per-model movement lock (🟡 exact visible effect; game_rules describes it as stopping the models'
  walk); condition **true**.
- Otherwise false, nothing changes. Broken units are not refused here (they are refused earlier, by library 151/153–156
  before switching to 161).
- Effects of the braced state relevant here: `ReactToThreat` refuses, periodic threat tracking (§12) does not queue
  0x03, and the contact handler skips braced units (game_rules "Engagement").

| Before | Instruction | After |
|---|---|---|
| remembered 0x07 from C, not braced | `Query 7` | target C, braced, remembered code cleared, true |
| same, second call | `Query 7` | false (code already cleared) |
| remembered 0x07, already braced | `Query 7` | false, remembered code kept |
| remembered 0x07, broken, not braced | `Query 7` | acts: target C, braced, true |

## 6. Case 8 — resolve a contact

Runs the game's **contact handler** for the map object the unit last collided with (recorded by the collision pass
that raised event **0x0B**). Condition always **false**. This is the second step of the engagement handshake in
`game_rules.md` "Engagement: battle grid and pairing" — implement it there; summary of the decisions:

1. Nothing if the unit is in the **cannot-engage** state (game_rules R70; side finding: that state is set while
   **Flying Bower** lifts the caster's unit off the map), or the contacted object is gone or is a routing unit's
   record.
2. Set the one-tick contact latch.
3. Contacted **regiment** U:
   - U cannot-engage, or U is a friend that is not the current target → clear the latch, nothing.
   - The unit is **charging or pursuing**: U ≠ current target → redirect the charge (0x1A to the old target, 0x07 to
     U, target := U); U = target → engage as charger; if refused → event 0x0C to U 🟡.
   - Not charging: no current target → (unless broken) target := U and event **0x07** to U ("you are being charged",
     source = the unit); current target T ≠ U → 0x1A to T, engage U (the unit not yet on a grid joins), if refused 0x0C
     to U 🟡, target := U; T = U → engage, if refused 0x0C to the unit itself.
4. Contacted **building/furniture** whose unit is the current target → engage it; otherwise a charging unit not in
   melee **ends its charge** (halt, charge sound stopped, 0x09 to its target).
5. 🟡 Other object kinds owned by a unit: target → engage; hostile → redirect.

## 7. Case 9 — assist a friend who attacks

Inside an event handler (shipped: events **0x13** "a friendly unit attacks" and **0x14** report from a child). Let F =
the event's source.

- Succeeds iff **F has a current target T**, **`d(self, F) < R`** (distance to the **friend**, not to T; R = own
  threat range) and **the unit has no current target**.
- Then queue **0x04** to self with source **T** (checked send) and return **true** (even if the send was refused).
- No check of T's state, side, visibility or distance. Otherwise false, nothing.

| Before (S, R = 240, no target) | Event / instruction | After |
|---|---|---|
| F at (0,239) targets E far away at (0,2000) | 0x13 from F, `Query 9` | 0x04 (source E) to S, true |
| F at (0,240) | `Query 9` | false |
| F at (31,224): d = 224 + 16 = 240 | `Query 9` | false (a floor metric would give 239 → true) |
| S already has a target | `Query 9` | false |
| F has no target | `Query 9` | false |

## 8. Case 10 — assist a friend against its threat

As case 9 but with T = **F's threat slot** (shipped: event **0x15**, a child's report): succeeds iff T exists,
**`d(self, T) < R`** (here the distance **is** to T) and the unit has no current target → 0x04 (source T) to self,
true. Otherwise false.

## 9. Cases 22 / 23 — a unit left the battle

Identical. Library 152 runs 22 on event **0x16** (unit removed) and 23 on **0x0E** (unit left the battlefield); one
mission runs 22 on **0x1B**. Let X = the event's source.

1. If the threat slot is X → slot := none (the stored score is left).
2. If the parent is X → parent := none.
3. If the current target is X:
   - not in melee → queue **0x19** to self (direct);
   - in melee → look for another opponent: the first of the unit's models whose paired opponent belongs to a unit
     ≠ X that is **hostile**, **not a building** and **on a battle grid**. None → the unit **leaves its battle grid**
     and 0x19 is queued. Found → every model paired with a model of X loses that pairing (re-paired by the normal
     pairing pass), the unit's pairing mode and attack direction are reset, current target := that opponent; no
     event.
4. Condition always **false**.

| Before | Event / instruction | After |
|---|---|---|
| slot X, target Y | 0x16 from X, `Query 22` | slot none, target Y, no event |
| target X, not in melee | `Query 22` | 0x19 to self |
| target X, in melee with X and Z (Z's models paired with ours) | `Query 22` | target Z, pairings with X dropped, no event |
| target X, in melee only with X | `Query 22` | left the grid, 0x19 to self |

## 10. Cases 17 / 18 — fanatics

Both need the fanatic model of `game_rules.md` "Night Goblin Fanatics" (parent link, hidden-until-clear, jump).
Condition always false.

- **18 `FanaticUpdate`**: the per-update fanatic routine of that section (release when no model of the parent is within
  reach; afterwards collision damage, death on artillery/rolling stock/buildings, terrain removal). Shipped loop:
  `SetThreatRange 64 0; loop { SetWait 5; Wait; Query 18 }`.
- **17 `Wander`** (fanatic interrupt scripts on event **0x34** "destination reached", so it repeats forever): two
  `rand()` draws, in this order:
  1. facing := `(facing + 128 − trunc((rand() mod 512) / 2)) mod 512` — an instant turn of −127…+128 (about ±90°);
  2. step `s = (rand() mod 4 + 4) × 12` (48, 60, 72 or 84); the unit's position jumps by
     `(SIN[h] × s >> 8, COS[h] × s >> 8)` (arithmetic shift, `movement_formation.md` convention) while its models
     stay where they are, and the unit enters the **re-forming** state, so the models walk to their new slots; the
     end of that re-form raises 0x34 again.
  🟡 No boundary or terrain check on the jump.

| Before | rand() draws | After |
|---|---|---|
| facing 0, at (0,0) | 0, then 0 | facing 128, position (48, 0), re-forming |
| facing 0 | 511, then 3 | facing 385 (−127), step 84 |

**Case 0**: does nothing (BF039 script 9 uses it as an idle loop body).

## 11. Case 24 — start the charge sound

Same rule as `script_animation_sound.md` §4 ("The charge sound is started by the game"): if the unit has no charge
sound running, start a looping positional effect from packet 2 at the unit — Infantry and Archers effect 1; Cavalry
13 (Human, Elven, Dwarven) or 14 (other races); other classes none — and store it as the charge-sound handle. Already
running → nothing. Condition false. Library 106/160 call it right after the charge starts (which may already have
started it), then `MoveUnitSound 0` every tick.

---

## 12. Worked example: threat tracking end to end

### 12.1 The two pieces

**`IfThreatOutweighsWorth` (0x3F)**: condition := threat slot not empty **and** `UnitScore(self, slot) > worth(self)`
(strict; own worth). It **does not scan** the units, does not use the stored score and writes nothing else; empty
slot → false. Always writes the condition.

**Behaviour code 15 `TrackThreat`** (`SetBehaviour 15 P`, the standard mission AI; runs every P + 1 updates,
`deployment.md` §5.3), one run:
1. **Spot hidden enemies** (game_rules "Hidden units": every hidden unit of the opposite army that the unit sees with
   the standard ±50° cone is revealed; 0x1C/0x1D).
2. Threat slot **empty** → pick the best threat exactly as `Query 1` (§1). No event this run.
3. Slot **set** and the unit **not braced**:
   - `s = UnitScore(self, slot)` (recomputed); if `s > worth(self)` → queue **0x03** to self, source = the threat,
     direct path. **The stored score is not updated.**
   - otherwise **re-pick**, starting from the current threat and its current score: another unit replaces it only if
     it scores **strictly more**; if nobody scores more, the slot keeps the old threat (even at score 0). Slot and
     stored score are written.
4. Slot set and braced → nothing after step 1.

The run happens **before** the unit's queued-event check in the same update, so a 0x03 it queues is handled in that
same update.

The 0x03 handler is `ReactToThreat; IfSwitchScript 159` (`threat_events_nodes.md` §6): it requires
`UnitScore(self, current target) < stored score`.

### 12.2 Scenario

Enemy unit S at (0,0) facing 0 (+Y), worth 120, `SetThreatRange 400` (divisor 100), `SetBehaviour 15 30`, no target.
Player unit P1 worth 150; player unit P2 worth 100 at (100,150) (d = 200, score 200). Neither targets S. Positions are
relative to S.

| Run | Before | What happens | After |
|---|---|---|---|
| 1 | slot empty; P1 at (0,200) | step 2: P1 d = 200 → 150×200/100 = 300; P2 = 200 → pick P1 | slot P1, stored 300, no event |
| 2 (31 updates later) | P1 advanced to (0,150) | s = 150×250/100 = 375 > 120 → 0x03 (source P1) | stored score still 300 |
| 2, same update | handler: `ReactToThreat` | target none → UnitScore 0 < 300 ✓; P1 within ±60° ✓; not in melee | target P1, slot none, approach waypoint, cond true → script 159 |
| 3 | slot empty, target P1 at (0,120) | re-pick → P1: 150×280/100 = 420 | slot P1, stored 420 |
| 4 | P1 at (0,100), S closing | s = 450 > 120 → 0x03; handler: UnitScore(target P1) = 450 < 420? no | `ReactToThreat` false; nothing changes |
| alt 4 | P1 now in melee with P2's ally | s = 0, not > 120 → re-pick from P1 (0): P2 (200) wins | slot P2, stored 200, no event |

Script form (library 127/148/164, BF003 script 1, BF004_2, BF021): `Query 1; IfThreatOutweighsWorth;
SendEventSelfIfTrue 3` — Query 1 refreshes slot and stored score in the same update, so the score that passed the worth
test equals the stored score; `SendEventSelfIfTrue` queues 0x03 by the direct path with **no source** (0), which is
harmless because `ReactToThreat` reads the slot, not the source. Queued from the main script, it is handled at the
start of the next update (`YieldIfTrue` follows).

### 12.3 Differences from the implementer's current model

1. **`Query 1` is not a no-op**: it writes the threat slot and stored score (clearing both when nothing qualifies) and
   the condition. All the selection happens there.
2. **`IfThreatOutweighsWorth` does not scan**: it tests only the unit in the threat slot (false when empty). An
   engine that scans for the best unit inside 0x3F gives the same result only when `Query 1` ran just before and
   nothing changed; it differs after `Query 6` filled the slot, after 22/23 cleared it, and after behaviour 15's
   "keep the old threat" re-pick.
3. **Score details**: integer octagonal distance with the half rounded **up**; exclusions are *not hostile, in
   melee, broken, pursuing, out of range*; hidden/marked/scriptless are excluded by the **search**, not the score;
   ×4 when the threat targets this unit, ×32 when it also charges (two different states — the engine's single ×4
   collapses them); 16-bit wrap (§0.3 🟡).
4. **Strict** `>` against the unit's own worth; strict `d < R`.
5. **Behaviour 15** sends 0x03 without refreshing the stored score, and keeps a stale threat on re-pick ties; braced
   units do not track. `ReactToThreat`'s "strictly more than the current target" test uses that stored score.
6. Other cases that are not "false, no side effects": 3, 6, 7, 9, 10 can be true; 3, 5, 8, 9, 10, 22/23 queue events;
   1, 6, 22/23 write the threat slot; 7, 22/23 (and 8) write the current target; 17 moves the unit.

---

## Part B — class, machine, objective and target tests

| op | name | words | operand | condition | other writes | uses |
|---|---|---|---|---|---|---|
| 0xCD | `IfClass` | 2 | class code | unit's class code = operand | – | 431 |
| 0xD0 | `SetClass` | 2 | class code | true if the class changed, false if it was already that class | the unit's class | 90 |
| 0xCF | `IfMachineDestroyed` | 1 | – | no leader model, or the leader's wounds taken ≥ the leader's W | – | 166 |
| 0xDE | `IfObjective` | 2 | objective index | the battle file defines that objective letter | – | 139 |
| 0x74 | `TargetValid` | 1 | – | safe to shoot at the aim point (`target_queries.md` §3) | – | 90 |
| 0x56 | `TargetGone` | 1 | – | see B5 | event 0x19, or a new opponent, or leaves the combat grid | 45 |

### B1. `IfClass class` (0xCD)

The operand is the **class code `class × 8`**, the same value as `s_race & 0xF8` (`game_rules.md` §3 `s_race`):
the race bits are **not** compared. Condition = the unit's current class code equals the operand, written in both
branches. Shipped operands: **8** Infantry (8), **16** Cavalry (8), **24** Archers (134), **32** Artillery (176),
**40** Wizard (46), **56** RollingStock (50).

**Difference from the current engine:** "always true" makes every `IfClass` branch fire; e.g. library 115/117
(`IfClass 24` → whole-unit volley, else leader-only shot) would make artillery volley with every model.

### B2. `SetClass class` (0xD0)

If the unit's class code already equals the operand: condition false, nothing else. Otherwise the class part of
`s_race` is replaced by the operand (**the race is kept**), the command panel is refreshed if this unit is the
selected one, and the condition is true. Every later class test (`IfClass`, shooting class rules, the
`Choose…OfClass` filters, the HUD) sees the new class. Shipped operand: always **8** (Infantry), in library
102/154 case 23 (event 0x17 "leader killed"): an **artillery crew whose machine model is killed becomes an Infantry
regiment**, its war-machine anchoring is cleared and it re-forms (unless broken).

### B3. `IfMachineDestroyed` (0xCF)

Condition = the unit has **no leader model** (the machine of a war machine is its leader model,
`game_rules.md` "war machines") **or** the leader model's wounds taken ≥ the leader's W. Written in both branches.
It does not look at the class, so for an ordinary regiment it means "the champion/character is dead". Shipped in
library 111/112/154 (artillery) and 31 mission uses: e.g. library 154 case 13 (fear test failed): if the machine is
destroyed, the crew may flee (`RoutAllowed` → `React 6` → rout script); otherwise they stay with the machine.

### B4. `IfObjective n` (0xDE)

Already public: `game_rules.md` "AI and mission opcodes" and "Objective table". Operand = **objective index
`letter − 'A' + 1`** (1 = A … 7 = G), **not** a letter code and not an evaluation result: the condition is "the
battle's `.BTS` defines `Objective:<letter>`" (the `MISSIONINFO` `Objective:L,a,b` lines, `FORMATS.md` "Mission
objectives"). It does not test whether the objective is met. Shipped operand: always **7** (G, "Inside the gates",
the siege battles BF015/BF017): library 100/101/152 branch on it.

**Difference from the current engine:** "true for N < 6" is wrong for every shipped use: `IfObjective 7` must be
true only in battles whose `.BTS` has an `Objective:G` line.

### B5. `TargetGone` (0x56)

The close-combat "my opponent has gone" handler, run from library 152 on event **24 (0x18)** (an object was
destroyed / left the field). Exactly:

```
if the unit has no current target, or the current event's source is not the current target:
    condition false; nothing else
elif the unit is NOT in melee:
    queue event 0x19 ("current opponent gone") to itself; condition false
else (in melee):
    look for another enemy unit engaged with this unit's models
    none  -> the unit leaves its combat grid (game_rules.md "Who leaves combat"); condition TRUE
    found -> it becomes the current target (opponent switched; the unit's "engageable" state is cleared and its
             engagement bookkeeping is redirected to the new opponent); condition false
```

Library 152 follows it with `IfSwitchScript 163` (re-form script) — so only the "left the grid" case switches
to re-forming. `game_rules.md` lists the same caller in "Every caller, and the condition each represents".

### B6. `TargetValid` (0x74)

Fully public in `target_queries.md` §3 (aim point = the target unit's position, or the target point when the unit
has no target **or the aim-at-point state is on** (`script_magic.md` §0.1); independent-unit friendly-crowding check;
crossbow line-of-fire check; true otherwise; false if neither a target nor a set point exists). Nothing to add:
it does **not** test range, arc, hidden or broken.

**Difference from the current engine:** "true iff a current target exists" misses the two refusals and the
target-point case.

### B7. Test vectors

| before | instruction | after |
|---|---|---|
| Artillery unit (class code 32) | `IfClass 32` / `IfClass 4` | true / **false** (class number, not code) |
| Orc Archers (`s_race` = 3 × 8 + 4 = 28) | `IfClass 24` / `IfClass 28` | true / **false** (race not compared) |
| Artillery crew, class 32 | `SetClass 8` | class 8 (race kept), cond true; `IfClass 32` now false |
| class already 8 | `SetClass 8` | cond false, nothing changed |
| war machine, machine model alive, 0 of 3 wounds | `IfMachineDestroyed` | false |
| machine model at wounds taken = W | `IfMachineDestroyed` | true |
| unit without a leader model | `IfMachineDestroyed` | true |
| `.BTS` with `Objective:A`, `Objective:G` | `IfObjective 7` / `IfObjective 2` | true / false |
| `.BTS` with only `Objective:A`…`F` | `IfObjective 7` | false |
| current target T, event source T, not in melee | `TargetGone` | event 0x19 queued to self; cond false |
| target T, event source T, in melee, another enemy E engaged with our models | `TargetGone` | target E; cond false |
| target T, event source T, in melee, no other enemy | `TargetGone` | leaves the grid; cond true |
| target T, event source U ≠ T | `TargetGone` | cond false; nothing |

---

## 🟡 Uncertainties

- Cases 6, 9, 10, 22/23 with no current event, and case 5 with no current target: unguarded in the original; no
  shipped script reaches them that way.
- Case 7: the visible effect of resetting the models' per-model lock.
- Case 8: whether every engagement refusal (not only an exhausted grid pool) leads to the 0x0C shown; the object kinds
  of step 5.
- Case 17: no bounds check on the jump; behaviour at the battlefield edge not observed.
- §0.3 16-bit wrap: certain from the rules, never observed in play; check shipped worth values before relying on it.
- Source of the 0x03 queued by behaviour codes 11/12 (`DetectThreat`) is not meaningful (left over from an earlier
  query); handlers do not read it.

## Corrections to existing public notes

- `game_rules.md` octagonal distance: `max + ceil(min/2)` (integer), not `max + min/2`.
- `game_rules.md` `UnitScore` exclusions: in melee, broken, pursuing (plus not hostile, out of range) — not
  "CantMelee or hidden".
- `game_rules.md` "`StoreEventInfo`": the brace query refuses an **already braced** unit, not a broken one.
- `game_rules.md` event table row 0x03: also queued by behaviour codes 14, 15, 16, 19, 20 and by
  `SendEventSelfIfTrue 3` in scripts 127/148/164 and missions — not only by 11/12.
- `game_rules.md` R70: the cannot-engage state is set during the Flying Bower flight and while a unit is inside a Sapphire Arch; there are no other sources (`notes/spell_channelled_effects.md` §2.3, §3).
