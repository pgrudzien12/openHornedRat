# Game rules — unit stats, combat, morale and shooting (`GAMEF.DLL`)

Roadmap tasks 4.3 (combat rules) and the parts of 4.2/1.8 they need. Static analysis only: the game
cannot be run reliably here, so nothing below was observed in the running game except the in-game unit
panel quoted by the project owner. Every claim is marked:

- ✅ **established**: the code path was read (function address, what it reads, the formula), and/or a
  data table matches a known chart, and/or the data agrees across all units;
- 🟡 **hypothesis**: consistent with the code or data but not fully traced, with the reason given.

This file describes the logic in prose and short pseudo-code. No decompiled listings are reproduced.

## Key findings

1. **Stat layout** ✅ Each `setstats` value is one byte of a fixed block (`unit + 0x7A + token − 13`);
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
6. **Leadership** ✅ `modifier + (rand() % 11 + 2) <= Ld` of the leader: a **uniform 2–12 roll, not 2D6**.
7. **Morale** ✅ Break test at the losing margin; beaten by a fear-causer = break; hatred = pass on
   10 or less. Panic at every lost quarter of original strength (casualties only). A charge into the rear
   or the rear half of a flank forces a Leadership test. Failed fear tests and any contact with a
   terror-causer mean flight. Routed units run straight away from their opponent and leave the table;
   pursuers get automatic hits while in contact; rally and pursuit restraint are rolled only on the
   player's order (or for units with the "independent" toggle).
8. **Shooting** ✅ No to-hit chart: a projectile flies to a point scattered by `rand() % (11 − BS)` steps
   per axis (step grows with distance; +8 behind scenery). Archers fire one projectile per 4 models,
   artillery one; targets must be in the 90° front arc and in range; reload `(10 − I) × 18` ticks minus a
   weapon constant. Arrows wound one model; blast weapons wound every model of a unit they land in or
   fly into, and S/2 models in the margin. Ranges at 24 units per inch. Shooting into close combat is
   allowed. Artillery misfires on a 6, explodes on a following 1.
9. **Unit behaviour is bytecode** ✅ Every unit runs a script (232-opcode interpreter in `GAMEF.DLL`) that
   consumes queued events (rout, charged, rally…) and decides the consequences. The scripts are data in
   `SCRIPT/BFxxx.DLL`: ids from 0 per mission (3–37 scripts), 100–170 a shared library identical in all 45 DLLs.
10. **Player commands** ✅ Orders are button codes executed by the unit scripts; a "fight harder" button gives the
    focused unit in melee +1 S and +1 Leadership for one segment; an "independent" toggle lets a unit rally,
    react and pick targets on its own.
11. **Time and movement** ✅ One tick per 100 ms timer message (≤ 10 ticks/s, no catch-up); 19 ticks per segment,
    10 segments per turn = 19 s. M only feeds a speed stat `s_rlmv = trunc(4.8 × M + I) / 2`; units move
    `s_rlmv × k / 16` units per tick (k 1.8 free, 1.0 closing, 2.5 charging, 1.5 fleeing); terrain does not slow
    them; units wheel on a front corner. Routes use a reactive steer-around controller (no path graph); units push
    apart on overlap; visibility is a 100° cone blocked by scenery and `SightEdge` lines, never by terrain height.
12. **Magic** ✅ Each side has one shared power pool of 0–8, re-rolled by a random walk every 50 s of real time;
    spells cost 1–3 and always work when the target is in range and within ±50° of the wizard's facing (no
    casting roll, no line of sight, no miscast). Dispelling is a spell or an item aura with a percentage chance.
13. **Biggest open points** (section 11): the objective evaluator functions (R63), the optional batch 5 (animation
    bytecode, sounds by event) and a few effects to confirm in the running game (never-ending spells). Campaign
    progression and save games: `notes/campaign.md`.

## Contents

1. Tooling
2. Binaries
3. Unit stat fields (`setstats`, `psy_status`)
4. Runtime structures, random numbers, battle clock, behaviour scripts and events
5. Close combat
6. Combat resolution and break tests
7. Leadership tests, panic, fear and terror, rally, pursuit
8. Shooting, artillery and magic
9. Deviations from Warhammer Fantasy Battle 4th edition
10. Function index
11. Open points (register, verification candidates)

## 1. Tooling

- Ghidra 12.1.3 headless with Temurin JDK 21, both unpacked under `~/tools` (no root; downloads
  checked against the published SHA-256). Default auto-analysis of `GAMEF.DLL` and `WHSHR.EXE`.
- Two small Ghidra scripts in `tools/ghidra/` (optional, documented in `tools/ghidra/README.md`):
  `DumpStringRefs.java` (strings → code references and pointer tables) and `Decompile.java`
  (decompile selected or all functions into one text file). Their output was kept in a scratch
  directory, outside the repository.
- `objdump` for spot checks of the disassembly (element sizes the decompiler hid), Python for raw
  table dumps.
- Verification in the repository: `whshr/rules.py`, run by `python3 -m whshr check` ("game rules
  tables and unit stats") and printable with `python3 -m whshr rules <installation> [BTS/MRC]`.
  The check reads the tables from the local `GAMEF.DLL`, compares them with the WFB 4th edition
  charts, and decodes every unit and leader in `FILE/SCRIPT` and `SAVE`.

Function names below (`FUN_1000xxxx` = Ghidra's default name, i.e. the entry address) are given
descriptive names in the function index (section 10).

## 2. Binaries

| File | Image base | Linker date | Role for the rules |
|---|---|---|---|
| `GAMEF.DLL` | `0x10000000` | 1995-12-11 03:03 | battle engine: exports `OpenGameWindow`, `OpenGameWindowDLL`, `KillGameWindow`, `DisplayAllGameWindow`, `GlueSetOptionAddress`; imports the Reality Lab renderer (`rlddf.dll`). **All addresses in this report are in `GAMEF.DLL`.** |
| `WHSHR.EXE` | `0x00400000` | 1995-12-11 06:49 | front end; imports `gamef.dll`. It contains byte-identical copies of the combat tables and the same script keyword tables and unit writer (e.g. `FUN_004087f5`), i.e. a second copy of much of the battle code. Not analysed further; `GAMEF.DLL` is taken as the reference. |

Both are 32-bit MSVC builds; `rand()` is the MSVC runtime LCG (section 4).

## 3. Unit stat fields

### 3.1 Keyword tokens and the byte block ✅

`GAMEF.DLL` maps script keywords to integer tokens with `{char *name; int token}` tables:

| Table | Address | Contents |
|---|---|---|
| instructions | `0x100E92A0` | `setstats`=1, `addunit`=2, `endunit`=3, `hidden`=4, `addleader`=5, `endleader`=6, `addspell`=7, `addmagicitem`=8, `set`=9, `addobject`=10 … (looked up by `FUN_1000efa0`, which reports `Unknow Instruction %s Line %d`) |
| fields | `0x100E97C8` | `psy_status`=10, `script`=11, `map`=12, **`s_side`=13 … `s_banner`=39**, `s_calualties`=40, `s_routed`=41, `s_kills`=42, `s_Exp`=43, then window/glue keys (`radius`, `Lines`, `sequence`, `res`, … `inactivedepend`=82), an empty entry (83), and `os_*`, `ns_*`, `bnd_*` flag values |
| psychology | `0x100E9AA8` | `CantBreak`=19 … `CantDie`=32 (section 3.4) |

The unit writer used by the developers' editor (`FUN_10009190`, which also prints the
`;S_RACE is %s %s...are you sure this is right?` comment) emits each `setstats` line with
`FUN_1000f160(file, unit+0x7A, token, count)`. The disassembly of `FUN_1000f160` shows that value
*i* is the **byte** at `unit + 0x7A + (token − 13) + i`. The calls are:

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

So **tokens 13–39 are one byte each at `unit + 0x7A + (token − 13)`**, and a `setstats` line fills
consecutive fields starting at its key. That explains why `s_mount` has 6 values
(`s_mount s_armr s_weap s_race s_pntval S_BalWeap`), why `s_cmdr=0,0,15,0` repeats
`s_armname=0,15`, and the old 9-value `s_rlmv`/`s_lead` lines in `PLOT1`. Tokens 40–43 are written as
`set:` lines from 16-bit fields at `+0x330`, `+0x332`, `+0x334`, `+0x336`.

The rules code reads the same bytes through a per-model pointer to this block (section 4), at offsets
that match exactly: `+9` WS, `+0xB` S, `+0xC` T, `+0xD` W, `+0xF` A, `+0x10` Ld, `+0x11` mount,
`+0x12` armour, `+0x13` weapon class, `+0x14` race.

Evidence from the data (check in `whshr/rules.py`): all 1415 units and leaders in the 87 scripts
and the save armies decode without overflow, and their 32 335 `setstats` values never contradict
each other (e.g. every `s_mount[2]` equals the separate `s_weap` line). The in-game panel of
"Mercenary Crossbows, Crossbow 12/12: M 4, WS 3, BS 4, S 3, T 3, W 1, I 3, A 1, Ld 7" is
`SAVE/PLAY.MRC`: `s_side=3,12,12,3`, `s_move=4,3,4,3,3,1,3,1,7`, `s_weponame` 15 → `BRTXT 215`
"Crossbow". (`FILE/SCRIPT/BF001.MRC` has the pre-campaign strength `10,10`.)

### 3.2 Field meanings

| Token | Field | Offset | Meaning | Status and evidence |
|---|---|---|---|---|
| 13 | `s_side` | `+0x7A` | bit 7 enemy side, bit 6 NPC/neutral, bits 0–5 type code (table in `FORMATS.md`) | ✅ bit 7 selects the side a combat result is credited to (`FUN_10004470`); type codes from statistics |
| 14 | `s_orgsize` | `+0x7B` | original number of models | ✅ panic test uses `orgsize >> 2`; test files write 0 here and a size in the next byte |
| 15 | `s_size` | `+0x7C` | current number of models | ✅ every per-model loop; decremented when a model is removed (`FUN_10008ca0`) |
| 16 | `s_rnks` | `+0x7D` | number of ranks | 🟡 read by formation code; values 1–7 fit the unit sizes |
| 17 | `s_wdth` | `+0x7E` | frontage (models per rank) | ✅ recomputed by the formation code `FUN_1002c9e0` as `ceil(size / ranks)`; rank bonus `size / width − 1` (section 6); charge bonus `1.5 × frontage` |
| 18, 19 | `s_rkmd`, `s_spar` | `+0x7F`, `+0x80` | runtime: number of ranks in the formation, models in the last rank | ✅ written by `FUN_1002c9e0`; never set by scripts |
| 20 | `s_rlmv` | `+0x81` | flee movement rate | 🟡 recomputed from a float at unit set-up (`FUN_10003aa0`); subtracted from the movement counter of fleeing units every tick (`FUN_10029780`) |
| 21–29 | `s_move`, `s_wepn`, `s_bals`, `s_strn`, `s_tuff`, `s_wnds`, `s_init`, `s_atks`, `s_lead` | `+0x82…+0x8A` | M WS BS S T W I A Ld | ✅ tables indexed by these bytes (sections 5–8); in-game panel |
| 30 | `s_mount` | `+0x8B` | 0 none, 1 Warhorse, 2 War Boar, 3 Giant Wolf, 4 Cave Squig | ✅ mount records at `0x100E8D58` (section 5.4); 1 on all horse riders, 2 on Boar Boyz, 3 on Wolf Riders |
| 31 | `s_armr` | `+0x8C` | armour code: 0–5 rating, 6 regeneration, 7 void, 8–13 mounted rating 1–6 | ✅ save table (section 5.3); `BRTXT` 100–105 "Armour Rating 0–5", 106 "REGENERATE!!!!", 107 "VOID!!!!!!!!!!", 108–113 "Armour Rating 1–6"; Troll has 6 |
| 32 | `s_weap` | `+0x8D` | close combat weapon class: 0 none, 3 hand weapon, 4 two-handed, 10 spear/halberd class | ✅ strength table (section 5.2); class 4 on Greatswords, Hammerers, Rat Ogre, Treeman; 10 on halberdiers, Stormvermin, Stickers, Wolf Riders, artillery crews |
| 33 | `s_race` | `+0x8E` | `class × 8 + race`; race 0 Human, 1 Elven, 2 Dwarven, 3 Goblinoid, 4 Orc, 5 Skaven, 6 Peasant, 7 big; class 0 notype, 1 Infantry, 2 Cavalry, 3 Archers, 4 Artillary, 5 Wizard, 6 Monster, 7 RollingStock, 8 Special, 9 Furniture | ✅ name tables `0x100E9B20`/`0x100E9B40`; the editor comment is built from them and agrees with `s_race` in 879/889 units; class drives code paths (`& 0xF8`) |
| 34 | `s_pntval` | `+0x8F` | points value: experience gained by the killer, +7 per campaign promotion | ✅ `RemoveModel`; promotions in `notes/campaign.md` |
| 35 | `S_BalWeap` | `+0x90` | missile weapon code (section 8) | ✅ shooting switches on it |
| 36 | `s_cmdr` | `+0x91` | unknown, always 0 | ⬜ |
| 37 | `s_armname` | `+0x92` | armour name, always 0 | 🟡 by analogy with the next field |
| 38 | `s_weponame` | `+0x93` | weapon name: string `BRTXT 200 + n` | ✅ 22 names checked against their units (1 Spear on Stickers, 11 Halberd, 13 2-H Hammer, 15 Crossbow, 17 Lance on Reiksguard, 25 Scimitar on Clanrats…) |
| 39 | `s_banner` | `+0x94` | unknown, always 0 | ⬜ |
| 40 | `s_calualties` | `+0x330` (16 bit) | models lost | ✅ incremented per model killed; used by the rally test |
| 41 | `s_routed` | `+0x332` | models removed without being killed | 🟡 incremented on the other removal path |
| 42 | `s_kills` | `+0x334` | enemy models killed | ✅ incremented on the killer unit |
| 43 | `s_Exp` | `+0x336` | experience | ✅ killer gains the victim's `s_pntval` |

A leader has its own block of the same layout; the unit record keeps a second copy at `+0x95`
(the reload and missile code read `+0xA3` and `+0xAB`, which are I and `S_BalWeap` of that copy).
Artillery crews carry their machine's `S_BalWeap` on the leader (e.g. 5, 6, 8).

### 3.3 Effective Leadership ✅

`FUN_10003d20`: the leader model's Ld if the unit has a leader with non-zero Ld, otherwise Ld of the
first model.

### 3.4 `psy_status` bits ✅

`psy_status` is a 16-bit field at `unit + 0xBE`; **bit = token − 19**. The writer masks `0x3FFF`.

| Bit | Flag | Effect found in the code |
|---|---|---|
| 0 | `CantBreak` | rout and fear-flight events are ignored (op 0xC8 `FUN_100204d0`; Dwarfs shout "We fight to the death!"); fear does not apply |
| 1 | `Frenzy` | Attacks doubled in close combat; excluded from fear and terror |
| 2 | `CauseFear` | enemies that lose a combat against it break without a test; engaging it needs a Leadership test |
| 3 | `CauseTerror` | units without `Frenzy`/`PsyImmune` cannot charge it and **flee without a roll** when charged by it or touching it (section 7.3) |
| 4 | `FearToGobs` | ✅ **unused**: no read of this bit exists in `GAMEF.DLL` (every access to the field enumerated), and scripts cannot read the field |
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

`WHSHR.EXE`'s copy of the table also names `AlwaysPursue` (bit 11) but ends at `CantRally`; the scripts
never use `AlwaysPursue`.

## 4. Runtime structures, random numbers, battle clock

- **Units**: array of `0x3F0`-byte records at `*0x100E2EF4`; a record's index is at `+0x3E`
  (16 bit). Other fields used here: flags `+0xB4` (32 bit; `0x2000` = broken, see "Can't engage a
  broken unit"), leader model pointer `+0xB0`, engaged enemy unit `+0x220`, attack direction
  `+0x22E`, battle grid pointer `+0x324`, model index list `+0x2D0`, charge counter `+0x338`,
  combat round counter `+0x33C`, unit worth `+0x33E` (`size × s_pntval × 12 artillery / 8 wizard / 4 monster / 1`, read by AI target scoring), magic items `+0x3C0` (count) / `+0x3C4` (list).
- **Models**: `0x8C`-byte records at `*0x100E2F0C`: flags `+0`, pointer to the stat block `+0x40`,
  opponent model `+0x48`, opponent unit `+0x4C`, wounds taken `+0x54` (a model dies when
  wounds ≥ W), attack counter `+0x58`.
- **Random numbers** ✅ `FUN_10060b99` is MSVC `rand()`: `seed = seed * 214013 + 2531011`,
  result `(seed >> 16) & 0x7FFF`. A D6 is always `rand() % 6 + 1`.
- **Battle clock** ✅ (`FUN_10003a30` reset, `FUN_10003a60` tick): **19 ticks** form a *segment* (the counter
  starts at 18 and is decremented before the `< 0` test);
  the segment counter `0x100E476E` runs 10, 9, … 1, then the turn counter `0x100E476C` increases
  and the segment returns to 10.

### Real time and movement ✅

- **Timer**: the battle window runs `SetTimer(100 ms)`; each `WM_TIMER` re-arms it, runs **exactly one tick**
  (`FUN_100291e0` → `BattleTick`) and renders. Frame-driven, no catch-up: at most 10 ticks per second, so a
  segment (19 ticks) lasts 1.9 s and a turn (10 segments) 19 s. Pause is bit `0x80` of the game state; there is
  no game speed option.
- **Speed stat**: Movement is used only to derive `s_rlmv` at unit set-up (`FUN_10003aa0`):
  `trunc(4.8 × M' + I) / 2`, or `trunc(2.4 × M') + 4` for neutral units, with `M'` = the mount's M when mounted.
  (So the mount's M does count here, contrary to the close combat mount record, which only uses WS, S, A and the
  charge S.)
- **Unit speed**: `s_rlmv × k / 16` world units per tick, recomputed every tick, with k = 1.8 moving freely,
  1.0 closing on a target, 2.5 charging or in melee, 1.5 fleeing (and pursuing: step `min(24 × s_rlmv,
  10 × distance)` per segment, k at `0x100E61F8` = 1.5). An M4 I3 infantry unit covers about 9.8" per turn moving
  freely and 5.4" closing in. Pursuers and fugitives use the same factor, so only a higher `s_rlmv` closes the gap.
  **Terrain has no effect on speed.**
- **Turning**: per tick `s_rlmv × (144 − s²)` scaled by state, with `s = frontage + ranks − min / 2`; units pivot on a
  front corner (a real wheel), halt to turn beyond 45° and wheel at half speed beyond 7.7°. (For `s ≥ 12` the
  formula stops working; no deployed unit reaches it.)
- **Charge**: reaches at most `12 × (s_rlmv + 1)` units, re-aiming halfway (about 6" for infantry, 9.5" for
  horsemen).
- **Boundaries**: region masks `0x20` = `BATTLEEDGE`, `0x90` = `INVSOLID|SOLID`, `0xB0` = `INVSOLID|BATTLEEDGE|SOLID`
  (the `bnd_*` flags of the script keyword table).
- **Flight check**: the "flee counter" of `FleeingUnitUpdate` is not a distance; it only schedules the battle-edge
  check about every half footprint radius.
- **Animation bytecode**: objects also run per-object animation scripts stored in `GAMEF.DLL` `.data`
  (`0x100E70F0–0x100E86A8`, located through the tables at `0x100E8B88` and `0x100E86A8`): negative words are frame
  delays, other words opcodes of a 59-entry table at `0x100E7000` (fire event 21, model death 23, `ApplyImpact` 52,
  sounds, effects, removal; 🟡 names).

### Routes, collisions and visibility ✅

Full detail: `extracted/agent_reports/L_ai_pathfinding.md` (local). The key visibility constants were
spot-checked in the code before merging.

- **Waypoints**: `ExecuteGoto` (`FUN_1002a950`) replaces and shift-click (`FUN_1002a6c0`) appends to a queue of
  **at most 8 waypoints** (`FUN_1002ab70`); a point within 17 units of the queue head or tail is ignored. Moving
  onto the unit's own position just halts and re-forms.
- **Routing is not pathfinding**: a unit walks straight towards its current waypoint. When `ObjectsOnPath`
  (`FUN_100276a0`) finds the first blocking map object on the line (scenery, spell area objects **or another
  unit's footprint**, tested with the same `asin(radius / d)` geometry as missile obstruction), `GotoTarget`
  (`FUN_1002b030`) dry-runs a detour to the left and to the right (`FUN_1002b390`: cost `4 × turn + distance` per
  leg, +12 000 for leaving the playable area, abandoned beyond a full turn or cost 5 999) and keeps the cheaper
  side; if both exceed 11 999 the unit gives up ("can't find the way to target"). Each tick `PlanStep`
  (`FUN_1002b980`) deflects the heading around the current obstruction again. `Nav*`, `SOLID`, `INVSOLID` and
  `BATTLEEDGE` boundaries are polygon-membership obstacles only, never a graph, so units can get stuck against
  concave shapes; an engine may use real pathfinding without visible change on the open maps.
- **Region masks**: `InRegion`/`NotInRegion`/`RegionCrossings` (`FUN_10015c60`, `FUN_10015bd0`, `FUN_10015d20`)
  scan the boundary records (40 bytes at `*0x100E26DC`) whose flags are active and match the mask; `INVSOLID`
  inverts containment (the outside of `BattleEdge` is solid); crossings snap to the boundary so movers slide
  along it. `0xB0` routes and fanatic jumps, `0x100` deployment, `0x200` `SightEdge` (spotting only), `8`
  `ViewEdge` and `0x40` `CameraEdge` (camera only), `0x20` leaving the table, `0x90` the rout probe.
- **Collisions** (`ResolveUnitCollisions`, `FUN_100289d0`, once per tick): every overlapping pair of footprints
  or objects is resolved. **Friendly units and solid scenery push apart** by half the overlap each
  (`PushApart`, `FUN_10028610`: circle-circle resolution; a charging unit hitting something within its 45°
  front arc ends the charge, event 0x09). **Enemy contact** engages (fear test, charge, redirect, rout: section
  5.5 and 7.3); contact with a routing unit makes automatic contact attacks (section 7.7). An `INVSOLID` object
  straight ahead sends event 0x27. There is no sub-tick sweep, so fast units can briefly overlap.
- **Visibility** (`IsVisible`, `FUN_10016d70`), shared by hidden-unit spotting and "is my target visible" for
  AI shooting and casting: the target must lie within the looker's **view cone** (half-width 71/512 turn =
  **±50°**, doubled to ±100° while in melee), one of three sample rays towards the target (spread by its
  footprint) must be free of scenery (`ScanObjectsOnLine`, the missile obstruction test), and the line must not
  cross a **`SightEdge`** boundary (if a battle has none, "No Sight Boundary" and visible). **No range limit and
  no terrain height** anywhere in spotting, shooting or casting line of sight: hills never hide units.
- **Hidden units** (`SpotHiddenUnits`, `FUN_10016ca0`, run by threat detection): each hidden enemy that passes
  `IsVisible` is revealed **permanently** (flag `0x80000` cleared), with event 0x1C to it and 0x1D to the spotter.
- **AI decisions**: `PickBestTarget` (`FUN_10022280`) scans all units for the highest `UnitScore`; `DetectThreat`
  (`FUN_10021f80`) spots hidden units, then keeps or re-picks the threat unless braced. `RunAway` (206) is one
  reactive flee step per behaviour period (±67.5° away from visible enemies), `CircleAroundTarget` (228) one
  offset move of +11.25°. **There is no army-level AI**: coordination comes only from the "assist a friend who
  attacks" rule (event 0x13, `AIQuery` 9/10) and from mission scripts that assign "attack the n-th nearest
  enemy" targets (opcodes 176–191) to individual units. AI armies are not repositioned at battle start (their
  `.BTS` positions are used).

### Unit behaviour scripts and events ✅

**Most consequences of morale are decided by bytecode, not C code.** Every live unit runs a behaviour
script each tick (`RunUnitScript`, `FUN_1001cae0`, called from the battle tick `FUN_10029260`).

- **Code**: 32-bit words; a word with bit 15 set is opcode `word & 0x7FFF`, dispatched through the
  **232-entry handler table at `0x100F53A0`**; `0x0ABC` is a label, `0x80E8` ends a script. Operand counts
  follow from each handler's returned PC. Handlers of the table have no direct callers, which is why
  several rule functions looked orphaned (`FUN_1001f990` is opcode 0x5B, `FUN_100204d0` opcode 0xC8).
- **Per-unit state**: current script `+0x242`, PC `+0x244`, return stack `+0x24E`/`+0x250`, interrupt
  script `+0x214`, pending switch `+0x246`, current event `+0x238`, event queue head `+0x216`, count `+0x20E`.
- **Script source**: `FUN_1001caa0(id)` calls `DLLGetScriptPointer` of the mission DLL named by
  `loadScript`. In every `SCRIPT/BFxxx.DLL` that export is a table lookup: ids from 0 → the mission's unit
  scripts (3–37 per DLL; `set:script=N` values are always below the DLL's count), ids **100–170 → a shared
  library, byte-identical in all 45 DLLs**. `DLLReturnInstCount` returns 33000 = `0x80E8` (the end-of-script
  word): a format check, not an instance count. `set:script=PLAYER_SCRIPT` is
  library script 100. So the "mission logic" DLLs are **data** (bytecode), not x86 code to disassemble.
- **Control opcodes** (names assigned; full catalogue of 0x00–0x73 in `extracted/agent_reports/G_opcodes_0_115.md`):
  push PC (0x06), loop jumps `Loop`/`LoopIfTrue`/`LoopIfFalse` (0x07–0x09), goto script (0x0C), switch script at
  end of tick (0x0D–0x10, 0x0F high priority), gosub/return (0x11/0x13), end of an event handler: return to the
  interrupted script or apply a pending switch (0x14), yield (0x17), skip if true (0x19), test/set/clear unit flags `+0xB4` (0x22–0x26) and `+0xB8`
  (0x29–0x2B), condition flags (0x2E–0x30), `GetEvent` (0x68), `ConsumeEvent` (0x69), `CaseEvent N`
  (0x6A), `Break` (0x6B, jumps to the next label, operand = label word `0x1ABC`), `If/IfNot/Else/EndIf` (0x6C–0x6F), queue event to self (0x5E/0x5F), send to own side / **enemy side**
  (0x62/0x63), `Query N` (0x16, cases of the AI routine `FUN_100214b0`), `React N` (0xC2).
- **More from the catalogue** ✅: after `ExecuteOrder` applies a player order, the interpreter drops the target and
  restarts the unit's script at its restart point (op 0x1E). `SetThreatRange` (0x31) sets `+0x218`, used by the AI
  threat score (`UnitScore`, `FUN_10022330`): `worth × (range − d) / round(range / 4)` with the octagonal distance
  `d = max(|dx|, |dy|) + min(|dx|, |dy|) / 2`, 0 for friends, broken, `CantMelee` or hidden units and beyond the
  range; ×4 if the enemy targets this unit, or ×32 instead if it is also charging (see "Routes, collisions and
  visibility"). Node opcodes move to a node (0x1F), face it (0x20), teleport to it (0x49), place and re-form there
  (0x4A) and scatter models around nodes (0x48). 0x4C, 0x5C, 0x5D are instant 90°/180° turns, 0x4B a wheel.
  Events 0x14/0x15 are reports from a unit to its linked parent (op 0x65), 0x33 comes from op 0x66 and 0x37 from
  op 0x63. A wizard busy casting ignores being charged and "enemy routed" events. Operand sizes of 0x1F, 0x87, 0x95
  and 0x9D are one word longer than first derived.
- **AI and mission opcodes** (catalogue of 0x74–0xE7 and all 28 `AIQuery` cases in
  `extracted/agent_reports/H_opcodes_116_231.md`) ✅: `IfObjective n` (222) tests whether the `.BTS` defines
  objective letter n; library scripts 100, 101 and 152 branch on objective G (behaviour 12, units become allied,
  side `0x40`). The standard mission AI is behaviour 15 `TrackThreat` (290 mission uses): keep the best threat and
  attack it when its score exceeds the unit's worth. Opcodes 176–191 attack the n-th nearest unit with side/class
  filters; 206 is an AI "run away"; 208 turns an artillery crew into Infantry when its machine is lost. Some
  handlers are duplicates (181 = 180, 185 = 184, 136 = 175) or unused (137, 171, 173, 174).
- **Events**: 14-byte records `[recipient, code, source, parameter, x, y, link]` in a 128-record pool at
  `0x100E1EB0`, queued per unit by `SendEvent` (`FUN_100211f0`), `BroadcastEvent` (`FUN_10021290`) and
  `SendEventToSide` (`FUN_10021230`). There is no C handler table: every unit script has the frame
  `GetEvent; CaseEvent a … Break; CaseEvent b … Break; Gosub 153…156 (library defaults, all ending in 152);
  ConsumeEvent; loop`. Player units run library script 100, which installs an event handler by class
  (101 default, 102 Artillery, 103 Wizards, 104 Archers → 154/155/156); mission scripts gosub 153.
- **`React N`** (`FUN_10020fc0`): per race (`s_race & 7`) and code, a battle message (table `0x100F5770`),
  a leader portrait expression (`0x100F5CB0`) and a speech sample (`0x100F5A10`): 1 "Engage!", 2 "CHARGE!"
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
| 0x1C / 0x1D | `FUN_10016ca0` | hidden unit spotted / was spotted | ops 0x40 / 0x41 |
| 0x1E | shooting order | missions only | |
| 0x27 | collision pass | enemy footprint straight ahead | missions only |
| 0x2B / 0x2C / 0x2D | order 0x17, casting animation end | cast a spell / launch it / use an item | casting scripts 132, 133, 142 (section 8.8) |
| 0x31 / 0x32 | Madness | became mad / madness ended | scripts 149 / 168 |
| 0x34 | movement | destination reached | |
| 0x05 | `AIQuery` case 5 | message to the unit's current target (`+0x220`) | mission scripts |
| 0x14 / 0x15 | op 0x65 | report from a unit to its linked parent | mission scripts |
| 0x33 | `AIQuery` cases 16/20, op 0x66 | threat within reach (fanatic parent units) | mission scripts |
| 0x36 | `AIQuery` case 12 | 🟡 | mission scripts |
| 0x37 | op 0x63 | event sent to the enemy side | mission scripts |
| 0x38 | `AIQuery` cases 19/20 | battle state 4 → 5 (broadcast) | |
| 0x35 | – | unused (no script handles it) | |
| 0x30 | pairing, withdraw | alone in a combat grid / disengaged | leave grid, re-form |

Mission scripts mostly add cases for 0x03, 0x04, 0x05, 0x13, 0x14, 0x15 and 0x1B.

**Tool** ✅: `whshr/behaviour.py` reads the script tables of every DLL (the lookup of `DLLGetScriptPointer`
is emulated, so each DLL's ranges are decoded, not assumed) and disassembles with a shipped table of 232
instruction lengths and the catalogue names; `python3 -m whshr check` ("behaviour scripts") verifies all 45
DLLs: 3787 scripts (592 mission scripts, 1 to 37 per DLL), 125 519 words with no stray word, the library
identical everywhere, `DLLReturnInstCount` = 33000, 224 of 232 instruction lengths confirmed from the handler
bytes (the other 8 transfer control or scan forward), and every `set:script` value of 53 battles present in
its DLL. `python3 -m whshr scripts <installation> [DLL] [ids…]` prints summaries and listings. Library
scripts 152–156 have **no end word**: each ends in `ReturnGosub` followed directly by another script.
Interpreter details: a word is read as signed 16 bits; `0x80E8` is never executed (only a sentinel for forward
scans); any other non-opcode word is a debug print and does not advance the PC.

**Library scripts 100–170** ✅ (full table with per-event detail: `extracted/agent_reports/I_behaviour_tool.md`).
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

Reports and the agent's scratch listings are kept locally in `extracted/agent_reports/` (not in git).

### Missions and objectives ✅ / 🟡

Full detail, per-battle table and BF001 walk-through: `extracted/agent_reports/J_missions.md` (local; survey tool
`J/survey.py`). Checked before merging: the objective table and letter indexing, the battles defining G, and the
`SPRITES.PBX` explanation (re-run with `J/sprites_check.py`).

- **Mission scripts use only the catalogued opcodes**: all 45 DLLs were disassembled; patrols, ambushes,
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
- **Deployment**: `DeployTroops:` battles hide all player units; placement is a UI action, not bytecode. `NS_END`
  nodes match the player unit count (BF001: 3). 🟡 Units with holding positions outside the field (BF001's crossbowmen
  at x = 1814) are placed by the player during deployment; 🟡 the `ns_startpos` chain probably outlines the
  deployment area for the UI. AI armies start at their `.BTS` positions.
- **BF001**: patrol and attack scripts for Hiln's Guard and Sleaquit, Otto Hiln with a short threat range and a
  scripted flight towards node 5 (🟡 exact trigger chain), the delayed Clanrat wave, and standard interrupt
  handlers; nothing beyond the general interpreter and library scripts is needed to run it.
- **Objective table** ✅ `0x100F4D48`: 40-byte records indexed `L − 'A' + 1` (record 0 is empty; opcode 222
  `IfObjective` uses the same index), with `+0x00` defined (set by the `.BTS` parser `FUN_1000d820`, which also links
  the defined letters), `+0x08` flags, `+0x0C` in-battle caption (`GMTXT 33000 + L − 'A'`), `+0x10` evaluator function,
  `+0x14` met, `+0x18/+0x1C` the numbers `a, b`. Flags: `0x1` ends the battle when met, `0x2` evaluated every tick,
  `0x4` no caption in the end-of-battle list, `0x8` evaluated in the separate pass, `0x10` still evaluated after the
  battle is decided, `0x20` custom debrief line. **Battle-ending letters**: A (Eliminate the enemy), F (BF009), H
  (BF015, BF017), N (Get past the Dragon, BF014) and Z (the silent loss condition).
- **Evaluation** ✅: battle set-up calls every defined evaluator with mode 1; `FUN_1001ae30` runs each tick (from
  `BattleTick`) and tests the not-yet-met objectives with flag `0x2` in mode 2; the first met objective with flag
  `0x1` decides the battle (`DAT_100e25b8 = 1`), opens the win or loss dialog (`FUN_1001adc0`) and plays the end
  stinger. `FUN_1001af30` evaluates flag-`0x8` objectives in mode 3 from a less frequent poll; at the end
  `FUN_1001ad40` lists captions, or calls the evaluator in mode 4 for a custom debrief line. ⬜ The 26 evaluator
  functions (what each letter counts) were not read; the known `a, b` snapshots suggest "compare current counts with
  the stored numbers".
- **Objective G "Inside the gates!"** ✅ (R60): only BF015 and BF017 (siege battles) define it. Player units then run
  threat behaviour 12; entering map node 14 in battle state 4 moves the battle to state 5 (event 0x38); a unit that
  reaches the interior node 99 in state 4 gets event 0x36, and library script 152 sets the allied side, unit flag
  `0x100` and switches it to script 170, which teleports it to node 24 and removes it from the battle: the unit has
  got inside the walls. The gate itself (a rolling stock unit) is excluded.
- **Mission-only events**: 0x05, 0x14/0x15, 0x33, 0x37 and 0x38 are used only by the fanatic battles and the two
  siege battles; **event 0x35 is never handled by any script** (unused).

### Player orders and the command panel ✅

The battle window (`FUN_10043820`) maps panel buttons (records at `0x100F7D60`, icons = frames of
`ICONS.BOP`; there are no tooltip strings) to a global order code (`DAT_100DC210`, cleared every tick).
`ExecuteOrder` (`FUN_1001d470`), run from the behaviour script, applies it to **player units** only: to every
selected unit (unit flag bit 25), otherwise to the unit's own pending order (`+0x200`); orders 0x17 and 0x1B act
only on the focused unit (`FUN_100275f0`). In deployment (`DAT_100DC21C == 1`) only placing and waypoints run.
The panel shows a button set by class and state (idle, attack sub-panel, broken/pursuing, melee, charging: none,
deployment).

| Order | Button (icon) | Effect |
|---|---|---|
| 1 / 2 | Move (boots) + click / shift-click | go to point (`FUN_1002a950`) / add waypoint; queued while busy |
| 3 | Attack (crossed swords) + click | event 0x04: approach and attack a unit (not `CantMelee`) or building |
| 0x0B–0x0E | face point, turn left/right 90°, about face | facing ∓0x80 / +0x100 (increasing facing = clockwise) |
| 0x0F / 0x10 | ranks up / down | re-form with ±1 rank |
| 0x13 | Withdraw (banner flag, melee) | disengages only when fighting rolling stock or furniture (classes 7, 9) with no other enemy unit fighting its models (`FUN_10024710`); **against living enemies the unit routs** (a voluntary rout) |
| 0x14 | Rally (open hand, broken or pursuing) | toggles the rally / pursuit-restraint attempts (section 7.4) |
| 0x15 | Charge (war horn) | event 0x06 → script 106 `ChargeForward` (op 0x4F): a charge **straight ahead**, reach 12 × `s_rlmv`, not inside `0xB0` regions |
| 0x16 | Fire (crossed bow) + click; Ctrl = Gyrocopter bomb | `OrderFire` (section 8.1) |
| 0x17 | Magic (chaos star) + spell + click | cast (focused unit) |
| 0x19 | Halt (open hand) | halt and re-form, "Hold!" |
| 0x1A | **Independent** (head in profile; idle and deployment panels) | toggles unit flag bit 27 |
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
- **Charging** flag `0x80` is set by `StartCharge` and by `FUN_1002d9b0` when a charging or pursuing unit runs into
  a different enemy (the pursuit becomes a charge, events 0x1A/0x07). **Pursuing** flag `0x8000` only by
  `StartPursuit`.
- Behaviour bytecode sets only unit flags `0x100`, `0x4000000` and `0x20000000`; `+0xB8` bit 0 anchors war machines,
  bit 3 ("hold fire") is tested but never set; `+0xB4 & 0x80000` marks hidden units.

## 5. Close combat

### 5.1 Order of blows ✅

`FUN_10003db0` runs a unit's close combat only **in the segment equal to its Initiative**
(`unit I == segment`). Segments count down from 10, so higher Initiative strikes first. In the first
combat round it also triggers hatred and frenzy shouts (events 8 and 9). Monsters (class 6) go
through `FUN_10003e70`, everything else through `FUN_10003fb0`.

**Initiative above 10** ✅: only two spells write I: "Ere We Go!" sets **I := 20** (and T +1) and "The Curse of
Anraheir" halves I, both restored when the effect ends. A unit with I 20 never matches a segment, so **Orcs and
Goblins under "Ere We Go!" make no close combat attacks** while it lasts (almost certainly a bug; meant as "strike
first"). The **Dragon** (I 20) never runs its own attacks either: it only deals return blows from the attack pool
filled when a battle grid is created around it (at most A = 7 per engagement), plus its breath weapon.

### 5.2 Attack of one model (`FUN_10003fb0`) ✅

For every live model engaged with an enemy model, an attack profile is assembled:

- `A` = model A, doubled by `Frenzy`;
- `WS` = model WS, **+1 when ganging up**: the first model to attack a free enemy model becomes its
  opponent and gets no bonus; every further model attacking that enemy model gets +1 WS (not against
  monsters). Up to 4 attackers fit around an enemy model (section 5.7);
- `S` = attack strength (`FUN_100047f0`): `weapon_table[s_weap] + S`, +1 while the unit's charge
  counter is non-zero, +1 while the "fight harder" flag (unit flag bit 30, order 0x1B, see "Player orders") is set. Weapon table at
  `0x100E8CA8`: class 0 → +0, 3 → +0, **4 → +2, 10 → +1**; classes 1, 2, 9 hold `0x83/0x84`
  (bit 7 = fixed strength 3/4, unused by the scripts);
- magic items of the attacking leader and the defending leader are applied (`FUN_10013ac0`,
  section 5.6);
- hatred: if the unit hates the target's race and the combat round counter is below 2, failed
  attacks are rolled once more.

Then `FUN_10004830` resolves the attacks:

```
repeat A times:
    if D6 >= TO_HIT[attacker WS][defender WS]:
        repeat wounds_per_hit times:          # 1, more with some items
            if D6 >= TO_WOUND[S][defender T] and armour_save_fails(defender armour, S):
                kills += 1
    if hatred re-roll allowed and this attack scored nothing: roll this attack once more
```

Automatic hits (`ResolveAutoHits`, `FUN_100053b0`: to-wound and saves, no to-hit, no hatred re-roll)
apply in three cases: (1) the war machine model of an artillery or rolling stock unit (the leader
model, flag `0x40000` set at unit set-up; the crew fight normally); (2) targets of class RollingStock or
Furniture: all attacks go to the unit's first model and the wounds do **not** count for the combat
result; (3) 🟡 contact attacks of charging or pursuing units (`FUN_10005170`, reach 12 units, 18 cavalry,
24 monsters) against models that are not in the timed "turning" state set when a unit routs.

**Return blows** ✅ (`FUN_100045c0`) exist only for monsters: `model+0x58` is a per-round attack pool
(A, 2A with frenzy) that only monster models get. Each enemy model that attacks a monster immediately
draws one blow back from the pool (one hit/wound/save roll against the attacker's modified WS, hatred
re-roll allowed, credited to the monster's side); the monster spends what is left in its own Initiative
segment, then the pool refills. A mounted attacker can draw two blows (after the rider and after the
mount).

**To-hit table** at `0x100E8C28`, 11 × 11, `[attacker WS][defender WS]` = lowest D6 that hits. For
WS 1–10 it is exactly the WFB 4th edition chart: 3+ if the attacker's WS is higher, 5+ if the
defender's WS is more than double, otherwise 4+. The extra WS 0 row/column give 4/5 (attacker 0)
and 3, or 2 for attacker WS ≥ 7 (defender 0).

**To-wound table** at `0x100E8CB8`, `[S][T]`: exactly the WFB 4th edition chart for S, T 1–10
(S ≥ T+2: 2+, T+1: 3+, equal: 4+, T−1: 5+, T−2 and T−3: 6+, less: 7 = impossible); T 0 is wounded
on 1+ by S ≥ 8.

### 5.3 Armour saves (`FUN_10004770`) ✅

```
armour_save_fails(code, S):
    if code == 6:                    # regeneration
        return D6 < 4               # (and never fails when the damage source sets a flag, see open questions)
    return D6 < SAVE[code] + SAVE_MODIFIER[S]
```

`SAVE_MODIFIER` at `0x100E8D38`: `max(0, S − 3)` (S4 −1 … S10 −7), the WFB 4th edition modifier.

`SAVE` at `0x100E8D48`, by armour code:

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

### 5.4 Mounts ✅

For a rider whose armour code has bit 3 set (codes 8–13), the mount makes its own attacks from the
mount record `0x100E8D58 + 32 × s_mount`: name pointer, a flag byte, **charge strength** at `+5`,
profile M WS BS S T W I A Ld at `+0xC`. The mount uses its A, WS and S, or the charge strength while
the charge counter is non-zero.

| `s_mount` | Name | Charge S | M WS BS S T W I A Ld |
|---|---|---|---|
| 1 | Warhorse | 5 | 7 3 0 3 3 1 3 1 5 |
| 2 | War Boar | 6 | 6 4 0 3 4 1 3 1 3 |
| 3 | Giant Wolf | 3 | 8 4 0 3 3 1 3 1 3 |
| 4 | Cave Squig | 0 | 5 4 0 5 3 1 5 2 2 |

Only charge strength, WS, S and A of the mount record are ever read; its M, T, W, I, Ld and the byte `+4` (255 on
the War Boar) are unused. A mounted model has a single wound counter: **the mount cannot be wounded or killed
separately** and does not change movement.

### 5.5 Charge ✅

`EngageCharging` (`FUN_10008050`) stores **`charge counter = floor(1.5 × frontage)`** (frontage `+0x7E`,
constant 1.5 at `0x100E6040`) on the unit that joins the battle grid; `Engage` (`FUN_10007ee0`, re-engaging
the current opponent) stores 0. The contact handler `FUN_1002d700` treats the moving unit with flags
`0x8080` (charge or pursuit order; event 8 "charge") as the charger; otherwise `FUN_10007eb0` gives the
counter to whichever unit is not yet on a grid, so a unit that runs into an ongoing combat also gets
one. The defender's counter is untouched and nothing resets it when the combat ends.

While non-zero: +1 S and the mount's charge strength. It is decremented once per attacking model
(after the rider's and the mount's attacks) and per return blow, so **the first `1.5 × frontage`
models to fight** get the bonus (16 models in 4 ranks: 6; 10 knights in 2 ranks: 7). 🟡 A charging
monster keeps +1 S on its own attacks, because `MeleeRoundMonster` never decrements the counter
(probable bug). The lance (`s_weponame` 17) has no special rule; the Reiksguard use weapon class 3.

### 5.6 Magic item effects (`FUN_10013ac0`, `FUN_10013ce0`) ✅

Items are identified by their `GMTXT` name string ids (`31000 + n`) in the spell/item table at
`0x100F6E48`. Most apply only when the unit's leader model attacks or is attacked.

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

### 5.7 Engagement: battle grid and pairing ✅

**Battle grid record** (pool of `0x14C`-byte records allocated at battle start, `FUN_10015a30`):
unit count `+0`, flags `+2` (bit 0 in use, bit 1 result resolved), facing `+4`, sound handles, side
vectors, owner unit `+0x20`, **tallies `+0x24` (side without `s_side` bit 7) and `+0x25` (with)**,
creation segment `+0x26`, turn of the last reset `+0x28`, and a **17 × 17 cell map** `+0x2A` (one cell =
12 world units = one model; bits 0–2 cell type, bits 5–7 side).

**Creation and joining** (`GetOrCreateBattleGrid`, `FUN_100085a0`): when unit A engages B, A joins B's
grid if B already has one (so several units share one combat and one pair of tallies); otherwise a
new record is taken, B's models are written into the cells around the centre (one cell per model,
or a full rectangle for war machines, rolling stock and monsters) and B becomes the owner. If the pool
is exhausted the engagement fails (event 0x0C). Engaging clears the pairing of A's models, sets A's
round counter to 0, stores the charge counter, attack direction and side, and sends event 0x0A to both.

**Pairing** runs every tick (`EngageTroops`, `FUN_10005750`):
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
🟡 In practice models in combat walk `s_rlmv / 8` units per tick, so the wrap-around completes within 2–4
segments, well inside the first combat turn; the limit is the number of free cells next to enemy models (about
`2 × (width + depth)`), so most models of both units fight by the first result.

**Leaving** (`LeaveBattleGrid`, `FUN_10008290`; on destruction, rout, or when no enemy remains, event
0x19): models are unpaired, ownership passes to another unit on the grid or the record is freed; a
lone remaining unit with `s_side & 0xE0 == 0x20` leaves as well. Tallies are not reset on join or leave.

Model flags: `0x1` alive, `0x2` dying, `0x4` timed turning/pause, `0x1000` at rest, `0x4000` has an
opponent (`+0x48` model, `+0x4C` unit), `0x8000` reserve, `0x10000` in hand-to-hand, `0x20000` on the
grid, `0x40000` war machine. Unit flags: `0x200` in melee, `0x400` owner pairing mode, `0x800` has a
grid, `0x1000` grid owner, `0x2000` broken.

## 6. Combat resolution and break tests

### 6.1 Result (`FUN_10004470`) ✅

After a unit's models have attacked, the kills it caused and the kills from return blows are added to
the two tallies of the shared battle grid (`+0x24`/`+0x25`, which one depends on the side bit).
The unit's own score also gets, when its enemy is a unit of classes 1–6:

- **rank bonus**: if frontage `s_wdth > 3`, `size / width − 1` (full ranks behind the first),
  **with no upper limit**;
- **direction bonus** from the attack direction code (`FUN_10008b00`, the angle of the attacker
  relative to the defender's facing): code 1 (behind) **+2**, codes 2–3 (sides) **+1**, 0 (front) 0.

`AttackDirection` returns eight codes (two halves each of front arc 0/4, rear arc 1/5, flanks 2/6 and 3/7);
`AddCombatResult` masks bit 2 away, so both halves of an arc get the same bonus.

There is **no standard, battle standard or general** ✅: `banner:` only selects the banner sprite, `s_banner` is never read, and Leadership comes only from the unit's own leader.

### 6.2 Break test (`FUN_10003ba0`) ✅

`BreakTest` is called for every unit in melee at each segment boundary but acts only in the grid's
creation segment, i.e. **once per turn**, and increments the unit's round counter `+0x33C`. The result
is evaluated when `turn − grid+0x28 == 2` and the round counter is at least 2; the first blow after a
result resets the tallies and sets `+0x28 = turn − 1`. Consequences: the **first result comes two turns
after contact** (rank and direction bonuses, added at every strike, count twice in that window); later
results come every 1 or 2 turns depending on the Initiatives involved; a unit that joins later cannot
be broken in its first turn. Every unit of the losing side (`difference = own tally − enemy tally < 0`,
not already broken) is tested separately against the same difference:

```
if unit hates the enemy:   difference = Ld − 10         # the test becomes a roll of 10 or less
if enemy causes fear and the unit has none of CantBreak/Frenzy/PsyImmune and no Dread Banner:
    break without a test
elif LeadershipTest(unit, modifier = −difference) fails:
    break  (event 0x0C)
```

## 7. Leadership tests and psychology

### 7.1 The Leadership test (`FUN_10003cd0`) ✅

```
pass  <=>  modifier + (rand() % 11 + 2) <= effective Ld     # modifier − 1 (= +1 Ld) while the "fight harder" flag is set
```

The roll is **uniform over 2–12**, not 2D6. For Ld 7 the chance to pass is 6/11 = 54.5% (2D6:
58.3%); Ld 9: 72.7% (83.3%); Ld 5: 36.4% (27.8%). Low Leadership is better and high Leadership
worse than on the tabletop. Callers: break test, panic, fear, rally, pursuit, artillery crews,
and a scripted test `FUN_1001f990`.

### 7.2 Panic (`FUN_10008ca0` → `FUN_10017410`) ✅

When a model is killed (any cause), with `q = orgsize >> 2` (so only units of 4 or more models):
if `floor(size_before / q) != floor(size_after / q)`, the unit tests with
`modifier = 1 − floor(size_after / q)`. For a 16-model unit that is −2 at the first loss below
16, −1 below 12, 0 below 8 and +1 below 4; each quarter of the original strength lost costs one test,
and the tests get harder. A failed test routs the unit (event 0x0C). The debug output prints
"at −1 while pursuing" for pursuing units but uses the same modifier.

The area damage routine (missiles and spells, section 8.4) can additionally order a panic test at
modifier 0 when a unit is at or below a quarter of its original size.

Only **deaths** trigger panic ✅: `RemoveModel(unit, slot, killed)` runs the check only when `killed != 0`,
which the death paths pass (the model death callback at `0x10001DD0` and the unit destruction callback at
`0x10003040`, both reached through animation callbacks). Removal without death (`killed = 0`: units that
leave the table, `FUN_10027070`; destroyed buildings, `FUN_10003210`) adds to `s_routed` instead, so
`s_routed` counts **models that fled off the battlefield**. A killed model flagged `0x40` also sends event 0x17.

### 7.3 Fear and terror ✅

`MayEngage(unit, enemy)` (`FUN_10009120`):
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
3. **Contact while moving** (`FUN_100289d0`, unless bit 14 is set): failure → event 0x0D, flight.

So a failed fear test means flight (when charged or on contact) or a refused charge, whatever the numbers,
and a terror-causer makes every non-immune unit that it charges or touches flee without a roll. There is no
terror test at a distance.

### 7.4 Rally (`FUN_10029780`, `FUN_10003d60`) ✅

A fleeing unit makes a rally attempt only when **all** of these hold: its scheduled segment has come
(`+0x33A`: the first attempt one full turn after the rout, then every 3 segments), its rally-attempt flag
`+0xBC` bit 11 is on, and no enemy is within 160 world units. The flag is set by the player's order 0x14
("Rally!"/"stop pursuing" toggle, allowed while broken or pursuing) or automatically at the rout for units
with unit flag bit 27 (🟡 a per-unit "independent action" toggle, order 0x1A); otherwise the unit keeps
fleeing.

The unit cannot rally with `CantRally`, or when `casualties ≥ 3 × size` (at or below a quarter of its
original strength). Otherwise it takes a Leadership test with modifier +2 if `casualties > size`, +1 if
`3 × casualties > size`, else 0. Success sends event 0x10: "Re-group!" (Dwarfs "Rally!"), and op 0x5A clears
the broken/charging/pursuing flags and re-forms the ranks.

### 7.5 Pursuit ✅

When a unit routs, every enemy unit receives event 0x0F, but only the routed unit's opponents react (op
0x53): a unit on a combat grid first looks for another opponent in the same fight and switches to it if
there is one; otherwise it pursues. A unit not on a grid pursues only if it was charging. Player artillery,
wizards and archers never pursue.

The pursuit script (164) shouts "Destroy them!", may attack a more attractive target instead (if its
value exceeds the unit's worth `+0x33E`), and starts the pursuit (`StartPursuit`, `FUN_1002a0e0`: state
`0x200`, flag `0x8000`). `PursuingUnitUpdate` (`FUN_10029a30`) and `PursuitStep` (`FUN_1002a150`) end it
with event 0x10 when:
- the target is gone, rallied or died;
- the chase budget runs out (not with `AlwaysPursue`): `min(2 × distance, 120)` at first, then changed at
  each update by `(previous distance − distance) − 4`;
- the next step would leave the battle area;
- the restraint test at the scheduled segment is passed, which is only rolled while the rally-attempt flag
  is on (player order 0x14). **AI units never test**; they chase until one of the other conditions ends it.

### 7.6 Other effects

- `CantDie` ✅: `FUN_10001770` removes a model when wounds ≥ W only if the unit lacks `CantDie`.
- `MagicResistent` ✅: in the area damage routine, a wound from a magical source is ignored on
  an even `rand()`.
- Hatred and frenzy: section 5.2; fear in break tests: section 6.2.

### 7.7 Flight and catching fleeing units ✅ / 🟡

Event 0x0C (rout) and 0x0D (fear flight) are handled by the library scripts: already broken or `CantBreak`
units ignore them; the player's own **artillery ignores rout events altogether** (it flees from fear only
while its leader model lives). Otherwise the unit shouts "Retreat!" or "Flee the abomination!" and switches to
the rout script, which starts the flight **directly away from its opponent** (bearing + 180°), or along its
facing without one.

`StartRout` (`FUN_1002a320`): movement state `0x100`, leaves the combat grid, **loses `Frenzy`**, gets the
broken flag `0x2000`, sends event 0x0F to every enemy unit and schedules the rally attempts.
`FleeingUnitUpdate` moves the unit; `RoutRoute` (`FUN_1002a4b0`) probes one step ahead and deflects the
heading by ±0x20 (of 512) around obstacles. Once outside the battle area the unit sends event 0x0E and is
then removed alive (every model counts in `s_routed`). 🟡 Speeds: the flee counter uses `s_rlmv`, the
distance per tick comes from the generic mover `FUN_1002c4c0` (not traced).

🟡 **Catching.** Pursuers never engage fleeing units in close combat: the collision pass skips routing
footprints. Instead, the fleeing unit's own collision pass calls `ContactAttacks` (`FUN_10005170`) for every
enemy unit it touches: once per segment per attacker, each attacker model makes up to A attempts against
random victim models within twice its reach (12, cavalry 18, monsters 24), with automatic hits (fleeing models
lack the "braced" model flag 4), charge bonus included. As the pursuer is steered onto the fugitive, this
repeats every segment of contact until the fugitive is destroyed, rallies or leaves the table. There is no
instant "caught = destroyed" rule.

### 7.8 Charge into the flank or rear ✅

`FUN_1001f990` is opcode 0x5B, run by the default event handler on **event 0x08**, which `EngageCharging`
sends to the charged unit when the charger is charging or pursuing. With the attack direction code of the
charger, the table at `0x100F5750` = `[0, 1, 1, 1, 0, 1, 0, 0]` selects a **Leadership test at modifier 0 for
a charge into the rear arc (codes 1, 5) or the rear half of either flank (2, 3)**; failure sends event 0x0C
(rout). Front arc and the front halves of the flanks (0, 4, 6, 7) need no test. Unlike WFB 4th edition
(panic when charged in flank or rear while already engaged), the test applies to any such charge.

## 8. Shooting, artillery and magic

Conventions: angles in 1/512 of a turn (0x40 = 45°), distances in world units (24 = 1"), ticks of the
battle clock (19 per segment, 100 ms each). Full per-point detail: `extracted/agent_reports/C_shooting.md` (local).

### 8.1 Who shoots, orders and volleys ✅

- Only classes 3 (Archers) and 4 (Artillery) use `FireMissile`, with at most 32 projectiles in flight
  (`FUN_10024ae0`; 64 for spell effects). The missile code is `S_BalWeap` of the unit (Archers), of the
  leader's block (Artillery) or the leader's if non-zero (others).
- Shooting is run by the **library behaviour scripts** (107–124, handlers 154/156, identical in all mission
  DLLs). A player fire order (`OrderFire`, `FUN_10025d80`) **halts a moving unit** and queues an event:
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
- `ReadyToFire` (`FUN_10024800`) order: hold-fire bit `+0xB8 & 8` → reload (`GMTXT 2003`) → machine present
  (`2015` "Artillery destroyed!") → at least 2 crew (`2016`). `GMTXT 2000` "Missiles fired!" is never used.

### 8.2 Reload time (`FUN_10018410`) ✅

```
base = (10 − min(I, 10)) × 18                       # the unit's own block: I (+0x88), weapon code (+0x90)
k    = bow 7, crossbow 4, Wood Elf bow 10, short bow 8, longbow 6, else 0
if k: reduction = 9k (k < 3) | 6k + 6 (3 ≤ k < 6) | (2k − 10) × 9 / 5 + 36 (k ≥ 6)
      → bow 43, crossbow 30, Wood Elf bow 54, short bow 46, longbow 39
      base = max(base − reduction, 18)
Artillery with fewer than 4 models: base += (4 − size) × 36
```

The last shot is stamped at every volley (`+0x380` segment, `+0x382` tick, `+0x384` turn). Examples: Orc
Arrer Boyz (I2) 101 ticks, crossbows I3 96, Goblin short bows I2 98, Wood Elves I6 18 (about once per segment),
artillery crews I3 126 and I2 144 (artillery reads the crew block, whose weapon code is 0). An I2 bow unit
fires about twice per turn; WFB fires every turn.

### 8.3 Aim, scatter, flight ✅

Each projectile (`LaunchProjectile`, `FUN_1001a360`, 27 arguments; records of `0x2DC` bytes at
`0x100DC334`) flies to the target point displaced on each axis by

```
offset = (rand() % (11 − min(BS, 10))) × (random sign) × spread × distance / max_range
```

`spread` = 8 for bows and crossbows, `8 × d` for artillery (*d* = the first artillery die, 8.5), **+8 if a
scenery object lies on the line of fire** (`NextObjectOnLine`, `FUN_100183b0`: buildings, walls, trees). An object blocks when
`min(Δ, 512 − Δ) < trunc(asin(radius / d) × 256 / π)`, with `d = trunc(distance)` below the range and Δ the difference
between the line's direction and the object's bearing `trunc(256 − 256 × atan2(dx, dy) / π)` (`ObjectOnLine`,
`FUN_10016fc0`); a firer inside an object's circle is never blocked by it.
Horizontal motion is linear over a fixed flight time; height follows an arc (bows apex ≈ 180 units,
crossbows ≈ 45, cannon low, mortar and rock lobber high). Holding Ctrl only changes the projectile graphic.

**In flight** the projectile is tested against map objects every tick (`StepProjectile`, `FUN_1001a700`);
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

### 8.4 Impact (`ApplyImpact`, `FUN_10017490`) ✅

Arguments: source unit, excluded object (the firer, only in flight), x, y, height, radius, wound die, S, S
against buildings, saves, magical, flags, messages. For every map object at distance *d* from the impact:

- **Units** (height test passed, flying units only between their base and top):
  - `d < footprint radius` (`GMTXT 2004` "Direct hit on the %s!"): radius 0 → **one random model**;
    radius ≠ 0 → **every model**. Each: `TO_WOUND[S][T]`, armour save if allowed (the leader with its armour
    items), `MagicResistent` 50% if magical, then `rand() % wound_die + 1` wounds.
  - `d < footprint + radius` (blast margin, `GMTXT 2005` "The %s have been hit!"):
    `n = (footprint + radius − d) × size / (footprint + radius)`, at least 1, random models (with repetition)
    at **S/2 for exactly 1 wound**.
  - Afterwards flag `0x80` → panic test if `size ≤ orgsize / 4`; flag `0x40` → rout.
- **Buildings and furniture**: the owning unit's first model takes `TO_WOUND[S2][T]` and the wound die
  (direct) or S2/2 and 1 wound (margin), no saves.
- A terminal impact does not exclude the firer, so a shot that scatters back can hit its own unit.
- The damage type (`flags & 0xFF3F`) is stored as the cause of death and passed to the save routine
  (missiles 2, fire effects 1).

### 8.5 Artillery misfire (`FUN_10024f70`) ✅

Before every artillery shot: D6; on 1–5 nothing happens and the result becomes the die *d* used for the
scatter. On a **6** a second D6 is rolled: on **1** the machine explodes: every crewman takes a wound on an
even `rand()`, and if any crew survive they take a Leadership test or rout (`GMTXT 2018` "The %s has misfired
and been destroyed."). On 2–6 the shot is lost (`GMTXT 2019` "The %s has misfired."). The warpfire thrower
never misfires.

### 8.6 Special weapons ✅

These reuse the **spell effect engine** (`LaunchEffect`, `FUN_1000f950`, innate casting) and are magical
(`MagicResistent` ignores half the hits).

| Code / routine | Targeting | Shots | Per shot |
|---|---|---|---|
| 13 Doomwheel warp lightning (behaviour 0x1A, `DoomwheelBolt` `FUN_100147c0`) | reload on the leader block | 3 bolts: ahead, right, left; distance `D6 × D6 × D6 × 12`; nearest unit **of either side** near that point | fails on a 6 (`GMTXT 2021`); S5, D6 wounds, no save |
| 14 Dragon breath (`FUN_10014920`) | target in the front 180° | D6+3 flames around the target | S8, 1 wound, no save, **every unit hit routs** (flags `0x41`) |
| 15 warpfire thrower (`FUN_10014b00`) | needs crew | D6 flames around the target | S4, 1 wound, no save; no misfire |
| 16 (Wyvern shaman) | – | – | not a weapon: marks a monster-class unit as a **spellcaster** (`CanCastSpells`, `FUN_1002ebd0`) |
| 17 Gyrocopter steam gun (`FUN_10014bd0`, Infantry-class files) | range 144 (6") | 1, passes through units | S4, 1 wound, no save, hits one model of each unit it crosses |
| 17 Gyrocopter bomb (`FUN_10025a80`, Archers-class files) | Ctrl + command, only while flying (`GMTXT 2020`) | 1, dropped | radius 72, S4, 1 wound, saves; artillery misfire roll |
| Pestilent Breath (behaviour 0x1B, `FUN_10014c30`) | scripted units | 1 near the unit | S3, 1 wound, no save, passes through |

The doom diver is an ordinary artillery shot (`0x4C` is only its graphic; no steering found). On landing
`FUN_10001300` places a dead-diver corpse decal (the ordinary 32-entry corpse ring, random facing): no game effect.

### 8.7 Night Goblin Fanatics ✅ / 🟡

Behaviour 0x12 (`FanaticUpdate`, `FUN_100049d0`). While hidden (object flag `0x400`) the fanatic waits until
no model of its parent unit (`+0x224`) is within reach, then is out. Each update afterwards:
- every model of an Infantry, Cavalry, Archers, Wizard or Monster unit within **12 units (18 against
  cavalry, 24 against monsters)** takes an **S5 wound roll: 1 wound, no save**; the fanatic survives;
- artillery: the crew as above plus D6 rolls against the machine, then the fanatic **dies**; rolling stock:
  D6 rolls, dies; buildings and scenery: dies; other special units: wounded automatically, dies;
- some terrain areas remove or kill it.
The release step (opcodes 216/217) clears `CantMelee` and runs the same collision with armour saves.
Fanatics are hidden template units tagged `0xABC0`; the parent unit's script spawns three copies with opcode 0xD3
(lateral offsets 0, −20, +20, parent link set). Each copy loops `Query 18` every 5 ticks (→ `FanaticUpdate`);
opcode 0xD8 is a 2D6 × 8 unit jump. `+0x210` (behaviour code) is set only by opcode 0x33. 🟡 The event of the
parent script that triggers the spawn was not traced.
WFB: D6 S5 hits per unit touched, 2D6" moves, dies on a double; here damage scales with the models within ½".

### 8.8 Winds of magic and casting ✅

Full detail: `extracted/agent_reports/F_magic.md` (local).

- **Power**: one pool per side, 0–8 (player `battle+0x32BA0+0x528`, enemy `+0x52C`; allies use the player's).
  No per-wizard power, no wizard levels. `FUN_1003c9f0` replaces each pool every **50 s of unpaused real time**
  by `Wind(current)` (`FUN_10014cb0`): an empty pool becomes 1–7, otherwise `current − 4 … current + 3`, at least
  1. (Count and Fixed = 8 modes are debug options behind Ctrl/Shift clicks on the magic panel.) Each pool **starts at `rand() % 8 + 1` (1–8)**, set by the battle
  window's create handler `FUN_1003c440`.
- **Spell/item table** `0x100F6E48`, 24-byte records `{GMTXT id, effect code, name, kind (1 spell, 2 item),
  cost, flags}`; costs: 1 Dispel Magic, Azure Blades, Lightning, Fireball, Flying Bower, Mork Save Uz,
  Skitterleap, Pestilent Breath; 2 Wind Blast, Sapphire Arch, Piercing Bolts, Burning Head, Hunting Spear,
  Flock of Doom, Gaze of Mork, Ere We Go, Fists of Gork, Warp Lightning, Madness; 3 Storm of Shemtek,
  Conflagration of Doom, Flamestorm, Tangling Thorn, Curse of Anraheir, Da Krunch. A unit lists up to 5 spells
  (`+0x390`) and 5 items (`+0x3C0`).
- **Casting**: the spell button is enabled when the cost fits the pool; the **cost is paid on the click**.
  Azure Blades, Dispel Magic and Fists of Gork need no target. The target click gives order 0x17 → event 0x2B to
  the wizard (a busy wizard: `GMTXT 2014` "…is preparing to cast a spell", order dropped) → casting animation →
  event 0x2C → op 147 `CastPending` → `LaunchEffect`. Storm of Shemtek and Flying Bower keep the wizard busy until
  they end. Ctrl+click on an active spell cancels the caster's effects of that code (no refund).
  **In close combat** a wizard casts at once without the animation if the target is in range and inside the arc; an
  engaged wizard cannot turn, so a target outside the arc cancels the spell (op 0xAA). Outside combat the wizard
  first turns ("Turning Wizard to cast spell.", script 141: instant quarter/half turn beyond 45°, then a wheel);
  the arc is not re-tested after the turn.
- **Checks** (`LaunchEffect`, `FUN_1000f950`): fewer than 64 active effects; the caster can cast (class Wizard,
  or a leader with `S_BalWeap` 16, e.g. the Orc shaman on a Wyvern); target point within `EffectRange` of the
  unit centre and within **±50° of facing**; unit-target spells need a unit under the point. **No line of
  sight, no casting roll, no miscast, no reload**; on failure `GMTXT 2021` "…attempted to cast … but failed" and
  the power is lost. The 2D6 inside `LaunchEffect` is the bolt count of Storm of Shemtek.
- 🟡 Holding **Shift** at launch switches several spells to alternative projectiles (Flying Bower then does S3
  hits); it reads the physical keyboard, so it affects AI casts too (probably a developer toggle).

### 8.9 Spells ✅

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

### 8.10 Dispel and anti-magic ✅

`DispelAura` (`FUN_1002ef50`): each tick of its schedule, every other dispellable effect within **80 units** of
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

### 8.11 Magic items in battle ✅

- **Banner of Wrath** (effect `0x105`) casts a Lightning and **Grudgebringer** (`0x10A`) a Fireball: no power, no
  wizard needed, once per wind (flag `0x20`, re-armed when the power pool is refreshed). The Dragon's breath uses
  the Grudgebringer effect innately (section 8.6).
- **Potion of Strength**: single use, +3 S for the rest of the battle (section 5.6).
- Passive items (banners, armour, swords, talismans) have disabled buttons. **The AI never activates items.**
- In the scripts, Banner of Wrath, the Talisman and Arcane Warding appear only in the `RLTEST*.MRC` test armies;
  Arcane Protection appears nowhere.

### 8.12 AI casting ✅

Library scripts (opcodes 147–175 named in the report): a computer wizard picks the nearest enemy and the first
spell of its list that it can afford and whose rule passes (`AIChooseSpell`, `FUN_10013f40`), turns to face and
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

## 10. Function index

| Address | Name given here | Role |
|---|---|---|
| `0x1000EFA0` | `LookupInstruction` | instruction keyword lookup (`0x100E92A0`) |
| `0x10009190` | `WriteUnit` | editor unit writer, `S_RACE` comment |
| `0x1000F160` | `WriteSetStats` | writes one `setstats` line from the byte block |
| `0x10009480` | `WritePsyStatus` | writes `psy_status` bits |
| `0x10060B99` | `rand` | MSVC LCG |
| `0x10003A30`, `0x10003A60` | `ResetBattleClock`, `TickBattleClock` | segments and turns |
| `0x10003DB0` | `UnitMeleeSegment` | close combat in the unit's Initiative segment |
| `0x10003FB0`, `0x10003E70` | `MeleeRoundTroops`, `MeleeRoundMonster` | build attack profiles, resolve |
| `0x10004830` | `ResolveAttacks` | hit, wound, save; hatred re-roll |
| `0x100053B0` | `ResolveAutoHits` | as above without to-hit |
| `0x100045C0` | `ReturnBlow` | monster blow back from its attack pool |
| `0x100047F0` | `AttackStrength` | weapon class, charge, bonus flag |
| `0x10004770` | `ArmourSaveFails` | save table, regeneration |
| `0x10013AC0`, `0x10013CE0` | `ItemCombatModifiers`, `ItemArmour` | magic items |
| `0x10013D50`, `0x10013D90` | `HasDreadBanner` | item 31002 |
| `0x10004470` | `AddCombatResult` | kills, rank and direction bonuses into the battle grid |
| `0x10008B00` | `AttackDirection` | front / rear / flank codes |
| `0x10008050`, `0x10007EE0` | `EngageCharging`, `Engage` | battle grid, charge counter |
| `0x10003BA0` | `BreakTest` | |
| `0x10003CD0`, `0x10003D20` | `LeadershipTest`, `EffectiveLeadership` | |
| `0x100090C0` | `HatesEnemy` | hatred flags vs race |
| `0x10009030`, `0x10009060`, `0x10009120` | `TerrorBlocks`, `FearApplies`, `MayEngage` | |
| `0x10008CA0` | `RemoveModel` | casualties, kills, experience, panic trigger |
| `0x10017410`, `0x100173D0` | `PanicTest`, `Rout` | rout = event 0x0C |
| `0x10029780`, `0x10003D60` | `FleeingUnitUpdate`, `RallyTest` | |
| `0x10029A30` | `PursuingUnitUpdate` | pursuit restraint test (only on order 0x14) |
| `0x100204D0` | `OpRoutAllowed` | op 0xC8: not broken and not `CantBreak` |
| `0x10001770` | `UpdateModels` | wounds ≥ W, `CantDie` |
| `0x10024AE0`, `0x100248B0` | `CanShoot`, `MissileWeaponCode` | |
| `0x10018410` | `ReloadReady` | reload timer |
| `0x10024990`, `0x100248F0` | `MissileRange`, `MissileBlastRadius` | per weapon code |
| `0x10025130`, `0x10025A80` | `FireMissile`, `DropBomb` | |
| `0x1001A360` | `LaunchProjectile` | BS scatter |
| `0x10017490` | `ApplyImpact` | area damage |
| `0x10024F70` | `ArtilleryMisfire` | |
| `0x100049D0`, `0x10004CE0`, `0x10004F30`, `0x10005000` | `FanaticUpdate`, `FanaticCollide`, `FanaticHitMachine`, `FanaticHitModels` | |
| `0x10005170` | `ContactAttacks` | charging/pursuing unit attacks models within reach (automatic hits on turned models) |
| `0x1001D470` | `ExecuteOrder` | order 0x1B sets unit flag bit 30 |
| `0x1002D700`, `0x10007EB0` | `UnitContactHandler`, `EngageNewcomer` | who charges whom |
| `0x100085A0`, `0x100086D0`, `0x10008860` | `GetOrCreateBattleGrid`, `CreateGridTroops`, `CreateGridBlock` | battle grid, monster attack pools |
| `0x10008A00`, `0x10008A50` | `ResetGrid`, `AttachGridOwner` | |
| `0x10008290`, `0x10008350`, `0x10008550` | `LeaveBattleGrid`, `UnpairModels`, `FindOtherUnitOnGrid` | |
| `0x10015A30`, `0x10015A80` | `AllocBattleGrids`, `FreeBattleGrids` | |
| `0x10005750`, `0x100059C0`, `0x100060C0` | `EngageTroops`, `PairOwnerModels`, `PairJoiningModels` | per-tick pairing |
| `0x10006DB0`, `0x10007BB0`, `0x10007260` | `PlaceModelsNextToEnemy`, `PlaceModelAdjacent`, `QueueReserveModels` | |
| `0x10006170`, `0x10006700` | `LineUpAgainstBlock`, `FillSideLine` | against machines, rolling stock, monsters |
| `0x10005800`, `0x10007510` | `MonsterEngage`, `MonsterMoveToTarget` | |
| `0x10005450`, `0x10005640` | `ModelArrivedInCombat`, `OpponentRetarget` | |
| `0x1002BEA0`, `0x1002D2A0`, `0x1002BBD0` | `MoveModels`, `ModelMoveStep`, `UnitMovementUpdate` | |
| `0x10029260` | `BattleTick` | per-segment unit update, break tests |
| `0x10003AA0`, `0x10003B50` | `InitUnitDerived`, `UnitWorth` | `s_rlmv`, `+0x33E` |
| `0x100272B0`, `0x1002BBB0`, `0x1002C9E0` | `InitFormationKind`, `FormationKind`, `ComputeFormationSize` | war machine flag, frontage/ranks |
| `0x1002A320`, `0x1002A420` | `RoutUnit`, `StartTurnPause` | |
| `0x10005380` | `ContactReach` | 12 / 18 cavalry / 24 monster |
| `0x1001CAE0`, `0x1001CAA0` | `RunUnitScript`, `GetScriptPointer` | behaviour bytecode interpreter; mission DLL export |
| `0x100F53A0` | `SCRIPT_OPCODES` | 232 opcode handlers |
| `0x100211F0`, `0x10021290`, `0x10021230`, `0x100212E0` | `SendEvent`, `BroadcastEvent`, `SendEventToSide`, `QueueEvent` | event pool `0x100E1EB0` |
| `0x100214B0` | `AIQuery` | cases of script op 0x16 |
| `0x10020FC0` | `React` | message, portrait, speech (tables `0x100F5770`, `0x100F5CB0`, `0x100F5A10`) |
| `0x1001F990` | `OpFlankRearTest` | op 0x5B, table `0x100F5750` |
| `0x1001E6F0`, `0x1001EF10`, `0x1001E1E0` | `OpFearWhenCharged`, `OpChargeTarget`, `OpReactToThreat` | ops 0x42, 0x4E, 0x39 |
| `0x1001F0C0`, `0x1001F560`, `0x1001F8F0` | `OpFleeFromOpponent`, `OpEnemyRouted`, `OpRally` | ops 0x50, 0x53, 0x5A |
| `0x1002A0E0`, `0x1002A150` | `StartPursuit`, `PursuitStep` | |
| `0x1002A4B0` | `RoutRoute` | flight around obstacles |
| `0x100289D0` | `ResolveUnitCollisions` | fear on contact, contact attacks, engage |
| `0x10027070`, `0x10008EB0` | `RemoveUnitAlive`, `RemoveUnit` | |
| `0x10001DD0`, `0x10003040`, `0x10003210` | `ModelDeathCallback`, `DestroyUnitCallback`, `DestroyObject` | death paths into `RemoveModel` |
| `0x10021F80`, `0x10022280`, `0x10022450` | `DetectThreat`, `PickBestTarget`, `NearestEnemyWithin` | |
| `0x1002B160`, `0x10024680` | `HaltAndReform`, `Withdraw` | |
| `0x100412A0` | `UiToggleIndependent` | unit flag bit 27 |
| `0x10043820`, `0x10041100` | `BattleWindowProc`, `CmdFightHarder` | panel buttons → order codes |
| `0x100275F0`, `0x1003F920` | `FocusedUnit`, `PanelMode` | |
| `0x1002D9B0` | `RedirectCharge` | charging/pursuing unit hits another enemy |
| `0x10024710` | `CanWithdraw` | not read (R48) |
| `0x1002E2D0` | `EndEffect` | restores I/T after "Ere We Go!", Curse of Anraheir |
| `0x100291E0` | `BattleTimerTick` | one tick per 100 ms `WM_TIMER` |
| `0x1003C9F0`, `0x10014CB0` | `WindsOfMagic`, `Wind` | power pools every 50 s |
| `0x10016FC0`, `0x100170C0`, `0x10017170` | `ObjectOnLine`, `ScanObjectsOnLine`, `ScanObjectsOnLine2` | asin half-width test |
| `0x10001300`, `0x10001410` | `SpawnCorpse`, `UpdateCorpses` | 32-entry corpse ring |
| `0x1003C440` | `BattleWindowCreate` | magic pools start at `rand() % 8 + 1` |
| `0x1002A950`, `0x1002A6C0`, `0x1002AB70` | `ExecuteGoto`, `AddWaypoint`, `SetOrQueuePoint` | 8-waypoint queue |
| `0x1002B030`, `0x1002B390`, `0x1002B980` | `GotoTarget`, `TrySteerSide`, `PlanStep` | reactive route controller |
| `0x100276A0` | `ObjectsOnPath` | first obstruction on the line (scenery or footprints) |
| `0x10028610`, `0x10028890` | `PushApart`, `EngageOnContact` | collision response |
| `0x10015C60`, `0x10015BD0`, `0x10015D20` | `InRegion`, `NotInRegion`, `RegionCrossings` | boundary masks |
| `0x10016D70`, `0x10016DB0`, `0x10016F70`, `0x10015E20` | `IsVisible`, `ArcAndObstructionTest`, `InFacingArc`, `SightEdgeClear` | visibility |
| `0x10016CA0` | `SpotHiddenUnits` | events 0x1C/0x1D |
| `0x10022330`, `0x10022280` | `UnitScore`, `PickBestTarget` | exact threat score |
| `0x100243C0`, `0x10018820` | `RunAway`, `CircleAroundTargetStep` | |
| `0x10040930`, `0x10011920`, `0x100238D0` | `SpellButtonClick`, `OrderCast`, `CastPending` | cost, order 0x17, op 147 |
| `0x1000F870`, `0x1002EC10`, `0x1002EBD0` | `EffectTargetCheck`, `EffectRange`, `CanCastSpells` | range and ±50° arc |
| `0x10011BE0`, `0x1002FBF0`, `0x1002E2D0` | `EffectTick`, `EffectPhase`, `EndEffect` | per-tick spell updates |
| `0x1002EF50` | `DispelAura` | |
| `0x10013F40` | `AIChooseSpell` | |
| `0x100186C0`, `0x10017D10` | `MadnessSwitchSide`, `Skitterleap` | |
| `0x10003AA0` | `InitUnitDerived` | `s_rlmv = trunc(4.8 × M + I) / 2` |
| `0x1002C4C0` | `MoveUnit` | speed `s_rlmv × k / 16` per tick |
| `0x0041A242` (WHSHR.EXE) | dead battle dispatcher | no callers: the EXE's battle code copy is unused |
| `0x1001A700`, `0x10026040` | `StepProjectile`, `UpdateAllMissiles` | flight, in-flight hits |
| `0x100247A0`, `0x1002E5E0`, `0x1002E6A0` | `MissileImpactThunk`, `EffectImpact`, `FireballImpact` | callbacks into `ApplyImpact` |
| `0x10024800`, `0x100185B0` | `ReadyToFire`, `StampReload` | |
| `0x1001A230`, `0x1001A290`, `0x1001A320` | `InRangeMsg`, `InArcAndRangeMsg`, `InArc` | script ops 112–115 |
| `0x100183B0`, `0x10016FC0` | `NextObjectOnLine`, `ObjectOnLine` | obstruction |
| `0x10026670`, `0x10026140` | `TargetValid`, `FindNearestTarget` | |
| `0x10025D80`, `0x10025CA0` | `OrderFire`, `FireAt90PercentRange` | |
| `0x10002220` | `AnimFireEvent` | every 4th model fires |
| `0x1000F950`, `0x1002EC10`, `0x1002EBD0` | `LaunchEffect`, `EffectRange`, `CanCastSpells` | spell effect engine |
| `0x10014920`, `0x10014B00`, `0x10014BD0`, `0x10014C30`, `0x100147C0` | `DragonBreath`, `Warpfire`, `SteamGun`, `PestilentBreath`, `DoomwheelBolt` | |
| `0x10017300`, `0x10017200`, `0x10022230` | `GroundHeight`, `Distance`, `BearingTo` | |

## 11. Open points

Everything that is not established, as a register for the next sessions. **Priority** is for an
engine that reproduces the battles: *high* = changes outcomes noticeably, *medium* = visible in some
situations, *low* = cosmetic or rare. "How to resolve" names the next concrete step; all of them are
static analysis unless marked Wine.

### 11.1 Close combat

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
| R35 | **Grid edge cases** | ✅ `s_side & 0xE0 == 0x20` = fake units for placed buildings/furniture (Madness keeps it); formation flag 0x80 = furniture footprint bit; ⬜ placements outside 17 × 17 not re-examined. | Low value. | low |
| R36 | **Models fighting in practice** | 🟡 wrap-around completes within 2–4 segments; limited by free cells (section 5.7). | Simulate or observe under Wine. | low |

### 11.2 Combat resolution and morale

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R13 | **Battle grid lifecycle** | ✅ resolved: record layout, joining, resolution timing, leaving (sections 5.7, 6.2); `+0x33E` is unit worth, not a counter. | — | done |
| R14 | **After a unit breaks** | ✅ resolved (sections 7.5, 7.7); 🟡 catching by contact attacks and the movement speeds remain (R39). | — | done |
| R15 | **Events** | ✅ mechanism and most codes resolved (section 4, behaviour scripts); 🟡 0x05, 0x09, 0x14, 0x15, 0x17, 0x1C/0x1D, 0x31–0x38 (R41). | — | done |
| R16 | **Standards, general** | ✅ none exist (section 6.1). | — | done |
| R17 | **Flank/rear test** | ✅ resolved: charge into rear arc or rear half of a flank → Leadership test (section 7.8). | — | done |
| R18 | **Panic triggers** | ✅ resolved: only deaths (`killed = 1` via the death callbacks); `s_routed` = models fled off the table (section 7.2). | — | done |
| R19 | **Fear/terror callers** | ✅ resolved: charged → flee, charging → refused, contact → flee; terror without a roll (section 7.3). | — | done |
| R20 | **Rally and pursuit schedule** | ✅ resolved: first attempt a turn later, then every 3 segments; attempt flag from order 0x14 or bit 27 (sections 7.4, 7.5). | — | done |
| R21 | **Unused/unclear psychology** | ✅ resolved: `FearToGobs` unused; `CantMelee` is a target property (section 3.4). | — | done |
| R38 | **Opcode catalogue** | ✅ all 232 opcodes catalogued (228 established, 4 hypotheses) and all 28 `AIQuery` cases (`extracted/agent_reports/G_opcodes_0_115.md`, `H_opcodes_116_231.md`, JSON tables); summarised in section 4. The `whshr` disassembler is R51. | — | done |
| R39 | **Flight and pursuit speeds** | ✅ k 1.5 for both, pursuit step `min(24 × s_rlmv, 10 × distance)` (section 4). | — | done |
| R40 | **Unit flag bit 27** | ✅ "independent" toggle and its effects (Player orders); 🟡 name. | — | done |
| R41 | **Remaining event codes** | ✅ senders of 0x05, 0x14/0x15, 0x33, 0x36, 0x37, 0x38 found (section 4); 🟡 meaning of 0x36, 0x39. | — | done |
| R42 | **Initial scripts** | ✅ `set:script=N` is the mission script id (3–37 per DLL), `PLAYER_SCRIPT` = 100; `DLLReturnInstCount` = 33000 format check. | — | done |

### 11.3 Shooting and artillery

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R22 | **Missile constants** | ✅ resolved: radius, wound die, S, S vs buildings, saves, flags traced end to end (section 8.3). `FUN_10002ee0` is an animation-stream opcode, not the missile path (R43). | — | done |
| R23 | **Range, line of sight, reload** | ✅ resolved: arc ± 45°, strict range, reload formula, scenery obstruction +8 scatter, crossbows blocked by friends (sections 8.1–8.3). | — | done |
| R24 | **Real time of a tick** | ✅ 100 ms timer, one tick per message; 19 ticks per segment (section 4, Real time and movement). | — | done |
| R25 | **Shooting restrictions** | ✅ resolved: ⌈N/4⌉ projectiles, halt before firing, no modifiers, shooting into combat allowed (section 8.1); 🟡 some flags (R44). | — | done |
| R26 | **Special missile weapons** | ✅ resolved (section 8.6). | — | done |
| R27 | **Fanatics** | ✅ hits and death conditions (section 8.7); 🟡 movement and behaviour assignment (R45). | — | done |
| R43 | **Animation instruction stream** | ✅ per-object animation bytecode in `GAMEF.DLL` `.data`, 59 opcodes (section 4); 🟡 opcode names. | Name the opcodes when animations are implemented. | low |
| R44 | **Shooting flags** | ✅ `+0xB8` bit 0 anchors machines, bit 3 never set, `+0xB4 0x80000` hidden, `0x100` set by library script 152 on event 0x36 when objective index 7 exists (units leaving the battle, R60). | — | done |
| R45 | **Fanatic release and movement** | ✅ spawned as three copies by opcode 0xD3, `Query 18` loop, jump opcode 0xD8 (section 8.7); 🟡 spawn trigger event. | Trace the parent script event. | low |
| R46 | **Obstruction geometry** | ✅ `asin(radius / d)` angular half-width (section 8.3). | — | done |
| R47 | **Doom diver remains** | ✅ corpse decal, no game effect (section 8.6). | — | done |
| R48 | **Withdraw condition** | ✅ only against rolling stock/furniture with no other enemy; otherwise the unit routs (Player orders). | — | done |
| R49 | **Order-blocking flag** | ✅ `0x100000` = braced against a charge (Player orders). | — | done |
| R51 | **Script tools** | ✅ `whshr/behaviour.py`, `python3 -m whshr scripts`, check group "behaviour scripts" (section 4). | — | done |

### 11.4 Structures and scope

| # | Open point | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R28 | **Remaining stat bytes** | ✅ `s_wdth`/`s_rkmd`/`s_spar` = frontage, ranks, models in last rank (recomputed); `s_rlmv` recomputed from a float at set-up; `s_cmdr`, `s_armname`, `s_banner` always 0; `s_rnks` is the script's rank count used by the formation code; second stat block at `+0x95` read for leaders/artillery. | Trace the float for `s_rlmv` in `FUN_10003aa0`; where `+0x95` is copied from the leader. | low |
| R29 | **Movement** | ✅ `s_rlmv` from M and I, speed factors, turning, charge reach, no terrain effect (section 4). | — | done |
| R30 | **Magic** | ✅ resolved: power pools, casting, every spell, dispel, AI (sections 8.8–8.12). | — | done |
| R31 | **`WHSHR.EXE` copy** | ✅ dead code: its battle dispatcher has no callers; only the army writer is used by the front end. | — | done |

| # | Open point (magic) | What is known | How to resolve | Priority |
|---|---|---|---|---|
| R52 | **Never-ending spells** | Flamestorm and Curse of Anraheir have no timeout in the code read. | Wine: cast and wait several turns. | medium |
| R53 | **AI area spells** | ✅ confirmed inverted: the AI never casts area spells at a unit target (section 8.12). | — | done |
| R54 | **Starting power and Storm of Shemtek count** | ✅ pools start at 1–8; Storm fires 2D6+1 bolts (sections 8.8, 8.9). | — | done |
| R55 | **Shift variants and Ctrl repeat casts** | Physical-keyboard tests at launch; Ctrl mouse flag repeats casts. | Decide whether an engine keeps them (developer toggles?). | low |
| R56 | **Casting in close combat, turning to cast** | ✅ casts at once in combat if in arc, else cancelled; turn step outside combat (section 8.8). | — | done |
| R57 | **Area objects** | ✅ temporary solid scenery (`os_active|os_solid`): push units back, stop charges, bend routes, block spotting, obstruct missiles. | — | done |
| R58 | **Spells against regenerators** | ✅ no-save spells wound them; save + type 0 spells allow regeneration; Burning Head never wounds them (section 5.3). | — | done |
| R59 | **Duplicate opcode names** | 0x3A, 0x88 and 0xAF share the name `TakeEventTarget` (same helper, different arguments). | Give distinct names in `whshr/behaviour.py`. | low |
| R60 | **Objective index 7 and leaving the battle** | ✅ letter G "Inside the gates!" in the siege battles BF015/BF017 (Missions and objectives). | — | done |
| R61 | **Visibility details** | Unit flag bit 3 (`0x8`) also doubles the view cone together with melee (`0x208`); the `0x90` region test at `0x10026337` in shooting/effect code was not traced; mode 1 of the "attack the n-th nearest" opcodes uses a signed-axis metric (🟡). | Read the callers. | low |
| R62 | **AI deployment** | ✅ none: AI armies start at their `.BTS` positions (Missions and objectives). | — | done |
| R63 | **Objective evaluators** | The 26 per-letter evaluator functions behind the objective table (`+0x10`) were not read; which counts they compare, and what S "Capture Hiln" and Y test in BF001. | Read the functions from the table (`0x1001b270`…`0x1001bd50`). | medium |
| R64 | **Win/loss dialog codes** | `FUN_1001adc0` opens dialog 9 or 0xF depending on `DAT_100f516c`/`DAT_100f4e60`; which is which. | Read the two globals' writers. | low |
| R65 | **Deployment nodes** | 🟡 the `ns_startpos` chain outlines the deployment area for the placement UI; units held outside the field are placed by the player. | Read the deployment UI code. | low |

### 11.5 Hypotheses in this report to confirm

Section 3.2: `s_rnks`, `s_rlmv`, `s_pntval`, `s_armname`. Section 3.4: `CantMelee`. Sections 5.2/5.5:
return blow, charge duration. Section 7.7: catching fleeing units, speeds.
Section 8.7: fanatic release and movement. Section 10: fanatic and contact attack functions.

### 11.6 Candidates for a Wine session

Only worth the effort if static analysis stalls, as the game exits randomly under Wine:

- R5: confirm that Orcs under "Ere We Go!" and the Dragon (`BF014`) make no close combat attacks of their own.
- R11: casualties inflicted on a leader with `s_armr=5` (e.g. Commander Bernhardt).
- R36: how many models of a deep unit end up fighting after a few turns of combat.
- R52: does a Flamestorm or a Curse of Anraheir ever end on its own?
- Whether a Banner of Arcane Warding has any visible effect.
- Section 7.1: a flat 2–12 roll cannot be distinguished from 2D6 in single tests; not worth testing.

### 11.7 Status of the analysis and next steps

- **Done**: the first pass (sections 3–8) and two batches of three research agents each (September 2026):
  A close combat engagement, B morale after breaking and the behaviour VM, C shooting, D flags and orders,
  E time and movement, F magic. Their full reports, with more detail than this file, are kept locally in
  `extracted/agent_reports/A_close_combat.md` … `F_magic.md` (git-ignored, derived from the binaries), together
  with scratch tools and the Ghidra decompilation in `extracted/decompiled/`.
- **Planned batches**: the full plan with agent briefs is in `notes/research_plan.md`: batch 3 (below), batch 4
  (J missions and objectives, K campaign progression and saves, L AI, pathfinding and visibility) and an
  optional batch 5 (M animation bytecode, events → sound/music/palette).
- **Batch 4 done**: L (AI, pathfinding, visibility) and J (missions and objectives) merged into section 4; K
  (campaign progression and save games) in `notes/campaign.md`.
- **Batch 3 done** (G, H, I; September 2026): all 232 opcodes and 28 `AIQuery` cases catalogued, the `whshr`
  disassembler with its check, the library script table, R41, R44, R46–R49, R51, R53, R54, R56–R58.
- **Open decisions for an engine**: whether to reproduce apparent original bugs (R11 armour rating 5, R33
  charging monsters keeping +1 S, "Ere We Go!" stopping close combat attacks in section 5.1).
- **Wine candidates**: section 11.6.

