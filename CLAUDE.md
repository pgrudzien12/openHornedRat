# Warhammer: Shadow of the Horned Rat — reverse engineering / open-source engine

## Project goal

Reverse-engineer the file formats of **Warhammer: Shadow of the Horned Rat** (Mindscape,
1995) in order to eventually write our own open engine/viewer able to reproduce the
assets (and perhaps the game itself), in the spirit of projects such as OpenMW (Morrowind)
or OpenRA (Command & Conquer).

## Language

**All documentation and all scripts/code are written in English**: Markdown files, code,
comments, docstrings, identifiers, script output (including generated reports such as the
battle atlas) and commit messages. The only place where another language (e.g. Polish) may
be used is the conversation with Claude Code itself. If you come across a file that still
contains non-English text, translate it.

## Background

The owner of the game (bought on GOG) tried to run it on Linux via Proton/Wine.
After a series of fixes (Windows XP compatibility, a virtual desktop instead of fullscreen,
a missing 32-bit FreeType library) the game reached the menu and the first mission,
but with **no sound** (the game's audio engine emulates an old AWE32/MIDI hardware card,
which has no chance of working under any Wine) and **random exits without an error**
after the first mission (a known bug of this version under Wine, documented on the GOG
forum and unresolved). An attempt with **BoxedWine** (an x86 emulator + its own Wine,
running as WebAssembly in the browser) also got stuck — its simple zip-as-filesystem
"mounter" has some bug/limitation with a large number of files / duplicate names
differing only in case, which we could not work around.

At that point, having some free time, instead of patching Wine any further we started
**reverse-engineering the game's own file formats** — the first step towards a fan-made
open-source engine, as other projects of this kind have done.

Set `WARFB` to the root directory of a local GOG v1.0 installation:
```
$WARFB/
```
(That installation is the data source for further work — `.BOP`/`.FOL`/`.PAL` files
in `FILE/BINARY/`, `UPDATE/BINARY/`, `REMOTE/BINARY/`).

## Current status

See **`FORMATS.md`** — a full, detailed description of the reverse-engineered and still
unknown formats. In short:

| Format | Status |
|---|---|
| `.PAL` (color palette) | ✅ 2 variants: RGB palette (`STANDARD`, `GLUE`/`WIND` halves) or 4→8-bit sprite color maps (512 B each) |
| `.FOL` / `.BOP` (sprites, backgrounds) | ✅ 8 bpp, 4 bpp, 4 bpp + zero RLE; color map index rule (modulo 16); legacy layouts; visually verified |
| Unit animation layout | ✅ groups × phases × 8 directions (move/dead/attack/stand/shoot); 🟡 `dir` zero frame (clockwise sense known), anchor y, timing |
| Script names → files | ✅ sprite and furniture tables in `WHSHR.EXE`/`GAMEF.DLL` |
| `.BTS` (battle), `.MRC` (army) | ✅ INI-style text scripts, parser works on 87/87 files, layout verified on the plan map. Objective letters solved; some fields (`set:map`, `whoami`, part of `setstats`) still unknown |
| `DLL/*.DLL` resources | ✅ bitmaps, texts, dialogs, cursors; `WND.DLL` campaign glue scripts parsed into a verified flow graph |
| `.FON`, `GLUE/*.PAL` | ✅ standard Windows NE/FNT fonts; front-end palette pairs |
| Music `.MID` + `.SBK` | ✅ MIDI GM/FM pairs + SoundFont 1.0 bank (3 presets); all 21 tracks rendered and reviewed |
| `.SFX` + WAV | ✅ `MSNDDS.DLL` effect packages; effects with pitch and speech reviewed |
| `MESH/*/*.PBX`, `GRND.GD` | ✅ RNC ProPack + container (Reality Lab textures and meshes, sprite bundles); terrain height field |
| Cutscenes `.SI/.SN/.SM/.SR` | ✅ Omni 1.0 container, Smacker films, WAV, MIDS, event tracks; 🟡 event semantics |
| Game rules (`GAMEF.DLL`) | ✅ `setstats` byte layout, close combat (WFB 4th ed charts), combat resolution, morale (flat 2–12 Ld roll), shooting (volleys, scatter, reload, ranges, blast damage), rout/pursuit/rally, movement and real time, magic (power pools, spells, dispel), unit behaviour bytecode and events. Report: `notes/game_rules.md` |
| `SCRIPT/*.DLL` (mission logic) | 🟡 Win32 DLLs that only carry bytecode unit behaviour scripts (mission ids from 0, 3–37 per DLL; 100–170 shared library) run by a 232-opcode interpreter in `GAMEF.DLL`; all 232 opcodes catalogued, disassembler `python3 -m whshr scripts` |
| Save games `savegame.0/.5` | ✅ RIFF `WHSV` (header with coffers, glue state, book flags, regiment roster, embedded `ARMY/PLAY/MARCH.MRC` and `debrief.dbf`, mission record); campaign rules (experience, economy, casualties). Report: `notes/campaign.md` |

## Repository layout

GitHub repository: https://github.com/pgrudzien12/openHornedRat (private).
`samples/`, `battles/`, `extracted/`, `logs/` and `saves/` are in `.gitignore`: they contain data
extracted from the game (or, for `logs/`, JSON Lines battle logs, and for `saves/`, engine campaign
saves — see "Engine saves" below — naming regiments and units from the game) and are kept locally only.

```
README.md          - project description (goal, required original game, where to buy it)
CLAUDE.md          - this file
FORMATS.md         - format reference: overview table, structures, hypotheses, open questions
ROADMAP.md         - work plan: game file inventory, phases 0-5 with status, milestones, order of steps
notes/             - full per-format reports (how each claim was verified, per-file tables, open questions)
  animations.md, battle_viewer.md, btp_sprite_leftovers.md, campaign.md, data_driven_audit.md, mission_selection.md, campaign_tent.md, glue_keywords.md, glue_interpreter.md, palette_selection.md, activity_results.md, debrief_evaluation.md, builtin_widgets.md, save_resume.md, troop_selection.md, briefing_dialogue.md, glue_portraits.md, fonts_glue.md, game_rules.md, music.md, pbx_rnc.md, research_plan.md,
  pe_resources.md, scene_scripts.md, sfx.md, si_omni.md, sprite_names.md, terrain_gd.md
  engine_gaps/     - one file per real-time-engine gap (mission scripts, deployment, neutral units, terrain
                     navigation, objectives/win-lose, formation movement): known facts (pointers into the
                     reports above), open questions, and behavioural implementation notes. Tracked as GitHub
                     epics/tasks (labels `type:epic`/`type:task`, `track:research`/`track:implementation`,
                     `area:*`); see `engine_gaps/README.md`
whshr/             - unified package and CLI: python3 -m whshr check|extract|catalog|engine|battle-replay|viewer|
                     viewer-web|viewer-2d|viewer-2d-web|terrain-check|rules|scripts|glue-spec (3D battle viewer: battle3d.py, 2D: battle2d.py,
                     GAMEF.DLL rule tables and unit stat decoding: rules.py,
                     behaviour bytecode disassembler: behaviour.py, traced block formation layout: formation.py,
                     scenes and lazy assets: scenes.py, campaign_scenes.py, assets.py, catalog.py, cache.py,
                     battle simulation: engine.py, fixed-step clock: clock.py, battle scene: battle_scene.py,
                     per-model close-combat battle grid (17x17 cells, pairing, arrival): battle_grid.py,
                     decoded battle data shared by viewers and engine: battlefield.py, battle camera: camera.py,
                     screen-to-ground picking: picking.py, Smacker decoder: smacker.py, mission briefings: briefing.py,
                     simplified combat, morale and shooting: combat.py, enemy AI: ai.py, win/lose: result_scene.py,
                     structured battle events: battle_events.py, JSON Lines battle log recorder: battle_log.py,
                     one readable log per close combat, with an ASCII cell map and grid invariant
                     checks: skirmish_log.py,
                     deterministic replay and comparison (python3 -m whshr battle-replay): battle_replay.py,
                     lossless typed WND.DLL importer and coverage inventory: glue.py,
                     shared headless campaign resource repository and indexed bitmap decoder: glue_content.py)
  frontend/        - runtime frontend, the ONLY third-party-dependent code (pygame-ce + zengl, requirements-engine.txt,
                     local .venv/); imported solely by `engine`: app.py (window, loop, overlay), views.py (registry),
                     scene_view.py, battle_view.py (GPU terrain/scenery/sprites, camera, selection and orders),
                     movie_view.py (in-engine Smacker playback and WAV cues, boot intro and glue playmovie), menu_view.py (menu, briefing), result_view.py, gpu.py
  launcher/        - standalone pre-game launcher (python3 -m whshr.launcher), stdlib-only (tkinter):
                     discovery.py (finds an installation across GOG/Steam/Proton default locations),
                     config.py (persists the recognized path), validate.py (quick + full `whshr check`
                     reuse), battles.py (lists playable battles), engine_launch.py (locates the engine's
                     own .venv interpreter and starts `whshr engine` as a subprocess), gui.py (tkinter UI)
tests/             - BDD-style unittest scenarios (docs/testing.md): python3 -m unittest discover -s tests -t .
docs/              - asset_pipeline.md (lazy loading, scene lifecycle), testing.md (BDD rules)
tools/ghidra/      - OPTIONAL analysis-only Ghidra headless scripts (Java) + setup notes; not stdlib Python,
                     their decompiled output must never be committed
scripts/           - parsers/renderers/extractors (Python 3 stdlib only); most have a --check mode
  parse_pal.py     - parses a .PAL, checks that indices are sequential
  render_pal.py    - renders a .PAL as a PPM image (color strip)
  render_bop_raw.py- decodes and renders an uncompressed .BOP (backgrounds) to PPM using .FOL+.PAL
  render_sprites.py- decoder for all .FOL/.BOP frame types (8bpp, 4bpp, 4bpp+RLE) -> PNG sheet
  anim_*.py        - animation layout: inventory + layout test, labelled sheets, export to sheets/GIFs
  btp_*.py         - SPRITE3.BTP, legacy .FOL layouts, SPELLS map rule, orphans, odd palettes, UPDATE vs FILE
  spritemap_*.py   - script name -> file tables from WHSHR.EXE (map.json) and their verification
  whscript.py      - .BTS/.MRC parser: tree, typed view (JSON), counter validation (--check)
  render_battle.py - top-down battle map (boundaries, objects, scenery, units, nodes) over the plan map
  battle_atlas.py  - atlas of N random campaign battles: PNG + .md description per battle + README with legend
  glue_palette_check.py - verifies the palindex palette rule against BITMAP.DLL/WND.DLL (notes/palette_selection.md)
  save_stax.py     - decodes the glue-interpreter part of savegame.N (notes/save_resume.md)
  pe_*.py          - PE resource parser, extraction of DLL resources, missions/objectives table
  fon_*.py         - .FON parser/renderer, GLUE/WIND palette analysis
  music_*.py       - MIDI and SBK (SoundFont 1.0) parsers, SBK->SF2 converter, stem renderer
  sfx_*.py         - .SFX package parser, WAV statistics
  pbx_*.py         - RNC ProPack decompressor, .PBX container extraction (textures, meshes, sprites)
  gd_render.py     - GRND.GD terrain: check, relief renders, .obj/.json export, height lookup
  si_*.py          - Omni .SI container extraction; si_smacker.py is a CLI over whshr/smacker.py
  scene_dump.py    - .SN/.SM/.SR scene side files, speech/text links
  rle_v2.py        - OBSOLETE: old, wrong RLE decoder attempts (triples/two layers)
extracted/         - [local only, not in git] output of the extractors, one directory per topic (~250 MB)
battles/           - [local only, not in git] generated atlas of 20 battles (battle_atlas.py, seed 1995);
                     contains maps from the game files, DO NOT distribute
samples/           - [local only, not in git] renders from the game files, DO NOT distribute
  standard_pal.png - rendered STANDARD.PAL palette (proof that .PAL is reverse-engineered)
  back1.png        - rendered BACK1.BOP background (proof that uncompressed .BOP is reverse-engineered)
  eshin.png        - 24 frames of Eshin assassins (proof that compressed sprites are reverse-engineered)
  sparkle.png      - SPARKLE: 5 sparkle frames + 8 snowman frames (two color maps)
  bf001_battle.png - BF001.BTS battle layout overlaid on MAP001 (proof of the coordinate system, Y axis flipped)
  identifiers.txt  - 1006 readable (CamelCase) identifiers extracted from
                     WHSHR.EXE and GAMEF.DLL - dictionary of unit/spell/building/banner names
```

## Project tracking on GitHub

All active work — bugs, features, research questions, and implementation tasks — is tracked as GitHub
issues in the private repository [pgrudzien12/openHornedRat](https://github.com/pgrudzien12/openHornedRat).
This is the single source of truth for "what's left to do"; the notes files below are the detailed
reference layer. Each issue links to the relevant notes file(s).

**Label scheme:**
- **`type:epic`** — groups related work (battle-screen gaps, per-research-topic)
- **`track:research`** — needs investigation before implementation
- **`track:implementation`** — ready to implement from an existing public report
- **`screen:battle`** — battle-screen work (engine features like scripting, deployment, objectives)
- **`topic:*`** — research topic (campaign-glue, sprites-animation, audio, cutscenes, pe-resources, combat-rules)
- **`area:*`** — battle-engine gap cluster (mission-scripts, deployment, neutral-units, terrain-nav, objectives, formations)
- **`documentation`**, **`bug`** — (standard labels)

**Finding active work:**
- Battle-screen gaps: `gh issue list --label screen:battle,type:epic`
- Research backlog: `gh issue list --label topic:\* --state open`
- What needs research vs. is ready to code: filter by `track:research` / `track:implementation`

Every notes file's "Open questions/items" section has a banner link to its GitHub issue(s), so you can
navigate from a problem statement to the live tracking. Conversely, each GitHub issue links back to its
source notes file for the full context.

## How to continue

Almost every data format is now reverse-engineered (see the overview table in `FORMATS.md`).
What is left is listed in `ROADMAP.md` ("Proposed order of the next steps"); in short:

Phase 2 (static 3D battle viewer, milestone M2) is closed; exact original camera parameters are
deliberately not pursued.

1. Game rules (combat, morale, unit stats) by targeted disassembly of `GAMEF.DLL`/`WHSHR.EXE` — top priority.
   First pass done (`notes/game_rules.md`); continue with its open questions, then magic.
2. Real-time engine prototype of the battle scene, in Python (pygame-ce + zengl frontend; decision and
   rationale in `notes/engine_architecture.md`).
3. Later: unit movement (M3), mission logic in `SCRIPT/BFxxx.DLL`, and Wine sessions for open
   questions (`dir` zero frame, frame timing, cutscene events) only when they block work.

When a new format task is done, write the full report to `notes/<topic>.md` and add a condensed
section plus a row in the overview table of `FORMATS.md`.

## Important rules for working on this project

- This is a **hobby/exploratory reverse-engineering project**, not a commercial clone —
  the goal is to understand the formats and (maybe one day) build a fan-made viewer/engine
  for one's own, legally owned copy of the game. Do not distribute game files or data
  extracted from them.
- Verify hypotheses **visually** whenever possible (render an image, compare it with what
  makes sense for a 1995 game) — "the byte count matches" alone can be misleading
  (see: 3/13 frames "matched" by accident under a wrong RLE hypothesis).
- Game files (`.BOP`, `.PAL`, etc.) are not in this repo (they are the property of GOG/Games Workshop) —
  the scripts in `scripts/` take the path to the installed game as an argument.

## Engine rule: read scene data, do not hardcode it

The campaign has dozens of missions, portrait windows and caravan variants. Positions, bitmap names, hotspot
rects and targets, animation frames and timing, text ids and portrait/background/panel numbers come from the
`WND.DLL` glue scripts (and the string DLLs) at runtime. Only the *front-end's own* constants may live in code, and then
as one documented table per concept (e.g. `controlpanel` → panel + button labels), each row citing its note; guessed
values go in a `PROVISIONAL` block. Never key content by a non-unique id (battle ids repeat across mission records).
Test on more than one mission/window. Audit and lessons: `notes/data_driven_audit.md`.

Assets follow the same rule: the engine and its tests load original data from the user's installation at runtime through
`AssetId`/catalog/loader (`docs/asset_pipeline.md`), never from `extracted/` PNGs or other extractor output. `extracted/` is
a debug/verification artefact only, absent on a fresh checkout. Glue bitmaps come from `BITMAP.DLL` via a `pe-bitmap`
loader (design: `notes/data_driven_audit.md` §3.1); take sizes and frame counts from the asset, not from literals.

## Engine rule: saves are the engine's own, not the original's

The engine never writes into the original installation (no autosaves, no `SAVE/ARMY.MRC`/`MARCH.MRC`/`savegame.N`
overwritten in place). Writes go to the engine's own save directory (`python3 -m whshr engine --save-dir`, default
`saves/` of this checkout, threaded as `SceneAssets.save_dir` / `CampaignState.save_dir`) — read-only game data stays
in `$WARFB`, mutable player state stays in the engine's own directory. The engine does not promise save-format
compatibility with the original either (mods may later need a different shape); reusing the original's readable
`.MRC` text grammar to write `ARMY.MRC`/`MARCH.MRC` (`whshr/roster.py`, `notes/glue_engine_integration.md` GEI7e) is a
convenient current implementation choice, not a compatibility commitment. The full save/load model is still open
(GEI7e's item in `notes/glue_engine_integration.md`, owned overall by GEI14).

## Research and implementation boundary (all agents must follow this)

The goal is **compatibility with a legally owned installation**, not reproduction of the
original code or assets. There are two roles with a one-way hand-off:

1. **Research agents** may use private working material, game-data inspection, runtime
   observation, and—when assigned—static analysis of the user's locally installed binaries.
   They must not implement engine code from that material. Their private scratch output stays
   untracked under `extracted/`; it may contain research locations and tooling output.
2. **Implementers** work only from public behavioural specifications, documented file
   formats, and independently written tests. They must not inspect or use binary-analysis
   tools, private research reports, executable addresses, function labels, decompiler output,
   or assembly as implementation input.

The hand-off is a **public implementation report** in `notes/` (and, where useful,
`FORMATS.md`). It describes only externally observable behaviour and independently useful
data facts: formulas, small tables, file layouts, state machines, test cases, uncertainties,
and gameplay examples. It must never contain executable virtual addresses, internal runtime
locations, `FUN_*`/`DAT_*` labels, decompiler-derived pseudocode, assembly, tool output, or
directions for recovering any of those. Describe *what the game does* ("WS vs WS uses an
11×11 to-hit table"), never how its executable implements it.

Implementation in `whshr/` and `scripts/` must be written independently from that public
report. Same behaviour is the objective; the original program's structure is not. Code
comments and docstrings may cite a public report section, never source locations or internal
names. If a required fact exists only in private research material, request a public hand-off
report before implementing it.

Practical rules:

- **Don't feed decompiled/assembly code to an LLM as implementation context.** A research
  agent may use it privately to produce a public hand-off report; an implementation agent
  should only ever see that report. If the only source available is private research material,
  stop implementation and produce a report first.
- **Research agents may consult private research indexes** under `extracted/` to avoid repeating
  analysis. They are research-speed shortcuts only. Never copy an address, internal name, or
  analysis artefact from them into a public report or implementation code.
- **Prefer reading data from the user's own installation at runtime** over baking constants
  into the repo, especially for anything closer to "content" than "fact" (e.g. a lookup
  table of numbers is fine to record as a fact in `notes/`; large blocks of text/art/audio
  are not). `extracted/`, `samples/`, `battles/` stay gitignored/local for this reason —
  don't add game-derived binary data, art, text, audio or video to tracked files.
- **Never commit original assets** (sprites, textures, models, music, SFX, voice, video,
  maps, narrative text, fonts, the `.EXE`/`.DLL` files themselves). If new replacement art
  is ever generated, base it on general descriptions of required properties (size, palette,
  frame count), not on reproducing a specific original image.
- **Don't copy strings verbatim** out of the executable into engine code/docs beyond what's
  needed to *locate* data (e.g. a signature or field name is fine; flavor text, dialogue,
  and lore strings should be loaded from the user's install, not embedded).
- **No DRM/copy-protection circumvention.** If something can't be reached through the
  normal installed game files, stop and flag it instead of working around protection.
- When unsure whether something is a fact/interoperability requirement vs. copyrightable
  expression, don't commit it — flag it for the user to review instead.
- **GitHub issues are public resources.** All issue descriptions, comments, and linked reports are visible to the repository (and potentially distributed). Never mention decompilation, binary analysis, disassembly, internal function addresses, Ghidra/IDA output, or other private research methodology in GitHub issues. Only reference publicly observable findings, data-extracted facts, and published notes files. GitHub issues document *what was found* (game behaviour, file formats, data facts), never *how it was found* (tools used, code analysis methods, addresses referenced).
