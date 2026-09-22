# Mission Walkthrough: BF005 — Escort the Refugees

**Campaign Mission:** 5  
**Mission Title:** Escort (likely refugees or supplies)  
**Objective:** Protect cargo units as they traverse the battlefield to safety

---

## Battle Overview

**Battlefield:** Player must defend mobile objectives  
**Enemy Army:** 3 combat units with staggered reinforcement arrival  
**Cargo Units:** 2 non-combatant units attempting escape from Node 2 to Node 8  
**Key Mechanic:** Phased enemy reinforcements while defending slow-moving cargo

---

## Cargo Units (Objectives to Protect)

### Cargo Unit 1 (Script 3)
- **Unit Type:** Non-combatant wagon/refugees
- **Tagged As:** 0xabc0 (specific identification for enemy targeting)
- **AI Behavior:** Defensive/escort (AI type 13)
- **Movement Pattern:**
  1. Start at deployment
  2. Move to Node 2 (initial rally point)
  3. Wait until routed/under heavy threat (UnitFlags 16)
  4. Move to Node 8 (escape point)
  5. Set escape flag (0x1000)
  6. **RemoveFromBattle** — successfully evacuated
- **Threat Range:** 240 (detection only, non-combatant)

### Cargo Unit 2 (Script 4)
- **Unit Type:** Non-combatant wagon/refugees
- **AI Behavior:** Defensive/escort (AI type 13)
- **Movement Pattern:** Identical to Unit 1
  1. Move to Node 2
  2. Wait until routed/under threat
  3. Move to Node 8 (escape)
  4. Set escape flag
  5. **RemoveFromBattle** — successfully evacuated

**Key Observation:** Cargo units will not move to escape point until they sense combat (routed). They attempt to shelter at Node 2 first, then flee to Node 8 once threatened.

---

## Enemy Forces (Timed Reinforcement)

### Enemy Unit 1 (Script 0) — Immediate Deployment
- **Arrival Time:** Battle start (0:00)
- **AI Behavior:** TrackThreat (aggressive, AI type 15, variant 28)
- **Threat Range:** 240
- **Initial Tactic:** Attack nearest enemy immediately, then patrol
- **Movement Pattern:** Attack → if no enemy visible, move to Node 5 → attack → wait 15 ticks → move to Node 6 → repeat
- **Secondary Target:** Attacks enemy class 56 if no standard enemies visible (likely artillery or special units)
- **Timing:** 10 ticks between combat checks, 15 ticks between moves

### Enemy Unit 2 (Script 1) — Delayed Arrival 1
- **Arrival Time:** 350 ticks after battle start (~52.5 seconds)
- **AI Behavior:** TrackThreat (aggressive, AI type 15, variant 29)
- **Special Trigger:** **Attacks tagged unit (0xabc0)** — specifically targets the cargo units!
- **Movement Pattern:** Same as Unit 1, but with intentional focus on cargo
- **Threat Priority:** Hunts cargo units (by tag), then standard enemies, then class 56
- **Danger Level:** HIGH — this unit is explicitly programmed to hunt the objectives

### Enemy Unit 3 (Script 2) — Delayed Arrival 2
- **Arrival Time:** 430 ticks after battle start (~64.5 seconds)
- **AI Behavior:** TrackThreat (aggressive, AI type 15, variant 30)
- **Threat Range:** 240
- **Pattern:** Similar to Unit 1, patrols nodes 5/6
- **Timing:** 10 ticks between checks, 15 ticks for patrolling
- **Role:** Third wave of pressure once cargo nears escape point

---

## Mission Timeline

### 0:00 — Battle Start

**Enemy Unit 1** becomes active and begins attacking the nearest enemy force.  
**Cargo Units** move to Node 2 (shelter/rally point) and await further orders.  
**Player must** engage and suppress Enemy Unit 1 before it breaks through to cargo.

### 0:52.5 (350 ticks) — First Reinforcement Arrives

**Enemy Unit 2** emerges. This unit is specifically programmed to attack the cargo (tagged 0xabc0).  
**Cargo Units** remain sheltered at Node 2 if combat is ongoing; they will flee to Node 8 once routed/threatened.  
**Player must** intercept Unit 2 or the cargo will be overrun.

### 1:04.5 (430 ticks) — Second Reinforcement Arrives

**Enemy Unit 3** enters the field as a third wave.  
**Cargo Units** (if still alive) may be in transit from Node 2 to Node 8.  
**Danger:** Player now faces 3 enemy units while protecting mobile targets.

### End — Escape

Once cargo units reach Node 8 and execute **RemoveFromBattle**, they are successfully evacuated. The player's primary objective is complete, though the battle may continue against remaining enemy forces.

---

## Strategic Observations

### Enemy Design

- **Unit 1** = immediate threat, generalist
- **Unit 2** = cargo-specific hunter, arrives mid-battle
- **Unit 3** = finishing wave, arrives as cargo approaches escape

The three-wave reinforcement forces the player to:
1. Deal with initial aggression (Unit 1)
2. Pivot to protect cargo from hunter (Unit 2)
3. Push through a third wave while escorting (Unit 3)

### Cargo Behavior

- Cargo units do **not** flee immediately; they shelter at Node 2 first
- They only move to escape (Node 8) when they detect threat (routed flag)
- Once removed from battle, they are safe; no more interaction possible

This creates a **puzzle**: the player must let the cargo sense danger (draw enemy attention) without actually destroying the cargo.

### Movement Geometry

- **Node 2:** Shelter/rally point (safe zone)
- **Node 5/6:** Enemy patrol route (between player and cargo)
- **Node 8:** Escape point (off-field)

The player should establish a defensive line between nodes 5/6 and node 2 to block enemy access to cargo.

---

## Recommended Tactics

1. **Early Aggression:** Eliminate or pin Enemy Unit 1 immediately to prevent it from reaching Node 2
2. **Prepare for Unit 2:** Around 50 seconds, be ready for a second assault specifically targeting cargo
3. **Establish Corridor:** Keep nodes 5/6 clear of enemies to allow cargo safe passage to Node 8
4. **Coordinate Escort:** Once cargo moves from Node 2 to Node 8, provide cover for their transit
5. **Leverage Timing:** The 52-second gap between Unit 1 and Unit 2 arrival is an opportunity to reposition or reinforce defenses

---

## Comparison with Earlier Missions

| Aspect | BF003 | BF004_1 | BF005 |
|---|---|---|---|
| Mission Type | Defense (protect civilians) | Direct combat (defeat + protect) | Escort (protect moving targets) |
| Enemy Units | 2 | 2 | 3 (phased arrival) |
| Cargo Behavior | Static, scattered | Static, scattered | Mobile (Node 2 → 8) |
| Cargo Escape | Stand and fight | Stand and fight | **Flee to escape point** |
| Reinforcements | One wave | None | Two waves (times 350, 430 ticks) |
| Difficulty | Moderate | Moderate-High | High (mobile defense + phased enemies) |

---

## Victory Condition

Success requires:
1. **Both cargo units successfully escape** to Node 8 and execute **RemoveFromBattle**
2. Player forces remain capable (sufficient morale to continue if additional battles follow)

Failure conditions:
- Either cargo unit is destroyed before reaching Node 8
- Cargo unit is routed off-field (escape route blocked)

---

## Data Sources

- **Battle File:** `BF005.BTS` (mission 5)
- **Mission Scripts:** Bytecode disassembled from `SCRIPT/BF005.DLL` (scripts 0–5)
- **Script Format:** Warhammer SotHR behavior bytecode (232 opcodes, per-unit state machine)

---

## Bytecode Semantics (Advanced)

For engine implementers, note these opcodes:

- **AttackTagged 0xabc0:** Unit 2 specifically targets units marked with tag 0xabc0 (the cargo)
- **SetUnitFlags2 2048, 0x1000:** Status flags for escape progression (checkpoint reached, escape complete)
- **RemoveFromBattle:** Permanently removes the unit from the battle once escape point is reached
- **WaitUntilUnitFlags 16:** Cargo waits for routed flag before initiating escape (threat detection)

This demonstrates that mission scripts use **tagging** to identify specific objectives and **flag sequences** to track progression through multi-stage mission events.

