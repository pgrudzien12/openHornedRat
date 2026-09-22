# Mission Walkthrough: BF004 — Breaking Through

**Campaign Mission:** 4  
**Variants:** BF004_1, BF004_2, BF004_4  
**Mission Title:** Breaking Through (or similar)  
**Objective:** Defeat enemy forces while protecting fleeing civilians

---

## Battle Overview (BF004_1 Variant)

**Battlefield:** Player-controlled army vs. occupying enemy force  
**Enemy Army:** 2 combat units  
**Neutral Forces:** 2 peasant groups  
**Key Mechanic:** Defend civilians while fighting for battlefield control

---

## Enemy Forces

### Enemy Unit 1 (Script 2)
- **AI Behavior:** TrackThreat (aggressive)
- **Threat Range:** 240
- **Initial Position:** Node 12
- **Tactics:** 
  - Start: Attack nearest visible enemy
  - After initial contact: Attack nearest enemy or NPC flag40 units
  - Wait timing: 15 ticks between attacks, then 10 ticks for pursuit

### Enemy Unit 2 (Script 3)
- **AI Behavior:** TrackThreat (aggressive)
- **Threat Range:** 240
- **Initial Position:** Node 12
- **Tactics:** 
  - Similar to Unit 1, but with conditional attack logic
  - Uses Query 3 (likely morale/threat assessment)
  - More cautious pursuit pattern; waits for threat evaluation before attacking NPC units

---

## Peasant Groups (Civilians to Protect)

### Peasant Group 1 (Script 0)
- **Position:** Node 2
- **Behavior:** Non-combatant scatter
- **AI Type:** 14 (defensive, non-hostile)
- **Pattern:** Scatters around node 2, waits 20 ticks, repeats
- **Threat Range:** 240 (detection range only)
- **Status:** Will not engage in combat; must be protected

### Peasant Group 2 (Script 1)
- **Position:** Node 1
- **Behavior:** Non-combatant scatter
- **AI Type:** 14 (defensive, non-hostile)
- **Pattern:** Scatters around node 1, waits 21 ticks, repeats
- **Threat Range:** 240 (detection range only)
- **Status:** Will not engage in combat; must be protected

---

## Mission Timeline

### 0:00 — Battle Start

**Enemy units** move to Node 12 and begin seeking the player's forces. They attack the nearest visible target immediately.

**Peasants** scatter to their defensive positions (nodes 1 and 2) and enter patrol mode.

### 0:00 to End — Continuous Defense

Both enemy units maintain aggressive patrol behavior, attacking any threat (player units or NPC units). The player must:

1. **Engage and eliminate enemy forces** to prevent them from overrunning peasant positions
2. **Protect the two peasant groups** at nodes 1 and 2
3. **Prevent peasants from being routed** — if pursued off-table, they are lost

---

## Strategic Observations

### Enemy Coordination

- Both units deploy to the same location (Node 12), suggesting a coordinated attack
- They use different threat evaluation logic (Unit 2 queries morale before attacking NPCs), indicating tactical variety
- Wait timings (15 ticks for initial, 10 ticks for pursuit) show a rhythm to their attacks

### Peasant Vulnerability

- **Peasants at nodes 1 and 2** are relatively close to enemy starting position (Node 12)
- **No reinforcements or retreats** are scripted — the engagement is direct from the start
- **Peasants have no combat AI** — they depend entirely on player protection

### Battle Characteristics

Unlike BF003 (which has a reinforcement wave), BF004_1 is a **simultaneous clash**:
- All forces present from the start
- No phased enemy arrival
- Player must manage divided attention immediately (combat + defense)

---

## Recommended Tactics

1. **Immediate Engagement:** Deploy forces aggressively to meet the two enemy units before they reach peasant positions (nodes 1, 2)
2. **Establish a Defensive Line:** Position units between enemy starting area (Node 12) and peasant positions
3. **Prevent Pursuit:** Once enemy units are routed, ensure they flee off-field and don't pursue fleeing peasants
4. **Protect Node Clusters:** Nodes 1 and 2 are the peasant rally points; keep them clear of enemy presence

---

## Comparison with BF003

| Aspect | BF003 | BF004_1 |
|---|---|---|
| Enemy Units | 2 (Stickers, Wolfriders) | 2 (Script 2, Script 3) |
| Peasant Groups | 3 (scattered nodes) | 2 (nodes 1, 2) |
| Enemy Deployment | Phased (reinforcements at 9 sec) | Simultaneous (both at start) |
| Battle Pace | Slow buildup, then rush | Immediate pressure |
| Difficulty | Mid (time to prepare) | Potentially harder (no preparation time) |

---

## Victory Condition

The mission objective is likely: **Defeat all enemy units while protecting both peasant groups.**

Success requires:
- All 2 enemy units eliminated or routed off-table
- Both peasant groups survive (remain on-field)
- Player units remain combat-capable (sufficient morale to continue fighting)

---

## Data Sources

- **Battle File:** `BF004_1.BTS` (mission 4, variant 1)
- **Mission Scripts:** Bytecode disassembled from `SCRIPT/BF004.DLL` (scripts 0–3)
- **Script Format:** Warhammer SotHR behavior bytecode (232 opcodes, per-unit state machine)

---

## Notes

- The BF004 mission exists in multiple variants (BF004_1, BF004_2, BF004_4), each potentially with different unit counts or deployment patterns
- This walkthrough is based on BF004_1's bytecode analysis
- Actual gameplay may reveal additional scripted events (reinforcements, objective changes, morale effects) not visible in the static script bytecode

