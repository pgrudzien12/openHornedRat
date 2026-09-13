# Engine architecture and modding direction

This is the implementation direction for the open engine. It is intentionally a
decision record, not a commitment to a final renderer or programming-language
boundary before a real-time prototype has proved the design.

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

The existing `whshr` Python package remains the reference implementation for
format readers, extractors, validation, rule experiments, and a first
headless/real-time simulation prototype. Python is deliberately useful in the
long term, not just an analysis tool. If profiling later requires native code,
settled hot paths may move behind narrow interfaces without changing data
definitions or the modding contract.

The preferred production frontend is a custom SDL2-based runtime with a 3D
renderer (initially likely OpenGL). SDL2 provides windowing, input, and audio;
it is not itself the renderer or game engine. This has more up-front work than
Godot, but preserves direct control over unusual original formats, palette
rules, sprite anchors, battle coordinates, deterministic simulation, and the
external data model.

Godot remains an acceptable disposable visualization or rapid-prototype client
if its camera, material, UI, or inspection tools materially accelerate work.
It must not own the authoritative rule implementation, asset formats, saves,
or mod format. The project does not currently rely on Godot editor workflows,
and Python is not a first-class Godot gameplay language, so adopting Godot as
the main runtime would add a bridge and lifecycle dependency without solving a
current problem.

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
- A custom frontend has a higher initial rendering/UI cost. It is justified
  only while its independent data model and Python-friendly workflow continue
  to serve the project better than an engine integration.

## Near-term consequences

1. Build M3 as a small Python simulation and visualization testbed first:
   movement, formations, `Nav*` pathfinding, collisions, directional animation,
   and debug views.
2. Keep the testbed's simulation API independent from pygame, SDL2, Godot, and
   any other presentation library.
3. Catalogue mission bytecode opcodes and model their state/event interface
   before designing the public mission schema.
4. Promote the SDL2/OpenGL frontend only after the prototype confirms the
   simulation/data boundary and identifies actual rendering needs.
