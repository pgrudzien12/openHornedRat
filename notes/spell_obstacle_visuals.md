# Spell visuals that leave battlefield obstacles

Public behavioural report for Wind Blast [#260](https://github.com/pgrudzien12/openHornedRat/issues/260),
Flamestorm [#265](https://github.com/pgrudzien12/openHornedRat/issues/265),
Tangling Thorn [#267](https://github.com/pgrudzien12/openHornedRat/issues/267), and
Da Krunch [#272](https://github.com/pgrudzien12/openHornedRat/issues/272).
Part of [epic #259](https://github.com/pgrudzien12/openHornedRat/issues/259).

Gameplay, casting checks, scatter, damage and obstacle collision are specified in
`spell_area_effects.md` §§0–4. This report supplies the artwork and its playback.
T is the launch tick, including the first effect update; one battle tick is 0.1 seconds.
Frame numbers are zero-based indexes in the installed `SPELLS` assets. Heights and distances
are battle units. A ground height is sampled at the stated world point.

## 1. Results and shared rules

| Spell | Artwork | Main timing | Placement |
|---|---|---|---|
| Wind Blast | Sprites 379–386; trail loops 384–386 | Head T…T+54; trail begins T+5 and lasts until cancellation | Moving ground-level gust; independently jittering sprites at fixed trail obstacles |
| Flamestorm | Ignition sprites 121–124; `FIRE1–4` meshes; default column sprites 595–598, or 117–120 with Shift | Ignition T…T+17; rising first column T+18…T+36; lasting fire thereafter | Fixed aim point and randomly scattered stationary flames |
| Tangling Thorn | Sprites 199–204 | Six growth frames T…T+5, then hold 204 until cancellation | Twenty fixed ground points around the aim |
| Da Krunch | `DAKRUNCH` mesh; dust sprites 474–479 | Fall T…T+9; stand T+10…T+46; lift T+47…T+56; gone T+57 | Foot at aim; twelve fixed ground dust sprites |

All sprites in this batch are **nondirectional**: the camera does not select an eight-direction
variant. Meshes retain their geometry and materials from the installed battle's `SCENERY.PBX`.
Normal figure casting, wound and death animations are separate.

### 1.1 Sprite anchors and colours

Use the `.FOL` anchor, as established in `spell_attached_visuals.md` §2.2.
For these assets it is the bottom centre of the entire frame, including transparent pixels.

| Frames | Frame size | Anchor X/Y | Added colour-map bank | Effective map |
|---|---|---|---|---|
| 379–386 | 32 × 64 | 16, 64 | 16 | 19 |
| 117–120 | 128 × 128 | 64, 128 | 0 | 5 |
| 121–124 | 32 × 32 | 16, 32 | 0 | 6 |
| 595–598 | 128 × 128 | 64, 128 | 0 | **10** |
| 199–204 | 32 × 32 | 16, 32 | 0 | 12 |
| 474–479 | 32 × 32 | 16, 32 | 16 | 27 |

The effective map is the frame's stored map nibble plus the spell's bank. The catalogue's
increasing map order does **not** override this selection. In particular, Flamestorm selects
map 10 for 595–598, even though a catalogue using cumulative map wraps assigns those frames
map 42. Do not add a bank twice when using a decoder that already accepts a full map index.

### 1.2 Visual state and cancellation

Track each spell's age/stage, aim, active state, and individual particles' birth positions,
animation progress and any jitter. A mesh also needs its orientation. Visual positions need
not coincide exactly with the solid obstacle: Wind Blast's sprites jitter; Thorn and Krunch's
dust are scattered over a square around their circular obstacle.

These spells animate even when the target area contains no unit. Failed casting checks do
not create a new effect. In particular, a failed replacement cast does not remove the old
Wind Blast, Flamestorm or Tangling Thorn.

Cancellation removes the instance's sprites, meshes and obstacles immediately, without a
fade, closing flash or normal lift sequence. This includes the applicable recast, manual
cancel, dispel, and Wizard-class caster-removal paths in `spell_area_effects.md`. A Fireball
can additionally burn Tangling Thorn under that report's existing rules.

Being outside the camera view does not pause animation age, damage or duration.
Overlap is allowed; particles are not redistributed to avoid one another, figures or scenery.

## 2. Wind Blast

### 2.1 Moving gust

The head appears at the projectile position from `spell_area_effects.md` §1.3: the scattered
flight lasts through T+54, with an independent offset of 0…7 on each horizontal axis per tick.
Sample ground at that jittered point. There is no additional vertical lift.

| Tick | Head frame |
|---|---|
| T…T+4 | 379, 380, 381, 382, 383, respectively |
| T+5…T+7 | 384, 385, 386 |
| T+8…T+54 | Repeat 384, 385, 386, one frame per tick |
| T+55 onward | No head |

The artwork develops from a small patch of dust into a tall brown whirlwind. It has no
impact explosion and does not return to its five small starting frames after reaching full size.

### 2.2 Lasting trail

Use the established placement rule: beginning T+5, deposit at the head's **previous tick's**
position if there is no previous deposit or its distance from the newest trail sprite's
**previous tick's visual world X/Y**, including that sprite's jitter, is strictly greater than 16.
This comparison happens before the trail's new jitter is selected for the current tick.
At most 30 deposits are retained. The T+55 update can deposit at the final
T+54 head position before the head disappears.

Each deposit creates a radius-16, height-16 obstacle and a sprite. A newly born sprite shows
384 immediately, then 385 and 386, looping forever at one frame per tick. Its phase is relative
to its own birth tick; deposits born on different ticks need not be in phase.

On **every** displayed update, independently on each axis, offset the sprite from its fixed
deposit point by `8 − (random integer modulo 16)`: the possible offsets are −7…+8, inclusive.
This jitter does not accumulate or move the obstacle. Retain the ground height of the deposit;
do not resample ground under each visual jitter position.

The head's completion does not dismiss the trail, stop its animation or release the obstacles.
Only cancellation ends them. There is no damage from these lingering trail sprites.

## 3. Tangling Thorn

Create **twenty** independent sprites at launch. For each, select X and Y separately as
`aim coordinate + 32 − (random integer modulo 64)`. Thus each axis spans −31…+32 relative
to the aim, including corners outside radius 32. Sample ground independently at each point.
These positions remain fixed; they are not attached to the trapped figures.

All twenty sprites begin together and show frames **199, 200, 201, 202, 203, 204** on
T…T+5. The brown twig artwork grows over those six frames. From T+6 onward, each holds
**204** at exactly the same position, with no intervening blank, second growth cycle or jitter.

The radius-32, height-16 obstacle and holding effect start at T, before the artwork finishes
growing. The thorns can therefore hold units while the first small frame is showing.
They remain even if no unit was caught, or all originally caught units subsequently die.
Leaving the camera view and returning does not restart their growth.

There is no natural visual timeout. Cancellation, including destruction by a qualifying
Fireball impact, removes all twenty sprites immediately. Release of held units follows
`spell_area_effects.md` §3.4 and is not a shrinking-thorn animation.

## 4. Da Krunch

### 4.1 The foot

Use effect record **28**, `DaKrunch`, mesh **`DAKRUNCH`**, throughout all three stages.
This is one mesh moving vertically, with no sequence of alternative foot meshes and no sprite
anchor. It stays at the chosen aim X/Y without horizontal scatter or jitter.

Let G be ground height at the aim:

| T-relative ticks | Height above G | State |
|---|---|---|
| 0…9 | 120, 106, 93, 80, 66, 53, 40, 26, 13, 0 | Descending mesh |
| 10…46 | 0 | Standing mesh |
| 47…56 | 0, 14, 27, 40, 54, 67, 80, 94, 107, 120 | Lifting mesh |
| 57 onward | — | Removed |

The change from descending to standing, and from standing to lifting, has no empty frame.
The descending foot is turned to the caster-centre-to-aim bearing selected at launch.
The standing foot retains that orientation. When lifting starts, the bearing is taken again
from the caster's **current** centre to the aim, so a caster that moved can cause a yaw change
at T+47. Orientation otherwise stays constant within a stage. There is no pitch or roll.
Use the ordinary mesh yaw convention in `spell_visuals.md` §0.

The solid radius-32, height-40 obstacle starts at **T+10** and is removed at **T+47**.
The foot already reaches ground and performs its final descent crush at T+9: obstacle creation
is one tick later. A screen shake accompanies the standing transition at T+10.

### 4.2 Impact dust

At T+10, create **twelve** brown dust sprites. Each independently selects X/Y over the same
−31…+32 square used by Thorn, centred on the foot's aim; sample ground at each selected point.
They are stationary and all begin together:

| Tick | Dust frame |
|---|---|
| T+10…T+15 | 474, 475, 476, 477, 478, 479, respectively |
| T+16 onward | No dust |

Dust does not loop or follow the lifting foot. There is no second dust burst at T+47, no
lifting trail and no disappearance flash at T+57. The nearby green frames 480–485 are not
selected by this spell.

### 4.3 Cancellation correction

Cancelling during descent prevents **future** crush tests and removes the foot immediately.
It does not undo casualties already caused by the falling foot. Tall objects can qualify before
T+9 under the height test in `spell_area_effects.md` §4.2. The older statement that any cancel
through T+8 means “no crush at all” was incorrect and has been corrected there.

## 5. Flamestorm

### 5.1 Art selection

The normal spell consists of ignition sparks followed by small **3D flame particles**,
effect records **1–4**, names `Flame1–4`, meshes **`FIRE1–4`**. These retain their installed
mesh materials and fixed zero yaw, pitch and roll; they are not directional sprite frames.

There is also a four-phase sprite column:

| Key state at launch | Column frames | Appearance in the installed assets |
|---|---|---|
| Shift not held | **595–598**, bank 0 | 595–597 are transparent; 598 contains only eight nonzero pixels |
| Shift held | **117–120**, bank 0 | Large orange/yellow column |

The Shift choice persists for that cast. Changing the key later does not change its artwork.
Both choices retain the same ignition sprites, small mesh flames, obstacle and gameplay.
The familiar large column from the sprite catalogue is therefore the Shift-selected variant.

### 5.2 Ignition, T…T+17

Emit **three new sparks every tick**, up to twelve simultaneously. Each spark plays
**121→122→123→124**, one frame per tick, then disappears on the next tick; replacements
can appear on that same tick. These are small orange fire sprites, not four more column frames.

Choose each spark's X/Y independently as `aim coordinate + 16 − (random integer modulo 32)`:
−15…+16 on each axis. Ground is sampled at its selected position. Each spark stays at that
point for its life. There is no additional jitter or movement.

The obstacle already exists at T. Damage starts at T+18, as previously specified.

### 5.3 Column position and phase

The column's X/Y stays at the aim. Its first rise occupies **T+18…T+36**, with heights relative
to ground at the aim:

`−40, −37, −35, −33, −31, −28, −26, −24, −22, −20, −17, −15, −13, −11, −8, −6, −4, −2, 0`.

Afterwards, 19-tick column periods continue at ground level: T+37…T+55, T+56…T+74, etc.
They do not rise again. There is no blank between periods and no terminal flash.

Animation progresses through four column frames, but **repeats a phase across each period's
first two ticks**. For column period j starting at `T+18+19j`, its starting phase is
`(2 + 2j) modulo 4`. At offsets 0 and 1 show that phase, then at offsets 2…18 advance once
per tick, wrapping modulo 4. Add the selected base frame (595 normally, 117 with Shift).

| Tick | Normal frame | Shift frame |
|---|---|---|
| T+18, T+19 | 597 | 119 |
| T+20 | 598 | 120 |
| T+21 | 595 | 117 |
| T+36 | 598 | 120 |
| T+37, T+38 | 595 | 117 |
| T+55 | 596 | 118 |
| T+56, T+57 | 597 | 119 |

### 5.4 Transition to small mesh flames

T+18 leaves the existing ignition sparks at their T+17 positions and frames. From T+19,
sparks give way to a continuing population of up to **eight** mesh flames. A flame's first
phase is selected independently and uniformly from `FIRE1`, `FIRE2`, `FIRE3`, `FIRE4`.
It then displays the remaining meshes in increasing order, one per tick, ending at `FIRE4`.
Thus it lasts one to four displayed ticks. On expiry, its replacement can be drawn immediately,
at a newly selected position and starting phase. Each life stays at a fixed point.

Each mesh birth selects independent X/Y offsets over −15…+16 around the aim, and a vertical
integer over 0…63. During births on **T+19…T+37**, that vertical value is an **absolute battle
height**. From **T+38**, add ground height at the **aim** to it. Do not sample terrain under
the scattered mesh X/Y. Existing flames retain their birth height until replaced.
On ground above zero, early flames can consequently lie partly or wholly below terrain.

### 5.5 Exact ignition overlap and first mesh births

At T+17, the twelve visible sparks are the three births from each of T+14, T+15, T+16 and
T+17. Identify the first, second and third spark of each group by their creation order.
All twelve retain their displayed frame during T+18. From T+19, the following rules apply:

| Spark's birth tick | Displayed frame at T+17/T+18 | Subsequent spark behaviour | First mesh successor |
|---|---|---|---|
| T+14, first and second | 124 | Each has a 50% early-removal test at T+19, before normal expiry | T+19 if kept by the test; T+20 if removed early |
| T+14, third | 124 | Holds 124; independent 50% removal tests at T+19, +23, +27, +31, +35 while still present | None |
| T+15, all three | 123 | Hold 123; independent 50% removal tests at T+20, +24, +28, +32, +36 while still present | None |
| T+16, first and second | 122 | Show 123 at T+19, 124 at T+20; removal test at T+21 before normal expiry | T+21 regardless of the test result |
| T+16, third | 122 | Same advancing frames and T+21 test | T+21 if kept; T+22 if removed early |
| T+17, first | 121 | Show 122, 123, 124 at T+19, +20, +21; removal test at T+22 before normal expiry | T+22 regardless of the test result |
| T+17, second and third | 121 | Same advancing frames and T+22 test | T+22 if kept; T+23 if removed early |

Each first mesh successor starts one continuing sequence of replacements with the positions,
random starting phases and lifetimes from §5.4. A successor does **not** inherit the spark's
position. Once a sequence has begun, its current mesh is replaced on expiry without a blank tick;
the spark-removal tests do not remove mesh flames.

Within an update, perform the applicable early-removal tests first, then advance surviving
sparks and existing meshes. Replace naturally expiring particles immediately. First mesh births
after an early removal occur afterwards, on the tick specified in the table. Thus a spark removed
early can leave a one-tick gap even though ordinary expiry has no gap. New meshes display their
randomly selected first phase immediately, without an extra advance on that birth tick.

The mesh population after each update is therefore:

| Tick | Number of mesh flames |
|---|---|
| T+18 | 0 |
| T+19 | 0–2 |
| T+20 | Exactly 2 |
| T+21 | 4–5 |
| T+22 | 6–8 |
| T+23 onward | Exactly 8 until cancellation |

These are active particle counts, including flames outside the view or below terrain. Up to four
frozen ignition sprites can overlap the eight meshes after T+23. Remove every remaining ignition
sprite at T+37, after that tick's normal particle update. No ignition sprite is born after T+17.

After ignition has gone, only the selected column and the recurring mesh flames remain.
They continue until cancellation, with no natural timeout or final burnout animation.

## 6. Before/action/after vectors

| Before | Action | Expected after |
|---|---|---|
| Wind launched at T | Render T+4, then T+5 | Head 383 then 384; first trail sprite 384 appears at T+4's head position |
| Wind's newest trail sprite was displayed at A; previous head point exactly 16 away | Update trail | No new deposit; existing sprites still advance and jitter |
| Wind's newest obstacle is at (0,0), its sprite was displayed at (8,0), previous head point is (20,0) | Update trail | No new deposit: measured distance is 12, despite distance 20 from the obstacle |
| Wind deposit born at U | Render U+3 | Frame 384 again; fixed obstacle unchanged despite sprite jitter |
| Wind head visible at T+54 | Update T+55 and T+56 | Head gone; possible last deposit at T+55; all trail loops continue |
| Thorn cast into empty ground | Run through T+6 | Twenty sprites grow through 199–204 and hold 204; obstacle remains |
| Thorn holding frame 204 | Burn it with a qualifying Fireball impact | All thorns vanish immediately; established release rules run |
| Krunch descending, tick T+9 | Update T+10 | Foot remains at ground; solid obstacle, twelve frame-474 dust sprites and shake begin |
| Krunch dust showing 479 at T+15 | Update T+16 | Dust gone, standing foot still present |
| Krunch standing at T+46 | Update T+47 | Obstacle removed; foot starts lifting at ground; no new dust |
| Krunch lifting at height 120 on T+56 | Update T+57 | Foot gone, no closing flash |
| A tall unit was crushed at T+7 | Cancel Krunch before T+8 | Foot vanishes; earlier casualties remain; no later crush or lift |
| Flamestorm, either key variant, at T | Render T…T+3 | Three sparks added each tick: 3, 6, 9, 12 visible; each advances one frame per tick |
| Shift-selected Flamestorm just finished ignition | Render T+18 and T+19 | Column frame 119 both ticks, at ground−40 then ground−37 |
| Normal Flamestorm | Render first column | Transparent 595–597 / sparse 598 selected; small meshes provide the fire, not the 117–120 column |
| Flamestorm at aim ground height 100 | Birth a mesh at T+37, then one at T+38 | Earlier birth height 0…63; later birth height 100…163; X/Y independently scattered |
| Flamestorm; every early-removal test keeps its spark | Render T+19…T+23 | Mesh counts 2, 2, 5, 8, 8; four frozen sparks remain until T+37 |
| Flamestorm; every early-removal test removes its spark | Render T+19…T+23 | Mesh counts 0, 2, 4, 6, 8; no ignition sparks remain after T+22 |
| Third spark born T+16 is removed early at T+21 | Render T+21, then T+22 | That spark vanishes; its mesh successor first appears at T+22 at a new random point |
| Any active spell in this batch | Dispel successfully | Its art and obstacles disappear immediately; no normal end sequence |

## 7. Corrections and remaining checks

- Wind Blast uses a five-frame formation followed by a three-frame loop, including a lasting
  jittering trail; removing the whole effect at flight completion is incorrect. Follow-up research
  corrects its spacing comparison to use the newest sprite's previous jittered position, rather
  than the fixed obstacle centre; `spell_area_effects.md` §1.4 is updated accordingly.
- Tangling Thorn has twenty stationary sprites and a held final frame, not a looping aura on
  each trapped figure.
- Da Krunch uses one mesh through all stages. Its brown dust is frames 474–479; these are not
  extra Ere We Go frames. The descent-cancellation rule in `spell_area_effects.md` §4.4 is corrected.
- Flamestorm's 117–120 column is selected with Shift. Frames 121–124 are ignition sparks;
  normal burning uses `FIRE1–4` alongside the nearly empty 595–598 sprite sequence.
- `FORMATS.md` now distinguishes catalogue map reconstruction from a spell's explicit runtime bank.

🟡 No original-game runtime capture was made for this batch. Sprite appearance was checked
against the installed artwork, and the timelines above distinguish drawing from obstacle and
damage timing. Flamestorm's previously unspecified spark/mesh overlap is now specified in §5.5.
Remaining visual comparisons concern mesh material appearance in the original renderer and
camera-dependent occlusion of the below-ground first column/flames. No claim of pixel-for-pixel
runtime validation is made.
