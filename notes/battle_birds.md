# Battlefield birds (issue #257)

Public behavioural report for the ambient crows. Companions: `battle_viewer.md` "3D sprite direction" (camera-relative
octants), `spell_visuals.md` §0 (sprite anchors and colour maps), `deployment_flags.md` (the same sprite-marker
mechanism), `casualty_bookkeeping.md` (when a model counts as killed), `sfx.md` (sound banks).
Units: positions in world units, headings in 1/512 of a turn (0 = +Y, increasing clockwise), one step per battle tick.

## 0. Shared state (read this first)

- **The battle keeps a ring of the last 32 corpses.** Every killed model (any side; `casualty_bookkeeping.md`
  "killed") is entered into the next place of the ring at its death position, wrapping after 32. A newer corpse
  replaces the one 32 deaths older in the same place.
- **A bird belongs to one ring place**, not to one corpse. It always flies around **whatever corpse currently occupies
  its place**, so after 32 more deaths it moves on to a newer casualty. That is why the birds drift to where the
  fighting is.

## 1. Q2, Q3: population, spawn, despawn

- **No birds at the start** and none during deployment.
- While the ring is still filling (the battle's first 32 deaths), the deaths that land in **ring places 0, 8, 16 and
  24**, i.e. the **1st, 9th, 17th and 25th killed models of the battle**, each create **one bird** at the dead model's
  position, **160 height units above the terrain**. So a battle has **0 to 4 birds**: one after the first death, two
  after 9 deaths, and so on.
- `NoBirds` in the battle file (`[DYNAMIC_LOAD]`) disables them completely.
- **Birds never leave** and are never removed during the battle. No terrain, weather or time-of-day rule was found.

## 2. Q1, Q6: frames and drawing

| GENBATT frames | Size | Anchor X/Y | Map |
|---|---|---|---|
| 74–105 | 32 × 32 | 16, 32 (bottom centre of the frame) | 7 (the frame's own, no bank) |

- **Directional**: frame = `74 + 8 × phase + octant`. There are 4 wing phases (0–3), and the octant is the bird's
  heading relative to the camera, by the same rule as unit figures (`battle_viewer.md` "3D sprite direction").
  No mirroring.
- Drawn as an ordinary battle sprite at the bird's position and height **above the terrain under it** (the terrain is
  added at drawing time). Culled when off screen, but **always updated**. No shadow was found. Depth handling 🟡 is
  the same as other battle sprites.

## 3. Q4, Q5: flight

Each bird follows a fixed program, about **52 ticks per round**, repeated forever:

| Part | Ticks | Frames | Steering |
|---|---|---|---|
| aim, then flap ×4 | 16 | phases 0,1,2,3 repeated four times | aim at its corpse, then steer every tick |
| aim, glide | 1 + 16 | phase 0 held for 17 ticks | aim, then steer every tick |
| flap | 3 | phases 1,2,3 | steer every tick |
| aim, call, flap ×4 | 16 | phases 0–3 ×4 | aim; one call chance; steer every tick |

- **Birth**: the heading is random (0–511, one draw). The first update aims and shows phase 0, and the bird does not
  move on that tick.
- **Aim** (3 times per round): the bird's *wanted bearing* := the bearing from the bird to its corpse,
  `trunc(256 − 256 × atan2(cx − bx, by − cy) / π)` (the usual bearing convention). It is only refreshed at these aim
  steps, so between aims it is stale.
- **Steer** (every other tick): if the heading differs from the wanted bearing by **more than 8** (shortest way round),
  the heading turns by **8 units, always in the bird's own direction**: birds of ring places 0 and 8 turn
  anticlockwise, those of places 16 and 24 clockwise. It does **not** turn the short way. Otherwise the heading is
  kept. Then the velocity is set from the heading: per tick
  `dx = floor(256·sin(2πh/512) / 32) / 4`, `dy = floor(256·cos(2πh/512) / 32) / 4` (the sine/cosine as integers
  truncated toward zero, then an arithmetic shift), i.e. about **2 units per tick** along the axes and about 1.8
  diagonally. Height: `vz = floor((68 − z) / 16) / 4` per tick, with z the integer height above the terrain. So a new
  bird sinks from 160 towards **about 68 above the terrain** and then stays there.
- The velocity also applies on the ticks without a steering step, so a bird moves every tick.
- **The result is a loop around the corpse**: the bird turns the same way until it points roughly at the corpse,
  flies straight past it on a stale bearing, then turns round again at the next aim. A full turn at 8 units per tick
  takes 64 ticks, about 128 units of flight, so the loops are a few tens of units across.
- **No other reaction**: birds ignore shooting, spells, units and melee. Only new corpses moving into their ring place
  change their goal. They do not stay inside the battlefield edges.

**Call**: once per round, one draw out of 10. 2 of the 10 play a call at the bird's position: sound **10** or **11**
of the battle sound bank 2 (`sfx.md` "Battle2"; which sounds these are was not listened to 🟡). Otherwise silence.

## 4. Q7: randomness

The birds use the **game's single shared random stream**: one draw at birth (heading) and one draw per round per bird
(the call). In the original these interleave with gameplay draws. An engine aiming at exact replay parity with the
original would have to draw them there, too. Using a separate stream is a harmless deviation for an engine that does
not reproduce the original's random sequence anyway.

## 5. Test vectors

| Before | Event | After |
|---|---|---|
| battle starts, nobody dead | – | no birds |
| 1st model killed at (500, 700) | its death | bird A (ring place 0) at (500, 700), height 160 above terrain, random heading, phase 0; anticlockwise turner |
| 9th model killed at (900, 300) | its death | bird B (place 8) at (900, 300), circling that corpse |
| 33rd model killed at (1200, 400) | enters ring place 0 | bird A's next aim points at (1200, 400); it turns (anticlockwise) and flies there |
| bird heading 0, wanted bearing 200, anticlockwise turner | steer | heading 504 (turned −8; it goes the long way round) |
| bird heading 100, wanted bearing 105 | steer | heading unchanged (difference ≤ 8) |
| bird at height 160 | steer | vz = floor(−92/16) = −6 → −1.5 per tick |
| battle file has `NoBirds` | any deaths | no birds |

## 🟡 Open

- What sounds 10 and 11 of bank 2 are.
- Whether birds are hidden behind scenery like other sprites.
- No running original-game capture was made.
