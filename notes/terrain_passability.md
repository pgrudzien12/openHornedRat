# Terrain passability and unit removal

This note is a short index to the public behavioural report
[`movement_boundaries_route_finding.md`](movement_boundaries_route_finding.md).
The prior version incorrectly said that `.BTS` boundaries have no `set:status`,
that `Nav*` and terrain boundaries never coexist, that every `Nav*` is a solid
obstacle, and that a routing regiment is removed immediately when its footprint
first crosses BattleEdge. Those claims are withdrawn.

The 54 shipped `.BTS` files contain 409 boundaries; **all 409 specify
`set:status`**. Movement roles follow status, not names. `Nav1`–`Nav8` are
active lines without solid status. Terrain-named boundaries can be solid,
inverse-solid, or, in one `RiverEdge` case, view-only. At least 34 battles
contain both a Nav line and a solid or inverse-solid terrain boundary.
The Nav lines can supply intermediate waypoints for a point route that crosses
a movement boundary; they do not themselves stop a moving unit on contact.
`BattleEdge` is tagged as a battlefield edge and normally defines a closed,
inset playable region. `GRND.GD` contains height geometry, not a passability
layer. Scenery objects must be assessed by their own collision data; the
absence of a forest boundary alone does not establish that every tree is
non-solid. BF024 places 187 pine trees and 85 active solid object circles.
Every object circle covers at least one tree position; 185 tree positions fall
inside those circles and two do not. Collision follows the authored objects,
not the visual tree count.

An ordinary regiment is kept toward the permitted side of a movement region;
a charging regiment ends its charge on boundary correction. A routing regiment
may flee across BattleEdge. Other units drop it as a target after its reference
point is detected outside; the regiment is marked for removal when a point one
footprint radius behind it is also detected outside. Those findings may occur
at the same periodic check or at different checks. It disappears on the first
later battle update when its models have no pending motion, which can be the
next update. A pursuit does not continue off the table.

If a boundary has no `set:status`, it remains active with its geometry but
has no movement, deployment, sight, view, or camera role. Its name supplies
no fallback. The permitted side of a custom open solid polyline is
defined by odd crossings of a rightward ray, without an implicit closing edge;
see the coordinate examples in the linked report.
