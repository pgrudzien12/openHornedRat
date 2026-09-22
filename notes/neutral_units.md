# Neutral Units & Side Relations — Survey Complete

**Status: ✅ Established** — Data-driven analysis of all 54 .BTS files

**Research Date:** 2026-09-23  
**Task:** #8 Survey neutral units  
**Previous blocking issue:** #7 Epic

---

## Executive Summary

**Neutral is a real, distinct third side in SotHR.** The original game has three sides: player, enemy, and neutral/NPC. They are identified by a side code bit flag in the unit data and placed in a dedicated "NPC units" section of `.BTS` files.

- **27 battles** contain 101 NPC-flagged units (out of 54 total)
- **10 battles include peasants** (campaign missions 3–4 and test files)
- **Different NPC categories exist:** peasants, dwarves, mercenaries, wizards, supply units, artillery
- **Behavior is script-driven:** each NPC unit runs a mission-specific behavior script, not a hardcoded neutral AI

---

## Section 1: The Neutral Side Flag

### Data Structure

**Unit side code (s_side[0] byte):**
```
bit 7 (0x80) = ENEMY side flag
bit 6 (0x40) = NEUTRAL / NPC side flag
bits 0-5 (0x3F) = unit type code
```

### Three-Way Side System

| Side | Condition | Range | Examples |
|------|-----------|-------|----------|
| **Player** | bit7=0, bit6=0 | 0x00–0x3F | Player units (Clanrats, Greatswords) |
| **Enemy** | bit7=1 | 0x80–0xBF | Enemy units (Goblins, Skaven) |
| **Neutral/NPC** | bit7=0, bit6=1 | 0x40–0x53 | Peasants, dwarves, cannons, mercenaries |

### Evidence

**All 101 NPC units observed:**
- Side codes range from 0x40 to 0x53
- Bit 6 always set (0x40 present in side code)
- Bit 7 always clear (0x80 absent from side code)
- This is distinct from both player (0x00–0x3F) and enemy (0x80+) ranges

**Interpretation:** The original game recognizes three distinct sides via the bit flags, not a binary player/enemy system.

---

## Section 2: Structural Identification in .BTS Files

### Two UNITS Sections Per Battle

The `.BTS` file format supports two `[UNITS]` sections:
1. **First section** (label: "Enemy Army" or equivalent) — enemy units only
2. **Second section** (label: "NPC units") — NPC-flagged units only

**Example from BF003.BTS:**
```
[UNITS] label='Enemy Army'
  [addunit] name=Goblin_Stickers
    setstats:s_side=139,20,20,4    ; 139 = 0x8B (enemy, type 0x0B)
  [addunit] name=Goblin_Wolfriders
    setstats:s_side=140,12,12,3    ; 140 = 0x8C (enemy, type 0x0C)

[UNITS] label='NPC units'
  [addunit] name=NPC_Peasants
    setstats:s_side=78,5,5,2       ; 78 = 0x4E (neutral, type 0x0E = Peasant)
    set:script=2
  [addunit] name=NPC_Peasants
    setstats:s_side=78,3,3,3       ; 78 = 0x4E (neutral, type 0x0E)
    set:script=3
  [addunit] name=NPC_Peasants
    setstats:s_side=78,4,4,2       ; 78 = 0x4E (neutral, type 0x0E)
    set:script=4
```

**Parsing Hint:** Battles with NPC units have the "NPC units" label in the second UNITS section. This is a human-readable structural marker, not the sole identification method (the s_side bit flag is the authoritative identifier).

---

## Section 3: NPC Unit Categories & Type Codes

### Type Code Ranges (bits 0–5 of s_side)

| Type Code | Count | Unit Categories | Battles |
|-----------|-------|-----------------|---------|
| 0x00 | 41 | Horses, carts, cannons, mortars (generic NPC, side 0x40) | BF005+, various |
| 0x0E | 29 | **Peasants** (side 0x4E) | BF003, BF004, test files |
| 0x04 | 9 | Dwarf Warriors, allies (side 0x44) | BF010, BF011, BF014, BF015, BF016, BF017, BF036 |
| 0x01 | 4 | Black Avengers, Grudgebringer Infantry (side 0x41) | BF015, BF017 |
| 0x02 | 4 | Ragnar's Wolves, Grudgebringer Cavalry (side 0x42) | BF015, BF017 |
| 0x03 | 4 | Mercenary Crossbows (side 0x43) | BF015, BF017 |
| 0x06 | 3 | Ceridan (wizard), Ilmarin (side 0x46) | BF010, BF015, BF017 |
| 0x10 | 3 | Peasants variant (side 0x50, test file) | _KFTEST.BTS |
| 0x13 | 3 | Amber Wizard, Bright Wizard (side 0x53) | BF015, BF017, BF029 |
| 0x08 | 1 | Orc Boyz (side 0x48) | BF016 |

**Key Finding:** NPC type codes are used for categorization. Peasants are type 0x0E; other NPC categories have distinct codes (0x00 for generic, 0x04 for dwarves, 0x13 for wizards, etc.).

### Peasant Presence Across Campaign

**Battles with peasants (type 0x0E, usually side 0x4E):**

| Battle | Campaign Mission | Count | Notes |
|--------|------------------|-------|-------|
| B.BTS | — | 2 | Starting position test file |
| BF003.BTS | Mission 3 (Protect Schnappleburg) | 3 | NPC_Peasants with scripts 2, 3, 4 |
| BF004_1.BTS | Mission 4 variant | 2 | NPC_Peasants |
| BF004_2.BTS | Mission 4 variant | 2 | NPC_Peasants |
| Test files | — | 12+ | RLTEST, WIZTEST, SPRED, _DESTEST, etc. |

**Campaign observation:** Peasants appear prominently in early missions (3–4) and heavily in development test files, suggesting they were a design focus.

### Other Notable NPC Categories

**Dwarven Allies (type 0x04, side 0x44):**
- Appear in late-game missions (BF010, BF011, BF014–BF017, BF036)
- Likely joined by the player through campaign progression
- Treated as combat-capable, allied units

**Mercenaries & Hired Units (types 0x01–0x03, sides 0x41–0x43):**
- Black Avengers, Grudgebringers (cavalry/infantry), Mercenary Crossbows
- Appear in BF015/BF017 (late campaign)
- Likely alternative recruitment options or temporary allies

**Wizards (types 0x06, 0x13, sides 0x46, 0x53):**
- Amber Wizard, Bright Wizard, Ceridan
- Appear in BF015, BF017, BF029 (late-game special forces)
- Treated as NPC-side units

**Supply & Objectives (type 0x00, side 0x40):**
- Horses and carts in escort missions (BF005, BF006, BF015, BF017, BF020)
- Cannons, mortars in defense/hold missions (BF026–BF042)
- Likely objective targets (protect wagons) or supportive AI forces

---

## Section 4: Behavior Scripts & AI

### Script Assignment Pattern

Each NPC unit has an individual `set:script=N` assignment in the `.BTS` file. Example:

```
[UNITS] label='NPC units'
  [addunit] name=NPC_Peasants
    set:script=2          ← This peasant runs script 2
  [addunit] name=NPC_Peasants
    set:script=3          ← This peasant runs script 3
  [addunit] name=NPC_Peasants
    set:script=4          ← This peasant runs script 4
```

**Script Range:** NPC unit scripts are typically 2–8 (test file scripts), or library scripts 100–170 (documented bytecode scripts).

### Behavior Is Script-Driven, Not Flag-Driven

**Key Insight:** The "neutral" flag (bit 6) identifies the side; it does **not** determine behavior. Behavior is determined by the assigned mission script.

**Implications:**
1. Peasants don't flee because they're neutral—they flee because their assigned script calls `RunAway` (opcode 206) or similar
2. Mercenaries don't assist the player because bit 6 makes them allied—they assist because their script has been ordered to do so
3. Wagons don't move because they're NPC—they move because their script orders movement
4. Different instances of the same unit type (e.g., 3 peasants) can have different behaviors by running different scripts (scripts 2, 3, 4)

This is a critical distinction: **the neutral side flag is structural; behavior is behavioral-bytecode-driven.**

---

## Section 5: Implementation Requirements

### Engine Data Model

Current model (insufficient):
```python
regiment.player: bool  # True = player, False = enemy
```

Required model (three-way sides):
```python
class Side(Enum):
    PLAYER = 0       # bit7=0, bit6=0
    ENEMY = 1        # bit7=1
    NEUTRAL = 2      # bit6=1, bit7=0

regiment.side: Side
regiment.type_code: int  # 0x00–0x13 for NPC, varies for others
```

### Parser Changes

```python
# Identify NPC units:
is_npc = (s_side[0] & 0x40) != 0 and (s_side[0] & 0x80) == 0

# Extract side and type:
if is_npc:
    side = Side.NEUTRAL
    type_code = s_side[0] & 0x3F
elif (s_side[0] & 0x80) != 0:
    side = Side.ENEMY
    type_code = s_side[0] & 0x3F
else:
    side = Side.PLAYER
    type_code = s_side[0] & 0x3F
```

### Behavior Handling

1. **Behavior scripts** run unchanged for all three sides (scripts are side-agnostic)
2. **Event routing** must account for three sides:
   - Events sent to "own side" must route only to regiments with the same `Side` value
   - Events sent to "enemy side" must route to opposite sides (PLAYER ↔ ENEMY, but not NEUTRAL unless scripted)
3. **Combat result credits** must be decided:
   - Do kills by NPC units credit to NPC, to the player, or to neither?
   - Do kills of NPC units credit to the killer's side or to a neutral pool?
   - **This is likely script-driven** (determined at mission design time)
4. **Routed unit handling** (from terrain_passability.md):
   - NPC routed units likely follow the same leave-table removal rule as other sides
   - Confirmation needed: do routed peasants leave at the same BattleEdge boundary?

### Campaign Integration

- NPC units in `.MRC` army files are part of the recruiting system (not in scope of this survey)
- Dwarves, mercenaries, wizards appear as joinable units in late-campaign missions
- Peasants are mission-specific objectives/non-combatants, not part of player recruitment
- Campaign-layer side handling (roster, experience, casualties) must account for three sides

---

## Open Questions (For Future Investigation)

1. **Event Routing Detail:** Do NPC units receive events from player units? From enemy units? Test case: does event 0x13 ("friend attacked") route to NPC allies?

2. **Combat Result System:** When a player unit defeats an NPC unit, who gets credit in the debrief? Do NPC unit kills count as casualties or as a separate pool?

3. **Peasant Specific AI:** What scripts do peasants run? Do they flee toward a designated exit, or do they rout normally toward the battlefield edge? Can they rally?

4. **Type Code Semantics:** Are type codes 0x00–0x13 used for AI discrimination (e.g., "type 0x00 = non-combatant, type 0x04 = combat-capable dwarf, type 0x0E = fleeing peasant")? Or are they purely organizational?

5. **Allied NPC Transitions:** When does a neutral unit (e.g., Dwarf Warriors in BF010) become player-allied? Is there a side-switch mechanism beyond objective G's documented 0x100 flag?

6. **Routed NPC Behavior:** Do routed NPC units leave the table via the same `0x20` boundary flag as player/enemy units, or do they have different removal logic?

---

## References

- `notes/engine_gaps/neutral_units.md` — Gap tracker for this research
- `notes/game_rules.md` § "Unit stat fields" — s_side bit layout (bit 7 = enemy, bit 6 = NPC)
- `FORMATS.md` — .BTS UNITS section format (two UNITS sections per battle)
- `notes/terrain_passability.md` — Leave-the-table rule (may apply to NPC routed units)
- `whshr/script.py` — Parser for .BTS files

---

## Data Inventory

**Battles with NPC units (27 of 54):**
B.BTS, BF003.BTS, BF004_1.BTS, BF004_2.BTS, BF004_4.BTS, BF005.BTS, BF006.BTS, BF010.BTS, BF011.BTS, BF014.BTS, BF015.BTS, BF016.BTS, BF017.BTS, BF020.BTS, BF026.BTS, BF028.BTS, BF029.BTS, BF030.BTS, BF031.BTS, BF036.BTS, BF042.BTS, RLTEST.BTS, RLTEST1.BTS, SPRED.BTS, WIZTEST.BTS, _DESTEST.BTS, _KFTEST.BTS

**Battles without NPC units (27 of 54):**
BF001.BTS, BF002.BTS, BF007.BTS, BF008.BTS, BF009.BTS, BF012.BTS, BF013.BTS, BF018.BTS, BF019.BTS, BF021.BTS, BF022.BTS, BF023.BTS, BF024.BTS, BF025.BTS, BF027.BTS, BF032.BTS, BF033.BTS, BF034.BTS, BF035.BTS, BF037.BTS, BF038.BTS, BF039.BTS, BF040.BTS, BF041.BTS, BF043.BTS, BF044.BTS, BF045.BTS

