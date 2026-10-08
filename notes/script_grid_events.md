# Unit-script close-combat grid, charge, fear and event targets

Public implementation report, batch 9 of the interpreter requests (GitHub #3), part 1 of 3 (companions: `script_spawn_move.md`, `script_shooting.md`). Behaviour only; states by name, numbers only for script operands, event codes and battle-file data.


Opcodes: `TakeEventTarget` 0x3A, `TakeRangedEventTarget` 0x88, `TakeSpellEventTarget` 0xAF,
`FearWhenCharged` 0x42, `ChargeForward` 0x4F,
`CheckCollisions` 0xC7, `SwitchOpponentInGrid` 0x55. All are 1 word, no operand.

Shipped uses (all 45 mission DLLs, library counted in every DLL): 0x3A 276, 0x88 450, 0xAF 315 (1041 together),
0x42 239, 0x4F 45 (library 106 only), 0xC7 45 (library 166 only), 0x55 94.

Already public and only extended here: `movement_formation.md` §3.6 (`ChargeForward`), §3.10 (`CheckCollisions`),
§7 (`SwitchOpponentInGrid`), §8 (`IfEngagedWithKind`); `script_magic.md` §4 (the cast order path);
`game_rules.md` "Fear and terror", "`StoreEventInfo` (0x61)", "Charge", event table;
`script_queries.md` §5 (Query 7, brace) and §6 (Query 8, contact handler); `target_queries.md` §5.1/§5.3 (aim
point P, final waypoint); `unit_script_control.md` (condition, LIFO queue, deferred switches).

---

## 0. Shared state first

| State | Who reads / writes it here |
|---|---|
| **current target** (= engaged enemy; one slot) | target-taking family (unit branch writes it; ground branch clears it), `FearWhenCharged` (writes it only if empty), `SwitchOpponentInGrid` (replaces it), contact fear in `CheckCollisions` (writes it) |
| **pending spell** (a code; any value ≤ 0 counts as *none*) | target-taking family **always** overwrites it with the event's argument |
| **target point** | target-taking family ground branch |
| **braced** (the order-blocking state of `game_rules.md` "Braced"; orders are refused while braced) | cleared by the target-taking family when it accepts a named unit; nothing else here touches it |
| **fear-passed** (game_rules psychology "fear test passed: spares further fear tests until the next charge clears it") | cleared by `FearWhenCharged` (when its gate passes) and by a successful `ChargeForward` (and `ChargeTarget`); set by a passed fear test |
| **final waypoint** | target-taking family unit branch replaces it with the aim point P (`target_queries.md` §5.1/§5.3) |
| **condition** | written by every opcode here except `SwitchOpponentInGrid` when the unit is not in melee |
| **deferred script switch** | not written by these opcodes, but the idioms below depend on it: `SwitchScript`/`IfSwitchScript` record a pending switch that a **later** `SwitchScript` in the same handler pass **overwrites**; only `IfSwitchScriptHigh` locks it (`unit_script_control.md` §1/§6) |

Event record (`threat_events_nodes.md` §0.2): recipient, code, **source unit** (or none), **argument**, **point x, y**.
The argument and point that the game's order code puts in each event kind are listed in §1.3 — they matter because
the target-taking family copies the argument into the pending spell unconditionally.

Unit states used by name: **charging**, **in melee**, **broken**, **pursuing** (set only by the start of a pursuit,
`game_rules.md` "Charging flag … Pursuing flag"), **braced**, **busy casting** (= `IfCasting`'s definition,
`script_animation_sound.md` §3.2: class Wizard and (a model in the cast action, or a spell pending, or channelling)).

---

## 1. Target-taking family — `TakeEventTarget` 0x3A, `TakeRangedEventTarget` 0x88, `TakeSpellEventTarget` 0xAF

### 1.1 One rule, one switch

The three opcodes run the same procedure. The only difference is a **"refuse broken units"** switch:

| Opcode | Refuse a broken named unit? | Shipped use |
|---|---|---|
| **0x3A** | **yes** | event **0x04** (attack this target) only: library 101, 103, 104, 151 and mission handlers (276) |
| **0x88** | no | shooter handlers library 154 (artillery) and 156 (archers), events 0x1E–0x21, 0x24, 0x25 (450) |
| **0xAF** | no | wizard handler library 155, events 0x28–0x2B, 0x2E, 0x2F; library 152 event 0x2D (item) (315) |

0x88 (`TakeRangedEventTarget`) and 0xAF (`TakeSpellEventTarget`) are behaviourally identical;
0x3A (`TakeEventTarget`) additionally refuses a broken named unit. The three names distinguish
their shipped uses in disassembly and logs, while the engine uses one shared handler rule.

### 1.2 Procedure

Runs inside an event handler (it reads the current event).

```
0. During the deployment phase (before the battle starts): condition := false; nothing else changes
   (the pending spell is NOT written).
1. pending spell := the event's argument                       (always, in every branch below)
2. If the event has a source unit S  ("unit branch"):
     refuse if the taker is charging, in melee, broken or pursuing
     refuse (0x3A only) if S is broken
     refused  -> condition := false. Target, point, braced, waypoints unchanged.
     accepted -> braced := off
                 current target := S
                 final waypoint := aim point P at S   (target_queries.md §5.1; same replacement rule as §5.3:
                                   last queued waypoint overwritten, or waypoint 1 if none queued)
                 condition := true
3. Else (no source: "ground branch"):
     if the new pending code is "item-marked" (code & 256 ≠ 0 — true for item codes and for −1)
        AND the taker already has a current target:
           nothing else changes (target and target point kept)
     else:
           current target := none
           target point   := the event's point (x, y)
     condition := true                                          (both sub-cases)
```

Notes:
- No validity checks on S beyond the two refusals: S may be any unit, alive or not, friend or foe (shipped senders
  only name live units).
- It never starts a move, a turn or a charge, and never sets aim-at-point; the switched-to script does that.
- The braced state is cleared **only** on the accepted unit branch. The ground branch and refusals leave it.
- The refusal set (charging, in melee, broken, **pursuing**) is the 🟡 "one more excluded state" of
  `script_magic.md` §4: it is **pursuing**. It is the same set for which `game_rules.md` says orders are ignored.

### 1.3 Per event kind (what the game puts in each event, and the outcome)

| Event | Sent for | Source | Argument | Point | Opcode | Outcome |
|---|---|---|---|---|---|---|
| 0x04 | attack order on a unit/building; also `ReacquireEventSource`, Find* queries | the target unit | 0 | 0,0 | 0x3A | unit branch; **pending := 0 (none)**; refused also if the target is broken |
| 0x1E / 0x1F (0x25 for an independent Archers unit) | shoot order clicked on a building / an enemy unit | that unit | 0 | – | 0x88 | unit branch; pending := none |
| 0x20 (0x24 independent Archers) | shoot order clicked on the shooter itself | none | 0 | (−1,−1) | 0x88 | ground: target := none, point := (−1,−1) |
| 0x21 | shoot order on open ground | none | 0 | click | 0x88 | ground: target := none, point := click |
| 0x28 / 0x29 (0x2F independent) | wizard order without a chosen spell, clicked on a building / another unit 🟡 (UI action) | that unit | −1 | (−1,−1) | 0xAF | unit branch; pending := −1 (none) |
| 0x2A (0x2E independent) | same, clicked on the wizard itself | none | −1 | (−1,−1) | 0xAF | ground, item-marked (−1): existing target **kept**, point unchanged; no target → target none, point (−1,−1) |
| **0x2B** | **cast order** (spell button, then click) | **none — always** | spell code | the click (🟡 may be snapped to the clicked unit's position in one panel mode) | 0xAF | ground: target := none, point := click; pending := spell |
| 0x2D | item use | none | item code (has 256) | click | 0xAF (library 152) | ground, item-marked: existing target kept, else target none + point := click |

**Correction to `script_magic.md` §4:** a player cast order (event 0x2B) **never names a unit** — the event source is
always none, so its unit branch ("becomes the target only if the caster is not charging, …") is never reached by a
cast order. The spell goes to the clicked point, and the launch then needs a unit under the point for unit-target
spells (`game_rules.md` "Checks"). The unit branch is reached by events 0x28/0x29/0x2F (wizard), 0x1E/0x1F/0x25
(shooters) and 0x04 (attack).

**Side effect to keep (all kinds): the pending spell is overwritten** even when the result is false. On an attack
event (argument 0) or a wizard/shoot event (argument 0 or −1) this silently **drops** a pending spell, without the
panel re-enable that `DropPendingSpell` does. Consequence: a wizard that accepts event 0x04 is no longer "busy
casting" by the pending-spell criterion. (Shipped handlers 103 and 155 guard 0x04/0x0A/0x2B with `IfCasting`, so a
busy wizard does not reach this in practice.)

### 1.4 Differences from the implementer's model

Model: "target := current event source, condition true". Differences: (1) the pending spell is overwritten from the
event argument; (2) refusal when the taker is charging/in melee/broken/pursuing (cond false, target kept); (3) 0x3A
also refuses a broken source; (4) accepted → braced cleared and final waypoint re-aimed at P; (5) no source → target
cleared and target point set (except the item-marked case); (6) deployment → nothing, cond false.

### 1.5 Test vectors

Unit A at (0,0); enemy block B centre (0,200) facing 256 (towards A), half-diagonal r 30, so P = B's far side
(0,230) (`target_queries.md` §5.1, front arc → aim angle f_t+256 = 0 → (0, 200+30)).

| Before | Event / instruction | After |
|---|---|---|
| A idle, no target, pending none, braced, 0 waypoints | 0x04 from B, `TakeEventTarget`(0x3A) | target B, braced off, waypoint 1 = (0,230), count 1, pending 0 (none), cond true |
| A idle, 2 waypoints [(50,50),(80,80)] | same | waypoints [(50,50),(0,230)], count 2 |
| B broken | 0x04 from B, 0x3A | cond false; target unchanged; pending := 0 |
| B broken | 0x1F from B, 0x88 | accepted: target B, cond true (no broken check) |
| A charging (or in melee, broken, pursuing), target C | 0x04 from B, 0x3A | cond false; target C; braced unchanged; pending := 0 |
| A wizard, pending 22, idle | 0x04 from B, 0x3A | target B, **pending 0 (none)**, cond true |
| A wizard, target C, pending none | 0x2B, argument 22, point (100,300) | target none, point (100,300), pending 22, cond true |
| A wizard in melee with C | 0x2B, arg 22, point (5,5) | target none (!), point (5,5), pending 22, cond true — the ground branch has no state refusal |
| A, target C | 0x2D, arg 0x105 (item), point (10,10) | target C kept, point unchanged, pending 0x105, cond true |
| A, no target | 0x2D, arg 0x105, point (10,10) | target none, point (10,10), cond true |
| A wizard, target C | 0x2A (self click), arg −1 | target C kept, point unchanged, pending −1, cond true |
| A shooter, target C | 0x21, point (40,60) | target none, point (40,60), pending 0, cond true |
| deployment phase, any | any | cond false, pending unchanged, nothing else |

---

## 2. `FearWhenCharged` 0x42

### 2.1 Rule

Inside the handler of event **0x07** ("you are being charged"); C = the event's source (the charger).

```
gate: C is charging  AND  the unit is not broken  AND  the unit is not busy casting
gate fails -> condition := false; nothing else.
gate passes:
   if the unit has no current target: current target := C      (an existing target is kept)
   fear-passed := off            (so the test below is always taken when fear applies)
   MayEngage(unit, C)            (game_rules.md "Fear and terror": terror -> refused without a roll unless
                                  Frenzy/PsyImmune; fear -> Leadership test at modifier 0, a pass sets fear-passed;
                                  otherwise allowed)
   refused -> queue event 0x0D to the unit itself (head of the queue). The record carries no meaningful
              source (🟡 it holds the first unit of the table; no shipped 0x0D handler reads the source)
   condition := the unit is neither charging nor in melee            (written whether or not the test failed)
```

Facts worth stating:
- **The condition does not report the fear result.** A failed test still leaves the condition true (if the unit is
  not charging/in melee); the flight comes from the queued 0x0D, which wins over the brace switch (§2.3).
- A unit **in melee or charging still takes the test** (and can be sent fleeing), it only does not brace.
- No `braced` state, no `StoreEventInfo` and no switch here — those are the script's (`StoreEventInfo`, Query 7 in 161).
- The target is set only when empty, so a unit that fails and flees runs (`FleeFromTarget`, script 162) away from its
  **existing** target, which need not be the charger. 🟡 (visible only for units that had another target.)
- Immediate; no movement.

### 2.2 Shipped idioms

- **Library 151, 153–156 and mission handlers (223 shipped copies)**: `CaseEvent 7: StoreEventInfo; FearWhenCharged; IfSwitchScript 161`.
- BF004_4 scripts 12–14: `SendEventToTag t 12` (tell a tagged unit to rout) before the same three.
- 11 mission handlers (BF005, 006, 015, 017, 020, 026, 029, 030, 031, 040, 042; the handler that also maps 0x27 to
  script 166 and 0x17 to `KillAllModels` — 🟡 the fanatic handler): `CaseEvent 7: FearWhenCharged` alone — its only
  lasting effects are "target the charger if no target" and the fear test (its 0x0D has no handler case there, so it
  is ignored).

### 2.3 When library 155 (and 151/153/154/156) switches to 161

`IfSwitchScript 161` is taken when, at the moment of the 0x07:
the charger is still charging, the unit is not broken, not busy casting (155: wizards), not charging, not in melee.

It **does not stand** if the fear test failed and the unit may rout: the 0x0D queued by `FearWhenCharged` is taken
in the same handler pass (`ConsumeEvent` → queue not empty → `LoopIfTrue` → `GetEvent`), its case runs
`RoutAllowed; If React 6; SwitchScript 162`, and that **later deferred switch replaces 161** (161 was set by
`IfSwitchScript`, which does not lock). With `CantBreak` (`RoutAllowed` false) the 161 switch stands and the unit
braces after all.

161 then: Query 7 (`script_queries.md` §5: if not braced and the stored code is 0x07 → target := charger, braced,
true), `HaltAndReform`, then `FaceModelsToTarget` every tick.

### 2.4 Test vectors

Unit U (not fear-immune), charger C.

| Before | Instruction (handling 0x07 from C) | After |
|---|---|---|
| C charging, C causes no fear; U idle, no target | `FearWhenCharged` | target C, fear-passed off, no event, cond true |
| same, U has target D | `FearWhenCharged` | target D kept, cond true |
| C no longer charging | `FearWhenCharged` | cond false, nothing changed (fear-passed kept) |
| U broken | `FearWhenCharged` | cond false, nothing |
| U Wizard with a spell pending | `FearWhenCharged` | cond false, nothing (busy casting ignores charges) |
| C causes terror; U not Frenzy/PsyImmune; idle | `FearWhenCharged` | 0x0D queued to U, target C, cond **true** |
| same, U in melee | `FearWhenCharged` | 0x0D queued, cond **false** |
| C causes fear, U passed a fear test earlier (fear-passed on) | `FearWhenCharged` | fear-passed cleared first, so a new Ld test is rolled |
| C causes fear, U has its own Dread Banner | `FearWhenCharged` | no test (fear does not apply), cond true |

---

## 3. `ChargeForward` 0x4F

Public mechanics are in `movement_formation.md` §3.6 (destination 12 × s_rlmv ahead, not from inside a `0xB0` region,
start of charge, free-charge state, failure → halt and re-form, cond false). Additions and relation to the charge rules:

- **No fear or terror test at the start** (resolves the 🟡 in `game_rules.md` "Fear and terror", situation 2). It has
  no target to test against, gives no "My men fear the beast!" refusal, and sends **no 0x07** to anyone, so no
  defender gets the "being charged" fear test or braces at the start of the charge.
- On success it also **clears the unit's own fear-passed state** (as `ChargeTarget` does), so the first enemy it
  touches triggers the contact fear test ("Contact while moving", game_rules situation 3) afresh.
- It does not touch the target or the pending spell; it plays no message — script 106 does `React 2` ("CHARGE!")
  **unconditionally after** it, so a refused `ChargeForward` still shows the charge message, then the loop
  `TestUnitFlags 16` is immediately true (halted) and the script goes to 163 (re-form).
- Contact during the charge is the ordinary contact handler (`script_queries.md` §6): the unit counts as charging,
  so a unit it runs into becomes its target (redirect: 0x1A/0x07) and is engaged as by a charger, giving the charge
  counter (`game_rules.md` "Charge").

| Before | Instruction | After |
|---|---|---|
| fear-passed on, open ground | `ChargeForward` | charging, fear-passed **off**, cond true |
| terror-causing enemy straight ahead | `ChargeForward` | charge starts (no test), no event to the enemy |
| inside a `0xB0` region | `ChargeForward` | halted + re-form, fear-passed unchanged, cond false |

## 4. `CheckCollisions` 0xC7

Public: `movement_formation.md` §3.10. Settled here:

- Probe mode only skips the **engagement** of an overlapping enemy (no contact handler, so **no event 0x0B**, no grid,
  no 0x07). Everything else of the collision pass runs:
  - friendly and scenery push-apart, edge repel;
  - event **0x27** to the unit itself when an `INVSOLID` footprint is straight ahead (within ±45°, i.e. bearing
    difference < 64/512) — this also makes the condition true;
  - **the fear-on-contact test does run** (resolves the 🟡): against an overlapping enemy unit (not leaving the battle),
    if the unit is not broken and fear-passed is off and `MayEngage` refuses → current target := that enemy and event
    **0x0D** queued to the unit (no meaningful source);
  - 🟡 the automatic contact attacks against/by a routing unit (`game_rules.md` §7.7) appear to run in probe mode too.
- Condition: true if anything was pushed, touched (an enemy footprint corner inside the box) or 0x27 raised; false
  otherwise, and then the one-tick contact latch is cleared.

| Before | Instruction | After |
|---|---|---|
| overlapping a terror-causing enemy E, fear-passed off | `CheckCollisions` | target E, 0x0D queued, cond true, no engagement, no 0x0B |
| same, fear-passed on | `CheckCollisions` | no test; cond true |
| `INVSOLID` object 40° to the right, overlapping | `CheckCollisions` | 0x27 queued to self, cond true |

Script 166 runs it every 20 ticks after `HaltAndReform` until false, then `Restart`. In the 11 mission handlers of
§2.2, event 0x27 leads straight to 166.

## 5. `SwitchOpponentInGrid` 0x55

`movement_formation.md` §7 verified as written. Restated by state:

- Only when the unit is **in melee**; otherwise nothing, and the **condition is not written**.
- Picks the **first unit in table order** that is live, is not the current target, is on a grid **and** on this unit's
  grid, is on the other side (allies count with the player), and is not a furniture pseudo-unit. No distance, score,
  broken or fear check.
- Found: the unit's models paired with models of the old target are unpaired (those still standing in a cell become
  reserves), attack direction := 0, the unit leaves "grid owner pairing" mode (joiner pairing), **current target (=
  engaged enemy, one slot) := the new unit**, condition true. No event, no fear test, no move. The per-tick pairing
  re-pairs everyone afterwards.
- Not found: nothing, condition false.
- 🟡 Edge: in melee with **no** current target and a candidate present, the original faults (it reads the old target
  while unpairing). An engine should simply skip the unpairing.

Shipped: library 152 and 155 on event 0x0A (`IfEngagedWithKind 128; If SwitchOpponentInGrid; EndIf; SwitchScript 165`
— in 155 wrapped in `IfCasting 0 0; IfNot`), BF010/BF011 handlers and the BF021 watchdog (`movement_formation.md` §9).

| Before | Instruction | After |
|---|---|---|
| A in melee, target building F; enemy units C (table slot 5) and D (slot 3) on the grid | `SwitchOpponentInGrid` | target D (first in table), cond true |
| A in melee, target F, only A and F on the grid | `SwitchOpponentInGrid` | cond false |
| A not in melee, cond true | `SwitchOpponentInGrid` | cond still true |
| A in melee with B; C broken but still on the grid | `SwitchOpponentInGrid` | target C (broken not excluded) |

---

## 6. Worked example — library 155 (wizard handler), events 0x0A and 0x07

Player Wizard W, handler 103 → gosub 155 for unhandled codes. 103's frame: `GetEvent; CaseEvent …; GosubScript 155;
ConsumeEvent; LoopIfTrue; ReturnInterrupt`.

**Event 0x0A (engaged).** W walked into an enemy watchtower F (a building) and the contact handler engaged it
(target F, in melee, 0x0A queued). Next step: pre-emptive dispatch → 103 → no case 10 → 155:
1. `IfCasting 0 0`: W has no spell pending and is not in the cast pose → false → `IfNot` taken.
2. `IfEngagedWithKind 128`: in melee, target F is a building → true.
3. `SwitchOpponentInGrid`: an enemy regiment R already fighting at F is on the same grid → target := R, W's models
   that faced F are unpaired, cond true.
4. `SwitchScript 165` (deferred) → `Break` → `ReturnGosub` → `ConsumeEvent` (queue empty → false) →
   `ReturnInterrupt` applies the switch: W runs 165 (idle `Yield` loop); the grid pairing now pairs W's models with R's.
   Had W been casting at step 1, nothing would happen: W keeps casting at F's grid (no switch to 165).

**Event 0x07 (charged).** Enemy cavalry K (causes no fear) starts a charge at W (`ChargeTarget` sends 0x07, source
K). W is idle with no target and no spell pending.
1. `StoreEventInfo`: remembered event := (K, 0x07).
2. `FearWhenCharged`: K charging, W not broken, not casting → target := K; fear-passed off; no fear applies → allowed;
   W not charging, not in melee → cond true.
3. `IfSwitchScript 161` → pending switch 161. `Break`, back in 103: `ConsumeEvent` → queue empty → handler ends,
   switch applied.
4. 161: `Query 7` → not braced, remembered code 0x07 → target K, braced, code cleared; `HaltAndReform`; then
   `FaceModelsToTarget` each tick. While braced, W ignores move/attack/charge/fire orders (`game_rules.md` "Braced")
   until e.g. an attack event is accepted by `TakeEventTarget` (which clears braced).

Variant: K is a **terror** monster. Step 2 also queues 0x0D (cond still true), step 3 records 161, but `ConsumeEvent`
now sees a queued event → `LoopIfTrue` → `GetEvent` 0x0D → 103 → 155 case 13: `RoutAllowed` true → `React 6`
("Flee the abomination!") → `SwitchScript 162` **overwrites** 161 → W flees from its target K (script 162,
`FleeFromTarget`). With `CantBreak`, `RoutAllowed` is false, 161 stands and W braces.

Variant: W has a spell pending (busy casting): `FearWhenCharged` does nothing (cond false), no brace; W keeps casting
and meets K's charge unbraced.

---

## 🟡 Uncertainties

- Which UI action produces events 0x28/0x29/0x2A/0x2E/0x2F (a wizard order with no spell chosen); and the panel mode
  in which a 0x2B point is snapped to the clicked unit's position.
- The 0x0D record's source (first unit of the table) — harmless for shipped handlers.
- Fleeing from an existing non-charger target after a failed `FearWhenCharged` (follows from the rules; not observed).
- Contact attacks in `CheckCollisions` probe mode.
- `SwitchOpponentInGrid` with no current target (fault in the original).
