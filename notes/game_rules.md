# Game rules — unit stats, combat, morale and shooting

This is a behavioural specification for the original game. Findings are based on corroborating game data, runtime observation where available, and internal research. It records what the game does so that the engine can be implemented independently; it does not reproduce original source code or implementation artefacts.

- ✅ **established**: the code path was read (function address, what it reads, the formula), and/or a
  data table matches a known chart, and/or the data agrees across all units;
- 🟡 **hypothesis**: consistent with the code or data but not fully traced, with the reason given.

Pre-battle rules and the complete regiment-action availability table are maintained in
[deployment.md](deployment.md).

## Key findings

1. **Stat layout** ✅ Each `setstats` value is one byte of a fixed block (consecutive in token order);
   a line fills consecutive fields from its key. `s_move` = M WS BS S T W I A Ld, `s_mount` =
   mount, armour code, weapon class, race, points, missile weapon (section 3).
2. **Charts** ✅ To-hit, to-wound and strength save modifiers are exactly the WFB 4th edition charts.
3. **Armour** ✅ Codes 1–4 = 6+…3+, mounted codes 8–13 one better (capped at 2+), 6 = regeneration: a 4+ save in
   close combat, but **regenerating models are never wounded by missiles**. **Code 5 gives no save**, almost
   certainly a table bug that affects some leaders (and an armour item upgrades it to regeneration).
4. **Close combat** ✅ Units strike in the segment equal to their Initiative (10 → 1). A model fights
   when it holds a battle-grid cell orthogonally next to an enemy model (no rank rules). Two-handed +2 S,
   spear/halberd +1 S; after a charge the first `floor(1.5 × frontage)` attacking models get +1 S;
   +1 WS when ganging up on an enemy model that fights someone else. Only monsters strike back
   immediately. Hatred re-rolls misses in the first round, frenzy doubles attacks; mounts attack with
   their own profile; leaders' magic items modify the profile.
5. **Combat result** ✅ Kills + rank bonus `size / width − 1` (no +3 cap) + rear +2 / flank +1, summed per
   side over all units sharing a battle grid; no standard bonus. Resolved once per turn at the grid's
   creation segment: first two turns after contact, then every 1–2 turns.
6. **Leadership** ✅ `modifier + (rand % 11 + 2) <= Ld` of the leader: a **uniform 2–12 roll, not 2D6**.
7. **Morale** ✅ Break test at the losing margin; beaten by a fear-causer = break; hatred = pass on
   10 or less. Panic at every lost quarter of original strength (casualties only). A charge into the rear
   or the rear half of a flank forces a Leadership test. Failed fear tests and any contact with a
   terror-causer mean flight. Routed units run straight away from their opponent and leave the table;
   pursuers get automatic hits while in contact; rally and pursuit restraint are rolled only on the
   player's order (or for units with the "independent" toggle).
8. **Shooting** ✅ No to-hit chart: a projectile flies to a point scattered by `rand % (11 − BS)` steps
   per axis (step grows with distance; +8 behind scenery). Archers fire one projectile per 4 models,
   artillery one; targets must be in the 90° front arc and in range; reload `(10 − I) × 18` ticks minus a
   weapon constant. Arrows wound one model; blast weapons wound every model of a unit they land in or
   fly into, and S/2 models in the margin. Ranges at 24 units per inch. Shooting into close combat is
   allowed. Artillery misfires on a 6, explodes on a following 1.
9. **Unit behaviour is bytecode** ✅ Every unit runs a script through a 232-opcode interpreter that
   consumes queued events (rout, charged, rally…) and decides the consequences. The scripts are data in
   `SCRIPT/BFxxx.DLL`: ids from 0 per mission (3–37 scripts), 100–170 a shared library identical in all 45 DLLs.
10. **Player commands** ✅ Orders are button codes executed by the unit scripts; a "fight harder" button gives the
    focused unit in melee +1 S and +1 Leadership for one segment; an "independent" toggle lets a unit rally,
    react and pick targets on its own.
11. **Time and movement** ✅ One tick per 100 ms timer message (≤ 10 ticks/s, no catch-up); 19 ticks per segment,
    10 segments per turn = 19 s. M only feeds a speed stat `s_rlmv = trunc(4.8 × M + I) / 2`; units move
    `s_rlmv × k / 16` units per tick (k 1.8 free, 1.0 closing, 2.5 charging, 1.5 fleeing); terrain does not slow
    them; units wheel on a front corner. That speed moves only the unit's own reference point — the models chase
    it separately at a rank-dependent rate with no charge multiplier, so a charging block visibly stretches and
    its rear rank cannot keep station. Routes use a reactive steer-around controller (no path graph); units push
    apart on overlap; visibility is a 100° cone blocked by scenery and `SightEdge` lines, never by terrain height.
12. **Magic** ✅ Each side has one shared power pool of 0–8, re-rolled by a random walk every 50 s of real time;
    spells cost 1–3 and always work when the target is in range and within ±50° of the wizard's facing (no
    casting roll, no line of sight, no miscast). Dispelling is a spell or an item aura with a percentage chance.
13. **Biggest open points**: the objective evaluators (R63), the optional batch 5 (animation
    bytecode, sounds by event) and a few effects to confirm in the running game (never-ending spells). Campaign
    progression and save games: `notes/campaign.md`.

## Contents

- Unit stat fields
- Runtime structures, time, movement, formations, routes, behaviour scripts, and objectives
- Player orders and HUD
- Close combat, combat resolution, and leadership
- Shooting, artillery, magic, and AI
- Differences from Warhammer Fantasy Battle 4th edition
- Open points

## 3. Unit stat fields

### Keyword tokens and the byte block ✅

The game maps script keywords to integer tokens with lookup tables:

| Table | Contents |
|---|---|
| instructions | `setstats`=1, `addunit`=2, `endunit`=3, `hidden`=4, `addleader`=5, `endleader`=6, `addspell`=7, `addmagicitem`=8, `set`=9, `addobject`=10 … |
| fields | `psy_status`=10, `script`=11, `map`=12, **`s_side`=13 … `s_banner`=39**, `s_calualties`=40, `s_routed`=41, `s_kills`=42, `s_Exp`=43, then window/glue keys (`radius`, `Lines`, `sequence`, `res`, … `inactivedepend`=82), an empty entry (83), and `os_*`, `ns_*`, `bnd_*` flag values |
| psychology | `CantBreak`=19 … `CantDie`=32 (section 3.4) |

The original editor writes each `setstats` line from this byte block. Value *i* is the
**byte** at position `(token − 13) + i` of the block. The relevant token ranges are:

| Line | Token | Count |
|---|---|---|
| `s_side` | 13 | 4 |
| `s_move` | 21 | 9 |
| `s_mount` | 30 | 6 |
| `s_weap` | 32 | 1 |
| `S_BalWeap` | 35 | 1 |
| `s_pntval` | 34 | 1 |
| `s_cmdr` | 36 | 4 |
| `s_armname` | 37 | 2 |

So **tokens 13–39 are one byte each, consecutive in token order**, and a `setstats` line fills
consecutive fields starting at its key. That explains why `s_mount` has 6 values
(`s_mount s_armr s_weap s_race s_pntval S_BalWeap`), why `s_cmdr=0,0,15,0` repeats
`s_armname=0,15`, and the old 9-value `s_rlmv`/`s_lead` lines in `PLOT1`. Tokens 40–43 are written as
`set:` lines from 16-bit fields.

The rules code reads the same bytes through a per-model pointer to this block (section 4): WS, S, T, W, A, Ld,
mount, armour, weapon class and race are consecutive stat-block bytes in token order.

Evidence from the data (check in `whshr/rules.py`): all 1415 units and leaders in the 87 scripts
and the save armies decode without overflow, and their 32 335 `setstats` values never contradict
each other (e.g. every `s_mount[2]` equals the separate `s_weap` line). The in-game panel of
"Mercenary Crossbows, Crossbow 12/12: M 4, WS 3, BS 4, S 3, T 3, W 1, I 3, A 1, Ld 7" is
`SAVE/PLAY.MRC`: `s_side=3,12,12,3`, `s_move=4,3,4,3,3,1,3,1,7`, `s_weponame` 15 → `BRTXT 215`
"Crossbow". (`FILE/SCRIPT/BF001.MRC` has the pre-campaign strength `10,10`.)

### Field meanings

| Token | Field | Meaning | Status and evidence |
|---|---|---|---|
| 13 | `s_side` | bit 7 enemy side, bit 6 NPC/neutral, bits 0–5 type code (table in `FORMATS.md`) | ✅ bit 7 selects the side a combat result is credited to; type codes from statistics |
| 14 | `s_orgsize` | original number of models | ✅ panic test uses `orgsize >> 2`; test files write 0 here and a size in the next byte |
| 15 | `s_size` | current number of models | ✅ every per-model loop; decremented when a model is removed |
| 16 | `s_rnks` | number of ranks | 🟡 read by formation code; values 1–7 fit the unit sizes |
| 17 | `s_wdth` | frontage (models per rank) | ✅ recomputed by the formation code as `ceil(size / ranks)`; rank bonus `size / width − 1` (section 6); charge bonus `1.5 × frontage` |
| 18, 19 | `s_rkmd`, `s_spar` | runtime: number of ranks in the formation, number of front ranks at full frontage (all ranks when `size % ranks = 0`) | ✅ written by, read by the slot code the game (later ranks are offset by half a slot); never set by scripts |
| 20 | `s_rlmv` | flee movement rate | 🟡 recomputed from a float at unit set-up; subtracted from the movement counter of fleeing units every tick |
| 21–29 | `s_move`, `s_wepn`, `s_bals`, `s_strn`, `s_tuff`, `s_wnds`, `s_init`, `s_atks`, `s_lead` | M WS BS S T W I A Ld | ✅ tables indexed by these bytes (sections 5–8); in-game panel |
| 30 | `s_mount` | 0 none, 1 Warhorse, 2 War Boar, 3 Giant Wolf, 4 Cave Squig | ✅ mount records (section 5.4); 1 on all horse riders, 2 on Boar Boyz, 3 on Wolf Riders |
| 31 | `s_armr` | armour code: 0–5 rating, 6 regeneration, 7 void, 8–13 mounted rating 1–6 | ✅ save table (section 5.3); `BRTXT` 100–105 "Armour Rating 0–5", 106 "REGENERATE!!!!", 107 "VOID!!!!!!!!!!", 108–113 "Armour Rating 1–6"; Troll has 6 |
| 32 | `s_weap` | close combat weapon class: 0 none, 3 hand weapon, 4 two-handed, 10 spear/halberd class | ✅ strength table (section 5.2); class 4 on Greatswords, Hammerers, Rat Ogre, Treeman; 10 on halberdiers, Stormvermin, Stickers, Wolf Riders, artillery crews |
| 33 | `s_race` | `class × 8 + race`; race 0 Human, 1 Elven, 2 Dwarven, 3 Goblinoid, 4 Orc, 5 Skaven, 6 Peasant, 7 big; class 0 notype, 1 Infantry, 2 Cavalry, 3 Archers, 4 Artillary, 5 Wizard, 6 Monster, 7 RollingStock, 8 Special, 9 Furniture | ✅ name tables; the editor output agrees with `s_race` in 879/889 units; class determines behaviour (`& 0xF8`) |
| 34 | `s_pntval` | points value: experience gained by the killer, +7 per campaign promotion | ✅ `RemoveModel`; promotions in `notes/campaign.md` |
| 35 | `S_BalWeap` | missile weapon code (section 8) | ✅ shooting switches on it |
| 36 | `s_cmdr` | unknown, always 0 | ⬜ |
| 37 | `s_armname` | armour name, always 0 | 🟡 by analogy with the next field |
| 38 | `s_weponame` | weapon name: string `BRTXT 200 + n` | ✅ 22 names checked against their units (1 Spear on Stickers, 11 Halberd, 13 2-H Hammer, 15 Crossbow, 17 Lance on Reiksguard, 25 Scimitar on Clanrats…) |
| 39 | `s_banner` | unknown, always 0 | ⬜ |
| 40 | `s_calualties` | models lost | ✅ incremented per model killed; used by the rally test |
| 41 | `s_routed` | models removed without being killed | 🟡 incremented on the other removal path |
| 42 | `s_kills` | enemy models killed | ✅ incremented on the killer unit |
| 43 | `s_Exp` | experience | ✅ killer gains the victim's `s_pntval` |

A leader has its own block of the same layout; the unit record keeps a second copy at `leader_stat_copy`
(the reload and missile code read `leader_I` and `leader_BalWeap`, which are I and `S_BalWeap` of that copy).
Artillery crews carry their machine's `S_BalWeap` on the leader (e.g. 5, 6, 8).

### Effective Leadership ✅

The effective value is the leader model's Ld if the unit has a leader with non-zero Ld, otherwise the Ld of the
first model.

### `psy_status` bits ✅

`psy_status` is a 16-bit field; **bit = token − 19**. The writer masks `0x3FFF`.

| Bit | Flag | Effect found in the code |
|---|---|---|
| 0 | `CantBreak` | rout and fear-flight events are ignored (op 0xC8; Dwarfs shout "We fight to the death!"); fear does not apply |
| 1 | `Frenzy` | Attacks doubled in close combat; excluded from fear and terror |
| 2 | `CauseFear` | enemies that lose a combat against it break without a test; engaging it needs a Leadership test |
| 3 | `CauseTerror` | units without `Frenzy`/`PsyImmune` cannot charge it and **flee without a roll** when charged by it or touching it (section 7.3) |
| 4 | `FearToGobs` | ✅ **unused**: no observed rule uses this bit, and scripts cannot read the field |
| 5 | `HateDwarfs` | hatred against race 2 (Dwarven) |
| 6 | `HateGreens` | hatred against races 3 and 4 (Goblinoid, Orc) |
| 7 | `HateSkaven` | hatred against race 5 (Skaven) |
| 8 | `PsyImmune` | excluded from fear and terror |
| 9 | `MagicResistent` | each magical hit is ignored on a 50% roll |
| 10 | `CantRally` | never attempts to rally |
| 11 | `AlwaysPursue` | never tests to stop a pursuit |
| 12 | `CantMelee` | ✅ property of the **target**: others do not counter-attack it (op 0x39), the player cannot order an attack on it, collisions make no contact attacks on it. Only Night Goblin Fanatics; op 0xD9 clears it |
| 13 | `CantDie` | models are not removed when wounds reach W |
| 14 | (runtime) | fear test passed: spares further fear tests until the next charge clears it |

`the original front end`'s copy of the table also names `AlwaysPursue` (bit 11) but ends at `CantRally`; the scripts
never use `AlwaysPursue`.

## 4. Runtime structures, random numbers, battle clock

Names in code font for per-unit and per-grid state below and in later sections (`unit_flags`, `move_state`, `engaged_enemy`,
`round_counter`, …) are this report's own descriptive labels, not names from the original program.

- **Units**: per-unit records with an index (16 bit). Other state used here: the flag word `unit_flags` (32 bit;
  `0x2000` = broken, see "Can't engage a broken unit"), the leader model, the engaged enemy unit `engaged_enemy`, the
  attack direction `attack_dir`, the battle grid `grid`, the model list `model_list`, the charge counter `charge_counter`,
  the combat round counter `round_counter`, the unit worth `unit_worth` (`size × s_pntval × 12 artillery / 8 wizard / 4
  monster / 1`, read by AI target scoring), and the spell and item lists `items` / `item_list`.
- **Models**: per-model records hold flags, a pointer to the stat block, the opponent model and opponent unit,
  the wounds taken (a model dies when wounds ≥ W) and an attack counter.
- **Random numbers** ✅ the game is MSVC `rand`: `seed = seed * 214013 + 2531011`,
  result `(seed >> 16) & 0x7FFF`. A D6 is always `rand % 6 + 1`.
- **Battle clock** ✅ (the game reset, the game tick): **19 ticks** form a *segment* (the counter
  starts at 18 and is decremented before the `< 0` test);
  the segment counter runs 10, 9, … 1, then the turn counter increases
  and the segment returns to 10.

### Real time and movement ✅

- **Timer**: the battle window runs `SetTimer(100 ms)`; each `WM_TIMER` re-arms it, runs **exactly one tick**
  (the game → `BattleTick`) and renders. Frame-driven, no catch-up: at most 10 ticks per second, so a
  segment (19 ticks) lasts 1.9 s and a turn (10 segments) 19 s. Pause is bit `0x80` of the game state; there is
  no game speed option.
- **Speed stat**: Movement is used only to derive `s_rlmv` at unit set-up:
  `trunc(4.8 × M' + I) / 2`, or `trunc(2.4 × M') + 4` for neutral units. `M'` is the **mount's** M when the
  armour code marks the model as mounted, otherwise the model's own M; the Initiative term is always the
  rider's. After set-up nothing reads M again — `s_rlmv` is the only movement input (see "Mounts").
- **Unit speed** ✅: recomputed **every tick**, before the unit's behaviour script and its movement update run,
  as a single stored value `speed = s_rlmv × 16 × k`. The factor `k` is chosen by the first matching case:

  | Condition | `k` |
  |---|---|
  | charging **or** in melee | **2.5** |
  | broken / fleeing | 1.5 |
  | pursuing | — (the pursuit step replaces the whole `s_rlmv × 16` term) |
  | no target, **or** distance to the target exceeds the target's radius | 1.8 |
  | otherwise (closing on a target) | 1.0 |

  The stored value is a speed in 1/16 world units per tick, so the unit's own reference point advances
  **`s_rlmv × k / 16` world units per tick**. An M4 I3 infantry unit covers about 9.8" per turn moving freely
  and 5.4" closing in. Pursuers and fugitives use the same factor, so only a higher `s_rlmv` closes the gap.
  **Terrain has no effect on speed.** Note that "in melee" shares the charge factor, but an engaged unit does
  not translate at all (see below), so the value is inert there.
- **Turning** ✅ (reached only through): facing is a **16.16 accumulator** at
  `facing_acc` whose high word `facing` is the integer facing in 1/512 turn. Per tick it advances by
  `s_rlmv × (144 − s²) × 2^(scale − 9)` facing units, with `s = frontage + ranks − min(frontage, ranks) / 2`
  and `scale` by state: **2 pursuing** (re-aiming at the fugitive), **1** halted-turn or turn order,
  **0 wheeling** (ordinary move), **−1 charging**. The turn counts as finished once under 11/512 (≈ 7.7°)
  remains. (For `s ≥ 12` the
  formula stops working; no deployed unit reaches it.)
  **Facing is never snapped to the travel bearing per tick**: the goal bearing lives in `goal_bearing` and the
  amount still owed in `turn_owed`, and the unit always translates along its **current** facing (`sin_facing/cos_facing`
  = sin/cos of `facing`), so a unit whose facing has not caught up walks off-axis and re-plans.
  Thresholds: required turn **> 45°** → halt and turn on the spot (`move_state |= 8`, no
  translation that tick); **7.7°…45°** → wheel while moving (`move_state |= 4`, half speed); **< 7.7°** → absorbed.
  A **pursuing** unit re-aims once per segment and turns only when the bearing error exceeds 22.5°; a
  **charge** turns for any non-zero angle at its start (no threshold, no snap), re-reads its aim point once at
  its halfway point, and never uses the half-speed wheel or the zero-translation turn (see "Turning,
  wheeling and reversing"). Separately, **at the moment a move order is
  issued** (the game from `GotoTarget`) a required turn of **68.2°–135°** snaps instantly 90°
  and **> 135°** snaps instantly 180°; the residue is then wheeled.
- **A turn always moves the unit position to keep the pivot still** ✅ — the rule an engine is most likely to
  get wrong. In-place turns pivot about the **block centre**: the about-face displaces the anchor by
  `(ranks − 1) × 12` backwards along the old facing (exactly twice the map-object offset, which holds the
  block centre fixed under 180°), and the 90° turn moves it to the new front-rank centre while swapping
  ranks and frontage (`ranks := frontage`). **Gradual** turns instead pivot about the **inner front corner** —
  uniformly, for every kind of gradual turn and not only for wheels — by shifting the anchor by the rotation
  applied to the half-frontage vector `6 × (frontage − 1)`; a wheel then keeps half its translation speed and
  every other gradual turn drops to zero. Details and the formation differences are in
  "Turning, wheeling and reversing" below. In both cases every model's
  stored offset is counter-shifted so the soldiers do not teleport, and a
  re-form is queued (`move_state |= 1`). **The unit position is never held fixed while the facing changes**, so a
  turn cannot open a gap between two touching units.
- **The footprint belongs to the map object, not to the unit position** ✅:
  the box is stored as half-extents `frontage × 6` by `ranks × 6` **symmetric about the map-object centre**
  and independent of the facing; the four rotated corners are stored with the unit; the map object's bounding radius
  is the box half-diagonal and the diagonal angle is stored with the unit. Every collision query — the broad
  circle and the narrow corner test — is expressed in object space and never touches the unit position.
  Note the half-extents use the **raw** frontage and rank counts, not `count − 1`, which is where the
  "half a cell to spare" comes from.
- **Contact is resolved by rolling the tick back** ✅: when a move would overlap an enemy,
  the tick's translation **and** rotation are undone for both the unit and its map object (`pos_x`, `pos_y`,
  `facing_acc`, ranks, and the object's centre and facing are all restored from saved copies), then
  the game halts the unit and queues a re-form. The contact pose is simply the last pose that did not
  overlap: there is no snap to a facing, no alignment to the target's edge and no stand-off distance.
  A charge aims at the target's object centre pushed out by the target's bounding radius along the
  **target's own** facing (the game; the rear/flank variants add 0x100/±0x80), and is aborted without
  engaging if it meets anything within ±45° of its front .
- **A unit in close combat does not move or turn at all** ✅: engaging clears every `move_state` movement state
  bit, and the tick dispatcher selects a handler purely from `move_state`, so a unit whose only
  relevant flag is `unit_flags & 0x200` runs no movement or turn code — it does not even set the idle flag. No
  store to `facing` exists anywhere in the melee path. (`A_close_combat.md`'s remark that a model is "made to
  face an attacker" by the `0x44000` test is a misreading: that test is on a **model** record and only pairs
  the defender with its attacker — no angle is touched.) The exceptions that still move an engaged unit are
  the unconditional boundary repel and the push-apart of a *broken* unit; ordinary push-apart is disabled
  for melee, being guarded by `& 0xA200` (pursuing | broken | in melee).
- **Charge**: reaches at most `12 × (s_rlmv + 1)` units, re-aiming halfway (about 6" for infantry, 9.5" for
  horsemen).
- **Boundaries**: region masks `0x20` = `BATTLEEDGE`, `0x90` = `INVSOLID|SOLID`, `0xB0` = `INVSOLID|BATTLEEDGE|SOLID`
  (the `bnd_*` flags of the script keyword table).
- **Flight check**: the "flee counter" of `FleeingUnitUpdate` is not a distance; it only schedules the battle-edge
  check about every half footprint radius.
- **Animation bytecode**: models and free-standing objects both run per-object animation scripts, one
  word per tick. Negative words set the sprite phase; other words are operations from a 59-entry set.
  Full behaviour in "Figure animation: actions, timing, and why the figures are never in step".

### Formations ✅

Observed in the game data and play sessions (September 2026). Unit sizes come from `s_side` in the scripts: across the campaign
battles infantry units have 1–32 models (median 19), cavalry up to 28 (median 16), archers 10–29 (median 18),
artillery 4–6 crew plus the machine, monsters and special units 1, wagons 2; enemy units have a median of 16
and at most 32 models, usually in 4 ranks (3–5).

- **Formation kind** by unit class (`FormationKind`, table the relevant data), dispatched by
  `ReformUnit`: Infantry, Cavalry, Archers, Wizard, Special and notype use the **block**
 ; Artillery the war machine layout; Monster a single-model footprint
 ; RollingStock the wagon layout. **The block is the only formation**: there
  is no skirmish, column or wedge order.
- **Size**: `frontage = ceil(models / ranks)`; the leftover models go
  into the **front** ranks (18 models in 4 ranks: rows of 5, 5, 4, 4).
- **Spacing**: **12 world units** (half an inch) between models, sideways and front to back, for every class
  including cavalry. The same 12 units are the battle-grid cell. The collision footprint is a
  box with half-extents `frontage × 6` and `ranks × 6`; its diagonal angle is stored in `diag_angle` (the arc used
  for front/flank/rear). The box belongs to the unit's **map object** (one per unit), which
  the game keeps in step with the unit (facing and centre): for a block the centre
  lies `(ranks − 1) × 6` units behind the unit position along the facing, the middle between the first and
  last rank, so the symmetric box covers every model with half a cell to spare. War machines, monsters and
  wagons keep the map object at the unit position. `+4` holds a square root computed from the extents
  (probably the bounding radius). the game shifts every model of a unit and refreshes its map object.
- **Block layout**: rank *n* stands `12 × n` units behind the first rank; each rank is centred
  and filled from the outside in, pairwise, with a centre model when its count is odd.
- **Placement**: a slot offset `(x, y)` is rotated by the unit's facing (sine/cosine tables
  the relevant data, the relevant data, 8.8 fixed point; world offset `x = side·cos + forward·sin`, `y = forward·cos − side·sin`) and stored in the model as its target relative to the unit
  position, together with its slot, rank and file. **The unit position is the front-rank centre**, and that
  slot is reserved for the leader model (unless it is fleeing). Every other slot takes the nearest free model
  (octagonal distance), so re-forming moves each soldier to the closest position. The model walking rule
  then walks each model towards its slot every tick — at a **rank-dependent** rate, described in
  "Models chase the unit, they are not carried by it" below.
- **Ranks** (orders 0x0F/0x10): refused while fleeing,
  held (Tangling Thorn) or charging; the request is clamped to `[min, models / min]` with
  `min = max(1, trunc(0.75 × √models))` (constants 1.5 × 0.5 at the relevant data/the relevant data). Examples: 8 models
  2–4 ranks, 18 models 3–6, 24 models 3–8, 32 models 4–8. Re-forming (`HaltAndReform`) restores the script's
  `s_rnks`.
- **War machines**: the layout depends on the **leader's sprite** (unit `leader_sprite`, the machine,
  set by the leader's `troopsprites`): Mortar, Cannon, Volley Gun and Doom Diver catapult use a box 2 wide × 3
  ranks, Great Cannon and Rock Lobber 3 wide × 4 ranks; the machine takes the centre and the crew stand in fixed
  slots around it.
- **Monsters**: one model at the unit position; footprint 2 × 2 cells by default (Troll, Rat
  Ogre, Warpfire Thrower), 3 × 3 for the sprites Gyrocopter, Wyvern, Treeman, Giant, Doomwheel and Dragon
 , 5 × 8 for the Mole Machine. Units whose sprite is not on that list fall back to 2 × 2 even when
  large: the 3D-mesh Dragon of BF014 (`MeshDragon`) and the Doomwheel entry with `VoidType`.
- **Wagons** (units of exactly 2 models): the two models stand 22 units apart front to back
  (team and wagon), footprint 2 × 4 cells, facing snapped to 45° steps.
- **Script opcodes**: `ScatterModelsAtNode` (0x48) spreads a unit's models around a node, `PlaceAndReformAtNode`
  (0x4A) re-forms at a node.

### Models chase the unit, they are not carried by it ✅

Traced September 2026. This is the rule that decides what a moving unit actually **looks like**, and it is the
one an engine is most likely to get wrong by assuming the soldiers are rigidly attached to the formation.

**There are two positions, and only one of them is driven by the speed stat.**

1. The **unit position** (the "anchor", the front-rank centre) is a bookkeeping point. It is what the footprint,
   the collision tests, engagement, charge distance and the charge counter are all keyed off. It advances at
   `s_rlmv × k / 16` world units per tick, with the `k` of the table in "Real time and movement" above — so
   **`k = 2.5` while charging**.
2. Every **model** keeps its own position, stored **relative to the anchor**. The moment the anchor translates,
   every model's stored position is decremented by exactly the same delta. The net effect is that a model's
   **absolute world position is completely unchanged** by the unit's own movement.

So the anchor never drags the soldiers along. All it does is move the models' target slots out from under them,
opening a gap of exactly one anchor-step every tick. The figures are then pulled forward only by a separate,
independent catch-up walk — and that walk runs at its own speed, which has **no charge multiplier in it at all**.

**The catch-up walk**, per model, per tick:

```
if the model has a pending start delay          -> it does not move this tick (see below)
dist          = straight-line distance to its slot
target_speed  = min(dist, s_rlmv)                 (no cap at all while the unit is broken)
current_speed = current_speed + 1, up to target_speed   (drops to target_speed immediately if lower)
position     += current_speed × step_vector
```

`current_speed` is a **counter, not a distance**. It is converted to world units by the step vector, whose
magnitude carries a per-model factor `F`:

```
step length per unit of current_speed = F × 2.4 / 256  world units
F = (ranks − rank_index) × 8 + (per-model stagger value & 6) + 4      rank_index 0 = front rank
```

The per-model stagger value is a fixed 16-bit number given to each model when it is created: **29 × n mod
65536**, where n is a single battle-wide counter of models created so far (starting from an arbitrary constant
that the game never resets). Only its low bits are read — `& 3`, `& 6`, `& 7`, `mod 3` and bit 1 — and because
29 ≡ 1 (mod 4), `& 3` cycles 0, 1, 2, 3 across consecutive models, `& 7` steps by 5 (0, 5, 2, 7, 4, 1, 6, 3)
and still visits all eight values, `mod 3` cycles through all three values, and bit 1 runs in pairs (0, 0, 1, 1).
So neighbouring models differ, giving the block its ragged, non-rigid look; the same value also staggers the
charge start, the rout pause and the figure animation. Its contribution to `F` is 0, 2, 4 or 6. An engine
should keep one running counter and take these fields from the full value rather than storing a 0–7 number.

**Top speed of a model, and whether it can keep station:**

```
v_model = s_rlmv × F × 2.4 / 256
v_anchor = s_rlmv × k / 16
v_model / v_anchor = 0.15 × F / k     ->   a model holds its place only while  F ≥ 6.67 × k
```

`F` drops by 8 for every rank further back, so **the rearmost rank always has `F` = 12…18, however deep the unit
is**. The thresholds that matters:

| Unit state | `k` | `F` needed to hold station | Rearmost rank (`F` = 12…18) |
|---|---|---|---|
| closing on a target | 1.0 | 6.7 | holds easily |
| moving freely | 1.8 | 12 | **exactly marginal** |
| fleeing | 1.5 | 10 | holds |
| **charging** | **2.5** | **16.7** | **falls behind** |

The tuning is deliberate: at the ordinary marching factor the rearmost rank's minimum step is
`12 × 2.4 / 256 = 0.1125` and the anchor's is `1.8 / 16 = 0.1125` — **identical**. The back rank is calibrated to
exactly keep pace with a normal march, and is therefore structurally incapable of keeping pace with a charge.

**Worked example** — Empire infantry (`s_rlmv` 11) in 4 ranks, world units per tick:

| | `F` | speed | vs. the charging anchor (1.72) |
|---|---|---|---|
| anchor, charging (`k` 2.5) | — | **1.72** | — |
| anchor, marching (`k` 1.8) | — | 1.24 | — |
| front rank | 36–42 | 3.71–4.33 | tracks tightly |
| second rank | 28–34 | 2.89–3.51 | tracks |
| third rank | 20–26 | 2.06–2.68 | tracks |
| **rear rank** | **12–18** | **1.24–1.86** | **three of the four stagger values trail** |

**What this produces on screen:**

- **A charging block visibly stretches.** The rear rank moves at about 72 % of the anchor's charge speed and
  loses roughly 0.48 world units per tick. Across a full infantry charge (about 84 ticks and 144 world units,
  see "Charge" below) the back rank ends up on the order of **40 world units — about 1.7", over three model
  spacings — behind where the formation says it should be**. Cavalry in two ranks string out the same way.
- **The stretch is recovered afterwards, not during.** Nothing caps the accumulated gap, and nothing accelerates
  the stragglers. Once the unit stops or engages, the anchor stops moving and the trailing models close the gap
  at their own rate, so the block visibly concertinas back together over roughly three seconds.
- **Nobody moves at all for the first moment of a charge.** Issuing the charge gives every model a freeze
  countdown of `(stagger value & 7) + 1` = **1 to 8 ticks** during which it does not move, while the anchor is
  already running at `k = 2.5`. That alone opens up to about 14 world units — more than a model spacing — before
  a model takes its first step, and it staggers the start model by model.
- **Models walk toward where the slot used to be.** The step vector is recomputed only when a per-model distance
  budget (reset to half the remaining distance at each recomputation) runs out, and a model is only considered
  arrived once it is within 3 world units of its slot. Between recomputations a model marches in a straight line
  on a stale heading, which is why a turning or charging block looks like it is sliding rather than tracking.
- **Broken units are the exception**: while broken, the `s_rlmv` cap on the catch-up walk is removed entirely, so
  fleeing models are not held to formation speed.

**Formation is what decides all of this** ✅. Note first that `s_rlmv` appears on both sides of
`v_model / v_anchor = 0.15 × F / k` and cancels out: **whether a model can hold station never depends on its
speed stat**, only on its rank index, its unit's rank count, its stagger value and the movement state. A Dwarf
and a wolf rider in the same formation stretch by the same proportion; they just do it at different absolute
speeds.

- **Rank count sets the whole speed gradient; frontage does not enter it at all.** `F` is built from
  `ranks − rank_index`, so each rank further back is `8 × 2.4 / 256 = 0.075 × s_rlmv` world units per tick
  slower than the one in front of it (0.83 for `s_rlmv` 11). Frontage affects the turn rate, the wheel pivot and
  the footprint, but never a model's step length.
- **The rearmost rank is always `F` = 12…18, whatever the depth.** Depth therefore does not make the back of a
  unit lag *worse* — it makes the front of it faster (`F` = `8 × ranks + 4 + stagger`), so the deeper the unit,
  the wider the spread of speeds inside it. A block re-formed from 4 ranks to 2 keeps the same rear-rank
  behaviour but loses much of its front-rank speed (`F` 36 → 20).
- **A one-rank formation is uniformly slow.** With `ranks` = 1 every model is rank 0 and so `F` = 12…18 — the
  whole unit trails a charge, not just its back. Rank clamping (`min = max(1, trunc(0.75 × √models))`) means
  this only arises for single-model units.
- **Monsters inherit it through their pseudo-formation.** The single model is placed at rank index 1 of the
  footprint-shaped layout, so the **2 × 2 monsters (`ranks` = 2) get `F` = 12…18 and trail their own charge**,
  while the 3 × 3 ones (`ranks` = 3) get `F` = 20…26 and keep up. The Mole Machine's 5 × 8 layout puts its model
  at rank 2 of 8, `F` = 52…58, so it tracks its reference point almost exactly. (Which monster has which
  footprint: see "Monsters" under Formations.)
- **War machine crew are deliberately the slow ones.** The machine takes rank 0 of the 3- or 4-deep layout
  (`F` = 28…34) and the crew are assigned rank indices at the back of it (`ranks − 1` and its neighbours), so the
  crew always re-settle around the machine rather than the other way round.
- **Wagons never stretch**: the two models sit at rank 0 and rank 1 of a 4-deep layout (`F` = 36…42 and 28…34),
  both far above the charge threshold.
- **Turning during a charge makes the stretch worse, not better.** A charge never uses the half-speed wheel or
  the zero-translation turn: it moves first and turns afterwards in the same tick, so it keeps full charge
  speed (`k` 2.5) on every turning tick and loses no translation. Its turn is its own very slow case
  (0.72°/tick for a 5×4 M4 I3 block, 0.17°/tick for a 10-wide line, 0.90°/tick for a single file), and every
  turning tick rotates the slot lattice about the inner front corner while the models stay put, so the whole
  slot sweep — about `0.0175 × r` world units per degree, `r` being the slot's distance from the inner front
  corner — is added to the rear ranks' lag. Simulated rear-rank lag after a full ~84-tick charge (±30 %;
  straight charge ≈ 29 mean / ≈ 45 for the slowest `F` = 12 model): a 5×4 block with a 45° turn ends about
  16 (worst model 22) units worse and cannot finish 90° or 135° within the charge (about 60° at most, +27 /
  +39); a 10×2 line ends about 14 (21) worse whatever the angle, having turned only ~15°; a single file about 2–5
  worse. A turning charge is never tidier than a straight one. Only the states that do cut translation trade
  it against the sweep — the half-speed wheel and the zero-translation turns of ordinary movement, pursuit
  re-aims and turn orders — and there the result depends on formation shape (for a 5×4 the sweep outweighs the
  translation saved; a slow-turning 10×2 comes out slightly better).

**For an engine**: the unit's logical position must be advanced by the full charge speed regardless of where the
sprites are, because every gameplay consequence (contact, engagement, charge bonus, footprint) reads the anchor.
The sprites must be a *separate* per-model pursuit of an anchor-relative slot, at a rank-dependent rate with no
charge multiplier. Treating the models as rigidly attached to the formation removes the stretch, the ragged
start and the concertina — the most recognisable visual features of movement in this game.

### Formation changes: how the figures re-sort themselves ✅

Traced September 2026. A rank change, or any queued re-form, is **not** the same process as the continuous
slot-chasing of ordinary movement. Three things differ, and together they are what makes a unit changing
formation look like men finding their places rather than a lattice snapping.

**1. Models are re-assigned to slots, not kept in them.** Re-forming first recomputes the shape —
`frontage = ceil(models / ranks)`, with the **leftover models going into the front ranks** (18 models in 4 ranks
gives rows of 5, 5, 4, 4) — and then fills the slots one at a time, front rank first, centre outwards. For each
slot it scans **every not-yet-placed model and takes the nearest one**, measured with an octagonal metric
(`larger + smaller / 2` of the two axis distances) rather than true distance, stopping early if it finds an
exact match. So a soldier does not keep his old place in the formation: he takes **whichever slot in the new
shape happens to be closest to where he is already standing**, and the unit re-sorts itself with the shortest
total walking. The front-rank centre slot is the exception — it is handed to the **leader model** directly,
without the search, whenever the leader has not already been placed.

**2. A different mover takes over.** Re-forming raises a flag meaning "models are off their slots", and while it
is set the unit switches away from the rank-dependent catch-up walk to a **separate mover**:

- each model moves at a **flat `s_rlmv / 8` world units per tick** — no rank factor, no `F`, and **no
  ramp-up**: it goes to full speed on the first tick and holds it. Every model in the unit re-forms at the
  same speed regardless of which rank it is in or is heading to.
- **it decelerates into its slot.** Inside the last 6 world units the step is divided by `7 − distance`, so it
  covers the final approach at a half, a third, a quarter … of speed and settles smoothly instead of stopping
  dead. (A separate cap holds any single step to one world unit, which only bites for the fastest units.)
- **arrival snaps the model's heading to the unit's facing**, which is what makes a finished formation suddenly
  read as aligned — the figures turn to face front only as they land.
- **the unit's own translation speed is halved** for as long as the re-form is in progress, so a unit that is
  changing formation on the move slows to half pace until everyone is in place.
- when the last model settles the flag clears and the unit raises a "re-form complete" event.

**3. Models trade places rather than walk through each other.** Each tick, before stepping, a moving model
checks its projected next position against every comrade that is **already at rest**. If it is about to step
onto one about half a spacing away and is heading into it, the two **exchange their entire slot assignment** —
target position, slot index, rank and column — and both re-aim. The walking model inherits the settled one's
place and stops; the settled one is woken up and walks off to the slot the first was heading for. This is the
shuffling, place-swapping motion a re-forming block shows, and it falls out of a purely local rule with no
global planning.

**Formation differences** ✅: **blocks and monsters** re-form through the flat mover above. **War machines and
wagons** do the opposite — their layouts explicitly clear the re-forming flag, so their models are carried by
the ordinary rank-dependent catch-up walk instead, ramping up and moving at rank-dependent speeds. A war
machine's crew therefore re-settle around the machine at their own varied rates rather than in the uniform
flat-speed shuffle of a regiment. **The war machine layout also inverts the model search** ✅: the machine
model itself is placed directly at the front-rank-centre slot with no search (if the machine is gone, every
slot is searched), and every **crew** slot then takes the **farthest** unplaced model (same octagonal
distance, greedy slot by slot, the last slot getting whoever is left) instead of the nearest. During normal battle play, crew slots use this farthest-model rule.
The pre-battle exception
is documented in [deployment.md §4.2](deployment.md#42-formation-layout-during-deployment).
Wagons, monsters and blocks never invert. After crew casualties the surviving crew can
therefore scramble across the machine on the slow rank-dependent walk.

A formation change **costs no time of its own** — the only delay is the walking. Requested rank counts are
clamped to `[min, models / min]` with `min = max(1, trunc(0.75 × √models))`, and a re-form is refused outright
while the unit is fleeing, held or charging.

### Turning, wheeling and reversing ✅

Traced September 2026. Turning is where the formation system is most visible, and where the differences between
formations are largest. There are two entirely separate mechanisms: **gradual turns**, which every unit performs
continuously, and **instant snaps**, applied once when a move order is issued (described in "Real time and
movement" above). Everything below is the gradual path.

**The per-tick turn step.** Facing is a fixed-point accumulator whose integer part is the facing in 1/512 of a
turn, wrapped to 0…511. Each tick the unit turns by

```
step    = s_rlmv × (144 − s²) / 2^(16 − shift)      units of 1/512 turn
s       = frontage + ranks − min(frontage, ranks) / 2
shift   = 9 pursuit re-aim · 8 halted turn and turn order · 7 wheel · 6 charge
```

Which case applies is decided by the unit's movement state, checked in this priority order: waiting, fleeing,
pursuit, ordinary move, charge, turn order. Starting a charge clears the ordinary-move and wheel states, so a
charging unit can never wheel at half speed. For 5×4 infantry at `s_rlmv` 11 (`s` = 7):

| state | shift | turn rate | translation on a turning tick |
|---|---|---|---|
| **charge** | 6 | 1.02 units/tick (0.72°) | **unchanged, full charge speed** — movement is applied before the turn |
| **pursuit** re-aim | 9 | 8.16 units/tick (5.7°) | **zero** — the turn is applied before movement |
| ordinary move, 7.7°–45° owed, > 32 units to go | 7 | 2.04 units/tick (1.44°) | **half speed** — the only wheel |
| ordinary move, > 45° owed (halted turn) | 8 | 4.08 units/tick (2.9°) | zero, then re-plans; the residue is wheeled |
| turn order | 8 | 4.08 units/tick | zero |

A charge lasts two halves of about 42 ticks (about 84 in all, a reach of `12 × (s_rlmv + 1)` world units), re-reads its aim point once at the halfway
point and ends whether or not it arrived; its length does not depend on turning, and nothing steers it toward a
moving target after the order. Because of the slow turn rate a charging block turns at most about 40° for a 5×4
block (60° in the whole charge), about 15° for a 10×2 line and 75° for a single file; a larger required angle
just means it spends the whole charge slowly wheeling and arrives facing part of the way round. Unit speed is
recomputed at the start of every tick, so the charge's request for zero speed after its turn has no effect.

so a halted turn advances `s_rlmv × (144 − s²) / 256` per tick. The direction is always **the shorter way
round** (the turn setup compares the required difference against a half turn and folds it, recording the side in
a flag that the step then reads). The angle still owed is reduced by the amount actually turned, and the turn
**ends once 10 or fewer of the 512 units remain** (about 7°).

**Wide units turn dramatically slower** — this is the `(144 − s²)` term, and it is the single most important
tactical consequence of choosing a formation:

| 20 models, `s_rlmv` 11 | frontage × ranks | `s` | `144 − s²` | 90° turn | 180° reverse |
|---|---|---|---|---|---|
| deep column | 5 × 4 | 7 | 95 | ≈ 31 ticks (3.1 s) | ≈ 6.2 s |
| wide line | 10 × 2 | 11 | 23 | ≈ 130 ticks (13 s) | **≈ 26 s** |
| 10 cavalry, `s_rlmv` 18 | 5 × 2 | 6 | 108 | ≈ 17 ticks (1.7 s) | ≈ 3.4 s |

A wide line reversing takes well over a full game turn, while the same models in a deep column manage it in six
seconds. 🟡 For `s ≥ 12` the term reaches zero or goes negative and the turn would never finish; the widest
formation in the campaign data reaches `s` = 10, so it is not reachable in practice.

**What the formation does.** On every tick of a turn that actually rotates the block:

- the unit's reference point is **displaced by the rotation applied to the half-frontage vector
  `6 × (frontage − 1)`**, which holds the **inner front corner** still — a true wheel rather than a spin about
  the anchor. The side is taken from the same turn-direction flag, and a **frontage of 1 inverts it**.
- **translation speed is changed for that tick**: a wheel keeps moving at **half speed**; every other kind of
  turn — halted turn, turn order, charge re-aim, closing redirect — **sets the speed to zero**. Only a wheel
  turns and travels at once; everything else stops the unit dead while it comes round.
- **every model's slot is recomputed from the new facing**, as
  `rotate(12 × column − 6 × (frontage − 1), −12 × rank)`. Ranks that are one model short are offset by a further
  half spacing (6 world units), which is the staggered look of the rear ranks.
- a re-form is queued, and a turn order ends by halting and re-forming to the script's rank count.

**What the individual figures do.** They are never rotated into place. The slot lattice rotates under them, and
at the same moment every model's stored position is **counter-shifted by exactly the reference point's
displacement**, so no figure teleports — each keeps its world position and simply finds its slot has moved. It
then walks to it under the ordinary rank-dependent catch-up walk of "Models chase the unit, they are not
carried by it": front ranks fastest, rear rank slowest, each ramping up by one speed unit per tick.

This is what makes a turning block read as a body of men rather than a rotating sprite sheet: the *shape* turns
at the formation's rate, and the *figures* stream after it individually, the outside of the turn hurrying and the
rear rank trailing, converging again once the facing settles.

**Differences by formation** ✅:

- **Blocks** (infantry, cavalry, archers, wizards, special) get all of the above; their turn rate and pivot both
  scale with frontage and depth.
- **Single-model units (monsters)** skip the entire pivot-and-slot block, which is guarded on the unit having
  **more than one model**. A monster therefore turns **on the spot with no reference-point displacement, no slot
  recomputation, and no speed penalty at all** — it keeps translating at full speed while it comes round.
  That skip is the whole of a monster's agility; its **turn rate still follows the ordinary formula** from
  whatever pseudo-formation its footprint gives it. For the common footprints that is fast (`s` = 3 for a
  2 × 2, 5 for a 3 × 3), but it does not generalise: the **Mole Machine's 5 × 8 footprint gives `s` = 11**, so
  it turns as sluggishly as a ten-wide line while still paying none of the pivot or speed penalties. "Single
  model" and "turns quickly" are two separate properties and must be implemented separately.
- **Units currently re-forming** are also skipped by the same guard, so a unit that is still settling its models
  does not additionally drag its reference point around.
- **Wagons** are snapped to **45° steps — but relative to the camera, not to the world** ✅. The battle update
  keeps a global view angle (the camera's rotation converted into the same 1/512 turn scale, with the previous
  frame's value retained), and the wagon layout rounds the unit's facing to the nearest 45° step **of a grid
  offset by where the camera currently sits inside a 45° sector**. The wagon layout is then re-run **only when
  the view angle has changed since the last update** — if the camera has not moved, the re-form is skipped
  outright. The effect is that a wagon always presents one of eight clean aspects *to the viewer* and re-snaps
  as the camera swings, which is a sprite-rendering accommodation rather than a movement rule. An engine that
  implements a world-aligned 45° snap will look wrong in exactly the situation the original handles: rotating
  the camera around a stationary wagon.
- **War machines** use a 2–3 wide, 3–4 deep layout (`s` ≈ 4–5, so a quick turn by the formula), but in practice
  they hardly ever turn because **they are anchored intrinsically** ✅: unit set-up computes the formation kind
  and, when it comes out as the war machine layout, **unconditionally sets the unit's anchor flag** (and marks
  the leader model as the machine). This is a property of being a war machine, decided at set-up — not a
  mission script or AI choice — so an engine has to implement it as a rule. 🟡 Their crew placement also
  inverts the slot search (taking the **farthest** eligible model rather than the nearest) depending on a
  battle phase; the pre-battle rules are documented in [deployment.md](deployment.md).

**When a unit breaks and turns to run**, every model that is currently at rest is given a pause of
`(per-model stagger value & 7) × 3 + 6` — **6 to 27 ticks** — with its timed-pause flag set, and is scattered
slightly from its position. If the unit is in melee, **each model's opponent is given the same pause**, so both
sides visibly hesitate together at the moment of the break before the routers turn about.

### Figure animation: actions, timing, and why the figures are never in step ✅

Every model runs **its own little animation program**, one step per tick, and several of those programs
deliberately start at a random point in their loop. That is the whole reason a marching or fighting
regiment in the original looks like a crowd of individuals rather than a rank of clones, and it is cheap
to reproduce exactly.

**The pieces.** A model carries five drawing fields — sprite set, shading, drawn facing, **group base
frame**, **phase** — plus an **action id**, a **program counter**, and the same small fixed
**per-model stagger value** used by the movement and rout rules. Sprite set + group base + phase +
direction resolve to a frame exactly as `notes/animations.md` describes:
`frame = group_base + phase × 8 + direction`. For the standard `32+8+32+32+8` unit sets the group bases
are **0 = move, 32 = dead, 40 = attack, 72 = stand, 104 = shoot**.

**The seven actions.** Each creature family has a table of 8 action scripts (slot 0 unused). The actions
are the same everywhere:

| action | meaning | what the script does (standard infantry) |
|---|---|---|
| **1** | stand still | stand group, **phase 1 held forever** — a single static frame |
| **2** | idle / mark time | stand group, 10-tick loop `0,0,0,1,1,2,2,2,3,3`, **not** randomised |
| **3** | walk | move group, 8-tick loop `0,0,1,1,2,2,3,3`, **random entry point 0…7** |
| **4** | fighting | attack group, 12-tick loop `0,0,1,2,3,3,1,1,3,0,2,2`, **random entry point 0…9** |
| **5** | weapon ready (in melee, unpaired) | attack group, **phase 0 or 2 chosen at random**, then held |
| **6** | dead | random facing, then the single corpse frame, held |
| **7** | shoot | shoot pose, **random entry 0…3**, 4 ticks, fire event, 2 more ticks, then back to action 1 |

Other creature families use the same seven meanings with their own loop lengths and hold patterns. The
second most common family, for example, walks on a flat 4-tick loop `0,1,2,3` with a random entry 0…3,
marks time on a lopsided 6-tick loop `0,0,1,2,2,3`, and makes even its *stand still* a random choice
between phases 0 and 2 instead of one fixed pose. There are **37 such families** in the data, each with
its own 8-action table, and **116 distinct scripts** between them.

**One script word per tick.** The animation stepper runs once per model per battle tick, inside the same
100 ms tick as everything else, so a "frame" word is exactly one tick. Standard infantry therefore walk a
0.8 s four-phase cycle, fight a 1.2 s cycle and mark time on a 1.0 s cycle. **Nothing scales this with
speed**: a charging unit's figures cover far more ground per tick (see "Models chase the unit") but their
legs cycle at the same 0.8 s, and there is no separate run animation — charging, marching, pursuing and
fleeing all use action 3.

**Where the desynchronisation comes from.** Five independent mechanisms, in rough order of visual weight:

1. **Random entry into the loop.** The dominant one. When a model *enters* a looping action, the script
   skips a random 0…n−1 steps before the first frame of the loop, then loops from there forever. Each
   model rolls independently, so a regiment that starts marching on one tick immediately spreads across
   the whole walk cycle instead of goose-stepping. It appears 39 times across the 116 scripts; the skip
   count is the loop length or close to it (4, 6, 8, 10, 12, 14, 15 or 16 depending on the creature).
2. **The offset is chosen once, and only on a change of action.** Re-issuing the action a model is already
   playing does nothing — the script is only reset when the action id actually changes. So the phase
   offsets a unit picks up when it starts marching persist for the whole march, and a unit that walks,
   stops and walks again re-rolls them. A model that is mid one-shot animation cannot be interrupted: the
   new action is queued and applied when the one-shot finishes, which desynchronises it further.
3. **Uneven frame holds inside the loop.** The loops are not `0,1,2,3` at a flat rate — infantry hold
   phases for 2 ticks each (`0,0,1,1,2,2,3,3`), the stand loop is lopsided (`0,0,0,1,1,2,2,2,3,3`), and
   the fight loop visits phases out of order and unevenly (`0,0,1,2,3,3,1,1,3,0,2,2`). Combined with the
   random entry, two models on the same loop rarely look alike even when they are the same number of ticks
   apart.
4. **Per-model variant selection.** Exactly three sprite sets pick their group from the model's stagger
   value, so each figure has a fixed look for life and its corpse matches it. `V = stagger mod 3`, `B = bit 1
   of stagger`, group = base + variant × step, frame = group + phase × 8 + direction as usual:

   | sprite set | actions | group |
   |---|---|---|
   | Peasants | stand, fight, weapon-ready, idle | `120 + 32 V` (120 / 152 / 184) |
   | Peasants | walk (random entry 0…7) | `0 + 32 V` (0 / 32 / 64) |
   | Peasants | dead | `96 + 8 V` (96 / 104 / 112) |
   | Slaves | stand, fight, weapon-ready | `216 + 32 V` (216 / 248 / 280), one held frame |
   | Slaves | idle **and** walk (the same 10-tick loop, no random entry) | `216 + 32 V` |
   | Slaves | dead | `96 + 8 V` |
   | Wagon | stand, walk, fight, ready | `0 + 32 B` (0 / 32), one held frame — a wagon never animates |
   | Wagon | idle (8-tick loop `0,0,1,1,2,2,3,3`, no random entry) | `0 + 32 B` |
   | Wagon | dead | wreck, group 64, no variant |

   The peasant sheet holds three characters (three costumes), so a peasant crowd is a 1 : 1 : 1 mix and each
   corpse matches its living costume; slaves use a different block of the same sheet and never use the move
   block, so they shuffle at idle pace. Wagons of a caravan alternate between two looks in pairs. No soldier
   family uses these. 🟡 Why slaves use the 216 block rather than 120 is worth one visual check.
5. **Staggered collapse.** A model whose wounds run out does **not** fall immediately. It is marked dying and
   keeps playing its current animation until the delay `d` has elapsed, then switches to action 6; the collapse
   comes exactly `d` ticks after the lethal wound (a delay of 1 means the next tick):

   ```
   d = ((stagger & 3) + 1) × 18                       # 18, 36, 54, 72 ticks = 1.8 … 7.2 s
   if death_kind in (1, 2, 3): d = 1                  # fire, missile / slain outright, warpfire — in and out of melee
   elif the model's unit is not in close combat: d = (d >> 2) + 1      # 5, 10, 14, 19 ticks
   ```

   The test is the **unit** being in close combat, not whether the individual model has a partner: a unit that
   is only shooting, charging or routing gets the short delay, an engaged unit the long one. A whole unit falls
   together only when it is slain outright (kind 2, one tick — Da Krunch, the Conflagration finale, artillery
   misfire, fanatic death) or a building is destroyed (zero delay); a regiment wiped out by ordinary wounds
   still uses each model's own delay. On reaching action 6 the model is given a **random facing**, which is
   why corpses lie at all angles rather than facing the way the figure died.

**Drawn facing is its own slew.** The facing used to pick the sprite direction is not snapped to the
target each tick: it turns by at most **32/512 of a turn (22.5°) per tick**, i.e. one of the eight sprite
directions per tick. Which target it turns towards depends on the action: a model playing *stand still*,
*weapon ready* or *shoot* faces **the unit's facing**, while a walking or fighting model faces **its own
heading** — its direction of travel or its opponent. A dead or one-shot-locked model's facing is frozen
where it was. The exception is RollingStock (wagons), whose models snap their drawn facing instantly with
no slew.

**The shooting fire event** is posted by the script, not by the combat code. The shoot script is: set the
shoot pose, **skip ahead a random 0…3 of its first four pose ticks**, hold the pose, fire, hold two more ticks,
then return to the stand pose. The random entry skips *ahead*, so it makes the shooter fire *sooner*. Counting
the tick on which the order applies as tick 1:

| skip | fire event on tick | back to stand on tick |
|---|---|---|
| 0 | 5 | 8 |
| 1 | 4 | 7 |
| 2 | 3 | 6 |
| 3 | 2 | 5 |

So each archer's fire tick is uniform over 2…5 (the note "four ticks into the pose" is only the latest case).
A volley is ordered for the whole unit at once (shoot action, modulus 4, countdown = the number of models N)
with the reload time stamped at that moment. Each model reaching its fire event decrements the countdown and
**posts an event when the new value is divisible by 4**, so exactly `ceil(N / 4)` events are posted — decided
by *arrival order*, not model index (N = 10 posts on the 2nd, 6th and 10th arrivals; N = 4 on the 4th). Each
posted event launches one projectile from the model that posted it, and events already posted always launch,
even if the unit has since become "not ready"; the reload only gates ordering a new volley. If models die
before firing they never post and the posting positions shift. Artillery and other classes order only the
leader or machine, with modulus 1. Expected launches per tick over a volley (each fire tick uniform 2…5):
N = 4 → 0.00 / 0.06 / 0.25 / 0.68 on ticks 2 / 3 / 4 / 5; N = 10 → 0.77 / 0.59 / 0.61 / 1.02; N = 16 → 0.62 /
1.01 / 1.00 / 1.37; N = 20 → 0.88 / 1.25 / 1.25 / 1.62 (small units tend to launch late).
Implement the per-model fire tick through the animation and the countdown rule; do not pre-pick the posting
models.

**Death kinds.** The kind is the damage type of the killing wound, kept on the model and read by the death
script:

| kind | meaning | produced by | collapse delay | shown |
|---|---|---|---|---|
| 0 | ordinary | close combat and every damage-type-0 spell | staggered (above) | the family's own corpse |
| 1 | fire | fire spells, Dragon breath, Flamestorm, Conflagration damage, a collapsing building | 1 tick | burning figure, then charred corpse |
| 2 | missile / slain outright | every missile weapon and shot, Da Krunch, the Conflagration finale, artillery misfire, fanatic death, the Giant's blast | 1 tick | the family's own corpse |
| 3 | warpfire | Warpfire Thrower flames and its death blast | 1 tick | green burning figure, then charred corpse |

On kind 1 or 3 the death script switches the model onto the general battle-effects sprite set and plays a fire
sequence; that covers standard infantry, archers, mercenaries, Dwarfs, Orcs and Goblins, mounted units, Skaven,
wizards, Troll / Rat Ogre / Treeman, peasants and slaves, squig hoppers, sheep, the Doom Diver and the Warpfire
Thrower. Wagons, pack ponies, fanatics, mortars and all war machines, Wyvern, Dragon, Giant, Gyrocopter and
Doomwheel never burn (their dead script ignores the kind); the caravan and machine wagons chain into the wagon
wreck. The model is removed from its unit's roster (strength drops, the formation re-forms) when the sequence
starts and then burns as a free figure:

| body class | orange (kind 1) group | green (kind 3) group | burn phases | burn length | charred corpse group |
|---|---|---|---|---|---|
| infantry and everything else | 0 | 16 | 0…7 cycling | 41–56 ticks | 32 (8 directions) |
| cavalry (and sheep) | 8 | 24 | 0…3 cycling | 41–48 ticks | 40 |
| monster | 12 | 28 | 0…3 cycling | 41–48 ticks | 48 |

Infantry start a random 0…15 ticks into a 16-tick lead-in and then run five full laps (`16 − r + 40` ticks);
cavalry and monsters start a random 0…7 into 8 lead-in ticks and then run ten laps of 0…3 (`8 − r + 40`). After
the burn the corpse takes a random facing, phase 0, held forever. The burning groups are not direction-indexed.
A Warpfire Thrower that dies from a non-fire kind does not simply fall: it spawns five flame puffs (centre, then
8 units right, left, up and down, two ticks apart) and a final blast of radius 48, D6 wounds, strength 5, damage
type 3, so anything it kills burns green; the Giant's death ends with a radius-40 blast (D6, S5, damage type 2).
🟡 The battle-effects frames are matched to these groups by eye, one frame per phase.

**Other things the scripts can do**, listed here because an engine that only implements frames will look
wrong: set and clear model flags, branch on model or unit flags and on the death kind, mark/loop/repeat
with a counter, yield a tick without changing the frame, chain into another action or sprite set, play one
sound or one of a random list, spawn blood decals, randomise the model's facing, and toggle the unit's
attached light/effect. There are 59 such operations in total.

### Routes, collisions and visibility ✅

The key visibility constants are recorded here for implementers.

- **Waypoints**: `ExecuteGoto` replaces and Ctrl-click appends to a queue of
  **at most 9 manual waypoints**; a point within 17 units of the queue head or tail is ignored. Moving
  onto the unit's own position just halts and re-forms.
- **Routing is not pathfinding**: a unit walks straight towards its current waypoint. When `ObjectsOnPath`
  finds the first blocking map object on the line (scenery, spell area objects **or another
  unit's footprint**, tested with the same `asin(radius / d)` geometry as missile obstruction), `GotoTarget`
  dry-runs a detour to the left and to the right (cost `4 × turn + distance` per
  leg, +12 000 for leaving the playable area, abandoned beyond a full turn or cost 5 999) and keeps the cheaper
  side; if both exceed 11 999 the unit gives up ("can't find the way to target"). Each tick `PlanStep`
  deflects the heading around the current obstruction again. `Nav*`, `SOLID`, `INVSOLID` and
  `BATTLEEDGE` boundaries are polygon-membership obstacles only, never a graph, so units can get stuck against
  concave shapes; an engine may use real pathfinding without visible change on the open maps.
- **Region masks**: `InRegion`/`NotInRegion`/`RegionCrossings`
  scan the 40-byte boundary records whose flags are active and match the mask; `INVSOLID`
  inverts containment (the outside of `BattleEdge` is solid); crossings snap to the boundary so movers slide
  along it. `0xB0` routes and fanatic jumps, `0x200` `SightEdge` (spotting only), `8`
  `ViewEdge` and `0x40` `CameraEdge` (camera only), `0x20` leaving the table, `0x90` the rout probe.
- **Collisions** (`ResolveUnitCollisions`, once per tick): every overlapping pair of footprints
  or objects is resolved. **Friendly units and solid scenery push apart** by half the overlap each
  (circle-circle resolution; a charging unit hitting something within its 45°
  front arc ends the charge, event 0x09). **Enemy contact** engages (fear test, charge, redirect, rout: section
  5.5 and 7.3); contact with a routing unit makes automatic contact attacks (section 7.7). An `INVSOLID` object
  straight ahead sends event 0x27. There is no sub-tick sweep, so fast units can briefly overlap.
- **Visibility** (`IsVisible`), shared by hidden-unit spotting and "is my target visible" for
  AI shooting and casting: the target must lie within the looker's **view cone** (half-width 71/512 turn =
  **±50°**, doubled to ±100° while in melee), one of three sample rays towards the target (spread by its
  footprint) must be free of scenery (`ScanObjectsOnLine`, the missile obstruction test), and the line must not
  cross a **`SightEdge`** boundary (if a battle has none, "No Sight Boundary" and visible). **No range limit and
  no terrain height** anywhere in spotting, shooting or casting line of sight: hills never hide units.
- **Hidden units** (`SpotHiddenUnits`, run by threat detection): each hidden enemy that passes
  `IsVisible` is revealed **permanently** (flag `0x80000` cleared), with event 0x1C to it and 0x1D to the spotter.
- **AI decisions**: `PickBestTarget` scans all units for the highest `UnitScore`; `DetectThreat`
  spots hidden units, then keeps or re-picks the threat unless braced. `RunAway` (206) is one
  reactive flee step per behaviour period (±67.5° away from visible enemies), `CircleAroundTarget` (228) one
  offset move of +11.25°. **There is no army-level AI**: coordination comes only from the "assist a friend who
  attacks" rule (event 0x13, `AIQuery` 9/10) and from mission scripts that assign "attack the n-th nearest
  enemy" targets (opcodes 176–191) to individual units. AI armies are not repositioned at battle start (their
  `.BTS` positions are used).

### Unit behaviour scripts and events ✅

**Most consequences of morale are decided by bytecode, not C code.** Every live unit runs a behaviour
script each tick (the per-tick script step, called from the battle tick).

- **Code**: 32-bit words; a word with bit 15 set is opcode `word & 0x7FFF`, dispatched through a
  **232-entry handler table**; `0x0ABC` is a label, `0x80E8` ends a script. Operand counts
  follow from each handler's returned PC. Handlers of the table have no direct callers, which is why
  several rule functions looked orphaned (the game is opcode 0x5B, the game opcode 0xC8).
- **Per-unit state**: current script `script`, PC `pc`, return stack `return_stack`/`return_stack2`, interrupt
  script `interrupt_script`, pending switch `pending_switch`, current event `current_event`, event queue head `event_queue`, count `event_count`.
- **Event dispatch is pre-emptive, not polled** ✅ (traced September 2026): every tick, before a unit's
  script executes any of its own instructions for that tick, the interpreter itself checks whether the
  unit has any queued, unconsumed events. If it does, the interpreter forces entry into the unit's
  registered interrupt script right there — regardless of what instruction the main script's program
  counter currently sits on (even, for example, in the middle of an indefinite idle `Wait` loop) — and
  arranges to resume the interrupted script afterward. Only then does it run the unit's (now possibly
  switched) script for the rest of the tick. The "enter interrupt script" opcode has no callers from
  any library or mission script anywhere in the corpus; it exists purely as this internal, once-per-tick
  scheduler mechanism, not something a script is expected to invoke itself. A unit idling in a
  `Wait`-only loop for most of a battle (the common case) is therefore still reactive to events like
  "you are being charged" every tick, without its own code ever polling for them.
- **Script source**: `the original game(id)` calls `DLLGetScriptPointer` of the mission DLL named by
  `loadScript`. In every `SCRIPT/BFxxx.DLL` that export is a table lookup: ids from 0 → the mission's unit
  scripts (3–37 per DLL; `set:script=N` values are always below the DLL's count), ids **100–170 → a shared
  library, byte-identical in all 45 DLLs**. `DLLReturnInstCount` returns 33000 = `0x80E8` (the end-of-script
  word): a format check, not an instance count. `set:script=PLAYER_SCRIPT` is
  library script 100. So the "mission logic" DLLs are **data** (bytecode), not native code to execute.
- **Control opcodes** (names assigned):
  push PC (0x06), loop jumps `Loop`/`LoopIfTrue`/`LoopIfFalse` (0x07–0x09), goto script (0x0C), switch script at
  end of tick (0x0D–0x10, 0x0F high priority), gosub/return (0x11/0x13), end of an event handler: return to the
  interrupted script or apply a pending switch (0x14), yield (0x17), skip if true (0x19), test/set/clear unit flags `unit_flags` (0x22–0x26) and `unit_flags2`
  (0x29–0x2B), condition flags (0x2E–0x30), `GetEvent` (0x68), `ConsumeEvent` (0x69), `CaseEvent N`
  (0x6A), `Break` (0x6B, jumps to the next label, operand = label word `0x1ABC`), `If/IfNot/Else/EndIf` (0x6C–0x6F), queue event to self (0x5E/0x5F), send to own side / **enemy side**
  (0x62/0x63), `Query N` (0x16, cases of the AI routine), `React N` (0xC2).
- **More from the catalogue** ✅: after `ExecuteOrder` applies a player order, the interpreter drops the target and
  restarts the unit's script at its restart point (op 0x1E). `SetThreatRange` (0x31) sets `threat_range`, used by the AI
  threat score (`UnitScore`): `worth × (range − d) / round(range / 4)` with the octagonal distance
  `d = max(|dx|, |dy|) + min(|dx|, |dy|) / 2`, 0 for friends, broken, `CantMelee` or hidden units and beyond the
  range; ×4 if the enemy targets this unit, or ×32 instead if it is also charging (see "Routes, collisions and
  visibility"). Node opcodes move to a node (0x1F), face it (0x20), teleport to it (0x49), place and re-form there
  (0x4A) and scatter models around nodes (0x48). 0x4C, 0x5C, 0x5D are instant 90°/180° turns, 0x4B a wheel.
  Events 0x14/0x15 are reports from a unit to its linked parent (op 0x65), 0x33 comes from op 0x66 and 0x37 from
  op 0x63. A wizard busy casting ignores being charged and "enemy routed" events. Operand sizes of 0x1F, 0x87, 0x95
  and 0x9D are one word longer than first derived.
- **AI and mission opcodes** ✅: `IfObjective n` (222) tests whether the `.BTS` defines
  objective letter n; library scripts 100, 101 and 152 branch on objective G (behaviour 12, units become allied,
  side `0x40`). The standard mission AI is behaviour 15 `TrackThreat` (290 mission uses): keep the best threat and
  attack it when its score exceeds the unit's worth. Opcodes 176–191 attack the n-th nearest unit with side/class
  filters; 206 is an AI "run away"; 208 turns an artillery crew into Infantry when its machine is lost. Some
  handlers are duplicates (181 = 180, 185 = 184, 136 = 175) or unused (137, 171, 173, 174).
- **Events**: 14-byte records `[recipient, code, source, parameter, x, y, link]` in a 128-record pool at
  the relevant data, queued per unit by `SendEvent`, `BroadcastEvent` and
  `SendEventToSide`. There is no C handler table: every unit script has the frame
  `GetEvent; CaseEvent a … Break; CaseEvent b … Break; Gosub 153…156 (library defaults, all ending in 152);
  ConsumeEvent; loop`. Player units run library script 100, which installs an event handler by class
  (101 default, 102 Artillery, 103 Wizards, 104 Archers → 154/155/156); mission scripts gosub 153.
- **`React N`**: per race (`s_race & 7`) and code, a battle message (table the relevant data),
  a leader portrait expression (the relevant data) and a speech sample (the relevant data): 1 "Engage!", 2 "CHARGE!"
  ("WAARRGGH!"), 3 "Destroy them!", 4 "Retreat!", 5 "My men fear the beast!", 6 "Flee the abomination!",
  7 "We fight to the death!" (Dwarfs), 8 "No mercy!" (hatred), 10–14 shooting and order replies, 17
  "Re-group!", 19 "Hold!".

| Event | Sent by | Meaning | Default handling (library) |
|---|---|---|---|
| 0x01 | op 0xD9 | script signal | return from script |
| 0x03 | threat detection (Query 11/12) | enemy to fight | op 0x39 → attack script 159 |
| 0x04 | attack order | attack target | op 0x3A → approach script 158 |
| 0x06 | `ExecuteOrder` | charge order | script 106 (React 2) |
| 0x07 | charge start, threat reaction, contact handler | you are being charged | fear/terror test op 0x42, then brace (script 161) |
| 0x08 | `EngageCharging`, charger flagged `0x8080` | contact by a charging/pursuing unit | flank/rear test op 0x5B (section 7.8) |
| 0x09 | end of a charge movement | charge against you ended | re-acquire the charger |
| 0x0A | `Engage`/`EngageCharging` | engaged in close combat | melee script 165 |
| 0x0B | movement collision | bumped into a unit | engage it (Query 8) |
| 0x0C | break test, panic, flank test, lost grid, contact handler | **rout** | op 0xC8, React 4, rout script 162 |
| 0x0D | failed fear/terror | **flee from a fear/terror enemy** | op 0xC8, React 6, rout script 162 |
| 0x0E | `FleeingUnitUpdate` (broadcast) | a unit left the battlefield | drop it as target |
| 0x0F | `StartRout`, withdraw | an enemy broke or withdrew | pursue or switch opponent (op 0x53) |
| 0x10 | rally, pursuit restraint, pursuit end | **rally / stop pursuing** | React 17, re-form script 163 |
| 0x13 | own attack script, missions | a friendly unit attacks | look for a target (Query 9) |
| 0x16 | `RemoveUnit` (broadcast) | unit removed | retarget |
| 0x17 | `RemoveModel`, model flag `0x40` | leader/character killed | re-form |
| 0x18 | `DestroyObject` (broadcast) | building destroyed | target gone |
| 0x19 | op 0x56, pairing code | current opponent gone | clear target, re-form |
| 0x1A | engagement code | opponent switched to another unit | re-acquire |
| 0x1B | op 0x53 | enemy routed while not in melee with it | queue 0x19 |
| 0x1C / 0x1D | the game | hidden unit spotted / was spotted | ops 0x40 / 0x41 |
| 0x1E | shooting order | missions only | |
| 0x27 | collision pass | enemy footprint straight ahead | missions only |
| 0x2B / 0x2C / 0x2D | order 0x17, casting animation end | cast a spell / launch it / use an item | casting scripts 132, 133, 142 (section 8.8) |
| 0x31 / 0x32 | Madness | became mad / madness ended | scripts 149 / 168 |
| 0x34 | movement | destination reached | |
| 0x05 | `AIQuery` case 5 | message to the unit's current target (`engaged_enemy`) | mission scripts |
| 0x14 / 0x15 | op 0x65 | report from a unit to its linked parent | mission scripts |
| 0x33 | `AIQuery` cases 16/20, op 0x66 | threat within reach (fanatic parent units) | mission scripts |
| 0x36 | `AIQuery` case 12 | 🟡 | mission scripts |
| 0x37 | op 0x63 | event sent to the enemy side | mission scripts |
| 0x38 | `AIQuery` cases 19/20 | battle state 4 → 5 (broadcast) | |
| 0x35 | – | unused (no script handles it) | |
| 0x30 | pairing, withdraw | alone in a combat grid / disengaged | leave grid, re-form |

Mission scripts mostly add cases for 0x03, 0x04, 0x05, 0x13, 0x14, 0x15 and 0x1B.

**Tool** ✅: `whshr/behaviour.py` reads the script tables of every DLL (the lookup of `DLLGetScriptPointer`
is emulated, so each DLL's ranges are decoded, not assumed) and decodes with a shipped table of 232
instruction lengths and the catalogue names; `python3 -m whshr check` ("behaviour scripts") verifies all 45
DLLs: 3787 scripts (592 mission scripts, 1 to 37 per DLL), 125 519 words with no stray word, the library
identical everywhere, `DLLReturnInstCount` = 33000, 224 of 232 instruction lengths confirmed from the handler
bytes (the other 8 transfer control or scan forward), and every `set:script` value of 53 battles present in
its DLL. `python3 -m whshr scripts <installation> [DLL] [ids…]` prints summaries and listings. Library
scripts 152–156 have **no end word**: each ends in `ReturnGosub` followed directly by another script.
Interpreter details: a word is read as signed 16 bits; `0x80E8` is never executed (only a sentinel for forward
scans); any other non-opcode word is a debug print and does not advance the PC.

**Library scripts 100–170** ✅.
A player unit runs 100 and gets a class handler (101–104); each handler handles orders and threats, then
gosubs a class layer (153–156) handling morale (rout, fear, pursuit, madness), which ends in the common layer
152. Mission units use the same pieces directly: their event loops gosub 153–156 and AI actions switch to
158/159/164.

| Ids | Role |
|---|---|
| 100 | `PLAYER_SCRIPT`: threat range 240, class handler, threat mode 12 if objective index 7 is defined else 11, wait for battle start, idle |
| 101–104 | player handlers: infantry/cavalry, artillery (crew becomes infantry when its leader dies), wizards, archers; threats are only answered when **independent** |
| 105 / 106 | player attack order (approach, charge when in reach → 160) / player charge order (`ChargeForward`) |
| 107–117, 123–125 | shooting: at a building, a unit, at will, single attempt, launch, 90 % range, hunt, volley (`TargetValid` → animation → projectiles), stop to shoot |
| 118–122 | AI skirmish: evade threats (`RunAway`), advance on nearest/current target, hunt steps |
| 126–128 | shooters' threat reaction, archers after an enemy breaks (keep shooting, no pursuit), maddened shooter |
| 129–149 | magic: cast at target / nearest enemy, cast order 132 (turn, animation, launch 133), AI wizard loops 135–140, turn to cast 141, cast now 142, advance/line of sight/stop 143–146, wizard threat reaction 147, after an enemy breaks 148, maddened wizard 149 |
| 150 | null handler (consumes events; spawned templates, script 170) |
| 151 | AI default handler (installed by some missions) |
| 152 | common event layer: madness end, grid alone, units leaving the battle (event 0x36, objective index 7), orders, targets, melee → 165, flank/rear test, rally, spotted, items |
| 153–156 | morale layers: infantry, artillery (rout events ignored), wizards, archers |
| 157, 162 | flight of an artillery crew / rout (the flight itself is C code) |
| 158–161 | AI attack order, AI threat attack, charge the target (`ChargeTarget`, fear test), brace for a charge |
| 163–165 | rally and re-form, pursue, melee (idle; close combat is C code) |
| 166–169 | separate after a collision (🟡), maddened infantry, madness ended, circle for line of sight |
| 170 | 🟡 leave the battle: teleport to node 24, rally, remove from the battle |

### Missions and objectives ✅ / 🟡

Per-battle detail and the BF001 walkthrough are retained in private research notes (the survey tool
`J/survey.py`). Checked before merging: the objective table and letter indexing, the battles defining G, and the
`SPRITES.PBX` explanation (re-run with `J/sprites_check.py`).

- **Mission scripts use only the catalogued opcodes**: all 45 DLLs were decoded; patrols, ambushes,
  reinforcements and guard behaviours are built from node opcodes, timers, events and `AIQuery` calls. There is no
  mission-specific opcode family.
- **Spawning**: only Night Goblin fanatics are created at run time (opcode 0xD3, three copies at lateral offsets
  0/−20/+20, in BF004_5, BF015, BF034, BF038). Everything else exists from the start.
- **`hidden:`** units exist on the battlefield but are invisible and untargetable until spotted (section "Routes,
  collisions and visibility") or placed. **Delayed reinforcements** are hidden units whose script first waits (BF001:
  three Clanrat Warriors wait 150 ticks, then march in along nodes 8 and 9).
- **`SPRITES.PBX` contents** ✅ (verified independently): in every campaign battle, the bundled sprite files are
  exactly the `.BTS` units' `troopsprites`/`banner`/`leaderportrait` sprites plus the `loadspr` entries (`GENBATT`,
  animated terrain such as `U_WATER`, `LAVA*`, `TORFLAM`, `BFK_*`, `N_FIRE`, `BEAM`). The player army's sprites come
  from the permanent `BINARY/` set. **No extra troops are spawned**; the old "20 of 44 battles" mismatch counted
  `loadspr` terrain animations.
- **Pre-battle deployment**: all phase rules, default slot allocation, marching-order effects,
  placement constraints, controls and open questions are in [deployment.md](deployment.md).
- **BF001**: patrol and attack scripts for Hiln's Guard and Sleaquit, Otto Hiln with a short threat range and a
  scripted flight towards node 5 (🟡 exact trigger chain), the delayed Clanrat wave, and standard interrupt
  handlers; nothing beyond the general interpreter and library scripts is needed to run it.
- **Objective table** ✅ the relevant data: one record per objective letter, indexed `L − 'A' + 1` (record 0 is empty; opcode 222
  `IfObjective` uses the same index), holding the defined flag (set by the `.BTS` parser, which also links
  the defined letters), the flags, the in-battle caption (`GMTXT 33000 + L − 'A'`), the evaluator function,
  the met flag and the numbers `a, b`. Flags: `0x1` ends the battle when met, `0x2` evaluated every tick,
  `0x4` no caption in the end-of-battle list, `0x8` evaluated in the separate pass, `0x10` still evaluated after the
  battle is decided, `0x20` custom debrief line. **Battle-ending letters**: A (Eliminate the enemy), F (BF009), H
  (BF015, BF017), N (Get past the Dragon, BF014) and Z (the silent loss condition).
- **What actually ends a given battle is mission data, not a fixed rule** ✅ — important for an implementer:
  only these five letters can *ever* end a battle (that's fixed by the game's code, the same for every
  mission), but whether one is *active* in a specific battle depends entirely on whether that mission's
  `.BTS` declares it, and different missions make different choices:
  - **Z** (the loss condition — player side wiped out) is declared in **50 of the 54 campaign battles**,
    close to universal. An implementer can treat "player army eliminated → defeat" as the default loss rule
    and only needs to special-case the 4 battles that omit Z.
  - The **win condition is usually A** ("eliminate the enemy" — declared in **47 of 54** battles), but three
    battles replace it with a different letter instead of also declaring A: **BF009** declares F in A's
    place (F runs the identical "wipe out the enemy" check, just tracked in its own slot), and **BF014**
    (the dragon mission) declares N in A's place (N runs A's check *plus* requires a player unit to reach a
    specific point — "get past the Dragon"). Neither battle also declares A: the replacement is exclusive,
    not additive.
  - **BF015 and BF017** (the two siege missions) are the one case where **two** battle-ending letters are
    declared together: both **A and H** are active at once, so either "eliminate the enemy" *or* "the siege
    gate reaches its breached state" ends the battle, whichever happens first.
  - So the general shape is "one loss condition (usually Z) racing one or two win conditions (usually just
    A, sometimes F or N instead of A, occasionally A and H together)" — but an implementer must read each
    mission's own declared letters rather than assuming a single game-wide pair. Within one tick, only the
    *first* flag-`0x1` objective the game happens to check that returns "met" decides the battle (relevant
    only for the A+H case above; no evidence in the shipped data of the two actually racing in the same
    tick).
- **Evaluation** ✅: battle set-up calls every defined evaluator with mode 1; the game runs each tick (from
  `BattleTick`) and tests the not-yet-met objectives with flag `0x2` in mode 2; the first met objective with flag
  `0x1` decides the battle (`runtime state = 1`), opens the win or loss dialog and plays the end
  stinger. the game evaluates flag-`0x8` objectives in mode 3 from a less frequent poll; at the end
  the game lists captions, or calls the evaluator in mode 4 for a custom debrief line.
- **All 26 letter evaluators read** ✅ (static analysis). Every evaluator shares the same four-mode contract
  (1 = initialize/snapshot a baseline, 2 = per-tick met-check, 3 = slow-pass met-check, 4 = custom debrief text),
  and only letters **A, F, H, N, Z** carry the "ends the battle" flag — independently confirming the flag reading
  above (no other letter in the shipped data has ever been seen with that bit set either). What each evaluator
  actually counts, in behavioural terms:

  | Letter | What it checks | Ends battle? | Notes |
  |---|---|---|---|
  | A | Count of enemy-side units still active in the battle, against a snapshot taken at battle start; met once none remain (enemy wiped out or routed off). | ✅ | The generic "Eliminate the enemy" condition; per-tick. |
  | B | Percentage of a specific NPC population (the same population category used by the villager objective) still present, against a start-of-battle snapshot; met when the survivor percentage is at or above the mission's threshold. | – | "Protect the villagers." Evaluated on the slow pass; has a custom debrief line. |
  | C | Percentage of a specific structure-type entity population still present, against a start-of-battle snapshot; met at or above the mission's threshold. | – | "Protect the buildings." Same shape as B; custom debrief line. |
  | D | Count of a wagon/rolling-stock-type, allied-side population lost since battle start; met when losses stay at or under the mission's allowed threshold. Evaluating D also gives any pending "downed but recoverable" allied units in that population a chance to be restored to the active roster. | – | "Protect the wagons." Slow pass only. |
  | E | Percentage of enemy-side **models** (not units) killed since battle start (a headcount, not a unit count); met at or above the mission's threshold. | – | "Leave no survivors." Distinguishes model casualties from unit count (contrast with A). |
  | F | Same underlying "count remaining enemy units against a start snapshot" logic as A, but in its own independent slot and without A's extra "already left the field" adjustment; used standalone in the one mission that defines F without also defining A. | ✅ | A mission-specific instance of the same elimination check, not a distinct condition. |
  | G | Recomputes the player roster (merging any allied reinforcements gained during the siege) as part of its init step; its met-check looks for the absence of two specific unit-class categories. The actual "player units get inside the walls" mechanic (unit reaches an interior map trigger, is teleported off-field and reassigned to the allied side) is separate scripted behaviour, not this evaluator — see "Objective G" below. | – | Siege-only (BF015, BF017). |
  | H | Reads a single state value from a "control piece" battlefield object (the siege gate/ram) and is met exactly when that value equals a specific state code. | ✅ | Siege-only; a direct state check, not a count. |
  | I | Initializes by locating a target node and, once located, by spawning something at that node's position (consistent with "Ambush," an ambush trigger placed at a location) and enabling related UI/state flags; its later-mode branches run a follow-up action but do not themselves return "met." | – | Evaluated on the slow pass; no caption in the end-of-battle list. |
  | J | Only becomes active after the battle has already been decided by another objective; if a "control piece" object's state hasn't advanced past a certain point once the battle ends, it advances that state and opens an additional in-battle dialog. Used only by fanatic-spawning missions. | – | A post-decision cleanup/notification objective, not a win condition of its own. |
  | K | Locates a target node holding a nameable item; once a player unit is within range of that node, the item is added to that unit's inventory and the objective becomes met. | – | "Get a unit to secret area" — in fact a pickup: reach the node **and collect the item there**. Shares its logic with X via a common helper, in an independent slot. |
  | L | Snapshots and re-snapshots a population count (same style as B/C/D) but its met-check is never reached in the read code path; effectively inert as a stand-alone win condition. | – | No confirmed "met" behaviour found. |
  | M | Always returns "not met." | – | Unused/placeholder. |
  | N | Runs the exact same "count remaining enemy units against a start snapshot" check as A (sharing A's tracking slot), **and additionally** requires at least one player unit to be within range of a specific target node. Only defined in missions that omit A. | ✅ | "Get past the Dragon": kill (or rout) the enemies present **and** get a unit past the guarded point. |
  | O | Looks up a specific named unit and requires it to have an associated "leader" sub-record; once found, is met when a particular status flag on that leader unit becomes set (consistent with the leader having fled or surrendered rather than been killed). | – | "Capture Guy Gourard." |
  | P | Looks up a specific named unit by its identity tag; met for as long as that unit is still present in the active roster (i.e. it has not been killed or removed). | – | A "keep this specific unit alive" check, reused per-mission. |
  | Q | Scans the battlefield's scenery/object list, counting how many of a particular scenery category are still standing as a percentage of the original total; met at or above the mission's threshold. | – | "Protect the forest": percentage of trees left standing. |
  | R | Always returns "not met." | – | Unused/placeholder (see correction below). |
  | S | Always returns "met" as soon as it is first evaluated (on the slow pass), regardless of any battlefield condition. | – | "Capture Hiln" in BF001. The evaluator itself performs no check; whatever "capturing" means in play is tracked elsewhere (e.g. the target's own scripted flee behaviour), not fed back into this function. |
  | T | Identical unconditional-"met" behaviour to S. | – | "Rescue Ilmarin." Same caveat as S: the evaluator is a stub: the actual rescue condition, if any, is not implemented here. |
  | U | On a repeating timer, picks one player unit and sends it a specific in-battle message (consistent with a "hopeless" warning), and stops the battle music as a scripted atmosphere beat; on the slow pass it sets the shared flag that selects which of two win/lose dialog variants is shown at battle end. Never itself returns "met." | – | "The Mission is Impossible" — an atmosphere/flavour objective, not a win/lose gate by itself. |
  | V | Recomputes a "population killed since battle start" tally for a specific race/class (same shape as B), but always returns "met" once evaluated; the computed tally exists for its debrief number, not to gate the outcome. | – | The "Count Dead Race" debrief statistic. |
  | W | Recomputes an "enemy artillery destroyed since battle start" tally (matched by a broad class category consistent with war machines), but, like V, always returns "met"; the tally is for the debrief line. | – | "Destroy the enemy artillery" — a debrief statistic, not a gate. |
  | X | Same pickup-at-a-node logic as K, in its own independent slot. | – | Paired with K; see K. |
  | Y | Not an independent check: mirrors either of two shared flags set elsewhere (one of which is the same win/lose-dialog-variant flag U also writes). | – | Bookkeeping/debrief flag, not its own count. |
  | Z | The silent loss condition; tracks the player-side population (adjusted for any allied units gained mid-battle) against its battle-start snapshot and is met when it reaches zero, or, read together with the "which objective decided the battle" bookkeeping, also drives the campaign-mode variant of the win/lose dialog and post-battle housekeeping. | ✅ | "Stay alive!" |

  **Corrects an earlier, mistaken reading of this table**: a first static-analysis pass momentarily matched two of these evaluator bodies to letters **R** and **S** by inference from debrief text alone, before the actual letter→evaluator table (a fixed data table, one 40-byte record per letter, read directly rather than guessed) was located. The two evaluator bodies in question are in fact letters **B** and **C**; R and S are, respectively, an unconditional-"not met" stub and an unconditional-"met" stub, per the table above. Any earlier note or engine code that used "R = percentage-threshold villager check" or "S = percentage-threshold building check" should be corrected to B and C.

  **The `a, b` numbers, resolved** ✅: for every percentage/count-threshold evaluator (B, C, D, E, Q; the same
  shape is very likely shared by I, L, V, W), `a` is the mission-authored threshold that the live count is
  compared against (a percentage 0–100, or a raw loss count for D), and `b` is **overwritten at battle start**
  with a freshly computed baseline snapshot (total population/count at the moment the battle begins) —
  discarding whatever value the `.BTS` author originally wrote for `b`. The running "current count" used
  each tick lives in extra scratch space within the same 40-byte record, past the documented `a`/`b` fields,
  not in a separate table. This confirms and sharpens the "compare current counts with the stored numbers"
  hypothesis: only `a` is ever meaningful past battle start; `b`'s authored value is a snapshot the mission
  editor happened to save, immediately replaced by the live count.

  **Confidence**: the mode dispatch, the "ends battle" flags, the `a`/`b` mechanism above, and the
  population/percentage-threshold shape (B, C, D, E, Q) are read directly and are ✅. The specific meaning of
  some internal class/category codes (e.g. exactly which population B's underlying class code designates, or
  which scenery category Q counts) is inferred from the matching debrief text and mission context rather than
  from a named constant, so is 🟡. S, T, V, W's "always returns met" behaviour and R, L, M's "never returns
  met" behaviour are read directly (✅) and are the most surprising findings: several letters that read as
  real win conditions from their debrief text are, in the shipped code, either unconditional or inert, with
  the real condition (if any) implemented by other means (bytecode unit scripts, tags) not confirmed to feed
  back into the objective table.
- **Objective G "Inside the gates!"** ✅ (R60): only BF015 and BF017 (siege battles) define it. Player units then run
  threat behaviour 12; entering map node 14 in battle state 4 moves the battle to state 5 (event 0x38); a unit that
  reaches the interior node 99 in state 4 gets event 0x36, and library script 152 sets the allied side, unit flag
  `0x100` and switches it to script 170, which teleports it to node 24 and removes it from the battle: the unit has
  got inside the walls. The gate itself (a rolling stock unit) is excluded.
- **Mission-only events**: 0x05, 0x14/0x15, 0x33, 0x37 and 0x38 are used only by the fanatic battles and the two
  siege battles; **event 0x35 is never handled by any script** (unused).

### Player orders and the command panel ✅

The battle window maps panel buttons (records at the relevant data, icons = frames of
`ICONS.BOP`; there are no tooltip strings) to a global order code (`runtime state`, cleared every tick).
`ExecuteOrder`, run from the behaviour script, applies it to **player units** only: to every
selected unit (unit flag bit 25), otherwise to the unit's own pending order (`pending_order`); orders 0x17 and 0x1B act
only on the focused unit. The panel shows a button set by class and state (idle, attack
sub-panel, broken/pursuing, melee, charging: none). Pre-battle order handling and panel
variants are documented in [deployment.md §3–4](deployment.md#3-player-interaction).

| Order | Button (icon) | Effect |
|---|---|---|
| 1 / 2 | Move (boots) + click / Ctrl-click | go to point / add waypoint; queued while busy |
| 3 | Attack (crossed swords) + click | event 0x04: approach and attack a unit (not `CantMelee`) or building |
| 0x0B–0x0E | face point, turn left/right 90°, about face | facing ∓0x80 / +0x100 (increasing facing = clockwise) |
| 0x0F / 0x10 | ranks up / down | re-form with ±1 rank |
| 0x13 | Withdraw (banner flag, melee) | disengages only when fighting rolling stock or furniture (classes 7, 9) with no other enemy unit fighting its models; **against living enemies the unit routs** (a voluntary rout) |
| 0x14 | Rally (open hand, broken or pursuing) | toggles the rally / pursuit-restraint attempts (section 7.4) |
| 0x15 | Charge (war horn) | event 0x06 → script 106 `ChargeForward` (op 0x4F): a charge **straight ahead**, reach 12 × `s_rlmv`, not inside `0xB0` regions |
| 0x16 | Fire (crossed bow) + click; Ctrl = Gyrocopter bomb | `OrderFire` (section 8.1) |
| 0x17 | Magic (chaos star) + spell + click | cast (focused unit) |
| 0x19 | Halt (open hand) | halt and re-form, "Hold!" |
| 0x1A | **Independent** (head in profile; idle panel) | toggles unit flag bit 27 |
| 0x1B | **Fight harder** (flexed arm; melee panels only) | sets unit flag bit 30 on the focused unit |

Orders other than 0x13, 0x14, 0x17, 0x19–0x1B are ignored while the unit is charging, in melee, broken or
pursuing.

- **Fight harder** (bit 30): +1 S on all close combat attacks and return blows, and −1 on every Leadership test
  modifier (break, panic, fear, rally, flank/rear), i.e. **+1 Ld**. `BattleTick` clears it at every segment boundary
  after the unit's step, so one click covers one segment; no cost or limit; never set by AI or scripts.
- **Independent** (bit 27, 🟡 name): the unit rallies and tests pursuit restraint without the Rally order, reacts to
  any enemy within its threat distance (not only one engaging it), keeps choosing new targets when shooting or
  casting, and checks for friends on the line of fire. Off at the start; AI units never have it.
- **Braced** flag `0x100000` ✅: set by `AIQuery` case 7 (library script 161, after event 0x07 and a passed fear test):
  the charger becomes the target and the unit halts facing it. While set, move, attack, turn, rank, charge and
  fire orders are ignored; cleared by a new attack event, "opponent gone", rally (event 0x39) or a still-accepted
  order such as Halt.
- **Charging** flag `0x80` is set by `StartCharge` and by the game when a charging or pursuing unit runs into
  a different enemy (the pursuit becomes a charge, events 0x1A/0x07). **Pursuing** flag `0x8000` only by
  `StartPursuit`.
- Behaviour bytecode sets only unit flags `0x100`, `0x4000000` and `0x20000000`; `unit_flags2` bit 0 anchors war machines,
  bit 3 ("hold fire") is tested but never set; `unit_flags & 0x80000` marks hidden units.

### Battle HUD layout ✅ (readout 🟡)

The deployment HUD variant is documented in [deployment.md §8](deployment.md#8-deployment-hud-reference).

The battle screen is a 640×480 client area made of independent child windows (nothing here is drawn procedurally
except text; all chrome is frames of the `ICONS` sheet, 225 frames, indexed as in `notes/sprite_names.md`).

| Window | Position | Size | Content |
|---|---|---|---|
| 3D view | (8, 8) | 624×417 | terrain and units |
| Command panel | (0, 304) | 640×176 | background = ICONS frame 98 (640×176) |
| Minimap | (425, 7) | 216×297 | bottom edge meets the panel top (y = 304) |

Inside the command panel (coordinates relative to it):

| Element | Position | Size |
|---|---|---|
| Command sub-window (5 button slots) | (492, 0) | 148×175 |
| Selected-unit readout / compass (alternate) | (72, 0) | 128×177 |
| Message text | (200, 0) | 243×61 |
| Scroll text | (0, 7) | 223×60 |
| Spell/item list | (200, 64) | size of ICONS frame 205 |

**Fixed panel buttons** (each is a raised/pressed frame pair; the lower frame is the raised one; the pressed frame is shown
while the mouse button is held and the command fires on release):

| Position | Frames | Size | Function |
|---|---|---|---|
| (11, 8) | 42/43 | 52×52 | rotate camera (left/right mouse button) |
| (11, 63) | 44/45 | 52×52 | zoom / tilt camera |
| (11, 118) | 46/47 | 52×52 | pause / resume; 50/51 (tent) opens the in-battle menu |
| (448, 13) | 58/59 | 44×44 | options |
| (448, 75) | 60/61 | 44×44 | select previous player regiment and centre on it |
| (448, 121) | 62/63 | 44×44 | select next player regiment |
| (140, 4) | 64/65 and 66/67 | 32×48 | two toggles in the message area (helmet, masked head; role 🟡) |
| (224, 9) / (224, 34) | 68/69, 70/71 | 20×20 | scroll text up / down |

**Command sub-window slots** (relative to it; screen = (492 + x, 304 + y); every button 60×60): TL (7, 11), TR (83, 11),
BR (83, 109), BL (7, 109), centre (45, 60). Empty slots show the plain panel background.

**Buttons** (order codes as in the table above; frame pair raised/pressed):
Move 0/1, Attack 2/3, Fire 4/5, Magic 6/7, Items 8/9 (opens the unit's item list, 🟡 meaning), Back 10/11 (centre skull:
cancel and return to the idle set, or back to the Move set), Turn right 12/13, Turn left 14/15, About face 16/17, Ranks sub-set
18/19, Ranks up 20/21, Ranks down 22/23, Ranks-decoration 24 (no action), Facing sub-set 25/26, Face point 35/36, Halt 37/38
and Rally 37/38 (same art), Withdraw 39/40, Independent 52/53, Charge 54/55, Fight harder 56/57. Frames 27–34 (numerals) and
41 are not used by any command button.

**Panel state** is chosen from the selected unit (the panel switches only when state or unit class changes):
no selected unit, or unit charging → none / idle set (below); fighting in close combat → melee set (caster variant if the unit
has spells or items, else non-caster); broken or pursuing → Rally set; otherwise idle.
Sub-sets are entered by buttons: Move → move set; Ranks → ranks set; Facing → facing set; Attack → attack set (caster or
non-caster variant). Fire and Magic keep the set and start a pending order with their own cursor. Any completed order or
Back returns to idle. The panel background never changes; only the buttons do.

Button sets by unit class and state. "Inf" = infantry and cavalry, "Arch" = archers, "Art" = artillery, "Wiz" = wizard,
"Mon" = monster (classes 0 and 7–9 have no buttons). Slots are listed TL / TR / BR / BL / C, `–` = empty.

| State | Class | TL | TR | BR | BL | C |
|---|---|---|---|---|---|---|
| Idle | Inf, Arch, Mon | Move | Attack | Independent | – | – |
| Idle | Art | – | Attack | Independent | – | – |
| Idle | Wiz | Move | Attack | Independent | Magic | Back |
| Idle, nothing selected | – | Move | Attack | Independent | – | – |
| Move set | Inf, Arch | Ranks sub-set | Facing sub-set | Halt | Face point | Back |
| Move set | Wiz, Mon | Turn left | Turn right | Halt | About face | Back |
| Move set | Art | none | | | | |
| Ranks set | Inf, Arch | Ranks up | decoration | – | Ranks down | Back |
| Facing set | Inf, Arch | Turn left | Turn right | – | About face | Back |
| Ranks / facing set | Art, Wiz, Mon | none | | | | |
| Attack set, caster | Inf, Wiz, Mon | Charge | – | Items | – | Back |
| Attack set, caster | Arch | Charge | Fire | Items | Halt | Back |
| Attack set, caster | Art | – | Fire | Items | Halt | Back |
| Attack set, non-caster | Inf, Wiz, Mon | Charge | – | – | – | Back |
| Attack set, non-caster | Arch | Charge | Fire | – | Halt | Back |
| Attack set, non-caster | Art | – | Fire | – | Halt | Back |
| Broken / pursuing | all | – | – | Rally | – | – |
| Melee, caster | Inf, Arch, Art, Mon | – | Withdraw | Items | – | Fight harder |
| Melee, caster | Wiz | – | Withdraw | Items | Magic | Fight harder |
| Melee, non-caster | Inf, Arch, Art, Mon | – | Withdraw | – | – | Fight harder |
| Melee, non-caster | Wiz | – | Withdraw | – | Magic | Fight harder |
| Charging | all | none | | | | |

**Selected-unit readout** (🟡 parts marked): the window has **no stat text**. It draws, in order: the battle's own
`portrait_bg` sprite set frame 0 at (4, 12) (no fallback: a missing portrait is simply not drawn); the unit's animated
portrait (loaded by the unit type's portrait id) at (4, 12); and an ornamental frame of eight `ICONS` pieces (frames
181–188 for the default look, 189–196 for enemy units, 197–204 for wizards/monsters — 🟡 which class bits pick the last
two) at fixed offsets. When nothing is selected the same rectangle shows a compass (frames 99 and 105). Unit name and counts
are not drawn here; whether the scroll-text window shows them was not read ⬜. Using another background than `portrait_bg`
(such as a `BACKALL` frame) is a guess.

**Minimap**: frame layers are ICONS 101 (216×16 top, at (0, 0)), 102 (16×216 left, at (0, 16)), 103 (16×216 right, at (200, 16))
and 104 (216×64 bottom decoration, at (0, 233)); the map area is 184×216 at (16, 17) and shows the battle's plan map scrolled
by an offset that is clamped to the map (right mouse drag pans). Four 44×20 tabs at (63, 241), (110, 241), (63, 264),
(110, 264) (frames 72/73, 74/75, 76/77, 78/79) and a 40×40 book at (162, 242) (frames 80/81) sit on the decoration. The tabs select
one of four marker display modes: 0 every unit has banner and dot; 1 selected units banner and dot, others dot; 2 friendly
banner and dot, enemy dot; 3 friendly dots during normal play (tab-to-mode icon order 🟡).
Drawing order: plan map, the selected unit's waypoints (numbered
dots 161–169, end marker 159), all regiments, the selected regiment again, the camera marker (frames 170–177, 8 orientations).
A regiment is an 8×8 dot centred on its position (fighting/charging base 119 friendly, 111 enemy; normal 135 / 127;
broken 151 / 143; plus one of 8 facing frames) and, if the mode allows, its banner frame anchored 8 px left and 24 px above
the point. Hidden units are skipped. **A left click on the minimap is handled exactly like a click in the 3D view**: with
no pending order it selects the unit under the point (shift toggles multi-select), with a pending order it executes it
there; it never issues a direct move.

**Feedback**: four custom cursors (default, attack, fire, magic) — Attack selects the attack cursor, Fire the fire cursor,
Magic the magic cursor, every other action and Back the default. A click sound plays on button press. There are no tooltips
and no hover highlight; buttons only have up and down frames.

**Implemented** in `whshr/frontend/hud.py` (`whshr/engine.py` adds a `Regiment.hud_class` field for
the class column, derived from the `s_side` race/type byte since this note's own numeric class
encoding was not recovered — 🟡, see the note's own comment on the mapping). Deliberate
simplifications rather than spec gaps: the engine has no spell/item system, so a regiment is always
in the non-caster attack/melee variant; camera rotate/zoom buttons render but the free WASD/mouse
camera already in place is unchanged (`notes/engine_architecture.md`'s own decision not to chase
exact original camera behaviour); the minimap always fits the whole battlefield rather than a
scrolled native-scale viewport (no pan yet); message/scroll text windows and the click sound are
not wired (their content/resource is not specified here); `whshr.engine.Regiment` has one
`target_x`/`target_y`, not a waypoint queue, so only the end marker is drawn, never numbered
waypoints; pre-battle implementation scope is tracked in [deployment.md](deployment.md);
the spell/item list window at (200, 64) is left as background-only chrome
for the same no-spell/item-system reason. The HUD's own two chrome pieces (the command panel and
the minimap) are each designed at their documented native size and scaled with the same
integer-snap factor as `NativeScreenView._layout` (`scene_view.py`), since `BattleView` itself
renders its 3D scene at full window resolution rather than through that letterbox; unlike a plain
centered letterbox of the whole 640×480 screen, each piece is then pinned to its own edge of the
actual window — the command panel to the bottom (horizontally centered), the minimap to the
top-right corner — rather than both floating in the middle of a larger window. The minimap's
selected-marker highlight is a brightness tint on the dot and banner rather than a separate
white-rim sprite (no such frame is documented); clicking a regiment's banner on the minimap, not
only the dot underneath it, selects that regiment (the banner is the larger, more visible target).
The camera marker shows the eye position (pulled back from the look-at target along yaw by the
orbit distance, converted mesh-to-world units as in `battle_view.py`'s panning; the marker is a
flat minimap so pitch does not affect it), not the target itself, clamped to the map area rect so
a large zoom distance cannot push it past the minimap chrome. A small "x" (the ICONS frame right
after the 8 camera-marker frames) also marks the look-at target itself, at the lowest z-order
above the plan map so every other minimap element paints over it.

An enemy regiment can be selected too (3D-view or minimap left-click, at any time - not only with
no player regiment already selected), for its HUD readout/banner/minimap highlight only: the
original lets a player inspect any regiment this way. `whshr.battle_scene.BattleScene.handle`'s
"select" no longer restricts the identifier to a player regiment, but `whshr.engine.Battle`'s
`order_move`/`order_attack`/`order_halt` (and `Hud._button_enabled`, independently) all still
refuse a command for a non-player regiment, so selecting one for inspection never grants it
orders. A first version of this only allowed an enemy click to select (rather than immediately
charge) when nothing player-owned was already selected — the pre-existing "click an enemy with a
selection orders a charge" shortcut took priority otherwise, so re-selecting an enemy while a
friendly regiment was selected silently failed. That shortcut was never part of this note's own
"Player orders and the command panel" (every order needs its own HUD button pressed first, then a
click executes it — "Move (boots) + click", "Attack (crossed swords) + click"); it was an engine
invention (`notes/engine_architecture.md`'s "Controls"). Removed for left-click: a plain left-click
(`BattleView.order_mode is None`) now always just selects whatever is under it, player or enemy,
and only ever issues an order when a HUD button armed one first. The pre-existing right-click
shortcut (`_ground_click(pixel, direct=True)`) keeps its old direct-order behaviour unchanged,
since it is a distinct, deliberate convenience the user did not report as broken.

The four cursors ("Feedback" above) are loaded from `GMCUR.DLL`'s own `RT_GROUP_CURSOR` resources
(`notes/pe_resources.md`, IDs 100-103) via `whshr.frontend.cursors.GameCursors` (shared with
`TroopSelectionView`'s `WHSHR.EXE`-named cursors), never substitute artwork. `BattleView._set_cursor`
switches it purely on `order_mode` (Attack armed → attack cursor; an immediately-issued order, no
action, or Escape → default) - Fire/Magic have their own cursor group ids wired up too, but nothing
currently arms those modes (no engine order exists for them yet, `ORDER_SUPPORTED`). The DLL's own
group→id mapping is not otherwise named anywhere, so the 100=default/101=attack/102=fire/103=magic
order (matching this note's own listed order) is 🟡 PROVISIONAL, and a first round of visual
testing against the running game (2026) found it wrong: id 100 showed the bow/arrow shape where
the hand (default) shape was expected. Confirmed shapes: default = hand, attack = sword, fire =
bow/arrow (magic's shape not seen yet) - the id for each is still open. Get the real ids by running
`python3 scripts/pe_extract.py "$WARFB/FILE/DLL/GMCUR.DLL" extracted/pe_resources/GMCUR` (repo
root) and comparing `extracted/pe_resources/GMCUR/cursor/*.png` against `groups.json`'s member id
lists, then correct `BATTLE_CURSOR_GROUPS` in `battle_view.py`.
`GameCursors` resolves every `*.DLL` target under `FILE/DLL` (`whshr.paths.Installation.file_dir`,
matching every other `*.DLL` resource load in this codebase) and only `WHSHR.EXE` itself at the
installation root - an initial version resolved `GMCUR.DLL` at the root too, so it silently never
found the file and the cursor never changed.

A regiment's banner marker on the minimap is anchored 8px left, 24px above its dot and can hang
outside the minimap's strict inner map-area rect near an edge (more often an enemy regiment's, in
a battle whose armies start apart along that axis). `BattleView.events`'s minimap-click routing
now checks `Hud.minimap_regiment_at` (no inner-rect restriction) as well as `minimap_position`
(inner-rect only, for "move" world coordinates), or such a banner click fell through to
`hit_test`/`occupies` and was silently swallowed as plain HUD chrome - the click never reached
`_minimap_click` at all, regardless of the fix earlier in this section.

Markers (dots and/or banners) can overlap on the minimap - most often several regiments' banners
near each other - so a click can land on more than one regiment at once. `Hud.minimap_regiment_at`
(engine addition, not derived from the original: there is nothing in the research to say how the
original handled this, if it came up at all given its markers are smaller/sparser) resolves the
whole hit stack, in normal top-to-bottom paint order: the topmost hit regiment wins, unless it is
already selected, in which case the click instead selects the bottom-most *other* regiment in the
stack that is friendly (falling back to the bottom-most of any side if none is friendly) - normal
selection promotes the picked regiment to the top of the paint order (`Hud._promote_marker`,
already wired through `Hud.set_selected`), so repeated clicks on the same spot step through
every regiment there, friendly ones first, without ever getting stuck reselecting the same one. If
the already-selected regiment is elsewhere in the stack but not on top, that is treated the same
as it not being in the stack at all (the topmost one wins) rather than a third special case.

That cycling rule is only for a plain click (selecting/inspecting a regiment); resolving an
order's target (Attack) uses a separate lookup, `Hud.minimap_target_at`, that always just
returns whichever regiment in the hit stack is topmost, ignoring current selection entirely - an
order's own acting regiment (`Hud.selected`) is essentially never one of its own targets, so the
cycling rule (meant to make an otherwise-stuck plain-click selection reachable) does not apply.
Issuing an order never changes the current selection either way, on either the minimap or the 3D
view. An Attack order with no regiment under the click point (`BattleView._ground_click`,
`_minimap_click`) is simply cancelled - the order mode clears exactly as if the order had fired
- and logs a `"Cannot attack!"` line to the same debug event log the HUD's own message-text window
would show it in, if that window were wired (see the "Implemented" paragraph above). This mirrors
the classic Warhammer UI's "Cannot!" cue on a targetless order, but only the log line: which SFX
resource plays that cue is not identified anywhere in `notes/sfx.md`, so no sound plays yet.

## 5. Close combat

### Order of blows ✅

the game runs a unit's close combat only **in the segment equal to its Initiative**
(`unit I == segment`). Segments count down from 10, so higher Initiative strikes first. In the first
combat round it also triggers hatred and frenzy shouts (events 8 and 9). Monsters (class 6) go
through, everything else through.

**Initiative above 10** ✅: only two spells write I: "Ere We Go!" sets **I := 20** (and T +1) and "The Curse of
Anraheir" halves I, both restored when the effect ends. A unit with I 20 never matches a segment, so **Orcs and
Goblins under "Ere We Go!" make no close combat attacks** while it lasts (almost certainly a bug; meant as "strike
first"). The **Dragon** (I 20) never runs its own attacks either: it only deals return blows from the attack pool
filled when a battle grid is created around it (at most A = 7 per engagement), plus its breath weapon.

### Attack of one model ✅

For every live model engaged with an enemy model, an attack profile is assembled:

- `A` = model A, doubled by `Frenzy`;
- `WS` = model WS, **+1 when ganging up**: the first model to attack a free enemy model becomes its
  opponent and gets no bonus; every further model attacking that enemy model gets +1 WS (not against
  monsters). Up to 4 attackers fit around an enemy model (section 5.7);
- `S` = attack strength: `weapon_table[s_weap] + S`, +1 while the unit's charge
  counter is non-zero, +1 while the "fight harder" flag (unit flag bit 30, order 0x1B, see "Player orders") is set. Weapon table at
  the relevant data: class 0 → +0, 3 → +0, **4 → +2, 10 → +1**; classes 1, 2, 9 hold `0x83/0x84`
  (bit 7 = fixed strength 3/4, unused by the scripts);
- magic items of the attacking leader and the defending leader are applied (the game,
  section 5.6);
- hatred: if the unit hates the target's race and the combat round counter is below 2, failed
  attacks are rolled once more.

Then the game resolves the attacks:

```
repeat A times:
    if D6 >= TO_HIT[attacker WS][defender WS]:
        repeat wounds_per_hit times:          # 1, more with some items
            if D6 >= TO_WOUND[S][defender T] and armour_save_fails(defender armour, S):
                kills += 1
    if hatred re-roll allowed and this attack scored nothing: roll this attack once more
```

Automatic hits use to-wound and saves, with no to-hit or hatred re-roll,
apply in three cases: (1) the war machine model of an artillery or rolling stock unit (the leader
model, flag `0x40000` set at unit set-up; the crew fight normally); (2) targets of class RollingStock or
Furniture: all attacks go to the unit's first model and the wounds do **not** count for the combat
result; (3) 🟡 contact attacks of charging or pursuing units (reach 12 units, 18 cavalry,
24 monsters) against models that are not in the timed "turning" state set when a unit routs.

**Return blows** ✅ exist only for monsters: `attack_counter` is a per-round attack pool
(A, 2A with frenzy) that only monster models get. Each enemy model that attacks a monster immediately
draws one blow back from the pool (one hit/wound/save roll against the attacker's modified WS, hatred
re-roll allowed, credited to the monster's side); the monster spends what is left in its own Initiative
segment, then the pool refills. A mounted attacker can draw two blows (after the rider and after the
mount).

**To-hit table** at the relevant data, 11 × 11, `[attacker WS][defender WS]` = lowest D6 that hits. For
WS 1–10 it is exactly the WFB 4th edition chart: 3+ if the attacker's WS is higher, 5+ if the
defender's WS is more than double, otherwise 4+. The extra WS 0 row/column give 4/5 (attacker 0)
and 3, or 2 for attacker WS ≥ 7 (defender 0).

**To-wound table** at the relevant data, `[S][T]`: exactly the WFB 4th edition chart for S, T 1–10
(S ≥ T+2: 2+, T+1: 3+, equal: 4+, T−1: 5+, T−2 and T−3: 6+, less: 7 = impossible); T 0 is wounded
on 1+ by S ≥ 8.

### Armour saves ✅

```
armour_save_fails(code, S):
    if code == 6:                    # regeneration
        return D6 < 4               # (and never fails when the damage source sets a flag, see open questions)
    return D6 < SAVE[code] + SAVE_MODIFIER[S]
```

`SAVE_MODIFIER` at the relevant data: `max(0, S − 3)` (S4 −1 … S10 −7), the WFB 4th edition modifier.

`SAVE` at the relevant data, by armour code:

| Code | 0 | 1 | 2 | 3 | 4 | **5** | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Meaning | rating 0 | 1 | 2 | 3 | 4 | **5** | regen. | void | mounted 1 | 2 | 3 | 4 | 5 | 6 |
| Save | none | 6+ | 5+ | 4+ | 3+ | **none** | 4+ (regeneration) | none | 6+ | 5+ | 4+ | 3+ | 2+ | 2+ |

Rating 5 on foot gives **no save**, almost certainly a table error (the string is "Armour Rating 5").
It matters: `s_armr=5` is used by leaders such as Commander Bernhardt and by some NPC cavalry. The item
code that improves armour only steps up when the next code has a better save, so it never moves a
unit from 4 to 5. Mounted rating 6 is capped at 2+.

**Regeneration by damage source** ✅: close combat passes damage type 0 → the 4+ regeneration roll. `ApplyImpact`
calls the save routine only for sources that allow saves, with type `flags & 0xFF3F`: all missiles (type 2) →
**regeneration never lets the wound through**, so a Troll is immune to bows, crossbows, cannon, mortar, volley gun,
rock lobber, doom diver and bombs. No-save effects (breath, warpfire, Doomwheel bolts…) wound it normally. **Spells**: every no-save spell wounds regenerators (Storm of Shemtek,
Lightning, Piercing Bolts, Flamestorm, Fireball, Hunting Spear, Fists of Gork, Warp Lightning, Pestilent Breath);
spells with a save and damage type 0 allow the 4+ regeneration roll (Wind Blast, Azure Blades, Flock of Doom, Gaze of
Mork, the Shift variant of Flying Bower); The Burning Head (save, fire type 1) never wounds them; Conflagration of
Doom and Da Krunch remove models outright. There is
no "fire negates regeneration" rule. **Armour code 5** is not special anywhere else (not in the item code nor in
the armour display); because its table value 7 is worse than code 6's, the armour items that step a code up (Shield
of Ptolos, Armour of the Beard) turn a code-5 leader into a *regenerating* one, immune to missiles.

### Mounts ✅

For a rider whose armour code has bit 3 set (codes 8–13), the mount makes its own attacks from the
mount record `the relevant data + 32 × s_mount`: name pointer, a flag byte, **charge strength** at `+5`,
profile M WS BS S T W I A Ld at `+0xC`. The mount uses its A, WS and S, or the charge strength while
the charge counter is non-zero.

| `s_mount` | Name | Charge S | M WS BS S T W I A Ld |
|---|---|---|---|
| 1 | Warhorse | 5 | 7 3 0 3 3 1 3 1 5 |
| 2 | War Boar | 6 | 6 4 0 3 4 1 3 1 3 |
| 3 | Giant Wolf | 3 | 8 4 0 3 3 1 3 1 3 |
| 4 | Cave Squig | 0 | 5 4 0 5 3 1 5 2 2 |

**Exactly five fields of the mount record are ever read** ✅: **M**, **WS**, **S**, **A** and the **charge
strength**. Its BS, T, W, I, Ld and the byte `+4` (255 on the War Boar) are never touched by anything.

**What a mount changes, and what it does not** ✅ (traced September 2026):

- **Movement — this is the mount's largest effect by far.** The speed stat is derived once at unit set-up, and
  when the armour code marks the model as mounted it takes the **mount's M in place of the rider's**; the
  rider's own Initiative is still used. Everything else about movement follows from that one substitution,
  because the speed stat is the master movement variable: the unit's per-tick advance in every state
  (free, closing, charging, fleeing), the **charge reach `12 × (s_rlmv + 1)`** and how long a charge lasts, the
  turn and wheel rate, flight and pursuit speed, and each model's formation catch-up speed all scale with it.
  A rider on a Warhorse (M7) with I3 gets a speed stat of 18 against 11 on foot (M4 I3) — about 64 % more of
  everything above, and a charge reach of 228 world units (9.5") instead of 144 (6").
- **An extra attack sequence in close combat.** The mount attacks in its own right with its own A, WS and S —
  substituting its **charge strength** for its S while the unit's charge counter is non-zero. Because the
  rider and the mount each run the attack resolution, a mounted model also **spends the charge counter faster**
  than a foot model does (see "Charge").
- **It does not add toughness, wounds or survivability.** A mounted model has a single wound counter and uses
  the **rider's** T and W; **the mount cannot be wounded or killed separately**, and it is never removed while
  the rider lives. A mount is pure offence and pure speed.
- **It does not change the charge counter's size** (that is `1.5 × frontage`, a formation property), the model
  spacing (12 world units for every class, cavalry included), or the formation layout.
- **It is not what sets the contact reach.** The reach used for the automatic contact attacks of a charging or
  pursuing unit (12 world units, **18**, or 24) is selected from the **unit's class** — Cavalry and Monster get
  the wider values — and is read without reference to the mount record or to whether any model is mounted.
  A unit's class and its models' mounts are independent facts, and only the class decides reach.

### Charge ✅

`EngageCharging` stores **`charge counter = floor(1.5 × frontage)`** (the formed frontage,
constant 1.5 at the relevant data) on the unit that joins the battle grid; `Engage` (re-engaging
the current opponent) stores 0. The contact handler treats the moving unit with flags
`0x8080` (charge or pursuit order; event 8 "charge") as the charger; otherwise the game gives the
counter to whichever unit is not yet on a grid, so a unit that runs into an ongoing combat also gets
one. The defender's counter is untouched and nothing resets it when the combat ends.

**The charge bonus is not carried by the charging flag, and it is not a duration** ✅. The charging flag is a
movement/order state meaning "this unit is executing a charge move", and engagement clears it immediately because
the move is over. The bonus lives entirely in the separate **charge counter** above, which is set at the instant
of engagement and is a **budget of attacks, not a timer**: nothing decrements it with time, and it survives until
it is spent. An engine must therefore keep the two concepts apart — clearing the "charging" state on contact must
not clear the pending bonus.

While non-zero it gives **+1 Strength**, and a mount uses its **charge strength** stat in place of its normal S.
It is consumed as it is used, at two points: the attack resolution that grants the +1 S decrements it, and the
per-model melee round decrements it again after that model's rider and mount attacks have been resolved. A
mounted model therefore drains it faster than a foot model (its rider and its mount each run the attack
resolution), and an attack against a war machine takes a different resolution path that does not decrement it.
The practical effect is that the bonus covers the **opening exchange of the fight only** — of the order of the
first half-frontage to frontage of models to actually land attacks, rather than a fixed count of models
(`1.5 × frontage` is the budget, not the number of beneficiaries). 🟡 The exact number of beneficiaries per
formation has not been measured against a live fight.

Consequences worth implementing deliberately:
- **Re-engaging an opponent you are already fighting sets the counter to 0** — no bonus for re-contacting.
- **A unit that runs into an ongoing combat also receives a counter**, because the counter goes to whichever unit
  is joining a grid it is not already on.
- **Nothing clears the counter when a combat ends.** A unit whose fight finishes before the budget is spent keeps
  the remainder, and would still be spending it in a later engagement.
- 🟡 A charging monster keeps +1 S on its own attacks, because the monster melee round never decrements the
  counter (probable bug).

The lance (`s_weponame` 17) has no special rule; the Reiksguard use weapon class 3.

### Magic item effects ✅

Items are identified by their `GMTXT` name string ids (`31000 + n`) in the spell/item table at
the relevant data. Most apply only when the unit's leader model attacks or is attacked.

| Id | Item | Effect in close combat |
|---|---|---|
| 31001 | Banner of Might | +1 WS |
| 31002 | Dread Banner | the unit causes fear; its own unit ignores fear |
| 31006 | Shield of Ptolos | armour code +1 |
| 31007 | Potion of Strength | +3 S while active |
| 31008 | Sword of Heroes | +3 S against T ≥ 5 |
| 31009 | Parrying Blade | enemy leader −1 A |
| 31010 | Sword of Might | +1 S |
| 31011 | Dragon Blade | +1 wound roll per hit |
| 31012 | Armour of Meteoric Iron | armour code 13 (2+) |
| 31013 | Armour of the Beard | armour code +1 |
| 31014 | Grudgebringer | +1 S, +1 WS |
| 31015 | Rocksplitter | +5 S and +5 wound rolls against inanimate targets |
| 31016 | Sword of Elior | wound rolls doubled against race 2 (Dwarven) |

After the attacker's items, S is capped at 9 and WS at 10.

### Engagement: battle grid and pairing ✅

**Battle grid record** (pool of `0x14C`-byte records allocated at battle start):
unit count `+0`, flags `+2` (bit 0 in use, bit 1 result resolved), facing `+4`, sound handles, side
vectors, owner unit `owner`, **tallies `tally_a` (side without `s_side` bit 7) and `tally_b` (with)**,
creation segment `creation_segment`, turn of the last reset `last_reset_turn`, and a **17 × 17 cell map** `cell_map` (one cell =
12 world units = one model; bits 0–2 cell type, bits 5–7 side).

**What triggers engagement** ✅ (traced September 2026): contact is decided in `ResolveUnitCollisions`, not in the contact handler, and it is a two-stage geometric test **between the two
units' map objects** (see "Formations": a block's map object sits `(ranks − 1) × 6` behind the unit
position):

- **Broad phase**: `trunc(sqrt(dx² + dy²)) − r_a − r_b < 0` on the two map-object centres, where `r` is
  the bounding radius at `object+4` (the box half-diagonal).
- **Narrow phase** : at least one of the mover's four rotated footprint
  corners (rebuilt every tick) must lie **strictly inside** the other unit's
  rectangular footprint, after being rotated into that unit's object frame. So engagement needs real
  **penetration**, not mere proximity: there is no "reach" constant and no facing or arc requirement.
  (The 12 / 18 / 24 reach values belong to the contact attacks of section 7.7, not to engagement.)

Engagement is then a **two-step handshake**, not instantaneous. On the first overlapping tick
the game only records the opponent in `engaged_enemy` and sends event 0x0D (gated by the fear/terror test
the game and by not being braced); a unit with no prior opponent gets event 0x07 ("you are being
charged") and nothing more. the game raises event 0x0B, which script 152 turns into `AIQuery 8`,
which calls the contact handler the game — and only there, on a **later** contact tick once
`engaged_enemy` already names that unit, is `Engage`/`EngageCharging` called. A one-tick latch
(`unit_flags |= 0x1000000`, cleared on every refusal) stops the handler re-firing every tick of overlap.

**Neither movement nor an order is required** ✅: nothing in the contact path reads a velocity, a
destination or an order code, so two stationary touching enemies engage as well. A charge or pursuit
order (`unit_flags & 0x8080`) only decides *who* receives the `floor(1.5 × frontage)` charge counter and
whether the defender gets the flank/rear event 8. A charging unit that bumps something that is **not**
its target is redirected instead (the game: event 0x1A to the old target, 0x07 to the new one,
`engaged_enemy` updated) and engages only on a later tick.

Engagement is refused when either unit is **broken** (`0x2000`, "Can't engage a broken unit"), when the
target's collision record is **routing** (record bit `0x400`, set by `StartRout` and cleared by any
re-form), when the target carries flag the relevant data (🟡 no writer found, R70), when the two are on the
same side and the target is not the current opponent, or when the grid pool is exhausted (event 0x0C).

**Creation and joining**: when unit A engages B, A joins B's
grid if B already has one (so several units share one combat and one pair of tallies); otherwise a
new record is taken, B's models are written into the cells around the centre (one cell per model,
or a full rectangle for war machines, rolling stock and monsters) and B becomes the owner. If the pool
is exhausted the engagement fails (event 0x0C). Engaging clears the pairing of A's models, sets A's
round counter to 0, stores the charge counter, attack direction and side, and sends event 0x0A to both.

**A unit is never on two grids** ✅: the game routes the engagement so that whichever side does
*not* already have a grid is the one that joins, and `EngageCharging` refuses a second grid ("Allready
has a BattleGrid") while still returning success, so no 0x0C is raised. Multi-unit fights are therefore
always one shared record. The **attack direction** (`attack_dir`) is computed once at
engagement, from the attacker's unit position to the defender's object centre against the defender's
box diagonal `diag_angle`, and is never recomputed while the fight lasts.

**Two units both charging each other at once** ✅ (traced September 2026): the engagement decision
is made **independently by each unit's own per-tick contact check**, not by a single comparison
between the two sides. Whenever a unit's own order flags say it is charging or pursuing (`0x8080`)
and it has already confirmed the other unit as its recorded opponent (from the prior handshake
tick), that unit unconditionally calls `EngageCharging` **with itself as the charging party** —
there is no read of the other unit's own order flags at that point. So if both units carry a charge
order and each has the other recorded as its opponent by the time their own handshake tick fires,
**each one's own contact check makes itself the charger**, independently: both would compute and
store their own `floor(1.5 × frontage)` charge bonus for the fight, rather than the engine picking
a single "winner" charger between the two.

The "refuses a second grid" guard only stops a unit from being handed a second charge counter when
*it itself* is asked to be the charger again while it already has one — it does not compare against
the other side. Grid creation/joining ("whichever side doesn't have a grid yet joins the other's")
is likewise decided per call, from the perspective of whichever unit initiated that particular
`EngageCharging` call, not as a global "is this pair already fighting" check. 🟡 Whether this can
produce two independent battle-grid records for what should be one shared fight in a truly
simultaneous mutual charge (as opposed to reliably converging on one shared record because the two
units' contact checks run on different ticks or in a fixed order within the same tick) is not
confirmed by a live trace — the per-tick unit processing order that would settle this was not
determined. Practically, this only matters for the exact edge case of two units charging each
other head-on and reaching contact together; the common case (one moving unit reaching a
stationary or already-engaged one) is unambiguous, as already described above.

**Pairing** runs every tick:
- The joining unit places at most **frontage** free models per tick, each in a free cell orthogonally
  next to the nearest enemy model (only the front and one flank cell are offered while the model is
  more than 18 units away, all four closer in). Models without a cell become **reserves** that wait
  beside a placed comrade and are placed on later ticks, so deep units gradually wrap around. Against
  a block (war machine, rolling stock, monster) models are lined up along its sides.
- The owner's free models pair with enemy models at Manhattan distance 1, otherwise move next to an
  engaged comrade. When the owner outnumbers the attacker by more than 1.5×, it switches to the
  joining procedure.
- A model **fights only once it has an opponent and has arrived in its cell** (model flags `0x4000`
  and `0x10000`). Opponents retarget to a unit with a higher `s_pntval` or away from a war machine.

There is no front-rank, supporting-rank or spear rule: contact on the square grid decides who fights.
🟡 The wrap-around completes within roughly 2–4 segments, well inside the first combat turn; the limit is the
number of free cells next to enemy models (about `2 × (width + depth)`), so most models of both units fight by
the first result.

#### Why the charger disperses and the charged unit stands still ✅

Traced September 2026. The two sides of a new engagement are **not** treated symmetrically, and the asymmetry is
decided entirely by **who the grid is built around**. This is the single most visible consequence of the whole
engagement system.

**The grid is created from the defender's own formation.** When a charge connects, the grid is fetched or created
**for the target**, and creating it does this:

- the grid record is anchored at the **defender's** position and takes the **defender's facing**;
- the defender's block is centred on the 17 × 17 cell map by offsetting it to the middle:
  `grid_column = model's formation column + (8 − frontage / 2)`, `grid_row = model's formation rank + (8 − ranks / 2)`;
- each defender model's stored column and rank are **overwritten with those grid coordinates**, its cell is
  stamped as occupied by its side, it is flagged "on the grid", and its heading is snapped to the unit's facing.

So the cell map is just the defender's existing block transcribed onto the grid. **Every defender model is already
standing exactly in the cell it has been assigned** — its target position does not change by a single world unit,
so it has nothing to walk to. This is why the charged unit appears to freeze in place on contact: not because it
was ordered to stand, but because the grid was drawn around where its models already were.

**The charger is entered as the joining unit.** The same engagement gives the charger "has a grid" and "in melee",
clears its charging flag and its charge movement state — so **its reference point stops translating immediately** —
and pointedly does **not** give it the owner-pairing bit. The two per-tick routines then diverge:

| | **Owner** (the charged unit) | **Joiner** (the charger) |
|---|---|---|
| Models already next to an enemy | pair **in place**, no movement at all | — |
| Models with no adjacent enemy | queued to shuffle up beside a comrade who is already fighting, nearest first | placed into a **free cell orthogonally next to an enemy model** |
| Cells used | the ones its own formation already occupies | cells belonging to the **defender's** block outline |
| Overflow | — | become **reserves**, placed next to an already-placed comrade on later ticks |

The joiner's candidate cells come from a small per-direction offset table selected by the attack direction, so
where it wraps depends on which side it came in from. Only the first **two** candidate cells are offered while the
model is more than **18** world units away, and all **four** once it is closer — so a distant model takes the
obvious cell and a close one can slot into any gap.

**How a relocated model actually moves.** Committing a placement writes a new target derived from the enemy
model's position plus the chosen adjacency offset (converted between the two units' reference frames, since model
targets are stored relative to their own unit), clears the model's "at rest" flag and zeroes its step budget, which
forces an immediate re-aim. It then walks there under the ordinary rank-dependent catch-up walk of
"Models chase the unit, they are not carried by it" — ramping up from a standstill, with the deeper ranks slower.
Conversely, **a model that is at rest is skipped outright while its unit is in melee**, which is what holds the
defender's models motionless: they are never given a new target, so they are never taken out of "at rest".
A defender model that does get paired is momentarily taken out of "at rest", finds itself already within the
3-world-unit arrival threshold of its target, and settles again the same tick without visibly moving.

**Net effect on screen**: at the moment of contact the charger's block stops dead, loses its formation cohesion,
and its models stream outward to fan around the defender's edge — arriving raggedly, front ranks first, with the
overflow trickling in over later ticks as reserves. The defender does nothing at all except turn to face and start
fighting. The charging unit's earlier charge stretch (see the movement section) is resolved during this same
dispersal, since its reference point has stopped.

**This is not the Braced flag.** Bracing is a separate mechanism: being charged raises an event, and a passed fear
test sets a flag that makes the engine ignore movement, turn, rank and charge **orders** for that unit. It governs
what the unit may be *told* to do. The stillness described here is mechanical and happens regardless — the
defender's models have nowhere to go because the grid was built on top of them.

**Leaving**: models are unpaired, ownership passes to another unit
on the grid or the record is freed; a lone remaining unit with `s_side & 0xE0 == 0x20` leaves as well.
Tallies are **not** reset on join or leave.

**Every caller, and the condition each represents** ✅ (traced September 2026; the earlier
"destruction, rout, or no enemy remains" was correct but incomplete):

| Caller | Condition |
|---|---|
| the game `RemoveUnit` | the unit is destroyed or removed (unconditional) |
| the game | the unit walked off the battlefield (record flag `0x100`), after event 0x18 |
| the game `StartRout` | it **routs** — but only `if unit_flags_hi & 2`, i.e. only if it was actually in melee |
| the game / the game | per-tick pairing: `engaged_enemy` is gone or has no grid **and** the game finds no other enemy → leave, event 0x19 |
| the game | removed from combat by a spell effect, then event 0x0F to the enemy side |
| the game (opcode 0x56 `TargetGone`) | the event source was my target and no other enemy is found |
| the game case 0x16/0x17 | "unit removed" / "leader killed" naming my opponent, and no other enemy → leave, event 0x19 |
| the game itself | recursion: the last unit on a grid whose `s_side & 0xE0 == 0x20` |
| opcode 0x57 leaving a shared grid | script-driven; the **first instruction of the pursuit script 164** (R71) |

**There is no geometric disengagement** ✅ — the single most important consequence for an engine.
Nothing in leaving a grid, in the per-tick pairing
or in their callers reads a position, distance, footprint or collision record in order to leave. A unit
stays on the grid until one of the **state** conditions above fires. Two units that have engaged can
never be pulled apart by drifting, by turning, or by their footprints shrinking as models die.

The "no enemy remains" test the game is not geometric either: it walks **the unit's own models in
model-list order** and returns the first unit that one of them is currently paired against, excluding
the departing one, provided that unit still has a grid and is on the opposite side. There is no
distance, threat or facing tiebreak.

**When a model's own opponent dies but enemy models remain**, the survivor is *demoted in place*, never
removed from the fight: the game clears its `0x2/0x4/0x1000/0x4000/0x10000` flags but leaves
`0x20000` (still holds a cell), so the ordinary per-tick pairing picks it up again next tick. Likewise
when a whole enemy unit is removed, the game unpairs only the affected models and turns any that
still hold a cell into reserves (`0x8000`), the unit clears `0x400` (back to joiner pairing mode), zeroes
`attack_dir` and sets `engaged_enemy` to the new enemy. **A unit never idles permanently and never disengages
because its particular opponent died.**

Model flags: `0x1` alive, `0x2` dying, `0x4` timed turning/pause, `0x1000` at rest, `0x4000` has an
opponent (model and unit), `0x8000` reserve, `0x10000` in hand-to-hand, `0x20000` on the
grid, `0x40000` war machine. Unit flags: `0x200` in melee, `0x400` owner pairing mode, `0x800` has a
grid, `0x1000` grid owner, `0x2000` broken.

**Cell ownership is per side, not per unit** ✅ (the routine that stamps a cell):
`*cell = placing_model's_unit.s_side & 0xE1 | 1` keeps only the side bits (5–7) and the "occupied"
bit — nothing identifies *which* unit on that side placed the model. So when several units of one
side share a grid against a common enemy, their models fill one undivided pool of free cells: there
is no reservation of "this flank is unit A's, that one is unit B's". Whichever joining unit is
processed first in a tick (`BattleTick`'s fixed unit-array order) claims the free cells nearest the
enemy; a second, later-processed friendly unit's excess models fall through to the reserve queue
exactly like an overflow from a single deep unit would.

**Grid ownership handover** is a linear
scan of the whole unit array for the first unit still pointing at this grid, **with no side filter**
— the new owner can be an ally or an enemy of the departing owner, decided purely by array order, not
by any tactical criterion.

**Retargeting** (`OpponentRetarget`) is a one-shot comparison made only when a model
first arrives at its cell (distance to target < 3 units): it keeps its assigned opponent unless that
opponent has none, or the arriving attacker's own unit has a higher `s_pntval` than the current
attacker's unit, or the current target is a war machine — in which case it steals the pairing.
A single model never re-polls this once `0x10000` (in hand-to-hand) is set, but across several ticks,
with two enemy units sharing a grid, a defending model's recorded "primary attacker" can flip more
than once as higher-`s_pntval` attackers arrive later — driven by arrival order, not stability.

**Result accounting for a pile-on** (`AddCombatResult`): rank and direction bonus are
computed **per attacking unit**, from that unit's own frontage/ranks and its own recorded attack
direction — there is no reference to which enemy unit or model it actually fought. Both attacking
units' bonuses (which can differ, e.g. one gets a flank bonus the other doesn't) add into the *same*
single shared side tally with no cap or diminishing return: a multi-unit pile-on onto one grid is
strictly additive.

**Grid pool and its limits** ✅: allocated once per battle as `total_battle_units / 2` records, the hard cap on the number of *simultaneous, separate* close-combat grids (each
needs ≥ 2 distinct units) — ordinary battles never approach it. Exhaustion sends event `0x0C` only on
the "new contact" engage path (the game → the game/the game); the "re-engage the
same opponent" path fails **silently**, with no event, if the pool happens to be
exhausted at that moment.

**No spatial awareness between separate grids or with terrain** ✅: grid lookup or creation decides
join-vs-create purely from a per-unit "already has a grid" flag — there is no proximity check against
*other* grid records. Two unrelated fights can freely overlap in world space with zero interaction:
each grid's cell array, model placement, movement and `AddCombatResult` accounting only ever indexes
its own record. Likewise, grid creation and per-tick pairing never call the region/boundary functions
(`InRegion`/`NotInRegion`/`RegionCrossings`) or the scenery obstruction check (`ObjectsOnPath`) that
ordinary movement respects (see "Routes, collisions and visibility"): a grid can be seeded on top of
impassable scenery or straddling `BATTLEEDGE`, and per-tick pairing will place and walk models into
such cells unconditionally. The only terrain interaction any unit gets, combat or not, is
`ResolveUnitCollisions`'s unconditional per-tick boundary repel (mask `SOLID |
INVSOLID | BATTLEEDGE`), which shoves the whole unit back over the boundary regardless of melee state
and does not reconcile the resulting displacement with the unit's assigned grid cell — a unit already
fighting can still be jostled off its nominal cell position by ordinary scenery push-apart resolved in the same neighbour scan, with nothing detecting or correcting the drift.

🟡 **Grid-footprint overflow at creation is unchecked**: per-tick reinforcement placement
 bounds-checks every candidate cell to `0..16` and simply defers an
out-of-range model to a later tick (it stays free, is retried, and can end up a permanent
non-fighter if the geometry never changes — not written off after one failure). But the *initial*
footprint written when a grid is first created computes cell
indices as `8 − frontage/2`, `8 − ranks/2` with **no clamp at all**; a unit with frontage or ranks
above roughly 16 would write outside the 17×17 array into adjacent grid-record memory. Whether any
real formation (given the formation-size caps in "Formations" above) can actually reach that width is
not established from this code alone — a candidate for grepping the army/formation size caps or a
Wine session forcing an oversized frontage.

### Battle grid procedure (implementation specification) ✅

Self-contained, behavioural summary of 5.7 for implementers. Based on observation and data correlation of
grid creation, per-tick pairing and arrival (verified against the sections above). Code in `whshr/`
must cite this section, not the original routines. Constants: `GRID_SIZE = 17`, `CELL = 12` world
units (one model), `NEAR_DISTANCE = 18`, `ARRIVAL_DISTANCE = 3`, `OWNER_SWITCH_RATIO = 1.5`.

1. **Cell frame.** A grid is a 17 × 17 array of cells. Its axes are fixed at creation from the owner's
   facing, with a pitch of one model spacing (12 units) per cell, so cell `(row, col)` maps back onto the
   owner's own block slots. The frame is never recomputed while the fight lasts.
2. **Seeding (owner's models).** The engaged unit (the grid owner) writes each model into the cell
   `col = file + (8 − frontage / 2)`, `row = rank + (8 − ranks / 2)` (integer halves), where `file`
   and `rank` are the model's slot in its own formation block. Cells record only the occupying
   *side* (plus an "occupied" bit), never the unit or model. The original does not range-check this
   write (see the hazard at the end of 5.7); a reimplementation should clamp.
3. **Joining unit, every tick.** Each unit that is not the owner (or the owner once it outnumbers the
   enemy, step 5) places at most `frontage` of its free models per tick. For each model: find the nearest
   enemy model that already holds a cell; try the free cells orthogonally adjacent to it. While the placing
   model is farther than `NEAR_DISTANCE` from that enemy only two candidates are offered — the cell on the
   side the attacker comes from and its first flank; closer than that all four are offered. Candidates
   outside `0..16` are skipped. A model that finds no cell becomes a **reserve** and is retried on later
   ticks; it is never discarded after one failure.
4. **Pairing.** A placed model takes the enemy model it is adjacent to as its opponent (Manhattan
   distance 1 on the grid). Units on the same side share one pool of free cells; the fixed per-tick
   unit order decides who claims cells first.
5. **Owner, every tick.** The owner's unpaired models take any enemy model at Manhattan distance 1,
   otherwise move next to an engaged comrade. When the owner has more than `OWNER_SWITCH_RATIO` times the
   enemy's models it uses the joining procedure of step 3 instead.
6. **Arrival.** A placed, paired model walks toward its cell. It **fights only once it holds an
   opponent and its remaining distance to the cell is below `ARRIVAL_DISTANCE`**. A model that is
   already that close when it receives a cell counts as arrived immediately.
7. **Retargeting** happens once, at arrival, as described in 5.7 (`s_pntval` comparison, war machines).
8. **Death and leaving.** A dead model frees its cell and unpairs its opponent; the survivor stays
   on the grid and is re-paired on a later tick. A unit leaves the grid only on the state conditions
   listed in 5.7, never because of distance.
9. **Not modelled by `whshr/`** (documented placeholders): war machine, monster and wagon block
   layouts (every unit is seeded as troops), opponent stealing by `s_pntval`, the original's exact
   per-tick model walking speed.

## 6. Combat resolution and break tests

### Result ✅

After a unit's models have attacked, the kills it caused and the kills from return blows are added to
the two tallies of the shared battle grid (`tally_a`/`tally_b`, which one depends on the side bit).
The unit's own score also gets, when its enemy is a unit of classes 1–6:

- **rank bonus**: if frontage `s_wdth > 3`, `size / width − 1` (full ranks behind the first),
  **with no upper limit**. ✅ `size` is the unit's **live** model count but `width` is the
  **formed** frontage (`frontage`), which casualties never reduce — only a re-form recomputes it. The
  bonus therefore **decays as the unit is worn down** and vanishes once it is below two full ranks.
  Deriving the width from the current model count instead pins the bonus near `ranks − 1` for the
  whole fight and inflates every result the unit is part of;
- **direction bonus** from the attack direction code (the angle of the attacker
  relative to the defender's facing): code 1 (behind) **+2**, codes 2–3 (sides) **+1**, 0 (front) 0.

`AttackDirection` returns eight codes (two halves each of front arc 0/4, rear arc 1/5, flanks 2/6 and 3/7);
`AddCombatResult` masks bit 2 away, so both halves of an arc get the same bonus.

There is **no standard, battle standard or general** ✅: `banner:` only selects the banner sprite, `s_banner` is never read, and Leadership comes only from the unit's own leader.

### Break test ✅

`BreakTest` is called for every unit in melee at each segment boundary but acts only in the grid's
creation segment, i.e. **once per turn**, and increments the unit's round counter `round_counter`. The result
is evaluated when `turn − last_reset_turn == 2` and the round counter is at least 2; the first blow after a
result resets the tallies and sets `last_reset_turn = turn − 1`. Consequences: the **first result comes two turns
after contact** (rank and direction bonuses, added at every strike, count twice in that window); later
results come every 1 or 2 turns depending on the Initiatives involved; a unit that joins later cannot
be broken in its first turn. Every unit of the losing side (`difference = own tally − enemy tally < 0`,
not already broken) is tested separately against the same difference:

**Timing and reset in detail** ✅ (traced September 2026; getting these wrong inflates every modifier):

- **All break tests on a grid resolve before any unit strikes in that segment.** The tick loop runs
  `BreakTest` over every unit in melee and only afterwards runs the melee pass, so the result is
  evaluated on the tallies as they stood at the end of the previous turn.
- The gate is `creation_segment == current segment`, the **grid's own creation segment** — identical for
  every unit on the grid, and unique within a turn, so it fires once per turn for all of them at once.
  Evaluating at a fixed segment (the turn's last, say) instead folds an extra turn of bonuses into
  every modifier.
- **The tallies are cleared lazily, per grid, by the first unit to strike after a result**, inside
  `AddCombatResult`: it zeroes the two tallies, sets the last-reset turn to `turn − 1` and clears the armed bit, and
  that same call's own contribution lands in the new window. The steady-state accumulation window is
  therefore **one turn**; only the first window is two.
- `round_counter` counts the result segments a unit has seen on this grid; it is zeroed on every (re)engagement
  and the test needs it `>= 2`, so **a unit cannot be broken by a result it was not present for**.
- A unit joining an existing fight never zeroes the tallies and never moves the window.
- The modifier is the **raw, uncapped** difference: no clamp, scale or table between the subtraction
  and the test. The tallies are stored as signed chars read back as unsigned bytes, so the arithmetic
  is mod 256 (a tally past 255 wraps — a real if rare hazard).
- Since the roll is flat 2–12, **any modifier of `Ld − 1` or more is an automatic failure**: there is
  no tail. A difference of 6 against Ld 7 is already certain death, which is why the accumulation
  window matters so much. The main per-unit decorrelators are hatred (below), differing Leadership,
  and the `round_counter` exemption — several units of one side sharing a grid otherwise get the *same*
  modifier in the *same* segment and tend to break together.

```
if unit hates the enemy:   difference = Ld − 10         # the test becomes a roll of 10 or less
if enemy causes fear and the unit has none of CantBreak/Frenzy/PsyImmune and no Dread Banner:
    break without a test
elif LeadershipTest(unit, modifier = −difference) fails:
    break  (event 0x0C)
```

## 7. Leadership tests and psychology

### The Leadership test ✅

```
pass  <=>  modifier + (rand % 11 + 2) <= effective Ld     # modifier − 1 (= +1 Ld) while the "fight harder" flag is set
```

The roll is **uniform over 2–12**, not 2D6. For Ld 7 the chance to pass is 6/11 = 54.5% (2D6:
58.3%); Ld 9: 72.7% (83.3%); Ld 5: 36.4% (27.8%). Low Leadership is better and high Leadership
worse than on the tabletop. Callers: break test, panic, fear, rally, pursuit, artillery crews,
and a scripted test.

### Panic ✅

**There is no friendly-unit panic** ✅ (re-verified September 2026 over every caller of the game
and): nothing makes a unit test morale because a *friendly* unit broke or was destroyed.
The rout broadcast (event 0x0F) goes to enemies only and drives pursuit; events 0x0E and 0x16 only make
other units drop the unit as a target. Panic is driven purely by a unit's **own** casualty thresholds
plus area damage and two spell effects, so it is one of the engine's *decorrelators* of morale: adding
it makes units break more often but **independently**, not in unison.

When a model is killed (any cause), with `q = orgsize >> 2` (so only units of 4 or more models):
if `floor(size_before / q) != floor(size_after / q)`, the unit tests with
`modifier = 1 − floor(size_after / q)`. For a 16-model unit that is −2 at the first loss below
16, −1 below 12, 0 below 8 and +1 below 4; each quarter of the original strength lost costs one test,
and the tests get harder. A failed test routs the unit (event 0x0C). The debug output prints
"at −1 while pursuing" for pursuing units but uses the same modifier.

The area damage routine (missiles and spells, section 8.4) can additionally order a panic test at
modifier 0 when a unit is at or below a quarter of its original size.

Only **deaths** trigger panic ✅: `RemoveModel(unit, slot, killed)` runs the check only when `killed != 0`,
which the death paths pass (the model death callback at the relevant data and the unit destruction callback at
the relevant data, both reached through animation callbacks). Removal without death (`killed = 0`: units that
leave the table; destroyed buildings) adds to `s_routed` instead, so
`s_routed` counts **models that fled off the battlefield**. A killed model flagged `0x40` also sends event 0x17.

### Fear and terror ✅

`MayEngage(unit, enemy)`:
- enemy causes terror and the unit has neither `Frenzy` nor `PsyImmune` → refused, **no roll**;
- fear applies (enemy `CauseFear` or Dread Banner; the unit has none of `CantBreak`, `Frenzy`, `PsyImmune` and
  no own Dread Banner) → Leadership test at modifier 0; a pass sets psy bit 14 (no further tests until the
  next charge clears it);
- otherwise allowed.

It is used in three situations:
1. **Being charged** (op 0x42 on event 0x07, only if the source really is charging): failure → event 0x0D →
   the unit flees ("Flee the abomination!"), unless `CantBreak`.
2. **Charging a target** (op 0x4E, the attack/approach charge of scripts 105, 158, 159 → 160; the player's Charge
   button uses the straight-ahead op 0x4F instead, 🟡 whether that tests fear): failure → "My men fear the beast!" and the unit halts and re-forms; success starts
   the charge (flag `0x80`) and sends event 0x07 to the target.
3. **Contact while moving** (unless bit 14 is set): failure → event 0x0D, flight.

So a failed fear test means flight (when charged or on contact) or a refused charge, whatever the numbers,
and a terror-causer makes every non-immune unit that it charges or touches flee without a roll. There is no
terror test at a distance.

### Rally ✅

A fleeing unit makes a rally attempt only when **all** of these hold: its scheduled segment has come
(`rally_timer`: the first attempt one full turn after the rout, then every 3 segments), its rally-attempt flag
`move_state` bit 11 is on, and no enemy is within 160 world units. The flag is set by the player's order 0x14
("Rally!"/"stop pursuing" toggle, allowed while broken or pursuing) or automatically at the rout for units
with unit flag bit 27 (🟡 a per-unit "independent action" toggle, order 0x1A); otherwise the unit keeps
fleeing.

The unit cannot rally with `CantRally`, or when `casualties ≥ 3 × size` (at or below a quarter of its
original strength). Otherwise it takes a Leadership test with modifier +2 if `casualties > size`, +1 if
`3 × casualties > size`, else 0. Success sends event 0x10: "Re-group!" (Dwarfs "Rally!"), and op 0x5A clears
the broken/charging/pursuing flags and re-forms the ranks.

### Pursuit ✅

When a unit routs, every enemy unit receives event 0x0F, but only the routed unit's opponents react (op
0x53): a unit on a combat grid first looks for another opponent in the same fight and switches to it if
there is one; otherwise it pursues. A unit not on a grid pursues only if it was charging. Player artillery,
wizards and archers never pursue.

**Opcode 0x53 in full** ✅ (traced September 2026). Only opponents react because the
opcode gates on `event sender == engaged_enemy` (the unit's current opponent); a unit busy casting aborts first. Then, exactly:

- **in melee** (`unit_flags & 0x200`): call. If it finds another enemy on the grid, **switch to
  it** — the game unpairs the models that were fighting the router, `attack_dir` is zeroed, `0x400` is
  cleared (back to joiner pairing mode) and `engaged_enemy` is set to the new enemy — and the pursuit condition
  is **false**. If it finds nobody, the condition is **true** and the unit pursues.
- **not in melee**: pursue only if it was charging (`unit_flags & 0x80`); otherwise send event 0x1B to self,
  which script 152 turns into 0x19 ("target gone").

**Pursuit is automatic for player and AI alike** ✅: the reaction is the behaviour script every unit runs,
and neither the game nor scripts 151/153 test the player-controlled bit. What the player controls is
*stopping* — the restraint test in the game is rolled only under order 0x14 (the Rally toggle).

**Which classes never pursue is encoded in the behaviour scripts, not in C** ✅ (read from `BF001.DLL`):
scripts **151** (generic) and **153** (melee) do an unconditional `IfSwitchScriptHigh 164`; script **155**
(wizard) and **156** (shooter) switch to 148 / 127 instead — 127 keeps shooting the target — and only when
flag `0x8000000` is set, else they just send event 25; script **154** (artillery / static) handles the
event with the separate opcode 0x54 `EnemyRoutedStatic` and never enters 164 at all. Script 164 itself is
`LeaveSharedGrid; ReformToScriptRanks; React 3 ("Destroy them!"); Query 1; IfThreatOutweighsWorth;
SendEventSelfIfTrue 3; YieldIfTrue; StartPursuit`, and `StartPursuit` sets state `0x200`
and flag `0x8000`, refused if `unit_flags2 & 9`.

**A pursuer can never re-engage its fugitive** ✅: the routing collision-record bit `0x400` removes the
fleeing unit from the collision scan and from the contact handler's entry check. All damage during a chase
comes from the contact attacks of section 7.7 —, once per segment per attacker
(`unit_flags2` bit 5), against models within `2 × reach` where reach is **12 units, 18 cavalry, 24 monsters**, hitting automatically any model that lacks the `0x4` turning/braced flag. There is no
instant kill, and no close combat.

**No re-engage cooldown** ✅, but a re-form gate: `0x400` is cleared by, which every re-form
calls, so a rallied unit becomes engageable again as soon as it re-forms. The only other bar is the broken
flag `0x2000`.

The pursuit script (164) shouts "Destroy them!", may attack a more attractive target instead (if its
value exceeds the unit's worth `unit_worth`), and starts the pursuit (`StartPursuit`,: state
`0x200`, flag `0x8000`). the pursuit update and the pursuit step end it
with event 0x10 when:
- the target is gone, rallied or died;
- the chase budget runs out (not with `AlwaysPursue`): `min(2 × distance, 120)` at first, then changed at
  each update by `(previous distance − distance) − 4`;
- the next step would leave the battle area;
- the restraint test at the scheduled segment is passed, which is only rolled while the rally-attempt flag
  is on (player order 0x14). **AI units never test**; they chase until one of the other conditions ends it.

### Other effects

- `CantDie` ✅: the game removes a model when wounds ≥ W only if the unit lacks `CantDie`.
- `MagicResistent` ✅: in the area damage routine, a wound from a magical source is ignored on
  an even `rand`.
- Hatred and frenzy: section 5.2; fear in break tests: section 6.2.

### Flight and catching fleeing units ✅ / 🟡

Event 0x0C (rout) and 0x0D (fear flight) are handled by the library scripts: already broken or `CantBreak`
units ignore them; the player's own **artillery ignores rout events altogether** (it flees from fear only
while its leader model lives). Otherwise the unit shouts "Retreat!" or "Flee the abomination!" and switches to
the rout script, which starts the flight **directly away from its opponent** (bearing + 180°), or along its
facing without one.

`StartRout`: movement state `0x100`, leaves the combat grid, **loses `Frenzy`**, gets the
broken flag `0x2000`, sends event 0x0F to every enemy unit and schedules the rally attempts.
`FleeingUnitUpdate` moves the unit; `RoutRoute` probes one step ahead and deflects the
heading by ±0x20 (of 512) around obstacles. Once outside the battle area the unit sends event 0x0E and is
then removed alive (every model counts in `s_routed`). 🟡 Speeds: the flee counter uses `s_rlmv`, the
distance per tick comes from the generic mover the game (not traced).

🟡 **Catching.** Pursuers never engage fleeing units in close combat: the collision pass skips routing
footprints. Instead, the fleeing unit's own collision pass calls `ContactAttacks` for every
enemy unit it touches: once per segment per attacker, each attacker model makes up to A attempts against
random victim models within twice its reach (12, cavalry 18, monsters 24), with automatic hits (fleeing models
lack the "braced" model flag 4), charge bonus included. As the pursuer is steered onto the fugitive, this
repeats every segment of contact until the fugitive is destroyed, rallies or leaves the table. There is no
instant "caught = destroyed" rule.

**Implemented**: `whshr.engine.Regiment.flee_x`/`flee_y` freeze that bearing once, in
`whshr.combat.start_rout`, matching "starts the flight directly away from its opponent" as a
one-time determination rather than a live one. An earlier version instead called
`Battle.flee_point` (re-deriving "away from the nearest enemy") fresh every tick from
`Battle._advance_regiments`; with two pursuers converging on the same fugitive from different
sides, whichever counted as "nearest" could flip every tick as their distances crossed over,
reversing the flee bearing each time and stalling the chase indefinitely - reported as a cavalry
charge that never seemed to catch and kill a fleeing goblin unit while a second friendly regiment
was also chasing it. `RoutRoute`'s own small per-step deflection around obstacles (±0x20 of 512) is
still not modelled - the frozen bearing here is exactly straight, an existing, separately-flagged
simplification of the pathing itself (`notes/engine_architecture.md`'s "Collisions": a simplified
push-apart rule, not the original's polygon obstruction routing).

### Scripted target and flight opcodes: `DropTarget`, `FleeAhead`, `StoreEventInfo`, `FaceModelsToTarget` ✅

Behaviour of four opcodes used by the shared library scripts (in every mission) and by mission scripts such as
BF001's scripted flight.

**`DropTarget` (0x3B)** — forget the current attack target.
- It acts only on a unit that is **not broken** and **has a target**. It then clears the target and cancels the
  "braced against a charge" state, and its condition is **true**. In any other case (broken, or no target) it does
  nothing and its condition is **false**, so a script can also use it to ask "did I have a target?".
- It does **not** end a melee engagement or leave the battle grid, change the unit's orders, movement or ranks,
  clear the remembered event (`StoreEventInfo`) or the event's source, or send any event — to the old target or
  to anyone else. Everything else comes from the surrounding script.
- Its shipped use is the library's handler for event 0x19, "opponent gone" (sent when the unit's opponent dies or
  leaves and it has no other enemy on the grid, `notes/game_rules.md` section 5): `DropTarget`, then, if the unit
  was pursuing, a bark and a switch to the rally script; a unit that was not pursuing just carries on with no
  target and its ordinary script picks a new one.

**`FleeAhead` (0x51)** — start a rout along the unit's current facing.
- It starts an ordinary **rout**, not a plain move: the unit becomes broken, leaves the combat grid, loses Frenzy,
  every enemy unit receives event 0x0F ("enemy routed", so the AI chases it), its models pause and scatter as on
  any break (6–27 ticks, see "Turning, wheeling and reversing"), and rally attempts are scheduled exactly as in
  "Flight and catching fleeing units". It also clears the unit's target, and its condition is **true**.
- **Direction: straight ahead.** The heading is the unit's facing at the instant it runs; there is no node or target
  in the opcode. To flee towards a node a script first does `FaceNode n`, which turns the unit to the bearing to
  that node **instantly** (no wheel), so face-then-flee is a straight run along that bearing. The unit does not
  stop at the node: it keeps going and only the obstacle deflection of the flight movement (±0x20 of 512 around
  obstacles) bends the line.
- **Distance: unlimited.** The flight runs until the unit is outside the battle area, where it sends event 0x0E and
  is **removed alive** — every model counts in `s_routed`, and for the "eliminate the enemy" objective (letter A) a
  unit that has run off counts as gone, the same as one routed off by morale. Flight speed is the ordinary rout
  speed (`k` = 1.5).
- Because `FleeAhead` is the rout itself, it does **not** consult `CantBreak` or the "may this unit rout" test —
  those live in the event-0x0C/0x0D handlers, not in the opcode — so a scripted flee always happens. It is refused
  only for an **anchored war machine**, which does not move (its target is still cleared).
- It is the fall-back half of the library's ordinary rout script: `FleeFromTarget` (start a rout directly away
  from the target, bearing + 180°) and, when there is no target, `FleeAhead`.
- A scripted flee is the same as any other for rallying: it only rallies if the unit carries the automatic-rally
  flag or is ordered to rally, and never with an enemy within 160 units. BF001's Sleaquit carries `CantRally`
  (and `CantDie`), so once he flees he never rallies and runs until he is off the battlefield.
- Example (BF001, the assassin Sleaquit): the enemy army's Otto Hiln carries the tag `0xabc0` and a script that
  kills all his models the moment his unit is in melee; Sleaquit waits until his own watch flag is set or 80 ticks
  have passed, then `AttackTagged 0xabc0` — he attacks Hiln although both are nominally the same side. When
  Hiln's models are killed, Sleaquit's opponent is gone and his unit receives event 0x19; Sleaquit's interrupt
  script handles event 25 by an immediate `SwitchScript 3` (no `DropTarget` — `FleeAhead` clears the target
  itself) and drains the queued events. Script 3 is `wait until re-forming is finished`, `FaceNode 5`,
  `FleeAhead`, then an idle loop of 100-tick waits: Sleaquit turns instantly to face node 5, becomes broken,
  sends "enemy routed" to the player's regiments, runs off in a straight line at 1.5 × his move speed and is
  removed when he crosses the edge of the battlefield. Test: facing 100/512 before `FleeAhead`, facing 100/512 after, target empty, broken set,
  position advancing along facing 100 each tick until off-field.

**`StoreEventInfo` (0x61)** — remember who sent the event being handled.
- It copies the current event's **sender (a unit) and event code** into the unit's single "remembered event" slot,
  overwriting any earlier one. It must run inside an event handler. The slot outlives the event, so it survives the
  script switch that follows.
- The shipped use is the "being charged" (event 0x07) handler in library scripts 151 and 153–156:
  `StoreEventInfo`, then the fear-when-charged test (a failure queues flight), then, if the unit is not itself
  charging, on the grid or broken, a switch to the **brace script** (161).
- The only reader is the brace query at the top of script 161. It acts only if the unit is not broken and the
  remembered code is **0x07**: it clears the remembered code (so one stored event braces at most once), makes the
  remembered sender — the charger — the unit's target, sets the braced state and stops the models' walking. No
  other opcode reads the slot.

**`FaceModelsToTarget` (0xE1)** — turn the *individual models* to face the target, not the regiment.
- With no target it does nothing (condition false). With a target it computes the bearing from the unit to the
  target and looks at every model: a model that is **still walking** is left alone and makes the condition true (not
  finished); a model **at rest** whose own heading differs from the bearing gets that heading set **instantly**
  and makes the condition true; a model already facing the bearing changes nothing. War-machine models are
  skipped. The regiment's own facing, its formation slots and its footprint do **not** change.
- The condition is therefore true while any model was walking or had to be turned, and false once every model is at
  rest and facing the target. Script 161 (`brace when charged`) runs `Query 7`, halts and re-forms, then repeats
  `Yield; FaceModelsToTarget` until the condition is false, after which it idles in 20-tick waits and does not
  call it again — so the models face the charger as it stood on the last call.
- **How fast it looks.** The heading change is instant, but a figure's *drawn* direction slews at most one of the
  eight sprite directions (22.5°) per tick, so a figure needs up to 8 ticks (0.8 s) to swing through 180°. Only
  figures whose current animation faces their own heading turn visibly; a figure whose animation faces the
  regiment's facing (the stand pose in some families) does not. The braced regiment keeps its formation and
  facing while the individual figures turn towards the charger.
- Test: a halted regiment with a target 90° off, all models at rest: the first call sets every model's heading to
  the bearing and returns true; the second call changes nothing and returns false.

🟡 **Uncertain.** Whether a scripted fleer that was fighting a same-side unit (BF001's assassin, whose target
kills itself when engaged) is subject to any extra objective bookkeeping is not settled; "Capture Hiln"
(objective S) itself checks nothing.

### Charge into the flank or rear ✅

the game is opcode 0x5B, run by the default event handler on **event 0x08**, which `EngageCharging`
sends to the charged unit when the charger is charging or pursuing. With the attack direction code of the
charger, the table at the relevant data = `[0, 1, 1, 1, 0, 1, 0, 0]` selects a **Leadership test at modifier 0 for
a charge into the rear arc (codes 1, 5) or the rear half of either flank (2, 3)**; failure sends event 0x0C
(rout). Front arc and the front halves of the flanks (0, 4, 6, 7) need no test. Unlike WFB 4th edition
(panic when charged in flank or rear while already engaged), the test applies to any such charge.

## 8. Shooting, artillery and magic

Conventions: angles in 1/512 of a turn (0x40 = 45°), distances in world units (24 = 1"), ticks of the
battle clock (19 per segment, 100 ms each).

### Who shoots, orders and volleys ✅

- Only classes 3 (Archers) and 4 (Artillery) use `FireMissile`, with at most 32 projectiles in flight
  (the game; 64 for spell effects). The missile code is `S_BalWeap` of the unit (Archers), of the
  leader's block (Artillery) or the leader's if non-zero (others).
- Shooting is run by the **library behaviour scripts** (107–124, handlers 154/156, identical in all mission
  DLLs). A player fire order (`OrderFire`) **halts a moving unit** and queues an event:
  target unit, target building, search (click on itself), ground point, or hunt variants with unit flag
  bit 27. Special shooters (codes 14, 15, 17) fire their own routine at once.
- The fire loops re-run every update: `ReadyToFire` (reload) ∧ `InArcAndRange` ∧ `TargetValid` → volley;
  otherwise the unit turns towards the target (threshold 11.25°) and **waits until halted**. Search picks the
  **nearest non-broken enemy unit in range**. A building out of range is shot at 90% of maximum range.
- **Volley**: every model of an Archers unit plays the shooting animation; every 4th model posts the fire
  event, so a volley is **⌈N/4⌉ projectiles, each launched from the model that posted it** (10 crossbowmen:
  3 bolts, 16: 4). Artillery fires **one** shot from the machine.
- **Arc of fire**: target within facing ± 45° (`GMTXT 2002` "Target not in line of sight." is really this
  arc test). **Range**: strictly below the maximum range (`GMTXT 2001`). No long-range, moving or cover
  modifier; **shooting into close combat is allowed** (hits are geometric, friends near the target can be
  hit). Crossbows alone refuse to shoot when a non-enemy unit stands on the line of fire (`TargetValid`).
- `ReadyToFire` order: hold-fire bit `unit_flags2 & 8` → reload (`GMTXT 2003`) → machine present
  (`2015` "Artillery destroyed!") → at least 2 crew (`2016`). `GMTXT 2000` "Missiles fired!" is never used.

### Reload time ✅

```
base = (10 − min(I, 10)) × 18                       # the unit's own block: I, weapon code
k    = bow 7, crossbow 4, Wood Elf bow 10, short bow 8, longbow 6, else 0
if k: reduction = 9k (k < 3) | 6k + 6 (3 ≤ k < 6) | (2k − 10) × 9 / 5 + 36 (k ≥ 6)
      → bow 43, crossbow 30, Wood Elf bow 54, short bow 46, longbow 39
      base = max(base − reduction, 18)
Artillery with fewer than 4 models: base += (4 − size) × 36
```

The last shot is stamped at every volley (`shot_segment` segment, `shot_tick` tick, `shot_turn` turn). Examples: Orc
Arrer Boyz (I2) 101 ticks, crossbows I3 96, Goblin short bows I2 98, Wood Elves I6 18 (about once per segment),
artillery crews I3 126 and I2 144 (artillery reads the crew block, whose weapon code is 0). An I2 bow unit
fires about twice per turn; WFB fires every turn.

### Aim, scatter, flight ✅

Each projectile (`LaunchProjectile`, 27 arguments; records of `0x2DC` bytes at
the relevant data) flies to the target point displaced on each axis by

```
offset = (rand % (11 − min(BS, 10))) × (random sign) × spread × distance / max_range
```

`spread` = 8 for bows and crossbows, `8 × d` for artillery (*d* = the first artillery die, 8.5), **+8 if a
scenery object lies on the line of fire** (`NextObjectOnLine`,: buildings, walls, trees). An object blocks when
`min(Δ, 512 − Δ) < trunc(asin(radius / d) × 256 / π)`, with `d = trunc(distance)` below the range and Δ the difference
between the line's direction and the object's bearing `trunc(256 − 256 × atan2(dx, dy) / π)` (`ObjectOnLine`); a firer inside an object's circle is never blocked by it.
Horizontal motion is linear over a fixed flight time; height follows an arc (bows apex ≈ 180 units,
crossbows ≈ 45, cannon low, mortar and rock lobber high). Holding Ctrl only changes the projectile graphic.

**In flight** the projectile is tested against map objects every tick (`StepProjectile`);
all missile weapons stop at their first hit. An arrow flying into a unit wounds one random model; a **blast
projectile flying into a unit's footprint hits every model at full S** (the flight test passes the radius
negated). Low trajectories (crossbows, cannon) can therefore hit intervening units; high arcs (mortar, rock
lobber) normally reach the aim point.

| Code | Weapon | Range | Blast radius | Wound die | S | S vs buildings | Flight ticks | Spread |
|---|---|---|---|---|---|---|---|---|
| 1 | bow | 576 (24") | 0 | 1 | 3 | none | 18 | 8 |
| 2 | crossbow | 720 (30") | 0 | 1 | 4 | none | 18 | 8 |
| 5 | great cannon | 1440 (60") | 24–48 (random) | D6 | 10 | 10 | 9 | 8*d* |
| 6 | mortar | 768 (32") | 24 | D3 | 7 | 7 | 27 | 8*d* |
| 7 | Hellblaster volley gun | 576 (24") | 24 | D4 | 5 up to 287 units (12"), else 4 | as S | 9 | 8*d* |
| 8 | rock lobber | 1440 (60") | 60 | D6 | 5 | 5 | 27 | 8*d* |
| 9 | Wood Elf bow | 576 (24") | 0 | 1 | 4 | none | 18 | 8 |
| 11 | cannon | 1152 (48") | 24–48 | D4 | 10 | 10 | 9 | 8*d* |
| 12 | doom diver | 1440 (60") | 0 | D6 | 5 | 5 | 18 | 8*d* |
| 17 | Gyrocopter bomb | own position | 72 | 1 | 4 | 4 | 9 (falls) | *d*, not scaled |
| 18 | short bow | 384 (16") | 0 | 1 | 3 | none | 18 | 8 |
| 19 | longbow | 720 (30") | 0 | 1 | 3 | none | 18 | 8 |

All missiles allow armour saves, are not magical and use damage flags `0x82` (panic test after a hit when
the unit is at or below a quarter; damage type 2); the Gyrocopter bomb omits the panic bit.

### Impact ✅

Arguments: source unit, excluded object (the firer, only in flight), x, y, height, radius, wound die, S, S
against buildings, saves, magical, flags, messages. For every map object at distance *d* from the impact:

- **Units** (height test passed, flying units only between their base and top):
  - `d < footprint radius` (`GMTXT 2004` "Direct hit on the %s!"): radius 0 → **one random model**;
    radius ≠ 0 → **every model**. Each: `TO_WOUND[S][T]`, armour save if allowed (the leader with its armour
    items), `MagicResistent` 50% if magical, then `rand % wound_die + 1` wounds.
  - `d < footprint + radius` (blast margin, `GMTXT 2005` "The %s have been hit!"):
    `n = (footprint + radius − d) × size / (footprint + radius)`, at least 1, random models (with repetition)
    at **S/2 for exactly 1 wound**.
  - Afterwards flag `0x80` → panic test if `size ≤ orgsize / 4`; flag `0x40` → rout.
- **Buildings and furniture**: the owning unit's first model takes `TO_WOUND[S2][T]` and the wound die
  (direct) or S2/2 and 1 wound (margin), no saves.
- A terminal impact does not exclude the firer, so a shot that scatters back can hit its own unit.
- The damage type (`flags & 0xFF3F`) is stored as the cause of death and passed to the save routine
  (missiles 2, fire effects 1).

### Artillery misfire ✅

Before every artillery shot: D6; on 1–5 nothing happens and the result becomes the die *d* used for the
scatter. On a **6** a second D6 is rolled: on **1** the machine explodes: every crewman takes a wound on an
even `rand`, and if any crew survive they take a Leadership test or rout (`GMTXT 2018` "The %s has misfired
and been destroyed."). On 2–6 the shot is lost (`GMTXT 2019` "The %s has misfired."). The warpfire thrower
never misfires.

### Special weapons ✅

These reuse the **spell effect engine** (`LaunchEffect`, innate casting) and are magical
(`MagicResistent` ignores half the hits).

| Code / routine | Targeting | Shots | Per shot |
|---|---|---|---|
| 13 Doomwheel warp lightning (behaviour 0x1A, `DoomwheelBolt`) | reload on the leader block | 3 bolts: ahead, right, left; distance `D6 × D6 × D6 × 12`; nearest unit **of either side** near that point | fails on a 6 (`GMTXT 2021`); S5, D6 wounds, no save |
| 14 Dragon breath | target in the front 180° | D6+3 flames around the target | S8, 1 wound, no save, **every unit hit routs** (flags `0x41`) |
| 15 warpfire thrower | needs crew | D6 flames around the target | S4, 1 wound, no save; no misfire |
| 16 (Wyvern shaman) | – | – | not a weapon: marks a monster-class unit as a **spellcaster** (`CanCastSpells`) |
| 17 Gyrocopter steam gun (Infantry-class files) | range 144 (6") | 1, passes through units | S4, 1 wound, no save, hits one model of each unit it crosses |
| 17 Gyrocopter bomb (Archers-class files) | Ctrl + command, only while flying (`GMTXT 2020`) | 1, dropped | radius 72, S4, 1 wound, saves; artillery misfire roll |
| Pestilent Breath (behaviour 0x1B) | scripted units | 1 near the unit | S3, 1 wound, no save, passes through |

The doom diver is an ordinary artillery shot (`0x4C` is only its graphic; no steering found). On landing
the game places a dead-diver corpse decal (the ordinary 32-entry corpse ring, random facing): no game effect.

### Night Goblin Fanatics ✅ / 🟡

Behaviour 0x12 (`FanaticUpdate`). While hidden (object flag `0x400`) the fanatic waits until
no model of its parent unit (`parent_unit`) is within reach, then is out. Each update afterwards:
- every model of an Infantry, Cavalry, Archers, Wizard or Monster unit within **12 units (18 against
  cavalry, 24 against monsters)** takes an **S5 wound roll: 1 wound, no save**; the fanatic survives;
- artillery: the crew as above plus D6 rolls against the machine, then the fanatic **dies**; rolling stock:
  D6 rolls, dies; buildings and scenery: dies; other special units: wounded automatically, dies;
- some terrain areas remove or kill it.
The release step (opcodes 216/217) clears `CantMelee` and runs the same collision with armour saves.
Fanatics are hidden template units tagged `0xABC0`; the parent unit's script spawns three copies with opcode 0xD3
(lateral offsets 0, −20, +20, parent link set). Each copy loops `Query 18` every 5 ticks (→ `FanaticUpdate`);
opcode 0xD8 is a 2D6 × 8 unit jump. `behaviour_code` (behaviour code) is set only by opcode 0x33. 🟡 The event of the
parent script that triggers the spawn was not traced.
WFB: D6 S5 hits per unit touched, 2D6" moves, dies on a double; here damage scales with the models within ½".

### Winds of magic and casting ✅

- **Power**: one pool per side, 0–8 (one for the player, one for the enemy; allies use the player's).
  No per-wizard power, no wizard levels. the game replaces each pool every **50 s of unpaused real time**
  by `Wind(current)`: an empty pool becomes 1–7, otherwise `current − 4 … current + 3`, at least
  1. (Count and Fixed = 8 modes are debug options behind Ctrl/Shift clicks on the magic panel.) Each pool **starts at `rand % 8 + 1` (1–8)**, set by the battle
  window's create handler.
- **Spell/item table** the relevant data, 24-byte records `{GMTXT id, effect code, name, kind (1 spell, 2 item),
  cost, flags}`; costs: 1 Dispel Magic, Azure Blades, Lightning, Fireball, Flying Bower, Mork Save Uz,
  Skitterleap, Pestilent Breath; 2 Wind Blast, Sapphire Arch, Piercing Bolts, Burning Head, Hunting Spear,
  Flock of Doom, Gaze of Mork, Ere We Go, Fists of Gork, Warp Lightning, Madness; 3 Storm of Shemtek,
  Conflagration of Doom, Flamestorm, Tangling Thorn, Curse of Anraheir, Da Krunch. A unit lists up to 5 spells
  (`spells`) and 5 items (`items`).
- **Casting**: the spell button is enabled when the cost fits the pool; the **cost is paid on the click**.
  Azure Blades, Dispel Magic and Fists of Gork need no target. The target click gives order 0x17 → event 0x2B to
  the wizard (a busy wizard: `GMTXT 2014` "…is preparing to cast a spell", order dropped) → casting animation →
  event 0x2C → op 147 `CastPending` → `LaunchEffect`. Storm of Shemtek and Flying Bower keep the wizard busy until
  they end. Ctrl+click on an active spell cancels the caster's effects of that code (no refund).
  **In close combat** a wizard casts at once without the animation if the target is in range and inside the arc; an
  engaged wizard cannot turn, so a target outside the arc cancels the spell (op 0xAA). Outside combat the wizard
  first turns ("Turning Wizard to cast spell.", script 141: instant quarter/half turn beyond 45°, then a wheel);
  the arc is not re-tested after the turn.
- **Checks** (`LaunchEffect`): fewer than 64 active effects; the caster can cast (class Wizard,
  or a leader with `S_BalWeap` 16, e.g. the Orc shaman on a Wyvern); target point within `EffectRange` of the
  unit centre and within **±50° of facing**; unit-target spells need a unit under the point. **No line of
  sight, no casting roll, no miscast, no reload**; on failure `GMTXT 2021` "…attempted to cast … but failed" and
  the power is lost. The 2D6 inside `LaunchEffect` is the bolt count of Storm of Shemtek.
- 🟡 Holding **Shift** at launch switches several spells to alternative projectiles (Flying Bower then does S3
  hits); it reads the physical keyboard, so it affects AI casts too (probably a developer toggle).

### Spells ✅

"Hit" = `ApplyImpact` through the magical callback (so `MagicResistent` ignores half); radius 0 = one random model
of each unit hit. Durations are tick counters: 180 ticks ≈ 18 s, just under one 190-tick turn; nothing ends
"at the end of the turn".

| Spell | Cost | Range | Effect | Duration |
|---|---|---|---|---|
| Wind Blast | 2 | random 4–24" | gust passing through units: S3, 1 wound, save, one model per unit per tick; replaces the previous blast | flight |
| Azure Blades | 1 | own unit | every tick, units overlapping the target unit (not the target itself) take S4 hits, 1 wound, save | 180 ticks |
| Storm of Shemtek | 3 | 24" | **2D6+1 bolts** (the phase counter is incremented after every phase, so the 1↔2 loop adds one) at the nearest enemy near the point: S6, D3 wounds, no save; wizard frozen | until spent |
| Sapphire Arch | 2 | 24" | portal: units swallowed by a previous arch reappear here (killed if gone more than 900 ticks); then every other unit within 48 units vanishes until the next arch | 180 ticks |
| Lightning | 1 | 24" | bolt: S6, D3 wounds, no save | flight |
| Piercing Bolts of Burning | 2 | 18" | bolt: S4, 1 wound, no save, fire | flight |
| The Burning Head | 2 | 18" | head passing through: S4, 1 wound, save, fire; units it is inside take a **panic test** | flight |
| Conflagration of Doom | 3 | unlimited | radius D6×8+8; panic tests every 9 ticks for D6×9 ticks, then units inside **lose all models** and overlapping units a share, **slain outright**; buildings destroyed | fuse + fall |
| Flamestorm | 3 | 24" | column of flame, every 18 ticks every model inside radius 16: S4, 1 wound, no save, fire | 🟡 **no end** (until dispelled, cancelled or recast) |
| Fireball | 1 | 24" | S4, 1 wound, no save, fire; burns Tangling Thorns | flight |
| The Flying Bower | 1 | unlimited | the caster's unit leaves combat and flies to the point | flight |
| Tangling Thorn | 3 | 24" | units within 32 are **halted and held** (also blocks shooting and casting); fire destroys it | growth + 90 ticks |
| Hunting Spear | 2 | 24" | homing spear; at the target strikes 6 times at S6…S1, D3 wounds each, no save | ≤ 180 ticks |
| The Curse of Anraheir | 3 | 24" | **movement rate and Initiative halved**; mounted targets take a panic test each tick of segment 10 and the curse ends when one routs | 🟡 **no end otherwise** |
| The Flock of Doom | 2 | 24" | three strikes, radius 32: S3, D6 wounds, save | 3 phases |
| Dispel Magic | 1 | self | dispel aura (8.10) | ≤ 180 ticks |
| Gaze of Mork | 2 | 24" | beam passing through: S6, 1 wound, save | flight |
| Ere We Go! | 2 | 36" | T +1 and **I := 20** (the unit makes no close combat attacks, section 5.1) | 180 ticks |
| Da Krunch | 3 | 24" | giant foot: **every model** of every unit reaching within 32 units **slain**; buildings destroyed | ≈ 45 ticks |
| Fists of Gork | 2 | self | every 4 ticks the nearest unit of **either side** within 16: wound roll at S6, 1 wound, no save, a 6 chains | 180 ticks |
| Mork Save Uz! | 1 | 24" | dispel aura around a unit, 50% every tick | 180 ticks |
| Warp Lightning | 2 | 24" | bolt: S5, D6 wounds, no save (Doomwheel version fails on 1 in 6) | flight |
| Skitterleap | 1 | unlimited | the caster's unit teleports to the point | animation |
| Pestilent Breath | 1 | 6" | cloud passing through: S3, 1 wound, no save | flight |
| Madness | 2 | 24" | the target unit **changes side** (events 0x31/0x32), friends drop it as a target | 180 ticks |

Area objects of Wind Blast, Flamestorm, Tangling Thorn and Da Krunch are temporary **solid scenery** (they push
units back, stop charges, bend routes, block spotting and obstruct missiles). Only Wind Blast, Flamestorm and
Tangling Thorn replace the caster's previous instance; other spells stack (two
overlapping Ere We Go casts would restore a wrong I, 🟡). No spell passes the panic or rout bits to
`ApplyImpact`; panic comes from Burning Head, the Conflagration fuse and the Curse on mounts.

### Dispel and anti-magic ✅

`DispelAura`: each tick of its schedule, every other dispellable effect within **80 units** of
the protected unit is removed on a percentage roll (`GMTXT 2006` "…has been dispelled by…"). Innate effects,
other dispels and effects cast by or on the protected unit are skipped; **there is no side test**, so friendly
spells nearby are dispelled too.

| Source | Chance | Schedule |
|---|---|---|
| Dispel Magic | 50% | every 3rd tick for up to 180 ticks |
| Mork Save Uz! | 50% | every tick, 180 ticks |
| Banner of Arcane Protection | 50% | every tick, whole battle |
| Talisman of Obsidian | 100% | every tick, whole battle |
| `MagicResistent` | 50% of magical hits ignored | always |
| Banner of Arcane Warding | – | **no code at all** |

🟡 Because effects on the bearer's own unit are skipped, a Talisman never removes a curse from its own unit.

### Magic items in battle ✅

- **Banner of Wrath** (effect `0x105`) casts a Lightning and **Grudgebringer** (`0x10A`) a Fireball: no power, no
  wizard needed, once per wind (flag `0x20`, re-armed when the power pool is refreshed). The Dragon's breath uses
  the Grudgebringer effect innately (section 8.6).
- **Potion of Strength**: single use, +3 S for the rest of the battle (section 5.6).
- Passive items (banners, armour, swords, talismans) have disabled buttons. **The AI never activates items.**
- In the scripts, Banner of Wrath, the Talisman and Arcane Warding appear only in the `RLTEST*.MRC` test armies;
  Arcane Protection appears nowhere.

### AI casting ✅

Library scripts (opcodes 147–175 named in the report): a computer wizard picks the nearest enemy and the first
spell of its list that it can afford and whose rule passes (`AIChooseSpell`), turns to face and
casts. The same scripts run for player wizards given an attack order, so they cast automatically from the
player's pool. Wind Blast and Sapphire Arch are never chosen. The area-spell rule (Conflagration, Flying Bower, Tangling Thorn, Flock of Doom, Da Krunch) is **inverted**:
`NonFriendNearPoint` returns 1 whenever a non-friendly unit is within the radius of the point, and the target unit
itself is at distance 0, so the **AI never casts these spells at a unit target**.

## 9. Deviations from Warhammer Fantasy Battle 4th edition

Comparison with the 4th edition rules as the project understands them (to-hit, to-wound and save charts,
combat resolution with rank bonus up to +3, flank/rear, standards, 2D6 Leadership tests, BS to-hit
chart for shooting).

| Rule | Game | Status |
|---|---|---|
| To-hit, to-wound, save modifiers | identical charts (plus WS/T 0 entries) | ✅ same |
| Armour values | ratings 1–4 = 6+…3+, mounted +1 (2+ cap) | ✅ same idea |
| Armour rating 5 on foot | no save (table value 7); with an armour item it becomes regeneration | ✅ deviation, probably a bug |
| Leadership test | uniform 2–12, not 2D6 | ✅ deviation |
| Rank bonus | `size/width − 1` for width > 3, **uncapped** | ✅ deviation |
| Standards, general | no standard bonus, no battle standard, no general's Leadership | ✅ deviation (absence) |
| Flank / rear | +1 / +2 | ✅ same |
| Hatred | re-roll misses in the first round, and break tests become "10 or less" | ✅ extended |
| Fear | beaten by a fear-causer: break; failed test when charged or on contact: flight regardless of numbers; charging it: refused | ✅ deviation |
| Terror | non-immune units flee without a roll when charged by or touching it, and cannot charge it | ✅ deviation |
| Panic | test at every lost quarter of original strength from casualties, sliding modifier; test on any charge into rear/rear half of a flank | ✅ deviation |
| Rally | impossible at ≤ 25% strength, casualty penalties; first attempt a turn after the rout, then every 3 segments, only on the player's order (or the independent toggle) | ✅ deviation |
| Strike order | by Initiative (segments 10…1), charging gives +1 S instead of striking first | ✅ deviation |
| Who fights | orthogonal contact on a 12-unit grid, gradual wrap-around; no rank or spear rules | ✅ deviation |
| Charge | +1 S for the first `1.5 × frontage` attacking models, no strike-first | ✅ deviation |
| Outnumbering a model | +1 WS for every attacker after the first on the same enemy model | ✅ deviation (no WFB 4th ed equivalent) |
| Monsters | part of their attacks struck back immediately at each attacker | ✅ deviation |
| Timing of results | once per turn at the grid's segment; first after two turns, then every 1–2 turns; newcomers immune for a turn | ✅ deviation |
| Caught fleeing troops | 🟡 automatic hits once per segment of contact (wound and save rolls still apply) instead of being destroyed | 🟡 deviation |
| Pursuit | only the routed unit's opponents; AI never tests to stop; ends on budget, target rallied/dead, or map edge | ✅ deviation |
| Fleeing movement | straight away from the opponent, continuous, off the table = removed | ✅ adapted |
| `FearToGobs` | parsed but never used | ✅ |
| Breath, warpfire, fanatics | several single-model magical hits (breath S8 with automatic rout); fanatics wound every model within ½" | ✅ deviation |
| Weapon rules | two-handed +2 S and spear/halberd +1 S only; no strike last, no spear ranks | ✅ deviation |
| Regeneration | 4+ in close combat; immune to all missiles; no fire rule | ✅ deviation |
| Initiative 20 | "Ere We Go!" and the Dragon never strike in their own segment | ✅ deviation, probably a bug |
| Mounts | never wounded separately; mount M unused | ✅ deviation |
| Command abilities | "fight harder" (+1 S, +1 Ld for a segment) and "independent" toggles | ✅ game addition |
| Movement | continuous; speed from M and I (`s_rlmv`), ×1.8 free, ×2.5 charging; no terrain penalties; wheel on a front corner | ✅ deviation |
| Turn length | 10 segments of 19 ticks at 10 ticks/s = 19 s real time | ✅ game addition |
| Magic | shared 0–8 power pool per side re-rolled every 50 s; costs 1–3; no casting roll, no line of sight, no levels, no dispel cards | ✅ deviation |
| Dispel | percentage auras within 80 units, also against friendly spells | ✅ deviation |
| Spell effects | real-time redesigns: slain-outright areas (Conflagration, Da Krunch), portal (Sapphire Arch), side change (Madness) | ✅ adapted |
| Lance | no bonus beyond the generic charge +1 S | ✅ deviation |
| Mounts | own attacks, fixed charge strength | ✅ deviation |
| Shooting | scatter by BS, no to-hit chart; ⌈N/4⌉ projectiles per volley; 90° arc; reload cooldown by Initiative; no moving/long-range/cover modifiers (scenery adds scatter); into close combat allowed | ✅ deviation |
| Artillery | projectile hits every model of a unit it lands in or flies through (no bounce, no template); blast margin S/2; misfire on 6 then 1 | ✅ adapted |

## 11. Open points
> **Tracked on GitHub**: these open items are tracked as issue #44 (`topic:combat-rules`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


Everything that is not established, as a register for the next sessions. **Priority** is for an
engine that reproduces the battles: *high* = changes outcomes noticeably, *medium* = visible in some
situations, *low* = cosmetic or rare. "How to resolve" names the next concrete step; all of them are
research unless marked Wine.

### Close combat

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R1 | **Charge counter value** | ✅ resolved: `floor(1.5 × frontage)` attacking models (section 5.5). | — | done |
| R2 | **Return blow** | ✅ resolved: monster attack pools only (section 5.2). | — | done |
| R3 | **Which models fight** | ✅ rules resolved: battle-grid adjacency, frontage per tick, reserves (section 5.7); the resulting numbers are R36. | — | done |
| R4 | **Unit flag bit 30** | ✅ "fight harder" button: +1 S, +1 Ld for one segment, focused unit in melee (Player orders). | — | done |
| R5 | **Initiative above 10** | ✅ "Ere We Go!" sets I 20 and stops the unit's own attacks; the Dragon only returns blows (section 5.1). | — | done |
| R6 | **Automatic hits** | ✅ war machines and inanimate targets; 🟡 contact attacks on turned models (section 5.2). | Case 3 follows R14. | done |
| R7 | **+1 WS condition** | ✅ ganging-up bonus (section 5.2). | — | done |
| R8 | **Weapon rules absent** | ✅ weapon class read only for strength (section 5.2). | — | done |
| R9 | **Mount details** | ✅ only charge S, WS, S, A used; no separate wounds (section 5.4). | — | done |
| R10 | **Regeneration flag** | ✅ missiles never wound regenerators; which spells do is R50 (section 5.3). | — | done |
| R11 | **Armour rating 5 = no save** | ✅ no special handling anywhere; items upgrade it to regeneration. Engine decision: reproduce or fix. | Owner decision. | decision |
| R12 | **Items outside close combat** | ✅ resolved (sections 8.10, 8.11); Banner of Arcane Warding has no code. | — | done |
| R32 | **Charge and pursuit orders** | ✅ order table and flag setters (Player orders). | — | done |
| R33 | **Charging monster keeps +1 S** | ✅ confirmed; engine decision (reproduce or fix). | Owner decision. | decision |
| R34 | **Early release of reserves** | ✅ set by every model death, so gaps in the line refill at once. | — | done |
| R35 | **Grid edge cases** | ✅ `s_side & 0xE0 == 0x20` = fake units for placed buildings/furniture (Madness keeps it); formation flag 0x80 = furniture footprint bit. ✅ resolved further: per-tick placement bounds-checks to 0..16 and defers overflow to later ticks (section 5.7); 🟡 initial grid-footprint creation has no such clamp — an out-of-range write is possible for frontage/ranks > ~16, reachability from real formation caps unconfirmed. | Grep formation-size caps, or Wine session with an oversized formation. | low |
| R36 | **Models fighting in practice** | 🟡 wrap-around completes within 2–4 segments; limited by free cells (section 5.7). ✅ resolved: cell ownership is per side not per unit (allied units on one grid share one undivided cell pool); pile-on rank/direction bonuses are strictly additive with no cap; separate grids never check proximity to each other and can freely overlap in world space with no interaction; grid placement/pairing never consults terrain or map-boundary code, only the generic always-on per-unit boundary repel applies, uncoordinated with grid cells (section 5.7). | Simulate or observe under Wine for real fight-population numbers. | low |

### Combat resolution and morale

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R13 | **Battle grid lifecycle** | ✅ resolved: record layout, joining, resolution timing, leaving (sections 5.7, 6.2); `unit_worth` is unit worth, not a counter. | — | done |
| R14 | **After a unit breaks** | ✅ resolved (sections 7.5, 7.7); 🟡 catching by contact attacks and the movement speeds remain (R39). | — | done |
| R15 | **Events** | ✅ mechanism and most codes resolved (section 4, behaviour scripts); 🟡 0x05, 0x09, 0x14, 0x15, 0x17, 0x1C/0x1D, 0x31–0x38 (R41). | — | done |
| R16 | **Standards, general** | ✅ none exist (section 6.1). | — | done |
| R17 | **Flank/rear test** | ✅ resolved: charge into rear arc or rear half of a flank → Leadership test (section 7.8). | — | done |
| R18 | **Panic triggers** | ✅ resolved: only deaths (`killed = 1` via the death callbacks); `s_routed` = models fled off the table (section 7.2). | — | done |
| R19 | **Fear/terror callers** | ✅ resolved: charged → flee, charging → refused, contact → flee; terror without a roll (section 7.3). | — | done |
| R20 | **Rally and pursuit schedule** | ✅ resolved: first attempt a turn later, then every 3 segments; attempt flag from order 0x14 or bit 27 (sections 7.4, 7.5). | — | done |
| R21 | **Unused/unclear psychology** | ✅ resolved: `FearToGobs` unused; `CantMelee` is a target property (section 3.4). | — | done |
| R38 | **Opcode catalogue** | ✅ all 232 opcodes catalogued (228 established, 4 hypotheses) and all 28 `AIQuery` cases; summarised in section 4. The `whshr` script tool is R51. | — | done |
| R39 | **Flight and pursuit speeds** | ✅ k 1.5 for both, pursuit step `min(24 × s_rlmv, 10 × distance)` (section 4). | — | done |
| R40 | **Unit flag bit 27** | ✅ "independent" toggle and its effects (Player orders); 🟡 name. | — | done |
| R41 | **Remaining event codes** | ✅ senders of 0x05, 0x14/0x15, 0x33, 0x36, 0x37, 0x38 found (section 4); 🟡 meaning of 0x36, 0x39. | — | done |
| R42 | **Initial scripts** | ✅ `set:script=N` is the mission script id (3–37 per DLL), `PLAYER_SCRIPT` = 100; `DLLReturnInstCount` = 33000 format check. | — | done |

### Shooting and artillery

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R22 | **Missile constants** | ✅ resolved: radius, wound die, S, S vs buildings, saves, flags traced end to end (section 8.3). the game is an animation-stream opcode, not the missile path (R43). | — | done |
| R23 | **Range, line of sight, reload** | ✅ resolved: arc ± 45°, strict range, reload formula, scenery obstruction +8 scatter, crossbows blocked by friends (sections 8.1–8.3). | — | done |
| R24 | **Real time of a tick** | ✅ 100 ms timer, one tick per message; 19 ticks per segment (section 4, Real time and movement). | — | done |
| R25 | **Shooting restrictions** | ✅ resolved: ⌈N/4⌉ projectiles, halt before firing, no modifiers, shooting into combat allowed (section 8.1); 🟡 some flags (R44). | — | done |
| R26 | **Special missile weapons** | ✅ resolved (section 8.6). | — | done |
| R27 | **Fanatics** | ✅ hits and death conditions (section 8.7); 🟡 movement and behaviour assignment (R45). | — | done |
| R43 | **Animation instruction stream** | ✅ per-object animation bytecode, 59 opcodes (section 4); 🟡 opcode names. | Name the opcodes when animations are implemented. | low |
| R44 | **Shooting flags** | ✅ `unit_flags2` bit 0 anchors machines, bit 3 never set, `unit_flags 0x80000` hidden, `0x100` set by library script 152 on event 0x36 when objective index 7 exists (units leaving the battle, R60). | — | done |
| R45 | **Fanatic release and movement** | ✅ spawned as three copies by opcode 0xD3, `Query 18` loop, jump opcode 0xD8 (section 8.7); 🟡 spawn trigger event. | Trace the parent script event. | low |
| R46 | **Obstruction geometry** | ✅ `asin(radius / d)` angular half-width (section 8.3). | — | done |
| R47 | **Doom diver remains** | ✅ corpse decal, no game effect (section 8.6). | — | done |
| R48 | **Withdraw condition** | ✅ only against rolling stock/furniture with no other enemy; otherwise the unit routs (Player orders). | — | done |
| R49 | **Order-blocking flag** | ✅ `0x100000` = braced against a charge (Player orders). | — | done |
| R51 | **Script tools** | ✅ `whshr/behaviour.py`, `python3 -m whshr scripts`, check group "behaviour scripts" (section 4). | — | done |

### Structures and scope

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R28 | **Remaining stat bytes** | ✅ `s_wdth`/`s_rkmd`/`s_spar` = frontage, ranks, full-frontage front ranks (recomputed); `s_rlmv` recomputed from a float at set-up; `s_cmdr`, `s_armname`, `s_banner` always 0; `s_rnks` is the script's rank count used by the formation code; second stat block at `leader_stat_copy` read for leaders/artillery. | Trace the float for `s_rlmv` in; where `leader_stat_copy` is copied from the leader. | low |
| R29 | **Movement** | ✅ `s_rlmv` from M and I, speed factors, turning, charge reach, no terrain effect (section 4). | — | done |
| R30 | **Magic** | ✅ resolved: power pools, casting, every spell, dispel, AI (sections 8.8–8.12). | — | done |
| R31 | **`the original front end` copy** | ✅ dead code: its battle dispatcher has no callers; only the army writer is used by the front end. | — | done |

| # | Open point (magic) | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R52 | **Never-ending spells** | Flamestorm and Curse of Anraheir have no observed timeout. | Play a controlled battle for several turns. | medium |
| R53 | **AI area spells** | ✅ confirmed inverted: the AI never casts area spells at a unit target (section 8.12). | — | done |
| R54 | **Starting power and Storm of Shemtek count** | ✅ pools start at 1–8; Storm fires 2D6+1 bolts (sections 8.8, 8.9). | — | done |
| R55 | **Shift variants and Ctrl repeat casts** | Physical-keyboard tests at launch; Ctrl mouse flag repeats casts. | Decide whether an engine keeps them (developer toggles?). | low |
| R56 | **Casting in close combat, turning to cast** | ✅ casts at once in combat if in arc, else cancelled; turn step outside combat (section 8.8). | — | done |
| R57 | **Area objects** | ✅ temporary solid scenery (`os_active|os_solid`): push units back, stop charges, bend routes, block spotting, obstruct missiles. | — | done |
| R58 | **Spells against regenerators** | ✅ no-save spells wound them; save + type 0 spells allow regeneration; Burning Head never wounds them (section 5.3). | — | done |
| R59 | **Duplicate opcode names** | 0x3A, 0x88 and 0xAF share the name `TakeEventTarget` (same helper, different arguments). | Give distinct names in `whshr/behaviour.py`. | low |
| R60 | **Objective index 7 and leaving the battle** | ✅ letter G "Inside the gates!" in the siege battles BF015/BF017 (Missions and objectives). | — | done |
| R61 | **Visibility details** | Unit flag bit 3 (`0x8`) also doubles the view cone together with melee (`0x208`); the shooting/effect region behaviour is not fully confirmed; mode 1 of the "attack the n-th nearest" opcodes uses a signed-axis metric (🟡). | Verify the behaviour in a controlled play session. | low |
| R62 | **AI deployment** | See [deployment.md §1](deployment.md#1-mission-entry-and-default-positions). | — | done |
| R63 | **Objective evaluators** | ✅ resolved: all 26 letter evaluators read (Missions and objectives). S "Capture Hiln" and several others (T, V, W) turn out to be unconditional stubs rather than real checks; Y mirrors a shared flag rather than computing anything itself. | — | done |
| R64 | **Win/loss dialog codes** | The game opens dialog 9 or 0xF depending on battle state; which is which is not yet confirmed. | Verify both outcomes in a play session. | low |
| R65 | **Deployment** | Default slots and zone rules established in [deployment.md](deployment.md); remaining interaction checks are listed there. | [Remaining checks](deployment.md#7-remaining-checks-for-full-original-parity). | low |
| R66 | **Footprint box and anchor** | ✅ resolved: for blocks the map object centre is `(ranks − 1) × 6` behind the unit position, the middle of the block; other kinds keep it at the unit position (section 4, Formations). | — | done |
| R67 | **Formation spacing on screen** | ✅ resolved: both viewers use the traced 12-unit block (`whshr/formation.py`); the BF001 screenshot matches its rank sizes and offsets (section 4, Formations). | — | done |
| R68 | **Troop sprite and scenery scale** | One troop sprite pixel ≈ 0.45 world units, measured on a screenshot and used by both viewers but not traced; against it, PBX pines in the 3D viewer look about twice as large as the trees in the screenshot. | Find the billboard scale in the 3D sprite renderer; compare scenery sizes with more screenshots. | low |

| # | Open point (engagement lifecycle, September 2026) | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R70 | **Cannot-engage flag** | A unit with this flag refuses engagement outright; its source and full effects remain unknown. | Verify with a unit that cannot be engaged. | medium |
| R71 | **Opcode 0x57 leaving a shared grid** | The first instruction of pursuit script 164; it materially affects the lifecycle. Behaviour is not yet independently verified. | Verify this behaviour directly. | medium |
| R72 | **Bounding radius formula** | The evidence is consistent with `sqrt((frontage×6)² + (ranks×6)²)`. Inferred, not verified. | Verify with known frontage/rank combinations. | low |
| R73 | **Rally inside an enemy footprint** | `0x400` is cleared by any re-form, so a rallied unit is immediately engageable; whether one that rallies while still overlapping an enemy re-engages on the very next tick or is pushed out first depends on the order of the game and the collision pass within that frame. | Wine session. | low |
| R74 | **Grid-ordering behaviour in practice** | The "another enemy on this grid" choice is the first match in **the unit's own model-list order**, with no distance or threat tiebreak, so a reimplementation that pairs models in a different order picks a different next opponent without being wrong about the rule. | Accept, or match the original pairing order. | low |

### Hypotheses in this report to confirm

Section 3.2: `s_rnks`, `s_rlmv`, `s_pntval`, `s_armname`. Section 3.4: `CantMelee`. Sections 5.2/5.5:
return blow, charge duration. Section 7.7: catching fleeing units, speeds.
Section 8.7: fanatic release and movement. Contact-attack behaviour.

### Candidates for a Wine session

Only worth the effort if research stalls, as the game exits randomly under Wine:

- R5: confirm that Orcs under "Ere We Go!" and the Dragon (`BF014`) make no close combat attacks of their own.
- R11: casualties inflicted on a leader with `s_armr=5` (e.g. Commander Bernhardt).
- R36: how many models of a deep unit end up fighting after a few turns of combat.
- R52: does a Flamestorm or a Curse of Anraheir ever end on its own?
- Whether a Banner of Arcane Warding has any visible effect.
- Section 7.1: a flat 2–12 roll cannot be distinguished from 2D6 in single tests; not worth testing.

### Status and next steps

This specification covers the mechanics currently needed by the reimplementation. Open points above
identify behaviour that still needs confirmation through gameplay. Engine decisions include whether to
preserve apparent original quirks, such as armour rating 5 and charging monsters retaining +1 Strength.
