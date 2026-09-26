# Native windows: how to construct every built-in screen

Public implementation report for the campaign screens that are **not** described by ordinary `WND.DLL` window data: the
front end opens them through a fixed table of built-in `res:` names (`notes/mission_selection.md` §8.1) or from another
native screen. It complements `notes/builtin_widgets.md` (roster book, Load/Save, Options, marching orders) and
`notes/troop_selection.md`. Each section says what the screen is for, where it appears, how to build it from the user's
installation, which hotspots/cursors/scripts it carries, how it exits, and the engine's status. Nothing here names original
functions or addresses. Scope: the full game only; demo menus/windows (`*Ects`, `*Ms`) are deliberately not researched. Marks: ✅ verified against the game files (and cross-checked), 🟡 read but not observed running,
⬜ open. All numbers are pixels on the 640×480 screen.

## 1. How a hotspot reaches a native window ✅

A hotspot's (or script's) `res:` name is compared **exactly (case-sensitive)** with a table of 15 built-in names; a name not in
the table is opened as a window resource. The launcher pushes the current window on the context stack first (when the hotspot
asks for it), remembers the *caller* window's name and mode, then the built-in destroys all glue windows and runs. A native
window that needs to return (`Done`) re-opens the **caller by name** (palette 2 first); `PopContext`-style exits pop the
context stack instead (`notes/glue_interpreter.md` §7.2). The `script:` line next to `res:` in these hotspots (`encybook.wnd`,
`magic.wnd`, `loadsav2.wnd`, `exit.wnd`, `Null.wnd`, `<Resident>`) names no resource that exists: it is documentation only.

### 1.1 Click cues (shared by every native button and every glue hotspot) ✅

Verified independently of the section drafts. A button press (mouse-down) plays the sound file `binary/glue/speech/B4.WAV`; the
release (mouse-up, only if the pointer is still inside the button) plays `B3.WAV`. Glue hotspots do the same through their
`downsfx` (press) and `upsfx` (release) numbers: every shipped hotspot has `downsfx=4`, `upsfx=3`, so the file name is
`B<number>.WAV` in the speech directory of the glue sounds. Both cues are skipped while a speech line is still playing and when
speech is off (`nospeech`, i.e. the Sound option). Earlier notes and drafts that said "3 on press, 4 on release" were inverted.
For glue hotspots the release cue plays for the hotspot under the pointer at release, even if the press was elsewhere.

## 2. The 15 built-in names: verification of the working table ✅

A scan of every hotspot of all 535 window scripts (targets that are not window resources) reproduces the table exactly, and the
built-in table in the executable holds exactly these 15 names. Corrections and additions to the working table:

| Target | Count and windows (scan) | Verdict |
|---|---|---|
| `NewGame` | 2, `MainMenu` only (the demo menus have none) | ✅ asks the player for the commander's name (modal edit box, 16 characters max); the engine skips the prompt |
| `ExitProcess` | 6: `MainMenu`, `MainMenuEcts`, `MainMenuMs` (2 each) | ✅ closes the application (a close command to the main window) |
| `LoadSaveWindow2` (Load) | 6: main menus | ✅ the working table's stray "(Load)" line is this row: a real window resource that carries `[LOADANDSAVEGAME]`, not one of the 15 |
| `LoadSaveWindow` (Save) | `CaravanCommon2`, `CaravanMs`, `CaravanEcts`, `CaravanDietrich` | ✅ real window resource (backdrop) + native dialog, not one of the 15 |
| `ArmyBook` | 5: `CaravanCommon4`, `CaravanDietrich`, `CaravanEcts`, `CaravanMs`, `Start` | ✅ |
| `HireOnlyArmyBook` | 1: `CaravanCommon5` | ✅ |
| `UnwindMission` | 11 | ✅ |
| `PopAndResume` | 7 | ✅ |
| `AbortGame` | 3: `CaravanCommon1`, `CaravanEcts`, `CaravanMs` | ✅ |
| `DietrichSpeech` | 15 | ✅ **not** one of the 15 built-in names: a separate 2-entry table used with `clickres`/`clickrescnt` (a click makes the speaker talk) |
| `MagicBook` | 4: `CaravanCommon1`, `CaravanDietrich`, `CaravanEcts`, `CaravanMs` | ✅ |
| `EncyclopediaBook` | 5: same four caravans + `Start` | ✅ |
| `OptionsDialog` | 3: `CaravanCommon1`, `MainMenu` ×2 (panel 9's Options button is native, not a hotspot) | ✅ |
| `OptionsDialogDone` | 1: `OptionWindow` | ✅ |
| `Credits` | 2: `MainMenu` | ✅ |
| `PopContext` | 2: `CaravanSelectMission`, `OptionWindow` (Cancel) | ✅ |
| `PopContextCheckResume` | 1: `CaravanContinueMission` | ✅ runs the **same routine** as `PopContext` |
| `NullWnd` | **0 live**; only in commented-out lines of `MainMenuEcts` | ✅ pops one frame and re-opens it (no visible effect) |

The engine-status column of the working table matches the code (`glue_scene._leave_caravan`, `menu_view.TARGET_ACTIONS`):
wired are `NewGame`, `ExitProcess`, `LoadSaveWindow2` (menu), `ArmyBook`, `HireOnlyArmyBook`, `LoadSaveWindow`, `AbortGame`,
`UnwindMission`, `PopAndResume`, and click speech through `clickres`; the rest logs "not yet implemented".

## 3. Credits ✅

**Purpose.** A fixed page of 28 role headings, each followed by up to 8 name lines in three columns, on the book background;
the intro tune plays; one Done button. Changes no state.
**Where.** `MainMenu` only: two hotspots at (98,337) and (501,337), 41×41, `HandCursor`, `res:Credits`, up/down sfx 3/4.
**Construction.**
1. The launcher pushes the main menu and remembers it as caller; all glue windows are destroyed; the tune `intro3` is started
   with repeat count 0, which loops until Done; palette 1 (BOOK).
2. Window: 640×480 at (0,0), class cursor `SwordCursor`, painted through an off-screen bitmap with the application palette.
3. Control: one owner-drawn button, id `0x102`, "Done" (`BRTXT 304`), 84×32 at (525,448), `HandCursor` (the Done slot of
   `notes/builtin_widgets.md` §1); click cues as in §1.1.
4. Drawing, black transparent text: background bitmap `TroopBook` at (0,0); title `BKTXT 9142` centred at y = 23, font slot 6;
   sections 0–8 at x = 50, 9–18 at x = 250, 19–27 at x = 425, every column from y = 50; a section is its heading `BKTXT 9000+n`
   (font slot 6), then its lines at x + 25 (font slot 2), each advancing y by the text height. Line ids (`BKTXT`, 0 ends a list):
   0:[9100] 1:[9100–9104] 2:[9102] 3:[9102,9106] 4:[9107] 5:[9108,9106] 6:[9109,9110] 7:[9111] 8:[9112,9137–9140] 9:[9100]
   10:[9101] 11:[9113,9141,9103] 12:[9100,9103] 13:[9103,9114] 14:[9115–9118] 15:[9119] 16:[9100,9119] 17:[9127,9128,9104]
   18:[9100,9104] 19:[9120] 20:[9143,9120] 21:[9120,9121] 22:[9121] 23:[9122] 24:[9123–9125] 25:[9126] 26:[9109]
   27:[9129,9134,9130,9131,9132,9133,9135,9136]. All ids exist in `BKTXT` (72 ids in 9000–9143); load the text at runtime.
**Asset inventory and glue.**

3b. ASSET INVENTORY ✅ (sizes measured from `BITMAP.DLL`; all loaded from the installation at runtime)
| Asset | Kind | Source | Size / rule | Use |
|---|---|---|---|---|
| `TroopBook` | bitmap | BITMAP.DLL (shared with the troop window) | 640×480, 8 bpp, no transparency | full-window background at (0,0) |
| `GreenATab` / `GreenATabDn0` | bitmap pair | BITMAP.DLL (shared bottom-strip art, `notes/builtin_widgets.md` §1) | 84×32 each, 8 bpp | Done button released / pressed; label `BRTXT 304` drawn on top |
| application palette 1 (BOOK) | palette | `GLUE/*.PAL` (`notes/palette_selection.md`) | 256 entries | set on entry; palette 2 on exit |
| font slot 2 = `PCTEXT.FON` ("Warhammer Font 2") | font | GLUE/ (`notes/fonts_glue.md` §3) | 12 px | name lines |
| font slot 6 = `PCTEXTB.FON` ("Warhammer Font 6", bold) | font | GLUE/ | 12 px | title and section headings |
| `SwordCursor` | cursor | class cursor of the window | | everywhere except the button |
| `HandCursor` | cursor | class cursor of the Done button | | over Done |
| `intro3` tune | music | `binary/music/intro3.mid` (with its SoundFont/FM twin, `notes/music.md`) | repeat count 0 = **loops until Done** (`notes/briefing_dialogue.md`) | started on entry, stopped and discarded on exit |
| click cues 4 (press) / 3 (release) | sfx | `binary/glue/speech/B4.WAV` (590 B) / `B3.WAV` (240 B) | 11025 Hz mono 8-bit | Done press / release inside the button |
| `BKTXT` 9142, 9000–9027, 9100–9143 | strings | BKTXT.DLL | 72 ids | title, headings, name lines |
| `BRTXT` 304 | string | BRTXT.DLL | | Done label |
Shared with other windows: `TroopBook`, `GreenATab*`, fonts, cursors, palette 1. Unique to Credits: the id table and the layout numbers.

3c. ANIMATIONS AND GLUE ✅
No animation, no timer, no scrolling: the page is painted once (and again only when Windows asks for a repaint). The single
time-based element is the tune. Glue: the main menu hotspot's `res:Credits` is matched against the built-in table; the
launcher pushes the menu window and stores its name as the caller; the built-in destroys all glue windows and opens the
native window; the Done command destroys it and re-opens the caller by name (fresh menu, palette 2). Draw order: background,
title, then sections column by column; the button is a child window above the picture.

**Hotspots/scripts.** None: not a glue window; no animation, timer or scrolling; the only click area is Done.
**Exit.** Done destroys the window, stops and discards the tune, sets palette 2 and re-opens the caller (a fresh main menu). No
keyboard handling found.
**Engine.** ❌ inert (`menu_view.TARGET_ACTIONS` has no entry). Imitate `ArmyRecordsScene`: static paint + one button. Tests:
(1) clicking a Credits hotspot shows a scene with 28 sections and title id 9142; (2) Done returns to the main menu and stops the
tune; (3) every id in the table exists in `BKTXT`.
⬜ fonts behind glue slots 2 and 6 in this window.

## Status of this report (research paused)

Done: §1–§3 (dispatch, verified table, click cues, Credits). Detailed per-window specifications for Options, Magic book,
Encyclopedia, New Game / Main Menu, Debrief (post-battle pages), Load/Save and the context-stack built-ins exist as private
research drafts and are still to be condensed into this file. Not yet researched to recreate grade: Roster book (see
`notes/builtin_widgets.md` §2), Troop window (see `notes/troop_selection.md`), Control panel. Deliberately not researched: `DietrichSpeech`
click speech and the demo windows.
