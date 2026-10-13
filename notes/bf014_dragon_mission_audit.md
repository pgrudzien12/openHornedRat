# BF014 "Escort Engrol Goldtongue": dragon breath and orc ambush, audit against the engine

Public behavioural report (behaviour only, no implementation details of the original). It re-checks
everything the public notes say about the BF014 Dragon and the four Orc regiments and compares it with the
engine's behaviour in a recorded play-through (`logs/battle-…-bf014.jsonl`, local only). Companion reports
(cited, not repeated): [script_behaviours.md](script_behaviours.md) §1.9 (behaviour 21), [script_shooting.md](script_shooting.md)
§0 and §3 (`ReadyToFire`, `FireAtNode`, the 154 → 110 → 115 path), [threat_events_nodes.md](threat_events_nodes.md)
Part A §4 (`AttackNearestMainEnemy`) and Part C (node areas), [unit_script_control.md](unit_script_control.md) §3 (d)
(`Restart` and the stack), [spell_effects.md](spell_effects.md) §2 and §3.4 (Fireball flight), [bf003_playtest_fireball_grid_pursuit.md](bf003_playtest_fireball_grid_pursuit.md)
§2 and §8 (Fireball visuals), [bf014_dragon_rendering.md](bf014_dragon_rendering.md) (mesh poses, sectors, origins),
[script_grid_events.md](script_grid_events.md) §2 (`FearWhenCharged` → 161), [game_rules.md](game_rules.md)
"Routes, collisions and visibility", "Special weapons", "Reload time".

**Summary of findings**

| # | Topic | Public notes | Engine (recorded run) | Verdict |
|---|---|---|---|---|
| 1 | `Restart` restores the stack depth saved by `SetRestartPoint` and discards the unit's queued events | stated (`unit_script_control.md` §3 (d), `player_missile_orders.md`) | neither is done | **engine bug**: the dragon's five-node breath cycle gets stuck on its last block (§2) |
| 2 | Flames per breath | D6+3 | D6+3 | ✅ |
| 3 | Spread of each flame around the aim point | "around the target" (unspecified) | ±24 per axis | **new fact**: −40…+39 per axis (§3.1) |
| 4 | Flame flight | each flame is a Fireball effect: 18 ticks, scattered, trail + explosion | 9 ticks, no scatter | **engine deviation**: flights twice as long in the original, so about twice as many trails are on screen at once (§3.2) |
| 5 | When the dragon breathes | §1.9 + script 7 | follows the scripts | ✅ in principle. Needs a unit (any side) in two trigger circles, or a non-allied unit within 120 in its front arc. With only Gotrek fighting it, the original dragon idles too (§1) |
| 6 | A looker standing **outside** the `SightEdge` area | not described | treated as blind (every ray crosses the edge) | **new fact**: it looks from the nearest point of the edge (§4). The BF014 orcs start outside it, so in the engine they never reveal the hidden player army and never find a target |
| 7 | `SightEdge` part of the visibility test | "the line must not cross a `SightEdge`" | tested on all three sample rays | **refined**: one line between the two regiment positions (§4.2) |

---

## 1. What the BF014 scripts make the dragon do (shipped data, unchanged from earlier reports)

Units and nodes (`BF014.BTS`; node numbers are **0-based file positions**, `threat_events_nodes.md` Part C §1):

| Item | Data |
|---|---|
| Dragon | enemy army, (1120, 600), facing 384 (−X), one model, `S_BalWeap` 14 (breath), I 20, BS 6, script 0 |
| Gotrek | allied side, (884, 367), script 1: `AttackTagged 0xabc0` (the dragon) every 10 ticks |
| Orcs | four **hidden** enemy regiments at y ≈ 1836 (x 172, 429, 603, 1089), scripts 2–5 |
| Player | `BF014.MRC`: every player regiment is `hidden:`; start nodes 0–16 at y 85–320 |
| Breath targets | nodes 17 (986, 609), 18 (1000, 509), 19 (979, 719), 20 (947, 672), 21 (947, 542): 134–187 from the dragon, all in its ±45° front arc |
| Trigger circles | node 22 (945, 485) r 175 ("north approach"), node 24 (945, 720) r 175 ("south approach"), node 23 (408, 802) r 37 (a small circle far to the west), node 25 (732, 1253) r 307 (the orcs' trigger) |

**Script 0** (dragon): threat range 120, interrupt 10, **behaviour 21 every 24 ticks**, `ExcludeFromArmy`, then forever
`PlaySoundAtUnit 12 0; Yield; GosubScript 7`.

**Script 7** (the node cycle), five blocks. Each block: `SetWait 5; Wait; ReadyToFire 0` (repeat until ready), then a
`FireAtNode n` guarded by the trigger circles, then `SetRestartPoint`, `SetActionState 4` if in melee, `SetWait N; Wait`.

| Block | Fires at node | Fires when | Wait after (N) |
|---|---|---|---|
| 1 | 17 | any unit in 22 or 24 | 35 |
| 2 | 18 | nobody in 23, and any unit in 22 or 24 | 50 |
| 3 | 19 | nobody in 23, and any unit in 22 or 24 | 40 |
| 4 | 20 | any unit in 22 or 24 | 20 |
| 5 | 21 | nobody in 23, and any unit in 22 or 24 | 55 |

`IfAnyUnitInNodeArea` counts **every unit of every side, hidden or not, including the dragon itself** (the dragon is
outside all four circles). Gotrek starts inside node 22, so the dragon starts breathing at once.

**Reload.** The dragon's reload is `(10 − min(I, 10)) × 18 = 0` (I 20, code 14 has no reduction): `ReadyToFire` is
true on any tick after the stamp, except when the battle clock did not advance (`script_shooting.md` §0: the last
tick of a segment and the first of the next share the same clock value). The reload never limits the dragon.

**From `FireAtNode` to flames.** The node is queued as ground-fire event 33. On the next tick, interrupt 10 has no
case for it, so it falls to library 154. There `TakeRangedEventTarget` runs, then 110 (`ReadyToFire 1`;
`InArcAndRange 1`: front ±45°, range 576 strict; else `React 14`), then 115 (`StampReload`, special shooter →
`ClearEvent; FireAtTarget` → the breath routine). The handler always ends with **`Restart`**, whether or not it
breathed. The main script then continues at the restart point set right after the `FireAtNode` block that queued
the event.

**Behaviour 21** queues the same event 33 at the nearest **player- or enemy-army** unit (allies excluded, hidden
units included) whose octagonal distance is < 120. It runs every 24 ticks, with no arc or visibility test of its
own (`script_behaviours.md` §1.9).

### 1.1 Expected rhythm in the original

- **Node cycle only** (somebody in 22 or 24, nobody within 120 in front): one breath about N + 6 ticks after the
  previous one, i.e. about **41, 56, 46, 26, 61** ticks between breaths, in node order 17 → 18 → 19 → 20 → 21 → 17…
  (about 23 s for five breaths, one every ~4.6 s). Anybody in node 23 suppresses blocks 2, 3 and 5: then only nodes
  17 and 20 are fired, about every 41 + … ticks.
- **Behaviour 21 adds breaths at the intruder** every 24 ticks while a non-allied unit is within 120 **and** in the
  dragon's ±45° front arc.
- **Quirk: every behaviour-21 event restarts the node cycle.** The handler ends with `Restart` even when 110
  refuses the shot (out of arc). The main script then goes back to the wait after the last block that fired.
  That wait is 35, 50, 40 or 55 ticks, longer than the 24-tick behaviour period, so it never finishes.
  - **While a non-allied unit stays within 120** of the dragon, the node cycle stops at its current block. If that
    unit is in the front arc, the dragon breathes at it every 24 ticks instead. If it is beside or behind the dragon
    (out of arc), the dragon **does not breathe at all**.
  - The only exception is the 20-tick wait after block 4: it can finish, so block 5 may still fire once.
- **Gotrek alone.** Gotrek charges the dragon. The charge (event 7) puts the dragon into library 161 (brace, face the
  charger). Engagement (event 10) sends it back to script 6, which runs the node cycle again
  (`script_grid_events.md` §2.3). A joining charger's reference point stops where contact was made
  (`game_rules.md` "Why the charger disperses…"). For Gotrek, coming from the north-west, that is roughly 20 units
  from the dragon's centre, outside node 22 (d² ≈ 35 800 > 30 625). So **in the original too, the dragon stops
  breathing once Gotrek is in melee and no other unit is in node 22 or 24.** 🟡 The exact contact distance depends
  on the footprints. The engine puts Gotrek about 11 units from the dragon, which gives the same result.

So the user's observation "no fireballs when none of my units are near" matches the original. The reduced frequency
when units *are* near is the engine bug of §2.

## 2. Engine bug: `Restart` keeps the stack (and the queued events)

`unit_script_control.md` §3 (d): `SetRestartPoint` stores the script, the next instruction **and the current stack
depth**. `Restart` sets the stack back to that depth, **discards every queued event of the unit**, and continues at
the restart point. The engine's `Restart` only changes the script and position.

Why this matters in BF014. The node cycle runs inside `GosubScript 7` and keeps `PushPC` words on the stack. Each
breath restarts from inside the interrupt, so the extra words are never removed. When block 5's wait ends,
`ReturnGosub` pops a stale `PushPC` word instead of the return into script 6. Execution falls back into block 5,
which fires at node 21 again. The recorded run shows this: nodes 19 → 20 → 21 → 21 → 20 → 21 → 21 … with gaps of
24–59 ticks and long silent stretches, instead of 17 → 18 → 19 → 20 → 21 → 17.

Test vector (any unit, stack shown as words):

| Before | Instruction | After |
|---|---|---|
| main script 7 pc 88, stack [s6 `PushPC`, s6 return, s7 `PushPC`] (depth 3) | `SetRestartPoint` | restart point = (7, 89, depth 3) |
| later: stack [s6 `PushPC`, s6 return, s7 `PushPC`, s7 `PushPC`] (depth 4), queue [ev 3, ev 33], running the interrupt | `Restart` | script 7 pc 89, stack [s6 `PushPC`, s6 return, s7 `PushPC`] (depth 3), queue [] |

## 3. The breath itself

### 3.1 Per breath (special weapon 14)

1. Draw the flame count **first**: `n = (rand mod 6) + 4` (4–9). The draw is made even when the next step rejects
   the breath.
2. Arc and sector test, pose and flame origin: `bf014_dragon_rendering.md` §3.1–3.2 (unchanged).
3. For each of the n flames: `ay = aim_y + (rand mod 80) − 40`, then `ax = aim_x + (rand mod 80) − 40`. Note the
   draw order, **y first**. The spread is **−40…+39** on each axis, not ±24 (±24 is the warpfire thrower's,
   weapon 15).
4. Launch one innate **Fireball effect** (spell effect 10) from the dragon at (ax, ay). Its start is moved to the
   sector origin, 72 units out (`bf014_dragon_rendering.md` §3.2). Every flame is a separate effect.

### 3.2 Each flame is an ordinary Fireball effect

Everything in `spell_effects.md` §2 and §3.4 applies, with the dragon's own numbers:

- **Scatter** (§2.2) with the dragon's BS 6 and the Fireball's range 576: `step = trunc(8 × d / 576)`, offset per
  axis `(rand mod 5) × (±1) × step`. At the node distances (134–187) the step is 1–2, so up to ±8 more on top of
  §3.1.
- **Flight: fixed 18 ticks** (the engine uses 9). It is flat: launch elevation 20 and no arc
  (`spell_effects.md` §2.1, `bf014_dragon_rendering.md` §3.2). There is one in-flight test per tick, and the
  flame stops at the first unit, building or solid object it hits. Damage per `game_rules.md` "Special weapons":
  S8, 1 wound, no save, magical, and **every unit hit routs**. Flames also burn Tangling Thorns (§3.4).
- **Visuals per flame**: the Fireball head, its trail of fading puffs and the 9-frame explosion at the end of its
  flight (`bf003_playtest_fireball_grid_pursuit.md` §2, §8.3–8.4). A 7-flame breath therefore shows **7 trails
  and 7 explosions**. Each lasts 18 ticks of flight plus the puff and explosion tails.

Test vectors (dragon (1120, 600), facing 384, aim = node 17 (986, 609), d = 134, step 1):

| Before | Breath | After |
|---|---|---|
| draws: 3 (count), then for flame 1: 0, 79, then scatter draws 4, even, 0, odd | special weapon 14 | 7 flames. Flame 1 aim (986 + 39, 609 − 40) = (1025, 569), then scattered by (+4, 0) → (1029, 569). 18-tick flight |
| aim bearing out of the front half-plane (e.g. facing 384, bearing 256) | special weapon 14 | one draw spent (count), no flame, no pose change |
| `InArcAndRange 1` fails (bearing 64 or more steps off the facing, or distance 576 or more) | library 110 | `React 14`, **no** breath; the handler still ends with `Restart` (§1.1 quirk) |

## 4. Visibility when the looker stands outside the `SightEdge` area (new)

### 4.1 Rule

The `SightEdge` part of the visibility test (`game_rules.md` "Routes, collisions and visibility") is made **from
the looker's regiment position to the target's regiment position**. If the looker's position lies **outside** the
`SightEdge` area:

1. find the nearest point P on the `SightEdge` boundary lines;
2. move the start **inward past the edge**: `start = P + 1.1 × (P − looker)`, i.e. 1.1 times the looker's
   distance outside, measured from the edge;
3. test the line from that start to the target's regiment position. Visible if it crosses no `SightEdge` line.

The target is **not** moved. A target outside the area is therefore not visible from inside: the line crosses the
edge. The view cone and the scenery sample rays are unchanged. They are taken from the looker's own position, and
the scenery rays are the only ones spread across the target's footprint.

### 4.2 Consequences in BF014

- The orcs stand at y 1836–1837, just below the `SightEdge` line y = 1832. With the rule, each orc looks from about
  y 1827.6 and sees normally into the field ahead (orc facings 212–292, cone ±50°). Their periodic behaviour 15
  (every 29–33 ticks) therefore **reveals hidden player units** in their cone and line of sight
  (`script_behaviours.md` §1.0 spotting; the spotter's own hidden state is not tested).
- The engine treats the orcs as blind, so player units stay hidden. `AttackNearestMainEnemy` /
  `AttackNearestVisibleMainEnemy` skip hidden candidates (`threat_events_nodes.md` Part A §4.1). The recorded run
  shows the result: Ceridan was inside node 25 from about tick 1045. From then on the orcs ran
  `AttackNearestMainEnemy` every 9–10 ticks and found nothing, because every player regiment was still hidden.
- Conversely, a player unit inside the field cannot spot the orcs while they stand outside the edge. In the engine,
  Ceridan "spotted" the off-field Black Orcs at tick 1021 because a footprint-spread side ray ended inside the area.

Test vectors (BF014 `SightEdge`, bottom line y = 1832 from x 88 to 1272; no scenery in the way):

| Looker (facing) | Target | Result |
|---|---|---|
| orc at (429, 1836), facing 257 | player unit at (845, 1177) | start (429, 1827.6); line inside the area → **visible** (cone: bearing ≈ 210, within ±71 of 257) |
| player unit at (845, 1177), facing 466 (towards the orc) | orc at (429, 1836) | line crosses y = 1832 → **not visible** |
| looker at (60, 1900), facing 200 (outside, nearest edge point the corner (88, 1832)) | (300, 1500) | start = (88, 1832) + 1.1 × (28, −68) = (118.8, 1757.2); test from there |

### 4.3 The orc ambush in the original

1. Behaviour 15 spots revealed player units within the cone; with a threat in range (240) the orc answers by its
   0x03 path (script 9 → 159). This happens only for revealed units within 240, and none are near at the start.
2. Scripts 2–5 poll every 10 ticks: is **any** unit (any side, hidden or not) inside node 25 (732, 1253) r 307?
   No unit starts there.
3. Then every 10 ticks: `AttackNearestMainEnemy` (script 3 first loops `AttackNearestVisibleMainEnemy` until it
   succeeds) picks the nearest **revealed**, unbroken player regiment, anywhere on the field.

So the orcs do march once a unit has entered node 25 and some player unit has been revealed, normally by the orcs'
own spotting. A player who enters node 25 while every regiment is still hidden waits until the next spotting run
reveals one.

## 5. What the implementer should change (summary)

1. `SetRestartPoint` saves the stack depth. `Restart` restores it and discards the unit's queued events (§2).
2. Breath flames: count draw first, spread `(rand mod 80) − 40` (y then x). Each flame is a Fireball effect with
   the standard scatter (BS 6, range 576), an 18-tick flat flight and the full Fireball trail/explosion visual (§3).
3. Visibility: the `SightEdge` test is one line between the regiment positions, from a looker moved inside when it
   stands outside the area (§4).
4. Keep the node-cycle and behaviour-21 interaction as scripted, including the out-of-arc `Restart` quirk (§1.1).
   The dragon idling while only Gotrek fights it is original behaviour.

## 6. Open items

- 🟡 Exact regiment position of a joining charger at contact (it decides whether Gotrek in melee is inside node 22).
  Both engine and estimate give "outside".
- 🟡 Whether a single original breath's flames overlap in screen time with the next breath's (they will at 24-tick
  behaviour-21 intervals: 18 ticks of flight + puff tails).
