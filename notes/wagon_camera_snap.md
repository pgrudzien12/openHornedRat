# Wagons: the camera-relative 45° snap and driving

Public behavioural report for the implementer's BF005 question (carts spinning with the camera and not driving).
Refines `game_rules.md` "Turning…" (Wagons) and `engine_gaps/formation_movement.md`; corrects one line of
`collision_probe_result.md` §5. Facing and view angle are in 1/512 of a turn, 0 = +Y, increasing clockwise.

## 0. Shared state (read this first)

- **The unit's facing** is the one movement and turning read and write. **The snap never changes it.**
- **The wagon layout** places the two figures, the team in front and the wagon behind, 11 units each side of the
  unit's position along a **layout direction**. Each time the layout runs it computes that direction **afresh from
  the unit's current facing** and the current view angle:
  `c = view angle mod 64`; `layout direction = ((facing − c + 32) rounded down to a multiple of 64) + c`
  (mod 512). This is the nearest 45° step of a grid shifted by c; an exact half rounds up.
  The result is used only to place the two figures. It is **not stored back**, so nothing accumulates however long
  the camera turns.
- **The figures' own drawn heading** is set to the unit's real facing whenever the layout runs. Their drawn frame is
  the usual camera-relative octant of that heading (`battle_viewer.md` "3D sprite direction"). Placing the pair on a
  45° grid aligned with the camera makes the pair line up with that octant.
- **The view angle** is the camera's rotation in the same 1/512 scale (`battle_compass.md`: the camera facing). The
  battle keeps the previous tick's value too.
- **The layout only exists for a wagon unit of exactly 2 figures.** A wagon reduced to 1 figure gets no layout:
  nothing is re-placed or snapped. Its class still gives every other wagon rule (look-ahead 0x27, never pushed, no
  reciprocal contact).

## 1. When the layout runs

Every tick, in the wagon's formation step:
- if the view angle is **unchanged since the previous tick** and the unit's footprint or facing has not changed (no
  turn step, no new footprint), the layout is **skipped** (only the re-forming state is cleared);
- otherwise the layout runs: the two figures are **put straight onto** their new places (no walking), their drawn
  heading is set to the unit's facing, and the unit's footprint is rebuilt.

The figures are carried with the unit when it moves; the layout does not move the unit, its route, its destination
or its facing. **A camera swing never slows or stops a driving wagon.**

## 2. Driving

A wagon drives under the ordinary movement rules (`game_rules.md` "Turning…", "Unit speed"). Its facing changes only
through those rules. The snap is applied afterwards, to figure placement only.

## 3. Test vectors

(a) Stationary wagon, facing 100:

| View angle | c | Unit facing after | Layout direction (figures placed along it) |
|---|---|---|---|
| 0 | 0 | 100 | ((100 + 32) → 128) + 0 = **128** |
| 10 | 10 | 100 | ((100 − 10 + 32) = 122 → 64) + 10 = **74** |
| 20 | 20 | 100 | (112 → 64) + 20 = **84** |
| 64 | 0 | 100 | 128 |

(b) Wagon driving due +X (facing 128) while the view angle goes 0 → 40 in steps of 4 over 10 ticks:

| View angle | 0 | 4 | … | 32 | 36 | 40 |
|---|---|---|---|---|---|---|
| Unit facing | 128 | 128 | … | 128 | 128 | 128 |
| Layout direction | 128 | 132 | … | 160 | 100 | 104 |

The distance covered is the ordinary 10 ticks of driving, exactly as with a still camera. The pair's axis tilts by up
to 32 units (22.5°) either side of the real facing, and jumps when c crosses 32.

(c) Wagon with 1 figure left, camera turning: no layout, so the figure keeps its place; facing and driving as usual.

## 4. Differences from the engine model

1. Do **not** write the snapped value into the unit's facing. Keep it as a separate layout direction used only to
   place the team and the wagon. That removes the accumulation and the "turn again" loop seen in BF005.
2. Recompute it from the real facing each time; run it only when the view angle (or the unit's footprint or facing)
   changed.
3. Only for wagon units with exactly 2 figures.

## 5. Corrections

- `collision_probe_result.md` §5(7): "the 45° camera-relative facing snap … whatever its model count" → the snap is a
  figure-placement layout and applies only while the wagon has exactly 2 figures (corrected there).
- `game_rules.md` "Turning…": "the wagon layout rounds the unit's facing" → it rounds a **copy** used for figure
  placement; the unit's facing is unchanged (clarified there).

## 🟡 Open

- No running original-game capture was made of a camera orbiting a moving wagon.
