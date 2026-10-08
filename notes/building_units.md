# Building pseudo-units: footprint, toughness, melee, collision and destruction (GitHub #185)

Public behavioural handoff for #185, following #173. Static research; the original was not run. Data values were read
from the installed game. Read with `battle_end_objectives.md` §12.1 (which furniture types become building units,
model counts, `W`), `script_behaviours.md` §2.2–2.5 (collision pass and contact handler), `casualty_bookkeeping.md`
(kill credit), `obstacle_steering.md` §6 (route steering) and `target_queries.md` §5 (charge reach).

## 1. Summary

- A building unit is a real (if inert) regiment: it has models, a map footprint, a grid presence and an army side
  (the building side). It runs no script and its models have **no attacks**.
- **Footprint**: a rectangle derived from the furniture type's size, centred on the furniture position and turned by
  its `dir` (table in §2). The unit position **is** that centre.
- **Toughness**: missiles wound against **T 0** (the building has no troop toughness). Melee wounds against the
  building's own T (§2 table, column T).
- **Melee**: possible only through a **charge** that touches the building while it is the charger's target. The
  attackers are laid along the building's sides on a combat grid, and every attack hits automatically. Wounds go to
  the first model; the building never strikes back, and the wounds do not count for the combat result.
- **Destruction** (first model at `W` wounds, checked every tick): models die at once, event 0x18 goes to **every**
  unit, the building leaves the grid, and the scenery piece becomes its ruin. The building's collision footprint
  stays (🟡).

## 2. Footprint per building type

From the type's size `w × h` (in 8-unit cells, sideways × front-to-back):

```
frontage = ceil(8w / 12) + 1          depth = ceil(8h / 12) + 1          (12-unit grid cells)
half-extents: sideways 6 × frontage, front-to-back 6 × depth   (rectangle, rotated by the furniture dir)
radius (circle used by the broad collision test and reach/steering tests) = trunc(√(hx² + hy²)) − 12
```

| type | w×h | frontage×depth | half-extents | radius | height | W | T | models | ruin piece (w×h, height) |
|---|---|---|---|---|---|---|---|---|---|
| `Tudor2Stry` | 7×4 | 6×4 | 36×24 | 31 | 88 | 5 | 5 | 2 | `D_Tudor2Stry` 9×4, 88 |
| `Yelo2Stry` | 7×4 | 6×4 | 36×24 | 31 | 88 | 5 | 4 | 2 | `D_Yelo2Stry` 9×4, 88 |
| `StnYelo2Stry` | 7×4 | 6×4 | 36×24 | 31 | 88 | 5 | 5 | 2 | `D_StnYelo2Stry` 9×4, 88 |
| `TudorChimney` | 9×4 | 7×4 | 42×24 | 36 | 88 | 4 | 4 | 2 | `D_TudorChimney` 9×4, 48 |
| `BalconyHouse` | 6×6 | 5×5 | 30×30 | 30 | 96 | 4 | 4 | 2 | `D_BalconyHouse` 7×6, 96 |
| `WaterMill` | 9×9 | 7×7 | 42×42 | 47 | 64 | 4 | 4 | 2 | `D_WaterMill` 9×9, 64 |
| `SmithyHut` | 11×13 | 9×10 | 54×60 | 68 | 72 | 4 | 4 | 2 | `D_SmithyHut` 11×13, 72 |
| `BrewerySmall` | 6×8 | 5×7 | 30×42 | 39 | 56 | 4 | 4 | 2 | `D_BrewerySmall` 6×8, 56 |
| `Brck2Stry` | 7×4 | 6×4 | 36×24 | 31 | 88 | 6 | 5 | 3 | `D_Brck2Stry` 9×4, 88 |
| `Crypt`, `NiteCrypt` | 6×13 | 5×10 | 30×60 | 55 | 96 | 6 | 5 | 3 | `D_Crypt` / `D_NiteCrypt` 6×13, 96 |
| `WatchTower` | 5×6 | 5×5 | 30×30 | 30 | 96 | 6 | 4 | 3 | `D_WatchTower` 5×6, 96 |
| `Farm` | 16×16 | 12×12 | 72×72 | 89 | 88 | 6 | 5 | 3 | `D_Farm` 16×16, 56 |
| `WindMill` | 6×6 | 5×5 | 30×30 | 30 | 96 | 6 | 5 | 3 | `D_WindMill` 6×6, 80 |
| `Tavern` | 17×9 | 13×7 | 78×42 | 76 | 96 | 6 | 5 | 3 | `D_Tavern` 17×9, 0 |
| `StnFarmHouse` | 4×7 | 4×6 | 24×36 | 31 | 104 | 6 | 5 | 3 | `D_StnFarmHouse` 4×7, 104 |
| `AngRoofHouse` | 13×9 | 10×7 | 60×42 | 61 | 72 | 6 | 4 | 3 | `D_AngRoofHouse` 13×9, 72 |
| `BreweryMain` | 11×15 | 9×11 | 54×66 | 73 | 136 | 6 | 5 | 3 | `D_BreweryMain` 11×15, 136 |
| `WoodShack` | 8×4 | 7×4 | 42×24 | 36 | 64 | 3 | 3 | 1 | `D_WoodShack` 9×5, 32 |
| `BlackWoodShack` | 9×5 | 7×5 | 42×30 | 39 | 64 | 3 | 3 | 1 | `D_BlackWoodShac` 9×5, 64 |
| `Barn1` | 12×6 | 9×5 | 54×30 | 49 | 80 | 3 | 3 | 1 | `D_Barn1` 12×6, 80 |
| `BreweryShed` | 8×6 | 7×5 | 42×30 | 39 | 56 | 3 | 3 | 1 | `D_BreweryShed` 8×6, 56 |
| `Well2` | 2×2 | 3×3 | 18×18 | 13 | 24 | 2 | 2 | 1 (single) | `D_Well2` 2×2, 16 |
| `HumanTent`, `NiteHumanTent`, `OrcBoyzTent`, `B_OrcBoyzTent`, `GrsOrcBoyzTent`, `GrsBlackOrcTent` | 6×6 | 5×5 | 30×30 | 30 | 40 | 1 | 1 | 1 (single) | matching `D_…` 6×6, 40 |
| `BlackOrcTent` | 7×7 | 6×6 | 36×36 | 38 | 48 | 1 | 1 | 1 (single) | `D_BlackOrcTent` 6×6, 40 |
| `Menhir` | 4×4 | 4×4 | 24×24 | 21 | 120 | 4 | 4 | 1 (single) | `D_Menhir` 4×4, 120 |
| `SkavBase10FR`, `SkavBase10FL` | 11×11 | 9×9 | 54×54 | 64 | 64 | 5 | 5 | 1 (single) | matching `D_…` 11×11, 64 |
| `SkavBase20FLR`, `SkavBase20FaR`, `SkavBase20FaL` | 21×21 | 15×15 | 90×90 | 115 | 120 | 5 | 5 | 1 (single) | matching `D_…` 21×21, 120 |
| `SkavBase20x10` | 21×11 | 15×9 | 90×54 | 92 | 120 | 5 | 5 | 1 (single) | `D_SkavBase20x10` 21×11, 120 |

"Height" is the type's height × 8 (world units), used by sight-line tests on scenery. "single" = the fixed-one-model
types of §12.1. A building's first model is its **leader** model: it carries `W` and T above. The other models only
count (§12.1).

## 3. Toughness and wounding

| Source | Hits | Wound roll | Save | Wounds per success | Credit |
|---|---|---|---|---|---|
| missile / artillery direct hit (weapons with an "S vs buildings", `game_rules.md` §8.3) | first model | `TO_WOUND[S][0]`: **T 0** | none | the weapon's wound die | lethal-only, to the firer (`casualty_bookkeeping.md`) |
| missile blast margin | first model | `TO_WOUND[S/2][0]` | none | 1 | lethal-only |
| close combat (§4) | first model | `TO_WOUND[S][T_building]` (§2 column T) | armour of the leader profile (none: rating 0) 🟡 | 1 | none (credit untouched) |
| spells that destroy buildings | — | destroyed outright | — | — | the caster |

With T 0, the wound roll needs **2+** for S 2–7 (a 5/6 chance) and is **automatic** for S 8 and above (cannon, great
cannon). S 1 needs 3+. Every weapon that can hit a building therefore wounds on 2+ or better, so your provisional T 5
is too high. Bows and crossbows (no "S vs buildings") cannot damage buildings at all. 🟡 That missiles and melee use
different toughness looks unintended in the original. It is what the data gives.

## 4. Melee against a building

1. **How it starts.** Only a **charging** (or already fighting) regiment makes contact with a building. A walking
   regiment is **pushed apart** from any building footprint, its target or not (`script_behaviours.md` §2.2 table).
   Contact with the charger's **target** building engages without a charge bonus (counter 0). The building becomes
   the grid owner, with the charger as its opponent (`ENGAGE_PLAIN`, §2.3). Contact with a **non-target** building
   while charging ends the charge (§2.5 latch; see §6).
2. **Placement.** The grid is built around the building's whole rectangle (`frontage × depth` cells, §2). The
   attacker is a joiner against a **block**: each tick, up to its frontage of free models are placed in free cells
   along the building's sides. The four sides are tried in an order that starts from the attack side. Every
   placed model's opponent is the building's **first model**. Overflow models become reserves (`game_rules.md`
   "Engagement", the block case of the pairing rules). So the number of attackers is limited only by the free side
   cells: `2 × (frontage + depth)` around the rectangle, fewer near the grid edge.
3. **Each melee round** (segment boundary), each attacker model that is fighting (paired and arrived, see
   `grid_gap_closing.md` §0) makes its `A` attacks (doubled with `Frenzy`). There is no to-hit roll. Each attack
   rolls to wound with its S (weapon class, items: Rocksplitter +5 S and +5 to the wound roll against inanimate
   targets) against the building's T, then the armour save. Each success is 1 wound on the first model.
4. **No strike back.** The building's models have no attacks. **No combat result**: these wounds are not added to
   either side's tally. 🟡 Whether rank or direction bonuses alone can produce a combat result against a building was
   not traced.
5. **Destruction** happens on the tick the first model reaches `W` wounds (§7). The attackers then get "target gone"
   (event 0x18) and "opponent gone" from leaving the grid, and go to re-form (library 152 → 163).
6. **Withdraw** (order 0x13) disengages a unit whose only opponent is a building (`game_rules.md` "Player orders").

## 5. Collision pass and steering (questions 4 and 5)

The public reports already give this; restated for the building case:

| Mover state | Overlapping a building footprint | Result |
|---|---|---|
| walking (not charging, not in melee) | any building, target or not | pushed apart; no contact |
| charging or in melee | building that is its target | contact → engage (counter 0) |
| charging | building that is not its target | **charge ends** (halted, charge sound off, 0x09 to its target); contact latch stays on |
| routing / any | — | routing movers are not edge-corrected; buildings are not exempt from push-apart |

**Steering** (`obstacle_steering.md` §6): a building footprint blocks a route unless it is the regiment's current
target, so a regiment ordered to attack a building plans straight through its footprint towards the centre.

**The latch after a charge ends on a non-target building** stays on, and while latched an ordinary move is undone
unless the step clears every overlap (`script_behaviours.md` §2.5). A unit that stays overlapping that building can
therefore stand still until a script `CheckCollisions` (library 166) or a halt/re-form clears the latch. 🟡 That
stalemate is real in the original's rules. The engine's reading of §2.2–2.3 matches the tables above.

## 6. Attack order on a building (event 0x04)

1. **Order** (player Attack + click): a click on a building that is **not destroyed** sends event 0x04 to the unit
   with the building as source. Destroyed buildings cannot be targeted.
2. **Script 158** (`movement_formation.md` §4): take the building as target; wait while re-forming; `React 1`;
   `MoveToTarget`, whose goal is the building's **centre**; steering ignores the target's footprint; `ReformBlock`;
   then loop `IfTargetInChargeReach` every 10 ticks.
3. **Charge reach for a building**: the aim point is the building's **centre** (P = C), **not** the far side used
   for regiment targets. `reach = d(unit position, C) − r_building`, in reach when `reach < 12 × s_rlmv`, with the
   other conditions of `target_queries.md` §5 (single leg, facing within 22.5°, not re-forming, not obstructed,
   outside `0xB0` areas). Correction: `target_queries.md` §5.1 lists formation kinds; a building's footprint takes
   the "other targets" branch (P = C).
4. **Script 160**: `ChargeTarget` (fear/terror check does not apply: buildings cause none) → charge at the centre;
   contact engages as §4.
5. Differences from attacking a regiment: no far-side aim point, no charge counter, no 0x07/0x08 events to the
   building, no flank/rear test, no return blows, no combat result.

While still walking (before the charge), the regiment is pushed apart by its own target building (§5). If the reach
test never passes (e.g. it arrives at an angle above 22.5°), it keeps walking at the centre and keeps being pushed.

## 7. Destruction and the ruin

On the tick the first model has `W` or more wounds (and not already destroyed):

1. The building is marked destroyed. Every model is killed at once (zero death delay; cause "fire": burning figure,
   `game_rules.md` figure animation table).
2. **Multi-model types**: a collapse effect is spawned at the building, and the scenery piece changes to its ruin
   when that effect ends 🟡. If no effect can be created, it changes at once. The unit stays with 0 models.
   **Single-model types**: the model is removed alive (`s_routed`), the unit is removed from the battle, and the
   piece changes to its ruin at once.
3. **Event 0x18** is sent to **every live unit** on the battlefield (both armies, allies, NPCs, other buildings),
   with the building as source. Library 152 handles it with `TargetGone`: units whose target was this building drop
   it and re-form (163) unless another enemy is found. Units without a handler ignore it. Your engine's "broadcast to
   every scripted unit" matches in effect.
4. The building leaves the combat grid.

**The ruin**: the scenery piece's size and height change (§2 last column; e.g. `D_Tavern` height 0, `D_TudorChimney`
48). The building's **collision footprint does not change**: the destroyed building still pushes walking regiments
apart and still blocks route steering for those not targeting it. 🟡 This was not checked for single-model types,
whose unit is removed. It can no longer be targeted, and missile hits on it do nothing (no model left). Sight-line
obstruction uses map objects by radius (`game_rules.md` §8.3), and the ruin piece takes its own size there 🟡.

## 8. Test vectors

| Before | Action | After |
|---|---|---|
| `Tudor2Stry` at (500, 500), dir 0 | load | building unit at (500, 500), facing 0, 2 models; footprint rectangle ±36 (x) × ±24 (y); radius 31; first model W 5, T 5 |
| `Farm` at (800, 300), dir 128 | load | rectangle 72 × 72 turned 90°, radius 89 |
| `Well2` | load | 1 model, rectangle ±18 × ±18, radius 13 |
| `Tudor2Stry`, 0 wounds | cannon hit (S vs buildings 10, die D4) | to-wound automatic (S 10 vs T 0); +D4 wounds, no save |
| `Tudor2Stry` | mortar blast margin (S 7 → 3) | wound on 2+; +1 wound |
| `WoodShack` (T 3) | 10 Empire swordsmen (S 3, A 1) fighting it for one round | 10 automatic hits, each wounds on 4+ (`TO_WOUND[3][3]`), no save → about 5 wounds; W 3 → destroyed |
| `Brck2Stry` (W 6, T 5), 4 wounds | round with 2 more wounds | destroyed: models killed, collapse effect, 0x18 to every unit, grid left |
| regiment walking to its target building | footprints overlap | pushed apart; no engagement |
| same, reach test passes (d − 31 < 12 × s_rlmv, facing within 22.5°) | `IfTargetInChargeReach` | true; aim point = building centre; script 160 charges |
| charging regiment touches its target building | contact | engaged, counter 0; building target := regiment; attackers placed along the sides (≤ frontage per tick) |
| charging regiment touches a non-target building | contact | charge ends, halted, 0x09 to its target, latch stays on |
| destroyed building | player Attack click on it | not accepted as a target |
| any unit whose target was the destroyed building | event 0x18 | `TargetGone` → re-form (163) |
| walking regiment meets a ruined building | footprints overlap | pushed apart (footprint unchanged) |

## 9. Uncertainties

- 🟡 Armour save in melee against a building (leader profile armour 0; assumed "no save").
- 🟡 Combat result and break tests in a fight whose only enemy is a building.
- 🟡 Timing of the ruin swap after the collapse effect (multi-model types). Footprint persistence for removed
  single-model types. Sight-line effect of ruins.
- 🟡 The T 0 used by missiles looks like an original oversight; reproduce it for parity.
