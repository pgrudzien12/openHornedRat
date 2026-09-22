# Gap: pre-battle deployment stage

**Symptom**: the engine currently drops every regiment straight onto its `.BTS` starting position at
battle start, visible immediately. The original hides the player's army and lets the player place it
before the battle begins.

## Known facts

From `notes/game_rules.md` §"Missions and objectives":

- `DeployTroops:` battles (a `.BTS` keyword) hide all player units at start; placement is a UI action, not
  bytecode — this is genuinely a front-end feature, not something a behaviour script drives.
- `NS_END` nodes match the player unit count (BF001 has 3), suggesting the node chain marks placement
  slots or a placement-area outline for the UI.
- Units with holding positions outside the playable field (BF001's crossbowmen at x = 1814) are inferred
  to be placed by the player during deployment (🟡, not yet confirmed under Wine).
- AI armies are never repositioned at battle start; only the player's own army goes through deployment.
- Related open campaign question (`ROADMAP.md` A9, `troop_selection.md` §11): does the list order chosen
  on the marching-order page (before the battle) affect initial deployment order/position in the battle?
  Unresolved without a Wine session.

## Open questions

- Exact deployment UI: is it drag-and-drop within a bounded zone, click-to-place in turn order, or
  something else? Not yet observed (needs a Wine session covering a `DeployTroops:` mission, e.g. BF001).
- Whether `NS_END` nodes are individual slots (one per unit) or corners of a polygonal deployment zone.
- Whether deployment order is constrained by the marching-order list (ROADMAP A9) or free.
- Whether the player can cancel/undo placement before confirming, and whether there's a time limit.

## Implementation notes

- Add a `DeploymentScene` (or a battle-scene sub-state) that runs before `Battle.tick` starts for any
  mission whose `.BTS` sets `DeployTroops:`: player regiments are created but flagged not-yet-placed
  (analogous to `hidden:`), rendered in a staging area or roster panel, and the player assigns each one a
  position inside the deployment zone (bounded by the `NS_END`/`ns_startpos` node chain, per the boundary
  mask semantics already documented in game_rules.md's routes/visibility section) before the battle clock
  starts.
- Until the exact UI is confirmed, a reasonable placeholder: list-and-click placement (select a regiment
  from a roster list, click a point inside the zone), which is functionally close to several other Mindscape
  UIs of the era and is easy to replace once observed.
- Missions without `DeployTroops:` keep the current "spawn at `.BTS` position" behaviour unchanged.
