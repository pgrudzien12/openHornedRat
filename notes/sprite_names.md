# Resource names -> sprite / scenery files (ROADMAP 1.4)

Report of the name-mapping task. Scripts: `scripts/spritemap_build.py`, `scripts/spritemap_verify.py`.
Output (game data, not for distribution): `extracted/sprite_names/map.json`, `verify_*.png`.

## Status

| Item | Status |
|---|---|
| Source of the mapping: two static tables in `WHSHR.EXE` `.data` (identical copy in `GAMEF.DLL`) | ✅ found, record layout decoded |
| `troopsprites`, `banner`, `leaderportrait`, `loadspr` -> `.FOL/.BOP/.PAL` in `BINARY/` | ✅ every name used by campaign battles resolves; verified visually and against every battle's `SPRITES.PBX` |
| `loadplanmap`, `loadportbg` | ✅ the argument is already an 8.3 file name (45 + 14 names, all files exist) |
| `loadfurn` / `placefurniture` -> `<FILE>.XOF` 3D object in `MESH/<battle>/SCENERY.PBX` | ✅ name -> object (all campaign battles match exactly); 🟡 object -> texture only by co-occurrence, since `.XOF` is not decoded |
| Meaning of the second number (`,0`) | ❌ unknown (always 0); hypotheses below |
| Frame ranges | ✅ none: a name always means the whole `.FOL` file (the table has no frame fields) |

## Mechanism (ready to paste into FORMATS.md)

### Name tables in `WHSHR.EXE` / `GAMEF.DLL`

The CamelCase names in scripts are resolved through two arrays of fixed-size records in the
`.data` section. No pointer tables are involved: the code addresses each array by its start
(image base `0x400000`).

- The sprite table starts at VA `0x5AA808` (file offset `0x65408`), with 31 absolute references in `.text`.
- The furniture table starts at VA `0x5ADF08` (file offset `0x68B08`), with 18 references.

`GAMEF.DLL` (image base `0x10000000`) contains the same two tables byte for byte. The only
exception is the code pointers in 12 furniture records, which differ because of relocation.

**Sprite table**: 220 records of 64 bytes. Record 0 is `VoidType`.

```c
struct SpriteName {          // 64 bytes
    uint32_t runtime0;       // +0   0 in the file
    char     name[16];       // +4   name used in scripts, NUL-padded
    char     file[16];       // +20  8.3 base name of NAME.FOL/.BOP/.PAL in BINARY ("" = no 2D sprite)
    uint8_t  runtime[28];    // +36  0 in the file (code references +0x34..+0x3C: filled at load time)
};
```

The array is grouped into contiguous categories. Names are unique within a category but not
across the whole table: `Engrol` is both troop #34 (`ENGROL`) and portrait #108 (`ENGR`).
Each command therefore looks names up in its own category.

| Indices | Category | Used by | Files |
|---|---|---|---|
| 0 | `VoidType` | `troopsprites`/`banner`/`leaderportrait` = none | — |
| 1–3 | effects: `BattleSprites`→`GENBATT`, `SpellSprites`→`SPELLS`, `Sparkle` | `loadspr` | type-4 frames |
| 4–78 | troops (`MercCaptain`→`MCCAPT` … `RockLobber`→`ROCKLOB`) | `troopsprites`, `loadspr` | 16–312 type-4 frames, 32×64/64×64/128×128 |
| 79–122 | leader portraits (`Commander`→`COMM`, `EshinAss`→`SKA4` …) | `leaderportrait` | 6–8 type-1 frames (face + mouth/eye frames) |
| 123 | `AllBGs`→`BACKALL` | ? | 21 × 120×152 type-1 frames |
| 124–186 | banners (`BannerMrcCmdr`→`BANMC` … `BannerDragon`→`BANDRAG`) | `banner` | 3 frames: 72×104 type 2 + two small type-4/2 frames |
| 187–214 | animated terrain tiles (`u_water`, `Lava*`, `G_Lava*`, `BFK_*`, `U_SArch*`, `TorFlam`, `Beam`) | `loadspr` | 4 or 8 type-1 frames |
| 215–219 | `PlanMap`→`MAP1`, `PortBG`→`MAP1`, `VoidBin`, `Buttons`→`icons`, `Portrait` | engine | placeholders |

Notes:
- The file name is not always derived from the name: `BorderSwordMen`→`BODYGRD`, `Cannon`→`IMPCANON`,
  `Marius`→`CELE`, `Schepke`→`GINF`, `Allor`→`AMBE`, `FlameStrike`→`BRIW`, `lieutenant1`→`MER1`.
- One file can serve several names: `Peasants` and `Slaves` → `PEASANT`.
- Case is inconsistent (`WoodElf`, `Ceridan`, `BANSKAv1`, `icons`), so match files case-insensitively.
- `MeshDragon` and `MoleMachine` have an empty file name, which suggests they are 3D objects
  (compare the `MoleMachine1..8` furniture).
- `loadplanmap:MAP001` and `loadportbg:BACK14` take the 8.3 name directly. The table has only the
  placeholders `PlanMap`/`PortBG` → `MAP1`. Hypothesis: the command overwrites the file field
  of the placeholder.

**Furniture table**: 402 records of 60 bytes. It follows the sprite table directly; record 0 is
`VoidFurn`. The array ends at `BFKeepEndColumn`, and the bytes after it are unrelated strings.

```c
#pragma pack(1)
struct FurnitureName {       // 60 bytes
    uint32_t runtime0;       // +0   0 in the file (code references the record start)
    uint8_t  flags;          // +4   see below
    char     name[16];       // +5   name used in loadfurn/placefurniture
    char     file[16];       // +21  8.3 base name of a 3D object FILE.XOF in MESH/<battle>/SCENERY.PBX
    uint8_t  pad;            // +37
    uint16_t dims[4];        // +38  small numbers, only for buildings/tents/bridges/mole machine
                             //      (Tudor2Stry 4,11,5,5; D_Tudor2Stry 4,11,6,6; tents 6,5,1,1); meaning unknown
    uint16_t pad2;           // +46
    uint32_t code[3];        // +48  function pointers (.text) for 12 animated objects:
                             //      Crypt, NiteCrypt, WaterMill, WindMill, Tavern, BreweryMain,
                             //      D_BreweryMain, PortcullisEnt, MoleHole0, MoleHole8, ZhufWallEnt,
                             //      NiteUnderwayEnt
};
```

`flags` values: 0 (82), 1 (87), 2 (10), 3 (15), 4 (26), 5 (112), 6 (4), 17 (7), 24 (19), 25 (3),
32/33 (2+2), 69 (18), 137 (4), 152/153 (1+9), 157 (1). The groups are consistent, but their
meaning is a **hypothesis**:
- low nibble 5: trees, effects, lava;
- 1: buildings and their destroyed `D_` variants;
- 0: rocks, walls, caves;
- 2: roads; 3: slime; 4: hedges and forest edges; 6: crops;
- 0x10/0x20/0x40/0x80: extra flags, e.g. 0x40 for all 18 living pines, 0x80 for tents and Skaven tunnels.

Records 1–52 (`Flame1..4`, `SmallFlame*`, `Arrows*`, `BurningBolts*`, `Lightning*`, `WarpLightning*`,
`GazeOfMork*`, `DaKrunch`, `SapphireArch`, `HuntingSpear*`, `Explosion1..8`, `WarpExplosion1..8`) are
missile and spell effects. They appear in `SCENERY.PBX` of almost every battle without any `loadfurn`.

### Containers packed per battle (`MESH/<battle>/*.PBX`, after RNC unpacking)

- **`SPRITES.PBX`**: u32 entry count at `+0x10`. Entries start at `+0x20`, each laid out as
  `u32 name_len, name (no NUL), u32 size, data`. After the entries comes an offset table.
  It contains exactly the `.bop/.fol/.pal` triples of the 8.3 files from the sprite table.
- **`SCENERY.PBX`**: u32 object count at `+0x0C` and u32 texture count at `+0x14`. Textures
  start at `+0x20`, each laid out as `u32 name_len, name + NUL, 9×u32` (pixel bytes, palette
  bytes = 1024, w, h, 1, 1, 8, 0, colours used), then pixel indices, a 1024-byte palette
  (256 × 4) and a 38-byte trailer. Next come the object data and a name table of
  `u32 len, NAME.XOF` entries, followed by u32 offsets.
  The texture palette layout is only approximately right: one of the tested byte alignments
  gives plausible colours. It should be settled in 2.3.

## How it was verified

1. **All names from all scripts** (87 `.BTS/.MRC`, via `whscript.parse`) were resolved:
   - `troopsprites` 77 names: 73 → file, `VoidType`, `MeshDragon`/`MoleMachine` (no 2D file),
     and `ImpCannon` unresolved.
   - `banner` 66 names: 62 → file, `VoidType`, and 3 unresolved.
   - `leaderportrait` 56 names: 41 → file, `VoidType`, and 14 unresolved.
   - `loadspr` 97/97, `loadfurn` 318/319, `placefurniture` 238/239, `loadplanmap` 45/45, `loadportbg` 14/14.
   - The unresolved names are `BannerDwarf10/11` (the table has `BannerDwar10/11`), `BannerLordNuln`,
     `LegionsMan01..15`, `ImpCannon` and `UnderBridge1`. **They occur only in developer test files**
     (`RLTEST.MRC`, `RLTEST1.MRC`, `PLOT1.BTS`, `_DESTEST.BTS`), and the corresponding files are
     not packed in their PBX. Every name used by campaign files resolves.
2. **Cross-check against every battle's packed data** (`spritemap_build.py --pbx`, 53 `.BTS` with a mesh directory).
   - For **scenery**, the objects predicted from `loadfurn` plus the always-present effect objects
     equal the `.XOF` names in `SCENERY.PBX` exactly in **all 44 campaign battles**. The only
     mismatches are in test files with stale PBX.
   - For **sprites**, the files predicted from `loadspr` plus `troopsprites`/`banner` of the units
     in the `.BTS` itself equal the `SPRITES.PBX` contents exactly in 24/44 campaign battles.
     No predicted file is missing in 36/44.
     - "Extra" packed files (`WAGON`, `ROCKLOB`, `WARPFIRE`, `ESHIN`, `DDCATPLT` …) are units not
       declared in the `.BTS`. The player's army (`loadmerc`) is normally *not* packed; only 10
       battles share such files with it. **Hypothesis:** the mission DLL spawns these units.
     - The "missing" cases follow two patterns:
       - `loadspr:Wagon` written without `,0` (BF026, BF029–031, BF042) is never packed;
       - banners of some NPC units (peasants `NPC_Carlsson's Family`, hidden `NPC_Mercenary Crossbows`,
         artillery `NPC_Cannon`/`NPC_Imperial Great Cannon`) are not packed.
3. **Visual check** (`extracted/sprite_names/verify_*.png`, inspected):
   - `ClanRats`→`CLANRATS`: ratmen in blue in 8 directions.
   - `BorderHorse`→`BRDHRS`: armoured horsemen with lance and shield.
   - `EshinAssassin`→`ESHIN`: black-clad Skaven with green blades.
   - `MercXbow`→`MERCXBOW`: crossbowmen.
   - `BannerSkaven3`→`BANSKAV3`: Skaven banner (big, small icon, medium).
   - `BannerMrcCmdr`→`BANMC`: the Grudgebringers' skull-and-sword banner in blue/red/gold.
   - `Commander`→`COMM`: Morgan Bernhardt's portrait with mouth frames.
   - `TriPineLrg`→`TRIPINEL.XOF`: the object occurs in 22 SCENERY.PBX, and the textures `tree1.gif`
     and `u_tree4.gif` occur in all 22 and nowhere else. Both render as pine silhouettes.
   - `Rock1`→`ROCK.XOF`: in 10 battles; `boulder.gif` occurs in 10/11 SCENERY.PBX and renders as a
     stone-block texture.
   - `SnwPineLrg`→`S_QPINEL.XOF` and `D_SnwWatchTower`→`S_WATCH.XOF` occur only in BF001, so
     co-occurrence cannot separate their textures. That PBX has `s_qutree.gif`/`s_tritre.gif`
     (snowy pine silhouettes) and `s_watch1..6.gif` (timber-frame walls with snow). This matches
     the names, but which texture belongs to which object is **not** verified.

## Scripts

```
python3 scripts/spritemap_build.py ".../WARFB" extracted/sprite_names/map.json --pbx /tmp/pbxcache
python3 scripts/spritemap_verify.py ".../WARFB" extracted/sprite_names/map.json extracted/sprite_names \
    --pbx /tmp/pbxcache ClanRats BorderHorse EshinAssassin MercXbow BannerSkaven3 BannerMrcCmdr \
    Commander SnwPineLrg Rock1 TriPineLrg D_SnwWatchTower
```

- `--pbx` is optional for the build: without it there is no cross-check. The cache holds unpacked
  PBX files, since pure-Python RNC takes about a minute for all 88 files.
- `map.json` contains:
  - `tables`: addresses, record counts, `.text` reference counts, GAMEF.DLL comparison;
  - `names[command][name]`: status, index, category, file, FOL summary (frames, kinds, sizes,
    colour maps), number of files using the name, second numbers seen;
  - `unresolved`;
  - `sprite_table` and `furniture_table`: all records;
  - `pbx_crosscheck`: per battle.
- For renderers (e.g. `render_battle.py`): `names['troopsprites'][n]['file']` gives the `.FOL`
  base name, and `names['placefurniture'][n]['file']` gives the `.XOF` object in the battle's `SCENERY.PBX`.

## Open questions

- **Second number `,N`**. It is 0 in all 3314 uses (including `SAVE/*.MRC`). The editor writes it
  with the format `%s:%s,%d`. When it is missing (`loadspr:Wagon`), the file is not packed
  (5/5 battles), so the parser probably requires it. Hypotheses: a colour-map/variant index,
  or a frame/animation-set offset. `PEASANT` has 312 frames = 3 × 104 and 12 colour maps = 3 × 4,
  while `Peasants` and `Slaves` share it. That makes a variant selector plausible, but it would
  need dynamic analysis or disassembly.
- How the game partitions the sprite table (index ranges hard-coded in code?). The categories
  above are inferred from contents and are consistent, but the exact boundaries used by the
  lookup are not proven. `AllBGs`/`BACKALL`, `VoidBin` and `Portrait` have no known use.
- Meaning of furniture `flags`, `dims[4]` and the three code pointers.
- `.XOF` object format and the exact object → texture link (2.1/2.3); texture palette entry layout.
- Why some NPC banners and all "extra" units differ from `SPRITES.PBX` (mission DLL spawning?).
- Missing names in test files suggest older table versions (`BannerDwarf10`, `LegionsMan*`, `ImpCannon`).

## Proposed ROADMAP.md changes

- 1.4: mark 🟡→✅ for 2D names (`troopsprites`/`banner`/`leaderportrait`/`loadspr`/`loadplanmap`/`loadportbg`).
  Furniture: ✅ name → `.XOF` object, but rendering it depends on 2.1/2.3. Update the "Weryfikacja"
  column: `render_battle` can now draw unit sprites.
- 2.1: add "list of `SPRITES.PBX` entries and `SCENERY.PBX` textures/objects" (layouts above).
- 2.3: add "decode `.XOF` objects (scenery) and their texture references".
- 1.8: add "meaning of `,N` after `troopsprites`/`banner`/`leaderportrait`/`loadspr`".
- FORMATS.md: replace the open question "How `troopsprites`/`banner`/`loadfurn`/`loadspr` names map to
  `.FOL/.BOP` files … maybe via `DLL/BITMAP.DLL`" with the section above. The mapping is in
  `WHSHR.EXE`/`GAMEF.DLL`, not `BITMAP.DLL`.
