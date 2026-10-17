# Charging a terror or fear causer: flight on contact, the brief grid and the causer's release

Public implementation report (behaviour only; states by name, numbers only for script operands, event codes and
gameplay constants). It answers what happens to **both** units when a unit charges (or walks into) a terror- or
fear-causing enemy and flees on contact. It was prompted by a BF026 replay: Orc Shaman Marak on a Wyvern
(one model, `CauseTerror`, class Monster, mission script 3) is charged by the Grudgebringer Cavalry.

Builds on (cite, do not repeat): `game_rules.md` "Fear and terror", "Engagement: battle grid and pairing" (Leaving,
caller table), "Pursuit" (op 0x53), §7.7 contact attacks; `script_behaviours.md` Part 2 (collision pass, contact
latch, §2.8 worked example, §2.9 contact-handler vectors); `script_grid_events.md` §2 (`FearWhenCharged`), §3
(`ChargeForward`), §4 (`CheckCollisions`); `script_queries.md` §6 (`Query 8`); `movement_formation.md` §5
(`FlankRearTest`), §6 (`LeaveSharedGrid`), "Left combat"; `unit_script_control.md` (LIFO queue, `Restart`).

---

## 0. Shared state first

These facts, all from the notes above or settled here, decide the whole sequence:

1. **The fear-on-contact test does not stop the contact.** In an ordinary (non-probe) collision pass, against an
   overlapping enemy the mover first runs the fear test (when it is not broken and its fear-passed state is off): a
   refusal sets the mover's current target to that enemy and queues **0x0D** to the mover. **Then, in the same
   pass, the contact is recorded as usual** and **0x0B** is queued to the mover (unless its contact latch is on).
   Only `CheckCollisions` probe mode skips the contact record (`script_grid_events.md` §4 is about probe mode).
2. **LIFO.** 0x0D is queued before 0x0B, so the mover handles **0x0B first**: the contact handler runs, and the
   flight comes only afterwards in the same handler pass.
3. **The contact handler never re-tests fear and never looks at a pending 0x0D.** A charging unit whose current
   target is the touched unit engages it as charger at once (`script_behaviours.md` §2.9 "A charging, X = U =
   target"). The only refusal there is "either unit broken", and the mover is not broken yet. Since the fear block
   has just made the causer the current target, **the charger always engages before it flees**.
4. **Reciprocal contact only for regiments.** When a mover touches another unit, the touched unit also gets a 0x0B
   (naming the mover) **only if the touched unit has an ordinary block footprint** (infantry, cavalry, archers;
   🟡 also wizards and special units, which share that footprint kind). **Monsters**, war machines and rolling stock
   have their own footprint kinds and get **no reciprocal 0x0B** from the mover's pass. They see the contact only through their own collision pass
   (re-check is switched on for them by the mover's pass).
5. **Rout leaves the grid** (`game_rules.md` caller table: rout leaves only if the unit is in melee, and here it is).
   The rout also marks the router's footprint as routing. After that the router is skipped by other units'
   collision scans and refused at the contact handler's entry, and **0x0F** is broadcast to the whole enemy side
   (source = router).
6. **A lone unit left on a grid gets 0x30, but not in the grid's creation segment.** A unit in melee runs the
   per-tick pairing step every tick. If it is the only unit on its grid, that step sends it **0x30** ("alone on a
   grid") on **every tick whose segment differs from the segment in which the grid was created**. It sends nothing
   while the segment is still the creation segment. Segments are the 19-tick units of `game_rules.md` "Battle
   clock". So the first 0x30 comes on the **first tick of the next segment**, 1–19 ticks after creation, and it
   repeats each tick until handled. (Side fact: a unit that is in melee but has no grid at all gets 0x0C from the
   same step. An engine must never leave a unit "in melee" without a grid.)
7. **The causer's engaged enemy is not set by the charger's engagement.** Engaging as charger points the
   **charger's** target at the defender. It leaves the defender's own current target as it was. So the
   rout-reaction gate (op 0x53, "event source = my current target") depends on what the causer was already
   targeting.

---

## 1. Q1 — what the terror causer receives; is a grid created?

**Yes, a grid is created**, around the causer (the causer is the **owner**, the charger joins and gets the charge
counter `floor(1.5 × frontage)`). It lasts only for the rest of the charger's own update, because the charger routs
in the same handler pass.

Events to the causer M from a charging C, in queue order (LIFO, so handled bottom-up of this list):

| Queued by | Event | When |
|---|---|---|
| (M's own collision pass, if M's corners penetrate C's box while C is not yet routing) | 0x0B (contact C) | the update of M after C's contact step, if M runs before C's next update |
| C's contact handler, engagement as charger | **0x08** (charger contact: flank/rear test), then **0x0A** (engaged) | C's update after contact |
| C's rout start | **0x0F** (an enemy routed, source C) | same C update, right after |
| M's own per-tick pairing (alone on the grid) | **0x30** | first tick of the next segment, repeated each tick until handled |

**No 0x07** reaches M. `ChargeForward` sends none at the start of the charge (`script_grid_events.md` §3), and
engaging as charger sends 0x08 + 0x0A, not 0x07. **No 0x0B from C's pass** reaches M, because M is a monster
(§0.4). **No 0x19** follows: the release is 0x30 (§2), not "opponent gone".

The charger C receives (handled in this order): 0x0B (contact M) → handler engages → 0x0A (engaged) → 0x0D (flee).
If M's pass ran in between, a second 0x0B also arrives (reciprocal from M's pass), and it is a no-op
("already has a grid").

## 2. Q2 — what releases the causer, and when

With M's mission handler (BF026 script 11 → library 155 → 152) the order of handling at M's next update is
**0x0F, then 0x0A, then 0x08, then any 0x0B**:

1. **0x0F** (script 11 case 15: `EnemyRouted; IfSwitchScriptHigh 164`). The gate is "source = M's current target".
   - **M's current target is not C** (none, or another unit): condition false, no switch.
   - **M's current target is C** (for example the mission loop's `TargetNearestEnemy` picked the approaching
     cavalry, and no cast made M busy). M is in melee and finds no other enemy on its grid → condition true →
     **164 locked as a high-priority switch** → M **pursues** C (§4 below).
   - M busy casting: `EnemyRouted` aborts, no switch.
2. **0x0A** (library 155 case 10). Not busy casting → `IfEngagedWithKind 128` false (C is not a building) →
   `SwitchScript 165` (pending; it does **not** override a locked 164). Busy casting → nothing, M keeps casting.
3. **0x08** (library 152 → `FlankRearTest`). C's direction now against M's facing: front → no roll; rear arc or the
   rear half of a flank → Leadership test, failure → 0x0C to M (handled next: 155 case 12 → `RoutAllowed` →
   `React 4` → `SwitchScript 162`, M flees; this overrides the pending 165 but not a locked 164).
4. **0x0B**, if present → `Query 8`: C's footprint is now routing → nothing.

Result in the common case: **M runs 165 while in melee, owner of a grid that holds only M**. Then, from the first
tick of the next segment, M's pairing step queues **0x30**: 11 → 155 → 152 case 48:
`LeaveSharedGrid` (true; grid freed) → `TestUnitFlags 0xa000` (broken or pursuing: false) →
`IfNotSwitchScript 163` → **163**: `Rally` (halt and re-form), `Yield`, `WaitWhileUnitFlags 8`,
`ReformToScriptRanks`, **`Restart`** → M's mission script 3 continues at its restart point (word 16, the
`IfEnemyPower 2 / ChooseEnemyAndSpellPay` loop).

So the original releases the causer **1–19 ticks** (at most one segment, 1.9 s) after contact, plus the re-form
time of 163. It does not wait 66 s for a 0x03 threat.

Side effects to keep:
- During that window M is in melee: player orders other than the exempt ones are refused (`game_rules.md` "Player
  orders"), and M's own collision pass does not run.
- If M was busy casting when 0x0A arrived (no 165), the later 0x30 still goes to 152 case 48 and switches M to 163.
  The `Restart` then begins the mission loop again. 🟡 This follows from the shipped scripts. Whether a cast already
  in its animation completes was not traced.

## 3. Q3 — fear instead of terror; Charge order versus Attack order

| Charger's path | Start-of-charge test | Contact with the causer |
|---|---|---|
| **Player Charge button** = `ChargeForward` (straight ahead) | none; it **clears** fear-passed | fear test runs on contact (fear-passed is off): terror → refused, no roll; fear → Leadership test at modifier 0 |
| **Attack order / AI attack** = 158/159 → `IfTargetInChargeReach` → 160 `ChargeTarget` | `ChargeTarget` clears fear-passed and then tests the target. **Terror: refused**, "My men fear the beast!", halt and re-form, then 163; **no charge ever starts** against a terror causer. Fear: Leadership test; failure is the same refusal; a pass sets fear-passed | a charge that started has fear-passed on, so the contact test is **skipped**: normal engagement, no flight |
| Ordinary move (the approach walk of 158/159, or a Move order) that overlaps the causer before charge reach | — | the same fear test on contact. A refusal gives the same sequence without the charge: the handler sees "not charging, target = touched unit", so the engagement is the ordinary newcomer one, still a grid around M, no 0x08; then 0x0D → flight |

**Fear case.** A failed Leadership test gives exactly the terror sequence of §1–§2 (engage, flee, M alone, 0x30).
A passed test sets fear-passed: no 0x0D, ordinary engagement and melee.

**Fear-passed is one state for the unit, not one per enemy.** While it is on, the contact test is skipped against
**every** enemy, a terror causer included. A unit that passed a fear test (or started a `ChargeTarget` charge at a
fear causer) and then touches a terror causer **does not flee**, until something clears the state (the next
`ChargeTarget`/`ChargeForward`, or `FearWhenCharged` when its gate passes). This follows directly from
`game_rules.md` "Fear and terror" situation 3 (the contact test is skipped while fear-passed is on), restated here because an engine that keys
the test per enemy diverges.

**Check for the BF026 replay.** If the Cavalry's charge at Marak started through `ChargeTarget` (script 160, the
"CHARGE!" of `React 2`), the original would have refused it at the start. A charge that reached contact must be
`ChargeForward` (the player's Charge button), or the contact must have come from a plain approach walk.

## 4. Q4 — the causer's contact attacks on the fleeing unit

The attack that "cuts down a fleeing model" is the automatic contact attack of `game_rules.md` §7.7. It is raised
by the **fleeing unit's own collision pass**: a broken mover that overlaps an enemy makes that enemy attack it. This
is at most once per segment per attacker, against models within `2 × reach` (24 for a monster). The attack changes
the victim's models only, plus the attacker's once-per-segment marker. It **does not** set M's current target, does
not make M charging or pursuing, queues no event to M and switches no script. Pursuit comes only from the 0x0F gate
in §2 step 1. If M does pursue (164: `LeaveSharedGrid` → re-form → "Destroy them!" → `Query 1` → `StartPursuit`),
the pursuit ends with 0x10, and 152 case 16 (`React 17; SwitchScript 163`) → `Restart` returns M to its mission
loop. A pursuer cannot re-engage its fugitive (`game_rules.md` "Pursuit").

## 5. Worked example (BF026 shape)

C = player cavalry on a Charge order (`ChargeForward`), no target, fear-passed off. M = terror monster, idle in
mission script 3, current target = none (variant: = C). Update t is the first in which C's step makes its footprint
corners penetrate M's box. Unit order does not change the outcome. Shown with M later in the order than C.

| Update / unit | What happens | State after |
|---|---|---|
| t, C | charge step; collision pass: M overlaps, C not broken, fear-passed off, terror → **C.target := M, 0x0D to C**; M re-check on; corners inside → **0x0B to C**; no reciprocal (M is a monster) | C charging, queue [0x0B, 0x0D] |
| t, M | no events; script; collision pass (re-check): C overlaps, C causes nothing → allowed; corners inside → 0x0B to M, reciprocal 0x0B to C | M queue [0x0B]; C queue [0x0B, 0x0B, 0x0D] |
| t+1, C | 0x0B → `Query 8`: charging, X = M = target → **engage as charger**: grid around **M** (M owner, in melee), C joins with the charge counter; **0x08, 0x0A to M; 0x0A to C**. 0x0A → 152 case 10 → pending 165. 0x0B → already has a grid, no-op. 0x0D → 151/153 case 13: `RoutAllowed` → `React 6` "Flee the abomination!" → `SwitchScript 162` (replaces 165). 162 `FleeFromTarget` → rout: **C leaves the grid**, broken, footprint routing, **0x0F to the enemy side** | C fleeing from M; grid holds M only; M queue [0x0F, 0x0A, 0x08, 0x0B] |
| t+1, M | 0x0F: source C ≠ M.target (none) → no switch. 0x0A → `SwitchScript 165`. 0x08 → `FlankRearTest` (frontal: no roll). 0x0B → C routing → nothing. Script 165. Pairing step: alone, still the creation segment → nothing | M in melee, alone, script 165 |
| t+2 … | C flees; each C pass that overlaps M makes M's contact attacks on C (at most once per segment) | unchanged for M |
| first tick of the next segment, M | pairing step: alone, segment changed → **0x30** → 152 case 48: `LeaveSharedGrid` (grid freed) → not broken/pursuing → **163** | M not in melee, re-forming |
| then | 163 → `Restart` → mission script 3 word 16: `IfEnemyPower 2` / `ChooseEnemyAndSpellPay` again | M casting loop resumes |

Variant M.target = C at t+1: 0x0F → in melee, no other enemy on the grid → **164 locked**; the 0x0A switch to 165
is ignored; 164 `LeaveSharedGrid` (grid freed, so no 0x30 ever comes) → re-form → "Destroy them!" → pursuit →
0x10 → 163 → `Restart`.

## 6. Test vectors

| Before | Step | After |
|---|---|---|
| C charging (`ChargeForward`), not broken, fear-passed off, no target; overlaps terror monster M | C's collision pass | C.target M; C queue [0x0B, 0x0D]; M gets **no** 0x0B; M re-check on |
| same, but M is a terror **regiment** (regiment footprint) | C's collision pass | as above, plus **0x0B to M** (reciprocal) |
| same, C fear-passed **on** | C's collision pass | no fear test, no 0x0D; 0x0B to C only → ordinary engagement |
| C queue [0x0B(M), 0x0D], C charging, C.target M, nobody on a grid | C's handler pass | grid around M (M owner), C joiner with charge counter, 0x08 + 0x0A to M, 0x0A to C; then C routs: leaves grid, broken, 0x0F to M's side; C runs 162 |
| C walking (not charging), same queue, C.target M | C's handler pass | ordinary newcomer engagement (grid around M, no 0x08), 0x0A both; then rout as above |
| M owner, alone on its grid, in melee, creation segment = current | M's pairing step | nothing |
| same, current segment ≠ creation segment | M's pairing step | 0x30 to M (again every tick until handled) |
| M in melee, **no grid** | M's pairing step | 0x0C to M (an engine state that must not happen) |
| M 0x0F from C, M.target none or another unit | script 11 case 15 | condition false, no switch |
| M 0x0F from C, M.target C, M in melee alone on the grid, not busy casting | script 11 case 15 | 164 locked (pursuit) |
| M 0x0A, not busy casting, target not a building | 155 case 10 | pending 165 |
| M 0x0A, busy casting | 155 case 10 | nothing |
| M 0x30, in a grid, not broken, not pursuing | 152 case 48 | grid left (freed), condition true → switch 163 → later `Restart` |
| C (broken, fleeing) overlaps M in C's pass, M's marker clear this segment | C's collision pass | M's contact attacks on C's models within 2 × 24; M's target, flags and script unchanged |
| C on an Attack order reaches charge reach of terror M | 160 `ChargeTarget` | refused, "My men fear the beast!", halt and re-form, no 0x07 to M, then 163 |

## 7. Differences from the implementer's current model (BF026 replay)

- **Missing grid.** The engine sends 0x0A to M without a grid. The original builds a real grid around M (C as
  charger-joiner), and the charger's rout then leaves it, so M is **in melee and alone**. Its pairing step then
  provides the release (0x30) one segment boundary later. With that, M leaves 165 within ≤ 19 ticks and returns to
  its mission script through 163 → `Restart`.
- **Extra events.** M should also receive **0x08** (flank/rear test) before the 0x0A, and **0x0F** after it (from
  C's rout). Check M.target at tick 2505. If it was the Cavalry, M pursues instead (164).
- **Charge path.** Check that the Cavalry's charge was a `ChargeForward`. A `ChargeTarget` charge at a terror causer
  is refused at its start in the original.

## 8. "Flee the abomination!" twice (issue #343)

Prompted by a BF026 replay in which the Grudgebringer Cavalry, charged by the Wyvern, shouted `React 6` on two
consecutive ticks and routed on the second. **In the original the unit is already broken by the end of the tick in
which it handles its first 0x0D**, so a later 0x0D is refused silently. No fear test remembers a failure: what
stops the second shout is the timing of the rout, nothing else.

### 8.1 Shared state

- **The handler drains the whole queue in one pass.** The player and AI event handlers (101, 103, …) end with
  `ConsumeEvent; LoopIfTrue` back to `GetEvent`, then `ReturnInterrupt` (`unit_script_control.md` §1, §4).
  `ConsumeEvent` sets the condition to "queue not empty". So every event queued before the pass, **and every event
  queued during it** (e.g. the 0x0D from `FearWhenCharged`), is handled in the same pass. LIFO order:
  `unit_script_control.md` §1.
- **Nothing rout-related happens in the 0x0D/0x0C arm itself.** In library 153/155 the arms are
  `RoutAllowed; If; React 6 (or 4); SwitchScript 162; EndIf`. `React` only shows text, speech and portrait.
  `SwitchScript` only records a pending switch. The unit stays unbroken for the rest of the handler pass. A second
  0x0D handled **in the same pass** passes `RoutAllowed` again and shouts again (§8.4).
- **`ReturnInterrupt` applies the pending switch and keeps running.** With a switch pending (and not refused), the
  unit leaves the handler straight into the new script **at its first instruction, in the same script run**. It does
  not first return to the interrupted script, and it does not wait for the next tick. Script 162 starts with
  `FleeFromTarget`, so the rout starts there and then: the unit is broken, leaves its grid, its footprint becomes
  routing and 0x0F goes to the enemy side (`game_rules.md`, rout start). It then reaches 162's `Yield`.
  (`unit_script_control.md` §1 says "applied at the end of the tick or at `ReturnInterrupt`". This section adds that
  in the `ReturnInterrupt` case the new script also **runs on** in the same tick.)
- **Per-unit tick order** (`game_rules.md`, unit tick): script (events first) → formation → movement → collision
  pass → models. The rout therefore starts **before** the unit's own collision pass of that tick. The contact fear
  test is skipped for a broken mover, so that pass queues no new 0x0D.
- **`RoutAllowed` on a broken unit is false and silent** (no shout; only `CantBreak` gives `React 7`). A 0x0D or
  0x0C handled on a later tick does nothing.
- **Other units' collision passes never queue 0x0D to this unit.** The contact fear test belongs to the mover only.
  When the Wyvern is the mover, it is the Wyvern that is tested, and the Cavalry causes no fear (§1).

### 8.2 Answers

1. **What stops the second shout:**
   - The rout starts in the same tick as the first 0x0D handler, through `ReturnInterrupt` → 162 →
     `FleeFromTarget`.
   - By the next tick the unit is broken, and `RoutAllowed` refuses silently.
   - No fear test checks for a "pending flight". `FearWhenCharged` and the contact test only refuse for a broken
     unit (and the contact test while fear-passed is on).
   - The pending-switch state is not read by `RoutAllowed` or by the arm.
2. **When 162 makes the unit broken:** the same tick, inside the same script run as the handler, before the
   unit's formation, movement and collision steps. At handler time (between `React 6` and `ReturnInterrupt`) only the
   pending switch to 162 exists. Fear-passed stays off, and the current target is the one the fear test wrote.
3. **Does the original ever show the shout twice?** Yes, but only **within one handler pass** (the same tick), never
   on two consecutive ticks. It needs two 0x0D in the queue before `ReturnInterrupt`. Example: the unit's own contact
   test queued 0x0D on tick t, and before its run on t+1 a terror causer starts a charge at it (0x07, whose
   `FearWhenCharged` queues a second 0x0D). The queue is then [0x07, 0x0D] (lists are written head first). Both 0x0D are handled in one pass and both shout. Effects: the text is printed
   twice; the speech cue is not restarted while it is still playing; the portrait shows once
   (`react_portrait.md` §2, "one portrait at a time"). 🟡 Not observed on screen, and rare in play.
4. **0x0C ("Retreat!", `React 4`):** the same rule, same arm shape, same `RoutAllowed`, same 162. Several 0x0C in one
   pass shout once each (e.g. two panic tests failed by one volley). A 0x0C together with a 0x0D gives "Retreat!"
   and "Flee the abomination!" in the same pass. After the pass the unit is broken, and later 0x0C are silent.

### 8.3 Difference from the implementer's model

The engine applies the switch at `ReturnInterrupt` (or at the end of the tick) but runs 162 only on the **next**
tick. The unit then stays unbroken for one tick. In that tick:

- its own collision pass re-runs the contact fear test (not broken, fear-passed off) and queues a second 0x0D;
- the next tick's handler shouts again before 162 runs.

Fix: when `ReturnInterrupt` applies a pending switch, start the new script at instruction 0 and **continue
interpreting in the same run**, until the new script yields or waits. Do this before formation, movement and the
collision pass. No extra "flight pending" state is needed, and adding one would hide the original's same-pass double
shout (§8.2 item 3). Handler 101/103 open with `ClearCondFlags 8`, so a switch that was pending before the handler
started is dropped at handler entry. Only switches recorded during the pass are applied.

### 8.4 Test vectors

C = Grudgebringer Cavalry (player, handler 101 → 153), W = Wyvern (causes terror), C not `CantBreak`, fear-passed
off.

| Before | Action | After |
|---|---|---|
| C idle, queue [0x07 (W charging)] | C's run, tick t | 0x07: `FearWhenCharged` → target W, **0x0D queued**, pending 161; loop: 0x0D → `RoutAllowed` true → **"Flee the abomination!" (1)**, pending 162; queue empty → `ReturnInterrupt` → 162 → `FleeFromTarget`: **C broken**, 0x0F to W's side; `Yield` |
| (same tick) C broken, overlapping W | C's collision pass, tick t | no fear test (broken mover), no 0x0D |
| W charging, overlapping C | W's collision pass | W is the tested mover; C causes no fear → no 0x0D to C |
| C broken, queue [0x0D] (left over) | C's run, tick t+1 | `RoutAllowed` false, **no shout**; C keeps fleeing (162 loop) |
| C on a Move order overlaps a stationary W | C's collision pass, tick t | C.target W, queue [0x0B, 0x0D] (0x0B at the head) |
| C queue [0x0B, 0x0D] | C's run, tick t+1 | 0x0B: ordinary newcomer engagement (§3); 0x0D: **one shout**; 162 → broken, same tick |
| C queue [0x07 (W), 0x0D (own contact test)] | C's run | 0x07 → `FearWhenCharged` queues 0x0D (head) → shout (1); then the old 0x0D → `RoutAllowed` still true → **shout (2)**, same pass; then rout. Text ×2, speech once if the cue is still playing, one portrait 🟡 |
| C queue [0x0C, 0x0C] (two failed panic tests) | C's run | "Retreat!" ×2 in the same pass; 162 → broken |
| C queue [0x0C, 0x0D] (0x0C at the head) | C's run | "Retreat!", then "Flee the abomination!"; 162 → broken |
| C `CantBreak`, queue [0x0D] | C's run | `React 7`, no switch from this arm, not broken; a later 0x0D gives `React 7` again |
| C broken, 0x0C queued later | C's run | silent |

### 8.5 Follow-up: event order at contact (the engine trace of BF026, update 2526)

The engine trace handled C's events in this order (head first):

1. 0x07 (W) → `FearWhenCharged` → 0x0D;
2. 0x0D → shout, pending 162;
3. 0x0B (the reciprocal from W's collision pass) → `Query 8` engages C;
4. 0x0A → `SwitchScript 165`, which replaces 162.

The pass ends with C unbroken and in melee on 165. C's own collision pass then queues a new 0x0D, which shouts again
on the next tick. In the original this order cannot arise. Each step below would behave the same if that order did
happen; the difference is the order itself.

**Where 0x07 is sent.** 0x07 is only ever sent during a **script step** (the sender's, or for `ReactToThreat` the
receiver's own), never from movement or from a collision pass. The senders are:

| Sender's script step | Condition | Target's later `FearWhenCharged` |
|---|---|---|
| `ChargeTarget` starts a charge (`game_rules.md` "Fear and terror", situation 2) | charge accepted | sender charging → fear/terror test runs |
| `ReactToThreat` (the **reacting unit's own** script step, AI handler on event 3): the threat is charging this unit | the unit is not charging, pursuing, broken or braced, and not in melee | the unit queues 0x07 **to itself**, source = the threat (charging) → test runs in the same pass |
| the contact handler (`Query 8`, while the sender handles **its own** 0x0B): sender charging (or pursuing) and the touched enemy is **not** its target → the charge is redirected to the touched enemy (0x1A to the old target) | — | sender charging → test runs |
| the contact handler: sender not charging, not in melee, **no target**, not broken → sender's target := touched enemy ("first contact", `game_rules.md` "Engagement") | no engagement yet | sender **not** charging → `FearWhenCharged` does nothing (condition false, no test) |

A charger that touches **its own target** engages; it sends no 0x07.

**Why the order cannot arise.**
1. Within one unit's run, the steps are script → movement → collision pass. So a 0x07 and a reciprocal 0x0B from
   the same sender's run reach C with the **0x0B newer**. LIFO then hands C the 0x0B **first**.
2. Every unit runs once per tick, and C's handler drains its whole queue (§8.1). C therefore always runs between W's
   collision pass and W's next script step. W's reciprocal 0x0B is gone before W's next 0x07 can be queued.
3. Hence, in C's pass, an engagement from W's 0x0B (and its 0x0A → 165) comes **before** the 0x0D that W's 0x07
   produces. The switch recorded last is 162.
4. A 0x0D from C's **own** collision pass is queued just before that pass's own 0x0B. It lies **under** its 0x0B and
   is handled after any engagement that 0x0B makes. 162 is again recorded last.

Here, "each step would behave the same" means:

- `Query 8` is not refused because a switch is pending.
- 0x0A's `SwitchScript 165` does replace a pending 162: the `SwitchScript` family does not lock, and only
  `IfSwitchScriptHigh` does (`unit_script_control.md` §1).
- `RoutAllowed` does not look at the pending switch.

Two edge cases could still put a fresh 0x0D above an engaging 0x0B. Both are 🟡 rare and not constructed in shipped
data:

- two fear causers in the same tick: W (any monster) touches C, then a **second** terror or fear causer X starts
  a charge at C before C runs;
- an AI unit whose handler meets event 3 (`ReactToThreat`) above an older 0x0B: the self-queued 0x07 → 0x0D →
  162 comes first, then the older 0x0B engages and its 0x0A → 165 replaces 162.

**The contact fear test while in melee (question C).** The test in the collision pass has **no** guard for "in
melee", "already engaged with this enemy" or "same grid", and no first-contact latch. When C's collision pass runs
with C overlapping a terror causer, and C is not broken with fear-passed off, the test refuses again, sets the target
and queues 0x0D, every time. The pass, however, runs only while C's **re-check** state is on (`fanatic_collisions.md`;
`game_rules.md` unit tick).

- A unit in melee does not translate, so its own movement does not arm re-check.
- Another unit's pass arms the touched unit's re-check only if that mover is **not** in melee.
- So in a settled melee the test does not repeat every tick. It repeats when something re-arms re-check: a
  moving unit's pass touching C, a turn or footprint change, a push, the contact handler's first-contact and
  redirect branches.
- In practice none of this matters, because C is broken by the end of the pass that handles the first 0x0D (§8.1).

**Answer to question D.** In the original, this BF026 situation does **not** shout on two consecutive ticks. C routs
in the tick in which it first handles the fear 0x0D. That tick can carry **two** shouts in one pass, when both a
0x07-derived 0x0D and its own pass's 0x0D are queued (trace below). The engine needs two rules:

- (a) send 0x07 only from the sender's script step (`ChargeTarget`, `ReactToThreat`, contact handling of the
  sender's own 0x0B). Never send it from movement or from the collision pass.
- (b) the collision pass queues its 0x0D **before** its 0x0B.

With both, the switch to 162 is always recorded after any 0x0A of the same pass.

Original order, the BF026 shape. W = Wyvern, charging with no target (e.g. `ChargeForward`) or with another target.
Unit order W before C. C idle, fear-passed off. Lists are written **head first**.

| Before | Action | After |
|---|---|---|
| tick t: W overlaps C | W's collision pass | 0x0B to W; reciprocal 0x0B to C; C re-check on. C queue [0x0B] |
| C queue [0x0B], C no target | C's run, tick t | 0x0B → `Query 8`, first contact: C.target := W, 0x07 to **W** (W's `FearWhenCharged` later does nothing: C is not charging). C not engaged |
| C overlapping W, re-check on | C's collision pass, tick t | fear test refused (terror): C.target W, **0x0D**; then contact: 0x0B to C (no reciprocal: W is a monster). C queue [0x0B, 0x0D] |
| W queue [0x0B, 0x07(C)] | W's run, tick t+1 | 0x0B → `Query 8`: W charging, C is not its target → redirect: W.target := C, **0x07 to C**. 0x07 → nothing. W's pass: 0x0B to W, reciprocal 0x0B to C. C queue [0x0B(W), 0x07(W), 0x0B(own), 0x0D(own)] |
| that queue | C's run, tick t+1 | 0x0B(W): C.target = W → engagement, C in melee, 0x0A → `SwitchScript 165`. 0x07: W charging → terror, C in melee → 0x0D queued (condition false, no 161). 0x0D → **shout 1**, 162 replaces 165. 0x0B(own): already on the grid, nothing. 0x0D(own) → `RoutAllowed` still true → **shout 2** (same pass), 162. `ReturnInterrupt` → 162 → **C broken** |
| C broken | C's collision pass, tick t+1 | no fear test |
| C broken, any later 0x0D/0x0C | later ticks | silent |

| Before | Action | After |
|---|---|---|
| (engine order, impossible in the original) C queue [0x07(W), 0x0D, 0x0B(W)] | C's run | 0x07 → 0x0D (head), shout, 162; 0x0D → shout, 162; 0x0B → engage, 0x0A → 165 **replaces 162**; ends on 165, unbroken. This is the reported bug; fix the send order, not the switch rules |
| C in melee with W, not broken, fear-passed off, re-check on | C's collision pass | refused again: 0x0D queued (no latch, no in-melee guard) |
| same, re-check off | tick | no pass, no 0x0D |

## 🟡 Uncertainties

- Whether a cast already in its animation finishes when 0x30 switches a busy-casting causer to 163 (§2).
- The exact contact-attack timing on the first contact tick (`game_rules.md` §7.7 is unchanged by this report).
- Not observed at runtime. The sequence follows from the traced collision pass, contact handler, rout start and
  pairing step together with the shipped BF026 scripts.
