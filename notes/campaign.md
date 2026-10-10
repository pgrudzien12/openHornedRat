# Campaign progression and save games

Roadmap 4.4, milestone M6. Campaign rules and the save-game file format. Status markers: ✅ established,
🟡 hypothesis, ⬜ unresolved.

Verification: a stdlib reader checks every chunk size formula and the header checksum; both real saves
(`savegame.0`, `savegame.5`) pass. No save after a completed debriefing exists, so promotions, healing and the
end-of-mission payment rest on the rules as documented and on arithmetic (section 8).

## Per-question summary

| Question | Status | Answer in one paragraph |
|---|---|---|
| 1. Experience and upgrades | ✅ | Kills give `s_Exp` = victim's `s_pntval`. At the debriefing the game applies one-time promotions at 2000 (+1 WS), 4000 (+1 S) and 6000 XP (+1 W) to troops and leader alike (the BS/I alternative for missile troops is never used). Wizards learn one random spell of their college per 1000 XP (up to 5 spells). Each promotion adds +7 `s_pntval` and +5 (wizard +15) to the price per model. "2x Experience" (5021) doubles the XP gained in that mission (`cash` type 15). "+1 Armour" (5022) is a reward for seven named regiments, used only by `cash` type 11 (Rat Trap). |
| 2. Economy | ✅ | Coffers start at 500. Each `cash` type is a balance-sheet program (19 opcode lists); the labels are `BKTXT` 5000–5024/5040–5042 and the amounts come from the `cash` line (initial, completion, rate A, rate B, required letters) and the `Result:` values in `debrief.dbf`. The initial payment is credited when troop selection is confirmed. Every regiment deployed costs price-per-model × models, and every hired regiment left behind costs 10 % of that ("Retainer"). Prices are static per regiment ×200 % (`cost` option). Worked check: 500 + 100 − 320 = 280, as in `savegame.5`. |
| 3. Troops and items | ✅ / 🟡 | `whoami` is the persistent regiment id (0–37, name `BKTXT 300+id`, index into the roster table). `PLAY.MRC` holds all regiments; `unitjoinmission` copies one into `ARMY.MRC`/`MARCH.MRC`, `unitleavemission` removes it. `addtroop` adds reinforcements that the player takes in the caravan. Routed models always return; of the killed models 65 % are wounded and come back a mission later, 35 % die. A regiment below 20 % strength is disbanded unless it is the commander's or a story regiment. No rule awards magic items between battles; items move with their regiments 🟡. |
| 4. Files | ✅ | `savegame.N` (slots 0–5, slot 5 = `autosave`) is a RIFF `WHSV` file: `SHDR` header (description, battle, window, coffers, glue status, stack counts), `STAX` (glue interpreter stacks), three book-page flag lists, `RMYI` (39 × 52-byte regiment roster: flags, experience baseline, reinforcements, prices, wounded), verbatim copies of `ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC` and `debrief.dbf`, and `MISS` (current mission and `cash` line). A stdlib reader validates both real saves. |
| 6. Mission availability | ✅ | A mission window offers up to 5 `[MISSION]` records; one rule decides per record whether it is drawn: already taken (`+0xA4`) hides it, `set:depend=<res>` requires that mission to be taken, `set:inactivedepend=<res>` requires that mission *not* to be on offer (recursive, not "not done"). The number of visible missions drives both the mission list on the map and the scroll pile on Dietrich's desk, which draws `CarScroll3/2/1` at thresholds 2/3/4 — that is, **visible − 1 scrolls, capped at 3**. Choosing a mission without `set:releaseflag=1` leaves the player on the same map window with that mission removed. |
| 5. Debrief flow | ✅ | `GAMEF.DLL` writes `debrief.dbf` (`Result:` lines + surviving and dead/routed units). `WHSHR.EXE` then runs the campaign-over check, wounded bookkeeping and the merge into `PLAY.MRC`, shows the balance sheet, and on Done adds the payment, applies armour rewards, doubled XP and promotions, then merges, heals and disbands in `ARMY.MRC` (and `MARCH.MRC`). |

## Summary of evidence sources

- The game's front end (`WHSHR.EXE`: glue interpreter, troop selection, debrief, save/load): observable behaviour, plus
  the static tables stored in the executable's data.
- The battle engine (`GAMEF.DLL`): the debrief file it writes and the army merge it performs.
- Real files: `SAVE/savegame.0`, `savegame.5`, `ARMY.MRC`, `MARCH.MRC`, `PLAY.MRC`, `debrief.dbf` of the
  owner's installation (a campaign started on the default difficulty and played up to the first mission,
  `BF003` "Protect Schnappleburg").

## 4. Save games `savegame.N` ✅

### 4.1 Container ✅

- File name `savegame.<slot>` for slot 0–5 only, in the `SAVE/` directory.
- The file is a Windows **RIFF** file: form type
  **`WHSV`**, followed by eleven chunks in a fixed order (the reader expects the same order). All integers are
  little-endian `u32`/`i32`. Chunk sizes are exact (no chunk in either file has an odd size that needs a pad
  byte except `RMY3`/`RMY4`, which follow the RIFF even-padding rule).

| # | Chunk | Size | Contents |
|---|---|---|---|
| 1 | `SHDR` | `0xF8` | header (4.2) |
| 2 | `STAX` | variable | glue interpreter window/script stack state (4.3) |
| 3 | `BK01` | 120 | book (journal) page flags, `u32` list terminated by `-1` (4.4) |
| 4 | `BKO2` | 16 | second book flag list, `-1` terminated |
| 5 | `BK03` | 72 | third book flag list, `-1` terminated |
| 6 | `RMYI` | 2028 | **regiment roster table**, 39 × 52 bytes (4.5) |
| 7 | `RMY1` | file size | verbatim copy of `SAVE/ARMY.MRC` |
| 8 | `RMY2` | file size | verbatim copy of `SAVE/PLAY.MRC` |
| 9 | `RMY3` | file size | verbatim copy of `SAVE/MARCH.MRC` |
| 10 | `RMY4` | file size | verbatim copy of `SAVE/debrief.dbf` |
| 11 | `MISS` | `0x110` | current mission record (4.6) |

Chunks 7–10 each hold a whole file, unchanged; loading a save writes them back to `SAVE/`. Verified: `savegame.0`
`RMY2` is byte-identical to the current `PLAY.MRC`, `savegame.5` `RMY3` to the current `MARCH.MRC`; the empty army
file written at campaign start is the 45/46-byte stub `[MERCARMY]\r\n\r\n[END]\t; end of BATTLESCRIPT` (the
`.dbf` copy ends with a DOS `0x1A` EOF byte).

### 4.2 `SHDR` header (0xF8 bytes) ✅

> **Correction (`notes/save_resume.md` §1-§2):** the four counters at `0xCC-0xD8` are the depths of the window-state, context, caller and script-frame stacks; the two u32 arrays after the snapshots are each snapshot's open-window count and palette id.

The header is a zeroed `0xF8`-byte block filled as follows.

| Offset | Type | Field | savegame.0 | savegame.5 | Evidence |
|---|---|---|---|---|---|
| `0x00` | char[64] | save description (user text) | `The Border Princes` | `Last Game` | text entered when saving |
| `0x40` | char[64] | current battle script | `bf003` | `bf003` | copied back on load |
| `0x80` | char[64] | current map/glue window | empty | `MapWindowBp1` | copied back on load |
| `0xC0` | u32 | format version, always 1 | 1 | 1 | the checksum below is only verified when it is 1 |
| `0xC4` | u32 | "checksum": sizes of `BK01`+`BKO2`+`BK03`+`RMYI` (2236) + file size of `FILE/DLL/WND.DLL` (string-table entry 1, 390 144 B) | `0x5FCBC` | `0x5FCBC` | ✅ value matches both files; 🟡 the loader recomputes it but a mismatch is not rejected |
| `0xC8` | u32 | `tentpos` | 0 | 0 | ✅ campaign tent position, restored on load (`notes/campaign_tent.md`) |
| `0xCC` | u32 | `nScripts`: number of glue script contexts in `STAX` | 0 | 2 | chunk size formula |
| `0xD0` | u32 | `nCalls`: return-address stack depth | 2 | 4 | chunk size formula |
| `0xD4` | u32 | `nWindows`: window stack depth | 2 | 4 | chunk size formula |
| `0xD8` | u32 | `nObjects`: loaded window objects | 0 | 2 | chunk size formula |
| `0xDC` | i32 | **coffers** (gold crowns) | 500 | 280 | worked check in section 2 |
| `0xE0` | u32 | glue status bits (`setgluestatus`/`testmission`) | 0 | 0 | restored on load |
| `0xE4` | u32 | glue status mask | `-1` | `-1` | as above |
| `0xE8` | i32 | mission kill counter used by the "Skaven killed bonus" line | 0 | 0 | — |
| `0xEC` | — | 12 zero bytes | | | never written |

### 4.3 `STAX` chunk ✅ (layout) / 🟡 (record contents)

The chunk holds, in order, with the counts from the header:

1. `nScripts` × `0x218A0` bytes — glue script contexts (each starts with the script
   resource name, e.g. `MapWindow`, and holds the loaded script text and interpreter state);
2. `nScripts` × `u32`, 3. `nScripts` × `u32`;
4. `nCalls` × `u32`;
5. `nWindows` × `0x80` bytes: pairs of 64-byte names (`MainMenu`/`StartCaravan`, `FlowScriptBP01`/`BPMission1`);
   6. `nWindows` × `u32`;
7. `nObjects` × `0xA0` bytes (name at `+4`, a string-table index at `+0x84` that the loader
   uses to reload the object's resource).

Size = `nScripts·0x218A8 + nCalls·4 + nWindows·0x84 + nObjects·0xA0`: 272 for `savegame.0`, 275 632 for
`savegame.5` — both match the files exactly. A save therefore resumes the glue interpreter exactly where it
stopped (the reason `savegame.5` is 8× larger: two script contexts were active on the map screen).


### 4.4 `BK01`, `BKO2`, `BK03`: book pages ✅

Three `u32` arrays (30, 4 and 18 entries including the `-1` terminator). The glue command
`enablebook:<book>=<index>` (token `0x64` in the glue scripts) sets entry `index` of array
`book` (0 = `BK01`, 1 = `BKO2`, 2 = `BK03`) to 1. They are the unlocked pages of the
in-game journal (troop book, bestiary/places). `savegame.5` has one more page enabled in `BK01` (index 26)
than `savegame.0`, set by the first mission's scripts.

### 4.5 `RMYI`: regiment roster table ✅

The table has 39 records of `0x34` bytes; **the record index is the unit's `whoami`**, and record 38 is all
`-1` (terminator). The initial values are static data in the game's executable; the whole table is saved and
restored, so it carries the campaign state of every regiment that is not in the text files.

| Offset | Field | Static values | Behaviour |
|---|---|---|---|
| `+0x00` | `keep`: never disbanded | 1 for whoami 21, 23, 24, 29, 31, 33 (1st Carlsson Guard, the three Dwarf Warriors regiments, Ceridan, Dwarf Envoy); `-1` terminator | a unit below 20 % strength is removed only when this is 0 (section 3.3) |
| `+0x04` | `forHire`: may be hired and fired | 0 for whoami 2, 8–13, 21–24, 29–31, 33–37; 1 otherwise | when a regiment joins with 0 here its unit gets `hired=1` automatically; the Hire/Fire button is disabled when 0 |
| `+0x08` | wizard | 1 for 18–20 (Celestial, Bright, Amber wizards) | selects the spell promotion path |
| `+0x0C` | artillery | 1 for 14–17 (cannons, mortars) and 25 (Hellblaster) | an artillery unit with fewer than 2 models counts as destroyed |
| `+0x10` | `pendingJoin` | 0 | set by glue token 2 (`<keyword>:<whoami>`); the game then copies such regiments from the roster into `ARMY.MRC` and clears it |
| `+0x14` | in marching orders | 0 | set from the `MARCH.MRC` list; read by glue `testforunitinmarch` (token `0x7D`) |
| `+0x18` | in army | 1 for whoami 2 and 3 (the two starting Grudgebringer units), 0 otherwise | set from the army units; read by glue `testforunitinarmy` (token `0x7C`) |
| `+0x1C` | experience at the start of the mission | 0 | baseline for the doubled-experience reward and the troop book's "Experience" column (`s_Exp − baseline`); set to `s_Exp` after each debrief |
| `+0x20` | reinforcements available | 0 | glue `addtroop:<whoami>=<n>` adds `n` (token `0x62`); the Reinforcements window moves them into the unit; unused reinforcements are cleared when the caravan is left |
| `+0x24` | base price per model (gold crowns) | full table in "Static roster table" below | scaled once by the campaign `cost` percentage |
| `+0x28` | current price per model | 0 | set to `+0x24` for a new campaign; +5 per troop promotion, +15 per wizard level |
| `+0x2C` | wounded in the last battle | 0 | set after each battle (section 3.3) |
| `+0x30` | wounded returning to the ranks | 0 | receives `+0x2C` at the next debrief, then is added to the unit's size |

Check against the files: in both saves `+0x24` and `+0x28` are exactly **twice** the static value for every
one of the 38 regiments (verified by `scripts/roster_check.py`) — the default `cost` of 200 %.
`+0x18` (army) is 1 for whoami 2 and 3 in `savegame.0`
(start of the campaign, `ARMY.MRC` holds the two Grudgebringer units), `+0x14` (marching orders) is 1 for the same two
units in `savegame.5`, whose `MARCH.MRC` holds them.

#### Static roster table (complete, whoami 0–37)

Read from the EXE image (39 × 52 bytes) and cross-checked: the four flag columns match the lists above, and the
saved `+0x24`/`+0x28` of both `savegame.0` and `savegame.5` equal 2 × the base price for all 38 records. Columns:
K = keep (`+0x00`), H = forHire (`+0x04`), W = wizard (`+0x08`), A = artillery (`+0x0C`), Ar = in army (`+0x18`),
Price = base price per model (`+0x24`). All other fields are 0 in the static image.

| whoami | K | H | W | A | Ar | Price | | whoami | K | H | W | A | Ar | Price |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 0 | 0 | 0 | 10 | | 19 | 0 | 1 | 1 | 0 | 0 | 50 |
| 1 | 0 | 1 | 0 | 0 | 0 | 8 | | 20 | 0 | 1 | 1 | 0 | 0 | 0 |
| 2 | 0 | 0 | 0 | 0 | 1 | 8 | | 21 | 1 | 0 | 0 | 0 | 0 | 0 |
| 3 | 0 | 1 | 0 | 0 | 1 | 4 | | 22 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 1 | 0 | 0 | 0 | 3 | | 23 | 1 | 0 | 0 | 0 | 0 | 0 |
| 5 | 0 | 1 | 0 | 0 | 0 | 14 | | 24 | 1 | 0 | 0 | 0 | 0 | 0 |
| 6 | 0 | 1 | 0 | 0 | 0 | 0 | | 25 | 0 | 1 | 0 | 1 | 0 | 18 |
| 7 | 0 | 1 | 0 | 0 | 0 | 0 | | 26 | 0 | 1 | 0 | 0 | 0 | 12 |
| 8–13 | 0 | 0 | 0 | 0 | 0 | 0 | | 27 | 0 | 1 | 0 | 0 | 0 | 10 |
| 14 | 0 | 1 | 0 | 1 | 0 | 33 | | 28 | 0 | 1 | 0 | 0 | 0 | 9 |
| 15 | 0 | 1 | 0 | 1 | 0 | 30 | | 29 | 1 | 0 | 0 | 0 | 0 | 0 |
| 16 | 0 | 1 | 0 | 1 | 0 | 20 | | 30 | 0 | 0 | 0 | 0 | 0 | 0 |
| 17 | 0 | 1 | 0 | 1 | 0 | 20 | | 31 | 1 | 0 | 0 | 0 | 0 | 0 |
| 18 | 0 | 1 | 1 | 0 | 0 | 0 | | 32 | 0 | 1 | 0 | 0 | 0 | 0 |
| | | | | | | | | 33 | 1 | 0 | 0 | 0 | 0 | 0 |
| | | | | | | | | 34–37 | 0 | 0 | 0 | 0 | 0 | 0 |

Price 0 means "not sold per model": the non-hireable story regiments, and hireable whoami 6, 7, 20, 32 (wizards
18 and 20 and these have no base price; the wizard rows gain +15 per level from 0). Whoami 19 is the only
priced wizard (50). The table's terminator is record 38 (all `-1`).

### 4.6 `MISS`: current mission record ✅

The record (`0x110` bytes) is filled by the mission window's `[MISSION]` block when the player picks a
mission (glue keywords `set:res=`, `res`, `script`, `setbattlescript`, `setmissionscript`, `cash`).

| Offset | Type | Contents | savegame.5 |
|---|---|---|---|
| `0x00` | u32 | mission name, `BRTXT` string id | 601 "Protect Schnappleburg" |
| `0x04` | char[32] | briefing run file | `bpbr1.run` |
| `0x24` | char[32] | briefing glue script | `BPBrief1` |
| `0x44` | char[32] | battle script | `bf003` |
| `0x64` | char[32] | mission glue script | `BPMission1` |
| `0x84` | char[32] | `replacescript`: the flow script that replaces the current one when this mission is chosen ✅ | empty |
| `0xA4` | u32 | **mission taken** ✅: 0 when the `[MISSION]` block is parsed, set to 1 when the player commits to the mission; hides it in its window (section 7) | 1 |
| `0xA8` | u32 | `set:releaseflag=` ✅: 1 = choosing this mission resumes the flow script instead of staying on the same map window (section 7) | 0 |
| `0xAC` | u32 | `set:depend=<res>` ✅: offer this mission only once the mission with that name id in the same window has been taken (section 7) | 0 |
| `0xB0` | u32 | `set:inactivedepend=<res>` ✅: offer this mission only while the mission with that name id is *not* itself on offer (section 7) | 0 |
| `0xB4` | u32 | debrief evaluator index = `n − 1` of `setdebrief:n`/`debrief:n` (the game runs entry `n − 1` of its debrief evaluator table) ✅ | 1 (`BPMission1` has `setdebrief:2`) |
| `0xB8` | u32 | `cash` type = balance sheet program (3.1) | 1 |
| `0xBC` | u32 | initial payment | 100 |
| `0xC0` | u32 | completion payment | 400 |
| `0xC4` | u32 | rate A | 50 |
| `0xC8` | u32 | rate B | 25 |
| `0xCC` | char[2] | objective letters required for the completion payment | `A`, 0 |
| `0xF0` | u32 × 8 | regiments forced into the army, stored as `whoami + 1` (whoami 2 is always forced) | 🟡 filled by `forceunits` |

The glue handler for `cash` (token `0x60`) proves the layout: `cash:type,initial,completion,rateA,rateB,L1,L2`
stores the integers at `+0xB8…+0xC8` and the first character of the two letter fields at `+0xCC`, `+0xCD`.
`whshr/campaign.py` names fields 4 and 5 `per_unit` and `penalty`; they are two generic rates whose meaning
depends on the program (for example `cash:1,100,400,50,25,A` in `BPMission1`: 50 per villager killed, 25 per
building destroyed).

### 4.7 Reader prototype

A stdlib reader prototype (local, not in git) parses a `savegame.N`, prints the header, the book flags,
the roster table with regiment names (`BKTXT 300 + whoami`), the mission record and the embedded text files,
and checks every chunk size formula. Both real saves pass.

## 1. Experience and promotions ✅

### 1.1 Gaining experience (battle) ✅

When a model leaves its unit (killed, or removed alive), the unit holding the model's credit gains +1 `s_kills` and
the victim unit's `s_pntval` in `s_Exp`; close combat, contact attacks and fanatics set the credit on any wound,
missiles, artillery and spells only on the lethal hit (`notes/casualty_bookkeeping.md` §2). `GAMEF.DLL` writes both into `debrief.dbf` (`set:s_kills=`,
`set:s_Exp=`); e.g. the owner's first battle gave the Grudgebringer Cavalry 11 kills / 165 XP and the
Infantry 20 kills / 80 XP.

### 1.2 Doubled experience: "2x Experience Points Awarded" (`BKTXT` 5021) ✅

At the end of the debriefing the multiplier is the result of
running the mission's balance-sheet program, which is 1 unless the program contains opcode
`0x0C` (it sets the multiplier to 2 and prints `BKTXT 5021`). Only program type 15 contains it, used by the five
missions with `cash:15,0,0,0,0`. For every unit in the debrief:

```
gained = s_Exp - roster[whoami].expAtStart
s_Exp  = roster[whoami].expAtStart + gained * multiplier
```

### 1.3 Promotions (applied once per unit at the end of the debriefing) ✅

Inputs: the unit, the experience before the mission (`roster.expAtStart`) and after it (`s_Exp`). Each
threshold is applied once, when it is crossed (`old < T ≤ new`). "+1" is applied to both the troop profile
and the leader's copy.

| Unit kind | Threshold | Effect | Also |
|---|---|---|---|
| troops, `roster.wizard == 0` | 2000 | **+1 WS** | price per model +5 (if not 0), `s_pntval` +7 |
| | 4000 | **+1 S** | same |
| | 6000 | **+1 W** | same (a developer message says "5000") |
| wizard, `roster.wizard != 0` | every 1000 (each multiple crossed) | learns one new spell, if it knows fewer than 5 | price per model +15, `s_pntval` +7 |

- The game contains an alternative for missile troops (+1 BS instead of WS, +1 I instead of S), but it is never
  selected, so every troop type gets WS and S. ✅
  The engine deliberately uses +1 BS instead of +1 WS at 2000 XP for ranged regiments; their 4000 XP promotion
  remains +1 S.
- The spell promotion picks one of three college spell lists according to the college of the spells the wizard
  already knows, then draws random spells from it until it finds one the wizard does not know yet
  (`Unit gaining new spell (%d)`).
- There is no separate leader progression: leaders gain the same +1 as their unit. There is no Ld, BS, T, I, A
  or M improvement and no promotion above 6000 XP.
- `s_pntval` +7 per promotion also makes the unit worth more experience to the enemy.
- Comparison with WFB 4th edition: the tabletop game has no experience; the thresholds are a computer-game
  addition. The "Dogs of War" flavour survives in paying for troops by the model.

#### Optional marksman progression (proposed engine mod rule)

Tracked in [issue #180](https://github.com/pgrudzien12/openHornedRat/issues/180).

The following is a **proposed optional rule**, not behaviour of the original game. The
original promotion track above should remain the default. The engine currently gives
the first promotion to Ballistic Skill for a broad ranged category, while leaving
the second and third promotions at Strength and Wounds. A selectable mod rule would
replace that interim behaviour with separate tracks:

| Regiment's ordinary missile weapon | 2000 XP | 4000 XP | 6000 XP |
|---|---|---|---|
| Bow, crossbow, Wood Elf bow, short bow, longbow | +1 BS | +1 I | +1 BS |
| Great cannon, cannon, mortar, Hellblaster, rock lobber, Doom Diver | +1 BS | +1 I | +1 W |
| Other special ranged attacks | +1 WS | +1 S | +1 W |

Identify the first two groups by their ordinary missile weapon, rather than the
regiment class alone: a Gyrocopter bomb and innate fire or breath attacks should not
inherit the bow track accidentally. In the battle rules, BS narrows ordinary shot
scatter and I shortens reload; artillery also loses its ability to fire when the
machine is destroyed (`game_rules.md` §8; `ranged_combat_handoff.md` §4). The thresholds,
leader and troop updates, price changes, and points-value changes stay as specified
above. A campaign should retain its chosen rule across engine saves, and changing it
should not recalculate promotions already earned.

### 1.4 "+1 Armour rating" (`BKTXT` 5022) ✅

The balance-sheet program's opcodes `0x0D`–`0x13` name one regiment each by
`whoami`: 4 (Black Avengers), 27 (Mercenary Crossbows), 20 (Amber Wizard), 16 (1st Mortar Crew), 17 (2nd
Mortar Crew), 1 (Ragnar's Wolves), 7 (Leitdorf 9th Crossbows). If that regiment is in the army with models left,
the line "%s Receive +1 Armour rating" is printed and its armour (`s_armr`) and the leader's
armour increase by 1 (`Unit %s gets a %d S_ARMOUR bonus`). Only program type 11 contains these
opcodes; it follows its payment lines.


## 2. Economy ✅

### 2.1 Coffers and campaign options ✅

- The treasury is one global `i32` (saved at `SHDR+0xDC`), changed only by set, add and subtract operations.
- New campaign: coffers = static default **500**; the prepaid initial payment = 0.
- Developer command-line options (16-byte records): `cash:<n>` initial coffers; `cost:<pct>` price scaling
  (default 200, i.e. all prices ×2); `maxselect:<n>` regiments per mission, clamped 8–38 (static default 13);
  `dead:<pct>` share of lost models that die (static 65; wounded = 100 − dead, see 3.3). Other
  option names: `nobattle`, `testarmy`, `testbook`, `unrealquit`, and one undocumented cheat option.
- A hidden key-sequence cheat adds 1000 crowns; otherwise a taunting message is shown.
- Glue commands: `addcash:<n>` (token `0x98`) and `iftrueaddcash:<n>` (`0x99`) add to the coffers. Only one
  use exists: `iftrueaddcash:200` (the merchant's 200 crowns, `BRTXT 933`).

### 2.2 Price of regiments ✅

- **Price per model**: roster `+0x28` (4.5). It starts at the static base price × `cost%` and rises by 5 per
  troop promotion and by 15 per wizard level.
- **Regiment price** = price per model × (`s_size` + `s_routed`), i.e. for the current number
  of models. It is fixed when the selection screen opens.
- Check: 500 (start) + 100 (initial payment of `BPMission1`) − (Grudgebringer Cavalry 16 × 12 + Infantry 8 × 16
  = 320) = **280**, exactly the coffers in `savegame.5`, which the mission script autosaved right after troop
  selection.

### 2.3 Troop selection: mission fee and retainers ✅

During troop selection the game keeps, for each unit: its regiment price, whether it is selected for this
mission, whether it is hired (belongs to the company), whether it was hired when the recruit screen opened, and the
reinforcements offered and taken.

- Opening the selection: every living regiment forced by the mission (`MISS+0xF0` list, and
  whoami 2 always) becomes hired and, unless destroyed, selected.
- Toggling a regiment is limited to `maxselect` regiments.
- **Done**:
  `coffers += prepaid initial payment` (set when the mission was chosen, by running the
  balance-sheet program up to its "Initial Payment" line), then
  `coffers −= Σ price(selected regiments) + Σ price(hired but not selected) × 10 / 100`. The screen labels are
  `BKTXT 409` "Mission Fee" and
  `410`/`411` "Retainer"/"Total Retainer Cost": a deployed regiment costs its full price for every mission,
  a regiment left in camp costs 10 %.
- **Bankruptcy** (checked when the selection opens): if `coffers + prepaid initial payment` is
  less than the price of the forced regiments, the screen switches to mode 5 and shows `BKTXT 601–603`
  (campaign over, the crowns owned, the minimum needed to sustain the army).
- Availability text: not hired → `BKTXT 415` (available for hire); excluded by the mission
  (`excludeunits`) → 416 (not available), except whoami 29 and 31 (Ceridan, Dwarf Envoy) → 418 (refuses to join)
  and whoami 13, 36, 37 (Gyrocopters) → 420 (engine trouble); destroyed → 417 (wounded).

### 2.4 Recruiting and reinforcements (caravan) ✅ / 🟡

- Recruit window (`gocaravan:recruit`): the Hire/Fire button (`BRTXT 319`/`320`) toggles
  the hired state; when the regiment was not hired on entry the coffers pay (or refund) its price
  immediately. It is enabled only for `forHire` regiments and only when the coffers cover the price.
  Cancel restores the hired state from when the window opened.
- Glue `addtroop:<whoami>=<n>` (117 uses, token `0x62`) adds `n` to the roster's reinforcements (`+0x20`). The
  Reinforcements window (`BKTXT 505` title, 507 available, 508 take)
  offers `min(available, orgsize − (models + wounded))` and moves the taken men
  into `s_size`, subtracting them from `+0x20`. They are not charged separately 🟡: they raise the model count
  and therefore the regiment's price in the next mission fee.
- Leaving the caravan removes every unit of `ARMY.MRC` that is not hired
  and clears all unused reinforcements.
- Glue `addunit:<whoami>` (token 2, 18 uses, e.g. `addunit:5 ; Carroburg Greatswords`) marks a regiment
  `pendingJoin`; the `gocaravan` handler that picks the
  `CaravanAfterMission[WithRecruit]` scripts then copies these regiments from `PLAY.MRC` into `ARMY.MRC`, giving
  `hired=1` to those that are not `forHire` 🟡. They then appear in the recruit window.

### 2.5 Mission payments: the balance sheet programs ✅

The `cash` type selects a program: a zero-terminated list of opcodes (19 programs). The interpreter runs one
opcode per step; each opcode prints a
`BKTXT` label with an amount and updates the running total. Inputs: `MISS` initial/completion/
rate A/rate B, the objective records of `debrief.dbf` (one per letter: a success flag and the four values of the `Result:`
line, called v18/v1C/v20/v24 below), and the bonus counter.

| Op | Label (`BKTXT`) | Amount |
|---|---|---|
| `0x01` | blank line | — |
| `0x0A` | 5002 Mission Total | shows the running total |
| `0x0B` | 5003 Total Final Payment | `max(total, 0)` |
| `0x0C` | 5021 2x Experience Points Awarded | sets the experience multiplier to 2 |
| `0x0D`–`0x13` | 5022 %s Receive +1 Armour rating | whoami 4, 27, 20, 16, 17, 1, 7 (1.4) |
| `0x14` | 5000 Initial Payment | `+initial` |
| `0x15` | 5001 Completion Payment | `+completion` if every required letter (`MISS+0xCC`, up to 2) has success 1, else 0 |
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
  `v20`, `v24`) of objective `L` from `debrief.dbf`. Only `BPMISSION5` uses it
  (`bonusadd:4,V`, the Skaven heads of Patrol).
- `cash` lines with only four numbers (`cash:5,0,5000,0,M`) put `M` into rate B (`atoi` → 0) and leave no
  required letter; their programs do not test completion, so this is harmless ✅ (parser).
- Worked example, the owner's `debrief.dbf` of `bf003` (`A,1,…`, `B,1,80,12,100,12`, `C,1,80,7,100,7`):
  100 + 400 = 500 total; −100 already received; villagers 50 × (12 − 12) = 0; buildings 25 × (7 − 7) = 0;
  final **400**, which the debriefing would add to the 280 in the coffers (the game exited before that under Wine).
- The payment is added when the debrief screen is dismissed: in debrief modes 2 (after
  `playgamewithdebrief`) and 4 (glue `debrief:`) `coffers += final total`; the glue
  `debrief` handlers may also apply the same addition through the window callback 🟡 (whether both run is
  not established).

## 3. Troops, casualties and items

### 3.1 `whoami`: persistent regiment id ✅

- `whoami` (glue field token `0x49`, next to `hired` = `0x4B`) is the regiment's index in the roster table
  (0–37; `BKTXT 300 + whoami` is its name). All the campaign code finds units by it.
- The unit loader shared by both programs (the `set:` key switch) stores `whoami` and `hired` from the unit text ✅.
- In `PLAY.MRC` the 38 regiments carry whoami 0–37 in order; `ARMY.MRC`, `MARCH.MRC` and `debrief.dbf` keep the
  same numbers, and the glue scripts address regiments by it (`addtroop:27=2 ; Merc Crossbowmen`).
- In battle, only when objective `G` is defined with a non-zero first value, the game loads `ARMY.MRC` and, for every
  NPC unit of the battle script (side bits `0x40`) with `whoami < 50`: if the regiment marches with the player the NPC
  is deleted; else if it is in the company the NPC is rebuilt from it (name, stat line including the **current
  model count**, leader profile, psychology, experience `s_Exp`, spells and items); else the NPC is **deleted**
  (corrected October 2026: not kept). Objective `I` does a different artillery swap. Full rules, the affected
  battles and test vectors: `notes/allied_npc_merge.md`.

### 3.2 Joining and leaving ✅

| Glue command | Token | Effect |
|---|---|---|
| `unitjoinmission:<id>` | `0x7E` | copy regiment `id` from `PLAY.MRC` into `ARMY.MRC`, then from `ARMY.MRC` into `MARCH.MRC` (only if not yet present), always with `hired=1` |
| `unitleavemission:<id>` | `0x7F` | remove regiment `id` from `ARMY.MRC` and `MARCH.MRC` (the unit's alive bit is cleared and the file rewritten); its record in `PLAY.MRC` stays |
| `addunit:<id>` | 2 | mark `pendingJoin` (2.4) |
| `forceunits:<ids>` / `excludeunits:<ids>` | `0x88`/`0x89` | `MISS+0xF0` forced list; excluded regiments show "Not available" 🟡 (the glue interpreter ignores both tokens, so the mission window parser reads them) |
| `testforunitinarmy:<id>` / `testforunitinmarch:<id>` | `0x7C`/`0x7D` | glue status := roster `inArmy`/`inMarch` |

Counts in `WND.DLL`: 30 `unitjoinmission`, 24 `unitleavemission` (Carlsson's guards 21, 22, 35 leave after their
escort, …), 20 `forceunits`, 39 `excludeunits`, 18 `addunit`, 117 `addtroop`.

### 3.3 Casualties, wounded and disbanding ✅

> **Exact order and timing:** `notes/casualty_bookkeeping.md` §3 (one state machine, worked examples). Corrected
> below: `Z` clears only this battle's wounded; the heal cap also clears `s_routed`; the commander-dead test.

After a battle (before the debrief screen) and when the debrief is accepted:

1. **Lost models** of a unit = `s_calualties − s_routed`. Of these,
   `wounded = lost × 65 / 100` (integer division, option `dead`) and `dead = lost − wounded`.
   The troop book shows them as `BKTXT 405` "Dead" and 406 "Wounded".
2. **Routed models return**: `s_size += s_routed`, and `s_calualties`, `s_routed`, `s_kills` are reset to 0
   before the army file is written. A regiment's model count for prices is `s_size + s_routed`.
3. **Wounded come back one mission later**: the previous `wounded` (roster `+0x2C`) is moved to
   `returning` (`+0x30`), the new wounded are stored in `+0x2C`, and
   the healing step adds `returning` to `s_size`, capped at `s_orgsize` (at the cap it also clears
   `s_calualties` and `s_routed`). If the battle's objective `Z` succeeded, this battle's wounded are lost (the
   returning wounded of the previous battle still heal)
   (`BKTXT 611`, "the wounded could not be recovered" 🟡 for the text link).
4. **Disbanding** removes a regiment whose `s_size + s_routed` is below `max(1, 20 % of s_orgsize)`,
   unless it is whoami 2 (the Grudgebringer Cavalry with the commander) or has the roster `keep` flag.
5. **Destroyed**: a regiment counts as destroyed when `s_size + s_routed == 0`, or when it is
   artillery with fewer than 2 models; destroyed regiments cannot be selected ("Wounded").
6. **The commander never dies outright**: if whoami 2 is destroyed but has wounded (of this battle), one wounded
   model is returned (`s_routed += 1`, `wounded −= 1`); a `keep` regiment with no models left also gets one model
   back.
7. **Campaign over**: if whoami 2 still has models, routed or wounded of this battle (`notes/casualty_bookkeeping.md` §3.6), the campaign ends when
   objective `G` or `Y` is present and flagged 1; if it has none, the campaign ends when objective `Z` is
   flagged 1, otherwise the commander gets one model back. The end plays movie `death01` (commander dead) or
   `death02`. 🟡 for the meaning of `G`/`Y`/`Z` (defeat conditions written by the battle).

Routed units are therefore not lost: fled models rejoin their regiment, and only the killed share is split
into dead and wounded.

### 3.4 Magic items and spells ✅ / 🟡

- Items and spells are part of the unit text (`addmagicitem:ItemGrudgeBringer`, `addspell:`). The campaign layer
  copies both lists when battle results are merged, and `GAMEF.DLL` copies them into merged NPCs. Items persist
  with the regiment in `PLAY.MRC`/`ARMY.MRC`.
- No rule in the campaign layer awards a new item: the only runtime additions are wizard spells (1.3).
  New items come with the regiments' text definitions (e.g. `Dwarf Hammerers` with `ItemRockSplitter`,
  `Dwarf Envoy` with `ItemArmourOfTheBeard` in `MAXARMY.MRC`) 🟡 (`BKTXT 610`, "%s have found the %s.", suggests a
  found-item message; its user was not located).


## 4.8 The text files in `SAVE/` ✅

All four are INI-style scripts read by the same parser as `.BTS`/`.MRC` (`whshr/script.py`); unit blocks use
`set:` keys. Every unit block is written by an editor-style writer present in both programs, which is why they
contain the `;S_RACE is … are you sure this is right?` comments.

| File | Role | Created from (new campaign) | Written | Read by |
|---|---|---|---|---|
| `PLAY.MRC` | **master roster**: all 38 regiments (whoami 0–37) with their current profile, experience, items, `hired` flag; the persistent state of regiments that are not in the company | `FILE/SCRIPT/MAXARMY.MRC` (copied to `SAVE/PLAY.MRC`) | after each battle, when the debrief is merged into it | `unitjoinmission`, `addunit` (copy into the army) |
| `ARMY.MRC` | **the company**: regiments currently with the Grudgebringers | `FILE/SCRIPT/STRTARMY.MRC` (Grudgebringer Cavalry and Infantry) | troop selection done, debrief done (heal/disband), caravan, join/leave | troop book, troop selection, `GAMEF.DLL` NPC merge |
| `MARCH.MRC` | **marching orders**: the regiments selected for the next battle, with deployment `dir`/`x`/`y` | `FILE/SCRIPT/MARCH.MRC` (45-byte empty `[MERCARMY]` stub) | march order window, debrief modes 3/6 | `GAMEF.DLL` as the player army (`SAVE\MARCH.MRC` in campaign mode, otherwise `script\<name>`) |
| `debrief.dbf` | **battle result** | `FILE/SCRIPT/DEBRIEF.DBF` (46-byte stub) | `GAMEF.DLL` at the end of the battle | debrief screen, balance sheet, `testobjective`, `bonusadd`, army merge |

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

- `GAMEF.DLL` writes one `Result:` line per objective record (format
  `"%s:%c,%d,%d,%d,%d,%d"`, keyword token `0x24` `Result`). Each line carries the objective letter, a success
  flag and four values (called v18, v1C, v20, v24 in this report, in file order). Their meaning depends on the
  objective type 🟡: for `B` (villagers) and `C` (buildings) of `bf003` the pair `80,12,100,12`/`80,7,100,7` reads as
  required %, count at start, current %, count now; `Z,0,28,…` gives 28 = the player's models at the start
  (12 + 16), used by "Payment for all men".
- Surviving units: every living player unit (side bits `0xE0 == 0`) and, when the battle has NPC merging
  enabled, living NPC units with `whoami < 50`. Dead or routed units: the removed-unit list; for
  such NPCs only `s_calualties` is reset to 0 (`s_routed`, `s_kills`, `s_Exp` are kept). Units keep `set:s_calualties/s_routed/s_kills/s_Exp` and the battle
  `dir`/`x`/`y`.
- The owner's file (`bf003`): `A,1` (objective met), `B,1,80,12,100,12`, `C,1,80,7,100,7`, `K,0,13,10,0,39`,
  `R,0,1,0,0,0`, `Z,0,28,2,0,0`; Grudgebringer Cavalry 0 casualties, 11 kills, 165 XP; Infantry 7 casualties
  (→ 4 wounded, 3 dead by 3.3), 20 kills, 80 XP.

## 5. Debrief flow (battle → campaign) ✅

> **Corrections (see `notes/debrief_evaluation.md` §7 and `notes/activity_results.md`):** the mode-4 payment is made by the `debrief:` callback, not by Done; modes 6 (`playgame`, `encounterplaygame`) are never paid; the evaluator table has 41 records and 8 evaluator kinds; "NPC merging enabled" means objective `G` or `I` is defined in the battle.

1. **Before the battle** the mission glue (e.g. `BPMission1`: `setdebrief:2`, `enablebook:0=26`, `autosave:`,
   `encounterplaygamewithdebrief:bf003`) records the debrief evaluator (`setdebrief:n` → `MISS+0xB4 = n − 1`),
   saves slot 5 and starts the battle. `playgame`/`playgamewithdebrief` (tokens `0x65`/`0x67`) start the
   battle; the `encounter*` variants (`0x66`/`0x68`) only store the battle name for the caravan's encounter.
2. **Battle** (`GAMEF.DLL`): loads `SAVE/MARCH.MRC` as the player army, merges NPCs with `ARMY.MRC`,
   and at the end writes `debrief.dbf`.
3. **Return**: chooses the end screen `GameEndScreen`/`GameEndScreenSuccess`/`…Failure` by
   running the mission's debrief evaluator (indexed by `MISS+0xB4`; key `A` → objective A, `T` → evaluator
   result, `Z`/`z` → objective Z), then schedules a debrief step: `withDebrief` → mode 2, without → mode 6;
   the `encounter` variants add the payment callback.
4. **Every debrief step first runs** the campaign-over test (3.3 item 7, `death01`/`death02`), the wounded
   bookkeeping on `debrief.dbf`, the merge of the debrief into
   `PLAY.MRC` (per whoami: copy profile, casualties, routed, kills, experience, spell
   and item lists; routed models back into ranks, counters reset, file written), and the clearing of the
   wounded if objective `Z` succeeded.
5. **Debrief screen**: shows the balance sheet and the troop book (kills, dead, wounded, experience gained).
6. **Done**:
   - modes 2 and 4: `coffers += final payment`;
   - "+1 Armour" rewards (1.4);
   - doubled experience, promotions, new experience baselines (1.2, 1.3);
   - mode 2: merge the debrief into `ARMY.MRC`, then heal and disband; modes 3 and 6:
     the same for `ARMY.MRC` and then, separately, for `MARCH.MRC`, with routed models returned in both
     (`notes/casualty_bookkeeping.md` §3.5);
   - clears `returning` wounded; control returns to the glue script (typically `addtroop:` lines,
     a movie and `gocaravan:select`).
7. Glue `debrief:<n>`/`debriefwithsummary:<n>` (tokens `0x87`/`0x8C`, with `iftrue`/`iffalse` variants
   `0x8D`–`0x90`) set the evaluator like `setdebrief` and open the debrief screen directly in mode 4 or 7 with
   the payment callback; `testobjective:<L>` (`0x8B`) and `testmission:`
   (`0x97`, the evaluator's result) set the glue status for `iftrue*`/`iffalse*` commands. `testmission`
   also appears to run `autosave` 🟡 — its single use is followed by glue that does not depend on it.


## 6. Condensed format description

### Save games `SAVE/savegame.0`–`savegame.5` ✅

Written by `WHSHR.EXE`; slot 5 "Last Game" is the glue `autosave:`.
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
and `[UNITS]` surviving and dead/routed units). A stdlib reader prototype (local) passes both saves (`--check`).
## 7. Mission availability and the caravan scrolls ✅

How many missions a mission window offers, and how many scrolls lie on Dietrich's desk in the caravan.
All of this belongs to the front end (`WHSHR.EXE`); `GAMEF.DLL` is not involved.

### 7.1 Where the missions live

A mission window resource (`MISSIONBP01WINDOW`, `MISSIONENWINDOW`, …) is attached to the map window by
`addobject:res=<name>` in a flow script (glue token `0x0A` with key `res`). Loading it parses the `[MISSION]`
blocks into the window's list of missions: **at most 5 records** per window, and a selected-record index.
There is one such window per window slot (0–7).

Each record has exactly the `MISS` layout of section 4.6 — that is the same struct the chosen mission is
copied into. The four fields that control availability are parsed from `set:<key>=<value>` (the keys are the
shared field names, the same table `GAMEF.DLL` uses, see `notes/game_rules.md`):

| Key | Index | Record offset | Meaning |
|---|---|---|---|
| `res` | 48 | `+0x00` | mission name id (`BRTXT`); **this is also the identity `depend` refers to** |
| `releaseflag` | 72 | `+0xA8` | choosing this mission resumes the flow script |
| `depend` | 76 | `+0xAC` | gate: another mission must have been taken |
| `inactivedepend` | 82 | `+0xB0` | gate: another mission must not be on offer |

The record offsets are consistent with neighbouring keys (`animstartframe` = 60, `animstopframe` = 67 and
`animrestartframe` = 69 land in adjacent fields) and `inactivedepend` = 82 matches the value recorded in
`notes/game_rules.md`.

`+0xA4` is the **taken flag**: it is cleared while a `[MISSION]` block is parsed, and set on the *current*
mission when the player commits to it (when troop selection is confirmed, and when the mission is chosen from the
map window). The chosen `MISS` struct is then copied back over the selected record, so the flag lands in the
window's own record.

Independent confirmation: `savegame.5` was autosaved right after troop selection (section 2.2), and its
`MISS+0xA4` is 1.

### 7.2 The visibility rule ✅

One rule decides everything — it applies to painting a row, hit-testing, the height of the list and the
visible count:

```
visible(window, m):
    if m.taken:                        return False          # already taken
    if m.depend:
        d = first record in this window with res == m.depend
        return d.taken if d else True                        # visible once the dependency is taken
    if m.inactivedepend:
        d = first record in this window with res == m.inactivedepend
        return (not visible(window, d)) if d else True       # visible while the other is NOT on offer
    return True
```

Three things are easy to get wrong:

- `inactivedepend` is **recursive on visibility, not on completion**. "Show me while that mission is not being
  offered" is not the same as "show me while that mission is not done": a mission that is still locked behind
  its own `depend` also counts as not on offer.
- Both lookups scan **only the current window's own records**, and a name id that is not in the window makes
  the mission unconditionally visible. `MISSIONL3WINDOW` relies on this: its single mission carries
  `set:depend=682`, but 682 is not in that window, so the gate is a no-op.
- `depend` and `inactivedepend` are checked in that order and `depend` wins — no shipped mission sets both
  (the one `[MISSION]` that would, `MISSIONENWINDOW` 628, has its `set:depend=662` commented out).

### 7.3 The mission list on the map ✅

The map shows a count of the visible records, refreshed whenever the window is opened or a mission is chosen.
The list itself is a `MissionWindow` child window at `[MISSIONWINDOW] set:x/y` (always 30,15):

- The row height is the height of the `Scroll0` bitmap **rounded up to a multiple of 5**, and the window
  height is row height × visible count.
- One row is painted per visible record, in record order, skipping hidden ones: bitmap `Scroll0`
  for the selected row, `Scroll1` for the others.
- The label is the `BRTXT` mission name, followed by `" (<initial>, <completion>)"` when
  either payment is non-zero, or by `BRTXT 612` when the `cash` type is 15.
- A click's y coordinate maps to the *k*-th visible row, so hidden rows never take clicks.

### 7.4 The caravan scrolls ✅

`CARAVANCOMMON1`, included by every caravan screen (`STARTCARAVAN`, `CARAVANSELECTMISSION`,
`CARAVANAFTERMISSION`, the `INFOCARAVAN*` variants, …), declares three scroll bitmaps:

| Bitmap | Position | `set:depend` |
|---|---|---|
| `CarScroll1` | 521, 271 | 4 |
| `CarScroll2` | 556, 279 | 3 |
| `CarScroll3` | 521, 314 | 2 |

`set:depend` on a `[BITMAP]` is a completely different field from `set:depend` on a `[MISSION]`. A bitmap is
drawn when

```
bitmap.depend == 0 or bitmap.depend <= visible_count
```

where `visible_count` is the cached count of **visible** missions. Hence:

| Missions on offer | Scrolls drawn |
|---|---|
| 0 | – |
| 1 | – |
| 2 | `CarScroll3` |
| 3 | `CarScroll3`, `CarScroll2` |
| ≥ 4 | all three |

**The number of scrolls is `min(max(visible − 1, 0), 3)`, and they fill in reverse order (3, then 2, then 1).**
The shelf has four cubbyholes (verified by compositing the three sprites onto `READBACKGROUNDPIC`): the
bottom-right one (about 557,325) is a scroll **baked into the background art** and always present, and
`CarScroll1` (521,271) top-left, `CarScroll2` (556,279) top-right and `CarScroll3` (521,314) bottom-left are
the three sprites. So the scrolls a player sees equal the missions on offer, up to 4 — a window with a single
mission, including `MISSIONBP01WINDOW`, shows just the baked one. The sprites are 28×28 with palette index 0
(pure blue) as the colour key; drawing them without keying that out gives a blue box.

These three are the only `[BITMAP] set:depend=` in all 535 `WND.DLL` resources, so this mechanism exists
solely for the scroll pile. The cached count is written only when a mission window is added
(`addobject:res=<window>`) and after every mission-window release — so while the player
is in the caravan the value is simply the last count taken on the map.

### 7.5 Why the count changes after a mission while you stay in the same place ✅

A row click selects the mission; it does not release the mission window. The following
release and write-back run later, when `UnwindMission` leaves the after-mission or info caravan:

1. the chosen mission's `releaseflag` is remembered;
2. the `MISS` record is copied over the selected record (this writes the taken flag back);
3. the visible count is recounted and the list refreshed;
4. if the current mission is no longer visible, the first visible record becomes selected;
5. if any mission is still visible, the window height becomes row height × count and the `MissionWindow` is
   destroyed and recreated;
6. with `releaseflag == 0` and something still visible, the player stays on this map window; otherwise the
   flow script resumes.

So a mission **without** `set:releaseflag=1` does not advance the campaign: the flow script stays parked on
`waitforrelease`, the map window and its mission window stay up, and the window is merely rebuilt one row
shorter because the mission just played is now marked taken. That is the "I finished a mission but I am still
in the same place on the map" case, and it is exactly when the caravan scroll pile shrinks. The flow script
resumes only when the chosen mission carries `set:releaseflag=1` (typically the "March to…"/"To Loren"
travel missions, which also carry `replacescript`) or when nothing visible is left.

### 7.6 Worked examples ✅

`MISSIONENWINDOW` (Envoy to Nuln) — 671 Decoy, 672 Bandit's Hideout (`depend=671`), 673 Capture Guy Gourard
(`inactivedepend=672`), 628 To Loren (`inactivedepend=672`, `releaseflag=1`):

| State | Visible | Count | Scrolls |
|---|---|---|---|
| start | 671, 673, 628 | 3 | 2 |
| 671 taken | 672 only (673 and 628 hide because 672 is now on offer) | 1 | 0 |
| 671, 672 taken | 673, 628 | 2 | 1 |

Playing Decoy therefore takes the desk from two scrolls to none, then back to one — a good regression case,
since a naive "`inactivedepend` = not completed" reading gives 3/2/2 instead.

`MISSIONSZWINDOW` (Siege of Zhufbar) — 661 Rat Trap, 662 Slave Assault, 663 The Iron Fort, 665 Escort Engrol
Goldtongue (`depend=662`, `releaseflag=1`):

| State | Visible | Count | Scrolls |
|---|---|---|---|
| start | 661, 662, 663 | 3 | 2 |
| 662 taken | 661, 663, 665 | 3 | 2 |
| 661, 662 taken | 663, 665 | 2 | 1 |
| 661, 662, 663 taken | 665 | 1 | 0 |

Only Escort Engrol releases the flow script, so the player works through the other three in any order while
the scroll pile counts down.

## 8. Open questions
> **Historical questions:** issue #24 is closed. These notes preserve the findings; the remaining unknowns are not standing research tasks. Reopen a focused issue only when a shipped feature or reproducible defect needs an answer.


- ✅ `SHDR+0xC8` is `tentpos` (`notes/campaign_tent.md`). ⬜ The two `u32` per script in `STAX`.
- 🟡 Whether the taken flags (`+0xA4`) of the *other* missions in a window survive a save/load. `STAX` stores
  window objects as `nObjects × 0xA0`, far too small for a whole mission window, and a reloaded flow
  script re-runs `addobject:res=…`, which re-parses the `[MISSION]` blocks with the taken flag cleared. Only the
  selected mission's record is restored (from the `MISS` chunk, and only on the next release). This
  predicts that saving and reloading inside a multi-mission window makes already-completed missions reappear
  (and the caravan scroll count jump back up). Needs a Wine session in `MISSIONSZWINDOW` or `MISSIONENWINDOW`
  to confirm; if it reproduces, it is an original bug rather than a rule to copy.
- 🟡 The cached visible count is never reset: `closewindow`/`removeobject:mission` frees the mission window
  without clearing it, so a caravan drawn between a `closewindow` and the next `addobject` would show a
  stale scroll pile. Every shipped flow script issues the two in that order inside one script run, so this was
  not observed — worth a check if the scroll count ever looks wrong by one step.
- 🟡 The meaning of the four `Result:` values per objective type (written by `GAMEF.DLL`; only
  `bf003` is available as a real file). Needed to reproduce penalties exactly.
- 🟡 Whether the debrief payment can be added twice in modes 4/7 (window callback and the Done handler);
  needs a run of the debrief window's Done step or a Wine session.
- 🟡 Objectives `G`, `Y`, `Z` as campaign-defeat conditions, and the exact text shown for "wounded could not be
  recovered".
- 🟡 The per-mission debrief evaluators (a table of 42 entries of `{function, key letter, 3 × u32}` with seven
  distinct evaluator kinds) are described in `notes/debrief_evaluation.md`; they decide success/failure end screens
  and `testmission`.
- ⬜ `BKTXT 610` (item finds) — user not located; `FILE/SCRIPT/ARMY.MRC`, `REVARMY.MRC` roles.
- 🟡 Whether `testmission` also runs `autosave`.
- Not verified at runtime: no save exists after a completed debriefing, so promotions, healing and payment were
  verified by the documented rules and arithmetic only. A Wine session finishing `bf003` would produce the next
  `PLAY.MRC`/`ARMY.MRC` and coffers 680 as a direct test.
