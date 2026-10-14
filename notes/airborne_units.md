# Airborne units: flying state, elevation, rules while airborne, in-air death (GitHub #388)

Public implementation report. Part A covers **which units fly, when, and how high**: take-off and landing,
drawing, script-visible state and the death in the air. Part B covers **what changes in the battle rules while a
unit is airborne**: movement, collisions, charges, close combat, sight, terror, the map edge and deployment, plus the
"over or around" questions about obstacles and height.

Legend: ✅ checked in this pass · 🟡 inferred or not watched in play.

Companion reports, cited rather than repeated: `spell_effects.md` §2.1 and §4 (aim height, the flying hit band),
`spell_blades_flock_items.md` §1, `game_rules.md` "Impact", "Fear and terror", "Engagement: battle grid and pairing",
`ranged_combat_handoff.md` (bomb), `camera_shake.md` §5, `machine_figure_animation.md` §2.9,
`script_animation_sound.md` §0 (animation actions), `script_behaviours.md` §2 (collision pass), `obstacle_steering.md`,
`movement_boundaries_route_finding.md`, `map_objects_and_projectiles.md` §2, `terror_contact_charge.md`,
`threat_events_nodes.md` §2 and §6, `target_queries.md`.

**Corrections made by this report:**

- `machine_figure_animation.md` §2.9 (Gyrocopter): the take-off and landing take 32 ticks as 2 laps of 12 frames plus
  4 height steps each. Whether it lands or hovers depends on whether the figure came **straight from its flying
  program**, not on whether it was flying (§A3.2). The crash step is the camera shake (already corrected).
- `threat_events_nodes.md` §6 open question: the "far side" approach point is used only for ordinary troops
  footprints. Monster, war machine, wagon, building and airborne footprints are approached at their centre (§B2.4).
- `spell_effects.md` §3.4: a terminal impact against a flier's point is made at height 0 and never strikes an
  airborne unit (§A8).
- The engine's flier height of 72 is not a height: 72 is the radius of the bomb and of the crash blast. Full flying
  height is **32** (§A2).

# Part A: the flying state

## A1. Which units can fly — decided by the figure's sprite set ✅

Flying is **not** a unit-type field, class, weapon code or `.BTS`/`.MRC` keyword. It is a property of the
**animation family of the figure's sprite set**: only two families contain take-off and landing steps.

| sprite set (`troopsprites:` name) | flies | notes |
|---|---|---|
| `Wyvern` | **yes** | the Orc shaman's Wyvern (BF026, BF034): `s_side=…,1,1,1` → **one figure**, the leader, whose own `troopsprites` is also `Wyvern`. Rider and mount are a single figure |
| `Gyrocopter` | **yes** | `3rd_Gyrocopters` (BF033.MRC, MAXARMY.MRC, saves): one figure. **Both** the Infantry-class file variant (steam gun) **and** the Archers-class variant (bomb) fly — the class and weapon code play no part |
| `SquigHopper` | **only during a hop** | the hop animation lifts the figure on a ballistic arc (§A7) |
| `Dragon` (3D mesh), `DoomDiver`, `Giant`, everything else | **never** | the Dragon's breath launches from 20 above the ground (`bf014_dragon_mission_audit.md`), but the Dragon itself is a ground unit; the Doom Diver's "flight" is a projectile |

Engine rule: a figure whose sprite set is `Wyvern` or `Gyrocopter` can take off. Every shipped flyer unit has
exactly one figure. 🟡 For a (non-shipped) multi-figure unit with a flying sprite set, each figure's program steps
the *same* unit elevation, so the unit would climb and descend faster; the engine may simply keep the elevation per
unit and step it once per tick.

**Correction to the engine model:** `airborne` is not "Archers-class with weapon 17, fixed at load". It is a
**state that changes during the battle** (§A2), possible for Wyverns and both Gyrocopter variants, and **every flyer
starts the battle on the ground** (elevation 0).

## A2. The flying state and elevation ✅

Each unit has an **elevation** (0 = on the ground). The unit is **in the flying state exactly while its elevation
is greater than 0**. There is no separate flag: the first climb step (elevation 4) puts it in the flying state; the
last descent step (elevation 0) returns it to the ground state. So during the climb and the descent the unit
already/still counts as flying for every rule, at its current (partial) elevation.

While in the flying state the unit no longer counts as an ordinary ground object (troop, artillery or monster kind)
for rules that only look for ground objects; it counts as a "flier" instead. When the elevation reaches 0 it
returns to its ordinary ground kind (artillery-class units back to artillery, monster-class back to monster, all
others back to troops). Which rules care is Part B; known public consequences: height-0 blasts and
area spells skip it, missiles and spells hit it only inside its raised window.

- **Step size 4, ceiling 32**, for both Wyvern and Gyrocopter. Elevation is clamped to 0…32.
- **Full flying height = 32** (world/script height units, the same units as the object height 16 and projectile
  heights). **The engine's 72 is wrong**: neither the missiles nor the spells use 72 for a flyer; 72 is the radius
  of the Gyrocopter bomb and of the crash blast, not a height. So a flyer at full height is hit by a projectile
  whose height above its ground is in **32…48**; an aim at a flyer at full height targets **8 + 32 = 40**.
- Each climb/descent step is a tick of its own (the figure keeps showing its previous frame on that tick).

## A3. Take-off and landing — driven by the figure's animation action ✅ (programs) / 🟡 (play consequences)

The figure's animation **action** (the public numbering of `script_animation_sound.md` §0: 1 stand, 2 idle/move,
3 walk, 4 fight, 5 weapon ready, 6 dead, 7 shoot/cast) decides it. Recap of when the game requests each action
(`script_animation_sound.md` §0.1): the unit-wide request is 2 at the start of a move or turn, a formation snap or
a re-form; on halting / end of a wait the "rest action" is 3 if charging or pursuing, 2 if a move/turn/flee/pursuit
is still active, 5 if the unit has a current target (not an anchored war machine), else 1. A figure arriving at its
place asks for the unit's rest action; rout and pursuit re-aims and charge starts give walking figures 3; close
combat gives 4/5. Scripts can request any action (`SetActionState`, `PlayUnitAnimation`, `PlayLeaderAnimation`).

### A3.1 Wyvern

| action | program |
|---|---|
| 2 (moving, turning, re-form start) | if **not flying**: **take off** (40 ticks, below), then wing-flap loop on the *stand* frames (group 72), **1 tick per phase** `0,1,2,3` |
| 1 stand, 5 weapon ready | if **flying**: **land** (40 ticks), then slow stand loop group 72, phases `0,0,0,1,1,1,2,2,2,3,3,3` |
| 3 walk (charging, pursuing, routing, walking to its place) | if flying: **land** (40 ticks, flap frames), then walk on the ground: group 0, `0,0,1,1,2,2,3,3`, random entry 0–7 |
| 4 fight | group 40 fight loop; **elevation unchanged** (a Wyvern paired while airborne fights in the air at its current height) |
| 7 shoot/cast | cast pose (group 104), event step after 4 ticks, 5 more ticks; then **if flying → action 2** (keeps flying, no new take-off) **else → action 1** |
| 6 dead | §A5 |

Take-off / landing sequence (group 72 frames, d = drawn direction): 4 laps of `F0, F0, F1, F1, step, F2, F2, F3, F3,
step` → **40 ticks, 8 steps of ±4**. A take-off is skipped entirely if the unit is already in the flying state at
the start of action 2 (any elevation > 0); a landing runs whenever it is in the flying state at the start of
action 1/3/5 (it always plays all 40 ticks; from a partial height the elevation just reaches 0 earlier and stays).

Consequence 🟡 (follows from the request rules above; not watched in play): a Wyvern flies **only while moving or
turning**, and while casting started in the air; it lands whenever it stops, starts a charge, pursues, routs, or
gets a target; a charging Wyvern lands during the first 40 ticks of the charge and arrives on foot.

Quirk ✅: interrupting a landing with a new move (action 2 while elevation is, say, 16) does **not** climb back:
the take-off is skipped because the unit is already flying, so it continues to move at 16 until the next landing.

### A3.2 Gyrocopter

| action | program |
|---|---|
| 2, 3, 7 (one shared program) | if **not flying**: **take off** (32 ticks), then fast rotor loop group 0 `0,1,2,3,1,2` (1 tick each). Marks the figure as "came from a flying program" |
| 1, 4, 5 (one shared program) | **if the figure came straight from the 2/3/7 program**: **hover** — no landing, keep the current elevation; remember "hovering". **Otherwise**: if flying, **land** (32 ticks). Either way then the slow rotor loop `0,0,0,1,1,1,2,2,2,3,3,3,1,1,1,2,2` (17 ticks) |
| 6 dead | §A5 |

Take-off / landing sequence: 2 laps of `F0, F0, F1, step, F1, F2, F2, step, F3, F3, F1, step, F1, F2, F2, step` → **32
ticks, 8 steps of ±4** (corrects `machine_figure_animation.md` §2.9's "two laps of a 12-frame sequence": 12 frames + 4 step ticks per lap).
The shoot action (7) has **no event step** for the Gyrocopter (its shots do not come from the pose).

"Hovering" detail: while hovering, a **repeat** of the same rest action (normally ignored) restarts the 1/4/5
program, which now takes the "otherwise" branch and **lands**; a *different* rest action (e.g. 1 → 5 when it gets a
target) also lands. Any 2/3/7 request clears "hovering" again (keeps flying).

Consequence 🟡: unlike the Wyvern, a Gyrocopter **stays in the air after a move** (hovering — which is what lets
the player drop a bomb on a stationary spot) and **flies when charging, pursuing, routing or walking**. It lands on
the second rest request after a move (a script `SetActionState 1`, the end of a timed wait, a re-request on
arrival), or when a target makes its rest action change. A Gyrocopter paired in melee straight out of a charge
fights hovering (4 without landing); after a later 5/1 it lands.

### A3.3 Timing table (tick 1 = the tick the program starts)

| tick | Wyvern take-off | Wyvern landing (from 32) | Gyrocopter take-off | Gyrocopter landing (from 32) |
|---|---|---|---|---|
| 1–4 | F0 F0 F1 F1, elev 0 (ground) | F0 F0 F1 F1, 32 | t1–3 F0 F0 F1; **t4 → 4 (flying)** | t4 → 28 |
| 5 | **→ 4 (flying from here)** | → 28 | | |
| 10, 15, 20, 25, 30, 35 | → 8, 12, 16, 20, 24, 28 | → 24, 20, 16, 12, 8, 4 | t8 → 8, t12 → 12, … t28 → 28 | t8 → 24 … t28 → 4 |
| 40 / 32 | → **32**; from t41 flap loop | → **0 (ground)**; from t41 stand loop | t32 → **32**; rotor loop from t33 | t32 → **0**; slow rotor from t33 |

Elevation after tick *t* during a Wyvern take-off: `4 × floor(t / 5)` (max 32); Gyrocopter: `4 × floor(t / 4)`.
Landing: `32 − ` the same.

The animation runs every game tick whether or not the unit is on screen, so the timing is game logic.

## A4. Drawing ✅

- A living figure is drawn at **ground height under the figure + its unit's elevation** — the raised figure
  follows the terrain under it. Frames are the ordinary sprite frames listed in §A3 (no special "flying" group;
  the Wyvern in the air uses its *stand* group 72 flapping fast, the Gyrocopter its single rotor group).
- The unit's banner/standard is raised by the same elevation (on top of its usual offset above the figure).
- 🟡 No shadow or ground marker for a raised figure was found in the figure drawing path.
- Effect sprites spawned by the figure at "height 0" are placed at **half the object height + elevation**
  (8 + elevation) while the unit is flying (the Gyrocopter's fall smoke, §A5).

## A5. Death in the air vs on the ground ✅

The test is made **once, at the start of the death program**: "is the unit in the flying state (elevation > 0)?".
Every shipped flyer is a single figure, so its unit is destroyed (out of the roster, kills credited by the
ordinary rule) at the first death tick; the dying figure continues as a corpse figure.

### A5.1 Wyvern, killed in the air

| tick | what happens |
|---|---|
| 1 | random facing (0–511) for the figure; figure removed from the unit; flap frames start (group 72) |
| 1–40 | the 4-lap descent of §A3.1 (−4 every 5th tick; the elevation reaches 0 by tick 40 from 32, earlier from lower) |
| 1–40 | **the corpse figure glides 2 world units per tick along its random facing** (about 80 units in all) 🟡 exact first/last tick |
| 41 | a new random facing; **corpse frame** group 32 (+ d); the glide stops |
| 42 | **crash blast** at the corpse's position (below), then the **medium camera shake** (`camera_shake.md`) |

### A5.2 Gyrocopter, killed in the air

| tick | what happens |
|---|---|
| 1 | random facing; figure removed from the unit; rotor frames (group 0) |
| 1–32 | the 2-lap descent of §A3.2, with a **smoke puff** (`SPELLS` smoke, 4 frames × 8 ticks) spawned right after each of the 8 steps, at 8 + the new elevation: 36, 32, 28, 24, 20, 16, 12, then 0 (on the ground) when starting from 32 |
| 1–32 | glide 2 units per tick along the random facing (about 64 units) 🟡 |
| 33 | new random facing; **wreck frame** group 32 (+ d); glide stops |
| 34 | an **explosion** sprite on the ground (the generic explosion effect), the **crash blast**, then the **medium camera shake** |

### A5.3 Visual quirk 🟡 (to check by eye)

A corpse figure is always drawn **at ground height**: the elevation steps of the fall continue on the destroyed
unit (they drive the smoke-puff heights and the blast height), but the figure itself appears on the ground
immediately, playing its flap/rotor frames and gliding, while the Gyrocopter's smoke puffs come down from 36. An
engine may reproduce this or (more naturally) draw the falling figure at the stepped elevation; the rules outcome
is the same.

### A5.4 The crash blast (both) ✅

An ordinary impact (`game_rules.md` "Impact") at the corpse figure's position at the end of the fall, **height 0**:

| parameter | Wyvern | Gyrocopter |
|---|---|---|
| radius | 72 | 72 |
| direct hit (impact point inside a unit's footprint) | **every model**, S5, **D6 wounds** each, armour save allowed | same |
| blast margin (`d < footprint + 72`) | `n = (footprint + 72 − d) × size / (footprint + 72)` (min 1) random models, S2 (5 halved), 1 wound, save at S2 | same |
| buildings / furniture | S5 vs the building, D6 (direct) / S2, 1 (margin), no save | same |
| magical | no | no |
| damage / death kind | 2 (ordinary missile) | **1 (fire)** — victims play the burning death |
| panic / rout bits | none (no impact panic test, no forced rout) | none |
| battle messages | **none** (no "Direct hit" / "have been hit" text) | none |
| who is hit | every active unit **of any side** whose height test passes: all ground units; **units in the flying state are never hit** (height 0 < their elevation); hidden, broken, routing included | same |
| the crashing unit | already destroyed — unaffected | same |
| kill credit | the **crashed flyer's own unit** (it is the blast's source), also for its own side's dead | same |

### A5.5 Ground death ✅

Killed while elevation = 0: corpse/wreck frame group 32 at once, no glide, **no blast, no shake** (Wyvern: corpse
held; Gyrocopter: wreck held). A flyer killed during its take-off or landing (elevation 4…28) counts as **in the
air**: full fall program, blast and shake.

For comparison (already public): the **Giant** death blast is radius 40, the same S5/D6/S2 numbers, damage kind 2,
at its first death tick (before the corpse frame), then the medium shake; it is not a flyer.

## A6. Script-visible state ✅

- **No script opcode reads the flying state**, and there is no take-off or land opcode. The flying state is not a
  unit flag (it lives with the unit's elevation), so `IfUnitFlags`/`WaitWhileUnitFlags` and similar never see it.
- Scripts change it only **indirectly**, through animation requests: `SetActionState 1` (shipped, 9 uses) makes a
  Wyvern land and a hovering Gyrocopter land; `SetActionState 2`/movement makes them take off; `PlayUnitAnimation 7
  …`/`PlayLeaderAnimation 7 …` (cast/shoot pose) keeps a flying Wyvern flying and returns it to action 2 after the
  pose. The shipped Wyvern scripts (BF026 script 1, BF034 script 2) never request an action directly; the Wyvern
  takes off and lands only as a side effect of the moves, charges and casts those scripts order.
- The AI spell-target queries (opcodes 0xA3–0xA7) treat a flying unit as a valid target like a ground one; the
  area-spell rule excludes it (public `script_magic.md`).
- **Not the same as** the "lifted off the map" state of a Flying Bower flight (`spell_channelled_effects.md` §2):
  that one is a unit state that hides the unit from contacts and drawing; ordinary flight never sets it, and a
  Bower flight does not change the elevation.

## A7. Squig Hopper hop (side finding) ✅ / 🟡

The hop animation (action 3, requested by BF039's scripts, `script_spawn_move.md` §4) lifts the single squig
figure into the flying state on an arc: after 5 crouch ticks, on tick 6 the elevation becomes `D / 4` (D = the hop
distance 16…96 recorded by `FanaticJump`), then each tick `v := v − 4` (v starts at D) and `elevation += v / 4`
(truncated toward zero), clamped to 0…**160**; rising frame while `v ≥ 0`, falling frame after; the loop ends on
the tick the elevation returns to 0, then the event step (event 53) and back to action 1. Example D = 16: elevations
4, 7, 9, 10, 10, 9, 7, 4, 0 (9 ticks in the flying state, peak 10). While the elevation is above 0 the squig is in
the flying state for every rule (height-0 blasts and area spells skip it, missiles hit it only in its raised
window). 🟡 Not watched in play; also the hop sets one further unit state whose meaning was not identified.


## A8. Spell projectiles against a flier whose elevation changes ✅

This section completes `spell_effects.md` §2–§3 for airborne targets. Heights are above the ground under the point.
F is a flier with elevation E (airborne while E > 0, band `E ≤ h ≤ E + 16`, §A2), footprint radius 25 (3 × 3 cells,
`game_rules.md` monster footprints, `movement_formation.md` bounding radius).

### A8.1 The rules

1. **The aim height is fixed at launch.** It is decided once, from the **pre-scatter** aim point, using the same
   pick as the player's Fire click (`building_map_object.md` §4): the first unit or building whose pick circle
   (footprint radius, at least 48) contains the aim point. If that object is airborne at the launch tick,
   `A = 8 + E(launch)` (half the flier's object height 16, plus its elevation); otherwise there is no aim height. Then
   comes the per-spell floor (`spell_effects.md` §3.0). After the scatter, the destination's ground is read at the
   scattered point, and the flight line from `ground(start) + L` to `ground(destination) + A` is **fixed for the
   whole flight**. Nothing re-reads the target's elevation, and nothing homes in on it in height. The only exception
   is the Hunting Spear's horizontal re-aim (§A8.3).
2. **Every in-flight test uses the target's *current* band.** A bolt hits F on a tick only if its point is inside
   F's footprint (`d < 25`) and its height on that tick lies within F's band at that moment. A flier that changed
   height since the launch can therefore be passed over or under.
3. **The terminal impact is always at height 0**, for 18-tick bolts and beams alike. So it **never hits a unit
   that is airborne at that tick**. It hits ground units, and a flier that has fully landed (E = 0), at the
   destination. Correction to `spell_effects.md` §3.4: "against a flying unit the terminal impact happens normally"
   means only that the bolt is not below ground and so reaches its terminal impact. That impact cannot strike the
   airborne flier. A Fireball hits an airborne flier only **in flight**.
4. **Launch heights do not use the caster's elevation**, except Gaze of Mork (`spell_effects.md` §3.0). Fireball,
   Lightning, Warp Lightning, Piercing Bolts, Burning Head and Pestilent Breath start at their fixed launch height
   above the ground under an airborne Wyvern shaman, as if it stood on the ground. The Hunting Spear starts at 8
   above the ground.

### A8.2 Heights near the target, flat ground

The caster is 288 from F, the bolt is aimed at F's figure and the scatter draws are all 0, so the destination is
F's position. `r` = remaining ticks (`spell_effects.md` §2.3), `d` = distance from the destination.

**Fireball** (L = 0, floor 0, 18 ticks, arc as in §3.4). Height = `arc(r) + A − trunc(A × r / 18)`:

| r | d | inside F (d < 25) | height if A = 40 (F at 32 at launch) | height if A = 0 (F on the ground at launch) |
|---|---|---|---|---|
| 3 | 48 | no | 36 | 2 |
| 2 | 32 | no | 37 | 1 |
| 1 | 16 | **yes** | **38** | **0** |
| 0 | 0 | **yes** | **39**, then terminal at 0 | **−1**, then removed (below ground, no terminal) |

**Lightning** (beam, L = 4, floor 4, `N = 1 + trunc(288 / 20) = 15`, ends at the first point with `d < 40`). Height =
`4 + A + trunc((4 − A) × r / 15)`:

| r | d | inside F | height if A = 40 | height if A = 4 (F on the ground) |
|---|---|---|---|---|
| 4 | 76 | no | 35 | 8 |
| 3 | 57 | no | 37 | 8 |
| 2 | 38 | **no** | 40, then the beam ends: **terminal at height 0** | 8, then terminal at height 0 |

So **a beam aimed straight at a flier never enters its footprint**: it stops 38 short of the destination, and its
terminal impact at height 0 cannot hit an airborne unit. A beam hits an airborne flier only when the scatter puts
the destination far enough past or beside it that a tested point at `d ≥ 40` falls inside the footprint (vector 5
below). The same holds for Gaze of Mork and Warp Lightning. Against a grounded flier the terminal impact hits it as
it hits any ground unit.

### A8.3 Hunting Spear

- The spear flies at **8 above the ground** everywhere (`spell_effects.md` §3.5). Its in-flight tests hit an
  airborne flier only when `E ≤ 8 ≤ E + 16`, i.e. at **E = 4 or 8**. Higher than that, the spear **passes under it**:
  it never stops on the flier and re-aims at the flier's centre every 3 ticks. It parks under the flier, follows it
  when it moves, and **expires when its 180-tick timer runs out**, unless something else stops it.
- If something else stops it (a ground unit under the flier, an obstacle), that costs 1 S as usual. If the stop
  point is inside the flier's footprint, the next tick's **strike chain** runs there. The chain tests at the
  spear's **absolute** height, ground + 8 (the high-ground quirk of §3.5). It hits the flier only if
  `E ≤ ground + 8 ≤ E + 16`. On low ground (ground height near 0) that again means E ≤ 8. On ground 24–40 high, a
  flier at 32 *is* struck by the chain (quirk). The chain also strikes every ground unit containing the point, for
  example the unit under the flier.
- **Landing mid-chase:** the first in-flight test after E has dropped to 8 or less, with the spear inside the
  footprint, hits the flier (the arrival hit, S as it stands, D3 wounds) and stops the spear. The next tick runs the
  chain at ground + 8, which hits a flier at E ≤ 8 on low ground and a landed one (E = 0, ground rules).

### A8.4 Test vectors (flat ground at height 0, caster 288 away, no scatter unless stated)

| # | Before | Action | After |
|---|---|---|---|
| 1 | Wyvern F hovering at E = 32 throughout | Fireball cast at F | A = 40. r = 3, 2 outside the footprint. **r = 1: height 38 within 32…48 → in-flight hit** (S4, 1 wound, no save, silent), bolt stops; no terminal impact |
| 2 | F at 32 at launch, starts landing on the launch tick (32 → 0 over 40 ticks); at the r = 1 and r = 0 tests F is at E = 20 (or 16) | Fireball | A = 40 (fixed). r = 1: 38 > 20 + 16 → miss; r = 0: 39 → miss; terminal at height 0 → F not hit (airborne); ground units at the destination are hit. **F unharmed.** Hit at r = 1 only if E ≥ 24 then |
| 3 | F on the ground at launch (A = 0), takes off during the flight; E = 12 (or 16) at the r = 1 and r = 0 tests | Fireball | r = 1: height 0 < 12 → miss; r = 0: height −1 → miss, bolt removed (below ground), no terminal. **F unharmed.** Had F still been at E = 0, r = 1 would hit it (ground rules) |
| 4 | F hovering at 32 | Lightning cast at F | A = 40; tested points r = 4, 3, 2 at d = 76, 57, 38: never inside the footprint; beam ends at r = 2; terminal at height 0 → **F not hit** |
| 5 | as 4, but the scatter puts the destination 28 beyond F along the line of fire | Lightning | at r = 2 (d = 38 from the destination, 10 from F): inside the footprint, height 40 within 32…48 → **hit** (S6, D3, no save), beam stops; on that same tick the terminal impact at height 0 still runs (`spell_effects.md` §2.4) and can only strike ground units |
| 6 | F landing; E = 20 when the beam's last points pass | Lightning, scattered as in 5 | height 40 > 36 → miss; terminal at height 0 → F not hit |
| 7 | F on the ground (E = 0) | Lightning | A = 4; terminal at the destination at height 0 → **F hit** like any ground unit |
| 8 | F hovering at 32, nothing else nearby | Hunting Spear at F | spear at height 8 reaches F's centre and keeps re-aiming there (8 < 32); **expires after 180 ticks, no hit** |
| 9 | F hovering at 32 over an enemy-side ground unit G that contains F's centre | Hunting Spear at F | the spear's in-flight test hits G (S6, D3), stopping it inside F's footprint; next tick chain at height 8 (S6, 5 … 1, one random model each): hits G again, misses F; effect ends |
| 10 | F at 32 while the spear chases, then lands; spear under F | landing | while E ≥ 12: misses. First in-flight test with E ≤ 8: **arrival hit** on F (S6 if nothing else was hit, D3, no save); next tick chain S6 … 1 (S as it stands) at height 8 hits F (E ≤ 8, band contains 8, or E = 0, ground) |
| 11 | airborne Wyvern shaman at E = 32 casts a Fireball | launch | starts at ground + 0 under the caster (no elevation added); Gaze of Mork would start at 32 |

---

# Part B: battle rules while airborne

Where Part B's per-action summary differs from Part A's programs, Part A's tables (§A3) are authoritative: in
particular a Gyrocopter going straight from a move, charge or shot into a fight or a halt **hovers** and does not
land (§A3.2).

## B0. The one fact that decides almost everything

Each unit owns one collision footprint, and every rule below chooses its behaviour by the footprint's **kind**:
troops (ordinary block), monster block, war machine block, wagon block, building/furniture, fanatic, plain
scenery (`script_behaviours.md` §2.1).

**While a unit is airborne its footprint kind is "flying" instead of its ground kind** ✅. On the first climb step
(elevation leaves 0) the troops / monster / war machine kind is removed and the flying kind set; when the
elevation returns to 0 the ground kind is restored from the unit's class (Monster class → monster block, Artillery
class → war machine block, anything else → troops). The elevation is a property of the footprint, so the whole unit
is airborne or not, never single models.

Consequence: every rule that asks "is this a troops/monster footprint?" treats an airborne unit as **not a unit
footprint**. Most such rules then fall through to their "plain object / scenery" branch or to "nothing". The few
rules that explicitly test for the flying kind are spells, missile hit tests, the Fire/Attack point pick and the
Gyrocopter bomb.

There is no separate rule path for "flying units" in movement, speed, steering, boundaries, deployment, fear,
spotting, or the map edge. §B2 goes through the list item by item.

### B0.2 Elevation reference

The elevation is an offset **above the terrain under the unit**, never an absolute height ✅ (all heights in the
battle rules are "ground height at the point + offset": projectile launch and flight, the impact height test;
`spell_effects.md` §2.1). Climbing stops at the maximum given by the animation (32 for both shipped fliers, §A2). Terrain therefore **cannot rise above a flier**. No movement, collision or steering rule reads the
terrain height at all (`movement_boundaries_route_finding.md`: no terrain passability layer; `game_rules.md`: "no
terrain height" in sight).

**Engine-model difference:** the engine's `+72` base height for airborne units (missiles and `FLYING_ELEVATION`)
is far above the data's maximum of 32 (§A2). The vertical hit band is
`elevation ≤ h ≤ elevation + 16` (`spell_effects.md` §4.1), so with the engine's 72 almost every missile and spell
height misses a flier that the original would hit.

---

## B1. Summary table

| Item | Changes while airborne? | How |
|---|---|---|
| Speed | **no** | same speed rule (M × 16 × order factor); no terrain or flight factor |
| Terrain cost, rough ground, hills | **no** | there is none for anyone |
| Boundaries (rivers, cliffs, walls as solid areas, battle edge) | **no** | still repelled exactly like a ground unit |
| Solid scenery, buildings | **no** | still pushed apart, with no height comparison |
| Route planning and steering (as mover) | **no** | detours around scenery, buildings and units as on the ground |
| Being an obstacle for others' steering | **yes** | counts as **plain scenery**: always blocks, whatever its side or state |
| Push-apart / contact, flier moving into ground units | **no** (mostly) | pushed by friends, makes contact with enemies, as on the ground |
| Push-apart / contact, ground units moving into the flier | **yes** | **ignored completely**: no push, no contact, no fear-on-contact, no contact attacks |
| Two airborne fliers | **yes** | ignore each other in collision; each is a scenery obstacle to the other's steering |
| Being charged / attacked by ground units | **yes** | contact is impossible while it stays airborne; a charge runs out |
| Its own charges / attacks | **no** (Gyrocopter); Wyvern lands first | contact with ground enemies engages normally |
| Close combat while airborne | **partly** | an airborne grid owner gets an ordinary block grid; attackers use the ordinary path (🟡) |
| Approach / charge aim point on a flier | **yes** | aims at the **centre**, not the far side |
| Fear / terror | **only on contact** | no fear-on-contact for ground units walking into it; charge-declaration and being-charged tests unchanged |
| Sight / visibility | **yes** (as blocker) | blocks other units' sight lines like scenery; it still sees and is seen normally |
| Spotting hidden units | **no** | spots and is spotted as on the ground |
| AI automatic missile target search | **yes** | `FindTarget` family **never picks an airborne unit** |
| Player Fire / Attack on it | **no** | can be picked and ordered |
| Missile and spell hits on it | **yes** | vertical band only (already public) |
| Its own ordinary missiles | **no** (🟡) | launched from the usual weapon height above the ground, not from its elevation |
| Leaving the map edge | **no** | same edge repel and leave-the-table rules |
| Deployment | **no** | starts grounded; nothing flier-specific |
| Night Goblin fanatics | **no** (🟡) | a fanatic still strikes an airborne unit it touches |

---

## B2. Item by item

### B2.1 Movement

- **Speed** ✅ no change. The per-update speed is the unit's M × 16 times the order factor (charge, pursuit,
  broken, …). It reads neither the flying state nor the terrain.
- **Terrain costs, rough ground, rivers, impassable terrain** ✅ no change. There is no terrain-type cost for anyone.
  Rivers, cliffs, lakes and walls stop movement only as `bnd_SOLID` areas
  (`movement_boundaries_route_finding.md`). The boundary repel that pushes a unit back to the allowed side runs for
  an airborne unit exactly as for an ordinary regiment. The repel skips only buildings, war machines, wagons,
  fanatics and inactive footprints, never by flight. **A Gyrocopter cannot fly across a river or a cliff that a ground
  regiment cannot cross.**
- **Obstacles and buildings** ✅ no change *for the flier as mover*. Its collision pass pushes it out of solid
  scenery and buildings with the same 2-D circle test and **no height comparison**. It also detours around them in
  route planning and live steering like any regiment (§B2.2).
- **Route planning** ✅ no change for the flier itself. Guides, detour trials and steering apply as on the ground.

### B2.2 Being an obstacle in other units' route steering ✅

The obstacle scan's relationship filter (`obstacle_steering.md` §3 rule 6) recognises regiment, building and wagon
footprints. An airborne unit's footprint is none of these, so it gets the **"scenery footprint: always blocks"**
branch:

- a ground unit (or another flier) detours around a hovering flier **whatever its side**: the enemy-is-hidden,
  enemy-is-broken, plan-trial, threat-range, "current target never blocks" and same-side speed/heading
  exceptions do **not** apply;
- rule 2 ("a footprint whose circle contains the waypoint is ignored unless it is an ordinary troop regiment")
  treats it as non-troop: a flier sitting on the mover's waypoint is ignored. Because the aim point on an airborne
  target is its **centre** (§B2.4), a unit heading for an airborne target is therefore not deflected by that target
  itself. It is deflected only by other fliers in the corridor.

The same plain-object treatment applies when a move destination is cleared away from occupied spots: a destination
inside a hovering flier's circle is moved out of it like one inside a scenery circle, whatever the flier's side 🟡.

### B2.3 Collisions and push-apart ✅

The collision pass (`script_behaviours.md` §2.2) runs for the **mover** against every other footprint. It
classifies the *other* footprint. It never looks at the mover's own flight state, and it never compares heights.

| Mover | Other footprint | Result |
|---|---|---|
| airborne flier | solid scenery | pushed apart (as on the ground) |
| airborne flier | building | pushed apart, or contact if charging / in melee (as on the ground) |
| airborne flier | war machine / wagon | as on the ground |
| airborne flier | ground regiment, same side | **pushed apart** (it cannot hover over its own troops) |
| airborne flier | ground regiment, enemy | fear-on-contact test of the flier, then **contact → engagement** (as on the ground) |
| airborne flier, broken (fleeing Gyrocopter) | ground enemy regiment | the enemy makes **contact attacks** on it (chase damage, as on the ground) |
| ground unit | **airborne flier** (either side) | **nothing**: no push, no contact, no fear test, no contact attacks, the flier is not woken |
| airborne flier | **airborne flier** | **nothing** |
| landed flier (ground kind) | anything | ordinary ground rules |

Notes:
- The reciprocal contact that a touched troops regiment receives names the flier. The touched unit's contact handler
  finds no regiment kind on the flier's footprint and does nothing. Its one-update contact latch is then cleared as
  usual on the next update without a collision (`script_behaviours.md` §2.8). 🟡 This is a harmless leftover, not
  an engagement.
- A hovering flier stops being airborne soon after it stops moving (§A3). Its collision pass runs only on its
  own re-check updates while it moves (`script_behaviours.md` §2.1). So "ground units pass under it" matters mainly
  while the flier is moving, and when a ground unit moves through a flier that is still descending.
- When a landed flier ends up overlapping a ground unit (it landed on top of it), nothing separates them until either
  unit runs a collision pass (moves, turns, re-forms).

### B2.4 Charges, attacks and close combat

**A ground unit charging or attacking an airborne flier** ✅
- The order itself is allowed: the player's Fire/Attack point pick includes airborne units
  (`player_missile_orders.md`). Charge declaration (`game_rules.md` "Fear and terror" case 2) and the target's
  "being charged" reaction (case 1, event 0x07) are unit-based and unchanged.
- The approach waypoint and the charge aim point on an airborne target are its **centre**. The "far side / approach
  side" point is used only for **troops** footprints (`target_queries.md` §5.1, `threat_events_nodes.md` §6 step 8).
  This answers the open question there: "regiment footprints" means **troops footprints only**. Monster, war machine,
  wagon, building and airborne footprints get the centre. An airborne Gyrocopter (normally troops) is therefore aimed
  at its centre.
- **Contact cannot happen while the target stays airborne** (§B2.3: ground movers ignore it). The charger runs its
  charge distance under or through the flier, and the charge ends as an ordinary charge that met nothing
  (`game_rules.md`; event 0x09 to the target when it was a free charge). An approach ends at the waypoint, under
  the flier.
- Contact is possible as soon as the flier is back on the ground (ground kind restored) and the attacker's
  collision pass runs. It also happens if the **flier** moves into the attacker (flier as mover, §B2.3).

**An airborne flier charging or attacking ground units** ✅
- Gyrocopter: charging keeps it airborne (action 3 is its take-off program). Its own collision pass makes contact
  with the ground target, and the contact handler engages exactly as on the ground (charger engagement, grid, 0x08
  and 0x0A, `terror_contact_charge.md` §1).
- Wyvern: a charge, pursuit or flight requests action 3, whose program **lands first**. It charges on foot. It can
  still make contact while it is descending, because it is the mover.
- Either flier moving under an **ordinary move** (airborne) into an enemy also makes contact and engages (the contact
  handler's non-charging branch: target := enemy, event 0x07 to the enemy).

**Close combat while airborne** 🟡
- Melee and the battle grid do not test the flying state, but they do choose by footprint kind.
  - The grid built around a defender is a full rectangle for war machine, wagon, building and monster footprints
    (`game_rules.md` "Engagement: battle grid and pairing") and an ordinary block grid otherwise. An **airborne** defender gets the
    ordinary block grid, even a Wyvern.
  - A unit attacking an opponent whose footprint is war machine / wagon / monster / building uses the separate block
    melee path (`game_rules.md` "charge bonus": "an attack against a war machine takes a different resolution
    path"). Against an **airborne** opponent the ordinary grid path is used instead.
- When does this happen? A Gyrocopter that goes into its fight (4) straight from a move, charge or shot **hovers**
  (§A3.2) and fights airborne; it lands only on a later rest request or a change of rest action (32 ticks, airborne
  until the elevation reaches 0). The Wyvern's
  **fight program does not land it**. A Wyvern that made contact while airborne (moving under an ordinary move) can
  therefore stay airborne while paired, until it is next given action 1, 3 or 5. 🟡 This needs a runtime check before
  anyone implements it deliberately. The simplest faithful model is: kind-dependent grid and melee choices read the
  **current** footprint kind.

### B2.5 Fear and terror ✅

`MayEngage` itself does not change. What changes is *where it is reached*:
1. Being charged (event 0x07 → op 0x42): unchanged. An airborne flier charged by a ground unit takes its fear
   test as usual, even though that charge can never reach it while it stays airborne.
2. Declaring a charge (op 0x4E): unchanged. A ground unit refuses to charge an airborne terror causer (e.g. the
   Wyvern) exactly as on the ground.
3. Fear on contact while moving: only the **mover** tests, and only against a ground regiment it touches.
   - an airborne flier moving into ground enemies tests its **own** fear of them, as on the ground;
   - a ground unit moving into an airborne terror- or fear-causing flier **never tests**, because there is no contact.

There is still no fear or terror test at a distance (`game_rules.md`).

### B2.6 Line of sight, visibility and spotting ✅

- **As a target and as a looker**: `IsVisible` (view cone, three rays, `SightEdge`) is computed between unit
  positions and does not look at the flight state. Spotting hidden units (`SpotHiddenUnits`, periodic behaviours)
  works for and against airborne units exactly as on the ground. There is no height in any sight rule, so flying
  does **not** let a unit see over scenery or `SightEdge` lines.
- **As a blocker** (rule-changing): a sight ray is blocked by every object that is neither a **troops** footprint nor
  camera-only and has a non-zero height (`map_objects_and_projectiles.md` §2 "Sight"). An airborne footprint is not a
  troops footprint, so an **airborne unit blocks other units' sight lines like scenery**, whatever its side. A
  grounded Gyrocopter (troops) does not. Side fact found on the way: **monster, war machine, wagon and building
  footprints block sight even on the ground**, so a landed Wyvern blocks sight too.
- A unit's own footprint never blocks its own view, and a blocker whose circle contains the looker does not block. Both
  follow from the ray test's geometry: the angular half-width is undefined when the looker is at or inside the
  circle, and the test then fails. 🟡 Treat both as "does not block".
- The target's own footprint never blocks the ray to itself: only objects strictly nearer than the target are tested.

### B2.7 Shooting

- **Flier as target, player orders** ✅: the Fire/Attack point pick includes airborne units. `TargetValid`, range
  and arc are unit-position tests and do not change.
- **Flier as target, AI search** ✅ (rule-changing): the weapon-target search (`FindTarget`, `FindTargetOfClass`,
  `FindTargetAnyRange`, `FindTargetOfClassAnyRange`, `FindNewTarget`; `threat_events_nodes.md` §2.1 "unit footprints
  (not scenery, not buildings)") considers only troops, war machine and monster footprints. An **airborne unit is
  never found**, while a landed one is. The friendly-crowding check of independent units (`threat_events_nodes.md` §2.1 rule 4) likewise
  ignores **airborne friends**. The other searches (threat search, attack-the-nearest, `UnitScore`/`PickBestTarget`,
  `DetectThreat`) walk the units themselves and include airborne units as usual.
- **Crossbow friends-on-the-line check** (`target_queries.md` §3): it tests only troops and camera-only objects, so an
  airborne friendly Gyrocopter over the line does not block a crossbow volley.
- **Hits on an airborne unit** are already public: the vertical band `elevation ≤ h ≤ elevation + 16`
  (`spell_effects.md` §4.1, `ranged_combat_handoff.md` blast rule). Height-0 area spells never touch it
  (`spell_area_effects.md`, `spell_blades_flock_items.md`). The aim height on an airborne unit is half its height
  plus its elevation (`spell_effects.md` §2.1).
- **Flier as shooter** 🟡: ordinary missiles start at the ground under the shooter plus the weapon's usual launch
  height. The elevation is **not** added. Only the Gyrocopter bomb (dropped from its elevation,
  `ranged_combat_handoff.md`) and the spells/innate attacks listed in `spell_effects.md` (Gaze of Mork from a flying
  caster's elevation) start from the elevation. The bomb order is refused unless the craft is airborne (GMTXT 2020,
  public).
- **Arc** ✅: unchanged (facing-based, no height).

### B2.8 Leaving the map edge, table edge ✅

No change. The battle-edge repel and the "leaving the table" boundary are applied to the unit's position by the same
rules as for a ground regiment (`movement_boundaries_route_finding.md`).

### B2.9 Deployment ✅

No change. Fliers are created with their ground footprint kind and start on the ground. Deployment placement and its
repeated collision passes treat them as ordinary units. No deployment rule mentions flight.

### B2.10 Fanatics 🟡

A released Night Goblin fanatic's per-model strike test chooses its victim by the touched unit's **class**, not by its
footprint kind, and has no height test. It therefore strikes an airborne unit it passes through, exactly as a ground one
(`fanatic_collisions.md`).

### B2.11 Flying Bower "lifted" state is a different thing ✅

The Flying Bower's lifted-off-the-map state (not drawn, cannot engage or be engaged,
`spell_channelled_effects.md`) is set **only** by the Flying Bower effect. Ordinary fliers never use it, and nothing
in this report applies to it.

---

## B3. Addendum — over or around? (implementer's questions)

1. **Over or around buildings, scenery, walls, trees, rivers, ground units?** **Around**, exactly like a ground
   regiment. As a mover, an airborne unit steers around and is pushed out of solid scenery, buildings, and friendly
   ground regiments. It makes contact with enemy regiments, and it is repelled by solid boundaries (rivers, cliffs,
   walls drawn as areas). The only thing it passes through is **other airborne fliers**. Ground units, conversely,
   pass through an airborne flier.
2. **Height comparison?** **None.** No movement, push-apart, steering or boundary rule compares the flier's
   elevation with an object's height or with the terrain. A low hedge (height 10) and a tall tower (height 150) block
   an airborne Gyrocopter equally. Height comparisons exist only for missiles and spells (§B2.7).
3. **Boundaries and impassable areas?** Still apply, unchanged.
4. **Elevation reference?** Above the ground under the unit (§B0.2). It follows the terrain, so a hill never rises
   above a flier. It does not matter for movement anyway, since movement ignores terrain height.
5. **Fliers vs fliers, fliers vs ground units under them?** Two airborne fliers never collide. An airborne flier
   **does** collide with ground units it moves into (pushed by friends, contact with enemies). A ground unit moving
   into an airborne flier does **not** collide with it. The rule is asymmetric because the collision pass is run by
   the mover and classifies only the other footprint.

---


---

# Test vectors

## A. Flying state, drawing, death

| # | before | action | after |
|---|---|---|---|
| 1 | Wyvern standing, elevation 0 | move order (action 2) at tick 1 | t1–4 flap frames on the ground; t5 elevation 4 (flying); … t40 32; t41+ fast flap loop |
| 2 | Wyvern flying at 32, moving | halts; rest action 1 | 40-tick landing: 28 at t5 … 0 at t40 (ground from t40); stand loop |
| 3 | Wyvern flying at 32 | charge (action 3) | lands over 40 ticks while the charge moves it; then walks on the ground (group 0) |
| 4 | Wyvern landing, elevation 16 | new move (action 2) | no take-off; keeps flying at 16 |
| 5 | Wyvern flying at 32 | AI cast (action 7) | cast pose at 32; then action 2 fast flap at 32 (not landed) |
| 6 | Gyrocopter (Infantry or Archers file) on the ground | move | take-off: 4 at t4 … 32 at t32; rotor loop |
| 7 | Gyrocopter flying, arrives | rest action 1 (first request after the move program) | hovers at 32, slow rotor; Ctrl-Fire bomb allowed |
| 8 | Gyrocopter hovering (#7) | `SetActionState 1` (same action again) | lands: 28 at t4 … 0 at t32; bomb now refused (`GMTXT 2020`) |
| 9 | Gyrocopter hovering | gets a current target (rest action 5) | lands (32 ticks) |
| 10 | Wyvern at 32, killed | death | figure glides 2/tick in a random direction for 40 ticks; corpse frame t41; t42: radius-72 S5 blast, damage kind 2, no messages; medium shake |
| 11 | #10, an enemy 20-model unit, footprint 40, crash point 50 from its centre | blast | margin: n = (40 + 72 − 50) × 20 / 112 = 11 (integer) random models at S2, 1 wound each, saves |
| 12 | #10, a friendly unit whose footprint contains the crash point | blast | every model S5, D6 wounds, saves; kills credited to the dead Wyvern's unit |
| 13 | #10, another flyer at 32 over the crash point | blast | not hit |
| 14 | Gyrocopter at 32, killed | death | 8 smoke puffs at 36…12, then 0; wreck t33; t34 explosion sprite + blast (fire, kind 1) + medium shake |
| 15 | Gyrocopter at 8 (mid take-off), killed | death | counts as in the air: full 32-tick fall program, elevation 4 at t4, 0 at t8; blast + shake at t34 |
| 16 | Wyvern on the ground, killed | death | corpse frame at once; no glide, no blast, no shake |
| 17 | flyer at 32 on a slope, ground 40 under the figure | drawing | sprite base at 72 (terrain 40 + 32) |
| 18 | arrow at height 30 above ground passing a flyer at 32 | flight test | not hit (30 < 32); at 32…48 hit |


## B. Rules while airborne

World units; F = flier, elevation E (0 < E ≤ 32 means airborne). Radii are footprint radii.

| # | Before | Action | After |
|---|---|---|---|
| 1 | Gyrocopter F airborne (E = 32), moving east under an ordinary move; a solid scenery circle of height 150 overlaps it | F's collision pass | F pushed out of the circle by `(|o|+2)/2` along the centre line (same as a ground regiment) |
| 2 | Same, but the scenery circle has height 10 (< E) | F's collision pass | **same push**: no height comparison |
| 3 | Same, but the object is `os_active` only (not solid), height 2 | F's collision pass; F's steering scan | no push; steering still detours around it (`obstacle_steering.md`, same as on the ground) |
| 4 | F airborne crosses a hill 60 units high in `GRND.GD` | moves over it | no effect on movement or speed; E stays 32 above the ground at each point; its hit band rises with the ground |
| 5 | F airborne moving towards a `bnd_SOLID` river area | boundary repel | repelled to the allowed side exactly as a ground regiment |
| 6 | F airborne moves into friendly infantry block I (stationary) | F's collision pass | F pushed away from I; I gets its re-check state (ordinary push-apart) |
| 7 | Friendly infantry I moves into hovering friendly F (F airborne, stationary or not) | I's collision pass | **nothing**: I not pushed, F not woken; they overlap |
| 8 | Two airborne fliers F1, F2 overlap | either's collision pass | nothing |
| 9 | Enemy cavalry C charges airborne Gyrocopter F; F keeps moving under an ordinary move (stays airborne) | C's charge run | C's fear test at declaration as usual; no contact during the run; the charge ends when its distance is spent (event 0x09 to F if it was a free charge). C's aim point = F's centre |
| 10 | Same, but F stops and lands (E reaches 0) before C arrives | C's collision pass after landing | ordinary contact → C engages F as charger; F's footprint is troops again |
| 11 | Airborne Gyrocopter F charges enemy infantry I | F's collision pass on overlap | F tests its own fear of I; contact → F engages I as charger (grid around I, charge counter to F, 0x08 + 0x0A to I); straight from the charge, F's fight program hovers (§A3.2): it fights airborne until a later rest request lands it |
| 12 | Wyvern W ordered to charge enemy I | action 3 | W lands (descends 4 per step to 0), then charges on foot as a monster block |
| 13 | Enemy infantry I (no immunity) walks into an airborne Wyvern (terror) | I's collision pass | **no terror test, no flight, no contact**; I passes through |
| 14 | Airborne Wyvern W moving under an ordinary move into enemy I | W's collision pass | W's own fear test vs I; contact → W engages I (event 0x07 to I) |
| 15 | Ground archer looker L, target T at 300; airborne friendly Gyrocopter F (radius 12, height 16) at 150 exactly on the line | `IsVisible(L → T)` | the ray through F is blocked (F counts as scenery); T visible only if another of the three rays is clear |
| 16 | Same, F grounded (troops) | `IsVisible(L → T)` | F does not block |
| 17 | AI bow unit S (R = 576); enemy airborne Gyrocopter F at 200; enemy infantry I at 500 | `FindTarget` | target = I (F is never a candidate while airborne) |
| 18 | Same, only F present | `FindTarget` | target cleared, false; after F lands: target = F |
| 19 | Player selects bowmen, clicks Fire on airborne F | Fire order | accepted, F becomes the target; missiles hit F only at heights E…E+16 |
| 20 | Airborne Gyrocopter F at E = 32 shoots an ordinary missile | launch | start height = ground under F + the weapon's usual launch height (E not added) 🟡 |
| 21 | Gyrocopter F on the ground, Ctrl+Fire | bomb order | refused (GMTXT 2020); airborne: bomb dropped from E |
| 22 | Battle start, deployment | – | every flier on the ground with its ground footprint kind |

---


---

# Engine-model differences

| Engine now | Original |
|---|---|
| `airborne` fixed at load, Gyrocopter only | dynamic; Gyrocopter **and Wyvern**; starts grounded; follows the animation action (§A3) |
| airborne base height 72 | elevation 0…32 above the ground (§A2); band `E…E+16` |
| collisions ignore airborne | flier as **mover** collides normally; **others** ignore an airborne flier; two fliers ignore each other |
| steering ignores airborne | airborne footprint is a **scenery** obstacle for everyone else's steering |
| charges/close combat ignore airborne | ground units cannot contact an airborne flier; aim point = centre; airborne grids use the ordinary layout |
| terror ignores airborne | no fear-on-contact when a ground unit walks into an airborne causer |
| (not modelled) | airborne units block sight like scenery; AI `FindTarget` family skips them; crossbow line check and friendly-crowding check ignore airborne friends |
| spells, missiles, bomb read `airborne` | keep, but with the dynamic state and the real elevation |

# 🟡 Open items


- Gyrocopter: which events in normal play give the "second" rest request that lands a hovering Gyrocopter (timed
  waits, re-request on re-arrival after pushes, script requests) — watch in Wine.
- Re-form after a Wyvern halt: the re-form start requests action 2 before the arrival requests 1; a Wyvern may
  begin to take off again for a few ticks before landing — watch.
- §5.3 corpse drawn on the ground during the fall; glide start/end tick.
- No shadow under raised figures (by eye).

1. The table in §0.1 uses the unit-wide default action. Per-model action requests (re-form walks, slot walks)
   can override it for individual models; §A3 gives the programs per action.
2. Airborne close combat for the Wyvern (§2.4): reachable in principle, never observed.
3. The ordinary-missile launch height from an airborne shooter (§2.7).
4. Destination clearance around a hovering flier (§2.2, last paragraph).
6. The self/inside-circle sight exemption (§2.6) rests on the geometry of the ray test (undefined half-width), not on
   an explicit rule.

