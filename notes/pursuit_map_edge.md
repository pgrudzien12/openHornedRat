# Pursuit and the map edge

Clean-room behavioural handoff for the implementer (issue under epic #10). It answers how a pursuing regiment
interacts with the BattleEdge, what ends a pursuit, and what the pursuer does afterwards. Read with
`game_rules.md` "Pursuit", "Player orders and the command panel" and "Real time and movement",
`movement_boundaries_route_finding.md` "Map edge and route outcomes", and `obstacle_steering.md`. Static research;
the original was not run.

## 1. Short answer

- A pursuer **respects the BattleEdge**, but it checks the edge only **once per segment** (every 19 ticks). It
  never leaves the table and is never removed for reaching the edge; only routing units are removed there.
- Between segment boundaries it moves in a straight line at pursuit speed with no edge check, so it **can run a
  little past the edge**. The ordinary per-update edge correction then pushes it back by halves. That correction
  **does not end a pursuit**: it only pushes. It ends a charge, and a pursuit is not a charge.
- At the next segment boundary, if the edge probe ahead of it is outside the battle area, the pursuer sends itself
  **"stop pursuing" (event 0x10)**. Next update it shouts "Re-group!", stops pursuing, re-forms where it stands, and
  goes back to its normal script. A player unit then waits for orders and accepts them normally, even from just
  outside the edge.

## 2. The pursuit update (once per segment)

A pursuing regiment moves every update along its current heading at its pursuit speed (`game_rules.md` "Unit
speed": the pursuit step). Everything else below happens **only on the segment-boundary tick**, the tick on which
break tests and melee resolve, once every 19 ticks:

1. **Restraint test.** If this is the pursuer's scheduled segment and its rally-attempt state is on (player Rally
   order 0x14, or the Independent toggle), it is rescheduled 3 segments later and, unless it has `AlwaysPursue`,
   rolls the pursuit-restraint test. A pass sends event 0x10 to itself. (`game_rules.md` "Pursuit", "Rally".)
2. **Target check.** If it has no target, or the target is no longer a live broken (routing) unit (dead,
   removed, left the table or rallied), it sends event 0x10 to itself and stops here.
3. **Re-aim.** It sets its route to the fugitive's footprint and steers there with the ordinary live steering of
   `obstacle_steering.md` §4. The chase point is the fugitive's position itself; it is **not** clipped to the
   battle area.
4. **Chase budget** (`game_rules.md` "Pursuit"): on the first check `min(2 × distance, 120)`; afterwards
   `+= (previous distance − distance) − 4`. Not with `AlwaysPursue`: if it reaches 0 or less, event 0x10 to itself.
5. **Edge probe.** Take the probe point **one own collision radius ahead of the front-rank position** along the
   current facing:
   `probe = (x + trunc(SIN[f] × r / 256), y + trunc(COS[f] × r / 256))`,
   with `f` the facing, `r` the regiment's stored collision radius and `SIN/COS` the 256-amplitude tables. If the
   probe is **not inside any active BattleEdge area**, the pursuer sends **event 0x10** to itself. Solid and
   inverse-solid areas are not part of this probe. With no BattleEdge entry in the battle at all, the first probe
   stops the pursuit (`movement_boundaries_route_finding.md`).

Event 0x10 is handled at the start of the **next** update (scripts run before movement), so a stopping pursuer
does not take another pursuit step.

## 3. The edge correction and pursuers

The per-update collision pass corrects any moving regiment whose **collision centre** lies outside the solid,
inverse-solid or BattleEdge limits. It moves the centre half the remaining distance toward the nearest allowed
point, per axis, truncated (`bf003_wolfriders_route.md` §3 step 7). Rules:

- **Routing units** (fleeing) and war machines are not corrected; routing units cross the edge and are removed
  (`game_rules.md` "Flight and catching fleeing units").
- A **charging** regiment that is corrected has its **charge ended**: charging state off, halted, charge sound
  stopped, event 0x09 to its target.
- A **pursuing** regiment that is corrected is **only pushed**. Its pursuit continues until the next segment
  probe.
- A pursuit turns into a charge when the pursuer runs into a **different** enemy (`game_rules.md` "Player orders
  and the command panel", Charging flag). From then on the correction rule for charges applies.

While a pursuer overshoots, its outward step each update competes with the correction pulling its centre back by
half. It hovers a few units outside until the next segment boundary stops the pursuit.

## 4. After the pursuit ends

Event 0x10 is handled by the common library event layer:
1. `React 17` ("Re-group!" for the race; `script_behaviours.md` §3.3);
2. the re-form script: **stop pursuing** (the pursuing state and pursuit movement end, as for a rally),
   **re-form** in place, then **restart** the regiment's main script at its restart point.

A player regiment returns to its normal script and waits for orders. An AI regiment resumes its mission loop
(typically threat tracking and new attacks). Nothing returns it to where the pursuit started.

**Standing just outside the edge.** After re-forming, the regiment stops moving. The edge correction runs only
while a regiment is moving, being pushed or in contact. Each correction halves the excess with truncation toward
zero, so the centre can end up to about **one unit outside** the edge and then stays there. Nothing pulls it
further in. This is harmless:
- the regiment is not "outside the battle" for any rule except that a pursuit probe from there would fail;
- move, attack and other orders are accepted and planned from its front-rank point exactly as anywhere else
  (`obstacle_steering.md` §5: a plan may start outside the permitted area; only steer points are tested);
- once it moves, the correction runs again.

## 5. Player control

- **Pursuit is automatic** for player and AI regiments (`game_rules.md` "Pursuit").
- **While pursuing**, a player regiment's order gate passes only Withdraw (0x13), Rally (0x14), Magic (0x17), Halt
  (0x19), Independent (0x1A) and Fight harder (0x1B). Move, attack, turn, rank, charge and fire orders are ignored
  (`game_rules.md` "Player orders and the command panel").
  - **Rally (0x14)** toggles the rally-attempt state. The restraint test then runs at the pursuer's scheduled
    segments; a pass stops the pursuit.
  - **Independent (0x1A)**, per `game_rules.md` "Player orders", also lets the regiment test pursuit restraint
    without the Rally order. 🟡 The pursuit update itself only looks at the rally-attempt state, so the
    Independent toggle must work by setting that state elsewhere; this was not traced.
  - **Halt (0x19)** has **no effect** on a pursuing (or broken) regiment apart from the "Hold!" shout. The halt
    and re-form is refused for those states, so the pursuit continues.
- **After the pursuit**, the regiment is an ordinary halted regiment and accepts every order.

## 6. Differences from the current engine

| engine now | original |
|---|---|
| the per-update edge correction ends a pursuit ("charge") and drops its target | the correction only **pushes** a pursuer; it ends only a **charge** |
| no edge probe for pursuers | once per segment: probe one radius ahead of the front rank along the facing; outside every BattleEdge area → event 0x10 |
| pursuer left orderless with the target dropped | event 0x10 → React 17, stop pursuing, re-form in place, restart the main script (player: awaits orders) |
| re-aim, budget and restraint presumably every update | re-aim, budget, restraint test and edge probe only on the **segment-boundary tick**; straight-line motion in between |

The engine's end state, about one unit outside the edge and halted, matches the original. What differs is **why
and when** the pursuit ends (segment probe, not correction), and that the original re-forms and returns control to
the regiment's script.

## 7. Test vectors (BF003 east edge)

The BattleEdge runs at **x = 1160 for y 1120…1200**, with diagonals (1240, 1040)–(1160, 1120) above and
(1160, 1200)–(1080, 1280) below. Pursuer: cavalry, collision radius 30, facing 128 (+X) unless stated.

| before | when | after |
|---|---|---|
| front (1120, 1130), pursuing a live routing target | segment tick | probe (1150, 1130) inside → pursuit continues |
| front (1135, 1130), pursuing | segment tick | probe (1165, 1130) outside → event 0x10 queued; next update: React 17, stop pursuing, re-form, restart script |
| front (1158, 1130), pursuing | ordinary tick | moves on along +X; no probe; if its centre is outside, the correction pulls it back half the excess; still pursuing |
| centre (1166, 1130), pursuing, moving | ordinary tick | correction `trunc((1166 − 1160) / 2) = 3` → centre 1163; pursuit continues |
| same, but the pursuit became a charge after hitting another enemy | ordinary tick | correction ends the charge: halted, event 0x09 to the target |
| centre (1161, 1130), halted after the pursuit, no movement | any tick | no correction runs; stays at 1161 |
| same | player Move to (900, 1130) | accepted; route planned from the front-rank point; moves west |
| pursuer's target removed after crossing the edge | next segment tick | target gone → event 0x10 (independent of the edge) |
| player pursuer, player issues Move | while pursuing | ignored |
| player pursuer, player issues Rally | while pursuing | rally-attempt state toggled on; at its scheduled segment the restraint test is rolled; a pass → event 0x10 |
| player pursuer, player issues Halt | while pursuing | "Hold!" shout only; pursuit continues |
| battle with no BattleEdge entry | first segment tick of a pursuit | probe outside every BattleEdge area → event 0x10 |
