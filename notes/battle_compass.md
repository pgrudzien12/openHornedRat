# Battle compass: heading tape, wind indicator and power markers

Public implementation report (behaviour only). It describes how the battle panel's compass rectangle is drawn: the
"N NE E SE S SW W NW N" heading tape (`ICONS` 105), the wind-cycle strip (`ICONS` 106), the lightning warning, and
the player's power markers. It resolves the 🟡 items of `player_magic_panel.md` §2. Companions: `react_portrait.md`
(the same rectangle alternates with the reaction portrait), `game_rules.md` "Battle HUD layout" and "Winds of magic
and casting", `battle_viewer.md` (camera yaw convention).

## 0. Geometry and draw order

The compass is the panel rectangle at **panel (72, 0), 128 × 177**. All positions below are **compass-local**
(add (72, 0) for panel coordinates). It is drawn in this order:

1. **Background**: the compass art is **not** `ICONS` 99. It is the matching piece of the **panel background,
   `ICONS` 98** (640 × 176, the whole panel). The compass copies frame 98's own region x 72–199, so the art lines up
   with the rest of the panel. Frame 99 (124 × 172) is a stand-alone copy of the compass art that this paint does not
   use. 🟡 If an engine draws frame 99 instead, align it so that it coincides with frame 98's art.
2. **Heading tape** (§1): a **91 × 27** window at **(17, 76)**, drawn **on top of** the art, over the cream slot in
   the compass art. Nothing outside that rectangle is touched.
3. **Wind strip** (§2): a **49 × 18** window at **(38, 108)**. The strip is drawn first and the art of frame 98 is
   then drawn **over** it, so the sky shows only through the art's transparent opening.
4. **Lightning warning** (§2.1), at (57, 114), on top.
5. **Power markers** (§3): the art of that region is restored, then one marker per pool point is drawn on top.

So the tape never extends beyond 91 px. Drawing all 256 px of frame 105 is the cause of the reported overlap with
the message scroll.

## 1. Heading tape (`ICONS` 105, 256 × 27)

Frame 105 shows **N NE E SE S SW W NW N** evenly over 256 px: **N at x 0 and 256** (split across both edges),
NE 32, E 64, SE 96, S 128, SW 160, W 192, NW 224.

**Source offset.** With θ = the camera yaw in **radians** (the same yaw as `battle_viewer.md`: the eye at
`target + d·(sin θ, ·, cos θ)`, looking along `(−sin θ, −cos θ)`; θ = π looks north):

```
a     = trunc(θ × 255 / (2π))            # 255, not 256; truncation toward zero
src_x = (a − 173) mod 256                # result 0..255 (negative remainders + 256)
173   = 91 / 2 + 256 / 2 = 45 + 128      # integer halves of the window and tape widths
```

The 91-px slice `src_x … src_x + 90` of frame 105 is copied to the window. **It wraps around**: when the slice
passes x 255, the rest comes from x 0, as two pieces. The tape column at the window's centre (local x 17 + 45) is
`a − 128 (mod 256)`, i.e. the **view heading** (θ = 0 looks south → S in the middle). The same yaw gives the
sprite-direction heading `H = θ·512/(2π) + 256` (`battle_viewer.md`). The tape's centre column is about H/2.

**Redraw.** The tape is redrawn whenever the camera angle differs from the one last drawn. This is checked on every
display timer tick, so in effect every frame while the camera turns. It is also redrawn in full when the compass
comes back after a portrait pop-up. Nothing is drawn while a portrait occupies the rectangle.

### 1.1 Test vectors

| yaw (°) | θ (rad) | a | src_x | window centre (tape x) | letter at centre |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 83 | 128 | **S** |
| 45 | π/4 | 31 | 114 | 159 | SW (160) |
| 90 | π/2 | 63 | 146 | 191 | **W** (192) |
| 180 | π | 127 | 210 | 255 | **N** (window 210–255 then 0–44) |
| 270 | 3π/2 | 191 | 18 | 63 | **E** (64) |
| 359 | 6.266 | 254 | 81 | 126 | S (−2 px) |

**Playtest check (original game).** North is up on the minimap. With the camera looking from the bottom of the minimap
towards the top (towards its look-at mark), the compass shows **N** in the middle. That is θ = π (yaw 180°): the
camera looks along +Y, which is facing 0 in the game's unit facings (`battle_viewer.md`: `H = θ·512/(2π) + 256` → 0).
At that heading `src_x = 210`, and window column j shows tape x `(210 + j) mod 256`. So **N (tape x 0/256) is
centred at window column 46**, compass-local x 17 + 46 = **63** (panel x 135). The window is 91 px wide, so its
exact middle is column 45: N sits **1 px right of centre**, because of the 255/256 truncation. Columns 0–45 show
NW…N's left half (tape 210–255) and columns 46–90 show N's right half…NE (tape 0–44). Turning the camera clockwise
(seen from above) moves the tape so that E comes to the middle at yaw 270°.

With θ outside 0…2π the same formula applies. A negative θ truncates toward zero before the modulo.

## 2. Wind strip (`ICONS` 106, 256 × 18: sky with clouds)

Frame 106 is the wind indicator. A **49 × 18** slice of it shows through the art's opening at (38, 108). It scrolls
with the **50 s wind cycle** (`game_rules.md`: one wind per 50 s of unpaused time):

```
phase = t mod 50000                      # t = the unpaused battle clock in ms, as last sampled
c     = trunc(phase × 255 / 49999) mod 256
src_x = c − 24;  if src_x < 0: src_x += 256   # wraps like the heading tape
```

The window's centre column (local x 38 + 24) shows strip x `c`, so the sky crosses the strip once per wind cycle.
At each wind it jumps back to the start. The clock is sampled **at most once per second**, the same check that
raises the winds, so the strip **steps once a second**.

| t (ms) | c | src_x |
|---|---|---|
| 0 | 0 | 232 |
| 25 000 | 127 | 103 |
| 40 000 | 204 | 180 (warning starts) |
| 49 999 | 255 | 231 |

### 2.1 Lightning warning (last 10 s of each cycle)

While `phase ≥ 40 000` (the last 10 s before a wind), a small looping flicker of **`ICONS` 108–110** (12 × 12
lightning frames, with blank steps in between) is drawn at compass-local **(57, 114)**, over the art next to the
strip. It advances one step per wind-strip redraw, i.e. about once a second. When the next cycle starts
(phase < 40 000) it stops and restarts from its first step at the next warning. 🟡 The exact order of frames and
blanks in the loop is not given here; any short flicker of 108–110 with gaps matches.

## 3. Power markers (`ICONS` 107, 8 × 8)

As `player_magic_panel.md` §2: one `ICONS` 107 marker per point of the **player's** pool (0–8), at compass-local
(34, 63), (40, 58), (47, 54), (55, 52), (63, 52), (71, 54), (78, 58), (84, 63), first point leftmost. They are
redrawn on every pool change and on a full compass redraw.

## 4. For the engine

- Draw the compass background from frame 98's region (x 72–199) or a correctly aligned frame 99. Then draw frame
  105 **only through the 91 × 27 window at (17, 76)** with the wrap-around slice above, not the whole frame.
- Frame 106 is the wind strip, drawn **under** the art at (38, 108), 49 × 18.
- Draw lightning frames 108–110 at (57, 114) in the last 10 s of each wind cycle, and frame 107 markers per power
  point.
- `ICONS` 111 (8 × 8) is not used by the compass.
