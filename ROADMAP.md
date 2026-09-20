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
| 1.8 | Script field semantics | 🟡 | M | objective letters solved, `A`/`Z` numbers mostly; `setstats` unit fields and `psy_status` bits resolved from `GAMEF.DLL` (`notes/game_rules.md`); objective table, evaluation passes and objective G found (per-letter evaluators not read); open: other letters' numbers, `set:map`, `whoami`, `,N` |
| 1.9 | **Lossless glue importer and campaign flow projection** (`WND.DLL`: typed programs/window records, source locations, coverage; `FLOWSCRIPT*` → `MISSION*WINDOW` → `*BRIEF*` → `*MISSION*` → `BFxxx`, movies, cash) | ✅ | M | `whshr.glue` imports and classifies all 535 resources; graph builder in `whshr.campaign`, JSON/DOT/Markdown export, verified against all 33 campaign mission windows and 17 flow scripts |
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
| 3.3 | `.SR/.SM/.SN` and scene timeline | 🟡 | M | side files decoded; opening captions and movie assets are present across A1–A27. TODO: replace the A1-specific frontend with a generic `.SI` player that runs caption/prologue states plus event (`EVT`) semantics (speaker, fade); verify under Wine |
| 3.4 | Speech ↔ texts ↔ scenes | 🟡 | M | `A*.WAV` ↔ `ANTXT` ids ↔ scenes done; open: `B*.WAV` lines ↔ portraits and missions |

## Phase 4 — game logic (hardest; disassembly)

Tool: Ghidra 12.1 headless (32-bit PE, MSVC 1995); optional setup and helper scripts in
`tools/ghidra/`. Order from lowest risk:

| # | Task | Status | Size | Verification / notes |
|---|---|---|---|---|
| 4.1 | Mission DLL interface: what `DLLGetScriptPointer`/`DLLReturnInstCount` return, which game APIs the scripts call (on the small `BF001.DLL`); which units the DLL spawns (units packed in `SPRITES.PBX` but missing from the `.BTS`) | 🟡 | M | the DLLs are bytecode tables: mission unit scripts from id 0 (3–37 per DLL, selected by `set:script=N`), 100–170 a shared library identical in all 45 DLLs, run by a 232-opcode interpreter in `GAMEF.DLL`; `DLLReturnInstCount` = format check; all 232 opcodes catalogued and a disassembler with a check (`python3 -m whshr scripts`, `notes/game_rules.md`); per-battle survey of all mission scripts done: only fanatics are spawned, extra `SPRITES.PBX` files are `loadspr` terrain animations (batch 4 J) |
| 4.2 | In `GAMEF.DLL`/`WHSHR.EXE`: the `.BTS/.MRC` command interpreter and the glue language semantics (syntax and content already known from 1.9) | 🟡 | M–L | keyword → token tables, instruction lookup and the editor's unit writer located; `setstats` byte layout established (`notes/game_rules.md`); the section readers and the glue interpreter not traced |
| 4.3 | Combat rules: how `s_move`, `s_armr`, `psy_status`, ranks and morale feed into the calculations (compare with the Warhammer Fantasy Battle 4th ed. rules) | 🟡 | L | established from code: WFB 4th ed to-hit/to-wound/save charts, armour codes, weapon classes, mounts, magic items, Initiative strike order, combat resolution (uncapped rank bonus, flank/rear), break/panic/fear/terror/rally/pursuit, flat 2–12 Leadership roll, shooting scatter by BS, reload, ranges (24 units per inch), misfires; `python3 -m whshr check` verifies tables and stat layout. Open points register R1–R31 with next steps in `notes/game_rules.md` §11; resolved so far: R1–R10, R12–R27, R29–R35, R39–R45 (charge bonus, monster return blows, battle-grid pairing and timing, events, flank/rear test, fear/terror flight, rout, pursuit, rally schedule, missiles, special weapons, fanatics, command panel and orders, regeneration, mounts, Initiative 20, real time, movement and speeds, script selection, magic: power pools, casting, every spell, dispel, items); decisions for an engine: R11, R33; batch 3 done (opcode catalogue, `whshr scripts` disassembler, R41, R44, R46–R49, R51, R53, R54, R56–R58); batch 4 (`notes/research_plan.md`): L ✅ routes, collisions, visibility and AI scoring, J ✅ missions and objectives, K ✅ campaign and saves (row 4.4) merged; to confirm under Wine: R52 |
| 4.4 | Save games `savegame.0/.5` + campaign state (`ARMY/MARCH/PLAY.MRC`, `debrief.dbf`, gold, mercenaries) | ✅ | M–L | RIFF `WHSV` format decoded (reader prototype passes on both real saves), experience and promotions, balance-sheet payments, prices and retainers, wounded and disbanding, debrief flow (`notes/campaign.md`); open: meaning of some `Result:` values, per-mission debrief evaluators; runtime check by finishing BF003 under Wine (coffers 680) |
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
- **Runtime**: **Python is the engine language** (decided September 2026): pygame-ce (SDL2) for window,
  input and audio, zengl (OpenGL 3.3 core) for rendering, FluidSynth for MIDI. Readers, rules and the
  simulation stay stdlib-only; only the frontend subpackage has third-party dependencies. The earlier C++
  SDL2/OpenGL prototype is parked. Godot may be used as a disposable visualization client, but must not
  own the authoritative rules, assets, saves, or mod format.
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

The M6 implementation architecture and its phased, testable migration from the current screen-specific prototype are specified in **`notes/glue_runtime_architecture.md`**. The key boundary is one long-lived glue runtime for campaign windows and contexts, with battles, movies and executable-owned widgets invoked through typed request/result adapters.

---

## Proposed order of the next steps

Phase 2 is closed (M2 reached). Priorities, as decided by the project owner:

1. **Game rules first (4.3, with the parts of 4.2 they need)**: targeted disassembly of
   `GAMEF.DLL`/`WHSHR.EXE` for combat, morale and how the `s_*` unit stats, ranks and `psy_status`
   feed into the calculations, compared with Warhammer Fantasy Battle 4th edition. 1.8 (script field
   semantics) is resolved along the way where the rules need it. **First pass done (September 2026):**
   stat layout, close combat, combat resolution, morale and the shooting mechanics are established in
   `notes/game_rules.md`; research batches A–F (September 2026) then resolved most open points,
   including the unit behaviour bytecode, movement, real time and magic. Batch 3 (behaviour opcode catalogue,
   `whshr scripts` disassembler) is done, and so is batch 4 (missions and objectives,
   campaign progression and saves, AI/pathfinding/visibility; `notes/game_rules.md`, `notes/campaign.md`); the optional
   batch 5 and the leftovers are listed in `notes/research_plan.md`.
2. **Real-time engine prototype (nice to have)**: the technology is chosen (Python with pygame-ce and zengl, see phase 5). Engine phase 1 is in
   progress: `python3 -m whshr engine` plays the intro, menu and BF001 briefing into the BF001 battle, where
   player regiments move, fight, shoot and rout against a simple enemy AI up to a victory or defeat screen
   (steps 1-5 done, rules simplified); show the
   `viewer-web` scene (terrain, scenery, sprites, moving camera) in real time. Independent of 1, so
   it can run in parallel.
3. **Later**: unit movement (M3: `Nav*` pathfinding, `OBJECTS` collisions, formations), mission DLLs
   (4.1), a Wine instrumentation session for 1.5a/3.3 and other open questions only when one blocks
   work, 1.5b effect sprites once magic is needed, save games (4.4) for M6.

## Open research questions

One register of every open item (🟡 inferred, ⬜ unknown, ⚠ conflicting evidence) from the notes, so nothing is lost inside a
per-topic note. Each row: id, question, where it is documented, what engine feature it blocks, and how to settle it. Priority: **P1**
blocks a screen being built now (briefing, mission map, caravan, troop selection); **P2** blocks campaign correctness (progression, money,
outcomes); **P3** polish or curiosity. When an item is settled, fix the source note first, then delete the row here.

### A. Needs a running original (Wine observation)

The game reaches the menu, the campaign map and the first mission under Wine (no sound). One session covering the P1 rows below would
settle most of this group; audio questions cannot be observed without sound.

| Id | Question | Source | Blocks | Prio |
|---|---|---|---|---|
| A1 | ⚠ Does double-clicking a mission-list row run Brief? (code says yes; the owner observed no effect) | `mission_selection.md` §4.1 | list input | P1 |
| A2 | Default of `animrestartframe` when absent (lamp, candle, tent, blink loops): equals `animstartframe`? | `campaign_tent.md` §10 | all animated glue bitmaps | P1 |
| A3 | Real step rate of text/animation (25 ms designed vs the original's about 55 ms on Windows 9x) | `briefing_dialogue.md` §8, `glue_portraits.md` §3.2 | dialogue and portrait feel | P2 |
| A4 | Tent position on screen and draw order relative to the trail dots | `campaign_tent.md` §10 | briefing map | P1 |
| A5 | `bkindex=1` repaint semantics and the bitmap `Mask` name | `campaign_tent.md` §10 | animated bitmaps | P3 |
| A6 | Ctrl+click in troop selection: does hiring append to the selection, and does the roster-full sound play? | `troop_selection.md` §11 | troop selection | P2 |
| A7 | Banner frame and rank/`RingMark` icon placement on troop rows | `troop_selection.md` §3.3, §11 | troop selection | P2 |
| A8 | Abort in troop selection opened from a briefing: which screen does it return to? | `mission_selection.md` §5, §10 | flow | P2 |
| A9 | Does the list order chosen on the marching-order page affect initial deployment in the battle? | `troop_selection.md` §11 | battle setup | P2 |
| A10 | Do the taken flags of the other missions in a window survive save and load (predicted: no, an original bug)? | `campaign.md` §8 | save/load | P2 |
| A11 | Is the debrief payment added twice in modes 4 / 7? Finish `bf003` and compare `PLAY.MRC`/`ARMY.MRC`/coffers (predicted 680) | `campaign.md` §8 | economy | P2 |
| A12 | Clicking during a single-line spoken block: can the audio be cut short? | `briefing_dialogue.md` §8 | dialogue | P3 |
| A13 | Music on the first campaign map after Abort from a briefing; does `scribe` carry over from the caravan? | `briefing_dialogue.md` §8, `mission_selection.md` §10 | music | P3 |
| A14 | Zero point of the unit `dir` mapping; frame timing per action; hit moment of attack phases | `animations.md` | unit animation (M3) | P2 |
| A15 | Which palette rule applies where: `SetWinGPalette` (GLUE+WIND) vs the bitmap's own table; BOOK pair vs bitmaps embedding `GLUEREND` | `fonts_glue.md` §6, `troop_selection.md` §11 | glue bitmap colours | P2 |

### B. Static analysis of `WHSHR.EXE` / `GAMEF.DLL` (no running game needed)

| Id | Question | Source | Blocks | Prio |
|---|---|---|---|---|
| B1 | Decode the 7 per-mission debrief evaluator functions (42 table entries) and the four `Result:` values per objective type | `campaign.md` §8 | success/failure end screens, `testmission` branches (`REMISSION4`, `WEMISSION2`, `GMMISSION3`) | **done: `debrief_evaluation.md` (41 records, 8 evaluators, all `Result:` values)** |
| B2 | Objectives `G`, `Y`, `Z` as campaign-defeat conditions; text for "wounded could not be recovered" | `debrief_evaluation.md` §4 | game over | done (G partly, 🟡) |
| B3 | `testmission` falling through into `autosave` (jump table check) | `glue_interpreter.md` §3, `debrief_evaluation.md` | progression | done: confirmed at instruction level |
| B4 | The two `u32` per script in the save file's `STAX` chunk; `BKTXT 610` item finds (who uses it; roles of `FILE/SCRIPT/ARMY.MRC`, `REVARMY.MRC`) | `campaign.md` §8 | save/load, items | P3 |
| B5 | Stale caravan scroll count when a caravan is drawn between `closewindow` and the next `addobject` | `campaign.md` §8 | caravan scrolls | P3 |
| B6 | Accelerator commands: Ctrl+X = 16, F2 = 14 (test table) | `mission_selection.md` §10 | quit shortcut | P3 |
| B7 | `Attack!` (panel 4) sets the true/false status flag before the battle; what "drain text" does with its two flag values; whether Brief's push is skipped for windows with their own portraits | `mission_selection.md` §10 | encounters, briefing | P2 |
| B8 | What `Report` (panel 5, unused) does | `mission_selection.md` §10 | none (unused) | P3 |
| B9 | Meaning of `set:frame=3`; the second flag that pauses animation ticks; the two extra integers per portrait record | `glue_portraits.md` §6 | portrait animation | P3 |
| B10 | Suspension conditions of the animation step beyond the two global flags | `campaign_tent.md` §10 | animation | P3 |
| B11 | Font slot -> `.FON` mapping for the troop window's two fonts | `troop_selection.md` §11 | troop selection text | P1 |
| B12 | Open mode 1 of the troop window (P1 alone) and the destination after Done on the bankruptcy page | `troop_selection.md` §11 | edge flows | P3 |
| B13 | Layout of the reinforcements sub-window (only bitmaps and strings known); roster-book pages | `builtin_widgets.md` | recruit screens, books | done (pixel offsets 🟡) |
| B14 | Uses of `MarchOrderMove` / `MarchOrderMoveDone` names | `troop_selection.md` §11 | troop selection | P3 |
| B15 | Where `BATTLE`, `FOREST`, `LOOKIN2`, `TENSE`, `VICTORY` music plays; how the Omni player resolves `musicawe\` / FM; default music option on a fresh install | `music.md` | battle and cutscene music | P2 |
| B16 | Which screens use `GLUEGAME`/`WINDGAME` and `GLUEOPT`/`WINDOPT`; why `GLUEREND.PAL` exists | `palette_selection.md` §6 | options screen colours | done: none use them; `GLUEREND` is an orphan |
| B17 | SF1 filter/envelope units for the AWE32 soundfont bank; drum-channel kits for `INTRO3`/`TITLE` | `music.md` | music rendering fidelity | P3 |

### C. Data grep and visual checks

| Id | Question | Source | Blocks | Prio |
|---|---|---|---|---|
| C1 | Overlay frame numbers of the 6- and 7-frame portraits (`Dwarf1`, `Treeman`, ...) against the kind-5 sequences | `briefing_dialogue.md` §8, `glue_portraits.md` | portraits | P3 |
| C2 | `tentpos` values 8, 16, 17, 21 are not used by any script (8 and 17 duplicate 7 and 15) | `campaign_tent.md` §10 | none (data only) | P3 |
| C3 | Story reason for `CeridanWindow` / `IlmarinWindow` using the hooded portrait | `glue_portraits.md` §6 | none | P3 |
| C4 | Direction/anchor labels: uncertain action labels, cannons split across `*CANON`/`*WAG`, 10 outlier anchors, flag bytes 13-15, `SPELLS`/`GENBATT` layout | `animations.md` | unit animation, effects | P2 |
| C5 | Whether `setdemodefault` is read by an out-of-tree demo build (inert here) | `briefing_dialogue.md` §8 | none | P3 |

### D. Note corrections owed

- `notes/campaign.md` §7.5: the mission-list *release step* runs when the after-mission (or info) caravan is left through `UnwindMission`
  (`mission_selection.md` §8.1), not "after the player picks a row"; a row pick only selects. Reword when `campaign.md` is next edited.
- `notes/music.md` "What exactly `win`/`lose`/`tactical` do": answered by `troop_selection.md` §1.3 and `briefing_dialogue.md` §2.3 (they loop;
  `tactical` for selection and marching order, `win`/`lose` for the debrief).
- `notes/music.md` "whether looping/fade is controlled by glue commands": answered by `briefing_dialogue.md` §2.2 (always loops, no fade is ever requested).

## Risks and rules

- **Legal**: the repo contains only code and descriptions. Extracted files stay local:
  `samples/`, `battles/` and `extracted/` are in `.gitignore`.
- **Visual/audible verification** of every hypothesis, rather than "the byte count matches".
  Music, pitched effects, and speech have received a listening review.
- **Speech and videos** are the largest volume of data (263 MB), but the least important for
  gameplay.
- **Logic in native DLLs** is the main risk of the project. Without it we will have a "viewer", not a
  "game". The campaign flow itself turned out to be text (glue scripts), which reduces this risk.
