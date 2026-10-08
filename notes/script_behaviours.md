# Unit-script periodic behaviours, contact wiring, case skipping and reactions

Public implementation report (batch 10 of the interpreter requests, GitHub #3). Behaviour only; states by name,
numbers only for script operands, event codes, battle-file data and gameplay constants.

Builds on (cite, do not repeat): `deployment.md` §5.3 (periodic scheduling), `script_queries.md` (§0.3 distance and
`UnitScore`, §1 `Query 1` / pick-best, §5 brace, §6 contact-handler summary, §12.1 behaviour 15), `threat_events_nodes.md`
(Part B §0.2 delivery paths, Part C node areas), `script_grid_events.md` (§2 `FearWhenCharged`, §4 `CheckCollisions`),
`movement_formation.md` (§1.2 tick order, §3.10, §4 Rally, §6 leave grid), `game_rules.md` ("Routes, collisions and
visibility", "Engagement: battle grid and pairing", "Charge", "Reload time", "Special weapons", "Pursuit", contact
attacks §7.7, "Fear and terror").

---

# Part 1 — periodic behaviour codes (`SetBehaviour code P`, 0x33)

## 1.0 Shared state first

- **Dispatch.** A due periodic decision (`deployment.md` §5.3: before the unit's own instructions and before its queued
  events; skipped entirely during deployment) runs the **same routine as `Query code`**: the behaviour code *is* a
  `Query` case number. The result is **discarded**: a periodic run **never writes the condition**.
- **Events and order.** Every event below is queued to the unit itself unless stated. Because the periodic run comes
  *before* the event check of the same update, anything it queues is handled **in that same update**. The queue is LIFO
  (`unit_script_control.md`): when one run queues two events, the **later-queued one is handled first**.
- **Delivery paths** (`threat_events_nodes.md` Part B §0.2): *direct* (only "recipient not live / scriptless" drops it)
  or *checked* (also refused during deployment; irrelevant here because periodic runs never happen in deployment).
- **Spotting** = `game_rules.md` "Hidden units": every hidden unit of the **opposite army** that passes the standard
  visibility test from this unit (±50° cone, doubled in melee, scenery rays, `SightEdge`) is revealed permanently; event
  0x1C to the spotter (source = revealed unit), 0x1D to the revealed unit (source = spotter), both checked. No state of
  the spotter is tested (broken, braced, in melee units spot too).
- **Threat slot / stored score / current target**: as `script_queries.md` §0.2.
- **Distance** `d` = octagonal, half rounded up; **R** = own threat range; range tests strict `d < R`
  (`script_queries.md` §0.3) — except node areas (Euclidean, inclusive, `threat_events_nodes.md` Part C §2).
- **Battle state**: the single per-battle mission state of `IfBattleState` (`deployment.md` §5.1 "mission choreography
  state"). Codes 12, 19, 20 read state **4**; 19/20 move it to **5**.

## 1.1 Summary

| Code | Name | Shipped (`SetBehaviour` uses) | One run |
|---|---|---|---|
| 0 | none | 45 (library 170 ×44 + NULL.DLL), always `SetBehaviour 0 0` | nothing |
| 11 | `DetectThreat` | 53: library 100 (player units, P = 30) ×44 + 9 mission (BF010 s0, BF011 s0 — allied Dwarfs; BF015 s24–26; BF017 s27–29) | spot; keep / answer the threat (§1.3) |
| 12 | `DetectThreatObjective` | 45: library 100 when the battle defines objective G (×44) | "inside node id 99 in state 4" → 0x36; then 11 |
| 13 | `SpotHidden` | 16 (BF005 s3/4, BF006 s4/5, BF015 s0/1, BF017 s0/1, BF020 s0, BF039 s0–6) | spot only |
| 14 | `ThreatInReach` | 8 (BF003 s2–4 peasants, BF004_1/2 s0/1 peasants, BF028 s4 sheep) | contact attacks by nearby chargers; 0x03 |
| 15 | `TrackThreat` | 290 | `script_queries.md` §12.1 |
| 16 | `TrackThreatSignal` | 3 (BF034 s5, BF038 s0/1 — fanatic parents) | 0x33 if the threat is in range; then 15 |
| 19 | `TrackThreatExit` | 31 (BF015 s2, s4–15, s32; BF017 s2–18) | state 4 → 5 inside node 14 (not broken); then 15 |
| 20 | `TrackThreatSignalExit` | 1 (BF015 s3, Night Goblins with fanatics) | same without the broken test; then 16 |
| 21 | `BombardNearest` | 1 (BF014 s0, the Dragon, P = 24) | 0x21 at the nearest non-allied unit in range |
| 26 | `DoomwheelBolts` | 2 (BF023 s7, BF035 s1 — Doomwheels) | when reloaded: three bolts |
| 27 | `PestilentBreath` | 8 (BF024 s0–7, Plague Monks, P = 24…38) | when (partly) reloaded: one Pestilent Breath cloud |

Codes never used periodically (1–10, 17, 18, 22–25) behave as the `Query` case of the same number
(`script_queries.md`), result discarded. Any other code: nothing.

## 1.2 Code 0 — none

Does nothing (no case). With P = 0 the scheduler never runs it anyway; library 170 (leave the battle) uses
`SetBehaviour 0 0` to stop the unit's periodic AI. Engine: no-op — correct.

## 1.3 Code 11 — `DetectThreat` (player units; also some allied/enemy mission units)

One run:
1. **Spot** hidden enemies (§1.0).
2. If the unit is **braced**: skip to step 4.
3. Let T = threat slot.
   - If T exists **and** (T's current target is this unit **or** this unit is **independent**) **and** `d(self,T) < R`:
     stored score := `UnitScore(self, T)` (written even when that is 0); queue **0x03** to self, **direct** (source not
     meaningful: a leftover value, `script_queries.md` 🟡 list — handlers read the slot, not the source).
   - Otherwise, **only if independent**: re-pick from scratch exactly as `Query 1` (`script_queries.md` §1: slot :=
     best or none, score := best or 0).
   - A non-independent unit with no qualifying threat: nothing (the slot is left as it is).
4. **Doomwheel rider**: if the unit's leader has missile weapon code **13** (`S_BalWeap` of the leader block; 🟡 the
   leader's close-combat weapon class 13 also qualifies, never in shipped data) run code 26 (§1.9) as well — even
   when braced. No shipped unit combines them.

Notes:
- **"Independent"** = the per-unit "independent action" state of `game_rules.md` "Rally" (player order 0x1A).
- Unlike 15, code 11 **never fills an empty slot** for a non-independent unit. For player units the slot is filled by
  `Query 6` on event 0x05 (an enemy attack script announces itself, `script_queries.md` §3/§4) or by the
  `Find*Threat*` opcodes. So "a player regiment reacts only to an enemy that has chosen it as target, within R"; and
  library 101 answers 0x03 only when independent (`TestUnitFlags` independent → `ReactToThreat`).
- No broken / in-melee test (a broken unit can still queue 0x03; `ReactToThreat` refuses later).

## 1.4 Code 12 — `DetectThreatObjective`

1. If the battle has an **active node whose `id` field is 99** and the unit's regiment position is inside that node's
   circle (Euclidean, inclusive, Part C §2 of `threat_events_nodes.md`) **and** the battle state is **4** → queue
   **0x36** to self, direct, source none.
2. Then exactly code 11.

The node is found by its **`id` field**, not by its index (unlike every node opcode). Shipped: only BF015/BF017 have
`id=99` — node **13** (1000, 1940), radius 47. The 0x36 is queued **before** 11's 0x03, so a 0x03 of the same run is
handled first. 0x36 → library 152 case 54 (`threat_events_nodes.md` "Worked example, library 152"): leave the battle
via script 170, which also sets behaviour 0 0. The 0x36 repeats every run while the conditions hold. No broken/braced
test on step 1.

## 1.5 Code 13 — `SpotHidden`

Spotting only (§1.0). No threat logic, no event other than 0x1C/0x1D.

## 1.6 Code 14 — `ThreatInReach` (non-combatants)

One run, two tests, **0x03** to self (direct, source none) if either is true:

1. **Contact attacks by nearby chargers.** For **every** live unit U (any side, **including friends and in principle the
   unit itself**) that is **charging or pursuing**, has **not yet made its contact attacks this segment**, and is at
   `d(self, U) < R`: U makes its automatic **contact attacks against this unit** right now (`game_rules.md` §7.7 /
   "Pursuit": U's models hit this unit's models within `2 × reach(U)`, reach 12 / 18 cavalry / 24 monsters, automatic
   hits on models not in the turning state, otherwise normal resolution) and is marked as having made its contact attacks
   this segment (so its ordinary collision contact attacks are spent too). Test 1 is true if **any wound** was caused.
   All such U are processed (no early stop).
2. Only when test 1 is false: is there any live unit of the **opposite army**, not hidden, not marked, not
   scriptless, at `d < R`? (Broken enemies count.)

So the event means "an enemy is near"; test 1 is the **damage mechanism** for marked non-combatants (peasants, slaves,
sheep): marked units are ignored by the collision pass (Part 2 §2.2), so charging raiders could not otherwise touch
them. No braced/broken test. Shipped handlers answer 0x03 by fleeing (BF003 script 7: `SendEventSelf 12` → script 8
`FleeAhead`).

## 1.7 Codes 15 and 16

**15**: `script_queries.md` §12.1, verified; nothing to add.

**16** = 15 with one extra step between "spot" and the threat logic: if the threat slot is set and `d(self, slot) < R`
→ queue **0x33** to self, **direct**, **source = the threat**. This happens **even when braced** and even if the
threat scores 0. Empty slot → no 0x33 that run (the slot is only filled). Then 15's step 3/4. If the same run also
queues 0x03, the 0x03 is handled **before** the 0x33 (LIFO). Shipped 0x33 handlers (fanatic parents BF034 s18, BF038
s7, BF004_5 s17) release the fanatics; library 101's case 51 is player-only (`React 18` under objective G).

## 1.8 Codes 19 and 20 — siege exit

1. If the battle state is **4**, and (**19 only**) the unit is **not broken**, and the unit is inside **node index 14**
   (Part C circle, inclusive): the battle state becomes **5**, the game plays its global sound effect 11 (🟡 which
   sample; non-positional), and event **0x38** is **broadcast to every live unit** (checked; the source field is not
   meaningful 🟡). Only the first unit to qualify does this (afterwards the state is 5).
2. Then exactly 15 (code 19) or 16 (code 20).

Here node 14 is an **index** (BF015/BF017 node 14: (1000, 2290), radius 16), unlike code 12's id lookup. Shipped
0x38 handlers: BF015 s32/s35, BF017 s33/s36. The engine needs the battle state to be 4 for anything to happen; which
game event sets state 4 is 🟡 (no shipped script writes 4; scripts only set 2).

## 1.9 Code 21 — `BombardNearest` (the BF014 Dragon)

- Candidates: every live unit **other than itself** whose side code is the **player army or the enemy army** (side code
  0x00 or 0x80 — **allied units 0x40 and building/furniture pseudo-units 0x20 are excluded**). **No hostility test**:
  units of its own army count. Hidden, broken, in-melee units are not excluded.
- Pick the smallest octagonal `d` with `d < R`; strictly smaller replaces → first in unit order on ties.
- Found → queue **0x21** to self (checked), no source (the "none" marker of a fire-at-ground order), argument 0,
  **point = the chosen unit's regiment position**. None → nothing.
- No reload, arc or visibility test here (the shooting layer that handles 0x21 decides; BF014's handler gosubs library
  154, whose case 33 fires at the point, `script_grid_events.md` §1.3 row 0x21).

Consequence: with R = 120, the Dragon breathes at the nearest unit within 120 **including Orcs of its own army**, but
never at Gotrek (allied side code).

## 1.10 Codes 26 and 27 — innate weapons on a reload clock

**Reload test** `ready(divisor)`: reload time `RT` = `game_rules.md` "Reload time" computed from the **leader block**
(leader I, leader missile weapon code, the artillery-class surcharge); `e` = ticks since the unit's last reload stamp
(the same stamp shooting uses).
- `e > trunc(RT / divisor)` (strict) → ready; and then *full* if `e > RT`, *partial* otherwise.
- not ready otherwise.

**26 `DoomwheelBolts`** (divisor 1, so ready always means full): stamp the reload clock, then fire three Doomwheel
bolts (`game_rules.md` "Special weapons", code 13) at headings **facing**, **facing + 128** and **facing + 384** (mod
512: ahead, right, left). No target, enemy, broken, braced or melee test — a reloaded Doomwheel fires on its next
periodic run whatever it is doing.

**27 `PestilentBreath`** (divisor = `trunc(models / 4) + 1`, current model count):
- full → stamp, then breathe; partial → breathe **without** stamping; not ready → nothing.
- So after a stamp the unit breathes on **every** run once `e > RT/divisor`, until the run where `e > RT` stamps.
  Larger units breathe more often.
- **Aim point** (exactly; looks like an original bug — both offsets are equal, so the cloud always goes towards
  +x, +y): `E = trunc(144 × 5 / 2) = 360` (144 = Pestilent Breath's 6" range); `h = rand() mod 512`; then
  `m = rand() mod E`; `t = (m − E/2 + E) >> 1` (= `(m + 180) >> 1`, 90…269); `off = (t × h) >> 8` (0…536);
  point = (x + off, y + off) from the unit's regiment position. The game then launches spell effect 24 (Pestilent
  Breath) from the unit at that point as an innate cast (no caster model, no power cost) — effect per `game_rules.md`.
- No target, enemy or state test.

## 1.11 Test vectors

Unit S at (0,0), R as given; positions relative to S.

| Code | Before | After one run |
|---|---|---|
| 0 | anything | nothing |
| 11 | not independent, R 240 (divisor 60), slot E (worth 100, not charging) at (0,100), E's target = S | stored score := `UnitScore` = 233 × 4 = 932; 0x03 queued (direct) |
| 11 | same, E's target = someone else | nothing (slot E kept, score kept) |
| 11 | independent, slot E at (0,100), E targets nobody | stored := UnitScore(S,E) = 233, 0x03 |
| 11 | independent, slot E at (0,240) | d = 240 not < 240 → full re-pick (`Query 1`) |
| 11 | braced, slot E targets S at (0,100) | only spotting; no 0x03, score unchanged |
| 11 | not independent, slot empty, enemies near | nothing (no fill) |
| 12 | BF015, state 4, S at (1000,1987) (node id 99: (1000,1940) r 47) | 0x36 queued (47 ≤ 47); then 11 |
| 12 | same at (1000,1988), or state 5 | no 0x36; then 11 |
| 14 | marked peasant S, R 160; enemy cavalry C charging at (0,150), contact attacks unused this segment, C's models within 36 of S's | C's contact attacks on S resolved; C's contact attacks spent; 0x03 queued (test 2 is true anyway) |
| 14 | only a **friendly** charging unit F at (0,100), no enemy within 160 | F's contact attacks hit S; 0x03 only if a wound was caused |
| 14 | only a hidden enemy at (0,100) | nothing |
| 16 | slot E at (0,100), R 240, braced | 0x33 (source E) queued; nothing else |
| 16 | slot E at (0,100), UnitScore 932 > worth 120 | 0x33 then 0x03 queued → 0x03 handled first |
| 19 | state 4, S broken, inside node 14 | state stays 4; then 15 |
| 20 | same | state 5, sound, 0x38 to all; then 16 |
| 19 | state 4, S at (1000, 2306) / (1000, 2307) (node 14 r 16) | inside → state 5 / outside → nothing |
| 21 | Dragon R 120; allied Gotrek at (0,50); enemy-army Orcs at (60,0); player unit at (0,100) | 0x21 with point (60,0) |
| 21 | nearest non-allied unit at (0,120) | nothing (120 not < 120) |
| 26 | facing 100, e = 91, RT 90 | stamp; bolts at headings 100, 228, 484 |
| 26 | e = 90, RT 90 | nothing |
| 27 | 24 models (divisor 7), RT 180, P 24 → runs at e = 25, 50, …, 200 | e 25: nothing (25 not > 25); 50…175: breath, no stamp (6 clouds); 200: stamp + breath |
| 27 | rand() draws 256 then 0 | off = (90 × 256) >> 8 = 90 → point (x+90, y+90) |
| 27 | draws 511 then 359 | t = 269, off = 137 459 >> 8 = 536 |
| 27 | first draw 0 | point = the unit's own position |


## 1.12 Differences from the engine model ("only 15 runs; all others are no-ops")

1. **11/12 are the player army's periodic AI** (every 31 updates): spotting reveals hidden enemies for the player
   (without it, ambushers are only revealed by enemy behaviour 13/15… or not at all), and independent player units
   react to threats. 12 additionally drives the siege "inside the gates" exit (0x36).
2. **13** reveals hidden units for mission units that do not track threats.
3. **14** is the only way charging raiders damage marked peasants/slaves/sheep, and it makes them flee.
4. **16** produces the 0x33 that releases fanatics (BF034, BF038).
5. **19/20** drive the siege battle state 4 → 5 and the 0x38 broadcast.
6. **21** is the Dragon's breath targeting; **26/27** are the only firing rule of the Doomwheel and the Plague Monks.
7. None writes the condition; queued events are handled in the same update.

---

# Part 2 — contact and engagement wiring

## 2.0 Answer to the key question

**All engagements go through one script-driven path.** The original creates or joins a battle grid in exactly one
place: the contact handler, which is reached only by `Query 8`, which shipped scripts run only in library 152 on event
**0x0B**. There is **no engine-side engagement**: the charge movement, pursuit, the per-tick pairing, `TargetGone`,
`Query 22/23`, `SwitchOpponentInGrid` and fanatics never create a grid or add a unit to one (pairing and opponent
switches only act inside an existing grid). Consequently **a unit whose interrupt handler never reaches `Query 8` never
engages through its own contacts**; it is engaged only when the *other* unit's handler engages it.

| Path that puts two units into one grid | Script involved |
|---|---|
| Contact handler, regiment contacted, **not charging**, contacted ≠ current target ≠ none → engage now | yes (0x0B → 152 → Query 8) |
| Contact handler, regiment contacted, not charging, contacted = current target → engage | yes |
| Contact handler, charging or pursuing, contacted = current target → engage as charger | yes |
| Contact handler, building / war machine / wagon that is the current target → engage (no charge counter) | yes |
| Anything else (charge arrival, pursuit, pairing, re-targeting) | – never creates an engagement |

## 2.1 Shared state

- **Contact record**: per unit, the last footprint it was recorded as touching (written with every 0x0B).
- **One-tick contact latch** (`movement_formation.md`: "contact latch"): while on, **no 0x0B** is queued to the unit
  (§2.3), a charging unit does not advance, and a non-melee unit's ordinary move/turn is undone while it overlaps
  anything (§2.5).
- **Collision re-check** state: the collision pass runs for a unit **only on updates where this state is on**
  (it is cleared at the start of the pass). Set by: the unit's own position step of an ordinary move, charge, pursuit or
  flight, **only on every 4th update of the unit** (a per-unit counter staggered by slot; `fanatic_collisions.md` §5);
  each gradual turn step; every formation re-layout; the battle-edge repel moving it; another unit's collision
  pass touching or pushing it (§2.2); the contact handler's "clear the latch" branches; `Rally`. **Not** set by
  standing still (corrected October 2026: turning and re-forming do set it).
- **Footprint kinds** (each unit owns one footprint): **troops** (ordinary regiments), **monster** block, **war
  machine** block, **wagon** (rolling stock) block, **building/furniture**; plus fanatic footprints. "Regiment kinds"
  below = troops and monster.
- **Marked** (`SetUnitFlags 256`, `script_queries.md` §1 note), **routing footprint** (set by the rout, cleared by any
  re-form; `game_rules.md` "Pursuit"), **cannot-engage** (`script_queries.md` §6 / R70), **fear-passed**
  (`script_grid_events.md` §0).

## 2.2 The collision pass (where 0x0B comes from)

**When.** Per unit, once per update, **after** its script, formation update and movement (`movement_formation.md`
§1.2 step 5), and only if its collision re-check state is on. Units are processed in unit order, so a unit later in
the order already sees this update's moves of earlier units. The same pass runs in the deployment phase and up to 10
times when a unit is placed during deployment (push-apart only matters there, see §2.7).

**Skipped entirely** for a unit that is **marked**, whose footprint is inactive, or which is a fanatic.

**Against what.** Every other active footprint that is **not a routing footprint**, broad phase then narrow phase
(`game_rules.md` "What triggers engagement": centre distance minus both radii < 0; then a corner of the mover's
footprint strictly inside the other footprint). Per overlapping footprint X (owner U), in this priority:

| X | Condition | Effect |
|---|---|---|
| solid scenery | – | push apart (`game_rules.md`; a charging mover hitting it within ±45° of its facing ends the charge) |
| building / furniture | mover not charging and not in melee | push apart; mover re-check on |
| building / furniture | mover charging or in melee | U re-check on; **touch test → contact** |
| war machine / wagon | same army | push apart unless either is in melee, broken or pursuing; both re-check on |
| war machine / wagon | other army, mover broken or in a catch-up re-form walk | push apart |
| war machine / wagon | other army, otherwise | U re-check on (if mover not in melee); **touch test → contact** |
| regiment kind, U **marked** | – | **nothing at all** (no push, no contact, no contact attacks) |
| regiment kind, same army and U ≠ mover's current target | – | push apart unless X is a fanatic or either unit is in melee, broken or pursuing; both re-check on |
| regiment kind, other army **or U is the current target**, mover **broken** | – | U makes contact attacks on the mover (`game_rules.md` §7.7; U need not be charging; once per segment) |
| same, mover not broken | – | (a) **fear on contact**: if fear-passed is off and `MayEngage(mover, U)` refuses → current target := U, **0x0D** to the mover (checked); (b) X not a fanatic: U re-check on (if mover not in melee); **touch test → contact**; X a fanatic: the mover's contact attacks on the fanatic, only if the fanatic lacks `CantMelee` (never in shipped data; `fanatic_collisions.md` §2) |

**"Push apart", exactly** (clarified October 2026, #197). Only the unit **running the pass** moves. The other unit
does not move in this pass: it only gets its re-check state, so it moves itself in **its own** pass (later in the
same update if it comes later in unit order, otherwise next update).
- Overlap `o = trunc(centre distance) − r_mover − r_other` (negative). The mover's position moves **away from the
  other centre** by `(|o| + 2) / 2` along the line between the centres: per axis `trunc(trunc(SIN/COS[b] × (o − 2) / 256) / 2)`,
  truncating toward zero, with `b` the bearing between the centres. Its figures are shifted by the same amount and woken.
- **One friendly push per pass**: after the first successful push against a regiment, war machine or wagon footprint,
  further friendly overlaps in the same pass only set re-check states. Scenery and building pushes always apply.
- A **rolling-stock** (wagon) mover is never moved by a push.
- If the mover is **charging** and the overlapped footprint lies within ±45° of its facing, the push also **ends the
  charge** (halt, 0x09 to its target). This applies to friendly footprints as well as scenery.

Example: two friendly regiments, radii 30 and 30, centres 50 apart (`o = −10`), A moving, B standing. A's pass moves
A 6 units away and switches B's and A's re-check on. B's pass then sees `o = −4` and moves B 3 units away. A's next
pass sees `o = −1` and moves A 1 unit. The pair separates over a few passes, with **each unit moving itself**, not by
"half each" in one step.

**Contact** (touch test true and not in `CheckCollisions` probe mode):
1. **Record on the mover**: if the mover's latch is **off** → mover re-check off, **0x0B** queued to the mover
   (**checked**; no source), contact record := X. Latch on → nothing.
2. **Reciprocal**, only when X is a **troops** footprint: the same for U, with contact record := the mover's
   footprint. (Monsters, machines, wagons and buildings get no reciprocal 0x0B.)

The touch test is repeated on **every** pass while overlapping; 0x0B is therefore raised **every update** the overlap
is re-checked until the handler sets the latch. Neither velocity nor order is read.

**Building pseudo-units.** When the pass runs for a building/furniture unit, a troops footprint overlapping it gets the
contact recorded (0x0B to that regiment, contact = the building).

**Event 0x27 — correction.** 0x27 is raised (checked, to the mover itself, no source) when the **mover's own footprint
is a wagon** (rolling stock) and an overlapping footprint of **any** kind lies within ±45° of its facing (bearing
difference < 64/512). It does **not** depend on `INVSOLID`: `game_rules.md` "Routes…", `movement_formation.md` §3.10
and `script_grid_events.md` §4 should read "a wagon touching anything ahead". This fits the shipped users: the 11
mission handlers mapping 0x27 → script 166 are the horse-and-cart / NPC artillery wagon handlers. The pass continues
normally after raising it.

## 2.3 The contact handler (`Query 8`) — exact

Refines `script_queries.md` §6. Let A = the unit, X = its contact record, U = X's owner, T = A's current target.
Events are sent checked, **source = A**.

```
if A is cannot-engage, or X is inactive, or X is a routing footprint: nothing
latch := on
X is a regiment kind (troops, monster):
    if U is cannot-engage, or (U is of A's army and U != T):  latch := off; done
    if A is charging or pursuing:
        if U != T:  REDIRECT                                   (latch off, re-check on)
        else:       ok := ENGAGE_AS(joiner A, owner U);  if not ok: 0x0C to U        (latch stays on)
    else (not charging):
        if T is none:
            if A not broken: T := U; 0x07 to U ("you are being charged" — U's FearWhenCharged ignores it
                             because A is not charging); latch off; re-check on
            else: latch off
        elif U != T:   0x1A to T; ok := ENGAGE_NEW(A, U); if not ok: 0x0C to U;
                       T := U; latch off; re-check on          (engages on the FIRST handled contact)
        else (U == T): ok := ENGAGE_NEW(U, A); if not ok: 0x0C to A                     (latch stays on)
X is a building/furniture:
    if U == T: ENGAGE_PLAIN(A, U)                              (latch stays on)
    elif A charging and not in melee: end the charge (halt, charge sound off, 0x09 to T) (latch stays on)
X is a war machine or wagon:
    if U == T: ENGAGE_PLAIN(A, U)
    elif U is of the other army: REDIRECT
```

- **REDIRECT**: A loses pursuing and becomes **charging** (charge movement on, pursuit movement off) — also when A
  was not charging (machine/wagon case); 0x1A to the old T; T := U; 0x07 to U; latch off; re-check on. No engagement
  this update; the next contact engages as a charger.
- **ENGAGE_NEW(x, y)** (who joins whom): if **y already has a grid** → `ENGAGE_AS(joiner x, owner y)`, else
  `ENGAGE_AS(joiner y, owner x)`.
- **ENGAGE_AS(joiner J, owner O)** (= `game_rules.md` "EngageCharging"): refused (false, nothing changes) if J or O is
  **broken**; if **J already has a grid → true, nothing changes** (this is the double-engagement guard); otherwise J
  gets charge counter `floor(1.5 × frontage)` and its attack direction, O's grid is joined or **created around O** (O
  becomes owner, in melee, its own charging state cleared) — pool exhausted → J's charging/re-forming/charge-movement
  cleared, false; else grid count +1, J's charge sound stopped, if O ≠ J's target: 0x1A to J's old target and
  J's target := O; **0x08 to O only if J is charging or pursuing**; **0x0A to O (source J) and to J (source O)**;
  J in melee, has grid, round counter 0, pairing reset; J's charging/re-forming/charge movement cleared. O's current
  target is **not** written.
- **ENGAGE_PLAIN(A, U)** (buildings, machines, wagons): only if A has no grid (and the target footprint is not in a
  special excluded state 🟡); like ENGAGE_AS but **charge counter 0**, A's charging cleared first, **U's target := A**,
  0x0A to both, no 0x08, no refusal event.

**Correction (charge counter, `game_rules.md` "Charge"):** the zero counter applies to buildings, war machines and
wagons, not to "re-engaging the current opponent": a regiment that walks into its current target regiment (no charge)
still gets `floor(1.5 × frontage)` as the joiner (§2.8).

## 2.4 Which handlers reach `Query 8`

All 45 DLLs, every `SetInterruptScript` operand, following `GosubScript` transitively:

- **No mission handler handles 0x0B itself.** 102 mission handlers and library 101–104, 151 reach library 152's
  `CaseEvent 11: Query 8` through 151 or 153–156 (each reaches 152 only for codes none of its own cases took; none of
  them takes 11).
- **21 mission handlers and library 150 never reach it:** BF001 s6 (Otto Hiln — empty handler), BF003 s7, BF004_1 s5,
  BF004_2 s10 (peasants), BF004_4 s15 (slaves), BF028 s6 (sheep), BF010 s8 (Ilmarin), BF011 s12 (Carlsson's family),
  BF035 s19 (Thanquol), BF005 s6, BF006 s7, BF020 s8 (horse and cart), BF026 s8, BF029 s6, BF030 s16, BF031 s10,
  BF042 s10 (NPC artillery wagons), BF004_5 s18, BF015 s36, BF034 s19, BF038 s10 (fanatics: only event 0x34);
  library 150 (null handler: spawned templates, units leaving via 170).
- These units never engage from their own contacts. An enemy touching them engages them through **its** handler
  (they become owner or joiner by the ENGAGE_NEW rule). Marked ones (peasants, slaves, sheep, convoys) are not even
  touched (§2.2), so they never enter close combat; they are hurt only by contact attacks (§1.6).

## 2.5 The latch — complete lifecycle

**On**: at the handler's start (valid contact). **Stays on** after an engagement (successful or refused) with the
current target, after ENGAGE_PLAIN, after a charge ended on a building.

**Off**: the handler's refusal / no-target / redirect / "engage a newcomer" branches; `CheckCollisions` false;
`LeaveSharedGrid` / `LeaveGrid`; `Rally`; the start of a rout; leaving the grid when lifted by Flying Bower; and the
movement check below when the unit no longer overlaps anything.

**Movement while latched (not in melee)**:
- **ordinary move or turn order**: at the start of the update the unit's position/facing/formation are remembered;
  after the step a probe collision pass runs; if anything still overlaps, the step is **undone** and the unit
  **halts and re-forms** (waypoints cleared, halted state); if nothing overlaps, the **latch goes off** and the step
  stands. A latched unit can only move by stepping completely clear in one step.
- **charge**: no advance; the halted state is set every update (`movement_formation.md` §1.3).
- pursuit and flight: unaffected.

While latched there is no new 0x0B, so a latched unit not on a grid (e.g. after a refused engagement, or a charge
ended on a non-target building) stays put until something clears the latch (🟡 possible lasting stalemate; library 166
`CheckCollisions` is the script-side way out).

## 2.6 Correction: stationary touching enemies

`game_rules.md` "Neither movement nor an order is required … two stationary touching enemies engage as well" holds only
when a collision pass runs for one of them. A unit that stands still runs no pass unless something sets its re-check
state (another unit moving into or pushing it, a handler branch, rally). Two enemies placed overlapping (e.g. by a
teleport) that never move do not engage.

## 2.7 Deployment

The pass runs during deployment, but 0x0B is a **checked** send and is refused: no contact handler, no engagement.
Push-apart still works (and placement repeats the pass up to 10 times). Side effects that remain: the contact record is
written, and 🟡 the fear-on-contact test (target write; its 0x0D is refused) could run if enemies overlap — deployment
zones normally prevent that.

## 2.8 Worked example — two regiments marching into each other (no charge)

A (earlier in unit order) and B, hostile troops regiments, both on ordinary moves towards each other, no targets, no
fear, standard handlers (153 → 152). Update t is the first in which A's step makes their footprints touch.

| Update / unit step | What happens | State after |
|---|---|---|
| t, A | script (no events); move; pass: B overlaps → B re-check on; touch → **0x0B to A** (contact B), reciprocal **0x0B to B** (contact A; B re-check off) | A queue [0x0B] ; B queue [0x0B] |
| t, B | dispatch 0x0B → `Query 8`: latch on; B has no target → **B.target := A**, 0x07 to A, latch off, re-check on. Move on (latch off: no rollback). Pass: touch → 0x0B to B; reciprocal 0x0B to A | A queue [0x0B, 0x07(B), 0x0B] ; B queue [0x0B] ; B.target = A |
| t+1, A | LIFO: 0x0B → handler: A no target → **A.target := B**, 0x07 to B, latch off. 0x07 from B: `StoreEventInfo`; `FearWhenCharged` false (B not charging) → no brace. 0x0B → handler: T = B → ENGAGE_NEW(B, A): A has no grid → **ENGAGE_AS(joiner A, owner B)**: grid created around B, A joins, **A gets charge counter floor(1.5 × frontage_A)**, no 0x08 (A not charging), 0x0A to B and to A; latch stays on. 0x0A → 152 case 10 → `SwitchScript 165`. A in melee: no movement; pairing starts. Pass (re-check was on): touch → A latched: nothing; reciprocal → 0x0B to B | A in melee (joiner), B in melee (owner, its march stopped) ; B queue [0x0B, 0x07(A), 0x0A(A), 0x0B] |
| t+1, B | LIFO: 0x0B → handler: T = A → ENGAGE_NEW(A, B): B has a grid → ENGAGE_AS(joiner A, owner B): A already has a grid → true, no change; latch on. 0x0A → `SwitchScript 165`. 0x07 from A → no brace. 0x0B → same no-op. B in melee, no pass | **both on the grid at the end of update t+1** |

Rules of thumb: the unit earlier in unit order (whose own step first detects the overlap) becomes the **joiner and
receives the charge counter**; the later one becomes the **owner** and stops at once. With a charge order A instead
engages as charger on its first handled contact with its target (one update earlier, plus 0x08 for the flank test);
with an existing different target A engages B on the first handled contact (0x1A to the old target) and, if B has no
grid, **B becomes the joiner** (ENGAGE_NEW(A, B)).

## 2.9 Test vectors (contact handler)

| Before (A not cannot-engage, contact X valid) | `Query 8` | After |
|---|---|---|
| X = enemy troops U; A idle, no target | | A.target U; 0x07 to U (src A); latch off; re-check on; cond false |
| same, A broken | | nothing but latch off |
| X = U, A.target = U, neither on a grid | | ENGAGE_NEW(U, A): A has no grid → ENGAGE_AS(joiner A, owner U): grid around **U**, A joiner with counter; 0x0A both; latch on |
| X = U, A.target = U, A already on a grid with C | | ENGAGE_NEW(U, A): A has a grid → ENGAGE_AS(U, A): **U joins A's grid**, U gets the counter, U.target := A (0x1A to U's old target if different) |
| X = U, A.target = T ≠ U, nobody on a grid | | 0x1A to T; ENGAGE_NEW(A, U): U no grid → ENGAGE_AS(U, A): grid around **A**, U joiner with counter; A.target U; latch off |
| X = U, A.target = U, U is broken (footprint not routing) | | refused → **0x0C to A** (rout!) 🟡 |
| A charging at target C, X = U ≠ C | | 0x1A to C, A.target U, 0x07 to U; still charging; latch off |
| A charging, X = U = target | | ENGAGE_AS(A, U): counter, 0x08 + 0x0A to U, 0x0A to A |
| A pursuing fugitive F, X = other enemy V | | becomes charging; 0x1A to F; target V; 0x07 to V |
| X = friendly regiment, not A's target | | latch off; nothing |
| X = enemy building, not A's target, A charging | | charge ends (halt, 0x09 to target); latch stays on |
| X = enemy war machine M, target = M | | ENGAGE_PLAIN: counter 0, M.target := A, 0x0A both |
| X routing footprint, or A cannot-engage | | nothing (latch unchanged) |
| any | | condition false |

## 2.10 Recommendation for the engine

1. **One collision pass produces contacts; no engagement in the pass.** Per unit with re-check on (moved this update,
   pushed, touched, handler/rally), after its movement: push-apart as now; on an enemy (or current-target) regiment /
   machine / wagon overlap — and on a building when charging or in melee — record the contact and queue 0x0B
   (checked, so none during deployment) unless latched; reciprocal record for a troops footprint. Fear-on-contact and
   router contact attacks belong here too.
2. **Engagement only in `Query 8`**, implemented as §2.3, calling a single `engage(joiner, owner, counter)` function.
   Make it **idempotent**: "joiner already has a grid → success, no change" is exactly the original's guard; also treat
   "already on the same grid" as success. This alone prevents double engagement when both units' handlers fire.
3. **Remove the engine's own "touching footprints engage automatically" and "charge contact" engagement** when the
   interpreter runs the unit. Keep at most one fallback for units without a running script/handler (not needed for
   shipped data: every unit has a handler; units whose handler lacks `Query 8` must *not* get a fallback, or they would
   engage on their own contacts, unlike the original).
4. **Implement the latch** with its exact on/off points (§2.5) — it is what stops 0x0B every update, and the
   rollback/halt is what makes a marching unit stop at the enemy instead of walking through it before the handshake
   completes.
5. Pairing, arrival, leaving stay engine-side; they never start an engagement.
6. Charge counter: joiner only, `floor(1.5 × frontage)` for regiments even without a charge order; 0 for
   buildings/machines/wagons.

---

# Part 3 — `CaseEvent` skipping, flag waits, `React N`

## 3.1 `CaseEvent N` (0x6A, 2 words) — exact skip rule

- If the **current event's code** equals `N`: continue at the next instruction (`pc + 2`).
- Otherwise: scan forward **word by word** from the operand word for the first word that is the **`Break` opcode**
  (0x6B), and continue **after that `Break` instruction** (the `Break` opcode word + its label operand = 2 words), i.e.
  normally at the next `CaseEvent` of the chain.
- The scan is a raw word scan, **not** nesting-aware: it does not decode instructions and ignores
  `If`/`Else`/`EndIf`. In shipped scripts every case arm contains exactly one `Break` (at its end), so this is the same
  as "skip to the end of the arm". 🟡 An arm with a `Break` inside an `If` would make the skip stop at that inner
  `Break`; no shipped script has one. (No operand in shipped data equals the `Break` opcode word, so the raw scan
  never stops on an operand.)
- The condition is not read or written. With no current event the original would fault; shipped scripts always run
  `CaseEvent` after `GetEvent` inside a handler (`unit_script_control.md` §4).
- **Default branch**: there is no default opcode. Whatever follows the last case arm's `Break` (typically
  `GosubScript 153`/`155`, the library defaults) runs for any event that matched nothing, because the failed
  `CaseEvent`s fall through to it. A **matched** arm reaches its own `Break`, which jumps to the handler's label
  (normally just before `ConsumeEvent`), skipping the defaults.

The implementer's stub ("scan to the next Break opcode and continue after it") is right; make sure it continues
**after the Break's operand** and does not decode the arm.

| before | instruction | after |
|---|---|---|
| current event 0x0A | `CaseEvent 10` | pc + 2 (arm runs) |
| current event 0x07; arm `CaseEvent 10 / X / Y / Break L / CaseEvent 7 …` | `CaseEvent 10` | pc → the `CaseEvent 7` after `Break L` |
| current event 0x2B, no arm matches | the chain | falls through to `GosubScript 155` after the last `Break` |

## 3.2 `WaitWhileUnitFlags` / `WaitUntilUnitFlags`

Already public: `unit_script_control.md` "Unit flag opcodes" — **any** bit of the mask (not all bits).
`WaitWhileUnitFlags 0x4008` waits while **either** state is on:
- **8 = re-forming**: the models are walking to their formation slots (`movement_formation.md` §1.2);
- **0x4000 = catch-up re-form walk**: the slower variant of the re-form in which the models catch up with a unit
  that keeps moving (always together with re-forming; `movement_formation.md`).
`WaitUntilUnitFlags` uses the same "any bit" rule with the opposite sense (continue as soon as one bit is set).

## 3.3 `React N` — message, portrait, speech

`React N` (and the game's own calls of the same routine) looks up a **per-race row** (`race = s_race & 7`:
0 Human, 1 Elven, 2 Dwarven, 3 Goblinoid, 4 Orc, 5 Skaven, 6 Peasant, 7 big) of 21 codes. Each entry has a `GMTXT.DLL`
string id (0 = none) and an optional speech cue (packet / effect of `notes/sfx.md`, plus two markers: **P** = "not for
enemy units", **E** = "also for enemy units off screen"). One per-code **portrait expression** applies to all races.

**When it shows.** Nothing at all if the entry has no text. An **enemy-army** unit's reaction is suppressed if the
entry is marked P; otherwise it is shown only if the entry is marked E **or** the enemy unit is **currently drawn on
screen** (inside the camera view and not hidden). Player-army and allied units always show it. When shown: the text
goes to the battle message window (as other battle messages), the unit's leader portrait pops up with the code's
expression (a talking animation, one pop-up at a time for 25 ticks; `react_portrait.md`), and the speech cue (if any) plays **non-positionally, not restarted if already playing**
(`script_animation_sound.md` §4, `PlaySound`). The text and the speech are never split: no text → no speech either.

Portrait expression per code (0–20): `0 2 0 1 4 2 2 1 2 2 0 2 2 2 2 3 2 1 3 1 2`.

String ids (`GMTXT.DLL`) and speech (`packet/effect`, markers) per race and code; codes not listed are empty for that
race:

| code | Human (0) | Elven (1) | Dwarven (2) | Goblinoid (3) | Orc (4) | Skaven (5) | Peasant (6) | big (7) |
|---|---|---|---|---|---|---|---|---|
| 1 | 34105 5/14 P | 34105 5/14 P | 34208 7/7 | 34000 | 34000 | – | – | – |
| 2 | 34102 5/0 P | 34102 5/0 P | 34102 7/1 | 34002 6/4 | 34002 6/2 | 34302 8/0 | (speech only, no text → nothing) | 34400 9/2 |
| 3 | 34100 5/2 | 34101 5/2 | 34209 7/8 | 34001 6/3 | 34001 6/1 | 34302 8/3 | – | 34400 9/2 |
| 4 | 34103 5/1 | 34104 5/1 | 34104 7/2 | 34003 6/9 | 34003 6/8 | 34301 8/1 | – | 34401 9/0 |
| 5 | 34106 5/10 | 34106 5/10 | 34106 5/10 | 34004 | 34004 | – | – | – |
| 6 | 34107 5/11 | 34107 | 34107 | 34005 | 34005 | – | – | – |
| 7 | – | – | 34200 7/5 | – | – | – | – | – |
| 8 | 34113 5/17 | – | 34202 7/9 | 34006 | 34006 | – | – | – |
| 9 | – | – | – | – | – | 34300 | – | – |
| 10 | 34108 5/3 | 34108 5/3 | 34108 5/3 | – | – | – | – | – |
| 11 | 34109 5/4 P | 34109 5/4 P | 34109 5/4 P | – | – | – | – | – |
| 12 | 34110 5/8 P | 34110 5/8 P | 34110 5/8 P | – | – | – | – | – |
| 13 | 34111 5/6 P | 34111 5/6 P | 34203 7/0 P | – | – | – | – | – |
| 14 | 34112 5/5 P | 34112 5/5 P | 34112 5/5 P | – | – | – | – | – |
| 15 | 1006 10/0 P | 1006 10/0 P | 1006 10/0 P | – | – | – | – | – |
| 16 | 1007 3/5 P | 1007 3/5 P | 1007 3/5 P | – | – | – | – | – |
| 17 | 34114 5/13 | 34114 5/13 | 34204 7/6 | – | – | – | – | – |
| 18 | – | – | 34205 11/1 | – | – | 34303 15/0 E | – | – |
| 19 | 34115 5/16 | 34115 5/16 | 34115 5/16 | – | – | – | – | – |
| 20 | – | – | 34201 16/0 | – | – | – | – | – |

(Packets: 3 `spells`, 5 `HumBtl`, 6 `OrcBtl`, 7 `DwrfBtl`, 8 `Skaven`, 9 `Monster`, 10 `Retreat`, 11 `Zhufbar`,
15 `Hiln`, 16 `HelpUs`. A speech cue whose packet is not loaded in the battle plays nothing.) Consequences:
- **Enemy shouts**: Goblinoid/Orc/Skaven/big enemies shout codes 1–9 when on screen; the "P" codes (Human/Elven
  charge and engage shouts, 11–16 order replies) are never shown for enemy-army units.
- `React 11` (enemy sighted, `threat_events_nodes.md` `ReactEnemySpotted`) has text only for Human, Elven and Dwarven
  rows and is P-marked, so in practice only player-side units of those races show it — consistent with batch 5.
- `React 18` (BF015/BF017 regiment 24's shout) is Dwarven 34205 with the Zhufbar speech, and Skaven 34303 with the
  `Hiln` cue marked E.
- Code 15/16 use the general battle strings 1006/1007 (shown for player-side Human, Elven and Dwarven units only).

Load the texts from `GMTXT.DLL` by these ids instead of embedding English strings.

| before | instruction | after |
|---|---|---|
| player Human unit | `React 4` | message 34103, portrait expression 4, speech HumBtl 1 |
| enemy Orc unit on screen | `React 2` | message 34002, expression 0, speech OrcBtl 2 |
| enemy Orc unit off screen | `React 2` | nothing |
| enemy Human unit on screen | `React 1` | nothing (P) |
| enemy Skaven unit off screen | `React 18` | message 34303 + Hiln 0 (E) |
| any Peasant unit | `React 2` | nothing (no text) |

## 🟡 Uncertainties

- Code 11's second Doomwheel alternative (leader close-combat weapon class 13): never in shipped data.
- Codes 19/20: which game event sets battle state 4; identity of sound effect 11; the 0x38 source field.
- Code 27 aim point (+off on both axes) reads like an original bug; reproduce for parity, or flag as "fix" in a mod.
- Code 14: a charging unit could in principle make contact attacks on itself (same unit within range of itself); never
  shipped (non-combatants do not charge).
- Contact handler refusals sending 0x0C to the contacted unit (newcomer branch) or to A (target branch) — exact visible
  effect not observed; `script_queries.md` already marks it.
- ENGAGE_PLAIN's extra refusal (a footprint state not identified).
- §2.5 possible stalemate of a latched, not-engaged unit.
- One special movement sub-state does not set the re-check state in the position step (not identified).
- Fanatic footprints in the collision pass (contact attacks against a fanatic) — see `game_rules.md` R45.

## Corrections to existing public notes

1. `game_rules.md` "Routes, collisions and visibility", `movement_formation.md` §3.10, `script_grid_events.md` §4:
   event 0x27 = a **wagon** touching any footprint within ±45° of its facing, not "an `INVSOLID` object straight
   ahead".
2. `game_rules.md` "Engagement": "two stationary touching enemies engage as well" — only if a collision pass runs for
   one of them (§2.6). Also "On the first overlapping tick the game only records the opponent … and sends event 0x0D"
   should read: the pass queues 0x0B (and runs the fear-on-contact test, whose failure is 0x0D); the *handler's* first
   step records the opponent and sends 0x07; engagement on a later handled contact — **except** when the unit already
   had a different target (engages at once) or is charging its target.
3. `game_rules.md` "Charge": `Engage` with counter 0 is used for buildings, war machines and wagons, not for
   "re-engaging an opponent you are already fighting"; a regiment contacting its current target regiment joins with
   `floor(1.5 × frontage)`.
4. `game_rules.md` event table: 0x0B is sent to the mover and, when the touched footprint is a troops regiment, also
   to that regiment; only by the collision pass.
5. `script_queries.md` §6 step 5 resolved: the "other object kinds" are war machines and wagons (rolling stock).
6. `script_queries.md` intro: code 11/12's `DetectThreat` re-picks only for **independent** units and answers a threat
   that targets the unit (or any threat, if independent) within R.
