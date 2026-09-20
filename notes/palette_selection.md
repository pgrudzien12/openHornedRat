# Front-end palette selection: which palette is active on which screen

Behavioral specification of how the campaign front end chooses the 256-colour palette its bitmaps are painted with: the `GLUE*` /
`WIND*` pairs selected by `[POSITION] set:palindex`, the palette embedded in a bitmap, the `BOOK` and `BK2` pairs of the built-in
screens, the orphan `GLUEREND`, and the Windows system-colour slots. It closes the "palette choice" gap of
`notes/glue_runtime_architecture.md` §5 and the open question at the end of `notes/fonts_glue.md` §3. Marks: ✅ read from the
executable and confirmed by the measurements of §7, 🟡 read from the executable but not observable in shipped data, ⬜ open.

Sources: the palette-setting, window-opening and window-state-restore routines of `WHSHR.EXE` (read as research input; no code
reproduced), a scan of all 535 `WND.DLL` resources, and `scripts/glue_palette_check.py` over the 717 bitmaps of `BITMAP.DLL`.

## 1. The rule in one table ✅

There is exactly **one application palette** (256 entries) for the whole front end. Bitmaps never carry their own colours onto the
screen: they are painted by copying their **pixel indices** (index 0 is the transparent key), and each index shows the colour of the
*current application palette*. A bitmap's embedded colour table is used only as a **source** when the rule below says so.

| Event | New application palette (indices 10-245) |
|---|---|
| Start of the program, and any restore of id 0 or an unknown/negative id | `STANDARD.PAL` (236 entries, all of 10-245) |
| A **top-level** window opens (`openwindow`, hotspot/mission `res:`, built-in launcher) with `palindex = N`, `1 ≤ N ≤ 9` | pair N: `WIND<name>.PAL` (106-245) + `GLUE<name>.PAL` (10-105); name table in §2 |
| ... with `palindex = 0` or absent | `STANDARD.PAL` (both halves) |
| ... with `palindex < 0` (only `-1` occurs) | the **colour table of the window's first bitmap** (indices 10-245 of that DIB) |
| A **child** window opens (`opensubwindow`) | unchanged |
| Built-in screens (§4): troop selection, debrief, magic book, encyclopedia, credits | pair 1 (`BOOK`) |
| Built-in army/roster book | pair 9 (`BK2`) |
| Leaving troop selection / debrief back to the map | pair 2 (`MAP`), then the context pop restores the saved id (§3) |
| Mindscape logo picture | pair 4 (`MIND`) |
| Full-screen pictures: start/title picture, end pictures (plain, success, failure) | the **colour table of that picture** (the `-1` path) |
| Restoring a pushed `RUN` context | the id that was active at the push (§3) |
| Movie playback | all of 10-245 black, then the film's own palette per frame (§5) |

Indices **0-9 and 246-255 are never taken from any file**: they are the Windows *static system colours* (§2.2). `GLUEREND.PAL`
is never used (§6).

## 2. Building the palette ✅

### 2.1 Palette ids

A palette id is an integer (`palindex` value; also passed literally by built-in screens). Loading id `N`:

| id | Upper half 106-245 from | Lower half 10-105 from |
|---|---|---|
| 0 | `STANDARD.PAL` (whole 10-245) | `STANDARD.PAL` again (same result) |
| 1 | `WINDBOOK.PAL` | `GLUEBOOK.PAL` |
| 2 | `WINDMAP.PAL` | `GLUEMAP.PAL` |
| 3 | `WINDCAR.PAL` | `GLUECAR.PAL` |
| 4 | `WINDMIND.PAL` | `GLUEMIND.PAL` |
| 5 | `WINDEND.PAL` | `GLUEEND.PAL` |
| 6 | `WINDTITL.PAL` | `GLUETITL.PAL` |
| 7 | `WINDGAME.PAL` | `GLUEGAME.PAL` |
| 8 | `WINDOPT.PAL` | `GLUEOPT.PAL` |
| 9 | `WINDBK2.PAL` | `GLUEBK2.PAL` |
| anything else (≥ 10, negative) | `STANDARD.PAL` (whole 10-245) | not loaded (already covered) |

The `.PAL` records are `[index, R, G, B]` (`FORMATS.md`); an entry is placed at its own index. Of ids 1-9 only 1, 2, 3 (windows) and 4 (logo), 1 and 9 (built-in screens) are reachable (§6): shipped windows use only
`palindex` -1, 1, 2, 3, on 4, 1, 53 and 24 windows respectively; 333 window resources have none because they are children or objects.

### 2.2 The 20 system-colour slots

Indices 0-9 and 246-255 of the application palette are copied from the operating system's current system palette (static colours
kept, `SYSPAL_STATIC`), never from the game files. On a default 256-colour Windows palette they are:

| Index | RGB | Index | RGB |
|---|---|---|---|
| 0 | 0,0,0 | 246 | 255,251,240 |
| 1 | 128,0,0 | 247 | 160,160,164 |
| 2 | 0,128,0 | 248 | 128,128,128 |
| 3 | 128,128,0 | 249 | 255,0,0 |
| 4 | 0,0,128 | 250 | 0,255,0 |
| 5 | 128,0,128 | 251 | 255,255,0 |
| 6 | 0,128,128 | 252 | 0,0,255 |
| 7 | 192,192,192 | 253 | 255,0,255 |
| 8 | 192,220,192 | 254 | 0,255,255 |
| 9 | 166,202,240 | 255 | 255,255,255 |

The engine should use this table (it is the standard Windows default, not game data). The application colours 10-245 are installed
as an identity palette (no colour matching): pixel index `i` shows entry `i`.

Bitmaps that use these slots (besides the transparent 0): `SKULL0`-`SKULL4` (indices 1-9), `DEADSCREEN` (3, 7, 247), `RINGMARK` (7, 255),
`AMBERMAGICPIC` (255) (`scripts/glue_palette_check.py`). Their own colour-table entries at those indices are **ignored**, so those few
pixels show the system colours (the skull icons look different from their authored table; §7.3).

### 2.3 The embedded-palette path (`palindex < 0`, full-screen pictures)

Entries 10-245 of the DIB colour table (RGBQUAD, B G R 0) become the application colours; slots 0-9 and 246-255 are the system slots
as in §2.2. Nothing else of the bitmap changes: it is still painted by index. If the picture cannot be found (unknown or empty name,
which the code passes for "repaint only" calls) the palette is left as it is.

For a **window** with `palindex < 0` the picture is the window's **first `[BITMAP]` record** (in file order, after `[INCLUDE]`
expansion). In shipped data: `MainMenu`, `MainMenuECTS` (`OptionScreen`), `MainMenuMS` (`OptionScreenDEMO`) and `OptionWindow`
(`MoreOptionScreen`). A window with `palindex < 0` and no bitmap leaves the palette unchanged.

## 3. When the palette is set ✅

1. **Top-level window open** (`openwindow`, hotspot or mission `res:`, and the built-in launchers). After the window's resource has been
   loaded and before its native window is created, the palette of §1 is selected from the window's `palindex` (default 0). A child
   window (`opensubwindow`, `addobject` objects) never selects a palette; objects' own `[POSITION]` blocks overwrite the host slot's
   field but nothing looks at it afterwards.
2. **Window-state snapshot.** A `RUN` context push stores the *id that was last selected* (a negative value for the embedded path);
   the matching pop reloads that id **before** the saved windows are recreated. A `WINDOW` context pop re-opens the window by name and
   therefore goes through rule 1 again.
3. **Screens implemented by the front end** select their id when they are created (§4); the troop-selection, debrief and book screens
   are pushed on top of a context, so leaving them pops the previous id.
4. Every selection **replaces** the previous one: there is no palette stack apart from the id stored in each window-state snapshot.

The window's off-screen picture buffer gets its colour table from the application palette **at the moment the window is created**;
since windows are created right after the palette is selected, a window always shows the palette that was active when it opened.

## 4. Built-in screens ✅ (id passed in code)

| Screen | Id | Notes |
|---|---|---|
| Start-up (before the first screen) | 0 | `STANDARD` |
| Mindscape logo | 4 (`MIND`) | logo bitmap matches `MIND` exactly |
| Title / start picture (`GameStartScreen`) | -1 (its own table) | matches no pair |
| End pictures (`GameEndScreen`, `…Success`, `…Failure`) | -1 | chosen from the debrief result (`notes/campaign.md` §5) |
| Troop selection, debrief/army screen | 1 (`BOOK`) | set when the screen is created |
| Back to the map after troop selection / debrief | 2 (`MAP`) | then the context pop applies the saved id |
| Army roster book (`ArmyBook`, `HireOnlyArmyBook`, army records window) | 9 (`BK2`) | |
| Magic book, encyclopedia, credits | 1 (`BOOK`) | |
| Options dialog | window resource with `palindex -1` | embedded path of `MoreOptionScreen` |
| Main menu | window resource with `palindex -1` | embedded path of `OptionScreen` |

## 5. Movies ✅ / 🟡

Before a film starts the front end installs an application palette whose entries 10-245 are black (flagged animatable) ✅, then updates
it from the film's own palette as frames are decoded 🟡 (`notes/si_omni.md`, `whshr/smacker.py`). After the film the window-state pop
(§3 rule 2) restores the saved id. The palette a film uses therefore never depends on `palindex`.

## 6. Unused and orphan palettes ✅

- `GLUEREND.PAL` is referenced by nothing: not by name, not by an id (there is no id for it, and no `WINDREND.PAL`). It appears to
  be a leftover of an earlier design of the troop screen (§7.3).
- Ids 5-8 (`END`, `TITL`, `GAME`, `OPT`) are loadable but no shipped resource or built-in screen requests them. The bitmaps that
  match them exactly (`TITLESCREEN` ↔ `TITL`, `ENDSCREEN` ↔ `END`) are not referenced by the executable or by any window
  resource either; the visible title and end pictures use the embedded path. `MIND` (id 4) is used for the logo only.
- No shipped window uses id 0 explicitly; 333 windows have no `palindex` because they are children or objects, and all 78
  `openwindow` targets carry `palindex` 2 (map windows).

## 7. Verification

`python3 scripts/glue_palette_check.py <WARFB> --check` (stdlib). Indices 0-9 and 246-255 are excluded (index 0 is transparent).

### 7.1 Windows against their pair ✅

For every window with `palindex ≥ 1` (own and `[INCLUDE]`d bitmaps; animated bitmaps expanded to all numbered cells), the pixels drawn
with an index whose colour in the bitmap's own table differs from the selected pair:

| `palindex` | Pair | Windows | Used pixels | Mismatching |
|---|---|---|---|---|
| 2 | `MAP` | 53 | 16 579 129 | **0** |
| 3 | `CAR` | 24 | 8 734 892 | **0** |
| 1 | `BOOK` | 1 (`JournalBook`, no bitmaps of its own) | 0 | - |

So the pair that `palindex` selects reproduces the authored colours of every bitmap those windows draw. This is the evidence that
the `WIND`+`GLUE` composition is right, and that `palindex 2/3` correspond to `MAP`/`CAR`.

### 7.2 Bitmaps against all candidates ✅

All 717 bitmaps of `BITMAP.DLL` (all uncompressed 8 bpp), grouped by the candidates that reproduce them exactly:

| Bitmaps | Exact candidates | Examples |
|---|---|---|
| 557 | all of `STANDARD`, `BOOK`, `MAP`, `BK2`, `GLUEREND+WINDBOOK` (they only use colours the pairs share) | animation cells, most `*PIC` |
| 42 | `CAR` | `CARAVAN`, candle and lamp cells |
| 28 | `BK2` | regiment portraits |
| 26 | `MAP` | frame and button pieces |
| 20 | `BOOK` | magic and item pictures |
| 20 | `BOOK`, `BK2`, `GLUEREND+WINDBOOK` | `ARMYBOOK`, tabs, `BOOKSCROLL*` |
| 14 | none (own table: embedded path) | `GAMESTARTSCREEN`, `GAMEENDSCREEN*`, `DEADSCREEN`, `MOREOPTIONSCREEN`, `NAMESCROLL`, `OPTIONBUTTON*` |
| 6 | only `GLUEREND+WINDBOOK` | `REDATABUP`, `RINGMARK`, `SKULL1`-`SKULL4` |
| 1 each | `END`, `MIND`, `TITL` | `ENDSCREEN`, `MINDSCAPELOGO`, `TITLESCREEN` |

Every bitmap that needs the embedded path is a full-screen picture or option-screen art (used by a `palindex -1` window or the picture path). Bitmaps that scripts add with `addobject`/`addanimobject` were not attributed to a specific window; they all sit in the exact-match groups above. Every other bitmap is exactly
reproduced by the pair of the window or screen that draws it.

### 7.3 The one discrepancy 🟡

`RINGMARK`, `REDATABUP` and `SKULL0`-`SKULL4`, drawn by the troop-selection screen, were authored for `GLUEREND` + `WINDBOOK`, but the
screen selects `BOOK` (`GLUEBOOK` + `WINDBOOK`). The two `GLUE` halves differ at 67 of 96 indices; about 5-16 % of the pixels of
these icons use a differing index (mean channel difference about 70). No code path that loads `GLUEREND` was found, and the painter
does not remap colours, so the shipped game shows them with `BOOK` colours (plus the system colours for the skull slots, §2.2). An
engine that wants the authored look could substitute `GLUEREND` for these icons; a faithful renderer keeps `BOOK`.

## 8. Rules for the engine

1. Keep one `AppPalette` (256 RGB entries) and one `palette_id` (an integer, or "embedded"); paint every indexed bitmap and sprite
   by index through it; never use a bitmap's own table except when building the palette by the embedded path.
2. On top-level window open: `palindex ≥ 1` → pair; `0`/absent → `STANDARD`; `< 0` → first bitmap's table (unchanged when none).
   Children and objects do nothing.
3. Fill 0-9 and 246-255 from the table of §2.2 in every case; entry 0 stays the transparent key.
4. Save the current id in each `RUN` context snapshot; on pop reload that id before recreating windows (a saved "embedded" id has
   no table to reload: the original then falls back to `STANDARD`, which changes colours; an engine may instead keep the saved
   palette itself).
5. Built-in screens pass the ids of §4; full-screen pictures use the embedded path.
6. Read `STANDARD.PAL`, `GLUE*.PAL` and `WIND*.PAL` from the installation at run time; do not embed them. Palette names and ids
   belong in one documented table (this note's §2.1).

## 9. Open items

- After the roster book returns to the troop window the palette appears to stay at id 9 (`notes/builtin_widgets.md`); unverified.
- Whether the original game visibly shows the troop-screen icons with `BOOK` colours (§7.3) needs a run under Wine, or a render of
  the troop screen with both palettes to compare against the icons' authored look.
- Palette handling of the battle scene (a separate 3D renderer, `GAMEF.DLL`) is out of scope here.
- The saved-id restore for a snapshot taken while an embedded-palette window was active (§3 rule 2) is reachable only if a script
  pushes a context from such a window; no shipped script does.
