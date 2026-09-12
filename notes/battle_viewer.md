# Static 3D battle viewer (ROADMAP 2.3)

`python3 -m whshr viewer <WARFB> <BFxxx.BTS> <out.png>` renders a local PNG with no
third-party runtime dependencies. It reads the battle script, decodes `GRND.PBX`,
`SCENERY.PBX`, and `SPRITES.PBX`, resolves `placefurniture` names through the existing EXE
furniture table, and uses `GRND.GD` to place scenery and unit sprites at ground height.

The view is an orthographic isometric projection. Ground and scenery textures are sampled from
their PBX palettes; black texels in scenery textures are treated as transparent. Unit sprites use
the first idle frame when available, falling back from the per-battle sprite bundle to `BINARY/`
for armies not bundled in `SPRITES.PBX`.

`--diagnostic` writes a JSON sidecar beside the PNG and draws magenta crosses at scripted scenery
pivots, green crosses at unit origins inside the terrain mesh, and red crosses for unit origins
outside it. `whshr terrain-check <WARFB> [BFxxx]` compares every `grnd.xof` vertex with
`GRND.GD.height(x,z)`. All 44 version-2 terrain meshes use the direct mapping, with a worst
maximum error of 0.02123 mesh units (`BF004_5`); axis flips yield errors many orders of magnitude
larger. This confirms that PBX X/Z and GD X/Z share orientation and scale, while PBX Y equals
the GD plane height.

The result verifies the complete static asset path for `BF001` and `BF015`: terrain and every
scripted scenery placement resolve, as do all units with a sprite resource. `BF015`'s NPC
Ceridan deliberately uses `VoidType`, so it has no sprite to render. It is a diagnostic viewer
rather than a reproduction of the original camera. The exact mapping of script `dir`, mesh
pivots, texture transparency, and original camera/lighting remain open questions for 2.4, 2.5,
and Wine instrumentation.

`BF001` also demonstrates that not every initial unit is inside the rendered terrain mesh:
`Mercenary Crossbows` is placed at `(1814, 502)`, beyond the `1600`-unit field width and the
`GRND.PBX` surface's `x=200` mesh limit (one mesh unit is eight script units). `GRND.GD` still
contains a height at this coordinate. The viewer deliberately renders the unit rather than
clamping it, preserving the scripted starting position.
