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
| Music | `MUSIC/*.MID` + `SOUND/WARINTR3.SBK` | 1.5 MB | ✅ formats, all 21 tracks rendered | **standard** MIDI + SoundFont **1.0** bank (3 presets) on top of the AWE32 GM ROM |
| Effects and speech | `SOUND/**/*.WAV` (96), `GLUE/SPEECH/*.WAV` (567), `*.SFX` (18) | 128 MB | ✅ formats and listening review | standard WAV; `.SFX` = `MSNDDS.DLL` effect packages |
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
- ✅ A `whshr/` package: path, image, sprite, script, RNC, PBX, audio, and SI implementations
  live in the package. The current `scripts/*.py` remain supported as thin compatibility CLIs.
- ✅ `whshr check` as one regression test calling the existing checks (scripts, PBX/RNC, GD,
  SFX/WAV, FON, SI/SN/SM/SR, MIDI/SBK). The existing sprite checks, including their known
  `ICONSTMP.FOL` and `SPRITE30.BOP` exceptions, remain a separate migration task.
- ✅ `whshr extract <installation> <cache>`: one entry point for the extractors that already exist
  (`pe_extract`, `pbx_extract`, `si_omni --extract`, `anim_export`, `sfx_parse --json`…).

## Phase 1 — 2D assets, texts and sound

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 1.1 | PE resources from `DLL/*.DLL` (bitmaps, strings, dialogs, cursors, glue scripts) | ✅ | S | 1669 resources extracted; bitmaps viewed |
| 1.2 | Music: `.MID` + `WARINTR3.SBK` | ✅ | S | formats and bank mapping done; SBK stems listened to and confirmed; all 21 tracks rendered with FluidSynth (uniform gain, no clipping) |
| 1.3 | `.SFX` effect packages ↔ WAV | ✅ | M | all 18 packages and 663 WAVs checked structurally; listening review complete under 1.10 |
| 1.4 | Script names → sprite files and 3D objects | ✅ | M | name tables decoded; all campaign names resolve; `,N` meaning open |
| 1.5 | Animation layout of directional sprites | ✅ | M | groups × phases × 8 directions, standard move/dead/attack/stand/shoot; sheets and GIFs |
| 1.5a | `dir` 0..511 → direction index, frame timing, anchor y | 🟡 | S–M | `dir` is clockwise from +Y (BTS statistics, scenery vs plan maps); zero frame, timing and anchor y need the running game under Wine |
| 1.5b | Effect sprite layouts: `SPELLS`, `GENBATT`; which `SPELLS` map belongs to which spell | ⬜ | M | |
| 1.6 | `.FON` and `GLUE` palettes | ✅ | S | menu text rendered; open: font → UI element, `GAME`/`OPT`/`REND` palettes |
| 1.7 | `SPRITE3.BTP` and sprite leftovers | ✅ | S | not a LUT; legacy `.FOL` layouts; `SPELLS` map index rule |
| 1.8 | Script field semantics | 🟡 | M | objective letters solved, `A`/`Z` numbers mostly; `setstats` unit fields and `psy_status` bits resolved from `GAMEF.DLL` (`notes/game_rules.md`); open: other letters' numbers, `set:map`, `whoami`, `,N` |
| 1.9 | **Glue script parser and campaign flow graph** (`WND.DLL`: `FLOWSCRIPT*` → `MISSION*WINDOW` → `*BRIEF*` → `*MISSION*` → `BFxxx`, movies, cash) | ✅ | M | full parser and graph builder in `whshr.campaign`, JSON/DOT/Markdown export, verified against all 33 mission windows and 17 flow scripts |
| 1.10 | Listening checks for music, effects (with `pitch`) and speech | ✅ | S | project owner reviewed the full music renders, effects with `pitch` applied, and speech |

**Milestone M1: asset browser.** The data side is ready (sprites with animations, maps, UI bitmaps,
texts, fonts, music, sounds); what is missing is one tool that shows it all.

## Phase 2 — 3D battle

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 2.1 | RNC ProPack method 2 + `.PBX` container | ✅ | M | 133/133 files, CRCs, textures and meshes rendered |
| 2.2 | `GRND.GD` terrain height field | ✅ | M | 45 files; relief matches the plan maps; open: height scale |
| 2.3 | Static battle scene: textured terrain (`grnd.xof`), scenery meshes from `placefurniture` (furniture table), unit sprites at their positions, heights from `GRND.GD` | ✅ | M | `whshr viewer` renders a static PNG (perspective, or orthographic for diagnostics); scenery rotation verified against plan maps; texture transparency provisional |
| 2.4 | Camera and lighting (`Camera`, `CameraEdge`, `Bank angle`) | ✅ | M | sufficient for an engine: the original camera is perspective, and the look-at camera (yaw, pitch, distance, FOV) with ambient/diffuse PBX-normal lighting in `viewer`/`viewer-web` reproduces the scene convincingly. Exact original parameters (`Camera` → heading, hypothesis `yaw = 180 + Camera`; FOV, eye height, lighting) are deliberately not pursued |
| 2.5 | Relation of `GRND.GD` to `grnd.xof` (logic height field vs render mesh?) | ✅ | S | all 44 modern terrain meshes match direct `GRND.GD(x,z)` heights (maximum error 0.02123 mesh units) |

**Milestone M2: static 3D battle viewer.** Any `BFxxx`: terrain, scenery, units at their starting positions.
✅ **Reached (September 2026)**: `whshr viewer`/`viewer-web` confirm that an engine can use a similar
perspective battle scene.

## Phase 3 — cutscenes and speech (REMOTE)

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 3.1 | `.SI` container | ✅ | M | 30/30 files fully covered; films, sounds, MIDI, event tracks extracted |
| 3.2 | Smacker playback | ✅ | S | pure-Python decoder; frames viewed; play at 125 ms per frame |
| 3.3 | `.SR/.SM/.SN` and scene timeline | 🟡 | M | side files decoded; open: event (`EVT`) semantics (speaker, fade), verify by watching under Wine |
| 3.4 | Speech ↔ texts ↔ scenes | 🟡 | M | `A*.WAV` ↔ `ANTXT` ids ↔ scenes done; open: `B*.WAV` lines ↔ portraits and missions |

## Phase 4 — game logic (hardest; disassembly)

Tool: Ghidra 12.1 headless (32-bit PE, MSVC 1995); optional setup and helper scripts in
`tools/ghidra/`. Order from lowest risk:

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 4.1 | Mission DLL interface: what `DLLGetScriptPointer`/`DLLReturnInstCount` return, which game APIs the scripts call (on the small `BF001.DLL`); which units the DLL spawns (units packed in `SPRITES.PBX` but missing from the `.BTS`) | 🟡 | M | the DLLs are bytecode tables: mission unit scripts from id 0 (3–37 per DLL, selected by `set:script=N`), 100–170 a shared library identical in all 45 DLLs, run by a 232-opcode interpreter in `GAMEF.DLL`; `DLLReturnInstCount` = format check; events and morale opcodes named (`notes/game_rules.md`); open: remaining opcodes |
| 4.2 | In `GAMEF.DLL`/`WHSHR.EXE`: the `.BTS/.MRC` command interpreter and the glue language semantics (syntax and content already known from 1.9) | 🟡 | M–L | keyword → token tables, instruction lookup and the editor's unit writer located; `setstats` byte layout established (`notes/game_rules.md`); the section readers and the glue interpreter not traced |
| 4.3 | Combat rules: how `s_move`, `s_armr`, `psy_status`, ranks and morale feed into the calculations (compare with the Warhammer Fantasy Battle 4th ed. rules) | 🟡 | L | established from code: WFB 4th ed to-hit/to-wound/save charts, armour codes, weapon classes, mounts, magic items, Initiative strike order, combat resolution (uncapped rank bonus, flank/rear), break/panic/fear/terror/rally/pursuit, flat 2–12 Leadership roll, shooting scatter by BS, reload, ranges (24 units per inch), misfires; `python3 -m whshr check` verifies tables and stat layout. Open points register R1–R31 with next steps in `notes/game_rules.md` §11; resolved so far: R1–R10, R12–R27, R29–R35, R39–R45 (charge bonus, monster return blows, battle-grid pairing and timing, events, flank/rear test, fear/terror flight, rout, pursuit, rally schedule, missiles, special weapons, fanatics, command panel and orders, regeneration, mounts, Initiative 20, real time, movement and speeds, script selection, magic: power pools, casting, every spell, dispel, items); decisions for an engine: R11, R33; top remaining: behaviour opcode catalogue and a `whshr` disassembler (R38, R51; batch 3 planned in `notes/game_rules.md` §11.7, interrupted by the spend limit); to confirm under Wine: R52, R53 |
| 4.4 | Save games `savegame.0/.5` + campaign state (`ARMY/MARCH/PLAY.MRC`, `debrief.dbf`, gold, mercenaries) | ⬜ | M–L | |
| 4.5 | Rewriting the 45 mission scripts into our own readable format (DSL/Python/Lua) | ⬜ | L, spread over time | alternative now possible: an engine-side interpreter for the original bytecode once the opcodes are catalogued |
| 4.6 | Game events → sound effect indices and battle music choice (`battle`, `tense`, `victory`…); runtime palette choice per screen | ⬜ | M | |

Supporting alternative: **instrumentation under Wine** (logging file opens, script API calls,
`MIDI_InitTune` arguments during play) to confirm hypotheses from Ghidra and several open questions
from phases 1–3.

## Phase 5 — engine

- **Architecture**: a data-first engine: original-installation readers -> normalized data -> deterministic
  headless simulation -> rendering/sound/input frontend. The full decision and constraints are in
  [`notes/engine_architecture.md`](notes/engine_architecture.md).
- **Tools, rules, and prototype**: keep `whshr` as the Python reference implementation for readers,
  validation, rule experiments, and an initial headless/real-time simulation prototype. Build M3 first
  as a Python testbed (plan map, animated sprites, movement, `Nav*`, `OBJECTS`/`BOUNDARIES`) whose
  simulation API does not depend on its presentation library. A local, never-committed asset cache is
  acceptable.
- **Runtime**: prefer a custom SDL2 frontend with a 3D renderer (initially OpenGL) after the prototype
  establishes actual requirements. SDL2 covers windowing, input, and audio, not rendering by itself.
  Godot may be used as a disposable visualization/prototyping client, but must not own the authoritative
  rules, assets, saves, or mod format.
- **Modding**: support ordered declarative data packages with stable namespaced identifiers, schemas,
  validation, dependencies, and deterministic merge/override rules. Original formats remain vanilla
  inputs, not the public mod authoring format. Defer a sandboxed, versioned mission scripting API until
  declarative data cannot express a required feature; do not accept arbitrary native plug-ins initially.
- **Original mission DLLs**: never execute `SCRIPT/BFxxx.DLL` as native code. Read their bytecode tables
  as data and implement the original interpreter for vanilla compatibility. New mission content will use
  a readable normalized mission format once the opcode/event model is established.
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

Phase 2 is closed (M2 reached). Priorities, as decided by the project owner:

1. **Game rules first (4.3, with the parts of 4.2 they need)**: targeted disassembly of
   `GAMEF.DLL`/`WHSHR.EXE` for combat, morale and how the `s_*` unit stats, ranks and `psy_status`
   feed into the calculations, compared with Warhammer Fantasy Battle 4th edition. 1.8 (script field
   semantics) is resolved along the way where the rules need it. **First pass done (September 2026):**
   stat layout, close combat, combat resolution, morale and the shooting mechanics are established in
   `notes/game_rules.md`; research batches A–F (September 2026) then resolved most open points,
   including the unit behaviour bytecode, movement, real time and magic. Next: batch 3 (§11.7 of the notes:
   behaviour opcode catalogue, `whshr` script disassembler, small leftovers).
2. **Real-time engine prototype (nice to have)**: choose the technology (see phase 5), then show the
   `viewer-web` scene (terrain, scenery, sprites, moving camera) in real time. Independent of 1, so
   it can run in parallel.
3. **Later**: unit movement (M3: `Nav*` pathfinding, `OBJECTS` collisions, formations), mission DLLs
   (4.1), a Wine instrumentation session for 1.5a/3.3 and other open questions only when one blocks
   work, 1.5b effect sprites once magic is needed, save games (4.4) for M6.

## Risks and rules

- **Legal**: the repo contains only code and descriptions. Extracted files stay local:
  `samples/`, `battles/` and `extracted/` are in `.gitignore`.
- **Visual/audible verification** of every hypothesis, rather than "the byte count matches".
  Music, pitched effects, and speech have received a listening review.
- **Speech and videos** are the largest volume of data (263 MB), but the least important for
  gameplay.
- **Logic in native DLLs** is the main risk of the project. Without it we will have a "viewer", not a
  "game". The campaign flow itself turned out to be text (glue scripts), which reduces this risk.
