# Gap: terrain navigation & unit removal

**Symptom**: routed units currently wander anywhere on the map, including terrain (woods) the original
likely blocks, and never leave the battlefield or get removed — a routed regiment just keeps existing,
visible, forever.

## Known facts

From `notes/game_rules.md` §"Routes, collisions and visibility":

- Movement obstruction is polygon-membership only (`Nav*`, `SOLID`, `INVSOLID`, `BATTLEEDGE` boundary
  records), never a navigation graph — the original itself can get units stuck against concave obstacles.
  An engine is explicitly free to use real pathfinding without a visible behaviour change on the shipped
  maps.
- Boundary flag `0x20` = "leaving the table" is a distinct mask from the general solid/inverse-solid
  obstacle flags — i.e. the original does have a specific concept of a unit leaving the battlefield through
  a boundary region, separate from being blocked by scenery.
- Event 0x0E (`FleeingUnitUpdate`, broadcast) fires when "a unit left the battlefield", and other units
  drop it as a target in response — so leaving the field is a real, modelled event with consequences for
  other units' targeting, not just an animation.
- `whshr/formation.py` and `whshr/engine.py` already implement movement and collision for the simplified
  rules (per `notes/game_rules.md`'s "Real time and movement" section); what's missing is (a) terrain-type
  blocking and (b) the leave-the-table removal path.

## Open questions

- ✅ **Which terrain types block movement:** **RESOLVED.** `notes/terrain_passability.md` findings:
  - Forests are **NOT impassable** (BF024 has 187 tree scenery but zero movement boundaries)
  - Impassable terrain (rivers, cliffs, walls, lakes) uses explicit **terrain-named boundaries** when needed
  - `Nav*` boundaries are secondary hand-placed obstacles with unclear purpose
  - GRND.GD contains only height data, no passability layer
  - Movement blocking is boundary-membership only (no terrain-type discrimination)

- ✅ **Exact leave-the-table rule:** **RESOLVED.** Routed units are removed immediately when they cross the `0x20`
  ("leaving the table") boundary flag, which corresponds to the **BattleEdge** field rectangle. Event 0x0E is
  broadcast to other units at that moment. Once removed, units are permanently marked `fled = True` and
  excluded from all game logic (no rally, no orders, no movement, no rendering).
  Reference: `notes/terrain_passability.md` Section 2.

- 🟡 **Campaign interaction of off-table routed units:** Whether fleeing off the table protects a model from
  being counted a casualty in the debrief — this interacts with the campaign-layer "routed models always
  return" rule (`notes/campaign.md` §3). Likely that off-table routed units do NOT count as casualties
  (they are `fled = True` permanently), but debrief logic needs to be cross-checked.
  Reference: `notes/terrain_passability.md` Section 2 (Campaign Interaction subsection).

## Implementation notes

- Terrain-type passability is a prerequisite here and should be resolved as its own research item before
  implementation; don't hardcode "forest = impassable" without the data-grep/Wine confirmation above, since
  the fact that woods block movement is currently an assumption carried over from tabletop Warhammer, not a
  confirmed rule of this game.
- Once terrain passability is known, add it to whatever pathfinding/collision the movement code already
  uses (currently the polygon-membership boundaries only) so routing units avoid or bounce off blocked
  terrain like they do scenery today.
- Add a battlefield-edge removal path: when a unit's position crosses the `0x20`/`BATTLEEDGE` boundary
  while routing (or matches whatever the confirmed original rule turns out to be), remove it from
  `Battle.regiments`/active model tracking and broadcast the engine's equivalent of event 0x0E so other
  units drop it as a target, instead of leaving it on the field indefinitely.
