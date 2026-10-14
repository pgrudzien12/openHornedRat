# Battle camera shake (GitHub #299)

Public implementation report on the camera shake that Da Krunch's landing and Conflagration of Doom's impact play,
and on the other things in the battle that use the same shake. It settles the 🟡 "shake curve" items of
`spell_obstacle_visuals.md` §4.1 and `spell_area_particle_visuals.md` §2.4.

Companion reports, cited rather than repeated:

- `spell_obstacle_visuals.md` §4.1 (Da Krunch: the foot stands at T+10).
- `spell_area_particle_visuals.md` §2.4 and `spell_area_effects.md` §5.3 (Conflagration: the impact tick T+9k+10).
- `machine_figure_animation.md` §2.9 (Gyrocopter death), `game_rules.md` "Death kinds" and
  `ranged_combat_handoff.md` (the Giant's death blast).
- `battle_viewer.md` (scene axes: mesh units, +Y up, 1 mesh unit = 8 BTS units).

**Correction:** `machine_figure_animation.md` §2.9 said the Gyrocopter's crash ends with "a blast … and a battle
message". That step is the **camera shake** (§5), not a message. Corrected there.

## 0. The model in one paragraph

The shake is a short, fixed list of **vertical offsets of the camera eye**, one per battle tick, with alternating
signs and decreasing size. Starting a shake restarts the list. Nothing in it is random, and nothing depends on where
the trigger happened. The camera's look-at point and its angles are untouched. So the whole view bobs straight up and
down for about 1.5 s and settles back exactly where it was.

## 1. Q1: what moves

- **Only the eye height.** On each tick the camera builds its eye position from the look-at point, the yaw and pitch
  and the distance, as usual. The shake value is then **added to the eye's vertical coordinate** (scene +Y, up).
- The **viewing angles are not re-aimed** at the look-at point. The camera keeps its yaw and pitch, so the image
  **translates** vertically. It does not tilt. For a pitched-down camera, the ground appears to slide a little up and
  down the screen.
- The offset is in **scene (mesh) units**: 1.0 = one mesh unit = 8 BTS world units. There is no horizontal component,
  and it does not depend on the view heading.
- The shaken eye then goes through the camera's ordinary height limits. These hold the eye within its allowed band
  above the ground under the look-at point, and keep it off the terrain. 🟡 So a camera already at a limit of that band
  loses the part of the bob that crosses the limit. With the engine's own camera rules (its terrain
  lift), applying the offset **after** the lift, as a pure presentation offset, is the recommended
  equivalent.

## 2. Q2: amplitude, duration, curve and randomness

Two strengths are used in the game:

| Strength | Used by (§5) | Largest offset | Ticks with a non-zero offset |
|---|---|---|---|
| **strong** | Da Krunch, Conflagration of Doom | 1.0 mesh unit | 15 |
| **medium** | the crash deaths of the Giant, the Wyvern and the Gyrocopter | 0.6 mesh unit | 11 |

- **Curve:** the sign alternates **every tick**: −, +, −, +, … So the bob has a 2-tick period, 5 Hz at 10 ticks/s.
  The size stays at full strength for 5 ticks, then drops in steps of 0.2 every 4 ticks (2 ticks for the last
  step). The exact values are in §6. The steps are discrete: there is no smooth decay and no interpolation.
- **Start:** the first offset shows on the tick **after** the trigger, and it is **negative** (the eye moves down).
  The list's own first value (+1.0, or +0.6 for medium) is loaded at the trigger and is **never shown**, because the
  next tick already advances past it. An engine can reproduce this simply by starting its table at the value shown
  in §6.
- **End:** after the last non-zero value the offset is 0 and stays 0 until the next shake.
- **Randomness:** none. The shake draws **nothing** from the battle's random stream, and an engine's shake must not
  draw from it either.
- **Rate:** the original updates and draws the camera once per battle tick (its 100 ms battle timer). The shake
  advances once per tick. An engine drawing at a higher frame rate should **hold** the tick's value for all frames of
  that tick. Interpolating between ticks would soften the 5 Hz alternation and is a deviation (an engine choice).

## 3. Q3: distance, zoom, visibility, side

- The shake **does not depend** on the camera's distance from the trigger point, on zoom, on whether the point is on
  screen, or on which side cast the spell or owns the dying figure. The trigger knows only "shake, this strength".
  So an enemy Da Krunch behind the camera shakes the view exactly like the player's own one in the middle of the
  screen.
- It does not depend on zoom in mesh units either: the same 1.0 unit at every distance. It therefore *looks* larger
  when the camera is close (low eye height) than when it is far.

## 4. Q4: overlap and pause

- **A new shake during one restarts the list** from the beginning, with the new trigger's strength. Offsets are not
  added, the larger one is not kept, and the new shake is not ignored. Two triggers on the same tick act as one, and
  the later one's strength is used.
- **While paused:** no new shakes can start (the battle does not advance, so no spell or death fires). 🟡 A shake
  already running continues and finishes during the pause. The camera keeps updating on the battle timer while
  paused, so that it can still be moved, and the shake steps with that update. This follows from the update order
  and was not observed on screen. Freezing it during a pause is an acceptable engine choice: the difference lasts at
  most 1.5 s.
- **Within one tick:** the camera is updated **before** the battle simulation step. So a trigger during tick N's
  simulation is first seen in tick N+1's view, which is why the table starts at N+1.

## 5. Q5: everything that shakes the camera

Only these five things start a shake. Other spells, the dragon, cannons, other war machines, building collapse and
the Doomwheel do not.

| Source | Strength | When |
|---|---|---|
| **Da Krunch** (spell 19) | strong | the tick the foot stands, T+10 (`spell_obstacle_visuals.md` §4.1) |
| **Conflagration of Doom** (spell 8) | strong | the impact tick T+9k+10, with flash 108 (`spell_area_particle_visuals.md` §2.4). Not during the fall |
| **Giant** death | medium | its first death tick, right after its radius-40 death blast, before the corpse frame. Every Giant death shakes |
| **Wyvern** death **in the air** | medium | at the end of the fall, right after its radius-72 crash blast, on the tick after the corpse frame appears. A Wyvern killed while not flying lies down without blast or shake |
| **Gyrocopter** death **in the air** | medium | likewise at the end of its fall, right after its radius-72 crash blast (`machine_figure_animation.md` §2.9). A Gyrocopter that dies on the ground has no blast and no shake |

So a shake always comes **together with** the crash blast in the three death cases. Tie it to that blast (same tick,
after it) and the timing follows whatever the engine already uses for the blast.

## 6. Test vectors

Ticks are counted from the trigger tick N (the tick whose simulation step started the shake). The offset is added to
the eye height in mesh units.

**Strong** (Da Krunch, Conflagration):

| tick | N | N+1 | N+2 | N+3 | N+4 | N+5 | N+6 | N+7 | N+8 | N+9 | N+10 | N+11 | N+12 | N+13 | N+14 | N+15 | N+16 … |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| offset | (as before) | −1.0 | +1.0 | −1.0 | +1.0 | −1.0 | +0.8 | −0.8 | +0.8 | −0.8 | +0.6 | −0.6 | +0.4 | −0.4 | +0.2 | −0.2 | 0 |

**Medium** (crash deaths):

| tick | N | N+1 | N+2 | N+3 | N+4 | N+5 | N+6 | N+7 | N+8 | N+9 | N+10 | N+11 | N+12 … |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| offset | (as before) | −0.6 | +0.6 | −0.6 | +0.6 | −0.6 | +0.4 | −0.4 | +0.4 | −0.4 | +0.2 | −0.2 | 0 |

The "(as before)" at N is 0 unless another shake was already running: the camera update for tick N happened before
the trigger.

**Scenarios**

| Before | Event | After |
|---|---|---|
| no shake, Da Krunch cast at T | foot stands on T+10 | view offsets −1.0 on T+11, +1.0 on T+12, …, −0.2 on T+25, 0 from T+26 |
| strong shake started on tick N | a Giant dies on N+6 (offset +0.8 shown on N+6) | N+7: −0.6, N+8: +0.6, … (medium list restarts), 0 from N+18 |
| medium shake started on tick N | Conflagration impact on N+3 | N+4: −1.0, then the strong list to the end, 0 from N+19 |
| enemy Conflagration far off screen, camera fully zoomed out | impact on tick N | same strong list, same 1.0 mesh units |
| Wyvern killed on the ground | death | no blast, no shake |
| strong shake running, player pauses on N+3 | pause held for 5 s | 🟡 the list keeps stepping on the camera timer and ends during the pause. Freezing is an accepted engine choice |
| any shake | — | battle random stream unchanged (no draws) |

**Invariants an engine can assert**

- With no shake running, the offset is exactly 0, and the camera returns to its exact unshaken eye after every shake.
- A complete shake shows 15 (strong) or 11 (medium) non-zero offsets, with alternating signs starting with −. Because
  the list's first value is never shown, the shown offsets sum to −1.0 (strong) or −0.6 (medium), not 0. This is
  harmless: the offset is not accumulated.
- A shake never changes the simulation, picking state or the random stream (presentation only). In the original the
  shaken camera is also the one used for picking. That difference is at most one mesh unit vertically for 1.5 s, and
  an engine may ignore it.

## 🟡 Open items

- The shake during a pause (§4): derived from the update order, not observed.
- The effect of the camera's height limits on a shake at the edge of the band (§1).
