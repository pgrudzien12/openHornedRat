# BF003 Wolfriders: entering from outside the edge and routing past the trees

Clean-room behavioural handoff for the implementer. Coordinates and unit data were checked against the locally
installed `BF003.BTS`. It is a worked example of the general rules in `obstacle_steering.md` (obstacle scan,
steering, two-trial route plan) and `movement_boundaries_route_finding.md` (guides, map edge). The original game was
not run for this report; the detour side and the arrival tick are computed from those rules, not observed.

## 1. Short answer

- At the order the Wolfriders stand **33 units outside** the playable edge, and the original does not move them
  in first.
- The straight line to the target **crosses the edge**, and neither guide line can be joined without crossing it,
  so the route is the **direct leg** to the target.
- A wood footprint lies on that leg, so the game tries **one detour on each side** of it.
- A detour trial is rejected only when its **steer point** lies outside the playable area. The path from the
  unit to that point is **not** tested against the edge. The west-side trial's steer points lie inside the field,
  so the detour is accepted and the move starts at once, round the **west side** of the wood.
- The engine fails because its detour check rejects a path that crosses the edge. The boundary correction's
  ~1–2 unit stall is not the cause: the original stalls in the same way.

## 2. BF003 order and geometry

- **Start.** The hidden Wolfriders' front-rank position is **(1113, 1420)**, facing **373/512 of a turn** (roughly
  west). They are 12 models in three ranks. A block's collision centre lies `(ranks − 1) × 6 = 12` units behind the
  front rank, at about **(1125, 1422)**. Its collision radius is `trunc(sqrt((4×6)² + (3×6)²)) = 30`.
- **Edge.** At y = 1420 the BF003 BattleEdge's eastern limit is the vertical line **x = 1080** (from y 1280 to
  1520). Both the front-rank point and the centre are outside it.
- **Script** (BF003 script 1). The unit is hidden, waits for battle start, waits 60 ticks, then `MoveToNode 2`, then
  waits until halted before its target-seeking loop. Its periodic threat behaviour can replace the route on the
  way.
- **Target.** Node operand 2 is the **third node in the node list**, at **(719, 970)**. It is not the node whose
  `id` field is 2, at (623, 702).
- **Obstacles.** The solid collision circle at **(967, 1221)**, radius **67**, lies about **21 units** from the
  straight line (1113, 1420) → (719, 970). That is well inside the combined clearance 67 + 30 = **97**, so the
  direct leg is blocked. The circle at (1074, 1243), radius 59, is nearby but outside its combined clearance of 89
  on that line.
- **Guides.** `Nav1` (1176,960) → (1080,1080) → (880,1144) → (848,1256) → (976,1400) is the authored road around
  the wood. `Nav2` runs along the western river.

## 3. What the original does at the move order (same update as the order)

1. **No prior correction.** A newly loaded regiment starts halted and stationary. The original runs its collision
   and edge-correction pass for a regiment only while it is moving or after something touched or pushed it. The
   Wolfriders have done neither, so at the order the front-rank point is still (1113, 1420).
2. **Destination.** The target point is clamped into the playable area if needed. (719, 970) is already inside,
   so it is unchanged.
3. **Guide check.** The straight segment from the front-rank point to the target crosses the BattleEdge at about
   (1080, 1382), so guide lines are tried. A guide is usable only if the straight connector from the unit to its
   nearest point on the guide, and from the target to its nearest point on the guide, both avoid every boundary
   line.
   - From (1113, 1420), the connector to `Nav1`'s end near (976, 1400) crosses x = 1080, so `Nav1` is rejected.
   - `Nav2`'s connector fails the same way.
   - With no usable guide, the route is **one waypoint: the target itself**. This is not a failure.
4. **Obstacle check on the leg.** Going from the front-rank point to the waypoint, the first blocking footprint in
   collision-object order is the (967, 1221) circle.
5. **Two trial detours** (`obstacle_steering.md` §4–§5), from the front-rank point (1113, 1420):
   - Waypoint heading to (719, 970): **314**. Bearing to the circle: **307**, at distance d = 246.8. Combined
     radius R = 67 + 30 = 97, half-width h = trunc(asin(97/246.8) × 256/π) = **32**. The difference 7 < 32, so the
     circle blocks.
   - The natural side is +1 (314 − 307 = 7 ≤ 256).
   - **Trial 1 (natural side):** heading 307 + trunc(5 × 32 / 4) = **347**, steer distance
     D/2 = sqrt(246.8² + 97²)/2 = 132.6 (stored 132). The rescan with ref 347 and reach 132 finds nothing else:
     the (967, 1221) circle is now 40 off (≥ 32), and the (1074, 1243) circle (radius 59, combined 89, distance
     181.2, bearing 273, half-width 41) is 74 off. Steer point ≈ **(994, 1362)**, inside the field, so the trial
     carries on from there round the west side of the wood.
   - **Trial 2 (opposite side):** the first response gives heading 307 − 40 = 267 (steer distance 132). The rescan
     with ref 267 and reach 132 is blocked by the **(1074, 1243)** circle:
     - it is 6 off its bearing 273, inside its half-width 41;
     - it is within the corridor, since 132 > 181.2 − 89;
     - it is within the look-ahead, at 181 < 256.

     Its response on the same side gives heading 273 − trunc(5 × 41 / 4) = **222** and steer distance
     sqrt(181.2² + 89²)/2 = 101. That steer point, ≈ **(1153, 1328)**, replaces the first one. It is east of the
     edge line x = 1080, so the score is **12,000**.
6. **Choice.** Trial 1 wins, and its side (+1, west of the (967, 1221) circle) is remembered for live steering. The
   move starts on this update. The plan would fail only if both trials scored 12,000.
7. **Afterwards, every update while moving.** Live steering retests obstacles. The regiment's collision and edge
   pass now runs because it is moving: it moves the **collision centre** half the remaining distance toward the
   nearest allowed point, per axis, truncated to whole units. So the centre can sit up to about one unit outside
   the edge. That is normal and harmless, because the regiment is heading west into the field anyway.

## 4. What to change in the engine

The engine log shows the edge correction stopping with the centre about 1.9 units outside (`whshr/engine.py`
around line 1994). The detour check (around line 1487) then rejects both paths around the trees because they cross
the edge, which cancels the move. Fix it like this:

1. **Detour trials** (`obstacle_steering.md` §5 and §7, rows 1 and 5). Score a trial as 12,000 only when its
   **steer point** is outside the permitted movement regions. Do **not** test the segment from the current position
   to the steer point, or the final leg, against the BattleEdge or any other boundary. Plan only at the order, at
   each waypoint and on a boundary-forced re-plan, not every update. A unit outside the edge must be able to accept
   a steer point inside it. Keep the existing rules: `4 × turn + distance`, stop above 5,999, give up only if both
   sides reach 12,000, and an exact tie keeps the second side.
2. **Route reference point.** Plan routes (direct-leg test, guide connectors, obstacle scan, trials) from the
   regiment's **front-rank position**, not from its collision centre. Run the edge correction on the **collision
   centre** only.
3. **No guide is not a failure.** If the direct leg crosses a boundary and no guide is usable, keep the target as
   the single waypoint and continue to the obstacle check. Do not cancel the order.
4. **Edge correction timing and rounding.** Run the correction only in the per-update collision pass of a
   regiment that is moving, being pushed or in contact, not for one that has been stationary since load. Halve the
   remaining offset per axis with truncation toward zero. Stalling about one unit outside is the original's
   behaviour, so do not compensate for it. If the engine keeps correcting stationary units, that's a visible
   difference only, and the fixes above still make the order succeed.

**Acceptance test.** Load BF003 unchanged and let the 60-tick wait run.
- At the `MoveToNode 2` order the Wolfriders may be entirely outside x = 1080.
- The order must keep its destination (719, 970): the route is the target as its single waypoint, with a detour
  around the (967, 1221) circle.
- On the same or the next update the regiment starts turning or moving west into the field.
- Over the next ticks its centre ends at most about one unit outside the edge while it moves away from it.
- Failure looks like "both detours rejected" or a cancelled order.

Optional unit tests:

| before | action | expected |
|---|---|---|
| unit at (1113, 1420) facing 373, three-rank 12-model block; circle (967, 1221) r 67 | plan a route to (719, 970) | no usable guide; one waypoint (719, 970); trial 1 (heading 347, steer point ≈ (994, 1362)) viable; trial 2 (heading 267, then 222 after the rescan meets the (1074, 1243) circle; steer point ≈ (1153, 1328)) scores 12,000; move accepted on the west side |
| same unit, but the only obstacle's first steer points on both sides lie east of x = 1080 | plan the same route | both trials score 12,000; the route attempt gives up |
| centre at x = 1081 (one unit outside), moving | collision pass | correction `trunc(1 / 2) = 0`; the centre stays at 1081 |

## 5. Timing

- One battle tick is a 100 ms timer message. The game runs at most 10 ticks per second and does not catch up when
  frames lag, so 10 ticks is about one second at full speed.
- The 60-tick wait is nominally **6 seconds** after battle start. The exact update of the order can differ by a
  tick or two because of script start, yield and wait ordering.
- The detour is chosen on the order's update. A visible turn near **tick 60** is the regiment swinging from its
  start facing toward the chosen detour point. It is not arrival.
- Arrival is much later. The straight distance from the start to (719, 970) is about 598 units. At the free-move
  rate of about 2.25 units/tick that is roughly **265 ticks (≈ 27 s) after the order** before any detour, turning
  or threat interruption.
