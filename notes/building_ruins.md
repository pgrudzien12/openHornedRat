# Destroyed buildings on screen: ruin pieces, the collapse effect, and shooting at a ruin (GitHub #374)

Public implementation report. It completes `building_units.md` §7 (destruction) and `building_map_object.md` §3–§4
(the building's map object and the Fire pick) for the visible side of a destroyed building, and it settles the 🟡
about shooting at a ruin.

Companion reports, cited rather than repeated:

- `sprite_names.md`: the furniture table in `WHSHR.EXE`, which the engine already reads (`whshr/battlefield.py`).
- `building_units.md` §2 and §7, and `building_map_object.md`.
- `script_queries.md` (`TargetGone`) and `script_animation_sound.md` §4 (sound packets).
- `script_shooting.md` (the building fire loop 107).

**Corrections and settled items:**

- `building_units.md` §7: the 🟡 on "when the swap happens after the collapse effect" is settled. The swap is a step
  **inside** the collapse effect, about 13.8 s in, and not at its end (§3).
- `building_map_object.md` §4: the 🟡 on shooting at a ruin is settled (§5). A Fire order given **after** the
  destruction keeps shooting at the ruin until something else changes the unit's target.

## 1. Q1 — the ruin piece is data: furniture record + 59

The ruin is a fixed property of the building type, and it can be read from the installation. In the **furniture table
of `WHSHR.EXE`** (`sprite_names.md`: 60-byte records, record 0 `VoidFurn`, name at +5, mesh file at +21), **the ruin
of the building in record `i` is record `i + 59`**:

- the 37 building types are the consecutive records 50–86 (`Tudor2Stry` … `SkavBase20FaL`);
- their ruins are the consecutive records 109–145 (`D_Tudor2Stry` … `D_SkavBase20FaL`), in the same order.

This was checked for every building type. The engine's own copy of the game's type data uses the same order, and its
destruction rule takes exactly that "+ 59" record.

So an engine should **read the ruin's name and mesh file from record `i + 59`** and not hardcode names. The names do
not follow a simple `D_` + name rule. The 16-byte name field truncates and abbreviates some of them:

| building | ruin name | ruin mesh |
|---|---|---|
| `BlackWoodShack` | `D_BlackWoodShac` | `SHACK2_D` |
| `GrsOrcBoyzTent` | `D_GrsOrcBoyzTen` | `TENT1_D` |
| `GrsBlackOrcTent` | `D_GrsBlkOrcTent` | `BOTENT_D` |
| `HumanTent`, `OrcBoyzTent` | `D_HumanTent`, `D_OrcBoyzTent` | both `TENT1_D` |
| `Menhir` | `D_Menhir` | `MENHIR_D` |
| `SkavBase10FR` … `SkavBase20FaL` | `D_SkavBase10FR` … | `SKTUN1_D` … `SKTUN6_D` |

How to tell a building type from the table: its flags byte has the "building" bit, which is the 8s bit of `flags`.
Values 24, 25, 137, 152, 153 and 157 in `sprite_names.md`'s list, i.e. exactly records 50–86. The ruin mesh, like every
furniture mesh, is a `.XOF` in the battle's `SCENERY.PBX`. ✅ Checked for every shipped battle: all 48 placements of
building types (in 16 battle files) have both the intact and the ruin mesh in that battle's `SCENERY.PBX`.

## 2. Q2 — placement

The swap replaces the **mesh of the same scene piece**. The piece keeps its frame, so the ruin has the **same
position, `dir`, scale and ground height** as the intact building. The intact mesh is removed **entirely**: there is
no overlay, and the intact piece is never drawn again. If the ruin type has an animation of its own (`D_BreweryMain`
is the only ruin with one, `sprite_names.md`), it starts at the swap.

## 3. Q3 — the collapse effect (multi-model types only)

**Single-model types** (`Well2`, the tents, `Menhir`, the Skaven bases: `building_units.md` §2 "single") have **no
effect**. The swap happens on the destruction tick itself, together with the model removal (`building_map_object.md`
§7(c)).

**Multi-model types**: one invisible "collapse" effect is created at the building's centre (its map-object centre).
It runs a fixed timed program. If no effect record is free, there is no collapse at all and the swap is immediate.

1. **Sound**: on its first tick it starts the positional sound **packet 2 (`Battle2`), effect 12** (0-based,
   `script_animation_sound.md` §4) at the building centre, as a looping/fading sound 🟡. It is stopped at the very end
   of the program.
2. **Smoke puffs**: each "puff" spawns one small effect at a random point of the building's circle: angle
   `rand() mod 512`, distance `rand() mod radius` (radius = `building_map_object.md` §1), each axis offset
   `floor(direction × distance / 256)`, and height `trunc(h / 2) − (rand() mod h)`, where `h` = the building's object
   height. That is three random draws per puff, in that order, from the battle stream. 🟡 Puffs below ground level
   are presumably not visible. Each puff animates frames 1, 2, 3, 4 four times (16 ticks), then frame 1 once, then
   ends (17 ticks), with a fixed rising speed 🟡. 🟡 Its sprite set is the effect sprite set of sprite-table entry 0;
   which sheet that resolves to was not traced (by eye, a dust or smoke cloud).
3. **Schedule** (ticks counted from the effect's first tick, a puff then the given wait):

   | Phase | Puffs | Gap after each puff | Ticks |
   |---|---|---|---|
   | 1 | 12 | 5 | 60 |
   | 2 | 18 | 3 | 54 |
   | 3 | 9 | 2 | 18 |
   | 4 | 6 | 1 | 6 |
   | **swap to the ruin** | — | — | at tick **≈ 138** (13.8 s) |
   | 5 | 12 | 2 | 24 |
   | 6 | 6 | 3 | 18 |
   | 7 | 4 | 5 | 20 |
   | 8 | 3 | 8 | 24 |
   | sound stopped, effect ends | — | — | at tick **≈ 224** (22.4 s) |

   So the smoke **thickens** up to the swap (gaps 5 → 1 tick), the building turns into its ruin at the peak, and the
   smoke thins out over the next 8.6 s. That gives 45 puffs before the swap and 25 after. There is no fire or other
   lasting effect after the program ends.
4. Everything else in `building_units.md` §7 (models killed at once with the burning death, 0x18 to every unit, the
   building leaves its grid) happens on the destruction tick, before the effect starts. The **game state** (destroyed,
   not targetable by Attack, object unchanged) does not wait for the swap: only the drawing does.

## 4. Q4 — what else changes on screen

Only the 3D scene piece's mesh changes. The swap is on the scene piece, so it shows in every 3D view and camera mode.
A shadow or anything else drawn as part of the mesh changes with it. 🟡 Nothing in the destruction touches the
minimap or the plan map (the plan map is a static picture); no change there was found.

## 5. Q5 — shooting at a ruin

- **Units targeting the building when it is destroyed.** The shooting target and the attack target are the same
  "current target" (`lone_unit_on_grid.md` §0.1). The destruction's event 0x18 (source = the building) reaches every
  unit, and library 152 runs `TargetGone`: a unit whose current target is the building and that is not in melee gets
  0x19 with the target kept, so `DropTarget` is true and it switches to 163 (stop, re-form, `Restart`). This applies
  to a player's Fire target set by event 30, to scripted shooters, and to units ordered to Attack it. They all stop.
- **A Fire order given after the destruction** (allowed, `building_map_object.md` §4): event 30 makes the ruin the
  current target, and the building fire loop (107) **keeps shooting at it until another order or event changes the
  target**. Nothing in that loop or in `FireAtTarget` checks for "destroyed" (or, for a single-model type, that the
  building unit has been removed). Its arc and range tests and the reload work as for an intact building, using the
  building's position. The 0x18 was sent only once, at the destruction, so nothing drops the target later. The shots
  are stopped by the ruin's map object and do nothing (`building_map_object.md` §3).
- **Scripted `FireAtTarget` on event 34** aimed at a building that is destroyed later: the destruction drops the
  target as above, so the next event 34 (posted before the drop, `script_shooting.md`) aims at the **target point**
  if one is set, and otherwise launches nothing.

🟡 Shooting at a ruin has not been observed on screen. An engine may choose to refuse a Fire pick on a ruin as a
usability deviation, and should tag it as one.

## 6. Test vectors

| Before | Action | After |
|---|---|---|
| `Tudor2Stry` (record 50) at (500, 500), dir 64 | destroyed (multi-model) on tick T | models killed, 0x18 to all, grid left; collapse effect at (500, 500); `Battle2` effect 12 starts; puff 1 on T (or T+1) |
| same | tick ≈ T+138 | mesh swapped to record 109 `D_Tudor2Stry` (`HOUSE1_D`), same position, dir 64, scale; intact mesh gone |
| same | tick ≈ T+224 | last puff faded, sound stopped, nothing more |
| same, no free effect record | destroyed on tick T | swap to `D_Tudor2Stry` on tick T; no smoke, no sound |
| `GrsOrcBoyzTent` (record 70) | destroyed on tick T | swap on tick T to record 129 `D_GrsOrcBoyzTen` (`TENT1_D`); no effect; unit removed |
| `BlackWoodShack` (record 57) | destroyed | ruin is record 116 `D_BlackWoodShac` (`SHACK2_D`) — read, not derived from the name |
| crossbow unit X with Fire target = building B | B destroyed | 0x18 → `TargetGone` → 0x19 (target kept) → `DropTarget` → 163: X stops shooting, re-forms, restarts |
| X idle, B already destroyed | player Fire click on B | 2007, event 30 → 107: X **keeps shooting at the ruin** (each shot stopped by B's object, no damage) until another order |
| artillery A with Fire target B, ball 1 in flight | B destroyed by another unit | A drops B (163). Ball 1 continues and is stopped by B's object, no damage |
| mortar terminal impact at the ruin of a destroyed `Brck2Stry` | impact | hit counted, no damage (no model) |

## 🟡 Open items

- The collapse smoke's sprite sheet, its rising speed, and whether puffs spawned below ground show (§3).
- Shooting at a ruin after a Fire order (§5): follows from the absence of any check, not observed on screen.
- The minimap and plan map unchanged (§4).
