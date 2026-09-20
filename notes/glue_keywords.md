# Glue window-script keyword reference (`WND.DLL` resources)

Reference for the block and key vocabulary of the window scripts (`[WINDOW]` resources) that describe every campaign screen.
It records, per block, which keys and commands the front-end parser accepts, what each does, whether shipped scripts use it and where
it is documented. Sources: the block parsers and the paint and animation code in `WHSHR.EXE` (read as research input; no code
reproduced), a usage scan of all 535 `WND.DLL` scripts (`extracted/pe_resources/WND/rcdata`), and the existing notes. Marks: ✅
verified from code and data, 🟡 inferred, ⬜ unknown. Companion notes: `notes/pe_resources.md` §1.7 (script overview),
`notes/campaign_tent.md` (bitmap animation), `notes/glue_portraits.md` (`[ANIM]`), `notes/mission_selection.md`, `notes/briefing_dialogue.md`.

## 1. Syntax and parse rules ✅

- One statement per line; `;` and `//` start a comment. Blocks are `[NAME] ... [END]`. Statements are either **`set:<key>=<value>`**
  (numeric, from one shared key-name table) or **`<command>:<argument>`** (string arguments, e.g. `setbitmap:Map`).
- Each block type has its own parser with a fixed switch. **Every key or command the block does not list is silently ignored**: there
  is no warning, so a misplaced or misspelt key has no effect. The engine should copy this behaviour (and may log a diagnostic).
- Block types: `WINDOW` (container), `POSITION`, `BITMAP`, `MISSION`, `MISSIONWINDOW`, `SUBWINDOW`, `ANIM`, `TEXT`, `HOTSPOT`,
  `DEMODEFAULT`, `LOADANDSAVEGAME`, `INCLUDE`, `MIDI`, and the script blocks `RUN`/`START`. `[END]` closes any block. The first
  statement of a resource must be the block the caller expects (`[WINDOW]` for windows, `[RUN]` for scripts) or the load fails with an
  error message 🟡.
- Records are appended in file order per window: bitmaps (drawn in that order), mission records (at most 5), anim blocks, texts,
  hotspots. Order therefore matters for drawing (`notes/campaign_tent.md` §5.6) and for the mission list.
- Numbers in a `set:` value may be negative decimals.

## 2. Blocks at a glance

| Block | Blocks / files in shipped scripts | Purpose | Detail |
|---|---|---|---|
| `[POSITION]` | 199 / 199 | window rectangle and palette | §3.1 |
| `[BITMAP]` | 274 / 264 | picture, optionally animated | §3.2 |
| `[ANIM]` | 115 / 115 | speaker portrait with talk/blink animation | §3.3 |
| `[TEXT]` | 144 / 50 | string drawn at a position | §3.4 |
| `[HOTSPOT]` | 112 / 32 | clickable rectangle or button | §3.5 |
| `[MISSIONWINDOW]` | 35 / 35 | position of the mission list on the map | §3.6 |
| `[MISSION]` | 68 / 35 | one mission record (max 5 per window) | §3.7 |
| `[MIDI]` | 25 / 25 | music of the window | §3.8 |
| `[INCLUDE]` | 87 / 68 | include another resource | §3.9 |
| `[DEMODEFAULT]` | 7 active / 7 | action after an idle timeout | §3.10 |
| `[LOADANDSAVEGAME]` | 2 / 2 | save/load list placement | §3.10 |
| `[SUBWINDOW]` | 0 (only in a comment) | sub-window placement record | §3.10 |

## 3. Keywords per block

Status column: **used** = at least one shipped script uses it; **parsed, unused** = the parser accepts it but no shipped script
does; "Doc" = the note that already explains it (`-` = this note is the first place).

### 3.1 `[POSITION]`

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `set:x`, `set:y` | window origin on the 640×480 screen | ✅ used (199) | `ALLORWINDOW` | `mission_selection.md` §9 |
| `set:vx`, `set:vy` | window width and height (the code may recompute the height for portrait windows) | ✅ used (199) | `SCRIBEMWINDOW` | `mission_selection.md` §9.3 |
| `set:palindex=N` | screen palette pair, 0-9 → named `WIND`/`GLUE` pairs (0 = `STANDARD`; 2 = map; 3 = caravan; …) | ✅ used (82) | `CARAVANAFTERENCOUNTER` | `mission_selection.md` §10, `fonts_glue.md` |
| `set:book=N` | book number the window represents | 🟡 used once | `JOURNALBOOK` | `mission_selection.md` |

### 3.2 `[BITMAP]`

Keys and commands the parser accepts (all others are ignored): `set:x`, `set:y`, `set:timecnt`, `set:looptimecnt`,
`set:animstartframe`, `set:animrestartframe`, `set:animstopframe`, `set:bkindex`, `set:depend`, `setbitmap`, `setmask`, `gettentpos`.

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `setbitmap:<Name>` | literal resource name (static) or base name of a numbered cell set (animated) | ✅ used (274) | `CARLAMPCELL` | `campaign_tent.md` §5 |
| `set:x`, `set:y` | position | ✅ used (189) | `CARAVANCOMMON1` | `campaign_tent.md` |
| `set:animstartframe=S` | first frame; **also stores the restart frame** | ✅ used (185) | `TRAILBP1A` | `campaign_tent.md` §5.1 |
| `set:animstopframe=E` | `-1` loop; `>= 0` play down to `E + 1` | ✅ used (149) | `TRAILBP1A` | `campaign_tent.md` §5.2 |
| `set:animrestartframe=R` | loop restart frame; defaults to `S` | ✅ parsed, unused | - | `campaign_tent.md` §5.1 (new) |
| `set:timecnt=T` | frame period and initial delay, in 50 ms steps | ✅ used (149) | `CARAVANCOMMON1` | `campaign_tent.md` §5.2 |
| `set:looptimecnt=L` | extra pause on the last frame of a loop | ✅ used (2) | `CARAVANCOMMON3` | `campaign_tent.md` §5.5 |
| `set:bkindex` | repaint flag (value ignored) | ✅ used (1) | `TENTOBJECT01` | `campaign_tent.md` §5.6 (new) |
| `set:depend=N` | draw only when the caravan's visible-mission count ≥ N | ✅ used (3) | `CARAVANCOMMON1` | `campaign.md` §7.4 |
| `setmask:<Name>` | stored, never read; transparency is always palette index 0 | ✅ inert (181 uses) | `ATHELMARAYAMARK` | `campaign_tent.md` §4 |
| `gettentpos:` | overwrite x, y from the tent position table | ✅ used (1) | `TENTOBJECT01` | `campaign_tent.md` §3 |

Not accepted here although scripts elsewhere use the same names in other blocks: `set:res`, `set:frame`, `cursor`, … (ignored).

### 3.3 `[ANIM]`

Accepted: `set:x`, `set:y` (stored; the blocks all use 0,0), `set:sequence`, `set:frame`, `set:index`, `set:controlpanel`, `set:bkindex`,
`name`, `settextcolor`.

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `name:<Speaker>` | display label only (no lookup) | ✅ used (110) | `SCRIBEMWINDOW` | `glue_portraits.md` §1 |
| `set:index=N` | portrait sprite set: position in a 37-entry resident list (4 = `SCRI`) | ✅ used (115) | `SCRIBEMWINDOW` | `glue_portraits.md` §1 |
| `set:bkindex=N` | `BACKALL` frame number (exactly N) | ✅ used (114) | `ALLORWINDOW` | `glue_portraits.md` §2 |
| `set:controlpanel=N` | button panel under the portrait (0 = none) | ✅ used (105) | `SCRIBEMWINDOW` | `mission_selection.md` §9.4 |
| `set:sequence=N` | initial mouth/eye sequence (1 = talking, 2 = stopped) | ✅ used (115) | any | `glue_portraits.md` §3.4 |
| `set:frame=N` | ornament border set 0-2, **3 = none** (all shipped blocks use 3) | ✅ used (115) | any | `glue_portraits.md` §3.4 (new) |
| `settextcolor:<name>` | speaker text colour | ✅ used (115) | any | `briefing_dialogue.md` |
| `set:x`, `set:y` | offset inside the window | ✅ parsed, always 0 | any | - |

### 3.4 `[TEXT]`

Accepted: `set:x`, `set:y`, `set:vx`, `set:vy`, `set:res`, `set:resfile`, `set:format`, `set:font`, `settextcolor`, `linked`.
`vx`/`vy` are the rectangle width and height in the sense used by the `format` modes below.

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `set:res=N` | string id | ✅ used (144) | `MAPWINDOWBP1` | `pe_resources.md` §1.3 |
| `set:resfile=N` | string table: 0 = the glue text table (`BRTXT`), 1 = the game-text table (`GMTXT`, used for the option strings 36000+) | ✅ used (8) | `OPTIONWINDOW` | - |
| `set:format=N` | placement mode, see below | ✅ used (144; values 1, 6, 7, 8) | `MAPWINDOWBP1` | - |
| `set:font=N` | glue font slot (1, 2, 3 or 6 in shipped scripts) | ✅ used | `MAPWINDOWBP1` | `fonts_glue.md`, `briefing_dialogue.md` |
| `settextcolor:<name>` | colour name (red 146, green 110, black 84, lgray 36, yellow 20, cyan 18, white 8, blue 1) | ✅ used (144) | any | `briefing_dialogue.md` (RGB table) |
| `linked:` | flag: show the string `res + n`, where `n` is the current state of the hotspot whose `linkid` equals `res` | ✅ used (8) | `OPTIONWINDOW` | - |

`format` modes (position `(x, y)`, size `(vx, vy)`) ✅ from the painter: 0 word-wrapped paragraph in the rectangle; 1 one line centred
horizontally in `[x, x + vx]`, drawn at `y + vy`; 2 one line at `x + vx`, centred vertically in `vy`; 3 one line at `(x, y)`;
4 word-wrapped, centred vertically around `y + vy / 2`; 5 right edge at `x`, top at `y`; 6 like 5 but drawn with an outline in the
text colour (skipped when a global "no text" flag is set); 7 right edge at `x + vx`, centred vertically in `vy`; 8 left edge at `x`,
centred vertically in `vy`. Shipped use: 1 (map titles), 6 (town labels), 7 and 8 (option lines).

### 3.5 `[HOTSPOT]`

Accepted keys: `set:x`, `set:y`, `set:vx`, `set:vy`, `set:res`, `set:count`, `set:clickres`, `set:clickrescnt`, `set:textx`, `set:texty`,
`set:linkid`, `set:upsfx`, `set:downsfx`. Commands: `cursor`, `altcursor`, `script`, `res`, `setmask`, `setupbitmap`, `setdownbitmap`,
`settextcolor`.

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `set:x/y/vx/vy` | rectangle | ✅ used (112) | `STARTCARAVAN` | `mission_selection.md` |
| `set:res=N` | hint string id shown when hovering; `-1` gold-coffers hint, `-2` none (buttons) | ✅ used (112); -1/-2 🟡 | `CARAVANCOMMON4` | `campaign.md`, `pe_resources.md` |
| `cursor:<Name>` / `altcursor:<Name>` | cursor resource while hovering / while pressed | ✅ used (99 / 51) | `CARAVANCOMMON4` | `pe_resources.md` |
| `res:<Window>` | window resource or built-in window to open; tried first | ✅ used (85) | `STARTCARAVAN` | `mission_selection.md` §2, §6 |
| `script:<file>` | original file name of the same target; fallback if `res:` is not found 🟡 | ✅ used (86) | `STARTCARAVAN` | `pe_resources.md` |
| `setupbitmap:<Name>`, `setdownbitmap:<Name>` | button picture up / pressed | ✅ used (20 each) | `MAINMENU` | - |
| `set:upsfx=N`, `set:downsfx=N` | sound-effect numbers for release and press | 🟡 used (20 each; 3 and 4) | `MAINMENU` | - |
| `set:linkid=N`, `set:count=N` | multi-state option button: `count` states, linked to `[TEXT]` blocks with `linked:` and `res = linkid` | ✅ code, used (8) | `OPTIONWINDOW` | - |
| `set:clickres=N`, `set:clickrescnt=N` | speech text id and line count played when the hotspot is clicked (Dietrich's "Hey, stop that!" type lines) | 🟡 used (14) | `CARAVANAFTERENCOUNTERWITHRECRUIT` | - |
| `set:textx`, `set:texty` | text position for the hotspot | ⬜ parsed, unused | - | - |
| `setmask:<Name>` | stored; use by the hit test not traced | ⬜ (comment only in `MAPWINDOW`) | - | `pe_resources.md` |
| `settextcolor:<name>` | hotspot text colour | ⬜ parsed, unused | - | - |

### 3.6 `[MISSIONWINDOW]`

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `set:x`, `set:y` | origin of the mission list on the map (always 30,15) | ✅ used (35) | `MISSIONBP01WINDOW` | `campaign.md` §7.3 |

The block that records `x`, `y` plus `script`/`res` names (a sub-window placement) is a different block type, `[SUBWINDOW]` (§3.10). ✅

### 3.7 `[MISSION]`

Accepted keys: `set:res`, `set:releaseflag`, `set:depend`, `set:inactivedepend`. Commands: `script`, `res`, `setbattlescript`,
`setmissionscript`, `replacescript`, `cash`, `debrief`, `forceunits`, `excludeunits`.

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `set:res=N` | mission name id (`BRTXT`); the identity `depend` refers to | ✅ used (68) | `MISSIONBP01WINDOW` | `campaign.md` §7.1 |
| `res:<Window>` / `script:<file>` | briefing window / original file name | ✅ used (68 each) | `MISSIONBP01WINDOW` | `mission_selection.md` §4 |
| `setbattlescript:<bf>` | battle file (not unique: `bf003` in 21 records) | ✅ used (66) | any | `data_driven_audit.md` |
| `setmissionscript:<Script>` | script that runs the battle | ✅ used (57) | any | `campaign.md` §5 |
| `replacescript:<Flow>` | flow script that replaces the current one when this mission is taken | ✅ used (25) | `MISSIONBM1234WINDOW` | `mission_selection.md` §10 |
| `cash:type,a,b,c,d,letters` | payment program and amounts | ✅ used (62) | `MISSIONAM1WINDOW` | `campaign.md` §2.5 |
| `debrief:<n>` | debrief evaluator index (n - 1) | ✅ used (4) | `MISSIONAM1WINDOW` | `campaign.md` §5 |
| `forceunits:<ids>` / `excludeunits:<ids>` | regiments forced / excluded for this mission (max 8) | ✅ used (20 / 39) | `MISSIONAM1WINDOW` | `campaign.md` §2.3 |
| `set:releaseflag=1` | choosing it resumes the flow script | ✅ used (12) | `MISSIONBM1234WINDOW` | `campaign.md` §7.5 |
| `set:depend=N`, `set:inactivedepend=N` | visibility gates | ✅ used (4 / 2) | `MISSIONENWINDOW` | `campaign.md` §7.2 |
| `set:tentpos=N` | **recognised and ignored** (one use, `MissionBP25Window`) | ✅ | `MISSIONBP25WINDOW` | `campaign_tent.md` §2 (new) |

### 3.8 `[MIDI]`

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `name:<tune>` | music name of the window (`scribe`, `title`, `intro3`) | ✅ used (25) | `CARAVANAFTERENCOUNTER` | `briefing_dialogue.md` §2 |
| `set:volume=N` | music volume | ✅ parsed, unused | - | - |

### 3.9 `[INCLUDE]`

| Keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `script:<Resource>` | include another window resource, parsed in place | ✅ used (144) | `CARAVANAFTERENCOUNTER` | `pe_resources.md` |

Only `script:` is accepted. The one `addobject:res=MarkObjectKurgKeep` written inside an `[INCLUDE]` (`MAPWINDOWMSZHUFBAR`) is
ignored, so that mark object is never added. ✅ (likely an authoring slip; the engine should replicate the ignore.)

### 3.10 `[DEMODEFAULT]`, `[LOADANDSAVEGAME]`, `[SUBWINDOW]`

| Block / keyword | Meaning | Status | Example | Doc |
|---|---|---|---|---|
| `[DEMODEFAULT]` `set:flag`, `script`, `res` | window to open after an idle timeout (e.g. `MAINMENU` → `StartCaravan`); the script command `setdemodefault:` sets the same record | ✅ parsed and stored; effect 🟡 inert in this build | `MAINMENU` | `briefing_dialogue.md` |
| `[LOADANDSAVEGAME]` `set:x`, `set:y`, `set:flag` | placement of the save/load list; `flag` 1 = **load**, 0 = save ✅ (`notes/builtin_widgets.md`) | ✅ used (2) | `LOADSAVEWINDOW` | - |
| `[SUBWINDOW]` `set:x`, `set:y`, `script`, `res` | sub-window record | ✅ parsed, unused (commented out in `MAPTESTWINDOW`) | - | - |

## 4. Keys shared with other parsers

The `set:` key-name table is one list shared by the glue parsers, the script interpreter (`set:animseq`, `set:textlines`, `set:tentpos`
in `[RUN]` scripts) and the `.BTS`/`.MRC` parsers. Glue-relevant names in it: `x`, `y`, `vx`, `vy`, `count`, `res`, `resfile`, `sequence`,
`frame`, `clickres`, `clickrescnt`, `animseq`, `timecnt`, `looptimecnt`, `index`, `textlines`, `controlpanel`, `animstartframe`,
`palindex`, `book`, `bkindex`, `flag`, `format`, `font`, `animstopframe`, `animrestartframe`, `textx`, `texty`, `releaseflag`, `tentpos`,
`depend`, `volume`, `linkid`, `upsfx`, `downsfx`, `inactivedepend`. Script-level keys (`animseq`, `textlines`, `tentpos`) are consumed by
the interpreter, not by block parsers, so they have no effect inside a block. The remaining names (`s_*`, `whoami`, `dir`, …) belong to
the battle/army formats (`notes/game_rules.md`).

## 5. What the engine should do

- Parse each block with the key set above and ignore everything else, exactly like the original; do not fail on unknown keys.
- Drive placement, art names, hotspot targets, animation timing and gating from these keys (`notes/data_driven_audit.md`); only the
  tables named in the notes (`controlpanel`, `format` modes, colour names, `tentpos`, ornament sets) live in code.
- Treat `setmask`, `bkindex` (bitmap), `[SUBWINDOW]`, `[MIDI] volume` and hotspot `textx/texty` as no-ops until something needs them.

## 6. Open questions

- 🟡 `script:` versus `res:` precedence in hotspots and mission records (which is tried first and what counts as "not found").
- 🟡 Hotspot `res=-1` / `-2` special values (gold hint, no hint) were read from usage, not from the hint code.
- 🟡 Numbers for `upsfx`/`downsfx` (sound-effect table used) and the meaning of `clickres`/`clickrescnt` beyond the example.
- ⬜ `set:book` (window ↔ book number), `textx`/`texty`.
- ⬜ Whether an idle timer ever fires `[DEMODEFAULT]` in this build (the script command form was found inert).
