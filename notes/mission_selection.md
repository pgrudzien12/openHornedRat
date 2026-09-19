# Mission selection flow (caravan → map → briefing → battle → caravan)

Behavioral spec of what happens after the player clicks the "select mission" hotspot in the caravan,
which parts are data (`WND.DLL` glue scripts, `BRTXT.DLL`) and which are built into `WHSHR.EXE`, and which
graphics each screen uses. Availability rules (`depend`, `inactivedepend`, scroll count) are in
`notes/campaign.md` §7 and are not repeated here. Status: ✅ from script data, 🟡 inferred from the
front-end code and not verified at runtime.

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

- The caravan hotspot (x 480, y 250, 160×110; hint `BRTXT 150`) has two forms:
  - `StartCaravan`: `res:FlowScriptBP01` — starts the campaign (runs the first flow script).
  - all later caravans: `script:pop.wnd` `res:PopContext` (`CaravanAfterMission`: `UnwindMission`) — built-in
    windows that pop back to the suspended flow script and its map window.
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
- `TentObject01`: bitmap `Tent4` at 384,318; the position frame comes from the flow variable `set:tentpos`
  (0 at the start, 1 after the first mission window is dismissed).
- Trail dots: `Trail*`/`FlowTrail*` objects (`addanimobject`).
- The list: `MissionWindow` at `[MISSIONWINDOW] set:x/y` (always 30,15), one row per visible mission, bitmap
  `Scroll0` (selected) / `Scroll1`, label = `BRTXT` mission name + `" (initial, completion)"` payment.
- Mission window resources: 41 `MISSION*WINDOW`, at most 5 `[MISSION]` records each. Each record:
  `set:res=<BRTXT name id>`, `script:<orig .run name>`, `res:<briefing script>`, `setbattlescript:<bf>`,
  `setmissionscript:<script>`, `cash:type,initial,completion,rateA,rateB,letters`, optional `depend`,
  `inactivedepend`, `releaseflag`, `replacescript`, `excludeunits`, forced regiments.

## 4. Selecting a row, and the Brief / Accept / Caravan buttons ✅ (code) / 🟡 (runtime)

A click on a list row only **selects** it: the selection index changes and the list repaints. Nothing is launched
by the click itself (see §9.4 for the panel that does). The Dietrich panel on the map (`ScribeMWindow`,
`controlpanel=2`) has three buttons:

- **Brief** copies the selected record into the current-mission struct (name, cash, forced regiments, battle,
  mission script) and runs the record's `res:` briefing window (falling back to its `script:` name);
- **Accept** opens troop selection for the current mission (`notes/campaign.md` §2.3), whose Done marks the mission
  taken, charges the fee, and lets the mission script run the battle;
- **Caravan** opens the `CaravanSelectMission` caravan; its hotspot `PopContext` returns to this map.

The list row hit-test also has a second path that runs the same brief action (double-click or click on the
already-selected row 🟡; not verified at runtime).

## 5. Briefing screen ✅

- Map window variant + tent + Dietrich (`ScribeWindow`) and Commander (`CommanderWindow`, 20,225,
  `index=2`, `bkindex=16`) portraits, each with a talking/stop-talking `animseq` (1/2).
- Dialogue: `settextcolor:red` (Dietrich) / `green` (Commander), `queuetoplaytext:res=<id>` … `playtext:res=<id>`;
  ids `B×1000 + 10k + j` in `BRTXT` (`notes/pe_resources.md`). `set:textlines=2`.
- MIDI `playmidi:sighted` during the briefing, `generic` during the mission script.
- Between dialogue turns: trail dots (`addanimobject:res=Trail…`).
- The repo's `whshr/briefing.py` already extracts the title and spoken lines from these scripts.

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

## 8. Caravan entry is not unconditional; where cutscenes occur ✅ (scripts) / 🟡 (UnwindMission)

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

🟡 `UnwindMission` presumably returns control to the suspended script, which then decides whether a mission list
appears; that was inferred from the script layout, not checked in the front-end code.

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
- `index` is **not** the position in the leader-portrait category (Dietrich would be 19, Commander 5): the table that maps
  the glue index to a file was not found. Only Dietrich → `SCRI` is supported (by the shared `index`); `Commander` → `COMM`
  is by name only 🟡.
- `bkindex=15` (Dietrich's usual value) is `BACKALL` frame 15, a red stage curtain with gold curl trim; the portrait's
  chair back matches it. Compositing frame 0 over it, with a mouth overlay at its stored position, gives the expected
  picture (rendered locally, not committed). Frames 16 and 17 (Commander's usual) decode with a wrong-looking palette
  (green/red interior with a bottle) when `STANDARD.PAL` is used, so `BACKALL` may need its own palette 🟡.

### 9.3 Frame geometry ✅

The window is 144 wide. `FRAMETOP` (136×8) is drawn at (4,4), `FRAMELEFT` (8×152) at (4,12), `FRAMERIGHT` (8×152) at (132,12),
and the panel bitmap at (4,164). The background/portrait is inside the frame (from 12,12: 8 + 120 + 8 = 136 wide,
152 tall). Below it is either `FRAMEBOTTOM` (136×8, no buttons) or `FRAMEPANEL1..4` (136 × 28/48/68/88 = 8 + 20 × N),
a panel with N button-shaped slots. A window with a 3-button panel is 12 + 152 + 68 + 8 = 240 tall, i.e. exactly
`ScribeMWindow` (144×240).

**What is data and what is fixed.** Across the 114 `[ANIM]` blocks (about 100 windows) the sub-window's own
`[POSITION]` varies per scene (e.g. Dietrich on the map/briefing 450,25 or 475,55; Commander 20,225 or 20,25; 38 distinct
values), always 144 wide and 180/200/220/240 tall. `[ANIM] set:x/y` is 0,0 in every block. The inner layout is
constant in the front end: frame at (4,4), portrait/background at (12,12) inside it, panel at (4,164), buttons at x + 9.
The declared height is not used as-is: the code derives it from the portrait bitmap plus the panel (20 px per button) 🟡.

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

So the panel the question asks about is `controlpanel=2`, read top to bottom: **Brief, Accept, Caravan**.
Button actions for 2 / 10 are in §4. Panels 6, 7, 10 additionally mark the current mission taken when Accept is
pressed and start the battle without troop selection 🟡 (which windows use them was not checked). Panel 9 ("Caravan"
= continue-mission caravan) belongs to `CaravanContinueMission`.

Text color: the button label is drawn in the `settextcolor` of the `[ANIM]` block; the font is glue font 2.
Pressed/hover states use `FRAMEBUTTONDN`. Disabled buttons use a grey (0xC0C0C0) label 🟡.

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
   (12,12), panel at (4,164), buttons at x + 9 (§9.4). Derive the window height from the portrait plus the panel
   (20 px per button) instead of trusting `set:vy` 🟡.
4. **Assets, at runtime from the installation.** Portrait sprite set (`SCRI` for index 4) and `BACKALL` via the FOL/BOP
   decoder (`whshr/sprites.py`, `STANDARD.PAL`); `FRAME*` bitmaps and button/label text from the `WND`/`BITMAP`/`BRTXT`
   resources. Do not commit frames.
5. **Animation.** Frame 0 alone when stopped; mouth overlays (frames 1, 3–6) while talking; eye overlays (2, 7) as blinks,
   each at the overlay's stored x/y. Frame timing is unknown (`notes/animations.md`).
6. Do **not** use the caravan close-up cells (`DietBookCell`, `DietMouthCell`, `ReadEyesCell`, `TalkEyesCell`): they belong
   to the separate in-caravan Dietrich animation, not to `[ANIM]`.

## 10. Open questions

- 🟡 Row-click handling details (double click? keyboard?) and what `PopContext` does when the stack is empty.
- 🟡 Which flow-script → mission-script chains produce chapter transitions and whether any adds dialogue before a list.
- ⬜ Exact `MapWindow` palette 2 vs caravan palette 3 switching between screens (`notes/fonts_glue.md`).
- ⬜ Contents of the built-in `TroopSelect` window layout (graphics not in `WND.DLL`).
- ⬜ The glue `index` → portrait file table, `BACKALL` palette for frames 16/17, and mouth
  frame timing (§9).
