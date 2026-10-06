# Unit-script shooting: projectile launch, 90 % range, fire at node, manned artillery

Public implementation report, batch 9 of the interpreter requests (GitHub #3), part 3 of 3 (companions:
`script_grid_events.md`, `script_spawn_move.md`). Behaviour only.

Behavioural report on the four shooting opcodes and on how a volley becomes projectiles. It builds on
`game_rules.md` §8 ("Who shoots, orders and volleys", reload, aim/scatter/flight, misfire, special weapons) and
"Figure animation" (fire tick 2…5, volley countdown), `script_animation_sound.md` §0.3 and §2 (animation request,
`PlayUnitAnimation`/`PlayLeaderAnimation`/`IfAnimationDone`, the 113 → 121 → 116 → 115 walk-through),
`target_queries.md` (arc, range, `TargetValid`, target point), `threat_events_nodes.md` §2 and §6 (`FindTarget`
family, `ReactToThreat`), `script_magic.md` §0 and §4 (target point, aim-at-point, `TakeEventTarget`),
`script_queries.md` (Query cases, `IfMachineDestroyed`, `TargetValid`) and `unit_script_control.md` (one condition
word, `ClearEvent`). Those facts are cited, not repeated.

## 0. Shared state (read this first)

| state | meaning here |
|---|---|
| **current target** | the unit slot shared with melee and magic. Aimed at by `FireAtTarget` unless aim-at-point is on. |
| **target point** | (x, y), "unset" while either coordinate is negative. Written by `TakeEventTarget` for a ground-point event (fire order on the ground, `FireAtNode`), by `SetCastPointNode` and by the spell chooser (`script_magic.md`). **No shooting or magic opcode ever resets it to unset**: once written it stays until overwritten. 🟡 its value at unit creation is assumed unset. |
| **aim at point** | `script_magic.md` §0. `FireAtTarget` reads it and **always clears it**. |
| **forget target after shot** | a unit state set/cleared by scripts with `SetUnitFlags 0x4000000` / `ClearUnitFlags 0x4000000` (operand bit 0x4000000 = this state only). `FireAtTarget` clears the current target at its end when it is on. Library 154/156 clear it on every player fire order (events 30, 31, 32, 36, 37); library 155 sets it before casts (`script_magic.md`); BF017 script 2 (a mission war machine) sets it, so that machine re-selects its target before every shot. |
| **current event** | the event being handled (`unit_script_control.md`). Its **source** field is what `FireAtTarget`/`FireAt90PercentRange` use as the **launching model**. |
| **launching model** | for an animation-posted event 34/35 the source is the **index of the model that posted it** (its position in the unit's model list). A launch from model *i* starts at the unit centre plus that model's current offset from the centre. A launch with "no model" (−1: no current event, e.g. after `ClearEvent`) starts at the unit centre. 🟡 If models died between posting and launch, index *i* may name another model or a slot past the current size; the original does not check. |
| **reload stamp** | the time of the last shot (`game_rules.md` "Reload time"). Written by `StampReload` (0x86) **and again by every projectile launch** (§1.3), i.e. by each arrow of a volley. |
| **projectiles in flight** | at most 32 (`game_rules.md`). At the cap a normal launch fails (§1.3). |

**Reload test, exact** (used by `ReadyToFire` 0x70). With the battle clock of `game_rules.md` ("Battle clock": a
tick counter running 18 → 0, segments 10 → 1, then the turn increases) define
`T = 18 × (10 × turn − segment) − tick`. The unit is reloaded when **`T_now − T_stamp > base`** (strict), `base`
from `game_rules.md` "Reload time". Because a segment has 19 tick values but `T` advances by 18 per segment, the
last tick of one segment and the first tick of the next have the **same** `T`: each segment boundary crossed adds one
real tick to the wait. Example: base 101 (Orc bow I2) → the unit needs 102 increments of `T`, i.e. about 107 real
ticks (102 + one per boundary crossed, ≈ 5–6).

`ReadyToFire msg` (0x70, 2 words; summary, `game_rules.md` order confirmed): false if the unit is **held**
(Tangling Thorn; `game_rules.md`'s "hold-fire bit" is this held state); false if not reloaded (message 2003 only
when `msg` ≠ 0); for **Artillery class**: false if the machine (leader model) is gone (message 2015) or the unit has
**fewer than 2 models** (message 2016) — these two messages are printed **whatever `msg` is**; otherwise true.
Writes the condition in every branch.

`StampReload` (0x86, 1 word): reload stamp := now. Condition not written. Shipped: library 115 and 117 only.

**"Manned"** (shared by `ReadyToFire` and `IfArtilleryManned`): class Artillery, the machine/leader model still
exists, and the unit has **at least 2 models** (the count includes the machine model 🟡; `game_rules.md` says "at
least 2 crew", which is one model stricter if the machine is counted).

## 1. `FireAtTarget` (0x84, 1 word, no operand) — launch one shot now

Shipped: library 111 (event 34 handler), 115 and 117 (special shooters, after `ClearEvent`): 3 per DLL, 135 in all.
Never in mission scripts.

### 1.1 Effect

```
model := source of the current event, or "none" (−1) when there is no current event
if current target exists and aim-at-point is off:
    if Launch(model, target unit's centre) succeeds: condition := true
    else: Launch90(model, target unit's centre); condition := false        # whatever Launch90 did
elif target point is set:
    if Launch(model, point) succeeds: condition := true
    else: Launch90(model, point); condition := false
else:
    condition := false                                                     # nothing launched
aim-at-point := off                                     # always, every branch
if the unit has "forget target after shot": current target := none     # always, every branch
```

- **Immediate.** One shot (or one special-weapon routine) per execution; nothing continues over ticks.
- **No checks of range, arc, reload, line of fire, visibility or the target's state.** All of those are made by the
  script *before* the volley was ordered (`ReadyToFire`, `InArcAndRange`, `TargetValid`). An arrow posted after the
  target moved out of range or arc still flies — at the target's centre **at launch time**, with the scatter that the
  larger distance gives (`game_rules.md` §8.3 scales the scatter by distance / max range; nothing caps the flight).
- The aim is the **target unit's centre**, not a figure.
- The condition is written in every branch, but no shipped script reads it (each use is followed by an instruction
  that rewrites it).

### 1.2 What "Launch" does (one shot)

1. **Special shooters** (missile code 14 breath, 15 warpfire, 17 steam gun — `script_magic.md` §3.7) whose unit is
   **not** of class Archers or Artillery (the Dragon and the Warpfire Thrower are Monster class, one Gyrocopter
   file is Infantry class): run the special routine of `game_rules.md` §8 "Special weapons" at the aim point; counts
   as **success**. No reload stamp, no projectile cap, no misfire.
2. Any other unit that is not Archers/Artillery class: **fails**.
3. Archers/Artillery class with 32 projectiles already in flight: **fails** — 🟡 except that a special-shooter code
   on an Archers/Artillery unit then takes branch 1 (an Archers-class Gyrocopter would fire its steam gun only while
   the cap is reached; practically unreachable).
4. Otherwise: **reload stamp := now** (even if step 6 then fails), obstruction test (+8 scatter step), then by
   missile code: bows 1/9/18/19, crossbow 2, cannons 5/11, mortar 6, Hellblaster 7, rock lobber 8, doom diver 12 →
   one projectile (`game_rules.md` §8.3 table) from the launching model, with the weapon's launch sound.
   Artillery codes (5, 6, 7, 8, 11, 12) roll for **misfire** first (`game_rules.md` "Artillery misfire"): on a
   misfire no projectile is launched but the result still counts as **success** (condition true, no 90 % retry).
5. A successful normal launch **clears the unit's hidden state** (firing reveals a hidden unit). A misfire does not.
6. Any other missile code (0, 13, 16, 17 on an Archers/Artillery unit, …) **fails** (after the stamp of step 4).

### 1.3 Consequences

- **Every projectile restarts the reload.** The volley stamps the reload when it is ordered (`StampReload` in 115),
  and every arrow stamps it again when it launches. The next volley therefore waits `base` measured from the
  **last arrow** of the previous one, i.e. about 3–5 ticks longer than `game_rules.md` "stamped at every volley"
  suggests.
- **The 90 % fallback almost never launches**: every way for Launch to fail (cap, wrong class, no projectile for the
  code) makes Launch90 fail the same way. It matters only for the edge of §1.2 step 3. An engine may implement it
  literally or skip it; it has no observable effect in shipped battles 🟡.
- With **no target and no point** (target removed mid-volley, see §5), the posted event is spent and nothing flies.
- With **no target but an old point** (the unit once had a ground-fire order or a point spell), the shot goes to
  that **stale point** 🟡 (rare, but it is what the original does).

## 2. `FireAt90PercentRange` (0x85, 1 word) — shoot short of an out-of-range target

Shipped: library 112 only (event 35 handler), 45 in all. Ordered by library 117 (`PlayUnitAnimation 7 35 4` /
`PlayLeaderAnimation 7 35`), which library 107 (fire order at a **building**) runs when the building is in arc but
out of range.

### 2.1 Effect

```
model := source of the current event       # the original reads it without checking; treat "no event" as −1
P := target unit's centre if a current target exists (aim-at-point is NOT consulted), else target point if set
if neither: condition := false; stop
condition := Launch90(model, P)
```

No reload/arc/range/target-state test beyond Launch90's own; does **not** clear aim-at-point or the target.

### 2.2 Launch90(model, P)

1. Fails at once unless the unit is a special shooter, or is Archers/Artillery class with fewer than 32 projectiles
   in flight.
2. **Arc**: the bearing from the unit to P must be inside the ±45° front arc (strict, `target_queries.md` §1); else
   fails (no turn).
3. `d = trunc(√(Δx² + Δy²))` from the unit centre to P; `r = trunc(R × 9 / 10)` with R the weapon range of the
   unit's missile code (`game_rules.md` §8.3: bow 576 → 518, crossbow 720 → 648, cannon 1152 → 1036, great cannon
   / rock lobber / doom diver 1440 → 1296, mortar 768 → 691, short bow 384 → 345).
4. Aim point `A = (ux + trunc((Px − ux) × r / d), uy + trunc((Py − uy) × r / d))` (32-bit integers, product first,
   truncation toward zero per axis). So the shot is aimed **exactly at 90 % of range along the line to P** — short of
   a far point, but **beyond** a point nearer than 0.9 R (only reachable through the `FireAtTarget` fallback).
   `d = 0` is a division by zero in the original (never happens in shipped play; an engine should fail).
5. Launch(model, A) as in §1.2; the result is Launch90's result.

### 2.3 Test vectors (unit at (1000, 1000), facing 0 = +Y, bow R = 576, 0 projectiles in flight)

| before | instruction | after |
|---|---|---|
| target point (1000, 2000), no target, event 35 from model 3 | `FireAt90PercentRange` | d = 1000, r = 518, A = (1000, 1518); one arrow from model 3; reload stamped; cond true |
| point (1300, 2000) | same | d = trunc(√(300² + 1000²)) = 1044; A = (1000 + trunc(300·518/1044), 1000 + trunc(1000·518/1044)) = (1148, 1496) |
| point (2000, 1999): bearing 64 (arc edge, `target_queries.md`) | same | out of arc → nothing; cond false |
| point (1000, 1100) (d = 100 < 518) | same | A = (1000, 1518): aims 418 units **past** the point |
| target unit T at (1000, 2000) and aim-at-point on, point (0, 0) | same | aims along the line to **T** (aim-at-point ignored here) |
| 32 projectiles in flight | same | cond false, nothing launched, reload **not** stamped |

## 3. `FireAtNode node` (0x87, 2 words) — order a ground shot at a map node

Shipped: 15 uses in 3 DLLs: BF014 script 7 (nodes 17–21, the scripted Dragon breathing at fixed places when a unit
stands in node areas 22/24), BF017 scripts 2–4 (nodes 16–18: a war machine that bombards a fixed point when
`FindTarget` finds nothing in arc and range), BF027 scripts 4 and 5 (node 12).

**Effect**: queue to the unit itself the **ground-point fire event 33 (0x21)** with no source (−1) and x, y = the
position of map node `node`. Condition := true if the event was queued (false only when the shared event pool is
full). Nothing else: no reload, range or arc test here, no target change yet.

**What happens next** (library 154/156, case 33; the unit's interrupt script must reach 154 or 156 — mission
shooters' handlers do): at the unit's next event dispatch (the start of its next tick, `game_rules.md` "Event
dispatch is pre-emptive"): `TakeEventTarget` → current target := none, target point := the node (cond true);
`GosubScript 110` → `ReadyToFire 1`, `InArcAndRange 1` (on the point), then the volley script 115 (or `React 14`
when not ready / not in arc and range); then **`Restart`** — the unit's main script restarts at its restart point.
BF014 script 7 places a `SetRestartPoint` right after each `FireAtNode` block for exactly this reason: each
bombardment step resumes from the following block.

The shot then follows the normal volley path (§5): `PlayLeaderAnimation 7 34` for a war machine, event 34 →
`FireAtTarget` → no target, so the **point** is used. For a special shooter (the Dragon) 115 calls `FireAtTarget`
directly with no launching model (breath from the unit's own position routine).

| before | instruction | after |
|---|---|---|
| node 17 at (812, 1430); queue empty | `FireAtNode 17` | queue: event 33 (source none, x 812, y 1430); cond true; target and point unchanged this tick |
| next tick, dispatch | (library 154/156) | target none, point (812, 1430); 110 runs; main script restarts at its restart point |

## 4. `IfArtilleryManned tag` (0x7A, 2 words)

Operand: a **unit tag** (the value set by `SetTag`); a negative operand means the unit itself. Shipped: `0xABC1`
(BF004_5 script 4) and `0xABC8` (BF017 script 5; the war machine running BF017 script 2 does `SetTag 0xABC8`).

Condition := the unit (self, or the unit carrying that tag) exists and is **manned** (§0: Artillery class, machine
present, at least 2 models). No unit with that tag → false. Written in every branch. No reload test, no message.

BF017 script 5 uses it as "while our gun is manned, shoot from where we stand (own ready/arc/range loop, turn and
wait when only out of arc); once it is not, run the full AI fire-at-will helper 121" (which adds the run-away
checks of 118 and the approach of 119).

| before | instruction | after |
|---|---|---|
| unit tagged 0xABC8: Artillery, machine alive, 3 models | `IfArtilleryManned 0xABC8` | true |
| same, 1 model left (machine only) | same | false |
| same, machine destroyed, 3 crew | same | false |
| no unit with tag 0xABC8 | same | false |
| self is Infantry class | `IfArtilleryManned -1` | false |

## 5. From volley to projectile: events 34 and 35

There is **no engine code that turns events 34/35 into shots by itself**: they are ordinary unit events, handled by
the shared library handlers **154** (player Artillery, via 102) and **156** (player Archers, via 104), which mission
interrupt scripts of shooting units also call:

```
case 34: SetCondFlags 4; GosubScript 111       case 35: SetCondFlags 4; GosubScript 112
script 111: FireAtTarget                        script 112: FireAt90PercentRange
            IfEventSource -1                                (same tail as 111)
            IfNot  IfClass 32  If  IfMachineDestroyed  IfNot
                       SetWait 10; Wait; React 12; ReformToScriptRanks
            ReturnGosub
```

- Each event 34 = **one `FireAtTarget`** launched from the model that posted it (its index is the event's source).
  Event 35 = one `FireAt90PercentRange`.
- After every artillery shot (source is a model, class Artillery, machine still there) the handler **waits 10 ticks
  inside the event handler** — the unit's main script is suspended meanwhile — then barks `React 12` and re-forms to
  its script ranks. 🟡 whether further events are dispatched during that wait.
- A unit whose interrupt script reaches neither 154 nor 156 (library 101/103 → 153/155 → 152: Infantry, Cavalry,
  Monster, Wizard handlers) **drops** events 33–35: a volley animation ordered for such a unit produces no shots. The
  Monster-class special shooters do not need them (115/117 fire them directly), but BF014's Dragon needs case 33 for
  `FireAtNode` and its handler does call 154.
- Timing: the model posts the event in the model update at the end of its unit's tick; the unit handles it at the
  **start of its next tick** (pre-emptive dispatch). So an arrow whose model reaches the fire step on tick k leaves on
  tick k + 1. Several events pending at once are all handled in that same dispatch pass (LIFO order,
  `unit_script_control.md`).

### 5.1 Who shoots without a script? (the implementer's key question)

**For ordinary missile weapons (codes 1, 2, 5–9, 11, 12, 18, 19) every projectile comes from `FireAtTarget` or
`FireAt90PercentRange`, i.e. from a unit script handling event 34/35.** The engine never picks a target and never
orders a volley on its own. The only launches that bypass scripts are:

1. **Player fire order on a special shooter** (codes 14, 15, 17, any class): the special routine fires **at once at
   the clicked point** — no reload, range or arc test, no event (`game_rules.md` "Who shoots"). 🟡 This includes an
   Archers-class Gyrocopter: its plain Fire order fires the **steam gun**, which contradicts `game_rules.md` ("the
   two Archers-class files … never use the steam gun"); the bomb is the separate Ctrl command.
2. **Gyrocopter bomb** (Ctrl + command).
3. **Periodic behaviours set by mission scripts** (`SetBehaviour`, timing in `deployment.md` §5.3): case 26
   (Doomwheel bolts, own reload on the leader block) and 27 (Pestilent Breath). Case 26 is also run by the player
   threat-detection behaviours 11/12 for a unit whose missile code is 13. Case 21 (one mission use) only queues
   event 33 at the nearest unit's position, i.e. goes through the scripts again.

**Who picks the target:**

| shooter | target selection |
|---|---|
| player unit, **no order** | **nobody fires** unless provoked. Library 100 gives every player unit threat range **240** and behaviour 11 (12 with objective 7) every 30 (31-tick period). Behaviour 11/12 = threat detection: if the unit's **threat slot** holds an enemy whose current target is this unit (an **independent** unit: any enemy in the slot; when none qualifies an independent unit re-picks its best threat, `script_queries.md` case 1) and that enemy is **closer than 240** (octagonal distance, strict), queue event 3. The threat slot of a non-independent unit is filled when an enemy announces its attack (event 5 → Query 6, `script_queries.md` §3–4). Archers and Artillery handlers then run `ReactToThreat` (`threat_events_nodes.md` §6: ±60° visibility, higher score) and, on success, library **126**: quarter-turn to the target, then loop 124 (or 122 if independent and not held) — fire whenever ready, in arc, in range and `TargetValid` — while `BrokenTargetInRange` holds. So an unordered bow unit only shoots back at an enemy within 10" that is attacking it; it never shoots at an enemy 20" away on its own. Other classes react only when independent (and charge rather than shoot). |
| player unit, **fire order** | the player's choice: unit (event 31 → loop 108/124), building (30 → 107), ground (33 → 110, one attempt with messages), search = click on itself (32 → loop 109/123: `FindTarget` = nearest non-broken hostile in range **every pass**). Independent Archers get hunt variants: on itself 36 → 113/121, on a unit or building 37 → 114/122 (re-target / approach as AI). |
| AI unit | its mission script: usually `GosubScript 121` (or 116/123 etc.): `FindTarget` (nearest hostile, not broken, `d ≤ R`, no arc test — `threat_events_nodes.md` §2), then `InArcAndRange` → volley; in range but out of arc → turn and wait until halted; out of range → 119 (`FindTargetAnyRange` + approach). Script 118 first lets it run from threats. |
| special shooters (14, 15, 17) | same scripts and targets; 115/117 take the `IsSpecialShooter` branch and fire the routine at once, from the unit (no launching model), at the current target (or point). |
| war machines | same scripts; the volley is the machine's own animation (`PlayLeaderAnimation 7 34`), one event, one shot, then the 10-tick wait of 111. Mission machines may use their own loops (BF017 script 2: ready → `FindTarget` → volley, else `FireAtNode`). |

## 6. Worked examples

### 6.1 Ten-model Archers unit (bow, I2, base 101), library loop 113 → 121 → 116 → 115

Unit A: 10 models, independent, given a hunt-search order (event 36); enemy E in arc at 400 units; reloaded.
Order of work inside a tick (per unit): event dispatch → script → formation → movement → model update.

| tick | what happens |
|---|---|
| 0 | dispatch: event 36 → `TakeEventTarget`, `ClearUnitFlags 0x4000000`, switch to 113: `SetUnitFlags2 4` (shooting sequence busy), `React 13`, `ClearAnimationRequest`, `PushPC; Yield`. |
| 1 | 113 → 121 → 118 (no threat) → `ReadyToFire 0` true → `IfAnimationDone 7` true (no request) → `FindTarget` = E → `InArcAndRange 0` true → 116: `TargetValid` true → 115: **`StampReload`** (T₁), not special, `React 10`, class Archers → `PlayUnitAnimation 7 34 4`: request (34, 4, 10). Model update: all 10 models enter the shoot pose with their random skip. |
| 2 | 121: `ReadyToFire` false (reload) → nothing. Model update: models whose fire tick is 2 reach the fire step. Say models 0 and 4: countdown 10 → 9 → **8** → event 34 (source 4) posted. |
| 3 | dispatch: event 34 (source 4) → 111 → **`FireAtTarget`: arrow 1 from model 4 at E's centre; reload re-stamped (T₃)**; hidden state cleared. Model update: model 7 reaches its step (8 → 7). |
| 4 | models 1, 2, 5, 9 reach the step: 7 → 6 → 5 → **4** (event, source 5) → 3. |
| 5 | dispatch: **arrow 2** from model 5 (stamp T₅). Models 3, 6, 8: 3 → 2 → 1 → **0** (event, source 8). |
| 6 | dispatch: **arrow 3** from model 8 (stamp T₆). The last pose ticks run out by tick 8; `IfAnimationDone 7` is true from now (countdown 0). |
| ≈ 113 | first tick with `T_now − T₆ > 101` (102 increments of T plus one tick per segment boundary): 121 orders the next volley. Without the per-arrow re-stamp it would have been ≈ 5 ticks earlier. |

Three arrows (⌈10/4⌉), launched on ticks 3, 5, 6 here; in general one tick after the posting model's fire step.

**Target dies mid-volley** (e.g. destroyed by someone else on tick 4): the removal broadcast reaches A as event
0x16 → Query 22 → event 0x19 → `DropTarget` → `SwitchScript 163` (rally, re-form, restart). Events 34 still to
come (the request is not cleared by 163) each run `FireAtTarget` with **no target**: no arrow (or an arrow at a
stale target point, §1.3). If an event 34 is handled before the 0x19 in the same dispatch, it still aims at the
removed unit's last centre 🟡 (LIFO order decides).
**Target moves out of range or arc mid-volley**: remaining arrows still fly at its current centre (no test in
`FireAtTarget`); the next pass of 121 sees `InArcAndRange` false and turns / approaches instead of ordering a volley.
**Shooters die mid-volley**: fewer events (`script_animation_sound.md` §2.6); positions shift by arrival order.

### 6.2 War machine (cannon, code 11, crew I3 + machine, 4 models, base 126)

| tick | what happens |
|---|---|
| 1 | 121 → … → 115: `StampReload`, `React 10`, class Artillery → `PlayLeaderAnimation 7 34`: only the machine model takes the shoot pose; request (34, 1, 1). |
| k ∈ 2…5 🟡 (the machine family's own shoot program) | machine reaches its fire step: countdown 1 → 0 → event 34, source = machine's index. |
| k + 1 | dispatch → 111: `FireAtTarget` → misfire roll (D6; on 6 a second D6: 1 destroyed, else lost — both count as "fired", no projectile, `game_rules.md`) → otherwise one ball from the machine, scatter die d; reload re-stamped (also on a misfire). Then source ≠ −1, Artillery, machine intact → **`SetWait 10; Wait`** inside the handler. |
| k + 11 | `React 12`, `ReformToScriptRanks`; handler ends, main loop resumes. Next shot after `T − T_{k+1} > 126` (+36 per model below 4). |

If the target dies before tick k + 1 the ball is not fired (no target, no point) but the 10-tick wait and re-form
still happen.

## 7. Differences from the implementer's current engine model

1. **No engine auto-targeting.** The original never chooses a target or orders a volley outside scripts. An engine
   that picks "nearest in arc and range" for every missile unit that is not moving makes **unordered player units
   fire at will**; in the original they fire only when ordered or when an enemy closer than 240 that is attacking
   them provokes the threat reaction (§5.1). AI units fire only through their mission scripts (most call 121).
2. **Double counting.** The library loops already order volleys (`StampReload` + `PlayUnitAnimation 7 34 4`). With
   the engine's own volley on top, a script-driven unit gets two volley orders, two reload stamps and, once events
   34/35 are wired, **two sets of projectiles**. Implement shots only as `FireAtTarget`/`FireAt90PercentRange` on
   events 34/35 (plus the §5.1 exceptions) and remove the engine volley.
3. `FireAtTarget` is not a no-op: it is the projectile launcher (§1). `FireAt90PercentRange`, `FireAtNode`,
   `IfArtilleryManned`, `StampReload` and the 111/112 artillery wait are needed for BF014, BF017, BF027 and every
   building order.
4. **Reload** restarts at **each projectile launch**, uses the strict `>` test and the 18-per-segment clock value
   (§0); the engine's stamp at volley time only is ≈ 3–5 ticks short per volley.
5. **Launch position** is the posting model (event source), not a pre-picked model; launch happens one tick after
   the model's fire step.
6. Firing **reveals** a hidden unit.
7. "Not moving or charging" is not a launch condition: scripts turn and wait until halted before ordering, and a
   player fire order halts the unit; already-posted arrows fly regardless.

## 8. Contradictions / refinements of public notes

- `game_rules.md` "Reload time": "the last shot is stamped at every volley" — also at **every projectile** (and at
  a misfire); the ready test is strict.
- `game_rules.md` "Who shoots": "A building out of range is shot at 90 % of maximum range" — refined in §2 (aim at
  exactly `trunc(0.9 R)` along the line, arc required, fails silently otherwise).
- `game_rules.md` §8 / `ReadyToFire`: "at least 2 crew" — at least 2 **models** (machine probably included 🟡); the
  2015/2016 messages ignore the message operand.
- `game_rules.md` special weapons: an Archers-class Gyrocopter's Fire order fires the steam gun (§5.1) 🟡.
- `unit_script_control.md` §5 🟡 "what that argument selects": the event source selects the **launching model**
  (and, for `CastPending`, presumably the same; not re-checked here).

## 🟡 Uncertainties

- Model index validity when models died between posting and launch.
- The machine's shoot-program timing (fire step tick) for war-machine families.
- Whether events are dispatched while the 111/112 handler waits 10 ticks.
- Initial value of the target point (assumed unset).
- `TakeEventTarget` also copies the event's parameter into the pending-spell slot for fire-order events
  (`script_magic.md` §4 mechanism); for shooting units this appears harmless.
