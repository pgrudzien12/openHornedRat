# Built-in widgets: roster books, reinforcements, Magic/Encyclopedia books, Load/Save, Options, and the marching-order hand-off

Behavioral specification of the campaign screens that are **not** described by ordinary `WND.DLL` window data: they are native
windows of `WHSHR.EXE` opened through the built-in `res:` names (`notes/mission_selection.md` §8.1) or by the troop-selection
screen. It extends `notes/troop_selection.md` (§8 roster book, §5.3 selection done, §7 bankruptcy) and answers the open items of
`ROADMAP.md` for these widgets. Marks: ✅ read from the executable (and cross-checked against shipped data where possible),
🟡 read from code but not observed running / inferred in part, ⬜ open.

Sources: the observed behaviour of the front end (`WHSHR.EXE`) and the battle loader (`GAMEF.DLL`, for §6), the option table and
registry settings of both, and the shipped `WND.DLL` scripts, `.BTS` files and the campaign files in `SAVE/`. Nothing in this note names
original functions or addresses. All numbers are pixels on the 640×480 screen
unless stated.

## 1. Shared conventions of the built-in windows ✅

- Every built-in window here (`ArmyRecordsWindow`, `MagicBookWindow`, `EncyclopediaWindow`, `TroopWindow`) is a 640×480 child of
  the main window at (0, 0), sword or hand cursor, with the whole picture drawn into an off-screen 8-bit bitmap that is then blitted
  (the colours come from the *current application palette*, never from the bitmap's own colour table: `notes/fonts_glue.md`).
- **Bottom button strip.** Owner-drawn buttons 84×32 at **y = 448**. The button id selects the art (`…ATabUp/Dn0`) and is shared by all
  windows:

  | Id | Art | Used as |
  |---|---|---|
  | `0x100` | `RedATab` | Next (BRTXT 300) at x = 530 |
  | `0x101` | `BlueATab` | Back (BRTXT 301) at x = 440 |
  | `0x102` | `GreenATab` | Done (BRTXT 304) at x = 350 (x = 325 in the troop window) |
  | `0x103` | `BrownATab` | Abort (troop window, x = 225) |
  | `0x104` | `BlueBTab` | hidden "previous" alias of Back in the roster book (PageUp) |
  | `0x105` | `PurpleATab` | Stat/Info toggle (roster book, x = 14) |
  | `0x106` | `VioletATab` | Hire/Fire (roster book, x = 104) |
  | `0x107` | `BrownBTab` | Abort (roster book, x = 194) |
  | `0x108` | `VioletATab` | Spells (Magic book, x = 14) |
  | `0x109` | `GreenATab` | Items (Magic book, x = 104) |
  | `0x201` | `reinfButton` | reinforcements "take" (label offset 0, 0) |
  | `0x202` / `0x203` | `reinfArrowUp` / `reinfArrowDown` | reinforcement +1 / -1 |

  Pressed art is the `…Dn0` twin; label offset (2, 4) released, (3, 3) pressed for the tab buttons. Every button plays speech cue
  `3` on press and `4` on release (the same `upsfx`/`downsfx` of glue hotspots).
- **Leaving.** A built-in that was opened by a glue `res:` closes with `SetPalette(MAP)` + `PopContext(show)` (§7.2 of
  `notes/glue_interpreter.md`); if the popped context is of kind `WINDOW` the *caller* window (recorded when the built-in was opened)
  is re-run by name. A built-in opened from another built-in (the roster book from troop selection) instead re-shows its parent window
  and does not touch the context stack.
- **Text sources.** Two string tables: *BRTXT* (button labels, stat names, armour/weapon names, dialog captions) and *BKTXT*
  (book text). Regiment descriptions and spell/item descriptions are RCDATA resources of `BKTXT.DLL`, keyed by the name tables
  described below.

## 2. Roster book ("Army Records") ✅

### 2.1 Variants

One window serves four entries. The two open parameters are *hire-capable* (has Hire/Fire and Abort) and *hire-only / money*
(hiring charges coffers).

| Entry | Opened by | Hire-capable | Money | Unit file | Return |
|---|---|---|---|---|---|
| `ArmyBook` | caravan hotspots (`CaravanCommon4`, `CaravanMs`, `CaravanEcts`, `CaravanDietrich`, `Start`) | yes | **no** | `ARMY.MRC` | caller window by name |
| `HireOnlyArmyBook` | recruit caravans (`CaravanCommon5`) | yes | **yes** | `ARMY.MRC` | caller window by name |
| roster book from troop selection, open modes 0/1 (Ctrl+click on a row) | troop window | yes | no | the in-memory company | parent (troop window) |
| roster book from troop selection, open mode 3 (debrief troop page) | troop window | **no** (view only) | no | the in-memory company | parent |

Open sequence (caravan entries): free any previous company, for *HireOnly* clear the selection list, load `ARMY.MRC`, set the
initial hired/selected flags of forced regiments exactly as troop selection does (`notes/troop_selection.md` §4.1, so a forced
regiment appears already hired), then open on regiment 0. The screen palette is glue palette 9 (`BK2`); music is unchanged.
A snapshot of every regiment's `hired` flag is taken at open (used by Abort and by the "hired this visit" rule).

### 2.2 Layout (both pages share the left page)

The background is the bitmap `ArmyBook` (640×480). One regiment per double page, in file order. The text area of each page is 240
wide: the left page spans x = 50..290, the right page x = 350..590. Text uses glue font slot 2 (`ForHireStamp` art excepted).

**Left page.** Bottom-anchored lines centred in x = 50..290, with `h` the text height:

| Element | Position | Content |
|---|---|---|
| cost line | y = 410 - h | `BKTXT 501` "Cost a / b gold crowns": a = price per model x current models, b = 10 % retainer of a. In the money variant, for a regiment that was **not** hired when the book opened: `BKTXT 509` mission fee only |
| experience | y = 410 - 2h | `BKTXT 500` |
| regiment name | above that | unit name (`<` shown as a space) |
| regiment picture | centred above the name, 4 px gap | bitmap `<Name>Pic`, chosen from a 38-entry table indexed by `whoami` |
| `ForHireStamp` | (50, 35) | 98×61 stamp when the regiment is **not hired** |
| status line | x = 350..590, y = 385 | skull icon (`Skull<level>` from the experience level) + `BKTXT 502` "Active a Wounded b", icon and text centred as a unit, vertically centred on the icon |

**Right page: Information (default page).** Heading `BKTXT 504` at (350, 39). Below it, two lines (2 x h) down: the regiment portrait
72×104 at (350, y); then y += 106: line `BKTXT 408` (armour/weapon heading), armour name `BRTXT 100 + armour class`, weapon name
`BRTXT 200 + weapon class`. If the regiment has a leader (and is not a single-model hero), the leader column is repeated at x = 470:
portrait 72×104, leader name, leader armour, leader weapon. The regiment description (RCDATA keyed by `whoami`, first letter drawn
from `FancyLetters`) is word-wrapped into a 240-wide rectangle starting one line below the last stat line, bottom at about y = 410.
**Right page: Statistics** (toggled by the button at x = 14, label `BRTXT 321` "Stat" on the Information page and `322` "Info" on the
Statistics page): heading `BKTXT 503` at (350, 39); portrait 72×104 at (350, y); nine rows M, WS, BS, S, T, W, I, A, Ld with the
row height of the font: name `BRTXT 700 + 2i` at x = 428, second label `BRTXT 701 + 2i` at x = 538, value (the nine stat bytes of the unit)
at x = 573. For a regiment with a leader a second block (leader name, portrait, the leader's nine stat bytes) follows at the
same x offsets below. A single-model regiment with a leader (a hero/wizard) shows only the leader block. 🟡 all y offsets are
from code, not measured on a screen.

### 2.3 Input, refresh and state ✅

- **Navigation.** Next (`0x100`, x = 530) and Back (`0x101`, x = 440) change regiment; PageDown/PageUp do the same when the button is
  enabled; End/Home jump to the last/first regiment. Next is enabled while `index < count-1`, Back while `index > 0`.
- **Stat/Info** toggles the right page and its own label.
- **Hire/Fire** (hire-capable only; label "Hire" when the regiment is not hired, "Fire" when it is):
  - enabled only if the roster's *for hire* flag of that `whoami` is set; disabled for an already-hired regiment whose flag is
    clear;
  - **money variant:** enabled only if the regiment was **not** hired at open; it can then be hired if `coffers >= fee`, and a
    regiment hired earlier *in this visit* can be un-hired (refund). A regiment already hired when the book opened is locked;
  - toggling flips `hired`. **Hire** also selects the regiment (appended to the selection list, if `selected < limit`);
    **Fire** removes it from the list. In the money variant Hire subtracts the fee from the coffers and Fire adds it back
    immediately (the coffers change on every click, not on Done).
- **Done** (`0x102`): if anything changed (a `hired` flag differs from the snapshot, or any reinforcements were taken) the company is
  written to `ARMY.MRC`; in the **money variant** the marching orders are rewritten too (`MARCH.MRC` from the selection list, in list
  order) and reloaded. Then close.
- **Abort** (`0x107`, hire-capable only; enabled only when something changed): restores every `hired` flag from the snapshot and
  closes without writing. ✅ **Quirk:** in the money variant the coffers were already changed by each click and are **not** restored, so
  hiring and then aborting keeps the money spent while un-hiring the regiment (original behaviour; 🟡 not observed running).
- The window has no keyboard focus handling other than the four keys above; Esc/Enter do nothing.
- Closing re-shows the parent window if it is hidden (troop selection). The palette is **not** switched back on that path, so the
  troop window keeps palette 9 (`BK2`) after the book closes 🟡 (see the palette notes; the glue-path exit resets palette 2).

**Leader portrait box ✅** (both pages: Information at x = 470, Statistics at x = 350, same routine, destination 72×104):
1. Background: frame 0 of `BACKALL` (sprite-table index 123, a hills landscape; the same for every regiment), cropped with the
   window of `notes/glue_portraits.md` §1.3. 🟡 that frame 0 is really the one shown (inferred from load order; confirm in the original).
2. Portrait: frame 0 of the leader's portrait set, cropped with the same window and drawn over the background.
3. No scaling, border or frame. Raw palette indices are copied (BK2 palette 9), index 0 is transparent, no colour map.
4. Draw order: background, portrait (or banner when the portrait set is not in the resident list, §1.3), then the name.
5. Information page: drawn whenever the regiment has a leader; a single-model leader is *not* excluded (🟡 confirm in the original).
Implemented in `whshr/frontend/army_records_view.py` (`_leader_box`/`_draw_crop`): crops, does not scale. No other window uses this routine.

### 2.4 Reinforcement sub-window (answers "layout and interaction") ✅

Shown **automatically** on top of the roster book whenever the regiment on screen has offered reinforcements and the book is in a
hire-capable variant (not in the view-only debrief variant). It is re-evaluated every time the page changes: it is closed first and
re-opened if the regiment still has an offer.

| Element | Geometry |
|---|---|
| window | 144×134, centred in the book: origin (248, 173); background bitmap `reinfScroll` |
| heading | `BKTXT 505` "Reinforcements", centred in the 144 width at y = 16, black, font slot 2 |
| line 1 | `BKTXT 507` "Available : n" with `n = offered - taken`, centred, y = 46 |
| line 2 | `BKTXT 508` "Take : n" with `n = taken`, centred, y = 46 + h + 2 |
| button `0x201` | 116×20 at (12, 110), label `BRTXT 319` ("Hire"), art `reinfButton` |
| button `0x202` (+1) | 11×13 at (29, 85), art `reinfArrowUp` |
| button `0x203` (-1) | 11×13 at (104, 85), art `reinfArrowDown` |

State per regiment: `offered` = `min(roster reinforcements of that whoami, orgsize - models)`, where *models* is the regiment's
present models plus the wounded/away count (computed for every regiment when the book opens); `taken` starts at 0 (a regiment
that was already reopened keeps its `taken`).

- **+1**: if `taken < offered`: `taken += 1`, the regiment's current size `+= 1` **at once** (so the cost line grows immediately), repaint.
- **-1**: if `taken > 0`: `taken -= 1`, size `-= 1`, repaint.
- **Take** (`0x201`): the offer is consumed: `offered := 0`, the roster's reinforcements `-= taken` (the untaken rest stays in the roster
  for a later visit), the window closes, and if anything was taken the book page is repainted. There is no cancel: paging away
  closes the window without change and `taken` survives until the offer is answered.

Where the reinforcement figures come from and how unused ones are discarded when the caravan is left: `notes/campaign.md` §2.4.
The three sub-window buttons play the same click cues as the other buttons.

## 3. Magic book and Encyclopedia ✅ (structure) / 🟡 (pixel offsets of the text engine)

Both use the `EncyBook` background (640×480, palette 1 = `BOOK`), the same button strip, and the same page model: an entry has a
picture on the left page and a description on the right page that continues over as many pages as the text needs.

| | Magic book | Encyclopedia |
|---|---|---|
| Opened by | `MagicBook` hotspots (caravan), `res:` built-in with `ARMY.MRC` | `EncyclopediaBook` hotspots (caravan, `Start`) |
| Buttons | Back `0x101` (440), Next `0x100` (530), Done `0x102` (350), **Spells** `0x108` (14, `BRTXT 334`), **Items** `0x109` (104, `BRTXT 335`) | Back, Next, Done |
| Books | two: index 0 = spells, index 1 = items; each has its own current entry and page. A button is enabled only while the *other* book is showing and has an entry | one book |
| Entry list | an entry is shown when it is *known*: spells and items carried by any regiment of `ARMY.MRC`, recomputed at **every** open (`testbook` option: all) | entry flags set by glue `enablebook:0=<n>` (`testbook`: all) |
| First page | first known entry of book 0, else book 1 (buttons only created if a book has an entry) | first enabled entry |
| Left page | picture from the entry's bitmap table centred in x = 50..290; if it fits in 250×125 it sits at the bottom (y = 285 - h) with the title (`BKTXT 200 + 50·book + entry`) above, otherwise centred vertically in y = 35..375 | picture (`…Pic`, e.g. the orc picture), same centring rule |
| Right page | description (RCDATA of `BKTXT.DLL`) in the rectangle x = 350, y = 35, 240 × 375; the first letter of an entry's first page is drawn as a large `FancyLetters` glyph and the text wraps around it; text continues on the next page | same |
| Next / Back | next page of the text; at the last page, the next *known* entry (skipping unknown ones); Back is the reverse; at the very first/last page the button is disabled | same |
| Done | closes (§1 "Leaving") | same |

Notes: ✅ glue `enablebook:1=` and `enablebook:2=` flags are **overwritten** each time the Magic book opens (it recomputes the item/spell
flags from the army), so only `enablebook:0=` (encyclopedia) is effective in shipped flows; 🟡 which entries the two book tables hold
(item and spell name tables) is not extracted here.

## 4. Troop-selection exits and edge modes

### 4.1 Abort destination ✅

Abort exists in open mode 0 only (id `0x103`, art `BrownATab`). Sequence: if anything is selected, confirm (`BRTXT 308`, question box,
title "Warhammer"; No = stay); then destroy the window, free the company, set palette 2 and `PopContext(show)`. The **context that Accept
pushed** is popped, so the destination is whatever was parked when Accept was pressed:

- from the **map's Accept**: the flow script was current with kind `RUN`, so the pushed context holds the script frame and the whole
  window set; Abort restores the **map window with its mission list and selected row**, and the script stays parked in
  `waitforrelease` (its `parked` flag is still 1, so nothing resumes it). ✅
- from a **briefing's Accept**: the briefing was opened as a `WINDOW`-kind resource, so the pushed context holds only the caller
  name; Abort re-opens the **briefing window by name** (a fresh instance, starting from its first command). ✅ (code; matches the
  🟡 in `notes/troop_selection.md` §1.1)

Nothing is charged by Abort. Hires made in the roster book were already written to `ARMY.MRC` (§2.3) and stay.

### 4.2 Open modes ✅

Callers pass mode 0 (Accept), 2 (battle end with debrief), 6 (battle end without debrief), 4 (glue `debrief:`), 7 (glue
`debriefwithsummary:`); mode 5 is set internally (below). Modes **1 and 3 are never requested** by any caller (the page states P1 and
P3 exist as *pages* reached by paging, but no open path starts on them), so the "P1 alone" open mode of `notes/troop_selection.md`
§1.2 is dead code. On P0 the "Next" branch that would jump from the last page to P1 is also unreachable (Next is disabled on the
last page; only Done leads to P1).

### 4.3 Bankruptcy (mode 5) ✅

Evaluated when the screen is opened in mode 0: **if `coffers + prepaid < sum of the fees of the forced regiments that are selected`** the mode
becomes 5. Forced regiments: `whoami = 2` (the Grudgebringer cavalry) always, plus the mission's `forceunits` list (up to 8). Page P5 shows
`BKTXT 601` (heading), `602` with the coffers and `603` with the required amount; only **Done** exists. Done destroys the window,
blanks the backdrop and **unwinds the whole context stack until the main-menu window is the caller**, i.e. the player lands on the
**main menu**. The campaign files are not deleted and the slot-5 autosave is untouched, so the player can load it.

## 5. Does the marching order change the battle? ✅ yes

Chain: Done on P1 writes `MARCH.MRC` with the selected regiments **in list order** (`notes/troop_selection.md` §5.3). The battle loader
reads that file after the `.BTS` and parses its `[UNITS]` block in file order. For every unit of the player faction (side byte
without the high three bits) the loader, at the unit's `endunit`, **overrides the unit's start x, y and direction from a start node**:

```
N      = number of active nodes with the ns_startpos flag, in .BTS node order      # NS_END is ignored (its bit is cleared at load)
count  = the file's  set:count  (number of units in the MRC block)
for the i-th unit of the block (0-based, file order):
    candidate = the (N - count)-th not-yet-used ns_startpos node       # 0-based among the unused ones
    if candidate exists: unit.x, unit.y, unit.dir = candidate.x, candidate.y, candidate.dir; mark candidate used
    (if N - count < 0 there is no candidate for any unit: the file's own x, y, dir stay)
```

Consequences:

- Unit *i* of the marching order takes start node number `N - count + i`: the **last `count` start nodes** of the chain, in order. The
  first regiment listed gets the earliest of them. This is the answer to the old question "`NS_END` count = player unit count": the
  authors flagged the last start nodes with `NS_END` for readability; the engine only uses `ns_startpos`.
- The order therefore decides **which regiment stands at which start position**, in every battle (with or without `DeployTroops:`).
  In `DeployTroops:` battles the player then drags the units inside the deployment boundary (boundary flag `DEPLOYMENT`); the drag
  starts from these node positions. Without `DeployTroops:` the positions stay as assigned.
- If the marching order is longer than the number of start nodes (`count > N`) **no** regiment is placed from nodes and all keep the
  coordinates stored in their army-file record (which are the campaign's fixed per-regiment starting coordinates, identical across
  battles: e.g. (1097, 645) and (1112, 585) for the two starting Grudgebringer regiments). Shipped battles have 4-29 start nodes
  (distribution over 54 `.BTS`: 4 x1, 5 x6, 8 x1, 9 x2, 10 x1, 11 x6, 12 x7, 13 x1, 15 x3, ...), the default selection limit is 13
  and can reach 38, so this edge exists in principle 🟡 (not observed).
- Nothing else in the loader depends on the order except the unit-table index (tick order). ⬜ whether script-side unit lookups use
  that index for player units (behaviour scripts address units by role and `whoami` in the material read so far).

## 6. Load and Save UI ✅

One native dialog, opened from a glue window through the built-in windows `LoadSaveWindow` (**Save**, `[LOADANDSAVEGAME] set:flag=0`) and
`LoadSaveWindow2` (**Load**, `flag=1`). Correction of `notes/glue_keywords.md` §3.10: **flag 1 = load, 0 = save**.

| Where | Entry |
|---|---|
| Main menu (`MainMenu`, `MainMenuEcts`, `MainMenuMs`) | Load (`LoadSaveWindow2`) only |
| Caravans (`CaravanCommon2`, `CaravanMs`, `CaravanEcts`, `CaravanDietrich`) | Save (`LoadSaveWindow`) only |

So a game can be loaded only from the main menu and saved only from a caravan (plus the automatic saves of `autosave:`).

**Layout.** The glue window (640×480, palette 2, background `Map`) supplies only the backdrop; the dialog is a child window of size
252 × H at x = 194, y = (480 - H) / 2 with H = **212 (save)** or **254 (load)**, background bitmap `LoadSaveWindow` / `LoadSaveWindow2`
(252 × H). Inside it:

| Element | Geometry |
|---|---|
| slot buttons 0-4 | 232×36 at x = 8, y = 8 + 36·i; label = the save's stored description, or the "empty" text |
| slot 5 ("Last Game", **load only**) | 232×36 at x = 8, y = 8 + 5·36 + 6 = 194 |
| OK | 116×20 at (8, 188) save / (8, 230) load |
| Cancel | 116×20 at (124, same y) |

**Interaction.** Clicking a slot selects it (highlight art `LoadSaveBtn<n>Up/Dn`), one at a time; there is no double-click action. OK is
disabled until a slot is selected; on an **empty** slot OK is enabled only in Save mode (Load needs an existing file). Cancel
(`0x301`) closes: `CleanUp` + `PopContext(show)`, then the caller re-runs if the popped kind is `WINDOW`, else nothing (`RUN` contexts are not resumed by
Cancel).

**Save (OK).** Prompts `Enter Save Description` (a modal one-line edit box at (172, 214), **25 characters max**, initial text = the slot's
current description, or a default caption chosen for the current mission). On OK: write back the four working files
(`ARMY.MRC`, `MARCH.MRC`, `PLAY.MRC`, `debrief.dbf`) and write `SAVE/savegame.<slot>` (`notes/campaign.md` §4). A write failure shows an
error box but the dialog still closes. Cancelling the edit box returns to the dialog.
**Load (OK).** Blocked (does nothing) when a demo option (`ectsdemo`, `msdemo`) is set. Otherwise discard the cached working files, read the
save (all of §4 of `notes/campaign.md`: header, coffers, glue status and mask, the four stack depths and the saved script frames,
the embedded `ARMY/PLAY/MARCH/debrief`), which **replaces the interpreter state completely**, including the saved context stack. The
dialog then closes with `CleanUp` + `PopContext(show)`: the popped context is the **top of the loaded stack**, so a caravan save resumes on
the caravan window (kind `WINDOW`: the caller is re-run by name) and an `autosave:` save resumes the parked flow/mission script at the line
after `autosave:` (kind `RUN`: window set restored and the script resumed). On failure an error box appears and the game is reset to the
main menu.
Slots: 0-4 are player slots, **slot 5 is the automatic save** written by `autosave:` (and by `testmission:`) with description "Last Game";
it is listed in Load only, so the player can never overwrite it by hand.

**Engine implementation (deviations).** A failed load or save keeps the dialog open with a message instead of resetting to the
main menu (load) or closing (save); the save file is the engine's own JSON, not `savegame.N` (`notes/glue_engine_integration.md`
GEI14). The key events are: click a slot to select it, OK or Enter to confirm, Cancel or Esc to close (in the description
prompt, Cancel returns to the dialog); typing and Backspace edit the description. The main menu's Load is also bound to `L`.

## 7. Options dialog ✅

Opened by the `OptionsDialog` built-in (caravan `CaravanCommon1`, `MainMenu*`, and panel 9's Options button). It opens the glue window
`OptionWindow` (backdrop `MoreOptionScreen`, palette index -1 = the picture's own palette) with an **initialisation step** that
reads the stored options and sets the state of the eight multi-state hotspots (`linkid` 36000...36060, `count` 3/2/2/2/2/2/2/3), each
labelled by the `linked:` texts (`GMTXT` 36000 + state). **Done** (`OptionsDialogDone`) applies and saves, then behaves like
`PopContext` (the remembered tune restarts); the second button is plain `PopContext` = Cancel (nothing applied, nothing saved).

**Storage.** A registry string value `options` under `SOFTWARE\Mindscape\WarhammerFB` holding eight comma-separated integers
`v1,...,v8`. The battle module reads the same value (with built-in defaults `2,1,1,1,1,1,1,1` if it is missing or has fewer than eight
numbers) and also writes it from its own in-battle options screen.

| Field | Link id (dialog line) | Stored value from hotspot state `s` | Meaning in the battle module |
|---|---|---|---|
| v1 | 36000 shading quality | `s + 1` (1..3) | shading level; 0 is raised to 1; level 3 (Phong) is lowered to 2 unless the battle is `bf025` |
| v2 | 36030 animate scenery | `1` if `s == 0` (on) else 0 | scenery animation |
| v3 | 36040 animate textures | `1` if `s == 0` else 0 | texture animation |
| v4 | 36010 texture mapping | `1` if `s == 0` (on) else 0 | texturing on/off |
| v5 | 36015 perspective correction | `1` if `s == 0` else 0 | perspective-correct mapping |
| v6 | 36020 pixel resolution | `1` if `s != 0` (full) else `2` (half) | render resolution divisor |
| v7 | 36050 sound effects | `1` if `s == 0` (on) else 0 | sound on/off (also sets `nosound` and `nospeech` at run time) |
| v8 | 36060 music | `s` (0 off, 1 FM MIDI, 2 General MIDI) | music mode |

Loading inverts these (each state is clamped to the hotspot's `count - 1`). Run-time effect of Done, and of the start-up read of the
stored value: sound on clears the `nosound`/`nospeech` switches, off sets both; music 0 sets `nomusic` and switches MIDI off; music 1
clears `nomusic`, sets `fmmidi`, clears `genmidi`, MIDI on, FM; music 2 clears `nomusic`, `fmmidi`, sets `genmidi`, MIDI on, not FM.
The command-line switches share one table of 30 flags (`nobattle`, `smallwnd`, `query`, `nosound`, `ectsdemo`, `msdemo`, `notimeout`,
`integerlibs`, `noanims`, `nospeech`, `xxx`, `noppt`, `manyxof`, `noenablequery`, `splitmesh`, `nomusic`, `stubwail`, `awemidi`, `genmidi`,
`fmmidi`, `verbose`, `novdu`, `dead`, `nocache`, `testbook`, `testarmy`, `cash`, `cost`, `maxselect`, `unrealquit`), which the battle
module receives by pointer.

Quirks 🟡: (a) with no stored value the dialog shows state 0 of every line (unlit flat shading, ..., half-pixel, music off) although
the battle module runs the built-in defaults (flat shading, full pixel, FM music) until the first Done; (b) the hotspot `count` of
36000 is 3, so state 3 "Phong" is unreachable from this dialog although the string exists.
**Note for `notes/game_rules.md` / debrief work:** the option `unrealquit` (30) decides what a battle that ends without a player win does: with
it **unset**, a result that is not a player victory goes to the end screen and the main menu instead of the debrief (resolves the open
item "battle-failure exit" of `notes/glue_interpreter.md` §8.1: the condition is *the battle module's result flag is 0* and `unrealquit` is 0).

## 8. Open items

1. ⬜ **Palette on return from the roster book to the troop window** (stays on palette 9 on that path): confirm which palette the original
   shows, for the palette-selection rule (`notes/fonts_glue.md` §3).
2. ⬜ **Item and spell tables** of the Magic book (which pictures and texts belong to which entry) and the encyclopedia entry list; only
   the paging and layout rules are specified.
3. 🟡 y offsets of the roster-book right page and the Magic/Encyclopedia text engine (drop-cap wrapping) are read from code but not measured on a
   screen; the left-page anchors and the reinforcement window are exact.
4. 🟡 Whether the loaded-stack pop after Load ever meets an empty stack (a save made with no glue context): the pop is then a logged
   no-op and nothing is re-run.
5. ⬜ Script-side effect of the unit-table order of player units (§5) beyond start-node assignment.
6. ⬜ The default save description text chosen for the edit box (a mission-dependent BRTXT id).
