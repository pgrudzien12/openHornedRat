# Obstacle steering and route planning around footprints

Clean-room behavioural handoff for the implementer: how the original moves an ordinary regiment around scenery,
buildings and other units on the way to a waypoint. It covers every Move-type order (point moves, node moves, moves
to a target unit) and every map, not one case. Guide lines and boundary-crossing routes are in
`movement_boundaries_route_finding.md`. The unit relationship filter is in `bf003_peasant_move_obstruction.md`. A
worked example is `bf003_wolfriders_route.md`. All of this is static research; the original was not run.

Notation: angles in 1/512 of a turn, 0 = +Y, clockwise (128 = +X); `SIN[a]`/`COS[a]` = `trunc(256·sin/cos(2πa/512))`;
"permitted area" = inside every active BattleEdge area, outside every solid area, inside every inverse-solid area.

## 1. The two layers

Obstacle handling has two layers that run at different times:

| layer | when it runs | what it decides |
|---|---|---|
| **Route plan** (two trial detours) | (a) when a move order is issued; (b) each time a waypoint is reached and the next one is taken; (c) while moving, when the current steer point would lie outside the permitted area | **which side** to pass the first obstacle on, or that no detour is possible |
| **Live steering** | every update of a moving regiment | the heading for this update, steering round the obstacles ahead on the **remembered side** |

The plan does **not** run every update, and live steering never cancels an order. An engine that re-plans both
sides every update, or cancels a moving regiment's order whenever both trials fail, does not behave like the
original.

## 2. Positions and sizes used

- **Reference point:** the regiment's **front-rank position**. It is used for the obstacle scan, steer points,
  trials and the distance to the waypoint. The formation's collision centre is used only for physical collision
  and edge correction.
- **Own radius:** the regiment's stored integer collision radius (`bf003_peasant_move_obstruction.md` gives the
  block formula). An obstacle's radius is its own stored footprint radius.
- **Waypoint heading** and **waypoint distance:** from the reference point to the current waypoint.

## 3. The obstacle scan (shared by both layers)

The scan walks the live collision footprints **in collision-object order**, skipping the regiment's own footprint.
It returns the **first** footprint that blocks, not the nearest one. A footprint blocks if all of the following
hold:

1. **Kind.** Footprints of routing regiments and of fanatics still inside their parent are never obstacles. 🟡 One
   further rare marker kind is also skipped.
2. **Not the destination.** A footprint whose circle contains the waypoint (distance from its centre to the
   waypoint ≤ its radius) is ignored, **unless** it is an ordinary troop regiment.
3. **Look-ahead.** Let `d` be the distance from the reference point to the footprint centre. The footprint is
   ignored if `d ≥ 256`. Obstacles further away are handled when the regiment gets closer.
4. **Corridor.** Let `R = obstacle radius + own radius` and `d' = max(d, R)`. The *reach* `L` is:
   - when not already steering: `waypoint distance − trunc(distance from the footprint centre to the waypoint)`;
   - when steering: the current steer distance (§4).

   The footprint is ignored if `L ≤ d' − R`. Roughly, it must lie in the corridor ahead, closer than the
   waypoint.
5. **Cone.** Let `b` be the bearing from the reference point to the footprint centre and
   `h = trunc(asin(R / d') × 256 / π)` its angular half-width (`h = 128` when touching). Let `ref` be the waypoint
   heading when not steering, otherwise the current steer heading. The footprint blocks only if the smaller
   difference between `ref` and `b` is **strictly less than `h`**.
6. **Relationship filter** (only for footprints owned by units or buildings):
   - **Scenery footprints** always block.
   - A **building or furniture** footprint blocks unless it is the regiment's current target.
   - **Other regiments** follow `bf003_peasant_move_obstruction.md`, with the corrections in §6 below. In brief:
     - A RollingStock mover is never blocked by units.
     - A unit at least as far away as the mover's **threat range** (`SetThreatRange`) is ignored.
     - Units in the "leaving the battle" state are ignored.
     - **Enemy** units are ignored during **plan trials** (§5) and when hidden or broken. They block otherwise.
     - **Same-side** units: the current target (or its group) never blocks; the rest follow the speed and heading
       rules.

## 4. The steering response to a blocking footprint

When the scan finds a blocking footprint (bearing `b`, half-width `h`, `d'`, `R`):

1. **Side.** Use the **remembered side** if one is set. Otherwise take the *natural side*: +1 if `(ref − b) mod 512 ≤
   256`, else −1. That means passing on the side the current heading already lies on. Remember it.
2. **Steer heading:** `H = (b + side × ((5 × h) >> 2)) mod 512`. That is 1.25 × the half-width off the obstacle's
   bearing.
3. **Steer distance:** `D = sqrt(d'² + R²)`. The **steer point** is the reference point plus
   `(SIN[H] × D / 512, COS[H] × D / 512)`, i.e. **D/2** along `H`. The stored steer distance is that half length,
   truncated.
4. **Repeat the scan** with `ref = H` and reach = steer distance. If another footprint blocks, steer again on the
   same side and add the absolute heading change to a running total. Stop when nothing blocks.
5. **Full circle.** If the running total exceeds **512**, the regiment gives up steering for this update.
   - Live: it heads straight for the waypoint and leaves the rest to physical collision.
   - Trial: the steer heading becomes facing + 256 (turn back) 🟡.

The **remembered side** is cleared as soon as a scan finds nothing blocking. The next obstacle met afterwards gets
its own natural side.

## 5. The route plan (two trial detours)

The plan runs at the three moments of §1. It first scans from the reference point. If nothing blocks, the plan
succeeds at once with no side remembered. Otherwise it runs **two trials** with the regiment's position and facing
saved and restored afterwards: trial 1 on the **natural side**, trial 2 on the **opposite side**. Each trial
repeats the following until it ends:

1. **Steering response (§4)** from the current trial position, giving a steer point and heading. Enemy units are
   not obstacles during trials.
2. **Region test on the steer point only.** If the steer point is **outside the permitted area**, the trial's
   score is **set to 12,000** and the trial ends.
3. **Advance.** Otherwise:
   - score += `4 × |H − facing| + steer distance`;
   - the trial position becomes the steer point and the trial facing becomes `H`;
   - the waypoint heading and distance are recomputed from there;
   - steering state is cleared.
4. **Next scan.** Scan again from the new position. The trial ends when nothing blocks or the score exceeds
   **5,999**.

**Trial result** = score + waypoint distance from the trial's last position.

**What is *not* tested:**
- the path from a position to its steer point (it may cross the BattleEdge or any boundary);
- the final leg from the last steer point to the waypoint;
- whether the **starting** position is inside the permitted area.

A regiment standing outside the edge can therefore plan a detour whose steer points lie inside.

**Choice.** The lower result wins, and its side becomes the remembered side. On an exact tie the **second** trial
(the side opposite the natural one) wins. The plan **fails** only if **both** results are ≥ 12,000.

**On failure:**

| when | consequence |
|---|---|
| move order issued | the regiment does not start moving (it stays halted; the route's waypoints remain). Scripts waiting for "halted" continue at once |
| waypoint reached and next leg planned | the regiment halts and re-forms |
| live steer point left the permitted area | the regiment **pauses 54 updates**, keeping its order, then continues (and re-plans if needed) |

## 6. Live movement each update

For a moving regiment, every update:

1. Run the scan (§3) from the waypoint heading, steering on the remembered side (§4). The resulting heading is the
   direction of travel.
2. If steering is active and the steer point lies **outside the permitted area**, run the full plan (§5). If the
   plan fails, pause 54 updates.
3. If a **same-side** unit was found **near** while the two units' travel directions differ by at least 45° and the
   mover is not faster, the mover **pauses 54 updates** instead of detouring. "Near" means octagonal distance
   `< 16 × the mover's speed stat` (`s_rlmv`).
4. If the needed turn exceeds **64**, the regiment first turns on the spot for half the turn's value in updates.
5. Within **32** of the waypoint it takes the next waypoint and plans again (§5).
   - If the straight line from the regiment to the **last** waypoint crosses no boundary, the intermediate
     waypoints are dropped first.
   - With no waypoint left, the move ends (halted).

## 7. Engine differences to fix

Compared against the current `whshr/engine.py` route steering (`_steering_target`, `_first_route_obstacle`,
`_score_detour`):

| # | engine now | original | rule |
|---|---|---|---|
| 1 | runs both trials **every update** and returns "no route" (cancelling the order) whenever both fail | trials only at order, waypoint and boundary-forced re-plan; between them live steering on the remembered side; failure while moving = 54-update pause | §1, §5, §6 |
| 2 | scans from the **formation centre** | scans from the **front-rank position** | §2 (also `movement_boundaries_route_finding.md` "A moving regiment has several relevant positions") |
| 3 | an obstacle blocks if the segment passes within `R` (perpendicular distance, `0 < t < 1`) | cone test `|ref − b| < trunc(asin(R/d')·256/π)`, corridor test, look-ahead `d < 256`, destination-footprint skip, first in object order | §3 |
| 4 | trial point = tangent point beside the circle, perpendicular to the target line | steer heading `b ± 1.25h`, steer point at `D/2`, `D = sqrt(d'² + R²)`, rescanned with the steer heading | §4 |
| 5 | a trial **adds** 12,000 when the steer point is forbidden **or the connector crosses a boundary**; adds 12,000 again if the **final leg** crosses one | the score **becomes** 12,000 only when the **steer point** is outside the permitted area; connectors and the final leg are not tested | §5 |
| 6 | meeting the same obstacle twice adds 12,000 | no such rule; the full-circle limit (> 512 total turn) ends steering | §4 |
| 7 | sides are always tried as −1 then +1, and a tie picks +1 | natural side first, opposite second; a tie picks the opposite (second) side; the winner is remembered for live steering | §4, §5 |
| 8 | same-side "near" exemption uses `16 × frontage` and passes the unit over | `16 × s_rlmv`, and the mover **pauses 54 updates** | §6 |
| 9 | no reach limit for unit obstacles | units at or beyond the mover's threat range are ignored; enemies ignored during trials | §3 |

Rows 1, 2 and 5 cause the BF003 Wolfriders' cancelled move (`bf003_wolfriders_route.md`). Rows 1 and 5 alone are
enough to make any regiment that meets an obstacle near the edge, a solid area or a river stop for good, where the
original carries on.

## 8. Test cases

| before | action | expected |
|---|---|---|
| regiment front-rank point at (0,0), own radius 30, waypoint (0,600); scenery circle r 50 at (10,200) | scan | d = 200.2, R = 80, h = trunc(asin(80/200.2) × 256/π) = 33; bearing b = trunc(256 − 256·atan2(10, −200)/π) = 4; diff 4 < 33 → blocks |
| same | steering | natural side: (0 − 4) mod 512 = 508 > 256 → side −1; H = (4 − 41) mod 512 = 475; D = sqrt(200.2² + 80²) = 215.6; steer point 107.8 along heading 475 |
| same circle at (10,300) with the waypoint at (0,250) | scan | circle contains no waypoint, but reach L = 250 − trunc(dist(circle, wp) 50.99) = 200 ≤ d' − R = 300.2 − 80 = 220.2 → ignored |
| circle at (0,260) | scan | d = 260 ≥ 256 → ignored this update |
| regiment outside the BattleEdge, both trial steer points inside | plan | both trials score normally; the move starts |
| both trial steer points outside the permitted area | plan at order | both 12,000 → regiment stays halted |
| moving regiment whose steer point drifts outside | live update | re-plan; on failure pause 54 updates and keep the order |
| equal trial results | plan | the opposite-of-natural side wins |
