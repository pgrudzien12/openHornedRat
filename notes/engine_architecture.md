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
