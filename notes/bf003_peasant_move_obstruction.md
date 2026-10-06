# BF003 Peasants and Move-order obstruction

Clean-room behavioural handoff for ordinary Move orders. The original game was unavailable for runtime testing; these findings come from static research and the installed BF003 unit data. They refine `movement_boundaries_route_finding.md`'s broad statement that unit footprints can obstruct routes. No engine behaviour has been changed by this report.

## Result

**Peasants are not universally ignored by route finding.** Their regiment footprints are ordinary live unit footprints. Route planning may nevertheless pass them over because the game's unit-obstruction decision depends on the mover's current movement state, the two units' travel directions and speeds, proximity, and target relationship. It does not test the Peasant name or unit type. For this decision, player and neutral regiments are on the same side of the conflict; an enemy regiment treats a neutral Peasant as an opposing unit.

The distinction that matters in BF003 is that a new Move order normally runs its first route check while the player infantry is **stationary**. A stationary Peasant regiment also has zero route speed even when its individual models are walking around their scatter nodes. Two stationary same-side regiments do not necessarily require a detour. The live route may be reassessed once infantry starts moving, so the exact later steering depends on their headings and positions.

## Route obstruction rule for unit footprints

The obstacle must have a live collision footprint other than the mover's own, lie closer than the current destination, be within the mover's obstruction reach, and subtend part of the mover's current route bearing. This reach is a per-unit script setting; the ordinary player script sets it to **240 world units**. The route geometry uses each regiment's **stored integer bounding radius**, added together for angular clearance. A near tangent is not equivalent to a physical overlap.

For ordinary block formations with `N` living models and `r` ranks:

`frontage = ceil(N/r)`; `half_width = 6×frontage`; `half_depth = 6×r`;
`route radius = trunc(sqrt(half_width² + half_depth²))`.

The footprint centre is `(r−1)×6` units behind the first-rank centre along the regiment's facing. The route compares a blocker at centre distance `d` using an angular half-width approximately `asin((own radius + blocker radius)/max(d, own radius + blocker radius))`; the blocker must also be ahead on the route and short of the destination. The original uses integer positions, stored integer radii and a 512-direction turn scale. Exact equality at an angular boundary should not be inferred from a floating-point simulation.

After this geometric test, a unit blocker is filtered by relationship and movement:

| Relationship and state | Route treatment |
|---|---|
| Current target, or a unit treated as part of the current target group | Not a detour obstacle. |
| Opposing unit | May obstruct while live, visible, unbroken and still on the battlefield. The mover's combat state and the route phase can also affect inclusion. |
| Same-side unit with travel directions within 45° | Obstructs only when the mover's effective travel speed is greater than the other's. Two stationary units therefore do not obstruct one another in this case. |
| Same-side unit with directions at least 45° apart | A faster mover treats it as an obstacle. When the mover is no faster, a **near** unit (octagonal distance `max(|dx|,|dy|)+ceil(min(|dx|,|dy|)/2)` below `16 × the mover's speed stat s_rlmv`) is not detoured around: the moving regiment **pauses 54 updates** and then continues (`obstacle_steering.md` §6). A more distant unit obstructs. |

These are route tests, not collision immunity. An individually scattering Peasant model does not by itself relocate its regiment's route footprint: BF003's scatter behaviour leaves the regiment position and formation slots in place. A Peasant regiment that actually moves or reforms can change its centre, radius, travel heading or effective speed and therefore change the next route decision. The rule applies to other same-side units, including player allies and other neutral NPCs; it is not Peasant-specific and not a blanket neutral exemption. A unit on the opposing side uses the opposing-unit branch regardless of its neutral label in another relationship.

## Physical collision is separate

Every ordinary live unit retains its block footprint for physical collision. Physical overlap uses the **same stored integer radii** but asks whether `centre distance < own radius + other radius`, rather than whether a route ray should avoid the other unit. If normally active, nonengaged player infantry overlaps BF003 Peasants, both can receive a push. For this pair the game uses the allied-side separation branch, since their side codes share the same conflict side. Each unit's collision pass can move its own regiment and models by roughly half the penetration plus a small separation allowance. Broken, engaged, removed and already resolved collision states can alter that result. The Peasants' lack of route detour on a particular check never makes them intangible.

## Worked BF003 geometry

The installed `FILE/SCRIPT/BF003.BTS` has three neutral Peasant regiments. Their sizes and ranks give these footprints:

| Peasant group | Models × ranks | Frontage | Half-width × half-depth | Stored radius | Floating-point half-diagonal |
|---|---:|---:|---:|---:|---:|
| First, at (645, 670) | 5 × 2 | 3 | 18 × 12 | 21 | 21.633… |
| Second, at (757, 588) | 3 × 3 | 1 | 6 × 18 | 18 | 18.974… |
| Third, at (693, 427) | 4 × 2 | 2 | 12 × 12 | 16 | 16.970… |

Their installed morale setting forbids rallying; it does not grant a route-obstruction or collision exemption.

For example, take a 20-model, four-rank player infantry block near the first Peasant group. Its stored radius is `trunc(sqrt(30²+24²)) = 38`; the Peasants' is 21. Their original-game physical overlap threshold is **59**, whereas a floating-point engine using full diagonals uses about **60.05**. If a log reports the formation centres about **0.02** beyond the engine's combined radius, their distance is about 60.07: they are more than one world unit beyond the original physical threshold. Neither side should be pushed at that instant. This example uses the installed Peasant size and an illustrative infantry formation; the exact infantry size and direction in the reported log were not supplied.

If both regiments are stationary when that infantry receives a new Move order, their effective route speeds start at zero. With travel directions within 45°, the Peasants fail the same-side speed test. With directions farther apart, the near-unit test uses the mover's speed stat: for example `s_rlmv` 11 gives a threshold of `16×11 = 176` octagonal units, which a Peasant group about 60 units away is well within. It is then not a detour obstacle, so the initial route is accepted without left and right trials. Once the infantry is moving it is faster than the stationary Peasants, so they become an ordinary detour obstacle; the 54-update pause applies only to a near same-side unit that is at least as fast as the mover. After movement starts, recheck the rule using the new speed and headings; an actual later overlap is resolved by a push, not by retroactively rejecting the original Move order. A repeated Move order issued **while infantry is already moving** can make a different route decision because its effective speed is then nonzero.

**Implementation acceptance cases:** (1) a stationary same-side Peasant with a matching travel direction and zero speed does not trigger detour selection for a newly stationary mover; (2) a faster mover can treat the same live Peasant as a route obstacle on a later update; (3) a slight gap measured with floating half-diagonals is recalculated with each stored integer radius; (4) an actual player–Peasant overlap pushes the normally active pair; (5) replacing Peasants with another allied-side unit of identical state and footprint gives the same route decision. Where directions differ, use the octagonal distance and `16 × s_rlmv` for the near-unit test; a moving mover pauses 54 updates instead of detouring.
