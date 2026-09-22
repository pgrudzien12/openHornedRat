# Dwarf Behavior Library — Scripts 151–170 Analysis

**Research Date:** 2026-09-23  
**Focus:** Library script 151 and related behavior tree  
**Question:** What does script 151 do, and is it shared across dwarf missions?

---

## Executive Summary

**Script 151 is a shared library interrupt handler** used by dwarf units across **four dwarven alliance missions**: BF010, BF011, BF016, BF036. It implements an **event-driven state machine** that routes the dwarf unit to different tactical behaviors based on 10+ event types (threats, charges, routs, targets, morale effects).

The handler delegates to a behavior tree of 16+ library scripts (152–170) that implement distinct tactical modes: charge assault, close combat, hold formation, flee panic, and pursuit. This demonstrates that **dwarf units have unified, shared behavior logic** implemented as a reusable library, not mission-specific scripts.

---

## Script 151: Dwarf Interrupt Event Handler

**Shared across missions:** BF010, BF011, BF016, BF036 (at least)  
**Not used in:** BF014, BF015, BF017, BF036 (these likely use different unit types or tactics)  
**Type:** Interrupt handler (processes event queue)

### Event Routing Table

| Event Type | Event Name | Dwarf Response | Switch Script |
|---|---|---|---|
| 19 | Query event | Check condition 9 | (stay) |
| 23 | Class event | Kill all models if target is class 56 | (conditional death) |
| **3** | **Threat detected** | **React to threat, charge** | **159** |
| **4** | **Target event** | **Take event target, close combat** | **158** |
| 27 | Custom event 27 | Send event 25 to self | (self-signal) |
| **12** | **Friendly unit routed (type A)** | **Enter reactive mode, flee** | **162** |
| **13** | **Friendly unit routed (type B)** | **Enter reactive mode, flee** | **162** |
| **7** | **Charged by enemy** | **Fear/morale check, hold position** | **161** |
| **15** | **Enemy routed** | **Pursue routed enemy** | **164** |
| (default) | Other events | Call shared subroutine handler | **152** |

**Key observation:** 9 out of 10 top-level event types trigger specific tactical behaviors, showing that dwarf units are highly event-responsive and have distinct reaction types.

---

## Behavior Tree: Related Library Scripts

### Script 158 — Close Combat Mode

**Triggered by:** Event 4 (target event)  
**Behavior:** Engage in single combat

```
Query 5                          ← Check some condition
SendEventToParent 20             ← Alert parent/leader
WaitWhileUnitFlags 0x4008        ← Wait until ready
React 1                          ← Reactive combat mode
MoveToTarget
ReformBlock                       ← Tight formation
Loop {
  SetWait 10
  If TargetInChargeReach → Switch to Script 160 (charge)
  TestUnitFlags 16 (routed?)
  If routed → Restart
  RefreshRouteToTarget            ← Keep moving toward enemy
}
```

**Tactical role:** Primary melee engagement; maintains formation block and reformats during movement. Transitions to charge (Script 160) when within close range.

### Script 159 — Targeted Assault

**Triggered by:** Event 3 (threat detected)  
**Behavior:** Seek and attack specific target

```
SendEventToOwnSide 19            ← Alert friendly units (unit attack message?)
React 1                          ← Reactive mode
ReformBlock                       ← Tight formation
MoveToTarget                      ← Chase target
Yield
WaitWhileUnitFlags 8             ← Wait until not routed
Loop {
  SetWait 10
  If TargetInChargeReach → Switch to Script 160 (charge)
  RefreshRouteToTarget
  TestUnitFlags 16 (routed?)
  If not routed → Loop to Script 159
}
```

**Tactical role:** Hunting; similar to Script 158 but maintains formation alertness (WaitWhileUnitFlags). Charges when close enough.

### Script 160 — Charge Execution

**Triggered by:** Transition from Scripts 158/159 (when target in close reach)  
**Behavior:** Execute charge attack

```
ChargeTarget
If {
  React 2
  Query 24
  PushPC
  Yield
  MoveUnitSound 0
  TestUnitFlags 16 (routed?)
  If not routed → Loop
} Else {
  GotoScript 163 (idle)
}
```

**Tactical role:** Explosive close-range attack; sound effect on impact. Returns to idle if charge succeeds or routed.

### Script 161 — Hold & Reform

**Triggered by:** Event 7 (charged by enemy / fear morale check)  
**Behavior:** Stand ground, face enemy

```
Query 7                          ← Check condition 7 (morale/fear?)
HaltAndReform
PushPC
Yield
FaceModelsToTarget               ← Turn to face attacker
Loop {
  SetWait 20                      ← Long wait between actions
  Loop
}
```

**Tactical role:** Defensive stance; dwarves hold ground when charged instead of routing immediately. Used for morale management and formation integrity.

### Script 162 — Flee / Panic

**Triggered by:** Event 12/13 (friendly unit routed, panic spread)  
**Behavior:** Flee from position

```
FleeFromTarget
SkipIfTrue 1 → 4
FleeAhead                        ← Flee in panic direction
PushPC
Yield
Loop
```

**Tactical role:** Morale cascade; when allies rout, dwarves enter panic mode and flee. The SkipIfTrue suggests conditional escape (fleeing only if routed).

### Script 163 — Idle / Waiting

**Transition to:** Default safe state  
**Behavior:** Wait for orders or threats

(Likely a simple wait loop, not fully disassembled here, but referenced as idle state)

### Script 164 — Pursue Routed Enemy

**Triggered by:** Event 15 (enemy routed)  
**Behavior:** Chase fleeing enemy

```
LeaveSharedGrid                  ← Break formation
ReformToScriptRanks              ← Re-cluster units
React 3                          ← Pursuit mode
Query 1                          ← Check if pursuit worthwhile
If ThreatOutweighsWorth {
  SendEventSelfIfTrue 3          ← Self-signal
  YieldIfTrue
}
StartPursuit
PushPC
Yield
Loop
```

**Tactical role:** Pursuit after victory; dwarves chase defeated enemies but only if it's tactically sound. LeaveSharedGrid suggests breaking off formation for pursuit.

### Script 152 — Comprehensive Event Handler (Gosub)

**Called by:** Script 151 (via Gosub) for non-primary events  
**Behavior:** Handle 20+ secondary event types

Processes events: 50, 48, 54, 1, 25, 26, 9, 14, 22, 24, 2, 5, 11, 10, 8, 16, 28, 29, 17, 45

**Notable secondary behaviors:**
- Event 1 (restart): Restart current script
- Event 10 (grid engagement): Switch opponent or change target
- Event 17: Set reinforcement flag (CondFlags 16) — triggers reinforcement gate
- Event 45: Special morale/condition event; clear flags and call script 133
- Event 54: Objective event; possible side change (SetSide 64) for objective completion
- Event 50: Switch to script 168
- Event 48: Leave shared grid formation

---

## Dwarf Mission Presence

### Using Script 151 (Shared Library Dwarves)

| Mission | Dwarf Unit Count | Notes |
|---|---|---|
| BF010 | 1 dwarf ally | First dwarf mission; introduces library behavior |
| BF011 | 1 dwarf ally | Continues library behavior from BF010 |
| BF016 | 2 dwarf allies | Multiple dwarf units using shared script 151 |
| BF036 | 2 dwarf allies | Late-game dwarf deployment |

### NOT Using Script 151

| Mission | Unit Type | Interrupt Scripts Used |
|---|---|---|
| BF014 | Dwarves (?) | Scripts 9, 10, 11 (mission-specific, not library) |
| BF015 | Mercenaries, wizards | Scripts 32–35 (different unit types) |
| BF017 | Mercenaries, wizards | Scripts 35–36 (different unit types) |

**Interpretation:** Dwarf units have a **standardized behavior library (Scripts 151–170)**, but different unit types (mercenaries, wizards, other NPCs) use their own interrupt scripts (32–36+). This suggests **a modular behavior library architecture** where unit types share behavior trees.

---

## Behavior Tree Summary

```
Script 151 (Dwarf Interrupt)
├─ Event 3 (threat) → Script 159 (assault)
│  └─ Close range → Script 160 (charge)
│     └─ Success → Script 163 (idle)
├─ Event 4 (target) → Script 158 (combat)
│  └─ Close range → Script 160 (charge)
├─ Event 7 (charged) → Script 161 (hold ground)
├─ Event 12/13 (routed) → Script 162 (flee)
├─ Event 15 (enemy routed) → Script 164 (pursue)
└─ Other events → Script 152 (gosub handler)
   ├─ Event 17 → Set reinforcement flag
   ├─ Event 54 → Objective handling (side change)
   ├─ Event 50 → Script 168
   └─ (15+ other events)
```

---

## Key Insights

### 1. Shared Library Architecture

Script 151 is **not mission-specific** — it's a reusable library script used across multiple campaigns/missions. This shows the engine supports:
- **Library scripts** (100–170 range) separate from mission scripts (0–37)
- **Shared behavior trees** for common unit types (dwarves)
- **Parameterized tactics** (React modes 1–17, Query conditions, tactical state)

### 2. Event-Driven State Machine

Dwarves respond to **10+ event types**, each triggering distinct tactical behavior:
- **Offensive:** Threat → assault, target → combat, charge → melee
- **Defensive:** Charged → hold ground, routed → flee
- **Morale:** Enemy routed → pursue, reinforcements → flag update
- **Objectives:** Objective reached → side switch (script 152, event 54)

This is more sophisticated than simple "attack nearest" AI. Dwarves have **tactical reasoning** about threats, morale, formations, and objectives.

### 3. Reactive Modes

Dwarves switch between multiple reactive modes (React 1–17):
- React 1: Combat mode
- React 2: Charge impact mode
- React 3: Pursuit mode
- React 4, 6: Panic/rout modes
- React 17: Fear/caution mode

**React modes** likely modify AI aggressiveness, formation tightness, and risk tolerance.

### 4. Formation Management

Dwarf scripts reference:
- `ReformBlock` — maintain tight combat formation
- `LeaveSharedGrid` — break formation for pursuit
- `ReformToScriptRanks` — re-cluster after breaking up
- `HaltAndReform` — defensive formation

This shows **formation coherence** is part of dwarf behavior (unlike generic enemies which have simpler AI).

### 5. Unit Types & Behavior Diversity

Early missions (BF010, BF011, BF016, BF036) use **standardized dwarf library (script 151)**. Later missions use **different libraries:**
- Mercenaries (scripts 32–36) — different behavior tree
- Wizards (scripts 32–36) — different behavior tree
- Other NPCs — mission-specific scripts

This suggests the engine has **unit-type-specific behavior libraries** that can be mixed and matched in missions.

---

## Open Questions

1. **Script 168, 170, 165, 163:** What do the other related library scripts do? (Would need BF010+ scripts from 165–170 range)

2. **React modes 1–17:** How do React modes modify base behavior? Are they aggressiveness settings, formation tightness, or risk tolerance?

3. **Query conditions 1, 7, 9, 23, 24:** What do these query conditions check? Morale? Fatigue? Threat assessment?

4. **Mercenary/Wizard libraries:** Do BF015/BF017 use similar event-driven libraries (scripts 32–36), or different architecture?

5. **Event sources:** What engine systems generate events 3, 4, 7, 12, 13, 15? Are they from collision detection, morale systems, objective tracking?

6. **Objective side-switch (event 54):** When dwarves reach certain objectives, they can switch sides (SetSide 64). Is this used in campaign progression?

---

## Data Sources

- `whshr/behaviour.py` — bytecode disassembler (scripts 151–164 extracted)
- Mission files: BF010.DLL, BF011.DLL, BF016.DLL, BF036.DLL (script 151 reference)
- Related research: `notes/neutral_units.md` (dwarf type codes), `notes/mission_walkthroughs_BF010.md` (BF010 mission context)

---

## Conclusion

**Script 151 is a production-quality behavior library** for dwarf units across multiple campaign missions. It demonstrates that:

1. The original game has **reusable behavior libraries** (scripts 100–170) separate from mission scripts
2. Dwarves have **event-driven tactical AI** with distinct modes (assault, combat, hold, flee, pursue)
3. **Unit types have specialized behavior trees** (dwarves use 151–164+, mercenaries use 32–36)
4. **Formation management** is integrated into behavior scripts (ReformBlock, LeaveSharedGrid)
5. **Objectives can trigger behavior changes** (side switching on objective reach)

This research reveals a sophisticated, modular behavior system that enables rich NPC unit interactions beyond simple "attack nearest" AI.

