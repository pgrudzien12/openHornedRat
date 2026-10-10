# BF003 playtest: Grudgebringer Fireball, a stalled melee, a pursuit ending at a house

Public hand-off for the implementer. It covers five symptoms from one recorded BF003 playthrough (Grudgebringer
Cavalry and Infantry against Goblin Stickers and Goblin Wolf Riders). Each symptom was traced in a deterministic replay
of the recorded battle log, and the original's behaviour is stated where it differs. Companion reports:
`spell_effects.md` (§2–§4: bolts, the magical hit), `grid_gap_closing.md` (§0–§2: the joiner search),
`movement_formation.md` (the timed pause), `script_behaviours.md` (§2.5: the contact latch), `building_units.md` (§5),
`pursuit_map_edge.md`, `flight_solid_obstacles.md`.

## 1. Short answers

| # | Symptom | Cause | Original behaviour |
|---|---|---|---|
| 1 | No Fireball is drawn | The battle view draws no spell effect at all (only missiles, innate flames and the impact explosion) | §2: a head sprite, a trail of fading puffs and a 9-frame explosion, all from `SPELLS` |
| 2 | No way to tell whether the Fireball worked | In-flight hits are silent in the original too, and the engine log records only the launch | §3: the three casts did fire; one struck and killed a goblin, one struck without wounding, one was destroyed on launch by an engine bug (§3.2) |
| 3 | Cavalry against Wolf Riders fought mostly one figure against one | A Wolf Rider's timed pause never counts down while it stands at rest in a melee, and pausing models are skipped by the joiner search | §4: the pause counts down every tick for every model, at rest or not |
| 4 | That melee stalled until the Wolf Riders broke | Same cause: from the clash on, 7 of 9 Wolf Riders were never placed on the grid, so the cavalry had nobody to strike | §4 |
| 5 | The cavalry stopped chasing the Wolf Riders | The engine treats a pursuer as a charger, so touching a house "ended the charge" and the pursuit | §5: starting a pursuit ends the charging state; a pursuer touching a building is only pushed clear |
| 6 | The cavalry then stood by the house ignoring move orders | Consequence of 5: the ended "charge" left the contact latch on while the unit still overlapped the house, so every move was undone | §5.3: in the original the latch is never set in this situation |

## 2. How the original draws a Fireball (also the Grudgebringer)

Both the Fireball spell and the Grudgebringer's item launch use the same visuals. They come from the battle's spell
sprite set `SPELLS` (`sprite_names.md`: `SpellSprites`), colour map 0. Frame numbers below count from 0 in
`SPELLS.FOL`, and the frame ranges were checked by rendering them (`scripts/render_sprites.py`).

| Frames | Look | Use |
|---|---|---|
| 125–144 | a round fire puff, largest at 125 and shrinking to a speck at 144 (20 frames) | head (125–128) and trail (125–144) |
| 145–176 | a flame bolt in 8 directions × 4 phases | not used by the normal Fireball (only by the Shift-key developer variant, `spell_effects.md` §3.9) |
| 177–185 | a growing fireball (177–180), then an expanding, fading ring (181–185) | the explosion |

**Head.** For every tick of the flight, one sprite is drawn at the projectile's position and height (§2.1 of
`spell_effects.md`, arc included). Its frame cycles **125, 126, 127, 128, 125, …**, advancing one step per tick.
It has no direction, because the puff is round.

**Trail.** Each tick the head has moved, a puff is left at the head's **previous** position and height. A puff
plays frames **125 → 144**, one frame per tick (20 ticks), and then disappears. It does not move or loop. The
original keeps at most about 30 puffs per Fireball. This limit is optional for an engine, because 18 flight ticks
never reach it.

**Explosion.** When the flight ends, a 9-frame explosion (177–185, one frame per tick) is placed on the ground at
the projectile's **last position**. The cause of the end does not matter: stopped by a hit, below the ground on
the last tick (the usual case for a ground target, `spell_effects.md` §3.4), or terminal impact against a flier. The
effect stays active (visual tail, `spell_effects.md` §1.5) until the explosion and every trail puff have finished,
i.e. about 20 ticks after the last puff was left. During this tail it does no more damage.

🟡 The vertical anchor of these sprites (bottom of the frame vs centre on the point) was not checked against the
original. Centre them on the point as an engine choice. The engine's other projectiles use scenery meshes
(`Arrows*`, `Explosion1..8`); the Fireball does **not**, because its art is the `SPELLS` sprite frames above.

## 3. What happened to the three casts

Engine replay of the recorded log (`python3 -m whshr battle-replay`); positions are world units.

| Cast (tick) | Flight | Result |
|---|---|---|
| 1 (444) | from the cavalry leader to a point among the Goblin Stickers about 280 away; 15 ticks of flight | struck the Stickers in flight (silent, as in the original). The S4 vs T3 wound roll (3+) failed: no casualty |
| 2 (893) | the cavalry was fighting the Stickers; the bolt struck them on its second tick | **one goblin killed** (7 → 6 models). Nothing in the log says so |
| 3 (1616) | the cavalry was fighting the Wolf Riders, with the aim point 22 away | **removed on its first tick, below the ground, without any test.** Engine bug, §3.2 |

### 3.1 Logging (engine recommendation, not original behaviour)

The original prints nothing for an in-flight hit and nothing when a bolt ends without a terminal impact, so the player
cannot tell either. For the engine's own battle log (not the message window), record per projectile spell:
- the launch: caster, aim point, scattered destination, flight length;
- every unit struck: wound roll, save, `MagicResistent` result, wounds dealt, deaths;
- the end reason: stopped by a hit, below ground, terminal impact, or dispelled.

### 3.2 Order of the per-tick bolt step (clarifies `spell_effects.md` §2.3)

One flight tick of an ordinary bolt, in this order:

1. Position `dest + trunc((start − dest) × r / N)`. In the original, positions are whole world units, so the first
   tested position (r = N) is **exactly** the start point.
2. Arc step (Fireball and arched bolts): +1 while `2r > N`, otherwise −1.
3. Height = launch line − ground here **+ arc**. This is the whole §2.1 height, arc included.
4. **The in-flight impact test always runs** at that height, even when the height is negative. A ground unit is struck
   whenever `height ≤ its object height`, so a negative height still strikes a ground unit there.
5. The projectile ends **after** the test if it hit something and stops on a hit. It is also removed, without a
   terminal impact, if the height (arc included) is **below 0**. Exactly 0 survives.
6. Otherwise r decreases, and the terminal rules of §2.4 apply.

Where the current engine differs: it tests the height **without the arc** **before** the impact test. It removes the
bolt at once when that height is negative and skips that tick's test. For a Fireball (launch height 0) this means:
- on the first tick the height without the arc is exactly 0;
- any rounding from non-integer positions, or ground rising by a fraction under the start point, makes it
  negative;
- the bolt then vanishes with no test, as cast 3 did (−0.0000 after a non-integer start point was truncated).

In the original the same tick has height +1 and the bolt flies on. In general, the arc lets a Fireball clear up to 9
units of ground that rises above the straight launch line. Without the arc, any such rise kills it.

Test vectors (flat ground at 16, Fireball, N = 18):

| Before | Step | After |
|---|---|---|
| r = 18, start (628, 869), ground under the start 16, arc 0 | tick 1 | position = start, arc 1, height **1**, test runs, flies on |
| same, ground under the start 16.0001 by rounding | tick 1 | height 0.9999, flies on (the engine: removed) |
| r = 0 at the destination, arc −1, a ground unit there | last tick | test runs at height −1 and strikes the unit (silently, caster excluded); then removed, no terminal impact |
| beam (arc 0), ground ahead rises above the line | the tick it is below | test runs at the negative height, then removed |

## 4. The timed pause in a melee (symptoms 3 and 4)

**What the replay shows.** The Wolf Riders had ended a pursuit and were re-forming when the cavalry clashed with them.
On that tick:
- only 2 of the 9 Wolf Riders had a grid cell;
- the other 7 kept a charge-start pause of 2 to 7 ticks, and the same values were still there 170 ticks later;
- every model with a pause left was skipped by the joiner search (`grid_gap_closing.md` §2.1: "not pausing");
- for the next 560 ticks the Wolf Riders had 0–2 placed models, and from the moment their one fighting model died
  they had none;
- the cavalry stood with 8 placed models and 0–1 fighting, until the Wolf Riders broke on a combat result.

**Original rule.** At the start of a unit's model update, every model with a timed pause (charge start stagger,
`ResetModelAnimations`, rout pause) has its pause decreased by 1. This happens **before** any decision about
stepping, so it also happens for models that are at rest, in a melee unit, or in any state. When the pause reaches 0,
the model leaves the pausing state and its action is set to walk. If it is at rest it still does not step, but it is
no longer "pausing", so the joiner search collects it on the next pass. The pause therefore lasts exactly its
length in ticks (2–8 for the charge start, 2–32 for `ResetModelAnimations`), whatever the model does in the meantime.

This also corrects an assumption in `reform_while_moving.md` §3, step 1 versus step 2. "A figure that is at rest is
skipped" must not skip the pause countdown: the countdown comes first, for every figure.

**Where the engine differs.**
- In a melee, the per-model step skips at-rest models before the pause countdown, so their pause never runs out.
- `battle_grid` then excludes them from the joiner collection forever.
- Any unit that is still pausing at the clash is affected: a unit hit while re-forming, one charged just as its own
  charge started, or one that had just stopped a pursuit.

Test vectors:

| Before | Tick | After |
|---|---|---|
| model at rest in a melee unit, unpaired, no cell, pause 3 | 1 | pause 2, still pausing, not collected |
| same | 3 | pause 0, not pausing; collected by the joiner pass of that tick or the next (🟡 within-tick order: count down before the grid pass) |
| 9 Wolf Riders vs 9 cavalry, 7 riders with pauses 2–7 at the clash | 8 ticks later | every Wolf Rider has been collected (≤ frontage = 3 per tick), and the fight spreads along the front |

## 5. Pursuit and buildings (symptoms 5 and 6)

### 5.1 What the replay shows

The cavalry pursued the broken Wolf Riders past a house (`Yelo2Stry`). For 3 ticks its footprint overlapped the house
and was **not pushed**. The engine then treated the overlap as a charge touching a non-target building:
- the "charge" ended, which dropped the attack target and sent "charge against you ended" to the Wolf Riders;
- the contact latch was set;
- next the unit shouted "Re-group!", stopped pursuing and re-formed **while still overlapping the house**.

The two later move orders were each undone by the latched-movement rule (`script_behaviours.md` §2.5), and the unit
stood still until the battle ended.

### 5.2 Original rule

- **Starting a pursuit ends the charging state** (and the halted, re-forming, braced and contact-latch states). A
  pursuer is "pursuing", not "charging", in every test that asks about charging. This repeats `pursuit_map_edge.md`
  §1 ("a pursuit is not a charge") for the building case.
- In the collision pass, a mover overlapping a building gets **contact** only if it is charging or in melee. Any
  other mover, **a pursuer included**, is simply **pushed clear** of the footprint. So a pursuer slides along a
  house and carries on, the pursuit ends only by its own rules (`pursuit_map_edge.md` §2), and no latch is set.
- `building_units.md` §5, table row "charging | building that is not its target → charge ends": "charging" means a
  true charge. The table's first row ("walking … pushed apart") also covers pursuers. That table is now annotated.

### 5.3 Where the engine differs

- The building pass treats "has an attack target" as charging. A pursuer keeps its pursued unit as its attack
  target, so it gets contact instead of a push.
- It was therefore not pushed (3 ticks overlapping), its pursuit was ended as a charge, and the latch was left on
  while the unit overlapped the house.
- In the original none of this happens. A latched unit standing in a building footprint and refusing moves remains
  possible only after a **true** charge ends on a non-target building (🟡 `building_units.md` §5). The fix for
  symptom 5 removes this occurrence.

Test vectors:

| Before | Event | After |
|---|---|---|
| pursuing unit (target = fleeing unit), footprint overlaps a house by 4 | collision pass | pushed clear of the house; still pursuing; target unchanged; no 0x09; no latch |
| charging unit (target T), overlaps a house that is not T | collision pass | contact: charge ends, halted, 0x09 to T, latch stays on |
| unit just switched from charging to pursuing | — | not charging: the house row "charging" no longer applies |

## 6. Corrections to public notes

- `spell_effects.md` §2.3: the sentence on negative height now states that the height includes the arc and that the
  in-flight test of that tick runs first (§3.2 here).
- `building_units.md` §5: "charging" excludes pursuers; a pursuer is pushed like a walking unit (§5.2 here).
- `reform_while_moving.md` §3: the pause countdown is not skipped for at-rest figures (§4 here).
- `animations.md` open item 1.5b (layout of `SPELLS`): the Fireball frames are in §2 here; other spells remain open.

## 7. Open items

- 🟡 Sprite anchor of the head, trail and explosion (§2).
- 🟡 Frame ranges of the other spells' visuals in `SPELLS` (each spell has its own first frame; only the Fireball
  was mapped and checked visually).
- 🟡 Within one tick, whether a pause that reaches 0 lets the model be collected by that same tick's grid pass. It
  depends on the unit's order of model update and grid pass; at most a one-tick difference.
