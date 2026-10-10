# When a unit is removed, and who hears about it (events 0x16 and 0x0E)

Public implementation report (behaviour only), answering the implementer's BF006 question: crossbows kept shooting
at a Goblin unit after its last model died. Companions, cited rather than repeated: `script_queries.md` §9 (Query 22/23,
what a unit does with the news), `casualty_bookkeeping.md` §2 (removal of a model: killed or removed alive),
`game_rules.md` "Death kinds" (collapse delays) and the event table (0x0E, 0x16, 0x19), `script_shooting.md` §6.1,
`threat_events_nodes.md` Part C §3 (which units count as "in the battle").

## 0. Shared state (read this first)

- **In the battle** = the unit has not been removed. It stays in the battle while it has models, whatever its
  state (hidden, broken, routing, in melee).
- **Removing a unit** is one step. In order:
  1. it **leaves its battle grid** (if the grid is left with only a building pseudo-unit, that leaves too);
  2. **its own queued events are discarded**;
  3. if it is of class Wizard, **all its own spell effects are cancelled**;
  4. **every spell effect aimed at it is cancelled**;
  5. its marker and footprint are removed (it no longer collides or blocks anything);
  6. it is **out of the battle** (searches, node areas and collision passes no longer see it);
  7. it joins the battle's list of removed units (objective bookkeeping, `battle_end_objectives.md`);
  8. unless the removal is **quiet** (§2), event **0x16** is broadcast (§1).
- Nothing in the removal step touches **other** units' current target, threat slot, parent or charge. They learn of it
  only through 0x16 or 0x0E and their scripts (`script_queries.md` §9).

## 1. Q2: the 0x16 broadcast

- **Recipients**: every unit **still in the battle** after step 6, i.e. everyone except the removed unit: both
  armies, allies, hidden units, routing units, building and furniture pseudo-units. Units removed earlier get
  nothing.
- **Content**: event 0x16, **source = the removed unit**, no other parameters.
- **Delivery**: queued like any event, with no condition per recipient. Each recipient handles it at the start of its
  next tick (`unit_script_control.md`, pre-emptive dispatch). Library 152 runs Query 22 on it, as do the player
  handlers that fall through to 152.
- **Order**: the broadcast is the **last** step of the removal (§0), after the grid, spell and footprint cleanups.

## 2. Q1, Q3: when a unit is removed

| how | removed when | 0x16? | other event |
|---|---|---|---|
| **last model killed** (missile, spell, close combat, fanatic, building collapse, …) | at the moment that last model's **death sequence starts**, i.e. after its collapse delay (`game_rules.md` "Death kinds": **1 tick** for missiles, fire, warpfire and "slain outright"; **staggered, up to 72 ticks** for ordinary close-combat deaths). The model is taken out of the unit at that point, and the unit is removed in the same step if it was the last. | **yes** | – |
| `KillAllModels` (library 151 on rolling stock whose team is killed, 13 mission uses) | as above, once the last of the dying models starts its death sequence | yes | – |
| **routing off the table** | 1. When the routing unit's centre crosses out of the battle area it **departs**: event **0x0E** is broadcast once (source = the unit, same recipients as §1). 2. It keeps running until its rear is out too. Then it halts and its figures finish moving, and only then is it removed. | **yes, at the final removal** | **0x0E first, at departure** |
| script **`RemoveFromBattle`** (library 170, 26 mission uses) | at once | **no** (quiet) | – |
| objective G/I steps (army merge, artillery swap, `allied_npc_merge.md`), the end-of-battle clean-up | at once | no (quiet) | – |
| destroyed building pseudo-unit (`building_units.md`) | when its model's wounds reach W | its own building-destroyed broadcast (§ there) | – |

So the engine's "destroyed = 0 models at once" is too early by the collapse delay, and it needs the 0x16 broadcast.
The "A removed at T+25" in `spell_channelled_effects.md` §1.5 is one example of that timing (bolt flight + collapse),
not a fixed constant.

## 3. Q4, Q5: what happens to units that were aiming at it

- **Nothing clears their current target, attack target or charge directly.** A charger keeps heading for the removed
  unit's **last position** until its handler runs Query 22/23 (next tick), which queues **0x19** ("opponent gone") when
  not in melee, or re-targets inside a melee (`script_queries.md` §9). 0x19 is then handled by the unit's scripts
  (`DropTarget` → 163: halt, re-form, restart for library units).
- Only spell effects aimed at the removed unit are cancelled by the removal itself (§0 step 4).
- **No query treats a removed target specially.** `TargetValid`, `FireAtTarget` and the arc and range tests read the
  target's last stored position as for a live unit 🟡 (arc/range not re-checked here). Until the 0x16 is handled, a
  shooter that is reloaded and whose script runs later in the same tick can still order a volley at the empty spot.
  Arrows already posted fly at that last position (`script_shooting.md` §6.1).
- **Quiet removals leave stale targets.** After `RemoveFromBattle` nobody is told: a unit that had the removed unit as
  its current target keeps it, and a fire loop keeps shooting at its last position, until something else changes its
  target. This is what the original does. An engine may deliberately clear such targets (a deviation).

## 4. Test vectors

| case | before | event | after |
|---|---|---|---|
| (a) | crossbows S in fire loop 108 on Goblins X (routing, 1 model); S's arrow kills X's last model in tick k (death kind 2) | tick k+1: the model's death sequence starts | X removed (grid left, effects on X cancelled, footprint gone); **0x16 (source X) queued to every other unit** |
| (a) cont. | same | tick k+2, S's dispatch: 0x16 → Query 22 → target X, not in melee → **0x19** → `DropTarget` → 163 | S halts, re-forms, restarts: no more volleys at X. (Only a volley ordered in tick k+1, after X's removal and before S's dispatch, can still fly at the spot.) |
| (a') | same, but X's last model killed in **close combat** | its collapse delay (up to 72 ticks) | X stays in the battle (and a valid target) until that model's death sequence starts |
| (b) | cavalry C charging X; X's last model dies (death sequence starts) in tick k | tick k | X removed, 0x16 queued; C keeps charging towards X's last position for the rest of tick k (no contact: X's footprint is gone) |
| (b) cont. | same | tick k+1, C's dispatch: Query 22 → C not in melee → 0x19 | charge abandoned by the script (163 for library units) |
| (b') | C in melee with X and with Z; X removed | Query 22 | C re-targets Z, its pairings with X dropped, no 0x19 |
| (c) | mission script runs `RemoveFromBattle` on X; Y's current target is X | at once | X removed **quietly**: no 0x16, no 0x0E. Y keeps X as current target and its loop may keep firing at X's last position |
| (d) | X routs; Y targets X | X's centre leaves the battle area | **0x0E** (source X) to every other unit → Query 23 → Y drops X (0x19) |
| (d) cont. | X keeps running | X's rear leaves the area, X halts, its figures settle | X removed, **0x16** broadcast; Y's Query 22 finds nothing more to do (X is no longer its target) |

## 5. Differences from the engine model

1. Remove a unit when its **last model's death sequence starts** (after the collapse delay), not when its model
   count first reaches 0.
2. On removal, run the cleanup of §0 in order and **broadcast 0x16** (source = the unit) to every unit still in the
   battle, except for quiet removals (`RemoveFromBattle`, objective steps).
3. For routing units, broadcast **0x0E at departure** and **0x16 at the final removal**.
4. Do **not** clear other units' targets silently. Let Query 22/23 do it via 0x19 on their next dispatch.

## 🟡 Open

- Whether the arc and range tests skip a removed target (assumed not).
- How long a routing unit takes between departure and final removal (its figures finishing their walk).
