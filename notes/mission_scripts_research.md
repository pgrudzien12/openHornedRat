# Mission Scripts Research — Behavioral Walkthroughs

**Status:** 🟢 Research in progress  
**Task:** GitHub Issue #2 (research) — Write public behavioral walkthroughs for missions beyond BF001  
**Research Date:** 2026-09-23  
**Method:** Bytecode disassembly + .BTS structure analysis  

---

## Executive Summary

The original game encodes **mission choreography as per-unit behavior scripts** — sequences of opcodes that define what each unit does during a battle. By disassembling these scripts (using the 232-opcode catalog and existing infrastructure in `whshr/behaviour.py`), we can extract the **intended gameplay flow** of each mission without decompiling or reverse-engineering the engine internals.

**Key finding:** Mission design is **data-driven**. Each battle defines:
- Enemy unit timing and objectives (when they arrive, what they target)
- NPC unit roles (static defenders, mobile cargo, reinforcements)
- Event handling and state transitions (routed behavior, escape routes, multi-phase attacks)

This research produces **public behavioral walkthroughs** — descriptions of what players observe during gameplay, sourced from script bytecode analysis.

---

## Walkthrough Files Generated

### 1. **[mission_walkthroughs_BF003.md](mission_walkthroughs_BF003.md)**
**Mission:** Protect Schnappleburg (Mission 3)  
**Type:** Static defense  
**Choreography:** Single enemy wave → reinforcement wave at 9 seconds → protect 3 peasant groups  
**Key Pattern:** Phased enemy arrival, scattered NPC objectives  

**Script Analysis:**
- Scripts 0–1: Enemy melee and cavalry units (TrackThreat AI, move → attack loop)
- Scripts 2–4: Three peasant groups (non-combatant scatter, patrol nodes 2/3/4)
- Timing: 60-tick reinforcement delay (Wolfriders after Stickers commit)

### 2. **[mission_walkthroughs_BF004.md](mission_walkthroughs_BF004.md)**
**Mission:** Breaking Through (Mission 4, Variant 1)  
**Type:** Direct combat + protection  
**Choreography:** Simultaneous enemy assault on 2 peasant groups  
**Key Pattern:** No reinforcements; immediate dual-front engagement  

**Script Analysis:**
- Scripts 0–1: Two peasant groups (non-combatant scatter, nodes 1/2)
- Scripts 2–3: Two enemy combat units (TrackThreat with conditional threat evaluation)
- Timing: Immediate pressure, no delays

### 3. **[mission_walkthroughs_BF005.md](mission_walkthroughs_BF005.md)**
**Mission:** Escort the Refugees (Mission 5)  
**Type:** Escort / mobile objective defense  
**Choreography:** Timed reinforcement waves (350 ticks, 430 ticks) while cargo transits Node 2 → Node 8  
**Key Pattern:** Phased enemy arrival, mobile objective with multi-stage escape sequence  

**Script Analysis:**
- Scripts 0–2: Three enemy units with staggered arrival (immediate, +350 ticks, +430 ticks)
- Scripts 3–4: Two cargo units (move → shelter → wait for threat → move to escape → RemoveFromBattle)
- Scripts 5: Interrupt handler for event routing (threat, targets, special items)
- Timing: Unit 2 is tagged to hunt cargo (AttackTagged 0xabc0); multi-checkpoint escape sequence

---

## Patterns Observed Across Missions

### Unit Behavior Model

**Combat Units** (enemy, some allies):
```
InitUnit (128 byte initialization)
→ SetBehaviour 15 (TrackThreat)
→ WaitForBattleStart
→ MoveToNode N
→ Loop: AttackNearestEnemy / WaitUntilUnitFlags / conditional checks
```

**Non-Combatant Units** (peasants, cargo):
```
InitUnit (64 byte initialization)
→ SetBehaviour 14 or 13 (defensive/scatter)
→ WaitForBattleStart
→ ScatterModelsToNode / MoveToNode (patrol)
→ Loop: repeat movement with wait timers
```

### Reinforcement Patterns

| Pattern | Example | Trigger |
|---|---|---|
| **Wave reinforcement** | BF003: Wolfriders at 60 ticks | Hardcoded delay (SetWait) |
| **Phased arrival** | BF005: Units at 0, 350, 430 ticks | Explicit timing per script |
| **Conditional arrival** | (not yet observed) | Event-driven (SetInterruptScript) |

### Objective Encoding

| Objective Type | Encoding | Example |
|---|---|---|
| **Static defend** | NPC at fixed node; non-combatant AI | BF003/BF004 peasants |
| **Mobile cargo** | Move → wait for threat → move to escape → RemoveFromBattle | BF005 cargo units |
| **Routed removal** | Boundary flag 0x20 triggers removal | All battlefields |

---

## Script Opcodes Used in Mission Logic

### Core Combat Opcodes

| Opcode | Effect | Missions Using |
|---|---|---|
| `AttackNearestEnemy` | Attack nearest visible hostile | BF001, BF003, BF004, BF005, BF010 |
| `AttackNearestFlag40Unit` | Attack non-combatants (flag 0x40) | BF003, BF004, BF005 |
| `AttackTagged <tag>` | Attack specific tagged unit | BF005, BF010 |
| `AttackNthNearestEnemy <n>` | Attack nth-nearest target (n=2 for second) | BF010 (skirmisher tactic) |
| `AttackEnemyOfClass <class>` | Attack enemy unit of type class | BF001 |
| `MoveToNode <n>` | Pathfind to node n | All missions |
| `SetWait <ticks>` | Delay n ticks before next opcode | All missions |
| `Wait` | Execute the wait timer | All missions |
| `SetBehaviour <type> <param>` | Set AI behavior (11=defense, 13=cargo, 14=scatter, 15=combat, 33=skirmish) | All missions |
| `FollowParent <distance>` | Follow parent unit at specified distance | BF010 (support units) |
| `SetParentByTag <tag>` | Link to unit with specified tag | BF010 (formation coordination) |

### Control Flow Opcodes

| Opcode | Effect | Missions Using |
|---|---|---|
| `WaitForBattleStart` | Stall unit until battle clock starts | All missions |
| `WaitUntilUnitFlags <mask>` | Stall until condition (routed, threatened) | BF005 (cargo escape trigger) |
| `TestUnitFlags <mask>` | Check condition, branch on result | BF003, BF004, BF005 |
| `LoopIfFalse` | Loop if condition not met | All missions |
| `Loop` | Unconditional loop | All missions |
| `RemoveFromBattle` | Permanently remove unit from play | BF005 (successful escape) |

### Event & State Opcodes

| Opcode | Effect | Missions Using |
|---|---|---|
| `Query <type>` | Test unit/battle state | BF004, BF005 |
| `GetEvent` | Receive event from event queue | BF005, BF010 (interrupt handlers) |
| `CaseEvent <type>` | Branch on event type | BF005, BF010 (event routing) |
| `SendEventToOwnSide <type>` | Broadcast event to allied units | BF005 |
| `SendEventToOwnSideIfTrue <type>` | Broadcast event if condition met | BF001 (alert signal) |
| `React <type>` | Enter reactive mode (respond to threats, not seek) | BF001, BF010 |
| `SetInterruptScript <script_id>` | Register interrupt handler (mission or library) | All missions |
| `SetTag <tag>` | Assign identification tag | All missions |
| `SetUnitFlags <flags>` | Set unit flags (256=anchored, 0x80000=hidden) | BF003, BF001 |
| `TestUnitFlags <mask>` | Check unit flags (8=routed, 16=threatened, 512=custom) | BF001, BF010, others |
| `TestCondFlags <mask>` | Check condition flags (16=reinforcement gate) | BF001, BF010 |
| `ClearCondFlags <mask>` | Clear condition flags | All missions |
| `KillAllModels` | Instant death if condition true | BF001 (difficulty scaling) |

---

## Key Insights

### 1. Choreography as Data

The original game treats mission design as **choreographed sequences of unit actions**, not as a hardcoded campaign/mission system. Each battle is a **self-contained data-driven flow**:

- Timing is explicit (wait timers, tick counts)
- Objectives are encoded as behavior sequences (move to node → wait → move to escape)
- Enemy behavior is deterministic (move to node, attack loop)
- Reinforcements use explicit delay timers or event gates
- Formation coordination via parent-child links (SetParentByTag, FollowParent)

### 2. Reinforcement Patterns (Three Types)

**Timer-based (BF003, BF005):**
- Enemy units arrive on hardcoded delays (60 ticks, 350 ticks, etc.)
- SetWait + Wait creates fixed arrival times
- Used for predictable multi-wave attacks

**Event-triggered (BF001):**
- External condition sets CondFlags on unit script
- Unit awakens when flag is set, not on timer
- Allows tutorial gates and player-progress-dependent reinforcements
- 80-tick grace period after activation (React mode)

**Coordinated/Formation (BF010):**
- Units link to each other via tags (SetParentByTag)
- Movement is synchronized but asymmetric (different nodes, shared timing)
- Allows multi-unit formations with complex battlefield tactics

### 3. Tagging & Targeting

Units use **tags** to identify each other for multiple purposes:
- `SetTag 0xabc0` marks a unit for future reference
- `AttackTagged 0xabc0` hunts that specific unit
- **SetParentByTag 0xabc1** creates runtime parent-child relationships (BF010)
- **FollowParent 36** keeps support units tethered to main unit with tight synchronization (every 6 ticks)
- **AttackNthNearestEnemy 2** allows tactical target prioritization (BF010 skirmisher)
- This allows mission designers to encode **targeting relationships and formation bonds** without hardcoding unit IDs

### 4. Event Driven Behavior & Communication

Multiple event systems identified:

**Event Broadcasting (BF001):**
- `SendEventToOwnSideIfTrue 17` broadcasts alert when condition is true
- Allows units to signal other units across the battlefield
- Event type determines routing (own side vs. enemy vs. all)

**Event-based Activation (BF001):**
- `TestCondFlags 16` checks if external flag was set
- Used to gate reinforcement arrival without timers
- Engine can set flags via campaign layer or victory conditions

**Library Event Handlers (BF010):**
- Script 151 (dwarf interrupt handler) processes events for allied units
- Library scripts enable shared behavior across multiple instances

### 5. AI Type Diversity & Roles

Beyond the combat TrackThreat (type 15) and scatter (type 14):

| AI Type | Observed In | Behavior | Purpose |
|---|---|---|---|
| 11 | BF010 (dwarf ally) | Defensive, reactive (React 20) | Allied unit support |
| 13 | BF005 (cargo) | Non-combatant, movement-focused | Mobile objectives |
| 14 | BF003/BF004 (peasants) | Scatter, patrol | Stationary/defensive NPC |
| 15 | BF001-BF010 (combat, variants 28–30, 33) | Aggressive, seek and attack | Combat units |
| 33 | BF010 (skirmisher) | Second-target focus (AttackNthNearestEnemy 2) | Ranged/support units |

AI types encode **unit role** at the script level, allowing the engine to apply role-specific logic.

### 6. Initialization Sizes & Conditional State

- **InitUnit 128:** Combat units (full setup, battle participation, damage tracking)
- **InitUnit 64:** Non-combatant units (minimal setup, movement-focused, passive roles)

**Conditional Unit State Changes (BF001):**
- `TestUnitFlags 512` checks external conditions
- `KillAllModels` removes unit instantly if condition is true
- Allows difficulty scaling without script variants
- Example: tutorial can automatically kill units on easy difficulty

**Routed State Coordination (BF010):**
- `WaitWhileUnitFlags 8` halts unit movement if routed
- Coordinated with parent/follower links for formation coherence
- Ensures formations don't advance with routed units

---

## Implementation Guidance for Engine

### For Behavior Interpreter

The engine's behavior script interpreter must support:

1. **Per-unit state machines:**
   - Each unit has independent script instruction pointer + wait timer
   - Loops repeat until conditions change or loop ends

2. **Synchronization:**
   - `WaitForBattleStart` blocks unit until battle clock starts (tick 0)
   - `SetWait N` + `Wait` blocks unit for N ticks
   - `WaitUntilUnitFlags` blocks until condition (routed, threatened)

3. **Tagging & Targeting:**
   - Units must store assigned tags
   - Targeting lookups must find units by tag
   - `AttackTagged` must resolve to correct unit

4. **Event Queue:**
   - Events must be queued per unit (or broadcast to side)
   - Interrupt scripts must process events while main script runs
   - Events consumed after handling

5. **Node Navigation:**
   - `MoveToNode N` must resolve node positions from battle data
   - Units must pathfind while avoiding boundaries
   - Scripts poll completion with `TestUnitFlags 16` (routed while moving)

### For Mission Design Tools

The script format supports:

- **Multi-phase battles** (phased enemy arrival with delays)
- **Objective-based gameplay** (move to node, wait for trigger, escape)
- **Coordination** (tag units, hunt specific targets, broadcast events)
- **Conditional behavior** (Query results affect action choice)

Mission designers encode these by:
1. Assigning behavior types (TrackThreat, scatter, defensive)
2. Scripting movement sequences (node A → wait → node B)
3. Setting timers for reinforcements
4. Tagging objectives and hunters

---

## Coverage

**Missions Analyzed:**
- ✅ BF001 (tutorial, event-triggered reinforcements)
- ✅ BF003 (defend static objectives with phased reinforcements)
- ✅ BF004_1 (direct combat + protect scattered objectives)
- ✅ BF005 (escort mobile objective with timed waves)
- ✅ BF010 (first ally mission, formation coordination)

**Missions to Analyze (Optional):**
- BF006 (likely similar escort pattern)
- BF015, BF017 (late campaign; mercenary/wizard coordination)
- BF024 (forest battle; boundary and navigation patterns)
- BF042 (last battle; final boss encounter structure)

---

## Data Sources

- **Behavior Script Disassembly:** `whshr/behaviour.py` (extraction + 232-opcode catalog)
- **Battle Data:** `.BTS` file parsing (nodes, units, objectives)
- **Earlier Research:** `notes/game_rules.md` (event system, stat fields, morale), `notes/neutral_units.md` (NPC side encoding)

---

## Open Questions (For Future Expansion)

1. **Event System Details:** 
   - What events does the engine broadcast? (Already catalogued in game_rules.md)
   - How do interrupt scripts interact with main scripts?
   - Can events trigger unit state changes (e.g., switching behavior mode)?

2. **Advanced Behaviors:**
   - What do behavior types 16–31 do? (Only types 13–15 observed so far)
   - Do behaviors support parameters beyond the opcode value?
   - Can scripts dynamically change unit behavior (SetBehaviour mid-battle)?

3. **Multi-Stage Objectives:**
   - Do missions use objective system (G, Z, etc.) or script-only control?
   - How do scripts interact with victory/defeat conditions?
   - Can objectives trigger script state changes?

4. **Campaign Integration:**
   - Do mission outcomes (casualties, retreat distance) affect campaign state via scripts?
   - Are scripted events (reinforcements, escape) recorded in debrief?
   - Do NPC units (peasants, cargo) appear in casualty counts?

---

## Report Status

**Public Walkthroughs:** ✅ 3 missions analyzed and documented  
**Script Patterns:** ✅ Documented across missions  
**Engine Guidance:** ✅ Provided (per-unit state, tagging, event handling)  
**Next Steps:** 
- Optionally expand to more missions (BF006, BF010, etc.) for pattern verification
- Use these walkthroughs as test cases for behavior interpreter implementation (Issue #3)
- Verify against actual gameplay footage (optional runtime validation)

---

## References

- `notes/mission_walkthroughs_BF003.md` — Full BF003 analysis
- `notes/mission_walkthroughs_BF004.md` — Full BF004_1 analysis
- `notes/mission_walkthroughs_BF005.md` — Full BF005 analysis
- `notes/game_rules.md` § "Unit behaviour bytecode" — 232 opcodes, event routing, interrupt system
- `whshr/behaviour.py` — Opcode disassembler and bytecode extraction tools
- `notes/neutral_units.md` § "Behavior Scripts & AI" — NPC unit scripting patterns

