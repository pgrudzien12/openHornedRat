# Campaign tent and dynamic / cell-set glue bitmaps

Behavioral spec of how a glue script's `setbitmap:<Name>` turns into pixels when `<Name>` is not a literal bitmap resource:
the campaign tent (`gettentpos:`, `Tent4`) is one case of a general rule (animated cell sets), and there is exactly one truly
dynamic keyword. Sources: the glue interpreter/parser and its animation tick in `WHSHR.EXE` (read as a research input, no code
reproduced here), all 535 `WND.DLL` scripts, `BITMAP.DLL` resource names (`extracted/pe_resources/BITMAP/bitmaps.json`), the
owner's `SAVE/savegame.5`. Marks: ✅ verified from code and data, 🟡 inferred, ⬜ unknown. Companion notes:
`notes/mission_selection.md` (screens), `notes/data_driven_audit.md` (engine rules), `notes/campaign.md` §6 (save header).

## 1. Summary

1. **`setbitmap:<Name>` is a literal resource name only for static bitmaps.** For an *animated* bitmap (anything with an
   `animstartframe` other than `-1`/absent) `<Name>` is a *base*: the engine strips trailing digits and appends the current
   frame number to get the real resource (`CarLampCell` -> `CARLAMPCELL5`, `CARLAMPCELL4`, ...; `Tent4` -> `TENT3`, `TENT2`, ...).
   ✅ Checked against all 274 `[BITMAP]` blocks: all 160 animated blocks resolve to existing frames; the 114 static ones are
   literal names (5 have no resource, see §7).
2. **The tent is a normal animated cell set plus one substituted field.** `Tent4` -> frames `TENT3..TENT0` (a 4-frame waving-flag
   tent, 16x20). `gettentpos:` does not choose the bitmap; it overwrites the bitmap's x/y from a static table indexed by the
   campaign variable `tentpos`. ✅
3. **`tentpos` is a small campaign state variable**: written only by `set:tentpos=N` in glue scripts, saved in the save header
   (`SHDR` +0xC8, which answers an open item of `notes/campaign.md` §8), read only by `gettentpos:`. The tent is drawn only by
   briefing scripts (46 of them), not by the flow scripts that show the mission list. ✅
4. **`gettentpos` is the only dynamic bitmap keyword** in the scripts. Other dynamic names exist only as built-in windows
   (`BookScroll<n>`, `Skull<n>`, `LoadSaveTent<n>`, the Dietrich cells), §6. ✅

## 2. `tentpos` state

- `set:tentpos=N` (a `set:` key, like `set:animseq=`) stores N in one global. Nothing else modifies it: no auto-advance along
  the trail, no per-map logic. The only other writer is load-game. ✅
- Saved: the save header (`SHDR`, 248 bytes) contains it at +0xC8 (between the checksum at +0xC4 and the window-stack depth at
  +0xCC). `savegame.5` (autosaved during `BPMission1`) holds 0, consistent with `FlowScriptBP01`: it sets 0 first and 1 only
  after the flow is released, which happens after the first mission is taken and nothing is left on offer
  (`notes/campaign.md` §7.5). ✅ (value checked only for 0)
- Values used by scripts (every `set:tentpos`): 0, 1 (BP01, BP03, BP05, BP25, `MissionBP25Window`), 2, 3 (`FlowScriptBP09`),
  4, 5, 6 (`FlowScriptRE`), 7 (`FlowScriptBPBM`, `BMBrief1/2`), 9 (`FlowScriptGF`), 10 (`FlowScriptREWE`, `REMission7`),
  11 (`ZhufbarMission`), 12 (`ZhufbarMission2`), 13 (`ZhufbarMission3`), 14, 15, 18, 19 (`FlowScriptSZENGML`, `EN4_SubScript2`
  uses 18), 20 (`LMission3`, `LastMission`). Not set by any script: 8, 16, 17, 21. ✅
- Flow scripts set it right before adding the next mission window (`set:tentpos=N` ... `addobject:res=Mission...Window` ...
  `waitforrelease:`), so a briefing opened from that mission window sees the value of the *current* map stage.

## 3. `gettentpos:` and the position table

Inside a `[BITMAP]` block the command copies (x, y) from a static table, indexed by the current `tentpos`, into the bitmap's
position when the block is parsed. Consequences:

- ✅ It overrides `set:x/y`, but only those written *before* it in the block. `TentObject01` has `set:x=384`, `set:y=318`
  first, so they are dead values; the table wins.
- ✅ It is evaluated once, when the object is added (`addanimobject:res=TentObject01`), not re-evaluated as `tentpos` later
  changes. A briefing that wants a different position sets `tentpos` first (`BMBrief1/2` do: `set:tentpos=7`, then
  `addanimobject`).
- The table has 21 real entries (0-20) and a 22nd entry (100, 100) that no script reaches. Values are top-left of the 16x20
  bitmap on the 640x480 map. ✅ (Read from the executable's data; each position lands on a route town when composited on `MAP`,
  rendered locally, not committed.)

| tentpos | x | y | tentpos | x | y | tentpos | x | y |
|---|---|---|---|---|---|---|---|---|
| 0 | 405 | 332 | 7 | 367 | 288 | 14 | 505 | 195 |
| 1 | 405 | 332 | 8 | 367 | 288 | 15 | 285 | 187 |
| 2 | 405 | 332 | 9 | 508 | 215 | 16 | 261 | 159 |
| 3 | 452 | 316 | 10 | 351 | 309 | 17 | 285 | 187 |
| 4 | 405 | 332 | 11 | 416 | 243 | 18 | 276 | 238 |
| 5 | 410 | 346 | 12 | 462 | 209 | 19 | 192 | 214 |
| 6 | 415 | 349 | 13 | 493 | 194 | 20 | 244 | 269 |

(21 = 100, 100, unused.) Duplicates (0-2 and 4, 7 = 8, 15 = 17) are as stored. The campaign route runs from the Border Princes
(south-east, 0-6) through the Black Mountains and Worlds Edge (7-14) to Nuln, Loren and Karak Norn (15-20).

## 4. `Tent4`, `bkindex` and animation of the tent block

`TentObject01` (used unchanged by all 46 briefing scripts, `addanimobject:res=TentObject01`):

```
set:x=384  set:y=318          (overwritten, see §3)
gettentpos:
setbitmap:Tent4
set:animstartframe=3  set:animstopframe=-1  set:timecnt=2
set:bkindex=1  setmask:Mask
```

- **`Tent4`** is a cell-set name with a stray digit. The animation code strips trailing digits (`Tent4` -> `Tent`) and appends
  the frame: `TENT3`, `TENT2`, `TENT1`, `TENT0` (16x20 each, present in `BITMAP.DLL`; there is no `TENT4` and there is no
  `Tent` either). ✅
- **Animation** (§5 rule): frames count down from `animstartframe` to 0; `animstopframe=-1` means "keep going" (loop), so the
  tent plays 3, 2, 1, 0 and repeats. Frame period `timecnt`=2 -> 3 animation steps = 150 ms (§5). Looping restarts from
  `animrestartframe`, which no script sets; the built-in animated objects set restart = start, so the tent almost certainly
  cycles 3-0 forever 🟡 (the four frames differ only in the flag's shape: visually a waving flag).
- **`set:bkindex=1`** inside a `[BITMAP]` block is only a flag (the value is ignored, it is stored as 1). It makes the animation
  step first repaint the bitmaps drawn before it that overlap it, so the transparent pixels of the changing frame show what is
  underneath instead of the previous frame 🟡 (from the tick logic; not visually confirmed). Do not confuse it with the
  portrait `[ANIM] set:bkindex` (`notes/mission_selection.md` §9.1), which is a `BACKALL` frame number.
- **`setmask:Mask`** names no resource (there is no bitmap `Mask`): 181 uses, always `Mask`. It behaves as a keyword; the
  glue bitmaps are drawn with palette index 0 as the transparent colour 🟡.

Sprites (`TENT0..3`): a small grey conical tent with a white flag; the four frames are near-identical (flag wave). ✅ (viewed)

## 5. General resolver and animation rule (all `[BITMAP]` blocks)

Per bitmap block the parser stores: name, x, y, `animstartframe` (S), `animstopframe` (E), `animrestartframe` (R),
`timecnt` (T), `looptimecnt` (L), `bkindex` flag, `depend`, mask name. Absent S/E/R/T/L are 0 (zero-initialised) 🟡 for R.

**Static (literal name, drawn as is)** if S = E (both absent -> 0/0, or equal) or S = -1. Used by backgrounds (`Map`,
`Caravan`, `ReadBackgroundPic`), marks (`SmallCross` uses S=-1), scrolls, option screens. Static bitmaps do not tick.

**Animated cell set** otherwise. State: current frame `cur` = S, delay counter = T. On each animation step:

1. if `cur == E`: finished. Redraw the last resource name once and stop (for E >= 0 the last frame shown is E + 1).
2. else if delay > 0: `delay -= 1`.
3. else: (a) if `cur != -1`: name := (name with trailing digits removed) + decimal(`cur`); draw it. (b) if `cur >= 0`:
   `cur -= 1`; if `cur < 0` then (if E == -1: `cur = R`, extra = L; else `cur = -1`). (c) delay := T + extra.

Hence: frames descend S, S-1, ..., E+1 (or ..., 0 when E = -1, then loop); one frame occupies (T + 1) steps; each loop adds L
steps of pause before the next cycle. Trail dots use E = 0 (`BP1aCell` S=5: `BP1ACELL5..1` appear one after the other and
stay on 1). Caravan lamp/candle/eyes/page use E = -1 (loop). ✅ code, ✅ names (all 160 animated blocks resolve; no missing
frame in the range E+1..S).

**Timing:** the glue window has a 25 ms timer. Elapsed time is converted to 25 ms ticks and accumulated; the animation step
runs when at least 2 ticks are pending (remainder kept, extra lag ticks are dropped). So one animation step = 50 ms and
`timecnt` is in 50 ms units. ✅ code. The step does not run while the in-battle/paused global flags are set 🟡.
Examples: `timecnt=1` -> 100 ms per frame; `timecnt=2` (tent) -> 150 ms; trail dots `timecnt=6` -> 350 ms per dot;
`looptimecnt=90` (Dietrich page turn) -> 4.5 s pause + one frame; `looptimecnt=30` (blink) -> 1.5 s. The engine's current
guesses (8 fps, hold 3.0 s, blink 2.0 s) should be replaced by these formulas.

**Cell numbering** differs per family: caravan/Dietrich/tent cells are 0..N-1 (`CARLAMPCELL0..5`), trail cells are 1..N
(`BP1ACELL1..5`, `BP15BCELL1..17`, ...). The rule needs no per-family knowledge: it just asks for `base + n`.

## 6. Names constructed by built-in windows (not glue scripts) ✅

| Built-in | Resource names | Notes |
|---|---|---|
| Dietrich speech / read animations (caravan) | `TalkEyesCell`, `DietMouthCell`, `ReadEyesCell`, `DietBookCell` + frame | same rule as §5, objects created in code with the same fields |
| Troop-book rank icon | `Skull0..4` | from the regiment's experience value (`notes/troop_selection.md`) |
| Book pages | `BookScroll0..2` | page decoration |
| Load/save slots | `LoadSaveTent1..6` | one per save slot; unrelated to `tentpos` |

## 7. Classification of every `setbitmap:` name in the WND scripts

Script-checked (throwaway script over `WND.DLL` text and `BITMAP.DLL` names): 69 distinct names in 274 `[BITMAP]` blocks.

| Class | Names | Count |
|---|---|---|
| **Exact resource** (static, literal) | `CARAVAN`, `READBACKGROUNDPIC`, `TALKBACKGROUNDPIC`, `CARSCROLL1..3`, `MAP`, `MAPTITLE`, `SMALLCROSS`, `OPTIONSCREEN`, `OPTIONSCREENDEMO`, `MOREOPTIONSCREEN`, `BATTLEMAP0`, `CROSS8` | 14 |
| **Numbered cell set** (animated) | 49 sets: caravan `CARCANDLECELL` (0-5), `CARLAMPCELL` (0-5), `DIETBOOKCELL` (0-11), `READEYESCELL` (0-2); all map trail sets, numbered 1..N: `AM1CELL` (6), `BM2CELL` (3), `BM3CELL` (3), `BM4CELL` (20), `BM4ACELL` (12), `BP1ACELL` (5), `BP1BCELL` (5), `BP2CELL` (15), `BP3CELL` (17), `BP3ACELL` (17), `BP5CELL` (16), `BP9CELL` (6), `BP9BCELL` (6), `BP10CELL` (11), `BP13CELL` (8), `BP14CELL` (9), `BP15ACELL` (9), `BP15BCELL` (17), `E1CELL` (16), `EN1CELL` (11), `EN1BCELL` (11), `EN3CELL` (5), `EN3BCELL` (5), `EN4ACELL` (9), `EN4BCELL` (12), `GM1CELL` (7), `GM2CELL` (8), `GM2BCELL` (8), `GM3CELL` (15), `L1CELL` (21), `L2CELL` (9), `L3CELL` (13), `RE1CELL` (3), `RE6CELL` (23), `RE6ACELL` (15), `RE6BCELL` (8), `RE6CCELL` (16), `RE7CELL` (17), `RE8ACELL` (8), `RE8BCELL` (9), `SZ5ACELL` (5), `SZ5BCELL` (14), `WE1ACELL` (5), `WE1BCELL` (20), `WE1CCELL` (16) | 49 |
| **Dynamic / substituted** | `Tent4` (cell set `TENT`, 0-3) + `gettentpos:` | 1 |
| **Unresolved** | `BattleMapBorderLeft/Right/Top/Bottom` (only in `BATTLEMAPBORDER`, a window no other script opens), `SampleJourBook` (`JOURNALBOOK`, whose caravan hotspot is commented out) | 5 |

The unresolved names have no `BITMAP.DLL` resource and no script reaches them, so they are unused leftovers, not an engine
gap. (`BATTLEMAP0` / `MAPBORDER0` exist but the `BattleMapBorder*` resources do not.) ✅

## 8. What the engine should read from data vs a small table

| Item | Source |
|---|---|
| Bitmap name, x, y, `animstartframe`, `animstopframe`, `animrestartframe`, `timecnt`, `looptimecnt`, `bkindex` flag, `depend`, mask | the `[BITMAP]` block (data); absent values default per §5 |
| Static vs animated, frame names, frame count | derived by the §5 rule (`resolve(name, S, E)` -> literal name, or the list `base + n` for n from S down to E+1 (0 when E = -1); missing frame -> report, not crash) |
| Trailing-digit strip | rule in §5 (`Tent4`, `BP1aCell` share it) |
| Frame period and pauses | `(timecnt + 1)` steps of 50 ms, plus `looptimecnt` steps per loop |
| `tentpos` variable | glue interpreter state: set by `set:tentpos`, saved and restored with the save header |
| `gettentpos:` | small table (§3, 22 x/y pairs) in one module citing this note |
| `setmask:Mask`, `bkindex=1` | flags; mask = palette index 0 transparent |
| Built-in dynamic names (`Skull<n>`, `BookScroll<n>`, `LoadSaveTent<n>`, Dietrich cells) | built-in windows, one documented table each |

Suggested handling in `whshr/frontend/glue_bitmap.py` and the briefing/map views: load bitmaps through one resolver that takes
the parsed block (not a bare name), returns either one resource or an ordered frame list, and treats `gettentpos` as a
generic "position source" so that further keywords of that kind would plug in the same way. `BP1aCell`-style trail objects and
`Tent4` then need no special cases; the `FileNotFoundError` for `BP1aCell` comes from treating an animated base name as literal.

## 9. Corrections to earlier notes

- `notes/mission_selection.md` §3 lists `TentObject01` under the map screen with the mission list. No flow script
  (`FlowScript*`) adds it: only the 46 briefing scripts (`*Brief*`) do. The mission-list map has no tent; the flow scripts only
  maintain `tentpos` for the following briefings. The position is the table value, not `set:x/y`.
- `notes/campaign.md` §8 open item "`SHDR+0xC8`": it is `tentpos`.

## 10. Open questions

- 🟡 Default of `animrestartframe` when absent (no script sets it; behaviour needed for the lamp, candle, tent and blink loops):
  inferred equal to `animstartframe`; needs a visual check against the running original.
- 🟡 `bkindex=1` repaint semantics and the `Mask` name (§4).
- 🟡 Whether the animation step is suspended by other conditions than the two global flags; exact trigger of those flags.
- ⬜ `tentpos` values 8, 16, 17, 21: no script uses them (8 and 17 duplicate 7 and 15).
- ⬜ Confirm the tent appears at table positions in the running game, and whether it is drawn above or below trail dots (order
  within the briefing scripts: map, tent, portrait windows, then trail objects).
