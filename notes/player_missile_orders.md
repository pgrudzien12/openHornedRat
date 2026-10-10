# Player missile orders vs. running unit scripts (fire loop, move/halt, crossbow line of fire, order targets)

Public implementation report (behaviour only), answering the implementer's request about Mercenary Crossbows in
BF001: Fire orders that seem ignored, Fire that keeps running after a Move order, and a Fire order that names a
friendly unit. Companions, cited rather than repeated: `script_shooting.md` (fire loops 107–124, events 30–37,
volley → projectile), `target_queries.md` §3 (`TargetValid`), `unit_script_control.md` (one condition word, the
start-of-tick order check), `reform_while_moving.md` §4 (orders during a re-form), `attack_order_flow.md`,
`ranged_combat_handoff.md` §1, `spell_lasting_effects.md` §0.1 ("the unit under the point"), `game_rules.md`
"Player orders" and §8.

## 0. Shared state (read this first)

| state | meaning here |
|---|---|
| **pending player order** | one per unit. A panel order for the selected units **replaces** it. It is examined at the start of every tick of that unit, before any script word runs (`unit_script_control.md`). After examination it is cleared, except a Move, Face-point or Charge that is **held** while the unit is re-forming (`reform_while_moving.md` §4), which stays and is examined again next tick. |
| **order gate** | while the unit is **charging, in melee, broken, pursuing or braced**, every order except Withdraw, Rally, Magic, Halt, Independent and Fight harder is dropped silently (`game_rules.md` "Player orders"). This includes Move, Attack, Turn, Ranks, Charge and **Fire**. |
| **"order applied" restart** | for some orders (table §1.1) the start-of-tick check ends with **target := none** (the **braced** state is cleared too), then a full `Restart`: the script stack is reset, **every queued event of the unit is discarded**, and execution continues at the unit's **restart point**. This is the same restart point that `Restart` uses (the last `SetRestartPoint`, or `InitUnit`'s). For a player unit on the library (BF001 `PLAYER_SCRIPT` 100) it is script 100's idle loop (`SetRestartPoint; PushPC; SetWait 100; Wait; Yield; Loop`). |
| **current target** | the one shared target slot (`script_shooting.md` §0). |
| **target point** | the ground/building point of a fire order. **Not** reset by the restart above or by any order. |
| **keep-firing state** | the state that `SetUnitFlags2 4` / `ClearUnitFlags2 4` / `TestUnitFlags2 4` read and write (script operand bit 4, this state only). Fire loops 107/108/109/113/114 set it at their start and loop while it is set. The state is cleared by `ClearUnitFlags2 4` and by the game's **halt-and-re-form** step. That step runs for a Halt order, for a Move to the point where the unit already stands, for a Move refused by an anchored or held unit, and when a Fire order (or a held Move) halts a moving shooter. **Nothing else in the game clears it**. In particular a target that cannot be shot does not clear it (§4). |

## 1. Q1: orders given while the unit runs a fire loop (or any other script)

A Move order (or any order) is **not an event**: it never goes through the interrupt script. It is applied by the
game at the start of the unit's tick, and the only things that touch the script are the "order applied" restart
(§0) and the events that some orders queue.

### 1.1 Per order (unit not charging/in melee/broken/pursuing/braced; otherwise see the gate)

| Order | Applied by the game | Script consequence | Target | Keep-firing state |
|---|---|---|---|---|
| **Move (1)**, accepted | route planned, the unit walks | **"order applied" restart** → idle loop; queued events discarded | **none** | left as it was, but no loop reads it any more (harmless: the next fire loop sets it again) |
| Move to where the unit already stands | halt-and-re-form | **restart** (counts as applied) | none | cleared |
| Move while **re-forming** | held, `React 13` once | no change **until** the held Move is applied (the loop keeps running and may fire meanwhile); then restart as above | none from then on | as above |
| Move refused (anchored war machine, or held by Tangling Thorn), not re-forming | `React 14`, halt-and-re-form | no restart; the loop sees the cleared state on its next pass → `ClearUnitFlags2 4; Restart` | **kept** | cleared |
| Ctrl-Move (2, add waypoint) | waypoint appended | **no restart** 🟡 (whether the waypoint starts a walk while the fire loop runs was not traced) | kept | kept |
| **Attack (3)** | event **0x04** queued (target search §5) | handler 104: `TakeEventTarget; IfSwitchScriptHigh 105` → approach script replaces the loop | := attacked unit | kept (no reader) |
| Face point (0x0B), turn left/right/about (0x0C–0x0E) | the turn | **restart** (counts as applied even when the turn itself is refused). A held Face point waits for the re-form like Move | none | kept (no reader) |
| Ranks up/down (0x0F/0x10) | re-form with ±1 rank | **no restart**: the fire loop keeps running | kept | kept |
| Charge (0x15) | event **0x06** (held while re-forming) | handler 104 case 6: `SwitchScript 106` (charge forward); 106 ends in 163 → `Restart` | kept until 163 | kept (no reader) |
| **Halt (0x19)** (passes the gate) | halt-and-re-form, `React 19` ("Hold!") | **no restart**, but the halt clears the keep-firing state → on 108's next pass `TestUnitFlags2 4` is false → `ClearUnitFlags2 4; Restart` | **kept** (the opcode `Restart` does not drop the target) | cleared |
| Fire (0x16) | event 30–33/36/37 (§5); a moving shooter is halted | handler 156 → `IfSwitchScriptHigh` 107/108/109/113/114 (always restarts the loop from its start) or 110 | := clicked unit / point | set again by the loop |

So **a Move order ends the fire loop and forgets the target**, and the unit does **not** fire on arrival. It stands
idle at its restart point. From then on it shoots only through the threat reaction (§2) or a new Fire order.
**Halt also ends the loop** (one tick later), but keeps the target slot. Turns end it. Ranks do **not** end it.

**Held orders.** A held order applied after the re-form takes the same path as the same order given at that moment.
For Move or Face point that is the "order applied" restart, to the unit's **restart point** (for library player units:
script 100's idle loop, not the start of script 100). For Charge it is event 0x06.

**Arrows in the pipeline.** The restart discards events 34/35 that were already queued. Shoot poses that are still
running may post more events 34 after the restart 🟡 (the animation request is not cleared by the order). These
are still handled (`FireAtTarget` via handler 156). With the target gone they launch **nothing**, unless an old
**target point** is still set (an earlier ground fire): then the arrow goes to that stale point
(`script_shooting.md` §1.3).

### 1.2 Test vectors (BF001 crossbows X, library scripts, enemy T in arc and range, X reloaded)

| before | action | after |
|---|---|---|
| X in 108 (keep-firing on), target T, not re-forming | player Move to P (accepted) | next tick, before any script word: target none, queue emptied, PC at script 100's idle loop; X walks to P; on arrival **no volley** |
| same, an event 34 from model 2 queued last tick | same | that event is discarded: no arrow |
| X in 108, re-forming after an earlier order | player Move to P | `React 13`; the order is held; 108 keeps running (may volley); the tick the re-form ends: restart as above |
| X in 108 | player Halt | halt + re-form, `React 19`; next pass of 108: `TestUnitFlags2 4` false → `ClearUnitFlags2 4; Restart` → idle; target slot still T; no further volleys |
| X in 108 | Ranks up | X re-forms with one more rank; 108 keeps looping and volleys when ready, in arc, in range and `TargetValid` |
| X in 108 | Turn about | restart, target none, idle |
| X in 108 | Attack on enemy E | event 0x04 → 105 (approach E), target E |
| X in melee | Move, Fire, Turn, Ranks | dropped silently (gate) |

## 2. Q2: does an idle player missile unit fire on its own?

No auto-targeting (`script_shooting.md` §5.1, unchanged). An idle player unit shoots only:

- after a **Fire** order; or
- through the **threat reaction**. Behaviour 11/12 (every 30 ticks) queues event 3 when an enemy closer than 240
  (octagonal) is attacking this unit. An **independent** unit reacts to any enemy in its threat slot, and re-picks
  its best threat when none attacks it. The Archers handler 104 then runs `ReactToThreat` and, on success,
  script 126: quarter-turn, then loop 124 (independent and neither anchored nor held: 122, which re-targets and
  approaches), **while `BrokenTargetInRange`**, then `Restart`.

## 3. Q3: crossbow line-of-fire refusal (`TargetValid`), exact geometry

Refines `target_queries.md` §3 item 2. Only **missile code 2 (crossbow)** runs this test; bows, artillery and every
other weapon skip it. The independent-unit "friend near the aim point" test (§3 item 1) is separate and unchanged.

**Aim point A**: the target unit's centre, or the target point when there is no target unit (or aim-at-point is on).
So Fire at a **building** or on the **ground** uses the same test towards that point.

**Line length** `L = trunc(distance(shooter centre, A))`.

**Candidates**: every **active** map footprint of a **regiment** (any unit's footprint: infantry, cavalry, monsters,
war machines, routing units, the shooter, the target), plus scenery objects flagged **camera-collide** in the battle
file 🟡 (only BF016 has them, 5 objects; their owner side is undefined, so an engine may ignore them). Building and
furniture footprints and ordinary solid scenery are **not** candidates here. Scenery only adds scatter at launch,
`game_rules.md` §8.3.

For each candidate O (centre `(ox, oy)`, footprint radius `r`, the same radius as for collisions):

```
d   = trunc(distance(shooter centre, O centre))
skip unless d < L                                   # strict: O's centre must be nearer than the aim point
skip if r > d                                       # the shooter stands inside O's circle → never blocks
hw  = trunc(asin(r / d) × 256 / π)                   # angular half-width, 512 units per turn
b(P) = trunc(256 − 256 × atan2(Px − sx, sy − Py) / π)  # bearing, 0 = +Y, clockwise; truncation, not rounding
Δ   = (b(A) − b(O)) mod 512;  Δ = min(Δ, 512 − Δ)
O is "on the line" if Δ < hw                        # strict
```

The shot is **refused** (`TargetValid` false) as soon as an "on the line" candidate is **not hostile** to the
shooter. Hostile means one of the two is the player army or allied and the other is the enemy army. So a friend, an
allied unit or a neutral one blocks; an **enemy** standing in front of the target does **not** block (the bolt may
hit it, `ranged_combat_handoff.md` §3). Consequences:

- **The target itself never blocks** (its centre is at distance L, not < L). The shooter never blocks itself (d = 0).
- **Units beyond the aim point never block**, even if they overlap the line near the target. **Units behind the
  shooter never block** (Δ ≈ 256).
- **A friend locked in melee with the target on the shooter's side blocks almost always.** Its centre is a little
  nearer than the target's, and only a few units off the line. This is the original's behaviour, so the
  "Fire ignored" symptom with cavalry fighting the Clanrats is **faithful**. A friend on the far side of the target
  does not block.
- `Δ < hw` with `hw = asin(r/d)` is, up to truncation, "the perpendicular distance from O's centre to the line is
  less than r". The implementer's provisional "centre within r of the segment" is right in spirit. The differences:
  the far end is cut at the **aim point's distance** (not "segment to the target centre plus radius"), objects
  behind are excluded, and the integer truncations below apply.
- **Truncation asymmetry.** Bearings are truncated, not rounded, so an object just left of the line
  (bearing ≈ 511.x) gets a Δ one larger than its mirror image on the right. See the vectors.
- Edge: `r = d` (the shooter touching O's rim) gives hw = 128, i.e. anything in a ±90° half-plane ahead blocks.

### 3.1 Test vectors (shooter centre (0, 0), aim point A = (0, 350), so L = 350 and b(A) = 0; O radius 30, friendly)

| O centre | d | hw | b(O) | Δ | result |
|---|---|---|---|---|---|
| (5, 300) (friend in melee, near side) | 300 | 8 | 1 | 1 | **refused** |
| (28, 300) | 301 | 8 | 7 | 7 | refused |
| (−28, 300) | 301 | 8 | 504 | 8 | **not** blocked (truncation asymmetry) |
| (31, 300) | 301 | 8 | 8 | 8 | not blocked (strict) |
| (40, 300) | 302 | 8 | 10 | 10 | not blocked |
| (5, 349) | 349 | 7 | 1 | 1 | refused (349 < 350) |
| (5, 360) (friend on the far side) | 360 | – | – | – | not a candidate (d ≥ L) |
| (0, −100) (behind) | 100 | 24 | 256 | 256 | not blocked |
| (0, 20) (shooter inside O's circle) | 20 | – | – | – | never blocks |
| (0, 30) (shooter on O's rim) | 30 | 128 | 0 | 0 | refused |
| (5, 300) but O is an **enemy** unit | | | | | not blocked (only non-hostile units refuse) |
| any, shooter has a **bow** | | | | | test not run: `TargetValid` true (if not independent) |

## 4. Q4: feedback and retrying when `TargetValid` refuses

- **Silent.** No message, no speech. The only speech of the fire order is `React 13` at the start of 108
  ("Yes my lord"), and the targeting text `GMTXT 2008` (§5) when the order is given. `ReadyToFire 0` and
  `InArcAndRange 0` in 124 are also silent (operand 0).
- **Retries every tick, indefinitely.** Each pass of 108 is `Yield` → 124. With the unit reloaded, in arc and range
  and the line blocked, 116's `TargetValid` is false, nothing is stamped (`StampReload` is only in 115, so the
  reload is **not** consumed), and the next tick tests again. The first tick the line is clear, the volley goes.
- 108 never ends by itself: there is no `BrokenTargetInRange` in 108/124. It ends on the §1 orders, on a script
  switch by an event (target removed → event 0x19 → 163, charge, rout, …), or on a halt-and-re-form.
- While waiting out of arc but in range, 124 turns to face (`TurnToFaceTarget`, then waits until halted) unless
  the unit is anchored or held. Out of range it simply does nothing (player loop 108 never approaches; only the
  independent hunt loops 113/114 do).

## 5. Q5, Q7, Q8: which unit an Attack or Fire click names

In the main view the order carries the **ground point under the cursor**, not a figure. The unit is chosen from that
point by the game when the order is applied. There is no figure or outline hit-testing for orders.

**Attack (3)**: "the unit under the point" (`spell_lasting_effects.md` §0.1: nearest **reference figure**,
`d < max(footprint radius, 48)` strict, ties to the earlier unit), but **only among units of the enemy army**. Allied
units are never candidates either. So in a melee scrum Attack **prefers the enemy**: friendly figures under the
cursor are simply not candidates. Then:

- the nearest enemy candidate is **hidden**, **marked** (the `SetUnitFlags 256` state, `script_queries.md`) or
  `CantMelee` → the order fails. There is **no fallback** to the next-nearest enemy.
- no enemy candidate (or it failed) → the same search among **building/furniture** pseudo-units (side neutral) whose
  footprint is not destroyed → event 0x04 on the building.
- nothing found → the order is **dropped silently** (no message, no speech). An anchored or held unit drops every
  Attack order the same way.
- **Q8: Attack on a friendly unit** therefore never names it. If the click is near only friends, nothing happens;
  if an enemy reference figure is within its radius (min 48) of the point, that enemy is attacked. No feedback text.

**Fire (0x16)**: the **first** footprint whose centre is within `max(footprint radius, 48)` (strict, squared
distance) of the point, among **all sides**: regiments of any kind (fliers and war machines included) and buildings.
It is **not** the nearest one, and there is **no hostility test**. "First" is the original's internal order of
footprints, 🟡 not specified: an engine may use unit-list order. Then:

| hit | event | text (`GMTXT`) |
|---|---|---|
| a building footprint | 30 (37 for an independent Archers unit) | 2007 "have targeted the building" |
| the shooter itself | 32 "search" (36 for an independent Archers unit) | 2009 "searching for a target" (2017 "moving to search" for independent Archers) |
| any other unit, **including a friendly, allied or neutral one, also in melee** | 31 (37 independent Archers) | 2008 "have targeted the regiment" |
| nothing | 33 ground point | – |

**Q5: a friendly Fire target is accepted.** The crossbows then shoot at it (your symptom 3 is faithful). It can even
be picked when an enemy overlaps the same point, because the first footprint in order wins. There is no refusal and
no feedback text for it (`ranged_combat_handoff.md` §1 already lists "enemy, friendly or neutral"). An engine that
prefers hostile units here is **deliberately deviating**. That is fine as a usability choice, but tag it as a
deviation.

**Minimap**: for Fire, and for the Attack search when the game is in minimap mode, the minimap pick runs first.
Among the candidates (Fire: all sides; Attack: the enemy army) it takes a unit whose minimap marker lies within a
small box at the cursor 🟡 (about ±8 px horizontally, up to about 24 px above the marker). **Repeated clicks on the
same minimap pixel cycle** to the next unit, ordered by distance. Fire then aims at that unit's centre (and resolves
the footprint there again, as above). If the minimap finds nothing, Attack falls back to the main-view search.

Already public, unchanged: picked targets in melee are allowed. A moving shooter is halted only when the Fire event
was queued.

## 6. Q6: `If`/`IfNot`/`Else` nesting

Confirmed: a false `If` (or a true `IfNot`) scans forward **counting depth**. Each `If`/`IfNot` adds 1, each `EndIf`
subtracts 1, and an `Else` ends the scan **only at depth 1** (its own level). The scan stops at the `EndIf` that
brings the depth to 0, and execution continues after the `Else` or `EndIf` it stopped on. It never runs past the end
word `0x80E8` (`skip_if_true.md`). `Else` reached while executing (the true branch) skips forward to its own `EndIf`
the same way. So in 124 a not-ready unit skips the whole body to the outer `EndIf`.

## 7. Differences from the implementer's engine model

1. **Move is not an event, and it restarts the script** at the restart point, drops the target and empties the
   event queue (engine: only engine fields were cleared, and 108 kept running → shots on arrival).
2. Halt ends the fire loop one tick later through the keep-firing state, but **keeps** the target slot. Turns
   restart like Move. Ranks and Ctrl-Move do not touch the loop.
3. Held Move/Face point while re-forming: the loop continues until the order is applied.
4. Crossbow refusal: far end cut at the aim point's distance (strict), units behind excluded, enemies never block,
   truncated bearings (asymmetric), `asin(r/d)` half-width, a shooter inside a footprint is not blocked by it.
5. Attack considers enemy-army units only (nearest reference figure); Fire takes the first footprint of any side.
   Picking uses the ground point, not figures.

## 8. Corrections to other public notes

- `script_grid_events.md` event table: "0x1E / 0x1F … shoot order clicked on a building / **an enemy unit**" →
  "**any other unit**, of any side" (corrected there).
- `target_queries.md` §3 item 2 is refined by §3 here (which footprints, far-end cut, truncation).

## 🟡 Open

- Whether shoot poses already running at a Move order keep posting events 34 (if they do: no arrow, except to a
  stale target point).
- Ctrl-Move (add waypoint) during a fire loop: whether it starts a walk.
- The original's order among overlapping footprints for Fire; the camera-collide scenery owner in the crossbow test.
- Exact minimap box.
