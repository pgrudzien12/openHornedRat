# Battle terrain `GRND.GD` (ROADMAP 2.2)

## Status

| Item | Status |
|---|---|
| Record layout (plane per triangle, 64×64 cells × 2) | ✅ verified structurally on all 45 files |
| Diagonal flag (1/2) and unused cells (0) | ✅ verified: seams are continuous only with this triangulation |
| Orientation (GD x → world x, GD z → world y) and scale (1 GD unit = 8 world units) | ✅ verified visually on 9 battles against the plan map |
| Height scale in world units (×8, i.e. uniform scaling) | 🟡 hypothesis (consistent, not proven) |
| Why a given cell uses diagonal 2 | 🟡 no simple rule found |
| Texturing / materials | ❌ not in `GRND.GD` (probably `GRND.PBX`, see open questions) |

## Format (ready to paste into FORMATS.md)

`FILE/MESH/<MESH>/GRND.GD`, where `<MESH>` is taken from `loadmesh:` in `.BTS`.
Always 196608 bytes, no header: **64 × 64 cells × 2 triangles × 24-byte record**.
Little-endian.

```c
struct GdTriangle {          // 24 bytes
    float32 gx;              // dh/dx: plane slope along x
    float32 gz;              // dh/dz: plane slope along z
    float32 x;               // anchor point of the plane (GD units)
    float32 h;               // height at the anchor
    float32 z;
    uint32  diag;            // 0 = unused cell, 1 or 2 = which diagonal splits the cell
};

// cell (cx, cz), cx, cz = 0..63; row stride is always 64 cells
GdTriangle A = file[2 * (cz * 64 + cx)];      // anchored at (cx*10,     cz*10)
GdTriangle B = file[2 * (cz * 64 + cx) + 1];  // anchored at ((cx+1)*10, (cz+1)*10)

// height of the triangle t at a point (X, Z):
//     h(X, Z) = t.h + t.gx * (X - t.x) + t.gz * (Z - t.z)
// which triangle covers (X, Z)? with u = X - cx*10, v = Z - cz*10 (0..10):
//     diag == 1: split along (x,z)-(x+10,z+10);  u >= v -> A, else B
//     diag == 2: split along (x+10,z)-(x,z+10);  u + v <= 10 -> A, else B
```

- A cell is 10 GD units wide. **1 GD unit = 8 world units** (`.BTS` coordinates), so one cell
  is 80 world units. By coincidence, a plan-map pixel is also about 8 world units.
- **GD x = world x, GD z = world y** (up the plan map). The grid origin is (0, 0) in both
  spaces, with no offset.
- Heights `h` are in GD units. Values are 0…80. 94% of vertex heights are whole numbers,
  and slopes are multiples of 0.1 (for example ±0.2, ±2.5 = a 25-unit step over one cell).
  The file stores triangle planes, not vertices. The vertex heights are recovered by
  evaluating the planes at the cell corners.
- Only a rectangle of **nx × nz cells starting at cell (0, 0)** is used. Every other record is
  24 zero bytes (`diag = 0`). The row stride stays at 64 even when nx < 64.
- Both triangles of a cell always carry the same `diag`, and neither 0 nor any other value
  appears inside the used rectangle.
- Small float noise such as `gz = 1.05e-06` or `h = 9.00001` comes from the tool that
  converted the meshes (it computed planes from a vertex mesh, probably `.ASC`: the EXE has a
  `mesh {*.asc}` file filter). It has no meaning.
- The grid always covers the battlefield, and is often larger:
  - nx ≥ ceil(field_x / 80) and nz ≥ ceil(field_y / 80);
  - usually 4 extra cells on the right and top, sometimes 0 (e.g. `BF004_1`, `BF004_2`, `BF036`)
    and at most 10;
  - 9 older battles (`BF001`, `BF003`, `BF004`, `BF004_3`, `BF005`–`BF008`, `BF012`) use the
    whole 64×64 grid (5120 world units), but relief exists only over the field. Outside it
    the terrain is flat at the edge height.
- `BF004` has no `.BTS` of its own. `BF004/GRND.GD` is not byte-identical to
  `BF004_3/GRND.GD`, but it is nearly the same terrain: 6741 records differ (mostly float
  noise), yet only 194 of 4225 vertices change height (by at most 10 GD units) and all
  diagonals are equal. Probably an earlier or later version of the same mesh.
- `MAXARMY.BTS` (a test file) uses `loadmesh:flatmesh`, but no such directory exists.
- `GRND.GD` holds **no texture, material or color index**. The only per-cell data besides
  geometry is the diagonal.

Vertex height from the planes, for a vertex (vx, vz): take any triangle touching the vertex
(all of them agree, maximum seam difference ≤ 0.015 GD units across all 45 files).

## How it was verified

Structural check, on all 45 files (`gd_render.py --check`):
- anchors of A and B equal the cell corners;
- `diag` is in {1, 2} inside the rectangle and 0 outside, and everything outside is zero bytes;
- every vertex evaluated from every adjacent triangle gives the same height (≤ 0.015). With
  the opposite triangle assignment for `diag = 1` the error rises to 2–43 units, so the
  triangulation above is the only consistent one.

Totals: 128162 records with diag 1, 5318 with diag 2, 235160 unused.

Visual check (`extracted/terrain_gd/*.png`, each image = relief | plan map | plan map shaded
by the terrain with contours every 2 GD units), on `BF001`, `BF004_1`, `BF005`, `BF009`,
`BF010`, `BF022`, `BF028`, `BF034`, `BF036`:
- `BF009`: the lake is an octagonal pit exactly under the plan-map lake. The high ground
  (top right) matches the contour line.
- `BF001`: the river (top) is the lowest part, the terrain rises in steps that follow the
  plan-map contour lines, and the rocky ridge (bottom) is the highest. `CliffsEdge`/`RiverEdge`
  boundaries from `.BTS` run along the steep slopes.
- `BF005`: the diagonal valley is low, the wooded slopes on both sides are high.
- `BF010`, `BF004_1`, `BF022`: the rocky bands on the plan map are steep cliffs (dense contours);
  rivers lie in the lowest areas.
- `BF034`: river at the top is low, hills left and right match the contours.
- `BF028`: flat battlefield with a single hill in the bottom-right corner, as on the map.
- `BF036` (dungeon): the raised 2-unit band traces the corridor walls exactly, an asymmetric
  shape that would not match with a wrong offset, flip or scale.

Checks that did not work: `OBJECTS z` in `.BTS` (values 0/2/10/39/64/80/115/140/150) is
unrelated to the terrain height under the object. It is probably the object's own height.

## Scripts

`scripts/gd_render.py` (Python 3 stdlib, uses `whscript`, `render_battle`, `render_sprites`):

```
G=".../WARFB/FILE"
python3 scripts/gd_render.py "$G/SCRIPT/BF009.BTS" extracted/terrain_gd/bf009.png 0.25
python3 scripts/gd_render.py "$G/MESH/BF004/GRND.GD" out.png 0.1      # no .BTS: relief only
python3 scripts/gd_render.py --export "$G/SCRIPT/BF009.BTS" extracted/terrain_gd/mesh
python3 scripts/gd_render.py --check "$G"
```

- Render: 3 panels cropped to the battlefield. (1) height tint plus hillshade, with terrain
  and battlefield boundaries from `.BTS`. (2) plan map. (3) plan map shaded by the terrain,
  with red contour lines.
- Export: `<MESH>.obj` in world units, Y up, −Z = up the plan map, triangulated by `diag`;
  and `<MESH>.json` with a vertex height grid `heights[z][x]` in GD units plus `diagonal[z][x]`.
- The class `Terrain` (`height(x, z)`, `triangle`, `vertex_heights`, `diagonals`) can serve
  as a library for placing scenery and units on the terrain (world → GD: divide by 8).

Outputs from the game data (local only, in `.gitignore`): `extracted/terrain_gd/bfXXX.png`
(44 battles), `extracted/terrain_gd/mesh/*.obj|json` (45 meshes).

## Open questions
> **Tracked on GitHub**: these open items are tracked as issue #37 (`topic:sprites-animation`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- **Height scale.** Using ×8 like the horizontal axes makes the largest cliffs about 200–640
  world units tall. That is plausible but unconfirmed. It should be checked against scenery
  sizes or a screenshot from the game (ROADMAP 2.3/2.4).
- **Diagonal choice.** Diagonal 2 appears in both convex and concave non-planar cells
  (968 / 1152), and also in 539 planar cells, so there is no geometric rule. It is probably
  copied from the source `.ASC` mesh.
- **Grid margins.** Why most grids have 4 extra cells and some have 0 or up to 10. Maybe the
  camera area (`CameraEdge`) or the texture size.
- **Texture coordinates.** Not stored in `GRND.GD`. `GRND.PBX` contains file names such as
  `gr1.gif`, `r.gif`, `3.gif`, `s_rocks2.gif`, `null.gif` (visible between the compressed
  bytes; unpacking is ROADMAP 2.1). Hypothesis: the terrain texture is mapped planarly from
  x/z (for example one texture tile per cell or per N cells), perhaps chosen by height/slope.
  To be checked once `.PBX` is unpacked.
- **Meaning of `BF004`.** A mesh without a `.BTS`, nearly the same as `BF004_3` (194 vertices
  differ). Probably a leftover version of it.
- Whether `UPDATE/` overrides `MESH` files: no `UPDATE/MESH` directory exists in this install.

## Proposed changes to ROADMAP.md

- Table "Map of the install": `Battle terrain and 3D assets` → status `✅ GD / 🟡 PBX`.
- 2.2 → ✅ with the note: "planes per triangle, 64×64×2, 1 GD unit = 8 world units,
  GD z = world y; `scripts/gd_render.py`; open: height scale, textures".
- 2.3: add "texture mapping from `GRND.PBX` (GD has no UV/material data)" and
  "sample `Terrain.height()` when placing scenery/units (world / 8)".
- 2.4: "verify the height scale (×8?) against a screenshot from the game".

## Proposed changes to FORMATS.md

Replace the `GRND.GD` bullet under "Battle 3D assets" with the "Format" section above.
