# Campaign progression and save games

Roadmap 4.4, milestone M6. Research batch 4, agent K (September 2026), static analysis of `WHSHR.EXE` and
`GAMEF.DLL` plus the owner's save files. Status markers: ✅ established, 🟡 hypothesis, ⬜ unresolved.

Verification: the stdlib reader prototype `extracted/agent_reports/K/whsv.py` (local, not in git) checks every
chunk size formula and the header checksum; both real saves (`savegame.0`, `savegame.5`) pass, re-run when this
report was merged. No save after a completed debriefing exists, so promotions, healing and the end-of-mission
payment rest on the code and on arithmetic (section 7).

## Per-question summary

| Question | Status | Answer in one paragraph |
|---|---|---|
| 1. Experience and upgrades | ✅ | Kills give `s_Exp` = victim's `s_pntval`. At the debriefing `WHSHR.EXE` `FUN_0044a2aa` applies one-time promotions at 2000 (+1 WS), 4000 (+1 S) and 6000 XP (+1 W) to troops and leader alike (the BS/I alternative for missile troops is dead code). Wizards learn one random spell of their college per 1000 XP (up to 5 spells). Each promotion adds +7 `s_pntval` and +5 (wizard +15) to the price per model. "2x Experience" (5021) doubles the XP gained in that mission (`cash` type 15). "+1 Armour" (5022) is a reward for seven named regiments, used only by `cash` type 11 (Rat Trap). |
| 2. Economy | ✅ | Coffers start at 500. Each `cash` type is a balance-sheet program in the EXE (19 opcode lists at `0x5BCF98`); the labels are `BKTXT` 5000–5024/5040–5042 and the amounts come from the `cash` line (initial, completion, rate A, rate B, required letters) and the `Result:` values in `debrief.dbf`. The initial payment is credited when troop selection is confirmed. Every regiment deployed costs price-per-model × models, and every hired regiment left behind costs 10 % of that ("Retainer"). Prices are static per regiment ×200 % (`cost` option). Worked check: 500 + 100 − 320 = 280, as in `savegame.5`. |
| 3. Troops and items | ✅ / 🟡 | `whoami` is the persistent regiment id (0–37, name `BKTXT 300+id`, index into the roster table). `PLAY.MRC` holds all regiments; `unitjoinmission` copies one into `ARMY.MRC`/`MARCH.MRC`, `unitleavemission` removes it. `addtroop` adds reinforcements that the player takes in the caravan. Routed models always return; of the killed models 65 % are wounded and come back a mission later, 35 % die. A regiment below 20 % strength is disbanded unless it is the commander's or a story regiment. No code awards magic items between battles; items move with their regiments 🟡. |
| 4. Files | ✅ | `savegame.N` (slots 0–5, slot 5 = `autosave`) is a RIFF `WHSV` file: `SHDR` header (description, battle, window, coffers, glue status, stack counts), `STAX` (glue interpreter stacks), three book-page flag lists, `RMYI` (39 × 52-byte regiment roster: flags, experience baseline, reinforcements, prices, wounded), verbatim copies of `ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC` and `debrief.dbf`, and `MISS` (current mission and `cash` line). A stdlib reader validates both real saves. |
| 5. Debrief flow | ✅ | `GAMEF.DLL` writes `debrief.dbf` (`Result:` lines + surviving and dead/routed units). `WHSHR.EXE` then runs the campaign-over check, wounded bookkeeping and the merge into `PLAY.MRC`, shows the balance sheet, and on Done adds the payment, applies armour rewards, doubled XP and promotions, then merges, heals and disbands in `ARMY.MRC` (and `MARCH.MRC`). |

## Summary of evidence sources

- `WHSHR.EXE` (front end, glue interpreter, troop selection, debrief, save/load): functions named by
  address below, read in `extracted/decompiled/exe_all.c`; static tables read directly from the EXE
  `.data` section (VA `0x5A8000` = file offset `0x62C00`).
- `GAMEF.DLL` (battle engine): debrief writer `FUN_1001bf10`, army merge `FUN_1001c270`.
- Real files: `SAVE/savegame.0`, `savegame.5`, `ARMY.MRC`, `MARCH.MRC`, `PLAY.MRC`, `debrief.dbf` of the
  owner's installation (a campaign started on the default difficulty and played up to the first mission,
  `BF003` "Protect Schnappleburg").
- Scratch files and extracted function listings: `extracted/agent_reports/K/`.

## 4. Save games `savegame.N` ✅

### 4.1 Container ✅

- **Writer** `FUN_00443cd2(path, name)`, **reader** `FUN_004447b0(path)`; path from `FUN_00443260(slot)`:
  `wsprintf("savegame.%d", slot)` for slot 0–5 only, resolved through `Reg_GetSaveFilenameF` (the `SAVE/`
  directory).
- The file is a Windows **RIFF** file written with `mmioOpen`/`mmioCreateChunk` (`FUN_0044352d`): form type
  **`WHSV`**, followed by eleven chunks in a fixed order (the reader expects the same order). All integers are
  little-endian `u32`/`i32`. Chunk sizes are exact (no chunk in either file has an odd size that needs a pad
  byte except `RMY3`/`RMY4`, which follow the RIFF even-padding rule).

| # | Chunk | Size | Source in memory | Contents |
|---|---|---|---|---|
| 1 | `SHDR` | `0xF8` | local struct | header (4.2) |
| 2 | `STAX` | variable | glue interpreter stacks | window/script stack state (4.3) |
| 3 | `BK01` | `DAT_005bb168` (120) | `DAT_005bb0f0` | book (journal) page flags, `u32` list terminated by `-1` (4.4) |
| 4 | `BKO2` | `DAT_005ba430` (16) | `DAT_005ba420` | second book flag list, `-1` terminated |
| 5 | `BK03` | `DAT_005ba480` (72) | `DAT_005ba438` | third book flag list, `-1` terminated |
| 6 | `RMYI` | `DAT_005b9ddc` (2028) | `DAT_005b95f0` | **regiment roster table**, 39 × 52 bytes (4.5) |
| 7 | `RMY1` | file size | `SAVE/ARMY.MRC` | verbatim copy of the text file |
| 8 | `RMY2` | file size | `SAVE/PLAY.MRC` | verbatim copy |
| 9 | `RMY3` | file size | `SAVE/MARCH.MRC` | verbatim copy |
| 10 | `RMY4` | file size | `SAVE/debrief.dbf` | verbatim copy |
| 11 | `MISS` | `0x110` | `DAT_00496230` | current mission record (4.6) |

Chunks 7–10 are written by `FUN_00443904(fourcc, filename)` which reads the whole file and writes it
unchanged; the loader `FUN_0044438d` writes them back to `SAVE/`. Verified: `savegame.0` `RMY2` is
byte-identical to the current `PLAY.MRC`, `savegame.5` `RMY3` to the current `MARCH.MRC`; the empty army
file written at campaign start is the 45/46-byte stub `[MERCARMY]\r\n\r\n[END]\t; end of BATTLESCRIPT` (the
`.dbf` copy ends with a DOS `0x1A` EOF byte).

### 4.2 `SHDR` header (0xF8 bytes) ✅

Built by `FUN_00443cd2` (a zeroed `0xF8` buffer), applied by `FUN_004447b0`.

| Offset | Type | Field | savegame.0 | savegame.5 | Evidence |
|---|---|---|---|---|---|
| `0x00` | char[64] | save description (user text) | `The Border Princes` | `Last Game` | second argument of the writer |
| `0x40` | char[64] | current battle script (`DAT_00496050`) | `bf003` | `bf003` | copied back on load |
| `0x80` | char[64] | current map/glue window (`DAT_005a4a50`) | empty | `MapWindowBp1` | copied back on load |
| `0xC0` | u32 | format version, always 1 | 1 | 1 | the loader only runs the check below when it is 1 |
| `0xC4` | u32 | "checksum" (`FUN_004432c3`): sizes of `BK01`+`BKO2`+`BK03`+`RMYI` (2236) + file size of `FILE/DLL/WND.DLL` (string-table entry 1, 390 144 B) | `0x5FCBC` | `0x5FCBC` | ✅ value matches both files; 🟡 the reader recomputes it but the decompiled code discards the result, so a mismatch is not rejected |
| `0xC8` | u32 | `DAT_005bb340` | 0 | 0 | ⬜ restored on load |
| `0xCC` | u32 | `nScripts`: number of glue script contexts in `STAX` | 0 | 2 | chunk size formula |
| `0xD0` | u32 | `nCalls`: return-address stack depth | 2 | 4 | chunk size formula |
| `0xD4` | u32 | `nWindows`: window stack depth | 2 | 4 | chunk size formula |
| `0xD8` | u32 | `nObjects`: loaded window objects | 0 | 2 | chunk size formula |
| `0xDC` | i32 | **coffers** (gold crowns, `DAT_00473e04`) | 500 | 280 | getter `FUN_004477c4` / setter `FUN_004477d9`, add `FUN_004477ec`, subtract `FUN_0044780a` |
| `0xE0` | u32 | glue status bits `DAT_005b9fd0` (`setgluestatus`/`testmission`) | 0 | 0 | restored with `FUN_0043cdeb`/`FUN_0043cd97` |
| `0xE4` | u32 | glue status mask `DAT_005b9fd4` | `-1` | `-1` | as above |
| `0xE8` | i32 | `DAT_005bcdb8`: mission kill counter used by the "Skaven killed bonus" line | 0 | 0 | `FUN_00447fce` |
| `0xEC` | — | 12 zero bytes | | | never written |

### 4.3 `STAX` chunk ✅ (layout) / 🟡 (record contents)

`FUN_004439fd` writes, in order, with the counts from the header:

1. `nScripts` × `0x218A0` bytes — glue script contexts (`DAT_00496340[i]`; each starts with the script
   resource name, e.g. `MapWindow`, and holds the loaded script text and interpreter state);
2. `nScripts` × `u32` (`DAT_005a2ca0`), 3. `nScripts` × `u32` (`DAT_00496210`);
4. `nCalls` × `u32` (`DAT_005a2c60`);
5. `nWindows` × `0x80` bytes: pairs of 64-byte names (`MainMenu`/`StartCaravan`, `FlowScriptBP01`/`BPMission1`)
   (`DAT_005a2840`); 6. `nWindows` × `u32` (`DAT_005a2c40`);
7. `nObjects` × `0xA0` bytes (`DAT_005a4050`; name at `+4`, a string-table index at `+0x84` that the loader
   uses to reload the object's resource through `FUN_004344f0`).

Size = `nScripts·0x218A8 + nCalls·4 + nWindows·0x84 + nObjects·0xA0`: 272 for `savegame.0`, 275 632 for
`savegame.5` — both match the files exactly. A save therefore resumes the glue interpreter exactly where it
stopped (the reason `savegame.5` is 8× larger: two script contexts were active on the map screen).


### 4.4 `BK01`, `BKO2`, `BK03`: book pages ✅

Three `u32` arrays (30, 4 and 18 entries including the `-1` terminator). The glue command
`enablebook:<book>=<index>` (token `0x64` in the interpreter `FUN_0040bd2c`) sets entry `index` of array
`book` (0 → `DAT_005bb0f0`, 1 → `DAT_005ba420`, 2 → `DAT_005ba438`) to 1. They are the unlocked pages of the
in-game journal (troop book, bestiary/places). `savegame.5` has one more page enabled in `BK01` (index 26)
than `savegame.0`, set by the first mission's scripts.

### 4.5 `RMYI`: regiment roster table ✅

`DAT_005b95f0`, 39 records of `0x34` bytes; **the record index is the unit's `whoami`**, and record 38 is all
`-1` (terminator tested by `FUN_00437e50`). The initial values are static data in the EXE (`.data` VA
`0x5B95F0`, file offset `0x741F0`); the whole table is saved and restored, so it carries the campaign state
of every regiment that is not in the text files.

| Offset | Field | Static values | Evidence |
|---|---|---|---|
| `+0x00` | `keep`: never disbanded | 1 for whoami 21, 23, 24, 29, 31, 33 (1st Carlsson Guard, the three Dwarf Warriors regiments, Ceridan, Dwarf Envoy); `-1` terminator | `FUN_0044b189`; `FUN_0044b5ee` removes a unit below 20 % strength only when this is 0 (section 3.3) |
| `+0x04` | `forHire`: may be hired and fired | 0 for whoami 2, 8–13, 21–24, 29–31, 33–37; 1 otherwise | when a regiment joins with 0 here its unit gets `hired=1` automatically (`FUN_00449a55`, `FUN_004498d5`, `FUN_0044ba94`: unit `+0x368`); the Hire/Fire button is disabled when 0 (`FUN_00438694`) |
| `+0x08` | wizard | 1 for 18–20 (Celestial, Bright, Amber wizards) | selects the spell promotion path (`FUN_0044a2aa`) |
| `+0x0C` | artillery | 1 for 14–17 (cannons, mortars) and 25 (Hellblaster) | `FUN_0044b0bb`: an artillery unit with fewer than 2 models counts as destroyed |
| `+0x10` | `pendingJoin` | 0 | set by glue token 2 (`<keyword>:<whoami>`) in `FUN_0040bd2c`; `FUN_0044ba94` copies such regiments from the roster into `ARMY.MRC` and clears it |
| `+0x14` | in marching orders | 0 | `FUN_0043b460` (from the `MARCH.MRC` list); read by glue `testforunitinmarch` (token `0x7D`) |
| `+0x18` | in army | 0 | `FUN_0043b3cb` (from the army units); read by glue `testforunitinarmy` (token `0x7C`) |
| `+0x1C` | experience at the start of the mission | 0 | baseline for the doubled-experience reward and the troop book's "Experience" column (`FUN_0043026f`: `s_Exp − baseline`); set to `s_Exp` after each debrief (`FUN_0044a5c8`) |
| `+0x20` | reinforcements available | 0 | glue `addtroop:<whoami>=<n>` adds `n` (token `0x62`); the Reinforcements window (`FUN_0043b06e`) moves them into the unit; cleared by `FUN_0044b9ba` |
| `+0x24` | base price per model (gold crowns) | 10, 8, 8, 4, 3, 14, 0, 0, …, 33, 30, 20, 20, 0, 50, 0, …, 18, 12, 10, 9 | scaled once by `FUN_00448741(cost%)` |
| `+0x28` | current price per model | 0 | set to `+0x24` for a new campaign (`FUN_00437e85`); +5 per troop promotion, +15 per wizard level (`FUN_0044a2aa`) |
| `+0x2C` | wounded in the last battle | 0 | `FUN_0044b42a` (section 3.3) |
| `+0x30` | wounded returning to the ranks | 0 | `FUN_0044b4c9` moves `+0x2C` here; `FUN_0044b5ee` adds it to the unit |

Check against the files: in both saves `+0x24` and `+0x28` are exactly **twice** the static value for every
regiment (20, 16, 16, 8, 6, 28, …, 66, 60, 40, 40, 100, 36, 24, 20, 18) — the default `cost` of 200 %
(`FUN_00448741(200)` in `WinMain` `FUN_00442a40`). `+0x18` (army) is 1 for whoami 2 and 3 in `savegame.0`
(start of the campaign, `ARMY.MRC` holds the two Grudgebringer units), `+0x14` (marching orders) is 1 for the same two
units in `savegame.5`, whose `MARCH.MRC` holds them.

### 4.6 `MISS`: current mission record ✅

`DAT_00496230`, `0x110` bytes, filled by the mission window's `[MISSION]` block when the player picks a
mission (glue keywords `set:res=`, `res`, `script`, `setbattlescript`, `setmissionscript`, `cash`).

| Offset | Type | Contents | savegame.5 |
|---|---|---|---|
| `0x00` | u32 | mission name, `BRTXT` string id | 601 "Protect Schnappleburg" |
| `0x04` | char[32] | briefing run file | `bpbr1.run` |
| `0x24` | char[32] | briefing glue script | `BPBrief1` |
| `0x44` | char[32] | battle script | `bf003` |
| `0x64` | char[32] | mission glue script | `BPMission1` |
| `0x84`–`0xB3` | u32 × 12 | ⬜ (`+0xA4` is 1 in `savegame.5`) | |
| `0xB4` | u32 | debrief evaluator index = `n − 1` of `setdebrief:n`/`debrief:n` (`FUN_0040bb27`; `FUN_004469b3` runs entry `n − 1` of the table at `0x5BC9CC`) ✅ | 1 (`BPMission1` has `setdebrief:2`) |
| `0xB8` | u32 | `cash` type = balance sheet program (3.1) | 1 |
| `0xBC` | u32 | initial payment | 100 |
| `0xC0` | u32 | completion payment | 400 |
| `0xC4` | u32 | rate A | 50 |
| `0xC8` | u32 | rate B | 25 |
| `0xCC` | char[2] | objective letters required for the completion payment | `A`, 0 |
| `0xF0` | u32 × 8 | regiments forced into the army, stored as `whoami + 1` (`FUN_0044bef7`; whoami 2 is always forced) | 🟡 filled by `forceunits` |

The glue handler for `cash` (token `0x60`) proves the layout: `cash:type,initial,completion,rateA,rateB,L1,L2`
stores the integers at `+0xB8…+0xC8` and the first character of the two letter fields at `+0xCC`, `+0xCD`.
`whshr/campaign.py` names fields 4 and 5 `per_unit` and `penalty`; they are two generic rates whose meaning
depends on the program (for example `cash:1,100,400,50,25,A` in `BPMission1`: 50 per villager killed, 25 per
building destroyed).

### 4.7 Reader prototype

`extracted/agent_reports/K/whsv.py` (see section 6) parses a `savegame.N`, prints the header, the book flags,
the roster table with regiment names (`BKTXT 300 + whoami`), the mission record and the embedded text files,
and checks every chunk size formula. Both real saves pass.

## 1. Experience and promotions ✅

### 1.1 Gaining experience (battle) ✅

From `notes/game_rules.md` 3.2: when a model dies, the killing unit's `s_kills` (+0x334) increases by one and
its `s_Exp` (+0x336) by the victim's `s_pntval`. `GAMEF.DLL` writes both into `debrief.dbf` (`set:s_kills=`,
`set:s_Exp=`); e.g. the owner's first battle gave the Grudgebringer Cavalry 11 kills / 165 XP and the
Infantry 20 kills / 80 XP.

### 1.2 Doubled experience: "2x Experience Points Awarded" (`BKTXT` 5021) ✅

`FUN_0044a146` (called by `FUN_0044a5c8` at the end of the debriefing): the multiplier is the result of
running the mission's balance-sheet program (`FUN_0044796b`), which is 1 unless the program contains opcode
`0x0C` (it sets `DAT_00473e08 = 2` and prints `BKTXT 5021`). Only program type 15 contains it, used by the five
missions with `cash:15,0,0,0,0`. For every unit in the debrief:

```
gained = s_Exp - roster[whoami].expAtStart
s_Exp  = roster[whoami].expAtStart + gained * multiplier
```

### 1.3 Promotions (`FUN_0044a2aa`, called per unit by `FUN_0044a5c8`) ✅

Arguments: the unit, the experience before the mission (`roster.expAtStart`) and after it (`s_Exp`). Each
threshold is applied once, when it is crossed (`old < T ≤ new`). "+1" is applied to both the troop profile
(`unit+0x7A+i`) and the leader's copy (`unit+0x95+i`).

| Unit kind | Threshold | Effect | Also |
|---|---|---|---|
| troops, `roster.wizard == 0` | 2000 | **+1 WS** (`+0x83`/`+0x9E`) | price per model +5 (if not 0), `s_pntval` +7 |
| | 4000 | **+1 S** (`+0x85`/`+0xA0`) | same |
| | 6000 | **+1 W** (`+0x87`/`+0xA2`) | same (debug text says "5000") |
| wizard, `roster.wizard != 0` | every 1000 (each multiple crossed) | learns one new spell, if it knows fewer than 5 (`FUN_00449fa5`) | price per model +15, `s_pntval` +7 |

- The code has an alternative for missile troops (+1 BS instead of WS, +1 I instead of S), selected by
  `FUN_0044afa4`, but that function **always returns 0**, so every troop type gets WS and S. ✅ (Ghidra
  removed the unreachable block; the function body is a constant return.)
- The spell promotion picks one of three college lists (`0x5BCFF8`, `0x5BD010`, `0x5BD028`) according to the
  college of the spells the wizard already knows (`FUN_00449e49`/`e6c`/`e8f`), then draws random spells from it until
  it finds one the wizard does not know yet (`Unit gaining new spell (%d)`).
- There is no separate leader progression: leaders gain the same +1 as their unit. There is no Ld, BS, T, I, A
  or M improvement and no promotion above 6000 XP.
- `s_pntval` +7 per promotion also makes the unit worth more experience to the enemy.
- Comparison with WFB 4th edition: the tabletop game has no experience; the thresholds are a computer-game
  addition. The "Dogs of War" flavour survives in paying for troops by the model.

### 1.4 "+1 Armour rating" (`BKTXT` 5022) ✅

`FUN_0044a6f2(debrief.dbf)` runs the balance-sheet program; opcodes `0x0D`–`0x13` name one regiment each by
`whoami`: 4 (Black Avengers), 27 (Mercenary Crossbows), 20 (Amber Wizard), 16 (1st Mortar Crew), 17 (2nd
Mortar Crew), 1 (Ragnar's Wolves), 7 (Leitdorf 9th Crossbows). If that regiment is in the army with models left
(`FUN_0044af65 > 0`), the line "%s Receive +1 Armour rating" is printed and `s_armr` (`+0x8C`) and the leader's
armour (`+0xA7`) increase by 1 (`Unit %s gets a %d S_ARMOUR bonus`). Only program type 11 contains these
opcodes; it follows its payment lines.


## 2. Economy ✅

### 2.1 Coffers and campaign options ✅

- The treasury is one global `i32` `DAT_00473e04` (saved at `SHDR+0xDC`), changed only through
  `FUN_004477d9` (set), `FUN_004477ec` (add) and `FUN_0044780a` (subtract).
- New campaign (`FUN_0043d653`): coffers = `DAT_005ba0b0`, static default **500**; the prepaid initial
  payment `DAT_00473ddc` = 0.
- Developer command-line options (table `PTR_PTR_005b7098` → `0x5B6E98`, 16-byte records, read in
  `FUN_004427ad`): `cash:<n>` initial coffers; `cost:<pct>` price scaling (default `FUN_00448741(200)` in
  `WinMain`, i.e. all prices ×2); `maxselect:<n>` regiments per mission, clamped 8–38 (static default 13);
  `dead:<pct>` share of lost models that die (static 65 → `DAT_005bcff0 = 100 − dead`, see 3.3). Other
  names in the table: `nobattle`, `testarmy`, `testbook`, `unrealquit`, and a cheat-like `k#df1g7ue!`.
- A hidden key-sequence cheat in `FUN_0042a102` adds 1000 crowns (`FUN_004477ec(1000)`, else the message
  "Oh... so you think you can build...").
- Glue commands: `addcash:<n>` (token `0x98`) and `iftrueaddcash:<n>` (`0x99`) add to the coffers. Only one
  use exists: `iftrueaddcash:200` (the merchant's 200 crowns, `BRTXT 933`).

### 2.2 Price of regiments ✅

- **Price per model**: roster `+0x28` (4.5). It starts at the static base price × `cost%` and rises by 5 per
  troop promotion and by 15 per wizard level.
- **Regiment price**: `FUN_0043802d` = price per model × (`s_size` + `s_routed`), i.e. for the current number
  of models. It is stored in the unit's runtime field `+0x360` by `FUN_00433efd` when the selection screen opens.
- Check: 500 (start) + 100 (initial payment of `BPMission1`) − (Grudgebringer Cavalry 16 × 12 + Infantry 8 × 16
  = 320) = **280**, exactly the coffers in `savegame.5`, which the mission script autosaved right after troop
  selection.

### 2.3 Troop selection: mission fee and retainers ✅

Unit runtime fields in `WHSHR.EXE` (0x3F0-byte unit record, same layout as `GAMEF.DLL` for the script part):
`+0x360` regiment price, `+0x364` selected for this mission, `+0x368` hired (belongs to the company),
`+0x36C` hired when the recruit screen opened, `+0x374` reinforcements offered, `+0x378` reinforcements taken.

- Opening the selection (`FUN_00433efd`): every living regiment forced by the mission (`MISS+0xF0` list, and
  whoami 2 always, `FUN_0044bef7`) becomes hired and, unless destroyed (`FUN_0044b0bb`), selected.
- Toggling a regiment (`FUN_0042e938`/`FUN_0042e994`) is limited to `maxselect` regiments.
- **Done** (`FUN_004320fe`, "DoTroopSelectionDone"):
  `coffers += prepaid initial payment` (`FUN_0044782c`, set when the mission was chosen, `FUN_00447a2a` runs the
  balance-sheet program up to its "Initial Payment" line), then
  `coffers −= Σ price(selected regiments) + Σ price(hired but not selected) × 10 / 100` (`FUN_0042e693` =
  `FUN_0043818a` + `FUN_004380b1`/`FUN_00438068`). The screen labels are `BKTXT 409` "Mission Fee" and
  `410`/`411` "Retainer"/"Total Retainer Cost": a deployed regiment costs its full price for every mission,
  a regiment left in camp costs 10 %.
- **Bankruptcy** (`FUN_0042e7a1`, called when the selection opens): if `coffers + prepaid initial payment` is
  less than the price of the forced regiments, the screen switches to mode 5 and shows `BKTXT 601–603`
  "Your campaign is over Commander!", "You have %d gold crowns.", "To sustain your army you need at least %d gold
  crowns." (drawn by `FUN_00430ef0`).
- Availability text (`FUN_0042ea32`): not hired → `BKTXT 415` "Available for hire"; excluded by the mission
  (`excludeunits`) → 416 "Not available", except whoami 29 and 31 (Ceridan, Dwarf Envoy) → 418 "Refuses to join
  you" and whoami 13, 36, 37 (Gyrocopters) → 420 "Has engine trouble"; destroyed → 417 "Wounded".

### 2.4 Recruiting and reinforcements (caravan) ✅ / 🟡

- Recruit window `FUN_00439b8c` (`gocaravan:recruit`): the Hire/Fire button (`BRTXT 319`/`320`) toggles
  `+0x368`; when the regiment was not hired on entry (`+0x36C == 0`) the coffers pay (or refund) its price
  `+0x360` immediately. It is enabled only for `forHire` regiments and only when the coffers cover the price
  (`FUN_00438694`). Cancel restores `+0x368` from `+0x36C` (`FUN_00438365`).
- Glue `addtroop:<whoami>=<n>` (117 uses, token `0x62`) adds `n` to the roster's reinforcements (`+0x20`). The
  Reinforcements window (`BKTXT 505` "Reinforcements", 507 "Available : %d", 508 "Take : %d";
  `FUN_0043a266`, `FUN_0043b06e`) offers `min(available, orgsize − (models + wounded))` and moves the taken men
  into `s_size`, subtracting them from `+0x20`. They are not charged separately 🟡: they raise the model count
  and therefore the regiment's price in the next mission fee.
- `FUN_0043b67c` (called when the caravan is left) removes every unit of `ARMY.MRC` that is not hired
  (`FUN_0044ba01`) and clears all unused reinforcements (`FUN_0044b9ba`).
- Glue `addunit:<whoami>` (token 2, 18 uses, e.g. `addunit:5 ; Carroburg Greatswords`) marks a regiment
  `pendingJoin`; `FUN_0044ba94` (from `FUN_0042ba35`, the `gocaravan` handler that picks the
  `CaravanAfterMission[WithRecruit]` scripts) copies these regiments from `PLAY.MRC` into `ARMY.MRC`, giving
  `hired=1` to those that are not `forHire` 🟡. They then appear in the recruit window.

### 2.5 Mission payments: the balance sheet programs ✅

The `cash` type selects a program: a zero-terminated list of opcodes in `WHSHR.EXE` (`.data`, pointer table
`0x5BCF98`, 19 entries). The interpreter `FUN_00448230` runs one opcode per call; each opcode prints a
`BKTXT` label with an amount and updates the running total `DAT_00473e00`. Inputs: `MISS` initial/completion/
rate A/rate B, the objective records of `debrief.dbf` (`FUN_00445d90(letter)`: 40-byte record per letter, `+0x00`
present, `+0x14` success flag, `+0x18`/`+0x1C`/`+0x20`/`+0x24` the four values of the `Result:` line), and the
bonus counter.

| Op | Label (`BKTXT`) | Amount |
|---|---|---|
| `0x01` | blank line | — |
| `0x0A` | 5002 Mission Total | shows the running total |
| `0x0B` | 5003 Total Final Payment | `max(total, 0)` |
| `0x0C` | 5021 2x Experience Points Awarded | sets the experience multiplier to 2 |
| `0x0D`–`0x13` | 5022 %s Receive +1 Armour rating | whoami 4, 27, 20, 16, 17, 1, 7 (1.4) |
| `0x14` | 5000 Initial Payment | `+initial` |
| `0x15` | 5001 Completion Payment | `+completion` if every required letter (`MISS+0xCC`, up to 2) has success 1 (`FUN_00447854`), else 0 |
| `0x16`/`0x17`/`0x18` | 5040/5041/5042 Arrival at Loren/Zhufbar/Nuln | `+completion` |
| `0x28` | 5004 Payment Already Received | `−initial` |
| `0x3C` | 5010 Villagers killed penalty | `−A × (B.v1C − B.v24)` |
| `0x3D` | 5011 Buildings destroyed penalty | `−B × (C.v1C − C.v24)` |
| `0x3E` | 5012 Wagons destroyed penalty | `−A × D.v20` |
| `0x3F` | 5015 Livestock killed penalty | `−A × (B.v1C − B.v24)` |
| `0x40` | 5017 Bolt holes remaining penalty | `−A × C.v24` |
| `0x41` | 5019 High Elder not rescued penalty | `−A` |
| `0x42` | 5023 Hiln killed penalty | `−A` |
| `0x50` | 5013 Skaven killed bonus | `+A × bonus counter` |
| `0x51` | 5014 Rock Lobbers destroyed bonus | `+A × W.v24` |
| `0x52` | 5020 All Rock Lobbers destroyed bonus | `+B` if `W.v1C ≤ W.v24` |
| `0x53` | 5016 Payment for all men | `+A × Z.v18` |
| `0x54` | 5024 Dwarfs rescued payment | `+A × B.v24` |

`X.vNN` = value at offset `NN` of objective `X`. `BKTXT 5018` "Dwarves rescued bonus" is never used.
Opcodes `0x41`/`0x42` are unconditional, so the programs that use them (13, 14) include them
only because the mission's objective structure makes the line apply 🟡.

| Type | Program | Missions (`cash` line) |
|---|---|---|
| 0 | (empty) | — |
| 1 | Initial, Completion, Total, ·, Already received, Villagers, Buildings, ·, Final | Protect Schnappleburg `bf003` (`1,100,400,50,25,A`; an alternative window has `1,100,300,100,0,A`) |
| 2 | Initial, Completion, Total, ·, Already received, Wagons, ·, Final | Escort to Holst `bf005` |
| 3 | Completion, ·, Final | 11 missions (Rescue Ilmarin, Bugman's Brewery, Shattered Pass…) |
| 4 | Initial, Completion, Skaven killed, Total, ·, Already received, ·, Final | Patrol `bf007` (`4,200,200,20,0`) |
| 5 / 6 / 18 | Arrival at Loren / Zhufbar / Nuln, ·, Final | marches (`5,0,5000,0,M` …), Escort Engrol uses 18 |
| 7 | Arrival at Zhufbar, ·, Rock Lobbers destroyed, ·, Final | The Listening Gate `bf017` |
| 8 | Initial, Completion, Total, ·, Already received, ·, Final | Decoy, Patrol Loren, Vanberg |
| 9 | Rock Lobbers destroyed, All Rock Lobbers destroyed, ·, Final | Counter Attack `bf027` (`9,0,1000,300,100`) |
| 10 | Completion, Livestock killed, ·, Final | Squatter's Rights `bf028` |
| 11 | Completion, Payment for all men, ·, Final, ·, +1 Armour ×7 | Rat Trap `bf041` (`11,0,500,25,0,A`) |
| 12 | Completion, Bolt holes remaining, ·, Final | Extermination `bf033` |
| 13 | Completion, High Elder not rescued, ·, Final | Rescue `bf032` |
| 14 | Completion, Hiln killed, ·, Final | Sven Carlsson `bf001` |
| 15 | 2x Experience | Mole Machine `bf040`, Orc Pursuit `bf011`, Slave Train `bf004_4` |
| 16 | Completion, ·, Livestock killed, Buildings destroyed, ·, Final | Against the Grain `bf004_2` (`16,0,500,10,50,A`) |
| 17 | Dwarfs rescued payment, ·, Final | The Iron Fort `bf036` |

Notes:
- Briefing texts describe the same bonuses: `BRTXT 2013` "10 crowns for each Skaven head" and 2030 "I'll double my
  offer to 20 crowns a head" (Patrol has rate A = 20), 30033 "25 crowns per man" (Rat Trap: rate A = 25), 32012
  "200 crowns for every Dwarf rescued" 🟡 (the text-to-mission links were not traced; the numbers agree).
- **Bonus counter** (`SHDR+0xE8`): `bonusinit` (token `0x93`) sets it to 0; `bonusadd:<n>,<L>` (`0x94`), `bonussubtract`
  (`0x95`), `iftruebonusadd` (`0x96`), `iffalsebonusadd` (`0x9A`) add/subtract value `n` (1–4 → `v18`, `v1C`,
  `v20`, `v24`) of objective `L` from `debrief.dbf` (`FUN_0040bb90`). Only `BPMISSION5` uses it
  (`bonusadd:4,V`, the Skaven heads of Patrol).
- `cash` lines with only four numbers (`cash:5,0,5000,0,M`) put `M` into rate B (`atoi` → 0) and leave no
  required letter; their programs do not test completion, so this is harmless ✅ (parser in `FUN_0040bd2c`).
- Worked example, the owner's `debrief.dbf` of `bf003` (`A,1,…`, `B,1,80,12,100,12`, `C,1,80,7,100,7`):
  100 + 400 = 500 total; −100 already received; villagers 50 × (12 − 12) = 0; buildings 25 × (7 − 7) = 0;
  final **400**, which the debriefing would add to the 280 in the coffers (the game exited before that under Wine).
- When the payment is added (`FUN_00432199` "DoDebriefingDone"): in debrief modes 2 (after
  `playgamewithdebrief`) and 4 (glue `debrief:`) `coffers += FUN_004479ee(MISS)` (the final total); the glue
  `debrief` handlers also pass `FUN_0044d8df` (the same addition) as the window callback 🟡 (whether both run is
  not established).

## 3. Troops, casualties and items

### 3.1 `whoami`: persistent regiment id ✅

- `whoami` (field token `0x49` in `WHSHR.EXE`'s key table at `0x5A99E8`, next to `hired` = `0x4B`) is the
  regiment's index in the roster table (0–37; `BKTXT 300 + whoami` is its name; unit byte `+0x24`, read by
  `FUN_0044adb7`). All the campaign code finds units by it (`FUN_004493ab`).
- The unit loader shared by both binaries (`GAMEF.DLL` `FUN_1000e250`, `set:` field switch) stores
  `whoami` (0x49) as a byte at unit `+0x24` and `hired` (0x4B) as an `int` at unit `+0x368` ✅, the offsets the
  front-end code reads.
- In `PLAY.MRC` the 38 regiments carry whoami 0–37 in order; `ARMY.MRC`, `MARCH.MRC` and `debrief.dbf` keep the
  same numbers, and the glue scripts address regiments by it (`addtroop:27=2 ; Merc Crossbowmen`).
- In battle, `GAMEF.DLL` `FUN_1001c270` loads `ARMY.MRC` and, for every NPC unit of the battle script (side bits
  `0x40`) with `whoami < 50`, looks for the same whoami in the player's army: if the regiment is in the army it
  copies the army's profile, psychology, experience (`+0x336`) and the spell and item lists into the NPC
  ("NPC %s is in Army Merging with %s"); if it is in the marching orders the NPC is deleted; if not found it is
  kept. Allied story regiments therefore keep their campaign state when they fight as NPCs.

### 3.2 Joining and leaving ✅

| Glue command | Token | Handler | Effect |
|---|---|---|---|
| `unitjoinmission:<id>` | `0x7E` | `FUN_0044bd75` | copy regiment `id` from `PLAY.MRC` into `ARMY.MRC`, then from `ARMY.MRC` into `MARCH.MRC` (`FUN_004498d5`, only if not yet present), always with `hired=1` |
| `unitleavemission:<id>` | `0x7F` | `FUN_0044bdb4` | remove regiment `id` from `ARMY.MRC` and `MARCH.MRC` (`FUN_00449c06` clears the unit's alive bit and rewrites the file); its record in `PLAY.MRC` stays |
| `addunit:<id>` | 2 | interpreter | mark `pendingJoin` (2.4) |
| `forceunits:<ids>` / `excludeunits:<ids>` | `0x88`/`0x89` | mission window | `MISS+0xF0` forced list; excluded regiments show "Not available" 🟡 (the interpreter ignores both tokens, so the mission window parser reads them) |
| `testforunitinarmy:<id>` / `testforunitinmarch:<id>` | `0x7C`/`0x7D` | interpreter | glue status := roster `inArmy`/`inMarch` |

Counts in `WND.DLL`: 30 `unitjoinmission`, 24 `unitleavemission` (Carlsson's guards 21, 22, 35 leave after their
escort, …), 20 `forceunits`, 39 `excludeunits`, 18 `addunit`, 117 `addtroop`.

### 3.3 Casualties, wounded and disbanding ✅

After a battle (`FUN_0043d760`, before the debrief screen) and when the debrief is accepted:

1. **Lost models** of a unit = `s_calualties − s_routed` (`FUN_0044aec7`). Of these,
   `wounded = lost × 65 / 100` (integer division; `DAT_005bcff0`, option `dead`) and `dead = lost − wounded`.
   The troop book shows them as `BKTXT 405` "Dead" and 406 "Wounded" (`FUN_0043026f`).
2. **Routed models return**: `s_size += s_routed`, and `s_calualties`, `s_routed`, `s_kills` are reset to 0
   before the army file is written (`FUN_0044abf4`). A regiment's model count for prices is `s_size + s_routed`
   (`FUN_0044ae68`).
3. **Wounded come back one mission later**: the previous `wounded` (`roster+0x2C`) is moved to
   `returning` (`+0x30`, `FUN_0044b4c9`), the new wounded are stored in `+0x2C` (`FUN_0044b42a`), and
   "HealWounded" `FUN_0044b5ee` adds `returning` to `s_size`, capped at `s_orgsize` (at the cap it also clears the
   casualty counters). If the battle's objective `Z` succeeded, all wounded are lost (`FUN_0044b39c`;
   `BKTXT 611` "The wounded could not be recovered." 🟡 for the text link).
4. **Disbanding**: `FUN_0044b5ee` removes a regiment whose `s_size + s_routed` is below `max(1, 20 % of s_orgsize)`
   (`FUN_0044b120`), unless it is whoami 2 (the Grudgebringer Cavalry with the commander) or has the roster
   `keep` flag.
5. **Destroyed**: `FUN_0044b0bb` treats a regiment as destroyed when `s_size + s_routed == 0`, or when it is
   artillery with fewer than 2 models; destroyed regiments cannot be selected ("Wounded").
6. **The commander never dies outright** (`FUN_0044b89e`): if whoami 2 is destroyed but has wounded, one wounded
   model is returned (`s_routed += 1`, `wounded −= 1`); a `keep` regiment with no models left also gets one model
   back.
7. **Campaign over** (`FUN_0044b270`, `FUN_0044b1b2`): if whoami 2 still has models, the campaign ends when
   objective `G` or `Y` is present and flagged 1; if it has none, the campaign ends when objective `Z` is
   flagged 1, otherwise the commander gets one model back. The end plays movie `death01` (commander dead) or
   `death02` (`FUN_0043d722`). 🟡 for the meaning of `G`/`Y`/`Z` (defeat conditions written by the battle).

Routed units are therefore not lost: fled models rejoin their regiment, and only the killed share is split
into dead and wounded.

### 3.4 Magic items and spells ✅ / 🟡

- Items and spells are part of the unit text (`addmagicitem:ItemGrudgeBringer`, `addspell:`), stored at unit
  `+0x390` (spells, count + list) and `+0x3C0` (items); `FUN_0044a881` copies both lists when battle results are
  merged, and `GAMEF.DLL` `FUN_1001c270` copies them into merged NPCs. Items persist with the regiment in
  `PLAY.MRC`/`ARMY.MRC`.
- No code path in the campaign layer awards a new item: the only runtime additions are wizard spells (1.3).
  New items come with the regiments' text definitions (e.g. `Dwarf Hammerers` with `ItemRockSplitter`,
  `Dwarf Envoy` with `ItemArmourOfTheBeard` in `MAXARMY.MRC`) 🟡 (`BKTXT 610` "%s have found the %s." suggests a
  found-item message; its user was not located).


## 4.8 The text files in `SAVE/` ✅

All four are INI-style scripts read by the same parser as `.BTS`/`.MRC` (`whshr/script.py`; the loader in
both binaries is `FUN_1000e250`-style `set:` switches). Every unit block is written by the editor-style writer
(`FUN_00448ea8` in `WHSHR.EXE`, `FUN_10009190` in `GAMEF.DLL`), which is why they contain the
`;S_RACE is … are you sure this is right?` comments.

| File | Role | Created from (new campaign) | Written by | Read by |
|---|---|---|---|---|
| `PLAY.MRC` | **master roster**: all 38 regiments (whoami 0–37) with their current profile, experience, items, `hired` flag; the persistent state of regiments that are not in the company | `FILE/SCRIPT/MAXARMY.MRC` (`FUN_0044949e` family, `Reg_GetLoadFilenameF("SCRIPT\\MAXARMY.MRC")` → save `PLAY.MRC`) | after each battle `FUN_0043d760` merges the debrief into it (`FUN_0044a98a`, `FUN_0044acbb`) | `unitjoinmission`, `addunit` (copy into the army) |
| `ARMY.MRC` | **the company**: regiments currently with the Grudgebringers | `FILE/SCRIPT/STRTARMY.MRC` (Grudgebringer Cavalry and Infantry) | troop selection done, debrief done (heal/disband), caravan, join/leave | troop book, troop selection, `GAMEF.DLL` NPC merge (`FUN_1001c270`) |
| `MARCH.MRC` | **marching orders**: the regiments selected for the next battle, with deployment `dir`/`x`/`y` | `FILE/SCRIPT/MARCH.MRC` (45-byte empty `[MERCARMY]` stub) | march order window (`FUN_00439b8c`, `FUN_00449a55`), debrief modes 3/6 | `GAMEF.DLL` as the player army (`FUN_1000cff0` returns `SAVE\MARCH.MRC` in campaign mode, otherwise `script\<name>`) |
| `debrief.dbf` | **battle result** | `FILE/SCRIPT/DEBRIEF.DBF` (46-byte stub) | `GAMEF.DLL` `FUN_1001bf10` at the end of the battle | debrief screen, balance sheet, `testobjective`, `bonusadd`, army merge |

Verified: `SAVE/ARMY.MRC` is byte-identical to `FILE/SCRIPT/STRTARMY.MRC` and `SAVE/PLAY.MRC` to
`FILE/SCRIPT/MAXARMY.MRC` (the owner's session never completed a debriefing), and the stubs equal the
`RMY3`/`RMY4` chunks of `savegame.0`. `FILE/SCRIPT/ARMY.MRC` (3104 B) and `REVARMY.MRC` (4902 B) are not
referenced by these code paths ⬜.

### `debrief.dbf` ✅

```
[DEBRIEF]
;Mission Results
		[MISSIONINFO]
				Result:<letter>,<success>,<v18>,<v1C>,<v20>,<v24>     one line per objective
		[END]	; end of MISSIONINFO
		[UNITS]
				set:count=<n>
				;Surviving Units
				addunit: … endunit:      (full unit blocks, same as .MRC)
				;Dead or Routed Units
				addunit: … endunit:
		[END]	; end of UNITS
[END]	; end of BATTLESCRIPT
```

- `GAMEF.DLL` `FUN_1001bf10`: writes one `Result:` line per objective record (list at `DAT_100f4d4c`, format
  `"%s:%c,%d,%d,%d,%d,%d"`, keyword token `0x24` `Result`). `WHSHR.EXE` stores them in 40-byte records per letter:
  `+0x00` present, `+0x14` success, `+0x18`/`+0x1C`/`+0x20`/`+0x24` the four values. Their meaning depends on the
  objective type 🟡: for `B` (villagers) and `C` (buildings) of `bf003` the pair `80,12,100,12`/`80,7,100,7` reads as
  required %, count at start, current %, count now; `Z,0,28,…` gives 28 = the player's models at the start
  (12 + 16), used by "Payment for all men".
- Surviving units: every living player unit (side bits `0xE0 == 0`) and, when the battle has NPC merging
  enabled, living NPC units with `whoami < 50`. Dead or routed units: the removed-unit list `DAT_100e25b4`; for
  such NPCs `s_calualties` is reset to 0. Units keep `set:s_calualties/s_routed/s_kills/s_Exp` and the battle
  `dir`/`x`/`y`.
- The owner's file (`bf003`): `A,1` (objective met), `B,1,80,12,100,12`, `C,1,80,7,100,7`, `K,0,13,10,0,39`,
  `R,0,1,0,0,0`, `Z,0,28,2,0,0`; Grudgebringer Cavalry 0 casualties, 11 kills, 165 XP; Infantry 7 casualties
  (→ 4 wounded, 3 dead by 3.3), 20 kills, 80 XP.

## 5. Debrief flow (battle → campaign) ✅

1. **Before the battle** the mission glue (e.g. `BPMission1`: `setdebrief:2`, `enablebook:0=26`, `autosave:`,
   `encounterplaygamewithdebrief:bf003`) records the debrief evaluator (`setdebrief:n` → `MISS+0xB4 = n − 1`),
   saves slot 5 and starts the battle. `playgame`/`playgamewithdebrief` (tokens `0x65`/`0x67`) call
   `FUN_0043dac1(battle, encounter, withDebrief)`; the `encounter*` variants (`0x66`/`0x68`) only store the battle
   name for the caravan's encounter.
2. **Battle** (`GAMEF.DLL`): loads `SAVE/MARCH.MRC` as the player army, merges NPCs with `ARMY.MRC`
   (`FUN_1001c270`), and at the end writes `debrief.dbf` (`FUN_1001bf10`).
3. **Return** (`FUN_0043d910`): chooses the end screen `GameEndScreen`/`GameEndScreenSuccess`/`…Failure` by
   running the mission's debrief evaluator (`FUN_00445e7b`: table `0x5BC9CC`, 20-byte records `{function,
   key letter, …}` indexed by `MISS+0xB4`; key `A` → objective A, `T` → evaluator result, `Z`/`z` → objective Z),
   then schedules a debrief wrapper: `withDebrief` → mode 2 (`FUN_0043d826`/`FUN_0043d85f`), without → mode 6
   (`FUN_0043d89b`/`FUN_0043d8d4`); the `encounter` variants add the callback `FUN_004322ab`
   (= DoDebriefingDone(1)).
4. **Every wrapper first runs `FUN_0043d760`**: campaign-over test (3.3 item 7, `death01`/`death02`), wounded
   bookkeeping (`FUN_0044b4c9`, `FUN_0044b42a`, `FUN_0044b89e` on `debrief.dbf`), merge of the debrief into
   `PLAY.MRC` (`FUN_0044a98a`: per whoami, copy profile bytes, casualties, routed, kills, `+0x33E`, experience, spell
   and item lists; `FUN_0044acbb`: routed back into ranks, counters reset, file written), and clearing of the
   wounded if objective `Z` succeeded.
5. **Debrief screen** `FUN_00432fb7(debrief.dbf, title, MISS name, …, mode)`: shows the balance sheet
   (`FUN_00448230` lines) and the troop book (kills, dead, wounded, experience gained).
6. **Done** — `FUN_00432199` ("DoDebriefingDone"):
   - modes 2 and 4: `coffers += final payment` (`FUN_004479ee`);
   - `FUN_0044a6f2(debrief.dbf)`: "+1 Armour" rewards (1.4);
   - `FUN_0044a5c8(debrief.dbf, 1)`: doubled experience, promotions, new experience baselines (1.2, 1.3);
   - mode 2: `FUN_0044bdf1` → merge the debrief into `ARMY.MRC` and HealWounded/disband; modes 3 and 6:
     `FUN_0044be4b` → the same for `ARMY.MRC` and `MARCH.MRC`, then `MARCH.MRC` is rewritten from the army;
   - `FUN_0044b3e3` clears `returning` wounded; control returns to the glue script (typically `addtroop:` lines,
     a movie and `gocaravan:select`).
7. Glue `debrief:<n>`/`debriefwithsummary:<n>` (tokens `0x87`/`0x8C`, with `iftrue`/`iffalse` variants
   `0x8D`–`0x90`) set the evaluator like `setdebrief` and open the debrief screen directly in mode 4 or 7 with
   the callback `FUN_0044d8df` (payment, `FUN_0040dae2`); `testobjective:<L>` (`0x8B`) and `testmission:`
   (`0x97`, the evaluator's result) set the glue status for `iftrue*`/`iffalse*` commands. In the decompiled
   switch `testmission` falls through into `autosave` (no `break`) 🟡 — its single use is followed by glue that
   does not depend on it.


## 6. Condensed format description

### Save games `SAVE/savegame.0`–`savegame.5` ✅

Written by `WHSHR.EXE` (`FUN_00443cd2`, read by `FUN_004447b0`); slot 5 "Last Game" is the glue `autosave:`.
A Windows RIFF file, form `WHSV`, little-endian, eleven chunks in fixed order:

| Chunk | Size | Contents |
|---|---|---|
| `SHDR` | 248 | `char[64]` description, `char[64]` battle script, `char[64]` current glue window, `u32` version (1), `u32` checksum (= size of `BK01`+`BKO2`+`BK03`+`RMYI` + size of `WND.DLL`), `u32` ?, `u32` nScripts, nCalls, nWindows, nObjects, `i32` coffers, `u32` glue status bits, `u32` glue status mask, `i32` bonus counter, 12 zero bytes |
| `STAX` | nScripts·0x218A8 + nCalls·4 + nWindows·0x84 + nObjects·0xA0 | glue interpreter state: script contexts (0x218A0 each) + 2×u32 per script, call stack, window stack (two 64-byte names + u32), window objects (0xA0 each) |
| `BK01`, `BKO2`, `BK03` | 120, 16, 72 | `u32` book-page flags set by `enablebook:<book>=<page>`, terminated by `-1` |
| `RMYI` | 2028 | 39 × 52-byte regiment records indexed by `whoami` (last all `-1`): `keep`, `forHire`, `wizard`, `artillery`, `pendingJoin`, `inMarch`, `inArmy`, experience at mission start, reinforcements available, base price, price per model, wounded, wounded returning (all `i32`) |
| `RMY1`–`RMY4` | file size | verbatim `ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC`, `debrief.dbf` |
| `MISS` | 272 | current mission: `u32` BRTXT name id, 4 × `char[32]` (briefing run file, briefing script, battle, mission script), 12 × `u32` ?, `u32` debrief evaluator index, `u32` cash type, 4 × `i32` (initial, completion, rate A, rate B), 2 required objective letters, …, 8 × `u32` forced regiments (whoami + 1) at `+0xF0` |

Campaign text files in `SAVE/`: `PLAY.MRC` (all 38 regiments, from `SCRIPT/MAXARMY.MRC`), `ARMY.MRC` (the
company, from `SCRIPT/STRTARMY.MRC`), `MARCH.MRC` (regiments and positions for the next battle, read by
`GAMEF.DLL`), `debrief.dbf` (battle result from `GAMEF.DLL`: `[MISSIONINFO]` `Result:<letter>,<success>,<4 values>`
and `[UNITS]` surviving and dead/routed units). Reader prototype: `extracted/agent_reports/K/whsv.py` (both saves
pass `--check`).


## 7. Open questions

- ⬜ `SHDR+0xC8` (`DAT_005bb340`), `MISS+0x84…+0xB3` (one flag at `+0xA4`) and the two `u32` per script in `STAX`.
- 🟡 The meaning of the four `Result:` values per objective type (written by `GAMEF.DLL` objective code; only
  `bf003` is available as a real file). Needed to reproduce penalties exactly.
- 🟡 Whether the debrief payment can be added twice in modes 4/7 (window callback `FUN_0044d8df` and
  `FUN_00432199`); needs the debrief window's Done handler or a Wine session.
- 🟡 Objectives `G`, `Y`, `Z` as campaign-defeat conditions, and the exact text shown for "wounded could not be
  recovered".
- 🟡 The per-mission debrief evaluators (`0x5BC9CC`, 42 entries of `{function, key letter, 3 × u32}`; seven
  distinct functions `0x4462D6`, `0x4463E5`, `0x446508`, `0x446613`, `0x446762`, `0x4467FF`, `0x44690C`) were not
  decoded; they decide success/failure end screens and `testmission`.
- ⬜ `BKTXT 610` "%s have found the %s." (item finds) — user not located; `FILE/SCRIPT/ARMY.MRC`, `REVARMY.MRC` roles.
- 🟡 `testmission` falling through into `autosave` (check the jump table in the disassembly).
- Not verified at runtime: no save exists after a completed debriefing, so promotions, healing and payment were
  verified by code and arithmetic only. A Wine session finishing `bf003` would produce the next `PLAY.MRC`/
  `ARMY.MRC` and coffers 680 as a direct test.
