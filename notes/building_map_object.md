# A building's own map object: projectiles, sight, ruins and the Fire pick (GitHub #165)

Public implementation report. It completes `building_units.md` (footprint, toughness, destruction) and
`map_objects_and_projectiles.md` (which map objects stop projectiles and block sight) for the one object those two
reports left open: the map object of a building pseudo-unit. It also states which things a player Fire click can
pick.

Companion reports, cited rather than repeated:

- `building_units.md` §2: type table with radius and height.
- `building_units.md` §3: wounding. `ranged_combat_handoff.md`: flight and impacts.
- `player_missile_orders.md` §5: the Fire click. `spell_effects.md` §3.4: projectile heights.

**Corrections made by this report:**

- `building_units.md` §7 said the ruin piece "takes its own size" for sight (🟡). It does not: the building's map
  object keeps the **original** type's radius and height after destruction (§3).
- `building_units.md` §7's open question about single-model types is now settled: their object also persists after
  the unit is removed (§3). Both sentences are corrected there.

## 1. The object (Q1, Q2)

Every building-type furniture piece (the types in `building_units.md` §2, and only those, see §6) gets one map
object when the battle loads:

| Property | Value |
|---|---|
| shape | a **circle**, not the footprint rectangle. The rectangle is used only by the collision pass and the melee grid (`building_units.md` §2, §4–§5) |
| centre | the furniture position (the same point as the building unit's position) |
| radius | the type's radius from `building_units.md` §2 (`trunc(√(hx² + hy²)) − 12`, e.g. 31 for `Tudor2Stry`) |
| height | the **type height** column of `building_units.md` §2 (type height × 8: 88 for `Tudor2Stry`, 40 for the tents, 24 for `Well2`, 136 for `BreweryMain`). Not 16 (that is the height of a regiment's object) and not the 80 default of `[OBJECTS]` entries |
| state | **exists**, building kind. It is **not** `os_solid` and not camera-only. Movement push-apart against buildings is the building rule of `building_units.md` §5, not the `os_solid` rule |

The same object, with the same geometry, is used by every consumer:

| Consumer | Rule for a building object |
|---|---|
| projectile in flight / terminal impact | §2 |
| sight (spotting, visibility tests) | blocks like any `[OBJECTS]` circle with `z ≠ 0` (`map_objects_and_projectiles.md` §2). Every building type has a non-zero height, so **every building blocks sight**, within its radius, at its type height |
| Fire pick | §4 |

## 2. Projectiles against a building (Q4)

The impact test is the one of `map_objects_and_projectiles.md` §2 and `ranged_combat_handoff.md`. It is run every
flight tick (the in-flight test, with no blast margin) and once at the end (terminal impact, at ground height, with the
weapon's blast radius). For a building's object it splits on the weapon:

| Weapon | Test | Effect |
|---|---|---|
| **has an "S vs buildings"** (artillery, mortar, bombs: `game_rules.md` §8.3) | `d < radius` (strict) **and** projectile height `≤` building height | **direct hit**: wound roll at building S against T 0, the weapon's wound die on the first model (`building_units.md` §3). It **counts as a hit**, so a stop-on-hit missile ends there |
| same | otherwise `d < radius + blast radius` and height `≤` building height (terminal impact only; the in-flight margin is 0) | **margin hit**: S/2 against T 0, 1 wound. Counts as a hit |
| **no "S vs buildings"** (bows, crossbows, spells' own impact tests) | `d < radius` (strict) **and** height `≤` building height | an obstacle: the projectile is **stopped, no damage**, exactly as by an `[OBJECTS]` circle |

So yes, an in-flight collision with a building is a direct hit at that point (when the weapon can damage buildings),
not only a stop. A missile aimed at a building (whose aim point is the building **centre**, `building_units.md` §6)
can still fly past or over it: when it has scattered so its line misses the circle, or when its arc is above the
building height where it crosses the circle. It then lands at its scattered destination, where the terminal impact
applies the direct or margin rule above, measured from the building centre.

`d` is measured from the projectile's point to the circle centre. As for all impacts, every object meeting the test in
the same call is affected, not only the first.

## 3. After destruction (Q3)

Destruction (`building_units.md` §7) marks the building destroyed and swaps the scenery piece to its ruin, but **leaves
the map object exactly as it was**: same centre, same radius, same original height, still existing. This holds for
both kinds:

- **multi-model types** (the unit stays, with no models left);
- **single-model types** (the unit is removed from the battle; removing a building unit does **not** remove its map
  object, unlike any other unit).

Consequences:

| Consumer | Destroyed building |
|---|---|
| projectiles | still **stopped** by it (within radius, at or below the **original** height). With a building-S weapon the hit counts but deals no damage (no model left) |
| sight | still **blocked** at the original height. The ruin's own height (e.g. `D_Tavern` 0) is only how it is drawn |
| push-apart and steering | unchanged (`building_units.md` §7) |
| Fire pick | **still pickable** (§4) |
| Attack pick | not pickable (`player_missile_orders.md` §5) |

Your engine's choice ("the entry stays and keeps stopping shots") is therefore the original's behaviour. The size and
height are simply the original type's, and there is no ruin size.

## 4. The player's Fire pick (Q5)

Already public in `player_missile_orders.md` §5. Restated, with the details #165 needs:

- **Candidates**: map objects that exist **and** are a regiment, war machine, monster, flier or **building**.
  **Plain `[OBJECTS]` collision circles are never candidates**, and neither are spell area objects. A click on one of
  those is an ordinary ground-point Fire (event 33, no text).
- **Geometry**: a circle around the object's centre with radius `max(object radius, 48)`, **strict**
  (`dx² + dy² < r²`). For a building that is its §1 circle, floored to 48 (so `Well2`, radius 13, picks within 48).
- **Destroyed buildings are not excluded**. A Fire click on a ruin targets it: text 2007, event 30 (37 for an
  independent Archers unit), with the building as source. 🟡 No later check for "destroyed" was found in the shooting
  loop's target tests, so the unit would keep shooting at it. Its shots are stopped by the still-existing object and
  do no damage. This was not observed on screen.
- **Order between candidates**: the **first** object in the original's object list wins, not the nearest one.
  Objects are created in battle-file order: `[OBJECTS]`, then `[SCENERY]` (which creates the buildings), then
  `[UNITS]`. So **a building comes before every regiment placed at load**. A Fire click inside both a building's circle
  and a regiment's circle picks the **building**. 🟡 Objects created later in the battle (re-used list positions) may
  come earlier. An engine can use "buildings first, then units in unit order".
- **Result per pick**: building → 2007 + event 30. The shooter itself → 2009 + event 32 (2017 + event 36 for
  independent Archers). Any other unit (any side) → 2008 + event 31. Nothing → event 33, a ground point at the click
  position.

## 5. Which furniture is damageable or targetable (Q6)

Only the **building-type** furniture of `building_units.md` §2 (a fixed type property). Every other `placefurniture`
piece, including walls, fences, gates and road pieces, is scene-only: no map object, no unit, never damaged, never
picked, never an obstacle (`map_objects_and_projectiles.md` §1). The BF015 gate control piece is the one special
scene piece a script drives (`bf015_gate_npc_column.md`), and it is not damageable by missiles either. `WatchTower`
**is** a building type (W 6, T 4), so the towers that use it are damageable.

## 6. Differences from your engine

| Your engine | Original |
|---|---|
| building circle height 24 | **type height** (`building_units.md` §2 column; 24 only for `Well2`) |
| status active + solid | exists, building kind, **not** `os_solid` (push-apart uses the building rule anyway) |
| circle at furniture centre, type radius | ✅ |
| in-flight test strict `<` radius, height `≤` | ✅ |
| impact = no damage, separate building damage pass from the impact point | ✅ equivalent, provided the in-flight hit on the building circle counts as **direct** (no margin in flight) |
| destroyed: entry stays, no ruin size | ✅ (original keeps the original height and radius) |
| Fire pick: any shooting object incl. plain `[OBJECTS]` circles | **only units and buildings**. Plain circles → ground-point fire, no text |
| Fire pick geometry: object circle | circle floored to radius **48**, strict |
| aim point = object centre | ✅ for buildings |

## 7. Tents (addendum): `HumanTent`, `NiteHumanTent`, `OrcBoyzTent`, `B_OrcBoyzTent`, `GrsOrcBoyzTent`, `GrsBlackOrcTent`, `BlackOrcTent`

Checked against the type data in the installed game. Every tent type is a building type, of the single-piece kind:
1 model, W 1, T 1. The `building_units.md` §2 row is confirmed: radius 30 (38 for `BlackOrcTent`), object height 40
(48 for `BlackOrcTent`). These are the tents of BF004_5 (`BlackOrcTent`), BF012 (`B_OrcBoyzTent`), BF015/BF017
(`GrsOrcBoyzTent`) and BF025 (`NiteHumanTent`).

**(a) Destructible**: yes. One wound on the leader model destroys a tent (W 1).

**(b) By what**:

| Attack | Can hurt a tent? | How (W 1, so any wound destroys it) |
|---|---|---|
| charge / melee (Attack order, `building_units.md` §4, §6) | **yes** | automatic hits, wound roll at the attacker's S against **T 1**: S 1 → 4+, S 2 → 3+, S 3+ → 2+ |
| missiles with an "S vs buildings" (great cannon, cannon, mortar, Hellblaster, rock lobber, doom diver, Gyrocopter bomb; `game_rules.md` §8.3 table) | **yes** | direct: S vs **T 0** (2+ for S 2–7, automatic for S 8+); margin: S/2 vs T 0 |
| **bows, crossbows, short bows, longbows, Wood Elf bows** (S vs buildings "none") | **no** | the tent's object stops the arrow or bolt, with no wound roll (§2, row 3) |
| magical bolts and beams (`spell_effects.md` §3 table: each spell's "S vs buildings"; Fireball 4, Lightning 6, Warp Lightning 5, Piercing Bolts 4, Pestilent Breath 3, Hunting Spear 6…1 …) | **yes** | the same building branch: spell S vs T 0 on the first model |
| area spells that destroy buildings outright (`spell_area_effects.md`: e.g. the crushing foot) | **yes** | destroyed, credited to the caster |

**(c) On destruction** (single-piece path of `building_units.md` §7):

1. The tent's model is removed **alive** (counts in `s_routed`, not as a kill), and the building unit is removed from
   the battle quietly: there is no "unit removed" (0x16) broadcast.
2. The scenery piece is swapped **at once** to its ruin (`D_HumanTent`, `D_BlackOrcTent`, `D_OrcBoyzTent`,
   `D_B_OrcBoyzTent`, `D_GrsOrcBoyzTen`, `D_GrsBlkOrcTent`, `D_NiteHumanTent`). There is no collapse effect. The piece
   is **not** removed, only redrawn as the ruin.
3. Event 0x18 goes to every live unit (shooters and chargers targeting it drop it via `TargetGone`).
4. The tent's **map object stays** (§3), with the same circle and the original height 40/48. The ruin still
   **stops projectiles**, still **blocks sight**, still **pushes** walking regiments apart, and can still be picked
   by Fire (not by Attack).

## 8. Test vectors

`Tudor2Stry` at (500, 500): radius 31, height 88, W 5. Heights are projectile heights in the convention of
`map_objects_and_projectiles.md` §3.

| Before | Action | After |
|---|---|---|
| building intact | crossbow bolt in flight at (520, 500), height 30 (d 20) | **stopped**, no damage |
| same | bolt at (531, 500), height 30 (d 31) | flies on (`31 < 31` false) |
| same | bolt at (520, 500), height 89 | flies on (89 > 88) |
| same | bolt at (520, 500), height 88 | **stopped** (88 ≤ 88) |
| same | cannonball (building S 10, D4) in flight at (510, 510), height 40 (d 14) | **direct hit**: automatic wound (S 10 vs T 0), +D4 wounds; ball stops |
| same | mortar terminal impact at (540, 500), ground height, blast radius 16 (d 40: `40 < 31 + 16`) | **margin hit**: S 3 (S 7 / 2) vs T 0 → wound on 2+, +1 wound |
| same | mortar terminal impact at (547, 500) (d 47) | no effect (`47 < 47` false) |
| destroyed `Brck2Stry` (multi-model) | bolt at d < radius, height ≤ 88 | **stopped**, no damage |
| destroyed `WoodShack` (single-model, unit removed) | bolt at d < 36, height ≤ 64 | **stopped** (object kept), no damage |
| destroyed `Tavern` (ruin `D_Tavern`, drawn height 0) | sight line across it | **blocked** (object height still 96) |
| `[OBJECTS]` circle at (300, 300), radius 60, no unit or building there | player Fire click at (310, 300) | ground-point fire at (310, 300), event 33, **no text** |
| `Well2` at (100, 100), radius 13 | Fire click at (140, 100) (d 40 < 48) | **building picked**: 2007, event 30 |
| `Well2` at (100, 100) | Fire click at (148, 100) (d 48) | not picked (strict) → ground point |
| `Tudor2Stry` at (500, 500) and an enemy regiment at (520, 500), both containing the click (510, 500) | Fire click | **building** picked (loaded before the regiment) |
| destroyed `Tudor2Stry` | Fire click at its centre | picked: 2007, event 30 (🟡 the shooting loop then shoots at the ruin) |
| destroyed `Tudor2Stry` | Attack click at its centre | not accepted (`building_units.md` §6) |
| a `placefurniture:Wall…` piece | any missile, Fire or Attack click | not an obstacle, not pickable, never damaged |
| `GrsOrcBoyzTent` (W 1, T 1) at (200, 200) | crossbow bolt in flight at d 10, height 20 | stopped, **no wound roll** |
| same | Fireball in flight at d 10, height 5 | S 4 vs T 0 → 2+: on success the tent is destroyed: model removed alive, unit removed (no 0x16), ruin `D_GrsOrcBoyzTen` drawn at once, 0x18 to every unit |
| same | charging Orc Boyz (S 3) in contact, one attack wounds | S 3 vs T 1 → 2+: destroyed as above |
| ruined `GrsOrcBoyzTent` | crossbow bolt at d 10, height 20 | **stopped** (object kept, height 40) |

## 🟡 Open items

- Shooting at a destroyed building after a Fire click (§4): no stop condition found. Not observed on screen.
- Fire pick order for objects created mid-battle (§4).
