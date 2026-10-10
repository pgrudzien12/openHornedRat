# Hidden reserves waiting off the field (BF008): boundary correction, spotting, entry

Public implementation report (behaviour only), answering the implementer's BF008 question. In BF008 two hidden
Clanrat units start in a cave pocket behind the solid cliff boundary. In the engine they were dragged out, spotted,
and then stuck at the cave mouth forever. Companions, cited rather than repeated: `script_behaviours.md` §2.1–2.2
(collision re-check state, collision pass, push apart), `movement_boundaries_route_finding.md` (boundary correction:
halfway step, truncation, timing), `bf003_wolfriders_route.md` item 4 (correction only for units that moved),
`game_rules.md` "Visibility" / "Hidden units", `threat_events_nodes.md` Part C (node areas, `IfAnyUnitInNodeArea`)
and §6 (`ReactToThreat`), `scatter_models_to_node.md`, `movement_formation.md` (`TeleportToNode` idiom),
`fanatic_collisions.md` §5 (re-check throttle).

## 0. Shared state (read this first)

| state | meaning here |
|---|---|
| **hidden** | the `hidden:` keyword of a `.BTS` unit (`deployment.md`). It ends **only** by being revealed: spotted (`game_rules.md` "Hidden units"), starting a charge, or launching a missile (`script_shooting.md` §1.2). No placement opcode reveals. |
| **army** | player army, allied, enemy (`game_rules.md`). Neutral/furniture pseudo-units are not regiments here. |
| **collision re-check** | `script_behaviours.md` §2.1: a unit's collision pass (and the boundary correction inside it) runs only on updates where this state is on. It is **not** on for a unit that has stood still since load. A new footprint (teleport, re-layout of the formation), a turn, moving, a push or a touch in another unit's pass, and the correction moving the unit each switch it on. |
| **boundary correction** | the step at the start of a unit's own collision pass that moves the footprint centre halfway towards the nearest legal point of a solid, inverse-solid or BattleEdge boundary (`movement_boundaries_route_finding.md`). |
| **leaving the battle** | the escape walk state that library script 170 sets (`SetUnitFlags2 2048`) before teleporting to node 24 and removal (`threat_events_nodes.md`). It also exempts a unit from boundary correction. It plays no part in BF008. |

There is **no** separate "off-field / not yet placed / staging" state. The reserves are ordinary active regiments,
hidden and standing still.

## 1. Q1: boundary correction, scenery push-out and push-apart for hidden units

**Boundary correction is skipped for a hidden unit of the enemy or allied army** (and for a unit leaving the
battle). It applies to every other regiment whose own collision pass runs, including a **hidden player-army** unit.
This covers all three kinds: solid, inverse-solid and BattleEdge. The skip lasts exactly as long as the unit stays
hidden: once revealed, its next pass with re-check on corrects it as usual.

Everything else in the collision pass ignores the hidden state:

| situation | hidden unit H (enemy army) |
|---|---|
| H's own pass (only when H's re-check is on) | runs normally **without** the boundary correction: solid-scenery and building push-out, push-apart against same-army regiments, contact with other-army regiments (`script_behaviours.md` §2.2) |
| another unit's pass, H overlapping it | H's footprint is an ordinary active footprint: the mover is pushed away from H, H's re-check is switched on, and an other-army mover makes **contact** (engagement) with H |
| H stationary since load, nothing touching it | no pass at all (re-check off), so nothing moves it, hidden or not |

Furniture without a building footprint (BF008's `CaveLeft/Mid/Right/Ent`) has no footprint and pushes nothing.

## 2. Q2: can a hidden unit in a solid pocket be spotted?

Spotting ignores position and boundaries. It is only `IsVisible`: the spotter's view cone (±50°, ±100° in melee),
scenery sample rays, and **no `SightEdge` line crossed**. There is no range limit (`game_rules.md`). So a hidden unit
inside a solid area **can** be spotted if a line of sight reaches it.

**In BF008 none does.** Its `SightEdge` area outlines the valley. One of its lines runs along y = 464 from x 888 to
1032 and another from (800, 568) to (888, 480). Both reserves (919, 382) and (992, 453) are on the far side of those
lines from every point of the valley, so every sight line from the field crosses a `SightEdge` line. Nobody on the
field can enter the pocket either: the solid cliff boundary keeps them out. The reserves stay hidden while they
wait.

The reserves' own periodic AI (behaviour 15 `TrackThreat`, every 30/31/32 updates) runs while they wait. Its
spotting and threat pick need the same visibility, so they find nothing (§5). Their `ReactToThreat` would also
need `IsVisible` (`threat_events_nodes.md` §6). A hidden reserve therefore never reacts out of the pocket.

## 3. Q3: is there another exemption?

No, only **hidden** (enemy/allied army). Reveal by spotting, charging or firing ends it. `ScatterModelsToNode`,
`SnapModelsToFormation`, `TeleportToNode`, `PlaceAtNode` and `ReformToScriptRanks` do **not** change the hidden
state. `InitUnit` keeps it as well (`deployment.md`).

What really keeps the reserves in place is the combination of two facts:
1. they stand still from load (no re-check state, so no collision pass at all). `InitUnit` queues a re-form at the
   current ranks, but its own `SnapModelsToFormation` cancels that before any re-layout. Even if a pass did run, it
2. would skip the boundary correction, because they are hidden enemy units.

## 4. Q4: after `TeleportToNode 3`

**Still hidden.** The teleport moves the regiment centre to node index 3 (920, 540) and sets its facing to the
node's direction (502). It translates every model by the same offset, so the formation is kept, and builds a new
footprint, which switches the collision re-check on. `ReformToScriptRanks` then re-lays out the formation for the
new facing and script ranks. `ResetModelAnimations` staggers the models' start (`movement_formation.md`), and
`WaitWhileUnitFlags 8` waits until every model has reached its slot.

From then on the unit is reachable by sight: (920, 540) is inside the sight area. It is revealed by the first player
unit's threat detection (behaviour 11/12, every 31 updates) whose cone and sight line reach it, or when it starts a
charge. Until then it is still exempt from boundary correction, but it collides normally (§1).

## 5. Q5: BF008 trace under the original's rules

Data (`BF008.BTS`): unit 1 = Clanrats (visible) at (899, 572), script 0 (`AttackNearestEnemy` every 10 ticks after
battle start). Unit 2 = hidden Clanrats at (919, 382), script 1. Unit 3 = hidden Clanrats at (992, 453), script 2.
Node index 3 = (920, 540) r 66. The only node with **id** 1 is index 4 = (920, 409) r 10, at the cave mouth inside
the pocket (`ScatterModelsToNode` takes an **id**, `scatter_models_to_node.md`).

| when | unit 2 (script 1) | unit 3 (script 2) |
|---|---|---|
| load / deployment | `InitUnit` (hidden kept, queued re-form cancelled by the snap), behaviour 15 every 31 updates, waits for battle start | same, behaviour every 32 updates |
| battle start → +90 / +250 | `SetWait 90; Wait` in place. No pass, no correction, not visible | `SetWait 250; Wait` |
| then every 10 ticks | `IfAnyUnitInNodeArea 3`: is **any** unit of any side, in any state (itself and hidden units included), within 66 (Euclidean, inclusive) of (920, 540)? Its own centre is 158 away and unit 3's is 112 away, so neither counts. **Unit 1 starts inside** (38 away) and leaves when its `AttackNearestEnemy` approach takes it off. A player unit standing at the cave mouth keeps the gate shut. | same gate; also shut while unit 2 is still inside the area after its own entry |
| gate open | `ScatterModelsToNode 1` (each model gets a destination within 10 of (920, 409)), immediately cancelled by `SnapModelsToFormation` (models back in their slots, no visible move; only the random draws are consumed). Then `TeleportToNode 3` → at (920, 540), facing 502, **still hidden**, re-form with staggered starts, wait for the re-form | same |
| after the re-form | restart point; every 10 ticks `AttackNearestEnemyByAxis` (hidden attacker allowed, hidden targets excluded). It is revealed when spotted or when it starts a charge | same, with `AttackNearestEnemy` |

So the reserves appear at the cave mouth **one at a time, each only once the mouth area is empty**. Unit 2 can come
from about tick 100 (90 + the first 10-tick check), and unit 3 from about tick 260, later if unit 2 or anyone else
is still in the area. They do not appear from the pocket's own position, and they are never dragged out of it.

## 6. Test vectors

Regiment H = hidden enemy Clanrats, footprint radius 30, inside a solid area 154 from its nearest edge, never moved
since load (re-check off) unless stated.

| before | action / update | after |
|---|---|---|
| H as above | any number of updates | H unmoved: no pass (re-check off) |
| H, re-check switched on (e.g. a turn) | H's pass | **no boundary correction** (hidden enemy). Scenery/same-army pushes as usual. H unmoved if it overlaps nothing |
| same, but H is a **hidden player-army** unit | H's pass | corrected: centre moves halfway towards the nearest legal point (truncated per axis) |
| same, H **revealed** (spotted) earlier | H's pass | corrected as any unit |
| H unit of the **leaving the battle** state (library 170), outside the field | its pass | not corrected |
| enemy H hidden, player regiment P overlapping H (P moving, re-check on) | P's pass | P makes **contact** with H (other army). H's re-check on. H's own pass: pushes/contact, no correction |
| two hidden same-army reserves overlapping, both re-check on | their passes | push apart as usual (`script_behaviours.md` §2.2). No boundary correction for either |
| player unit S in the valley, its ±50° cone covering H at (919, 382), sight line crossing the BF008 `SightEdge` line y = 464 | S's behaviour 11 run | H **not** revealed |
| H after `TeleportToNode 3` at (920, 540), S's cone covers it, no scenery and no `SightEdge` in between | S's behaviour 11 run | H revealed: event 0x1C to S, 0x1D to H |
| H after the teleport, not yet spotted, starts a charge | – | revealed by the charge |
| unit 1 at (899, 572) (d = 38 ≤ 66 from node 3) | unit 2: `IfAnyUnitInNodeArea 3` | true → keeps waiting |
| no unit within 66 of (920, 540) | same | false → enter |
| a player unit at (960, 590) (d = 64) | same | true: the reserves stay inside as long as it stands there |

## 7. Differences from the implementer's engine model

1. Boundary correction must **skip hidden enemy/allied units** (and units leaving the battle), and run only inside a
   unit's own collision pass while its re-check state is on (already public: `bf003_wolfriders_route.md` item 4).
   Both conditions keep the BF008 reserves in the pocket. Push-apart, scenery and building push-out, and contact
   keep treating hidden units normally.
2. `InitUnit` must not leave a pending re-form behind (its snap cancels it), so a fresh unit is not "moved" at load.
3. Spotting must cross-check `SightEdge` lines. BF008's pocket is sealed by them.
4. `ScatterModelsToNode` takes a node **id** (BF008: index 4), not an index. `TeleportToNode`/`PlaceAtNode` do not reveal.
5. The entry gate counts every unit in the area, so a unit pushed into node area 3 (your symptom) or a player unit
   parked at the cave mouth holds the reserves back. With (1) fixed, nothing pushes the reserves there.

## 🟡 Open

- Whether a regiment's footprint is built at load in a way that leaves its re-check state on for the first update.
  It does not matter for the hidden reserves (§1 skips the correction anyway). For visible units the public timing
  rule above stands.
- Exact first-check tick (90 + 10 per the wait semantics of `unit_script_control.md`; ±1 tick).
