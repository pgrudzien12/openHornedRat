# Roadmap — from file formats to an open engine

End goal: an engine/viewer that reads files from a **legally owned installation** of the game
(like OpenMW/OpenRA) and never contains or distributes its assets.

Legend: **S** = hours, **M** = 1–3 evenings, **L** = weeks.
✅ done, 🟡 partial, ⬜ to do. Format details: `FORMATS.md`; full reports: `notes/`.

## Overview — what is in the installation

| Area | Files | Size | Status | Kind |
|---|---|---|---|---|
| Sprites, backgrounds, plan maps | `BINARY/*.FOL/.BOP/.PAL` | 21 MB | ✅ incl. animation layout | custom, reverse-engineered |
| Script names → files | tables in `WHSHR.EXE`/`GAMEF.DLL` | — | ✅ | static data tables |
| Battle and army scripts | `SCRIPT/*.BTS/.MRC`, `SAVE/*.MRC/.dbf` | 1.6 MB | ✅ syntax / 🟡 semantics | INI-like text |
| Campaign flow ("glue" scripts) | `DLL/WND.DLL` (535 text resources) | 0.4 MB | ✅ extracted / 🟡 semantics | INI-like text in PE resources |
| Mission logic | `SCRIPT/BFxxx.DLL` (45) | 1.1 MB | ⬜ | x86 code, disassembly |
| Battle terrain and 3D resources | `MESH/*/GRND.GD`, `*.PBX` | 25 MB | ✅ | RNC ProPack container, Reality Lab textures/meshes, height field |
| Music | `MUSIC/*.MID` + `SOUND/WARINTR3.SBK` | 1.5 MB | ✅ formats / 🟡 not listened to | **standard** MIDI + SoundFont **1.0** bank (3 presets) on top of the AWE32 GM ROM |
| Effects and speech | `SOUND/**/*.WAV` (96), `GLUE/SPEECH/*.WAV` (567), `*.SFX` (18) | 128 MB | ✅ formats / 🟡 not listened to | standard WAV; `.SFX` = `MSNDDS.DLL` effect packages |
| Videos/cutscenes | `REMOTE/BINARY/ANIM/*.SI/.SR/.SM/.SN` (4×30) | 135 MB | ✅ containers / 🟡 event semantics | Mindscape Omni 1.0 + Smacker 640×272 at 8 fps + WAV + MIDS + event tracks |
| UI bitmaps, texts, cursors | `DLL/BITMAP.DLL`, `*TXT.DLL`, `DLGGMTXT.DLL`, `GMCUR.DLL` | 11 MB | ✅ | **standard** PE resources |
| Fonts, UI palettes | `*.FON`, `GLUE/*.PAL` | 0.6 MB | ✅ | standard NE/FNT fonts; `GLUE` 10–105 + `WIND` 106–245 palette halves |
| `SPRITE3.BTP` | 1 file | 64 KB | ✅ | not a LUT: a copy of 32 raw frames of `SPRITE3.BOP` (developer leftover) |
| Save games | `SAVE/savegame.0/.5` | 0.4 MB | ⬜ | custom binary |
| Game rules, script interpreter | `WHSHR.EXE`, `GAMEF.DLL` | 0.9 MB | ⬜ | x86 code, disassembly |

`UPDATE/BINARY` is a byte-identical copy of the top level of `FILE/BINARY` (731 files, no
differences); in the GOG version the patch changes nothing.

---

## Phase 0 — tooling cleanup (S–M)

Why: every following step uses the same paths, decoders and tests. The format work has produced
about 30 standalone scripts, each with its own `--check`; they now need to be consolidated.

- ✅ `git init` + `.gitignore` (no game files or extracted assets: `samples/`, `battles/`, `extracted/`).
- ⬜ A `whshr/` package instead of loose scripts: `paths.py` (case-insensitive lookup, UPDATE before
  FILE), `image.py` (PNG, GIF, palettes), `sprites.py` (FOL/BOP incl. the color-map index rule and
  legacy layouts), `script.py` (BTS/MRC/glue), `rnc.py`/`pbx.py`, `audio.py`, `si.py`. The current
  `scripts/*.py` become thin CLIs.
- ⬜ `whshr check` as one regression test calling the existing checks (sprites, scripts, PBX/RNC, GD,
  SFX/WAV, FON, SI/SN/SM/SR, MIDI/SBK), skipping the known orphans (`ICONSTMP.FOL`, `SPRITE30.BOP`).
- ⬜ `whshr extract <installation> <cache>`: one entry point for the extractors that already exist
  (`pe_extract`, `pbx_extract`, `si_omni --extract`, `anim_export`, `sfx_parse --json`…).

## Phase 1 — 2D assets, texts and sound

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 1.1 | PE resources from `DLL/*.DLL` (bitmaps, strings, dialogs, cursors, glue scripts) | ✅ | S | 1669 resources extracted; bitmaps viewed |
| 1.2 | Music: `.MID` + `WARINTR3.SBK` | 🟡 | S | formats and bank mapping done, SF1 → SF2 converter written; **full render and listening pending** (needs fluidsynth, a GM soundfont, ffmpeg) |
| 1.3 | `.SFX` effect packages ↔ WAV | ✅ | M | all 18 packages and 663 WAVs checked structurally; listening pending |
| 1.4 | Script names → sprite files and 3D objects | ✅ | M | name tables decoded; all campaign names resolve; `,N` meaning open |
| 1.5 | Animation layout of directional sprites | ✅ | M | groups × phases × 8 directions, standard move/dead/attack/stand/shoot; sheets and GIFs |
| 1.5a | `dir` 0..511 → direction index, frame timing, anchor y | ⬜ | S–M | compare with the running game under Wine |
| 1.5b | Effect sprite layouts: `SPELLS`, `GENBATT`; which `SPELLS` map belongs to which spell | ⬜ | M | |
| 1.6 | `.FON` and `GLUE` palettes | ✅ | S | menu text rendered; open: font → UI element, `GAME`/`OPT`/`REND` palettes |
| 1.7 | `SPRITE3.BTP` and sprite leftovers | ✅ | S | not a LUT; legacy `.FOL` layouts; `SPELLS` map index rule |
| 1.8 | Script field semantics | 🟡 | M | objective letters solved, `A`/`Z` numbers mostly; open: other letters' numbers, `set:map`, `whoami`, `,N` |
| 1.9 | **Glue script parser and campaign flow graph** (`WND.DLL`: `FLOWSCRIPT*` → `MISSION*WINDOW` → `*BRIEF*` → `*MISSION*` → `BFxxx`, movies, cash) | ⬜ | M | new: the campaign flow is readable text, which lowers the risk of 4.2/4.4 and M6 |
| 1.10 | Listening checks for music, effects (with `pitch`) and speech | ⬜ | S | needs audio tools installed by the user |

**Milestone M1: asset browser.** The data side is ready (sprites with animations, maps, UI bitmaps,
texts, fonts, music, sounds); what is missing is one tool that shows it all.

## Phase 2 — 3D battle

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 2.1 | RNC ProPack method 2 + `.PBX` container | ✅ | M | 133/133 files, CRCs, textures and meshes rendered |
| 2.2 | `GRND.GD` terrain height field | ✅ | M | 45 files; relief matches the plan maps; open: height scale |
| 2.3 | Static battle scene: textured terrain (`grnd.xof`), scenery meshes from `placefurniture` (furniture table), unit sprites at their positions, heights from `GRND.GD` | ⬜ | M | **unblocked**; open inputs: `dir` of scenery, mesh pivots, texture transparency |
| 2.4 | Camera and lighting (`Camera`, `CameraEdge`, `Bank angle`) | ⬜ | M | framing as in the game; also verifies the height scale |
| 2.5 | Relation of `GRND.GD` to `grnd.xof` (logic height field vs render mesh?) | ⬜ | S | |

**Milestone M2: static 3D battle viewer.** Any `BFxxx`: terrain, scenery, units at their starting positions.

## Phase 3 — cutscenes and speech (REMOTE)

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 3.1 | `.SI` container | ✅ | M | 30/30 files fully covered; films, sounds, MIDI, event tracks extracted |
| 3.2 | Smacker playback | ✅ | S | pure-Python decoder; frames viewed; play at 125 ms per frame |
| 3.3 | `.SR/.SM/.SN` and scene timeline | 🟡 | M | side files decoded; open: event (`EVT`) semantics (speaker, fade), verify by watching under Wine |
| 3.4 | Speech ↔ texts ↔ scenes | 🟡 | M | `A*.WAV` ↔ `ANTXT` ids ↔ scenes done; open: `B*.WAV` lines ↔ portraits and missions |

## Phase 4 — game logic (hardest; disassembly)

Tool: Ghidra (32-bit PE, MSVC 1995). Order from lowest risk:

| # | Task | Size |
|---|---|---|
| 4.1 | Mission DLL interface: what `DLLGetScriptPointer`/`DLLReturnInstCount` return, which game APIs the scripts call (on the small `BF001.DLL`); which units the DLL spawns (units packed in `SPRITES.PBX` but missing from the `.BTS`) | M |
| 4.2 | In `GAMEF.DLL`/`WHSHR.EXE`: the `.BTS/.MRC` command interpreter and the glue language semantics (syntax and content already known from 1.9) | M–L |
| 4.3 | Combat rules: how `s_move`, `s_armr`, `psy_status`, ranks and morale feed into the calculations (compare with the Warhammer Fantasy Battle 4th ed. rules) | L |
| 4.4 | Save games `savegame.0/.5` + campaign state (`ARMY/MARCH/PLAY.MRC`, `debrief.dbf`, gold, mercenaries) | M–L |
| 4.5 | Rewriting the 45 mission scripts into our own readable format (DSL/Python/Lua) | L, spread over time |
| 4.6 | Game events → sound effect indices and battle music choice (`battle`, `tense`, `victory`…); runtime palette choice per screen | M |

Supporting alternative: **instrumentation under Wine** (logging file opens, script API calls,
`MIDI_InitTune` arguments during play) to confirm hypotheses from Ghidra and several open questions
from phases 1–3.

## Phase 5 — engine

- **Tools and extraction**: stay in Python (the `whshr/` package).
- **Prototype**: Python + pygame (2D: plan map + animated sprites) as a quick testbed for movement,
  animation and collisions with `OBJECTS`/`BOUNDARIES`. Does not require phase 2.
- **Target**: an engine reading the game installation on the fly, e.g. C++/SDL2 + OpenGL or Godot
  (GDExtension for reading the formats). Decide after M2, once it is clear how much 3D is really needed.
- Audio in the engine: MIDI through the user's GM soundfont + the converted SBK in bank 1 (GM file
  preferred, FM name rule `name[:6] + 'FM'`); SFX = PCM resampled to `pitch`, volume/pan, loop/list/random,
  priority channels.

Milestones:
- **M3**: units walk across the map (pathfinding with `Nav*`, collisions), directional animations.
- **M4**: combat and morale according to the rules from 4.3, compared with the original under Wine.
- **M5**: one playable mission (`BF001`) with a hand-rewritten script.
- **M6**: campaign (glue flow from 1.9, army between battles, briefings, movies, save games).

---

## Proposed order of the next steps

1. **Phase 0**: consolidate the ~30 scripts into the `whshr/` package with one `check` and one `extract`.
2. **1.10 listening check** (install fluidsynth, a GM soundfont and ffmpeg): hear the original music,
   which was the missing piece under Wine, plus effects and speech.
3. **2.3 static 3D battle viewer (M2)**: every input format is decoded now.
4. **1.9 glue scripts → campaign flow graph**, the data side of M6.
5. **Wine instrumentation session** for 1.5a, 3.3 and the smaller open questions (`dir`, frame timing,
   event semantics, which files are loaded).
6. Phase 4 only before M4/M5, at first targeted at specific questions.

## Risks and rules

- **Legal**: the repo contains only code and descriptions. Extracted files stay local:
  `samples/`, `battles/` and `extracted/` are in `.gitignore`.
- **Visual/audible verification** of every hypothesis, rather than "the byte count matches".
  Audio has so far only been checked structurally.
- **Speech and videos** are the largest volume of data (263 MB), but the least important for
  gameplay.
- **Logic in native DLLs** is the main risk of the project. Without it we will have a "viewer", not a
  "game". The campaign flow itself turned out to be text (glue scripts), which reduces this risk.
