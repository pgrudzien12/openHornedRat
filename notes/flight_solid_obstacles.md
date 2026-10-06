# Flight and pursuit around solid areas and other boundaries

Clean-room behavioural handoff for the implementer (epic #10). It covers how a routing (fleeing) regiment and its
pursuer deal with solid and inverse-solid areas (rivers, cliffs), footprints and the BattleEdge. Read with
`game_rules.md` "Flight and catching fleeing units" and "Pursuit", `pursuit_map_edge.md`, `obstacle_steering.md`
and `movement_boundaries_route_finding.md`. Static research; the original was not run.

## 1. Short answer

- A fleeing regiment's direction is **not fixed**. Every *flee period* it re-routes from its **current facing**:
  - it probes a point **256 units ahead**;
  - if that point lies in a solid or inverse-solid area, or the line to it crosses one, it re-aims at the nearest
    allowed point and turns **a further 22.5°**, repeating until the line is clear.

  A fugitive running at a river therefore swings round and **runs along the bank**. It is never re-aimed "away
  from the enemy" again after the rout starts.
- Routing regiments get **no boundary correction at all**: not solid, not inverse-solid, not the BattleEdge. They
  are never pushed back and never pinned. They avoid solid areas only by the re-route.
- Only the **BattleEdge** removes a fugitive. Solid areas never do.
- A **pursuer** handles solid areas only through the ordinary per-update correction, which pushes it out and does
  **not** end the pursuit. A solid line never ends a pursuit. The pursuit ends only by its own rules
  (`pursuit_map_edge.md` §2): target, chase budget, restraint test, BattleEdge probe.

## 2. Flight movement

- **Start.** The rout faces the regiment **directly away from its opponent** (or keeps its facing without one;
  `game_rules.md` "Flight and catching fleeing units").
- **Every update.** It moves along its **current facing** at flee speed (`game_rules.md` "Unit speed": factor 1.5).
- **Flee period.** A per-regiment counter drops by `s_rlmv` each update. When it goes below 0 (every
  `⌊r/2⌋ + 1` updates for collision radius `r` and an unchanged `s_rlmv`; `movement_boundaries_route_finding.md`
  "routed edge rule"):
  1. **If it has not yet departed:**
     - its front-rank point outside every BattleEdge area → **departure** (event 0x0E broadcast, other units drop
       it as a target);
     - otherwise → the **flight re-route** of §3.
  2. **If it has departed:** a point one radius behind the front rank also outside every BattleEdge area →
     **flight complete**. It stops, and it is removed on the first later update when its models have settled
     (`movement_boundaries_route_finding.md`).
  3. The counter is reset to `r × s_rlmv / 2`.
- **Rally.** Rally attempts on the scheduled segments are unaffected (`game_rules.md` "Rally").

## 3. The flight re-route (once per flee period)

Start with `H` = the regiment's **current facing**, and repeat:

1. **Probe** `P` = front-rank point + `(SIN[H], COS[H])`, i.e. **256 units ahead** along `H`. 🟡 The probe is first
   nudged clear of scenery, building and same-side regiment footprints that contain it.
2. **Snap** `P` to the nearest point allowed by the **solid and inverse-solid** areas. The BattleEdge is **not**
   used here. Note whether `P` had to move.
3. **If `P` did not move and the straight line from the regiment to `P` crosses no solid or inverse-solid boundary
   line:** `P` becomes the flee waypoint. The regiment then runs the ordinary **live steering** of
   `obstacle_steering.md` §3–§4 around footprints toward it. A footprint that blocks deflects the heading (enemy
   regiments block a broken mover; same-side units follow the usual filter). If steering deflected it, `H` := the
   steer heading and repeat from step 1; otherwise stop.
4. **Otherwise** (the probe was in a forbidden area or the line crosses a boundary):
   - `B` = the bearing from the regiment to the **snapped** `P`.
   - Find the turn direction from the current facing to `B`: clockwise when `(B − facing) mod 512 ≤ 256` (this
     includes `B` = facing), otherwise anticlockwise.
   - `H := (B + 32) mod 512` if clockwise, `(B − 32) mod 512` if anticlockwise. That is 22.5° beyond the bearing,
     in the turning direction.
   - The facing becomes `H`, and repeat from step 1.
5. **Stop** when an iteration leaves `H` unchanged, or the total of the heading changes reaches 512 (a full turn).

The regiment's **facing is set to the final `H` at once** (no gradual turn), and it travels along it until the
next flee period. Head-on into a wall (`B` = facing) it turns **clockwise** (increasing facing).

**When no way is found** (the full-turn limit is reached, e.g. in a pocket), the regiment keeps the last heading.
Routing regiments are never corrected, so it can then walk into the forbidden area. 🟡 What a later re-route does
from inside a forbidden area was not traced. It doesn't happen on shipped maps' open river banks.

## 4. Boundaries and fleeing regiments

| boundary | flight re-route | per-update correction | removes the fugitive |
|---|---|---|---|
| **solid area** (e.g. BF003 `RiverEdge`) | avoided: probe snapped, +22.5° turns | none for routing units | never |
| **inverse-solid area** | avoided the same way | none | never |
| **BattleEdge** | ignored (runs straight at it) | none | yes: departure, then flight complete, then removal (§2) |
| **guide line** (`bnd_LINE`) | not used | — | — |
| scenery, building, unit footprints | live steering (§3 step 3) | — (physical collision pass still runs) | never |

## 5. The pursuer near solid areas

- **Chase point.** On each segment-boundary tick the pursuer aims at the fugitive's **leading edge**: the
  fugitive's footprint centre plus one fugitive radius along the fugitive's facing. Every update it steers there
  with live footprint steering (`obstacle_steering.md` §3–§4). It uses no guide lines and no two-trial plan, so
  solid areas play no part in its aiming. The fugitive's own footprint is never an obstacle (routing footprints
  are skipped).
- **Correction.** A pursuer is a moving non-routing regiment, so the per-update correction (solid, inverse-solid
  and BattleEdge; centre moved half the excess per axis, truncated) pushes it back out of a solid area. It
  **only pushes**; the pursuit goes on (`pursuit_map_edge.md` §3). Along a river it therefore slides along the bank
  while the fugitive runs along it.
- **Ending.** Only `pursuit_map_edge.md` §2 ends a pursuit. A pursuer stuck at a river bank while the fugitive
  draws away loses chase budget (it gains `previous distance − distance − 4` per segment, so any segment without
  progress costs at least 4) and stops when the budget runs out (not with `AlwaysPursue`). The solid line itself
  never ends the pursuit. The BattleEdge probe tests only BattleEdge areas.

## 6. Differences from the current engine

| engine now | original |
|---|---|
| flee bearing fixed at the rout | re-routed every flee period from the current facing: 256-unit probe, snapped clear of solid/inverse-solid areas, +22.5° turns, then footprint steering (§3) |
| routing units corrected against solid and inverse-solid areas, so they get pinned | routing units get **no** boundary correction of any kind |
| flee steering ignores unit footprints | footprint steering includes units (enemies block a broken mover; same-side by the usual filter) |
| — (pursuer) | unchanged in principle: correction only pushes, solid lines never end a pursuit; aim at the fugitive's leading edge |

The BF003 symptom of a Wolfrider pinned at x ≈ 213, sliding south for 750 ticks, cannot happen in the original. At
its first flee period near the river it turns to run along the bank (§7) and is never pushed.

## 7. Test vectors (BF003 west river)

BF003 `RiverEdge` is a solid area whose allowed side is east of the line (216, 1280)–(216, 720) (then (216, 720) →
(296, 640) → (296, 240)). Fugitive: front-rank point given, collision radius 30, routing, not departed.

| before | event | after |
|---|---|---|
| (260, 1000), facing 384 (−X) | flee period | probe (4, 1000) in the river → snapped (216, 1000); B = 384 = facing → clockwise → H = 416. Probe (24, 1097) in the river → snapped (216, 1097); B = 477, turn 477 − 416 = 61 → clockwise → H = 509. Probe ≈ (251, 1255) allowed, line clear → waypoint; final facing **509** (+Y, along the bank) |
| (240, 1250), facing 509 | flee period | probe ≈ (231, 1505) allowed (east of the diagonal bank (216, 1280)–(0, 1496)), line clear → keeps 509; runs on toward the north BattleEdge (y 1664) |
| (213, 1050) inside the river (as in the engine log) | any update | no correction (routing); only the re-route can turn it, as above |
| fugitive's front point crosses y = 1664 (BattleEdge) | flee period | departure (0x0E); flight complete when the trailing point is also outside; then removed |
| pursuer centre (210, 1100), pursuing, river at x < 216 | update | correction `trunc((210 − 216) / 2) = −3` → centre x 213 (pushed east); pursuit continues |
| same pursuer, fugitive pulling away along the bank, no progress for a segment | segment tick | budget −4 or more; at ≤ 0 (not `AlwaysPursue`) → event 0x10, stop pursuing |
| pursuer, solid line between it and the fugitive | segment tick | no special handling; the edge probe ignores solid areas; pursuit continues |
