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

| Target | Definitions (full-game windows, scan) | Verdict |
|---|---|---|
| `NewGame` | 2, `MainMenu` | ✅ asks the player for the commander's name (modal edit box, 15 characters max); the engine shows the prompt, starts from a fresh in-memory campaign (state lives only in the JSON save slots; no loose `.MRC` files) and keeps the menu frame on the context stack (§7; `whshr/new_game.py`, `whshr/name_prompt_scene.py`) |
| `ExitProcess` | 2, `MainMenu` | ✅ closes the application (a close command to the main window) |
| `LoadSaveWindow2` (Load) | 2, `MainMenu` | ✅ the working table's stray "(Load)" line is this row: a real window resource that carries `[LOADANDSAVEGAME]`, not one of the 15 (§8) |
| `LoadSaveWindow` (Save) | `CaravanCommon2` (included by ~20 caravan windows), `CaravanDietrich` | ✅ real window resource (backdrop) + native dialog, not one of the 15 (§8) |
| `ArmyBook` | 4: `CaravanCommon4`, `CaravanDietrich`, `Start` (+ demo caravans, not researched) | ✅ (§10) |
| `HireOnlyArmyBook` | 1: `CaravanCommon5` | ✅ (§10) |
| `UnwindMission` | 11 | ✅ (§13) |
| `PopAndResume` | 7 | ✅ (§13) |
| `AbortGame` | 1: `CaravanCommon1` (included by many caravans) | ✅ (§13) |
| `DietrichSpeech` | 14 hotspots with `clickres` + 1 (`CaravanDietrich`, no `clickres`) | ✅ **not** one of the 15 built-in names: a separate 2-entry table (`DietrichSpeech`, `DietrichRead`) used with `clickres`/`clickrescnt` (§14) |
| `MagicBook` | 2: `CaravanCommon1`, `CaravanDietrich` | ✅ (§5) |
| `EncyclopediaBook` | 3: `CaravanCommon1`, `CaravanDietrich`, `Start` (the working table's 5 counted demo caravans) | ✅ (§6) |
| `OptionsDialog` | 3: `CaravanCommon1`, `MainMenu` ×2 (panel 9's Options button is native, not a hotspot) | ✅ (§4) |
| `OptionsDialogDone` | 1: `OptionWindow` | ✅ (§4) |
| `Credits` | 2: `MainMenu` | ✅ (§3) |
| `PopContext` | 2: `CaravanSelectMission`, `OptionWindow` (Cancel) | ✅ (§13) |
| `PopContextCheckResume` | 1: `CaravanContinueMission` | ✅ runs the **same routine** as `PopContext` (§13) |
| `NullWnd` | **0 live** (only in commented-out lines of a demo menu) | ✅ pops one frame and re-opens it (no visible effect) |

The engine-status column of the working table matches the code (`glue_scene._leave_caravan`, `menu_view.TARGET_ACTIONS`); the per-window sections give the exact deviations:
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
**Engine.** ✅ `credits_scene.py` + `frontend/credits_view.py`, wired through `menu_view.TARGET_ACTIONS` (not yet run against a real installation). Tests (`tests/test_credits.py`):
(1) clicking a Credits hotspot shows a scene with 28 sections and title id 9142; (2) Done returns to the main menu and stops the
tune; (3) every id in the table exists in `BKTXT`.
⬜ fonts behind glue slots 2 and 6 in this window.

## 4. Options dialog ✅

Marks: ✅ verified from game data/code and cross-checked, 🟡 inferred / not observed running, ⬜ open. Full-game windows only.

### 4.1 Purpose
A one-screen settings page with eight multi-state toggles (six rendering options, sound effects, music) plus OK and Cancel.
Each click on a toggle cycles its state. OK applies sound/music at once, stores all eight values and returns to the caller;
Cancel returns and changes nothing. The six rendering values are only *stored*; the battle module reads them the next time it starts.

### 4.2 Where it appears
| Opening window | Hotspot / button | Count | Target |
|---|---|---|---|
| `MainMenu` | two Options hotspots at (98,285) and (501,285), 41x41, `HandCursor`, art `OptionButtonUp`/`OptionButtonDown`, sfx 3/4 | 2 | `OptionsDialog` |
| `CaravanCommon1` (shared hotspot set included by about 20 full-game caravan windows: `StartCaravan`, `CaravanSelectMission`, `CaravanContinueMission`, `CaravanAfterMission`, `CaravanAfterEncounter`, the two `...WithRecruit` variants, `CaravanRecruitAndResume`, `CaravanRecruitNoSpeechAndResume`, the `InfoCaravan*` windows) | one hotspot (245,85) 145x65, hint `BRTXT 162`, cursor `HandOpenCursor`, altcursor `HandCloseCursor`, no art | 1 definition | `OptionsDialog` |
| mission-script control panel with `controlpanel` = 9 (Scribe/Commander "TL" map windows of the `*Mission*` scripts) | the panel's middle button "Options" (label `BRTXT 339`, hint `BRTXT 162`); a native button, **not** a hotspot; acts on release | 1 per panel | same dialog |

3 hotspot definitions plus the panel-9 button. The dialog's own exits are hotspots of `OptionWindow`: OK = `OptionsDialogDone`,
Cancel = `PopContext` (the only other user of `PopContext` is `CaravanSelectMission`). Names are matched case-sensitively.

### 4.3 Construction
**Calling sequence.**
- From a hotspot (`res:OptionsDialog`): the launcher pushes the current window on the context stack and records its (name, mode) as
  caller; all glue windows are destroyed; glue window `OptionWindow` opens, then an init step runs once (below). The window's
  `[MIDI]` block starts tune `intro3`; the previously running tune's name is the "remembered tune" restarted on exit.
- From panel 9: unless the game is paused, pending text is drained and speech stopped; the running tune is **always** stopped and
  discarded (name kept as remembered tune); the current frame (a script RUN frame) is pushed and the same window opens with caller
  name `OptionsDialog`.
- Palette: `palindex -1` = keep the picture's own palette (the backdrop's table, entries 10-245 used). 🟡 The front-end palette is
  not re-applied until the caller is re-opened.

**Window.** `[WINDOW]` 640x480 at (0,0); backdrop `MoreOptionScreen` (title "OPTIONS", ten round sockets and the "OK"/"Cancel"
labels are painted in the bitmap, not drawn from strings); font slot 6; text colour white.

**Controls.** Eight toggle hotspots and two exit hotspots (section 4.6), all 41x41 with `OptionButtonUp`/`OptionButtonDown`.

**Drawing.** Backdrop; per hotspot its up bitmap (down bitmap while pressed); each `[TEXT]` block. A `linked:` text draws GMTXT
(`resfile=1`) string `res + state`, where `state` is the current state of the hotspot whose `linkid` equals the block's `res`.
Left-column blocks are right-aligned (format 7, right edge at x + vx = 190, vertically centred in the 41 px row); right-column
blocks are left-aligned (format 8, left edge x = 450). The button art is identical in every state; the state is shown by the text only.

**State.** The eight states exist only in the open window. Click on release: `state = (state + 1) mod count`; only the linked text
row is repainted. Init step: only if the stored options string exists is it parsed (eight comma-separated integers); each toggle's
state is set from it and clamped **above** to `count - 1` (no lower clamp). With no stored string all states are 0.

**Storage.** Registry key `Software\Mindscape\WarHammerFB` (path levels separated by ':' in the game's own notation), string value
`Options` (case-insensitive). Format `v1,v2,v3,v4,v5,v6,v7,v8` (decimal, no spaces). The GOG installer leaves `3,1,1,1,1,1,1,2`.
Read at dialog open and by the battle module; written only by Done (the battle module's in-battle options screen writes the same
value; not covered here).

### 4.4 State <-> stored value
GMTXT id of state `s` of a toggle = `linkid + s` (strings loaded at runtime).
| # | Row (column, y) | linkid | states | GMTXT per state | Stored value from state `s` | State from stored `v` | Meaning |
|---|---|---|---|---|---|---|---|
| v1 | Shading (L, 106) | 36000 | 3 | 36000, 36001, 36002 | `s + 1` (1..3) | `min(2, v - 1)` (no lower clamp: `v = 0` gives -1) | shading level; battle treats 1 as unlit/flat, 2 flat, 3 Gouraud-or-higher; 36003 exists but is unreachable |
| v4 | Texture mapping (L, 160) | 36010 | 2 | 36010, 36011 (on, off) | `1` if `s == 0` else `0` | `1` if `v == 0` else `0` | textures on/off |
| v5 | Perspective correction (L, 214) | 36015 | 2 | 36015, 36016 (on, off) | as v4 | as v4 | perspective-correct mapping |
| v6 | Pixel resolution (L, 268) | 36020 | 2 | 36020 (half), 36021 (full) | `2` if `s == 0` else `1` | `0` if `v == 2` else `1` | render pixel divisor: 2 half, 1 full |
| v2 | Animate scenery (R, 106) | 36030 | 2 | 36030, 36031 (on, off) | as v4 | as v4 | scenery animation |
| v3 | Animate textures (R, 160) | 36040 | 2 | 36040, 36041 (on, off) | as v4 | as v4 | texture animation |
| v7 | Sound effects (R, 214) | 36050 | 2 | 36050, 36051 (on, off) | as v4 | as v4 | effects + speech |
| v8 | Music (R, 268) | 36060 | 3 | 36060, 36061, 36062 (off, FM MIDI, General MIDI) | `s` | `min(2, v)` (no lower clamp) | music mode |

Stored order is v1..v8 as numbered (shading, scenery, animate textures, texture mapping, perspective, pixel resolution, sound,
music), different from the screen order. Counts 3,2,2,2,2,2,2,3. All 19 GMTXT ids exist; 36070 (quit-campaign question) sits in the
same block but is unused here. Caveat 🟡: for pixel resolution state 0 is "half"; for the other two-state rows state 0 is "on".

**Run-time effect of Done** (applied before returning):
- Sound (v7): state 0 clears the switches `nosound` and `nospeech`; state 1 sets both.
- Music (v8): 0 sets `nomusic` and turns MIDI off; 1 clears `nomusic`, sets `fmmidi`, clears `genmidi`, MIDI on (FM variant); 2 clears
  `nomusic` and `fmmidi`, sets `genmidi`, MIDI on (General-MIDI variant).
- Then the string is written to the registry. v1-v6 have no immediate effect (🟡 per `notes/builtin_widgets.md`: level 3 is lowered
  to 2 outside `bf025`; missing-value defaults `2,1,1,1,1,1,1,1`; not re-verified). The same sound/music switching is applied at
  start-up from the stored value.

### 4.5 Asset inventory
| Asset | Kind | Source | Size / frames / transparency | Use |
|---|---|---|---|---|
| `MoreOptionScreen` | bitmap | BITMAP.DLL | 640x480, 8 bpp, 1 frame, own colour table; title "OPTIONS", ten empty round sockets, painted "OK"/"Cancel" | backdrop at (0,0); its table (entries 10-245) becomes the palette (`palindex -1`) |
| `OptionButtonUp` | bitmap | BITMAP.DLL | 41x41, 8 bpp, 1 frame, index 0 transparent; own table differs but is drawn by index under the backdrop palette | idle art of all 10 hotspots; shared with `MainMenu` Options/Credits hotspots (20 uses) |
| `OptionButtonDown` | bitmap | BITMAP.DLL | 41x41, same rules | pressed art; shared |
| `OptionScreen` | bitmap | BITMAP.DLL | 640x480, same colour table as `MoreOptionScreen` | NOT used here (main menu backdrop) |
| `HandCursor` | cursor | `WHSHR.EXE` cursor resource | 32x32; hotspot offset ⬜ | hover cursor over all 10 hotspots; elsewhere window cursor `SwordCursor` |
| `HandOpenCursor` / `HandCloseCursor` | cursors | same | 32x32 | only on the caravan's Options hotspot (hover/pressed) |
| Font slot 6 | font | `GLUE/PCTEXTB.FON`, "Warhammer Font 6", FNT 3.0, 31 pt nominal, cell height 12, ascent 9, avg/max width 9/16, bold | white (255,255,255), transparent bg | all 8 `[TEXT]` rows |
| Palette | palette | embedded in `MoreOptionScreen` | 256-entry DIB table (indices 10-245 used) | set when the window opens |
| `intro3` | music | `binary/music/INTRO3.MID` (16736 B, General MIDI), `INTRO3FM.MID` (13759 B, FM) | one tune per music mode; shared with `Credits` | window `[MIDI]` block; repeat count 0 = loops until replaced or stopped; which file plays follows the music mode |
| click cues | sound | `REMOTE/BINARY/GLUE/SPEECH/B4.WAV` (590 B, ~54 ms) and `B3.WAV` (240 B, ~22 ms); RIFF PCM 11025 Hz mono 8-bit | | `downsfx=4`: press (mouse-down) = `B4.WAV`; `upsfx=3`: release inside the control = `B3.WAV`; skipped while a speech line plays and when speech is off (`nospeech`, i.e. Sound "off") |
| GMTXT ids | strings (table 6, `resfile=1`) | 36000-36002, 36010-36011, 36015-36016, 36020-36021, 36030-36031, 36040-36041, 36050-36051, 36060-36062 | 19 used ids | `[TEXT]` rows, `linkid + state` |
| BRTXT ids | strings (table 4) | 162 (hint, caravan/panel entry points), 339 (panel 9 button label) | | not used inside `OptionWindow` |

Shared: both button bitmaps, the font, the tune, the click cues. Unique: `MoreOptionScreen` and the 19 GMTXT ids. No sprite sets, RCDATA,
speech or portraits.

### 4.6 Animation and glue
Animation: **none** (no `[ANIM]`, no timer, no frame strip). Toggles change only the linked text; pressed art is a plain 2-state swap.
Multi-state binding: hotspot `linkid=L`, `count=N` owns state `s` in `[0,N)`, initial 0. On mouse release inside the hotspot, after
the `upsfx` cue: `s := (s+1) mod N`, and only the rectangle of the `[TEXT]` block with `res == L` (and `linked:`) is repainted. On
press the `downsfx` cue plays and the pressed art shows. Hotspots without `res:` targets (`res=-2`) launch nothing, so toggles never
leave the window. Layers, bottom to top: backdrop, hotspot art, linked text rows; the pointer is the system cursor.

Caller hand-off: the launcher pushes the caller frame (window frame for `MainMenu`/caravans, script RUN frame for panel 9) and
records its (name, mode). Exit pops the dialog frame, then the caller frame; a window frame is re-opened by name (fresh instance), a
RUN frame resumes the mission script if not paused. Order on OK: apply sound/music, save string, destroy windows, restart remembered
tune (if not paused), pop/re-open or resume.

**`OptionWindow` script.** `[POSITION]` x0 y0 vx640 vy480 palindex -1; `[MIDI]` `intro3`; `[BITMAP]` `MoreOptionScreen`. Every
hotspot: `set:res=-2`, cursor `HandCursor`, up `OptionButtonUp`, down `OptionButtonDown`, `upsfx=3`, `downsfx=4`, no altcursor/clickres.
| Hotspot | x | y | vx | vy | res / script | linkid | count |
|---|---|---|---|---|---|---|---|
| OK | 203 | 335 | 41 | 41 | `res:OptionsDialogDone`, `script:<Resident>` | - | - |
| Cancel | 397 | 335 | 41 | 41 | `res:PopContext`, `script:<Resident>` | - | - |
| Shading | 203 | 106 | 41 | 41 | - | 36000 | 3 |
| Texture mapping | 203 | 160 | 41 | 41 | - | 36010 | 2 |
| Perspective | 203 | 214 | 41 | 41 | - | 36015 | 2 |
| Pixel resolution | 203 | 268 | 41 | 41 | - | 36020 | 2 |
| Animate scenery | 397 | 106 | 41 | 41 | - | 36030 | 2 |
| Animate textures | 397 | 160 | 41 | 41 | - | 36040 | 2 |
| Sound effects | 397 | 214 | 41 | 41 | - | 36050 | 2 |
| Music | 397 | 268 | 41 | 41 | - | 36060 | 3 |

`[TEXT]` blocks (`resfile=1` GMTXT, `font=6`, `settextcolor:white`, `linked:`, height 41, width 190), `res` = row linkid: left column
x=0, `format=7`, y 106/160/214/268 -> res 36000/36010/36015/36020; right column x=450, `format=8`, y 106/160/214/268 -> res
36030/36040/36050/36060.

### 4.7 Input and exits
Mouse only (🟡 no keyboard handling). No timeout. Destroying the window discards the eight states, so re-opening shows the saved values.
- **OK** (`OptionsDialogDone`): (1) apply sound/music and save the string; (2) destroy glue windows; (3) if not paused and a remembered
  tune exists, load it (`binary/music/<name>.mid`, FM variant chosen by the loader), repeat 0 = loop, play; (4) pop the dialog frame
  and the caller frame (window caller re-opened by name with fresh init, e.g. the caravan replays its tune; RUN caller resumes the
  script if not paused).
- **Cancel** (`PopContext`): as OK without step (1); nothing applied or saved. Difference: the remembered tune is restarted even when
  paused and then immediately paused; OK skips the restart while paused.

### 4.8 Engine status and deviations
The engine opens a customized Options page from the main menu, caravan, and panel 9. It uses the original
`MoreOptionScreen` backdrop and button art, with three controls: Music, Dialogue, and Sound Effects. Each cycles
through Off, 25%, 50%, 75%, and 100% (default). OK atomically writes `options.json` in the engine's save directory;
Cancel discards the edits. The original six rendering controls and FM/GM choice are not exposed because they do not
map to working engine features. The original registry value is not read or written.

Music controls glue, credits, and debrief tunes; Dialogue controls glue speech and movie WAV cues; Sound Effects
controls battle and missile cues. The Options page leaves the caller's tune playing and applies its new volume on
exit instead of starting the original `intro3` tune. The three controls occupy the first three left-column sockets;
the other sockets remain empty for future settings, such as a campaign difficulty choice.

### 4.9 Test scenarios
1. Given no stored options, when the dialog opens, then every toggle shows state 0 and row texts are GMTXT 36000, 36010, 36015, 36020,
   36030, 36040, 36050, 36060.
2. Given stored `3,1,1,1,1,1,1,2`, when it opens, then shading shows state 2 (36002), each two-state on/off row shows state 0, pixel
   resolution state 1 (36021) and music state 2 (36062).
3. Given the dialog, when Shading is clicked three times, then its text goes 36001, 36002, 36000; the button art does not change.
4. Given state changes and Cancel, when re-opened, then saved values, not edited ones, are shown.
5. Given all rows at state 0 except Sound at state 1 and Music at state 0, when OK is pressed, then speech and effects are muted, music
   is off, and the stored string is `1,1,1,1,1,2,0,0`.
6. Given the dialog opened from panel 9 during a mission script, when OK or Cancel is pressed, then the script resumes if not paused.

### 4.10 Open questions
- 🟡 Whether shading levels 1/2/3 correspond to labels 36000/36001/36002 or 36001/36002/36003 in the battle renderer (an older note says
  level 3 = Phong, contradicting a Gouraud third label); needs a battle-side check.
- 🟡 A fresh install without a stored value shows all state 0 (predicted from the init step only).
- 🟡 Palette behaviour with `palindex -1` on entry and on the first re-open of the caller.
- ⬜ Effect of the in-battle options screen (not part of this window).

## 5. Magic book ✅

Marks: ✅ verified, 🟡 inferred / not observed running, ⬜ open. Full-game windows only.
Section 5.7 ("Shared book machinery") is the single description of the text engine, buttons, drop-cap set and paging used by both
this window and the Encyclopedia (section 6). The Encyclopedia has its own opener, tables and paint routine, so "shared" means the
same rules, verified here for the Magic book; differences are listed in section 6. Items marked **[Magic]** are specific to this book.

### 5.1 Purpose
A read-only reference book opened from the caravan with two books: **Spells** (3 entries, the three colleges of magic) and **Items**
(17 magic items). Only entries the company "knows" are shown: a college appears when some unit of `ARMY.MRC` carries a spell of that
college, an item when some unit carries it. Each entry is a double page: picture and blackletter drop-cap title on the left, wrapped
description on the right (may run over several pages). It changes no campaign state except rewriting the two "known entry" flag
lists kept in savegames (5.5).

### 5.2 Where it appears
| Opening window | Hotspot (x, y, vx, vy) | cursor / altcursor | hint | `res:` |
|---|---|---|---|---|
| `CaravanCommon1` (sub-script included via `script:CaravanCommon1` by 20 caravan windows: `CaravanSelectMission`, `CaravanContinueMission`, `CaravanAfterMission`, `CaravanAfterMissionWithRecruit`, `CaravanAfterEncounter`, `CaravanAfterEncounterWithRecruit`, `CaravanRecruitAndResume`, `CaravanRecruitNoSpeechAndResume`, `StartCaravan`, `InfoCaravanLA/LB/REA/REC/BMA/BPC/ENA/ENE/SZA/SZB/WED`) | (0, **246**, 164, **46**) (an older y = 192 is commented out) | `HandOpenCursor` / `HandCloseCursor` | `set:res=158` = `BRTXT 158` | `MagicBook` |
| `CaravanDietrich` (own full window, opened after a battle and debrief) | (0, **192**, 164, **52**) | same | same | `MagicBook` |

Each hotspot also carries `script:magic.wnd`, which does not exist as a resource (documentation only). No `upsfx`/`downsfx`,
`linkid`/`count`/`clickres`. The name `MagicBook` is matched (exact, case-sensitive) as a built-in before any WND resource is tried.
Two hotspot definitions in the full game; the book is reachable from every caravan screen, including the first caravan of a new game.

### 5.3 Construction
**Calling sequence ✅.**
1. The launcher pushes the caravan window on the context stack, remembers the caller **name** and **mode**, destroys all glue
   windows and builds the book with (caller name, mode, file `ARMY.MRC`).
2. Window: class `MagicBookWindow`, 640x480 child of the main window at (0,0), child + thin border, created hidden. Class cursor
   `SwordCursor`; erase-background is fully handled (whole 640x480 painted into an off-screen bitmap and blitted).
3. Glue palette index **1** (`BOOK`) is set right after creation.
4. `ARMY.MRC` is loaded as the working company (same in-memory company the roster book uses).
5. Unless option `testbook` is set, the two known-entry flag lists are recomputed from the company (5.5). With `testbook` the
   recomputation is skipped and flags keep their value (all 1 in a fresh process).
6. For each book: page 0, entry 0; if entry 0 is unknown the current entry becomes the next known one, or **-1** if none.
7. Initial book = first of (Spells, Items) whose current entry is not -1. If neither has a known entry nothing more is built (no
   buttons, hidden window; unreachable with shipped data since the company always holds the commander cavalry's item). Otherwise
   the five buttons and the off-screen bitmap are created, the window is focused and shown, and the first page is painted.
8. Music: nothing started or stopped by the book (🟡 the caravan's tune keeps playing / is restarted by the caravan's `[MIDI]` block on
   re-open). No speech, no animation.

**Window ✅.** 640x480 at (0,0). Background `EncyBook` (640x480, 8-bit) drawn first on every paint. Colours come from the current
application palette (palette 1), never from a bitmap's own table. Text: transparent background, colour **RGB (67,47,39)** (set by the
title routine on every paint, inherited by the body). Title font = glue slot **5** (`GLUE/GOTHTEXT.FON`, "Warhammer Font 5",
blackletter, height 40, ascent 32). Body font = slot **2** (`GLUE/PCTEXT.FON`, "Warhammer Font 2", height 12, ascent 9, weight 700).
Emphasis font for `@...#` spans = slot **6** (`GLUE/PCTEXTB.FON`, height 12). Page areas: left x = 50..290, right x = 350..590 (240
wide each); top y = 35, bottom limit y = 410. The off-screen bitmap is repainted in full on each state change; only (0,0)-(640,440)
is invalidated, so the button strip (y >= 448) is not erased on paging.

**Controls ✅.** Owner-drawn buttons, class cursor `HandCursor`, 84x32 at y = **448**, common button rules in 5.7:
| id | Label (`BRTXT`) | x | Art (up / pressed) | Enabled when | Action |
|---|---|---|---|---|---|
| `0x108` **[Magic]** | 334 Spells | 14 | `VioletATabUp` / `VioletATabDn0` | current book = Items **and** Spells has a known entry | switch to book 0 (own remembered entry and page) |
| `0x109` **[Magic]** | 335 Items | 104 | `GreenATabUp` / `GreenATabDn0` | current book = Spells **and** Items has a known entry | switch to book 1 |
| `0x102` Done | 304 | 350 | `GreenATabUp` / `GreenATabDn0` | always | exit (5.6) |
| `0x101` Back | 301 | 440 | `BlueATabUp` / `BlueATabDn0` | page > 0, or page 0 and an earlier known entry exists | previous page / entry |
| `0x100` Next | 300 | 530 | `RedATabUp` / `RedATabDn0` | next page exists, or last page and a later known entry exists | next page / entry |

Enable state is recomputed at the end of every paint. Spells/Items buttons exist even when their book is empty (then disabled).

**Drawing per paint, in order ✅ (geometry) / 🟡 (glyph-metric-dependent y):**
1. `EncyBook` at (0,0).
2. **Title + picture** of the current entry (left page). Picture bitmap from the entry table (5.5); title = `BKTXT` id
   **200 + 50*book + entry** (Spells 200..202, Items 250..266; all 20 exist). Picture x = (240 - w)/2 + 50.
   - If **h + 3 < 250** (h <= 246) and title block height + 3 < 125 (always true): the picture is bottom-anchored, y = 285 - (h+3) =
     282 - h, and the title block starts at y = **288** (directly below the picture).
   - Otherwise (h >= 247): picture and title are centred vertically together in y = 35..410 (375 tall): with B = title block height,
     picture y = (375 - (B + h + 5))/2 + 35, title y = picture y + h + 5 (title still below).
   - Title block: first letter is a drop cap from `FancyLetters` (5.7), the rest in slot 5 to the right of the cap; every line whose top
     y < title y + cap height is indented by the cap width. The block is centred in x = 50..290 by its widest line (including the cap),
     lines left-aligned inside it, width limit 240. B = max(text height, cap height) (cap 74, or 87 for titles starting with "P").
     🟡 Simulated: titles 200-202, 254-256, 263, 266 are 1 line (B = 74); 250, 253, 257, 259, 260, 261, 262, 264, 265 are 2 lines
     (B = 79 or 87); 251, 252, 258 are 3 lines (B = 119). Never >= 122.
   - The picture is drawn after the title; raw palette indices, index 0 transparent.
3. **Description** (right page): the BKTXT RCDATA named in the entry table, from the page's start offset, laid out by the text engine
   (5.7) into x = 350, y = 35, 240 wide, bottom y = 410; body slot 2, `@...#` spans slot 6.
   - **Items book only, page 0:** drop cap. The first character is drawn from `FancyLetters` at (350,35) (cap 54..95 x 74..87), text
     starts at index 1, its first line is placed at y = 35 + (capH - 12) and indented by the cap width; later lines start at x = 350
     and the available height shrinks by (capH - 12) so the bottom stays 410. Only the **first** line is indented (rule: line top y <
     y0 + 12).
   - **Spells book:** no cap (per-book flag: book 0 no cap, book 1 cap); texts begin with an `@...#` heading span.
   - Continuation pages (page >= 1): no cap, y = 35, full 240 x 375.
4. Blit the off-screen bitmap, then enable/disable the buttons.

**State read/written ✅.** Read: `ARMY.MRC` at every open; option `testbook`. Written: only the two flag lists, kept in savegames
(`campaign.md` 4.4: lists 2 and 3, 16 and 72 bytes = 3 + 17 flags each followed by a -1 terminator).

`ARMY.MRC` fields used: for every unit block in use (same listing the roster/troop screens show, **hired or not**; 🟡 no `hired` test
is applied) the **unit-level** `addspell:<Id>` and `addmagicitem:<Id>` commands (not the `addleader` sub-block); exposed by
`whshr/script.py` as `unit["spells"]` / `unit["items"]`.

*Spells book (book 0, 3 entries).* Entry i is known iff some unit has a spell of college i (college = spell number: Celestial 1-5,
Bright 6-10, Amber 11-15):
- 0 Celestial: `CelestialWindBlast`, `CelestialAzureBlades`, `CelestialStormOfShemtek`, `CelestialSapphireArch`, `CelestialLightning`;
- 1 Bright: `BrightPiercingBoltsOfBurning`, `BrightBurningHead`, `BrightConflagrationOfDoom`, `BrightFlamestorm`, `BrightFireball`;
- 2 Amber: `AmberFlyingBower`, `AmberTanglingThorn`, `AmberHuntingSpear`, `AmberCurseOfAnraheir`, `AmberFlockOfDoom`.
`GeneralDispel` (16), the five `Waaagh...` and four `Skaven...` spells (17-25) belong to no college and unlock nothing; unknown ids are
ignored. Shipped data: `MAXARMY.MRC`/`PLAY.MRC` carry Celestial, Bright and Amber wizards; `STRTARMY.MRC`/`SAVE/ARMY.MRC` at game
start carry no spells, so the book opens on Items.

*Items book (book 1, 17 entries).* Entry i known iff some unit has `addmagicitem:<Id>` equal (case-sensitive) to the i-th id: 0
`ItemBannerOfWrath`, 1 `ItemBannerOfArcaneWarding`, 2 `ItemBannerOfArcaneProtection`, 3 `ItemArmourOfTheBeard`, 4 `ItemDragonBlade`,
5 `ItemDreadBanner`, 6 `ItemGrudgeBringer`, 7 `ItemSwordOfHeroes`, 8 `ItemArmourOfMeteoricIron`, 9 `ItemBannerOfMight`, 10
`ItemParryingBlade`, 11 `ItemPotionOfStrength`, 12 `ItemShieldOfPtolos`, 13 `ItemRockSplitter`, 14 `ItemSwordOfMight`, 15
`ItemTalismanOfObsidian`, 16 `ItemSwordOfElior`. These are exactly the 17 `Item...` ids of the game's spell/item table. At game start
the two Grudgebringer regiments carry `ItemGrudgeBringer` (entry 6) and `ItemPotionOfStrength` (entry 11), so the first opening shows
those two and the Spells button is disabled.

*Flag lists.* Both are cleared to 0 before recomputing (stale flags vanish). Shipped scripts contain no `enablebook:1=`/`:2=`; the
lists are written only by this recomputation (`enablebook:0=` belongs to the Encyclopedia). With `testbook` the recomputation is
skipped and every flag's static initial value is 1 (🟡 in a process that already recomputed once, that recomputation's flags stay).

**Entry tables ✅** (title id = `BKTXT` 200 + 50*book + entry; pos B = bottom-anchored, C = centred with title):
| book | entry | picture bitmap (w x h) | pos | title id | description RCDATA |
|---|---|---|---|---|---|
| 0 | 0 | `CelestialMagicPic` 129x166 | B | 200 | `SpeCelestialText` |
| 0 | 1 | `BrightMagicPic` 154x154 | B | 201 | `SpeBrightText` |
| 0 | 2 | `AmberMagicPic` 137x157 | B | 202 | `SpeAmberText` |
| 1 | 0 | `BanOfWrathPic` 140x188 | B | 250 | `BanOfWrathText` |
| 1 | 1 | `BanOfArcaneWardingPic` 146x220 | B | 251 | `BanOfArcaneWardingText` |
| 1 | 2 | `BanOfArcaneProtectionPic` 129x183 | B | 252 | `BanOfArcaneProtectionText` |
| 1 | 3 | `ArmOfBeardPic` 136x165 | B | 253 | `ArmOfBeardText` |
| 1 | 4 | `SwoDragonPic` 62x256 | C | 254 | `SwoDragonText` |
| 1 | 5 | `BanDreadPic` 146x220 | B | 255 | `BanDreadText` |
| 1 | 6 | `SwoGrudgebringerPic` 46x249 | C | 256 | `SwoGrudgebringerText` |
| 1 | 7 | `SwoOfHerosPic` 54x252 | C | 257 | `SwoOfHerosText` |
| 1 | 8 | `ArmOfMeteoricIronPic` 100x255 | C | 258 | `ArmOfMeteoricIronText` |
| 1 | 9 | `BanOfMightPic` 130x207 | B | 259 | `BanOfMightText` |
| 1 | 10 | `SwoParryingPic` 50x249 | C | 260 | `SwoParryingText` |
| 1 | 11 | `PotOfStrengthPic` 80x175 | B | 261 | `PotOfStrengthText` |
| 1 | 12 | `ShiOfPtolosPic` 140x140 | B | 262 | `ShiOfPtolosText` |
| 1 | 13 | `SwoRocksplitterPic` 74x174 | B | 263 | `SwoRocksplitterText` |
| 1 | 14 | `SwoOfMightPic` 75x277 | C | 264 | `SwoOfMightText` |
| 1 | 15 | `TalOfObsidianPic` 144x129 | B | 265 | `TalOfObsidianText` |
| 1 | 16 | `SwoOfEliorPic` 77x247 | C | 266 | `SwoOfEliorText` |

The entry index of an item is the identifier order above (BKTXT titles 250-266 and GMTXT item names 31000+ follow the game-rules item
table order, but the entry index is this one).

### 5.4 Asset inventory ✅ (single-frame 8-bit DIBs)
| Asset | Kind | Source | Size / frames / rule | Use |
|---|---|---|---|---|
| `EncyBook` | bitmap | BITMAP.DLL | 640x480, 1 frame, 8 bpp (own table ignored) | background at (0,0); **shared** with the Encyclopedia |
| `FancyLetters` | bitmap (drop-cap sheet) | BITMAP.DLL | 640x480, 1 frame; 30 glyph rects (5.7) | title cap and (Items) description cap; shared with roster book / Encyclopedia / Credits-style pages |
| `VioletATabUp` / `VioletATabDn0` | bitmap | BITMAP.DLL | 84x32 each | Spells button; shared (roster Stat/Info via `PurpleATab`, Hire/Fire) |
| `GreenATabUp` / `GreenATabDn0` | bitmap | BITMAP.DLL | 84x32 | Items and Done; shared |
| `BlueATabUp` / `BlueATabDn0` | bitmap | BITMAP.DLL | 84x32 | Back; shared |
| `RedATabUp` / `RedATabDn0` | bitmap | BITMAP.DLL | 84x32 | Next; shared |
| Spell pictures (3) | bitmap | BITMAP.DLL | `CelestialMagicPic` 129x166, `BrightMagicPic` 154x154, `AmberMagicPic` 137x157 (palette group `62e60fe3`) | left page, all bottom-anchored; unique |
| Item pictures (17) | bitmap | BITMAP.DLL | table in 5.3 (palette group `1f678eee`) | left page; unique |
| Description texts (20) | RCDATA | `BKTXT.DLL`, names in 5.3 | 115-1848 bytes, latin-1, `\r\n`, `@...#` spans (spells), ends at ESC | right page; unique (Encyclopedia uses other names in the same DLL) |
| Titles (20) | string | `BKTXT` 200-202, 250-266 | one line, first letter A-Z | title block |
| Button labels | string | `BRTXT` 300 Next, 301 Back, 304 Done, 334 Spells, 335 Items | | captions |
| Hint | string | `BRTXT` 158 | | caravan hotspot hint |
| Fonts | font | slot 2 `GLUE/PCTEXT.FON` (12 px), 5 `GLUE/GOTHTEXT.FON` (40 px), 6 `GLUE/PCTEXTB.FON` (12 px) | proportional bitmap | body / title / `@` spans; button labels use slot 2 |
| Text colours | colour | | (67,47,39) book text; (255,255,0) enabled label; (192,192,192) disabled label | |
| Palette | palette | glue palette 1 (`BOOK`: `GLUE/GLUEBOOK.PAL` / `WINDBOOK.PAL` pair) on entry; 2 on exit | | whole window |
| Cursors | cursor | `SwordCursor` (window), `HandCursor` (buttons), `HandOpenCursor` / `HandCloseCursor` (caravan hotspot); 32x32 1-bpp cursors of `WHSHR.EXE`, hotspot (0,0) | | |
| Click cue press | speech wav | `BINARY/GLUE/SPEECH/B4.WAV` (11025 Hz mono 8-bit, 0.05 s) | | mouse-down on a button |
| Click cue release | speech wav | `BINARY/GLUE/SPEECH/B3.WAV` (11025 Hz mono 8-bit, 0.018 s) | | mouse-up inside the button |
| Music | - | none started by the book | | |

### 5.5 Animation and glue
**No animation** (no timer, `[ANIM]`/`[MIDI]`/`[INIT]` block, scrolling or hover effect other than cursor and pressed art). Repaint
happens only on entry, button clicks and erase-background.

Glue: (1) caravan hotspot `res:MagicBook` -> launcher pushes the caravan window, records its name and mode, destroys all glue windows
and calls the book with (name, mode, `"ARMY.MRC"`). (2) Init: load `ARMY.MRC`; recompute flags unless `testbook`; reset both books;
choose the initial book; create the five buttons only if some entry is known. (3) Layers bottom to top: `EncyBook`, title block,
picture, description text (with Items cap), buttons (child windows over y = 448..480). (4) No events are sent to the interpreter; button
commands are handled inside the window. (5) Exit (Done, the only exit): destroy buttons and off-screen bitmap and window; if a caller
name is present free the in-memory company, set palette **2** (front-end / MAP), pop one context frame and re-open the caller window
**by name** with the saved mode (fresh instance; the caravan's `[INIT]`/`[MIDI]` run again). An empty caller name re-opens nothing.
Nothing is saved to disk.

### 5.6 Hotspots, input and exits
No hotspots inside the book; no click area on the page; no hint text. Mouse: the five buttons only. Keyboard ✅: none handled (Enter,
Space, Esc, Tab, PageUp/PageDown, Home/End do nothing; differs from the roster book, which handles PageUp/PageDown/Home/End). No
timeouts. Exit only via Done (no close box, no Esc): caller re-opened by name, palette 2. Music untouched (a glue tune with repeat
count 0 loops until replaced or stopped, so the caravan's tune is whatever its `[MIDI]` block starts on re-open). Company freed on
exit; nothing written to `ARMY.MRC`/`PLAY.MRC`.

### 5.7 Shared book machinery (Magic book and Encyclopedia) ✅ / 🟡
**Buttons (all book windows).** Owner-drawn "Button" class, `BS_OWNERDRAW`, class cursor `HandCursor`, 84x32, art chosen by button id
and state (`...Up` normally, `...Dn0` while pressed). A disabled button keeps its Up art (no disabled twin); only the label colour
changes. Label = window text (a `BRTXT` string), font slot 2, centred in the art plus an offset of **(+4,+2) released, (+3,+3)
pressed**; colour RGB (255,255,0) enabled, (192,192,192) disabled. Click cues: on left-button-down cue `B4.WAV`; on left-button-up
inside the button `B3.WAV` (both in the glue speech directory), skipped while a speech line is playing and when speech is off.

**Per-book state.** Current page (0-based), current entry, a vector of page start offsets into the description text (index 0 = 0),
and the first-page-cap flag. Page p+1 starts where the layout of page p stopped; when page p contained the end of the text the start of
page p+1 is recorded as -1 ("last page"). Changing entry clears the vector and sets page 0. Offsets are remembered so Back re-lays a
page identically.

**Text end.** Resource text ends at the first ESC byte (0x1B); everything from it on (raw resources end `... ESC CR LF`, `CR LF ESC`
and/or a trailing 0x1A) is not text. Stripping a trailing 0x1A/0x1B only at the very end is not enough.

**Line layout (Magic book; the Encyclopedia differs on paragraphs and markers, see 6.4).** Measured per line with the font's text extent:
1. Leading spaces, tabs and CR/LF at page start are skipped (start after the cap character on a cap page).
2. Characters are appended to the line. A line ends when (a) the next char is CR or LF, or (b) the next char is a space/tab and adding
   the following whitespace run plus the next word would extend the line beyond x + 240 (strictly greater). A word longer than the
   column is never split.
3. After a break all following spaces, tabs, CR and LF are skipped: **blank lines and paragraph breaks collapse**; no paragraph
   indent or spacing. Line advance = font text height (12).
4. `@` switches to the emphasis font (slot 6), `#` back to slot 2; the markers are never drawn but 🟡 count toward a line's measured
   width (default-glyph width in the body font). Emphasis carries across line breaks.
5. After a line is placed, if the next line's bottom would exceed y0 + height (410) the page ends: if any non-whitespace remains its
   offset is the next page's start, else the text is finished. (A line fits iff its bottom <= 410; 31 lines fit after y = 35.)
6. No hyphenation, justification or body centring.

**Next / Back ✅.**
- Next: on the last page (next start = -1) move to the **next known entry** of the same book, page 0; otherwise page + 1.
- Back: on page 0 move to the **previous known entry**, showing its **first** page (page 0); otherwise page - 1.
- The other book is untouched; no wrap-around (Next disabled on the last page of the last known entry, Back on page 0 of the first).
- 🟡 Estimated page counts (simulation with real PCTEXT widths): Celestial 2 pages (31 + 29 lines), Bright 2 (31 + 14), Amber 2 (31 +
  26); every item 1 page (7-10 lines).

**Drop-cap sheet `FancyLetters` ✅** (x, y, w, h as stored; drawn/measured rectangle is (x, y) to (x + w + 2, y + h + 2)):
A (0,0,60,72) B (64,0,66,72) C (136,0,51,72) D (192,0,52,72) E (248,0,61,72) F (312,0,56,85) G (376,0,56,72) H (440,0,54,82)
I (496,0,50,72) J (552,0,67,83) K (0,88,62,73) L (64,88,59,72) M (128,88,93,71) N (224,88,56,76) O (288,88,46,72) P (336,88,58,85)
Q (400,88,62,82) R (464,88,54,72) S (520,88,45,72) T (568,88,52,72) U (0,176,51,72) V (56,176,58,72) W (120,176,61,72)
X (184,176,45,78) Y (232,176,48,85) Z (288,176,52,72) 1 (344,176,25,72) 2 (376,176,38,72) 3 (416,176,37,72) 4 (456,176,44,72).
Only A-Z and digits 1-4 have glyphs; any other first character draws nothing (all 20 Magic book titles and item descriptions start with an
uppercase letter; initial letters seen: T, A, F).

### 5.8 Engine status and deviations
✅ Implemented in `whshr/magic_book.py`, `whshr/campaign_scenes.py` (`MagicBookScene`) and
`whshr/frontend/magic_book_view.py`. Caravan hotspots open the book; the two tabs derive known entries from the campaign company,
remember their entry and page, and draw the installed pictures, descriptions, drop caps and buttons with palette 1. Done returns to
the parent caravan scene. The engine currently resumes that scene instance, rather than rebuilding the caller by name as the original
does. Button click sounds are not yet played by the book view.

### 5.9 Test scenarios
1. Given the starting company (items `ItemGrudgeBringer`, `ItemPotionOfStrength`), when the book opens, then Items is current on entry 6
   (title id 256), Spells disabled, Back disabled, Next enabled (entry 11 follows), Items disabled (already current).
2. Given a company with a Bright wizard (`GeneralDispel`, `BrightFireball`) and the two starting items, when it opens, then Spells is
   current on entry 1 (title 201), Items enabled, Spells disabled; pressing Items shows entry 6; pressing Spells returns to entry 1
   on the page it was left on. A company whose only wizard has Waaagh spells has no Spells entry.
3. Given Items at entry 11, when Back is pressed on page 0, then the previous known entry (6) shows its first page; when Next is
   pressed on the last known entry's last page, the button is disabled (no wrap).
4. Given a spell entry needing two pages, when Next is pressed, then page 1 shows (start offset = where page 0 stopped); Back returns
   to page 0; on the last page Next moves to the next known entry, page 0.
5. Given any entry, when Done is pressed, then the caller caravan is re-opened by name, palette 2 selected, `ARMY.MRC` unchanged.
6. Data test: 20 titles (`BKTXT` 200-202, 250-266), 20 RCDATA names, 20 picture bitmaps and labels (`BRTXT` 300, 301, 304, 334, 335)
   exist; the item id list equals the game's 17 `Item...` ids; a description ends at its first ESC.
7. Layout: a picture of height <= 246 has bottom at y = 282 and title at y = 288; height >= 247 is centred with title below; the Items
   description's first line is at y = 35 + capH - 12 and indented by the cap width; Spells description has no cap.

### 5.10 Open questions
- 🟡 Exact y of the centred case and of the title block depend on text extents of the blackletter and PCTEXT fonts (simulated from the
  `.FON` glyph widths; formulas exact).
- 🟡 Whether `hired = 0` units count (they appear to).
- 🟡 Whether `@`/`#` markers add width to line measurement (simulated as default-glyph width; small effect on wraps).
- 🟡 Palette-1 rendering of pictures (item and spell pictures belong to different bitmap palette groups; not re-rendered).
- 🟡 Music continuity across the visit.
- ⬜ Empty books (no known entries): the original shows a hidden window with no way out; an engine should return to the caller.
- ⬜ The per-entry "page count" the original records when a text finishes is never read back.

## 6. Encyclopedia ✅

Marks: ✅ verified, 🟡 inferred / not observed running, ⬜ open. Full-game windows only.
Shared machinery (button strip and drawing rules, click cues, drop-cap sheet `FancyLetters` and its glyph table, page-start
bookkeeping, text end at the first ESC, greedy word wrap, Next/Back rules) is described once in section 5.7 (Magic book). This
window has its own opener, tables and paint routine; differences are in 6.3-6.4.

### 6.1 Purpose
A read-only illustrated bestiary (hint `BRTXT 152`): 28 entries about the races and creatures met in the campaign. Each entry is a
picture and title on the left page and a multi-page description on the right. The player pages through the *known* entries; an entry
becomes known when a mission's glue script executes `enablebook:0=<key>`. The window changes no state. It is not a book of places or
items.

### 6.2 Where it appears
Three full-game hotspots, all `res:EncyclopediaBook`, `cursor:HandOpenCursor`, `altcursor:HandCloseCursor`, `set:res=152` (hint
`BRTXT 152`), `script:encybook.wnd` (documentation only, no such resource), no `upsfx`/`downsfx`/`linkid`/`clickres`:
| Opening window | x | y | vx | vy |
|---|---|---|---|---|
| `CaravanCommon1` | 0 | 349 | 180 | 42 |
| `CaravanDietrich` | 0 | 295 | 180 | 42 |
| `Start` (first caravan-style window of a new game; its hotspot list also has `ArmyBook` and a map test window) | 0 | 290 | 165 | 35 |

(`CaravanCommon1` carries an older commented-out `y=295`; the live value is 349.) The next hotspot of `Start` (y=350, `set:res=153`,
`BRTXT 153`) is a different feature (the Journal).

### 6.3 Construction
**Calling sequence ✅.** The launcher pushes the calling window on the context stack, records its name and mode as caller, destroys all
glue windows, then builds the window. If option `testbook` is on, **every** entry flag is set to 1 first (permanently in the live
flag array). Palette index 1 (BOOK) is set on entry. No music, sound or animation command is issued (🟡 the caravan's tune keeps
playing). Initial state: position 0, page 0; position 0 (`Men`) is known from the start, so the book always opens on it.

**Window ✅.** 640x480 child of the main window at (0,0), class cursor `SwordCursor`, no window brush, painted through an off-screen
8-bit bitmap on every erase-background. Background `EncyBook` at (0,0). Text colour RGB(67,47,39) (set while painting the title, so it
covers the body), transparent background. Fonts: slot 2 (`GLUE/PCTEXT.FON`, "Warhammer Font 2", cell 12, ascent 9, avg width 9, bold)
for the body and button labels; slot 5 (`GLUE/GOTHTEXT.FON`, "Warhammer Font 5", blackletter, cell 40, ascent 32, avg width 16) for
the title after the drop cap.

**Controls ✅.** Three shared owner-drawn buttons (drawing, offsets, colours and click cues: section 5.7):
| Id | Label | Position, size | Art | Enabled |
|---|---|---|---|---|
| `0x100` Next | `BRTXT 300` | (530,448) 84x32 | `RedATab` | not last page of the entry, or last page and a later known entry exists |
| `0x101` Back | `BRTXT 301` | (440,448) 84x32 | `BlueATab` | page > 0, or page 0 and an earlier known entry exists |
| `0x102` Done | `BRTXT 304` | (350,448) 84x32 | `GreenATab` | always |

Enable rules are re-evaluated after every paint of the right page. Next is disabled on the last page of the last known entry; Back on
page 0 of position 0.

**Entry table ✅.** 28 entries in a fixed display order (position 0..27). Each has a key 0..28 = its index in the Text/Pic name
tables; `enablebook:0=<key>` addresses the key. The flag array has 29 entries (keys 0..28) plus a `-1` terminator (30 u32 = the
120-byte `BK01` save chunk). Key 11 (`GoblinShaman`) exists in the name tables and `BKTXT` but is **not in the display order**: it can
never be shown and no script enables it. Defaults: keys 0, 6, 10, 21, 28 known from the start (others 0).
Title = `BKTXT 100 + key` (all 29 ids exist). Description = RCDATA of `BKTXT.DLL` named `<Name>Text` (79 RCDATA in that DLL, 29 belong
to this book, the rest to the Magic book/troops). Picture = bitmap of `BITMAP.DLL` named `<Name>Pic` (none larger than 243x244):
| Pos | Key | Title id (BKTXT) | Text RCDATA | Picture | Known when: scripts that run `enablebook:0=<key>` |
|---|---|---|---|---|---|
| 0 | 28 | 128 | `MenText` | `MenPic` 211x209 | **default** |
| 1 | 6 | 106 | `DwarfText` | `DwarfPic` 201x154 | **default** |
| 2 | 12 | 112 | `GyrocopterText` | `GyrocopterPic` 214x205 | `GMMISSION1`, `GMMISSION2`, `GMMISSION3` |
| 3 | 22 | 122 | `SlayerText` | `SlayerPic` 211x178 | `BPMISSION15` |
| 4 | 1 | 101 | `WoodElfText` | `WoodElfPic` 182x193 | `GMMISSION3`, `LMISSION1` |
| 5 | 10 | 110 | `GoblinText` | `GoblinPic` 137x154 | **default** |
| 6 | 3 | 103 | `DoomDiverText` | `DoomDiverPic` 189x147 | `LASTMISSION`, `REMISSION5` |
| 7 | 8 | 108 | `FanaticText` | `FanaticPic` 187x163 | `LASTMISSION`, `REMISSION5`, `WEMISSION145`, `ZHUFBARMISSION2`, `ZHUFBARMISSION3` |
| 8 | 13 | 113 | `NiteGoblinText` | `NiteGoblinPic` 106x178 | `BPMISSION15`, `LASTMISSION`, `REMISSION3`, `ZHUFBARMISSION` |
| 9 | 14 | 114 | `NiteShamanText` | `NiteShamanPic` 149x233 | `LASTMISSION`, `REMISSION3`, `ZHUFBARMISSION2`, `ZHUFBARMISSION3` |
| 10 | 23 | 123 | `SquigText` | `SquigPic` 156x191 | `BPMISSION15` |
| 11 | 26 | 126 | `WolvesText` | `WolvesPic` 147x221 | `BPMISSION1` |
| 12 | 0 | 100 | `OrcText` | `OrcPic` 223x177 | **default** |
| 13 | 27 | 127 | `BlackOrcText` | `BlackOrcPic` 226x175 | `BPMISSION10`, `REMISSION5` |
| 14 | 2 | 102 | `WarBoarText` | `WarBoarPic` 190x187 | `LASTMISSION`, `REMISSION1`, `ZHUFBARMISSION` |
| 15 | 15 | 115 | `OrcShamanText` | `OrcShamanPic` 240x227 | `LASTMISSION`, `WEMISSION145` |
| 16 | 19 | 119 | `RockLobberText` | `RockLobberPic` 238x178 | `LASTMISSION`, `WEMISSION2`, `ZHUFBARMISSION`, `ZHUFBARMISSION2`, `ZHUFBARMISSION3` |
| 17 | 21 | 121 | `SkavenText` | `SkavenPic` 232x183 | **default** |
| 18 | 4 | 104 | `DoomWheelText` | `DoomWheelPic` 222x242 | `LMISSION1` |
| 19 | 7 | 107 | `EshinText` | `EshinPic` 165x140 | `BPMISSION3` |
| 20 | 20 | 120 | `SeerText` | `SeerPic` 221x227 | `BMMISSION3`, `GMMISSION3`, `LMISSION1` |
| 21 | 16 | 116 | `PackMasterText` | `PackMasterPic` 202x234 | `BPMISSION15` |
| 22 | 17 | 117 | `PlagueText` | `PlaguePic` 159x179 | `LMISSION2` |
| 23 | 18 | 118 | `RatOgreText` | `RatOgrePic` 162x204 | `BPMISSION9` |
| 24 | 25 | 125 | `WarpFireText` | `WarpFirePic` 156x197 | `BMMISSION3`, `BPMISSION15`, `FLOWSCRIPTSZENGML`, `GMMISSION3`, `LMISSION1` |
| 25 | 5 | 105 | `DragonText` | `DragonPic` 243x216 | `SZMISSION5` |
| 26 | 9 | 109 | `GiantText` | `GiantPic` 191x244 | `GMMISSION2` |
| 27 | 24 | 124 | `TrollText` | `TrollPic` 157x236 | `BMMISSION2`, `REMISSION5` |

Each script above is a mission glue window (`[START]` block of a `*MISSION*`/flow resource) that runs before or during the mission
sequence, in the set-up part next to `setdebrief:` / `autosave:` (e.g. `BPMission1` sets key 26 before the battle). Keys 0, 6, 10, 21,
28 and 11 are never enabled by script. No script uses `enablebook:1=` or `:2=` (Magic book lists).

**State ✅.** Read: the 30-word flag array (`BK01` in the WHSV save, `notes/campaign.md` 4.4) and option `testbook`. Written: nothing,
except that `testbook` sets keys 0..28 to 1 in memory when the book opens; being the array that is saved, a later save contains all
entries. `enablebook` only sets (never clears), so the array is monotonic within a campaign. 🟡 The array is initialised from static
defaults at process start and by loading a save; nothing in the New Game path resets it, so flags from an earlier campaign of the same
run survive New Game.

### 6.4 Drawing (differences from the Magic book) ✅ (geometry) / 🟡 (text engine pixel offsets)
Painted in this order on each erase-background (640x480 client area):
1. `EncyBook`.
2. **Title** (left page): `BKTXT 100+key` (max 32 chars), first letter as a drop cap from `FancyLetters` (section 5.7), remaining letters
   in slot 5 to the right of the cap, top aligned to the cap; the line is centred in x = 50..290 (`x = (240 - lineWidth)/2 + 50`); its
   bottom sits at y = 410 (`y = 410 - max(lineHeight, capHeight)`). (Magic book: title below the picture.)
3. **Picture** `<Pic>` at `x = (240 - w)/2 + 50`, `y = 285 - h` (bottom edge at y = 285). Raw palette indices, index 0 transparent.
   There is no 250x125 "fits" rule here (that is the Magic book's).
4. **Description**, slot 2, x = 350..590, y = 35..410 (375 high):
   - Page 0 only: the first character is a raised drop cap from `FancyLetters` at (350,35), size (glyph w + 2) x (glyph h + 2); it is
     skipped in the text; the first text line is indented by the cap width, its top at `y = 35 + capHeight - lineHeight` (bottom
     aligned with the cap's); only that line is indented, later lines start at x = 350; available height is `375 - (capHeight -
     lineHeight)`. **Every** entry has a cap (the Magic book only for Items).
   - Pages 1..n: no cap, text from (350,35), height 375.
   - Wrapping: greedy word wrap on space/tab (a word is a maximal run of non-space characters; a line breaks before a word that would
     extend beyond x = 590). Whitespace runs between lines are swallowed. A CR or LF ends the line and starts a new **paragraph**: no
     blank line, but indented by **3 x the width of the letter "X"** in the body font, on every page (the Magic book collapses
     paragraph breaks). Line height = text height. A page is full when the next line would end below y = 410; the next page starts at
     the next non-whitespace character; if only whitespace remains the page is the last one. No `@...#` spans in this book.
   - Texts: ASCII with `\r\n` paragraph breaks (0-3 per entry), no ESC, no bytes above 127; the first character of every entry is a
     letter A-Z (glyphs exist for A-Z and 1-4 only). 🟡 Texts of 328-2154 bytes need 1-4 pages (not counted per entry).
5. Blit the off-screen bitmap.

### 6.5 Asset inventory ✅ (from the `BITMAP.DLL` catalogue and resource dumps)
All bitmaps are 8 bpp, single frame, drawn as raw palette indices through the current application palette (own tables unused), index 0
transparent, no colour map.
| Asset | Kind | Source | Size / frames / rule | Use | Shared? |
|---|---|---|---|---|---|
| `EncyBook` | bitmap | BITMAP.DLL | 640x480, 1 frame, opaque | (0,0), first layer | with the Magic book |
| `FancyLetters` | bitmap | BITMAP.DLL | 640x480, 1 frame; 30 glyph rects (5.7) | title cap and page-0 cap | all book-like windows |
| `RedATabUp` / `RedATabDn0` | bitmap | BITMAP.DLL | 84x32 each; no disabled twin | Next `0x100` at (530,448) | roster book, troop window, ... |
| `BlueATabUp` / `BlueATabDn0` | bitmap | BITMAP.DLL | 84x32 each | Back `0x101` at (440,448) | shared |
| `GreenATabUp` / `GreenATabDn0` | bitmap | BITMAP.DLL | 84x32 each | Done `0x102` at (350,448) | shared |
| 28 entry pictures `<Name>Pic` | bitmap | BITMAP.DLL, table in 6.3 | 106..243 x 140..244, 1 frame | left page, x = (240-w)/2+50, y = 285-h | unique |
| `GoblinShamanPic` (key 11) | bitmap | BITMAP.DLL | exists, never drawn | - | unique, unused |
| 28 (+1) descriptions `<Name>Text` | RCDATA | BKTXT.DLL, type 10 | ASCII, 328..2154 bytes, `\r\n`, no terminating NUL in the dump | right page | unique |
| 29 titles | string | BKTXT ids 100..128 (= 100 + key) | <= 32 chars | left page title | unique |
| button labels | string | BRTXT 300 Next, 301 Back, 304 Done | <= 64 chars | button text | shared |
| hotspot hint | string | BRTXT 152 | | caravan hint line | 3 caravans |
| Fonts | font | slot 2 `GLUE/PCTEXT.FON`, slot 5 `GLUE/GOTHTEXT.FON` (6.3) | | body/labels; title | shared |
| Text colours | colour | (67,47,39) title/body; (255,255,0) enabled label, (192,192,192) disabled | | | shared |
| Palette | palette | id 1 = `WINDBOOK.PAL` (upper half, 106-245) + `GLUEBOOK.PAL` (lower half, 10-105) on entry; id 2 (`WINDMAP`/`GLUEMAP`) on exit | | whole screen | shared |
| `SwordCursor` | cursor | WHSHR.EXE, 32x32 1 bpp, hotspot (0,0) | | window class cursor | shared |
| `HandCursor` | cursor | WHSHR.EXE, 32x32, hotspot (0,0) | | over the three buttons | shared |
| `HandOpenCursor` / `HandCloseCursor` | cursors | WHSHR.EXE, 32x32, hotspot (0,0) | | only on the caravan hotspot | shared |
| Click cues | sfx | `B4.WAV` press, `B3.WAV` release (glue speech directory; rules in 5.7) | | button mouse down / up | shared |
| Music, speech | - | none started or stopped | | 🟡 caravan tune untouched | - |

### 6.6 Animation and glue
**No animation** (no timer, frame strip, fade, scrolling or hover effect). Repaint only on erase-background, forced by Next/Back
(region y = 0..440) and window exposure. Only visual state changes: button pressed art and enabled/disabled label colour.
Glue: (1) Trigger: caravan hotspot `res:EncyclopediaBook` is released; the name is tried as a native built-in and matches, so no WND
resource is opened. (2) Hand-over: launcher pushes the current window, stores the caller name (`CaravanCommon1`, `CaravanDietrich`,
`Start`) and mode, destroys glue windows, calls the book with (name, mode); both are handed back on exit. (3) Init: if `testbook`, flags
0..28 := 1; create the window, palette 1; position 0, page 0; create Next, Back, Done; create the off-screen bitmap, focus, show; the
first paint computes page 0 of `Men` and sets Next/Back. (4) Layers bottom to top: `EncyBook`, title (drop cap + text), picture,
right-page cap (page 0), right-page text, buttons. (5) Flags are read-only here: `known(pos) = flag[key(pos)] == 1`; written by
`enablebook:0=<key>`, `testbook` and loading a save (`BK01`), and stored at every save. (6) Events: Next/Back change (position, page)
and repaint; Done exits; nothing reaches the campaign or script interpreter. (7) Exit: destroy buttons, off-screen bitmap and window;
palette 2; pop the pushed context frame; a WINDOW frame re-opens the caller by name (its `[INIT]`/palette/hotspots and `[MIDI]` run
again); a RUN frame would resume the script (never the case for these hotspots).

### 6.7 Input and exits
Mouse only ✅ (🟡 no keyboard handling, no page-turn shortcut, no click action on the pages, no tab stops). Next: on the last page,
clear the page-offset memory, go to the next known entry, page 0; otherwise page + 1. Back: on page 0, go to the **previous known
entry, page 0** (not its last page); otherwise page - 1. After either, repaint y = 0..440. Unknown entries are skipped in both
directions. Done: destroy everything, palette 2, pop the frame, re-open the caller by name (fresh instance). The book's position is not
kept: it always opens at entry 0. No timeout, no autosave, no cue other than the shared button cues.

### 6.8 Engine status and deviations
✅ Implemented in `whshr/encyclopedia.py`, `whshr/campaign_scenes.py` (`EncyclopediaScene`) and
`whshr/frontend/encyclopedia_view.py`. Caravan hotspots open it; the scene reads `book_flags[0]`, visits known entries in display
order and remembers description page offsets. A new campaign seeds the five default keys. The view draws the installed title and
description drop caps, pictures, text and buttons with palette 1. `testbook` is supported by the scene but the engine has no global
option for it yet. Done resumes the existing caravan scene rather than rebuilding it by name. Button click sounds are not yet played.

### 6.9 Test scenarios
1. Given a new campaign, when the book opens, then `Men` is shown and the entries reachable by Next are exactly `Men, Dwarf, Goblin,
   Orc, Skaven` in that order; Back is disabled on `Men`, Next on `Skaven` at its last page.
2. Given `enablebook:0=26` was run on a new campaign, when paging, then `Wolves` (position 11) is added and known entries follow
   display order, so the sequence is `Men, Dwarf, Goblin, Wolves, Orc, Skaven`, not unlock order.
3. Given the last page of an entry and a later known entry, when Next is pressed, then the later entry shows at page 0; when Back is
   pressed on page 0 of that entry, then the earlier entry shows at page 0.
4. Given option `testbook`, then all 28 entries are known and key 11 is never shown; after closing, keys 0..28 are set.
5. Given a saved game, when loaded, then the `BK01` flags decide which entries appear (no reseeding beyond the save).
6. Given Done, then the caller window is re-opened by name and palette 2 is set.
7. Every RCDATA name, picture name and title id in 6.3 exists in the installation; every text starts with A-Z.
8. Given a description with `\r\n` breaks, then each new paragraph's first line is indented by 3 "X" widths and no blank line is left.

### 6.10 Open questions
⬜ Per-entry page counts (depend on font metrics); 🟡 music carry-over; 🟡 whether flags are really not reset on New Game; 🟡 exact
title vertical position (bottom at 410 derived from the drop-cap line measure); 🟡 no keyboard handling; ⬜ why the display order is
neither alphabetical nor unlock-ordered (it looks like order of first appearance in the campaign, not strictly); ⬜ whether RCDATA
carries a terminating NUL in the DLL (the extracted files do not); 🟡 the unused per-entry page-count array the window fills while
painting is never read.

## 7. New Game and the Main Menu ✅

Marks: ✅ established from the game data and cross-checked, 🟡 inferred / not observed running, ⬜ open.

### 7.1 Purpose
`MainMenu` is the front-end hub: a full-screen picture with five labelled choices (New Campaign, Load Campaign, Options, Credits,
Exit), each shown as a pair of round buttons (one left, one right of the label). Every choice opens something else (`NewGame`,
`LoadSaveWindow2`, `OptionsDialog`, `Credits`, `ExitProcess`).

`NewGame` (built-in name, position 10 of the 15-entry table) starts a fresh campaign: it discards the working campaign files,
re-creates them from the shipped templates, asks for the **commander's name** in a small modal edit box (pre-filled with the default),
stores that name as the leader name of the commander's regiment in the company file, resets the in-memory campaign counters
(coffers, bonus counter, roster flags) and opens the first caravan window `StartCaravan`.

### 7.2 Where it appears
| Opening window | Hotspot (x, y, vx, vy) | Count | `res:` |
|---|---|---|---|
| `MainMenu` | (98,180,41,41) and (501,180,41,41), `script:<Resident>` (documentation only) | 2 | `NewGame` |

No other window uses the built-in (✅ scan of all 535 scripts). `MainMenu` is opened by the boot sequence after the intro, and
re-opened by name by Credits/Options Done and by the abort/exit paths (🟡 the abort path re-enters the menu, `notes/mission_selection.md` §8.1).

### 7.3 Construction

#### 7.3.1 Calling sequence of NewGame ✅ (exact order)
Before it runs, the hotspot launcher (on mouse-up, after the release cue) **pushes the current window (MainMenu) on the context stack
as a WINDOW frame** (every hotspot click pushes), stores the caller (name, mode) and runs the built-in dispatcher. `NewGame` then, without
destroying any glue window first:

1. Zeroes every hotspot record of all 8 glue windows (records only; no window is destroyed). The menu stays visible but is no longer clickable. 🟡 effect: inert menu behind the modal prompt.
2. Drops the four campaign files from the in-memory roster cache: `ARMY.MRC`, `PLAY.MRC`, `debrief.dbf`, `MARCH.MRC`.
3. **Copies the templates over the working files** (overwrite; read-only attribute cleared afterwards; a failed copy is silently ignored):

   | Source (installation `FILE/SCRIPT/`) | Destination (`SAVE/`) |
   |---|---|
   | `STRTARMY.MRC` | `ARMY.MRC` |
   | `MAXARMY.MRC` | `PLAY.MRC` |
   | `MARCH.MRC` (45 B empty `[MERCARMY]`) | `MARCH.MRC` |
   | `DEBRIEF.DBF` (46 B stub; source path spelled lower case, so lookup is case-insensitive) | `debrief.dbf` |

4. Reads the default name: loads `ARMY.MRC` and takes the **leader name of the record with roster id (`whoami`) 2** (the Grudgebringer
   Cavalry; `addleader:` name, `_` and `<` shown as spaces). Shipped value: a 15-character "rank + surname" string, into a 16-byte buffer.
5. Shows the **name prompt** (§7.3.2-7.3.4) and runs its nested message loop until Enter or Esc.
6. **OK (Enter)**: writes the edited text back as the leader name of roster id 2 in `ARMY.MRC` (spaces converted to `_`) and re-saves the file.
   **Cancel (Esc): nothing is written and the default name stays. Cancel does NOT return to the menu and does NOT abort: the game starts
   anyway with the default name.** No validation: an empty text after Enter is written as an empty leader name (🟡, only by deleting the
   pre-selected default). `PLAY.MRC` is not touched, so its regiment 2 leader keeps the shipped name (⬜ whether a later merge overwrites it).
7. Resets the in-memory counters: coffers := static default (500; the `cash:<n>` developer option overrides), bonus counter := 0.
8. Resets the per-regiment roster flag table (39 records of 13 `i32`, `notes/campaign.md` §4.8 `RMYI`): pendingJoin, inMarch, inArmy,
   experience-at-mission-start, reinforcements-available, wounded, wounded-returning := 0; price-per-model := base price. Then reloads
   `ARMY.MRC` and sets **inArmy := 1 for every regiment in it** (whoami 2 and 3).
9. Opens the start flow: script name `start` -> window `StartCaravan`. The `start` request does **not** push a context frame (unlike
   `select`/`resume`/`recruit`/`info*`); it destroys all glue windows (menu, prompt) and opens `StartCaravan`. **Consequence: the
   WINDOW frame of MainMenu pushed by the launcher stays on the context stack, below `StartCaravan`** (🟡 stack depth after NewGame = 1,
   kind WINDOW, caller name `MainMenu`).

Music: NewGame issues no music call. The menu tune `title` keeps playing under the prompt; opening `StartCaravan` starts that window's
own tune (`scribe`), replacing `title` (a window's `[MIDI]` block starts on every creation; `notes/briefing_dialogue.md` §2). Palette: not
changed by NewGame; the prompt uses the menu's palette; `StartCaravan` sets palette index 3.

Saves: NewGame never touches `savegame.N`. The roster files are held in an in-memory cache and flushed to `SAVE/` when a game is saved / a
mission starts, so the entered name lives in the cached company first (🟡 flush timing).

#### 7.3.2 The name prompt ("EditScroll" widget) ✅
One reusable modal widget, also used (same position, other art/caption/limit) by the Save dialog's description prompt (§8.3.6, `notes/builtin_widgets.md` §6).

| Parameter | New Game | Save description |
|---|---|---|
| Parent | glue window 0 (the menu window) | the Save dialog's parent |
| Panel position (client coords) | **(172, 214)**, 296 x 52 (centred horizontally; y centre 240) | same |
| Caption | hard-coded 25-character English "enter your name" prompt (**no string-table id**; literal) | literal |
| Buffer size / max typed | 16 -> **15 characters** (limit = size - 1) | 25 -> **24 characters** |
| Art | `NameScroll` | `EditScroll` |
| Initial text | leader name of roster id 2, **all selected** | slot description, all selected |
| Character filter | on | on |

Structure: a class `EditScroll` panel (child of the parent, id 0x5000, class cursor `HandCursor`, no background brush; erase reported
"handled") containing one system `Edit` control (id 0x5001) at (18, 28) inside the panel, 260 x 12, glue font slot 2, text limit 15,
text pre-set and all selected, keyboard focus. No auto-horizontal-scroll style (single line; input that would not fit the 260 px is
refused by the control) 🟡. Edit colours: background = brush of **palette index 98** (`NameScroll`; index 151 for `EditScroll`), i.e. the
parchment colour of the art; text black. **No OK/Cancel controls and no mouse handling**: the mouse cannot confirm or dismiss the prompt.

#### 7.3.3 Painting the panel ✅ (WM_PAINT; off-screen 296 x 52 bitmap, one blit)
1. Copy the menu backdrop region under the panel into the off-screen bitmap (transparent corners show the menu).
2. Draw `NameScroll` (296 x 52, 8 bpp, index 0 transparent: 628 px = four ragged corners) at (0,0) by index under the current palette.
3. Caption at **(16, 10)**, left aligned, transparent background, black. Font: not selected explicitly (🟡 glue font 2, as the edit text).
4. Blit to the panel; the Edit control paints over it (parchment interior x 6..293, y 1..50 of the art).

#### 7.3.4 Keyboard and modal loop ✅
A nested message loop runs until Enter or Esc; nothing else can be done meanwhile. Characters are filtered before the Edit control sees them:
- Enter (CR) and Esc are forwarded to the panel and **not** inserted: Enter -> "OK", Esc -> "Cancel"; the loop ends.
- Only letters a-z / A-Z, digits 0-9, backspace, space and `! " ' ( ) , . : ; ?` pass. Everything else is swallowed: `_`, `<` (the file
  encodings of a space), `-`, `/`, non-ASCII. Otherwise ordinary Edit behaviour (caret, Delete, Home/End, selection, clipboard); no Tab handling.
- On leaving, the text is read back into the caller's buffer and the edit control, panel, font and brush are destroyed.

### 7.4 State read / written
Read: `FILE/SCRIPT/{STRTARMY.MRC, MAXARMY.MRC, MARCH.MRC, DEBRIEF.DBF}`; `ARMY.MRC` (regiment 2 leader name); default coffers.
Written: `SAVE/{ARMY.MRC, PLAY.MRC, MARCH.MRC, debrief.dbf}` (overwritten), leader name in `ARMY.MRC`, coffers = 500 (or `cash:`), bonus
counter 0, roster flag table (step 8), context stack (+1 WINDOW frame). **Not** touched: glue status bits, book-page flags
(`BK01/BKO2/BK03`), completed-mission state, options, `savegame.N`. Glue status bits are cleared by the first flow script
(`FlowScriptBP01` START does `setgluestatusmask:ffffffff` + `clrgluestatus:` before opening the map). Book-page flags: ⬜ no clearing found (see §7.10).

### 7.5 Asset inventory ✅ (sizes measured from `BITMAP.DLL` / the installation)
| Asset | Kind | Source | Size / rule | Use |
|---|---|---|---|---|
| `OptionScreen` | bitmap | BITMAP.DLL | 640 x 480, 8 bpp, opaque. All labels (NEW CAMPAIGN, LOAD CAMPAIGN, OPTIONS, CREDITS, EXIT), the title logo and the ten socket rings are baked in; no engine-drawn text | backdrop at (0,0); its colour table (indices 10-245) becomes the palette (`palindex -1`, `notes/palette_selection.md`) |
| `OptionButtonUp` | bitmap | BITMAP.DLL | 41 x 41, 8 bpp, 1 frame, index 0 transparent (368 px); own colour table differs from the backdrop's but is drawn by index under the backdrop palette | idle art of all 10 hotspots at their (x,y) |
| `OptionButtonDown` | bitmap | BITMAP.DLL | 41 x 41, 8 bpp, 1 frame, index 0 transparent (368 px); differs from Up only inside the 1-px border (bbox 1..40) | shown while the button is held |
| `NameScroll` | bitmap | BITMAP.DLL | 296 x 52, 8 bpp, index 0 transparent (628 px); parchment = index 98; same palette table as `OptionScreen` | prompt art. Twin `EditScroll` (same shape, indices 151-156 instead of 92-107, other palette) is the Save prompt's art |
| glue font slot 2 = `PCTEXT.FON` | font | GLUE/ | 12 px (`notes/fonts_glue.md`) | edit text (🟡 and prompt caption) |
| `HandCursor` | cursor | WHSHR.EXE cursor group | 32 x 32 | hover over the ten hotspots; class cursor of the prompt panel |
| `SwordCursor` | cursor | WHSHR.EXE | 32 x 32 | default cursor of the menu window (`notes/troop_selection.md` §2) |
| system I-beam | cursor | Windows | | over the Edit control |
| `title` tune | music | `FILE/BINARY/MUSIC/TITLE.MID` (79 425 B GM) / `TITLEFM.MID` (44 463 B FM) | `[MIDI] name:title`, started on every creation, repeat 0 = loops until replaced | menu music, continues under the prompt |
| `B4.WAV` / `B3.WAV` | sfx | `REMOTE/BINARY/GLUE/SPEECH/` | 590 B / 240 B, 8-bit mono 11 025 Hz | `downsfx=4` press (B4), `upsfx=3` release inside (B3), every hotspot; skipped while a speech line plays and when speech is off |
| `SAVE/ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC`, `debrief.dbf` | data | engine save directory (original: install `SAVE/`) | text/INI (`notes/campaign.md` §4.8) | written by NewGame |
| `STRTARMY.MRC` 2 014 B, `MAXARMY.MRC` 34 218 B, `MARCH.MRC` 45 B, `DEBRIEF.DBF` 46 B | data | `FILE/SCRIPT/` | templates | read by NewGame |
| prompt caption | string | literal in the game, no table id (25 chars) | | implementer supplies a short English phrase of the same meaning |
| no other strings | | hotspot `res=-2` = no hint; no BRTXT labels | | |

Shared with other windows: `OptionButtonUp/Down`, the two cues, `HandCursor`, font slot 2, the `EditScroll` widget (Save). Unique to the menu: `OptionScreen`, `NameScroll`, `title`.

### 7.6 Animation and glue ✅
**No animation** in the menu or the prompt: no `[ANIM]`, `animstartframe`/`timecnt`, no timers. Only the tune and the pressed-state art (down
bitmap while the mouse is held over a hotspot; the action fires on mouse-up over the same hotspot).
Layering: (1) `OptionScreen`, (2) ten `OptionButtonUp/Down` sprites at the hotspot rects, (3) while NewGame runs, the prompt panel with the Edit control above it.
Glue: `[POSITION] x=0,y=0,vx=640,vy=480, palindex=-1`; `[MIDI] name:title`; `[BITMAP] setbitmap:OptionScreen`; ten `[HOTSPOT]` blocks (§7.7);
`[DEMODEFAULT]` (§7.7). No `[INIT]`, `[TEXT]`, `[ANIM]`, `[INCLUDE]`.
Wiring: hotspot `res:NewGame` -> launcher matches the name (exact, case sensitive) against the built-in table -> case 10 (§7.3.1). The `start` request opens
`StartCaravan` (`[POSITION] palindex=3`, `[MIDI] name:scribe`, background `ReadBackgroundPic`, one hotspot (480,250,160,110) `res:FlowScriptBP01`
which starts the campaign flow script, plus the `CaravanCommon1-4` include). That flow script clears glue status bits, opens `MapWindow`, and autosaves.

### 7.7 Hotspots, cursors and scripts (`MAINMENU`)
All ten: vx = vy = 41, `set:res=-2` (no hint), `cursor:HandCursor`, no `altcursor`, `setupbitmap:OptionButtonUp`, `setdownbitmap:OptionButtonDown`,
`upsfx=3`, `downsfx=4`, no `linkid`/`count`/`clickres`. Each choice appears twice, left x = 98 and right x = 501:

| Row y | Label (baked into `OptionScreen`) | `script:` (documentation only) | `res:` |
|---|---|---|---|
| 180 | New Campaign | `<Resident>` | `NewGame` |
| 233 | Load Campaign | `loadsav2.wnd` | `LoadSaveWindow2` (WND resource with `[LOADANDSAVEGAME]`, flag 1 = load; §8) |
| 285 | Options | `Null.wnd` | `OptionsDialog` (built-in; opens `OptionWindow`, see Options section) |
| 337 | Credits | `Null.wnd` | `Credits` (built-in, see Credits section) |
| 389 | Exit | `exit.wnd` | `ExitProcess` (built-in; closes the application, no confirmation) |

Hit rectangles are the sprite rectangles (41 x 41); the label text is not a hotspot. Left and right buttons of a row do the same.

`[DEMODEFAULT]`: `set:flag=1`, `script:caravan.wnd` (non-existent), `res:StartCaravan`, comment "Action after timeout!". The block is parsed and stored (target
name, script name, flag); the script command `setdemodefault:` stores the same record (`FlowScriptBP01` uses it for `BPBrief1`). No reader of the stored
record and no idle timer was found: the timeout is 🟡 inert in this build (`notes/glue_keywords.md` §3.10). If live it would open `StartCaravan` without the reset/prompt.

### 7.8 Input and exits
Menu: mouse only (press shows the down art and the press cue; release inside the same hotspot plays the release cue and activates it). No keyboard
shortcuts found 🟡 (N/L/Q/Esc/Enter in the engine are additions). Prompt: Enter = OK, Esc = Cancel. Exits of NewGame: always -> `StartCaravan` (OK and Cancel
alike); no path returns to the menu from the prompt; the menu's context frame stays parked on the stack (§7.3.1 step 9). Exit: closes the main window
(standard close), no confirmation.

### 7.9 Engine status and deviations
Today (`whshr/campaign_scenes.py` `MainMenuScene`, `whshr/frontend/menu_view.py` `MainMenuView`):
- ✅ background `OptionScreen`, ten hotspots parsed from `MAINMENU`, up/down button art (blue chroma key), targets `NewGame`/`LoadSaveWindow2`/`ExitProcess` wired
  to `new_campaign`/`load_game`/`quit`; Options and Credits inert.
- 🟡 `new_campaign` builds `CampaignState.from_installation` (company from `STRTARMY.MRC`, master roster from `MAXARMY.MRC`, coffers 500) in memory and goes
  straight to `GlueScene(window="STARTCARAVAN")`: same as an accepted default name minus the prompt. It writes no `SAVE`-equivalent files (correct per the engine save rule).
- ❌ no name prompt; no context-stack frame; menu music / click cues not checked here.

Suggested shape: a modal `NamePromptScene(parent=MainMenuScene, ...)` (imitating `LoadSaveScene`'s description box) carrying `caption`, `initial`, `limit` (15), `art` (`NameScroll`),
`allowed` filter; on OK or Cancel build `CampaignState.from_installation(...)`, replace `Regiment(whoami=2).leader_name` with the entered text when OK, enter `STARTCARAVAN`.
A view draws `NameScroll` at (172,214) over the frozen menu, the caption at (16,10), and the edit text in a 260 x 12 box at (18,28) with the parchment colour,
all-selected initial text (first printable key replaces it), Enter/Esc only. The same widget (art `EditScroll`) replaces the placeholder panel of the Save prompt.
The name should appear wherever the company's leader name is formatted (roster book leader line of regiment 2); `whshr/roster.py` already stores `leader_name`.

### 7.10 Test scenarios (BDD)
1. Given the main menu, when the left New Campaign hotspot is released, then a name prompt at (172,214), 296 x 52, with `NameScroll`, pre-filled with the shipped leader name of whoami 2 and all text selected is shown.
2. Given the prompt, when the player types "Gotrek_x<" then Enter, then `_`, `<` are ignored, regiment 2's leader name is "Gotrekx" and `StartCaravan` opens; coffers = 500.
3. Given the prompt, when 20 letters are typed, then only 15 are kept.
4. Given the prompt, when Esc is pressed, then `StartCaravan` opens and the leader name is still the default (Cancel does not return to the menu).
5. Given a campaign in progress (regiments hired, coffers 800), when NewGame is chosen and confirmed, then company = the two starting regiments (whoami 2, 3), master roster = 38 fresh regiments, coffers 500, bonus counter 0, no marching orders.
6. Given the menu, then each of the 5 rows has two hotspots at x = 98 and 501 (y = 180/233/285/337/389) with targets as in §7.7.
7. Given NewGame has opened `StartCaravan`, then the context stack holds exactly one WINDOW frame naming `MainMenu` (the `start` request pushes nothing itself).

### 7.11 Open questions
- ⬜ Prompt caption font (no explicit selection) and exact caption wording (a hard-coded English phrase, not a string id).
- ⬜ Whether the entered name is ever written to `PLAY.MRC` (a later company/master merge could overwrite it) and how the roster cache flush interacts with the SAVE copies.
- ⬜ Book-page flags (`BK01/BKO2/BK03`) and completed-mission state on New Game after a game in the same session: no reset found; likely fresh only at process start.
- 🟡 One WINDOW frame of `MainMenu` remains on the context stack after NewGame.
- 🟡 Empty name accepted (no fallback); Edit refuses overflow because no auto-scroll style is set.
- 🟡 `[DEMODEFAULT]` never fires.
- ⬜ Whether the menu reacts to any key.

## 8. Load / Save dialog ✅

Marks: ✅ established from the game data and cross-checked, 🟡 inferred / not observed running, ⬜ open.

### 8.1 Purpose
One native dialog, two modes. **Save** (opened from a caravan) lets the player pick one of five slots, type a description (modal edit box) and
writes the whole campaign state to `savegame.<slot>`. **Load** (opened from the main menu) lists six slots (five player slots plus the automatic
"Last Game" slot 5) and restores the picked save, replacing the interpreter state (windows, context stack, script frames) completely. The dialog
is a child window laid over an ordinary glue window that only supplies the backdrop.

### 8.2 Where it appears
| Opener | Hotspot (x, y, vx, vy) | Cursor / hint / cues | `res:` | Mode |
|---|---|---|---|---|
| `MainMenu` | (98,233,41,41) and (501,233,41,41) (row "Load Campaign"), `script:loadsav2.wnd` (documentation only) | `HandCursor`, `res=-2` (no hint), `upsfx=3`, `downsfx=4` | `LoadSaveWindow2` | Load (flag 1) |
| `CaravanCommon2` (an `[INCLUDE]` block) | (450,85,190,180), `script:LoadSaveWindow` (documentation only) | `HandCursor`, hint `BRTXT 157`, no sfx keys | `LoadSaveWindow` | Save (flag 0) |
| `CaravanDietrich` | (450,85,190,180), same keys | same | `LoadSaveWindow` | Save |

✅ scan of all 535 scripts. `CaravanCommon2` is `[INCLUDE]`d by 20 windows, so each carries the Save hotspot: `StartCaravan`, `CaravanSelectMission`,
`CaravanContinueMission`, `CaravanAfterMission`, `CaravanAfterEncounter`, `CaravanAfterMissionWithRecruit`, `CaravanAfterEncounterWithRecruit`,
`CaravanRecruitAndResume`, `CaravanRecruitNoSpeechAndResume` and the eleven `InfoCaravan*` windows (`REC SZA SZB REA WED LB LA ENA BPC ENE BMA`).
`LoadSaveWindow` / `LoadSaveWindow2` are ordinary WND resources, not members of the 15-entry built-in name table. No hotspot and no Save entry exists
elsewhere (battle screens, options).

### 8.3 Construction

#### 8.3.1 Calling sequence ✅
1. The hotspot launcher (mouse up over the hotspot) **pushes the current window as a context frame**, records the caller (name, mode), finds that
   `LoadSaveWindow[2]` is not a built-in name and opens it as a WND window resource (top-level glue window, palette id 2). The Save hotspot has no
   click cue keys; the menu's Load hotspot has `downsfx=4` / `upsfx=3`.
2. The window resource (§8.6): 640x480 at (0,0), `palindex=2` (application palette pair 2 = `MAP`), one bitmap `Map` as backdrop, and a
   `[LOADANDSAVEGAME]` block. **No hotspots, no `[MIDI]`, no `[INIT]`, no `[ANIM]`**: the opener's tune keeps playing (menu `title`, or the caravan's tune).
3. On window creation, a `[LOADANDSAVEGAME]` block whose `x` or `y` is non-zero creates the native dialog child. **`set:x=100 / set:y=100` are only that
   non-zero gate; the values are not a position.** The position is fixed (§8.3.2). `set:flag` = mode: **0 = Save, 1 = Load**.
4. After creation nothing is scripted; all behaviour is the dialog's own.

#### 8.3.2 Window geometry ✅
Dialog = child of the glue window, class cursor `HandCursor`, no background brush (erase handled; everything painted off-screen and blitted), command id 0x302.

| Mode | Size (w x h) | Position | Art (BITMAP.DLL) |
|---|---|---|---|
| Save | 252 x 212 | x = 194, y = (480 - 212)/2 = 134 | `LoadSaveWindow` |
| Load | 252 x 254 | x = 194, y = (480 - 254)/2 = 113 | `LoadSaveWindow2` |

Art is drawn by palette index, index 0 transparent (199 transparent pixels = the ragged corners, which show the `Map` backdrop) 🟡 (backdrop -> art order
not observed). A composition of `Map` + art + slot art + tents at the geometry below looks correct (numbered tent flag 1..5 and "L" in the socket at the slot's left end).

#### 8.3.3 Controls ✅ (coordinates relative to the dialog's top-left)
| Control | Id | Position | Size | Art up / pressed | Label | Enabled |
|---|---|---|---|---|---|---|
| OK | 0x300 | (8, 188) Save; (8, 230) Load | 116 x 20 | `LoadSaveBtn0Up` / `LoadSaveBtn0Dn` | `BRTXT 337` in Save, `BRTXT 336` in Load | see rule below |
| Cancel | 0x301 | (124, same y) | 116 x 20 | same twins | `BRTXT 307` (the shared abort word, same id as the troop-selection abort label) | always |
| slot n = 0..4 | 0x310 + n | (8, 8 + 36 n) | 232 x 36 | `LoadSaveBtn1Up` / `LoadSaveBtn1Dn` | the save's description, or the literal "-Empty-" | always |
| slot 5 "Last Game" | 0x315 | (8, 194) = 8 + 180 + 6 gap | 232 x 36 | same | same | **exists only in Load mode** |

All are owner-drawn buttons (child|visible|owner-draw). No tab stop, **no keyboard handling in the dialog** (no Enter/Esc/arrows; those exist only in the
description prompt). OK / Cancel are plain push buttons (act on release inside; id sent to the dialog as a command). A slot button acts **on mouse-down** and
swallows the mouse-up: it becomes the selected slot (the previous is un-pressed; the selected slot is drawn with its pressed art), then the dialog
re-evaluates OK. No double-click action.

**OK enable rule** (on every slot click and at creation): no slot selected -> disabled. Slot occupied (a file `savegame.<n>` exists) -> enabled. Slot empty ->
enabled in **Save**, disabled in **Load**. Initially nothing is selected, so OK starts disabled in both modes. "Occupied" is only file existence (a header read
follows but its result is not checked: a corrupt file still counts, showing whatever text the read produced 🟡).

**Click cues 🟡 (not confirmed for this dialog).** The research found no cue call in the dialog's own code, so whether its owner-drawn buttons (OK, Cancel,
slots) play a click cue was not confirmed. Expected behaviour, from the shared glue rule: press (mouse-down) = `B4.WAV`, release inside the control = `B3.WAV`
(glue speech directory), skipped while a speech line is playing and when speech is off. For slots (select on mouse-down, mouse-up swallowed) at most the press cue is plausible.

#### 8.3.4 Drawing of a control (owner-draw routine) ✅
Font: glue font slot 2 (`PCTEXT.FON`, 12 px), transparent text. Text colour: **palette index 206** (near-black, (11,11,27) in palette pair 2); a disabled
control uses plain RGB (127,127,0) (olive). Art is drawn by index at the control position (both twins opaque), then text.
- OK / Cancel: art `LoadSaveBtn0Up/Dn` (Dn while pressed); label centred in the 116 x 20 art (`x + (116 - textW)/2`, `y + (20 - textH)/2`), **no 1-px press offset**.
- Slot: art `LoadSaveBtn1Up` (unselected) or `LoadSaveBtn1Dn` (selected). Then in order:
  1. **tent icon** `LoadSaveTent<n>`, n = slot + 1 (slots 0..4 -> Tent1..5, slot 5 -> Tent6), 16 x 20 index-0-transparent, at `x + 5 + (18 - 16)/2 = x + 6`,
     `y + 1 + (30 - 20)/2 = y + 6` (18 x 30 nominal cell);
  2. label = the window text (description or "-Empty-", at most 63 characters), centred horizontally in a **207-px field starting at x + 24**
     (`x + 24 + (207 - textW)/2`) and vertically as `y + 1 + (30 - textH)/2` (30, not 36).
  Icons are the numbered tent flags (slots 1..5 red, blue, green, orange, purple; "L" tent for slot 5) and are drawn even on empty slots.
- The slot label is set once at creation and never refreshed (the dialog closes after every successful action).

#### 8.3.5 Slot descriptions: what is read from `savegame.N` ✅
For each slot 0..4 (0..5 in Load) the dialog checks whether `SAVE/savegame.<n>` exists and, if so, reads the RIFF `WHSV` file's first chunk `SHDR` (`notes/campaign.md`
§4.2, 0xF8 bytes) and uses only its **first field, the 64-byte description string**. There is **no date, mission name, coffers or window caption** in the dialog
(header fields `+0x40` battle and `+0x80` window names are read only by Load). `savegame.5` = autosave.

#### 8.3.6 The description prompt (Save OK) ✅
On Save OK the dialog is **hidden entirely** (only the `Map` backdrop remains) and the modal edit box is shown: the same widget as the New Game name prompt (§7.3.2).

| Parameter | Value |
|---|---|
| Parent / backdrop copy | the glue window (`Map`): the prompt sits over the plain map, not over the dialog |
| Panel | (172, 214), 296 x 52, art `EditScroll` (296 x 52, 8 bpp, index 0 transparent = 628 px) |
| Caption | short English "enter save description" prompt (22 characters, literal, **no string id**) at (16, 10) in the panel, black, transparent |
| Edit control | (18, 28) in the panel, 260 x 12, glue font slot 2, background = palette index **151** = (199,167,139) of palette pair 2 (parchment), text black |
| Buffer / limit | buffer **25**, edit limit = buffer - 1 = **24 characters** |
| Initial text | the slot's current description if occupied, otherwise **`BRTXT 500`** (§8.3.7); **entire text pre-selected** |
| Filter | only a-z A-Z 0-9, backspace, space and `! " ' ( ) , . : ; ?`; everything else (`_`, `<`, `-`, non-ASCII) dropped |
| Keys | Enter = OK, Esc = Cancel; no OK/Cancel buttons, no mouse handling |

**Esc**: the prompt closes, the dialog is shown again (selection kept), nothing is written. **Enter**: the text (no trimming, no empty check: an empty
description is written and later shows as an empty label) is the description.

#### 8.3.7 Default description rule ✅ (closes open item 6 of `notes/builtin_widgets.md` §8)
The default text is **not mission-dependent**: always `BRTXT 500` (the campaign's opening-region name, 18 characters, fits the 24 limit), used when the picked slot
is empty; an occupied slot pre-fills its current description. Matches the shipped `savegame.0`. The autosave uses a separate literal "Last Game" (no string id).

#### 8.3.8 Save OK sequence ✅
Selected slot required. Description prompt (§8.3.6); on Enter: flush the four cached working files (`ARMY.MRC`, `MARCH.MRC`, `debrief.dbf`, `PLAY.MRC`) to `SAVE/`; write
`savegame.<slot>` (`notes/campaign.md` §4). **Write failure**: system message box, caption literal "Error", text a "Save Game Failed. Error Code <n>" style literal, OK-only, no
icon, owner = the glue window; afterwards the dialog **still closes normally**. Then §8.3.10.

#### 8.3.9 Load OK sequence ✅
Selected slot required. Discard the four cached working files; if the header cannot be read nothing happens (dialog stays; cannot occur for an enabled OK). Else load the
whole file (`notes/campaign.md` §4 / `notes/save_resume.md` §4). **Failure**: message box (caption "Error", "Load Game Failed. Error Code <n>" style text), then the game
**resets to the main menu** (stop and discard the tune, clean up windows, rebuild the menu); the dialog does not stay. **Success**: §8.3.10.

#### 8.3.10 Exit and pop ✅ (identical to `notes/builtin_widgets.md` §6)
- **OK after successful Save or Load**: CleanUp (destroy the dialog and all glue windows), then pop one context frame. Kind `WINDOW` (0xC): re-open the recorded caller by
  name (Save from a caravan -> the same caravan; Load -> the top of the *loaded* stack, i.e. the caravan the save was made in). Any other kind (`RUN`, 0x13, autosave-style
  frame): **resume the parked script** at the saved position. After Load the popped frame belongs to the loaded stack (the menu's frame died with the old stack).
- **Cancel**: CleanUp, pop one frame; `WINDOW` -> re-open the caller by name; `RUN` -> **nothing resumes** (only OK resumes scripts).
- Esc/Enter on the dialog do nothing. Save leaves palettes etc. as the pop restores them (the caller sets its own).

#### 8.3.11 Autosave (`autosave:` and `testmission:`) ✅
Not through this dialog: the interpreter command writes the four working files, pushes a `RUN` context without hiding windows, writes **slot 5** with the description
literal "Last Game", drops the pushed frame and re-shows the windows. Failure: box with caption "Error", "Save Game Failed. Error Code <n>" style text, no owner, execution
continues. Frame semantics: `notes/save_resume.md` §6, `notes/glue_interpreter.md` §9.1 (56 `autosave:` lines in the scripts). Only Load lists slot 5; Save never creates it.

#### 8.3.12 State
Read: `SAVE/savegame.0..5` (headers), on Load the whole file. Written: on Save the four working files and `savegame.<slot>`. No option or campaign counter is touched by the
dialog itself (Load restores them all).

### 8.4 Asset inventory ✅ (sizes measured from `BITMAP.DLL`; palette-index copies, index 0 transparent unless stated)
| Asset | Kind | Source | Size, frames, rule | Use |
|---|---|---|---|---|
| `Map` | bitmap | BITMAP.DLL | 640 x 480, 8 bpp, opaque, 1 frame | backdrop of both windows at (0,0) |
| application palette 2 (`MAP`) | palette | `GLUE/WINDMAP.PAL` (106-245) + `GLUEMAP.PAL` (10-105) | 256 entries; the art's own DIB tables (hash 1225d1a2 dialog art, 55b7644f `Map`/tents 1-5, 15177bfc tent 6) are ignored, only indices are drawn | `palindex=2` on window open |
| `LoadSaveWindow` | bitmap | BITMAP.DLL | 252 x 212, 199 transparent px | Save panel at (194,134) |
| `LoadSaveWindow2` | bitmap | BITMAP.DLL | 252 x 254, 199 transparent px | Load panel at (194,113) |
| `LoadSaveBtn0Up`, `LoadSaveBtn0Dn` | bitmap pair | BITMAP.DLL | 116 x 20 each, opaque, 1 frame | OK / Cancel released / pressed; also used by the Yes/No confirm |
| `LoadSaveBtn1Up`, `LoadSaveBtn1Dn` | bitmap pair | BITMAP.DLL | 232 x 36 each, opaque | slot unselected / selected (Dn darker) |
| `LoadSaveTent1`..`LoadSaveTent6` | bitmap x6 | BITMAP.DLL | 16 x 20, index 0 transparent (172-174 px); numbered flag tents 1..5, "L" tent 6 | slot icon at slot (6,6) |
| `EditScroll` | bitmap | BITMAP.DLL | 296 x 52, index 0 transparent 628 px | Save prompt panel art at (172,214) |
| font slot 2 = `PCTEXT.FON` | font | GLUE/ | 12 px | labels and edit text (🟡 prompt caption: no explicit font, same face assumed) |
| `HandCursor` | cursor | EXE cursor group | 32 x 32 | class cursor of the dialog and prompt panel; which cursor shows over the buttons is unverified (🟡 default chain) |
| `B4.WAV` / `B3.WAV` | sfx | `REMOTE/BINARY/GLUE/SPEECH/` | press / release cues, skipped while speech plays or is off | MainMenu Load hotspot (`downsfx=4`, `upsfx=3`); Save hotspot none; inside the dialog 🟡 see §8.3.3 |
| music | tune | none: no `[MIDI]` block; opener's tune continues | | |
| `BRTXT 336 / 337` | strings | BRTXT.DLL | OK label Load / Save | OK |
| `BRTXT 307` | string | BRTXT.DLL | Cancel label | Cancel |
| `BRTXT 500` | string | BRTXT.DLL | default description | Save prompt initial text |
| `BRTXT 157` | string | BRTXT.DLL | hover hint of the caravan Save hotspot | caravan hotspot |
| literals: empty-slot label, prompt caption, "Last Game", error caption, two error phrases | strings | in the game, **no table id** | | implementer supplies equivalent English text |

Shared: `Map`, palette 2, fonts, `HandCursor`, `LoadSaveBtn0*` (also the Yes/No confirm), the prompt widget (New Game uses `NameScroll`). Unique: `LoadSaveWindow*`, `LoadSaveBtn1*`, `LoadSaveTent*`, `EditScroll`.

### 8.5 Animation and glue ✅
**No animation**, timer or scrolling; painted on creation and on selection change. Glue: the opener's hotspot names the window resource; the launcher pushes the opener
(WINDOW frame), opens the resource (palette 2, backdrop `Map`); `[LOADANDSAVEGAME]` creates the native dialog (flag = mode); Cancel/OK destroys everything and pops (§8.3.10).
Draw order: backdrop, panel art, slot art + tent icon + label, OK, Cancel; the prompt replaces the (hidden) dialog and is drawn over the backdrop only. No script event is
emitted. Context stack: net effect of Save/Cancel = zero (push by launcher, pop by dialog); of Load = the stack is replaced by the saved one, then popped once.

### 8.6 Hotspots, cursors and scripts (the two WND resources) ✅
Both resources are identical except the flag: `[WINDOW]` with `[POSITION] x=0 y=0 vx=640 vy=480 palindex=2`, `[BITMAP] setbitmap:Map`, `[LOADANDSAVEGAME] set:x=100 set:y=100
set:flag=0` (`LoadSaveWindow`, Save) or `flag=1` (`LoadSaveWindow2`, Load). No hotspots, `[MIDI]`, `[INIT]`, `[ANIM]`, cursors or sfx. Keys of `[LOADANDSAVEGAME]`: `x`,`y` (non-zero gate only), `flag` (mode).

### 8.7 Input and exits
Mouse only in the dialog (click slot, OK, Cancel); keyboard only inside the description prompt (Enter/Esc/typing). Exits: OK (Save: written, Load: restored) and Cancel, both per
§8.3.10; Load failure -> main menu reset.

### 8.8 Engine status and deviations
Existing: `whshr/load_save_scene.py`, `whshr/frontend/load_save_view.py`, `whshr/savegame.py` (JSON slots), opener wiring in `whshr/campaign_scenes.py` (menu Load) and `whshr/glue_scene.py`
(caravan Save hotspot), tests in `tests/test_load_save.py`. Deviations to fix:
1. OK/Cancel labels are `GMTXT 163/164`; should be `BRTXT 336`/`337` (Load/Save verb) and `BRTXT 307`.
2. Button text has a 1-px press offset and grey disabled colour; original: no offset, colour index 206, disabled = olive RGB (127,127,0).
3. Slot text is centred over the whole 232 px and vertically in 36; original: 207-px field at x+24, y + 1 + (30 - h)/2.
4. No tent icons (`LoadSaveTent1..6` at slot (6,6)); "-Empty-" literal instead of "Empty".
5. Description limit 25 -> **24**; no character filter; initial text not pre-selected; default description constant -> **`BRTXT 500`** at runtime.
6. Prompt: dark placeholder panel 296 x 58, yellow caption, white text; original: `EditScroll` 296 x 52 at (172,214), black caption at (16,10), edit box (18,28) 260 x 12 with parchment index 151; the
   **dialog is hidden while the prompt is up** (engine draws it under and hides only overlapping labels).
7. Enter/Esc/`L` keys drive the dialog although the original dialog has none (prompt only): intentional convenience.
8. Load failure keeps the dialog with a message (original: message box then reset to main menu); Save failure keeps the dialog (original: closes). Documented kinder deviations.
9. Slot click selects on mouse-down (✅ same).
10. The engine opens Save from any caravan hotspot; verify all 20 windows of §8.2 carry it (data-driven, so automatic).
11. Save file is the engine's own JSON (not compatible by design).

### 8.9 Test scenarios (BDD)
1. Given the Save dialog, then it is 252 x 212 at (194,134) with slot buttons at y = 8, 44, 80, 116, 152 and OK/Cancel at y = 188; in Load mode 252 x 254 at (194,113), slot 5 at y = 194, buttons at y = 230.
2. Given an empty slot 2 in Save, when clicked, then OK is enabled, the prompt opens with `BRTXT 500`'s text selected, and typing "A_b" yields "Ab".
3. Given the prompt, when 30 letters are typed, then 24 are kept.
4. Given the prompt, when Esc is pressed, then the dialog reappears with the same slot selected and no file is written; the dialog is not drawn while the prompt is up.
5. Given Load with slot 3 empty, when clicked, then it is selected but OK is disabled; slot 5 is listed only in Load.
6. Given a slot with description "X", then its button shows the Tent(slot+1) icon at (6,6) and "X" centred in the field x+24..x+231.
7. Given a Load of a save made in a caravan, when OK, then the caravan opens (pop of the loaded stack, kind WINDOW re-opens by name); given an autosave (slot 5), then the parked script resumes after the `autosave:` line.
8. Given the labels, then OK reads `BRTXT 337` in Save and `336` in Load, Cancel `307`.
9. 🟡 Given a button press then release inside OK with speech on and no line playing, then `B4.WAV` then `B3.WAV` play (expected shared rule; unconfirmed for this dialog).

### 8.10 Open questions
- 🟡 Whether OK/Cancel/slots play the click cues (`B4` press / `B3` release; no cue call found in the dialog itself); which cursor shows over the owner-drawn buttons.
- 🟡 Whether the prompt caption uses font slot 2 (same face assumed).
- 🟡 Backdrop/art compose order and corner transparency (not observed).
- ⬜ A corrupt `savegame.N` (unreadable header): slot counted occupied, label text undefined.
- ⬜ Exact wording of the literals (empty-slot label "-Empty-" known; error phrases known in shape only).
- Close-out: open item 6 of `notes/builtin_widgets.md` §8 is answered (`BRTXT 500`, constant).

## 9. Debrief screen (post-battle pages) ✅

Marks: ✅ established from the game data and cross-checked, 🟡 inferred / not observed running, ⬜ open.
Builds on `notes/troop_selection.md` (pre-battle pages P0/P1/P5 and the shared row layout), `notes/debrief_evaluation.md` (evaluators, text programs, payment),
`notes/activity_results.md`, `notes/campaign.md` §1, §2.5, §3.3, §4.8, §5 and `notes/builtin_widgets.md` §1-§2. This section adds per-page geometry, string ids, button/paging state
machines per open mode, skip rules, music, exits and assets.

### 9.1 Purpose
After a battle the player sees a short report inside the **same native window as troop selection** (class "TroopWindow", pages P2..P4; P5 is the bankruptcy page): P2 a verdict text chosen
by the mission's evaluator, P3 a per-regiment table (kills, dead, wounded, experience gained), P4 the mission balance sheet (payments, penalties, armour rewards, doubled experience) and the new
coffers. Pages depend on the *open mode* (2, 4, 6, 7; modes 3 and 1 are never requested). Done runs the *completion* that pays the mission (mode 2; modes 4/7 through their own callback), applies
armour rewards, experience/promotions, merges the debrief into the company and lets the campaign continue. Mode 5 (P5) is the "campaign over" page of troop selection, not a debrief page.

### 9.2 Where it appears
| Trigger | Glue command / place | Open mode | Pages shown | Completion (Done) |
|---|---|---|---|---|
| battle with debrief | `playgamewithdebrief:<bf>[,n]` | 2 | P2, P3 (paged), P4 | full completion (§9.9.1), no context pop |
| battle with debrief, encounter | `encounterplaygamewithdebrief:<bf>[,n]` | 2 | same | full completion + context pop + resume |
| battle without debrief | `playgame`, `encounterplaygame`, panel buttons Defend/Attack! | 6 | P2, P3 (paged), **no balance page** | completion without payment, merges ARMY and MARCH (+pop for encounter) |
| glue `debrief:[n]` | 6 sites: `MissionSZWindow`, `MissionAM1Window`, `MissionWE45Window` (x2), `SZMission5`, `ENMission1` (bare `debrief:`) | 4 | P4 only | payment only, pop 1, resume script |
| glue `debriefwithsummary:n` | `BPMission2`, `BPMission5`, `BPMission13`, `BPMission15B`, `GMMission3`, `LMission1` (n = 5, 7, 10, 11, 34, 35) | 7 | P2, P4 (no P3) | payment only, pop 1, resume script |
| debrief troop page from the roster book | Ctrl+click on a P3 row (§9.3.5) | - (child window) | view-only roster book | returns to P3 |

The `iftrue/iffalse` variants of both commands exist but no shipped window uses them (✅ scan). `debrief:` without a number keeps the previous evaluator index (`notes/debrief_evaluation.md` §1).
A debrief is never opened by a hotspot `res:` and has no WND.DLL resource; its only glue is the command/callback of §9.3.1 and §9.9.

### 9.3 Construction

#### 9.3.1 Calling sequence
Battle end (modes 2 and 6) ✅. The battle-end handler: battle-module cleanup (sound restored); result-record test; then either
(a) *quit path* (record's "valid" word cleared and option `unrealquit` off): show the neutral end-screen bitmap, then go to the main menu (all glue windows destroyed, no debrief, script not resumed); or
(b) *normal path*: show the end-screen bitmap chosen by the evaluator key (`notes/debrief_evaluation.md` §4.2/§4.4: `GameEndScreen` neutral / `GameEndScreenSuccess` / `GameEndScreenFailure`, 640x480, own
    palette: the bitmap is put on the glue window with its own colours, palette argument -1), set the arrow cursor, re-initialise the glue front end (movie player etc.), arm a 50 ms timer with delay
    argument 0, and on that timer (or a left-button release / Enter on the glue window) call the **post-battle wrapper**. 🟡 hold time of the end screen: the delay argument is 0, so it is visible for
    the re-initialisation plus about one timer tick unless a click/Enter comes first.

The **wrapper** ✅ (bookkeeping: `notes/activity_results.md` §2.2, `notes/campaign.md` §3.3/§5): with option `nobattle` off it loads `debrief.dbf`, runs the campaign-over test (death movie then main menu,
no screen), else does the wounded bookkeeping, merges the debrief into `PLAY.MRC`, clears the wounded when objective `Z` was met; then opens the screen with: file `debrief.dbf` (savegame directory), title
argument = the current mission's name id (`BRTXT` id at record offset 0), open mode 2 or 6, completion callback = none (plain) or "pop and resume" (encounter variants). (A second numeric argument, 500, is stored but never used for text.)
Glue `debrief:` / `debriefwithsummary:` (modes 4/7) ✅: the interpreter pushes the current window (script frame), destroys all glue windows and opens the screen on `debrief.dbf` with the mission name id and the "pay, pop, resume" callback (§9.9.2).

Every open ✅ (in order): allocate a fresh unit list; load the file (`debrief.dbf`: objective records + surviving and dead/routed units, `notes/campaign.md` §4.8); if it cannot be loaded, or (modes 2, 3, 6, 7 only) the evaluator
chosen by the mission's debrief index yields **no text list**, the screen is **not shown** and the completion of §9.9 runs at once (§9.3.1a); music starts; palette index 1 (BOOK) is set; string tables read; off-screen bitmap and window
created; buttons (§9.3.3) created; first page painted; a 250 ms timer (id 3, its handler only matters on P1) created and a "ready" flag set (clicks before it are ignored).

**9.3.1a Skip rule ✅** (corrects earlier notes): the "no list" test applies to modes 2, 3, **6 and 7** (6/7 are folded into 2 before the test), not to mode 4. Effect: a battle whose evaluator returns a null list for the achieved
outcome shows no debrief: n = 17, 18, 19 (BMMission1-3, list A none: a victory shows nothing), n = 6 (`bf001`, list B none: a defeat shows nothing), and every other row of `notes/debrief_evaluation.md` §4.2 whose list for the
achieved outcome is `-`. The completion still runs (payment for mode 2, merges, promotions).

Music ✅: `binary/music/win.mid` when the evaluator's result T = 1, else `binary/music/lose.mid`, for **modes 2, 6 and 7** (folded to 2); `binary/music/tactical.mid` for every other open (mode 4, P0/P1/P5). Repeat count 0
(loops until the window is destroyed); stopped and discarded when the window is destroyed (Done; the skip path too).
Palette ✅: index 1 (BOOK, `GLUEBOOK`+`WINDBOOK`) at open. Nothing restores index 2 on exit (unlike Abort): the next window sets its own. 🟡 nothing on screen is affected.
Cursor ✅: class cursor `SwordCursor` on P2, P3, P4 (P5 leaves it); holding Ctrl shows `HelpCursor`; the system hourglass is shown while a page repaints.

#### 9.3.2 Window
640x480 child of the main window at (0,0), no window brush. Everything is painted into an off-screen 8-bit bitmap (current application palette) and blitted; repainted (not cached) whenever the page or unit page changes.
Background `TroopBook` (640x480, open-book parchment with green cover edge) at (0,0) on every page. Text transparent, black unless stated. **H** = height of font slot 2 (`PCTEXT.FON`, 12 px); **H4** = height of
font slot 4 (`SUBTEXT.FON`, "Warhammer Font 4", 22 px). Body line pitch = H (12); centring is relative to the 640-px window: `x = (640 - text width) / 2`.

#### 9.3.3 Controls (owner-drawn buttons, class cursor `HandCursor`, y = 448, 84x32)
| Id | Label | x | Art (up / pressed) | Created when |
|---|---|---|---|---|
| `0x102` Done | `BRTXT 304` | 325 | `GreenATabUp` / `GreenATabDn0` | always |
| `0x100` Next | `BRTXT 300` | 525 | `RedATabUp` / `RedATabDn0` | every mode except 5 |
| `0x101` Back | `BRTXT 301` | 425 | `BlueATabUp` / `BlueATabDn0` | every mode except 5 |
| `0x103` Abort | `BRTXT 307` | 225 | `BrownATabUp` / `BrownATabDn0` | mode 0 only: **never in a debrief** |

Label ✅: font slot 2, yellow `(255,255,0)` enabled, light grey `(192,192,192)` disabled; centred on the art then offset by **(+4,+2) released, (+3,+3) pressed**. Press cue `B4.WAV`, release-inside cue `B3.WAV`
(glue speech directory; skipped while a speech line plays and when speech is off). While a Ctrl+click roster book is open no button is active.

**Enabled rules** (re-evaluated after every page change; "up" = unit page index on P3, "pages" = ceil(units/6)):
| Open mode | Next | Back | Done |
|---|---|---|---|
| 2 | enabled on P2 and on **every** unit page of P3 (last P3 page -> P4); disabled on P4 | enabled on P3 (any unit page) and P4; disabled on P2 | always |
| 6 | enabled on P2; on P3 only while `up < pages-1`; disabled on the last P3 page (**P4 unreachable in mode 6**) | enabled on P3 only | always |
| 7 | enabled on P2 only (jumps to P4) | enabled on P4 only (returns to P2) | always |
| 4 | disabled | disabled | always |
| 3 (never requested) | enabled while `up < pages-1` | enabled while `up > 0` | always |

Transitions ✅ (no roster book open): Next: P2 -> P3 unit page 0 (mode 7: P4); P3 with `up < pages-1` -> `up+1`, else P4 (unit page reset to 0). Back: P3 `up > 0` -> `up-1`, P3 `up = 0` -> P2; P4 -> P2 in mode 7, else P3 last unit page.
Each change repaints. Done is valid on any of P2/P3/P4 and runs the callback or completion (§9.9) without visiting other pages.
Keyboard ✅: none except Ctrl (help cursor); every other key goes to the hidden cheat-code detector; Enter/Esc/Space do nothing.

#### 9.3.4 Drawing (640x480 window; H = 12, H4 = 22)
Common: page title `BKTXT 403` with `%s` = `BRTXT <mission name id>`, centred, y = 25, font slot 2, black, on P2, P3, P4 (**not P5**). Its height is also the row offset used below.

**P2 - verdict text** (modes 2, 6, 7). The text program of `notes/debrief_evaluation.md` §4.3 (list A/B/C from the evaluator) is walked as lines: op 2 -> string `BKTXT <id>`, op 1 -> an empty line, measured ops -> one formatted line
(ids and `%d`/`%%` arguments in that note).
1. `y0 = 8*H + 50` (= 146). The **first** line is drawn in font slot 4, centred at `y0`; then `y = y0 + 2*H4` (= 190).
2. Every following line in font slot 2, centred, at `y`, then `y += H`. An empty line only advances `y`.
3. After the list `y += H` (one blank gap). Then, if objective `K` is present **and met**, one line: `BKTXT 610` with `%s` = name of the regiment whose `whoami` is in the record's third value (first unit of the list if not found)
   and `%s` = the item name selected by the record's fourth value (item table index); centred at `y`, `y += H`. Then the same for objective `X`. (`K`/`X` records exist in shipped battles, `notes/debrief_evaluation.md` §2.2, e.g. BF003 for `K`.)
No pictures.

**P3 - troop table** (modes 2, 6). Six regiments per page in file order of `debrief.dbf` (surviving units first, then dead/routed; every listed unit is shown, allied NPC units too when merged, 🟡 no filter found); `pages = ceil(n/6)`; the last page holds `n - 6*(pages-1)` rows.
- Column headers, font 2, y = 50: `BKTXT 404` (kills) x = 345, `BKTXT 405` (dead) x = 405, `BKTXT 406` (wounded) x = 465, `BKTXT 412` (experience) x = 530.
- Row i (0..5): `y_i = 50 + H + 4*H*i` (= 62, 110, 158, 206, 254, 302), same row routine as P0/P1 (`notes/troop_selection.md` §3.2-§3.3) with x = 45, style 0 (no scroll strip, **no ring mark**): name line at (105, y_i) formatted
  `<name> <models> (<original size>)` (models = current + routed, original = `s_orgsize`); weapon/armour line at (105, y_i + H) `<BRTXT 200+weapon>/<BRTXT 100+armour>`; rank icon `Skull<n>` (`n` from `s_pntval`, formula in that note)
  centred on (65, y_i + 12); banner sprite at (80, y_i). Name/line colour: grey (127,127,127) if the unit's `hired` flag is 0, red if destroyed (models 0, or artillery with < 2), else black. 🟡 numbers are black except in the odd not-hired + destroyed case.
- Numbers, plain decimal (`%d`), no unit suffix, font 2, at y_i, left-aligned: x = 345 kills (`s_kills`); x = 405 dead and x = 465 wounded with `lost = s_calualties - s_routed`, `wounded = lost * dead% / 100` (option `dead`, default 65),
  `dead = lost - wounded` (integer division; `notes/campaign.md` §3.3); x = 530 experience gained = `s_Exp` (file value) minus the roster's experience-at-start of that `whoami` **before** the doubling of §9.9.1 (a "2x Experience" mission still shows the single value).
- Below the last row of the page, at `y = 50 + 4*H*rowsOnPage`, x = 345: `BKTXT 611` (wounded could not be recovered) when objective `Z` is present and met. No other footer.
- Ctrl+click on a row opens the view-only roster book (§9.3.5); a plain click does nothing.

**P4 - balance sheet** (modes 2, 4, 7; in 6 only through the unreachable route). Font 2, black.
1. Heading `BKTXT 5005` in font slot 4, centred, y = 50; `y = 50 + 2*H4` (= 94).
2. The mission's cash program (`notes/campaign.md` §2.5) is run once; each step yields (label, amount, kind). Pitch after every step (including invisible ones) is `floor(3*H/2)` = 18 px.
   - "credit" (payments, mission total, final): label at x = 45; amount text `" %d <BKTXT 419>"` (leading space, number, unit word) **right-aligned to x = 390**.
   - "debit" (payment already received, every penalty): same, amount text `"-%d <BKTXT 419>"`.
   - "label only" (`BKTXT 5021` 2x Experience Points Awarded; `BKTXT 5022` `%s` Receive +1 Armour rating with the regiment's name): label at x = 45, no amount. An armour line is printed only if the regiment is in the debrief list with at least one model; otherwise the step is skipped and takes **no** vertical space.
   - blank step (op 1): nothing drawn, one pitch of space.
   - "Mission Total" (`BKTXT 5002`) shows the running total; "Total Final Payment" (`5003`) clamps the running total at 0 first.
3. After the last step `y += 18`: label `BKTXT 5007` at x = 45; value `BKTXT 5008` (`%d gold crowns`) right-aligned to x = 390: **current coffers + the program's final running total** (coffers already include any prepaid initial payment; this is what the coffers become after Done in mode 2/4/7, only a preview in mode 6).
Worked example: BF003 (`notes/campaign.md` §2.5): Initial 100, Completion 400, Total 500, blank, Already received -100, Villagers -0, Buildings -0, blank, Final 400; coffers 280 -> lines `5007`/`5008` show 680.

**P5 - bankruptcy** (mode 5, troop selection only): no title; `BKTXT 601` in font 4 centred at y = 8*H + 50; `y += 2*H4`: `BKTXT 602` (`%d` = coffers) in font 2 centred; `y += 2*H`: `BKTXT 603` (`%d` = fees of the forced regiments still alive) centred. Only Done exists.

#### 9.3.5 Ctrl+click on a P3 row (view-only roster book)
Ctrl is tested at click time. On P3 the row is `floor((click_y - 50) / (4*H))` (only rows actually present); the selection window is hidden, the roster book (`notes/builtin_widgets.md` §2) opens on the `debrief.dbf` unit list at that unit, **view-only**
(no Hire/Fire, no Abort, no reinforcements sub-window), and the debrief window is repainted and shown again on close. Ctrl+click on P2/P4 does nothing. The book uses palette 9 (BK2); which palette the debrief shows after the return is the open question of `notes/builtin_widgets.md` §8 item 1.

#### 9.3.6 State read / written
Read: `debrief.dbf` (objective records and units, `notes/campaign.md` §4.8), the current mission record (name id, debrief evaluator index, cash type and the four payment numbers), roster experience-at-start per `whoami`, option `dead` (65), coffers, item table (names), BKTXT/BRTXT tables.
Written **only when Done runs the completion** (nothing while paging): §9.9.

### 9.4 Asset inventory ✅ (bitmap sizes measured from `BITMAP.DLL`, fonts from `notes/fonts_glue.md`)
| Asset | Kind | Source | Size / frames / rule | Where and how used |
|---|---|---|---|---|
| `TroopBook` | bitmap | BITMAP.DLL (shared with troop selection, credits) | 640x480, 8 bpp, opaque | background of P2-P5 at (0,0) |
| `GreenATabUp` / `GreenATabDn0` | bitmap pair | BITMAP.DLL | 84x32 each | Done (`0x102`) at (325,448) |
| `RedATabUp` / `RedATabDn0` | bitmap pair | BITMAP.DLL | 84x32 | Next (`0x100`) at (525,448) |
| `BlueATabUp` / `BlueATabDn0` | bitmap pair | BITMAP.DLL | 84x32 | Back (`0x101`) at (425,448) |
| `BrownATabUp` / `BrownATabDn0` | bitmap pair | BITMAP.DLL | 84x32 | Abort (`0x103`): **not created in a debrief** (listed because ids are shared) |
| `Skull0`..`Skull4` | bitmaps | BITMAP.DLL | 9x10, 9x22, 21x22, 21x22, 15x18; 8 bpp, index 0 transparent | rank icon on P3 rows, centred (65, y_i+12) |
| banner sprite (2nd frame, 16x24 marker) | sprite set | resident banner sets named by the unit's `banner:` key (`notes/animations.md`, `notes/troop_selection.md` §3.3) | 16x24 | P3 row at (80, y_i); none if the set is not resident |
| `GameEndScreen`, `GameEndScreenSuccess`, `GameEndScreenFailure` | bitmaps | BITMAP.DLL | 640x480 each, own palette | shown on the glue window before the wrapper (§9.3.1); chosen by evaluator key |
| `RingMark`, `BookScroll0/1/2` | bitmaps | BITMAP.DLL | 65x45; 408x42, 408x42, 56x42 | **not used** on P2-P4 (P0/P1 only) |
| font slot 2 = `GLUE/PCTEXT.FON` "Warhammer Font 2" | font | GLUE/ | cell height 12, ascent 9 | title, headers, rows, body, button labels |
| font slot 4 = `GLUE/SUBTEXT.FON` "Warhammer Font 4" | font | GLUE/ | cell height 22, ascent 17 | P2 first line, P4 heading, P5 heading |
| `SwordCursor` (group 7), `HelpCursor` (group 10), `HandCursor` (group 2) | cursors | WHSHR.EXE resources | 32x32 mono | window default / Ctrl held / buttons; system hourglass while repainting |
| palette index 1 = BOOK | palette | `GLUE/GLUEBOOK.PAL` + `WIND/WINDBOOK.PAL` (`notes/palette_selection.md`) | 256 entries | set at open |
| `win.mid` / `lose.mid` / `tactical.mid` | music | `FILE/BINARY/MUSIC/` (+ FM twins, `notes/music.md`) | repeat 0 (loops) | win/lose by evaluator T for modes 2, 6, 7; tactical for mode 4 |
| `B4.WAV` / `B3.WAV` | sfx | glue speech directory | press / release-inside cues | every button; skipped while speech plays or is off |
| strings | BKTXT | 403, 404, 405, 406, 412, 419, 610, 611, 5000-5008, 5010-5024, 5040-5042, 10000-10148 (text programs), 601-603 (P5) | | §9.3.4 |
| strings | BRTXT | mission name (id from the mission record), 300, 301, 304, weapon 200+w, armour 100+a, item names via the item table | | buttons, title argument, rows |

Shared with troop selection: everything above. Unique to the debrief: the page painters, the enable table, the end-screen bitmaps' use. Nothing is a WND.DLL resource; no `[TEXT]`, `[ANIM]` or `[MIDI]` block exists for this screen.

### 9.5 Animation and glue
**No animation**: no sprite frames, scrolling or fade. Timers: the shared 250 ms timer (all modes, acted on only on P1) and the glue-side 50 ms end-screen timer that fires the wrapper (§9.3.1). Draw order per repaint: background; title; page content (P2 lines; P3 headers, then per row text, skull, banner sprite, then numbers; P4 heading, program lines, coffers pair); buttons are child windows above.
Glue: battle-end handler -> end-screen bitmap -> wrapper (campaign-over test, wounded bookkeeping, `PLAY.MRC` merge, `Z` handling) -> open -> Done -> completion/callback -> (`gocaravan:select` or pop + resume). `debrief:` / `debriefwithsummary:` skip the first two steps.

### 9.6 Hotspots / scripts
None (built-in window). The commands that open it and their numbers are in §9.2; WND.DLL scripts contain no `res:` name for it.

### 9.7 Input and exits (summary)
Mouse: buttons and (P3) Ctrl+click rows only; plain clicks on P2/P3/P4 do nothing. No keyboard beyond Ctrl. Exits: Done (§9.9), skip path, failure exits to the main menu.

### 9.8 State read / written
See §9.3.6 and §9.9.

### 9.9 Completion and exits
**9.9.1 Done, modes 2 and 6 (default completion)** ✅ (payment: `notes/debrief_evaluation.md` §6; effects: `notes/campaign.md` §1.2-§1.4, §3.3):
1. arrow cursor; 2. **mode 2 only**: coffers += the program's final total (mode 6 pays nothing); 3. armour rewards: the program is run again, each named regiment in the list with models gets +1 armour (its own and its leader's), debrief file rewritten;
4. experience: multiplier 2 if the program has the "2x" opcode (else 1), new `s_Exp = start + gained*multiplier`, promotions per `notes/campaign.md` §1.3, roster experience-at-start := new `s_Exp`, debrief file rewritten;
5. merge: mode 2 -> `ARMY.MRC` (heal, disband < 20 %, commander rule); mode 6 -> `ARMY.MRC` and `MARCH.MRC`, then `MARCH.MRC` re-derived (option `nobattle` skips these merges);
6. "returning wounded" counters of all roster entries cleared; 7. window destroyed (timer killed, buttons/bitmap freed, tune stopped and discarded);
8. **continue**: if the current mission has **no mission-script name** (or the never-set campaign-over flag) -> `gocaravan:select` behaviour; otherwise, for the encounter/callback variant pop **one** context then resume the parked script (plain variant: resume without popping). No palette call.
**9.9.2 Done, modes 4 and 7** ✅: coffers += the program's final total (once); window destroyed (tune stopped); pop one context (the script frame pushed at open); resume the script. No armour rewards, experience, promotions or merges.
**9.9.3 Skip path** (§9.3.1a): the same completion/callback runs immediately with no window; the tune had been started and is stopped by the completion.
**9.9.4 Bankruptcy P5 Done**: window destroyed, background cleared, all glue windows destroyed, front end returns to the main menu (troop selection only).
**9.9.5 Failure exits to the main menu**: (a) battle quit (valid word 0, `unrealquit` off): neutral end screen, main menu, no debrief, nothing saved (slot 5 autosave remains); (b) campaign-over test in the wrapper (commander regiment dead + `Z`, or `G`/`Y`): death movie, main menu, no debrief, no payment, no merge (`notes/debrief_evaluation.md` §3). With `unrealquit` **on** (developer option) a quit falls through to the normal path.

### 9.10 Engine status and deviations
Status: ✅ pages P2/P3/P4, the evaluator table (41 rows, 8 kinds) with its text programs, the mode/page/button state machine, the skip rule, win/lose/tactical music and Done (issue #123 / GEI8) are implemented:
`whshr/debrief_rules.py` (evaluators, text programs), `whshr/debrief_screen.py` (pure page model and drawing lists), `whshr/debrief_scene.py` + `whshr/frontend/debrief_view.py` (scene and painter), `whshr/debrief.py` and `whshr/debrief_rewards.py`
(Done: payment, armour rewards, doubled experience, promotions), `whshr/payments.py` (cash programs and their step list for P4). A battle now ends in the debrief screen (mode 2 with `playgamewithdebrief`, mode 6 otherwise; the plain "Victory!/Defeat" `ResultScene` still shows first);
`debrief:`/`debriefwithsummary:` open modes 4/7. `testmission:` runs the same evaluator (and the last mission's status bits). No-battle mode keeps skipping the screen.
Deviations and gaps (all reported in the campaign log `debrief` row as *skipped*): the engine measures no objective itself, so a played battle's records are derived from its outcome (`payments.played_results`: a win is the flawless result, a loss meets `Z`);
kills and experience are credited per model in battle (`notes/casualty_bookkeeping.md` §2) and the wounded, healing and disbanding bookkeeping runs before the screen and at Done (§3, `whshr/casualties.py`); routed models rejoin at Done rather than at the next troop selection, the campaign-over test is not run, and allied NPC regiments are not merged back;
wizard promotions require a known Celestial, Bright or Amber spell to identify the college; the `K`/`X` item-pickup line needs an item-name table the engine does not have; Ctrl+click opens no view-only roster book; the end-screen bitmaps and the campaign-over/quit routes of §9.9.5 are not implemented; the mode-6 P4 page is unreachable as specified.

### 9.11 Test scenarios (BDD; run on several missions)
1. Given `bf003` won (evaluator n = 2, key `Z`, list A) opened in mode 2, when P2 is drawn, then its first line is `BKTXT 10008` in the heading font at y = 146, the following lines at y = 190 + 12k, and Next leads to P3, then P4; Back on P2 is disabled.
2. Given a mode-6 debrief with 13 regiments (3 unit pages), when Next is pressed on P3 page 2, then it is disabled and no P4 is reachable; Done does not add coffers but merges ARMY and MARCH.
3. Given mode 7 (`debriefwithsummary:11`), when Next is pressed on P2 then P4 shows and Back returns to P2; Done adds the final payment once, pops the context and resumes the script, without promotions.
4. Given mission `bf001` defeated (n = 6, list B none), when the battle ends in mode 2, then no window opens, the payment/merges still run, and the caravan or script continues.
5. Given the Grudgebringer Infantry with `lost = 7` and option `dead = 65`, when P3 is drawn, then wounded = 4, dead = 3, kills and experience gained come from the file and the doubled value is not shown.
6. Given a cash program with armour lines and a regiment with 0 models in the debrief, when P4 is drawn, then that regiment's armour line is absent and takes no vertical space.
7. Given a quit in battle (valid 0), when the battle ends, then the main menu is shown and no debrief file is read.
8. Given the Next button label, then it is drawn centred on the art plus (+4,+2) released and (+3,+3) pressed.

### 9.12 Open questions
- 🟡 End-screen hold time (§9.3.1); whether the end-screen bitmaps' palette is restored to palette 2 before the BOOK palette is set.
- 🟡 P3 row colours for units whose `hired` flag is 0 (whether the loader sets `hired` for debrief units was not traced).
- 🟡 Allied NPC units in the P3 table (no filter found).
- ⬜ Zero-unit edge case (page count 0 draws six rows in the original); ⬜ exact palette shown after returning from the roster book to P3.
- ⬜ Design intent of the unpaid mode-6 balance page (already in `notes/debrief_evaluation.md` §8).

## 10. Roster book (Army Records) ✅

Marks: ✅ verified from data and cross-checked, 🟡 inferred / not observed running, ⬜ open. Full-game windows only. All y values assume
body font height h = 12 (glue slot 2, `PCTEXT.FON`, 12 px); formulas are given with h. Covers the caravan entries `ArmyBook` and
`HireOnlyArmyBook`, the reinforcement sub-window and the leader-portrait box. The same window is also opened from the troop window
(§11.5.6); this section owns the parts both share (button strip §10.3.3, text helpers §10.3.4, hand-off §10.5).

### 10.1 Purpose
A browser-plus-hire window over the company of `ARMY.MRC`: one regiment per double page (picture, name, cost, experience on the left;
information or statistics on the right). In the caravan it also lets the player hire/fire regiments and take offered reinforcements.
`ArmyBook` hires/fires without money; `HireOnlyArmyBook` (recruit caravans) charges/refunds the coffers at once.

### 10.2 Where it appears (✅ scan of all WND scripts)
| Opening window | Hotspot x, y, vx, vy | Hint (BRTXT id) | cursor / altcursor | `res:` |
|---|---|---|---|---|
| `CaravanCommon4` (included with `script:CaravanCommon4` by 13 windows: `CaravanSelectMission`, `StartCaravan`, `CaravanAfterMission`, `CaravanAfterMissionWithRecruit`, `InfoCaravanREC/REA/LA/WED/ENA/LB/BPC/ENE/BMA`) | 0, **299**, 164, 47 (an older y = 245 is commented out) | 151 | `HandOpenCursor` / `HandCloseCursor` | `ArmyBook` |
| `CaravanCommon5` (7 windows: `CaravanAfterEncounter`, `CaravanContinueMission`, `CaravanAfterEncounterWithRecruit`, `CaravanRecruitNoSpeechAndResume`, `CaravanRecruitAndResume`, `InfoCaravanSZA`, `InfoCaravanSZB`) | 0, **299**, 164, 47 | 151 | same | `HireOnlyArmyBook` |
| `CaravanDietrich` (own window) | 0, 245, 164, 47 | 151 | same | `ArmyBook` |
| `Start` (first window of a new game) | 0, 245, **165, 40** | 151 | same | `ArmyBook` |

Every hotspot also carries `script:armybook.wnd` (no such resource: documentation only), no `upsfx/downsfx`, no `linkid/count/clickres`.
Each of the 20 caravan windows has exactly one of the two hotspots; 5 hotspot definitions in total (4 ArmyBook, 1 HireOnly).

### 10.3 Construction

#### 10.3.1 Calling sequence ✅
1. The launcher (§13) pushes the current window, records caller **name** and **mode**, all glue windows are destroyed.
2. The book resets its state: page = Information, current regiment = **0** (cleared at every caravan open, so a visit always starts on the
   first regiment), dirty = 0. Previous company freed; `HireOnly` also empties the marching list (it stays **empty**: forced regiments are
   flagged hired/selected but are not put on the list).
3. `ARMY.MRC` is loaded. If loading fails nothing opens (stack stays pushed: black screen).
4. Initial flags (as troop selection, §11.3.4): every forced regiment (whoami 2, or listed in the mission's forced list) becomes hired, also
   selected unless destroyed. Then a **snapshot** of every `hired` flag is taken, stored prices are computed (per-model price x
   (models + routed)) and reinforcement offers: offered = min(roster reinforcements of that whoami, orgsize - (wounded + models + routed)),
   taken = 0.
5. Window class with `SwordCursor`, 640x480 child at (0,0), thin border; palette **9 (BK2, `GLUEBK2/WINDBK2.PAL`)**; buttons created;
   off-screen bitmap painted; shown and given keyboard focus. No music started/stopped, no speech, no animation.
6. Hire-capable is always true for both caravan entries (Hire and Abort exist); money = 0 for `ArmyBook`, 1 for `HireOnly`.

#### 10.3.2 Window ✅
640x480 at (0,0). Everything is painted into an off-screen bitmap (bitmap `ArmyBook` first) and blitted on erase-background; when only the
pages change, rectangle (0,0)-(640,440) is repainted, so the button strip is not erased. Colours come from the current palette.
Fonts: body slot 2 (`PCTEXT.FON`, 12 px); regiment name = slot 5 (`GOTHTEXT.FON`, 40 px blackletter) with a `FancyLetters` drop cap (same
title routine as the §5 (Magic book)); button labels slot 2.
Text colours: left-page cost and experience lines **black**; regiment name **(67,47,39)**; every right-page text (headings, stats,
equipment, leader name, description, status line) uses one state colour: **grey (127,127,127) when the regiment is currently not hired,
black when hired, red (255,0,0) when "destroyed"** (models + routed = 0, or artillery with fewer than 2). Page columns: left x = 50..290,
right x = 350..590 (240 wide).

#### 10.3.3 Button strip ✅ (shared by the troop window §11.3.3 and debrief §9)
All 84x32 at y = 448, `BS_OWNERDRAW`, hand cursor, shared owner-draw and click-cue subclass.
| id | Label (BRTXT) | x | Art up / down | Enabled | Action |
|---|---|---|---|---|---|
| 0x105 | 321 "Stat" on Information, 322 "Info" on Statistics | 14 | `PurpleATabUp` / `PurpleATabDn0` | always | toggle right page |
| 0x106 | 319 not hired, 320 hired | 104 | `VioletATab*` | §10.3.6 | hire/fire |
| 0x107 | 307 | 194 | `BrownBTab*` | dirty flag set | Abort |
| 0x102 | 304 | 350 | `GreenATab*` | always | Done |
| 0x101 | 301 | 440 | `BlueATab*` | index > 0 | previous regiment |
| 0x100 | 300 | 530 | `RedATab*` | index < count - 1 | next regiment |
(0x104 `BlueBTab*` is not a window: it is only the command id sent by PageUp; 0x101 and 0x104 do the same.) Creation order: Back,
[Hire, Abort], Next, Stat, Done. Hire and Abort exist only in hire-capable books.

**Owner-draw paint (shared by every tab-style button):** art = `...Up` normally, `...Dn0` while the button is selected (pressed);
disabled buttons show the Up art. Label = window text, font slot 2, centred on the art (`(w - textW)/2`, `(h - textH)/2`), then shifted by
**(+4, +2) released and (+3, +3) pressed**. For h = 12 on a 32-high button: label top y = 448 + 10 + 2 = 460 released, 461 pressed. Text
colour (255,255,0) enabled, (192,192,192) disabled; no focus rectangle. Sub-window buttons (§10.3.5) use offset (0,0) and **black** text.
**Click cues:** press (mouse-down) = `B4.WAV`, release inside the control = `B3.WAV`, both in the glue speech directory (11025 Hz, 8-bit,
mono; 0.050 s / 0.018 s); skipped while a speech line is playing and when speech is off.
Keyboard (window must have focus; buttons take focus when clicked, so 🟡 keys work only until the first click): PageUp = Back if enabled;
PageDown = Next if enabled; Home = regiment 0; End = last; Esc/Enter nothing.

#### 10.3.4 Drawing ✅ (h = 12; order = order of painting)
1. `ArmyBook` at (0,0).
2. **Left page** (x centred in 50..290: x = 50 + (240 - w)/2):
   - cost line at y = 410 - h = 398: if money variant and the regiment was **not hired at open**: `BKTXT 509` with the price; otherwise
     `BKTXT 501` with **(retainer, price)** in that order. price = price-per-model x (models + routed); retainer = price x 10 / 100.
   - experience `BKTXT 500` with the Exp value at y = 410 - 2h = 386.
   - name block: top y = (410 - 3h) - B = 374 - B, B = max(40 x lines - 1, cap height) (cap = `FancyLetters` glyph rectangle: 74 for most
     letters, 84-87 for F H J P Q Y, 75-80 for K N X; §5 (Magic book)). Name = unit name with `_` and `<` replaced by spaces; first letter as drop
     cap, rest in slot 5, wrapped in 240 with the cap-width indent for lines above the cap bottom, block centred by its widest line.
     🟡 Simulated with the real GOTHTEXT widths for all 38 names: B = 74 (1 line: whoami 9, 15, 20, 29, 31, 34), 79 (2 lines, most),
     84 (25, cap H), 119 (3 lines: 13, 36, 37); top y = 300 / 295 / 290 / 255.
   - picture (`<Name>Pic`, table in §10.3b) bottom edge 4 px above the name block: y = (374 - B) - 4 - h_pic; x = 50 + (240 - w)/2. None for
     whoami 32.
   - `ForHireStamp` at (50, 35) when the regiment is **currently** not hired (drawn last, over the picture top).
   - status line (both pages), `BKTXT 502` "Active a Wounded b": a = models + routed, b = 65 % x (casualties - routed) (65 = 100 - option
     `dead`; 0 in caravans because counters are reset after each battle). Skull icon `Skull<n>`, n = ((pntval & 31) x 4)/31 (0..4). Group
     width W = iconW + 6 + textW, x0 = 350 + (240 - W)/2; icon at (x0, 385); text at (x0 + iconW + 6, 385 + (iconH - 12)/2).
3. **Right page, Information** (default): heading `BKTXT 504` **left-aligned at (350, 39)**. y0 = 39 + 2h = 63.
   - regiment picture = frame of the unit's banner set (first record 72x104) at (350, 63), always (also for heroes).
   - unless the regiment is a *hero* (has a leader and `s_orgsize` = 1): `BKTXT 408` at (350, 169), armour `BRTXT 100 + s_armr` at (350, 181),
     weapon `BRTXT 200 + s_weponame` at (350, 193).
   - if a leader exists: leader box (§10.3.7) at (470, 63); leader name at (470, 169) (raw, **`_` not replaced** 🟡), armour (470, 181),
     weapon (470, 193) (no `BKTXT 408` heading in the leader column).
   - description (RCDATA of `BKTXT.DLL` named by the table, latin-1): x = 350, first line y = y0 + 106 + 4h = **217**, 240 wide, plain body
     font, **no drop cap**, no `@`/`#` spans, ends at the first ESC byte, single paragraph in all 29 shipped texts (a CR/LF break would indent
     the next line by 3 x width("X") = 21). Simulated 4-11 lines, bottom <= 349. Placeholder `NullText` (whoami 32) drawn as stored.
4. **Right page, Statistics**: heading `BKTXT 503` at (350, 39). Non-hero: portrait (350, 63); rows i = 0..8 at y = 63 + 12i: `BRTXT 700 + 2i` at
   x = 428, `BRTXT 701 + 2i` at x = 538, value (s_move, s_wepn, s_bals, s_strn, s_tuff, s_wnds, s_init, s_atks, s_lead) left-aligned at
   x = 573. Then y = 63 + 116 = 179. With a leader (block starts at y = 179, or at 63 for a hero): leader name at (350, y), leader box at
   (350, y + 12), leader stat rows at x = 428/538/573 from y + 12, row height 12.
5. Reinforcement sub-window on top (§10.3.5), then buttons.

**Shared text helpers** (also used by the troop rows §11.3.5): rank icon `Skull<n>` with n = ((pntval & 31) x 4)/31; name text `_`/`<` -> space;
`"%s/%s"` = `BRTXT 200 + weapon` / `BRTXT 100 + armour`; state colours grey (127,127,127) not hired / red (255,0,0) destroyed / black.

#### 10.3.5 Reinforcement sub-window ✅
Child class `ReinforcementsWindow`, id 0x200, 144x134 centred in the book: origin (248, 173). Shown by every page-change/hire repaint when the
regiment on screen has offered > 0 (hire-capable books only); closed and re-created each time. Background = copy of the book image behind
it, then `reinfScroll`. Text black, slot 2, centred in 144: heading `BKTXT 505` y = 16; `BKTXT 507` (offered - taken) y = 46; `BKTXT 508`
(taken) y = 46 + 12 + 2 = 60.
| id | rect in window | art | label |
|---|---|---|---|
| 0x201 Take | (12, 110) 116x20 | `reinfButtonUp` / `reinfButtonDown` | `BRTXT 319`, black, offset (0,0): y = 110 + 4 |
| 0x202 +1 | (29, 85) 11x13 | `reinfArrowUp` (same art pressed) | none |
| 0x203 -1 | (104, 85) 11x13 | `reinfArrowDown` (same art pressed) | none |
+1 (taken < offered): taken += 1 and the regiment's model count += 1 at once; -1: the reverse; Take: offered = 0, roster reinforcements -= taken,
the window closes, dirty recomputed, and if taken > 0 the right page area (350,35)-(590,410) is repainted. Paging away closes the window; taken
persists. 🟡 Quirks: dirty is recomputed only on Take and hire/fire, not on +1/-1; +1/-1 repaint only the rectangle (50,360)-(290,410) and the
window text, so the "Active" status stays stale until Take.

#### 10.3.6 State read/written ✅
Read: `ARMY.MRC` (per unit: name, whoami, `hired`, `s_size`, `s_orgsize`, `s_routed`, `s_calualties`, `s_Exp`, stat bytes, banner set/frame,
leader name/portrait/stats), roster table (for-hire flag, artillery flag, price per model, reinforcements), coffers, forced list, options.
Hire/Fire enable (recomputed at every paint): base = for-hire flag of the whoami. Money variant: disabled if hired at open; otherwise enabled
iff (currently hired) or coffers >= stored price (overrides the for-hire flag; unreachable in shipped data). Toggle: flips `hired`; hire adds
to the marching list if count < limit and (money variant, not hired at open) coffers -= stored price; fire removes from the list and
coffers += stored price (stored price = computed at open, not updated by reinforcements). Abort enabled = dirty (a hired flag differs from the
snapshot, or a taken count != 0).
Done (dirty only): whole company written to `ARMY.MRC` (file order); money variant also merges the marching list (units hired this visit) into
`MARCH.MRC` (appending those not present, hired = 1) and refreshes `MARCH.MRC`'s unit copies from the new army. Then close.
Abort: restores every `hired` flag from the snapshot, writes nothing, closes. 🟡 Quirks: coffers are **not** restored; marching-list edits are
not undone; Taken reinforcements stay deducted from the roster although `ARMY.MRC` is not written (the men are lost).

#### 10.3.7 Leader portrait box ✅ (shared with the troop window, §11.5.6)
72x104 at the given position. Step 1: background = frame 0 of `BACKALL` (sprite-table 123; 21 frames, 120x152) cropped at window (cx, cy);
step 2: portrait = frame 0 of the leader's portrait set (120x152) cropped with the same window; index 0 transparent, raw indices with palette 9.
(cx, cy) comes from the 37-entry resident list, found by the leader's sprite-table index (`notes/glue_portraits.md` §1.3; identical to
`whshr/portraits.py`). Not found (all artillery: leader portrait `VoidType`; whoami 14, 15, 16, 17, 25): background window (25, 5) and the
regiment's banner drawn whole (72x104) instead of the portrait.

### 10.3b Asset inventory ✅
| Asset | Kind | Source | Size / frames / rule | Use |
|---|---|---|---|---|
| `ArmyBook` | bitmap | BITMAP.DLL | 640x480, 8 bpp, palette group `f7c3160f` (same as `EncyBook`) | background (0,0) |
| `ForHireStamp` | bitmap | BITMAP.DLL | 98x61 | (50,35), not hired |
| `<Name>Pic` x28 distinct | bitmap | BITMAP.DLL | table below | left page |
| `Skull0..Skull4` | bitmap | BITMAP.DLL | 9x10, 9x22, 21x22, 21x22, 15x18 (no Skull5) | status line |
| `FancyLetters` | bitmap | BITMAP.DLL | 640x480; 30 glyph rects (§5 (Magic book)) | name drop cap |
| `reinfScroll` | bitmap | BITMAP.DLL | 144x134 | sub-window background |
| `reinfButtonUp` / `reinfButtonDown` | bitmap | BITMAP.DLL | 116x20 each | Take up / pressed |
| `reinfArrowUp` / `reinfArrowDown` | bitmap | BITMAP.DLL | 11x13 each | +1 / -1 (no pressed twin) |
| `PurpleATab`, `VioletATab`, `BrownBTab`, `GreenATab`, `BlueATab`, `RedATab` (`Up`, `Dn0`) | bitmap | BITMAP.DLL | 84x32 each (12 bitmaps) | strip (`BlueBTab*` exists, unused as a window) |
| banner sets `BAN*` (`banner:`) | sprite set | `FILE/BINARY` `.FOL/.BOP/.PAL` (or UPDATE) | 3 frames 72x104, 16x24, 32x32; first record used; 30 resident sets, all 38 regiments' banners resident | right-page picture |
| leader portrait sets (MER2, MER1, COMM, GINF, RAMO, CARO, REIK, HOLG, ELF1, HAMM, IRON, DWA1-4, CELE, BRIW, AMBE, BERN, HALB, XBOW, KEEL, CER2, ENGR, GOTR, AZGU, TREE ...) | sprite set | `.FOL/.BOP` (no `.PAL`) | 6-8 frames, frame 0 = 120x152 | leader box |
| `BACKALL` | sprite set | `.FOL/.BOP` | 21 frames 120x152, frame 0 used | leader box background |
| description texts (29 used) | RCDATA | `BKTXT.DLL` | 6-354 bytes | Information page |
| palette 9 | palette | `GLUEBK2.PAL`/`WINDBK2.PAL`; 2 on exit through the caller path | | window |
| fonts | font | slot 2 `PCTEXT.FON` 12 px; slot 5 `GOTHTEXT.FON` 40 px | | text |
| cursors | cursor | `SwordCursor` (window), `HandCursor` (buttons), `HandOpenCursor`/`HandCloseCursor` (caravan hotspot) | 32x32, hotspot (0,0) | |
| click cues | wav | `B4.WAV` press, `B3.WAV` release (glue speech dir, `REMOTE/BINARY/GLUE/SPEECH` here) | skipped when speech off or busy | every button incl. sub-window |
| strings BKTXT | | 408, 500-505, 507-509 | | |
| strings BRTXT | | 100-113 (armour), 200+ weapon (ids used 1,3,4,11-17,22,24,26,27; 31 -> BRTXT 231 **absent**: blank line), 300, 301, 304, 307, 319-322, 700-717, 151 (hint) | | |

Picture / description table by whoami (0..37): 0 `VanheimPic` 142x203/`VanheimText`; 1 `RagnarsWolvesPic` 155x208; 2 `Grudgebringers1Pic`
117x198/`GrudgebringersText`; 3 `Grudgebringers2Pic` 150x195/same text; 4 `BlackAvengersPic` 116x162; 5 `GreatswordsPic` 70x202; 6 `ReiksguardPic` 99x203;
7 `LeitdorfPic` 117x196; 8 `WoodElfArchersPic` 153x200; 9 `DwarvenSlayersPic` 141x201; 10 `DwarvenHammerersPic` 125x143; 11, 12 `IronBreakersPic`
116x190; 13 `GyrocopterSquadronPic` 208x136; 14 `CannonCrewPic` 177x131/`ImperialCannonCrewText`; 15 same pic/`CannonCrewText`; 16, 17 `MortarCrewPic`
157x138; 18 `CelestialWizardPic` 156x200; 19 `BrightWizardPic` 119x201; 20 `AmberWizardPic` 144x195; 21, 22 `CarlssonPic` 98x190; 23, 24 `DwarfWarriorsPic`
133x198; 25 `VolleyGunPic` 144x140; 26 `NulnHalberdiersPic` 115x191; 27 `MercCrossbowmenPic` 93x174; 28 `LongbowsPic` 93x191; 29 `CeridanPic` 133x193;
30 `DwarfCrossbowPic` 130x142; 31 `DwarfEnvoyPic` 141x180; 32 no picture/`NullText`; 33 `DwarfWarriorsPic`; 34 `TreemanPic` 191x199; 35 `CarlssonPic`;
36, 37 `GyrocopterSquadronPic`. Description = `<Name>Text` of the same stem except: `Grudgebringers*` -> `GrudgebringersText`, 14 -> `ImperialCannonCrewText`,
15 -> `CannonCrewText`, 16/17 -> `MortarCrewText`, 11/12 -> `IronBreakersText`, 23/24/33 -> `DwarfWarriorsText`, 21/22/35 -> `CarlssonText`,
13/36/37 -> `GyrocopterSquadronText`. The engine tables in `army_records_view.py` match this ✅.
Shared with other windows: `ArmyBook`/`FancyLetters` (Encyclopedia/Magic book), tab art, fonts, cursors, palette 9 (troop window), cues. Unique:
`ForHireStamp`, `Skull*` (also troop rows), `reinf*`, `*Pic`.

### 10.3c Animation and glue ✅
**No animation, no timer.** Repaints only on entry and after clicks/keys. Glue: caravan hotspot -> launcher pushes the caravan window and stores its
(name, mode) -> destroys glue windows -> book built (§10.3.1). Layers: bitmap, left page, right page, status line, sub-window (child), buttons
(children). Exit (Done or Abort): window and buttons destroyed, company freed, palette 2 set, one context frame popped (§13), the caller
re-opened by name with the saved mode (fresh instance, its `[INIT]`/`[MIDI]` run again). Coffers are the global value changed live by hire/fire;
`ARMY.MRC`/`MARCH.MRC` are written only on Done. No events are emitted to the interpreter.

### 10.4 Hotspots
Only the caravan hotspots of §10.2; no click areas on the pages.

### 10.5 Input, exits and the hand-off from the troop window
Mouse: buttons only. Exits: Done, Abort (only when dirty). No Esc. Hand-off: the troop window opens the same window with a **parent window** instead
of a caller name: no palette change, no context pop, the parent is re-shown and repainted on close; Hire/Fire semantics there are in §11.5.6.

### 10.6 Engine status and deviations (`whshr/roster_book.py`, `frontend/army_records_view.py`, `campaign_scenes.ArmyRecordsScene`)
✅ button set, x positions, labels, enable rules for Back/Next/Abort, picture/description tables, Skull formula, reinforcement geometry, leader crop
windows. Deviations to fix:
1. Tab-label offset: engine (2,4)/(3,3); real (+4,+2)/(+3,+3).
2. Take label colour: engine yellow, real black.
3. Cost line arguments: engine (price, retainer), real (retainer, price); price must be models + routed and the stored per-model price.
4. ✅ Left page now draws the name with slot 5 blackletter and a `FancyLetters` drop cap, with the picture bottom-anchored 4 px above
   the name block. The description also stops at its first ESC byte.
5. Headings `BKTXT 503/504` are left-aligned at x = 350, not centred.
6. Status line: real on both pages, group-centred; engine only on Information, icon centred at x = 380.
7. Information page: no `BKTXT 408` heading in the leader column; regiment equipment omitted for heroes (leader present and `s_orgsize` = 1, not
   models = 1); description y = 217 for everyone, no drop cap. Statistics: regiment block also drawn when a leader exists; leader name above the leader
   box; leader block below the regiment block for non-heroes.
8. Right-page state colour (grey not hired, red destroyed) missing; `destroyed` must count routed models.
9. Description must cut at the first ESC; leader names are not underscore-cleaned in the original (🟡).
10. Abort: engine reverts taken reinforcements and prunes the list; original keeps them deducted. HireOnly list should start empty. Money-variant Hire
    enable ignores the for-hire flag in the original.
11. Caravan hotspot rects must come from the scripts (y = 299 Common4/5, 245 Dietrich/Start), not be hard-coded.

### 10.7 Test scenarios
1. Given a company of two regiments and ArmyBook opened from a caravan, when it opens, then regiment 0 on Information is shown, Back disabled, Next enabled, palette 9, and Done returns to the caller with palette 2.
2. Given HireOnlyArmyBook, coffers 300, an unhired for-hire regiment of price 200, when Hire is pressed, then coffers are 100, the label reads Fire, Abort is enabled; when Abort is pressed, then hired is restored, coffers stay 100, `ARMY.MRC` unchanged.
3. Given a regiment with offered 3, when the page shows it, then the sub-window appears at (248,173); +1 twice then Take gives models +2, offered 0, roster reinforcements -2 and the sub-window does not reappear.
4. Given a regiment with cost 400, then the cost line shows retainer / price = 40, 400 at y = 398, experience above it.
5. Given the Grudgebringer Cavalry (leader Commander) on Statistics, then the leader box at (350,191) uses BACKALL frame 0 and COMM frame 0 cropped at (26,6).
6. Given a cannon crew (leader void portrait), then the leader box shows the crop (25,5) background plus the full banner.
7. Data tests: all string ids of §10.3b exist (except BRTXT 231), all 28 pictures / 29 descriptions / 30 banner sets exist, every leader portrait index of the shipped company is in the resident list or void.
8. Given any strip button, when pressed then released inside, then B4 then B3 play (not while speech plays / speech off); label offset (+4,+2) released, (+3,+3) pressed.

### 10.8 Open questions
🟡 leader-name underscores and blackletter block heights never seen on screen; 🟡 keyboard focus loss after a click; 🟡 reinfScroll/portrait
transparency (index 0 assumed); ⬜ what `s_orgsize` = 1 non-hero units with a leader look like (none in shipped data); ⬜ marching-list merge details
(`MARCH.MRC` unit copy refresh).

## 11. Troop-selection window (pre-battle pages) ✅

Marks: ✅ verified from data and cross-checked, 🟡 inferred / not observed running, ⬜ open. Full game only. Pages P0 / P1 / P5 (pre-battle);
post-battle pages P2-P4 are in §9 (Debrief) and not repeated. Builds on `notes/troop_selection.md`. H = height of glue font slot 2
(`PCTEXT.FON`, 12 px); H4 = slot 4 (`SUBTEXT.FON`, 22 px). The button strip (label offsets, click cues, art), the text helpers (rank icon, weapon/armour
line, state colours) and the leader box are shared with the Roster book and described there (§10.3.3, §10.3.4, §10.3.7); context-stack terms (push, pop,
CleanUp, caller name/mode) are in §13.

### 11.1 Purpose
Opened by Accept on the campaign map or a briefing panel. P0: choose which regiments march (limit, forced and excluded regiments, costs).
P1: marching order (drag to reorder). Done on P1 pays, writes `MARCH.MRC`/`ARMY.MRC`/`PLAY.MRC` and starts the mission. P5: "cannot afford the
forced regiments" page. Abort returns to the window that was current at Accept.

### 11.2 Where it appears
| Trigger | Open mode | First page |
|---|---|---|
| Accept (slot 1) of a mission panel (panel types 1, 2, 5; §12) on the map or a briefing | 0 | P0 (P5 if bankrupt at open) |
| (no caller) | 1 | P1 alone: its button-enable routine does nothing, so Next/Back/Done are all enabled; dead code ✅ |
| debrief callers | 2, 4, 6, 7 | see §9 (mode 3 also unused) |
Mode 5 is never passed in; it is set at open when bankrupt. The window has no WND.DLL resource and no hotspot of its own.

### 11.3 Construction

#### 11.3.1 Calling sequence (mode 0) ✅
Accept handler, in order: resume the game timers if paused; drain pending panel events; reset the map's per-window state; **stop and discard the map's
tune**; clear the "current battle script" variable; **push the current context frame** (§13; this also pushes the caller record = name and mode of the
window most recently opened by name, i.e. the map/briefing); destroy all glue windows; open the troop window with file `ARMY.MRC`, title argument = the
highlighted mission row's name id (`BRTXT` id, first field of the row; an override id set by some scripts wins), the caller (name, mode), mode 0, no
completion callback.
Open, in order: clear window state; free any loaded company; load the company (`ARMY.MRC`); if load fails, mode 0 runs Done at once (no window); start
`binary/music/tactical.mid` (repeat 0 = loop; win/lose tunes only for mode 2); page count = ceil(units/6) (units = every record in the file); mode 0:
initial selection (§11.3.4) and bankruptcy test (§11.3.7); palette index 1 (BOOK); build the three title strings (`BKTXT 400/401/403` with `%s` =
`BRTXT <mission name id>`, 63 chars max); off-screen 640x480 bitmap; window; buttons; first visible P1 row = 0; show, repaint; store the return (name,
mode); start a 250 ms timer (id 3); set the "ready" flag (clicks/moves before it are ignored). Music starts before the bankruptcy decision, so P5 also
plays tactical.

#### 11.3.2 Window ✅
Class `TroopWindow`, class cursor `SwordCursor`, no background brush, child of the main window at (0,0), 640x480 (child style + thin border flag; the
client area is painted whole). Paint = off-screen 8-bit bitmap in the current palette, blitted; the page is redrawn only when flagged dirty
(hourglass cursor while redrawing). Text transparent, font slot 2, black unless stated. Erase/paint only cover y < 440 for partial updates (the
button strip is child windows).

#### 11.3.3 Controls ✅ (owner-drawn, class cursor `HandCursor`, all 84x32 at y = 448; paint and cues as §10.3.3)
| Id | Label | x | Art up / pressed | Exists |
|---|---|---|---|---|
| 0x103 Abort | `BRTXT 307` | 225 | `BrownATabUp` / `BrownATabDn0` | mode 0 only |
| 0x102 Done | `BRTXT 304` | 325 | `GreenATabUp` / `GreenATabDn0` | always |
| 0x101 Back | `BRTXT 301` | 425 | `BlueATabUp` / `BlueATabDn0` | not in mode 5 |
| 0x100 Next | `BRTXT 300` | 525 | `RedATabUp` / `RedATabDn0` | not in mode 5 |
Label offset (+4,+2) released / (+3,+3) pressed; yellow (255,255,0), light grey (192,192,192) disabled; disabled art = the Up bitmap. Click cues:
press `B4.WAV`, release inside `B3.WAV`, skipped while speech plays / speech off.
**Buttons are ignored while a P1 drag is in progress** (a carried regiment): Next, Back, Done and Abort do nothing then.

Enable rules (re-evaluated after every page change or toggle) ✅:
| Page | Next | Back | Done |
|---|---|---|---|
| P0 | page < pages-1 | page > 0 | selected count != 0 (**not** affordability) |
| P1 | disabled | enabled | enabled |
| P5 | not created | not created | enabled |
Done on P0 acts only if count != 0 **and** total cost <= coffers + prepaid (otherwise the enabled-looking button does nothing: no message, no
sound). Transitions: Next P0 page+1; Back P0 page-1; P0 Done -> P1 (no clamp of the P1 scroll position, §11.5.4); P1 Back -> P0 on the last page; P1 Done ->
§11.5.3; P5 Done -> §11.3.7; Abort -> §11.5.2.

#### 11.3.4 Initial state at open ✅
For every active record (record flag bit 0): not forced -> selected = 0 (hired unchanged); forced (whoami 2 or in the mission's forced list, whoami+1
values, 8 each) -> hired = 1 and selected = 1 unless destroyed. Prices fixed for current models. Selection list = selected records in file order (forced
first only if they come first in the file).

#### 11.3.5 Drawing P0 ✅ (Y positions use H)
- Background `TroopBook` at (0,0). Title `BKTXT 400` centred (x = 320 - w/2), y = 25, black. Headers at y = 50: `BKTXT 409` x = 345, `410` x = 425, `413` x = 505.
- Rows i = 0..5 of the page (rows_on_page = 6, or the remainder on the last page): `y_i = 50 + H + 4H i`.
  - Numbers (x = 345 price, 425 retainer, 505 pay), each `"%d %s"` with `BKTXT 414`: price = models x price-per-model, retainer = price x 10 / 100
    (integer), pay = price if selected else retainer; **or** one status text at x = 345 instead (order: not hired `BKTXT 415`; excluded `416`, or `418` for
    whoami 29/31, `420` for whoami 13/36/37; destroyed `417`). Colour of numbers/status: grey (127,127,127) if not hired or excluded, red (255,0,0) if
    destroyed, else black. ("Excluded" never applies to whoami 2.)
  - Then the shared row painter (x0 = 45): name line at (x0+60, y_i) formatted `"%s %d (%d)"` = name, models (= current + routed), original size; line 2 at
    (x0+60, y_i+H) `"%s/%s"` = `BRTXT 200+weapon` / `BRTXT 100+armour`; both lines grey if not hired, red if destroyed (destroyed wins), else black (an
    excluded but hired regiment's name stays black). Rank icon `Skull<n>`, n = ((pntval & 31) x 4)/31, centred on (x0+20, y_i+12) = (65, y_i+12); banner
    sprite at (x0+35, y_i) = (80, y_i) (2nd frame of the resident banner set, 16x24; none if not resident; `notes/troop_selection.md` §3.3). The colour after
    the row is restored to the previous colour, except after a destroyed row where it becomes the first colour set (grey/black) 🟡 (affects only the total
    line colour). An optional scroll strip is drawn only for style != 0 (not on P0).
  - `RingMark` at (45, y_i - H) if the regiment is selected, drawn after the row (over icon and text).
- Total line at y_t = 50 + 4H x rows_on_page: label `BRTXT 303` right-aligned to x = 495, value `"%d %s"` (total cost, `BKTXT 414`) at x = 505; both red when
  total cost > coffers + prepaid.
- `BKTXT 5006` (`%d` = coffers + prepaid) centred at y = 400 - 2H, black; `BKTXT 613` at (45, 400 - 2H) black when selected count >= limit.
- `BRTXT 314` centred at y = 400, blue = **pure (0,0,255)**; `BRTXT 316` centred at y = 400 + H, same blue.
Total cost = sum over every active record of: price if selected, plus retainer if hired and not selected. **It does not check excluded/destroyed**, so
retainers of hired excluded regiments (and destroyed artillery with >= 1 model) are charged ✅.

#### 11.3.6 Drawing P1 ✅
Background, title `BKTXT 401` (y = 25). Visible rows: from `first` to min(count, first+7) (7 rows); row k: `y_k = 50 + H + 4H k`. Per row: `BookScroll0` at (145, y_k-10)
(408x42); order badge `BookScroll2` (56x42) at (83, y_k-10) with the 1-based number (`"%d"`, black) at x = 83 + (25 - w)/2 + 15, y = (y_k-10) + (24 - h)/2 + 10;
row content with the P0 row painter using x0 = 157 (name at 217, icons at 177/192, same relative offsets), style 1. No ring mark, no numbers/status.
Hints: `BRTXT 315` blue centred y = 400, `BRTXT 316` blue y = 400 + H. No money lines.

#### 11.3.7 P5 bankruptcy page ✅
At open (mode 0, after the initial selection): if coffers + prepaid < sum of prices of forced, selected records: mode 5. Draw: `TroopBook`, **no title**,
`BKTXT 601` in font 4 centred at y = 8H + 50; `BKTXT 602` (`%d` = **coffers only**, prepaid not added) font 2 centred at y = 8H + 50 + 2 x H4; `BKTXT 603`
(`%d` = sum of forced prices) centred at that y + 2H. Only Done (x = 325). Done: destroy window (tune stopped), clear backdrop, clean glue windows, pop
contexts (§13) until a WINDOW frame whose caller name starts with "MainMenu" is found and re-open it (main menu). Files untouched.

#### 11.3.8 State read/written
Read: `ARMY.MRC` company, `PLAY.MRC`/roster flags (`forHire`), mission record (name id, forced/excluded lists, prepaid, cash), coffers, `maxselect` option (default
13, clamped 8..38; this option is the selection limit, no mission field). Written only on P1 Done (§11.5.3). The window keeps a selection list of up to 38 records.

### 11.3b Asset inventory
| Asset | Kind | Source | Size / rule | Use |
|---|---|---|---|---|
| `TroopBook` | bitmap | BITMAP.DLL (shared with debrief) | 640x480, 8 bpp, opaque (0 index-0 pixels) | background of every page |
| `RedATabUp/Dn0`, `BlueATabUp/Dn0`, `GreenATabUp/Dn0`, `BrownATabUp/Dn0` | bitmaps (8) | BITMAP.DLL | 84x32, opaque | button up/pressed |
| `RingMark` | bitmap | BITMAP.DLL | 65x45, index 0 transparent (2395 of 2925 px) | selected row, (45, y_i-H) |
| `Skull0..4` | bitmaps | BITMAP.DLL | 9x10, 9x22, 21x22, 21x22, 15x18; index 0 transparent | rank icon centred (65, y_i+12) |
| `BookScroll0` / `BookScroll1` | bitmaps | BITMAP.DLL | 408x42, index 0 transparent (835 px each) | P1 row strip / drop-target highlight (hovered row) |
| `BookScroll2` | bitmap | BITMAP.DLL | 56x42, 98 transparent px | P1 order badge |
| banner sprite | sprite set | resident banner set of the unit's `banner:` (2nd frame 16x24) | | row (x0+35, y) |
| font slot 2 `GLUE/PCTEXT.FON`, slot 4 `GLUE/SUBTEXT.FON` | fonts | `notes/fonts_glue.md` | 12 / 22 px | all text; slot 4 only on P5 |
| cursors: `SwordCursor` (hot 0,0) window default; `HelpCursor` (2,2) while Ctrl; `PencilCursor` (0,0) / `NoPencilCursor` (0,0) over P0 rows; `HandOpenCursor` (0,0) / `HandCloseCursor` (0,0) P1 rows idle/carrying; `UpArrowCursor` (13,0) / `DownArrowCursor` (13,25) P1 scroll zones; `HandCursor` (0,0) buttons | cursors | `WHSHR.EXE` groups (ids 7,10,8,9,4,5,11,12,2), 32x32 mono | | see §11.5 |
| palette 1 = BOOK (`GLUEBOOK`+`WINDBOOK`) | palette | `notes/palette_selection.md` | | set at open; restored to 2 (MAP) on Abort only |
| `binary/music/tactical.mid` | music | FILE/BINARY/MUSIC (+FM twin) | loops | whole window |
| `B4.WAV` press, `B3.WAV` release inside | sfx | glue speech dir | | buttons |
| `binary\glue\speech\b9.wav` | sfx | same dir | | refusal: click on an unselected row when full; not played while speech plays/off |
| strings BKTXT | | 400, 401, 409, 410, 413, 414, 415, 416, 417, 418, 420, 613, 5006, 601, 602, 603 | `%s`: 400/401; `%d`: 5006, 602, 603 | |
| strings BRTXT | | 300, 301, 303, 304, 307, 308, 314, 315, 316, mission name id, 100+armour, 200+weapon | | |
Shared with the debrief: everything; unique here: RingMark, BookScroll0-2, pencil/hand/arrow cursors, b9 cue. Roster-book assets (Ctrl+click): §10.3b (palette 9).

### 11.3c Animation and glue
**No animation.** The 250 ms timer (id 3) only scrolls P1 (§11.5.4). The dragged strip follows the mouse (immediate redraw), no frames. Glue: no WND resource, no
script commands, no events; entered from the panel handler (§11.3.1), leaves through Abort (pop + reopen), P1 Done (mission-script window by name, else battle
directly) or P5 Done (unwind to MainMenu). Draw order: background, title, page content in the order above (P0: headers, per row numbers then row painter then
ring, total line, bottom lines, hints), buttons above as child windows.

### 11.4 Hotspots / cursors
No hotspots. Cursor rules and hit zones are in §11.5 (P0 rows: pencil / no-pencil; P1 rows: open/closed hand; P1 y 0..50 and 420..440: arrows).

### 11.5 Input and exits
**11.5.1 Mouse-down (left) only; no release, right button or wheel handling.** While ready: if carrying (P1): drop. Else y' = y - 50; Ctrl held (async state at
click) -> roster-book hand-off (§11.5.6); else P0 -> toggle, P1 -> pick up.
Toggle (P0) ✅: row = y'/(4H) + page x 6 (no x test). Acts iff hired, not forced, not excluded, not destroyed. Unselected: if count < limit select and
append, else b9 cue; selected: deselect and remove. Then repaint and re-enable buttons. 🟡 Quirk: signed division lets y in about 3..49 (above the first row)
hit row 0, and smaller y hit rows of the previous page; unmapped rows on a short last page are inactive so nothing happens. Recommended: rows only for y >= 50.
**11.5.2 Abort**: `BRTXT 308` Yes/No box (title "Warhammer", question icon) only if count != 0; No = stay. Yes or nothing selected: destroy window (stop and discard tune),
free the company, palette 2, pop one context (§13); if the popped frame is a WINDOW frame the caller window is re-opened by its saved (name, mode) (fresh
instance); if a RUN frame its script/window set is restored (map case). If the stored caller name is empty nothing is reopened. Nothing charged.
**11.5.3 P1 Done** (also the skip path in mode 0): coffers += prepaid; coffers -= total cost; mission marked taken; routed models put back, `MARCH.MRC` written in
list order; roster flags inArmy (every record) / inMarch (selected); write `ARMY.MRC`, `PLAY.MRC`; caravan-leave housekeeping (drop non-hired, clear
reinforcements); destroy window; then the mission script window if the record names one, else start the battle (`notes/troop_selection.md` §5.3).
**11.5.4 P1 mouse** ✅: rows hit for y' in [0, min(count,7) x 4H] (index first + y'/(4H) must be < count). Pick up: strip (BookScroll0 with the row content at +12,+10)
follows the pointer (offset kept; clamped inside x 0..639, bottom <= 439); original row hidden; closed-hand cursor. The row under the pointer (other than the carried one)
is redrawn on `BookScroll1`. Second click drops: carried entry moves to the hover index (in [0,count)), others shift by one; outside a row nothing changes. Scroll: mouse y
in 0..50 sets "up", 420..440 sets "down"; the 250 ms timer moves `first` by 1 per tick (only when count >= 8, on P1, also while dragging): up while first > 0, down while
first < count-7. Pointer idle over the list = open hand; in a zone = arrow cursor. 🟡 Bug: P0 Done to P1 does not clamp `first`; after scrolling, Back, deselecting until
count < first+7 the top rows stay hidden and cannot be scrolled (count < 8).
**11.5.5 Keyboard**: Ctrl = help cursor (restored on release); other keys go to a hidden cheat-code detector; no shortcuts (Enter/Esc/Space nothing). No wheel.
**11.5.6 Ctrl+click, hand-off to the Roster book (§10)**: P0 row = y'/(4H) + page x 6 must be < rows_on_page (negative-index quirk as above); P1 entry = list[first + (y'/(4H)) % 7].
The window is hidden and the roster book opens with (hire-enabled flag = 1, no coffers change, unit array, record index, parent window, file `ARMY.MRC`), palette 9; on close
the parent is re-shown and fully repainted (🟡 no palette call: the page is redrawn with palette 9). Book Hire selects immediately if room (no b9 cue), Fire deselects.
The book's leader box, buttons, sub-window and page layout are those of §10.

### 11.6 Engine status and deviations
Status: deviations 1-6 below are implemented in the engine (label offsets, P0 Done enable/click rule, hint colour, P5 coffers line and spacing, total cost, full-width row hit zones incl. the click-above-row-0 quirk, buttons ignored while dragging); tests in `tests/test_troop_selection.py` and `tests/test_glue_scene.py`.
Present: `whshr/troop_selection.py`, `whshr/frontend/troop_selection_view.py`, `TroopSelectionScene` in `whshr/campaign_scenes.py`. Deviations:
1. Button label offsets (4,3)/(0,3) -> must be (+4,+2)/(+3,+3).
2. Done on P0 is greyed when unaffordable; original: enabled when count != 0, click ignored when unaffordable. Scene `done` also lacks the affordability check.
3. Hint colour (0,0,180) -> (0,0,255).
4. P5: coffers line shows coffers + prepaid (original: coffers only); line spacing +H4/+H (original +2 x H4, then +2H).
5. `total_cost` counts AVAILABLE rows only; original adds retainers of hired excluded/destroyed rows.
6. Row hit rectangles limited to x 45..595 / 83..565; original: full width.
7. Not modelled: 250 ms tick granularity, hand/arrow cursors only partly, b9 cue (check), stopping the map's tune, the P1 `first` clamp bug (engine clamps: keep, flag as intentional).

### 11.7 Test scenarios
(a) Given a mission with 14+ hired regiments and limit 13, when the 14th unselected row is clicked, then nothing changes and b9 plays.
(b) Given coffers + prepaid below total cost and count 2, when Done is pressed, then the button looks enabled but the page stays P0.
(c) Given forced regiments costing more than coffers + prepaid, when opened, then P5 shows coffers alone and Done lands on the main menu.
(d) Given 9 selected, when the pointer stays in y 420..440 for 3 ticks, then `first` advances by 2 (max count-7).
(e) Drag entry 0 onto row 3: order becomes 1,2,3,0,...
(f) Abort with nothing selected reopens the caller without a box.
(g) A hired excluded regiment: its retainer is included in the total.
(h) Given a strip button pressed then released inside, then B4 then B3 play; label offset (+4,+2) / (+3,+3).

### 11.8 Open questions
🟡 Palette after the roster-book return; 🟡 the caller frame kind on Accept from the map (RUN vs WINDOW); ⬜ use of the `MarchOrderMove`/`MarchOrderMoveDone` assets; 🟡 border flag on
the window style; 🟡 colour leak after destroyed rows.

## 12. Control panel ✅

Marks: ✅ verified from data and cross-checked, 🟡 inferred / not observed running, ⬜ open. Full-game windows only. Stack mechanics (push, pop, CleanUp,
caller name/mode, launcher) are in §13 and only referenced here.

### 12.1 Purpose
The control panel is the block of 1 to 4 native buttons drawn under a speaker portrait (`[ANIM]` block, key `controlpanel`). It is NOT a glue hotspot and not a
window of its own: the front end creates it for every `[ANIM]` block whose `controlpanel` is 1..10, as child buttons of the glue (sub-)window that carries the
`[ANIM]`. It is how the player leaves the map and briefing (Brief, Accept, Caravan, Abort), controls a running mission script (Caravan, Options, Pause/Resume)
and answers encounters (Defend, Attack!, Evade, Decline). Buttons are fixed front-end logic keyed by (panel value, slot); nothing in the WND data names them
except the panel number.

### 12.2 Where it appears
The panel exists wherever a portrait window with a non-zero `controlpanel` is open (✅ scan of all `[ANIM]` blocks; about 60 carry 0 = frame bottom only).
| `controlpanel` | Windows | Opened by |
|---|---|---|
| 1 (22) | briefing speakers: `ScribeWindow`, `Scribe2/3/4Window*`, `YouWindow*`, `Dwarf*Enc1`, `Woodelf*`, `GotrekSpecialWindow`, `Azguz3Window`, `BernardP2/P3Window`, `Ceridan9Window` | briefing scripts |
| 2 (1) | `ScribeMWindow` (450,25,144x240) beside the map and mission list | the first-chapter flow script via `opensubwindow`, after `openwindow:MapWindow` and before `addobject:<mission window>` |
| 3 (4) | `AmbushWindow`, `Forest/Mountain/SnowyAmbushWindow` | ambush subscripts |
| 4 (1) | `CeridanEncounterWindow` (`EncounterWindow` never opened) | one mission script |
| 8 (4) | `HarkonEncounterWindow`/`2`, `AzguzWindowEnc8`, `ScribeWindowEnc8` | mission scripts |
| 9 (17) | `Scribe5Window`, `Scribe5WindowTL`, `Scribe5WindowTL2` (opened by nearly every `*Mission*` script right after its map), `ScribeWindowEnc9*`, `CommanderWindowEnc9*`, `CommanderWindowEnc2TR` | mission scripts and subscripts |
| 5, 6 (2), 7 (3), 10 | 6: `ScribeWindowEnc6`, `CommanderWindowEnc7TR`; 7: `ScribeWindowEnc7`, `AzguzWindowEnc7TM`, `HolgerOfferWindow`; 5 and 10: none. No shipped script opens any of them | (dead data) |
Only one WND flow script (the first chapter's) opens the panel-2 window; other chapters' mission-select maps are not created by a WND script that names it (⬜, §12.7).
Panel 2's window sits at the right of the map, the mission list at left (30,15), no overlap. Numbers 5, 6, 7, 10 exist in the front end, so a complete engine should
support all 10.

### 12.3 Construction

#### 12.3.1 Calling sequence ✅
The panel is built when the window that owns the `[ANIM]` is created (initial open, or re-created by a context pop, §13). Nothing to call: no push, no palette
change, no music. Order inside window creation: window (class `GlueWindow`, cursor `SwordCursor`), off-screen picture, child windows, then per `[ANIM]` entry the
off-screen bitmap of the frame and then the buttons. Buttons are above the picture; sibling sub-windows created later (e.g. the mission list added after the
portrait window) are above earlier ones. Buttons are destroyed with their window (CleanUp, push of a RUN frame).

#### 12.3.2 Window and frame geometry ✅
Portrait sub-window: 144 wide; own `[POSITION]` x,y. Frame bitmap size = (120 + 2x12) x (152 + 2x14 + 20 N), N = number of buttons: 144 x (180 + 20 N) (200 / 220 /
240 / 260 for N = 1..4; 180 for panel 0). Layout (window-relative): `FrameTop` (4,4); `FrameLeft` (4,12); `FrameRight` (132,12); panel art (`FramePanel1..4`, or
`FrameBottom` for panel 0) at (4,164); portrait/background inside at (12,12).
Panel art by value: 1,2,6,7,9,10 -> `FramePanel3` (3 buttons); 3,8 -> `FramePanel1` (1); 4 -> `FramePanel2` (2); 5 -> `FramePanel4` (4); 0 or other -> `FrameBottom`.
Blit/redraw ✅: the whole bitmap is blitted on erase-background; on mouse-move (hover refresh of the portrait name) the blit height is reduced by panel-art height + 8
(8, 36, 56, 76, 96 for N = 0..4) so the button area is never overpainted. Class cursor of the sub-window `SwordCursor`; over the buttons `HandCursor`.

#### 12.3.3 Controls ✅
Buttons: class "Button", style child|visible|owner-draw, **empty caption** (no mnemonic/keyboard shortcut), no tab stop. Id = 0x100 + slot; size 119x20 (art size);
x = window x + 9 (relative to the `[ANIM]` window origin; `[ANIM] x,y` are 0 in all data); y = H - 12 - 20 (slot + 1) with H = 180 + 20 N (slot 0 is the lowest button).
Example (N = 3): slot 2 y = 168, slot 1 y = 188, slot 0 y = 208 (verified by composing the art: the buttons fall exactly in the three pockets of `FramePanel3`).
Every button uses the shared button subclass (same as the roster/troop/credits Done buttons): erase-background suppressed; **mouse-down plays cue `B4.WAV`, mouse-up
inside the client rect plays cue `B3.WAV`**, then the standard button handling runs (click on release with capture). A cue plays only when speech is enabled and no
speech clip is being spoken (the cue routine also stops any clip). No hint string, no hover art. The click = WM_COMMAND to the window: the handler receives (panel value
of the button's `[ANIM]`, id).

Labels (BRTXT ids) by panel, slot 0 = lowest:
| Panel | Slot 0 (0x100) | Slot 1 (0x101) | Slot 2 (0x102) | Slot 3 (0x103) |
|---|---|---|---|---|
| 1 | Abort 311 | Accept 309 | Pause 310 / Resume 312 | - |
| 2 | Caravan 333 | Accept 309 | Brief 313 | - |
| 3 | Defend 331 | - | - | - |
| 4 | Evade 330 | Attack! 329 | - | - |
| 5 | Abort 311 | Accept 309 | Report 332 | Brief 313 |
| 6 | Abort 311 | Accept 309 | Pause 310 / Resume 312 | - |
| 7 | Decline 338 | Accept 309 | Brief 313 | - |
| 8 | Attack! 329 | - | - | - |
| 9 | Caravan 333 | Options 339 | Pause 310 / Resume 312 | - |
| 10 | Caravan 333 | Accept 309 | Brief 313 | - |
(All ids exist in BRTXT; the front end also carries placeholder literals "Empty 0..3" for undefined slots; unreachable.) A Pause slot's label is chosen at draw time from the
global pause flag: 312 while paused, else 310 ✅ (agrees with `mission_selection.md` §9.4).
**Enabled rule ✅: there is none.** These buttons are never disabled, hidden or greyed. The draw code supports a disabled label colour (192,192,192) but nothing sets it.
Buttons that make no sense do nothing (Report) or act on "no selection" (§12.3.6).

#### 12.3.4 Drawing of a button ✅
Owner-draw, only for "draw entire" and "select" actions (no focus rectangle). Art `FrameButtonUp` (119x20), or `FrameButtonDn` while selected (pressed); no hover art. The art is copied
opaque, by palette index, into a bitmap of the art size, then the label: glue font slot 2 (`PCTEXT.FON`, 12 px), transparent background, **colour black (0)**, plain text (no
outline/shadow), centred with `x = (119 - textW)/2`, `y = (20 - textH)/2`, **no press offset**. (The tab-style buttons of other windows, ids 0x200..0x203 in the same routine, differ:
yellow text, offsets (+4,+2) released / (+3,+3) pressed, §10.3.3; not part of this panel.) Pause/Resume: after toggling, the single button is invalidated and redrawn with the other label.
Frame art is drawn opaque into the frame bitmap in order: background/portrait, `FrameTop`, `FrameLeft`, `FrameRight`, panel art; hover name text after.

#### 12.3.5 State read / written ✅
Read: panel value of the button's `[ANIM]`; global pause flag; selected record of the first mission-list window (id, -1 when none); the "current mission" override id (set when
Brief/selection copies a record); the pending-text queue of the owner window. Written: pause flag (Pause/Resume, also cleared by most other buttons), remembered tune name (cleared),
glue true/false status bits (Attack! panel 4), mission-taken flag (Accept 6/7/10), the current-mission record (Brief). No file is written by the panel itself.

#### 12.3.6 What each button does ✅ (steps in order; stack mechanics §13)
Vocabulary. UNPAUSE = if paused: clear the flag, restore the shelved speech clip and resume it, resume the tune. DRAIN(k) = stop the current speech clip, then, if the panel window has an
owner window, repeat "fast-forward the owner's pending dialogue text" until none is queued; when the text finishes and k = 1 the interpreter is **resumed** (the rest of the script runs until
it blocks again, and further text it queues is drained by the same loop); with k = 0 the interpreter is never resumed by the drain. DROP-SPEECH = discard the shelved (paused) speech clip.
STOP-TUNE = stop and discard the running tune. FORGET = clear the remembered tune name. PUSH/CLEANUP/POP as in §13.

| Panel / slot | Steps |
|---|---|
| 1,5,6 / 0 **Abort** | UNPAUSE if paused; stop speech; DROP-SPEECH; STOP-TUNE; FORGET; end the running script; CLEANUP; POP one frame; if the frame kind is WINDOW re-open the caller by name; a RUN frame is restored by the pop itself (the parked map with its selection), no script resumes |
| 2,10 / 0 **Caravan** | DRAIN(0); PUSH; CLEANUP; open window resource `CaravanSelectMission` directly (mode 1, not through the launcher; its own tune replaces the current one). No unpause |
| 3,8 / 0 **Defend / Attack!** | UNPAUSE if paused; DRAIN(1); start the pending encounter battle |
| 4,7 / 0 **Evade / Decline** | UNPAUSE if paused; DRAIN(1); resume the script |
| 9 / 0 **Caravan** | only if not paused: DRAIN(0), DROP-SPEECH; then always PUSH; CLEANUP; open `CaravanContinueMission`. The tune keeps playing until the caravan's tune replaces it |
| 1,2,5 / 1 **Accept** | read selected mission id; UNPAUSE if paused; DRAIN(1); DROP-SPEECH; STOP-TUNE; FORGET; if the current-mission override id is set use it; PUSH; CLEANUP; open the troop window (§11) on the company file with the current caller (name, mode) as return target |
| 4 / 1 **Attack!** | DRAIN(1) (no unpause step); OR the status mask into the glue status; start the battle |
| 6,7,10 / 1 **Accept** | DRAIN(1); DROP-SPEECH; STOP-TUNE; FORGET; PUSH; CLEANUP; set the mission-taken flag; run the mission script directly (or its battle when it has no script); no troop selection |
| 9 / 1 **Options** | only if not paused: DRAIN(0), DROP-SPEECH; always STOP-TUNE (name kept); open `OptionsDialog` through the launcher (which pushes). OptionsDialogDone restarts the remembered tune (and re-pauses it if paused) |
| 1,6,9 / 2 **Pause/Resume** | toggle the pause flag. Pause: flag on, pause the running speech clip (shelved), pause the tune. Resume: the reverse. While paused the 25 ms glue timer does nothing (no typing, no portrait/bitmap animation, no script resume); hotspots and buttons still work |
| 2,7,10 / 2 and 5 / 3 **Brief** | UNPAUSE if paused; DRAIN(1); find the window that owns the mission records, copy the selected record into the current mission, PUSH (skipped when that owner has portrait entries of its own), CLEANUP, open its briefing (`res:` else `script:` name) |
| 5 / 2 **Report** | nothing |
Pause persistence 🟡: Caravan and Options skip the unpause, so the flag stays set across the trip; the timer stays frozen inside the caravan (its animations and typing stop) and a RUN pop
does not resume the script while paused, so the player must press Resume on return. Not observed running.
Consequence ✅: a click cue plays on every button press independent of the action; actions run synchronously inside the click, destroying the button being clicked.

### 12.3b Asset inventory ✅
| Asset | Kind | Source | Size, frames, rule | Use |
|---|---|---|---|---|
| `FrameButtonUp` / `FrameButtonDn` | bitmap pair | BITMAP.DLL | 119x20, 8 bpp, 1 frame each, opaque | button released / pressed |
| `FramePanel1` `FramePanel2` `FramePanel3` `FramePanel4` | bitmap | BITMAP.DLL | 136 x 28 / 48 / 68 / 88 (= 8 + 20 N), 8 bpp | panel pockets at (4,164) |
| `FrameBottom` | bitmap | BITMAP.DLL | 136x8 | panel 0 (no buttons) at (4,164) |
| `FrameTop` / `FrameLeft` / `FrameRight` | bitmap | BITMAP.DLL | 136x8 / 8x152 / 8x152 | frame at (4,4) / (4,12) / (132,12) |
| app palette 2 (`MAP`) | palette | `GLUE/WINDMAP.PAL` + `GLUEMAP.PAL` (`palette_selection.md`) | frame art carries table 55b7644f, button art c329351e; only indices are drawn | whole panel |
| font slot 2 | font | `PCTEXT.FON`, 12 px | label colour black | labels (also the mission-list rows) |
| `SwordCursor` / `HandCursor` | cursors | `GMCUR` group of the front-end executable | 32x32 | window / buttons |
| cues `B4.WAV` / `B3.WAV` | sfx | `binary/glue/speech/` (11025 Hz mono 8-bit) | played by the shared button subclass | press / release inside |
| `BRTXT` 309-313, 329-333, 338, 339 | strings | BRTXT.DLL | labels (§12.3.3) | button text |
| music / speech | none of its own | | Abort/Accept/Options/Caravan stop/discard/pause them (§12.3.6) | |
Shared: frame art is used by every portrait window; button art also by other native windows with `FrameButton*` labels; the cue subclass and font by all native buttons. Portrait and
background art: `glue_portraits.md`.

### 12.3c Animation and glue ✅
No animation of the panel: static art, button state only changes on press (Dn art) and on Pause/Resume (label swap). The portrait above it animates (`glue_portraits.md` §3),
independently. Glue: `[ANIM] set:controlpanel=N` is the only link; button set, art, labels and actions come from the front end's table (`whshr/controlpanel.py`). Draw order:
portrait background, frame parts, panel art, hover name, then buttons as child windows on top. No script event is emitted; effects are the stack operations above and, for
Evade/Decline/Attack!/Defend, the script resume / battle start (`activity_results.md` §3). Redraw only on WM_ERASEBKGND, hover refresh (panel area excluded) and Pause invalidation.

### 12.4 Hotspots / scripts
None: no hotspot rectangles, `res:` or `script:` on the panel; the only data key is `controlpanel`.

### 12.5 Input and exits
Mouse only: left press (cue B4, pressed art), release inside (cue B3, action); release outside: no cue, no action. No keyboard shortcut, accelerator or mnemonic (empty caption). 🟡 Windows
default: after a click the button holds focus and Space would click again. Pause/Resume is reachable only through this button. Exits: as §12.3.6 (each action ends in a CLEANUP, then a new
window/script, a POP, or a resume).

### 12.6 Engine status and suggested shape
Existing: `whshr/controlpanel.py` (table, correct labels/panel bitmaps/geometry), `whshr/frontend/mission_map_view.py` (legacy map: buttons with Dn art), `whshr/frontend/glue_view.py`
`_refresh_panel` and `whshr/glue_runtime.py` `_panel_action` (glue runtime path: only Pause and Abort real; other actions log "not yet implemented"; encounter actions implemented).
Deviations:
1. Label colour: notes say the block's `settextcolor`; the original is always black (engine draws black: fix the note).
2. `mission_map_view` greys buttons (192,192,192) when no mission is selected; the original never greys, and its selection is an index (first row after creation 🟡); Accept with none passes id -1.
3. Label y = +4 offset / padding; original centres in 20 px, no press offset.
4. Frame art via colour key (0,0,255); original copies opaque by index (🟡 corner look).
5. Glue path draws no pressed art (`FrameButtonDn`), no click cues B4/B3, no cue rules (skip while speaking or speech off).
6. Glue path: Caravan/Accept/Brief/Options are diagnostics; Pause toggles a flag but does not pause speech/music/timers, and Caravan/Options must not unpause.
7. Extensions not in the original: Up/Down/Esc keys, hover-select of mission rows in the map view (original selects on press/drag).
8. DRAIN(1) resuming the script (Accept/Brief/Defend/...) is not modelled.

### 12.7 Test scenarios
1. Given `ScribeMWindow` (panel 2) at (450,25), then three buttons 119x20 at x = 459 and y = 25 + 168 / 188 / 208 read Brief / Accept / Caravan from top to bottom, ids `BRTXT 313/309/333`.
2. Given panel 9 and a running dialogue, when Pause is pressed, then the label reads `BRTXT 312`, typing and portrait animation stop, speech and tune pause; when pressed again all resume and the label is 310.
3. Given a paused panel 9, when Caravan is pressed, then the pause flag stays set and the caravan opens (pushed frame); after PopContext the script does not resume until Resume is pressed.
4. Given panel 1 with text pending, when Abort is pressed, then speech, tune and script stop, windows are destroyed and the parked map with the same selected row returns.
5. Given any panel button, when pressed and released inside, then cue B4 then B3 play (unless speech is speaking/off); released outside: no B3 and no action.
6. Given panel 4, when Attack! is pressed, then the status mask is ORed into the status before the battle starts; Evade leaves it untouched.
7. Given panel numbers 5/6/7/10 (no shipped user), then heights are 260/240/240/240 and Report does nothing.

### 12.8 Open questions
- ⬜ How the mission-select maps of later chapters obtain the panel-2 window (only one WND flow script names `ScribeMWindow`).
- 🟡 Whether the drain-and-resume (k = 1) behaviour is visible in play (Accept during a briefing).
- 🟡 Pause persisting into the caravan/options; initial selected row of a fresh mission list; corner transparency of the frame art.
- ⬜ Whether the placeholder literals and panel values > 10 have any use (assumed none).

## 13. Context stack, launcher and non-visual built-ins ✅

Marks: ✅ established and cross-checked, 🟡 inferred / not observed running, ⬜ open. Scope: full-game windows only.

### 13.1 Purpose

Every front-end screen change that is not a plain script command goes through one routine, the **hotspot launcher**: it saves where
the player is on a **context stack**, decides whether the hotspot's `res:` name is a built-in, a window resource or nothing, and runs it.
The built-ins here are the "way back" half: `PopContext`, `PopContextCheckResume`, `NullWnd`, `UnwindMission`, `PopAndResume`,
`AbortGame`, `ExitProcess` (plus `OptionsDialogDone` and the native windows' "Done" exits, which use the same machinery). They discard the
screen, restore an earlier one from the stack and, depending on the built-in, resume a suspended mission script, release a finished mission
on the map, leave the campaign for the main menu (after a Yes/No question) or close the program. The only campaign file touched is
`ARMY.MRC` (by `PopAndResume`).

### 13.2 Where it appears

Table: each of the 15 built-ins x every full-game hotspot that uses it (scan of all 535 window scripts, `[INCLUDE]` resolved). Rectangle =
hotspot (x, y, vx, vy); "hint" = the `set:res=<id>` tooltip string id (BRTXT). Caravan windows share hotspot definitions through
`[INCLUDE]` (`CaravanCommon1..5` are fragments never opened themselves), so "definitions" and "windows showing it" differ.

| # | Built-in | Definitions | Windows that show it | Rectangle, cursor, hint / notes |
|---|---|---|---|---|
| 0 | `ArmyBook` | `CaravanCommon4`, `CaravanDietrich`, `Start` | 15: `CaravanAfterMission`, `CaravanAfterMissionWithRecruit`, `CaravanSelectMission`, `CaravanDietrich`, `StartCaravan`, `Start`, `InfoCaravan` BMA BPC ENA ENE LA LB REA REC WED | Common4: (0,299,164,47), `HandOpenCursor`/`HandCloseCursor`, hint 151; Dietrich (0,245,164,47); Start (0,245,165,40) |
| 1 | `EncyclopediaBook` | `CaravanCommon1`, `CaravanDietrich`, `Start` | 22: the 20 windows including `CaravanCommon1` + `CaravanDietrich` + `Start` | Common1: (0,349,180,42), hint 152; Dietrich (0,295,180,42); Start (0,290,165,35) |
| 2 | `PopContext` | `CaravanSelectMission`, `OptionWindow` | 2 | CaravanSelectMission: (480,250,160,110), `HandCursor`, hint 150 (the map's Caravan button opens this caravan); OptionWindow Cancel: (397,335,41,41), no hint (-2), sfx up 3 / down 4 |
| 3 | `ExitProcess` | `MainMenu` x2 | 1 | (98,389,41,41) and (501,389,41,41), `HandCursor`, art `OptionButtonUp`/`OptionButtonDown`, sfx 3/4 |
| 4 | `NullWnd` | none | 0 | occurs only in commented-out lines; unreachable in the full game (behaviour specified in 13.4.4) |
| 5 | `MagicBook` | `CaravanCommon1`, `CaravanDietrich` | 21: the 20 `CaravanCommon1` windows (`StartCaravan` among them) + `CaravanDietrich` | Common1: (0,246,164,46), hint 158; Dietrich (0,192,164,52) |
| 6 | `UnwindMission` | 11 direct: `CaravanAfterMission`, `CaravanAfterMissionWithRecruit`, `CaravanAfterEncounter`, `CaravanAfterEncounterWithRecruit`, `CaravanDietrich`, `InfoCaravan` BMA BPC ENE LB REA REC | same 11 | (480,250,160,110), `HandCursor`; hint 150 (AfterMission*, Dietrich, Info*) or 161 (AfterEncounter*) |
| 7 | `PopAndResume` | 7 direct: `CaravanRecruitAndResume`, `CaravanRecruitNoSpeechAndResume`, `InfoCaravan` ENA LA SZA SZB WED | same 7 | (480,250,160,110), `HandCursor`; hint 161 (both Recruit*, SZA, SZB) or 150 (ENA, LA, WED) |
| 8 | `OptionsDialog` | `CaravanCommon1`, `MainMenu` x2 | 21: the 20 Common1 windows + `MainMenu` (`CaravanDietrich` does not include Common1) | Common1: (245,85,145,65), `HandOpenCursor`/`HandCloseCursor`, hint 162; MainMenu (98,285) and (501,285), 41x41, sfx 3/4 |
| 9 | `AbortGame` | `CaravanCommon1` | 20 (every window including Common1, i.e. all caravans except `CaravanDietrich`) | (0,0,244,171), `HandCursor`, hint 159 |
| 10 | `NewGame` | `MainMenu` x2 | 1 | (98,180,41,41), (501,180,41,41), sfx 3/4 |
| 11 | `HireOnlyArmyBook` | `CaravanCommon5` | 7: `CaravanAfterEncounter`, `CaravanAfterEncounterWithRecruit`, `CaravanContinueMission`, `CaravanRecruitAndResume`, `CaravanRecruitNoSpeechAndResume`, `InfoCaravanSZA`, `InfoCaravanSZB` | (0,299,164,47), hint 151 |
| 12 | `OptionsDialogDone` | `OptionWindow` | 1 | OK: (203,335,41,41), no hint, sfx 3/4 |
| 13 | `Credits` | `MainMenu` x2 | 1 | (98,337,41,41), (501,337,41,41) |
| 14 | `PopContextCheckResume` | `CaravanContinueMission` | 1 | (480,250,160,110), `HandCursor`, hint 161 |

Table notes:
- `ArmyBook` has 3 full-game definitions, `HireOnlyArmyBook` is shown by 7 windows (one definition), `MagicBook` 2 definitions,
  `EncyclopediaBook` 3.
- **`CaravanDietrich` is unreferenced: no script and no string in the executable opens it.** It has its own, older hotspot positions
  (listed above) and still works if opened by name; treat it as a dead/development window.
- `Start` and `MapTestWindow` are development windows (no route from the game reaches them).

**Hotspots that open a window resource instead of a built-in** (launcher only, 13.3.2): `LoadSaveWindow` (20 caravan windows,
(450,85,190,180); its `[LOADANDSAVEGAME]` block makes it the native dialog), `LoadSaveWindow2` (`MainMenu` x2, (98,233) and (501,233)),
`FlowScriptBP01` (`StartCaravan`'s exit, (480,250,160,110), the first chapter's flow script), `JournalBook` (`CaravanDietrich`, `Start`),
`MapTestWindow` (`Start`, dev). `DietrichSpeech` (15 hotspots) is not a window: the click-speech table catches it *before* the launcher
(`notes/glue_keywords.md`).

**The `script:` key.** Values next to these `res:` names: `pop.wnd`, `armybook.wnd`, `encybook.wnd`, `magic.wnd`, `abort.wnd`,
`null.wnd`/`Null.wnd`, `exit.wnd`, `loadsav2.wnd`, `<Resident>`, `s1.run` (only `StartCaravan` -> `FlowScriptBP01`). None exists as a
resource. It is only a **fallback disk-file name** (13.3.2); with a valid `res:` it is never consulted. The single hotspot with a
`script:` and no `res:` (development window `Start`, `maptext.wnd`) would read that name as a plain file from the current directory, fail
silently and leave a blank screen.

### 13.3 Construction (state machine over the context stack)

#### 13.3.1 Registers and the four stacks ✅

All state is global (no per-window ownership).

| Register | Meaning |
|---|---|
| **K** (current kind) | kind of the current top-level block: `WINDOW` = 0x0C (window resource opened by the launcher or `gocaravan`) or `RUN` = 0x13 (script running or parked). A window opened *by a running script* (`addobject` etc.) keeps K = `RUN`; the launcher/`gocaravan` set K = `WINDOW`. Loading a script resource as the current script sets K = `RUN`. |
| **current frame** | running/parked script: 160-byte record (name, module kind, read position, **`parked`** flag as last dword; `notes/save_resume.md` §2) |
| **window slots** | up to 8 glue windows (one slot per opened resource, named after it even when it holds no window, e.g. a script), each 17,172 bytes: name, parent link, geometry, bitmaps, hotspots with state, text rows, animation state, mission list (records, count, **selected row**), control-panel buttons, the window's `[MIDI]` tune name, ... |
| **open-window count**, **palette id** | slots in use; current palette index (1 BOOK, 2 MAP/front end, 3 caravan, -1 from the bitmap; `notes/palette_selection.md`) |
| **caller name + caller mode** | resource name (<= 127 chars) of the **most recently opened window resource** and its module index (1 = glue-script module for real windows; 0 = plain disk file, only the `script:` fallback). Set on every window-resource open (launcher, `gocaravan`, a native "Done" re-opening its caller); native windows receive it as "the caller" |
| **remembered tune** | tune last started by script `playmidi:` (cleared by `stopmidi:`, by panel Abort/Accept and by the panel Options path, `notes/briefing_dialogue.md`); a window's own `[MIDI]` block never sets it |
| **paused** | game-pause flag toggled by the Pause/Resume panel button (and a menu item) |

Four independent stacks (all four depths are stored in every save game, `notes/save_resume.md` §1):

| Stack | Depth limit | Entry |
|---|---|---|
| **context stack** | **16** | one dword: kind K at push time (0x13 or 0x0C) |
| **script-frame stack** | 16 | copy of the current frame (160 bytes); RUN contexts only |
| **window-state stack** | **8** | snapshot of all 8 slots (8 x 17,172 = 137,376 bytes) + open-window count + palette id; RUN contexts only |
| **caller stack** | **8** | 128-byte name + mode dword; **every** context (both kinds) |

Counters are separate: context depth counts pushes of both kinds, the other three only what they received.

**Push** (`PushContext(hide)`, always hide = 1) ✅
```
kind = K
if context depth == 16: log "stack overflow", change nothing, return failure
context[depth] = kind
if kind == RUN:
    script-frame stack  <- copy of current frame               (skipped + logged if full)
    window-state stack  <- snapshot of 8 slots + count + palette; every window is DESTROYED (native handles gone, slot data kept,
                           child parent links stored as slot indexes; a window with a [MIDI] tune name stops and discards it);
                           if hide: remaining windows hidden    (skipped if full)
    caller stack        <- (caller name, caller mode)
else (WINDOW in practice):
    caller stack        <- (caller name, caller mode)          (skipped if full)
context depth += 1
```
A WINDOW push saves no windows, no script and no palette; the window is destroyed later by the built-in's clean-up.

**Pop** (`PopContext(show)`, returns the popped kind, 0 on failure) ✅
```
if context depth == 0: log "stack underflow", return 0          # nothing changes
kind = context[depth-1];  K = kind
if kind == RUN:
    current frame <- script-frame stack top (popped)             # parked flag comes back with it
    window-state pop (if empty: log, windows NOT restored):
        8 slots + open-window count copied back; saved palette selected;
        top-level windows re-created first, then child windows (parent links re-resolved);
        if show: every restored window shown; each window's idle/animation timer reset to "now";
        creating a window starts its own [MIDI] tune, if any (looping)
    caller (name, mode) <- popped
elif kind == WINDOW:
    caller (name, mode) <- popped                                # the caller re-opens the window by name
else:
    log "stack corrupt", return 0                                # depth NOT decremented; K stays = kind
context depth -= 1;  return kind
```
`show = 0` (only the first pop of `PopContext`/`PopAndResume`/`OptionsDialogDone`) restores a RUN frame without showing windows; the launcher
always pushes a WINDOW frame for a launcher-opened window's hotspot, so that first pop never restores windows in practice.
Practical depth: 2 (`MainMenu`, `StartCaravan`) + 1 (flow script) + 1 (mission script) + 1 (launcher's WINDOW frame) = 5; the 8-deep
sub-stacks are never reached. Before every pop of the abort loop all queued keyboard/mouse messages are discarded so a repeated click cannot
hit the screen about to be re-created.

#### 13.3.2 The hotspot launcher ✅

Trigger: mouse **button release** over a hotspot whose **press** was on the same hotspot, when it has a `res:` or `script:` value. Before it
runs, in order: (1) if `res:` is in the click-speech table (`DietrichSpeech` and its twin) the speech routine runs instead; (2) it is skipped
while the window is **busy**: dialogue text queued or a text row still being typed (🟡 not observed running). Inputs: window slot index,
`res` name, `script` name.
```
1. mission-id global := (window's mission list non-empty ? first field of its selected record : -1)   # no built-in can observe it
2. PushContext(hide=1)                    # always; return value ignored (overflow: no frame, run anyway)
3. if res is a built-in (exact, case-sensitive match against the 15 names): run it; done
4. else (window resource name, or empty):
     CleanUpGlue()                        # 13.3.3
     if res == "" or OpenWindowResource(res, mode 1) fails:
         if script != "": OpenWindowResource(script, mode 0)     # mode 0 = plain text file in the current directory
     # every failure is silent; nothing is popped
```
`OpenWindowResource(name, mode)`: caller name := name, caller mode := mode; look `name` up as an RCDATA resource of module `mode` (1 =
WND.DLL) or read it as a file (mode 0); if found, run it into the next free slot (slot named `name`; K becomes the new block's kind unless a
script asked to keep it); returns success. If not found it fails and **the screen stays blank with the launcher's frame still pushed**.
Consequences: (a) the frame pushed in step 2 is the "caller" frame (name+mode of the clicked window); (b) a hotspot whose target neither
is a built-in nor exists shows a blank screen and leaks one context (data error; none in the full game); (c) built-in names win, so a window
resource must not be named like one.

The launcher is also invoked (same push) by the control-panel **Options** button (`controlpanel = 9`) with `OptionsDialog`/`OptionsDialog`,
after the panel drained text, stopped speech and discarded (but remembered) the running tune; K = `RUN` there, so this push is a **RUN
frame** (script frame + window snapshot + caller). Other push producers are not hotspots: the panel Caravan/Accept buttons and `gocaravan:`
push a RUN frame themselves (`notes/mission_selection.md` §4.2, `notes/glue_interpreter.md` §7.3); `FlowScriptBP01` is reached through a
WINDOW frame pushed by the launcher.

#### 13.3.3 CleanUpGlue ✅ (called first by every built-in except `AbortGame`)
Suppress painting; destroy the edit box of the name prompt; destroy every child window of every slot, then every parent window (slot state
wiped to zero; a window with a `[MIDI]` tune name **stops and discards the running tune**); open-window count := 0; mission-id global and
four pointer-tracking globals := -1; restore painting. It does not touch the four stacks, caller registers, remembered tune, speech or the
paused flag.

#### 13.3.4 The built-ins

**`PopContext` (2) and `PopContextCheckResume` (14)** ✅ identical dispatch (the name is only data; one hotspot: `CaravanContinueMission`):
```
CleanUpGlue()
if remembered tune != "":  start binary/music/<name>.mid, repeat count 0 (loops); if paused: pause it at once
pop(show=0)                     # discards the launcher's WINDOW frame (caller registers restored to the clicked window)
k = pop(show=1)
if k == WINDOW:  OpenWindowResource(caller name, caller mode)                     # the window that was current below
elif k == RUN and not paused and current-frame.parked == 0:  resume the script    # else stay on the restored screen
# k == 0, or RUN with parked = 1, or paused: nothing more
```
The remembered-tune restart happens **before** the restore, so a restored window's own `[MIDI]` tune replaces it. The tune of the window
left (e.g. the caravan's `scribe`) was already stopped by the clean-up, so the map is silent unless a remembered tune exists.

**`PopAndResume` (7)**:
```
CleanUpGlue()
pop(show=0)                     # the launcher's WINDOW frame, discarded
pop(show=1)                     # the RUN frame gocaravan pushed: script frame, windows, palette, caller ARE RESTORED
caravan-leave housekeeping
resume the script               # ALWAYS: no paused check, no parked check; nothing if the current frame is empty
```
Housekeeping (`notes/campaign.md` §2.4, refined): reload the roster from `ARMY.MRC` (cache first, else file); for every roster entry whose
hired field is 0 clear its presence bit (bit 0 of its flags word); write the roster back to `ARMY.MRC`; flush the roster cache; mark **every
reinforcement slot unused** (walk the slot table to its terminator, zero each "taken" count). 🟡 Whether the written file drops a record whose
bit 0 is clear is the roster writer's rule; the engine (`CampaignState.leave_caravan`) drops it. The popped RUN frame is **not discarded**:
it becomes the current frame and the script continues on the line after its `gocaravan:` command.

**`NullWnd` (4)** (unreachable): `CleanUpGlue(); k = pop(show=1); if k == WINDOW: OpenWindowResource(caller name, caller mode)`. No tune
change, no resume; with a RUN frame on top the frame is restored but the script is **not** resumed.

**`UnwindMission` (6)**:
```
CleanUpGlue()
loop:
    k = pop(show=1)
    if k == 0: stop                                             # stack exhausted, nothing on screen
    if k == WINDOW: continue                                    # caller dropped
    # k == RUN: script frame, windows, palette, caller restored
    s = first slot (0..7) whose mission list is non-empty        # "window has a MissionWindow child with records"
    if none: CleanUpGlue(); continue                            # the mission script that ran gocaravan, or any frame without a map list
    R = selected record of slot s
    if R.replacescript != "":                                   # travel/chapter mission
        OpenWindowResource(R.replacescript, mode 1) as a script run in this frame's windows; stop    # NO copy, NO resume here
    releaseflag = R.releaseflag
    copy the current mission record over R                      # writes the "taken" flag back; whole 272-byte record
    n = recount visible records of slot s
    if the current record is not visible: select the first visible one
    if n != 0: window height := row height x n; rebuild list rows; recreate the MissionWindow child; refresh the slot
    if releaseflag == 0 and n != 0: stop                        # player stays on the map (script still parked in waitforrelease)
    resume the script                                           # releaseflag == 1, or nothing visible
    stop
```
The caravan window's tune is stopped by the clean-up and nothing restarts it (no remembered-tune restart here): the map is silent afterwards
unless restored windows carry a `[MIDI]` block or the resumed script plays a tune (🟡, see open questions). The pause flag is not consulted.
Frames popped are unbounded (until a frame with a map list): 1 launcher WINDOW frame, usually 1 mission RUN frame cleaned and dropped, then
the flow script's RUN frame.

**`ExitProcess` (3)**: `CleanUpGlue()`, then post the system close command (SC_CLOSE) to the main window; its handler closes the window and
posts quit; the shutdown sequence destroys all glue windows and pending text/speech objects, discards the tune, closes the sound driver,
releases palette and surface, destroys the main window and unloads the resource DLLs. **No confirmation, no save**: not the options string
(written only by the Options dialog OK), not `ARMY.MRC`/`PLAY.MRC`/`MARCH.MRC`, not an autosave (only script `autosave:` writes slot 5). The
close box and Alt+F4 take the same path. The launcher's WINDOW frame is never popped.

**`AbortGame` (9), the Yes/No box** ✅. The box is shown **first**, before any clean-up, so the caravan stays on screen behind it.
```
text   := BRTXT string 308 (module 4, id 308)        # the same question the troop-selection Abort asks
result := system MessageBox(owner = main window, text, caption "Warhammer", flags YESNO | ICONQUESTION)   # Yes = default
if result == Yes:
    CleanUpGlue(); repaint the main window (erase to background)
    loop:
        discard queued keyboard/mouse messages
        k = pop(show=1)
        if k == 0: stop                                                 # stack exhausted: nothing on screen
        if k == WINDOW:
            if first 8 characters of the restored caller name are "MainMenu" (case-sensitive):
                    OpenWindowResource(caller name, caller mode); stop
            else:   continue                                            # a caravan / StartCaravan frame: dropped
        else (RUN): CleanUpGlue(); continue                             # windows re-created by the pop, destroyed again
else (No, or box closed):
    CleanUpGlue()
    k = pop(show=1)                                                     # the launcher's WINDOW frame
    if k == WINDOW: OpenWindowResource(caller name, caller mode)        # same caravan, freshly built
```
Box look: the **system message box**: question-mark icon, text = **BRTXT 308**, caption "Warhammer" (the executable's own literal; BRTXT
212 holds the same word), buttons Yes/No (captions from the OS), Yes default, modal to the main window; no game font, palette or bitmap;
a Yes/No box has no cancel. `GMTXT 36070` is **not** used here (it is the in-battle quit prompt).
Yes pops until it finds the **WINDOW frame whose caller is the main menu** (pushed by the launcher when the menu's New Game hotspot was
clicked) and re-opens `MainMenu` with the saved mode (fresh menu, own tune `title`); every RUN frame above it is discarded; all four stacks
end at depth 0. It does **not** delete/reset `ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC`, `debrief.dbf`, the autosave slot or the coffers (only a later
New Game resets them), does not clear the remembered tune or paused flag, and does not run `ClearGlueScriptStack`. Failure mode: with no
`MainMenu*` frame on the stack every frame is popped and the screen stays blank.

**Related exits (same machinery)** ✅
- `OptionsDialogDone` (12): apply and store options (`options.md`), `CleanUpGlue()`, **if not paused** and a remembered tune exists restart it
  (no pause afterwards; when paused nothing is restarted), `pop(show=0)`, `k = pop(show=1)`; `WINDOW` -> re-open caller; `RUN` and not paused and
  `parked == 0` -> resume. It differs from `PopContext` only in the apply step and the paused-tune handling.
- Native windows (`ArmyBook`, `MagicBook`, `EncyclopediaBook`, `Credits`, `HireOnlyArmyBook`, `LoadSaveWindow*`): the built-in does
  `CleanUpGlue()` and opens the native window with (caller name, caller mode) from the registers. Done/Close calls the shared "return to
  caller" routine: if the caller name is non-empty: flush a pending roster write if the roster is loaded, select palette 2, `pop(show=1)`, and
  only if k == WINDOW re-open (name, mode). One pop suffices (only the launcher's frame is pushed); a RUN frame restored this way is **not** resumed.
- `NewGame`: no extra push, `CleanUpGlue()`, open `StartCaravan` (K = `WINDOW`); the main-menu frame the launcher pushed stays at the bottom.
- "Return to main menu" (game over, quit battle, `endgame:`): `ClearGlueScriptStack` (all four depths and the data-file stack to 0), stop and
  discard the tune, build the menu; not a pop loop.

### 13.4 Asset inventory

No bitmap, font, palette, cursor, sound or music asset belongs to these built-ins; `AbortGame` uses the OS message box (buttons, icon, font,
beep are the system's). Data they read:

| Asset | Kind | Source | Use |
|---|---|---|---|
| question text | string | `BRTXT` 308 (module 4) | AbortGame box (and the troop-selection Abort box) |
| caption | string | executable literal "Warhammer" (same word as `BRTXT` 212) | that box's caption |
| hint texts of launching hotspots | strings | `BRTXT` 150, 151, 152, 158, 159, 161, 162 | tooltip ids on the 13.2 table (not used by the built-ins) |
| remembered tune | music | `binary/music/<name>.mid` (+ SoundFont/FM twin, `notes/music.md`) | restarted by `PopContext`, `PopContextCheckResume`, `OptionsDialogDone`; repeat count 0 = loops until replaced |
| window `[MIDI]` tunes | music | tune name per window (`title` for `MainMenu`, `intro3` for `OptionWindow`, `scribe` for the caravans) | stopped/discarded whenever the window is destroyed (clean-up, push), started when created (open, pop-restore) |
| resource names | WND.DLL RCDATA | `MainMenu`, `StartCaravan`, ... | re-opened by name (mode 1) |
| `ARMY.MRC` | file (working copy) | `SAVE/` | reloaded, edited, rewritten by `PopAndResume` |

### 13.5 Animation and glue

No animation, timer or visual effect belongs to the built-ins (the message box has none). The glue is the point: the launcher is the single
entry for every hotspot; the way back is `PopContext`, `PopContextCheckResume`, `UnwindMission`, `PopAndResume`, `AbortGame`, a native
window's "return to caller" or `OptionsDialogDone`; `gocaravan:` and the panel buttons push RUN frames these pops later restore. Side effects an
engine must reproduce: **creating a window starts its `[MIDI]` tune, destroying it stops the tune** (also for push/pop restores); window-local
animation timers restart on restore.

### 13.6 Stack effect of each hotspot

`W(x)` = WINDOW frame whose caller is window `x`; `R` = RUN frame (script frame + window snapshot + caller). Stacks bottom -> top; `S` = whatever lies
below, unchanged unless shown; the launcher's frame is `W(c)`, `c` = the clicked window.

| Built-in | Hotspot(s) | Stack before | After launcher push | After built-in | Screen / script result |
|---|---|---|---|---|---|
| `PopContext` | `CaravanSelectMission` (480,250) | `S, R(map)` | `S, R, W(CaravanSelectMission)` | `S` | map restored as left (same selected row); flow stays parked unless not paused and `parked = 0` |
| `PopContext` | `OptionWindow` Cancel (397,335) | `S, W(c)` (`c` = caravan or `MainMenu`) or `S, R` (panel Options) | `S, W(c), W(OptionWindow)` | `S` | `c` re-opened by name; panel case: RUN restored, resumed only if `parked = 0` |
| `PopContextCheckResume` | `CaravanContinueMission` (480,250) | `S, R(mission)` | `S, R, W(CaravanContinueMission)` | `S` | mission map restored; script resumed if not paused and `parked = 0` |
| `PopAndResume` | `CaravanRecruit*AndResume`, `InfoCaravanENA/LA/SZA/SZB/WED` | `S, R(mission)` | `S, R, W(caravan)` | `S` | mission windows restored, housekeeping, script continues after `gocaravan:` |
| `UnwindMission` | `CaravanAfterMission*`, `CaravanAfterEncounter*`, `InfoCaravanBMA/BPC/ENE/LB/REA/REC`, `CaravanDietrich` | `S, R(flow), R(mission)` | `S, R(flow), R(mission), W(caravan)` | `S` | flow map restored, release step, flow resumes or player stays on the map |
| `AbortGame` No | (0,0,244,171) | `S, ...` | `S, ..., W(caravan)` | `S, ...` | same caravan rebuilt |
| `AbortGame` Yes | same | `W(MainMenu), W(StartCaravan), R(flow) [, R(mission)]` | `..., W(caravan)` | empty | main menu |
| `ExitProcess` | `MainMenu` (98,389), (501,389) | empty (a Load may leave `W(MainMenu)`) | `W(MainMenu)` | (frame left) | process ends |
| `NullWnd` | none | `S, x` | `S, x, W(c)` | `S` | previous window re-opened |
| `OptionsDialog` | `CaravanCommon1` (245,85), `MainMenu` x2, panel 9 | `S, [W(c) or R]` | `..., W(c)` (or `R` for the panel) | `..., W(c)` | `OptionWindow` open (frame still on the stack) |
| `OptionsDialogDone` | `OptionWindow` OK (203,335) | `S, W(c)` | `S, W(c), W(OptionWindow)` | `S` | options applied, `c` re-opened |
| `ArmyBook`, `HireOnlyArmyBook`, `MagicBook`, `EncyclopediaBook`, `Credits`, `LoadSaveWindow*` | see 13.2 | `S, x` | `S, x, W(c)` | same (native window on top) | on Done: one pop, `c` re-opened |
| `NewGame` | `MainMenu` (98,180), (501,180) | empty | `W(MainMenu)` | `W(MainMenu)` | `StartCaravan` open |
| window resource (`FlowScriptBP01`, `JournalBook`, ...) | `StartCaravan` (480,250) | `W(MainMenu)` | `W(MainMenu), W(StartCaravan)` | same | resource opened on top |

**Worked examples** (`MM` = main menu, `SC` = `StartCaravan`).

**A. Map -> caravan -> back** (first chapter). After New Game and the first flow script: `[W(MM), W(SC)]`, flow script current (K = RUN), map windows up,
flow parked in `waitforrelease`. (1) Panel Caravan button (slot 0): drain text; **push RUN** -> `[W(MM), W(SC), R(flow)]` (script frame, window
snapshot incl. mission list + selected row, palette 2, caller); windows destroyed; open `CaravanSelectMission` (K = WINDOW, palette 3, tune `scribe`
starts). (2) Click the back hotspot (480,250,160,110): launcher pushes `W(CaravanSelectMission)` (depth 4). `PopContext`: clean-up (stops `scribe`), no
remembered tune, pop #1 drops the W frame, pop #2 restores R(flow): frame, windows, palette 2, caller. Depth 2: `[W(MM), W(SC)]` (the R was consumed).
Flow has `parked = 1`, so nothing runs; map as left; silent unless the map's windows have a tune or one was remembered.

**B. After-mission caravan -> UnwindMission.** The mission script reaches `gocaravan:select`: `[W(MM), W(SC), R(flow)]`, mission script current.
`gocaravan` pushes RUN -> `[..., R(flow), R(mission)]`, cleans up, opens `CaravanAfterMission`. Click (480,250): launcher pushes `W(CaravanAfterMission)`.
`UnwindMission`: clean-up; pop W: dropped; pop R(mission): restored, no slot has a mission list -> clean-up, continue; pop R(flow): restored, slot with the
map's list found; no `replacescript`; copy the current mission over the selected record, recount, rebuild; `releaseflag = 0` and rows remain -> stop on the
map (`[W(MM), W(SC)]`); or `releaseflag = 1` -> resume the flow script.

**C. Mid-mission caravan -> PopAndResume.** `[W(MM), W(SC), R(flow)]`, mission script current; `gocaravan:recruit` -> `[..., R(flow), R(mission)]`,
`CaravanRecruitAndResume` open. Click exit: push `W(caravan)`. `PopAndResume`: clean-up; pop drops W; pop restores R(mission) (script frame current, mission
windows recreated and shown); `ARMY.MRC` housekeeping; resume -> the script runs the line after `gocaravan:recruit`. Stack `[W(MM), W(SC), R(flow)]`.

**D. Options from a caravan.** `[W(MM), W(SC), R(flow)]`, `CaravanSelectMission` open. Click Options (245,85): push `W(Caravan)`; `OptionsDialog`: clean-up
(stops `scribe`), open `OptionWindow` (tune `intro3` starts). Stack `[..., R, W(Caravan)]`. Click OK: push `W(OptionWindow)`; `OptionsDialogDone`: apply/store
options, clean-up (stops `intro3`), restart remembered tune if any and not paused, pop drops `W(OptionWindow)`, pop -> `W(Caravan)`:
`OpenWindowResource("CaravanSelectMission", 1)` (fresh caravan, `scribe` restarts). Stack `[..., R]`. From `MainMenu` the same with `W(MM)`; from a mission map
(panel 9) the push is a RUN frame and Done restores it and resumes only if `parked == 0` and not paused.

**E. Abort.** `[W(MM), W(SC), R(flow)]`, caravan open. Click (0,0,244,171): push `W(Caravan)`; the box appears over the still visible caravan. No: clean-up,
pop -> `W(Caravan)`, re-open it; stack back to `[W(MM), W(SC), R(flow)]`. Yes: clean-up, repaint; pop `W(Caravan)` (caller is a caravan: skip); pop `R(flow)`
(windows recreated then destroyed); pop `W(SC)` (skip); pop `W(MM)` -> caller starts with "MainMenu": re-open `MainMenu` (mode 1), tune `title`. Stack empty;
campaign files untouched.

**F. Underflow.** `PopContext` clicked when the stack holds only the launcher's frame: clean-up done, first pop drops it, second pop returns 0 and logs
"stack underflow": nothing restored, screen blank.

### 13.7 Input and exits

Mouse only for the launcher (release over the pressed hotspot, not while dialogue text is busy). The box is a system dialog (Y/N, Enter = Yes,
Alt+F4 ignored while it is up). `ExitProcess` is also reachable through the window's close box/Alt+F4. Exits: see 13.6. Nothing here writes a save
game or the options.

### 13.8 Engine status and deviations

Existing code: `whshr/glue_runtime.py` (`ContextSnapshot`, `push_context`, `pop_context`, `drop_context`, `unwind_to_run`, `MAX_CONTEXT_DEPTH = 16`),
`whshr/glue_scene.py` (`_leave_caravan`, `_confirm_abort_game`, `_reopen_caravan`, `release_mission`), `whshr/confirm_scene.py`,
`whshr/campaign_state.py` (`leave_caravan`), `whshr/glue_scene_state.py`.

| Item | Status | Deviation |
|---|---|---|
| RUN context push/pop with windows, frame, palette, current window | 🟡 exists | single stack; no WINDOW frames, no (caller name, mode) stack, no 8/8/16 sub-limits; `pop_context` returns `None` for both "empty" and other failures; a non-RUN kind is not "corrupt" |
| WINDOW frames / "re-open the caller by name" | ❌ scene links (`return_scene`, `caravan_return`) instead | equivalent for common paths, but `NullWnd`, arbitrary nesting and the abort loop's "pop until MainMenu" are not expressible |
| `PopContext` / `PopContextCheckResume` | 🟡 `_reopen_caravan` / scene transitions | remembered-tune restart and paused/`parked` resume test not modelled |
| `UnwindMission` | ✅ `_leave_caravan` + `release_mission` | frame walk replaced by the `return_scene` link; **`unwind_to_run` stops at the first RUN frame and does not test for a mission list**, does not clean mission-script frames; `replacescript` handled in `campaign.complete_mission` |
| `PopAndResume` | ✅ `_leave_caravan` | housekeeping done; script resumed unconditionally (matches); the engine also **stops speech** on every leave (not established for the original: 🟡) |
| `AbortGame` | 🟡 `_confirm_abort_game` | wrong question string: uses `GMTXT 36070` instead of `BRTXT 308`; box drawn by the engine on a dark screen, not over the caravan; Yes creates a fresh `MainMenuScene` (equivalent result, mode/tune not from a frame, no stacks unwound); No returns the same scene object (original rebuilds the caravan: animation/tune restart) |
| `ExitProcess` | ✅ main menu maps `exitprocess` to quit | no confirmation (correct) |
| `OptionsDialog`, `OptionsDialogDone`, `NullWnd`, `PopContext` (options), `MagicBook`, `EncyclopediaBook`, `Credits` | ❌ inert ("not yet implemented") | |
| window `[MIDI]` tune stop on destroy / start on create | ❌ | see 13.3.1 |
| busy-window launcher gate | ❌ | see 13.3.2 |

Suggested shape: keep the scene graph if preferred, but make the launcher the single point that records a "caller" (window name + mode) and pushes a
frame; add an explicit `ContextFrame(kind, caller, script_state?, windows?, palette?)` stack (16 deep) with the caller stack derived from it, so
`PopContext`, `UnwindMission` (with the map-list test), `PopAndResume` (housekeeping + unconditional resume), `NullWnd` and the AbortGame loop can be
tested without scene links. Engine saves may store a different shape (`CLAUDE.md`, "saves are the engine's own").

### 13.9 Test scenarios (BDD)

1. **PopContext returns to the parked map.** Given `[W(MM), W(SC), R(flow)]`, flow parked (`parked = 1`), `CaravanSelectMission` open and a mission row
   selected; When its back hotspot is clicked; Then the map shows the same row selected, the stack is `[W(MM), W(SC)]`, the flow script is not resumed.
2. **PopContext resumes an unparked script.** Given the restored RUN frame has `parked = 0` and the game is not paused; When `PopContextCheckResume` runs;
   Then the script continues; with the game paused it does not.
3. **Remembered tune.** Given `playmidi:sighted` ran and the map windows have no `[MIDI]`; When `PopContext` returns from a caravan; Then `sighted` plays
   (looping); paused: started paused; no remembered tune: the map is silent.
4. **UnwindMission skips frames without a mission list.** Given `[W(MM), W(SC), R(flow, list), R(mission, no list)]` and an after-mission caravan; When its exit
   is clicked; Then the mission frame is dropped, the flow frame restored, its selected record overwritten by the finished mission, stack `[W(MM), W(SC)]`.
5. **UnwindMission with `replacescript`.** Given the selected record has a replacement script; When the release step runs; Then the named script is opened,
   the current mission is **not** copied and the flow is not resumed by the built-in.
6. **PopAndResume.** Given a mid-mission caravan; When its exit is clicked; Then the mission script's frame and windows are restored, unhired regiments are
   dropped from `ARMY.MRC`, reinforcements cleared, and the script continues after `gocaravan:` even if the game is paused.
7. **AbortGame No.** Given a caravan; When Abort is clicked and No chosen; Then the same caravan is shown again and the stack is unchanged.
8. **AbortGame Yes.** Given `[W(MM), W(SC), R(flow)]` and a caravan; When Yes is chosen; Then the main menu is shown, the stack is empty, and
   `ARMY.MRC`/`PLAY.MRC` are byte-identical to before.
9. **AbortGame text.** Given the installation strings; Then the question is `BRTXT 308`, caption "Warhammer", buttons Yes/No, question icon.
10. **Abort with no menu frame.** Given a stack without a `MainMenu*` frame; When Yes is chosen; Then every frame is popped and the engine reports an
    error (original: blank screen).
11. **ExitProcess.** When an Exit hotspot is clicked; Then all windows are destroyed and the process ends without a prompt and without writing files.
12. **Launcher fallback.** Given a hotspot whose `res:` is neither built-in nor resource; Then the `script:` name is tried as a disk file and, failing that,
    the screen is blank and one context frame stays (data error; tests should assert a diagnostic).
13. **Depth/underflow.** Given 16 frames, a 17th push is refused without changing anything; a pop on an empty stack returns "nothing" and changes nothing.
14. **Window tune lifecycle.** Given `CaravanSelectMission` (tune `scribe`); When a book is opened from it; Then `scribe` stops; When the book is closed;
    Then the caravan is rebuilt and `scribe` starts from the beginning.

### 13.10 Open questions

- 🟡 **Music across a caravan visit**: a window's tune stops when it is destroyed and starts when created, so after `UnwindMission`/`PopAndResume` the map is
  silent unless restored windows or the resumed script start a tune. This contradicts the inference in `notes/briefing_dialogue.md` ("the caravan's `scribe`
  tune carries over"); listening after an after-mission caravan would settle it.
- ⬜ Whether the busy-window launcher gate really blocks all hotspots while dialogue is queued (not observed).
- ⬜ Whether speech and portrait animation are stopped by destroying windows (no built-in stops speech explicitly; the engine stops it on leave).
- ⬜ The exact rule by which caravan-leave housekeeping removes a regiment (flag bit vs. file record) and the meaning of the "hired" field it tests.
- ⬜ After **Load**, whether a `MainMenu` frame is guaranteed below the loaded stack (the save format stores all four stacks; `savegame.5` has
  `[WINDOW, WINDOW, RUN, RUN]`); needed for the AbortGame Yes loop.
- 🟡 A hotspot while paused: the launcher does not check it; only the two resume tests do.

## 14. Click speech (`DietrichSpeech`) ✅

Marks: ✅ read from the game data and cross-checked, 🟡 inferred / not observed running, ⬜ open. Full game only. This is NOT a window: it is a hotspot
behaviour. Context stack and launcher are in §13 and only referenced here.

### 14.1 Purpose
A caravan window shows the scribe Dietrich in its backdrop. Clicking him plays a canned run of 1 to 4 text lines (voice clip + typed subtitle) while two small
overlay animations (eyes, mouth) play on his portrait. The run differs per caravan variant. Nothing else changes: no window opens, no context frame is pushed,
no palette or music change, no state is read or saved. Every click replays the run from its first line (no counter, no randomness).

### 14.2 Where it appears
Exactly 15 hotspots in the full game (scan of all 535 WND scripts), all with the same rectangle **(x 270, y 150, vx 95, vy 110)**, `cursor:HandOpenCursor`,
`altcursor:HandCloseCursor`, `set:res=160` (hover hint, BRTXT 160), `script:null.wnd` (documentation only, no such resource), `res:DietrichSpeech`, no
`downsfx`/`upsfx`, no `count`/`linkid`. **No click cues exist for this hotspot type** (cues come from per-hotspot `downsfx`/`upsfx`).

| Window | clickres (first id) | clickrescnt | lines | ids spoken |
|---|---|---|---|---|
| `InfoCaravanWED` | 914 | 2 | 3 | 914-916 |
| `InfoCaravanENA` | 919 | 3 | 4 | 919-922 |
| `InfoCaravanREA` | 929 | 1 | 2 | 929-930 |
| `CaravanAfterMissionWithRecruit` | 931 | 1 | 2 | 931-932 |
| `CaravanAfterEncounterWithRecruit` | 931 | 1 | 2 | 931-932 |
| `CaravanRecruitAndResume` | 931 | 1 | 2 | 931-932 |
| `InfoCaravanREC` | 933 | 3 | 4 | 933-936 |
| `InfoCaravanSZA` | 938 | 1 | 2 | 938-939 |
| `InfoCaravanSZB` | 940 | 3 | 4 | 940-943 |
| `InfoCaravanLA` | 944 | 2 | 3 | 944-946 |
| `InfoCaravanLB` | 947 | 0 | 1 | 947 |
| `InfoCaravanBPC` | 955 | 1 | 2 | 955-956 |
| `InfoCaravanENE` | 958 | 0 | 1 | 958 |
| `InfoCaravanBMA` | 959 | 1 | 2 | 959-960 |
| `CaravanDietrich` | absent (0) | absent (0) | 0 | none |

- The 11 `InfoCaravan*` windows are the per-place info caravans (BMA BPC ENA ENE LA LB REA REC SZA SZB WED), each with its own run.
- `CaravanDietrich` is the only one without `clickres`; no WND script and no executable string references it (dead or development window). Its click would use
  text id 0 (no BRTXT id 0, no `B0.WAV`): no text, no voice (🟡, moot).
- Line k of a click is id `clickres + k`, k = 0..clickrescnt. `clickrescnt` counts the lines AFTER the first (key absent = one line). Every id used has a BRTXT
  string and a `B<id>.WAV`.

### 14.3 Construction (behaviour)

#### 14.3.1 Detection and dispatch ✅
In the glue window's mouse handler, on **button release** over the hotspot whose **press** was on the same hotspot, when the hotspot has a non-empty `res:` or
`script:` value:
1. The click-speech table is consulted FIRST, before the busy gate and the launcher (§13): a 2-entry table matched by an exact, case-sensitive compare with the
   hotspot's `res:` name: `DietrichSpeech` -> variant 1 (talking), **`DietrichRead`** -> variant 2 (reading).
2. Found: the click-speech routine runs with (window, `clickres`, `clickrescnt`, variant) and reports "handled". The launcher is **not** run: no context push, no
   `CleanUpGlue`, no caller name, nothing destroyed. Not found: the click continues to the busy gate and the launcher (§13).
3. Routing is by NAME, not by the presence of `clickres`: a `DietrichSpeech` hotspot without `clickres` uses id 0; a hotspot with `clickres` and another `res:`
   name does not speak.
4. A "handled" click also skips the generic "finish pending dialogue" fast-forward that a non-launching release performs.

#### 14.3.2 The two names ✅
| Name | Variant | Overlay animations |
|---|---|---|
| `DietrichSpeech` | 1 | `TalkEyesCell` at (300,200) 44x16 and `DietMouthCell` at (288,220) 68x48; used by all 15 hotspots |
| `DietrichRead` | 2 | `ReadEyesCell` at (312,208) 44x16 and `DietBookCell` at (296,260) 148x108 (Dietrich reading a book); **no shipped script uses it** |

Text/voice logic is identical for both; only the overlay pair differs.

#### 14.3.3 Start of a run ✅
1. **Guard.** If the variant's animation handle is still live (previous run not finished) the click is **ignored completely**: no restart, no queueing, no line
   skip. Handles are reset by `CleanUpGlue`, so a new window starts free.
2. Two overlay entries are added to the window's bitmap-animation list (limit 16 per window; if full, silently dropped):

   | Variant | Entry (+ mask `Mask`) | x | y | w | h | cells | start cell | loop pause (50 ms steps) | `timecnt` (steps) |
   |---|---|---|---|---|---|---|---|---|
   | 1 | `TalkEyesCell` | 300 | 200 | 44 | 16 | 0..2 | 1 | 60 | 2 |
   | 1 | `DietMouthCell` | 288 | 220 | 68 | 48 | 0..5 | 5 | 0 (🟡 not set) | 2 |
   | 2 | `ReadEyesCell` | 312 | 208 | 44 | 16 | 0..2 | 1 | 0 (🟡) | 2 |
   | 2 | `DietBookCell` | 296 | 260 | 148 | 108 | 0..11 | 11 | 0 (🟡) | 2 |

   All loop until the run ends. Cell 2 of each eyes set is never shown.
3. Dialogue state set globally (persists after the run; scripts set their own later): **text colour index 2 (`red`)**, left alignment, **`textlines` = 2**.
4. **Speech ON** (sound option on, device present), sequential mode: remaining := `clickrescnt`, id := `clickres`; hover hint cleared; the clip of the first id
   starts (previous clip stopped first); its BRTXT string is queued with an end marker and the "line finished" callback. When a line's text is finished the
   callback waits for its clip, stops it, and if remaining > 0: remaining -= 1, id += 1, hint cleared, next clip started, next string queued with the same
   callback. On the last line the callback removes both overlay entries (rectangles invalidated, plain backdrop shows) and the run is over.
5. **Speech OFF**, text only: strings `clickres .. clickres+clickrescnt` are ALL queued at once (only the last carries the end marker), no clip; overlays run
   while the text types and are removed after the last line. With `textlines = 2` the lines scroll as in a briefing without audio (`briefing_dialogue.md` §3.1).

#### 14.3.4 Text table and audio ✅
- Text: **BRTXT** (glue text table), ids 914-960 (hover hint ids 150-160 are BRTXT too). Not GMTXT. The id is also the audio id:
  `binary/glue/speech/b<id>.wav`, decimal, no padding, no speaker prefix (`A*` files are cutscene lines). GOG install: `REMOTE/BINARY/GLUE/SPEECH/B<id>.WAV`
  (case-insensitive). Lookup/playback identical to `playtext` (`briefing_dialogue.md` §3.2): whole file read, played once at the `setwavvolume` level, missing
  clip = text only.
- Measured clips (PCM mono 22 050 Hz 16-bit; seconds = data bytes / 44100):

  | ids | durations (s) |
  |---|---|
  | 914-916 | 4.63, 6.80, 6.66 |
  | 919-922 | 2.84, 3.93, 3.46, 2.92 |
  | 929-930 | 7.44, 3.14 |
  | 931-932 | 3.64, 4.76 |
  | 933-936 | 12.24, 8.33, 4.38, 4.56 |
  | 938-939 | 5.52, 2.68 |
  | 940-943 | 3.85, 6.52, 7.32, 9.99 |
  | 944-946 | 4.45, 4.60, 8.87 |
  | 947 | 8.04 |
  | 955-956 | 9.02, 8.78 |
  | 958 | 2.40 |
  | 959-960 | 5.53, 8.08 |

  Longest run: `InfoCaravanREC`, about 29.5 s. 100 % coverage (string and WAV for every id). Line lengths about 40-144 characters.

#### 14.3.5 How the text is shown ✅
Same dialogue block as a briefing (`briefing_dialogue.md` §3.3-§3.5): drawn into the 640x480 base glue window, glue font slot 4 (`SUBTEXT.FON`), bottom-anchored
(bottom baseline 1.5 line heights above the bottom edge, 1.10 line heights per extra line), left margin 5 %, wrap at 90 %, black 5x5 outline plus red, 2 visible
lines, 25 ms timer, one character per 2 ticks; with a clip the typed fraction follows the playback percentage; final hold 8 ticks with a clip (30 without). The
hover hint uses the same bottom band (red, font 4, centred) and is blanked when the run starts and between lines.

#### 14.3.6 Clicks while it is running ✅ / 🟡
| Click | Effect |
|---|---|
| Dietrich hotspot again | **ignored** (guard). Not a skip, not a restart. |
| another hotspot (Army Book, Encyclopedia, Caravan, ...) | the launcher's busy gate (dialogue queued or a text row still on screen) blocks it: **nothing opens**; the release then only fast-forwards the text (`glue_interpreter.md` release rule) |
| empty window | fast-forward: typing finishes without delays, the line's clip is waited out and stopped, the callback then queues the next line 🟡 (one click ending the whole run or only the current line is not settled) |
| Pause (Dietrich panel where present) | freezes typing and animation steps, pauses the clip |
| leaving the caravan | `CleanUpGlue` wipes the entries and resets the guards |

### 14.4 Asset inventory ✅ (sizes measured from the BITMAP.DLL catalog)
| Asset | Kind | Source | Size / rule | Use |
|---|---|---|---|---|
| `TalkEyesCell0..2` | bitmap set | BITMAP.DLL | 44x16, 8 bpp, 3 cells, same palette as the caravan backdrops (`palindex 3`) | eyes at (300,200); cells 1 then 0 (cell 1 = eyes closed, checked visually) |
| `DietMouthCell0..5` | bitmap set | BITMAP.DLL | 68x48, 6 cells | mouth at (288,220); cells 5..0 (5 = closed) |
| `ReadEyesCell0..2` | bitmap set | BITMAP.DLL | 44x16, 3 cells | `DietrichRead` eyes (312,208); cells 1,0 |
| `DietBookCell0..11` | bitmap set | BITMAP.DLL | 148x108, 12 cells | `DietrichRead` book (296,260); cells 11..0 |
| `Mask` | mask name | per entry; transparency is palette index 0 (`glue_keywords.md` `setmask`) | | all overlays |
| `TalkBackgroundPic` (Info caravans), `Caravan` (`CaravanDietrich`) | bitmap | BITMAP.DLL 640x480 8 bpp | | the portrait; compositing eyes cell 1 + mouth cell 5 at the listed positions lands exactly on the face |
| `HandOpenCursor` / `HandCloseCursor` | cursor | named RT_CURSOR groups in `WHSHR.EXE` (32x32 mono) | | hover / left button held over the hotspot |
| `SwordCursor` | class cursor | `WHSHR.EXE` | | default outside hotspots |
| `B914..B960` (runs of §14.2) | speech | `REMOTE/BINARY/GLUE/SPEECH/` | 22 050 Hz mono 16-bit, 2.4-12.2 s | one clip per line |
| BRTXT run ids, BRTXT 160 | strings | BRTXT.DLL | | subtitle text; hover hint |
| font slot 4 `SUBTEXT.FON` | font | GLUE/ | | subtitles and hint, red |

Shared: backdrops, cursors, font 4, the dialogue block, the speech folder. Unique: the four `*Cell` sets, the name table, the id runs. `B3.WAV`/`B4.WAV` are not used.

### 14.5 Animation and glue ✅
- Two overlay animations per run, no portrait sprite. They are ordinary window bitmap-animation entries (the mechanism of a `[BITMAP]` block with
  `animstartframe`/`animstopframe`/`timecnt`/`looptimecnt`, `glue_keywords.md`, `campaign_tent.md` §5) created by code at click time. Cell name = base name +
  decimal frame number; the index counts **down** from the start cell to 0 and wraps.
- Timing: 50 ms steps (two 25 ms ticks); each cell shows for `timecnt + 1` = 3 steps = 150 ms; the wrap after cell 0 adds the loop pause. Talk eyes: cell 1
  (150 ms, a blink at the moment of the click), cell 0 (150 ms + 60 steps = 3.15 s), repeat. Mouth: 5..0, 150 ms each, 0.9 s cycle. Book: 11..0 (1.8 s cycle).
  Read eyes: 1,0.
- Stop: after the last line's text is finished and its clip waited out, the entries are removed and their rectangles repainted.
- Layers: backdrop, overlays (eyes then mouth), hotspot art, dialogue/hint band. The mouth is not lip-synced; it runs for the whole run.
- Palette, music, other animations (lamp, candle) unaffected. No `[ANIM]`/`[INIT]`; wiring is only `res:DietrichSpeech`, `set:clickres`, `set:clickrescnt`,
  `cursor`, `altcursor`, `set:res`. No script events, never resumes a script.

### 14.6 Hotspot keys and cursors
| Key | Value | Meaning |
|---|---|---|
| `x,y,vx,vy` | 270,150,95,110 | click rectangle (all 15 identical) |
| `cursor` / `altcursor` | `HandOpenCursor` / `HandCloseCursor` | hover / while the left button is held 🟡 exact press moment |
| `set:res` | 160 | BRTXT hover hint (red, only for hotspots with a cursor) |
| `set:clickres`, `set:clickrescnt` | §14.2 | first id, extra lines |
| `res` | `DietrichSpeech` | routes the click |
| `script` | `null.wnd` | documentation only |

### 14.7 Input and exits
Left mouse only. No exit path; the run ends itself. No frame is pushed or popped.

### 14.8 State read/written
None persistent: no per-hotspot counter, no visited flag, nothing in `savegame` or ARMY/PLAY/MARCH. The hotspot record's `count`/`linkid` rotation is a different
feature and unused here. Global side effect only: text colour red, left alignment, `textlines` 2 (§14.3.3). Every click starts at `clickres`.

### 14.9 Engine status and deviations
Engine: `whshr/glue_render.py` (parses the keys), `whshr/glue_runtime.py` (`_hotspot_speech`), `whshr/frontend/glue_view.py` (release -> `hotspot-speech`),
`tests/test_hotspot_speech.py`, `tests/test_speech.py`. The line count (`clickrescnt + 1`) and the id run are right.

Deviations:
1. **Trigger**: routed by the `res:` NAME (`CLICK_SPEECH_NAMES`, exact match); a named hotspot without `clickres` speaks id 0 (nothing). ✅ fixed
2. **Second click while running**: ignored, as in the original (only a click on the empty window still skips a line). ✅ fixed
3. **Overlay animations** (`SPEECH_OVERLAYS` table in `glue_runtime.py`, drawn by `glue_view.py`) run for the whole run and are removed after the last line. ✅ fixed
4. **Text state**: red and `textlines` = 2 are always set at the start of a run. ✅ fixed
5. **Speech OFF**: original queues all lines at once (scrolling 2-line block); engine steps them singly. 🟡
6. **Busy gate**: other hotspots must be inert while the text is on screen. Unverified in the engine. 🟡
7. **Reaction hotspots** (only `set:res` + `altcursor:HandCursor`, the PROVISIONAL rule in `glue_render.py`): the original never calls the speech routine for them
   (no `res:`/`script:` value); the `set:res` text is shown as the red hint line on **button press** (a hotspot without a cursor shows its hint on press, one with a
   cursor on hover), voice only if the hotspot has `downsfx`/`upsfx` (these carry none). So "reaction speech" is a hint line. 🟡 confirm by running.

Suggested shape: a click-speech table {`DietrichSpeech`: (eyes, mouth), `DietrichRead`: (eyes, book)} in the glue runtime, a guard, two synthetic bitmap animators
added on start and removed on the last line, then the existing dialogue block.

### 14.10 Test scenarios (BDD)
1. Given `InfoCaravanREC`, when Dietrich is clicked, then BRTXT 933-936 show red one at a time with `B933-B936.WAV`, both overlays animate throughout and
   disappear after 936, and no context frame is pushed.
2. Given a run in progress, when Dietrich is clicked again, then nothing changes.
3. Given speech off, when `InfoCaravanWED` Dietrich is clicked, then 914-916 are queued at once as text, no clip is requested, and the overlays stop after the last line.
4. Given a run in progress, when Army Book is clicked, then it does not open.
5. Given `CaravanRecruitAndResume` clicked twice after the first run finished, then both runs start at 931.
6. Given the button held on Dietrich, the cursor is `HandCloseCursor`; hovering shows `HandOpenCursor` and hint 160.
7. Given `CaravanDietrich`, when clicked, no text, no clip, no crash.
8. Data: every id of every run has a BRTXT string and a `B<id>.WAV`.

### 14.11 Open questions
- ⬜ Fast-forward on the empty window during a voiced run: one line or whole run; is the clip cut.
- ⬜ Loop pause of mouth/book/read-eyes entries (not set; assumed 0).
- ⬜ Exact moment the closed-hand cursor appears (press or next move): runtime test.
- ⬜ Whether the 0 -> 5 wrap of the mouth cycle looks natural (visual test).

## 15. Corrections to earlier notes (to be applied to the named files)

Statements in existing notes or in the engine that this report shows to be wrong or incomplete, grouped by the window whose research found them.

### options
- `notes/builtin_widgets.md` section 7: registry value is `Options` under `Software\Mindscape\WarHammerFB` (case-insensitive); GOG leaves `3,1,1,1,1,1,1,2`. The field order, state<->value rules, counts (3/2/2/2/2/2/2/3), sound/music effects and flag list hold.
- Same section: "`GMTXT` 36000 + state" holds only for the shading row; each row has its own base (linkid). Full table is in the Options section 4.4.
- Same section: Done restarts the remembered tune only when not paused (no music restart before applying music); PopContext restarts it and then pauses it if paused.
- Same section: load clamps only from above (`v1 = 0` or a negative music value gives an out-of-range state).
- Same section: panel 9's Options button acts on release and pushes a RUN frame; on return the script resumes (unless paused) instead of a window re-open.
- `notes/builtin_widgets.md` native-button line "speech cue 3 on press, 4 on release" is wrong: press = `B4.WAV`, release inside the control = `B3.WAV` (glue `downsfx=4`, `upsfx=3`); skipped while speech plays or speech is off.
- Same section quirk (b) "state 3 Phong unreachable": true, but only labels 36000-36002 exist for states; the in-game mapping of stored levels to names is unverified.
- Hotspot table (working-table row) "OptionsDialog: 3 hotspots (CaravanCommon1, MainMenu x2)" is right for definitions, but `CaravanCommon1` is included by about 20 full-game caravan windows, so Options is reachable from all of them.
- Music: a glue tune with repeat count 0 loops until replaced or stopped.

### magic book
`notes/builtin_widgets.md`:
- Section 1 (button table): "speech cue 3 on press and 4 on release" is inverted. Press (mouse-down) = `B4.WAV`, release inside the control = `B3.WAV`, both in the glue speech directory; skipped while speech plays and when speech is off (also affects `credits.md`). Label offset of ATab buttons is (+4,+2) released, (+3,+3) pressed.
- Section 3 left page: the title is **below** the picture (picture bottom y = 282, title block from y = 288), not above. The fit test is picture height + 3 < 250 (width not tested) and title-block height + 3 < 125 (always true). Title = `FancyLetters` drop cap + slot 5 blackletter, colour (67,47,39).
- Section 3 right page: "text wraps around the drop cap" is true only for the title; in the description only the first line is raised/indented (first line on the cap's bottom edge, rest full width) and **only the Items book has a cap**; spell texts start with an `@Name#` bold heading. Text ends at the first ESC; blank lines collapse; page bottom y = 410.
- Section 3 Next/Back: Back from page 0 goes to the previous known entry's **first** page, not its last.
- Section 3 entry list: spells are known by **college** (Celestial 1-5, Bright 6-10, Amber 11-15), three entries; General Dispel, Waaagh! and Skaven spells unlock nothing; items known iff any unit carries the id; lists come from unit-level `addspell:`/`addmagicitem:` lines of every unit in `ARMY.MRC` (hired or not).
- Section 3 buttons: Spells `0x108` x = 14 (`VioletATab`), Items `0x109` x = 104 (`GreenATab`), Done x = 350 are right; add: no keyboard handling at all.
- Section 3 last note and section 8 item 2: closed for the Magic book (17 items, 3 colleges, all names/ids/bitmaps/RCDATA); section 8 item 3 (drop-cap wrap rule) is now exact.
`notes/campaign.md` 4.4: the second and third book lists (`BKO2` 16 bytes, `BK03` 72 bytes) are the Magic book's known spell **colleges** (3 flags + -1) and **items** (17 flags + -1), rewritten from `ARMY.MRC` at every open, not "bestiary/places" pages. Only `BK01` (`enablebook:0=`) is the Encyclopedia list.
`notes/glue_keywords.md`: `set:res=158` on the Magic book hotspot is a `BRTXT` hint id (text 158). `magic.wnd` has no matching resource (as for `encybook.wnd`).
Working-table row for `MagicBook`: the full game has two hotspot definitions: `CaravanCommon1` (an included sub-script, present on 20 caravan windows) at (0,246,164x46) and `CaravanDietrich` at (0,192,164x52), hand-open/hand-close cursors, hint `BRTXT 158`.
`whshr/frontend/army_records_view.py` `_description` should cut at the first ESC (0x1B), not only strip `\x1a\0\r\n`.

### encyclopedia
1. `notes/builtin_widgets.md` section 3 (Encyclopedia column):
   - Left page: the title is centred at the *bottom* (y = 410 - height) with a drop-cap first letter in slot 5; the picture is at y = 285 - h; the "fits in 250x125 -> bottom, else vertically centred" rule belongs to the Magic book only.
   - Title id is `BKTXT 100 + key` (Magic book: `200 + 50*book + entry`).
   - Description at x = 350, y = 35, 240x375; the page-0 drop cap indents the first line and starts the text block at `35 + capHeight - lineHeight`; paragraphs (CR/LF) are indented by three "X" widths.
   - Back from page 0 goes to the previous known entry's page 0.
   - The first shown entry is always position 0 (`Men`) since key 28 is known by default; keys 0, 6, 10, 21, 28 are known at start.
   - Contents: 28 races/creatures, not "bestiary/places"; key 11 exists but is never shown.
   - Done is at x = 350 (not 525 as in Credits); no keyboard.
   - Button label offset is (+4,+2) released, (+3,+3) pressed (the (2,4)/(3,3) pair is wrong). Click cues: press = `B4.WAV`, release inside = `B3.WAV` (not 3 on press, 4 on release).
2. `notes/builtin_widgets.md` section 8 item 2: the Encyclopedia entry list is now given (Encyclopedia section 6.3) and can be closed for this book; Magic book tables are covered in section 5.
3. `notes/builtin_widgets.md` section 3 row "Opened by": `EncyclopediaBook` appears in `CaravanCommon1`, `CaravanDietrich` and `Start` (full game); `Start` is a caravan-style window, not a caravan.
4. `notes/campaign.md` 4.4: array sizes are 30/4/18 words including the terminator; BK01 = Encyclopedia (29 keys, 5 known by default); flag index = entry key = name-table index, not display position. "In-game journal (troop book, bestiary/places)" should read: BK01 = bestiary entries (this window); the Journal hotspot (`BRTXT 153`) is a separate feature not opened by any built-in found so far. `savegame.5` differs from `.0` by key 26 (Wolves, enabled by `BPMission1`).
5. Working-table row "EncyclopediaBook 5": 3 full-game hotspots (`CaravanCommon1`, `CaravanDietrich`, `Start`).
6. `notes/glue_keywords.md` (`enablebook`): kind 0 = Encyclopedia, keys 0..28; a repeated call is harmless; `enablebook:1`/`:2` are unused by any shipped script.

### new game main menu

- `notes/native-windows.md` §2 (`NewGame`): "16 characters max" is the buffer size; the limit is **15** typed characters. The prompt is not a "player name" field: the text is the *leader name of regiment id 2* in `ARMY.MRC` (default = its current leader). Add: **Esc/Cancel still starts the game** (default name kept); no OK/Cancel buttons, keyboard only; allowed characters as in §7.3.4.
- `notes/builtin_widgets.md` §6 and `whshr/savegame.py DESCRIPTION_LIMIT = 25`: the Save description box limits input to **24** characters (buffer 25). Also say the two prompts are one widget (art `EditScroll` vs `NameScroll`, same (172,214) origin).
- `notes/campaign.md` §4.8 / §2.1: New Game overwrites all four working files (from `SCRIPT/STRTARMY.MRC`, `MAXARMY.MRC`, `MARCH.MRC`, `DEBRIEF.DBF`), sets coffers to the default, resets the roster flag table (§7.3.1 step 8) and stores the commander name in `ARMY.MRC` only; the note lists none of this.
- `notes/glue_interpreter.md` row "`start` | no | yes | `StartCaravan` (new game: nothing to return to)": the `start` request itself does not push, but the hotspot launcher already pushed the menu's WINDOW frame, so the stack is NOT empty after New Game.
- `notes/glue_keywords.md` §3.10: consistent (`[DEMODEFAULT]` inert); add the parsed field names (target, script, flag) and that `setdemodefault:` also writes them.
- `notes/palette_selection.md` (`palindex -1`): `NameScroll` shares the `OptionScreen` colour table (no palette change needed); twin `EditScroll` uses shifted indices 151-156 (other palette).
- Native-windows table entry 10 (NewGame): omits that no window is destroyed before the prompt, the copies overwrite, the flag-table/coffers reset happens, the prompt is modal, and Cancel continues.

### load save

- `notes/builtin_widgets.md` §6: description limit is **24** (not 25); default description is the constant `BRTXT 500` (item 6 closed), not mission-dependent.
- `notes/builtin_widgets.md` §6: OK/Cancel labels = `BRTXT 336`/`337` and `307`; slot labels = description or literal "-Empty-"; add tent icons, the 207-px text field at x+24, colours, that the dialog is hidden during the prompt, that the prompt art is `EditScroll` 296 x 52 (not 58), that `[LOADANDSAVEGAME] set:x/y` are only a non-zero gate (position fixed), and that the dialog has no keyboard handling.
- `notes/builtin_widgets.md` §6 opener table: Save also appears through the `CaravanCommon2` include (20 windows, §8.2).
- `notes/glue_keywords.md` §3.10: `[LOADANDSAVEGAME]` `x`/`y` = "placement" is wrong: non-zero gate only.
- `whshr/savegame.py` `DESCRIPTION_LIMIT = 25`, `whshr/load_save_scene.py` `DEFAULT_DESCRIPTION` / "builtin_widgets open item 6" comments, and the test that caps at 25: limit is 24, default is `BRTXT 500`.
- `notes/native-windows.md` line 29: `LoadSaveWindow2` is opened by two hotspots on `MainMenu`; line 30 window list should be the 20-window include.

### debrief

- `notes/debrief_evaluation.md` §4.1 (last paragraph): "modes 4/6/7 have no such check" is wrong for 6 and 7; the "no list -> screen skipped" test applies to modes 2, 3, 6, 7 and not to mode 4 (§9.3.1a). Null-list outcomes are skipped in 6 and 7 too.
- `notes/debrief_evaluation.md` §4.4 and `notes/troop_selection.md` §1.3: win/lose music is used for modes 2, **6 and 7**, not only mode 2; mode 4 uses `tactical`.
- `notes/troop_selection.md` §1.2: "6 and 7 behave as 2 for paging" is wrong. Mode 6 has P2 and P3 only (Next disabled on the last P3 page); mode 7 has P2 and P4 only (Next on P2 jumps to P4, Back from P4 returns to P2); mode 2 has P2, P3, P4. Mode 3 cannot reach P4 either.
- `notes/troop_selection.md` §6 (debrief pages): P3 columns are kills 345, dead 405, wounded 465, experience 530, plain integers, no ring mark, no bottom hints; the `BKTXT 611` line sits at x = 345 under the rows; P2's "up to two more result lines" are the item-pickup lines of objectives `K` and `X` (`BKTXT 610`), preceded by one blank line; P2 has no pictures. P4: title too (`BKTXT 403`), `BKTXT 5005` in the heading font at y = 50, pitch 18, credit format `" %d gold crowns"`, debit `"-%d gold crowns"`, label-only lines for armour/2x, coffers pair = coffers + final.
- `notes/troop_selection.md` §2 / `notes/builtin_widgets.md` §1: tab-button label offsets `(4,3)/(0,3)` and `(2,4)/(3,3)` are wrong; the correct offsets are (+4,+2) released and (+3,+3) pressed added to the centred text position.
- Click cues (all glue buttons): press = `B4.WAV`, release inside = `B3.WAV`; "3 on press, 4 on release" is wrong.
- `notes/campaign.md` §5 step 5: the debrief screen does not always show "the balance sheet and the troop book": pages depend on the open mode; mode 6 shows no balance sheet.
- `notes/activity_results.md` §2.4/§5: when a `debrief:`/`debriefwithsummary:` window is skipped by the null-list rule (modes 6 and 7; mode 4 has no such test), the callback (payment + pop + resume) still runs immediately.
- `notes/mission_selection.md` / `FORMATS.md`: no debrief hotspot exists; `debrief*` commands appear at 12 sites: six `debriefwithsummary:` (BPMission2, 5, 13, 15B, GMMission3, LMission1) and six `debrief:` lines (MissionSZWindow, MissionAM1Window, MissionWE45Window x2, SZMission5, bare `debrief:` of ENMission1).

### roster book

- `notes/builtin_widgets.md` §1: tab-label offset is (+4,+2) released / (+3,+3) pressed (not (2,4)); click cues: press `B4.WAV`, release inside `B3.WAV` ("3 on press, 4 on release" is wrong).
- `builtin_widgets.md` §2.1: caravan open starts on regiment 0 with Information; the HireOnly marching list starts empty; `HireOnlyArmyBook` is also reached from `CaravanContinueMission`, `CaravanAfterEncounter*` and `InfoCaravanSZA/SZB`.
- `builtin_widgets.md` §2.2: cost line order is (retainer, price); regiment name is a `FancyLetters` blackletter block (slot 5) above the bottom lines with a bottom-anchored picture; headings are left-aligned; the description has no drop cap; status line on both pages; right-page state colour (grey/black/red); hero test uses `s_orgsize`; Information leader column has no "Troops" heading; all y offsets are exact (no longer 🟡).
- `builtin_widgets.md` §2.3: Abort also leaves taken reinforcements deducted; `MARCH.MRC` is merged, not rewritten; Done writes only when dirty (dirty is recomputed only at hire/fire/Take).
- `builtin_widgets.md` §2.4: Take label is black; +1/-1 do not refresh the right page; window origin/size/ids confirmed.
- Leader box (`glue_portraits.md`): frame 0 of BACKALL is certain; the crop table is verified.

### troop window

- `notes/troop_selection.md` §2 and `notes/builtin_widgets.md` §1: button label offset (4,3)/(0,3) and (2,4) are wrong; right is (+4,+2) released / (+3,+3) pressed. Click cues: press `B4.WAV`, release inside `B3.WAV`.
- `troop_selection.md` §4.4: Done enable rule on P0 is "selected count != 0" only; affordability is checked when the click is handled (silently ignored).
- `troop_selection.md` §3.1/§3.2: hint lines are pure blue (0,0,255); total cost includes retainers of hired excluded/destroyed rows; the name colour of an excluded but hired regiment stays black.
- `troop_selection.md` §7: the P5 coffers line shows coffers without prepaid; spacing is 2 x H4 then 2H; Done unwinds to MainMenu (already in `builtin_widgets.md` §4.3).
- `troop_selection.md` §1.2: mode 1 buttons are all enabled (the enable routine is empty). §5.2: buttons are ignored during a P1 drag; hit zone and scroll zones as §11.5.4; badge number offset (+15,+10).
- `troop_selection.md` §1.1: Accept also stops and discards the map's tune and applies to panel type 5.

### control panel

- `notes/mission_selection.md` §9.4 "label is drawn in the `settextcolor` of the `[ANIM]` block": wrong, it is always black. "Pressed/hover states": only a pressed state exists (no hover art). "Disabled buttons use a grey": drawn only if disabled, and nothing ever disables them.
- `mission_selection.md` §9.4: "Pressed = `FRAMEBUTTONDN`" is fine; add: id = 0x100 + slot, 119x20 at x + 9, no caption (no shortcuts), shared cue subclass (B4.WAV on press, B3.WAV on release inside), text centred without offset.
- `notes/builtin_widgets.md`/`context_builtins` §4.2: add that DRAIN comes in two kinds (Caravan/Options never resume the script; the others do, which may run the script forward), that Attack! (panel 4) and Accept 6/7/10 do not unpause, and that Caravan/Options leave the pause flag set.
- `notes/briefing_dialogue.md` §3.6 item 6 ("the briefing script is not resumed" on Accept): the drain with k = 1 resumes the interpreter as text finishes (🟡).
- `whshr/frontend/mission_map_view.py`: the grey-out rule for buttons without a selection is not in the original (see §12.6 item 2).
- Click-cue statement anywhere reading "3 on press, 4 on release" is wrong: press = B4.WAV, release inside = B3.WAV.

### context builtins

- `notes/mission_selection.md` §8.1, `PopAndResume`: "pop and discard two frames" is wrong. The first pop discards the launcher's WINDOW frame; the
  **second frame is restored** (script frame, windows, palette, caller) and the script is resumed unconditionally.
- `notes/mission_selection.md` §8.1, `AbortGame`: "Yes pops one frame and runs a final step that presumably abandons the campaign" -> Yes pops **repeatedly**
  until a WINDOW frame whose caller starts with `MainMenu` is found (RUN frames are cleaned up and dropped) and re-opens the main menu; nothing is deleted or reset.
- `notes/mission_selection.md` §8.1, overflow/underflow: "logged and ignored" is true, but there are four stacks with limits 16/16/8/8, and a built-in that has
  already cleaned up leaves a blank screen.
- `notes/mission_selection.md` §8.1, `UnwindMission`: the frame test is "a slot with a non-empty mission list"; a `replacescript` skips the copy.
- `notes/mission_selection.md` §8.1, `OptionsDialogDone` "then as `PopContext`": the remembered-tune restart happens only when not paused, with no re-pause.
  Also add: destroying a window stops its `[MIDI]` tune, creating one starts it; `PopContext` restarts the remembered tune before the restore.
- `notes/glue_interpreter.md` §7.1/§7.2: the pseudo-code omits the (name, mode) caller stack's 8-deep limit and the independent counters (context 16, frames 16,
  window states 8, callers 8); a kind other than 0x13/0x0C on pop is "corrupt" and leaves the depth unchanged; the built-ins' first pop is `show = 0`.
- `notes/activity_results.md` §6 table and §6.3: `AbortGame` Yes does **not** clear the four stacks (that is `endgame`/quit-battle); it pops down to the `MainMenu`
  frame. `NullWnd` is unreachable in the full game.
- `notes/builtin_widgets.md` §4.1 (engine paragraph) and `notes/glue_engine_integration.md` (GEI7h): the AbortGame message box text is **`BRTXT 308`**, not
  `GMTXT 36070` (the in-battle quit prompt); `whshr/glue_scene.py` `_confirm_abort_game` and the `whshr/confirm_scene.py` docstring cite the wrong id.
- `notes/glue_keywords.md` (`playmidi:` row): "play once" -> loops until replaced/stopped (repeat count 0), as `notes/briefing_dialogue.md` already says.
- `notes/campaign.md` §2.4: "removes every unit that is not hired" -> clears the unit's presence flag and rewrites `ARMY.MRC` after reloading it (13.3.4).
- `notes/briefing_dialogue.md` §2: "the caravan's `scribe` tune carries over" is contradicted (a window's tune stops on destroy); unresolved, see 13.10.
- Working-table inventory: `ArmyBook` has 3 definitions (not 5), `HireOnlyArmyBook` is shown by 7 windows, `EncyclopediaBook` 3, `MagicBook` 2;
  `PopContext` also has the `OptionWindow` Cancel; `NullWnd` 0. `CaravanDietrich` is unreferenced by any script or the executable.

### dietrich speech

- `glue_keywords.md` (`set:clickres`): `res:DietrichSpeech` is on **15** hotspots, 14 carry `clickres` (`CaravanDietrich` does not). Add: routing is by NAME, the two overlay animations, the text-state side effects (colour red, left, 2 lines), and "second click ignored".
- `glue_interpreter.md` (~line 374, "a hotspot that has a `clickres` line"): routing is by `res:` name, not by `clickres`.
- `native-windows.md` (DietrichSpeech "deliberately not researched"): now researched, see §14.
- `native-windows.md` / `context_builtins.md` §3.2 ("`DietrichSpeech` and its twin"): the twin is **`DietrichRead`**, used by no shipped script. Also confirm there that the click-speech table runs before the busy gate and that a click-speech hotspot never pushes a frame.
- `briefing_dialogue.md` §3.1 "caravan speech resets it to 2": it also sets text colour red and left alignment.
- `STATUS.md`: DietrichSpeech researched; open item 3 settled (`CaravanDietrich` is referenced by no script or string).
