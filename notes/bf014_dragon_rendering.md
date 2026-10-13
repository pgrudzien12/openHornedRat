# BF014 dragon: textured mesh poses, transforms and asset failures

Public behavioural hand-off for rendering `MeshDragon`. Companion references:
[pbx_rnc.md](pbx_rnc.md) (container, geometry and texture formats), [animations.md](animations.md)
(the separate DRAGON sprite sheet), [script_animation_sound.md](script_animation_sound.md) (action requests),
[script_shooting.md](script_shooting.md) (breath triggers), [exclude_from_army.md](exclude_from_army.md).

The BF014 dragon is a **single textured neck-and-head mesh, replaced by one of four complete poses**. It has no
sprite-sheet prerequisite, skeletal joints or attached DRAGON sprite head. Its cave is independent scenery.
The resource contents and multi-angle textured reconstructions were checked locally. 🟡 Original-game scene
captures have not been obtained; lighting, filtering and the exact screen appearance remain to be compared.

## 1. Installed resources and formats

BF014's `loadmesh:bf014` selects `FILE/MESH/BF014`. In a complete installation:

| Resource | Contents / role |
|---|---|
| `SCENERY.PBX` | four mesh poses `DRAGON1.xof`–`DRAGON4.xof`, their embedded textures, and `BURROW.xof` for `DragonCave` |
| `GRND.PBX`, `GRND.GD` | battlefield terrain mesh/textures and terrain heights; terrain supplies the dragon's placement height |
| `SPRITES.PBX` | battle sprite resources including `BANDRAG.bop/.fol/.pal`; **no DRAGON sprite sheet** |
| `FILE/BINARY/DRAGON.BOP/.FOL/.PAL`, also in `UPDATE/BINARY` | separate sprite-family `Dragon`; 32 directional images = four phases × eight directions; not the BF014 MeshDragon visual |
| `BANDRAG` | dragon banner/HUD/marker art, separate from the creature |

BF014 explicitly loads `DragonFrame1`–`DragonFrame4`; these resolve to the corresponding DRAGON mesh names.
`MeshDragon` itself has an empty sprite-file name **by design**. Both the troop and leader visual select it;
there is one model in the unit, so this does not draw two dragons.

The PBX wrapper is RNC method 2, followed after decompression by the version-2 container in `pbx_rnc.md`.
The `.xof` names identify custom serialized mesh blobs inside the bundle, not standalone textual DirectX files.
Each dragon pose has **195 vertices, 256 normals and 129 triangular faces**, per-vertex UV coordinates and
per-face texture references. All four share face topology, texture assignments and UVs; vertex positions change.
There is no bone hierarchy or animation file required for these poses.

Texture names below are embedded resource identifiers. Despite `.gif`, their records contain indexed pixels and
palettes in the serialized image format documented in `pbx_rnc.md`; a GIF decoder is inappropriate.

| Texture | Dimensions |
|---|---|
| `drag2.gif`, `drag3.gif`, `dragscal.gif`, `drageye.gif` | 32 × 32 each |
| `dragfin.gif`, `horn.gif`, `nostril.gif` | 16 × 16 each |
| `dragteet.gif` | 8 × 8 |
| `dragtong.gif` | 16 × 32 |

They use their own 256-entry RGB palettes, not the battle sprite palette. UV v=0 addresses the image's top row.
Preserve the texture transparency/material metadata from the bundle; the shared interpretation of black-key
transparency remains qualified in `pbx_rnc.md`. Do not invent dragon-specific palette or alpha rules.

The mesh contains red scales, yellow underside/eyes, horns, teeth, tongue and the neck fin. These are surfaces
of the selected mesh, not separately attached sprite layers. Multi-angle reconstruction shows a real profile and
back of the neck: camera yaw must change the projection, not select an eight-direction image.

## 2. Placement, scale and orientation

BF014 authors the unit at **(1120, 600)**, facing **384** on the 512-step heading circle, with no `hidden:` line.
`DragonCave` is separately placed at **(1120, 640)**, direction **0**. Moving/turning the unit does not move/turn the
cave. No pose or head attachment is positioned at the cave's origin.

Mesh coordinates use **Y up**, X and Z as the ground plane. The battle conversion is **8 script units per mesh
unit**. The dragon keeps its authored mesh dimensions, with no extra size multiplier or camera-facing billboard
transform. Its origin follows the unit/model position and its vertical translation adds terrain height and the
model's height above ground. Do not recenter the mesh on its bounding box: the authored origin is its pivot.

As a size check, pose 1's local extents are approximately X −2.216..2.091, Y 1.087..11.214,
Z −5.285..5.927 mesh units. Thus its vertical span is about **81 script units**, and the lowest geometry is about
8.7 script units above the translated origin. These bounds describe the asset, not a collision box.
The head looks along local **+Z** in pose 1. Ordinary yaw rotates the entire neck/head around local Y; no extra
pitch or bank is authored for the BF014 model.

**Heading fidelity:** the original mesh yaw uses a coarser heading conversion than the unit's 512-step value:
for nonnegative headings, the visual yaw step is the heading divided by 8, rounded down; each visual step is
360/63 degrees. Consequently heading 384 displays approximately **274.286°** of mesh yaw, although its gameplay
heading is the nominal 270°. The positive yaw takes local +Z toward +X. This small mismatch belongs to the
original mesh display and must not change movement or breath aiming.

The figure's displayed heading can approach a newly requested heading by at most **32 heading units per model
update** (shortest turn) during battle. Normal turning holds the neutral mesh; it does not animate the neck by cycling the four poses. Camera rotation changes
projection only. 🟡 Compare the coarse yaw and action-freeze transition against an original scene capture.

## 3. Animation state and timing

These are **simulation/model-update ticks**, nominally 100 ms per running battle tick, not renderer frames.
Animation advances with model updates rather than once per camera redraw. Re-requesting the current action does
not restart it. Pausing running battle simulation stops its advancement. Deployment has its own model updates;
do not infer an elapsed battle tick from every deployment image.

| Model action | Mesh behaviour |
|---|---|
| stand (1), idle (2), walk (3), weapon ready (5), dead (6) | pose 1 held; no autonomous idle sway |
| fight (4) | discrete pose cycle below, randomized entry |
| shoot/breathe (7) | select a directional open-mouth pose, hold it for a short one-shot, then pose 1 |

Fight's complete repeating pose sequence, with each listed pose lasting **two updates**, is:
**1, 2, 1, 3, 1, 4, 1, 2, 1, 4, 1, 3** (24 updates per full cycle).
On entry the starting point is randomly selected among the first 16 individual update positions. It then runs
through the remainder and repeats the complete cycle. There is **no mesh interpolation** between poses.
BF014 script 7 requests fight while the dragon is in melee between its timed breath checks.

Breathing chooses pose **3** for aim sector 0, pose **2** for sector 1, and pose **4** for sector 2:

- pose 2: head forward, lower than pose 1, mouth open;
- pose 3: head toward local negative X, mouth open;
- pose 4: head toward local positive X, mouth open.

The breath weapon derives these sectors from the aim bearing relative to unit facing across its front half-plane.
The outer sectors aim the flame origin approximately 45° to either side; the middle sector aims forward.
This changes the **whole selected mesh pose**, rather than rotating an attached head or the unit toward each shot.
Each breath enters at a random offset among four starting positions of a ten-update repeated attack pose, so it
holds that pose for **7–10 updates**, then displays pose 1. The attack freezes action changes and
drops competing action requests while the pose is frozen (`script_animation_sound.md` §0.1).
🟡 The extreme edge of the front firing arc and a new breath during an already-playing breath need scene checks;
do not assume every repeated breath restarts the visible one-shot.

Flames are **separate Fireball effects** launched by the special weapon, not textures attached to the dragon.
Their origins are offset **72 script units** from the unit along the chosen forward/side direction. The launcher
creates them when the weapon fires; it does not wait for a later mesh frame or mouth attachment event.
This action does not itself impose a new unit heading or a special yaw lock: the ordinary figure-heading rules
still apply. Scripted `FireAtNode` supplies an aim point without needing a current target; ordinary no-target queries and
failed firing checks do not themselves start a new animation. The node-breath loop and special shooter activation
are covered by `script_shooting.md`, rather than a renderer-owned animation timer.

## 4. Hidden, off-field and removed states

- **Excluded from army:** still active, rendered and animated normally. BF014 excludes the dragon before battle
  start; that is not a visual hide (`exclude_from_army.md`).
- **Hidden enemy:** its unit/model display is suppressed, including the mesh. No head sprite remains behind.
  This does not suppress the independent cave scenery. On becoming visible it draws the current pose/state;
  visibility alone does not reset the animation.
- **Display-suppressed state** (`SetUnitFlags 0x10000000`, named “no display/contact” in
  `bf015_gate_npc_column.md`): also suppresses the model mesh, independently of hidden state.
- **Outside the camera's ground visibility rectangle:** the unit's front-rank reference position fails the
  ordinary display test. The mesh is withdrawn, even if its long head could otherwise extend into view. Edges of
  that rectangle are inclusive. Normal 3D clipping/occlusion still applies to geometry admitted for display.
- **Off-map:** BF014 has no authored off-map dragon episode. Off-map is not a replacement pose. The ordinary
  display test above uses the camera rectangle; do not invent a dragon-specific field-edge hide rule.
  🟡 Original scene comparison is still needed for geometry at map/camera edges.
- **Actually removed:** normal model/visual cleanup removes the mesh. Exclusion alone never does so.

A hidden or camera-culled active unit continues its normal model updates, so attack/fight timing can progress
while it is invisible. Renderer visibility must not become a simulation or breath-combat gate.

## 5. Missing assets: distinguish optional sprite files from required mesh data

This is a mesh visual, so “sprite sheet missing” is not sufficient grounds to skip it.

| Missing item / failure | Established behaviour and limits |
|---|---|
| MeshDragon sprite filename | normally empty; mesh drawing is selected explicitly, not a sprite-load failure |
| standalone `DRAGON.BOP/.FOL/.PAL` | unused by BF014 MeshDragon; no fallback to them and no participation in its head/neck rendering |
| standalone `DRAGON1.xof` or the nine `.gif` files | not required as loose files: the complete bundle supplies the meshes and image records |
| a selected dragon mesh name absent from `SCENERY.PBX` | mesh load fails; that pose is marked unavailable. There is **no substitute pose or DRAGON sprite fallback**. The dragon's dynamic mesh display still attempts to use its selected pose; this is an unsafe failure path, not a supported invisible-unit fallback. 🟡 Exact original user-visible termination/error and first failing frame have not been reproduced |
| entire `SCENERY.PBX` unavailable | the bundle load fails and no dragon pose is provided; no DRAGON sprite substitution. The later dynamic pose path is likewise unsafe. 🟡 Exact battle-load/first-display failure presentation needs a damaged-installation runtime check |
| texture image cannot be created, or face texture cannot be assigned | loader reports a texture error and can continue processing mesh geometry; it does not select a sprite substitute. 🟡 Exact appearance of affected faces, and whether a particular malformed bundle fails earlier, remain unverified |
| cave mesh unavailable | independent scenery load fails; no automatic conversion of cave geometry into a dragon part or sprite |

A missing texture's **name on disk** differs from an absent embedded image or an invalid face reference.
Deleting a hypothetical loose `.gif` does not remove the image stored in PBX. Truncating/editing PBX is corruption,
not a meaningful test of a normal file-name lookup, and has no established graceful recovery contract.

For the engine, supporting a diagnostic or skipping a missing mesh would be a deliberate defensive policy.
Do not describe a placeholder sprite, pose-1 substitution or magenta texture as original behaviour.

## 6. Requested test vectors

| Before | Action | Expected result / evidence |
|---|---|---|
| visible idle BF014 dragon | render from front, side, back and rotated camera | one complete textured neck/head mesh, pose 1; real depth/profile; cave remains at its independent placement; no DRAGON sprite layer |
| idle at (1120,600), heading 384 | render | natural mesh scale, terrain-relative origin; nominal west-facing unit with approximately 274.286° visual mesh yaw |
| idle dragon | turn unit | same pose 1, whole mesh yaw follows displayed figure heading; ordinary heading smoothing and coarse mesh yaw; no eight-direction sprite selection |
| idle dragon, forward breath accepted | fire | pose 2 for 7–10 model updates, then pose 1; separate flames start at weapon firing, no mesh-frame spawn gate |
| idle dragon, side breath accepted | fire in sector 0 / 2 | pose 3 / 4 respectively; authored head bend replaces whole mesh; separate flame origins displaced to corresponding side |
| dragon in fight action | 24 model updates | full discrete 12-pose-pair cycle; first entry may start partway through first 16 update positions |
| visible dragon | hide enemy or suppress display | mesh withdrawn; independent cave unchanged; active simulation continues |
| hidden dragon mid-breath | advance updates, reveal | current animation phase, not guaranteed first attack frame |
| active dragon reference outside camera rectangle | render | no dragon mesh; bringing only the head's bound into view is insufficient |
| BF014 dragon active | ExcludeFromArmy | mesh, animation and breath remain active |
| no DRAGON sprite files but intact BF014 bundles | load/render MeshDragon | mesh has no dependency on that sheet |
| required selected pose absent | render that pose | no supported asset fallback; unsafe original path, exact on-screen failure 🟡 |
| texture creation/assignment fails | load/render | error path, no sprite substitution; exact affected-face appearance 🟡 |

## 7. Consequence for the stated engine model

Drawing must support a mesh resource independently of `sprite_resource` and sheet availability. Resolve the four
poses and embedded materials from the user's installation; preserve the authored pivot, terrain placement and
model heading. Model animation state selects discrete meshes and breath direction; camera direction does not.
Keep simulation ticking when the model is culled. The DRAGON four-phase sprite family is a distinct visual asset,
not an attachment or required substitute for MeshDragon. No engine code or original assets accompany this report.
