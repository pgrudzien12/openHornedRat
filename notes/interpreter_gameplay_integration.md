# Bytecode Interpreter Integration into Live Battle Gameplay

**Research Date:** 2026-09-23
**Task:** Issue #46 — Wire the bytecode interpreter into live battle gameplay
**Status:** Research phase (see "Implementation Status" below for what has since been built)

---

## Implementation Status (2026-09-23, added by the implementer, not part of the research above)

Landed against this document's "Proposed" section:

- **Item 1, "Wire `script_dll` through to `BattleScene`"**: done. `Battle.from_script`/`from_battle_file`
  take `script_dll`; `BattleScene._load_script_dll()` loads the mission's own `SCRIPT/BFxxx.DLL` from
  its `loadScript` name and fails closed (returns None, falls back to `whshr.ai`) on a missing or
  unparseable DLL. Each regiment's initial script id now comes from its own `set:script=` value
  instead of a hardcoded default. Tests: `tests/test_interpreter_wiring.py`.
- **Item 2, "Implement the missing opcodes scripts actually use"**: the opcodes this document listed
  as verified-missing are now implemented: `AttackNearestEnemy`, `AttackNearestVisibleEnemy`,
  `AttackNearestFlag40Unit` (falls back to plain nearest-enemy — no neutral-side/flag-0x40 tracking
  exists yet, see item 3 below), `AttackNthNearestEnemy`, `WaitUntilUnitFlags`, `IfSwitchScript`,
  `IfSwitchScriptHigh`, `IfNotSwitchScript`, `RoutAllowed`, `FleeFromTarget`, `FearWhenCharged`. The
  `SwitchScript` priority family's exact semantics beyond "0x0F is higher priority than 0x0D/0x0E"
  are a best-effort reading of this document's own bytecode findings, not independently confirmed —
  flagged as such in each handler's docstring. `TargetNearestEnemy` was also fixed: it was an
  existing stub that always set `cond_flags = 1` without finding anything. Tests:
  `tests/test_interpreter_phase2_opcodes.py`.
- **Bug found and fixed along the way**: `Event.source` was typed `int` but every emitting opcode
  computed it as `int(unit_id) if unit_id.isdigit() else 0` — always `0` for real regiment
  identifiers (e.g. `"Goblin_Stickers"`), silently breaking `TakeEventTarget` and `IfEventSource`
  for any real mission. Now `source` holds the sender's regiment identifier directly.
  `RunAway` also had `combat.start_rout(battle, regiment)` (swapped argument order against the
  real `start_rout(regiment, battle)` signature) — would have raised `AttributeError` the moment
  it ran against real event data. Both fixed with regression tests.
- **Item 3, "Connect script outputs to engine state"**: partially done — `AttackNearestEnemy` and
  friends set `regiment.attack_target` directly now (same approach `ChargeTarget`/`FireAtTarget`
  already used). Neutral-side/flag-0x40 tracking (needed for a real `AttackNearestFlag40Unit`) is
  still open.
- **Item 4, "Generate events from engine conditions"**: still not built. `WaitUntilUnitFlags` and
  `FearWhenCharged` are implemented against the interpreter's own state (`unit_flags`, event
  `source`), but nothing in `whshr/combat.py` yet raises engine conditions (attacked, routed,
  charged) as events or flags — a script that waits on one will block indefinitely, which is
  documented in the opcode's own docstring rather than papered over.
- **Item 5, "Movement feedback"**: the node-coordinate half is done. The battle's own `[NODES]`
  table was already fully parsed by `whshr.script.load_battle` (each node has real `x`/`y`) but
  `Battle.from_script` silently discarded it -- `Battle.nodes` (`{id: (x, y)}`) now carries it
  through. `MoveToNode` issues an ordinary move order toward the node's coordinates,
  `TeleportToNode`/`PlaceAtNode` reposition instantly, and `FaceNode` turns toward it using the same
  pivot-preserving `Battle.turn_to` every other turn in the engine uses. All four fail-safe (no-op,
  never raise) for an id the battle has no node for.

  Arrival feedback is now also built: `MoveToNode`/`ScatterModelsToNode` arm `pending_arrival` and
  clear a new `ARRIVED_FLAG` (unit_flags bit `0x10`) on the order's regiment; once the regiment
  stops moving (checked at the start of every `ScriptInterpreter.run()` call), the flag is set, so a
  `WaitUntilUnitFlags(16)` loop can unblock. `TeleportToNode`/`PlaceAtNode` set it immediately
  (instant completion). **This is a well-evidenced hypothesis, not a confirmed public fact**: no
  document confirms bit `0x10` means "arrived", but the `MoveToNode N; WaitUntilUnitFlags 16` idiom
  appears throughout real scripts immediately after a move order, nothing else in the engine ever
  set any bit `WaitUntilUnitFlags` checks, and this was confirmed as the actual cause of Goblin
  Wolfriders freezing permanently (forever blocked on this exact wait) in a real BF003 playthrough.

  Also implemented: `ScatterModelsToNode`, the opcode NPC "patrol" scripts actually use -- a real
  trace showed peasant regiments never call `MoveToNode` at all, only this (in a
  `SetWait 20`/`Wait`/`Loop` cycle). Reuses the ordinary move order with a small random jitter
  around the node (`SCATTER_RADIUS`, a documented placeholder -- issue #47 tracks confirming the
  real value, possibly the node's own unread `radius` field).

  Tests: `tests/test_interpreter_wiring.py` (`NodeWiringTests`),
  `tests/test_interpreter_phase3.py` (`MovementOpcodeWithRealNodesTests`, `ScatterModelsToNodeTests`,
  `ArrivalFlagTests`).
- **Real bug found via the new opcode trace (see below) and fixed**: `WaitForBattleStart` blocked
  (tick 0) without setting `_should_yield`, so `ScriptInterpreter.run()`'s dispatch loop
  re-dispatched the exact same instruction until hitting `max_iterations` (10000) instead of
  properly ending the tick -- confirmed from a real trace: every regiment burned ~9993-9997
  identical `WaitForBattleStart` dispatches on tick 0 alone (and made the trace file itself, at
  17 MB, hard to read for anything else). Fixed to yield like `Wait`/`WaitUntilUnitFlags` do.
  Regression tests: `tests/test_interpreter_phase2_opcodes.py` (`WaitForBattleStartYieldTests`),
  `tests/test_interpreter_tracing.py` (`WaitForBattleStartIterationTests`).
- **Real bug found (after peasants were reported still freezing mid-patrol despite the above) and
  fixed**: `op_Loop` popped the return stack instead of peeking it, unlike its siblings
  `LoopIfTrue`/`LoopIfFalse`, which already peeked correctly. `PushPC` runs once, before a loop
  body; `Loop` is meant to jump back to it on every iteration (a "while true" idiom). Popping
  destroyed that stack entry after the very first jump back, so the *second* time a script reached
  `Loop`, the stack was already empty and it silently fell through to `pc + 1` instead of looping
  again. Confirmed from a real trace as the exact cause of NPC peasant regiments (BF003) scattering
  exactly twice via `PushPC`/`ScatterModelsToNode`/`SetWait`/`Wait`/`Loop`, then freezing in place
  for the rest of the battle (regiment data showed `models` and `corpses` unchanged throughout --
  they were never actually dying, just permanently stuck). Regression tests:
  `tests/test_interpreter_phase2_opcodes.py` (`LoopPeeksNotPopsTests`),
  `tests/test_interpreter_tracing.py` (`ScatterPatrolLoopEndToEndTests`, a full `Battle.tick()`
  replay of the exact script shape that proves the loop now repeats more than twice).
- **Real regression found and fixed after item 2 landed**: `SetBehaviour` called
  `LibraryBehaviors.track_threat()` immediately and unconditionally the moment it ran, setting
  `regiment.attack_target` on tick 0/1 regardless of any `SetWait`/`Wait`/`MoveToNode` gating later
  in the *same* script. Confirmed against a real BF003 playthrough: the reinforcement Goblin
  Wolfriders regiment attacked from the very first tick instead of respecting its own `SetWait 60`
  gate (and Goblin Stickers likely attacked faster than intended too, for the same reason). Fixed:
  `SetBehaviour` now only records `state.behaviour_id`; there is no confirmed public documentation
  of exactly when a declared library behavior like TrackThreat is meant to run relative to a unit's
  own script instructions, so this is deliberately a no-op rather than a second guessed
  reimplementation — a unit's own `AttackNearestEnemy`/`AttackNearestVisibleEnemy`/`FindTarget*`
  calls (item 2, now implemented) are what actually drive targeting. Regression tests:
  `tests/test_interpreter_wiring.py`.
- **Opcode-level tracing and gap reporting**, added because both regressions above were only found
  by manually cross-referencing regiment positions across dozens of battle-log snapshots. Two
  mechanisms (`tests/test_interpreter_tracing.py`):
  - `WHSHR_TRACE_SCRIPTS=1` environment variable: `BattleScene.enter()` turns on
    `BattleLogger.trace_scripts`, which makes `ScriptInterpreter.run()` write an `"opcode"` record
    (tick, unit, script id, pc, opcode name, operand, outcome, a small state snapshot) for every
    instruction it dispatches, into the same JSON Lines file as the rest of the battle log. Off by
    default -- much higher volume than the rest of the log. Usage:
    `WHSHR_TRACE_SCRIPTS=1 .venv/bin/python -m whshr engine "$WARFB" --battle BF003`, then
    `grep '"type": "opcode"' logs/battle-*.jsonl` or filter by `unit_id`.
  - Always on, independent of tracing: the first time any unit's script hits an opcode with no
    handler, or one whose handler raises, it's recorded once as a normal `"event"` record
    (`kind: "script_gap"`) -- deduplicated per (unit, script, opcode) so a tight retry loop doesn't
    spam the same complaint every tick for the rest of the battle. Visible in every battle log
    without needing `WHSHR_TRACE_SCRIPTS` at all.
- **User-reported gap, long-standing**: in the original, a charged unit freezes and waits, rather
  than continuing to close on its attacker; without this, both units instead independently charge
  each other (visible in play, not from a log). Two things were missing together:
  - `CallInterruptScript`/`ReturnInterrupt` (opcodes 0x12/0x14): the interpreter plumbing a script's
    event-handling frame uses to jump into, and return from, the script registered by
    `SetInterruptScript`. Implemented as a one-level gosub (`state.interrupt_return`), with
    `ReturnInterrupt` applying a pending switch immediately instead of returning if the interrupt
    handler itself requested one -- matching game_rules.md's own description of opcode 0x14 ("end
    of an event handler: return to the interrupted script or apply a pending switch").
  - `ScriptInterpreter.raise_charge_events()`: nothing in the engine ever raised event 0x07 ("you
    are being charged", per game_rules.md's event table) in the first place, so even with the above
    working, a charged unit's script had nothing to react to. Now called once per tick from
    `Battle.tick()`, after every unit's script has run: queues event 0x07 to a regiment the moment
    another regiment's `attack_target` freshly names it (not every tick the same charge continues).
    Once queued, the target's own already-implemented event-handling opcodes (`GetEvent`,
    `CaseEvent`, `FearWhenCharged`, `SwitchScript`, ...) drive whatever reaction its real script
    data specifies -- no "freeze" behavior is hardcoded here, it should fall out of the real
    bytecode once the event actually reaches it.
  - **Bug found and fixed while investigating this**: `op_FireAtTarget` set `regiment.attack_target`,
    which both charges the shooter into melee (`Battle._advance_regiments`) and makes
    `combat.resolve_shooting` skip the unit entirely (it explicitly skips anyone with
    `attack_target` set, since it already does independent nearest-in-arc-and-range targeting) --
    silently breaking every scripted shooting order. Fixed to a documented no-op: the actual target
    for a shot is `resolve_shooting`'s own search, not script-directed, in this simplified engine.
  - Tests: `tests/test_interpreter_charge_events.py` (12 new), plus an updated
    `test_fire_at_target_never_sets_attack_target` in `tests/test_interpreter_phase3.py`.
- **The remaining two opcodes real BF003 traces showed as unimplemented** (beyond
  `ScatterModelsToNode`, already fixed above): `SetParentByTag` (every regiment traced --
  Stickers, Wolfriders, all three peasant regiments -- calls it early in their script) and
  `SnapModelsToFormation` (every peasant regiment, right after `ScatterModelsToNode`). Implemented:
  `SetParentByTag` looks up the tag in the same `Battle._unit_tags` registry `SetTag`/`AttackTagged`
  already use and records the result on a new `UnitScriptState.parent_id`; `SnapModelsToFormation`
  is a documented no-op for the same reason `PlaceAtNode`'s "in formation" aspect already was --
  `Regiment.model_positions()` always recomputes every model's slot from the regiment's current
  anchor/models/ranks/direction, so there is no separate scattered-model state to snap back from in
  this engine. `parent_id` itself is not yet consumed by anything (`FollowParent`/
  `SendEventToParent` remain unimplemented/no-op stubs -- not confirmed as actually called by any
  traced BF003 script, so left alone rather than guessed at). Tests:
  `tests/test_interpreter_phase3.py` (`UnitTaggingTests`, 3 new).
- **`IfThreatOutweighsWorth`**: the only gap left in a real, *won* BF003 playthrough (a fresh trace
  after all the fixes above), and it turned out to be genuinely well-documented -- it's the actual
  decision gate behind library behaviour 15 (TrackThreat): game_rules.md describes TrackThreat as
  "keep the best threat and attack it when its score exceeds the unit's worth", and separately
  documents both formulas exactly: unit worth = `size x s_pntval x 12 artillery / 8 wizard / 4
  monster / 1`, threat score = `worth x (range - d) / round(range / 4)` with octagonal distance,
  zero for friends/routing/`CantMelee`/beyond range. Implemented both formulas
  (`ScriptInterpreter._unit_worth`, `._threat_score`) and the opcode itself, plus a new
  `Regiment.points` field (from each unit's own `s_pntval`, previously undecoded) to make worth
  computable at all. Confirmed against the real trace: Goblin Wolfriders hits this exact opcode in
  the documented `Query 1` / `IfThreatOutweighsWorth` / `SendEventSelfIfTrue` /
  `AttackNearestFlag40Unit` sequence.

  Simplification: game_rules.md documents a x4 score multiplier when "the enemy targets this unit"
  and x32 when it is "also charging" -- these collapse into a single x4 here, since this engine's
  `attack_target` field doesn't distinguish "targeting" from "charging" as separate states (setting
  it always implies a charge order). Hidden units are not excluded from scoring either (no bit is
  currently read for that anywhere in this engine) -- a known, documented gap, not a silent one.

  Tests: `tests/test_interpreter_threat_score.py` (17 new: worth's class multipliers, the score
  formula's exclusions and distance/charging behavior, the opcode's own decision threshold), plus
  two in `tests/test_engine.py` confirming `s_pntval` actually reaches `Regiment.points`.

---

## Methodology Note

Every claim below was verified against the current checkout on 2026-09-23 by reading
`whshr/interpreter.py`, `whshr/engine.py`, and `whshr/battle_scene.py` directly, and by
disassembling mission scripts with `python3 -m whshr scripts`. Sections are labeled
**Verified** (checked against code/bytecode in this session) or **Proposed** (a design
for Phase 2 that has not been built or tested). Nothing here is inferred from decompiled
engine internals — only from the interpreter's own source and from script bytecode.

---

## Verified: Current State

### The interpreter framework exists but does not run in live battles

`Battle.__init__` (`whshr/engine.py:260-284`) only creates a `ScriptInterpreter` when a
`script_dll` argument is supplied:

```python
self.interpreter = interpreter.ScriptInterpreter(self, self.event_bus, script_dll) if script_dll else None
```

`Battle.from_script()` (`whshr/engine.py:291`) has **no `script_dll` parameter at all**.
`BattleScene.enter()` (`whshr/battle_scene.py:42`), the only place that constructs a
`Battle` for actual gameplay, calls:

```python
self.battle = Battle.from_script(self.field.script, seed=self.seed)
```

No `script_dll` is passed anywhere in this path. Consequently `self.interpreter` is
always `None` in every live battle, and `Battle.update` (the tick method — there is no
`update_phase` method in this codebase) falls back to `ai.decide_orders(self)` instead.

**Conclusion: the interpreter has never executed a single opcode in an actual battle,
and not even in a test.** Checked every `ScriptInterpreter(...)` construction and every
`interpreter.run(...)` call across `tests/test_interpreter_bf001.py`,
`tests/test_interpreter_bf003.py`, and `tests/test_interpreter_phase3.py` (28
constructions total): every one passes `None` for `script_dll`, and `run()` is never
called anywhere in the test suite. All existing tests call individual `op_*` handler
methods directly (`interp.op_MoveToNode(state, ...)` etc.) against hand-built
`UnitScriptState` objects — this is real and useful coverage of each handler's own logic,
but the DLL-loading and opcode-dispatch loop in `ScriptInterpreter.run()` has not been
exercised by anything in this repository, ever, against real or synthetic bytecode.

### Opcode coverage: 87 of 232 catalogued opcodes have handlers

`grep -c "def op_" whshr/interpreter.py` returns 88, but that count is wrong: it
includes a docstring line ("Handlers follow the pattern: def op_<name>...") that matches
the same grep pattern without being a real method. Counted the actual `def op_` lines
that begin a method (`grep -oP "def op_\K\w+"`, then de-duplicated) → **87** distinct
handler methods, against 232 opcode slots in `whshr/behaviour.py`'s `OPCODE_NAMES` table
(232 keys, 230 unique name strings — two opcode numbers share a name).

**Further check — are all 87 handlers actually reachable?** Cross-referencing the 87
handler names against the 230 unique catalogued names found **4 that don't match any
catalogued opcode**: `op_IfRouted`, `op_FindTargetNear`, `op_IfBreak`,
`op_FindNewTargetNear`. `_dispatch()` builds the handler name from
`behaviour.opcode_name(opcode)`, which does an exact dict lookup with no fuzzy matching —
so these 4 methods can never be reached by any opcode value and are dead code. (This is
an interpreter implementation detail, not something Phase 2/Issue #46 needs to fix, but
it means only **83** of the 87 defined handlers are actually wired to dispatch.)

**Implemented** (verified present as `op_*` methods): InitUnit, Restart, SetRestartPoint,
GotoScript, SwitchScript, GosubScript, ReturnGosub, PushPC, Loop, Yield, ResetStack,
SetUnitFlags, ClearUnitFlags, TestUnitFlags, SetCondFlags, ClearCondFlags, TestCondFlags,
GetEvent, ConsumeEvent, CaseEvent, Break, SendEventSelf, SendEventSelfIfTrue,
SendEventSelfIfFalse, SendEventToOwnSide, SendEventToOwnSideIfTrue, SendEventToEnemySide,
If, IfNot, Else, EndIf, WaitForBattleStart, SetWait, TestWait, Wait, LoopIfTrue,
LoopIfFalse, FindTarget, FindTargetNear, FindNewTargetNear, TargetNearestEnemy,
TargetValid, TargetGone, InRange, AttackTagged, SetTag, SetThreatRange, SetBehaviour,
React, Query, KeepThreat, IfRouted, IfClass, IfTag, IfTagExists, IfBreak, IfEventSource,
IfBattleState, IfGameMode, IfObjective, IfMachineDestroyed, IfTargetInChargeReach,
SetInterruptScript, TakeEventTarget, EnemyRouted, EnemyRoutedStatic, StartPursuit,
ChargeTarget, FireAtTarget, ReadyToFire, StampReload, RunAway, KillAllModels,
RemoveFromBattle, MoveToNode, FaceNode, PlaceAtNode, TeleportToNode, HaltAndReform,
ReformBlock, FollowParent, SetClass, SetBattleState, SpawnUnit, ExcludeFromArmy,
ExecuteOrder, RestartAfterOrder.

**Verified missing** (catalogued in `behaviour.py`, no `op_*` handler in
`interpreter.py`), specifically re-checked one by one because a prior draft of this
document incorrectly marked several of these as working:

| Opcode | In behaviour.py catalog? | Handler in interpreter.py? |
|---|---|---|
| `AttackNearestEnemy` (0xB0) | Yes | **No** |
| `AttackNearestVisibleEnemy` (0xB1) | Yes | **No** |
| `AttackNearestFlag40Unit` (0x92) | Yes | **No** |
| `AttackNthNearestEnemy` (0xB6) | Yes | **No** |
| `WaitUntilUnitFlags` | Yes | **No** |
| `IfSwitchScript` | Yes | **No** |
| `IfSwitchScriptHigh` | Yes | **No** |
| `RoutAllowed` | Yes | **No** |
| `FleeFromTarget` | Yes | **No** |
| `FearWhenCharged` | Yes | **No** |

These are not a complete list of the 145 missing opcodes (232 − 87) — they are the specific ones
that appear in the BF003/BF005/BF010 walkthroughs referenced below, checked because a
previous version of this document claimed (falsely) that scripts using them were
integration-verified.

---

## Verified: Bytecode Actually Disassembled

Re-disassembled directly in this session via `python3 -m whshr scripts` against the
user's installation (`$WARFB`), not recalled from memory:

```
BF003 script 0 (excerpt):
  SetBehaviour 15 29
  ...
  AttackNearestVisibleEnemy
  SetWait 15
  Wait
  ...

BF005 script 3 (excerpt):
  MoveToNode 2
  WaitUntilUnitFlags 16
  MoveToNode 8
  SetUnitFlags2 0x1000
  RemoveFromBattle

BF010 script 151 (excerpt, interrupt handler):
  GetEvent
  CaseEvent 3
  ReactToThreat
  IfSwitchScript 159
  Break -> L79
```

This bytecode is real and was independently re-verified. What is **not** verified is
that running it through the current interpreter produces correct battle behavior —
several of the opcodes it uses (`AttackNearestVisibleEnemy`, `WaitUntilUnitFlags`,
`IfSwitchScript`) have no handler yet, so a script that reaches one of them currently
raises `NotImplementedError`, which `ScriptInterpreter.run()` catches and silently skips
past (advancing the PC by the instruction length and continuing). The unit does not
crash; it just never performs the missing action.

---

## Proposed: What Phase 2 Needs to Build

Everything below is a design proposal, not a description of existing behavior.

### 1. Wire `script_dll` through to `BattleScene`

`BattleScene.enter()` must load the mission's `SCRIPT/BFxxx.DLL` and pass it to
`Battle.from_script()`, which must gain a `script_dll` parameter and forward it to
`Battle.__init__`. Without this, none of the rest matters — the interpreter simply never
runs.

### 2. Implement the missing opcodes scripts actually use

Priority order should follow what the walkthrough missions need, since those are the
mission scripts already disassembled and documented:
- `AttackNearestEnemy` / `AttackNearestVisibleEnemy` / `AttackNearestFlag40Unit` /
  `AttackNthNearestEnemy` — target-selection opcodes used by nearly every combat script
- `WaitUntilUnitFlags` — blocks script until a unit-flag condition holds (used by BF005
  cargo escape sequencing)
- `IfSwitchScript` / `IfSwitchScriptHigh` — conditional script transitions (used
  throughout the BF010 dwarf interrupt handler, script 151)
- `RoutAllowed`, `FleeFromTarget`, `FearWhenCharged` — morale-reaction opcodes used by
  the dwarf behavior library (`notes/dwarf_behavior_library.md`)

### 3. Connect script outputs to engine state

`TargetNearestEnemy` (implemented) and the still-missing `AttackNearestEnemy` family
need to actually set something the combat system reads. Whether that's
`regiment.attack_target` or a new field is an implementation decision, not something
observed in bytecode — the bytecode only shows that a target gets selected and then
attacked in subsequent opcodes.

### 4. Generate events from engine conditions

Script 151 (BF010) and the general event architecture assume the engine will queue
events such as "unit was attacked," "friendly unit routed," "enemy routed" at the
right moments. `EventBus.queue_event()` exists and can route self/side/enemy, but
nothing in `whshr/combat.py` currently calls it. This is pure design work: decide where
in the combat/morale resolution loop each event type should be queued, matching the
event codes documented in `notes/game_rules.md`.

### 5. Movement feedback

`MoveToNode` (implemented) sets `state.current_node`, but whether/how the engine signals
"arrived" back to the script (so a `TestUnitFlags`/`WaitUntilUnitFlags` loop can exit) is
not yet built and not observable from bytecode alone — only that scripts poll a flag in
a loop after issuing movement.

---

## What This Document Is Not

This is not a verification that the five items above work — none of them have been
implemented or tested yet. It is a plan, built from re-reading the actual interpreter
source and re-disassembling actual mission bytecode in this session, for what Phase 2
implementation work needs to cover.
