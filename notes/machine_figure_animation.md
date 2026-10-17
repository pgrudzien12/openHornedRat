# War-machine figure animation: the machine model's action table

Public behavioural report (batch 14; companion of [`runaway_routers_broken.md`](runaway_routers_broken.md)) for the implementer question "what does the machine figure of a war machine show
while its crew stands, fights, walks or routs, and when it is destroyed". Behaviour only.

**Read first, not re-derived here:**
- `game_rules.md` "Figure animation: actions, timing, and why the figures are never in step" — the seven action ids,
  one script word per tick, random entry, the rule "re-issuing the current action does nothing", collapse delay,
  drawn-facing slew, death kinds.
- `script_animation_sound.md` §0 — the unit's one-tick action broadcast, the model's own pending request, the
  animation request (event, divisor, countdown) and `PlayLeaderAnimation` (countdown 1, divisor 1).
- `leader_figure_sprite.md` — every figure animates from **its own sprite set**; the machine is the leader figure.
- `game_rules.md` "Formations" (war-machine layout, anchoring) and `animations.md` (group layouts per file).
- `ranged_combat_handoff.md` / `script_shooting.md` — what the posted fire event does (projectile, misfire).

Frame numbers below are `frame = group_base + phase × 8 + direction`, exactly as in `animations.md`.

## 0. Shared state (read this first)

### 0.1 Which figure gets which family

- **The animation family is the figure's sprite set.** There is one 8-slot action table per sprite set (several sets
  share a table, §2). Nothing about the unit's class, the figure's role or the unit's state selects the table.
- In a war-machine unit the **first figure (the leader) carries the leader block's `troopsprites`** — the machine set
  (`Mortar`, `Cannon`, `GrtCannon`, `VolleyGun`, `RockLobber`, `DoomDvrCatapult`) — and therefore the **machine
  family**. Every other figure carries the unit's `troopsprites` — the crew set — and the crew family (standard
  infantry for `NulnHalberdiers`, `OrcBoyz` …; the Doom Diver family for `DoomDiver`, §2.6).
- So the engine's current fallback (machine figure → standard-infantry table) is wrong: the machine figure must use
  the machine set's own table. With that table, **actions 1–5 all show one held frame** (§1), so fight / weapon-ready
  never animate the throwing arm.
- Single-figure "machines" (Doomwheel, Warpfire Thrower, Gyrocopter) have only the leader figure; it uses the leader
  block's set (the Doomwheel's troop set is `VoidType`).
- Limbered guns (`MrtWagon`, `ImpCWagon`, `GrtCWagon`, `VollyWagon`) are RollingStock units: the leader figure is the
  limber/gun wagon, the other figure the team (`PackPony`) (§2.8).

### 0.2 The machine figure receives requests like any figure

There is **no exclusion** of the machine figure from the action broadcast or from per-figure requests:

- The unit's broadcast (rest action after a halt, 2 at a move/turn start or re-form, `SetActionState`,
  `PlayUnitAnimation`) is applied to **every** figure without its own pending request, the machine included.
- Close combat: when the machine unit is the grid owner, its figures — the machine included — are written onto the
  grid as one block, and the owner's free figures that are next to an enemy figure are paired (request 4); a figure
  arriving in melee without an opponent asks for 5. 🟡 Whether the machine figure is in practice ever adjacent/paired
  was not traced to completion — **it does not matter for the picture**, because 4 and 5 show the same held frame as 1
  for every machine family (§1). (A machine unit that *joins* a block fight never places its machine figure.)
- The rest action itself never picks 5 for an anchored war machine (`script_animation_sound.md` §0.1): with a
  target it still chooses 1.
- Shooting: artillery orders **only the machine figure** (`PlayLeaderAnimation 7 …`, the leader's own pending
  request), so the crew never play a shoot pose for the machine's shot.

### 0.3 The machine's shot locks out requests (drops, not queues)

Every machine shoot program (and the wizard cast pose) puts the figure in the **locked** state for the whole shot:
any request that arrives — broadcast or own — is **dropped**, not queued. The program ends by switching itself to
action 1 (stand), which clears the lock. Consequences:

- A melee pairing, a rest broadcast or a script `SetActionState` during the shot is lost; the machine still
  finishes the shot and returns to *stand*, never to the dropped action. (Visually nothing is lost: 1–5 look the same.)
- Death still wins: the collapse timer (`game_rules.md`, staggered collapse) clears the lock and forces action 6 when
  it expires, even mid-shot.
- Because the posted fire event happens part-way through, a machine that is hit mid-shot still launches.

> Settled (#344, `script_animation_sound.md` §0.5): the **standard archer shoot program does not lock** the figure (a
> new request interrupts it), while the wizard cast pose and all machine shots lock with *drop* semantics. Queuing
> is used only by the timed charge/rout pause (and machine wrecks). Death is not a queue: a dying figure takes
> requests until it collapses, and a corpse drops them. `game_rules.md` and `script_animation_sound.md` §0.1 are
> corrected.

### 0.4 Drawn facing

Every machine program (stand, idle, walk, fight, ready, shoot) makes the figure face **the unit's facing**
(slewing 22.5° per tick as usual). A machine therefore never turns to face a melee opponent or its travel direction.
Wreck programs **freeze** the facing where it was — **no random facing** for machine wrecks (unlike corpses).
Exceptions: the Doomwheel faces its own heading while rolling (§2.5); the Doom Diver crew faces its heading while
flapping.

### 0.5 The machine never "walks"

War machines are anchored at set-up (`game_rules.md`), so the machine figure does not travel with move orders.
When the crew walk to new slots after casualties, only the walking figures ask for 3; the machine stays at rest.
Even if a 3 reaches the machine (broadcast, rout start — the rout start asks every figure at rest for 3 after its
pause), its walk program is the same held frame. 🟡 Whether a routing war-machine unit drags its intact machine
figure along was not traced; the library scripts only let the crew flee once the machine is destroyed
(`script_queries.md` B3), and a destroyed machine is a wreck that has already left the roster.

## 1. The common machine table (Cannon, Great Cannon, Volley Gun, Rock Lobber, Doom Diver catapult, Mortar)

| action | program |
|---|---|
| 1 stand, 2 idle, 3 walk, 4 fighting, 5 weapon ready | intact group, **phase 0, held forever** (one static frame, faces unit facing) |
| 6 dead | wreck group, phase 0, held forever; figure leaves the roster when the program starts; facing frozen; **never burns** (death kind ignored) |
| 7 shoot | locked (§0.3); random entry 0…3 skips into the lead-in; frame sequence and fire step per family (§2); then switches to 1 |

Changing between 1–5 restarts the program, but since it is one held frame there is no visible change. There is no
random entry anywhere except the shoot lead-in.

Collapse timing is the ordinary rule: a machine killed by ordinary wounds (melee automatic hits, kind 0) keeps its
intact frame for the collapse delay (18/36/54/72 ticks if its unit is in close combat, 5/10/14/19 otherwise), then
shows the wreck; missile / slain-outright kills (kind 2, including the misfire "destroyed" result) collapse after
1 tick.

## 2. Per family

`r` = the random entry 0…3 rolled when the shoot request applies. Ticks are counted with the tick on which the
request is applied as tick 1. "fire" = the event step (`script_animation_sound.md` §0.3): it takes a tick of its own
during which the frame does not change.

### 2.1 Cannon (`IMPCANON`) and Great Cannon (`GRTCANON`) — one shared table

| | group | frames |
|---|---|---|
| intact (1–5) | 8 | 8–15 |
| wreck (6) | 0 | 0–7 |
| shoot (7) | 8 | unchanged frame throughout |

Shoot: ticks 1 … 6−r intact; tick 7−r: a **muzzle puff** effect is spawned 24 units ahead of the **unit position**
(not the machine figure; rotated by the unit facing, `volley_gun_shot.md` §4), 12 units up — battle-effects sprite set, a 4-tick, 4-frame one-shot (frames 110–113 of
`GENBATT` 🟡 by eye) — **and** the fire step; ticks 8−r … 11−r intact; tick 12−r back to stand. The gun itself never
changes frame; the shot is shown by the puff and the projectile.

### 2.2 Volley Gun (`VOLEYGUN`) — same frames as 2.1, its own shot

Intact 8–15, wreck 0–7. Shoot (three independent random entries r0, r1, r2, each 0…3):
`6−r0` intact ticks → puff + **unconditional event post** (one tick) → `4−r1` intact ticks → puff + unconditional event
post (one tick) → `4−r2` intact ticks → puff + the ordinary fire step (one tick) → 4 intact ticks → stand.
So one shot shows **three puffs** and posts the unit's animation-request event **three times**: twice without
consulting the countdown and without a figure reference, once through the normal countdown step. ✅ Each post is
handled as an ordinary event 34 and **launches its own projectile** (the two extra ones from the unit position, each
with its own misfire roll, scatter and reload re-stamp): `volley_gun_shot.md`.

### 2.3 Rock Lobber (`ROCKLOB`) and Doom Diver catapult (`DDCATPLT`) — one shared table

| | group | frames |
|---|---|---|
| intact (1–5) | 0, phase 0 | 0–7 (arm down, loaded) |
| wreck (6) | 32 | 32–39 |
| shoot (7) | 0 | phases 0,1,2,3 |

**The "fire" group is the stand group**: its phase 0 is the rest frame used by actions 1–5; phases 1–3 (arm thrown,
frames 8–31) appear **only** inside the shoot program.

Shoot: ticks 1 … 4−r phase 0; tick 5−r fire step (phase 0 still shown); ticks 6−r and 7−r phase 1; tick 8−r phase 2;
tick 9−r phase 3; tick 10−r phase 0; tick 11−r stand. The event (launch) precedes the arm swing.

Wreck differences: Rock Lobber's wreck is plain locked; the Doom Diver catapult's also keeps the "face unit facing"
mark — both freeze the facing in practice. (Implement both as "facing frozen".)

### 2.4 Mortar (`MORTAR`)

| | group | frames |
|---|---|---|
| intact (1–5) | 40 | 40–47 |
| wreck (6) | 0 | 0–7 (the overturned mortar) |
| shoot (7) | 40 then 8 | 40 → 8, 16, 24, 32 (smoke) → 40 |

Shoot: ticks 1 … 4−r frame 40+d; tick 5−r 8+d; tick 6−r 16+d; tick 7−r fire step (16+d held); tick 8−r 24+d;
ticks 9−r, 10−r 32+d; tick 11−r 40+d; tick 12−r stand (40+d).

**Correction to `animations.md`**: the MORTAR labels "nibble 1 ready … nibble 3 third pose (?)" are the other way
round in use — group 0 (frames 0–7) is the **wreck** (confirmed by eye: a toppled mortar, consistent with "nibble 1 is
always the wreck"), group 40 (frames 40–47) is the **intact / rest** frame, group 8 (frames 8–39) the firing smoke.

### 2.5 Doomwheel (`DWHEEL`) — crewless, self-moving, single figure

| action | program |
|---|---|
| 1 stand, 5 weapon ready | group 8 phase 0 held; faces unit facing |
| 2 idle, 3 walk, 4 fighting, 7 shoot | group 8, **flat 4-tick loop `0,1,2,3`, no random entry**; faces its own heading (travel/opponent) |
| 6 dead | group 0 (frames 0–7), phase 0, held; facing frozen; never burns |

So the wheel rolls (frames 8–39) whenever it moves, marks time, fights or "shoots", and stands still on 1 and 5.
Changing between 2, 3, 4 and 7 **restarts the loop at phase 0** (they are different actions sharing one loop), a small
visible hitch. Its shoot program has **no fire step**: the Doomwheel's lightning is not timed by its animation.

### 2.6 Doom Diver crew (`DOOMDIVR`) — the catapult's crew figures

| action | program |
|---|---|
| 1 stand, 4 fighting, 5 weapon ready | group 0 phase 0 held; faces unit facing |
| 2 idle, 3 walk | group 0, 10-tick loop `0,0,0,1,1,2,2,2,3,3`, **no random entry**; faces own heading |
| 6 dead | burns on kind 1/3 (battle-effects sequence of `game_rules.md`), else corpse group 32 (frames 32–39) with a random facing |
| 7 shoot | none (no program — the figure keeps its current frame) |

The crew never shows a fighting pose. Groups 40, 48 and 56 of the file are **not used by this table** (verify:
probably the diver in flight, drawn by the projectile).

### 2.7 Warpfire Thrower (`WARPFIRE`) — single figure, no machine model

Monster-type single figure, not a war machine (no anchoring, no machine figure). Its shot is ordered to the whole
unit (its troop and leader sets are both the Warpfire set), not to a leader figure.

| action | program |
|---|---|
| 1 stand, 4 fighting, 5 weapon ready | stand group 48, phase 1 held; faces unit facing — **no attack pose** |
| 2 idle | group 48, 10-tick loop `0,0,0,1,1,2,2,2,3,3`, no random entry |
| 3 walk | group 0, 8-tick loop `0,0,1,1,2,2,3,3`, random entry 0…7 |
| 6 dead | burns (kind 1/3) or corpse group 32 with random facing, then the five puffs and blast already in `game_rules.md` |
| 7 shoot | locked; group 40 phase 0 for `10 − r` ticks, then stand; **no fire step** (the flames are timed elsewhere) |

### 2.8 Limbered guns (`MrtWagon`, `ImpCWagon`, `GrtCWagon`, `VollyWagon`) — RollingStock leaders

| set | 1, 3, 4, 5 | 2 idle | 6 dead |
|---|---|---|---|
| `MrtWagon` | group 0 phase 1 held | group 0, 8-tick loop `0,0,1,1,2,2,3,3`, no random entry | switches to the **Wagon** set's dead program (Wagon wreck, group 64 of `WAGON`) — the same chain as `Caravan` |
| `ImpCWagon` / `GrtCWagon` / `VollyWagon` (one shared table) | group 0 phase 0 held | same held frame | group 8 (frames 8–15), held, facing frozen |

No shoot program (slot empty). `MRTWAG` is one 4-phase rolling group (frames 0–31), so its held frame is 8 + d and
its idle loop rolls the wheels; the `*CWAG` files have one 1-phase intact group (0–7) and the wreck (8–15).
(verify the frames in the viewer.)

### 2.9 Gyrocopter (`GYROCOPT`) — single flying figure (brief; 🟡)

Not crewed. Actions 2, 3 and 7 share one program: if the figure is on the ground it first **takes off** (32 ticks:
two laps of a 12-frame rotor sequence with an altitude step of +4 every 4 ticks, up to 32), then loops the rotor
`0,1,2,3,1,2` (6 ticks). Actions 1, 4 and 5 share another: if the figure came **straight from** the 2/3/7 program it
**hovers** (keeps its height); otherwise, if flying, it **lands** (corrected October 2026, `airborne_units.md` §A3.2) (the same 32 ticks with −4 steps), then loops a slow rotor
`0,0,0,1,1,1,2,2,2,3,3,3,1,1,1,2,2` (17 ticks). Dead: in the air it falls for 32 ticks with smoke puffs, then wreck
group 32 with a blast (radius 72, fire damage) and a medium camera shake (`camera_shake.md`; corrected: not a battle message); on the ground, wreck group 32 held. The
hover rule, the timing and the blast are specified in `airborne_units.md` §A3.2 and §A5; its shoot has no fire step.

`MoleMachine` uses its own non-directional frame loops and a demolition sequence; out of scope (3D mesh unit).

## 3. Family map (sprite set → table)

| table | sprite sets |
|---|---|
| gun (2.1) | `Cannon`/IMPCANON, `GrtCannon`/GRTCANON |
| gun stand/dead + volley shoot (2.2) | `VolleyGun`/VOLEYGUN |
| thrower (2.3) | `RockLobber`/ROCKLOB, `DoomDvrCatapult`/DDCATPLT (dead programs differ only in the frozen-facing detail) |
| mortar (2.4) | `Mortar`/MORTAR |
| Doomwheel (2.5) | `DoomWheel`/DWHEEL |
| Doom Diver (2.6) | `DoomDiver`/DOOMDIVR |
| Warpfire (2.7) | `WarpFireThrower`/WARPFIRE |
| limber (2.8) | `MrtWagon` (own table); `ImpCWagon`, `GrtCWagon`, `VollyWagon` (shared) |
| crew | whatever set the unit's `troopsprites` names — e.g. `NulnHalberdiers` (Mortar crew, standard infantry table), `OrcBoyz` (Rock Lobber crew) |

## 4. Test vectors

Direction `d` = the drawn direction (unit facing for machines). All use `frame = group + phase × 8 + d`.

| # | before | request | frames / result over ticks |
|---|---|---|---|
| 1 | Rock Lobber machine at rest (action 1), d = 2 | crew paired in melee; machine receives 4 | frame 2 every tick (no change, no arm movement) |
| 2 | same | 5, then 1, then 4 | frame 2 every tick |
| 3 | Rock Lobber, action 1, d = 0 | leader shoot 7, r = 0 | t1–t4: 0; t5: 0 + fire event; t6–t7: 8; t8: 16; t9: 24; t10: 0; t11+: 0 (stand) |
| 4 | same, r = 3 | 7 | t1: 0; t2: fire event (0); t3–t4: 8; t5: 16; t6: 24; t7: 0; t8+: stand |
| 5 | Rock Lobber mid-shot (t6 of #3) | broadcast 4 (crew charged) | dropped; frames continue 8, 16, 24, 0, then stand (action 1); a later 4 (next pairing change) is applied normally |
| 6 | Cannon, action 1, d = 4 | 7, r = 1 | t1–t5: 12; t6: puff spawned + fire event (12); t7–t10: 12; t11: stand (12) |
| 7 | Mortar, action 1, d = 1 | 7, r = 0 | t1–t4: 41; t5: 9; t6: 17; t7: fire (17); t8: 25; t9–t10: 33; t11: 41; t12+: 41 stand |
| 8 | Volley Gun, d = 0 | 7, r0 = r1 = r2 = 0 | t1–t6: 8; t7: puff + event; t8–t11: 8; t12: puff + event; t13–t16: 8; t17: puff + counted fire event; t18–t21: 8; t22: stand |
| 9 | Great Cannon machine killed by melee automatic hits, unit in close combat, stagger & 3 = 1 | lethal wound | 36 ticks of the intact frame (8 + d), then 0 + d held, facing frozen; figure off the roster from that tick; no fire/burn even for a fire kill |
| 10 | Mortar machine, misfire "destroyed" (kind 2) | lethal | next tick: frame 0 + d (wreck) held |
| 11 | Doomwheel, action 1, heading 3 | move order (walk 3) | t1: 8 + 3; t2: 16 + 3; t3: 24 + 3; t4: 32 + 3; t5: 8 + 3 … (direction follows its heading) |
| 12 | Doomwheel rolling (action 3) at phase 2 | 4 (contact) | restarts: 8 + d, 16 + d, 24 + d, 32 + d … |
| 13 | Doomwheel | 6 | 0 + d held |
| 14 | Warpfire Thrower, action 1, d = 6 | 4 or 5 (melee) | 48 + 8 + 6 = 62 held |
| 15 | Warpfire Thrower | 7, r = 2 | t1–t8: 40 + d; t9: stand 56 + d |
| 16 | Doom Diver crew figure | 4 | 0 + d held (no attack pose) |
| 17 | Mortar unit at rest with crew re-forming after a casualty | crew walk (3, own requests) | machine keeps 40 + d; only the walking crew animate |

## 🟡 Open / verify

- Whether the machine figure is ever paired (4) in practice; irrelevant visually.
- Whether a routing war-machine unit moves its intact machine figure.
- Volley Gun's two extra event posts: how the shooting script launches them.
- Muzzle-puff frames (`GENBATT` 110–113, 1 tick each) by eye.
- `DOOMDIVR` groups 40–63 and `MrtWagon` held frame — visual check.
- Gyrocopter take-off / landing / hover branch and its crash blast.
- The archer-shoot lock discrepancy in §0.3 side note.
