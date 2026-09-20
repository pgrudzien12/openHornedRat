# Engine architecture and modding direction

This is the implementation direction for the open engine. It is a decision record: it states the
chosen language and libraries and why, and it may be revised when a real-time prototype proves a
design wrong.

## Goals

- Run the original campaign from a legally owned installation without Wine or
  the original executable.
- Preserve the original game as a compatibility target while allowing an open,
  extensible game more like OpenXcom than a one-for-one executable replacement.
- Make rules, missions, and campaign content data-driven and modifiable.
- Keep the reverse-engineered formats and game behaviour testable without
  opening a graphical window.
- Never distribute original game assets or turn extracted assets into repository
  content.

## Chosen direction

The engine will be data-first and split into independent layers:

```text
original installation
    -> vanilla importers and asset readers
    -> normalized engine data and stable internal model
    -> deterministic headless simulation
    -> runtime frontend: rendering, sound, input, and debug UI

mod packages
    -> ordered overrides and extensions of normalized engine data
```

The original installation is the source of the vanilla campaign. Original file
formats are compatibility inputs, not the public authoring format for new
content.

### Language: Python (decided September 2026)

**Python is the main engine language.** The `whshr` package is not only the reference
implementation but the engine itself: format readers, normalized models, rules, the behaviour
bytecode interpreter, the deterministic simulation, and the runtime frontend. This supersedes the
earlier plan for a C++ SDL2/OpenGL frontend (`CMakeLists.txt`, `engine/src/main.cpp`,
`horned-rat-engine`), which is **parked**: kept in the repository for reference, not developed further.

The runtime frontend will use:

- **pygame-ce** (SDL2 underneath) for the window, input, timing, and audio output;
- **zengl** (OpenGL 3.3 core) for rendering terrain, scenery meshes, and sprite billboards, with
  palette and colour-map lookups done at texture upload or in shaders;
- **FluidSynth** for MIDI music with the converted SoundFont, either through a binding or
  pre-rendered to PCM at load time (decided when music is added).

Both main libraries install as pre-built wheels on Windows, macOS, and Linux. Nothing is installed
without the project owner's approval.

The first plan named moderngl. When the frontend was started (September 2026), its latest release
(5.12.0, October 2024) and its `glcontext` dependency had no wheels for Python 3.14, so installing it
would mean compiling from source. zengl 2.7.3 is by the same author, is actively released, ships
Python 3.14 wheels for all three platforms, and attaches to the OpenGL context pygame-ce creates. Its
pipeline objects (shaders, bindings, render state, and target in one object) suit a few large batched
draws per frame.

### Why not C++

Most Python media libraries wrap the same C libraries a C++ engine would link (PyAV wraps FFmpeg,
pygame wraps SDL2, pyfluidsynth wraps FluidSynth), so C++ offers no extra decoders; Python mainly
makes them easier to install on every platform. For this game the question hardly arises: every
original format already has a verified pure-Python reader in `whshr` (Smacker, RNC ProPack, PBX,
FOL/BOP, SBK, SFX, BTS/MRC, behaviour bytecode).

Measurements on the development machine (September 2026):

| Workload | Result | Consequence |
|---|---|---|
| Pure-Python Smacker decoder, cutscene A13 (640×272, 1 249 frames) | whole film in 0.23 s; last frame equal to FFmpeg within ±1 per byte (palette rounding) | cutscenes need no native decoder (the films play at 8 fps) |
| FFmpeg (C), same film | 0.21 s | no practical advantage |
| Python software battle render (`viewer`, `viewer-2d`) | 0.38 s / 0.13 s per frame | per-pixel work must move to the GPU, which a C++ engine would need as well |
| Battle simulation scale | about 30 units of up to 32 models, 100 ms ticks, bytecode scripts | well within Python's reach |

A C++ engine would have to re-implement and re-verify every decoder and rule, or keep Python behind
an export step whose boundary is extra work and a source of drift; it would also need per-platform
CMake builds and development packages, and two test suites for one set of rules. Python keeps one
implementation that is already tested against the original data and is quick to change while the
rules are still being refined.

### Rules for Python performance

- Never run per-pixel loops per frame. Decode sprites, maps, and textures once at load time and
  upload them as GPU textures; sprite batches and palette lookups belong to the GPU.
- The simulation ticks at its own fixed rate (100 ms game ticks), independent of the render frame
  rate, and never depends on the frontend.
- Profile before optimising. If a hot path is proven too slow, move that one function behind a narrow
  interface (a C extension via `ctypes`/`cffi`, or Cython) without changing data definitions, the
  simulation API, or the modding contract.
- Distribution to players (a bundled application) is solved later; it does not affect the design.

### Dependencies

The readers, rules, simulation, and `scripts/` remain **Python-stdlib-only**, so they stay testable
headlessly on a bare Python installation. Only the runtime frontend depends on third-party libraries:
it lives in its own subpackage, is imported solely by the runtime command, and declares its
dependencies in a separate requirements file.

Godot remains an acceptable disposable visualization client if its tools materially accelerate an
experiment. It must not own the authoritative rule implementation, asset formats, saves, or mod
format.

## Modding contract

Modding must be designed into the data layer rather than added after the
renderer is complete. Initial mods should be declarative packages containing
human-editable metadata and assets, with:

- stable, namespaced identifiers;
- documented schemas and validation;
- explicit package dependencies and deterministic load order;
- defined override and merge rules;
- versioned formats and compatibility policy; and
- no requirement to create original `.BTS`, `.MRC`, `.FOL`, `.BOP`, or mission
  bytecode files.

The precise text format (YAML or JSON) is deferred until the normalized models
exist. It must be easy to diff, review, generate, and validate. The engine's
own save format will be separate from both original save files and mod source
data.

Do not initially permit arbitrary native plug-ins or unrestricted code from a
mod package. They undermine reproducibility, compatibility, and user safety.
When declarative content cannot express a mission mechanic, introduce a small,
sandboxed, documented, and versioned mission scripting API. That API is a
future public contract, not a wrapper around internal engine objects.

## Vanilla mission compatibility

Do not load or execute the original `SCRIPT/BFxxx.DLL` files as native DLLs.
They are containers for bytecode tables interpreted by `GAMEF.DLL`; executing
their original native environment would retain the proprietary engine's
platform, safety, and compatibility problems.

Instead:

1. Read the mission bytecode tables from the original DLLs as data.
2. Implement the required original bytecode interpreter and its narrow engine
   API in the open engine.
3. Use this interpreter to run and validate unmodified vanilla missions.
4. Decode and translate established bytecode behaviour into a readable,
   normalized mission representation.
5. Author new missions through the future mod-facing mission format, while
   retaining original bytecode support for vanilla compatibility.

This avoids prematurely reinventing unknown mission semantics while preventing
the opaque original bytecode from becoming the permanent modding language.

## Constraints and non-goals

- The simulation must remain deterministic and runnable headlessly so rules,
  missions, and imported content can be regression-tested.
- Rendering must consume simulation state, not define it; no gameplay rule
  should depend on a scene graph, editor resource, frame rate, or renderer.
- Original assets remain local to a user's installation or a local cache and
  must never be committed or redistributed.
- Claims about matching original behaviour require static evidence and, where
  practical, visual, audible, or Wine-based runtime verification.
- Exact original camera parameters are not a goal; the established perspective
  scene is sufficient for an engine.
- A custom frontend has a higher initial rendering/UI cost than an engine integration. It is
  justified while its independent data model and single-language workflow serve the project better.

## Near-term consequences

Most non-battle screens are programs for one shared `WND.DLL` glue interpreter rather than independent scene types. The architecture review and phased implementation plan are in **`notes/glue_runtime_architecture.md`**: keep `SceneMachine` for coarse application modes, and host campaign navigation, active windows and saved contexts in one `GlueRuntime`/`GlueScene`.

1. Keep the simulation API independent of pygame-ce, zengl, and any other presentation library.
2. Done: the frontend subpackage `whshr/frontend/` and its requirements file `requirements-engine.txt`.
3. Engine phase 1, in order: a battle view (plan map or terrain, directional sprites in the traced
   formations) → movement on 100 ms ticks → scenes (menu, transitions, mission briefing, cutscene
   playback with the pure-Python Smacker decoder into a texture) → simplified close combat, shooting,
   and morale from `notes/game_rules.md` → one winnable battle.
4. The behaviour bytecode opcodes are catalogued (`python3 -m whshr scripts`); implement the
   interpreter in the simulation after the first battle runs with a simple rule-based AI.

## Current prototype

`whshr.engine` defines the presentation-independent battle state and fixed-tick movement behaviour,
and the Python `SceneMachine` provides the scene lifecycle.

The runtime frontend starts with `python3 -m whshr engine <WARFB>`, run with the interpreter of a local,
git-ignored virtual environment that holds `requirements-engine.txt`:

```sh
python3 -m venv .venv && .venv/bin/pip install --only-binary=:all: -r requirements-engine.txt
.venv/bin/python -m whshr engine <WARFB>
```

Without those packages the command explains how to install them; no other command imports the frontend.
Its structure:

- `frontend/app.py`: the window (OpenGL 3.3 core), the main loop, and the debug overlay (FPS, tick
  count, scene). Measured frame time goes through the stdlib `whshr.clock.FixedStepClock`, which releases
  fixed 10 ms scene steps (at most 25 per frame) to `SceneMachine.update`. Scenes that simulate a battle
  group those steps into their own 100 ms game ticks. Window close or Ctrl+Q quits.
- `frontend/views.py`: one view per scene type. A view draws its scene and translates raw pygame input
  into scene events (for example any key or click becomes `skip` in the intro). Scenes never see pygame
  events, and a view is replaced, releasing its GPU resources, whenever the machine changes scene.
- `frontend/gpu.py`: the off-screen colour and depth target presented once per frame, textured
  screen-space quads, and text labels rendered by pygame's font and uploaded only when they change.

- `frontend/battle_view.py`: the battle scene on the GPU. The static geometry is one buffer and one draw
  call: terrain and every scenery placement are baked into world-space triangles with precomputed flat
  lighting, and all their textures share one texture array. Troops are one instanced draw of upright
  billboards: sprite frames are palette indices in one atlas, coloured by a palette texture in the
  fragment shader. Each billboard is depth-tested at its foot moved toward the camera, as in `battle3d`.
  Camera: arrow keys or WASD pan, Q/E rotate, Page Up/Page Down tilt, the mouse wheel zooms, right-drag
  pans, middle-drag rotates, and Home resets.

The data behind it is stdlib-only and shared with the static viewers:

- `whshr.battlefield.load_battlefield` decodes a battle once: terrain, scenery transforms, flat shading,
  texture layers, troop sprite sheets (the per-battle `SPRITES.PBX` first, then `BINARY/`), the sprite
  atlas and the battle palette. `battle3d` uses the same placement, shading, frame-direction and table
  helpers, and its PNG output was byte-identical before and after that refactor.
- `whshr.camera.BattleCamera` is the camera state and controls. It produces the verified `battle3d`
  perspective `Projection`, and its initial yaw follows the `180 + Camera` working hypothesis.
- `whshr.battle_scene.BattleScene` loads the battle through `SceneAssets` (decoder `battle-script`),
  builds `engine.Battle.from_script`, advances it on 100 ms ticks, and releases the battle assets on exit.
  Repeated script unit ids (BF001 has three `Clanrat_Warriors`) become `Clanrat_Warriors#2`, `#3`.

`--battle BF001` starts directly in a battle (a development shortcut; the scene flow reaches it through the
menu and briefing),
and `--camera YAW PITCH DISTANCE` sets its initial camera.

For reproducible captures, `--hidden --frames N --frame-time S --screenshot out.png` renders N frames
of exactly S seconds each without showing the window. Screenshots show game assets: keep them local.

The frontend now plays `A1.SI` itself (see "Scene flow (engine step 4)" below); the earlier
`whshr game` command and its `ffplay` stopgap are removed. `scripts/run_engine.sh <WARFB>` launches
`python3 -m whshr engine` through the repository's local `.venv`.

The C++ SDL2/OpenGL movement prototype (`CMakeLists.txt`, `engine/src/main.cpp`) is parked. Original
mission DLLs are data inputs only: the engine will never execute them as native code.

## Movement (engine step 3)

`whshr.engine.Battle` now moves regiments on the documented speed rule instead of a single arbitrary
constant, and models walk to their own formation slot rather than teleporting with the block.

- **Speed**: `engine.speed_per_tick(M, I)` implements game_rules.md, "Real time and movement":
  `s_rlmv = trunc(4.8 * M + I) / 2`, then `s_rlmv * 1.8 / 16` world units per 100 ms tick (the "moving
  freely" `k` factor; closing/charging/fleeing `k` values are not modelled yet, since there is no combat
  or morale). `Battle.from_script` reads `M`/`I` from each unit's decoded `profile` (script.py); a
  regiment without a decoded profile falls back to a documented placeholder, `engine.DEFAULT_S_RLMV`
  (an M4 I3 infantry profile, the worked example in game_rules.md). Every observed BF001 combat unit
  does carry `s_move`, so the placeholder is a safety net, not the normal path.
- **Anchor movement**: unchanged in spirit from the previous prototype — a regiment's `(x, y)` (the
  front-rank centre) moves in a straight line toward `order_move`'s destination at its speed and turns
  to face the direction of travel; `Battle.tick(seconds)` scales the per-tick distance by
  `seconds / TICK_SECONDS`, so passing anything other than the real 100 ms tick is only an approximation
  (`BattleScene` always calls it with exactly `TICK_SECONDS`).
- **Formation catch-up**: `Battle._advance_models` recomputes each model's formation slot from the
  current anchor position and facing (`formation.block_slots` + `formation.place`, the traced block
  layout) every tick, then walks each model toward its slot by at most the regiment's own per-tick
  distance — matching `MoveModels`' "never faster than the unit's `s_rlmv`" rule in game_rules.md. A
  regiment therefore visibly reforms while turning or after arrival, instead of snapping into shape;
  `tests/test_engine.py` (`FormationMovementTests`) asserts a turning order leaves models short of their
  ideal slots after one tick and that they do settle back into the exact block after enough ticks.
- **Facing and animation**: a regiment's `direction` still only changes while its anchor is actively
  moving (as before); `Regiment.walking` is true whenever the anchor is moving or any model has not yet
  settled into its slot (`engine.SETTLE_EPSILON`), and `Regiment.animation_seconds` accumulates while
  `walking` and resets to 0 when idle. The frontend (`frontend/battle_view.py`) uses `walking` to pick the
  `move` or `stand` sprite group and `animation_seconds * WALK_ANIMATION_FPS` for the phase within it.
  **Placeholder**: `WALK_ANIMATION_FPS = 8.0` — the original per-frame walk-cycle timing is not traced
  (game_rules.md, "Animation bytecode" lists it as unresolved), so this is a documented guess, not a
  measured value.
- **Selection and orders**: `Battle.regiment_at(x, y)` (game_rules.md footprint box, via
  `formation.footprint`) finds the player regiment, if any, whose oriented block contains a ground point;
  enemy regiments are excluded by default and so can never be selected or ordered. `BattleScene` owns the
  presentation-facing selection state (`selected_id`) and interprets three scene events from the view:
  `("select", regiment_id)`, `("deselect",)` and `("move_to", x, y)` (the last only acts when a player
  regiment is selected, and silently ignores a destination `order_move` rejects, e.g. outside the field —
  "blocked orders preserve a clear observable state" per docs/testing.md). The view never touches
  `Battle` state directly; it only turns pygame input into these three events using a screen-to-ground
  pick (see below) and `Battle.regiment_at`, which is a read-only query, not a rule.
- **Controls** (`frontend/battle_view.py`): left-click picks the ground under the cursor; if it hits a
  player regiment's footprint the regiment is selected (tinted yellow in the sprite shader, a per-instance
  `selected` flag blended into the palette colour), otherwise the click orders the current selection there.
  A right-button press and release within `CLICK_DRAG_THRESHOLD` pixels (no drag) does the same; a right
  *drag* still pans the camera, and a middle drag still rotates it, unchanged from the battle-view
  prototype. Escape deselects. The debug overlay's `selected` line names the current selection.
- **Picking** (`whshr/picking.py`, stdlib-only, no frontend import): `screen_ray` inverts the verified
  `battle3d.Projection` perspective camera to a mesh-space ray through a screen pixel, and
  `intersect_ground` marches that ray against a terrain height function (`Battlefield.ground_height`,
  called through a small wrapper converting BTS world units to mesh units and back) and bisects the
  crossing. `tests/test_picking.py` exercises it against flat and sloped synthetic ground, independent of
  any real battle data.
- **Collisions**: `Battle._resolve_collisions`, run once per tick after movement, is a simplified,
  deterministic `PushApart` (game_rules.md, "Routes, collisions and visibility"): when the bounding circles
  (`formation.bounding_radius`) of two regiments overlap, only the regiments under a move order give way,
  sharing the overlap, in identifier order for determinism. Standing regiments are never pushed, so
  scripted deployments that already overlap (BF001's Grudgebringer cavalry and infantry) stay put. This keeps regiments from passing through each other but is not
  the original's polygon obstruction routing (`Nav*`, `ObjectsOnPath`, left/right detours); real
  pathfinding around obstacles is left for a later milestone, as the task called for.

**Open questions / placeholders carried forward:**
- `WALK_ANIMATION_FPS` (frontend/battle_view.py): walk-cycle frame rate is unverified; needs a Wine
  session or a traced frame-delay table (game_rules.md already flags the animation bytecode's frame
  delays as 🟡).
- Only the "moving freely" `k` factor (1.8) is implemented; closing, charging and fleeing speeds (the
  other documented `k` values) wait for close-combat and morale behaviour.
- Mounts are not modelled: `speed_per_tick` always uses the regiment's own `M`/`I`, not a rider's mount
  (game_rules.md notes the mount's M does count for `s_rlmv`, unlike close combat). No BF001 regiment
  currently needs this to look reasonable, so it is left as a follow-up rather than guessed at.
- Collision resolution and formation catch-up are both deliberately simple (circle-circle push, straight
  per-model chase); they are not meant to reproduce `ResolveUnitCollisions`/`ObjectsOnPath` exactly.

## Scene flow (engine step 4)

`python3 -m whshr engine <WARFB>` (no `--battle`) now plays the full phase-1 flow: intro cutscene ->
main menu -> BF001 mission briefing -> the BF001 battle, each with a short fade-in.

- **Intro playback.** `whshr.smacker` (moved out of `scripts/si_smacker.py`, which is now a thin CLI
  wrapper around it) decodes the Smacker video kept in `whshr.si.process_si`'s rebuilt object summary.
  `whshr.si.process_si` now also keeps each rebuilt object's raw bytes in memory (`entry["blob"]`,
  dropped again before any `objects.json` extraction dump) so the engine never writes temporary files.
  `whshr.campaign_scenes.IntroScene` loads two catalog assets for the same `.SI` file: the existing
  `omni-si` (raw object tree, used only for the verified 8 fps timeline length) and a new
  `omni-si-media` decoder that returns the full `process_si` summary with blobs. The frontend's
  `frontend/intro_view.IntroView` decodes video frames on demand from `whshr.smacker.frame_index_at
  (scene.elapsed_seconds)` -- the scene's own clock is the single source of truth for both which frame
  is due and which WAV cues have started -- uploads each decoded frame as an `r8unorm` palette-index
  texture plus a 256-colour palette texture, and looks up colours in a small fragment shader (the same
  index+palette pattern `battle_view.py` already uses for troop sprites). The frame is centred on black
  at its correct aspect ratio (`VideoQuad` in `frontend/intro_view.py`). All of the container's WAV
  objects (wind, thunder, leaves, dialogue) play through `pygame.mixer.Sound` at their scheduled start;
  mixer setup is best-effort and silently no-ops without a usable audio device. MIDI music is skipped
  (optional per the session brief). Any key or click sends `skip`. Verified visually: frames captured
  at 2 s/30 s/60 s of engine playback (`--hidden --frame-time 0.1`) match a direct `whshr.smacker`
  decode of the same frame index byte-for-byte, letterboxing is centred and aspect-correct, the overlay
  reports 180-200+ FPS during decode, and cue counts increase over time confirming audio scheduling
  runs (mixer channel activity was checked without an audio device in the sandboxed agent environment;
  needs a final by-ear check on a real desktop).
- **Main menu.** `whshr.campaign_scenes.MainMenuScene` is a stdlib scene with two events: `new_campaign`
  transitions to a `BriefingScene` for the first battle, `quit` returns a new `whshr.scenes.Quit` signal
  instead of a `Transition`. `frontend/menu_view.MainMenuView` draws clickable text buttons with keyboard
  shortcuts (N/Enter, Q/Escape) and translates clicks/keys into those two events; it uses simple text,
  not original front-end graphics (deferred: `notes/pe_resources.md` describes the original bitmaps).
- **Quit signal.** `whshr.scenes.Quit(reason)` is a third value a scene's `handle`/`update` may return,
  alongside `Transition` and `None`. `SceneMachine.quit` records it without calling `exit`/`enter` (no
  scene switch happens) and further `handle`/`update` calls become no-ops once set. `frontend/app.py`'s
  main loop checks `machine.quit` after every `machine.handle` call and stops cleanly, returning the quit
  reason from `run()`. Covered by stdlib BDD scenarios in `tests/test_scenes.py` and, end-to-end, by
  `tests/test_campaign_scenes.py`; verified live by posting a `K_q` key event from a background thread
  into a hidden `run()` window and observing it exit after one frame with
  `{"quit": "player quit from the main menu"}`.
- **Mission briefing.** A new logical asset `vanilla:briefing/<battle>` (currently only `bf001`, listed
  in `whshr.catalog.build` when `DLL/WND.DLL` exists) resolves through a new stdlib module,
  `whshr.briefing`: it reuses `whshr.campaign.build_campaign_graph` to find the mission window entry for
  a battle, then reads its `brief_script` glue text out of `WND.DLL` and its `playtext`/
  `queuetoplaytext` resource ids out of `BRTXT.DLL`, returning `{title, lines: [{speaker_color, text}]}`
  in script order. `whshr.campaign_scenes.BriefingScene` loads it and shows it; `start_battle`
  (Enter or click) transitions to `whshr.battle_scene.BattleScene(self.battle_id)`.
  `frontend/menu_view.BriefingView` renders the title and word-wrapped spoken lines with `Gpu`'s
  `pygame.font` labels. Verified against the real installation: BF001 resolves to mission window
  `MISSIONBP03WINDOW`, title "Sven Carlsson", and 16 correctly ordered/coloured lines of dialogue
  between Dietrich, Carlsson and Ilmarin.
- **Transitions.** `frontend/app.py` keeps a short (0.3 s) fade-in-from-black after every scene switch,
  drawn as a tinted full-screen quad (`Gpu.fade`, a 1x1 white pixel stretched and tinted) over the new
  scene. This is a frontend-only presentation detail with no stdlib state; only the fade-in direction is
  implemented (a true crossfade would need to keep the departing view alive one extra frame, deferred).
- **Entering the battle.** `BriefingScene.handle("start_battle")` returns
  `Transition(BattleScene(self.battle_id), "briefing accepted")`; `SceneMachine` then calls `exit` on the
  briefing and `enter` on `BattleScene`, which loads BF001 exactly as the existing `--battle` shortcut
  does. Verified by driving the whole flow (skip -> new_campaign -> start_battle) through the real
  frontend and capturing the resulting `BattleScene` frame, which renders BF001's terrain, scenery and
  troop billboards as before.
- **Removed the `ffplay` stopgap.** `whshr/game.py` now only exposes `scene_context()` (the lazy-asset
  setup shared by all scenes); the old `start()` function and the `whshr game` CLI command (which shelled
  out to `ffplay`) are gone. `scripts/run_engine.sh <WARFB> [engine options...]` now execs
  `.venv/bin/python -m whshr engine "$@"`, failing with a clear message if that venv is missing.

Open questions and gaps:
- The fade is fade-in only; a true fade-out of the departing scene is not implemented.
- The main menu and briefing use plain rendered text, not the original front-end bitmaps/fonts/palettes
  (`notes/pe_resources.md`, `notes/fonts_glue.md`) or portraits/speech audio for the briefing speakers.
- `whshr.catalog.build` only lists a briefing asset for `bf001`; supporting further missions needs one
  more record per mission (or a small generic rule) rather than a hand-picked list.
- MIDI music during the intro is not played (skipped per the session brief; no new audio binding added).
- Audio playback was verified by cue-count bookkeeping in the sandboxed agent environment, which has no
  audio device; a by-ear check on a real desktop is still open.

## Combat, morale, shooting and AI (engine step 5)

BF001 is now a playable battle: `whshr.combat` (close combat, morale, rally, shooting) and `whshr.ai`
(a simple rule-based enemy) are new stdlib-only modules, called from `engine.Battle.tick`; `whshr.result_scene`
adds the win/lose scene. All three are simplified from `notes/game_rules.md` sections 4-8, not a
byte-faithful port; every simplification is called out in each module's docstring and summarised below.

- **Combat profile.** `engine._decode_combat_profile` reads WS/BS/S/T/W/I/A/Ld, armour (`s_armr`), weapon
  class (`s_weap`) and missile code (`S_BalWeap`) straight from each unit's raw `setstats` lines with
  `rules.stat_fields`, and `psy_status` flags the same way `rules.decode_unit` already did — no `GAMEF.DLL`
  access is needed at battle time, since the WFB charts it would supply are already verified constants in
  `whshr.rules` (`wfb_to_hit`, `wfb_to_wound`, `EXPECTED_ARMOUR_SAVE`, `EXPECTED_WEAPON_BONUS`). Verified
  against the real installation: BF001's Mercenary Crossbows decode to missile code 2 (crossbow, range
  720), and Otto Hiln/Sleaquit correctly carry `CantBreak`/`CantDie`/`CantRally`.
- **Movement modes.** `engine.py` now implements the documented k factors (game_rules.md, "Real time and
  movement"): 1.8 free (unchanged from engine step 3), 2.5 for a charge/attack order (`Battle.order_attack`,
  chased every tick at the target's current position, never "arriving" on its own — contact ends it), and
  1.5 fleeing (`Regiment.routing`, moving directly away from the nearest active enemy, `Battle._flee_point`).
  1.0 "closing" is defined (`CLOSING_K`) but unused: a documented simplification, since this engine does not
  model the original's charge-counter distinction between closing and charging.
- **Contact** (`combat.resolve_contacts`, game_rules.md "Engagement"): recomputed every tick over every
  active, non-routing regiment's **oriented block footprint** (`formation.footprint_corners`/
  `footprint_gap` — the exact minimum distance between two oriented rectangles, not a bounding-circle
  approximation), so a regiment only enters melee once its front rank is within one model spacing
  (`CONTACT_MARGIN = formation.MODEL_SPACING`, 12 world units) of an enemy's footprint. This replaced an
  earlier bounding-circle contact test that let two regiments "fight" tens of world units apart without
  their sprites ever touching on screen (an owner playtest report); `engine._resolve_collisions`'
  push-apart now also skips every cross-player pair (it only keeps same-side regiments from overlapping
  a stationary ally), so a charging regiment is free to keep closing all the way to footprint contact
  instead of stopping at the old, looser circle distance.
- **Fight groups** (`Battle.fights`, game_rules.md 5.7's battle grid): `resolve_contacts` unions every
  touching pair (regardless of side) into connected components each tick, so **several regiments on one
  side can share a single fight against a lone enemy** — the fix for BF001's "no 2 vs 1" bug, where a
  single `Regiment.melee_opponent` field made that impossible. Each fight keeps one shared id
  (`Regiment.melee_group`), a per-side score tally and a kills/rank/direction breakdown
  (`Battle.fights[group]["tally"]`/`"breakdown"`), and its own break-test timer; a regiment newly joining
  an existing fight (a third regiment closing in) does not reset that fight's tally. `Regiment.
  melee_touching` is the live set of enemy ids this regiment's footprint currently touches.
- **Melee resolution** (`combat.resolve_melee`, game_rules.md 5.1/5.2/5.5/6.1): a unit strikes once per
  turn, in the segment equal to its own Initiative (`combat._segment_state`, segments count down 10..1
  within a `SEGMENTS_PER_TURN = 10`-segment turn), against the nearest enemy it is currently touching
  (`combat._pick_melee_target`); the moving side with an active charge order is flagged as the charger
  (`Regiment.melee_charging`) and gets +1 S on its first strike after joining a fight (game_rules.md 5.5,
  granted once per regiment rather than decremented per attacking model). Attacks = front rank models x A
  (front rank only, not capped by the opponent's frontage); hit/wound/save rolls use `rules.wfb_to_hit`/
  `wfb_to_wound`/`EXPECTED_ARMOUR_SAVE`. Each strike's kills plus **rank bonus** (`combat._rank_bonus`:
  `size / frontage - 1` when frontage > 3, uncapped) and **direction bonus** (`combat._direction_bonus`:
  +2 rear, +1 flank, quartering the angle of attacker relative to the defender it struck) accumulate into
  its **fight's own-side tally**, not a per-regiment one — this, plus the fight-group fix above, is what
  keeps the break-test modifier proportional to the actual round (the traced diagnosis found modifiers of
  +6/+9/+10 caused by stale/mis-paired tallies from the old single-opponent model; after the fix the same
  log's largest modifier is +3, see below). There is still no ganging-up WS bonus, hatred, magic items,
  mounts or monsters. A multi-wound model dies on its first failed save (no per-model wound tracking).
  Casualties (`combat.apply_casualties`) turn into corpses at the models' last positions and shrink the
  formation — **except `CantDie` models** (game_rules.md 7.6), which are never removed; their wounds
  still count toward the tally (`_roll_attacks`' raw `kills`, not `apply_casualties`' return value), a
  documented placeholder since the notes do not say whether they should.
- **Break tests** (`combat._resolve_group_break_test`, game_rules.md 6.2, timing traced): a fresh fight's
  tally and breakdown start at zero and its first break test is due two turns after contact
  (`fight["next_test_turn"] = contact_turn + 2`); once due (checked at each turn's last segment), the
  losing side (by tally difference, so rank/direction bonuses can outweigh a raw kill deficit) — **every
  active regiment on that side of the fight**, not just one pairwise opponent — takes the documented flat
  2-12 Leadership roll (`combat.leadership_test`) with modifier = the tally deficit; the `leadership_test`
  event now also carries both sides' kills/rank/direction `breakdown` so a large modifier can always be
  traced back to what produced it. The tally and breakdown then reset and the next test is due next turn
  — simplified from the original, which varies the interval with the units' Initiatives. `CantBreak`
  never routs.
- **Rally** (game_rules.md 7.4, timing and casualties modifier traced): a routing regiment
  (`combat._start_rout`) schedules its first rally attempt one full turn later
  (`Regiment.rally_next_segment`), then every 3 segments regardless of outcome; it flees directly away
  from its nearest active enemy at fleeing speed and is removed (`fled = True`) once it leaves the field.
  When its scheduled segment comes, a non-`CantRally` regiment with casualties below 3x its current size
  and no enemy within `FLEE_SAFE_DISTANCE` (160 units) takes a Leadership test with modifier +2
  (casualties > size), +1 (3x casualties > size) or 0 (`combat._rally_modifier`, using
  `Regiment.original_models` set at creation); casualties at or above 3x size block rallying outright.
  `resolve_rally` now also skips any regiment that is `not regiment.active` (i.e. `fled`, since `active`
  is `not destroyed and not fled`) before checking `rally_next_segment` — the fix for an owner-reported
  bug where a regiment that had already routed off the field edge (`fled = True`) kept passing later
  rally tests and effectively returning to play, because the old check only looked at `routing` (which
  `fled` never clears). A `fled` regiment is now permanently out: no rally tests, no orders
  (`order_move`/`order_attack` already required `player`/not-`routing`), no movement or contact
  (`active` already gated those), and no rendering (`battle_view` already iterates only `active`
  regiments).
- **Verified against a real BF001 log** (`logs/battle-20260915-090524-bf001.jsonl`, `python3 -m whshr
  battle-replay`): under the pre-fix rules that log's own recorded snapshots show Grudgebringer Cavalry
  already routing by tick 323, 36 ticks after its tick-287 contact (under two segments); replaying the
  same orders under the traced timing produces no break test at all by the log's last recorded tick
  (469, the player quit), since the earliest one is now due at contact_turn + 2 turns (tick ~667) —
  confirming the "instant rout on contact" bug is gone. The order replay itself diverges from tick 323
  (the AI's own attack-target choice differs once its decisions no longer follow the old per-segment
  break-test cadence), which is the expected kind of divergence for a rules change, not a regression.
- **Verified against a second real BF001 log** (`logs/battle-20260915-234951-bf001.jsonl`, contact/fight
  group/fled fix): the owner reported units "fighting many squares apart" and break-test modifiers of
  +6/+9/+10 (worst: the cavalry vs. the single `CantDie` assassin Sleaquit, roll 8 + modifier 10 against
  Ld 7). Replaying the same orders under the new footprint contact and fight groups: 18 clashes, anchor-
  to-anchor clash distance 21.6-66.4 world units (up to a large regiment's own half-frontage — the front
  ranks are confirmed touching by `formation.footprint_gap <= CONTACT_MARGIN` at every one of them, not
  merely "close"), and the largest break-test modifier across the whole replay is now +3.0. A one-frame
  hidden-window capture at the first recorded clash (`Grudgebringer<Cavalry` vs. `Clanrat_Warriors`,
  tick 286) shows the touching regiment in its attack pose clustered tightly at the contact point;
  `Regiment.melee_touching` confirms the pairing programmatically. The replay still diverges from the
  logged snapshots soon after (expected: the rules changed), and two regiments (`Grudgebringer<Infantry`,
  `Clanrat_Warriors`) sharing one fight against a third strike independently in the timeline, confirming
  the fight-group fix.
- **Shooting** (game_rules.md 8.1-8.3, simplified): only the basic bow-type missile codes
  (`engine.ARCHER_MISSILE_CODES`: bow, crossbow, Wood Elf bow, short bow, longbow) are modelled as
  shooters — artillery and special weapons are not. A stationary, non-engaged missile regiment fires at
  the nearest active enemy within range and its front 45 degree arc (`combat._shooting_target`), a shot
  count of `ceil(front rank / 4)`, and reloads using the documented formula (`combat._reload_ticks`,
  game_rules.md 8.2) — verified: an I3 crossbow regiment reloads in exactly 96 ticks, matching the
  worked example. **Placeholder**: hit chance is a simple BS-indexed die target (`combat.SHOOT_TO_HIT`),
  not the original's geometric scatter/flight simulation; there are no projectiles in flight (optional
  per the task).
- **Enemy AI** (`whshr.ai`, stdlib, no behaviour bytecode): each enemy regiment holds its deployment
  position until the nearest active player regiment is within `ai.ENGAGE_DISTANCE` (400 units, a
  documented placeholder trigger distance — not described anywhere in game_rules.md, which covers the
  original's scripted mission bytecode instead of a from-scratch AI), then charges it
  (`Regiment.attack_target`); a regiment carrying a missile weapon holds and shoots instead once its
  target is in range, but still approaches and charges if the target is merely within engage distance but
  out of missile range. Routing and already-engaged regiments are left alone.
- **Player orders.** `Battle.order_attack(id, target_id)` orders a selected player regiment to charge a
  named enemy regiment (charge speed, chased into contact); `order_move` and `order_attack` both reject a
  routing regiment. `BattleScene.handle` gained an `("attack", enemy_id)` event alongside `select`/
  `deselect`/`move_to`. `frontend/battle_view.py`'s `_ground_click`: a click on an enemy regiment with a
  selection now issues `attack` instead of falling through to `move_to`.
- **Win/lose and the result scene.** `Battle._update_result` (guarded so a one-sided synthetic battle,
  as most movement tests use, never auto-resolves) sets `result` to `"victory"`/`"defeat"` once every
  regiment on the other/own side is destroyed or has fled, and `Battle.tick` becomes a no-op afterwards.
  `BattleScene.update` then returns a `Transition` to the new `whshr.result_scene.ResultScene` (title +
  a casualty summary line per regiment); `ResultScene` is kept out of `campaign_scenes.py` and imports
  `MainMenuScene` lazily inside `handle` to avoid an import cycle (`battle_scene` -> `result_scene` ->
  `campaign_scenes` -> `battle_scene`). `frontend/result_view.py` renders it; any key or click returns to
  the main menu.
- **Presentation** (`frontend/battle_view.py`): an engaged regiment plays the `attack` action, a
  stationary ready-to-shoot missile regiment plays `shoot`; both fall back to the sheet's longest group
  when a sprite has no such animation (`battlefield.SpriteSheet._group`, unchanged). Corpses
  (`Regiment.corpses`) are drawn every frame as `dead` frame billboards at the positions models died,
  independent of whether their regiment is still active; the instance buffer's fixed capacity (computed
  once from the battle's total starting model count) always suffices because a casualty converts one live
  instance into exactly one corpse instance, so the sum per regiment never grows. A routing regiment
  already renders running (the `move` action, facing its flight bearing) with no special-case code, since
  routing reuses the same anchor-movement/`walking` machinery as an ordinary move order. The debug overlay
  gained a rolling 3-line battle event log (`BattleView.event_log`, fed from `Battle.events` every frame).
- **Determinism.** `Battle` owns a seeded `random.Random` (`Battle(..., seed=...)`, default 1995) used by
  every dice roll in `whshr.combat`; all new BDD scenarios (`tests/test_combat.py`, `tests/test_ai.py`,
  and additions to `tests/test_engine.py`/`tests/test_battle_scene.py`) fix a seed and assert exact,
  reproduced outcomes rather than probabilistic ranges.
- **Verification.** A headless, scripted-player run of the real BF001 installation (a player order every
  2 simulated seconds at the nearest active enemy, seed 1995) reaches `"victory"` at tick 2127 (about 3.5
  simulated minutes), after multiple genuine routs, rallies, a shooting exchange, and several melee
  rounds — see the tick log kept with this session for the full event trace. A synthetic overwhelming-force
  scenario reaching `"defeat"` is also covered by a BDD test. Screenshots captured the same way (hidden
  window, scripted orders, camera refocused on the active regiment) show a melee in progress (attack
  animation on both sides), a regiment fleeing after a lost combat round, and the victory result screen
  with its casualty summary; kept locally in the scratchpad, not the repository.

**Open questions / placeholders carried forward:**
- `ai.ENGAGE_DISTANCE`, `combat.SHOOT_TO_HIT`, and the "no ganging-up/rank/direction bonus, one round per
  segment resolves the whole tally" combat simplification are documented placeholders, not traced values;
  see each module's docstring.
- `CLOSING_K` (1.0) is defined but never applied: player/AI attack orders always use charging speed, since
  this engine has no charge-counter concept to distinguish closing from charging.
- Multi-wound models (`Regiment.wounds`) are decoded but not used: a model dies on its first failed save,
  matching every core BF001 infantry/missile unit (W=1) but not correctly modelling higher-wound
  models/monsters if BF001 ever fields one.
- Artillery, special weapons (cannon, mortar, breath weapons, warp lightning, ...), mounts, magic items,
  hatred/frenzy, fear/terror, and the behaviour bytecode interpreter are not modelled, per the task's scope
  for a first playable battle.

## Bug fixes after playtesting

- **Troop sprite facing** (owner report: figures did not keep their facing and changed sprite far too
  often while the camera rotated). Root cause: the stored direction frames run **clockwise** on screen
  (0 back view, 2 facing screen-right, 4 toward the viewer, 6 facing screen-left), not counter-clockwise
  as `notes/animations.md` had recorded. Labelled 4x `BRDHRS` sheets settle it: the horse's head points
  right in frame 2 and left in frame 6, where the rider's shield arm faces the viewer. With the wrong sign
  every sprite turned against the camera rotation, so figures seemed to spin at twice the rate and
  side-facing units showed the mirrored profile. `battlefield.sprite_direction` now returns
  `round((dir - H) / 64) mod 8` (`H` = the camera's screen-up heading), `battle2d` uses
  `+round(dir / 64)`, and `battle3d` shares the helper. BDD scenarios in `tests/test_battlefield.py` fix
  the clockwise order and the orbit sense (one step per 45 degrees, against the orbit).
- **Intro never ends**: a hidden run and a stdlib scenario both reach `MainMenuScene` at the Omni timeline
  end (96.5 s), holding the last of the 722 frames from 90.25 s. The last-frame clamp moved from
  `IntroView` into `smacker.frame_index_at(elapsed, frame_count)` with BDD coverage. The loop the owner saw
  was not reproduced; see `notes/si_omni.md` ("Playtesting: intro never ends").

## Battle logs and replay

The playtest that produced "Bug fixes after playtesting" above left no record of what actually
happened, which made both bugs there hard to pin down. Every battle is now recorded to a JSON Lines
log and can be deterministically replayed, so future playtest reports come with a log instead of a
memory of what seemed to happen.

**Format.** One JSON object per line, UTF-8, each carrying `type` and `tick` (the `header` is always
line 1, `tick` 0). Record types:

- `header`: `format_version`, `battle_asset` (`AssetId` string, e.g. `vanilla:battle/bf001`), `bts_path`
  (the script's own basename), `seed`, `width`/`height`, `started_at` (wall-clock UTC, the *only*
  wall-clock value in the log -- never read by the simulation, informational only), and `regiments`: one
  row per regiment with `id`, `name`, `side`, `sprite_resource`/`sprite_base` (the script's troop sprite
  resource and its resolved `FOL`/`BOP`/`PAL` file base, `whshr.battlefield.troop_sprite_files` -- to
  check a suspected wrong sprite mapping), `models`/`ranks`/`x`/`y`/`direction`, the decoded combat
  `profile` (WS/BS/S/T/W/I/A/Ld, armour, strength bonus, missile code/range) and `psychology` flags.
- `order`: one scene event (`whshr.battle_scene.BattleScene.handle`'s `select`/`deselect`/`move_to`/
  `attack`), tagged with the tick count at which it was applied (whether or not the engine accepted it;
  a rejected order -- outside the field, no selection, routing -- is still visible in the log as an
  order with no effect on the following snapshot).
- `event`: one `whshr.battle_events.BattleEvent` (`whshr.combat`, `whshr.engine`), as `{"kind", "text",
  ...structured fields}`. Kinds: `clash`, `combat_round` (per-side attack counts, hit/wound/save target
  numbers, and every individual attack's rolls and result), `leadership_test` (Ld, roll, modifier,
  `cant_break`, `passed`), `rout_start` (position and flee-point), `rally_test` (Ld, roll, `cant_rally`,
  `blocked_by_enemy`, `nearest_enemy_distance`, `passed`), `shooting`/`reload` (shots, target numbers,
  rolls, distance, range), `fled` (position against `width`/`height` when a routing regiment leaves the
  field) and `result` (`victory`/`defeat` with the side counts below). `BattleEvent` is a `str` subclass,
  so `Battle.events` is unchanged for the frontend's rolling event-log overlay and for BDD scenarios that
  compare it against plain strings (`tests/test_combat.py`); `.kind`/`.data` are the structured payload
  `BattleLogger` reads instead of re-parsing text.
- `snapshot`: written every battle segment (`combat.SEGMENT_TICKS`, 19 ticks) and once more at the
  battle's end: `side_counts` (`Battle.side_counts()`: active/routing/fled/destroyed/total per side --
  the exact inputs `Battle._update_result` checks, so "why no result was declared" is always visible even
  when the answer is "one side still has an active regiment"), `result`, and `regiments` (`Battle.
  snapshot()`: x/y/direction/models/corpses/walking/routing/fled/in_melee/melee_group/melee_touching/attack_target/
  reload_ticks per regiment).
- `result`: written once, when `Battle.result` is set, with the final `side_counts`.
- `end`: `reason` (`"result"`, `"player quit"`, or `"scene left"` for any other scene exit) and the final
  tick; always the last line.

**Where logs go.** `whshr.battle_log.BattleLogger` writes to
`<log_dir>/battle-<YYYYmmdd-HHMMSS>-<battle_asset_name>.jsonl` (`battle_log.default_log_path`).
`whshr.battle_scene.BattleScene(battle, log_dir=..., seed=...)` owns the logger: it is created and the
header written in `enter`, an `event`/`snapshot` pair after every tick in `update`, an `order` in
`handle`, and `end` in `exit` or via the idempotent `close_log(reason)` (also called by
`frontend/app.py`'s `finally` block for a window close or Ctrl+Q mid-battle, since that path bypasses
`SceneMachine`'s own transition/exit). `log_dir=None` disables logging outright (`BattleLogger(path=
None)` is a no-op recorder); `campaign_scenes.IntroScene`/`MainMenuScene`/`BriefingScene` all take and
forward `log_dir`/`seed` so the setting applies however the battle is reached -- the `--battle` shortcut
or intro -> menu -> briefing. `logs/` (repository root) is the default and is `.gitignore`d: a log names
regiments and units straight from the game script, so it must stay local like `samples/`/`battles/`.
**Logging never crashes the battle**: any `OSError` opening or writing the log file (missing/unwritable
directory, disk full, ...) disables the logger silently (`BattleLogger.enabled` reports this) instead of
raising; `tests/test_battle_log.py` covers both a disabled and an explicitly unwritable log directory.
The file is flushed after every write, so a crash or a closed window still leaves a usable log.

**CLI.** `python3 -m whshr engine <WARFB>`: `--battle-log DIR` (default `logs/`), `--no-battle-log`,
`--seed N` (default 1995, unchanged from before this feature so existing behaviour stays reproducible
by default). The engine prints the log path on exit. `python3 -m whshr battle-replay <WARFB> <log.jsonl>`
(`whshr.battle_replay`, stdlib-only) rebuilds the battle from the header (same BTS, same seed) through a
fresh `BattleScene`, replays every recorded `order` at its tick via `scene.handle` and every tick via
`scene.update(BATTLE_TICK_SECONDS, ...)` (never wall-clock time), and compares each recorded `snapshot`
(a small float tolerance, `1e-6`, covers accumulated movement rounding) plus the final `result`. It
prints `replay identical: ...` or the first divergence (`tick`, `regiment`, `field`, `recorded`,
`replayed`) and exits 1; `--timeline` prints every applied order and emitted event per tick; `--until
TICK` stops early. Tests inject a synthetic `SceneAssets` via `battle_replay.replay(..., context=...)`
rather than the real installation (docs/testing.md).

**Determinism contract.** Recording and replay run the identical simulation code path -- `BattleScene.
handle`/`update`, in turn `Battle.tick`/`order_move`/`order_attack` -- rather than two implementations
that could drift apart. This only holds if every source of randomness or non-determinism stays inside
`Battle.rng` (seeded, `whshr.combat`'s only randomness source) and ticks are always driven by the fixed
100 ms step, never measured wall-clock time; `BattleScene.update`'s `FixedStepClock` already enforces the
latter for a live battle, and replay calls `scene.update(BATTLE_TICK_SECONDS, ...)` once per recorded
tick for the same reason. `started_at` in the header is the one deliberate exception: wall-clock,
informational only, and never read back by `battle_replay`.

**Verification.** A scripted-player run of the real BF001 installation (a synthetic scratch script, not
committed: charge `Grudgebringer<Cavalry` at the nearest enemy, order `Mercenary_Crossbows` toward the
field edge, then let the AI and `whshr.combat` play out for up to 4000 ticks) produced a 474-line log
(210 snapshots, 47 combat rounds, 23 Leadership tests, 16 routs, 14 shooting volleys) and replayed
byte-for-byte identical (`replay identical: vanilla:battle/bf001 (...), final tick 4000, result None`).
The battle never resolved in that run: three `Clanrat_Warriors` regiments were destroyed in melee, but
`Hiln's_Guard`, `Otto_Hiln` and `Sleaquit` stood well outside `ai.ENGAGE_DISTANCE` (400 units, already a
documented placeholder) the whole time and the AI never advanced them -- exactly the kind of "why no
result was declared" question the `snapshot` `side_counts` field exists to answer, now visible in the log
instead of only inferable from a playtest report. `tests/test_battle_log.py` covers the same scenarios
synthetically: record + replay identical, a combat round's full roll/Leadership detail, a routing
regiment's field-edge removal logged with its position, per-side `side_counts` in a snapshot, an
unwritable log directory, disabled logging, and that every log line parses with the header first.

**Open questions / observations, not fixed here (per the task's scope):**
- A destroyed regiment (`models == 0`) can still show `in_melee: true` with a stale `melee_group`/
  `melee_touching` in a snapshot (seen in the BF001 log above): `resolve_contacts` only releases
  regiments it still considers `active`, not the destroyed regiment's own flags, and `refresh_melee_state`
  only runs on regiments that are themselves `in_melee`. Cosmetic in the current simplified combat model
  (a destroyed regiment is excluded from `resolve_melee`/`resolve_contacts`/`resolve_shooting` by their
  own `active`/`in_melee` filters either way), but visible now that snapshots are logged.
- A regiment that starts already outside the field's declared bounds (BF001's `Mercenary_Crossbows` at
  x=1814, field width 1600) never logs a `fled` event even if left alone there, since that only fires for
  a *routing* regiment crossing the boundary; whether the script's field size or such a unit's placement
  is the one that needs revisiting is unresolved.
- `resolve_rally` still runs its Leadership test (and now logs a `rally_test` record) for a regiment that
  has already fled (`fled=True`); harmless (a fled regiment is inert either way) but a slightly misleading
  log entry.

## Display scaling and fullscreen (research)

Prompted by the owner's reaction to the integer-scale fix (`whshr/frontend/scene_view.py`
`NativeScreenView`): it makes fonts and pixel art crisp again, but at a non-multiple window size
it now letterboxes down to a small integer instead of filling the screen the way the engine used
to (blurrily). Two related asks: a real fullscreen mode, and a scaling technique that fills any
window/display size without either the fractional-nearest blur the original bug report was about,
or the letterboxing the fix traded it for. Not implemented yet — this section records the design
so the next step can go straight to it.

### Why per-view fractional scaling was the wrong place to fix this

Today every view (`CaravanView`, `MissionMapView`, `MainMenuView`, …) draws its own bitmaps and
text quads straight into the window-sized render target (`Gpu.target`, sized to the actual window
in `app.py`), multiplying every coordinate and size by that view's own `_layout()` scale. This is
why the bug had to be fixed once in `NativeScreenView` and then inherited everywhere, and it's also
why there's no single place to apply a smarter upscale filter — by the time a quad is drawn it is
already sized in window pixels, one draw call at a time, each independently sampled by its own
`nearest`/`linear` sampler.

**Better architecture: render at native size, upscale once.** Give the frame a second, always
`640x480` off-screen `RenderTarget` (the game's native resolution is fixed and known — see
`NativeScreenView`). Every view draws into *that* using plain, unscaled native pixel coordinates
(no more `_layout()`, no more `scale` threaded through every `draw()`/`_button_at()`/hit-test
method — a real simplification, not just a rendering change). Once a frame is complete, one final
full-screen pass stretches that 640x480 color texture onto the actual window-sized target. This
also fixes hit-testing for free: mouse coordinates only need converting from window space to
native space once, at the same place the final blit computes its own placement/scale, instead of
duplicating that math in every view's `_mission_at`/`_button_at`.

### The final upscale filter

With rendering unified into one texture-to-window blit, the filter for *that one blit* decides
sharpness for the whole game at once:

| Technique | Result | Cost |
|---|---|---|
| `nearest`, integer scale + letterbox (current fix) | Pixel-perfect, but wastes screen space unless the window is an exact 640x480 multiple | none |
| `linear`, stretch to fill (the old per-quad behavior that prompted the whole investigation) | Fills the screen, but blurs text and pixel art at any non-integer scale | none |
| **"Sharp-bilinear"**: sample the native texture with `linear` filtering, but remap the fragment shader's UV so that only the thin band actually crossing a source-pixel boundary gets interpolated, using the exact `screen_size / 640x480` scale as a shader uniform (`uv_px = floor(uv*640) + saturate((frac(uv*640) - 0.5 + 0.5/scale) * scale)` and the analogous line for the y axis, then sample at `uv_px/640`) | Fills the screen at any size, looks crisp because most of every source pixel is still flat-sampled — only its edges blend; this is the technique behind emulators' "sharp-bilinear-simple" / RetroArch's default pixel-art shader | one shader, no extra texture, one draw call — cheap |
| Edge-detecting upscalers (xBR/hqx family) | Best for hand-drawn sprite art, invented for exactly this kind of asset | Real complexity (multi-tap kernels, usually precomputed at fixed 2x/3x/4x factors) for a benefit that matters more to sprites than to the mostly text/UI screens the bug was about; not recommended as the first step |

Recommendation: implement the native-target-plus-one-final-blit architecture with the
sharp-bilinear shader for that blit. It fills the screen at any resolution/aspect ratio (no
letterbox unless the window's aspect ratio actually differs from 4:3, which needs one either way),
keeps text and UI art crisp, and is one shader — much less engineering than an xBR-style filter.
`ScreenQuad.filter` already supports choosing `nearest`/`linear` per quad
(`whshr/frontend/gpu.py`); the new blit would use a bespoke pipeline instead, since sharp-bilinear
needs the scale as a uniform, not just a sampler mode.

### Fullscreen

No fullscreen support exists today (`open_window` in `whshr/frontend/app.py` always opens a plain
window at the caller's `size`; there's no `--fullscreen` flag and no window-resize handling).
Recommended approach: **borderless fullscreen**, not exclusive (`pygame.FULLSCREEN`) — sized to
`pygame.display.Info()`'s current desktop resolution, opened with `pygame.NOFRAME` (no exclusive
video-mode switch, which is the flaky part on Linux/Wayland/X11 and multi-monitor setups). Once
rendering is unified behind one native-to-window blit (above), fullscreen is just "a window sized
to the desktop" — no special-casing needed elsewhere, and the same code path also gives cheap
support for resizing an ordinary window at runtime (recreate `Gpu.target` — a `RenderTarget` sized
to the window — on `pygame.VIDEORESIZE`; every other GPU resource is sized to its own content, not
the window, so nothing else needs to change). A runtime fullscreen toggle (e.g. Alt+Enter/F11) is
then simply switching `size` and rebuilding `Gpu.target`; deferred as a nice-to-have, not required
for the first fullscreen pass.
