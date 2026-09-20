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
5. **Animated bitmaps run a small countdown state machine, and `addanimobject` of a finite animation blocks the script until it
   ends** (§5). `animrestartframe` defaults to `animstartframe` (the parser sets both when it reads `animstartframe`), `bkindex`
   is a repaint flag, `setmask` is inert. ✅ (code, all shipped scripts)

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
- ✅ A `set:tentpos=1` inside a `[MISSION]` record (`MissionBP25Window`) does nothing: the mission-record parser recognises the
  key and drops it. The same value is set by the flow script that the record's `replacescript` starts (`FlowScriptBP05`), so
  the script author's intent still holds. Only `set:` in a flow/briefing/mission *script* writes `tentpos`.
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

**Decision (project owner):** the table stays **hardcoded** in the engine as one documented table (`TENT_POSITIONS` in
`whshr/glue_runtime.py`, citing this section). It is 22 small coordinate pairs, recorded here as a fact; reading it back out of
`WHSHR.EXE` at run time was judged too close to extracting content from the executable for the clean-room policy. Do not add an
executable-table loader for it. This is a deliberate exception to the "read scene data, do not hardcode it" rule of `CLAUDE.md`,
because the values exist only inside the executable, not in any glue script or data file.

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
- **Animation** (§5 rule): `animstartframe`=3, `animstopframe`=-1 (loop), `timecnt`=2. Frames count down 3, 2, 1, 0 and repeat; each is
  shown for `timecnt`+1 = 3 animation steps = 150 ms nominal, so one flag cycle is 600 ms. The restart frame is 3 (the parser sets
  `animrestartframe` to `animstartframe`), so the loop is 3-0 forever. ✅ code. The four frames differ only in the flag's shape.
- **`set:bkindex=1`** in a `[BITMAP]` block is a flag (any value stores 1). When set, each new frame is preceded by a repaint of the
  earlier bitmaps that lie under the object's top-left corner (§5.6), so the transparent pixels of the new frame do not show the
  previous frame. The tent is the only shipped bitmap with the flag, and it is the only animated one whose frames have transparent
  pixels *and* replace each other (172 of 320 pixels are transparent). ✅ code, ✅ frame data. It is unrelated to the portrait
  `[ANIM] set:bkindex` (a `BACKALL` frame number, `notes/mission_selection.md` §9.1).
- **`setmask:Mask`** names no resource (there is no bitmap `Mask`). The parser stores the name and **nothing reads it**: it is inert. ✅
  Transparency does not depend on it: every glue bitmap is drawn with palette index 0 transparent (§5.6).

Sprites (`TENT0..3`): a small grey conical tent with a white flag; the four frames are near-identical (flag wave). ✅ (viewed)

## 5. General resolver and animation rule (all `[BITMAP]` blocks)

Sources: the `[BITMAP]` block parser, the per-window animation step and the window timer handler in `WHSHR.EXE` (read as research
inputs; no code reproduced), all 274 `[BITMAP]` blocks of `WND.DLL`, and the frame bitmaps. Marks as above.

### 5.1 Fields and how the parser fills them ✅

| Key / command | Field | Note |
|---|---|---|
| `setbitmap:<Name>` | base name (max 32 chars) | rewritten by the animation step, §5.2 |
| `set:x`, `set:y` | position | may be overwritten by `gettentpos:` (§3) |
| `set:animstartframe=S` | current frame `cur` **and restart frame `R`** | the parser stores the value into both fields (the two keys share one code path) |
| `set:animrestartframe=R` | restart frame | overrides the value from `animstartframe` only if the line comes *after* it; no shipped script uses it |
| `set:animstopframe=E` | stop frame | `-1` = loop forever; `>= 0` = play down to `E + 1` and stop |
| `set:timecnt=T` | frame period **and** the initial countdown | both set to `T` |
| `set:looptimecnt=L` | extra pause per loop | used only when looping |
| `set:bkindex` | repaint flag | any value stores 1 |
| `set:depend=N` | draw gate (caravan scrolls, `notes/campaign.md` §7.4) | |
| `setmask:<Name>` | stored, never used | inert |
| `gettentpos:` | copies x, y from the tent table | §3 |

All fields are zero when absent, except that `R` follows `S` as above. Every other key in the block is silently ignored (the
parser has an empty case for each). A misspelt key therefore has no effect and no error.

### 5.2 The step (state machine) ✅

Per animation step, for each bitmap in the order they were added:

1. **Static or finished** if `cur == E`: nothing is advanced. If an earlier bitmap was refreshed in this step, redraw this one
   (to keep the drawing order); if the wait flag is set (§5.4), clear it and signal "finished".
2. **Waiting** else if `delay > 0`: `delay -= 1` (and redraw if an earlier bitmap was refreshed).
3. **Draw** otherwise:
   1. if `cur != -1`: name := base name with trailing digits removed + `cur` (stored back, so `Tent4` becomes `Tent3`, then
      `Tent2`, ...); if `cur == -1` the name is used as written;
   2. if the `bkindex` flag is set, repaint underneath (§5.6);
   3. draw the bitmap named in (1);
   4. advance: if `cur >= 0` then `cur -= 1`, and if `cur` is now negative: when `E == -1` set `cur = R` and `extra = L`, else
      set `cur = -1`;
   5. `delay = T + extra` (`extra` is 0 except on the wrap of a looping animation).

Consequences: frames are `S, S-1, ..., E+1` (down to `0` when looping); each frame is on screen `T + 1` steps, except the last frame
of a loop, which is on screen `T + L + 1` steps; a finite animation ends holding frame `E + 1`. `S = E` (both absent) is static and
never ticks. `S = -1` draws the literal name every step (harmless: `SmallCross`). Cell numbering differs per family: caravan,
Dietrich and tent cells are `0..N-1`, trail cells `1..N`; the rule only asks for `base + n`. All 160 animated blocks resolve.
**First-frame delay** ✅ (code): `set:timecnt=T` initialises **both** the period `T` and the initial delay to `T` (a block without
`timecnt` has both 0), so the first step-drawn frame `S` appears on step `T + 1` after the object is added (step 1, at most 50 ms, when
`timecnt` is absent: 36 of the 185 animated blocks). Before that step the window paint draws the **stored base name** as written:
for 153 animated blocks it is not a bitmap (`CarLampCell`, `Tent4`, `TrailBP1a`, ...), so nothing is drawn until the first step; for 32
blocks it is a real bitmap (`Cross8` with `S = 7`, used by the `Mark*Object` cross markers) and that picture (the extra frame 8) is visible
from the moment the object is added until step `T + 1` replaces it with frame 7. A looping animation's delay after the wrap is `T + L`
(§5.2), not the initial value.

### 5.3 Timing and pausing ✅

The glue window runs a 25 ms timer. Each timer message computes `ticks = floor(elapsed / 25 ms)`, re-bases its reference to a 25 ms
boundary and adds `ticks` to an animation accumulator. When the accumulator holds at least 2, **one** animation step runs and the
accumulator keeps only its odd bit. So the nominal step is **50 ms**; a late message does not run extra steps. The step rate is
bounded by the OS timer resolution (about 55 ms on Windows 9x), so the original's speed was machine dependent. The portrait
sequences use a separate rule with a one-tick unit (`notes/glue_portraits.md` §3.2). An engine should use 50 ms per step unless
a measurement of the running original says otherwise.

Steps do not run while either of two global flags is set: the **paused** flag (the Pause/Resume button, which also pauses the music)
and a **glue busy** flag that is raised while windows are being built, cleaned up, started or shut down and restored afterwards. ✅

### 5.4 `addanimobject` waits for finite animations ✅ code / 🟡 runtime (new)

`addanimobject:res=<Object>` adds the object's bitmaps to the current window, and then: if the object's **last** `[BITMAP]` has
`animstopframe != -1`, that bitmap gets a wait flag and the running script is suspended. On the step where that bitmap reaches its stop
frame (§5.2 case 1) the flag is cleared and the script resumes. Consequences for briefings:

- All trail-dot objects (133 of the 134 objects added by `addanimobject`; `E = 0`) block the script until the dots are drawn, e.g. in
  `BPBrief1` the dots after Dietrich's speech finish before the Commander speaks. `TentObject01` (`E = -1`) does not block.
- The wait is `n * (T + 1) + 1` steps with `n = S - E`: the script resumes one step after the last dot is drawn, without waiting out
  that frame's period. `TrailBP1a` (`S=5`, `E=0`, `T=6`): `5 * 7 + 1 = 36` steps = **1.8 s** nominal, dots at steps 7, 14, 21, 28,
  35.
- Only the last bitmap of the object is checked. `addobject` (the non-animated add) never waits.
- The window timer that finishes the animation is the same one that drives §5.3, so a paused game does not resume.

### 5.5 Worked examples (50 ms steps)

| Bitmap | S | E | T | L | Frames | Period | Cycle |
|---|---|---|---|---|---|---|---|
| `CarLampCell`, `CarCandleCell` (caravan) | 5 | -1 | 1 | 0 | 5, 4, 3, 2, 1, 0 | 2 steps = 100 ms | 12 steps = 0.6 s |
| `TentObject01` `Tent4` | 3 | -1 | 2 | 0 | 3, 2, 1, 0 | 3 steps = 150 ms | 12 steps = 0.6 s |
| `ReadEyesCell` (Dietrich blink) | 2 | -1 | 1 | 30 | 2, 1, 0 | 100 ms each; frame 0 rests 32 steps = 1.6 s | 36 steps = 1.8 s |
| `DietBookCell` (page turn) | 11 | -1 | 1 | 90 | 11 ... 0 | 100 ms each; frame 0 rests 92 steps = 4.6 s | 114 steps = 5.7 s |
| `BP1aCell` (trail dots) | 5 | 0 | 6 | 0 | 5, 4, 3, 2, 1, then holds 1 | 7 steps = 350 ms | 36 steps, ends |
| `Map`, `Caravan`, scrolls (static) | - | - | - | - | literal name | - | - |

The engine's earlier guesses (8 fps, hold 3.0 s, blink 2.0 s) are replaced by these formulas. Trail dots: `BP1ACELL5..1` are cumulative,
each later frame contains the earlier dots.

### 5.6 Compositing, transparency and `bkindex` ✅

- All bitmaps of a window are drawn in list order into one 8-bit window buffer. The blit copies a source pixel **only if its
  palette index is not 0**, for every glue bitmap regardless of `setmask`. Palette index 0 is therefore the transparent colour
  (the extracted PNGs show it as `(0, 0, 255)`).
- Nothing clears the buffer between steps, so a new frame with transparent pixels would leave the old frame's pixels visible.
  The `bkindex` flag prevents that: before drawing the new frame, every **earlier** bitmap whose rectangle contains this bitmap's
  top-left corner is redrawn at the correct offset, and later bitmaps are redrawn on top. The check is on the top-left corner only.
- In shipped data the flag is needed only for the tent. Lamp, candle, eye and page-turn cells contain no index-0 pixel (fully opaque,
  checked on the extracted frames), and trail-dot frames are cumulative, so leftover pixels are harmless.
- **Engine consequence** 🟡: a renderer that recomposes the whole scene every frame gives the same picture, provided objects are
  drawn in the order they were added (later `addanimobject` calls over earlier bitmaps). The flag can be ignored.

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
| Bitmap name, x, y, `animstartframe`, `animstopframe`, `animrestartframe`, `timecnt`, `looptimecnt`, `bkindex` flag, `depend` | the `[BITMAP]` block (data); absent values default per §5.1 (`animrestartframe` = `animstartframe`) |
| Static vs animated, frame names, frame count | derived by the §5 rule (`resolve(name, S, E)` -> literal name, or the list `base + n` for n from S down to E+1 (0 when E = -1); missing frame -> report, not crash) |
| Trailing-digit strip | rule in §5 (`Tent4`, `BP1aCell` share it) |
| Frame period and pauses | `(timecnt + 1)` steps of 50 ms, plus `looptimecnt` steps on the last frame of a loop (§5.2, §5.5) |
| Script wait on `addanimobject` | finite last bitmap: `n * (timecnt + 1) + 1` steps (§5.4) |
| `tentpos` variable | glue interpreter state: set by `set:tentpos`, saved and restored with the save header |
| `gettentpos:` | small table (§3, 22 x/y pairs) in one module citing this note |
| `setmask:<Name>` | ignore (inert); transparency is always palette index 0 |
| `bkindex` flag | ignore if the whole scene is recomposed each frame (§5.6) |
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
- `notes/glue_portraits.md` §3.2 mentions that portrait sequences advance once per 25 ms message; `[BITMAP]` animations use the 2-tick step of §5.3 here.

## 10. Open questions

- ✅ `animrestartframe` default: equal to `animstartframe` (same code path in the parser); `bkindex` (bitmap): a repaint flag;
  `setmask`: inert; pause conditions: paused flag and glue-busy flag (§5).
- 🟡 Whether a bitmap really shows nothing before its first tick (initial paint with the unresolved base name); compare with the
  running original (first-frame delay `T + 1` steps).
- 🟡 Real step length: nominal 50 ms; the original depended on OS timer resolution. Needs a timing capture of a briefing in
  the running original (Wine).
- 🟡 Draw order of tent versus trail dots: by list order the tent (added first by the briefing scripts) is under the dots.
- ⬜ `tentpos` values 8, 16, 17, 21: no script uses them (8 and 17 duplicate 7 and 15).
- ⬜ Confirm the tent appears at the table positions in the running game.
- ⬜ Hotspot `setmask`: stored like the bitmap one; whether the hit test uses it was not traced (its only use in shipped scripts is
  a comment in `MAPWINDOW`).
