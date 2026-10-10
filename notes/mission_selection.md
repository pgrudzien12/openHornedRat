# Mission selection flow (caravan → map → briefing → battle → caravan)

Behavioral spec of what happens after the player clicks the "select mission" hotspot in the caravan,
which parts are data (`WND.DLL` glue scripts, `BRTXT.DLL`) and which are built into `WHSHR.EXE`, and which
graphics each screen uses. Availability rules (`depend`, `inactivedepend`, scroll count) are in
`notes/campaign.md` §7 and are not repeated here. Status: ✅ from script data or verified static analysis of the
front end, 🟡 inferred (read from code, not observed running), ⬜ unknown, ⚠ evidence conflicts.

One authoritative place per fact: portrait `index` table, `bkindex`, mouth/blink animation -> `notes/glue_portraits.md`;
tent, animated/cell-set bitmap naming -> `notes/campaign_tent.md`; music, dialogue text, pacing, speech -> `notes/briefing_dialogue.md`;
troop selection screen -> `notes/troop_selection.md`; money and mission availability -> `notes/campaign.md`. This note owns the
map/mission-list input, the control-panel actions, the glue context stack (§8.1) and how screens are entered and left.

## 1. The screens are scripted windows on a stack ✅

The front end ("glue") is an interpreter of `WND.DLL` text scripts (`notes/pe_resources.md` §1.7). Every
screen is a window script; flow scripts (`[RUN]`) open windows, wait, and continue. There is no dedicated
"mission selection" state in the data: it is the **map window with a mission-list child window**.

| Step | Screen | Defined by |
|---|---|---|
| 1 | Caravan (`StartCaravan` first time, `CaravanAfterMission[WithRecruit]` after a battle, `CaravanSelectMission`, `CaravanContinueMission`, `CaravanAfterEncounter*`, `CaravanRecruit*AndResume`, `InfoCaravan*`) | data (window scripts) |
| 2 | Map window + mission list | flow script (`FlowScript*`) opens `MapWindow`, then `addobject:res=Mission…Window`, `autosave:`, `waitforrelease:` |
| 3 | Briefing | mission record's `res:` script (`BPBrief1` …): map variant, Dietrich and Commander portraits, dialogue |
| 4 | Troop selection | built-in window `TroopSelect` (set as `setdemodefault` at the end of the briefing) |
| 5 | Battle | mission script (`BPMission1` …): `encounterplaygamewithdebrief:<bf>` |
| 6 | Debrief, cutscene, back to caravan | end of the mission script: `addtroop`, `playmovie:A<n>`, `gocaravan:select` |

## 2. Caravan → map ✅

- The caravan hotspot (x 480, y 250, 160×110; hint `BRTXT 150`) has several forms; its `res:` is a built-in window (§8.1):
  - `StartCaravan`: `res:FlowScriptBP01` - starts the campaign (runs the first flow script);
  - `CaravanSelectMission` (opened from the map's Caravan button): `PopContext`;
  - after-mission and after-encounter caravans (with and without recruit) and most `InfoCaravan*`: `UnwindMission`;
  - `CaravanRecruit*AndResume` and `InfoCaravanENA/LA/SZA/SZB/WED`: `PopAndResume`;
  - `CaravanContinueMission` (hint 161 "continue mission"): `PopContextCheckResume`.
- The flow script is **parked**, not restarted: `waitforrelease:` returns only when the mission window
  releases it (chosen mission carries `set:releaseflag=1`, or nothing visible remains; `notes/campaign.md` §7.5).
- The caravan is entered by the built-in `gocaravan:<mode>` command. Modes seen in scripts: `select` (28×,
  end of mission scripts), `resume`, `recruit`, `recruitnospeech`, `start`, `info*` (`infoBMA`, `infobpc`, …).
  `select`/`resume` choose the `…WithRecruit` variant when there are reinforcements to take (and first copy
  `addunit` regiments from `PLAY.MRC` into `ARMY.MRC`; `notes/campaign.md` §2.4).

## 3. The map screen with the mission list ✅

- Background: bitmap `Map`, palette index 2 (`[POSITION] palindex=2`). Per-chapter variants
  (`MapWindowBP1`, `…SZ1`, `…RE3`, …) add `[TEXT]` town labels (font 2), the mission title (`BRTXT 6xx`, black,
  centred at 210,20) and `[INCLUDE]` objects: `BriefingTitleBMP` (`MapTitle` bitmap at 210,15) and
  `SMarkNN` crosses (`SmallCross` bitmap at the town).
- Sub-window `ScribeMWindow` (450,25, 144×240): `[ANIM] name:Dietrich`, `sequence=1`, `controlpanel=2`;
  the flow script forces `animseq=2` (stop talking). The briefing uses `ScribeWindow` (`controlpanel=1`).
- The campaign tent is **not** part of the mission-list map: only briefing scripts add `TentObject01`. Flow scripts just
  maintain the `tentpos` variable (0 at the start, 1 after the first mission window is dismissed) for those briefings, whose
  tent position comes from a table indexed by it and whose bitmap `Tent4` is the cell set `TENT3..0` (`notes/campaign_tent.md`).
- Trail dots: `Trail*`/`FlowTrail*` objects (`addanimobject`).
- The list: `MissionWindow` at `[MISSIONWINDOW] set:x/y` (always 30,15), one row per visible mission, bitmap
  `Scroll0` (selected) / `Scroll1`, label = `BRTXT` mission name + `" (initial, completion)"` payment.
  Not declared through `[TEXT]`/`set:font=`: the front end's built-in row painter selects glue font 2
  (`GlueCreateFont(2)`, i.e. `PCTEXT.FON`) with a constant argument before drawing every row's label —
  confirmed by static analysis (`notes/fonts_glue.md` §6), the same font number as the mission title and
  the control-panel button labels (§9.4 below).
- Mission window resources: 41 `MISSION*WINDOW`, at most 5 `[MISSION]` records each. Each record:
  `set:res=<BRTXT name id>`, `script:<orig .run name>`, `res:<briefing script>`, `setbattlescript:<bf>`,
  `setmissionscript:<script>`, `cash:type,initial,completion,rateA,rateB,letters`, optional `depend`,
  `inactivedepend`, `releaseflag`, `replacescript`, `excludeunits`, forced regiments.

## 4. Map and mission-list input, and the control-panel actions ✅ (static analysis) / 🟡 (runtime)

### 4.1 The mission list (`MissionWindow` child of the map)

| Input | Behaviour | Status |
|---|---|---|
| Left button down on a row | selects that row; ignored if the row is hidden, already selected, or its record names neither a battle nor a mission script | ✅ |
| Mouse move with the left button held | same as a press: drag-selects the row under the pointer | ✅ |
| Hover (no button) | nothing; there is no hover highlight | ✅ |
| Left button up | nothing | ✅ |
| Double-click | the window class enables double-clicks and its handler runs the **Brief** action for the current selection (same as the Brief button, §4.2) | ✅ code, ⚠ conflicts with the owner's observation, below |
| Keyboard (arrows, Enter, Space, Esc, ...) | none: the list has no key handler; the glue window's key handler only feeds a hidden cheat-code detector; the only other keyboard input is the application accelerator table (Ctrl+X = command 16, effect unknown ⬜; the test table also has F2 = command 14) | ✅ (no key advances or selects anything) |
| Empty list | no rows are painted, the window height is 0, clicks fall outside it; Brief and Accept do nothing when the window owns no records | ✅ |
| Selection wrap | not applicable (there is no keyboard selection) | ✅ |

All 64 shipped `[MISSION]` records (comments excluded) name a battle, so the "names a battle or mission script" rule never hides a real row; 7 records have no mission script (their battle is started directly, `notes/troop_selection.md` §5.3). ✅ (data)

A row is painted with `Scroll0` when selected and `Scroll1` otherwise, in record order, skipping hidden rows (`notes/campaign.md` §7.3).
The selected index is part of the saved window state, so returning to the map (Abort from a briefing, `PopContext`) shows the same
selection. ✅ (window state is restored as a block, §8.1)

**Double-click conflict ⚠.** Earlier text here said a click on the already-selected row runs Brief. That was wrong: a plain click
never does. The static finding is that a **double-click** runs Brief. The project owner reports from playing the original that
double-clicking a row has no effect beyond selecting it. The two disagree; the code path looks live (class registered with double-click
support, handler present, same routine as the panel's Brief button) but has not been observed running. Unresolved until a
runtime check; the engine should follow the owner's observation (double-click = plain selection) and keep the option easy to flip.

Arrow keys, Esc-to-caravan and any wrap-around selection in the engine are **extensions**, not original behaviour.

### 4.2 The control panel buttons (`controlpanel`, §9.4): what each slot does

Slot 0 is the lowest button (§9.4). "Drain text" = finish or fast-forward the window's pending dialogue text (the same routine used
when a click fast-forwards). "Stop audio" = stop the speech clip, the MIDI tune is discarded and (where noted) the remembered
tune name is cleared. "Push" = save the running script state plus all glue windows on the context stack (§8.1), then destroy the
windows. "Pause" = §5.

| `controlpanel` | Where used (§9.4) | Slot 0 | Slot 1 | Slot 2 | Slot 3 |
|---|---|---|---|---|---|
| 1 | briefing windows | **Abort**: unpause; stop audio; forget the tune name; end the running (briefing) script; destroy all glue windows; **pop** one context and restore it (the parked map with its mission list) | **Accept**: unpause; drain text; stop audio; forget the tune name; **push**; open troop selection for the current mission (`notes/troop_selection.md` §1.1) | **Pause / Resume** | - |
| 2 | map + mission list | **Caravan**: drain text; **push**; open `CaravanSelectMission` (its tune replaces the current one) | **Accept**: as panel 1 Accept | **Brief**: unpause; drain text; run Brief (below) | - |
| 3 | ambush windows | **Defend**: unpause; drain text; start the pending encounter battle (the one an `encounterplaygame*` command stored) 🟡 | - | - | - |
| 4 | encounter windows | **Evade**: unpause; drain text; resume the script | **Attack!**: drain text; set the script's true/false status flag to true 🟡; start the battle | - | - |
| 5 | (no window) | Abort as panel 1 | Accept as panel 1 | Report: no action | Brief as panel 2 |
| 6 | (no window opens it) | Abort as panel 1 | **Accept**: drain text; stop audio; forget the tune name; **push**; mark the current mission taken; run its mission script directly, or, if it has none but names a battle, start that battle; **no troop selection** | Pause / Resume | - |
| 7 | (no window opens it) | **Decline**: as Evade | Accept as panel 6 | Brief as panel 2 | - |
| 8 | Harkon, Azguz and Scribe encounter windows | **Attack!**: as Defend | - | - | - |
| 9 | mission-script windows and encounters | **Caravan**: unless paused, drain text and stop the speech; **push**; open `CaravanContinueMission` (the mission script's tune keeps playing until the caravan's own tune replaces it) | **Options**: unless paused, drain text and stop the speech; always stop and discard the tune (its name is kept, so closing the dialog restarts it); push; open the Options dialog | Pause / Resume | - |
| 10 | (no window uses it) | Caravan as panel 2 | Accept as panel 6 | Brief as panel 2 | - |

**Brief** (panel 2 slot 2, panel 5 slot 3, and the list double-click): find the window that owns the mission records, copy the
selected record into the current-mission struct (name, cash, forced regiments, briefing, battle, mission script) and open the record's
briefing window (`res:`, falling back to its `script:` name), pushing a context first (the push is skipped when the owning window has portrait entries of its own 🟡). The
briefing script therefore always starts from its first command; nothing remembers that it was seen. ✅

**Accept on the map does not need Brief first**: the record is copied into the current mission whenever the selection changes,
and Accept reads it from there (`notes/troop_selection.md` §1.1). ✅

### 4.3 Hotspots and other keys

- Hotspots (caravan, main menu) act on **button release** over the same hotspot that received the press. While the glue window
  still has pending dialogue text, a hotspot's `script:`/`res:` target is not run. ✅ (control flow) / 🟡 (not observed)
- **Enter, Esc, Space** do nothing on the map, briefing, caravan or troop windows. Enter and a left click only end two fixed-length
  waits (about 3 s and 10 s) in the start-up path, apparently the logo/splash screens 🟡. In the troop window Ctrl is only a click
  modifier (Ctrl+click opens the roster book, `notes/troop_selection.md`). ✅

## 5. Briefing screen ✅ / 🟡

- **Composition** (per briefing script): the briefing's map window variant (`MapWindowBP1`, ... : `MapTitle`, town labels,
  trail dots), the campaign tent (`notes/campaign_tent.md`), Dietrich's window with panel 1 (Abort / Accept / Pause), the
  Commander's window without a panel, and the dialogue text drawn on the map (`notes/briefing_dialogue.md` §3). Portraits, backdrops
  and mouth/blink animation: `notes/glue_portraits.md`.
- **Sequence**: `playmidi:sighted`, open the map, tent, portrait windows, then Dietrich and the Commander alternately talk
  (`animseq` 1/2) while their `queuetoplaytext`/`playtext` lines are typed and spoken. Pacing, speech, colours, font: `briefing_dialogue.md`.
- **After the last line** nothing happens by itself: the script ends, the windows stay, and the screen waits for a panel button.
  `setdemodefault` is inert (`briefing_dialogue.md` §3.6). ✅
- **Abort**: ends the script and all briefing windows, stops speech and music, and returns to the map exactly as it was left (§4.2,
  §8.1). ✅ **The map is then silent**: Abort discards the tune and forgets its name, and the pop that Abort uses restores the
  windows without restarting any tune. Only a map that a flow script gave its own tune with `addmidiobject` (the first campaign map)
  could restart it when its window is re-created 🟡.
- **Accept** while text is still being typed drains (skips) the remaining lines, stops the speech, and opens troop selection. The briefing
  script is not resumed. ✅ What Abort in troop selection returns to when it was entered from a briefing (the parked briefing or the
  map) depends on which context is on top of the stack 🟡.
- **Pause / Resume** freezes text typing, portrait animation, speech and music; Resume undoes it (`briefing_dialogue.md` §2.5).
- **Brief again** replays the briefing from the start (§4.2).
- The current engine `BriefingScene` differs from the original in three ways: it advances by click/Enter instead of by timer, uses the
  battle font instead of glue font slot 4, and continues automatically after the last turn instead of waiting for Accept / Abort.

## 6. Data versus hardcoded

**Data** (`WND.DLL`, `BRTXT.DLL`, `BKTXT.DLL`): mission sets per window, names, briefing/battle/mission
scripts, payments, gating fields; every layout, bitmap, hotspot, hint, cursor name, dialogue line, movie
and MIDI cue; the order of screens (flow/mission scripts).

**Built into `WHSHR.EXE`**: the glue command set; the visibility predicate and scroll count; row painting;
the built-in windows `PopContext`, `UnwindMission`, `TroopSelect`, `AbortGame`, `LoadSaveWindow`, the
books; the `gocaravan` mode → caravan script mapping; the debrief/economy programs.

## 7. Is it a different state-machine candidate than the briefing? ✅

Yes. The briefing is a linear scripted scene (dialogue turns, then continue). Mission selection is
an **interactive parked state** inside a flow script that is suspended while sub-screens (caravan, books,
save/load, troop selection, briefing, battle) push and pop over it. Nothing in the shipped data prepends
dialogue or a cutscene before the list: scripts *can* (`playtext`, `playmovie`, `opensubwindow` are ordinary
commands) but, before the first `waitforrelease`, no flow script does (only the demo script `FlowScriptEcts`
contains `playmovie`/`playtext`). Cutscenes and debrief text come **after** a battle, at the end of the
mission script, before `gocaravan:select`. Chapter changes come from a mission script that chains into
the next flow script (not checked script by script 🟡).

Suggested engine model: a stack of scenes (caravan, map+list, briefing, troop select, battle, movie),
with transitions taken from the parsed scripts (`whshr/campaign.py`), so any window script can be a
scene. The current `CaravanScene → BriefingScene` shortcut skips the map-and-list screen.

## 8. Caravan entry is not unconditional; where cutscenes occur ✅

Found by grepping the tails of the extracted mission scripts (`extracted/pe_resources/WND/rcdata`), not by
tracing every script in full.

The mode of the built-in `gocaravan:<mode>` command, issued by the mission script, decides which caravan opens:

| Mode | Caravan | Hotspot | Where used |
|---|---|---|---|
| `select` | `CaravanAfterMission` (`…WithRecruit` when reinforcements are waiting) | 150 → `UnwindMission` | most mission scripts |
| `resume` | `CaravanAfterEncounter[WithRecruit]` / `CaravanContinueMission` | 161 "continue mission" → `PopContextCheckResume` | `GMMission1`, `GMMission2` |
| `recruit`, `recruitnospeech` | `CaravanRecruit[NoSpeech]AndResume` | – | mid-script: `BPMission2`, `LastMission`, `SZMission5End` |
| `info*` (`infobpc`, `infoREA`, `infoszb`, `infoena`, `infoLA`, `infoLB`, `infoWED`, `infoBMA`, `infoREC`) | `InfoCaravan*` | 150 (text still "select mission") → `UnwindMission` | end of some missions, or in subscripts |

Conditional entry: `REMISSION4` does `testmission:` then `iftruegocaravan:infoREC` / `iffalsegocaravan:select`;
`WEMISSION2` runs `WE2_SubScript1` (`gocaravan:infoWED`) on one branch and `select` on the other;
`BMMISSION1..3` run `BM123_SubScript1` (`infoBMA`) before `select`. `LastMission` never returns to the
caravan: after the A24 movie and the last battle it plays A25, A26 or A27 by objective flags, closes the map and
runs `endgame:`.

What each caravan's hotspot does when it is left (`PopContext`, `UnwindMission`, `PopAndResume`, `PopContextCheckResume`) is
specified in §8.1.

### 8.1 The glue context stack and the built-in windows ✅ (static analysis) / 🟡 (runtime)

**Context stack.** The front end keeps a stack of at most 16 context frames. A **push** saves (a) the running glue script's
state, when a script is running (a "script frame"; otherwise a plain "window frame" that only records the window name), (b) the whole
set of glue windows (up to 8: bitmaps, hotspots, portrait windows, the mission list and its **selected row**, the palette), and (c) the
caller's window name; then it destroys the windows. A **pop** restores (b) and, for a script frame, (a), and shows the windows again; for
a window frame the caller re-opens the saved window by name. Overflow and underflow are logged and ignored (no crash), so an extra pop
with nothing on the stack is a harmless no-op.

Who pushes: the panel buttons that open another screen (Caravan, Accept, Options: §4.2); `gocaravan:<mode>` (pushes the running
script); and **every hotspot whose `res:` is opened** (the launcher pushes the current window before running the target).

**Built-in windows.** A hotspot's or script's `res:` name is first matched, exactly, against this table of 15 built-in names; a name
not in it is opened as a window resource. Each built-in first destroys the current windows.

| Built-in window | Behaviour | Used by |
|---|---|---|
| `PopContext` | restart the remembered tune (looping; paused if the game is paused); pop and discard one frame (the window frame the hotspot launcher just pushed for the caravan); pop the next frame: a window frame re-opens that window, a script frame is restored and, if the game is not paused and the restored script's own flag is clear, the script runs again (the flow script re-parks in `waitforrelease`) | `CaravanSelectMission`, `OptionWindow` |
| `PopContextCheckResume` | **identical dispatch to `PopContext`** (same routine, same resume check); the name differs only in the data | `CaravanContinueMission` |
| `UnwindMission` | pop frames until a script frame is restored **whose windows contain a mission list**; a restored script frame without one (the mission script that ran `gocaravan`) is cleaned up and popped again. Then the mission-list *release step* (`notes/campaign.md` §7.5): a selected record with `replacescript` switches the flow; otherwise the current mission (marked taken by troop selection's Done) is copied over the selected record, visible rows are recounted, the first visible row is selected if the current one is hidden, the list is rebuilt, and the flow script resumes only if the record has `releaseflag` or nothing visible remains (else the player stays on the map) | after-mission and after-encounter caravans, `InfoCaravanBMA/BPC/ENE/LB/REA/REC`, `CaravanDietrich` |
| `PopAndResume` | pop and discard two frames (the hotspot's window frame, then the mission script's frame `gocaravan` pushed), run the caravan-leave housekeeping (unhired units removed from `ARMY.MRC`, unused reinforcements cleared: `notes/campaign.md` §2.4), then resume the mission script after its `gocaravan:` command | `CaravanRecruit*AndResume`, `InfoCaravanENA/LA/SZA/SZB/WED` |
| `AbortGame` | Yes/No confirmation (`BRTXT 308`); Yes cleans up, pops one frame and runs a final step that presumably abandons the campaign toward the main menu 🟡; No pops one frame and re-opens the window | caravan (`CaravanCommon1`), `CaravanEcts/Ms` |
| `NewGame` | asks for the commander's name, creates the campaign files (`ARMY/PLAY/MARCH.MRC`, `debrief.dbf`) and enters `StartCaravan` | main menu |
| `OptionsDialog` / `OptionsDialogDone` | open the option window / apply the settings, then as `PopContext` (restart the remembered tune) | caravan, main menu, panel 9 |
| `ArmyBook`, `HireOnlyArmyBook`, `MagicBook`, `EncyclopediaBook` | open the roster book (mode 0 / hire-only), magic book or encyclopedia | caravan hotspots |
| `ExitProcess` | close the application | main menu |
| `Credits` | play the credits | main menu |
| `NullWnd` | pop one frame and re-open it (no visible effect) | - |

**How each caravan is left.** `CaravanSelectMission` (opened by the map's Caravan button): `PopContext` returns to the map. After-mission
caravans (`gocaravan:select`): `UnwindMission` unwinds to the parked flow script and applies the mission result to the list (this
happens when the caravan is left, **not** when a row is picked; the wording in `notes/campaign.md` §7.5 "after the player picks a row"
should read "when the after-mission caravan is left"). Mid-mission caravans (`recruit`, `infoena` ...): `PopAndResume` continues the
mission script. `CaravanContinueMission` (from panel 9's Caravan button while a mission script is showing its map, e.g. every
`BPMission*` and encounter): `PopContextCheckResume` returns and the mission script continues.

**When the encounter caravans appear.** `CaravanAfterEncounter[WithRecruit]` is opened by `gocaravan:resume` (`GMMission1`,
`GMMission2`, after `encounterplaygamewithdebrief`); `CaravanContinueMission` is opened only by panel 9's Caravan button.

### Cutscenes (`playmovie:A<n>`)

Ordinary script command. Found only in mission scripts, after the battle and before the next caravan:
A2 (`BPMission1`), A3, A4+A5, A6, A7, A8, A9/A12/A12b, A10, A11, A13, A15, A16a, A17, A18/A18b, A20, A24–A27.
Two scripts play one **between two caravans**: `SZMission2` (`gocaravan:infoszb` → `playmovie:A13` →
`gocaravan:select`) and `SZMission5` (`gocaravan:infoena` → `playmovie:A16a`). The flow scripts that build the
mission list contain no `playmovie`/`playtext` before their first `waitforrelease`.

Consequence: the engine should not hardwire caravan → mission list. The caravan mode and what follows it
should come from the parsed mission-script sequence, including `iftrue`/`iffalse` branches and `endgame:`.

## 9. Artwork for the `[ANIM]` portraits (Dietrich, Commander, …)

Question: `ScribeMWindow` declares `[ANIM] name:Dietrich`, but no bitmap of that name exists and the
extracted caravan art (`Diet*Cell`, `Read*Cell`, `Talk*Cell`) is unrelated. Answer ✅ (visually verified, see below):
the portrait is an ordinary **leader-portrait `.FOL/.BOP` sprite set** drawn over a **`BACKALL` background
frame** inside a **frame border**; nothing has to be extracted from `WND.DLL` bitmaps.

### 9.1 What the `[ANIM]` keys mean

`name:` is only a speaker label (no string `Dietrich`/`Cpt Bernard` exists as a lookup key in the front end).
The artwork is selected by numbers:

| Key | Meaning | Evidence |
|---|---|---|
| `set:index=N` | fixed per person: which portrait sprite set | 19 Dietrich windows all use 4, Commander always 2, Carlsson 1, Dargrimm 7, Harkon 6, Gotrek 10, Holger 20, Engrol 21, Azguz 22, Allor 23, Marius 28; the single `name:Scribe` window also has index 4 |
| `set:bkindex=N` | which frame (0–20) of `BACKALL` (21 frames of 120×152) is drawn behind the figure | varies per scene for the same person (Dargrimm 0/4/8/10/14/16, Harkon 5/8/14/16/17); Dietrich mostly 15 |
| `set:controlpanel=N` | which button panel sits under the portrait (0 = none) ✅, see §9.4 | Dietrich 1, 2, 6–9; Commander 1, 2, 6, 9 |
| `set:sequence=1`, `set:frame=3` | initial animation sequence / frame | all `[ANIM]` blocks |
| script `set:animseq=1/2` + `applyseq:` | 1 = talking, 2 = stopped | briefing and flow scripts |

### 9.2 Dietrich = the `Scribe` portrait `SCRI` ✅

- `index=4` is shared by `name:Dietrich` (19 windows) and `name:Scribe`. The sprite-name table (`notes/sprite_names.md`)
  has `Scribe` → `SCRI` in the leader-portrait category (table index 98), so index 4 → `SCRI`.
- `SCRI.FOL/.BOP` (8 type-1 frames, standard palette): frame 0 = 120×152 portrait of the old, bespectacled scribe in a
  green tunic holding a red book (the same man as the caravan close-up); frames 1, 3, 4, 5, 6 = 44×26 mouth overlays at
  (40, 84); frames 2, 7 = 32×5 eye overlays at (47, 69) (blink). The overlay position is the record's `int16 x, y`
  (`notes/animations.md`).
- `index` is **not** the position in the leader-portrait category: it is a position in a separate 37-entry resident portrait
  list. The full table (all indices used in glue, with sprite sets) is in `notes/glue_portraits.md` §1; Dietrich → `SCRI` and
  Commander → `COMM` are both verified.
- `bkindex=15` (Dietrich's usual value) is `BACKALL` frame 15, a red stage curtain with gold curl trim; the portrait's
  chair back matches it. Compositing frame 0 over it, with a mouth overlay at its stored position, gives the expected
  picture (rendered locally, not committed). Frames 16 and 17 (Commander's usual) need the window's map screen palette pair,
  not `STANDARD.PAL` alone (`notes/glue_portraits.md` §2.1). Mouth/blink animation: `notes/glue_portraits.md` §3.

### 9.3 Frame geometry ✅

The window is 144 wide. `FRAMETOP` (136×8) is drawn at (4,4), `FRAMELEFT` (8×152) at (4,12), `FRAMERIGHT` (8×152) at (132,12),
and the panel bitmap at (4,164). The background/portrait is inside the frame (from 12,12: 8 + 120 + 8 = 136 wide, 152 tall). Below it
is either `FRAMEBOTTOM` (136×8, no buttons) **or** `FRAMEPANEL1..4` (136 × 28/48/68/88 = 8 + 20 × N), a panel with N button-shaped
slots; exactly one of them, never both (`notes/data_driven_audit.md` §1 item 9).

**Height ✅.** The declared window height equals `164 + panel height + 8` in **111 of 115** `[ANIM]` windows: 180 (no panel), 200
(panel 1), 220 (panel 2), 240 (panels with 3 buttons), 260 (panel 4). The four exceptions are `Bernard3Window` (declared 240, no
panel), the two `HarkonEncounterWindow*` (declared 220, one button) and the test `MapTestWindow` (480); they look like authoring
inconsistencies (the real size is derived from the panel by the code 🟡).

**What is data and what is fixed.** Across the 114 `[ANIM]` blocks (about 100 windows) the sub-window's own
`[POSITION]` varies per scene (e.g. Dietrich on the map/briefing 450,25 or 475,55; Commander 20,225 or 20,25; 38 distinct
values), always 144 wide and 180/200/220/240 tall. `[ANIM] set:x/y` is 0,0 in every block. The inner layout is
constant in the front end: frame at (4,4), portrait/background at (12,12) inside it, panel at (4,164), buttons at x + 9.

### 9.4 The control panel: Brief / Accept / Caravan ✅

`controlpanel` selects the panel and the button set (front-end logic, not data). Buttons are ordinary child buttons
119×20 at x + 9, stacked upward from the panel bottom: slot 0 (id `0x100`) is the **lowest**, slot 2 the highest, at
y = window height − 12 − 20 × (slot + 1). Art: `FRAMEBUTTONUP` / `FRAMEBUTTONDN` (119×20, up/pressed); the label is
drawn over it from `BRTXT`. Labels by slot (BRTXT ids in brackets):

| `controlpanel` | Panel | Slot 0 (bottom) | Slot 1 | Slot 2 (top) | Slot 3 |
|---|---|---|---|---|---|
| 2, 10 (map with mission list) | `FRAMEPANEL3` | **Caravan** (333) | **Accept** (309) | **Brief** (313) | – |
| 1, 6 (battle-side) | `FRAMEPANEL3` | Abort (311) | Accept (309) | Pause (310) / Resume (312) | – |
| 7 | `FRAMEPANEL3` | Decline (338) | Accept (309) | Brief (313) | – |
| 9 | `FRAMEPANEL3` | Caravan (333) | Options (339) | Pause / Resume | – |
| 5 | `FRAMEPANEL4` | Abort (311) | Accept (309) | Report (332) | Brief (313) |
| 4 | `FRAMEPANEL2` | Evade (330) | Attack! (329) | – | – |
| 3 | `FRAMEPANEL1` | Defend (331) | – | – | – |
| 8 | `FRAMEPANEL1` | Attack! (329) | – | – | – |
| 0 / other | `FRAMEBOTTOM` | – | – | – | – |

So the panel the question asks about is `controlpanel=2`, read top to bottom: **Brief, Accept, Caravan**. What every slot does is in §4.2.

**Which windows use each panel** (all 115 `[ANIM]` windows):

| `controlpanel` | Windows | Opened by |
|---|---|---|
| none / 0 (60 windows) | speaker windows without buttons: `CommanderWindow*`, `Ceridan*`, `Dwarf*`, `Bernard*`, `Carlsson*`, `EngrolWindow*`, ... | briefing and encounter scripts |
| 1 (22) | briefing windows: `ScribeWindow*`, `Scribe2/3/4Window*`, `YouWindow*`, `Dwarf*Enc1`, `Woodelf*`, `GotrekSpecialWindow`, ... | the briefing scripts |
| 2 (2) | `ScribeMWindow` (map with mission list), `MapTestWindow` (test) | the flow scripts |
| 3 (4) | `AmbushWindow`, `Forest/Mountain/SnowyAmbushWindow` | ambush subscripts, `BPMission5` |
| 4 (2) | `CeridanEncounterWindow` (`SZMission5`); `EncounterWindow` (never opened) | mission scripts |
| 5 | **no window** | - |
| 6 (2), 7 (3) | `ScribeWindowEnc6`, `CommanderWindowEnc7TR`; `ScribeWindowEnc7`, `AzguzWindowEnc7TM`, `HolgerOfferWindow` - **never opened by any shipped script** | - |
| 8 (4) | `HarkonEncounterWindow*` (`BPMission15`), `AzguzWindowEnc8`, `ScribeWindowEnc8` (Loren subscripts) | mission scripts |
| 9 (17) | `Scribe5WindowTL*` (opened by nearly every `*Mission*` script: the map while a mission runs), `ScribeWindowEnc9*`, `CommanderWindowEnc9*` | mission scripts and subscripts |
| 10 | **no window** | - |

Panels 5, 6, 7 and 10 exist in the front end but are unused by the shipped data; an engine needs them only for completeness
(the labels and actions are in §4.2). During a mission script the player therefore always has the panel-9 buttons: Caravan
(`CaravanContinueMission`), Options and Pause.

Text color: the button label is drawn in the `settextcolor` of the `[ANIM]` block; the font is glue font 2.
Pressed/hover states use `FRAMEBUTTONDN`. Disabled buttons use a grey (0xC0C0C0) label 🟡.

Cross-verified by static analysis (`notes/fonts_glue.md` §6): the front end's shared `FrameButtonUp`/
`FrameButtonDn` button-label painter (the same routine draws Brief/Accept/Caravan, reinforcement and tab
button labels) also selects glue font 2 with a constant argument, matching the mission-list row painter
and the mission title — all three built-in UI text elements use font 2 (`PCTEXT.FON`).

### 9.5 What an engine needs: read the data, don't hardcode the placement

Where things go is decided by the scene's glue scripts; the engine reads it and only the *inside* of the sub-window is
fixed layout.

1. **Which window and where.** The flow/briefing script opens a named sub-window (`opensubwindow:res=ScribeMWindow`,
   `ScribeWindow`, `CommanderWindow`, …). Read that resource's `[POSITION]` (`set:x`, `set:y`, `set:vx`) for the
   window's place on the screen (450,25 for `ScribeMWindow`). Do not put Dietrich at a constant coordinate: the same
   speaker appears at other positions in other scenes.
2. **Who and which backdrop.** In the same resource read the `[ANIM]` block: `set:index` (portrait sprite set),
   `set:bkindex` (`BACKALL` frame), `set:controlpanel` (panel and buttons, §9.4), `settextcolor` (label / dialogue
   colour), `sequence`/`frame` (initial state). The script commands `set:animseq=1/2` + `applyseq:` switch talking and
   stopped; `set:textlines` sets the dialogue line count.
3. **Inside the window** use the fixed layout of §9.3: frame pieces at (4,4)/(4,12)/(132,12), backdrop and portrait at
   (12,12), panel at (4,164), buttons at x + 9 (§9.4). The height is `164 + panel height + 8` (§9.3); it equals the declared
   `set:vy` except in four windows, so derive it from the panel and ignore `set:vy`.
4. **Assets, at runtime from the installation.** Portrait sprite set (`SCRI` for index 4) and `BACKALL` via the FOL/BOP
   decoder (`whshr/sprites.py`, `STANDARD.PAL`); `FRAME*` bitmaps and button/label text from the `WND`/`BITMAP`/`BRTXT`
   resources. Do not commit frames.
5. **Animation.** Frame 0 alone when stopped; mouth overlays (frames 1, 3–6) while talking; eye overlays (2, 7) as blinks,
   each at the overlay's stored x/y. Frame timing is unknown (`notes/animations.md`).
6. Do **not** use the caravan close-up cells (`DietBookCell`, `DietMouthCell`, `ReadEyesCell`, `TalkEyesCell`): they belong
   to the separate in-caravan Dietrich animation, not to `[ANIM]`.

## 10. Open questions
> **Historical questions:** issue #27 is closed. These notes preserve the findings; the remaining unknowns are not standing research tasks. Reopen a focused issue only when a shipped feature or reproducible defect needs an answer.


Resolved by this note (kept for the record): input handling of the list, the panel actions of every `controlpanel` value, the built-in
window table, `PopContext` / `PopContextCheckResume` (identical), `UnwindMission`, the music after Abort (silent), the "which windows use
panels 6/7/10" question (none), the window height rule. The full register of open items across all notes is in `ROADMAP.md` ("Open
research questions").

Still open in this note:

- ⚠ **Double-click on a list row** (§4.1): the code runs Brief, the project owner observed no effect. Needs a runtime check.
- ⬜ Effect of accelerator command 16 (Ctrl+X) and command 14 (F2, test table).
- 🟡 Which context Abort in troop selection returns to when troop selection was opened from a briefing (§5).
- 🟡 `Attack!` (panel 4) sets the script's true/false status flag before starting the battle (inferred from the shared routine).
- 🟡 Whether the "drain text" step fast-forwards or merely finishes pending text (two variants: with and without a skip flag), and the
  first step of Abort/Caravan whose purpose is not identified (it runs when speech is enabled).
- 🟡 Whether the brief action's push is skipped when the owning window has portrait entries of its own (§4.2).
- ⬜ What `Report` (panel 5, unused) would do.
- 🟡 Music after Abort on the first campaign map, whose window carries its own tune (`addmidiobject`): silent or restarted on re-creation (§5).

Resolved elsewhere (pointers):

- Chapter transitions: **not** a chain of flow-script calls. Each `[MISSION]` record can carry `replacescript:<FlowScriptXxx>`; when that mission is
  taken and the release step runs (§8.1) the running flow is swapped for the named one, and the next map/list is built by the new chapter's flow
  script. Chapter graph: `FlowScriptBP01` -> (`MissionBP23Window`) `BP03` or `BP25`; `BP03` -> `BP05` -> `BP09`; `BP09` (`MissionBP131415Window`) -> `RE`,
  `BPBM` or `GF`; `RE` (`MissionRE4568Window`) -> `RE01`, `RE02`, `WE` or `REBM`; `RE01` (`MissionRE5678Window`) -> `RE02`, `REWE` or `REBM`; `RE02`
  (`MissionRE678Window`) -> `REWE` or `REBM`; `GF02c` -> `SZENGML`; `WE1`/`WE45`/`BM1234`/`BM1235` -> `WE` or `SZENGML`; `MissionLWindow` -> `L3`. No
  flow script has `playtext`/`playmovie` before its first `waitforrelease` (only the demo `FlowScriptEcts`); dialogue and cutscenes around a chapter
  change belong to the mission script that ends the previous chapter (§8). ✅ (data)
- Palettes: `palindex` (0-9) indexes a fixed table of named screen palette pairs, each a `WIND<name>.PAL` (RGB half, loaded first) plus a
  `GLUE<name>.PAL` (colour-map half): 0/other `STANDARD`, 1 `book`, **2 `map`**, **3 `car`**, 4 `mind`, 5 `end`, 6 `titl`, 7 `game`, 8 `opt`, 9 `bk2`. Going from
  the map to the caravan loads a different pair. `BACKALL` frames 16/17: `notes/glue_portraits.md` §2.1. ✅
- The troop window (class `TroopWindow`, six pages, modes 0-7, buttons, music): `notes/troop_selection.md` (this note previously carried a partial
  description; it is superseded).
- Portrait `index` -> sprite table and animation timing: `notes/glue_portraits.md`.
