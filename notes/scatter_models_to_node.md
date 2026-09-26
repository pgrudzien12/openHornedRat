# `ScatterModelsToNode` — wander distance and semantics

Public implementation report for GitHub issue #47 (epic #1, area `mission-scripts`).
Describes observable behaviour only. Status: ✅ radius rule, ✅ node selection by `id`,
✅ destinations are around the node centre (not around the unit).

## Answer

The wander distance is **not a constant**. It is the `radius` value of the selected node (the `radius`
keyword of the node's own `[NODES]` entry in the battle's `.BTS`; when a node omits it, the default is 16).
The circle is drawn **around the node's centre**, and patrol nodes are placed on the area the NPCs belong to.
In BF003 the four scatter circles (radius 85–143) lie among the village houses, so peasants stay in the
village. That matches what is seen in play: they do not wander far from it.

The maximum distance from the node centre is `radius − 1`; the average is about `radius / 2`
(BF003: about 42–71 units).

## Behaviour

Operand: a node **id** (the `id` keyword of a `[NODES]` entry), *not* a position in the node list.
Nearly every node has `id 0`; scatter opcodes use small non-zero ids.

1. Considered are the unit's models that are still "in formation" (not scattered since the last
   snap/re-form). Models already wandering are left alone.
2. Nodes are scanned in `[NODES]` order, skipping inactive ones (no `ns_active`), starting just after the
   node used for the previous model (the first model starts at the top of the list), wrapping around at the
   end. The next active node whose `id` equals the operand is taken.
3. **Each model gets its own destination**: node centre + a random distance `d` uniform over the integers
   `0 … radius−1` (`rand % radius`) at a uniformly random angle (512 angle steps per full circle).
   The distance is uniform, not the area, so points cluster toward the node centre.
4. When several active nodes share the id (BF003: id 4 is on two nodes), successive models alternate
   between them (model 0 → first node, model 1 → second, model 2 → first, …), so the unit ends up split
   across all of them.
5. The model leaves formation and walks to its destination individually; **the regiment position and its
   formation slots do not change**. Patrol scripts loop `SetWait ~20 / Wait / ScatterModelsToNode` and
   call `SnapModelsToFormation` in between, so each pass re-scatters the models afresh.
6. If no active node has the operand id, the opcode stops distributing and the script continues.

## Data (all `.BTS` files)

In every one of the 15 battles whose scripts use the opcode, every scatter operand matches an existing,
active node `id`. This consistency is evidence that the operand is an id. Radii of scatter nodes, by
battle:

| battle | radii of scatter nodes |
|---|---|
| BF003 | id 2: 133; id 3: 143; id 4: 85, 95 |
| BF004_1 / BF004_2 | 53–133 |
| BF012, BF025 | large (106–119) and tiny (6–9) sets |
| BF016, BF028, BF035, BF037 | 59–153 |
| BF029 | 38–45 |
| BF008, BF015, BF019, BF033, BF036 | 4–11 (models stay practically on the spot) |

BF003 in detail: the circles span the village houses (roughly x 460–880, y 360–760):

| list index | id | x, y | radius |
|---|---|---|---|
| 5 | 2 | 623, 702 | 133 |
| 6 | 4 | 665, 514 | 85 |
| 7 | 4 | 786, 616 | 95 |
| 8 | 3 | 702, 416 | 143 |

Across all battles the most common node radius is 16 (the default). A radius of 0 exists on a few nodes;
treat it as "exactly the node centre" (never divide by zero).

## Consequences for the engine (`whshr/interpreter.py`)

- Use the node's `radius`; drop `SCATTER_RADIUS`.
- **Resolve the operand by node id** with the cycling rule above. `Battle.nodes` is keyed by list index, so
  for BF003 `ScatterModelsToNode 2` currently picks list index 2 (`id 0`, x 719, y 970, radius 21). That
  point is outside the village, south of it, where the peasants have no reason to be. This is a functional
  bug, not only cosmetic. Whether other node opcodes (`MoveToNode`, `FaceNode`, …) take ids or indexes
  should be checked separately before changing them.
- Per-model destinations are the faithful model. A regiment-level approximation should at least aim at a
  point inside the correct node's circle (uniform distance, uniform angle), not a ±square jitter.

## Test cases

1. One active node, id 2, radius 133: every destination is within 133 of the centre; the distances are
   uniform in `[0, 133)`.
2. Two active nodes with id 4: an 8-model unit's destinations alternate node A, node B, A, B, …
3. Operand id with no active node: no destinations, the script continues.
4. A node with `id 0` at list index 2 must not be chosen for operand 2 when a node with `id 2` exists.
5. Radius 0: destination equals the node centre.
6. A node without a `radius` keyword behaves as radius 16.

## Open points

- The model's walking speed and animation during the scatter: ordinary individual movement is assumed.
- **When a model counts as "in formation" again.** Every mission script that scatters calls
  `SnapModelsToFormation` exactly once, right after its *first* `ScatterModelsToNode`, before the patrol
  loop; the loop itself (`PushPC / ScatterModelsToNode / SetWait ~20 / Wait / Loop`) never snaps. Point 5
  above ("snap in between") therefore does not match the scripts, and under a strict "scattered until
  snapped" reading the loop would only ever scatter once. The engine (issue #162) provisionally treats a
  model that has reached its destination as available for the next scatter, which gives the continuous
  wandering seen in play. What `SnapModelsToFormation` does with the models (walk back vs. instant
  placement, and whether it applies to the destinations just chosen) is unconfirmed; the engine clears
  the destinations so the models walk back to their slots.
- **Other node opcodes take list positions, not ids** (data check across all mission scripts and
  `.BTS` files, issue #162): of 180 `MoveToNode`, 8 `FaceNode` and 99 `PlaceAtNode` operands, all but one
  are valid list positions and only two (both BF003 `MoveToNode 2`) also equal an active node's `id`,
  so these keep list-position lookup. `TeleportToNode` has 26 of 85 operands beyond the node list
  (meaning unknown).
