# Battle viewers

## Static 2D game-view renderer

`python3 -m whshr viewer-2d <WARFB> <BFxxx.BTS> <out.png>` writes a local, top-down PNG using
only the game's 2D asset path. Unlike the PBX viewer below, it loads the battle's `loadplanmap`
(`MAP*.FOL/.BOP`) as the background and composites the first idle frame of each unit's mapped
`.FOL/.BOP` sprite over it. It reads enemy/NPC units from the `.BTS` and the player force from
the referenced `.MRC`.

The default 544×386 viewport is the size of the supplied cropped game screenshot. Its default
centre is the battlefield centre; `--target-x`, `--target-y`, and `--zoom` select a game-world
viewport (at default zoom, one BTS unit is one output pixel). Soldiers follow the block formation
traced in `GAMEF.DLL` (`whshr/formation.py`; `notes/game_rules.md`, "Formations"): the third `s_side`
value (current size) gives the number of models and the fourth the ranks; the unit position is the
front-rank centre, ranks stand 12 BTS units apart behind it, leftover models widen the front ranks,
and the slots are rotated by the unit's script `dir`. `--spacing` (default 12, the traced value) is
kept for experiments. War machine, monster and wagon layouts are not drawn yet. Troop sprites are drawn at
0.45 world units per sprite pixel (measured on a BF001 screenshot, not traced), so models keep the gaps seen
in the game.

Directional unit frames use the established `phase * 8 + direction` layout and the first standing
phase for standard 104-frame sets. Script `dir` is 0 = +Y (north on the plan map) and increases
clockwise (512 units per turn); see "World conventions" below. Sprite directions are stored
counter-clockwise, so the renderer uses
`frame_direction = direction_offset - round(dir / 64) (mod 8)`. The zero offset (which sprite frame
`dir = 0` selects) is still unverified; `--direction-offset` is deliberately exposed for
screenshot calibration.
Rendering uses each FOL frame's horizontal anchor and provisional foot-line anchor directly.

This renderer intentionally stays separate from `whshr.battle3d`: it does **not** decode PBX
terrain, 3D scenery, lighting, or the 3D camera. Its output is local derived game data and belongs
under ignored directories such as `samples/`; neither it nor `screenshots/` is committed.

Validation against the local GOG installation rendered `BF001.BTS` at
`--target-x 1100 --target-y 600`: `MAP001` loaded successfully and all 9 scripted/MRC regiments
(85 soldiers) resolved into the default 544×386 RGB PNG.

## Static 3D PBX asset viewer (ROADMAP 2.3)

`python3 -m whshr viewer <WARFB> <BFxxx.BTS> <out.png>` renders a local PNG with no
third-party runtime dependencies. It reads the battle script, decodes `GRND.PBX`,
`SCENERY.PBX`, and `SPRITES.PBX`, resolves `placefurniture` names through the existing EXE
furniture table, and uses `GRND.GD` to place scenery and unit sprites at ground height.

The viewer has two camera modes. **The original battle camera is a perspective camera**: visual
comparison with the running game (September 2026) rules out an orthographic/isometric projection,
so `--projection perspective` is the model to calibrate and to carry into an engine.
`--projection orthographic` remains only as a diagnostic view (for example, top-down orientation
checks against plan maps). The perspective mode is a look-at camera: its target is the `--target-x`/`--target-y` ground point (BTS world units), with
the target height read from `GRND.GD`. The eye is offset from that point by yaw, pitch/elevation,
and `--distance` mesh units; vertical `--fov` determines the perspective framing. Ground and
scenery textures are sampled from their PBX palettes; black texels in scenery textures are treated
as transparent. Unit sprites use the first idle frame when available, falling back from the
per-battle sprite bundle to `BINARY/` for armies not bundled in `SPRITES.PBX`.

Perspective triangles are clipped to the camera near plane. Texture coordinates use
reciprocal-depth interpolation, and the depth buffer stores reciprocal camera depth, so terrain
and scenery occlude each other correctly rather than exhibiting affine texture or depth inversions.
`--zoom` only affects the orthographic mode; perspective uses `--distance` and `--fov`.

`--diagnostic` writes a JSON sidecar beside the PNG and draws magenta crosses at scripted scenery
pivots, green crosses at unit origins inside the terrain mesh, and red crosses for unit origins
outside it. `whshr terrain-check <WARFB> [BFxxx]` compares every `grnd.xof` vertex with
`GRND.GD.height(x,z)`. All 44 version-2 terrain meshes use the direct mapping, with a worst
maximum error of 0.02123 mesh units (`BF004_5`); axis flips yield errors many orders of magnitude
larger. This confirms that PBX X/Z and GD X/Z share orientation and scale, while PBX Y equals
the GD plane height.

Both modes have `--yaw`, `--pitch`, `--target-x`, and `--target-y` controls; target coordinates
use BTS world units. Orthographic additionally uses `--zoom`; perspective additionally uses
`--distance` and `--fov`. The CLI defaults (`orthographic`, `yaw=45`, `pitch=26.565`, and `zoom=1`)
are historical and are not game values. Lighting uses `--ambient` plus a directional
`--light X Y Z` vector and PBX normals. The `[FIELD]` `Camera`, `Position`, and `Bank angle`
values are not yet applied because their runtime semantics remain unverified.
`--scenery-scale` is an explicitly provisional uniform multiplier for scenery meshes only; it
exists to measure the visual mismatch before any unsupported per-object scale rule is recorded.
`yaw` places the eye at `target + distance * (sin yaw, ·, cos yaw)` in mesh X/Z, so the camera
looks along `(-sin yaw, -cos yaw)`: `yaw=180` looks north with +X to the right. An earlier
`viewer_yaw = 180 - Camera` rule predates the handedness convention below and is void.
The working hypothesis is now `viewer_yaw = 180 + Camera`, i.e. `Camera` is the view heading
clockwise from north: `BF001` stores `Camera:45` and the in-game compass reads "N ne E"
(yaw 225); `BF007` `Camera:90` would look east (yaw 270). `viewer-web` applies this as its initial
yaw, pending validation against more references.

### World conventions

- **Handedness.** BTS X/Y map to mesh X/Z with +Y up, which is a left-handed frame (as in Direct3D
  Retained Mode): seen from above with north (+Z) at the top, +X points right. A right-handed
  (OpenGL-style) camera basis mirrors every render in X relative to the plan map; any future engine
  must keep this in mind. `battle3d.check_orientation()` (run by `whshr check`) guards it: at yaw 180,
  pitch 85, +X must project right, +Z up, and the look-at target to the screen centre. A top-down
  `BF001` render matches `samples/bf001_battle.png` (river, gully, and out-of-field units).
- **Script `dir`.** 512 units per turn, 0 = +Y, clockwise. Evidence (medium-high confidence): over
  all `BF*.BTS`, 426 units with non-zero `dir` face the nearest unit of another army with mean
  cosine +0.44 (55 % within 45°) under this convention, versus +0.20 for counter-clockwise and
  ≤ 0 for E/W/S zero points; in `BF001`, Otto Hiln (dir 105) and the Eshin assassin (dir 378)
  face each other and the three Clanrat units face their bearings to Hiln.
- **Scenery rotation.** The same clockwise convention: local mesh +Z faces `(sin a, cos a)` and
  local +X faces `(cos a, -sin a)` in BTS X/Y, identical to the formation basis. Verified top-down
  against plan maps: `BF036` pipe grilles (dir 128/256/384) protrude toward the drawn slime in all
  four cases, and `BF035` TwinTowers (dir 71) lie on the plan map's NW–SE diagonal; the previous
  counter-clockwise transform put them SW–NE.
- **3D sprite direction.** Frames are relative to the camera: with screen-up heading
  `H = (yaw + 180) * 512/360`, `frame_direction = round((H - dir) / 64) mod 8`. At yaw 180 this
  reduces to the 2D viewer's formula with offset 0. The zero offset is derived, not observed.

For manual calibration, `whshr viewer-web <WARFB> <BFxxx.BTS>` starts a local panel at
`http://127.0.0.1:8765/`. A projection select switches between orthographic and perspective
look-at rendering. The panel has yaw (0–360), pitch (5–85), distance, vertical FOV, orthographic
zoom, ground-target X/Y, ambient, and scenery-scale controls. The mini-map shows the battle's plan
map (BTS Y up), player units in blue, script units in red, the target crosshair, and a look-direction
arrow; clicking it sets the ground target X/Y. Rendering is latest-wins (one request in flight),
and invalid values or render failures are shown as text on the page. Decoded PBX/GD assets and EXE
tables are cached per process. The HTTP server is bound only to loopback and stops with `Ctrl+C`.

The result verifies the complete static asset path for `BF001` and `BF015`: terrain and every
scripted scenery placement resolve, as do all units with a sprite resource. `BF015`'s NPC
Ceridan deliberately uses `VoidType`, so it has no sprite to render. The camera model is settled
(perspective) and sufficient for an engine. Its exact original parameters (how `Camera` maps to the
heading, pitch, FOV, eye distance/height, `CameraEdge` limits) are deliberately not pursued.
The sprite frame for `dir = 0`, mesh pivots, texture transparency, and original lighting remain open
questions for 2.4 and Wine instrumentation. Formations in both viewers follow the traced block layout
(12 BTS units = 1.5 mesh units between models) and the measured troop sprite scale; against it, PBX pines
look about twice as large as in the game screenshot (see `--scenery-scale`).

`BF001` also demonstrates that not every initial unit is inside the rendered terrain mesh:
`Mercenary Crossbows` is placed at `(1814, 502)`, beyond the `1600`-unit field width and the
`GRND.PBX` surface's `x=200` mesh limit (one mesh unit is eight script units). `GRND.GD` still
contains a height at this coordinate. The viewer deliberately renders the unit rather than
clamping it, preserving the scripted starting position.
