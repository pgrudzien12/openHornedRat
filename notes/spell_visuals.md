# What projectile spells look like in flight

Public implementation report (behaviour only). It covers the drawing of every projectile spell except the Fireball,
which is in `bf003_playtest_fireball_grid_pursuit.md` §2 and §8.3–8.4 and whose model the other sprite spells follow.
Flight paths, timing, heights and impacts are public in `spell_effects.md` §2–3; this report adds only **what is drawn
where**. Companions: `sprite_names.md` (effect records 1–49 and their mesh files), `pbx_rnc.md` (`SCENERY.PBX` effect
meshes), `FORMATS.md` (`.FOL` anchors, colour maps).

For Curse of Anraheir, Azure Blades, Ere We Go and Mork Save Uz, see `spell_attached_visuals.md`:
per-figure animation, anchors, timing and cleanup. That report also confirms the absence of separate
effect art for Dispel Magic and Fists of Gork.

## 0. Shared model (read this first)

Two kinds of art are used:

- **Effect meshes** from the battle's `SCENERY.PBX`, named by the effect records of `sprite_names.md`:

  | records | name | mesh file |
  |---|---|---|
  | 12–15 | BurningBolts1–4 | `BOLTBUR1–4` |
  | 16–19 | Lightning1–4 | `LIGHT1–4` |
  | 20–23 | WarpLightning1–4 | `WLIGHT1–4` |
  | 24–27 | GazeOfMork1–4 | `GAZE1–4` |
  | 30–33 | HuntingSpear1–4 | `SPEAR1–4` |

  A mesh is placed at its 3-D point (x, y, height) and **turned about the vertical axis to the flight's bearing**,
  with the same yaw convention as the ordinary missile meshes (arrows). The bearing is the one from the start of the
  current flight leg to its aim. There is **no visible pitch or roll**: the original's pitch term is at most a few
  512ths of a turn, so draw level. 🟡 The original quantises the head's yaw to 64 steps per turn; an engine may use
  the exact bearing.
  **The `SPEAR1–4` meshes are the Hunting Spear's** (records 30–33). 🟡 Which art the ordinary artillery shots use
  was not traced here; the engine's current use of `SPEAR1–4` for them is not supported by this table.
- **`SPELLS` sprite frames** (the battle's spell sprite set, frames counted from 0). Each is drawn at its point with
  its `.FOL` anchor, exactly as for the Fireball (§8.3 there: 32 × 32 frames, bottom-centre anchor). A spell may add a
  **colour-map bank offset** of 16 or 32: use colour maps 16–31 or 32–47 instead of 0–15 (`FORMATS.md`
  "Color map"). A **directional** sprite picks one of 8 frames by the flight direction relative to the camera, with
  the same rule as unit figures (`battle_viewer.md` "3D sprite direction").

Every per-tick cycle below advances once per battle tick. The effect's first update runs on the launch tick, so a
cycle shows its first frame on the launch tick, as for the Fireball.

**Head** = the flying object itself, drawn at the projectile position and height of `spell_effects.md` §2 every
tick of the flight. **Trail** = objects left behind along the path. **Flash** = an end sprite at the end point.

## 1. Summary table

| spell (effect code) | head | trail | end | colour bank |
|---|---|---|---|---|
| **Hunting Spear** (13) | mesh, cycle `SPEAR1→2→3→4→1…` (records 30–33) | none | none (vanishes) | – |
| **Lightning** (5), **Banner of Wrath** shot, each **Storm of Shemtek** bolt | mesh, cycle `LIGHT1→4` (16–19) | **beam segments**: `LIGHT1→4` meshes, looping, one about every 32 units | final segment + **flash SPELLS 433–439** (7 frames) | +16 |
| **Warp Lightning** (22), also innate launches | mesh, cycle `WLIGHT1→4` (20–23) | beam segments `WLIGHT1→4` | final segment + **flash 522–525** (4 frames) | +16 |
| **Gaze of Mork** (17) | mesh, cycle `GAZE1→4` (24–27) | beam segments `GAZE1→4` | final segment + **flash 464–469** (6 frames) | +16 |
| **Piercing Bolts of Burning** (6) | mesh, cycle `BOLTBUR1→4` (12–15) | none | none | – |
| **The Burning Head** (7) | **directional sprite 32–39** (a flaming skull, one frame per direction, no phase cycle) | fire puffs **40–59**, 20 frames each (like Fireball puffs) | no explosion; the effect ends when the last puff has faded | 0 |
| **Pestilent Breath** (24) | sprite **533–536**, chosen by flight progress (§2.6) | **static** cloud sprites, one per tick, each frozen at the head's frame when it was left | trail removed one sprite per tick, oldest first | +32 |
| Storm of Shemtek, extra | a **storm sprite at the wizard** (SPELLS 391–394 forming, 395–398 at each bolt) 🟡 | – | – | +16 |

## 2. Per spell

### 2.1 Hunting Spear

- Head: the `SPEAR` mesh. Its record is `30 + k`, with k = 0, 1, 2, 3, 0, … advancing every tick from the launch
  tick. It sits at the spear's position and height: ground + 8 at the start of each leg and at its aim, straight in
  between (`spell_effects.md` §3.5). It is turned to the **current leg's bearing**. At every re-aim (every third
  tick) a new leg starts from the spear's position towards the target's new centre, so the yaw jumps to the new
  bearing then.
- No trail, no flash, no explosion. The spear simply stops being drawn when the effect ends: kill chain done,
  target lost, or strikes exhausted. The strikes themselves draw nothing special.

| tick | k (record) | yaw |
|---|---|---|
| T (launch; leg 1 from caster to target centre C₀) | 0 (SPEAR1) | bearing caster → C₀ |
| T+1 | 1 (SPEAR2) | same |
| T+2 (re-aim: leg 2 from the current position to C₂) | 2 (SPEAR3) | bearing → C₂ |
| T+3 | 3 (SPEAR4) | same |
| T+4 | 0 (SPEAR1) | same |
| T+5 (re-aim) | 1 | new bearing |

🟡 The re-aim falls on the third update after a launch (the leg clock starts at 9 and re-aims when it reaches a
multiple of 3), consistent with `spell_effects.md` A 3.5. The mesh cycle is independent of it.

### 2.2 Lightning family: Lightning, Banner of Wrath, Storm bolts, Warp Lightning, Gaze of Mork

All five share one beam model. They differ only in the mesh set, the flash and the start height. The start heights
are already public: Lightning 4 above ground; Warp from ground level; Gaze 4, or a flying caster's own height.

1. **Head**: the spell's mesh `base + k`, with k cycling 0–3 every tick, at the bolt's position and height, turned to
   its bearing.
2. **Beam segments**: on the launch tick, and afterwards whenever the head's previous position is **more than 32
   units** from the newest segment, a segment is left at the head's previous position and height. The rule is the
   same as for Fireball puffs (`bf003_playtest_fireball_grid_pursuit.md` §8.4), with spacing 32 instead of 0. Each
   segment is the same mesh set, **looping** `base → base+3` every tick, turned to the bolt's bearing (level). At
   about 20 units per tick, a segment appears every second tick, so the chain reads as a continuous crackling beam
   from the caster to the head. Segments never move. At most about 30 are kept.
3. **Arrival**: when the head comes within 40 of the aim point (the beam's terminal impact, `spell_effects.md` §2.3),
   a **last segment** is placed at the aim point, turned back along the beam (bearing + 256), and the head is
   removed.
4. **Flash**: the end sprite plays once at the aim point (the scattered destination), one frame per tick: Lightning
   / Banner / Storm bolt **433–439**, Warp **522–525**, Gaze **464–469**. All use colour bank +16. Then the segments
   and flash are removed. 🟡 The exact number of ticks the segments stay after the flash starts is not settled: keep
   them until the flash ends.
5. A beam stopped early (hit in flight, `spell_effects.md` §2.3) skips 3. It still shows the flash at its end point
   🟡.

### 2.3 Storm of Shemtek

Each bolt is §2.2 with the Lightning meshes and the 433–439 flash, launched from the wizard's leader at 4 above the
ground (timing: `spell_channelled_effects.md` §1). 🟡 A storm sprite also sits on the ground at the wizard's leader
figure. It plays **391–394** once when the spell starts and **395–398** as each bolt is released (colour bank +16).
The exact phase-by-phase cycle was not traced.

### 2.4 Piercing Bolts of Burning

Head only: the `BOLTBUR` mesh, cycling 12→15 every tick, at the bolt's position and height (ground + 8 at both ends,
a straight 18-tick flight, `spell_effects.md` §2). It is turned to the bearing. No trail, no flash.

### 2.5 The Burning Head

- Head: a **directional sprite**, frame `32 + d`, with d = 0–7 the flight direction relative to the camera (as for
  figures). The frames are a flaming skull seen from 8 sides. There is no phase cycle, colour bank 0, and it is drawn
  at the head's position and height.
- Trail: puffs exactly as the Fireball's (one at the start on the launch tick, then one at the previous position
  whenever it differs from the newest puff), but with frames **40 → 59** (20 frames, one per tick, then gone).
- End: **no explosion**. The effect stays (doing nothing) until its last puff has finished.

### 2.6 Pestilent Breath

- Head: sprite `533 + s`, colour bank +32. s is the **flight stage** (with N the flight ticks and r the ticks left, as
  in `spell_effects.md` §2.3): s = 0 while `4(N − r) ≤ N`, 1 while `≤ 2N`, 2 while `≤ 3N`, then 3. So the cloud
  **grows** in four steps over the flight: 533 a few small skulls → 536 a large cloud of skulls.
- Trail: every tick the head has moved, a sprite is left at its previous position with the **head's frame at that
  moment**. It does **not** animate and stays until removal. The path is lined with clouds growing from caster to
  target.
- End: after the flight, the trail sprites are removed **one per tick, oldest (caster end) first**.

| N = 18, r (ticks left) | 4·(N − r) | stage s (head frame) |
|---|---|---|
| 18 … 14 | 0 … 16 (not > 18) | 0 (533) |
| 13 … 9 | 20 … 36 (> 18, not > 36) | 1 (534) |
| 8 … 5 | 40 … 52 (> 36) | 2 (535) |
| 4 … 0 | 56 … 72 (> 54) | 3 (536) |

The stage rises on the first tick with `4·(N − r)` strictly greater than N, 2N, 3N. 🟡 The stage is updated after
the tick's drawing, so the frame may lag one tick behind this table.

## 3. Notes for the engine

- Draw the mesh heads and beam segments with the effect meshes of the battle's `SCENERY.PBX`, looked up by the mesh
  file names above.
- One generic "trail" mechanism covers the Fireball, the Burning Head, the beams and the breath. Its parameters per
  spell: mesh or sprite, start frame, frame count (or looping, or frozen), spacing (0 or 32), and removal (when the
  animation ends, at the end of the effect, or one per tick).
- Colour banks: +16 for the Lightning family flashes, Storm sprites and Gaze; +32 for Pestilent Breath; 0 for
  Burning Head and Fireball.
- Holding Shift at launch switches several spells to developer sprite variants (`spell_effects.md` §3.9). Those use
  SPELLS frames 60–63, 145–176, 401–424 and 440–463 (directional bolts). An engine can ignore them.

## 🟡 Open

- How long beam segments stay after the flash starts; whether an early-stopped beam shows its flash.
- The storm sprite's exact cycle; the head's 64-step yaw quantisation (optional).
- Not covered: Fireball (already public), Flamestorm, Conflagration, Wind Blast, Flock, Doomwheel bolts and the
  other area or lasting effects.
