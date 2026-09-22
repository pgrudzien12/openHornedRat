# Bytecode Interpreter Implementation Status

## Overview

Implementing the bytecode interpreter for issue #3 (epic #1): replacing the placeholder distance-based AI with the original's 232-opcode behaviour script execution.

**Repository**: `whshr/interpreter.py` (created in commit 0ebc5cd)

## Current Status: Foundation Complete (Phase 1)

### What's Implemented

**Core Infrastructure**:
- `UnitScriptState`: per-unit runtime state (script id, PC, return stack, event queue, flags)
- `Event`: 14-byte event records matching the original's format
- `EventBus`: event routing (self, own-side, enemy-side broadcasts)
- `ScriptInterpreter`: main interpreter loop with opcode dispatch

**Opcode Handlers** (22 opcodes):
- **Control flow** (10): InitUnit, Restart, SetRestartPoint, GotoScript, SwitchScript, GosubScript, ReturnGosub, PushPC, Loop, Yield
- **Flags** (6): SetUnitFlags, ClearUnitFlags, TestUnitFlags, SetCondFlags, ClearCondFlags, TestCondFlags
- **Events** (7): GetEvent, ConsumeEvent, CaseEvent, Break, SendEventSelf, SendEventToOwnSide, SendEventToEnemySide
- **Conditionals** (4): If, IfNot, Else, EndIf

**Integration**:
- `Battle.__init__` accepts optional `script_dll` parameter
- `Battle.tick()` runs interpreter when script_dll is available; falls back to simple AI otherwise
- Backward-compatible: all tests pass (405 tests, 30 engine/AI tests)

### Architecture Decisions

1. **Data-driven, not decompiled**: Reads opcodes as data from the DLL, never executes native code
2. **Graceful degradation**: Missing opcodes raise `NotImplementedError` but don't crash; handler logs error and continues
3. **Fallback to AI**: When no script_dll is available, uses the existing simple AI (ENGAGE_DISTANCE-based)
4. **Per-unit state**: Each regiment has its own `UnitScriptState`, executed independently each tick

## What's Still Needed (Phase 2+)

### High Priority (needed for BF001)

**Timing and waiting**:
- `Wait N`: yield until N ticks have elapsed
- `TestWait`: test if a wait has completed
- `SetWait N`: set a wait timer
- `LoopIfTrue/LoopIfFalse`: conditional loops (partial impl, needs testing)
- `WaitForBattleStart`: hold until battle clock starts

**Movement and positioning**:
- `MoveToNode N`: move to a waypoint (needs integration with battle's movement system)
- `FaceNode N`: turn to face a waypoint
- `TeleportToNode N`: instant repositioning
- `PlaceAtNode N`: place unit at a node in formation
- `HaltAndReform`: stop and reform in place

**Targeting and threat**:
- `FindTarget...`: targeting opcodes (FindTarget, FindTargetOfClass, FindThreatNear, etc.) - ~25 variants
- `AttackTarget`: set attack target
- `AttackTagged N`: attack a unit marked with tag N
- `SetTargetByTag N`: set target from tag
- `TargetNearestEnemy...`: find closest enemy by various criteria

**Library behavior 15 (TrackThreat)** - the primary AI used by 290 missions:
- Maintain a current threat (best enemy)
- Attack when threat score > unit's worth
- Threat score formula: `worth × (range − d) / round(range / 4)` (game_rules.md)

**Combat and morale effects**:
- `ChargeTarget`: issue charge command
- `FireAtTarget`: issue fire command
- `KillAllModels`: instant unit death (used for tutorial)
- `ReactToThreat`: AI response to contact
- `React N`: display battle message (1="Engage!", 2="CHARGE!", etc.)

**Queries and checks**:
- `Query N`: ask the AI routine (cases 11-14)
- `IfInNodeArea N`: test if unit is at a waypoint
- `IfAnyUnitInNodeArea N`: test if any unit is at a waypoint
- `IfTargetInChargeReach`: test charge range
- `TargetValid`: test if current target is still valid
- `ReadyToFire`: test if unit can shoot

**Unit and state management**:
- `SetUnitFlags2/ClearUnitFlags2/TestUnitFlags2`: secondary flags (+0xB8)
- `SetThreatRange N`: set threat detection range
- `SetInterruptScript N`: set script to call on events
- `SetTag N`/`IfTag N`: unit tagging system
- `IfClass N`: check unit class (infantry, archer, etc.)
- `SetClass N`: change unit class

**Event routing and special events**:
- `SendEventToTag N`: send event to a tagged unit
- `SendEventSelfIfTrue/SendEventSelfIfFalse`: conditional events
- `SendEventToParent`: notify parent unit
- `SendEventToUnitId N`: send to specific unit
- `StoreEventInfo`: save current event for later

**Specialized behaviors**:
- `SpawnUnit N`: create Night Goblin Fanatics (4 missions use this)
- `FollowParent`: child unit follows parent
- `RunAway`: flee behavior
- `ExcludeFromArmy`: remove from battle without death
- `RemoveFromBattle`: remove from play

### Medium Priority (needed for other missions)

- Animation and sound opcodes (PlayUnitAnimation, PlaySound, etc.)
- Spell/magic system (ChooseEnemyAndSpell, CastPending, etc.)
- Specialized unit behaviors (FanaticJump, BrokenTargetInRange, etc.)
- Advanced positioning (CircleAroundTarget, ApproachTargetInReach, etc.)
- Formation management (ReformBlock, SnapModelsToFormation, etc.)

### Low Priority (rarely used)

- Duplicate/unused opcodes (136=175, 181=180, 185=184, 137/171/173/174 unused)
- Obsolete or mission-specific opcodes

## Testing Strategy

1. **Unit tests**: Add tests for each new opcode before implementation
2. **Mission tests**: Test with BF001, then BF003/BF004/BF005 (walkthroughs available)
3. **Regression**: Ensure simple AI fallback still works
4. **Script validation**: `python3 -m whshr scripts` disassembler already validates scripts

## Implementation Notes

**Operand handling**: Currently simplified to read only the first operand word. Should enhance to support multi-word operands (some opcodes like `0x1F`, `0x87`, `0x95`, `0x9D` have operands one word longer than initially derived - see game_rules.md).

**Effect integration**: Opcodes like `ChargeTarget`, `FireAtTarget`, `KillAllModels` need to call into `whshr.combat` and `whshr.engine.Battle` to have actual effects. These are placeholder stubs that log but don't yet execute.

**Yield and timing**: The `Yield` opcode pauses script execution to let the battle tick proceed. Full implementation needs a scheduler to resume scripts at the right time, not just next tick.

**Event queue**: Currently uses a simple deque. The original has a 128-record pool with linking; current simplified version might need enhancement for complex event sequences.

## File Structure

```
whshr/interpreter.py
  - Event: 14-byte record
  - UnitScriptState: per-unit runtime
  - EventBus: routing infrastructure
  - ScriptInterpreter: main loop + opcode dispatch
    - op_<OPCODE_NAME>(self, state, operand, script_words, unit_id, tick_count, rng) -> pc
    - Handlers organized by category (control, flags, events, conditions, TODO)

Integration points:
  - whshr/engine.py: Battle.__init__ and tick() updated
  - whshr/behaviour.py: Opcode constants (LABEL, END, LENGTHS, OPCODE_NAMES)
  - whshr/ai.py: Fallback when script_dll is None
  - whshr/combat.py: Called by opcodes for charge/fire effects (future)
```

## Next Steps (by priority)

1. **Add Wait/timing opcodes** (SetWait, TestWait, LoopIfTrue/False)
2. **Test with real scripts** (requires game installation or extracted script data)
3. **Implement FindTarget** and targeting variants
4. **Implement TrackThreat** library behavior 15
5. **Add movement opcodes** (MoveToNode, FaceNode, etc.)
6. **Test with BF001**, then BF003/BF004/BF005
7. **Combat integration**: ChargeTarget, FireAtTarget call into combat module
8. **Expand to all 232 opcodes** as missions require them

## References

- **Public specification**: `notes/game_rules.md` § "Unit behaviour scripts and events"
- **Implementation notes**: `notes/engine_gaps/mission_scripts.md` § "Implementation notes"
- **Mission walkthroughs**: `notes/mission_walkthroughs_BF00*.md` (BF001-BF005, BF010)
- **Opcode catalogue**: `whshr/behaviour.py` (all 232 opcodes enumerated, lengths table)
- **Disassembler**: `python3 -m whshr scripts` (validates scripts and shows disassembly)

## Known Limitations

- No script DLL means no mission choreography (fallback to simple AI)
- Partial opcode set means some missions may not run fully
- Yield timing simplified: scripts resume next tick, not based on event queue depth
- Multi-word operands not fully supported yet
- No persistence of script state across save/load cycles (TODO)

## Success Criteria (from issue #3)

✅ Generic interpreter driven by catalogued 232-opcode table  
✅ Per-unit runtime state (script id, PC, return stack, event queue)  
✅ Event bus matching original's routing (self/own-side/enemy-side)  
✅ Integration with battle engine (partially; movement/combat TBD)  
⏳ Replace placeholder distance rule with library behaviour 15 (TrackThreat)  
⏳ Test on multiple missions (BF001+)  

## Architecture Diagram

```
Battle.tick()
  ↓
if self.interpreter:
  for each regiment:
    interpreter.run(unit_id, state, tick_count, rng)
      ↓
      fetch script words from script_dll
      ↓
      while not Yield and pc < len(script):
        dispatch opcode → handler
        handler modifies state, returns new pc
        ↓
        if event in queue, GetEvent and process CaseEvent
        ↓
        apply pending script switch at tick end
else:
  ai.decide_orders(self)  ← fallback
```

