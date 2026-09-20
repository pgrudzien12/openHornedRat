# Lazy asset pipeline and runtime loading

## Goal

Load original game data directly from a user-selected `WARFB` installation without
copying it into the engine, extracting it into the repository, or decoding all assets
at startup. The engine must support the first campaign flow:

```text
intro cutscene -> glue-driven campaign front end -> battle/movie/built-in activity -> resumed glue program
```

The campaign architecture and phased implementation plan are specified in `notes/glue_runtime_architecture.md`. The menu, caravan, map, briefings and encounters are compositions executed by one shared `WND.DLL` glue interpreter.

The initial implementation targets the GOG v1.0 installation. Its asset readers,
paths, and reverse-engineered formats remain the Python `whshr` reference
implementation, which is also the engine: the Python runtime frontend (pygame-ce, zengl) uses
these contracts directly.

## Principles

- Original game files stay in the installation selected with `--data <WARFB>`.
- The engine never uses a hard-coded Wine-prefix path.
- The existing lookup precedence is preserved: `UPDATE/BINARY` overrides
  `FILE/BINARY`; all original filenames are resolved case-insensitively.
- A catalog indexes metadata only. It never imports game bytes or becomes a second
  source of asset truth.
- Assets load on demand and are cached by stable logical ID and source fingerprint.
- A coarse scene declares predictable immediate assets and optional next-scene prefetches. Interpreted glue programs request dynamically discovered resource assets through the same catalog and cache.
- Caches have explicit ownership. Transitioning away from a battle can release its
  terrain, scenery, and unit resources without evicting reusable campaign UI assets.
- Original mission DLLs are not native plugins and must never be executed as code.

## Asset layers

| Layer | Responsibility |
|---|---|
| `AssetLocator` | Validates `WARFB`, resolves case-insensitive original paths, and applies `UPDATE -> FILE` precedence. |
| `AssetId` | Stable namespaced identifier, for example `vanilla:cutscene/intro` or `vanilla:battle/bf001`. |
| `AssetCatalog` | Metadata mapping from an `AssetId` to source path/resource ID, decoder, dependencies, and source fingerprint. |
| `AssetLoader` | Loads and decodes a requested typed asset from the original installation. |
| `AssetCache` | Holds decoded CPU data and uploaded GPU resources, keyed by `AssetId` and invalidated when the source changes. |
| `SceneManifest` | Predictable immediate and prefetch dependencies for one coarse scene. |
| `Scene` | Owns a coarse application mode such as the intro, glue front end, movie or battle. |
| `GlueContent` | Resolves programs, windows and their dynamic resource references through catalog IDs. |

## Logical asset catalog

Use namespaced IDs rather than raw filesystem paths in scene and gameplay code.
The first catalog is generated from existing Python readers and contains only metadata:

```text
vanilla:cutscene/intro
  source: REMOTE/BINARY/ANIM/A13.SI
  decoder: omni-si
  produces: smacker-video, wav-audio, midi, event-track

vanilla:bitmap/optionscreen
  source: FILE/DLL/BITMAP.DLL, bitmap resource <id>
  decoder: pe-bitmap

vanilla:glue-window/mainmenu
  source: FILE/DLL/WND.DLL, text resource <id>
  decoder: glue-script

vanilla:glue-program/flow-script-bp01
  source: FILE/DLL/WND.DLL, text resource <id>
  decoder: glue-script

vanilla:battle/bf001
  source: FILE/SCRIPT/BF001.BTS
  decoder: battle-script
  dependencies: player MRC, plan map, palette, terrain, scenery, troop sprites
```

The catalog may be stored as a generated JSON index under the user's cache or
configuration directory. It is safe to regenerate, contains no extracted art/audio,
and is invalid if its installation fingerprint or generator version changes.

Only semantic mappings belong in the catalog. Resource-level IDs may be generated from original resource indexes; do not maintain a handwritten list for every `.FOL`, `.BOP`, `.WAV`, bitmap or texture. File and resource references in the original scripts remain the canonical dependency graph.

## Load lifecycle

### Startup

1. Parse the runtime command's `--data <WARFB>` argument.
2. Validate the expected `FILE`, `FILE/SCRIPT`, `FILE/BINARY`, and `REMOTE`
   structure without decoding all assets.
3. Open or regenerate the metadata catalog.
4. Load a minimal bootstrap manifest: fallback font, loading screen, and error UI.
5. Enter the intro scene and request its immediate assets.

### Scene loading

1. Resolve each `AssetId` through the catalog and locator.
2. Compare the source fingerprint with an existing cached value.
3. Decode only missing or stale data.
4. Upload GPU resources only when a renderer needs them.
5. Retain assets using a scene ownership handle.
6. Prefetch the next scene at low priority while the current scene is visible.
7. Release the departing scene's handle on transition; shared assets remain alive
   while referenced by another handle.

### Interpreted glue loading

1. Load and index `WND.DLL`, `BITMAP.DLL` and string tables once through `GlueContent`.
2. Resolve the active program and its initial windows.
3. As the program opens a window or starts media, acquire the resource-level IDs referenced by that definition or instruction.
4. Retain resources while their window, animation, audio operation or saved context can use them.
5. Release resources when the owning windows and contexts are destroyed.
6. A mod override participates in the same lookup and never requires a view to open an installation path directly.

The first cache is in memory. Add a derived XDG disk cache only after profiling shows
that repeated decoding is a practical problem. A disk cache must be outside the
installation and repository, be safely invalidated, and never replace original files.

## Initial scene sequence

### 1. Intro cutscene

Load one Omni `.SI` container and its video, WAV, MIDI, and event-track objects.
Play the confirmed 8 fps video timing. While the video is playing, prefetch the main
menu manifest. Skipping the video transitions directly to the menu.

Implemented reference behaviour: `IntroScene` loads the verified game-intro container
`vanilla:cutscene/a1` (`A1.SI`) through `SceneAssets` and `AssetCache`. Its timeline
end is calculated from the Omni object schedule; either that end or a `skip` event
transitions to `MainMenuScene`. Video and audio presentation are native-frontend work.

### 2. Glue campaign front end

Enter one long-lived `GlueScene`. `GlueRuntime` executes menu, caravan, map, briefing and encounter programs; `GlueView` renders their active windows. Resource references are resolved lazily as instructions open windows, start dialogue, animate bitmaps or play media. The runtime retains its program, window and context stacks while an external activity is active.

### 3. External activity and resumption

Battle, movie, troop-selection, book, save/load, options and debrief operations cross a typed request/result boundary. A completed activity returns its result to the suspended glue instruction, which then continues the same program.

For a battle, load the selected `.BTS` and `.MRC`, then lazily resolve their direct plan-map, palette, terrain, scenery and unit-sprite dependencies. The battle scene owns these large resources and releases them when returning its result to the campaign runtime.

## Implementation order

1. Keep the existing `AssetId`, `AssetLocator`, catalog, cache and coarse scene lifecycle.
2. Add resource-level IDs and a one-time `GlueContent` index for programs, windows, bitmaps and strings.
3. Move PE bitmap decoding into the stdlib core and keep GPU conversion in the frontend.
4. Add dynamic acquire/release support for assets discovered by `GlueRuntime`.
5. Implement the lossless glue importer, runtime and render model in the phases defined by `notes/glue_runtime_architecture.md`.
6. Invoke battle, movie and built-in UI scenes through typed request/result adapters and resume the same glue runtime.
7. Add prefetch only where the next dependency is predictable and measure whether it is useful.

## Deferred work

Persistent disk caching remains deferred until profiling shows a practical need. The public mod authoring format remains deferred until normalized engine models exist; vanilla glue is a compatibility input, not the permanent modding API. Exact historical timing and other fidelity questions that do not block reachable campaign behavior may be settled after the shared runtime works.
