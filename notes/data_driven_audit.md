# Data-driven engine: lessons learned and hardcoding audit

Written while building the caravan, mission map and briefing scenes. The campaign has 44 missions
(41 mission windows, ~100 portrait windows, 28 caravan-type windows); anything typed into a Python constant
for "the first mission" has to be re-typed, and re-verified, for all the others. Audit covers the current working tree
(uncommitted mission-map work included).

## 1. Lessons learned

1. **Scene placement, art names and what a click does are in the glue scripts (`WND.DLL`). Read them; do not copy them
   into constants.** Example that triggered this note: the Dietrich sub-window was placed at a constant (450,25).
   The same speaker appears at 38 different window positions across scenes (`notes/mission_selection.md` §9).
2. **Split every screen into two layers and say which one a number belongs to.**
   - *Data layer* (per scene, in `WND.DLL`/string DLLs): window `[POSITION]`, bitmap names, hotspot rects, `script:`/`res:`
     targets, animation start/stop frames and timing, text ids, `settextcolor`, `index`/`bkindex`/`controlpanel`.
   - *Front-end layer* (constant in the original executable): internal layout of built-in widgets (portrait frame, panel,
     buttons), the `controlpanel` -> panel/buttons/labels/actions table, the mission-list row rule, the `settextcolor` name ->
     colour table. These are *tables*, not scattered literals: one module, one row per value, each row citing the note that
     established it, unverified rows marked.
3. **"Magic values" are still tables.** `controlpanel` has 10 values; the panel and labels of all 10 are decoded. Implement the
   whole table now, with actions filled only where known and the rest disabled, instead of coding the one value the current
   scene needs. Nobody has to redo it for the next 43 missions.
4. **A key that looks unique may not be.** `setbattlescript:bf003` occurs in 21 mission-window records (many use it as a
   placeholder), and 13 battle ids occur in more than one record. Anything keyed by battle id (briefing lookup, asset ids)
   picks the wrong mission. Key by mission: (window resource, record index) or the record's `name_id`.
5. **Prefer reading from the installation at runtime over the extracted PNG folder.** `extracted/` is a local, gitignored
   convenience; three views duplicate `ART_DIR = extracted/pe_resources/BITMAP/bitmap` and load PNGs by hardcoded file name.
   The clean-room policy (`CLAUDE.md`) prefers runtime reads from the user's install.
6. **Take sizes from the assets, not from literals** (`148 * scale`, `120 * scale`, `range(12)`). A bitmap knows its size and
   frame count.
7. **No guessed values in shipped constants without a marker.** Guesses (label colour and offset, fps, hold times) belong in
   one clearly named `PROVISIONAL` block with a link to the open question, so they are easy to grep and replace.
8. **Do not embed original strings as fallbacks** (`_hint` carries English UI sentences). Load them from `BRTXT`; tests should
   inject strings.
9. **When code and notes disagree, verify visually and fix the note in the same change.** Verified from the 136×68
   `FRAMEPANEL3` art: the panel belongs at y = 164 and already contains the complete three-slot section. `FRAMEBOTTOM`
   is its alternative for a no-button window, not an 8 px separator. The current mission-map view draws *both* assets at
   y = 164, overlaying the panel's top strip; it must render exactly one. The button rows (168, 188, 208) are therefore
   consistent with the panel, rather than 8 px off the frame rule.
10. **Trace the decision, not just the first case.** "Row click starts the briefing" was wrong: the code shows a click only
    selects and the Brief button starts the briefing.

## 2. Audit of what is hardcoded now

Legend: **DATA** = should come from a glue script or resource; **TABLE** = a front-end constant that should be one documented
table; **PROV** = guessed value; **KEY** = wrong lookup key; **STRINGS** = embedded original text.

### `whshr/frontend/mission_map_view.py`

| Item | Class | Should come from / become |
|---|---|---|
| `SCRIBE_POSITION = (450, 25)` | DATA | `[POSITION]` of the opened sub-window (`ScribeMWindow` etc.) |
| Which portrait windows are shown at all | DATA | the flow script's `opensubwindow:` commands for the current window |
| Portrait: index 4 / `SCRI`, background frame 15 (`dietrich_portrait`) | DATA + TABLE | `[ANIM]` `index`/`bkindex` of that window; one index -> sprite-set table (only 4 -> `SCRI` verified) |
| `FRAMEPANEL3`, three fixed buttons, labels 313/309/333, actions | TABLE | `controlpanel` table: panel bitmap, slot labels, action per slot (`notes/mission_selection.md` §9.4) |
| `BUTTON_Y`, `PANEL_ORIGIN`, `FRAME_ORIGIN`, `PORTRAIT_ORIGIN`, `BUTTON_X`, 119x20, 136x8, 152 | TABLE | one frame-geometry rule (portrait height, slot count) |
| `MAP.png` by name | DATA | the map window's `setbitmap:` and `palindex` |
| `SCROLL_ORIGIN (30, 15)` | DATA | `[MISSIONWINDOW] set:x/y` |
| `ROW_PITCH = 90`, `SCROLL_SIZE (144, 88)` | TABLE | height of `Scroll0` rounded up to a multiple of 5, computed from the bitmap |
| Label offset (12, 30), size (120, 28), colours `(28,20,12)`, `(210,30,30)`, disabled grey | PROV | `settextcolor` name -> colour table; label rect from the executable's list painter |
| Colour key `(0, 0, 255)` | TABLE | palette index 0 of the glue palette |
| `NATIVE_SIZE (640, 480)` (also in the caravan and menu views) | DATA | root window `[POSITION] vx/vy` |

### `whshr/frontend/caravan_view.py`

| Item | Class | Should come from / become |
|---|---|---|
| Hotspots (`BOOKS`, `GOLD_RECT`, `MISSION_RECT`, `DIETRICH_RECT`, `EXIT_RECT`, `SAVE_RECT`) | DATA | the active caravan window's `[HOTSPOT]` list, selected from the documented `gocaravan` mode mapping |
| Hint id -> action mapping (`150 -> open_mission_map`, `151 -> books`, ...) | DATA | each hotspot's `script:`/`res:` target (`PopContext`, `MagicBook`, `AbortGame`, `LoadSaveWindow`, ...) |
| `CANDLE_POS`, `LAMP_POS`, book (296,260), eyes (312,208), talk eyes (300,200), mouth (288,220) | DATA + TABLE | `[BITMAP] set:x/y` in `CARAVANCOMMON1`/`3`; talk cells are created by the caravan built-in and live in `CARAVAN_BUILTIN_BITMAPS` |
| `ANIMATION_FPS = 8`, `PAGE_HOLD_SECONDS = 3.0`, `BLINK_PERIOD_SECONDS = 2.0` | PROV | `animstartframe`, `animstopframe`, `timecnt`, `looptimecnt` (90, 30) of those bitmaps |
| Scroll positions and thresholds (`SCROLLS`; `caravan_scroll_count` uses `min(.., 3)`) | DATA | `[BITMAP] set:x/y/depend` of `CARAVANCOMMON1`; draw when `depend <= visible missions` |
| Frame counts `range(6)`, `range(12)`, `range(3)` and draw sizes | DATA | asset frame count and image size |
| `_hint` fallback English strings | STRINGS | `BRTXT` only |
| Gold hint special case (id 402) | TABLE | the `res=-1` hotspot's hint |

### `whshr/frontend/menu_view.py` (main menu)

| Item | Class | Should come from |
|---|---|---|
| `BUTTON_ROWS`, `BUTTON_COLUMNS`, `BUTTON_SIZE` | DATA | the 10 `[HOTSPOT]` rects of `MAINMENU` (`set:x/y/vx/vy`) |
| Button -> action list (`new_campaign`, `None` x3, `quit`) | DATA | each hotspot's `res:` (`NewGame`, `LoadSaveWindow2`, `OptionsDialog`, ...) |
| Keyboard shortcuts | ENGINE | acceptable engine feature, keep separate from data |

### `whshr/campaign_scenes.py`, `whshr/campaign_state.py`, `whshr/briefing.py`

| Item | Class | Should come from |
|---|---|---|
| `FIRST_FLOW = "FLOWSCRIPTBP01"` | DATA | the `StartCaravan` hotspot's `res:` |
| `MainMenuScene` hardwires `continuation="open_mission_map"`; `CaravanScene` mode default `"start"` | DATA | the mission-script `gocaravan:<mode>` sequence (parsed as `caravan_entries`, not consumed yet) |
| `INITIAL_COFFERS = 500` | TABLE | executable default; keep, cite `notes/campaign.md` §2.1 |
| `briefing_asset_for(battle)` / `load_briefing(installation, battle)` return the first record with that battle | **KEY** | key by mission record; `bf003` alone matches 21 records |
| `BriefingScene(AssetId(battle))` built from `mission["battle"]` | **KEY** | the record's `res:` briefing script |
| Caravan mode → window-resource mapping | DATA | `gocaravan` mode mapping; each active mode now projects its own window UI |
| `MissionMapScene` action names (`open_briefing`, `open_troop_select`, ...) | ENGINE | fine; the slot -> action mapping goes in the `controlpanel` table |

### `whshr/portraits.py`

`dietrich_portrait` is named and hardcoded for one speaker, index and frame. Generalise to `speaker_portrait(index, bkindex)`
fed by the `[ANIM]` block; keep the index -> sprite-set table separate and small.

## 3. Proposed order of work

1. **Fix KEY problems first** (correctness, not polish): key briefings and battles by mission record. Add a regression test
   with two records sharing `bf003`.
2. **One `glue_ui` data layer**: parse a window script into `{position, bitmaps (x, y, name, anim frames/timing, depend),
   hotspots (rect, hint id, script/res), anim blocks (index, bkindex, controlpanel, colour)}` from `WND.DLL`, with tests against
   the extracted script text. Views render that structure and do not know coordinates. This replaces the per-view rect tables
   for the main menu, the caravan variants and the map window.
3. **One `controlpanel` table module** (all 10 rows, with note references) and the frame-geometry rule, used by the portrait
   sub-window renderer. Add tests that the table matches `notes/mission_selection.md` §9.4 and that a 3-button panel gives the
   240 px window.
4. **Bitmaps from the installation, not from `extracted/` PNGs** (see §3.1 below): a `pe-bitmap` loader behind
   `AssetId("vanilla", "bitmap", name)`, replacing the three copies of `ART_DIR`; sizes and frame counts from the assets.
5. **Move remaining guesses into a `PROVISIONAL` block** with the open question they wait on, and delete the English fallbacks.
6. Only then extend to further windows (briefing screen with the Commander portrait, troop select): they are new data, not
   new code.

### 3.1 Bitmap loading design

Problem: `caravan_view`, `menu_view` and `mission_map_view` load `extracted/pe_resources/BITMAP/bitmap/<NAME>.png`. That folder
is gitignored output of `scripts/pe_extract.py`, so a fresh checkout fails with `FileNotFoundError`, the PNGs bake in the
extractor's colour decisions, and it contradicts `docs/asset_pipeline.md` (original data is read directly from the user's
`WARFB`, scenes use `AssetId`s, never raw paths). Fonts, string tables, cutscenes and `whshr/portraits.py` already load at
runtime; bitmaps are the remaining gap.

Source in the original: `FILE/DLL/BITMAP.DLL`, 717 named 8 bpp bitmap resources (`FRAMEPANEL3`, `CARAVAN`, `SCROLL0`, ...),
each with its own colour table (`notes/fonts_glue.md`: rendering with the embedded table is correct for every image viewed).
Whether the game instead realises one `GLUE` + `WIND` `.PAL` pair per screen (`[POSITION] palindex`) is a hypothesis; verify
that the embedded table matches for the bitmap groups that use another pair before relying on it everywhere.

Mechanism (same pattern as the existing `pe-string-table` and `warhammer-fon` loaders in `default_scene_loaders`):

1. Catalog record `AssetId("vanilla", "bitmap", "<name>")`: source `FILE/DLL/BITMAP.DLL`, resource name, decoder `pe-bitmap`.
2. Move the DIB / PE-resource parsing from `scripts/pe_extract.py` into the `whshr/` package; the script becomes a thin
   wrapper (as `scripts/render_sprites.py` wraps `whshr/sprites.py`).
3. The loader returns width, height, indexed pixels and the RGB palette, with palette index 0 flagged as the colour key. Views
   convert to RGBA; the literal `(0, 0, 255)` key disappears.
4. A scene lists its bitmaps in its `SceneManifest` and gets them with `context.load(id)` (as `CaravanScene` already does for
   its font). The `AssetCache` keeps them by id and source fingerprint.
5. Frame sets (`CarCandleCell0..5`, `DietBookCell0..11`, ...) are enumerated from the resource names, replacing `range(6)` and
   `range(12)`.
6. `extracted/` stays a debug and verification output only. Tests use a small synthetic bitmap or skip when no installation
   is available; no test or view may depend on `extracted/`.

Two separate questions: *how* a bitmap is loaded (this section) and *which* one (the audit in §2). The name comes from the
window script (`setbitmap:Map`, `setbitmap:CarLampCell`); built-in widget art (`Scroll0`, `FrameTop`, `FrameButtonUp`) is a
small documented table.

## 4. Test guidance

- Run scene tests on a mission window **other than `MissionBP01Window`** and a portrait window other than `ScribeMWindow`;
  that catches hardcoding by construction. Parametrise over every mission window and caravan window (headless, no GPU).
- Assert derived values (row pitch, window height, scroll count) against formulas from the notes, not against the literal the
  implementation happens to contain.
