# Sprite animation layout (ROADMAP 1.5)

Black-box analysis of `.FOL/.BOP/.PAL` in `UPDATE/BINARY` (falls back to `FILE/BINARY`),
verified visually on labelled, anchor-aligned sheets. No disassembly.

## Status

| Topic | Status |
|---|---|
| Inventory and classification of all 288 `.FOL/.BOP` pairs | ✅ |
| Colour-map nibble = animation group (each group has its own 16-colour map) | ✅ verified visually (a wrong map gives garbage colours) |
| 8 directions stored explicitly (no mirroring), `frame = group_start + phase * 8 + direction` | ✅ fits 173/178 multi-phase groups automatically, all 72 sets by eye |
| Direction order: 0 = away from viewer, clockwise on screen | ✅ labelled 4× BRDHRS sheets (September 2026); the earlier counter-clockwise reading swapped the profiles |
| Standard unit layout `32+8+32+32(+8…)` = move, dead, attack, stand (+ shoot/cast) | ✅ move and dead, 🟡 attack/stand/shoot (visual, partly ambiguous) |
| Anchor: byte 3 = x, byte 2 = distance of the anchor row from the frame bottom | 🟡 x well supported; y only statistically |
| Script `dir` (0..511): 0 = +Y (north on the plan map), clockwise, so `direction = round(dir/64) mod 8` in a north-up view | 🟡 rotation sense from BTS statistics and scenery vs plan maps (`notes/battle_viewer.md`); zero frame derived, not observed |
| Frame timing | ✅ per-action animation scripts, one step per 100 ms tick — `notes/game_rules.md`, "Figure animation: actions, timing, and why the figures are never in step" |

## Inventory (`scripts/anim_inventory.py`)

Counted from `UPDATE/BINARY` (288 pairs; `HALBERD`, `ICON2`, `SPRITE3` skipped — different record layout):

| Class | Files | Frames | Recognition | Contents |
|---|---|---|---|---|
| directional | 72 | 6464 | every frame type 4, bytes 13–15 = `02 04 40`, bytes 0–1 = 0, every group a multiple of 8 frames | units, characters, monsters, artillery, vehicles, animals |
| portrait | 45 | 344 | frame 0 is 120×152, later frames smaller; all type 1, bytes 13–15 = `04 00 40` | portrait + mouth/eye overlays (int16 hotspot = position inside the portrait) |
| single | 69 | 69 | one frame | backgrounds `BACK*`, plan maps `MAP*`, `OPTIONS` |
| other | 98 | 1307 | the rest | 69 banners `BAN*` (3 frames: 72×104 type 2, 16×24 type 2, 32×32 type 4), `ICONS`/`ICONSTMP`, `SPELLS` (599), `GENBATT` (138), `SPARKLE`, `BACKALL` (21×120×152), 4-frame type-1 tiles (`LAVA*`, `G_LAV*`, `BFK_*`, `U_*`, `N_*`, `TORFLAM`), `BEAM` |

Flag bytes 13–15 per class: directional always `02 04 40`; portraits `04 00 40`; raw type-1 tiles
(`LAVA*`, `BEAM`…) `02 00 40`; banners, icons, spells `02 04 40`. The meaning is still unknown.

Frame sizes in directional sets: 32×64 (infantry), 64×64 (cavalry, corpses of infantry,
artillery, large infantry such as `BLACKORC`/`GRTSWORD`), 64×128 (`TROLL`, `RATOGRE`),
128×128 (`GIANT`, `TREEMAN`, `WYVERN`, `DRAGON`, `GYROCOPT`, `ROCKLOB`, `DWHEEL`, `GRTCANON` intact), 32×32 (`SHEEP`).
Corpse groups are often wider than the living frames (32×64 unit → 64×64 corpse).

## Layout (ready to paste into FORMATS.md)

### Groups

A **group** is a maximal run of consecutive frames with the same colour-map nibble
(`kind >> 4`). Every group has its own 16-colour map in `<NAME>.PAL` (in 68 of 72 sets all maps
differ; rendering a group with another group's map gives garbage colours). So the nibble is not a
"regiment colour variant" but the index of a separately quantised animation strip.

Inside a group of `n` frames: `phases = n / 8` and

```
frame = group_start + phase * 8 + direction
```

### Directions

8 directions, all stored (no mirroring: e.g. the `BRDHRS` rider's shield faces the viewer in `W`
(frame 6) and is hidden behind the horse in `E` (frame 2)).

| direction | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| on screen | N: away from the viewer (back visible) | NE | E: facing screen-right | SE | S: facing the viewer | SW | W: facing screen-left | NW |

The order is clockwise on screen (N → E → S → W), the same sense as script `dir` from `.BTS/.MRC`
(clockwise from +Y), so in a north-up view `direction = round(dir / 64) mod 8`. Verified in September
2026 on labelled 4× `BRDHRS` sheets (horse head right in frame 2, left in frame 6); the earlier
counter-clockwise table swapped the two profiles. Whether `dir = 0` really selects frame 0 has not been
observed in the game.

### Standard unit set (`32+8+32+32`, 37 files; `+8` for archers/wizards, 11 files)

| frames | group (nibble) | action | phases | notes |
|---|---|---|---|---|
| 0–31 | 0 | **move** (walk / gallop) | 4 | cycle 0-1-2-3; phases 1 and 3 are the similar "passing" poses |
| 32–39 | 1 | **dead** (corpse on the ground) | 1 | often 64×64 even for 32×64 units; blood pool |
| 40–71 | 2 | **attack** (melee) | 4 | weapon raised, swing, recovery |
| 72–103 | 3 | **stand** (idle) | 4 | small movements; flyers (`WYVERN`) flap their wings |
| 104–111 | 4 | **shoot / cast** (archers, wizards, `WYVERN`) | 1 | crossbow aimed (`DWXBOW`), arms raised (`CELWIZ`, `SEER`) |
| 112–119 | 5 | second cast pose (`CELWIZ` only, 64×64) | 1 | |
| 112–143 | 5 | cast with effect (`GOBSHAM` only, 64×64) | 4 | green lightning around the shaman |

`frame = [0, 40, 72][action] + phase * 8 + dir`, `dead = 32 + dir`, `shoot = 104 + dir`.
Example: `ESHIN` = 104 = 8 × 13 columns (4 + 1 + 4 + 4).

### Other patterns

| pattern | files | groups (visual labels) |
|---|---|---|
| `32+8+32` | `SHEEP`, `PACKPONY` | move, dead, stand (no attack) |
| `32+8+8+32` | `WARPFIRE` | move, dead, shoot (1 phase), stand |
| `32+8` | `GYROCOPT` / `ROCKLOB`, `DDCATPLT` | fly / fire (4 phases), wreck |
| `8+32` | `DWHEEL` | wreck, move |
| `8+8` | `IMPCWAG`, `GRTCWAG`, `VOLLYWAG` (nibbles 0,1); `IMPCANON`, `GRTCANON`, `VOLEYGUN` (nibbles 1,2); `FANATIC` | intact + wreck; **nibble 1 is always the wreck**; `FANATIC` = spinning + dead |
| `8+32+8` (nibbles 1–3) | `MORTAR` | ready, fire with smoke (4 phases), third pose (?) |
| `32+32+8` | `WAGON` | covered wagon moving, open cart moving, wreck |
| `32` | `CARAVAN`, `MRTWAG` (wheels roll), `ILMARIN` (walking figure), `DRAGON` (neck-and-head monster, 4 phases, 128×128) | |
| `32+8+8+8+8` | `DOOMDIVR` | flying (wing flap in phases 0/2 vs 1/3), then 4 single-frame poses (glide/dive?) |
| 12 groups | `PEASANT` (312) | 3 characters (A red, B green, C tan) × 4 actions, ordered by action: move A,B,C (0–95), dead A,B,C (96–119), attack? A,B,C (120–215), stand? A,B,C (216–311) |

The group order move → dead → attack → stand → special is kept wherever the actions exist,
and nibble 1 is dead/wreck in every file except `DWHEEL`, `WAGON`, `MORTAR`, `DOOMDIVR`, `PEASANT`.
The cannon files without nibble 0 (`IMPCANON`, `GRTCANON`, `VOLEYGUN`) may be the deployed half of
the `*WAG` (limbered) files, which have nibble 0 — a hypothesis.

### Anchor (bytes 0–3 of the record)

In `FORMATS.md` bytes 0–3 are `int16 hotspot_x, hotspot_y`. That reading fits portraits
(`AMBE` frame 1: x = 40, y = 57 inside the 120×152 portrait), but in **all directional sets bytes
0–1 are zero and bytes 2 and 3 are two independent `u8`**:

| byte | meaning (hypothesis) | evidence |
|---|---|---|
| 3 | anchor **x** in the frame | ≈ width/2 − 1…+1 (15/16/17 for 32 wide, 31–34 for 64, 63–64 for 128); bounding-box centre of the figure within about ±4 px in infantry; `DRAGON` has a different value per direction (63, 39, 29, 42, 63, 87, 96, 88), roughly mirrored around 63, which keeps the neck base in place in the aligned sheet |
| 2 | anchor **y** measured from the frame bottom (`y = h − byte2`), probably the ground/foot line | constant per group (0–24); within about ±3 px of the lowest opaque pixel of the group in infantry (exactly equal in 101 of 278 group/value combinations), 0 in cavalry and most 128×128 monsters |

Anchor-aligned sheets show figures standing still on a common point (e.g. `CELWIZ`, `GIANT`),
which supports the hypothesis, but the exact meaning must be confirmed in the game (e.g. where a
unit stands relative to its `x/y` from the `.BTS`).

**Outlier frames** (anchor differs from the rest of the group): `CELWIZ` 6, `CLANRATS` 32,
`GOBSHAM` 30, `GRTCANON` 0 (b3 = 64), `IMPCANON` 5 (0,0), `MCSWORD` 40, `PEASANT` 216,
`RATOGRE` 31, `RATSLAVE` 32, `VANHEIMS` 40 (0,0). In the aligned sheets they are visibly shifted
(`CELWIZ` 6, `GRTCANON` 0), so they are most likely data errors; an engine should use the group's
majority anchor. (`DRAGON` is not an error: the anchor varies deliberately per direction.)

## How it was verified

1. **Inventory** of all pairs (sizes, types, flag bytes, anchors, groups): `anim_inventory.py --verbose`.
2. **Colour maps**: `BRDHRS` group 3 rendered with maps 3, 0 and 2 — only its own map gives a brown horse.
3. **Layout, automatically**: for each group with ≥ 2 phases, the anchor-aligned opacity mask of
   frame `i` is compared with `i+8` (same direction, next phase) and `i+1` (next direction).
   `phase*8+dir` requires `d_phase < d_dir`: true in **173 of 178** groups. The 5 exceptions
   (`DOOMDIVR` g0, `HAMMERS` g2, `ILMARIN`, `SQUIGS` g0, `PEASANT` g0) are consistent by eye; there
   the phases differ a lot (hopping squig, big hammer swings, flapping wings) or neighbouring
   directions look alike (small robed figure), so the metric is a near tie (e.g. 0.29 vs 0.28).
4. **Walk cycle**: in group 0 of all 50 standard sets, phases 1↔3 are more alike than 0↔2 (`d13 < d02`).
5. **Stand vs attack**: group 3 has the lowest phase-to-phase difference in 37 of 50 standard
   sets (mean 0.28 vs 0.32 for move and attack). This is only weak support; the labels rest mainly on the visual check.
6. **Visually** (labelled sheets, rows = directions): `ESHIN`, `GIANT`, `BRDHRS`, `DWXBOW`, `CELWIZ`,
   `GOBSHAM`, `PEASANT`, `WAGON`, `DOOMDIVR`, `WARPFIRE`, `MORTAR`, `GRTCANON`, `DRAGON`, `HAMMERS`,
   `SQUIGS`, `ILMARIN`, `DWHEEL`, `GYROCOPT`, `ROCKLOB`, `FANATIC`, `IMPCWAG`, `WYVERN`, `SHEEP`,
   `PACKPONY`, `TREEMAN`, `CARAVAN`, `DDCATPLT`, `VOLEYGUN`, `IMPCANON`, `MRTWAG`, `VOLLYWAG` (31 sets).
7. **GIF output**: all 274 GIFs (808 frames) decoded with an independent LZW decoder; every frame
   decodes to exactly `w × h` pixels; the first frame was also checked visually.

### Per-file table (output of `anim_inventory.py --md`)

`d_phase / d_dir` = mean mask difference to the next phase / next direction (layout fits when the
first is smaller); `d13 / d02` = phase 1 vs 3 and 0 vs 2 in 4-phase groups; anchors = distinct `(byte2, byte3)`.

| file | frames | groups (frames) | actions (visual labels) | phase<dir in groups | d_phase / d_dir | d13 / d02 (4-phase groups) | anchor b2,b3 |
|---|---|---|---|---|---|---|---|
| AMBWIZ | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.36 / 0.48 | 0.20 / 0.37 | 8,31 9,31 |
| ARRABOYZ | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.31 / 0.40 | 0.15 / 0.33 | 6,15 6,31 |
| AVENGERS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.27 / 0.35 | 0.14 / 0.31 | 11,16 17,33 |
| BANDIT | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.28 / 0.43 | 0.13 / 0.30 | 7,16 7,32 |
| BIGUNS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.26 / 0.33 | 0.14 / 0.32 | 4,32 9,16 |
| BLACKORC | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.31 / 0.40 | 0.12 / 0.35 | 11,33 |
| BOARBOYZ | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.22 / 0.44 | 0.12 / 0.21 | 1,32 |
| BODYGRD | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.32 / 0.40 | 0.19 / 0.34 | 9,16 12,32 |
| BRDHRS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.21 / 0.45 | 0.12 / 0.20 | 0,32 6,32 |
| BRIWIZ | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.22 / 0.45 | 0.11 / 0.20 | 0,32 7,31 |
| CARAVAN | 32 | 0:32 | move | 1/1 | 0.08 / 0.34 | 0.01 / 0.01 | 0,32 |
| CARLGRD | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.32 / 0.42 | 0.21 / 0.35 | 10,33 11,17 |
| CELWIZ | 120 | 0:32 1:8 2:32 3:32 4:8 5:8 | move, dead, attack, stand, cast, cast2 | 3/3 | 0.28 / 0.41 | 0.09 / 0.30 | 3,15 3,31 13,31 |
| CERIDAN | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.32 / 0.50 | 0.21 / 0.38 | 5,16 5,32 |
| CLANRATS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.37 / 0.46 | 0.20 / 0.44 | 8,33 13,16 13,32 |
| DDCATPLT | 40 | 0:32 1:8 | fire, wreck | 1/1 | 0.34 / 0.56 | 0.28 / 0.46 | 0,32 |
| DOOMDIVR | 64 | 0:32 1:8 2:8 3:8 4:8 | fly, pose?, pose?, pose?, pose? | 0/1 | 0.58 / 0.46 | 0.07 / 0.35 | 9,31 |
| DRAGON | 32 | 0:32 | idle? | 1/1 | 0.63 / 0.79 | 0.68 / 0.65 | 0,29 0,39 0,42 0,63 … |
| DWHEEL | 40 | 0:8 1:32 | wreck, move | 1/1 | 0.15 / 0.32 | 0.04 / 0.03 | 0,64 |
| DWSLAY | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.31 / 0.42 | 0.19 / 0.36 | 11,16 11,32 |
| DWWAR | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.24 / 0.37 | 0.14 / 0.27 | 3,32 9,17 |
| DWXBOW | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.28 / 0.42 | 0.18 / 0.32 | 9,15 9,31 |
| ENGROL | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.23 / 0.35 | 0.10 / 0.26 | 3,32 15,19 |
| ESHIN | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.36 / 0.44 | 0.17 / 0.42 | 6,15 6,31 |
| FANATIC | 16 | 0:8 1:8 | spin, dead | 0/0 | - | - | 6,32 |
| GIANT | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.35 / 0.44 | 0.16 / 0.42 | 0,64 |
| GOBARCH | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.34 / 0.45 | 0.20 / 0.40 | 11,17 11,33 |
| GOBSHAM | 144 | 0:32 1:8 2:32 3:32 4:8 5:32 | move, dead, attack, stand, cast, cast fx | 4/4 | 0.32 / 0.49 | 0.19 / 0.36 | 12,32 17,16 17,32 |
| GOURARD | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.32 / 0.38 | 0.18 / 0.39 | 10,16 10,32 |
| GRTCANON | 16 | 1:8 2:8 | wreck, intact | 0/0 | - | - | 0,32 0,64 21,63 |
| GRTCWAG | 16 | 0:8 1:8 | intact, wreck | 0/0 | - | - | 0,32 19,65 |
| GRTSWORD | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.37 / 0.45 | 0.22 / 0.41 | 10,32 13,34 |
| GYROCOPT | 40 | 0:32 1:8 | fly, wreck | 1/1 | 0.20 / 0.35 | 0.18 / 0.10 | 0,32 0,64 |
| HAMMERS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 2/3 | 0.33 / 0.46 | 0.20 / 0.36 | 8,17 8,33 |
| ILMARIN | 32 | 0:32 | move | 0/1 | 0.29 / 0.28 | 0.09 / 0.34 | 10,16 |
| IMPCANON | 16 | 1:8 2:8 | wreck, intact | 0/0 | - | - | 0,0 0,32 |
| IMPCWAG | 16 | 0:8 1:8 | intact, wreck | 0/0 | - | - | 0,32 |
| IRONBRKS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.28 / 0.43 | 0.18 / 0.36 | 11,16 11,32 |
| KEELERS | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.32 / 0.38 | 0.17 / 0.32 | 11,16 11,32 |
| LEIT9TH | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.35 / 0.46 | 0.22 / 0.34 | 8,16 13,31 |
| MCCAPT | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.18 / 0.43 | 0.09 / 0.14 | 0,33 |
| MCSWORD | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.31 / 0.39 | 0.18 / 0.35 | 6,18 10,16 13,32 |
| MERCXBOW | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.29 / 0.39 | 0.16 / 0.31 | 10,16 10,32 |
| MORTAR | 48 | 1:8 2:32 3:8 | ready, fire, pose? | 1/1 | 0.18 / 0.40 | 0.22 / 0.24 | 4,33 |
| MRTWAG | 32 | 0:32 | move | 1/1 | 0.02 / 0.34 | 0.01 / 0.00 | 5,33 |
| MTDRKS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.21 / 0.45 | 0.13 / 0.17 | 0,32 |
| NLNHLB | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.33 / 0.41 | 0.17 / 0.35 | 7,16 12,34 |
| NTGOBLIN | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.32 / 0.41 | 0.19 / 0.37 | 13,15 13,31 |
| ORCBOYZ | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.33 / 0.44 | 0.17 / 0.36 | 7,16 7,32 |
| PACKMAST | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.37 / 0.44 | 0.19 / 0.42 | 6,16 10,32 |
| PACKPONY | 72 | 0:32 1:8 2:32 | move, dead, stand | 2/2 | 0.21 / 0.58 | 0.14 / 0.18 | 0,33 |
| PEASANT | 312 | 0:32 1:32 2:32 3:8 4:8 5:8 6:32 7:32 8:32 9:32 A:32 B:32 | move a/b/c, dead a/b/c, attack? a/b/c, stand? a/b/c | 8/9 | 0.28 / 0.30 | 0.15 / 0.32 | 11,16 11,18 12,16 12,32 … |
| PLAGMONK | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.31 / 0.38 | 0.16 / 0.38 | 9,16 11,32 |
| RAGNAR | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.20 / 0.44 | 0.10 / 0.18 | 0,32 |
| RATOGRE | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.35 / 0.47 | 0.15 / 0.39 | 0,31 0,32 6,32 |
| RATSLAVE | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.35 / 0.43 | 0.14 / 0.37 | 7,16 7,32 |
| ROCKLOB | 40 | 0:32 1:8 | fire, wreck | 1/1 | 0.17 / 0.61 | 0.22 / 0.20 | 0,64 |
| SEER | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.36 / 0.44 | 0.11 / 0.33 | 7,17 7,33 |
| SHEEP | 72 | 0:32 1:8 2:32 | move, dead, stand | 2/2 | 0.22 / 0.54 | 0.13 / 0.23 | 0,16 |
| SQUIGS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 2/3 | 0.34 / 0.35 | 0.11 / 0.47 | 7,31 |
| STICKERS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.36 / 0.47 | 0.20 / 0.44 | 13,15 13,31 |
| STMVERM | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.35 / 0.43 | 0.17 / 0.40 | 0,33 7,15 |
| TREEMAN | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.40 / 0.58 | 0.23 / 0.46 | 9,63 15,63 |
| TROLL | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.41 / 0.49 | 0.19 / 0.45 | 1,33 16,33 |
| VANHEIMS | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.23 / 0.48 | 0.13 / 0.21 | 0,0 0,32 8,31 |
| VOLEYGUN | 16 | 1:8 2:8 | wreck, intact | 0/0 | - | - | 0,32 |
| VOLLYWAG | 16 | 0:8 1:8 | intact, wreck | 0/0 | - | - | 0,32 |
| WAGON | 72 | 0:32 1:32 2:8 | move a, move b, wreck | 2/2 | 0.03 / 0.36 | 0.01 / 0.00 | 5,32 |
| WARPFIRE | 80 | 0:32 1:8 2:8 3:32 | move, dead, shoot, stand | 2/2 | 0.30 / 0.51 | 0.09 / 0.36 | 0,32 |
| WOLFRIDE | 104 | 0:32 1:8 2:32 3:32 | move, dead, attack, stand | 3/3 | 0.26 / 0.53 | 0.19 / 0.27 | 0,32 |
| WOODELF | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.33 / 0.44 | 0.12 / 0.27 | 5,16 8,32 |
| WYVERN | 112 | 0:32 1:8 2:32 3:32 4:8 | move, dead, attack, stand, shoot/cast | 3/3 | 0.37 / 0.52 | 0.19 / 0.43 | 0,64 |

Vehicles and machines (`CARAVAN`, `MRTWAG`, `WAGON`, `DWHEEL`) have almost identical phases
(only the wheels change), hence the very low `d_phase`. In the "actions" column the `WYVERN`
group 4 (spread wings) is labelled shoot/cast by pattern only.

## Scripts

All read the installation (UPDATE before FILE), Python 3 stdlib only. Output goes to `extracted/`
(game data, not for distribution; in `.gitignore`).

```
# library: loading, 3x5 font, canvas, PNG, GIF (LZW encoder)
scripts/anim_lib.py

# inventory + automated layout check (text or Markdown table)
python3 scripts/anim_inventory.py ".../WARFB" [--verbose] [--md]

# analysis sheet: frame numbers, group nibble, anchor lines (yellow x = byte 3, red y = h-1-byte 2)
python3 scripts/anim_sheet.py ".../WARFB" ESHIN out.png --cols=8 --scale=2 [--first=N --count=N --no-marks]

# export: <out>/<name>/<name>_sheet.png (rows = 8 directions, columns = phases of all groups,
# anchor-aligned, group titles with action labels) and <name>_gK.gif (8 directions side by side)
python3 scripts/anim_export.py ".../WARFB" ESHIN GIANT [--out=extracted/animations] [--scale=2] [--delay=15] [--no-gif] [--marks]
python3 scripts/anim_export.py ".../WARFB"      # all 72 directional sets: 274 GIFs, ~17 MB, ~25 s
```

`anim_export.py` also exposes `groups()`, `is_directional()`, `anchor_xy()` and `action_names()` for reuse
(e.g. by `render_battle` once names map to files, ROADMAP 1.4).

## Open questions
> **Tracked on GitHub**: these open items are tracked as issue #35 (`topic:sprites-animation`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- Zero point of the `dir` → direction mapping (the clockwise sense is established) — compare a unit's
  `dir` in a `.BTS` with its facing in the running game.
- Anchor y (byte 2): the ground contact point is only a statistical fit; byte 3 as x is much better supported.
  Why do portraits use bytes 0–3 as two int16 while directional sprites use bytes 2–3 as two u8?
- ~~Frame timing (frames per second per action), whether attack/shoot loop or play once~~ — answered in
  `notes/game_rules.md`, "Figure animation: actions, timing, and why the figures are never in step":
  one step per 100 ms tick, attack loops, shoot plays once and returns to standing. Still open: which of
  the 4 attack phases is the visual "hit" moment (the rules resolve the blow independently of the frame).
- Labels that are not certain: attack vs stand in sets where both look calm (`AVENGERS`, `BLACKORC`,
  `GOURARD`, `MTDRKS`, `VANHEIMS`…), `MORTAR` group 3, `DOOMDIVR` groups 1–4, `PEASANT` groups 6–11,
  `DRAGON` (a single 4-phase group).
- Cannons: `*CANON` files lack nibble 0 while `*WAG` files have nibbles 0–1 — are they one logical
  sprite set split across two files (limbered + deployed)? Crews are probably separate files (`ENGROL`?).
- Outlier anchors in 10 frames (list above): data errors, or does the game ignore per-frame anchors?
- Flag bytes 13–15 (`02 04 40` / `04 00 40` / `02 00 40`) — still unknown; they do not distinguish animation groups.
- Not covered here: `SPELLS` (599 frames, 43 maps, nibble wraps around), `GENBATT` (138),
  `SPARKLE`, banners, icons; `HALBERD`/`ICON2`/`SPRITE3` (separate task).

## Proposed ROADMAP.md changes

- 1.5 → 🟡 (almost ✅): "layout of directional sprites solved (8 directions × phases per colour-map
  group, standard move/dead/attack/stand/shoot); anchor x solved; export to sheets and GIFs
  (`scripts/anim_export.py`)". Remaining work as new rows:
  - 1.5a `dir` 0..511 → direction index, frame timing, anchor y — verified against the game under Wine (S–M);
  - 1.5b effect sprites: layout of `SPELLS` and `GENBATT` (projectiles, spell effects in 8/16 rotations?) (M).
    Fireball/Grudgebringer frames done: `bf003_playtest_fireball_grid_pursuit.md` §2.
- `FORMATS.md`: rename bytes 0–3 of `FolEntry` (int16 x/y for portraits; `u8 zero, zero, anchor_y_from_bottom, anchor_x`
  for directional sprites), describe the nibble as "animation group with its own colour map",
  and add the layout tables above; the old open question "hotspot, direction and frame order" can be closed.
- Phase 5 / M3 ("animated directional units"): the data side is ready — frame index formula and group
  labels in `anim_export.action_names()`.
