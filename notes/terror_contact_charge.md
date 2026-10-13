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

## 🟡 Uncertainties

- Whether a cast already in its animation finishes when 0x30 switches a busy-casting causer to 163 (§2).
- The exact contact-attack timing on the first contact tick (`game_rules.md` §7.7 is unchanged by this report).
- Not observed at runtime. The sequence follows from the traced collision pass, contact handler, rout start and
  pairing step together with the shipped BF026 scripts.
