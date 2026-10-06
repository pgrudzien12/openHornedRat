# Terrain navigation and off-table movement status

The public behavioral handoff is
[`movement_boundaries_route_finding.md`](../movement_boundaries_route_finding.md).
`whshr/navigation.py` and `whshr/engine.py` now load movement status from `.BTS`,
use active Nav lines as route guides, correct the collision-footprint centre at
solid/inverse-solid/BattleEdge regions, push against active solid object circles,
and process the two-stage routed exit. The previous claim that these features
were wholly absent is obsolete.

## Current movement fidelity

- A point order retains its requested destination when no usable guide exists;
  ongoing correction can slide or stall the unit at a boundary.
- Local scenery and unit avoidance scores both steering sides and recalculates
  the trial point on every update. Trials can inspect every authored obstacle;
  the previous twelve-obstacle limit is gone. Each update chooses the lower
  trial score; an exact tie chooses the second side tested.
- Routing units steer around solid scenery while continuing toward their flight
  point. BattleEdge permits flight out, while other movement regions still
  correct the footprint centre.
- Solid scenery corrects half the overlap on each update. Frontal scenery and
  forbidden movement boundaries end an active charge and notify its target;
  an approach outside charge range remains an approach. Friendly unit pushes
  translate the anchor and model positions together.

Exact steering trajectories and charge-contact timing still need comparison
with observed game movement. The trials use the public rules for turn and
distance scores, but their tangent geometry remains an engine approximation.

The campaign casualty treatment of a unit that routed off the table is a
separate debrief question; it does not change the battle movement rule.
