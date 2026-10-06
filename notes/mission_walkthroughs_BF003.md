# Mission Walkthrough: BF003 — Protect Schnappleburg

**Campaign Mission:** 3  
**Mission Title:** Protect Schnappleburg  
**Objective:** Defend three peasant groups from enemy attack

---

## Battle Overview

**Battlefield:** 1440 × 1680 (moderate size)  
**Enemy Army:** 2 units (Goblin Stickers, Goblin Wolfriders)  
**Neutral Forces:** 3 peasant groups scattered across the field  
**Key Mechanic:** Two-phase enemy attack with hidden reinforcements

---

## Enemy Forces

### Phase 1: Goblin Stickers (Leader)
- **Unit Type:** Melee infantry
- **AI Behavior:** Aggressive (TrackThreat), threat range 240
- **Tactics:** Attacks nearest visible enemy immediately upon battle start
- **Role:** Initial assault force; should be dealt with quickly

### Phase 2: Goblin Wolfriders (Hidden Reinforcement)
- **Unit Type:** Fast cavalry
- **Script trigger:** `MoveToNode 2` follows a 60-tick wait after battle start (nominally ~6 seconds at 100 ms/tick)
- **Deployment Location:** Node 2
- **AI Behavior:** Aggressive (TrackThreat), threat range 400 (wider than Stickers)
- **Tactics:** Flanking cavalry attack after initial melee starts
- **Strategic Impact:** Reinforcements force player to split attention or have reserves ready

---

## Peasant Positions & Behavior

The three peasant groups are non-combatants that must be protected. They are positioned at different locations:

| Peasant Group | Position | Behavior | Script |
|---|---|---|---|
| Peasant 1 | Node 2 | Patrols around node 2; non-aggressive | Script 2 |
| Peasant 2 | Node 4 | Patrols around node 4; non-aggressive | Script 3 |
| Peasant 3 | Node 3 | Patrols around node 3; non-aggressive | Script 4 |

**Peasant Characteristics:**
- Non-combatant units (cannot attack enemy)
- Will likely flee if attacked or routed
- Must survive the battle duration to complete the objective
- Spread across nodes 2, 3, 4 (central and nearby field positions)

---

## Mission Timeline

### 0:00 — Battle Start

**Goblin Stickers** move to Node 0 (likely center or enemy deployment area) and begin attacking the nearest visible enemy. The player must respond immediately to counter this threat.

**Peasants** scatter around their assigned nodes and enter patrol behavior.

### ~0:06 (60 ticks) — Wolfrider Move Order

**Goblin Wolfriders** receive `MoveToNode 2` after the wait. The static script establishes the order time, not the exact position or visibility at that instant. They have a wider threat range (400 vs. Stickers' 240).

### Ongoing Combat

The player must manage two priorities:
1. **Eliminate the initial Stickers threat** before Wolfriders arrive (if possible)
2. **Defend the peasants** at nodes 2, 3, 4 from incoming cavalry and pursuit

---

## Strategic Observations

### Enemy AI

- **Initial Phase (before the Wolfrider move order):** Stickers apply focused pressure
- **After the Wolfrider move order:** Cavalry with wider threat range forces spread defense
- **Both units use TrackThreat behavior,** meaning they will pursue routed enemies and seek highest-threat targets

### Peasant Vulnerability

- The peasants occupy nodes 2, 3, 4 and do not move far from these positions
- They do not engage in combat, so they depend entirely on player protection
- If surrounded or routed, they will likely flee off-table (triggering leave-the-table rule)

### Recommended Tactics

1. **Early Response:** Deploy forces to meet Stickers immediately and prevent it from reaching peasant positions
2. **Anticipate Reinforcements:** Position reserves or keep forces in reserve; the Wolfrider move order is scripted after 60 battle ticks (~6 seconds nominally)
3. **Protect Central Nodes:** Peasants at nodes 2 and 3 are closest to expected cavalry approach; prioritize defense there
4. **Block Routes:** Use terrain and unit positioning to channel enemy forces away from peasant clusters

---

## Victory Condition

The mission objective is likely: **Protect all three peasant groups until the end of the battle.**

A unit is considered protected if:
- It remains on the battlefield (does not cross BattleEdge boundary while routed)
- It is not eliminated (health > 0)
- It is not permanently routed off-field

---

## Data Sources

- **Battle File:** `BF003.BTS` (1440×1680 field, 14 nodes, 3 NPC units, 2 enemy units)
- **Mission Scripts:** Bytecode disassembled from `SCRIPT/BF003.DLL` (scripts 0–4)
- **Script Format:** Warhammer SotHR behavior bytecode (232 opcodes, per-unit state machine)

---

## Open Questions (For Gameplay Verification)

1. **Exact peasant victory condition:** Do all 3 peasants need to survive, or a majority?
2. **Casualty counting:** When a peasant is killed, is it counted in debrief, or ignored?
3. **Morale effects:** Do peasants route if friends are killed nearby?
4. **Rally behavior:** Can routed peasants rally, or do they flee immediately?
5. **Time limit:** Is there a turn limit, or does the battle end when enemies are defeated?
