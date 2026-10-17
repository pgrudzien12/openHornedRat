# Battle tick order: the engine's phased tick versus the original's per-unit tick

Decision record (2026-10-17). The engine **deliberately keeps its own phased battle tick** instead of the original's
per-unit interleaved tick. Where the difference shows up in play, it is compensated by small local rules, each
marked `PROVISIONAL` in the code and listed in §3. This is a design decision, not an open task. There is no
tracking issue, and none should be opened unless §4's condition is met.

Sources: `battle_tick_order.md` (the original's tick, behaviour only), `terror_contact_charge.md` §8 (the flight
event order), issue #343.

---

## 1. The two orders

**Original** (`battle_tick_order.md`): one 100 ms tick visits the units in table order. Each unit's step is
complete before the next unit starts:

- event handling and the script;
- formation (re-forming, grid pairing);
- one movement step, or, in melee, its close-combat round on its own segment tick;
- its own collision pass;
- its models.

Only missiles, spell effects and housekeeping run after the loop, plus a break-test pre-pass on segment-change ticks
before it.

**Engine** (`Battle.tick` in `whshr/engine.py`): each stage runs for every unit before the next stage starts:

1. every unit's script (with event handling);
2. every unit's movement;
3. push-apart for every unit;
4. the collision pass for every unit;
5. on segment ticks, melee rounds, contact attacks and rally for every fight;
6. shooting, spell effects, removals.

## 2. What the difference means

Within one tick, with unit A before unit B in the order:

| Interaction | Original | Engine |
|---|---|---|
| A's collision-pass event to B | B handles it in the same tick, in its own step | B's script has already run: B handles it next tick, **under** whatever A's next script step sends |
| B's events to A | next tick | next tick |
| Positions seen by B's script and collision pass | A's new position | A's old position (scripts), everyone's new position (collision passes) |
| Grid cells around one enemy | claimed unit by unit | claimed during the shared contact stage |
| Melee rounds in a segment | per unit, in table order, break tests first | per fight, in the shared melee stage |

All differences stay within one tick (0.1 s). Most of them cannot be seen. They become visible only where the
**order of events in one unit's queue** decides the outcome, because events are handled most recent first.

**Why we keep the phased tick.** The battles look and feel right. Rewriting the core loop would change the timing
of most battle behaviour and of many tests, for little gain the player can see. Visible consequences are rare
(§3 has one so far) and can each be fixed locally.

## 3. Local compensation rules

Each rule restores the original's **outcome** for a case where our order produces a different one. The rule
names the case, cites this section and is marked `PROVISIONAL` in the code.

### 3.1 A flight decided in a handler pass stands (issue #343)

**Case.** A unit charges a unit C (or walks into it) and touches it. C fails its terror test.

- In the original, the contact event (0x0B) from the charger's collision pass is always handled **before** the
  charge event (0x07) from the charger's next script step (`terror_contact_charge.md` §8.5).
- C therefore first engages: the engaged event 0x0A switches it to the melee script.
- Then the fear flight (0x0D) records the switch to the flight script, which is recorded last.
- C routs in that same tick, with one "Flee the abomination!".

In the engine, C's script runs before the charger's collision pass, so C receives that pass's 0x0B a tick late,
under the charger's next 0x07. C then handles the flight first and the engagement second. The melee switch
replaced the flight switch, so C stayed in melee for a tick and shouted again on the next tick before routing
(BF026 replay, Grudgebringer Cavalry and the Wyvern).

**Rule.** When `RoutAllowed` passes and the next switch of the same script run is recorded, that switch is the
unit's **flight**. No later switch of the same run replaces it. It is applied as usual at `ReturnInterrupt` or at
the end of the run. In shipped scripts every `RoutAllowed` is followed by `If`, then `React`, then a `SwitchScript`
to the flight script (162 or 157 in the library, once a mission script), so "the switch after a passing
`RoutAllowed`" is always the flight.

**Effect.** Both event orders end in the same flight in the same tick: one shout and no tick in melee. A
`CantBreak` unit fails `RoutAllowed`, so it is not affected, and nothing carries over to the next run.

**Known difference from the original.** `terror_contact_charge.md` §8.5 names two rare cases in which the original
itself ends on the melee script: a second fear causer charging in the same tick, and an AI unit's `ReactToThreat`
self-charge event above an older contact event. The engine flees in both. Neither case is built into shipped
missions.

**Tests.** `tests/test_flee_bark_once.py`.

## 4. When to revisit

Reconsider the per-unit tick (`battle_tick_order.md` has the full order and its test vectors) only if:

- the compensation rules in §3 start to pile up or to interact with each other; or
- a visible behaviour cannot be fixed with a local rule.

Until then, add each new case to §3.
