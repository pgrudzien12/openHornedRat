# Briefing dialogue pacing, campaign speech and glue music

Behavioral spec of how the original front end plays music (`playmidi`, `addmidiobject`, `[MIDI]`), and how it shows and
paces campaign dialogue (`playtext`, `queuetoplaytext`, `settextcolor`, `set:textlines`, `applyseq`) with its spoken
audio. It follows the clean-room policy: what the game does, not how its code is written; no original text, only string
ids. Status marks: ✅ verified from data or code, 🟡 inferred (read from code, not observed running), ⬜ unknown.

Sources: glue scripts in `WND.DLL` (all 535 resources), the front-end executable (static analysis), `MIDI.DLL`
(disassembly of the exported functions), the installation (`FILE/BINARY/MUSIC`, `REMOTE/BINARY/GLUE/SPEECH`),
`notes/music.md`, `notes/sfx.md`, `notes/scene_scripts.md`, `notes/fonts_glue.md`, `notes/mission_selection.md`,
`notes/troop_selection.md`.

## 1. Summary

- Music is chosen by **name**. `playmidi:<name>` (and a window's `[MIDI] name:` / `addmidiobject:<name>`) loads
  `binary/music/<name>.mid` from the installation, or the FM variant (first six characters + `fm`) when the music option is
  FM. It **loops forever**, a new tune **replaces** the old one **abruptly** (no fade is ever requested), `stopmidi:`
  stops and discards. ✅
- Dialogue is **not click-driven**. A 25 ms timer types the text one character at a time, holds it, clears it and
  resumes the script by itself. With speech enabled each line's recording (`B<id>.WAV`, id = the string id in the script)
  starts with the line and the script resumes after the audio ends. A click fast-forwards the text. ✅ (mechanics) / 🟡 (click
  edge cases)
- Every glue speech id used by a `playtext` / `queuetoplaytext` command has a recording: **331 of 331** distinct ids. ✅
- After the last line of a briefing nothing else happens by itself: the screen waits for the player to use Dietrich's
  button panel (Abort / Accept / Pause). `setdemodefault` is stored but never read in this build. ✅ (data) / 🟡 (no reader)

## 2. Glue music

### 2.1 Commands

| Command / block | Effect | Status |
|---|---|---|
| `playmidi:<name>` | remember `<name>` as the current tune, load and start it (looping); replaces whatever plays | ✅ |
| `stopmidi:` | stop the tune, discard it, forget the current-tune name; immediate, no fade | ✅ |
| `addmidiobject:<name>` | store `<name>` as the *current window's* music and start it now | ✅ |
| `[MIDI] name:<name>` in a window resource | the window's music: **started every time the window is created** (also when a caravan is re-entered), even if the same tune is already playing | ✅ (window creation), 🟡 (restart when already playing: the load always discards the previous tune first) |
| `setmidivolume:<n>` | sets the MIDI mapper volume; **no script uses it** | ✅ |
| `setwavvolume:<n>` | sets the speech/effects volume (0-100, initialised to 100); **no script uses it** | ✅ |
| `pause` | no-op in the interpreter; no script uses it | ✅ |

The **current-tune name** is set by `playmidi` and cleared by `stopmidi` and by the panel buttons that leave a screen for good
(Abort, Accept, and Accept of panels 6/7/10: `notes/mission_selection.md` §4.2). While it is set, `PopContext` and
`PopContextCheckResume` (leaving a caravan) and `OptionsDialogDone` (closing the Options dialog) **restart that tune from the beginning**
(looping, paused if the game is paused); panel 9's Options button discards the running tune but keeps the name, so it comes back after the
dialog. Abort discards the tune and clears the name, so nothing restarts it. ✅ (code)

### 2.2 Name to file

- The path is `binary/music/<name>.mid` relative to the installation, looked up case-insensitively (the files are `NAME.MID`
  in `FILE/BINARY/MUSIC`; `UPDATE/BINARY` has no `MUSIC` directory). ✅
- The music option has three values: 0 off, 1 FM, 2 GM (wavetable); the option value comes from the saved options string. ✅
- **FM rule verified in `MIDI.DLL`**: if FM is selected, the base name is cut to at most **6 characters** and `fm` is
  appended (`sighted` -> `SIGHTEFM.MID`, `generic` -> `GENERIFM.MID`, `looking` -> `LOOKINFM.MID`). This confirms the
  hypothesis in `notes/music.md`. ✅
- **Looping**: the front end always calls the repeat setter with 0. The library maps `n <= 0` to a sentinel that means "restart
  when the tune ends, forever"; `n >= 1` means that many extra repeats. So **every glue tune loops until replaced or stopped**. ✅
  This includes the built-in tunes of the troop-selection, marching-order and debrief pages (`tactical`, `win`, `lose`): the same
  repeat setter with 0 is called before each of them (`notes/troop_selection.md` was corrected accordingly). ✅
- Loading a new tune first discards the previous one, so a `playmidi` over a playing tune is a hard cut. The library exports a
  fade-and-discard function, but neither the front end nor the game DLL ever calls it. ✅

### 2.3 Complete name table (every name used in the glue scripts, plus the ones the front end builds itself)

| Name | GM file | FM file | Where it is used | Uses |
|---|---|---|---|---|
| `title` | `TITLE.MID` | `TITLEFM.MID` | `[MIDI]` of the `MAINMENU` window (main menu) | 1 |
| `intro3` | `INTRO3.MID` | `INTRO3FM.MID` | `[MIDI]` of `OPTIONWINDOW`; also credits | 1 |
| `scribe` | `SCRIBE.MID` | `SCRIBEFM.MID` | `[MIDI]` of the caravan windows: `StartCaravan`, `CaravanSelectMission`, `CaravanAfterMission[WithRecruit]`, `CaravanAfterEncounter[WithRecruit]`, `CaravanContinueMission`, `CaravanRecruit*AndResume`, `CaravanDietrich`, `CaravanEcts`, `CaravanMs`, the `InfoCaravan*` set | 23 windows |
| `looking` | `LOOKING.MID` | `LOOKINFM.MID` | `addmidiobject` on the first campaign map (`FlowScriptBP01`), in `BPMission15`, `ZhufbarMission`, `EN4_SubScript2` | 4 |
| `sighted` | `SIGHTED.MID` | `SIGHTEFM.MID` | `playmidi` at `[START]` of **every briefing script** (45) and `RE7_SubScript1` | 46 |
| `generic` | `GENERIC.MID` | `GENERIFM.MID` | `playmidi` at `[START]` of mission scripts (48), and in ambush windows / subscripts (7) | 55 |
| `combat` | `COMBAT.MID` | `COMBATFM.MID` | ambush windows (Forest, Mountain, Snowy, Standard) and `BPMission5` | 5 |
| `tactical` | `TACTICAL.MID` | `TACTICFM.MID` | built into the front end: troop selection / marching order pages | - |
| `win`, `lose` | `WIN.MID`, `LOSE.MID` | `WINFM.MID`, `LOSEFM.MID` | built in: debrief page, chosen by the mission result | - |
| `stopmidi:` | - | - | 43 uses, before battles and cutscenes | 43 |

`LOOKIN2.MID` (a near-copy of `LOOKING`) and `LOOKING.MID` have no separate FM file (`LOOKINFM` serves both), so only
`looking` is reachable by name from the scripts. All files above exist in the installation. ✅

### 2.4 Music per campaign screen

| Screen | Music | How | Status |
|---|---|---|---|
| Main menu | `title` | window `[MIDI]` | ✅ |
| Options | `intro3` | window `[MIDI]` | ✅ |
| Caravan (all variants) | `scribe` | window `[MIDI]`, restarted on every entry | ✅ |
| Map with mission list | none of its own, except the very first map (`looking`); whatever played before keeps playing. After a caravan visit that is the caravan's `scribe` tune (`UnwindMission` and `PopAndResume` never touch the music; `PopContext` restarts a remembered tune only if one is set). After **Abort** from a briefing the map is silent | no `[MIDI]` on `MapWindow`; only `FlowScriptBP01` calls `addmidiobject`; Abort stops and discards the tune; restoring a saved window does not restart window music | ✅ (data, code) / 🟡 (first map after Abort; `scribe` carrying over is inferred from the absence of any stop) |
| Briefing | `sighted` | `playmidi` at `[START]` of the briefing script | ✅ |
| Troop selection / marching order | `tactical` | built in | ✅ |
| Debrief | `win` or `lose` | built in | ✅ |
| Mission script (map trail, encounters) | `generic`; `combat` in ambushes | `playmidi` | ✅ |
| Before a battle or cutscene | silence | `stopmidi:` | ✅ |

Order over one mission: caravan `scribe` -> (map, no change) -> briefing `sighted` -> troop selection `tactical` -> mission
script `generic` -> `stopmidi` -> battle (game DLL) -> cutscene -> `generic` again -> caravan `scribe`. 🟡 (order assembled
from the scripts and the built-in windows).

### 2.5 Pause

The Pause button of Dietrich's panel (label swaps to Resume) freezes text typing and all portrait / bitmap animation steps,
pauses the speech clip and pauses the MIDI tune; Resume undoes all of it. ✅ (§3.6)

## 3. Dialogue

### 3.1 Commands and state

| Command | Effect | Status |
|---|---|---|
| `settextcolor:<name>` | sets the **global** text colour (case-insensitive name, table in §3.4); it is read when text is drawn, so it takes effect for the next characters typed | ✅ |
| `settextalign:<left\|center\|right>` | text alignment of the dialogue block: `left` = 0 (default), `center` = 1, `right` = 2, anything else = 0; scripts only ever use `left` (14 uses, in ambush windows and encounter scripts); briefing scripts do not set it | ✅ |
| `set:textlines=<n>` | number of visible lines of the dialogue block; program default 1; the briefing scripts set 2 (and the caravan speech resets it to 2) | ✅ |
| `set:animseq=<n>` then `applyseq:res=<window>` | sets the animation sequence of every `[ANIM]` in that window: 1 = talking, 2 = stopped (the only values scripts use: 170 x 1, 304 x 2) | ✅ |
| `queuetoplaytext:res=<id>` | see below | ✅ |
| `playtext:res=<id>` | queue the text of BRTXT string `<id>` **and wait**: the script pauses until the text (and audio) are done | ✅ |

The two commands differ only when speech is **off**:

| Speech option | `queuetoplaytext` | `playtext` |
|---|---|---|
| on (speech engine available, sound option on) | starts the recording, queues the text, **waits** like `playtext` | same |
| off | queues the text **without waiting** (lines accumulate in the block) | queues and waits |

So a script `queuetoplaytext` x N + `playtext` shows N lines one at a time with audio, and as one accumulated block (two lines
visible, scrolling) without audio. ✅ The speech option is the same on/off switch as sound effects (Options "sound"); it
is not separately configurable. 🟡

### 3.2 Speech audio lookup (part c)

- Path: `binary/glue/speech/b<id>.wav`, where `<id>` is the decimal string written after `res=` in the script. In the
  installation these files live in **`REMOTE/BINARY/GLUE/SPEECH/B<id>.WAV`** (case-insensitive). The same lookup call is
  used as for music; the GOG install resolves this one from the `REMOTE` tree. ✅
- The directory holds 567 files: 501 `B*` (glue and battle lines), 65 `A*` (cutscene lines, not used here) and one
  effect. The number equals the string id in `BRTXT.DLL` (`notes/scene_scripts.md`). Format: PCM mono 22 050 Hz 16-bit;
  the RIFF size field of most files is wrong, so read the `data` chunk length (`notes/sfx.md`). ✅
- **Coverage**: all **331 distinct ids** used by `playtext` / `queuetoplaytext` in the 535 glue scripts have a `B<id>.WAV`. ✅
- Playback: the whole file is read into memory and played once through the sound device at the `setwavvolume` level; starting
  a line first stops the previous clip. If the clip cannot be loaded, the line is shown as text only. ✅ / 🟡 (fallback)
- Example: the first campaign briefing has nine recorded lines whose clips are 2.4 to 7.2 s long (about 44 s in total). ✅

### 3.3 Where and how the text is drawn

| Aspect | Rule | Status |
|---|---|---|
| Surface | the text is drawn into the **base glue window** (the map, 640x480), not into a portrait window | ✅ |
| Font | glue font slot **4** = `GLUE/SUBTEXT.FON` (serif, "subtitles for speech") | ✅ (`notes/fonts_glue.md`) |
| Position | block anchored at the **bottom** of the window: the bottom line's baseline is `1.5 x line height` above the bottom edge; each line above is `1.10 x line height` higher | ✅ |
| Alignment | `left` (default): left margin **5 %** of the window width; wrap when the current line plus the next word would exceed **90 %** of the width. `center` (`settextalign:center`, unused by scripts): the line is centred using the width of the text typed so far. `right` is stored but drawn as `left` | ✅ / 🟡 |
| Lines | `textlines` visible lines (1..n); new text types on the bottom line, older lines scroll **up** | ✅ |
| Drawing | transparent background; each string is drawn first in **black at every offset in a 5x5 square** (-2..2 px), then once in the colour: a 2 px black outline | ✅ |
| Buffer | a 1 024-character ring buffer per window; a line holds at most 127 characters | ✅ |
| Colour | global colour index; default 0 (black) until a script sets one | ✅ |

### 3.4 `settextcolor` name to RGB (front-end table, 16 entries)

| Index | Name | RGB | Index | Name | RGB |
|---|---|---|---|---|---|
| 0 | `black` | 0,0,0 | 8 | `gray` | 127,127,127 |
| 1 | `white` | 255,255,255 | 9 | `lgray` | 192,192,192 |
| 2 | `red` | 255,0,0 | 10 | `dkred` | 127,0,0 |
| 3 | `green` | 0,255,0 | 11 | `dkgreen` | 0,127,0 |
| 4 | `blue` | 0,0,255 | 12 | `dkblue` | 0,0,127 |
| 5 | `yellow` | 255,255,0 | 13 | `olive` | 127,127,0 |
| 6 | `magenta` | 255,0,255 | 14 | `purple` | 127,0,127 |
| 7 | `cyan` | 0,255,255 | 15 | `drab` | 0,127,127 |

An unknown name leaves the colour unchanged. Briefings use `red` for Dietrich and `green` for the Commander. ✅ (table read
from the executable's data, colour order verified)

### 3.5 Timing

Everything is driven by a **25 ms timer** on the main window (500 ms only while minimised). "Tick" below = one 25 ms quantum.
The timer handler computes how many quanta have elapsed and then does **one** step per message, not one per quantum, so on
a system that delivers timer messages more slowly than 25 ms (a Windows 95/98 machine: about 55 ms) everything runs
proportionally slower. The numbers are the designed rate. 🟡 (reading of the timer code)

| What | Constant | At 25 ms/tick | Status |
|---|---|---|---|
| Text typing step | one character per step, then a 1-tick pause -> **1 character every 2 ticks** | 20 characters/s | ✅ (structure) / 🟡 (exact rate) |
| Speech playing | text is stepped repeatedly until the typed fraction of the text is at least the audio's playback percentage | text follows the audio | ✅ |
| Gap between scroll-outs of remaining lines | **4 ticks** | 100 ms | ✅ |
| Final hold before the block clears, no speech | **30 ticks** | 0.75 s | ✅ |
| Final hold, speech was playing | **8 ticks** | 0.20 s | ✅ |
| Portrait sequences (§4) | one step per timer message; entry lasts `duration + 1` steps | see §4 | ✅ |
| Window `[BITMAP]` animations (`animstartframe`, `timecnt`, `looptimecnt`) | one step per **two** ticks: a frame lasts `(timecnt + 1)` x 50 ms; `looptimecnt` adds that many extra 50 ms steps when the loop wraps | Dietrich's reading loop (`looptimecnt=90`) waits 4.5 s, blink (`30`) 1.5 s | 🟡 (reading) |

### 3.6 How a line ends and how the player interacts

1. After the last character the block holds (30 or 8 ticks), lines scroll out (4-tick gaps), the block clears and, when a
   speech clip is playing, the code waits for the clip to finish. Then the glue script **resumes by itself**. ✅
2. **Left click** (button release) on the glue window, when no hotspot took the click and text is pending: the typing is
   fast-forwarded (pauses are skipped) until the next wrap or the end, the speech clip is stopped once all text is
   typed, and the script resumes if the block completed. A click on a hotspot (panel button) does not skip. ✅ / 🟡: for a
   one-line block the completion path itself waits for the clip to end, so the click may not cut the audio short there.
3. **Keyboard**: the glue window's key handler only records a hidden cheat key sequence. Keys do not advance dialogue. The
   application-level key input is an accelerator table (Ctrl+X, F2 in the test table) plus two start-up waits that Enter or a click
   ends. There is no Enter/Esc/Space handling for dialogue anywhere. ✅ (`notes/mission_selection.md` §4.3)
4. **Pause** (panel, `controlpanel=1`): §2.5. While paused the timer handler does nothing: no typing, no animation.
5. **Abort** (panel): stops speech, discards the music and forgets its name, ends the briefing script, destroys the briefing windows
   and pops the context stack back to the parked map (silent). ✅ (`notes/mission_selection.md` §4.2, §5, §8.1)
6. **Accept** (panel): drains (skips) any text still pending, stops speech and music, and opens troop selection; the briefing script is not
   resumed. ✅ (`notes/troop_selection.md`, `notes/mission_selection.md` §4.2)
7. **`setdemodefault:res=<name>`** (last command of every briefing, value `troopselect` or `BPBrief1`): the name, an enable
   flag and a "last activity" time are stored on the window (the time is refreshed on mouse movement), **but nothing in the
   executable reads them**: it is an inert leftover of a demo / attract mode. So a briefing does **not** auto-continue and
   has no idle timeout. ✅ (no reader found) / 🟡 (static analysis only)

## 4. Portrait animation during dialogue

The mouth and blink sequences, frame roles, tick length and the meaning of `animseq` / `applyseq` are specified in
**`notes/glue_portraits.md` §3** (sequence tables: §3.3, frame roles: §3.1); they are not repeated here. What matters for dialogue:

- The portrait that talks is the window named by the last `applyseq` with `animseq=1`; all other portraits in the scene are `animseq=2`.
  Talking is **scripted, not driven by the audio**: the scripts start and stop it explicitly around `queuetoplaytext`/`playtext`.
- "Stopped" shows base frame 0 plus the closed-mouth overlay and the blinking eyes, not frame 0 alone.
- Frame 2 is the open-eyes pose and frame 7 the closed (blink) pose (`glue_portraits.md` §3.1, verified visually).
- One animation step per glue timer message (25 ms nominal); with this timing a talking mouth frame lasts 75 ms and the blink flash 50 ms.

## 5. Portrait `index` -> sprite set

The table (glue index -> sprite set -> speaker, 37 entries, plus the `BACKALL` backdrop entry) is in **`notes/glue_portraits.md` §1**.
That note is authoritative; this section previously held a copy with the sprite-name-table entry numbers, which are
the same records seen from the other side (each record holds a sprite-table index, `notes/sprite_names.md`).

## 6. Data versus front-end constants

| Item | Class | Source |
|---|---|---|
| Which music plays when | DATA | `playmidi`, `addmidiobject`, `stopmidi`, window `[MIDI] name:` in the glue scripts |
| Name -> `binary/music/<name>.mid`, FM = first 6 characters + `fm` | TABLE (rule) | §2.2 |
| Music option 0/1/2 (off / FM / GM), loop forever, replace-on-play | ENGINE | §2.2 |
| `tactical`, `win`, `lose` music, `title`/`intro3`/`scribe` windows | TABLE + DATA | built-in windows (§2.3) |
| Which strings are spoken, in which order, in which colour | DATA | `playtext` / `queuetoplaytext` + `settextcolor` in the briefing script; text from `BRTXT` |
| Number of visible lines | DATA | `set:textlines` (default 1) |
| Speaker portrait state | DATA | `set:animseq` + `applyseq`, `[ANIM] index/bkindex/controlpanel` |
| Speech file per line | DATA (+ rule) | `binary/glue/speech/b<id>.wav` from `res=<id>` |
| Text font slot, bottom anchoring, 5 % / 90 % margins, 1.5 x and 1.10 x line spacing, 2 px outline; `settextalign` (default left) | TABLE + DATA | §3.1, §3.3 |
| Colour names -> RGB | TABLE | §3.4 |
| Typing rate (1 char / 2 ticks), scroll gap 4, hold 30 / 8, tick = 25 ms | TABLE | §3.5 |
| Portrait mouth / eye sequences | TABLE | `notes/glue_portraits.md` §3 |
| Glue index -> sprite set | TABLE | `notes/glue_portraits.md` §1 |
| `setdemodefault`, `[DEMODEFAULT]` | DATA, unused | §3.6 |

## 7. What `whshr/briefing.py` and the briefing scene / view should read

The loader already carries the map window, the sub-windows (`parse_window_portrait`), overlays, and one turn per string.
Per the current tree it should additionally take from data:

1. **Music**: return the `playmidi` name(s) of the briefing script (`sighted`) and let the scene ask the audio layer for
   `binary/music/<name>.mid` (GM by default), looping, replacing the caravan tune, stopping only on the next `playmidi` /
   `stopmidi`. Do not add a fade. Caravan windows restart `scribe` on entry.
2. **Turn data**: keep the string **id** per turn (the current turn has only text), so the scene can look up
   `B<id>.WAV` in the installation, and record the `set:textlines` value and the **colour name** in effect (map it with the
   §3.4 table; keep the name, not just an RGB, in the data).
3. **Speaker**: the portrait that talks is the window named by the last `applyseq` with `animseq=1`; every other portrait in the
   scene is `animseq=2`. Both keep blinking.
4. **Portrait art**: resolve `index` with the table in `notes/glue_portraits.md` §1 (not a per-speaker constant), draw base frame 0,
   then the two overlay channels from its §3 sequences; `bkindex` selects the `BACKALL` frame (palette: its §2.1).
5. **Font**: the briefing text uses glue font slot **4** (`glue_font_asset(4)`, `SUBTEXT`). The scene currently loads the
   battle font `PCTEXTA`; that is not the original's choice.
6. **Pacing**: replace "click or Enter advances" by the original model: type at 1 character / 2 ticks, hold 30 ticks
   (8 with audio), then advance by itself; with audio, finish when the clip ends and drive the typed fraction by playback
   progress. Keep click as a fast-forward and add Pause / Resume (which pauses text, animation, speech and music).
7. **End of the briefing**: after the last line stay on the briefing screen until the player presses **Accept** (troop
   selection) or Abort; do not continue automatically. `setdemodefault` can be parsed and ignored.
8. **Layout**: draw the text on the map window at the bottom, left margin 5 %, wrap at 90 %, outline 2 px; the position
   comes from the map window's size (`[POSITION] vx/vy`), not from constants of the 640x480 case.
9. **No speech / no audio device**: keep the two-mode rule of §3.1 (`queuetoplaytext` accumulates instead of waiting).

## 8. Open questions

Resolved since the first version: music after Abort (silent, §2.1/§2.4), a global keyboard handler (none for dialogue, §3.6), which eye
frame is closed (7, `glue_portraits.md`), what the remembered tune name is used for (§2.1). Full register: `ROADMAP.md`.

- 🟡 Effective step rate: designed 25 ms, but the timer code steps once per message; the original ran at whatever the OS timer gave
  (about 55 ms on Windows 9x). A runtime capture (Wine, timing a briefing) would settle what the original felt like.
- 🟡 Click during a single-line block with audio: the completion path waits for the clip to end; check whether the audio can
  be cut by a click in the real game.
- 🟡 Music on the first campaign map after Abort (its window carries its own tune).
- ⬜ Meaning of the two remaining fields of the glue-index table (`glue_portraits.md` §6).
- ⬜ Overlay frames of the 6- and 7-frame portraits (`Dwarf1`, `Treeman`, ...) against the kind-5 sequences.
- ⬜ Default music option on a fresh install (no saved options string): GM is a guess.
- ⬜ Whether `setdemodefault` is read by an out-of-tree demo build; it is inert here.
