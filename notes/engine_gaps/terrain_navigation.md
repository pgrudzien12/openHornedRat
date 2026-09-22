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

- **Which terrain types block movement**, specifically whether wooded/forest areas are marked with a
  boundary flag, a scenery collision object, or a `GRND.GD` height/type value — not yet identified as a
  public fact. `notes/terrain_gd.md` documents the height field but not a passability/terrain-type layer;
  this needs a targeted look at whether `GRND.GD` or the `.BTS`/`OBJECTS` scenery placement carries a
  terrain-type or passability byte, and/or a data grep correlating forest scenery meshes with boundary
  records in battles that describe woods (e.g. BF024 "Protect the forest", `FORMATS.md`).
- Exact rule for units reaching the `0x20` "leaving the table" boundary while routing: removed
  immediately, after a delay, or only past both this boundary and `BATTLEEDGE`? Not yet documented as a
  public fact beyond the existence of the flag and event 0x0E.
- Whether player units that flee off-table are gone for the rest of the *battle* only, or whether it
  interacts with the campaign-layer "routed models always return" rule (`notes/campaign.md` §3) — i.e.
  does fleeing off the table protect a model from being counted a casualty in the debrief? Cross-reference
  needed, not yet done.

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
