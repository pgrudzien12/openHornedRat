# Map objects: what stops a projectile, blocks sight or pushes a unit (roads do none of these)

Public hand-off for the implementer. It answers a BF003 bug: a Grudgebringer Fireball launched from the road was
stopped on its second tick by a road tile. It refines `spell_effects.md` §2.3 and §4.3, `ranged_combat_handoff.md`
(in-flight scenery hits) and `game_rules.md` "visibility … blocked by scenery". Static research plus a census of the
shipped `.BTS` files.

## 1. Short answers

1. **A road tile never stops a bolt, a missile, sight or movement.** Road pieces (`PlnStrRoad`, `GrvStrRoad`,
   `GrsStrRoad`, `PlnAngRoad`, …) are `placefurniture` scenery pieces. They are drawn, and that is all.
   Placed furniture creates **no** map object, with one exception: building-type furniture (`building_units.md`),
   which becomes a building unit with its own map object.
   - The obstacles projectiles and sight test come only from the battle file's **`[OBJECTS]` section** (the authored
     "Collision Object" circles), from units and buildings, and from spell area objects.
   - So trees, fences, rocks and road pieces are not obstacles in themselves. Where the designers wanted one (around
     a wood or a house), they placed a collision object over it.
   - The engine's list of "shooting objects" adds every furniture piece as a solid circle with a guessed radius.
     That is not the original's model and is the cause of the bug.
2. **A collision object's height is its `z` value** in its `addobject:` block. When `z` is absent, the height is
   **80**. It does not come from a mesh or from the furniture type. Other keys:
   - `radius`: its circle;
   - `x`, `y`: the centre, offset like every battle-file position;
   - `dir`: kept with the object; not used by these tests;
   - `status`: a combination of `os_active` (the object exists), `os_solid` (pushes units apart) and `os_camcollide`
     (camera only).
3. Each consumer reads the object's state differently; §2 has the table. Projectiles and route steering ignore
   `os_solid`, while sight also needs a non-zero height.

## 2. Which objects each consumer tests

Every consumer considers only objects that exist (`os_active`). Camera-only objects (`os_camcollide`) are skipped
by all four consumers below; they exist for the camera.

| Consumer | Collision object counts if | Geometry |
|---|---|---|
| **Projectile in flight** (spell bolts, ordinary missiles, every impact test with radius 0) | not camera-only. `os_solid` is **not** required | distance from the point to the object's centre `< radius` (strict) **and** projectile height `≤ z` |
| **Sight** (spotting, `AttackNearestVisibleEnemy` and other visibility tests) | not camera-only, **and `z ≠ 0`** | the sight line passes within the object's radius (angular half-width test along the line, `game_rules.md`) |
| **Movement push-apart** (collision pass) | **`os_solid`** | footprint overlap → pushed clear (`script_behaviours.md` §2.2) |
| **Route steering** (obstacle scan, `obstacle_steering.md`) | not camera-only (and not a routing or fanatic footprint) | the planned line meets the circle |

- An `os_active` object without `os_solid` still stops projectiles, blocks sight (if `z ≠ 0`) and deflects
  steering. It just does not push units apart.
- A `z = 0` object stops only a projectile at height ≤ 0, i.e. one at ground level, and does not block sight.
- A projectile hitting a collision object deals no damage (`spell_effects.md` §4.3). It stops a stop-on-hit
  projectile, and counts as a hit for the Fireball's thorn burning.

Shipped data (all 54 battle files, 1158 `addobject` entries):

| Property | Values |
|---|---|
| `status` | `os_active\|os_solid` 1087, `os_active` 66, `os_active\|os_camcollide` 5 |
| `z` | 0 (81), 2 (10), 10 (20), 39 (106), 64 (652), 80 (210), 115 (1), 140 (5), 150 (14); absent (59) → 80 |

## 3. Test vectors

A Fireball's height is 1–9 above the ground on flat ground (`spell_effects.md` §3.4). Positions are world units.

| Object under the bolt | Bolt height there | Result |
|---|---|---|
| road piece (`placefurniture:PlnStrRoad`), no collision object | 0 | flies on (not a map object) |
| same | 3 | flies on |
| same | 16 | flies on |
| collision object `os_active\|os_solid`, `z = 39`, radius 52, bolt 20 from its centre | 0 / 3 / 16 | **stops** (≤ 39) |
| same, bolt height 40 | 40 | flies on |
| same, bolt 52 from its centre | any | flies on (`52 < 52` is false) |
| collision object `os_active`, `z = 0`, radius 20, bolt inside | 0 | **stops** (0 ≤ 0) |
| same | 3 / 16 | flies on |
| collision object `os_active\|os_camcollide`, any `z` | any | flies on |
| collision object with no `z` (height 80) | 3 / 16 | **stops** |

Sight, same objects: road piece → never blocks. `z = 39` and `os_active` alone (no `os_solid`) → blocks. `z = 0` →
does not block. Camera-only → does not block.

## 4. Where the engine differs

- It builds one obstacle list from the `[OBJECTS]` entries **plus every placed furniture piece**, each piece a
  solid circle of a guessed radius with no height (the unit height is used instead). In the original only buildings
  among the furniture are obstacles, through their building unit's map object. Road pieces, trees and fences are not.
- The projectile test requires `os_solid`; the original requires only "exists and not camera-only".
- A missing height falls back to the unit height; the original uses **80** for an `addobject` without `z`. The
  furniture case does not arise.

## 5. Corrections to public notes

- `spell_effects.md` §2.3 and §4.3: "solid objects (scenery …)" and "trees, walls" now say **collision objects from
  `[OBJECTS]`** (plus spell area objects), with height `z`, and point here.
- `ranged_combat_handoff.md` (in-flight hits): "an intersected solid scenery object can stop it" means a collision
  object as above. Furniture pieces are not tested.

## 6. Open items

- 🟡 The missile aim-line scatter test (`ranged_combat_handoff.md`: +8 spread when "scenery obstructs the aim line")
  was not re-traced here. Treat its object filter as the sight filter until checked.
- 🟡 Height of **unit** map objects (the "unit object height" 🟡 of `spell_effects.md` §8): a unit's object is
  created at height 16. Whether it is later set per unit type was not checked.
