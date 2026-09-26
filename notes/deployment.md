# Pre-battle regiment deployment

Behavioural hand-off, updated 2026-09-26. This report describes deployment rules and
acceptance scenarios for an independent implementation. It contains no private research
locations or original program listings. No new original-game play session was performed
for this update; interaction details still requiring observation are explicitly listed below.

## Readiness assessment

The previous report was **not sufficient for a full implementation**. In particular, its
proposed undeployed roster and node-defined placement polygon were based on incorrect
assumptions. The following are now established: default starting-slot allocation, the
separate deployment boundary, single-regiment dragging and rotation, direct formation
controls, and the start-battle transition.

These rules support implementing the deployment feature with documented limits. Exact
original interaction and collision parity still needs the checks in §7. A simplified
list-and-click placement screen would be a product choice, not established original behaviour.

## 1. Mission entry and default positions

`DeployTroops:` in `[MISSIONINFO]` requests a deployment phase before normal battle play.
Without it, the mission enters normal battle play directly. **Default player starting-slot
allocation still applies without this keyword.** It is separate from the optional UI phase.

Player regiments already have starting positions. There is no requirement to place every
regiment manually, and no established separate inventory of unplaced regiments.
`DeployTroops:` itself does not mean “hide the entire player's army.” Preserve the individual
`hidden:` visibility rule and normal spotting behaviour; do not turn that field into a
not-yet-deployed state. During deployment, changing or selecting a regiment can refresh its
visibility relative to the enemy. Enemy armies keep their file-defined positions; allied
and neutral armies do not receive the player's default slot allocation.

### 1.1 Starting-slot allocation

The candidate positions are nodes with both `ns_active` and `ns_startpos`, ordered by their
appearance in `[NODES]`. Their `x`, `y`, and `dir` supply regiment position and facing.
The node's `radius` and `id` are not placement-zone geometry or regiment identity keys.

For a normal army section containing **U player regiments** and **N candidate start nodes**,
where N >= U, the army occupies the **last U candidates**, in army-file order. Thus a
smaller marching army starts farther back along the authored line of slots. Each occupied
slot is reserved once during loading. Existing node reservations matter if more than one
army section supplies player regiments.

More precisely, the declared unit count of the army section determines how many candidates
are skipped: N minus that count. That many *currently unreserved* candidates are skipped
for each player regiment, and the next unreserved candidate supplies its position. The
usual section contains only player units; do not silently replace its declared count with
the total units in the whole battle, or with a count pooled from several army files.
If no candidate can be selected, retain that regiment's file-defined position and facing;
do not invent a replacement slot. This includes too few candidate nodes.

`NS_END` does **not** select a special set of slots for this allocation. A start node with
that token remains eligible; one without it is also eligible. The old correlation between
`NS_END` count and authored army size was not a sufficient rule.

Marching order affects **which regiment receives which default slot**: the troop-selection
screen writes its ordered list to `MARCH.MRC`, and army-file order is used here. It does not
force the player to rearrange regiments in that order during deployment.

### 1.2 Examples

Node indices here are zero-based positions in the battle's full node list. Coordinates are
small interoperability examples; load the actual nodes from the user's battle files.

| Battle / army size | Candidate node indices | Assigned node indices in army order |
|---|---|---|
| BF001 / 3 | 0, 1, 2, 3, 4 | 2, 3, 4 |
| BF001 / 2 | 0, 1, 2, 3, 4 | 3, 4 |
| BF001 / 5 | 0, 1, 2, 3, 4 | 0, 1, 2, 3, 4 |
| BF003 / 2 | 3, 4, 9, 10, 12 | 10, 12 |
| BF010 / 4 | 0, 1, 2, 3, 4 | 1, 2, 3, 4 |

For BF001's three-regiment example the initial positions/facings are respectively
(240, 209, 64), (160, 144, 64), and (80, 82, 64). These supersede the player army's own
`x`/`y`/`dir` values, including holding coordinates outside the playable field.

## 2. Deployment zone

Read `[BOUNDARIES]` entries with `bnd_ACTIVE` and `bnd_DEPLOYMENT` status. The boundary
name is descriptive, not a lookup key: shipped names include `DeploymentArea`, `Deployment`,
and other variants. The deployment boundary category uses mask `0x100` in the boundary
status vocabulary. Use its `AddLine` geometry and existing boundary semantics, including
inverted-region status if present. Do not infer the zone from start nodes or their radii.

A survey of the 44 campaign `BF*.BTS` files found 31 with `DeployTroops:`. Each of those
31 has exactly one deployment-tagged boundary. Multiple disjoint deployment regions and
missing-zone behaviour are therefore additional compatibility cases, not covered by this
shipped-data sample.

Translation is constrained using the **regiment's formation centre**, not by requiring
all soldiers, all four formation-box corners, or the front-rank anchor to lie inside the
zone. For a block, the front-rank centre and formation centre differ by half its depth;
see `game_rules.md`, “Formations.” Facing and rank changes must retain
that distinction.

Dragging beyond the active zone clips the proposed centre to the nearest point on its
boundary segments. Equally near segments favour the first in boundary order; projected
coordinates truncate toward zero to whole world units. The proposed centre approaches its drag target in successive half-distance
steps, with whole-world-unit truncation. This is responsive placement, not marching at the
regiment's movement rate. Normal collision adjustment also participates, so **do not assume
that regiments may freely overlap**, or that the clipped point is the final centre after
all collision adjustments. Collision correction follows zone clipping, with up to ten
correction passes and **no final deployment-zone clamp**. A collision may therefore push
the centre outside the zone, and the next placement update may pull it back before another
collision correction. This does not guarantee complete separation after a difficult overlap.
Exact visible outcomes and point-on-edge inclusion remain in §7.

The remembered region is shared across selections and drags for the deployment phase;
releasing or selecting another regiment does not reset it. A target inside a different
active deployment region switches it; the first matching region in boundary order wins
when regions overlap. A target outside every region uses the remembered region. With no
remembered region, translation waits until a target enters one. Missing deployment zones
therefore prevent direct translation, though facing and collision correction can still act.

**First acquisition and region switching have a placement quirk.** The proposed centre is
first moved to the target, then receives the half-distance step measured from its previous
centre, before clipping. For example, with old centre (10, 10) and target (30, 30), ordinary
movement within an already remembered region proposes (20, 20); acquiring/switching the
region proposes (40, 40), then clips if needed. These are arithmetic examples, not recorded
play-session measurements. Preserve this distinction when checking custom multi-region data.

A drag update with less than two world units of difference on **both** axes makes no
placement or facing change: both half-distance steps truncate to zero.

## 3. Player interaction

- A map click selects one regiment during deployment. Shift does not enable the normal
  battle multi-selection behaviour here. Only the player's own regiment can be dragged;
  inspecting an enemy does not make it deployable.
- Pressing on an eligible player regiment and holding the left mouse button enables
  dragging. The grab offset is preserved rather than immediately snapping its anchor to
  the cursor. Releasing the button ends the drag and clears the transient drag target.
- Holding **Ctrl while dragging** changes facing toward the drag target instead of
  translating the formation centre. Translation resumes without Ctrl. Facing uses the
  ordinary 512-direction convention. A block's front-rank anchor swings around its
  stationary formation centre; centre rotation does not hold the front anchor fixed.
- A regiment may be adjusted repeatedly and in any order before starting battle. Releasing
  a drag retains the resulting placement; it is not an undo. A separate undo/history
  control has not been established.
- The deployment **Move** button and map orders also allow move/waypoint planning. This is
  distinct from direct dragging. Waypoints can be prepared for execution after battle starts;
  do not interpret every Move-button click as a teleport into the placement zone.
  Choose Move, then Ctrl-click successive destinations to append waypoints; an ordinary
  click replaces the route/ends append targeting. Ctrl here is route planning, while Ctrl
  during a direct drag is rotation. Shift is not the waypoint modifier. The manual route
  limit is nine destinations, subject to the ordinary near-point and detour limits.
  Selecting a regiment by direct map press starts a halt/re-form and clears its previous
  route; previous/next HUD selection does not have that same route-clearing side effect.

The minimap shares map selection/order handling with the main view, and shows deployment
boundary markers. Deployment-specific icons and layout are in §8; the shared HUD layout is
in `game_rules.md`, “Battle HUD layout.” Both views support left dragging, Ctrl rotation and release through the same placement
rules. The main view picks projected ground coordinates; the minimap converts its map pixels
to world coordinates, so their coordinate precision differs. Leaving the minimap during a
held drag ends it. Right-drag operates the camera in the main view and pans the minimap;
neither gesture restores the previous placement. Esc has no deployment undo action.

## 4. Formation and command controls

| Regiment class | Deployment controls |
|---|---|
| Infantry, cavalry, archers | Ranks up, Move, Independent, Ranks down |
| Wizard, monster | Move, Independent |
| Artillery | Independent; no Move or rank buttons |

Ranks up/down changes the selected formation directly by one rank, subject to the normal
rank limits in `game_rules.md`, “Formations.” It does not queue a normal
battle rank order. Re-forming updates the model layout immediately for deployment.
Independent toggles the selected regiment's setting directly and carries into battle.

**Artillery:** direct left-drag and Ctrl-drag are allowed for an otherwise eligible own
regiment, and placement updates the weapon and crew layout. The absence of a Move button
restricts marching orders, not direct deployment rearrangement. Furniture/rolling-stock
classes likewise do not gain a command panel, but lack of panel buttons is not a drag
exclusion; ordinary ownership, visibility and picking eligibility still apply. On-screen
picking and model appearance for these unusual classes remain useful confirmation checks.

### 4.1 Available and unavailable regiment actions

Availability here is for ordinary player controls during deployment. A button absent from
this panel should not be rendered as a usable battle command just because the regiment
can normally perform it. Deployment also restricts ordinary order execution to move and
waypoint orders; direct dragging, rank changes and Independent are separate actions.

| Action | Infantry / cavalry / archers | Wizard / monster | Artillery | Deployment effect |
|---|---|---|---|---|
| Select own regiment | Available | Available | Available | One selected regiment; previous/next buttons also select and centre the camera. |
| Drag with left button held | Available for eligible own regiments | Same | Available for eligible own regiments | Rearrange within deployment constraints; release retains placement. |
| Ctrl while dragging | Available | Available | Available for eligible own regiments | Rotate toward the drag target instead of translating the centre. |
| Move button | Available | Available | Unavailable | Target a move; prepare a route for battle start. |
| Add waypoints | Available through move targeting | Available through move targeting | No Move button | Ctrl-click appends destinations during Move targeting; see §3. |
| Ranks up / down | Available | Unavailable | Unavailable | Immediate one-rank change, clamped to normal limits. |
| Independent | Available | Available | Available | Immediate toggle retained into battle. |
| Attack / attack sub-panel | Unavailable | Unavailable | Unavailable | No pre-battle attack command. |
| Charge | Unavailable | Unavailable | Unavailable | No pre-battle charge command. |
| Fire, including special firing action | Unavailable | Unavailable | Unavailable | No pre-battle firing command. |
| Magic / spell casting | Unavailable | Unavailable | Unavailable | No pre-battle spell command. |
| Items / special-item panel | Unavailable | Unavailable | Unavailable | Not offered in the deployment panel. |
| Halt command | Unavailable | Unavailable | Unavailable | Starting a drag or Move targeting may halt/re-form as part of that action; no separate Halt button. |
| Turn left / right, about-face, face-point button | Unavailable | Unavailable | Unavailable | Use Ctrl-drag to set facing; do not expose the battle facing sub-panel. |
| Normal rank/facing sub-panels | Unavailable | Unavailable | Unavailable | Block regiments have direct rank buttons instead. |
| Withdraw | Unavailable | Unavailable | Unavailable | No pre-battle withdrawal/rout order. |
| Rally | Unavailable | Unavailable | Unavailable | No pre-battle rally order. |
| Fight harder | Unavailable | Unavailable | Unavailable | No pre-battle combat-effort command. |
| Multi-selection with Shift | Unavailable | Unavailable | Unavailable | Deployment selection stays singular. |
| Undo previous placements | Unavailable | Unavailable | Unavailable | Release, right-click and Esc do not restore an earlier placement. |

The rank-display decoration in the centre slot is **not an action**. Selecting an enemy
for inspection does not grant any deployment control over it. Classes outside these panel
categories, such as furniture and rolling stock, have no established deployment button set;
do not give them the infantry controls by default.

**Keyboard access:** the battle and main-view key handling and the normal application
accelerator table provide no ordinary unit-command shortcuts that bypass these panel
restrictions. Ctrl participates in drag rotation; Shift and other map modifiers are handled
by their interaction context. The application's unrelated accelerator is not a deployment
command. Enter/Space/Esc provide no deployment equivalents of Start, Rotate or Undo.

**Screen controls:** camera rotation/zoom, minimap display tabs and previous/next regiment
selection remain separate from regiment orders. Start battle is available in place of the
normal pause/resume button. The normal in-battle menu button is hidden during deployment.
Options/book controls are shared screen functions, not evidence that spells or items may be
used on the field before battle starts. A right-button gesture in the main view operates the
camera; it must not be described as an established placement undo.

### 4.2 Formation layout during deployment

The battle has three player-relevant phases: no battle, deployment, and normal battle play.
Pausing is independent of those phases. A mission initially loads with normal-play formation
rules, then enters deployment if requested, and returns to normal play when the player starts.

War-machine crew slots take the **nearest** available crew model when a layout is generated
during deployment. In normal battle play they take the **farthest** available model instead.
The machine itself has its reserved centre slot while present. Blocks, monsters and wagons
do not switch their model-allocation rule at the phase transition. Do not assume the initial
loading layout was already generated under deployment rules, or regenerate every formation
merely because the phase changes. See [game_rules.md](game_rules.md) for the
ordinary formation geometry and model catch-up rules.

**Formation example**: the BF001 deployment screenshot shows exactly this layout (16 infantry in 3 ranks as 6, 5, 5,
  the two rear ranks offset by half a spacing; 12 crossbows as 4 × 3). In both units the model spacing is about
  1.43 times the on-screen sprite width, so one troop sprite pixel covers about **0.45 world units** (measured,
  not traced; R68). `whshr/formation.py` implements the block layout for both battle viewers.

## 5. Deployment time and starting battle

The flag button starts battle explicitly and replaces the deployment controls with their
battle equivalents. Existing positions, facings, ranks, and Independent settings carry
forward. Visibility is refreshed for the opposing armies at the transition, so an army's
initial `hidden:` value is not a promise that it remains hidden after being placed near an
enemy. Routes prepared before battle may begin once their unit passes `WaitForBattleStart`.

There is no “all regiments must be manually placed” gate on the start action, and no
established deployment countdown or automatic start. Keeping the defaults and immediately
starting is valid. The start action does not offer a return to deployment.

Deployment is a distinct active phase, **not a global pause of every update**. Placement,
formation/model updates and unit scripts still receive updates. Scripts using
`WaitForBattleStart` wait there and resume after confirmation. Do not advance normal battle
rounds/objective scheduling as if the battle had started, but also do not freeze the entire
interpreter: mission-specific setup before that wait still matters. Script wait timers reached **before** `WaitForBattleStart` consume deployment updates;
waits placed after it do not begin until the script passes that wait. Periodic AI decisions
are suppressed during deployment, although their countdowns can advance. Ordinary combat
clock/round progression remains stopped. Waiting at the start barrier gates ordinary unit
movement; deployment is not a blanket rule suppressing all script-driven activity. Test
mission-specific activation against these distinctions, rather than assuming all enemy
setup and delayed activity starts on the flag click.

## 6. Independent acceptance scenarios

These are proposed implementation tests, not new observations of the running original.

1. With five ordered start nodes and three player regiments, allocate the last three nodes
   in army order. Reorder the marching army and verify the regiment-to-slot assignments swap.
2. Repeat with two and five regiments. Remove all `NS_END` tokens and verify the result is
   unchanged. Interleave ordinary waypoint nodes and verify they are not candidates.
3. Change `radius`/`id` without changing start status/position/facing: allocation is unchanged.
   Give a regiment an outside-field army coordinate and verify an available start slot wins.
4. Remove `DeployTroops:`: retain default slot allocation, skip the placement UI phase.
   Supply fewer start slots than the army count: preserve the file-defined positions.
5. Rename a deployment boundary while keeping its status/geometry: placement constraints
   remain unchanged. Change start-node geometry without changing boundaries: the allowed
   zone remains unchanged.
6. Drag a player regiment repeatedly, release, select another, and return. Its placement
   persists. Shift-selection still leaves only one selected regiment. Enemy selection
   cannot reposition the enemy.
7. Hold Ctrl during a drag: facing changes while translation of the formation centre stops.
   Release Ctrl: constrained translation resumes. Rank changes respect the published limits.
8. Try every unavailable action in §4.1 for each class: no attack, shot, spell, charge or
   normal facing/rank order is executed; missing buttons stay absent. Then start immediately
   without dragging any regiment: battle begins at the default positions.
   Repeat after changing facing, ranks, and Independent: those settings survive the transition.
9. A unit waiting for battle start remains at that wait while deployment continues, then
   resumes after the flag action. A prepared waypoint route is retained and starts afterward.

## 7. Remaining checks for full original parity

Tracked in [research issue #5](https://github.com/pgrudzien12/openHornedRat/issues/5);
implementation is tracked in [#6](https://github.com/pgrudzien12/openHornedRat/issues/6).

The follow-up resolved the rule questions about collision order, artillery dragging,
main/minimap input, Ctrl-waypoint gestures, cancellation, timer gates and custom-region
selection. These findings were not newly observed in a running original-game session.
The remaining work is confirmation of visible outcomes and exact coordinate edge cases:

| Check | Expected rule / next observation |
|---|---|
| Collision at edges and corners | Compare centre and soldiers for overlapping, deep and rotated formations. Correction follows clipping and can move the centre outside; no final zone clamp. |
| Exact on-edge arithmetic | Confirm horizontal/sloping edge and vertex inclusion, truncated projected coordinates, equal-distance first-segment choice and the one-unit dead zone. |
| Artillery and unusual classes | Confirm picking and visible weapon/crew movement during left/Ctrl drag; test monsters and controllable wagons without granting them extra panel actions. |
| Main view versus minimap | Confirm both drag paths, front-anchor swing, Ctrl-click route planning, nine-destination limit, route clearing on direct selection, retention across Start and leaving-minimap release. |
| Cancellation and unavailable commands | Confirm right-drag camera/pan and Esc do not undo, and no ordinary keyboard shortcut bypasses §4.1. |
| Multiple/missing regions and outside starts | Confirm shared remembered region, initial-acquisition/switch overshoot, boundary-order selection and missing-zone translation refusal using custom data. |
| Mission setup timing | Confirm a wait before the start barrier consumes deployment time, a wait after it starts later, periodic AI decisions remain suppressed, and combat time starts only on Start. |

Default placement, marching-order effects and boundary identification are ready for
implementation. These remaining checks prevent claiming a fully verified reproduction of
the original's interaction and edge cases. Research output here changes documentation only;
engine implementation must be independently written from the public rules.

## 8. Deployment HUD reference

The shared 640×480 screen layout and asset names remain in
[game_rules.md, “Battle HUD layout”](game_rules.md).
The following differences belong to deployment:

- The fixed button at command-panel (11, 118), size 52×52, uses `ICONS` frames **48/49**
  (start-battle flag), replacing the normal pause/resume frames 46/47. After start the flag
  disappears and the pause/resume button becomes available.
- A selected player regiment uses the deployment panel variant. Rank buttons change the
  formation directly, Move begins move/order targeting, and Independent toggles directly.
- Minimap marker-display mode 3 shows friendly banners plus dots during deployment; in
  normal battle play it shows their dots. The icon-to-mode correspondence remains uncertain
  as described in the shared HUD reference.
- Before waypoint paths and regiment markers, the minimap draws deployment-boundary
  markers using `ICONS` frame **160**, size **8×8**. These markers describe the boundary,
  not the start-node positions or an inventory of unplaced regiments.

Command-panel slots are relative to its sub-window at screen (492, 304): TL (7, 11),
TR (83, 11), BR (83, 109), BL (7, 109), centre (45, 60). Buttons are 60×60.

| Class | TL | TR | BR | BL | Centre |
|---|---|---|---|---|---|
| Infantry, cavalry, archers | Ranks up (20/21) | Move (0/1) | Independent (52/53) | Ranks down (22/23) | Decoration (24) |
| Wizard, monster | – | Move (0/1) | Independent (52/53) | – | – |
| Artillery | – | – | Independent (52/53) | – | – |

The frame pair gives raised/pressed icons. The centre decoration has no command.
Pre-battle zone markers and this panel variant require the deployment phase in the engine;
ordinary battle HUD support alone does not provide them.
