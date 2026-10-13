# RunAway, routers chased by a charger, EnemyRoutedStatic, Rally and the ways out of the broken state

Public implementation report (batch 14 of the interpreter requests). Behaviour only; states by name, numbers only for
script operands, event codes and gameplay constants. It answers implementer questions from a BF026 replay (a Rock
Lobber crew evading and routing, chased by Ragnar's Wolves): `RunAway` (206 / 0xCE), a charger whose target routs
before contact, `EnemyRoutedStatic` (0x54), and every way a unit stops being broken / routing. Companion report:
[`machine_figure_animation.md`](machine_figure_animation.md) (what the war-machine figure shows).

Read these instead of re-deriving them:
- visibility (`IsVisible`: view cone, three sample rays, scenery, `SightEdge`): `game_rules.md` "Routes, collisions and
  visibility";
- an ordinary point move (route planning, goal push-out, snap from rest, "already there", arrival):
  `movement_formation.md` §3.1 steps 2–5 and §3.8 (`CircleAroundTarget` uses the same move);
- threat slot, `FindThreatNear` / `FindNewThreatNear` / `KeepThreat`, `SetThreatRange`: `threat_events_nodes.md` §0, §1;
- the rout itself (`FleeFromTarget` / `FleeAhead` / `FleeBackward`, `StartRout` effects, rally attempts, pursuit):
  `game_rules.md` "Rally", "Pursuit", "Flight and catching fleeing units", "Scripted target and flight opcodes";
  `movement_formation.md` §3.7;
- `FearWhenCharged` and the brace (script 161): `script_grid_events.md` §2, `game_rules.md` (`StoreEventInfo`);
- `ReacquireEventSource` and event 0x39: `threat_events_nodes.md` §1 (second numbering, 0x3C);
- `ReactToThreat`: `threat_events_nodes.md` §6; `EnemyRouted` (0x53): `game_rules.md` "Pursuit";
- the terror/contact handshake and the rout broadcast 0x0F: `terror_contact_charge.md`;
- the charge run and its ends: `attack_order_flow.md` §1, §5.

**A war-machine crew with an intact machine does not rout.** Library 154 ignores event 0x0C while the unit is still
of class Artillery (`IfClass 32; IfNot …`) and event 0x0D unless the machine is destroyed (`IfMachineDestroyed`). Even if
a flee opcode ran, the rout start is refused for an anchored war machine (`movement_formation.md` §3.7: "nothing moves
but the target is still cleared"). The machine's destruction (event 0x17 in 154: `ClearUnitFlags2 1; SetClass 8`)
lifts the anchor and makes the crew infantry; only then can it rout. An engine that lets an anchored crew rout diverges.

## 0. Shared state first

| State | Meaning here | Who changes it (in this report) |
|---|---|---|
| **broken** | the unit has routed (the morale state) | set only by a rout start (the three flee opcodes). Cleared only by `Rally` and by `InitUnit` (§4) |
| **fleeing movement** | the rout movement mode (the flight mover runs) | set by a rout start (it becomes the *only* movement mode). Cleared by `Rally`, `InitUnit`, and by a pursuit start (§4) |
| **routing footprint** | the unit's map footprint is marked "routing": the collision pass and the contact handler skip it, pursuers cannot engage it, no boundary correction | set by a rout start. Cleared by **any re-form that is actually laid out**, and by every opcode that re-places the footprint (teleports, follow-parent) (§4) |
| **rally attempts enabled** | the periodic C-side rally attempt may run | set by the player's Rally toggle or automatically for independent units at the rout; cleared by `Rally` |
| **current target** (= engaged enemy, one slot) | the unit's opponent | **cleared by every rout start** (all three flee opcodes, even when the rout is refused). While broken, nothing in the shipped scripts sets it again (§2.4) |
| **threat slot** | the enemy the unit is worried about | `FindThreatNear` etc.; `RunAway` reads it, never writes it |
| **braced** | braced against a charge (script 161) | cleared by a rout start and by `Rally` |
| **halted** | the "done / at rest" signal scripts wait for (`WaitUntilUnitFlags 16`) | set by `Rally`, `HaltAndReform`, the end of a charge |
| **condition** | the script condition (`unit_script_control.md`) | written by all three opcodes of this report on every path (§1, §2, §3) |

Key consequence for both questions: **a broken unit has no current target**, so every target-gated reaction
(`EnemyRoutedStatic`, `EnemyRouted`, `ReacquireEventSource`, `TargetGone`, `DropTarget`) is inert for it.

## 1. `RunAway` (206 / 0xCE)

### 1.1 Format

1 word, no operand. Not a rout: it issues one ordinary point move of 256 world units. It never sets broken, fleeing
movement, the routing footprint, rally attempts, a React/bark or any event, and it does not change the target or the
threat slot.

### 1.2 Rule

```
T := the threat slot; if empty, the current target.
T empty -> condition := false; nothing else.

b := bearing from T's regiment position to the unit's regiment position   (i.e. straight away from T)
     = trunc(256 - 256 * atan2(ux - tx, ty - uy) / pi)        in 0..511, 0 = +Y, clockwise
     (unit exactly on T's position: b = 256)

A "look" in direction d: is there ANY unit E such that
     E != the unit, E active, E not hidden, E not withdrawn (🟡 see 1.5),
     E hostile to the unit (one of the two is player-army or allied, the other enemy-army; neutral never),
     trunc(sqrt(dx^2 + dy^2)) between the two regiment positions <= the unit's threat range (SetThreatRange),
     IsVisible(unit -> E) with the unit's facing temporarily turned by d
        (the cone is the normal ±71/512 (strict), doubled while the unit is in melee OR re-forming)?
  Broken / routing enemies count. T itself counts. The facing is restored afterwards (no lasting change).

rear  := look(facing + 256)        -- behind the unit
if not rear:                      heading := b
else if not look(facing + 128):   heading := (b - 96) mod 512     -- the unit's right side is clear
else if not look(facing + 384):   heading := (b + 96) mod 512     -- right blocked, left clear
else:                             condition := false; nothing else (cornered)

goal := (ux + trunc(256 * sin(heading)), uy + trunc(256 * cos(heading)))     (256 world units)
condition := result of an ordinary point move to goal (below)
```

There is no comparison between candidates: the order is fixed (straight away, then b − 67.5°, then b + 67.5°). 96/512
is exactly 67.5°; no angle is compared with 67.5°, so there is no "exactly 67.5°" boundary. The boundaries are the view
cone edge (strict `< 71`, or `< 142` doubled) and the distance (`<= threat range`, inclusive).

Note that the three looks are relative to the unit's **facing**, not to `b`. For a unit facing its threat (the usual
case) "rear" is the escape direction and "right"/"left" are the two sides; for a unit already facing away, "rear" looks
at the threat itself (always found if T is within range and visible), and the side mapping is mirrored (vector 6).

**The move** is the same point move as `CircleAroundTarget` (`movement_formation.md` §3.8 / §3.1 steps 2–5, no
follow-unit mode):
- refused (condition false, nothing changes) while **re-forming**, for an **anchored war machine**, or while **held**
  (Tangling Thorn);
- the waypoint list is cleared and re-planned to the goal (goal push-out, boundary detours as in §3.1 step 3);
- "already there" (no waypoint planned) → the unit halts and re-forms, condition **true**;
- both detour sides hopeless → condition false (🟡 as §3.1: the moving state set during planning is not undone);
- during deployment → condition true, nothing moves;
- otherwise the move starts as §3.1 step 5 (instant 90°/180° snap if it starts from rest, walk animation) and the
  condition is **true**; over the following ticks it is an ordinary walk that arrives and halts at the goal.

It is **immediate**: one call = one order. Repetition comes from the calling script.

### 1.3 States

| Unit state | Result |
|---|---|
| anchored war machine (the state `TestUnitFlags2 9` reads together with held) | move refused → **false**. Library 118 never gets there: it tests that state first |
| held (Tangling Thorn) | refused → false |
| re-forming | refused → false (and its looks used the doubled cone) |
| halted / idle | ordinary move, true |
| braced | no test: the move is issued, true (🟡 whether bracing survives an issued move was not traced; library callers never run while braced) |
| in melee | no test of its own: the looks use the doubled cone, the move order is issued and the condition is true. It does **not** leave the grid. 🟡 What the movement does for a unit in melee was not traced; no shipped caller runs it in melee (147 is entered only after `ReactToThreat` succeeded, which a unit in melee does not do; 118 is a shooter's main-script step) |
| charging / pursuing | no test of its own (🟡 interaction with the charge / pursuit mover not traced; not reached by shipped scripts) |
| broken / fleeing | no test of its own; it would overwrite the waypoints but leaves broken and fleeing movement set (🟡 effect on the flight not traced). Not reachable in shipped scripts: a broken unit runs a rout script, and the wizard path requires `ReactToThreat` (refuses broken) |
| no threat and no target | false, nothing |
| cornered (all three looks find someone) | false, nothing (library 147 then turns to face the target and fights) |

**It is never a rout.** An implementer's placeholder that starts a full rout is wrong in every respect (broken, event
0x0F to the enemy side, target cleared, rally schedule): none of that happens.

### 1.4 Shipped use

3 uses, all in the shared library (present in every mission DLL); **0 mission uses**.

**Library 118** (skirmish evade step, 2 uses), called by library 121 and 122 (skirmish shooter loops) and directly by
13 mission scripts in 6 DLLs (BF022 7, 8; BF030 9, 10; BF032 1, 3; BF033 16, 17; BF035 10, 11, 15; BF036 12, 14).
Library 121 is called by 22 mission scripts, 122 by 7.

```
script 118:
    0  TestUnitFlags2 9          anchored war machine or held?
    2  IfNot
    3    FindThreatNear          fill the threat slot (threat_events_nodes.md §1)
    4    If
    5      RunAway
    6      If                    the move was accepted
    7        PushPC
    8        SetWait 15          every 15 ticks:
   10        FindNewThreatNear
   11        If
   12          RunAway             a new threat: run again (from the new one)
   13        Else
   14          KeepThreat          the same threat still close (d < 5/8 of range) and watching?
   15          If
   16            Wait
   17          Else
   18            GosubScript 125
   20          EndIf
   21        EndIf
   22        TestUnitFlags 16    until halted (the walk arrived)
   24        LoopIfFalse
   25        SetUnitFlags2 4
   27      EndIf
   28    EndIf
   29  EndIf
   30  ReturnGosub
```

**Library 147** (1 use): the wizard's threat reaction. Library 100 (the default script) gives Wizard-class units
interrupt handler 103 (missions BF015 25 and BF017 28 set 103 explicitly); 103 handles event 0x03 with
`IfCasting / IfNot / ReactToThreat / IfSwitchScript 147`. Script 147:
`SendEventToOwnSide 19; RunAway; If (nothing) Else QuarterTurnToTarget; Yield; WaitWhileUnitFlags 8; ... fight
(138/140) while a broken target is in range; Restart`. So a wizard threatened by an enemy steps 256 away; only if
cornered (or the move is refused) does it turn and fight.

### 1.5 Worked example and vectors

Unit U at (0,0), facing 0 (+Y), threat range 240, not re-forming, not in melee, at rest, not anchored or held.
Threat T in the threat slot at (0,100), hostile. Direction values: heading 256 → (0,−256); 160 → (236,−97);
352 → (−236,−97).

1. b = 256 (straight away, −Y). Rear look (cone centred on 256) finds nobody → heading 256 → goal (0,−256). Move
   starts (from rest the bearing to the goal is 256, a 180° turn → instant about-face, re-form queued, per §3.1 step 5);
   condition true.

| # | Before | Instruction | After |
|---|---|---|---|
| 1 | as above, nobody behind | `RunAway` | goal (0,−256), moving, true |
| 2 | as 1, hostile E at (0,−150) (behind, 150 ≤ 240, visible), nobody at the unit's right (+X) | `RunAway` | heading 160 → goal (236,−97), true |
| 3 | as 2, another hostile at (150,0) (right, visible) , left (−X) clear | `RunAway` | heading 352 → goal (−236,−97), true |
| 4 | as 3, a third hostile at (−150,0) | `RunAway` | cornered: false, no move |
| 5 | as 2 but E at (0,−241) (distance 241 > 240) | `RunAway` | E ignored → heading 256, goal (0,−256), true |
| 5b | as 2 but E at (0,−240) | `RunAway` | E counts (inclusive) → heading 160 |
| 5c | as 2 but E broken | `RunAway` | broken enemies count → heading 160 |
| 5d | as 2 but E hidden, or E on U's own side | `RunAway` | E ignored → heading 256 |
| 5e | as 2 but E behind scenery on every sample ray, or across a `SightEdge` | `RunAway` | E not visible → heading 256 |
| 6 | U facing 256 (already facing away), T at (0,100) | `RunAway` | the rear look (centred on 0) sees T itself → right look (centred on 384 = −X): clear → heading b − 96 = 160 → goal (236,−97). (Mirror of a unit facing T.) |
| 7 | threat slot empty, current target T at (100,0) | `RunAway` | target used: b = 384 → goal (−256,0) if nothing behind, true |
| 8 | threat slot and target empty | `RunAway` | false, nothing |
| 9 | U re-forming | `RunAway` | false, nothing (the looks still ran, harmlessly) |
| 10 | U anchored war machine, or held | `RunAway` | false, nothing |
| 11 | U exactly on T's position | `RunAway` | b = 256 |
| 12 | during deployment | `RunAway` | true, nothing moves |

Edge rule for the cone: an enemy whose sample rays all lie at exactly 71/512 from the looked direction is **not**
visible (strict); while U is in melee or re-forming the limit is 142/512.

🟡 "Withdrawn": units in a particular out-of-play state are also excluded (the state library 152 sets with
`SetUnitFlags 256` when an allied NPC changes sides; `game_rules.md` lists the same state for units that walked off).
The same state makes the move itself fail (condition false).

**Correction for `game_rules.md` "Routes, collisions and visibility"**: the view cone is doubled while the looker is in
melee **or re-forming** (the public text says only "in melee"). `game_rules.md`'s one-line summary of `RunAway`
should read: "one 256-unit point move per call, straight away from the threat (or target), or 67.5° to the clear side
when an enemy is visible behind; false when cornered; never a rout".

## 1A. A charging unit whose target routs before contact

### Shared state
- **Routing footprint.** From the start of a rout the router's footprint is marked routing (`game_rules.md` "Pursuit": "A
  pursuer can never re-engage its fugitive"). Every *other* unit's collision pass skips a routing footprint
  entirely: no push, no fear test, no contact record, no contact attack. The contact handler refuses it as well.
- **The router's own pass still runs** while it flees (its position moves every tick). Against an overlapping enemy
  that is not routing, a broken mover only triggers that enemy's **contact attacks on it**. These are forced: the
  attacker need not be charging or pursuing. At most once per segment per attacker, reach 12 / 18 cavalry /
  24 monsters (`game_rules.md` §7.7). There is no push and no engagement. Against an overlapping friend a broken
  mover is not pushed either (pushes between friends need both to be neither broken, pursuing nor in melee).
  Solid scenery still pushes it. A building pushes it unless the mover is charging or in melee. Edge correction
  does not apply to a routing unit (`movement_formation.md` §3.10).
- **A charge run does not follow its target.** It is a straight run with one re-aim at the halfway point and a
  distance budget of `12 × (s_rlmv + 1)` (`attack_order_flow.md` §1 and §5). It ends on contact, on a
  ±45° scenery/friendly push, on a non-target building, when the budget runs out, or on edge correction.

### What the charger does when its target routs
The rout broadcasts **0x0F** (source = router) to the router's enemies (`terror_contact_charge.md` §0.5). At the
charger's next event dispatch the library handler (player handler 101 → 153 case 15, AI 151 case 15; mission handlers
alike: `EnemyRouted; IfSwitchScriptHigh 164`) applies `game_rules.md` "Opcode 0x53 in full":
- the router **is** the charger's current target, the charger is not busy casting and not in melee, and it **is
  charging** → condition true → **164 locked** (high priority) → `LeaveSharedGrid` (false, no grid),
  `ReformToScriptRanks`, `React 3` "Destroy them!", `Query 1` / `IfThreatOutweighsWorth` (may switch to a better
  threat via 0x03), else **`StartPursuit`**. The unit is now **pursuing, no longer charging**. The target stays the
  router. Script 160 is abandoned.
- the router is not its current target (for example a free `ChargeForward` charge with no target, or a charge at
  another unit) → condition false, nothing changes, and the charge run goes on along its line.
- not in melee and **not** charging (still on the approach walk of 105/158/159) → 0x1B to self → 152 turns it into
  0x19 → `DropTarget` → 163 (stop, re-form). The walk ends and the target is dropped.
- busy casting → no reaction.

So a charger never "keeps charging the router" for long. Within one dispatch it becomes a pursuer, or (when the
router was not its target) it finishes its straight run, which by its budget lasts only a few seconds. A charger
that stays "charging, target = router" for 250 ticks does not occur in the original.

### Contact attacks and pushes between charger and router
- **The charger's own pass ignores the router** (routing footprint skipped). A charger or pursuer therefore makes
  no contact attacks, gets no push and makes no engagement from its own movement.
- **The router's pass** makes the charger/pursuer attack it whenever their footprints overlap on the router's
  update (forced, once per segment per attacker, models within `2 × reach`). This is the only source of chase
  damage. With a 35–49 unit gap between the footprints nothing happens.
- **No push either way** between a router and an enemy (or a friend). The router changes facing only through its
  own flee steering, never by being pushed by the chaser.

**Correction to `grid_gap_closing.md` §5.** The row "a charging or pursuing unit's footprint touches a routing unit →
the charger/pursuer attacks" is not a separate case. The attacks come from the router's own collision pass (the
row "a broken unit's footprint, while it moves, touches any enemy unit"), and the attacker need not be charging or
pursuing. The charge/pursuit requirement applies only to contact attacks on a released fanatic and to behaviour 14
`ThreatInReach`.

### Event 0x09 to the target when a charge ends
Every end of a **targeted** charge run (`ChargeTarget`) — budget, scenery or friendly push, non-target building,
edge correction — halts the charger and sends **0x09** ("the charge against you ended", source = charger) to its
current target, which may be a router. A free charge (`ChargeForward`) sends it 🟡 only in a special target state
(normally it has no target anyway). Pursuit is not a charge: pushes and budgets in a pursuit never send 0x09.

### Test vectors (charger and router)
| Before | Step | After |
|---|---|---|
| W charging at L (target L), 40 units apart; L routs | W's next dispatch (0x0F from L) | W pursuing L (164 → `StartPursuit`), not charging; "Destroy them!" |
| W free-charging (`ChargeForward`, no target); L routs | 0x0F | condition false; W's straight run continues |
| W walking (105 approach, not charging) at L; L routs | 0x0F | 0x1B → 0x19 → target dropped → 163 re-form |
| W charging at L, L routing (W did not react, e.g. busy casting); footprints overlap on W's update | W's pass | nothing (L skipped): no push, no attacks, no engagement |
| same overlap on L's update | L's pass | W makes contact attacks on L's models within 2 × 18 (cavalry), once this segment; no push |
| L routing, overlapping friendly F | L's pass | no push |
| L routing, overlapping solid scenery | L's pass | L pushed out by half the overlap + 1 |
| W charging at L (targeted), budget runs out or scenery within ±45° pushes W | W's step | W halted, charge sound off, **0x09 to L**; 160 → 163 |
| W pursuing L, scenery within ±45° pushes W | W's pass | pushed; pursuit goes on; no 0x09 |

## 2. `EnemyRoutedStatic` (0x54) — priority question

### 2.1 Format and rule

1 word, no operand. Used only inside an event handler (it reads the current event). Let S = the source of the current
event, T = the unit's current target (= engaged enemy).

```
T empty                         -> condition := false
S is not T                      -> condition := false
the unit is in melee:
    n := number of enemy units (hostile side, not neutral) that are on the SAME combat grid as the unit
         (S counts if it is still on the grid; 0 if the unit itself has no grid)
    n = 0  -> condition := true
    n > 0  -> unpair the unit's models from S's models (as EnemyRouted does),
              current target := the first such enemy unit on the grid (in the battle's unit order; this may be S
              itself if S is still on the grid), condition := false
the unit is not in melee:
    condition := the unit is braced
```

The condition is **always written** (every path). It does **not** test busy casting (unlike `EnemyRouted` 0x53), does
not test broken, does not clear the owner pairing mode or the attack direction (0x53 does), does not send any event,
and does not change any flag. Side effects only on the "in melee, n > 0" path: the unpairing and the new target.

### 2.2 Shipped use

2 uses, both in library **154** (the war-machine crew layer), reached from library handler **102** (Artillery class,
set by default script 100) and from mission handlers BF004_5 16, BF014 10, BF017 35, BF026 12, BF027 10,
BF034 13/14. 0 mission uses.

```
CaseEvent 15            0x0F  an enemy broke / withdrew   (sent by a rout start to every unit of the router's
  EnemyRoutedStatic                                         enemy side; source = the router)
  If
    LeaveSharedGrid
    Rally
  EndIf
CaseEvent 9             0x09  "the charge against you ended" (source = the charger)
  EnemyRoutedStatic
  If
    LeaveSharedGrid
    Rally
  EndIf
```

`Rally` here is used as "stand down and re-form": the crew stays put (war machines never pursue,
`game_rules.md` "Pursuit"), leaves the grid and re-forms.

### 2.3 Event 0x09 in this context

Event 0x09 is sent when a **charge movement ends without an engagement**: the charger hits solid scenery or a friendly
unit within its front ±45° (push-apart), meets the battle boundary correction, hits a building, or the charge movement
runs out (at a periodic re-plan the charge route has nowhere further to go; 🟡 exact re-plan rule not traced). The charger stops charging and halts, and **its target** receives 0x09 with the charger as source. It is not
sent for a "free" charge (a charge order with no target, `ChargeForward`) unless the unit it would go to is braced.
It is not sent when the charge ends by engaging (that path produces 0x08 / 0x0A instead).

The ending of the charger's charge touches **nothing else on the target**: no flag, no rout state, no target change.
The only effect on the target is this event, i.e. whatever the target's own handler does with it.

So for the crew:
- **intact, braced crew charged by S, S's charge ends short at scenery** → T = S (the brace query made the charger the
  target), not in melee, braced → **true** → `LeaveSharedGrid` (no grid: nothing) → `Rally` → the crew un-braces,
  halts and re-forms. This is the intended "the threat has gone, stand down".
- **crew in melee with another unit, T = S** (rare) → n counts the crew's grid opponents → n > 0 → target := first
  enemy on the grid, false.
- **broken (routing) crew**: its target was cleared when it routed (every flee opcode clears it; §0) and nothing sets
  it while broken → **false at the first test**. Even if it had the target, it is neither in melee (the rout left the
  grid) nor braced (the rout cleared bracing) → false. **A routing crew never reaches `Rally` through 0x09 or 0x0F.**

### 2.4 Why a broken unit has no target (verification of "nothing sets it")

Target writers and their gates: `FearWhenCharged` (refuses a broken unit), `TakeEventTarget` (refuses broken),
`ReactToThreat` (refuses broken), the brace query in script 161 (161 is entered only when not broken), the contact-fear
block of the collision pass (the mover must not be broken), `SwitchOpponentInGrid` / `EnemyRouted` / this opcode
(in-melee paths only; a routing unit has left the grid), `ReacquireEventSource` (only queues an event; its 0x04 is then
refused by `TakeEventTarget`; artillery handler 102 ignores 0x04 anyway). 🟡 Mission-only target opcodes were not
audited one by one; none is known to run on a broken crew.

### 2.5 Test vectors

C = crew (Artillery, interrupt handler 102 → 154). W = an enemy cavalry unit.

| # | Before | Event / instruction | After |
|---|---|---|---|
| 1 | C intact, braced, target W, not in melee | 0x09 from W → `EnemyRoutedStatic` | true → `LeaveSharedGrid`, `Rally`: C not braced, halted, re-formed |
| 2 | C intact, not braced, target W, not in melee | 0x09 from W | false; nothing |
| 3 | C broken, fleeing, target none (the normal routing crew) | 0x09 from W | **false**; still broken, fleeing, routing footprint; no Rally |
| 4 | C broken, target none | 0x0F from any router | false |
| 5 | C in melee with W only; W routs (W left the grid) | 0x0F from W | n = 0 → true → leaves grid, `Rally` |
| 6 | C in melee with W and X (both on C's grid); W routs | 0x0F from W | n = 1 → models unpaired from W, target := X, false |
| 7 | C in melee, target X; W (not its target) routs | 0x0F from W | S ≠ T → false; nothing |
| 8 | C not in melee, target W, not braced; W routs | 0x0F from W | false |
| 9 | C in melee with target W, W's charge ended without engagement and W still on C's grid (🟡 rare) | 0x09 from W | n ≥ 1 (W counts) → unpaired from W, target := first enemy on the grid (may be W), false |
| 10 | C busy casting (not applicable to crews; the opcode does not test it) | any | as the other rows |

**Engine note**: a stub that leaves the condition true makes library 154 run `Rally` on a fleeing crew, which clears
broken and fleeing movement and the routing footprint (§3). The original never does that on these events.

## 3. `Rally` (0x5A) — its own gates

1 word. **It has no gate**: it does not test broken, `CantRally`, casualties, enemies nearby or anything else. In order:

1. clears **charging, broken, pursuing, braced**, the one-tick contact latch, and the rout's own companion state;
   sets **halted**, the "re-form by walking" mode and a collision re-check;
2. clears the movement modes **charge, free charge, fleeing, pursuit**, and **rally attempts enabled**;
3. halt and re-form (now permitted, since broken/pursuing were just cleared): waypoints dropped, keep-firing/casting
   script flags cleared;
4. asks for the script rank count through the ranks check: refused only if the unit is **held** (fleeing and charging
   were just cleared) → the opcode **yields and repeats itself next tick** (steps 1–3 run again each time);
5. accepted → the re-form is laid out at once (skipped if the unit still has a grid or has no models: then nothing is
   re-placed), which **clears the routing footprint**; the unit's looping charge sound is stopped. Next instruction.

Condition: not written. `CantRally` is honoured only by the **rally attempt** (C side), never by `Rally`. So a
`CantRally` unit does stop routing if any script path reaches `Rally` (§4 rows 6, 7).

| Before | Instruction | After |
|---|---|---|
| broken, fleeing, routing footprint, `CantRally`, no grid | `Rally` | not broken, not fleeing, halted, re-forming at script ranks, footprint no longer routing |
| held, broken | `Rally` | broken etc. cleared, but the ranks request is refused → yields, same instruction next tick, until released |
| pursuing | `Rally` | pursuit ended, halted, re-forming |

## 4. Every way out of the broken / routing state

Columns: B = broken, F = fleeing movement, R = routing footprint, P = pursuing. "CR?" = can a `CantRally` unit reach it.

| # | Way | Trigger | Clears | CR? |
|---|---|---|---|---|
| 1 | **Rally attempt succeeds** (C side, `game_rules.md` "Rally") | scheduled segment, rally attempts enabled (player Rally toggle, or independent unit), no enemy within 160, not `CantRally`, casualties < 3 × size, Leadership test passed | sends event 0x10 → library 152 case 16: `React 17; SwitchScript 163` → `Rally` → B, F, R, P | **no** (`CantRally` refuses the attempt) |
| 2 | `Rally` via script 163 from other events | 0x10 from pursuit restraint / pursuit end (pursuers only); 0x39 (via `ReacquireEventSource 1`, needs target); 0x19 after `DropTarget` (refuses broken); 0x30 (`TestUnitFlags 0xa000; IfNotSwitchScript 163`: skipped while broken or pursuing); 0x18 via `TargetGone` (needs target); library 106/160 and BF001 script 10 after a charge (not broken) | B, F, R, P | no (all gated by "has a target" or "not broken") |
| 3 | `Rally` in library 154 on 0x0F / 0x09 (§2) | `EnemyRoutedStatic` true | B, F, R, P | no (a broken unit has no target) |
| 4 | **Madness ends** (`spell_lasting_effects.md` §1.3) | the effect ends / is dispelled / its caster removed → event 0x32 → library 152 case 50 → script 168 → `GotoScript 163` → `Rally` | B, F, R, P | **yes** 🟡 — no gate on this path; Madness may be cast on a broken unit (§0.1 there) and the rout scripts do not lock script switches. Static script reading, not runtime-verified |
| 5 | Leaving the battle, library 170 | objective G (allied NPC) battles: event 0x36 → library 152 `IfSwitchScriptHigh 170` (no broken gate); BF015 35 / BF017 36 `SwitchScript 170` | `Rally`, teleport to node 24, then removed from battle | yes (it leaves the battle) |
| 6 | `InitUnit` (0x00) | a script switch to a script that starts with `InitUnit` (library 100; 370 mission uses, normally the first instruction of a mission script) | B, F, also in melee, charging, halted→set, target, threat, event queue, stack; the re-form it requests is cancelled by its own model snap, so **R is NOT cleared** 🟡 | 🟡 only if a mission handler switches a broken unit to such a script (not audited) |
| 7 | Pursuit start (`StartPursuit`, script 164) | replaces the movement mode with pursuit | F only (B stays) | not reachable while broken (164 is entered only through `EnemyRouted`, which needs a target) |
| 8 | Any **laid-out re-form** | `ReformToScriptRanks`, rank orders, `ReformBlock`, `SetRanks`, the halt-and-reform, snap turns, the formation update's pending re-form | R only | no: every one of them is refused while in fleeing movement (and halt-and-reform while broken), so it can only happen after `Rally`/`InitUnit` |
| 9 | Footprint re-placement | `TeleportToNode` (0x49), the other node teleport (0x4A), `FollowParent` (0xD4), grid-join placement 🟡 | R only (B, F stay) 🟡 | if a script does it to a broken unit |
| 10 | Leaving the table | flight carries the centre outside the battle area → 0x0E, then removal alive | everything (unit gone) | yes |
| 11 | Destroyed | last model dies (contact attacks during the chase, missiles, spells) | everything | yes |
| 12 | `RemoveFromBattle` (0x8C) / `KillAllModels` | script | everything | if a script does it |

Not a way out (checked):
- **The charger's charge ending** (at scenery, a friend, the edge, a building): changes only the charger; its target
  gets event 0x09 and nothing else (§2.3). Through library 154 that event cannot rally a routing crew.
- **Boundary (edge) correction**: skips routing units entirely; on a charger it only ends the charge (0x09 as above).
- **Halt / `HaltAndReform`** (player halt, scripts, Tangling Thorn's entangle): refused for broken or pursuing units.
- **Player orders**: refused for broken units, except the Rally toggle, which only enables rally attempts (row 1).
- **`ClearUnitFlags` in shipped scripts**: operands 0x1104098, 0x30000000, 0x4000000, 0x80000, 8 — none includes
  broken. `ClearUnitFlags2` operands 1, 2, 4, 2048: none is a rout state.
- **Spells other than Madness**: no spell clears broken (Tangling Thorn halts only non-broken units; a held routing unit
  keeps its rout state; transports keep the unit's states).
- **Event 0x0C / 0x0D to a routing unit**: the handlers ignore an already broken unit (`RoutAllowed`).

## 5. The implementer's observation, explained

(In the original the crew could not have routed while anchored to its intact machine, §0; the explanation below
holds for any routing crew.) A `CantRally` rock lobber crew routing, Ragnar's Wolves charging it, the Wolves' charge ending at solid scenery, the crew
stops routing on the next tick: in the original the crew receives event 0x09 (source = Wolves), library 154 runs
`EnemyRoutedStatic`, which is **false** (the crew has no target since its rout; and it is neither in melee nor braced),
so `LeaveSharedGrid; Rally` is skipped. The crew keeps fleeing. The engine's stub that left the condition true was the
whole cause; no other part of the charge-end sequence touches the target.

## 6. Uncertainties

- 🟡 `RunAway` on a unit in melee, charging, pursuing, braced or broken: the opcode has no gate and the order is issued;
  the movement consequences were not traced (no shipped caller reaches these states).
- 🟡 the "withdrawn" exclusion state (§1.5).
- 🟡 Madness on a routing unit leading to `Rally` (§4 row 4): a static script path, not observed.
- 🟡 `InitUnit` reached by a broken unit (§4 row 6), and its leaving the routing footprint in place.
- 🟡 §2.5 row 9 (0x09 while in melee with the charger still on the grid).

## Corrections to existing public notes

- `game_rules.md` "Routes, collisions and visibility": the view cone is doubled in melee **or while re-forming**; the
  `RunAway` summary is corrected (one 256-unit point move, never a rout).
- `game_rules.md` "Pursuit": `EnemyRoutedStatic` is summarised and linked here.
- `grid_gap_closing.md` §5: the "charging or pursuing unit touches a routing unit" row is folded into the router's own
  pass (§1A).
