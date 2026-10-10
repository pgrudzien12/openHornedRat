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
sprite set `SPELLS` (`sprite_names.md`: `SpellSprites`). Each frame uses its own colour map from its `.FOL` entry
(`FORMATS.md` "Color map"); the Fireball adds no bank offset, i.e. maps 0–15. Frame numbers below count from 0 in
`SPELLS.FOL`, and the frame ranges were checked by rendering them (`scripts/render_sprites.py`).

| Frames | Look | Use |
|---|---|---|
| 125–144 | a round fire puff, largest at 125 and shrinking to a speck at 144 (20 frames) | head (125–128) and trail (125–144) |
| 145–176 | a flame bolt in 8 directions × 4 phases | not used by the normal Fireball (only by the Shift-key developer variant, `spell_effects.md` §3.9) |
| 177–185 | a growing fireball (177–180), then an expanding, fading ring (181–185) | the explosion |

**Head.** For every tick of the flight, **from the launch tick on** (§8.3), one sprite is drawn at the projectile's position and height (§2.1 of
`spell_effects.md`, arc included). Its frame cycles **125, 126, 127, 128, 125, …**, advancing one step per tick.
It has no direction, because the puff is round.

**Trail.** On the launch tick a puff is left at the start point. After that, a puff is left at the head's
**previous** position and height only when that position differs from the newest puff's position. So there is no
second puff at the start; tick-by-tick table in §8.4. A puff plays frames **125 → 144**, one frame per tick
(20 ticks), and then disappears. It does not move or loop. The original keeps at most about 30 puffs per Fireball;
this limit is optional for an engine, because 18 flight ticks never reach it.

**Explosion.** When the flight ends, a 9-frame explosion (177–185, one frame per tick) is placed on the ground at
the projectile's **last position**. The cause of the end does not matter: stopped by a hit, below the ground on
the last tick (the usual case for a ground target, `spell_effects.md` §3.4), or terminal impact against a flier. The
effect stays active (visual tail, `spell_effects.md` §1.5) until the explosion and every trail puff have finished,
i.e. about 20 ticks after the last puff was left. During this tail it does no more damage.

Anchor: see §8.3. The engine's other projectiles use scenery meshes
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
| same | 3 | pause 0, not pausing; not collected yet (that tick's grid pass ran before the countdown) |
| same | 4 | collected by this tick's joiner pass (§8.1: the pass after the pause reached 0) |
| 9 Wolf Riders vs 9 cavalry, 7 riders with pauses 2–7 at the clash | 8–10 ticks later | each rider is collected on the tick after its pause reaches 0 (≤ frontage = 3 per tick), so all are in by about tick 8–10, and the fight spreads along the front |

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

- 🟡 Sprite anchor: the frame data gives bottom-centre (§8.3); whether effect sprites are drawn with the same anchor
  rule as unit figures was not checked on screen.
- 🟡 Frame ranges of the other spells' visuals in `SPELLS` (each spell has its own first frame; only the Fireball
  was mapped and checked visually). Ask for a separate batch when other spell visuals are implemented.
- ~~Same-tick vs next-tick collection of an expired pause~~: answered in §8.1 (next tick).

## 8. Follow-up answers (implementer questions, 2026-10-10)

### 8.1 Pause timing

- **One pause per model.** The original keeps a **single** timed-pause countdown per model. The charge start, the rout
  start and `ResetModelAnimations` all **set** that same countdown, so a newer pause **replaces** whatever was left of
  an older one. Two pauses never run side by side, and one never blocks the other's countdown.
  - Charge start: every model, `(stagger & 7) + 1` ticks (1–8).
  - Rout start: only models **at rest** at that moment, `(stagger & 7) × 3 + 6` ticks (6–27). A model that is walking
    when the rout starts keeps whatever pause it had.
  - `ResetModelAnimations`: `(stagger & 15) × 2 + 2` ticks (`movement_formation.md`).
  An engine with two fields gets the same result if setting either one clears the other.
- **Counting down.** The pause drops by 1 once per tick in the unit's model update, for every model, whatever its
  state (§4). When it reaches 0 the pausing state ends that tick.
- **Same tick or next? Next.** For a unit in melee, its update runs its **grid pass first** (the joiner or owner
  search of `grid_gap_closing.md` §2) and **then** its model update with the countdown. A pause that reaches 0 in
  tick T is therefore first collected by the grid pass of tick **T + 1**.

| Before (tick T, unit in melee) | During tick T | Tick T + 1 |
|---|---|---|
| unpaired at-rest model, pause 1 | grid pass skips it (still pausing); countdown → 0, no longer pausing | grid pass collects it |
| same, pause 3 | skipped; → 2 | skipped; → 1 (collected at T + 3) |
| model with charge pause 5, at rest, unit starts a rout | rout pause set to `(stagger & 7) × 3 + 6`, replacing the 5 | counts down from the new value only |

### 8.2 Bolt positions and heights

- **Whole units.** In the original the start point (unit position plus the origin model's offset), the scattered
  destination and the ground heights are whole numbers. Positions are `dest + trunc((start − dest) × r / N)` per
  axis, truncating toward zero, so at r = N the position **is** the start point exactly. An engine with fractional
  unit positions should round the start and destination to whole units **once, at launch**, then use the same
  formula. The r = N position then equals the stored (whole) start, and the ground under it equals the ground the
  launch line starts from. Truncating the start toward zero matches the original's conversion of positions; any
  consistent rounding avoids the cast-3 failure.
- **Height.** Confirmed: height = launch height + arc + `line(r)` − ground(here). Here
  `line(r) = trunc((startLevel − endLevel) × r / N) + endLevel`, with `startLevel = ground(start) + L` and
  `endLevel = ground(dest) + A`, all whole numbers. The in-flight test always runs first. The projectile is then
  removed if the height is **< 0**; height exactly **0 survives**.
- Beams (Lightning, Gaze, Warp Lightning, Banner of Wrath) have arc 0 and are subject to the same removal: a ridge
  stops a beam.

Beam vector (Lightning: L = 4, A = 4; flat ground 0 at start and destination; start (0, 0), destination after scatter
(0, 200); N = 1 + trunc(200 / 20) = 11; `line` = 4 throughout, so height = 8 − ground here):

| r | position | ground here | height | result |
|---|---|---|---|---|
| 11 | (0, 0) | 0 | 8 | test, flies on |
| 6 | (0, 91) | 8 | 0 | test, **survives** (exactly 0) |
| 5 | (0, 110) | 9 (a ridge) | −1 | test runs at −1 (a ground unit standing there is struck); then **removed**, no terminal impact |
| (no ridge) 2 | (0, 164) | 0 | 8 | within 40 of the destination: terminal impact at the destination after the test (`spell_effects.md` §2.4) |

(r = 6: −200 × 6 / 11 = −109.09 → −109, y = 91; r = 5: −90.9 → −90, y = 110; r = 2: −36.4 → −36, y = 164.)

### 8.3 Fireball visuals: timing and anchor

- **Head on the launch tick: yes.** The effect's first update runs later in the launch tick (`spell_effects.md`
  §1.6, §1.7). It places the head at the start point and draws frame 125. The frame advances by one after each
  update: 126 on the next tick, and so on.
- **Trail.** See §8.4 for the exact rule. In short: the first puff appears on the launch tick at the start point.
  After that a puff is left at the head's previous position only when that position differs from the newest puff's
  position. A new puff is drawn at frame 125 on the tick it appears.
- **End tick.** On the tick the flight ends (the tick of the final in-flight test), the head is **no longer drawn**
  and the explosion **starts that same tick**, showing frame 177. It sits on the ground under the last tested
  position and shows frames 177–185 on that tick and the 8 following ones.
- **Anchor.** Every frame used (125–144, 177–185) is 32 × 32. Its `.FOL` entry gives anchor x = 16 (the centre) and
  anchor row 0 counted from the bottom (`FORMATS.md` `.FOL`, the same fields as unit figures). Read as for unit
  figures, the point is the **bottom-centre** of the sprite:
  - the head and puffs sit just above their 3-D point;
  - the explosion stands on the ground, like a figure.
  🟡 This was not checked on screen. Use the frame's own anchor fields, read the same way as for unit sprites,
  rather than a hard-coded centre.
- **Other spells.** Not traced. Each spell has its own first frame in `SPELLS` and its own particle use (beams use
  a flash particle, not a head). Request a separate batch when they are implemented.

### 8.4 Trail spawn rule, tick by tick

Each tick, after the head has been placed:
- With no puff yet (the launch tick), a puff is left at the head's **previous position**. On the launch tick that is
  the start point, the same as the head.
- Otherwise a puff is left at the head's previous position **only if** the distance from there to the **newest puff**
  is greater than 0.

The test compares against the newest puff, not "did the head move this tick". So on tick 2 the previous position is the
start point, where the launch-tick puff already is, and **no second puff** is left there. Exactly one puff is ever
at the start point. On the final tick a puff is left at the previous position as usual, because it differs from
the newest puff.

Each puff's height is the previous tick's launch-height-plus-arc term plus the current tick's launch line. This is
within a fraction of a unit of the head's previous height, and an engine may simply use the head's previous height.

Example: Fireball from (100, 100) to (100, 280), N = 18, flat ground. The head positions are r = 18 (100, 100),
r = 17 (100, 110), r = 16 (100, 120), r = 15 (100, 130).

| Tick | Head (frame, position) | Puffs after the tick (frame, position), newest last |
|---|---|---|
| 1 (launch, r = 18) | 125, (100, 100) | P1 125 (100, 100) |
| 2 (r = 17) | 126, (100, 110) | P1 126 (100, 100). No new puff: previous position (100, 100) is P1's |
| 3 (r = 16) | 127, (100, 120) | P1 127 (100, 100); P2 125 (100, 110) |
| 4 (r = 15) | 128, (100, 130) | P1 128; P2 126; P3 125 (100, 120) |

So the trail lags the head by two positions from tick 3 on, and there is a one-tick gap after the first puff. Each puff
plays 125 → 144 and is gone after its 20th tick (P1's last frame, 144, is on tick 20).

### 8.5 Whole-number ground height

Every ground height in the bolt maths comes from one lookup. The same lookup serves the start, the destination, the
current position and the explosion.

1. The position is a whole-unit world point (§8.2).
2. The terrain height there is **interpolated** on the `GRND.GD` triangle plane that contains the point
   (`terrain_gd.md`).
3. It is converted to world units (× 8, the same scale as the horizontal axes).
4. It is **rounded to the nearest whole number, halves up**: `ground = floor(8 × h_GD + 0.5)` (heights are never
   negative).

It is **not** truncated: a ridge at 9.9 world units counts as **10**, so a bolt whose line is at 9 there is below the
ground and removed. The engine's battle ground lookup already returns world units (the ×8 is applied), so only the
rounding step is missing.

Vectors (BF003, whole-unit points, interpolated world-unit height → value the original uses; truncation in brackets
for contrast):

| Point | Interpolated | Original | (trunc) |
|---|---|---|---|
| (1100, 983) | 40.6 | 41 | (40) |
| (1100, 987) | 41.4 | 41 | (41) |
| (1100, 988) | 41.6 | 42 | (41) |
| any point at exactly n + 0.5 | n + 0.5 | n + 1 | (n) |

🟡 The original interpolates in single precision, so a value within about 10⁻⁵ of a half could round the other way.
This does not matter for an engine.
