# Engine architecture

The runtime will be a standalone SDL2 application with an OpenGL renderer. SDL2 owns
windowing, input, audio device access, and platform integration; it is not a renderer.
The first native executable is `horned-rat-engine`.

Python remains the reference layer for original-installation readers, normalized data
models, reverse-engineered rules, and deterministic simulation tests. A frontend must
not duplicate decoder or rules semantics. The initial `whshr.engine` module defines the
presentation-independent battle state and fixed-tick movement behaviour.

The first native milestone deliberately validates its installation argument and provides
a fixed-tick click-to-move loop, but does not yet load game assets. The next increment
will feed normalized `whshr.engine` battle data to the native frontend, followed by plan
map and directional-sprite rendering. No extracted game data belongs in this repository.

Godot may be used for disposable visualization experiments, but it must not own assets,
rules, saves, mission formats, or modding. Original mission DLLs are data inputs only:
the engine will never execute them as native code.
