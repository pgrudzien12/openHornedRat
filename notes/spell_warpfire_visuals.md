# What a Warpfire Thrower's flames look like

Public implementation report (behaviour only) for issue #426, part of the spell-visuals epic #259. This report covers
**what is drawn, where and when** for the Warpfire Thrower's shot (special weapon 15, effect 26). Gameplay is already
public in several places:

- who fires and when: `script_shooting.md` §1.2 (script "Launch") and `gyrocopter_steam_gun.md` (the player's Fire
  order reaches a special shooter's own routine, aimed at the clicked ground point);
- the weapon row: `game_rules.md` "Special weapons" (code 15: D6 flames, S4, 1 wound, no save, no misfire);
- the effect framework (innate, never cancelled, effect limit): `spell_effects.md` §1;
- the Fireball flight, heights, scatter and impacts that the flame reuses: `spell_effects.md` §2 and §3.4;
- the Fireball drawing model and the trail rule: `bf003_playtest_fireball_grid_pursuit.md` §8.3–8.4;
- the shooter's pose: `machine_figure_animation.md` §2.7; the sound: `spell_sounds.md` (`SFX_Cast_Fireball`).

**Main result:** each warpfire flame is a **green Fireball**. It flies, arcs, scatters, leaves puffs and ends with a
burst exactly like a cast Fireball (`spell_effects.md` §3.4). Only the art (SPELLS **562–590**, colour bank **+32**),
the start point (16 units in front of the unit), the damage type (warpfire, death kind 3) and the jittered aim
differ. A shot is **1–6 independent flames**, all launched on the same tick.

## 1. Result tables

| part | art | placement | timing |
|---|---|---|---|
| head | SPELLS **562 + (i mod 4)**: 562, 563, 564, 565, 562 … (i = ticks since launch). Not directional | the flame's position and height (Fireball flight: 18 ticks, low arc) | from the launch tick T to T+17. Not drawn on the last flight tick, nor after a stop |
| trail puffs | SPELLS **562 → 581**, one frame per tick, **once** (not looping) | fixed, at the head's previous position and (almost) its previous height. One on T at the start, then one per tick from T+2 on, each where the head was the tick before. Not on T+1 (see §3) | 20 ticks each, gone on its 21st tick |
| end burst | SPELLS **582 → 590**, one frame per tick, once | **on the ground** under the flame's **last position** (the scattered destination after a full flight, the stop point after a hit or a dive below the ground). One per flame | 9 ticks, starting on the tick **after** the flight ends |

| frames | size | anchor (x, y) | FOL map | bank added | effective map | look |
|---|---|---|---|---|---|---|
| 562–565 | 32 × 32 | 16, 32 (bottom centre) | 7 | +32 | 39 | bright green fireball with sparks (head, and each puff's first four frames) |
| 566–581 | 32 × 32 | 16, 32 | 7 | +32 | 39 | darker green smoke shrinking to a few specks (the rest of a puff) |
| 582–590 | 32 × 32 | 16, 32 | 8 | +32 | 40 | green ball growing (582–585), then breaking into widening rings (586–590) |

All frames are drawn with their `.FOL` anchor, so a head or a puff sits with its bottom on its 3-D point and the burst
stands on the ground like a figure. `UPDATE/BINARY` and `FILE/BINARY` `SPELLS.FOL` agree for all of these records.

There is **no Shift developer variant** for this effect (unlike Fireball, `spell_effects.md` §3.9). Nothing is drawn on
the Warpfire Thrower figure itself: its shoot pose (§2.1) has no muzzle sprite.

## 2. Placement

### 2.1 Who fires, and the pose

The shot is the special routine of missile code 15. It runs when a script "Launch" reaches it
(`script_shooting.md` §1.2) or when a player Fire order reaches the unit (the clicked ground point is the aim). In
order:

1. **The flame count** is drawn first: `count = (rand mod 6) + 1`. It is drawn even if step 2 then fires nothing.
2. **The shoot pose** (action 7) is requested on the spot:
   - if both the unit's troop and leader sprite sets are the Warpfire Thrower's (`WarpFireThrower`, every shipped
     Warpfire Thrower), it is requested for **the whole unit** (`machine_figure_animation.md` §2.7: group 40 for a
     while, then stand);
   - otherwise (another unit given missile code 15) it is requested for the unit's **leader figure**;
   - such a unit with **no leader fires nothing**: no flame, no sound, no message.
3. The **flames are launched in the same tick**, one after another. They do not wait for any step of the pose
   (the pose has no fire step).

### 2.2 Aim of each flame

For each flame, in this draw order:

```
aim_y = target_y + (rand mod 48) − 24        # drawn first
aim_x = target_x + (rand mod 48) − 24        # drawn second
```

So each offset is in **−24 … +23** (48 values, not symmetric). The flame is then launched at (aim_x, aim_y) like an
innate Fireball, which makes **four more draws** for the scatter (x magnitude, x sign, y magnitude, y sign;
`spell_effects.md` §2.2) before the next flame's two jitter draws. The scatter uses the unit's own BS and range
**576**, with the distance measured from the **unit position** to the jittered aim. A flame has no range or arc test.

Per flame the draws are therefore: y jitter, x jitter, x magnitude, x sign, y magnitude, y sign. With count `c` a
shot uses `1 + 6c` draws, or only 1 when step 2 fires nothing.

### 2.3 Start point and heights

- **Start:** the unit's position (not a figure), moved **16 units forward** along the unit's gameplay facing `f`
  (0…511) at the moment of the shot. The displacement uses the same integer rule as the Dragon's 72-unit origin
  (`bf014_dragon_rendering.md` §3.2), with 16:
  - dx = `floor(16 × trunc(256 × sin(2πf/512)) / 256)`
  - dy = `floor(16 × trunc(256 × cos(2πf/512)) / 256)`

  Examples: f = 0 → (0, +16); f = 128 → (+16, 0); f = 384 → (−16, 0); f = 320 → (−12, −12); f = 64 → (+11, +11).
  The move applies to the start and the first flight position only. The destination is not moved, so the flight
  converges from the moved start towards the scattered destination. All flames of one shot share the same start.
- **Heights:** launch height **0**, aim height = a flier's half height plus elevation if a flying unit stands at the
  jittered aim point, else **0** (floor 0). The launch line's start height is the ground at the **unmoved** unit
  position, as for the Dragon. On flat ground the head flies at heights **1, 2 … 9, 8 … 0** over T … T+17 (the
  Fireball arc, `spell_effects.md` §3.4), so the flames lob low over the ground.
- **Flight:** fixed **N = 18**, position `dest + trunc((start − dest) × r / 18)` per axis with r = 18 … 0
  (`spell_effects.md` §2.3), whatever the distance. A long shot flies fast, a short one slowly.
- The flame aims at a **point**, never at a unit.

## 3. Animation and stages (one flame)

The effect's first update runs on the launch tick T (`spell_effects.md` §1.6–1.7). Every particle is drawn first and
then advances (draw-then-advance), so a new puff shows 562 on its birth tick and the burst shows 582 on its first tick.

Worked example: unit at (1000, 1000), facing 0, so the start is (1000, 1016). Jittered aim (1000, 1196), scatter 0,
flat ground, nothing in the way. Then the flight positions are y(r) = 1196 − 10r and x = 1000 throughout.

| tick | r | head (frame, y, height) | puff born this tick (y) | burst |
|---|---|---|---|---|
| T | 18 | 562, 1016, 1 | P0 at 1016 (the start) | – |
| T+1 | 17 | 563, 1026, 2 | none: the previous position 1016 is P0's | – |
| T+2 | 16 | 564, 1036, 3 | P1 at 1026 | – |
| T+3 | 15 | 565, 1046, 4 | P2 at 1036 | – |
| T+4 | 14 | 562, 1056, 5 | P3 at 1046 | – |
| T+8 | 10 | 562, 1096, 9 (top of the arc) | P7 at 1086 | – |
| T+9 | 9 | 563, 1106, 8 | P8 at 1096 | – |
| T+17 | 1 | 563, 1186, 0 | P16 at 1176 | – |
| T+18 | 0 | **not drawn** (the flight's last test, height −1: the flame is below the ground and ends) | P17 at 1186 | – |
| T+19 | – | – | P18 at **1196** (the destination) | **582** at (1000, 1196), on the ground |
| T+20 … T+27 | – | – | – | 583 … 590 |
| T+28 | – | – | – | **gone** |
| T+38 | – | – | P18 shows 581, its last frame | – |
| T+39 | – | – | P18 gone: nothing is drawn any more | – |
| T+40 | – | – | – | the effect ends; its sound is stopped |

- A puff born on tick b shows `562 + (t − b)` on tick t, for b ≤ t ≤ b+19, and is gone at b+20. P0 shows 581 on T+19
  and is gone on T+20. At most 19 puffs are ever left by one flame, so the original's trail limit is never reached.
- The trail lags the head by one position, with a one-tick gap after P0 (exactly as the Fireball trail,
  `bf003_playtest_fireball_grid_pursuit.md` §8.4). The last puff lands on the destination itself, on the tick after
  the flight ends, together with the burst.
- A puff's height is the head's height on the previous tick, within a fraction of a unit (bf003 §8.4). The last puff
  (P18) is at the destination's aim height minus 1 (on flat ground just below the surface; its bottom anchor makes
  this invisible).
- Up to 6 flames run this table side by side, each with its own destination and its own puffs and burst. They start
  on the same tick and, because N is fixed, their bursts all start on the same tick T+19 unless some are stopped.

## 4. Removal and every way a flame ends

| end | what is seen |
|---|---|
| **full flight against ground** (the usual case) | as §3: last head on T+17, nothing on T+18 except the trail, burst at the destination on T+19 … T+27, last puff gone at T+39. No terminal impact is made: the flame's last test at the destination (T+18) is its only chance to hit something there (`spell_effects.md` §3.4) |
| **full flight against a flier** (aim height ≥ 1) | the head **is** drawn on T+18 at the destination, at aim height − 1, and the terminal impact is made on T+18. Then as above from T+19. The **burst is on the ground** under the destination, not at the flier's height |
| **stopped by a hit** on tick H (a unit other than the shooter's, a building, a solid object; `spell_effects.md` §2.3) | H: no head; a puff at the previous position as usual. H+1: one last puff at the **stop point** (if it differs from the newest puff), and the **burst at the stop point**, on the ground there. Burst H+1 … H+9. Last puff gone at H+21, the effect ends at H+22 |
| **dives below the ground** in flight (a ridge between thrower and aim) | as "stopped by a hit": burst on the ground at the last tested position, one tick later |
| **hit on the launch tick** (the moved start point lies inside another unit, a building or a solid object) | T: no head at all; P0 at the start. T+1: no new puff (same point), burst at the start |
| **launch fails** (the global effect limit, `spell_effects.md` §1.2) | that flame draws nothing and makes no sound. `GMTXT 2021` if the shooter is in the player's army. Its jitter draws were already made. The other flames of the shot still try |
| **no leader** (non-Warpfire unit with missile code 15, §2.1) | the whole shot draws nothing, no pose, no message |
| **shooter destroyed or removed** during the flight | **nothing changes.** Innate effects are never cancelled (`spell_effects.md` §1.4); the flames fly, burst and fade normally |
| **target unit removed or moves** | nothing changes: the flames fly to fixed points |
| dispel, Ctrl+click, recast | do not apply (innate). A new shot adds new flames beside those still in flight |

In every case the effect stays alive until its last puff and its burst have finished, then disappears with no
further tail (`spell_effects.md` §1.5). Nothing visible is removed early.

## 5. Ownership of neighbouring frames

| frames | owner | used by the warpfire? |
|---|---|---|
| 537–557 | Madness (537–540), Conflagration flash (541–549), unattributed sparkles 550–557 (`spell_madness_visuals.md`, `spell_area_particle_visuals.md`) | no |
| 558–561 | Sapphire Arch's blue sparkles (`spell_transport_visuals.md`) | no |
| 562–565 | warpfire head, and the first four frames of every puff | yes |
| 566–581 | the rest of a warpfire puff | yes (puffs only, never the head) |
| 582–590 | warpfire end burst | yes |
| 591–594 | steam-gun cloud (effect 27, `gyrocopter_steam_gun.md` §6.1) | no |
| 595– | Flamestorm Shift column (`spell_obstacle_visuals.md`) | no |

The catalogue sheet name "Doomwheel bolt explosion" for 582–598 is wrong: 582–590 are the warpfire burst and the
Doomwheel uses the Warp Lightning flash (`spell_doomwheel_visuals.md` §5).

## 6. Test vectors

| before | action | after |
|---|---|---|
| Warpfire Thrower at (1000, 1000), facing 0, rand gives 2 for the count draw | shot at (1000, 1200) on tick T | count 3 flames; pose 7 on the whole unit; three effects created on T, each starting at (1000, 1016) |
| same, next draws for flame 1: y 47, x 0 | – | flame 1 aimed at (976, 1223) before scatter (y jitter +23, x jitter −24) |
| same, unit's troop set is not Warpfire and it has no leader | shot | count draw made, nothing else: no flame, no sound, no message |
| flame of the §3 example | T / T+3 / T+4 | head 562 / 565 / 562 |
| same | T+1 | head 563 at y 1026; puffs: only P0 (showing 563) |
| same | T+17 / T+18 / T+19 | head 563 at height 0 / no head, P17 at 1186 / P18 at 1196 and burst 582 on the ground at (1000, 1196) |
| same | T+27 / T+28 | burst 590 / burst gone |
| same | T+38 / T+39 / T+40 | P18 shows 581 / nothing drawn / effect ended, sound stopped |
| same flight, a unit is struck at T+5 (y = 1066) | T+5 / T+6 / T+14 / T+15 | no head, P4 at 1056 / P5 at 1066 and burst 582 at (1000, 1066) on the ground / burst 590 / burst gone |
| aim on a flier with aim height 20 | T+18 / T+19 | head 564 at the destination, 19 above the ground (terminal impact) / burst 582 on the ground under it |
| shooter wiped out on T+3 | T+3 … T+40 | flames continue unchanged |
| facing 320 | shot | every flame starts at unit + (−12, −12) |

## 7. Differences from the current public text and engine, and open items

Corrections and additions to public notes (gameplay):

- `game_rules.md` "Special weapons", row 15 ("D6 flames around the target") and `ranged_combat_handoff.md` are right
  but incomplete. Add: each flame is an **innate Fireball** projectile (`spell_effects.md` §3.4): 18-tick flight,
  launch height 0, Fireball arc, **stops on hit**, S4 (4 against buildings), 1 wound, no save, damage type warpfire
  (death kind 3), burns Tangling Thorns like a Fireball. Aim = target ± (−24…+23) per axis, **y drawn first**, then
  the ordinary bolt scatter with the unit's BS and range 576. Start 16 units ahead of the unit. Against a ground point
  there is **no terminal impact** (the Fireball rule), so a flame hits only what it flies into or what stands at
  its destination on the last flight tick.
- `spell_effects.md` §3.0 has no warpfire row. Suggested row: "warpfire flame (26), innate | unit position + 16
  forward | 0 / 0, arc | 18 ticks | yes | 4 (4) | 1 | no | 3 warpfire | plain + burns thorns".
- The shoot pose goes to the whole unit only for the Warpfire sprite set, else to the leader, and a code-15 unit with
  no leader does not fire (not stated anywhere yet).
- 🟡 Possible correction to `bf003_playtest_fireball_grid_pursuit.md` §8.3 (the same code path serves Fireball and
  warpfire): that section says the explosion starts **on the same tick** as the final in-flight test. This study finds
  it starts on the **next** tick: on the last test (r = 0, height −1) the head is removed and the flight is marked
  finished. The end step that creates the explosion runs on the following update. The same one-tick delay is in
  `spell_doomwheel_visuals.md` §4 for beams. The owner should check the engine's Fireball against this.

Differences from the current engine (`whshr/ranged.py` innate projectiles, `battle_view.py`):

- The engine flies warpfire as a 9-tick straight line drawn with `FLAMES1–4` meshes at ground + 8, with no scatter, no
  arc, no puffs and no burst. Replace it with the Fireball effect path with this report's art, bank and start.
- The jitter is drawn x first and over −24…+24. The original draws y first, over −24…+23, then scatters each flame.
- The engine's flames start at the unit's origin. The original starts them 16 units forward along the facing.
- The engine applies one hit at the end point after 9 ticks (terminal hit). The original has no terminal impact
  against ground (the Fireball's in-flight test at the destination on the last tick is the only hit there).
- The shoot pose, the leader/no-leader rule and the per-flame `SFX_Cast_Fireball` are not modelled
  (sound: `spell_sounds.md`, played at the unit position for each flame and stopped when that flame's effect ends).

🟡 Open (no original screen capture was made):

- The look of up to six overlapping green trails and bursts was not observed in game.
- Whether the one-tick gap between the last head (T+17) and the burst (T+19) is noticeable in play.
