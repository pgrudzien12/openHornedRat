# Movement boundaries, map edges, and route finding

Public behavioural research handoff, 2026-10-05. World coordinates use the `.BTS`
convention: X increases right and Y increases up. This report records shipped game-data
facts and movement outcomes suitable for independent tests. **No new original-game play
session was completed for this report.** The custom scenarios give expected outcomes
derived from the movement rules; they are acceptance tests, not claimed screen
measurements. Exact visible trajectories involving multiple moving units remain
dependent on update order and their positions.

## Shipped boundary roles

All **409** boundary entries in the **54** local shipped `.BTS` files have a
`set:status` line. If a custom entry omits that line, the boundary remains active
and its `AddLine` geometry is retained, but it has no movement, deployment,
sight, view, or camera role. The name supplies no default role. Status, not the
descriptive name, identifies the boundary's role: `RiverEdge` is normally a solid
area, but one shipped entry is a view line. `Nav1` through `Nav8` carry
`bnd_ACTIVE|bnd_LINE` alone; they do **not** carry
`bnd_SOLID` or `bnd_INVSOLID` in the shipped files. At least 34 files contain both a
`Nav*` line and a solid or inverse-solid terrain area (BF001 is one example).

| Status on an active entry | Shipped names / use | Unit movement outcome |
|---|---|---|
| `bnd_BATTLEEDGE` | `BattleEdge`, one `Battlefield edge` | Playable-area boundary; ordinary movement stays on its inside, while flight can leave the table. |
| `bnd_SOLID` | Cliffs, rivers, walls, lake, some hedges; sometimes also `bnd_LINE` | Region movement constraint. The allowed side is the geometric interior; a unit on the other side is pushed toward the line. |
| `bnd_INVSOLID` | `Hedge`, `MiddleHedge`, `TopHedge`, `SteepEdge`, `RockyRidge`, `BottomEdge` | Inverted region constraint: the interior is forbidden and movement is pushed outward. |
| `bnd_LINE` alone | `Nav1`…`Nav8` | Route guide when a direct point route encounters a movement boundary. It can supply intermediate waypoints but is not a solid collision wall. |
| `bnd_DEPLOYMENT` | `DeploymentArea`, `Deployment`, `Merc Deployment` | Constrains pre-battle placement by formation centre; does not by itself constrain battle movement. |
| `bnd_SIGHT` | `SightEdge` | Blocks spotting across its lines; does not itself block movement. |
| `bnd_VIEWEDGE` | `ViewEdge`, one `RiverEdge` | View control; does not itself block movement. |
| `bnd_CAMEDGE` | `CameraEdge` / `Cameraedge` | Camera control; does not itself block movement. |

Most of these entries also carry `bnd_AREA`; some terrain boundaries carry both
`bnd_AREA` and `bnd_LINE`. Those tags describe the geometry, not a replacement for
`bnd_SOLID`, `bnd_INVSOLID`, or `bnd_BATTLEEDGE`. A boundary without `bnd_ACTIVE` has
no movement effect. An entry with no `set:status` is active but has none of the
special roles in the table. Combined or contradictory custom statuses need a play
check. The shipped `BattleEdge` has `bnd_BATTLEEDGE`, **not** `bnd_INVSOLID`.

The data does not contain a terrain-type passability layer in `GRND.GD`. A visible river,
cliff, forest, or building does not by its appearance acquire a boundary role. Solid
scenery objects have their own collision footprints. BF024 has no terrain-named
solid boundary. It places 187 pine trees and 85 active solid collision objects;
each object circle covers at least one tree position, and 185 tree positions
fall within those circles. Two tree positions do not. Thus that forest blocks
units through the authored object circles, not a general forest terrain rule
or an automatic collision circle for every visible tree.

## Which side and which position

For a **closed polygon** with an ordinary solid status, the boundary contains the
permitted region. An inverse-solid polygon excludes its interior. A BattleEdge polygon
contains the battlefield. This is a containment rule, not a left/right rule based on
the order of the segments. Segment direction reversal leaves the result unchanged.
The edge convention is **half-open**. For a square with corners (100,100) and
(300,300), a test point at (100,200) or (200,300) counts as inside; (300,200)
or (200,100) counts as outside. Of the corners, (100,300) counts as inside;
the other three count as outside. Inverse-solid status reverses those results.
These results come from rightward crossing parity with a small adjustment when
a point shares a segment endpoint's Y coordinate; do not treat every boundary
point as uniformly inside or uniformly outside.

An **open polyline is not a two-sided wall merely because it is called `Nav*`**. With
`bnd_LINE` alone it has no solid side, though it can guide a route. If an open
polyline is explicitly tagged
solid or inverse-solid, it still uses region containment: a point is inside when
a ray from it to the right crosses an odd number of its segments. There is **no
implicit closing segment between the endpoints**. Solid status permits that odd-
crossing region; inverse-solid status forbids it. Reversing segment order does
not exchange the sides. Because an open line does not enclose a finite region,
its effective side can change beyond an endpoint. The shipped terrain areas
normally close their perimeter, often beyond the visible field, to make the
intended side unambiguous. Exact equality at a segment or endpoint remains an
edge case governed by the same half-open convention.

A moving regiment has several relevant positions. A point move's destination and
straight-line route checks use the regiment's **front-rank reference point**. The
ongoing boundary correction uses the **centre of its collision footprint**. For a
multi-rank block these positions differ, so the front rank, footprint rim, and
individual models may visually overlap or cross a boundary before the centre is
corrected. Boundary correction does not test every soldier. Deployment instead tests
the **formation centre**; a later collision push can place that centre briefly outside
the deployment region because no final placement clamp follows that push. Ordinary
overlap with a unit or scenery object uses the two collision footprints. Turning
can move the formation centre relative to its reference point and trigger a later
boundary correction. Collision pushes can put the centre on the forbidden side;
a subsequent correction moves it back toward the line. On a correction update,
the regiment centre moves **half the distance toward the nearest point on the
boundary, with each coordinate truncated to a whole world unit**. All its models
move by the same correction. For example, a centre at (330,200) facing a vertical
boundary at x=300 moves to x=315, then 308, 304, 302, and 301 on successive
otherwise unopposed correction updates. At one unit of separation, truncation
leaves it at 301 until another motion changes the position.

Boundary correction precedes the nearby-object and unit collision pushes in the
same collision pass. There is no second boundary clamp after those pushes. A push
may therefore place the centre on the forbidden side until a later update; pairs
and regiments processed later in the update can alter the result again. Movement
and collision are discrete rather than swept along the whole step. A fast step
may pass entirely across a narrow excluded strip if its final centre lands on an
allowed side, though ordinary route planning can separately reject a direct
order across that strip. This is an endpoint effect, not a permission to remain
on a forbidden side.

If a unit starts on the forbidden side, it is **not necessarily teleported to a fully
legal position**. Boundary correction moves it toward the nearest segment over updates;
the nearby geometry, turning, and other collisions can prevent a clean separation.
Custom outside starts should be tested separately from a normal move toward a boundary.

## Map edge and route outcomes

`[FIELD] set:x/y` gives map dimensions. It is not itself the unit collision wall.
BF001 declares a 1600 by 1760 field, while its `BattleEdge` is the rectangle from
(16,16) to (1584,1744). The 16-unit inset is data, not a universal rule. Authored
units can start outside the field or BattleEdge pending deployment or a mission event;
their starting coordinates must not be silently clamped. The two shipped files with no
BattleEdge entry are DB015 and PLOT1. Without such an entry, the `[FIELD]`
rectangle does not replace it: ordinary units have no battlefield-edge
constraint from that rectangle. Other solid or inverse-solid boundaries still
apply; DB015 has an inverse-solid region, while PLOT1 has no boundaries. For a
custom battle with no BattleEdge, a routing unit is judged outside at its first
periodic edge check regardless of its coordinates; its trailing-point check
also succeeds then, followed by the normal model-settling removal stage. A
pursuing unit's next edge probe likewise finds no playable area and ends its
pursuit. This is a missing-boundary compatibility case, not an alternative
field-size rule.

| Situation | Expected visible outcome | Qualification |
|---|---|---|
| Ordinary move aimed straight through a closed solid or inverse-solid boundary | A usable guide line can provide a detour. Otherwise the destination is limited to the boundary or a nearby allowed point; the unit can slide, stop short, or become stuck. | The point order and ongoing footprint correction can give different visual clearance. |
| Ordinary move near an endpoint / convex corner | A route can pass around the end when there is room, then head toward the target again. | Authored guide lines can change the chosen path. |
| Ordinary move into a deep concave pocket | A direct route crossing the boundary does not cause an automatic search around its corners; without a usable guide route, boundary correction can hold the unit at the pocket wall. | A Nav line whose ends can be reached without another boundary crossing can supply waypoints around the pocket. |
| Solid scenery footprint or another unit on the line to the goal | Tests two steering sides around the first blocking footprint, uses the lower scored side, and retests while moving. If both sides score at least 12,000, the current route attempt gives up. | A moving unit can alter the result; enemy contact follows combat rules. |
| Ordinary unit at BattleEdge | A destination outside is clipped and the footprint is pressed back toward the playable area. It remains active. | Individual models may protrude. |
| Charging unit at BattleEdge | Boundary correction ends the charge and moves the centre halfway toward the nearest edge point on that update; the unit stays active. | The final centre depends on its position and any later collision pushes. |
| Routing unit at BattleEdge | Flight may pass the edge. Once its reference point is checked outside, other units drop it as a target. When a point one collision-footprint radius behind it is also outside, flight completes. It disappears on the first later update when its models have no pending motion. | The two edge findings may happen at the same periodic check or at different checks; disappearance is at least one update later. |

An ordinary point order first checks the straight line to the destination. If it
meets a solid, inverse-solid, or BattleEdge boundary, the game can use active
`bnd_LINE` guide polylines to build a multi-waypoint route around it. It compares
candidate routes by travel distance; this is not a guarantee of a globally shortest
path. As waypoints are reached or a moving target changes position, the route can
be shortened or refreshed. Separately, scenery and unit footprint obstacles can
cause an initial left-versus-right avoidance choice; the moving unit retests those
local obstacles. Boundary contacts may still slide or stall if the authored
guides do not provide a usable passage. A collision push
can undo some of a planned step, especially near a boundary. A frontal collision while
charging ends the charge; friendly regiments push apart, while enemy contact can start
combat. A failed detour is a stopped route, not proof the destination is unreachable.

**Guide selection.** If the direct point route crosses a movement boundary, each
active `bnd_LINE` polyline is considered in authored order. The route attaches to
the nearest point on that guide from the start and the nearest point from the
destination. The straight connection from each end to its attachment must avoid
movement boundaries. The candidate follows the intervening guide vertices in
their connecting order, with the attachment points and destination at its ends.
The game chooses the candidate with the shortest sum of straight-leg distances.
An exact length tie keeps the first candidate in the `.BTS` boundary order.
It does not combine vertices from different guides to find a global shortest
route. If the direct leg is clear, it is used without a guide. This guide rule
comes from the game's movement behavior; `.BTS` supplies the lines and their
order, not a per-map route-selection script.

**Scenery and unit avoidance.** The first blocking live footprint found in
collision-object order along the current leg prompts two trial detours, one
on each steering side. This need not be the nearest blocker. Each trial
adds four times its turning angle (in the game's 512-units-per-turn scale) plus
the distance advanced; its final straight distance to the waypoint also counts.
A trial step outside the permitted movement regions adds 12,000. A side's trial
stops after it clears the detected obstructions or its accumulated trial cost
exceeds 5,999. The shorter trial score wins; an exact tie keeps the *second*
side tested. Which screen side that is depends on the initially detected
obstruction and facing. Only when **both final scores are at least 12,000** does
the route attempt give up. Passing the 5,999 trial cutoff alone does not mean
the order is rejected: the shorter, still affordable side can be tried. Live
steering tests obstacles again as the unit moves, so a moving regiment can
change the path or cause another route attempt.

The **routed edge rule is two-stage**. When a periodic flight check finds the
regiment's reference point outside every active BattleEdge area, it broadcasts
departure: other units drop it as a target. On that same check, or a later
periodic check, a point one collision-footprint radius behind the reference
point, opposite the flight heading, is tested. If it too is outside, flight is
complete. With an unchanged movement rating and collision radius *r*, periodic
checks repeat after ⌊*r*/2⌋ + 1 battle updates; they do not run at the instant
the first model or footprint rim touches the edge. The unit is
**not removed on the update that completes flight**. It disappears on the first
later battle update when its models have no pending motion; if they are already
settled, that is the very next update. Until then it remains present but no
longer moves or seeks a rally. Once removed it cannot receive orders, move, or
rally in that battle. A pursuing unit stops at the table edge rather than
following it off the map. Thus there is no universal fixed number of rendered
frames between crossing the edge and removal; model motion and the periodic
checks determine it.

## Small reproducible scenarios

These are **custom-data acceptance cases**, not claims that the named coordinates
occur in a shipped mission. Use a small regiment, remove unrelated scenery and units,
and record both the front-rank reference point and formation centre each update.
Keep its target at least 100 units beyond the boundary so normal arrival tolerance
does not mask the result. Compare a stationary unit before and after a turn as well as
a moving one. Expected coordinates below identify sides or limiting lines, not exact
per-tick stopping coordinates.

1. **Closed ordinary region.** Make a solid square (100,100)–(300,300), start at
   (200,200), aim at (400,200). The centre remains on, or is corrected toward, the
   square's interior side of x=300. Reverse the segment order: the allowed side should
   be unchanged. Start instead at (330,200): expect correction toward x=300 rather than
   permission to continue indefinitely at x>300. Test points at (100,200),
   (200,300), (300,200), and (200,100): the first two count as inside, the
   last two as outside. The exact correction steps for x=330 are given in
   scenario 8.
2. **Closed inverted region.** Give the same square inverse-solid status. Start at
   (80,200) and aim at (200,200): the centre stays outside or is pressed toward x=100.
   Start at (200,200): it is on the forbidden side and should be moved toward a nearest
   edge, possibly over several updates. Compare a target near the corner (320,320):
   passage around (300,300) is possible if the route does not stall.
3. **Open line.** Use one segment (200,100)–(200,300), status
   `bnd_ACTIVE|bnd_LINE`, start (150,200), aim (250,200). It does not act as a
   solid wall solely because its name is `Nav1`. Add `bnd_SOLID`: (150,200) is
   on the permitted side, while (250,200) is blocked. A point such as (150,350)
   is also outside the permitted region; the allowed area does not continue
   infinitely above the endpoint. Replace solid with `bnd_INVSOLID`:
   (150,200) is blocked, while (250,200) and (150,350) are permitted. Reverse
   the segment: the results stay the same. A horizontal single segment has no
   odd-crossing region for points off the segment: solid status permits no such
   points, while inverse-solid status forbids none by containment. Direct-route
   intersection with that segment can still trigger a route change.
4. **Straight edge and endpoint.** Use a legal region whose right boundary follows
   (200,100)–(200,300), with a large return path outside the test area. From (150,200)
   aim at (250,200), then from (150,330) aim at (250,330). The first order meets the
   line; the second passes beyond its endpoint. Observe any slide, turn, or stopping
   point. This distinguishes a region edge from an infinite wall.
5. **Concave region.** Make a U-shaped permitted region with a 100-unit-wide inward
   notch. Put the unit at the notch bottom and a target beyond one arm. With no guide
   line, the direct route encounters the wall; expect repeated correction, sliding,
   or a stop rather than an automatic corner route. Add an active line whose
   endpoints can each be reached by a straight segment within the permitted region,
   and whose vertices follow the free passage around the arm. Expect the point order
   to gain intermediate waypoints and escape. Widen the notch or move a guide endpoint
   behind the wall to distinguish a valid guide from an unusable one.
6. **Scenery and unit detours.** On an otherwise open field, put a solid object of
   radius 40 at (200,200). Move from (100,200) toward (350,200); expect a left or
   right detour and renewed steering after it clears. Replace the object with a
   friendly stationary regiment of similar footprint; expect avoidance plus visible
   push if they overlap. Then put a second obstacle across the chosen side and
   compare the newly chosen path. A rejected route requires both trial scores
   to reach 12,000; merely making one route longer does not guarantee rejection.
7. **BattleEdge and flight.** Use BF001's inset rectangle. Aim an ordinary unit from
   (1500,800) at (1650,800), then charge east from the same point. A charge ends
   on the first boundary correction after its footprint centre is outside;
   its centre moves halfway toward x=1584 on that update and may still be outside.
   Later corrections move it closer, subject to collision pushes. Route another
   unit east and follow
   its reference point, a point one footprint radius behind it, visibility, and
   target selection. Expect target loss at the first periodic check with the
   reference point outside. When the trailing point is outside at that or a
   later check, expect no removal until a later update; if its models are at
   rest, expect removal on the next update. Change its frontage/ranks to
   separate those moments. Place a pursuer behind it: the pursuer stays on the
   table.
8. **Centre versus models and pushes.** Face a deep block east with its reference
   point just inside x=300 of a solid allowed square. Increase ranks or turn it 90°
   without changing the reference point; compare the footprint centre and model
   positions. Put another friendly footprint so its push drives the centre across
   x=300; expect a later correction toward the permitted side, not a final clamp
   in the same collision pass. Start an isolated centre at x=330 against the same
   line and expect x=315, 308, 304, 302, 301 on successive correction updates.
   Repeat at high speed and inspect every update for transient overlap.
9. **Status versus name.** In a copy of a test battle, rename a deployment boundary
   without changing its status: deployment should remain constrained. Rename a solid
   terrain boundary `ViewEdge` while retaining solid status: its movement role should
   remain. Conversely, give a former solid entry only view status: it should cease
   constraining unit movement. Remove `set:status` entirely and compare with the
   status-free name alone: it should keep its boundary geometry but cease to
   constrain movement or serve as a deployment, sight, view, or camera boundary.
10. **Forest scenery versus collision data.** In BF024, compare a unit aimed
    through a cluster covered by an active solid object circle with one aimed
    through the isolated pine at (480,80), which has no object circle at its
    position. The first route should detour or be pushed by the circle; the
    second tree position alone should not push the unit. Keep other objects
    and regiments away from the second route.
11. **Competing guide lines.** Use a permitted field (0,0)–(600,600) and an
    inverse-solid square (250,150)–(350,450). Move from (100,300) to (500,300).
    Add an active guide from (200,500) to (400,500), then one from (200,100)
    to (400,100). Both connector legs are clear and the routes are symmetric:
    expect the top guide because it is listed first. Swap the entries and
    expect the bottom guide. Move the upper guide to y=550 and expect the
    shorter lower guide regardless of entry order. Remove the obstacle and
    expect a straight route that ignores both guides.
12. **Avoidance rejection.** In a permitted rectangle (0,0)–(500,200), put an
    active solid object of radius 110 at (250,100). Aim a small regiment from
    (80,100) to (420,100). The object blocks the direct leg and leaves no
    route for its footprint between the object and either long side of the
    rectangle. If both trial detours step outside, expect the move attempt to
    give up. Widen the rectangle on one side so one trial stays inside:
    expect it to choose that side. Moving another unit into the opening can
    change the next trial result. Record the chosen side and final position;
    the exact rejection tick depends on footprint size and facing.

## Remaining uncertainty

The shipped data settles the presence of `set:status` and the distinct status
assignments, including the coexistence of Nav and terrain boundaries. The rules
above settle the listed collision, edge, charge, routing, and forest-data cases.
Two limits remain: no new original-game play session measured the visible
trajectories in the custom scenarios, and contradictory combinations of status
roles on a custom boundary have no shipped example. Test those combinations
separately if an independent editor permits them.
