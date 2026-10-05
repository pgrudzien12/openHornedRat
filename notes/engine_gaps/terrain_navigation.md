# Gap: terrain navigation & unit removal

**Symptom**: routed units currently ignore authored movement boundaries and solid
scenery objects, and never leave the battlefield or get removed — a routed
regiment just keeps existing, visible, forever.

## Known facts

From `notes/game_rules.md` §"Routes, collisions and visibility":

- Movement boundaries use the explicit `SOLID`, `INVSOLID`, and `BATTLEEDGE` statuses.
  Shipped `Nav*` entries carry line status without a solid status; they must not be
  assumed to be impassable. They can guide multi-waypoint routes around movement
  boundaries. See `notes/movement_boundaries_route_finding.md`.
- Boundary flag `0x20` = "leaving the table" is a distinct mask from the general solid/inverse-solid
  obstacle flags — i.e. the original does have a specific concept of a unit leaving the battlefield through
  a boundary region, separate from being blocked by scenery.
- Event 0x0E (`FleeingUnitUpdate`, broadcast) fires when "a unit left the battlefield", and other units
  drop it as a target in response — so leaving the field is a real, modelled event with consequences for
  other units' targeting, not just an animation.
- `whshr/formation.py` and `whshr/engine.py` already implement movement and collision for the simplified
  rules (per `notes/game_rules.md`'s "Real time and movement" section); the
  remaining gaps are authored region/object blocking and the leave-the-table path.

## Resolved movement facts and separate open question

- **Which terrain blocks movement:** use boundary status and active solid object
  circles, not terrain names or a `GRND.GD` passability layer. BF024's 187 visible
  pine trees are paired with 85 solid object circles covering 185 tree positions;
  two tree positions have no circle. Shipped Nav lines and solid terrain regions
  coexist in many battles.

- **Leave-the-table timing:** a routing unit may cross BattleEdge. Other units
  drop it as a target after its reference point is detected outside; inactivation
  follows after a point one footprint radius behind it is detected outside. The
  checks are periodic, not immediate on first contact by a model or footprint rim.
  Removal occurs on the first later update with no pending model motion. See
  `notes/movement_boundaries_route_finding.md`.

- 🟡 **Campaign interaction of off-table routed units:** Whether fleeing off the table protects a model from
  being counted a casualty in the debrief — this interacts with the campaign-layer "routed models always
  return" rule (`notes/campaign.md` §3). Likely that off-table routed units do NOT count as casualties
  (they are `fled = True` permanently), but debrief logic needs to be cross-checked.
  This campaign question is separate from the battle movement rule in
  `notes/movement_boundaries_route_finding.md`.

## Implementation notes

- Implement authored movement-region statuses and active solid object circles;
  do not infer blocking from the visual forest texture or each tree sprite.
- Add a battlefield-edge removal path: periodically test the routing unit's
  reference point and a point one footprint radius behind it against active
  BattleEdge areas. The first outside finding makes other units drop it as a
  target; the trailing-point finding completes flight. Remove it on the first
  later battle update with no pending model motion. See the public report for
  the no-BattleEdge case and acceptance scenarios.
