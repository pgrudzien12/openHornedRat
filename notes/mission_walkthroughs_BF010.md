# Mission Walkthrough: BF010 — The Dwarf Alliance

**Campaign Mission:** 10  
**Mission Title:** Dwarven Reinforcement (or similar)  
**Objective:** Coordinate with dwarf allies against enemy forces

---

## Battle Overview

**Battlefield:** Player forces + dwarf allies vs. enemy army  
**Player + Allied Units:** 2 units (including dwarf ally with support)  
**Enemy Army:** 4 units with complex coordination  
**Key Mechanic:** Formation management, parent-child unit relationships, tactical positioning

---

## Allied Forces (Player Army + Dwarves)

### Allied Unit 0 (Script 0) — Dwarf Warrior / Support
- **Unit Type:** Non-combatant support (init size 64)
- **AI Behavior:** **Type 11** (defensive/support, distinct from combat)
- **Threat Range:** 240
- **Pattern:**
  1. **React 20** — reactive mode (responds to threats, not seeking)
  2. If threatened or during combat: Patrol nodes 8 and 9
  3. Wait 10 ticks between actions
- **Interrupt Handler:** Script 151 (library script for support behavior)
- **Role:** Defensive support that remains passive until engaged

### Allied Unit 1 (Script 1) — Support Companion
- **Unit Type:** Tiny unit (init size 64, flags 256 = anchored)
- **AI Behavior:** Movement-only (FollowParent)
- **Tag:** 0xabc0 (identification tag)
- **Threat Range:** 80 (very close, likely detection range for leader)
- **Pattern:**
  1. WaitForBattleStart
  2. **FollowParent 36** — continuously follows unit tagged 0xabc0 at distance 36
  3. Loop every 6 ticks (very tight synchronization)
- **Role:** Support unit that stays glued to main combat unit; likely carries supplies, standards, or tactical support

---

## Enemy Forces

### Enemy Unit 0 (Script 2) — Primary Attack Force
- **Unit Type:** Infantry (init size 128)
- **AI Behavior:** TrackThreat variant 28
- **Threat Range:** 240
- **Pattern:**
  1. Attack nearest enemy (continuous loop, 10-tick intervals)
  2. If no visible enemy: Move to Node 11, patrol
  3. Attack while patrolling
  4. Repeat with 15-tick intervals during patrol
- **Interrupt Handler:** Script 7
- **Role:** Direct assault force

### Enemy Unit 1 (Script 3) — Coordinated Commander
- **Unit Type:** Leader/commander (init size 128)
- **Tag:** 0xabc1 (identifies this unit)
- **AI Behavior:** TrackThreat variant 29
- **Threat Range:** 240
- **Movement Pattern:**
  1. **WaitWhileUnitFlags 8** — wait until NOT routed (routed = flag 8)
  2. Move to Node 6, wait until routed or threatened (UnitFlags 16)
  3. Move to Node 5, wait until routed/threatened
  4. Once at Node 5: Attack nearest enemy (15-tick loop)
- **Role:** Tactical leader positioning units and controlling approach

### Enemy Unit 2 (Script 4) — Formation Follower
- **Unit Type:** Combat (init size 128)
- **Tag:** 0xabc2 (identifies this unit)
- **Parent Link:** **SetParentByTag 0xabc1** — follows Unit 1 (the commander)
- **AI Behavior:** TrackThreat variant 30
- **Pattern:**
  1. WaitWhileUnitFlags 8 (wait until rally)
  2. Move to Node 6 (mirrors Unit 1's path)
  3. Move to Node 10 (different destination, but coordinated timing)
  4. Wait 100 ticks between actions
- **Role:** Flanking unit coordinated with commander; slower/more cautious movement

### Enemy Unit 3 (Script 5) — Skirmisher / Archer
- **Unit Type:** Combat (init size 128)
- **AI Behavior:** TrackThreat variant 33 (**unique to this unit**)
- **Threat Range:** 240
- **Special Tactic:** **AttackNthNearestEnemy 2**
  - Attacks the **second-nearest** enemy, not the first
  - Useful for ranged units that support main combatants
  - Allows focus fire on secondary targets or support units
- **Pattern:** Loop every 10 ticks, targeting second-nearest
- **Interrupt Handler:** Script 7
- **Role:** Skirmisher or ranged support; doesn't always attack closest threat

---

## Strategic Observations

### Formation & Coordination

**Enemy Formation:**
- Unit 1 (commander) positions at Node 6 → 5
- Unit 2 (follower) coordinates via parent link (SetParentByTag)
- Unit 3 (skirmisher) independent but with tactical role (second-target focus)
- Unit 0 (assault) direct attack path to Node 11

This shows a **three-tier enemy structure**:
1. **Commander** (Unit 1): Sets tempo, controls rallying
2. **Follower** (Unit 2): Mirrors commander's positioning, flanking angle
3. **Support** (Unit 3): Independent tactical target priority
4. **Assault** (Unit 0): Direct engagement, no coordination

### Allied Response

**Player Formation:**
- Main combat unit (tagged 0xabc0 — likely player commander)
- Support companion (follows main unit with distance 36)
- Dwarf ally (defensive support, uses library script 151)

The dwarf ally's AI type 11 and React mode suggest **tactical defense** — dwarves may have a distinct combat doctrine (holding ground vs. pursuing enemy).

### Parent-Child Relationships

**BF010 demonstrates two linking types:**

1. **SetParentByTag:** Enemy Unit 2 follows commander (Unit 1)
   - Used for **coordinated formation advance**
   - Follower mirrors parent's positioning
   - Both wait for routed flag (synchronized rallying)

2. **FollowParent:** Allied companion follows main unit
   - Used for **tight support** (distance 36, every 6 ticks)
   - Likely represents standard-bearer, healer, or ammo carrier
   - Very high sync rate (6 ticks vs. 10-15 tick combat intervals)

### Tactical Variety

The **AttackNthNearestEnemy 2** opcode (used by Unit 3) is the first instance of target discrimination by order:
- Allows ranged/support units to avoid "overkilling" one target
- Enables focus-fire on priority targets
- Supports asymmetric combat (some units ignore main threat)

---

## Bytecode Patterns

### Formation Following
```
SetParentByTag 0xabc1       ← Link to unit with tag 0xabc1
WaitWhileUnitFlags 8        ← Synchronize rallying (wait until parent rallies)
MoveToNode 6                ← Parent moves here
MoveToNode 10               ← Follower goes to different node (flanking)
```

This shows **asymmetric formation movement** — units coordinate timing but use different routes.

### Support Unit Attachment
```
FollowParent 36             ← Stay 36 units behind main unit
SetWait 6                   ← Check every 6 ticks (tight sync)
Wait
Loop
```

This pattern keeps support units tightly synchronized with main unit for leadership/logistics support.

### Tactical Targeting
```
AttackNthNearestEnemy 2     ← Attack second-nearest, not first
SetWait 10                  ← Consistent 10-tick intervals
Wait
Loop
```

This pattern allows **role-specific targeting** — skirmishers/ranged support avoid redundant overkill.

---

## Comparison with Earlier Missions

| Aspect | BF001 (Tutorial) | BF005 (Escort) | **BF010 (Alliance)** |
|---|---|---|---|
| Ally Units | None | Cargo (NPC) | Dwarf (allied AI type) |
| Formation Complexity | Single enemy | Isolated objectives | **Multi-unit coordinated formation** |
| Tagging Usage | Event-based | Cargo hunting | **Formation coordination** |
| AI Variety | Variants 28–30 | Variants 28–30 | **Variants 11, 28–30, 33** |
| Support Mechanics | None | None | **FollowParent, SetParentByTag** |

---

## New Concepts Introduced

### AI Type 11 (Defensive/Support)
- First observation of an AI type other than 13–15
- Used for dwarf ally (reactive, defensive)
- Suggests distinct unit role support in engine

### AI Type 33 (Tactical/Skirmish)
- First specialized variant for role-specific behavior
- Used for second-target hunting
- Implies AI types can encode unit roles (infantry vs. cavalry vs. ranged)

### Library Script 151
- Used by dwarf ally as interrupt handler
- Suggests **shared behavior libraries** for common unit types
- Earlier missions used scripts 4–7 (mission-specific)
- Script 151 likely defines "dwarf support" behavior universally

### UnitFlags 8 (Routed Flag)
- Used in WaitWhileUnitFlags 8 (wait until NOT routed)
- Synchronizes unit movement with rally status
- Enemy units won't advance if routed (coherent formation tactics)

---

## Mission Objectives

Likely requires:
1. **Survive coordinated multi-wave enemy attack**
2. **Protect dwarf ally** (casualties may fail mission)
3. **Defeat all enemy forces or achieve territorial objective**
4. **Coordinate dwarf formations** (may need to hold positions or support player advance)

---

## Data Sources

- **Battle File:** `BF010.BTS` (mission 10, dwarf alliance)
- **Mission Scripts:** Bytecode disassembled from `SCRIPT/BF010.DLL` (scripts 0–5)
- **Library Scripts:** Script 151 (dwarf support behavior, shared library)
- **Script Format:** Warhammer SotHR behavior bytecode (232 opcodes, per-unit state machine)

---

## Advanced Implementation Notes

**For Behavior Interpreter:**

1. **Linked Units:** Engine must support SetParentByTag creating runtime links between units (not just static references)

2. **AI Type Dispatch:** New AI types (11, 33) require distinct behavior handlers. Engine needs flexible AI type→behavior mapping.

3. **Tight Synchronization:** FollowParent 36 updates every 6 ticks (0.6 seconds). Engine must support frequent position syncing for support units.

4. **Conditional Formation Movement:** Units can wait for parent (or sibling) conditions before advancing. Movement isn't blind — it's coordinated.

5. **Library Scripts:** Interrupt handlers can reference scripts outside mission scripts (151 is shared library). Engine must load scripts from multiple DLLs.

---

## Open Questions

1. **Dwarf Alliance Progression:** How do dwarf units become available? Campaign recruitment? Previous mission outcome? This is the first allied NPC unit mission.

2. **Library Script 151:** What does dwarf support script 151 do? Is it shared across all dwarf units in other missions (BF011, BF014, etc.)?

3. **Formation Coherence:** When follower (Unit 2) and commander (Unit 1) have different destinations (nodes 6 vs. 10), what determines spatial coherence? Do they reunite?

4. **Casualty Consequences:** If dwarf ally is killed, does the mission fail, or does it continue with reduced support?

5. **Second-Target Logic:** Is AttackNthNearestEnemy 2 unique to ranged units, or is it available as a general tactic?

