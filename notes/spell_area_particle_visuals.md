# Area particle spell visuals: Flock of Doom and Conflagration of Doom

Public behavioural report for The Flock of Doom
[#269](https://github.com/pgrudzien12/openHornedRat/issues/269) and Conflagration of Doom
[#264](https://github.com/pgrudzien12/openHornedRat/issues/264), with one finding for
[#279](https://github.com/pgrudzien12/openHornedRat/issues/279) (frames 541–549). Gameplay is already public and is only
cited here: `spell_blades_flock_items.md` §3 (Flock strikes and timing) and `spell_area_effects.md` §5 (Conflagration
fuse, fall and finale). Shared drawing conventions: `spell_visuals.md` §0, `spell_attached_visuals.md` §2.2 (sprite
anchors), `spell_obstacle_visuals.md` §1 (colour maps, particle lifetimes, cancellation),
`spell_transport_visuals.md` (trail spacing and jitter).

Validation: the original's frames and frame metadata were inspected and the playback schedule was established from
the original's behaviour. No running original-game scene was captured, so scene-level appearance (exact colours on
screen, the shake's feel) remains a comparison item, marked 🟡 where it matters.

## 0. Shared particle rules used here

These are the rules of `spell_obstacle_visuals.md` §1, restated only where this batch depends on them.

- A sprite is drawn at its stored ground point with its `.FOL` anchor. For every frame in this report that is the
  **bottom centre of the whole frame**, transparent padding included. Its height is the **terrain height sampled
  once at birth** at that sprite's own point, plus any stated offset; it is never re-sampled.
- **Effective colour map = the frame's stored map + the spell's bank.**
- A non-looping N-frame particle draws its N frames on its first N updates and is removed on the next update. A
  caller may replace it on that same update, and the replacement draws at once, so **no blank frame** appears.
- **Off-screen sprites still animate**, jitter and count down; culling only skips drawing.
- **Cancellation** (Ctrl+click on the active entry, dispel, or removal of a Wizard caster, `spell_effects.md` §1.4)
  removes every sprite, mesh and projectile of the effect **at once**: no fly-off, flash, burst or fade is played.

## 1. The Flock of Doom

### 1.1 Art

| Frames | Size | Anchor X/Y | Bank | Effective map | What it shows | Used for |
|---|---|---|---|---|---|---|
| 357–362 | 32 × 64 | 16, 64 | 16 | 18 | thin streaks diving down, thickening | approach, first 6 frames |
| 363–366 | 32 × 32 | 16, 32 | 16 | 18 | a dark cluster of birds | approach, last 4 frames |
| 367–374 | 32 × 32 | 16, 32 | 16 | 18 | a flapping flock | each strike cycle |
| 375–378 | 32 × 32 | 16, 32 | 16 | 18 | the flock scattering, shrinking | fly-off |

All 22 frames are used, in these four runs only. They are **not directional**: the same frame is drawn whatever the
camera angle. 🟡 The on-screen colours with map 18 were not compared against a running original scene.

### 1.2 Birth

On the launch tick, **20 bird sprites** are created around the aim point P, one after another. For each:
`x = Px + 32 − (rand mod 64)`, then `y = Py + 32 − (rand mod 64)`, so offsets **−31…+32** on each axis. These are the
40 launch draws already public. Each sprite stands on the terrain at its own (x, y), height offset 0. The sprites are
created but **not drawn on the launch call itself**: the effect's first update, in the same tick T, draws them.

There is one sprite per bird position, **not one per target figure**. The birds never move: they do not follow units,
and they have no per-tick jitter. P is fixed (`spell_blades_flock_items.md` §3.2).

### 1.3 Playback (all 20 sprites in step)

| Ticks | Frames shown by every bird | Event |
|---|---|---|
| T … T+9 | 357, 358, …, 366 (one per tick) | approach |
| T+10 | **367** (replacement drawn at once, no blank) | **strike 1** (same tick) |
| T+11 … T+17 | 368 … 374 | |
| T+18 | 367 | **strike 2** |
| T+19 … T+25 | 368 … 374 | |
| T+26 | 367 | **strike 3** |
| T+27 … T+33 | 368 … 374 | |
| T+34 … T+37 | 375, 376, 377, 378 | fly-off, no strike |
| T+38 | – (all removed) | effect ends |

Each new run restarts the birds at the run's first frame **at their own birth positions** (they are not re-scattered,
and no random number is drawn).

### 1.4 Edge cases

- **Cancellation** at any tick removes all 20 birds at once. A dispel before T+10 leaves no strike, and the birds
  vanish without the fly-off.
- **Several flocks** stack: each is independent, with its own 20 birds and 40 launch draws.
- **No unit at P** changes nothing visually. The birds appear over empty ground and strike the empty point.
- Birds on very uneven ground keep their own terrain heights, so a flock straddling a slope is drawn at several heights.

## 2. Conflagration of Doom

### 2.1 Art

| Art | Size | Anchor X/Y | Bank | Effective map | Use |
|---|---|---|---|---|---|
| Sprites 92–95 | 32 × 32 | 16, 32 | 0 | 3 | falling fire, fuse k = 1 |
| Sprites 96–99 | 32 × 64 | 16, 64 | 0 | 3 | falling fire, k = 2 or 3 |
| Sprites 100–103 | 64 × 64 | 32, 64 | 0 | 3 | falling fire, k = 4 or 5 |
| Sprites 104–107 | 64 × 64 | 32, 64 | 0 | 3 | falling fire, k = 6 |
| Sprites 108–116 | 64 × 64 | 32, 64 | 0 | 4 | impact flash: a fireball growing then breaking into rings |
| Sprites 177–185 | 32 × 32 | 16, 32 | 0 | 9 | ground burst explosion (the Fireball's explosion art), 2 times in 3 |
| Sprites 541–549 | 32 × 32 | 16, 32 | 0 | 3 | ground burst explosion, alternative art, 1 time in 3 |
| Meshes `FLAMES1–4` (effect records 5–8, "SmallFlame1–4") | – | – | – | – | small burning flames left by each burst |

The four falling-fire sets are the same burning ball at four sizes. **A longer fuse gives a bigger falling fire.**
Note the `FLAMES1–4` meshes are the *small* flame records, not the `FIRE1–4` meshes used by Flamestorm.

The burst passes no colour bank: frames 541–549 use their own map 3, and 177–185 their own map 9.

### 2.2 Fuse (ticks T … T+9k−1): nothing is drawn

No sprite, mesh or projectile exists during the fuse, only the public panic tests. 🟡 The magic book's description
("a burning fireball appears high above… growing larger") does not match: in the original nothing of the spell is
drawn until the fall starts. Ordinary casting poses of the wizard are outside this report.

### 2.3 Fall (ticks T+9k … T+9k+9)

On the fuse's last tick (T+9k−1) the falling fire is set up at the aim point P. It is first drawn on the next tick.

- Position: directly above P, on a straight vertical line. Height above the ground at P on the tick with r ticks left
  (r = 9 … 0): `trunc(120 × r / 9)`, i.e. **120, 106, 93, 80, 66, 53, 40, 26, 13, 0**. That is **10 drawn samples
  over 9 steps**, both ends included.
- Frame: `base + (i mod 4)` for the i-th sample (i = 0 … 9), base = 92, 96, 100 or 104 by k (§2.1). Not directional,
  no scatter, no jitter.
- These ticks are the public fall tests. The last sample (height 0, T+9k+9) is the finale's tick.
- **No screen shake during the fall** (correction, §4).

### 2.4 Impact (tick T+9k+10)

On the tick after the finale, the falling fire is removed and replaced, in the same tick, by:
- the **flash** at P on the ground: frames 108 … 116, one per tick, on T+9k+10 … T+9k+18, removed on T+9k+19;
- **one camera shake**, the same shake as Da Krunch's landing (`spell_obstacle_visuals.md` §4.1) 🟡 (its curve is not
  specified here);
- the impact sound.

### 2.5 Ground bursts and flames (from T+9k+11)

**At most 5k burst sprites** belong to the effect at once (5 … 30).

1. **Births during the flash**, on each of the 9 updates T+9k+11 … T+9k+19:
   - one random draw picks the art for this update's births: `rand mod 3 == 0` → 541–549, otherwise 177–185;
   - **up to 3 new bursts** are born, while fewer than 5k exist. Each takes two draws: `x = Px + h − (rand mod 2h)`,
     then `y = Py + h − (rand mod 2h)`, with `h = 8k + 8` (= R), so offsets `1 − h … +h` around P. It stands on the
     terrain at its own (x, y) and **draws its first frame on its birth update**.
2. **After the flash** (its removal is noticed on T+9k+19), all remaining places are filled at once in the same tick,
   with one more art draw. This only matters for k = 6, where 27 births leave 3 places.
3. **Each burst** plays its 9 explosion frames once, one per tick. On the update it would be removed it is replaced,
   with no blank frame, by a **small flame mesh** at the same spot:
   - it starts on a **random** one of `FLAMES1–4` (one draw: `rand mod 4`) and then loops FLAMES1→2→3→4→1, one per tick;
   - it **flickers in place**: every update its drawn position is the burst point plus an offset of **−3…+4** on each
     axis (`4 − rand mod 8`, X then Y, two draws), kept at the burst's terrain height;
   - it keeps its default orientation (it does not turn to the camera or the caster).

### 2.6 Dying down (36 ticks from T+9k+20)

After the flash a 36-step countdown starts. On each update with c steps left (c = 35 … 1):
- `n = 5k − c` random picks are made, each `rand mod 5k`, choosing uniformly among the burst's 5k places. A pick that
  lands on a **burning flame** puts it out (removed at once). A pick that lands on a still-playing explosion, or on an
  empty place, does nothing. n ≤ 0 means no picks, so **the flames burn steadily at first and go out faster and
  faster near the end**;
- then every remaining sprite steps (explosions still playing turn into flames as in §2.5);
- if no sprite is left after that, the effect ends in that same update.

When the countdown reaches 0 (T+9k+55 at the latest), every remaining flame is removed and **the effect ends**. The
effect is still active (dispellable, `spell_area_effects.md` §5.4) until then.

### 2.7 Random-draw order (replay determinism)

All of these draws come from the game's single shared random stream, interleaved with gameplay draws, and they are
made even when the effect is off screen.
- Each update during the flash: flame flicker draws (2 per flame, oldest place first), conversions (1 start draw,
  then 2 flicker draws), then 1 art draw, then 2 draws per new burst.
- Each update while dying down: the n removal picks first, then the stepping as above.

### 2.8 Cancellation

Ctrl+click, dispel or the caster's removal (Wizard class) at any time removes everything at once:
- during the fuse: nothing was drawn;
- during the fall: the falling fire vanishes, with no flash, shake or bursts;
- afterwards: the flash, bursts and flames vanish together.

## 3. Test vectors

**Flock**, P = (1000, 1000), launched at tick T:

| Before | Action | After |
|---|---|---|
| first launch draw = 0, second = 63 | bird 1 created | bird 1 at (1032, 969) on the terrain there; drawn at T with 357 |
| birds created | updates T … T+9 | every bird shows 357 … 366 in turn |
| T+9 shown | update T+10 | every bird shows 367 at the same spot; strike 1 |
| T+33 shown (374) | update T+34 | every bird shows 375; no strike |
| T+37 shown (378) | update T+38 | birds removed; effect over |
| dispel at T+5 | – | all 20 birds removed at once; no strike ever |

**Conflagration**, P = (2000, 2000), k = 2 (R = 24, base 96, at most 10 bursts), launched at T:

| Before | Action | After |
|---|---|---|
| fuse running | ticks T … T+16 | nothing drawn (panic tests on T and T+9) |
| fuse ends at T+17 | tick T+17 | falling fire set up, not yet drawn |
| – | T+18, T+19, T+20, T+21, T+22 | fire at heights 120, 106, 93, 80, 66 above P, frames 96, 97, 98, 99, 96 |
| – | T+27 | fire at height 0, frame 97 (finale's tick) |
| fire at the ground | T+28 | fire gone; flash 108 at P; one camera shake |
| flash 108 | T+29 | flash 109; art draw; 3 bursts born (first frame each) |
| 3 bursts | T+30, T+31, T+32 | 3, 3, 1 more born (10 in all); then none |
| burst born at T+29 | T+38 | the burst turns into a flickering FLAMES mesh (random start) |
| flash 116 at T+36 | T+37 | flash removed; fill finds no free place; dying down starts |
| 10 flames, c = 9 at T+64 | update | 1 random pick (5k − c = 1) |
| c = 1 at T+72 | update | 9 random picks |
| countdown 0 at T+73 | – | remaining flames removed; effect ends |

**Conflagration**, k = 6 (R = 56, base 104, 30 bursts): fall T+54 … T+63, flash T+64 … T+72, 27 bursts born
T+65 … T+73, the last 3 filled on T+73; picks begin when c < 30 (from T+80); end at T+109 at the latest.

## 4. Corrections to public notes

- `spell_area_effects.md` §5.3: "The fall and the finale shake the screen" → the shake comes **once**, on the tick
  after the finale, with the impact flash (corrected there).
- `spell_area_effects.md` §5.4: "A flash and embers follow (≈ 10 + up to 36 ticks)" → the flash is 9 frames; bursts
  and flames follow as in §2.5–2.6, ending by T+9k+55 (corrected there).
- Unidentified frames (#279): **541–549** are Conflagration's alternative burst explosion. 550–557 remain
  unidentified (121–124 and 558–561 were assigned earlier, `spell_obstacle_visuals.md` and
  `spell_transport_visuals.md`).

## 🟡 Open

- Scene comparison of the Flock's colours (map 18) and of the flash and flames on screen.
- The camera shake's exact curve (shared with Da Krunch).
- Why the magic book describes a visible fireball during the fuse when nothing is drawn.
