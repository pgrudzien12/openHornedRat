# Player move routes: multi-stop orders, route markers, end facing

Clean-room behavioural handoff for the implementer. Static research; the original was not run, so nothing here was
checked on screen. Companion reports:
[deployment.md §3–4](deployment.md#3-player-interaction) (deployment input),
[game_rules.md, "Player orders and the command panel"](game_rules.md#player-orders-and-the-command-panel) (order codes,
panel sets, minimap layout),
[movement_boundaries_route_finding.md](movement_boundaries_route_finding.md) (detour points from guide lines),
[close_point_move.md](close_point_move.md) and [movement_formation.md §1.4](movement_formation.md) (turning on a leg,
arrival test). Conventions: facing in 1/512 turn, 0 = +Y, clockwise; positions in world units.

## 1. Short answers

1. **Re-selecting in deployment clears the route.** Any left press on your own regiment in deployment halts it,
   which drops its prepared route. This happens at the press, before any movement and whether or not a drag follows.
   A press on the minimap goes through the same handler, so it clears the route too. A press on an allied or enemy
   regiment only selects it. Previous/next selection does not clear the route. Pressing the deployment **Move button**
   also halts the regiment and clears its route (new, see §2). **In battle, a click on your own regiment never
   touches its route.**
2. **Route markers** are drawn only on the **minimap**, in deployment and in battle, and only for the **focused
   regiment** (the one the HUD shows). That regiment must be the player's own (not allied), active, and not charging,
   in close combat, broken or pursuing. Only the stops the player clicked are drawn; the route finder's detour points
   are never drawn and never numbered. Each stop gets two sprites: a **number label** (`ICONS` 161–169 = "1"–"9") and,
   centred on the stop, either a **red arrow** toward the next stop (`ICONS` 119–126, 8 directions) or, on the last
   stop, the **red end dot** (`ICONS` 159). A stop is removed when it is reached, and the remaining stops renumber, so
   the next stop is always "1". There is no marker in the 3D view.
3. **Battle Ctrl-append works as in deployment.** The limit is nine stops. A point near the **last** stop is
   refused. A point near the **first** stop **closes the route into a loop**, and the regiment then patrols it
   until it gets another order. Each of these ends the append mode. A plain click while appending **adds no
   stop** and only ends targeting; this corrects deployment.md §3. Shift has no meaning for move orders. Every
   order goes to **every selected player regiment at the same clicked point**, with no formation offsets.
4. **There is no chosen end facing.** No gesture or order gives a route a final facing, and the stop arrows are
   display only. The regiment halts with the heading of its **last leg**: whatever its steering had when the
   arrival test passed. Face point, the 90° turns and about-face all **replace** the route; they do not queue
   behind it. With several selected regiments, each one walks to the same point, keeps its own last-leg heading,
   and the collision push sorts them out. Their relative positions are not kept.
5. **Only rank changes leave a route alone.** Ranks up/down re-forms the block without dropping the route. Move,
   Attack, Charge, Halt, Face point and the turns all replace it. While the regiment is re-forming, a Move or Face
   point waits and runs when the re-form ends ("queued while busy" in game_rules.md); it does not join the route.

## 2. Input: how a Move order is built

Ctrl is read **at the moment of the map click**, not when the Move button was pressed. Targeting has two modes:
*Move* (entered from the Move button) and *Append* (entered by the first Ctrl-click).

| Mode | Click | Order sent | Targeting afterwards |
|---|---|---|---|
| Move | plain | go to point (**replaces** the route) | ends. In battle the panel returns to idle; the deployment panel stays as it is. |
| Move | Ctrl | go to point (**replaces** the route) | switches to Append |
| Append | Ctrl | add stop (§3) | stays in Append unless the add is refused or closes a loop (§3) |
| Append | plain | **nothing** | ends, as above |

So the first Ctrl-click of a chain starts a new route; it does not add to the old one. A minimap click acts the same
as a 3D-view click at the converted world point.

**Who receives the order.** The order goes to every *selected* regiment that belongs to the player. Allied regiments
never take it. In battle Shift-click toggles a regiment's selection without clearing the others. A plain click clears
every other selection and then **toggles** the clicked regiment, so a plain click on the only selected regiment turns
its selection off while the HUD still shows it 🟡. That looks like a quirk; confirm it on screen before copying it.
Deployment keeps one selected regiment and ignores Shift.

**Deployment-only differences.**

- A left press on your own regiment halts it and starts a drag, which clears its route (point 1 above). This
  happens before the drag code looks at any mouse movement.
- The deployment Move button halts the focused regiment and snaps its models to their slots before targeting
  starts, so **every new Move chain in deployment starts from an empty route**. The battle Move button and Move
  sub-set do not halt.
- An *add stop* that reaches a regiment with no prepared route turns into a plain *go to point* at that click.
  In battle the same add does nothing (§3).
- The prepared route waits at the battle-start barrier and resumes after Start (deployment.md §5).

## 3. Adding a stop (Ctrl-click in Append mode)

Distances below are Euclidean, **truncated to whole units**. Steps, in order, for each receiving regiment:

1. If the regiment has **no route** or is **not on a move**, the add does nothing in battle; in deployment it
   becomes a plain go-to-point (§2). An arrived regiment has halted and is no longer on a move, so after the last
   stop Ctrl-clicks do nothing. Append mode stays on until a plain click.
2. If the route already has **9 stops**, the click is refused and Append mode ends.
3. The last stop's arrow is set to point at the new click: bearing from that stop to the click, in the
   facing convention, rounded to the nearest eighth (`(bearing + 32) / 64 mod 8`).
4. If the click is **within 17 of the last stop** (`d < 17`), it is refused. The last stop's arrow is removed, so it
   shows the end dot again, and Append mode ends.
5. If the click is **within 16 of the first stop** (`d < 16`), the route is **closed into a loop**. The leg from
   the last stop back to the first is planned with its detours, the click point itself is not kept as a stop, and
   Append mode ends. The first stop is the current next stop, so stops already reached do not count.
6. Otherwise the leg from the last stop to the click is planned and added: the route finder's detour points, then
   the click as a new stop. If the route finder cannot plan the leg, the click is refused and Append mode ends.

When the order goes to several regiments, each one runs these steps on its own route. A refusal or a loop by any one
of them ends Append mode for the whole player 🟡 (targeting is a single player-wide state).

**Loop (patrol) routes.** When a stop is reached on a loop route, it is moved to the end of the route instead of
being removed. The detours on the way to the *first* stop are the exception: they are dropped once passed, since
they belong to the approach and not to the loop. The regiment cycles through the stops until anything else
replaces the route: a new move, a halt, a turn, an attack, a charge, close combat, or a rout. A loop has no end
dot: every stop shows an arrow, and the last one points back at the first. Labels still count from the next
stop.

**Arrival at a stop** uses the ordinary test of movement_formation.md §1.4 and close_point_move.md: within 32
units and a turn of 64 or less. Detour points use the same test. Reaching an intermediate stop does not halt the
regiment; it goes straight on to the next stop. Reaching the last stop of an open route **halts and re-forms**
the regiment, with no turn.

## 4. Route markers on the minimap

Drawn after the plan map and the deployment-zone markers, and before the regiment markers.

| Item | Rule |
|---|---|
| Whose route | Only the focused regiment's. It must be the player's own (allied regiments never show one), active, and not charging, in close combat, broken or pursuing. Deployment and battle alike. |
| Which points | Only stops: clicked points and the destination of a single Move. Detour points are skipped, and they are not counted in the numbering. |
| Label | Stop *n* (1 = next stop) uses `ICONS` frame 160 + *n* (digits "1"–"9"). Its top-left corner sits 3 px left of and 12 px above the stop's minimap pixel. |
| Stop marker | Centred on the stop's minimap pixel. A stop with a following stop uses `ICONS` 119 + *k*: a red arrow, *k* = 0 points up (+Y), and each step turns it 45° clockwise. The last stop of an open route uses `ICONS` 159 (red dot). |
| Removal | A stop disappears when it is reached; the rest renumber. Halting, a new move or any order that replaces the route removes them all. |

The arrow frames are the same 8-way red arrows used for a friendly fighting regiment's minimap dot. The arrow shows
the *click-to-click* direction, not the detour path between them.

🟡 While a deployment drag is held, the route list is reused for the drag target. If the regiment's old first entry
was a stop, an end dot labelled "1" may follow the cursor until release. Not checked on screen; harmless to omit.

## 5. Other orders and the route

| Order during a route | Effect on the route |
|---|---|
| Move (plain or first Ctrl-click) | Replaced by the new one. |
| Ctrl-click in Append mode | Stop added (§3). |
| Face point | **Replaced**: the route is cleared and the regiment turns on the spot toward the point. |
| Turn left / right 90°, about-face | **Replaced**: the route is cleared and the turn is done. |
| Halt | Cleared; the regiment halts and re-forms. |
| Attack, Charge | Replaced by the approach or charge (attack_order_flow.md, battle_attack_charge_buttons.md). |
| Ranks up / down | Kept; the block re-forms with the new rank count. 🟡 How the march looks while it re-forms was not traced. |
| Independent toggle | Kept. |
| Any order while charging, in close combat, braced, broken or pursuing | Ignored (the regiment takes no ordinary orders). |
| Move or Face point while re-forming | Held until the re-form ends, then carried out. It still replaces the route. |

## 6. Test vectors

Routes are written as stop lists; detours are left out unless stated. "Sel" means selected, "foc" means focused.

### 6.1 Deployment

| Before | Action | After |
|---|---|---|
| Own regiment R, route [A, B], foc + sel | Press and release on R, no mouse movement (3D view or minimap) | Route empty; R halted and re-formed; no markers |
| Same | Previous/next button lands on R | Route [A, B] kept; markers "1"+arrow at A, "2"+end dot at B |
| Same | Press on an enemy regiment | Enemy focused; R keeps [A, B] (markers hidden: the focused unit is the enemy) |
| R, route [A, B] | Move button | Route empty (Move halts); Move targeting |
| R, Move targeting | Plain click P | Route [P]; targeting ends |
| R, Move targeting | Ctrl-click P, Ctrl-click Q, Ctrl-click S | Route [P, Q, S]; Append mode stays on |
| R, route [P, Q, S], Append | Plain click T | Route [P, Q, S] (T **not** added); targeting ends |
| R, route [P, Q, S], Append | Ctrl-click at distance 16.9 from S | Refused; S shows the end dot again; targeting ends |
| R, route [P, Q, S], Append | Ctrl-click at distance 17.0 from S and 40 from P | Route [P, Q, S, T] |
| R, route [P, Q, S], Append | Ctrl-click at distance 15.9 from P (and ≥ 17 from S) | Loop P→Q→S→P; S's arrow points at P; no end dot; targeting ends |
| R, route [P, Q, S], Append | Ctrl-click at distance 16.0 from P (and ≥ 17 from S) | Not a loop: route [P, Q, S, T] |
| R, route with 9 stops, Append | Ctrl-click anywhere | Refused; targeting ends; route unchanged |
| R, route [P, Q], Append | Start battle | R waits at the battle-start barrier, then walks P then Q |

### 6.2 Battle

| Before | Action | After |
|---|---|---|
| R moving on [A, B], foc | Plain click on R (no pending order) | Route kept; R's selection toggled 🟡 (§2) |
| R moving on [A, B] | Move button, Ctrl-click P | Route [P] (A, B dropped); Append mode |
| R moving on [P], Append | Ctrl-click Q | Route [P, Q] |
| R halted after arriving at its last stop, Append still on | Ctrl-click Q | Nothing happens; Append stays on |
| R moving on [A, B] | Face point at F | Route empty; R turns on the spot toward F |
| R moving on [A, B] | Ranks up | Route [A, B] kept; re-form with one more rank |
| R moving on [A, B] | Reaches A (≤ 32 away, turn ≤ 64) | Route [B]; B labelled "1" with the end dot; R goes on without halting |
| R moving on [B], last leg heading 300 | Reaches B | Route empty; R halts and re-forms facing ≈ 300; no turn |
| R on loop [A, B, C] (heading to A) | Reaches A | Loop [B, C, A]; labels B "1", C "2", A "3"; A's arrow points at B |
| R1 and R2 selected (Shift), R1 foc | Move, plain click P | Both regiments plan their own routes to the same point P. Only R1's marker shows. Both end on their own last-leg headings, and the collision push separates them. |

## 7. Changes for the engine model in the request

- **Re-select in deployment:** the engine's behaviour matches the original. A press with no movement does clear the
  prepared route, and so does a minimap press. Also clear the route when the deployment Move button is pressed. In
  battle, keep the route on a click.
- **Plain click while appending:** it must end targeting without adding the point. At the moment it replaces the
  route.
- **The first Ctrl-click in Move mode** replaces the route, then switches to appending.
- **Near-point rules:** within 17 of the *last* stop, refuse and end appending. Within 16 of the *first* stop, close
  a **patrol loop** and end appending. Do not simply ignore a near-first point.
- **Detour points:** keep them apart from clicked stops. Only stops count toward the nine-stop limit, get labels
  and arrows, and are drawn; detours are skipped.
- **Minimap markers:**
  - draw the label frame 160 + *n* above-left of the stop;
  - centre the arrow 119 + *k* toward the next stop, or the end dot 159 on the last stop;
  - hide them for charging, fighting, broken or pursuing regiments, and for allied ones.
  
  The request's "161–169 on intermediate stops, 159 on the last" mixes the label with the marker. The last stop
  also has a number.
- **Facing:** there is no end facing to add. Turns and Face point clear the route.

## 8. Open items

- 🟡 None of this was observed in the running game: marker offsets, the loop patrol, the toggle-off on a plain
  click of the selected regiment, and the drag-time end dot.
- 🟡 With several regiments appending at once, one regiment's refusal ending Append mode for all of them.
