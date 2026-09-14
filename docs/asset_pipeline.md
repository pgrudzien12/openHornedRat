# Lazy asset pipeline and campaign scene plan

## Goal

Load original game data directly from a user-selected `WARFB` installation without
copying it into the engine, extracting it into the repository, or decoding all assets
at startup. The engine must support the first campaign flow:

```text
intro cutscene -> main menu -> campaign room -> mission briefing -> battle
```

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
- A scene declares its immediate assets and optional next-scene prefetches.
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
| `SceneManifest` | Immediate and prefetch dependencies for one scene. |
| `Scene` | Presents a state and owns the transition to the next state; it never discovers arbitrary files itself. |

## Logical asset catalog

Use namespaced IDs rather than raw filesystem paths in scene and gameplay code.
The first catalog is generated from existing Python readers and contains only metadata:

```text
vanilla:cutscene/intro
  source: REMOTE/BINARY/ANIM/A13.SI
  decoder: omni-si
  produces: smacker-video, wav-audio, midi, event-track

vanilla:ui/main-menu/background
  source: FILE/DLL/BITMAP.DLL, bitmap resource <id>
  decoder: pe-bitmap

vanilla:campaign/mission-window/bf001
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

Only semantic mappings belong in the catalog. Do not write a hand-maintained table
for every `.FOL`, `.BOP`, `.WAV`, or texture file. File references already present in
the original scripts remain the canonical dependency graph.

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

### 2. Main menu

Load the menu background, palettes, fonts, buttons, and text resources. Initially it
only needs a functional New Campaign action and Quit action. Release cutscene-only
video/audio assets once the transition finishes.

### 3. Campaign room

Implement a normalized scene rather than attempting to emulate every original
`WND.DLL` glue command immediately:

```text
CampaignRoom
  background
  counsellor visual
  treasury/money display
  current mission card
  briefing action
  battle action
```

The existing `WND.DLL` campaign-flow parser supplies mission-window, briefing,
mission, reward/cash, and next-window links. Unknown original commands remain in a
campaign adapter and must not leak into UI rendering.

### 4. Mission briefing

Load only the selected mission's text, portraits, speech, and optional scene/video
assets. The Start Battle action resolves one logical battle ID.

### 5. Battle

Load the selected `.BTS` and `.MRC`, then lazily resolve their direct plan-map,
palette, terrain, scenery, and unit-sprite dependencies. The battle scene owns these
large resources and releases them when returning to campaign.

## Implementation order

1. Add `AssetId`, `AssetLocator`, source fingerprint, and typed catalog record types,
   matching the `Installation` lookup contract.
2. Add a Python catalog generator for known cutscenes, PE resources, campaign flow,
   fonts/palettes, and battle scripts. Test generated IDs and source resolution.
3. Add catalog loading and an in-memory typed `AssetCache`.
4. Add a `Scene` interface, `SceneManifest`, transition coordinator, and bootstrap
   loading/error scene.
5. Implement the intro cutscene and menu transition.
6. Implement the functional menu and normalized campaign room backed by the campaign
   flow graph.
7. Implement a mission briefing that resolves and enters one battle.
8. Connect the existing deterministic battle model and the pygame-ce/zengl frontend to
   install-backed map and sprite loading.

The Python reference implementation now provides `Scene`, `SceneManifest`,
`Transition`, and `SceneMachine`. It intentionally has no SDL2, HTTP, OpenGL, or
decoder dependency. The runtime frontend drives the same lifecycle directly.

## Deferred work

The first scene pipeline does not require original campaign save formats, complete
glue-script semantics, counsellor animation fidelity, combat, AI, mission bytecode,
audio mixing, mod packages, or a persistent disk cache. Each later addition must use
the same logical-ID, lazy-loader, and scene-manifest contracts.
