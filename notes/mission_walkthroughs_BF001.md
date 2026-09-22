# Mission Walkthrough: BF001 — Tutorial Battle

**Campaign Mission:** 1 (Tutorial)  
**Mission Title:** First Battle / Tutorial  
**Objective:** Destroy enemy forces; introduction to game mechanics

---

## Battle Overview

**Battlefield:** Small introductory engagement  
**Enemy Army:** 3 units (2 active, 1 dormant reinforcement)  
**Mechanics:** Conditional enemy reinforcement (triggered by player progress)  
**Key Pattern:** Tutorial with paced enemy activation

---

## Enemy Forces

### Enemy Unit 0 (Script 0) — Initial Aggressor
- **Unit Type:** Infantry/leader (full init size 128)
- **Tag:** 0xabc1
- **AI Behavior:** TrackThreat (aggressive, type 15, variant 28)
- **Threat Range:** 240
- **Tactics:**
  1. Attack nearest enemy immediately
  2. **SendEventToOwnSideIfTrue 17** — broadcasts alert to allied units when attacking
  3. If no visible enemy, move to Node 6 then Node 7 (patrol)
  4. Resume attacking if enemy encountered during patrol
- **Role:** Primary aggressive force; sends signals to allies

### Enemy Unit 1 (Script 1) — Dormant/Waiting
- **Unit Type:** Specialized/commander (full init size 128)
- **Tag:** 0xabc0
- **AI Behavior:** TrackThreat variant 29
- **Threat Range:** Very low (40) — indicates minimal engagement distance
- **Special Condition:** **If TestUnitFlags 512 → KillAllModels**
- **Pattern:**
  1. WaitForBattleStart
  2. Loop: Wait 10 ticks
  3. If flag 512 set by external event, kill all models in unit
- **Role:** Conditional unit; possibly for dynamic battle adjustment (difficulty scaling or tutorial progression)

### Enemy Unit 2 (Script 2) — Triggered Reinforcement
- **Unit Type:** Combat (full init 128)
- **AI Behavior:** TrackThreat variant 30
- **Threat Range:** 40 (low, specialized)
- **Initial State:** Dormant (ClearCondFlags 16 = not yet activated)
- **Activation Trigger:**
  1. Wait for CondFlag 16 to be SET by external source
  2. Once activated: Wait 80 ticks (12 seconds)
  3. **React 18** — reactive mode (not proactive seeking)
  4. **AttackTagged 0xabc0** — hunts the tagged unit
  5. Loop with 100-tick delays between checks
- **Role:** Reinforcement that activates only after player meets certain conditions (tutorial gate)

---

## Key Observations

### Conditional Reinforcement System

Unit 2 demonstrates a **reinforcement gate**: the enemy will not engage until:
1. Some external condition triggers flag 16 on Unit 2's script
2. Unit 2 waits 12 seconds before attacking

This is likely tied to **tutorial progression**:
- Player destroys some units or reaches a checkpoint
- Condition triggers flag 16
- Reinforcement wakes and begins hunting (12-second grace period for player to prepare)

### Communication System

Unit 0 sends an **event 17 to own side** when attacking successfully. This could:
- Alert other friendly units that contact has been made
- Trigger Unit 2's CondFlag 16 indirectly (via event routing)
- Coordinate behavior between units

### Conditional Unit Death

Unit 1's flag 512 check (KillAllModels) is unusual:
- **If condition 512 is true, the entire unit dies instantly**
- This allows tutorial difficulty scaling without scripting multiple variants
- Example: on easier difficulty, Unit 1 could be killed automatically to lighten challenge

---

## Tutorial Design Pattern

**BF001 shows game design for learning:**

1. **Phase 1 (Initial):** Unit 0 attacks immediately, teaching player about combat
2. **Phase 2 (Conditional):** After player progresses (kills units, reaches position), reinforcement Unit 2 activates
3. **Adaptive Difficulty:** Unit 1 can be killed by external flag (difficulty scaling)
4. **Paced Progression:** 80-tick (12-second) delay before Unit 2 engages gives player breathing room to prepare

This differs from other missions:
- BF003/BF004: Reinforcements on hardcoded timers
- **BF001: Reinforcements gated by player progress**

---

## Bytecode Patterns

### Event Broadcasting
```
AttackNearestEnemy
SendEventToOwnSideIfTrue 17  ← Broadcast event 17 (attack success?) to allied units
LoopIfFalse                    ← Only if event was sent
```

This pattern shows **inter-unit communication** — one unit's action triggers behavior in others.

### Conditional Activation
```
ClearCondFlags 16          ← Start dormant (flag 16 clear)
...
TestCondFlags 16           ← Check if flag was set by external source
LoopIfFalse                ← Keep dormant until set
SetWait 80                 ← Once triggered, wait 80 ticks
Wait
React 18                   ← Enter reactive mode
AttackTagged 0xabc0       ← Hunt specific target
```

This pattern shows **event-driven unit state transitions** — units sleep until activated by external flag.

### Conditional Termination
```
TestUnitFlags 512
If
  KillAllModels            ← Instant death if flag set
EndIf
```

This pattern allows **dynamic unit removal** without changing scripts — useful for difficulty scaling.

---

## Mission Success Conditions

Likely requires:
1. Defeat all active enemy forces
2. Survive the reinforcement phase (Unit 2 engagement)
3. Minimal casualties (tutorial mission, likely forgiving)

---

## Data Sources

- **Battle File:** `BF001.BTS` (mission 1, tutorial)
- **Mission Scripts:** Bytecode disassembled from `SCRIPT/BF001.DLL` (scripts 0–2)
- **Script Format:** Warhammer SotHR behavior bytecode (232 opcodes, per-unit state machine)

---

## Comparison with Other Missions

| Aspect | BF001 (Tutorial) | BF003 (Defense) | BF005 (Escort) |
|---|---|---|---|
| Reinforcement Style | **Event-triggered** | Hardcoded timer | Hardcoded timers |
| Enemy Activation | Conditional flag | Immediate | Phased arrival |
| Difficulty Scaling | Flag 512 (kill unit) | Static | Static |
| Inter-unit Communication | SendEventToOwnSide | None | TaggedAttack |

---

## Advanced Insights

**For Engine Implementation:**

1. **Condition Flags System:** Units can sleep until external flags are set. Engine must support persistent unit state queries.

2. **Event Routing:** Events can be sent to "own side" with conditional broadcasting (SendEventToOwnSideIfTrue). Event types determine routing and behavior.

3. **Difficulty Scaling:** Flag-based unit removal (KillAllModels) allows tutorial missions to adapt without script variants. Could be driven by difficulty setting or campaign progression.

4. **Reactive vs. Proactive:** React 18 indicates units can operate in reactive mode (wait for threat) vs. proactive (seek and attack). This affects AI aggressiveness and search patterns.

---

## Open Questions

1. **Flag 16 Source:** What external system sets the CondFlag 16 on Unit 2? Campaign layer? Player action detector? Time-based event?
2. **Event 17 Semantics:** What does event type 17 mean? "Unit attacked?" "Bloodlust?" "Flee?" How do other units respond?
3. **Flag 512 Trigger:** What sets flag 512 on Unit 1? Difficulty setting? Mission parameter? Scripted condition?
4. **React Mode:** Does React 18 change Unit 2's behavior tree, or just activation policy? Can units switch between reactive/proactive mid-mission?

