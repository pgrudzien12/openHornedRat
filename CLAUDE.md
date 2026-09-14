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

The game installation (GOG v1.0) lives in a Wine prefix:
```
~/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/
```
(this prefix is also the data source for further work — `.BOP`/`.FOL`/`.PAL` files
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
| Save games `savegame.0/.5` | ⬜ Unexplored |

## Repository layout

GitHub repository: https://github.com/pgrudzien12/openHornedRat (private).
`samples/`, `battles/` and `extracted/` are in `.gitignore`: they contain data extracted from the game and are kept locally only.

```
README.md          - project description (goal, required original game, where to buy it)
CLAUDE.md          - this file
FORMATS.md         - format reference: overview table, structures, hypotheses, open questions
ROADMAP.md         - work plan: game file inventory, phases 0-5 with status, milestones, order of steps
notes/             - full per-format reports (how each claim was verified, per-file tables, open questions)
  animations.md, battle_viewer.md, btp_sprite_leftovers.md, fonts_glue.md, game_rules.md, music.md, pbx_rnc.md, research_plan.md,
  pe_resources.md, scene_scripts.md, sfx.md, si_omni.md, sprite_names.md, terrain_gd.md
whshr/             - unified package and CLI: python3 -m whshr check|extract|viewer|viewer-web|
                     viewer-2d|viewer-2d-web|terrain-check|rules|scripts (3D battle viewer: battle3d.py, 2D: battle2d.py,
                     GAMEF.DLL rule tables and unit stat decoding: rules.py,
                     behaviour bytecode disassembler: behaviour.py)
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
  pe_*.py          - PE resource parser, extraction of DLL resources, missions/objectives table
  fon_*.py         - .FON parser/renderer, GLUE/WIND palette analysis
  music_*.py       - MIDI and SBK (SoundFont 1.0) parsers, SBK->SF2 converter, stem renderer
  sfx_*.py         - .SFX package parser, WAV statistics
  pbx_*.py         - RNC ProPack decompressor, .PBX container extraction (textures, meshes, sprites)
  gd_render.py     - GRND.GD terrain: check, relief renders, .obj/.json export, height lookup
  si_*.py          - Omni .SI container extraction, pure-Python Smacker decoder
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

## How to continue

Almost every data format is now reverse-engineered (see the overview table in `FORMATS.md`).
What is left is listed in `ROADMAP.md` ("Proposed order of the next steps"); in short:

Phase 2 (static 3D battle viewer, milestone M2) is closed; exact original camera parameters are
deliberately not pursued.

1. Game rules (combat, morale, unit stats) by targeted disassembly of `GAMEF.DLL`/`WHSHR.EXE` — top priority.
   First pass done (`notes/game_rules.md`); continue with its open questions, then magic.
2. Real-time engine prototype of the battle scene (nice to have; engine technology not chosen yet).
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
