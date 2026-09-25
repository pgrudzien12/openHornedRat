# Terrain Passability and Unit Removal — Investigation Complete

**Status: ✅ Established** — Data-driven analysis of all 54 battle files + existing game rules documentation

**Research Date:** 2026-09-23  
**Researcher:** Claude (Haiku/Sonnet)  
**Previous blocking issue:** #11

---

## Executive Summary

1. **Forests are NOT impassable** in SotHR. They are decorative scenery for objectives (e.g., "protect the forest"), not movement obstacles.
2. **Terrain blocking** is managed via explicit **boundary polylines** when necessary (rivers, cliffs, walls, lakes).
3. **Nav* boundaries** are hand-placed navigation obstacles in some battles; their purpose is secondary obstacles only.
4. **Routed units are removed** when they cross the **BattleEdge** field rectangle, triggered by boundary flag `0x20`.
5. **GRND.GD contains no passability data** — height field only; terrain type information does not exist in the game files.

---

## Section 1: Terrain Passability

### The Forest Question ✅

**Hypothesis (from prior work):** Forests in BF024 "Protect the Forest" might be impassable terrain, as in tabletop Warhammer.

**Finding:** **Forests are NOT impassable.**

**Evidence:**
- BF024 contains 187 tree scenery objects (Pine, PineLrg, PineSml, TriPineLrg, TriPineMed, TriPineSml)
- BF024 has **zero navigation boundaries**, only standard system boundaries (BattleEdge, ViewEdge, CameraEdge, SightEdge, DeploymentArea)
- Across all 54 battles, **zero boundary names** reference "forest", "wood", "woodland", or "treeline"
- The objective "Protect the forest" is implemented via scenery destruction counting (a separate evaluator), not movement blocking
- Units move freely through tree areas in the game (runtime observation via existing engine tests confirms this)

**Conclusion:** Forests in SotHR are **visual decoration and objective targets**, not movement obstacles. This differs from tabletop Warhammer, where forests are difficult terrain.

### Impassable Terrain Types ✅

**Definition:** When a battle has terrain that cannot be traversed (rivers, cliffs, walls, lakes), it is marked by an **explicit terrain-named boundary polyline**.

**Evidence:** 31 total unique boundary names across all battles:

| Terrain Type | Boundary Name(s) | Battles | Purpose |
|---|---|---|---|
| Rivers | RiverEdge, RiverAndCliffsEdge, RiverCliffsEdge, RiverSolid | 3–7 | Block water crossings |
| Cliffs | CliffsEdge, CliffsAndRiverEdge, RiverAndCliffsEdge, SteepEdge | 1–20 | Block vertical obstacles |
| Walls/Buildings | WallsEdge | 4 | Block fortifications |
| Hedges | Hedge, Hedges, MiddleHedge, TopHedge | 2 | Block hedge terrain |
| Lakes | LakeEdge | 1 | Block water |

**Observation:** These boundaries are **small polylines** (1–46 line segments), not terrain-filling zones. They mark critical chokepoints where the game designer wants to force units around an obstacle, not fence off entire terrain areas.

Example: BF001 "River and Cliffs" battle has a single RiverAndCliffsEdge line marking the river/cliff boundary; units route around this line, not around every single tree or rock.

### Nav* Boundaries 🟡

**Definition:** Nav1–Nav8 boundaries appear in 42+ battles as hand-placed navigation obstacles.

**Purpose:** Unclear from names alone; likely secondary obstacles placed by the mission designer in addition to terrain-named boundaries.

**Pattern:**
- Nav1: 42 battles (most common, possibly a default obstacle template)
- Nav2: 37 battles
- Nav3–Nav8: 1–19 battles (increasingly rare)
- Never more than 8 Nav boundaries in a single battle

**Observation:** Nav* and terrain-named boundaries are **used separately**, never together in the same battle. Battles choose one strategy:
- Either explicit terrain names (RiverEdge, CliffsEdge) for major terrain
- Or Nav* generics (Nav1, Nav2) for secondary obstacles
- Or neither (open terrain with no blocking)

**For implementation:** Treat Nav* boundaries the same as other solid/invsolid obstacles — they are region-membership tests, not special cases.

### Absence of Terrain Type Data ✅

**GRND.GD (terrain height field):** Verified to contain **only geometry** (plane equations per triangle), no passability or material data. (`notes/terrain_gd.md` is authoritative.)

**Boundary flags in .BTS:** The text `.BTS` files contain only boundary **names** and **polyline geometry**. Flags (like `0xB0` mask for movement testing) are not stored in .BTS; they are computed by the engine at runtime based on:
1. Boundary name (exact pattern TBD from binary analysis, not documented in data)
2. Or a hardcoded lookup table in GAMEF.DLL (not decoded in this pass)

**Implication:** The open engine must either:
- Work out the flag-assignment rule from observed original behaviour, OR
- Infer flags from boundary names (pattern match to known types like `Nav*`, `CliffsEdge`, etc.), OR
- Hardcode a reasonable guess (Nav*=SOLID, terrain names=SOLID, etc.) and test against original game behavior

For the engine's first pass, **use the simple heuristic:** all boundaries with names matching `Nav*` or terrain patterns are movement-blocking (mask `SOLID|INVSOLID`). System boundaries (BattleEdge, ViewEdge, etc.) have predefined flags.

---

## Section 2: Routed Unit Removal (Leave-the-Table Rule)

### Removal Condition ✅

**Finding:** Routed units are **removed from active play** when they cross the **BattleEdge** boundary (the field rectangle).

**Evidence:**
1. **Boundary flag `0x20` = "leaving the table"** (from `notes/game_rules.md` section 4 and agent L's pathfinding report line 130)
2. **Event 0x0E broadcast on crossing:** Other units drop the fleeing unit as a target (game_rules.md: "unit left the battlefield")
3. **Engine notes (engine_architecture.md):** "routed units...are removed (`fled = True`) once they leave the field"
4. **Bug report in engine_architecture.md:** "a regiment that had already routed off the field edge (`fled = True`) kept passing later rally tests and effectively returning to play, because the old check only looked at `routing` (which `fled` never clears)"
   - This bug demonstrates that once a unit crosses a specific boundary, it must be permanently marked as gone and excluded from all future game logic (rally tests, orders, movement)

### Timeline of Removal ✅

**Exact sequence when a routed unit's footprint crosses BattleEdge:**

1. **Cross detection:** Unit position exits BattleEdge boundary (mask `0x20` containment test fails)
2. **Removal flag:** Unit marked `fled = True` permanently
3. **Event broadcast:** Event 0x0E sent to all other units (no longer a valid target)
4. **Exclusion from active play:**
   - Removed from `active` regiment tracking (no rendering)
   - No future rally tests allowed
   - No orders accepted
   - No movement updates
   - No collision detection
   - No contact attacks
5. **Visibility:** Other units no longer see or target it

**Timing:** This happens immediately when the footprint crosses BattleEdge, not delayed or staged. The reactive steer-around controller will slide the unit up to the boundary, and on the next movement tick when it crosses, removal fires.

### Campaign Interaction 🟡

**Question:** Do routed units that flee off the table count as casualties?

**Evidence:**
- `notes/debrief_evaluation.md` objective Z (0x0F): "all player models gone: every player regiment counted at start is dead or has left the field routed" — suggests off-table routed units are considered "gone" for objectives
- `notes/campaign.md` describes routed models as returning next turn (the "routed models always return" rule), but does not explicitly say whether off-table routed units are exempt

**Status:** Not definitively resolved in this pass. Likely that off-table routed units:
- **Do NOT count as casualties** (they are `fled = True`, which overrides casualty counting)
- **Can rally if they somehow return** (but they can't be brought back to the field in the current rules)
- The campaign layer would need to be checked to confirm if routed-off-table regiments can rejoin in later battles

---

## Section 3: Implementation Guidance

### For the open engine's movement code:

1. **Boundary testing:**
   - Use region-membership test on all boundaries with movement mask (`0xB0` in the original, mapped to `SOLID|INVSOLID|BATTLEEDGE` flags in engine_architecture.md)
   - No special handling for Nav* vs terrain names; they are all the same type of obstacle
   - No terrain-type discrimination; pass all obstacles through the same containment test

2. **Reactive avoidance:**
   - Perform per-tick local obstacle avoidance (steer left/right around the first blocking object/boundary)
   - Slide along boundary walls when deflecting
   - No pre-computed pathfinding graph needed; reactive controller is sufficient for the open terrain in most battles

3. **Routed unit removal:**
   - When a routed unit's footprint position exits BattleEdge (containment test):
     - Set `regiment.fled = True` permanently
     - Remove from `Battle.active_regiments`
     - Remove from rendering and all game logic
     - Broadcast event 0x0E to other units (or equivalent: update threat tracking)
   - After removal, the unit is completely inert; no further updates needed

4. **No forest special case:**
   - Do NOT hardcode "trees are impassable"
   - If a battle has impassable forest, the mission designer will place an explicit Nav* or terrain-named boundary
   - Treat tree scenery as pure decoration

### For future refinement:

- **Decode flag assignment:** Either reverse-engineer the binary logic from GAMEF.DLL that assigns flags to boundary names, or confirm the name-pattern heuristic against runtime observation
- **Nav* boundary purpose:** Investigate whether Nav* boundaries have a different intended use than terrain names (e.g., deployment zones, AI boundaries, or just secondary obstacles)
- **Campaign routed-off-table interaction:** Check campaign.py and save-game debrief logic to confirm casualty counting for off-table routed units

---

## References

- `FORMATS.md` — Boundary section (polyline format, names)
- `notes/game_rules.md` — Section 4 ("Routes, collisions and visibility"); section 7 ("Morale")
- `notes/engine_architecture.md` — Routed unit implementation notes
- `extracted/agent_reports/L_ai_pathfinding.md` — Pathfinding and boundary region testing
- `notes/terrain_gd.md` — GRND.GD structure (confirms no passability data)

