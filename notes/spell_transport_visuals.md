# Transport spell visuals

Public behavioural report for The Flying Bower
[#266](https://github.com/pgrudzien12/openHornedRat/issues/266), Sapphire Arch
[#263](https://github.com/pgrudzien12/openHornedRat/issues/263), and Skitterleap
[#275](https://github.com/pgrudzien12/openHornedRat/issues/275), under
[epic #259](https://github.com/pgrudzien12/openHornedRat/issues/259).

Gameplay is specified in `spell_channelled_effects.md` §§2–3 and `spell_lasting_effects.md`
§2. This report adds artwork, positions, animation, transitions and removal. T means the
successful launch tick, including its effect update. One battle tick is 0.1 seconds.
All frame numbers are zero-based indexes in the installed `SPELLS` assets; distances and
heights are in battle units.

## 1. Results

| Spell | Artwork | Placement | Main timing |
|---|---|---|---|
| Flying Bower | Head 186–193; dust 194–198 | Ground-following moving vortex, stationary dust along the flight | Take-off T…T+18; flight T+19…T+73; landing T+74; short dust tail |
| Sapphire Arch | Effect record 29, mesh `SAPHARCH`; sparkle sprites 558–561 | One fixed, scaling arch at the aim; eighteen fixed scattered sparkles | Art T…T+179; removed T+180 |
| Skitterleap | Smoke sprites 529–532 | One fixed departure sprite per caster figure | Ordinary isolated cast: T…T+3; teleport and smoke removal T+4 |

The sprites are nondirectional. They do not select a new frame for the camera angle, unit
facing or travel bearing. Sapphire Arch's mesh has a fixed world orientation, described below.
Frame changes occur once per effect update, with the transition exceptions stated explicitly.
Camera culling does not stop animation age or transport timing.

### 1.1 Anchors and palettes

Use the original frame dimensions and transparent padding. These frames all use bottom-centre
anchors, following `spell_attached_visuals.md` §2.2.

| Frames | Dimensions | Anchor X/Y | Added bank | Effective colour map |
|---|---|---|---|---|
| 186–193 | 32 × 64 | 16, 64 | 0 | 10 |
| 194–198 | 32 × 32 | 16, 32 | 0 | 11 |
| 529–532 | 32 × 64 | 16, 64 | 32 | 32 |
| 558–561 | 32 × 32 | 16, 32 | 32 | 38 |

Sapphire Arch uses its installed `SAPHARCH` geometry and materials, including the two texture
bindings `u_sarch1` and `u_sarch2`. The blue textured arch is not a sprite column. Preserve the
mesh's own origin and scale convention from `pbx_rnc.md`; the percentages below are relative
to that normal size.

## 2. The Flying Bower

### 2.1 Take-off and head frames

The take-off head moves from the casting origin figure to the caster unit's launch-time
centre over **T…T+18**, inclusive. Follow the existing 18-step projectile interpolation and
sample ground under the resulting point. Add independent horizontal offsets of **0…3** on
each axis on every displayed take-off tick, including T+18. Offsets are not cumulative.

The caster's figures remain visible and otherwise act normally during take-off. The head's
amber vortex artwork grows through **186, 187, 188, 189, 190** on T…T+4, then loops
**191→192→193**, one frame per tick. It never returns to the first five frames.

At **T+19**, replace the take-off head with the flight head immediately, without a blank.
The flight starts at the caster's current unit centre, towards the scattered destination
described in `spell_channelled_effects.md` §2.2. The caster's unit becomes lifted and its
figures are not drawn. The replacement does **not** restart the formation animation:

| Tick | Head frame | State |
|---|---|---|
| T+18 | 192 | Last take-off sample |
| T+19 | 193 | First flight sample; unit lifted |
| T+20 | 193 | Next flight sample; repeated phase at transition |
| T+21 | 191 | Three-frame cycle continues |
| T+22 | 192 | Flight |
| T+23 | 193 | Flight |
| T+73 | 192 | Last flight sample |
| T+74 | None | Head removed; unit lands |

Flight positions follow the 54-step path, with samples on T+19…T+73. Each sample adds
independent **0…7** X/Y offsets and uses ground at that point. There is no vertical airborne
arc for the vortex. The lifted unit's centre follows the previous flight sample, one effect
update behind the visible head, until landing.

Landing at T+74 restores the figures at the **nudged aim point**, not the scattered flight
endpoint. This can produce a visible position jump. There is no landing burst, reverse growth,
closing vortex animation or additional destination sprite. Shift at launch changes the flight's
damage as already documented; it does not select different Bower artwork.

### 2.2 Dust trail

No dust is deposited during take-off or on the first flight sample at T+19. The first deposit
is made at **T+20**, at the T+19 head position, including its wobble. Subsequent deposits are
also made at the head's **previous tick's** point, subject to the spacing rule below. The
T+74 update may still deposit dust at the final T+73 head position before landing.

Each deposit plays **194→195→196→197→198** at one frame per tick, beginning immediately
on its birth tick U. It is gone at U+5. The artwork shrinks from a broad brown dust patch to a
few specks; there is no extra fade after frame 198. Each sprite keeps the deposited X/Y and
ground height for its whole life. There is no dust jitter, drift, direction change or obstacle.

**Spacing:** let P be the previous head point eligible for a deposit, and use the established
integer-truncated centre distance. The first deposit is unconditional. Until the thirtieth
deposit has been made, later deposits require distance **greater than 8** from the most
recent deposit's birth point. At distance 8 or less, skip the new deposit but continue advancing
all existing dust.

After the **thirtieth deposit**, the comparison point remains that deposit's birth point for
the rest of the flight, even after its dust has disappeared. Later dust can still be emitted:
there is no cap of thirty total births. This means a long flight can emit on every subsequent
tick while away from that fixed reference point, rather than enforcing distance 8 between
each consecutive late deposit. At most one new deposit is born per tick, so at most five
five-frame dust sprites are visibly active together.

### 2.3 Tail and cancellation

After landing, surviving dust continues its current animation. Let L be the last deposit's
birth tick, measured relative to T. Its last visible frame is on T+L+4; it is removed on
T+L+5. The effect ends on **T + max(75, L+6)**: completion is detected on the update after
the last active dust has been removed. With a last deposit at T+74, this means frame 198
at T+78, no dust from T+79, and effect completion at T+80.

The caster remains channelled until that effect completion, rather than merely until landing.
Cancellation immediately removes head and dust with no tail. During take-off it leaves the
unit where it is; during flight it restores the unit at its current centre, one flight sample
behind the head. During the tail the unit has already landed. These cancellation rules remain
those of `spell_channelled_effects.md` §2.4.

## 3. Sapphire Arch

### 3.1 Mesh and growth

Place one `SAPHARCH` mesh, effect record **29**, at the aim X/Y and ground height there.
It never moves or rotates during the spell. Its orientation is selected from the caster-centre
to aim bearing at launch, using the ordinary mesh yaw convention; retain the full 1/512-turn
bearing rather than the coarser 64-direction quantisation used by some projectile meshes.
No pitch or roll is added.

The mesh uniformly scales about its own origin on all three axes:

| Tick | Displayed size |
|---|---|
| T | 10% |
| T+1…T+17 | 15%, 20%, …, 95% |
| T+18…T+161 | 100% |
| T+162…T+179 | 95%, 90%, …, 10% |
| T+180 | Removed |

There is no displayed 5% or 0% stage. This is a size change, not an opacity fade or a cycle
of alternative arch meshes. At T+20, previously swallowed units reappear while the arch is
already at full size. At T+161, new units are swallowed on the **last full-size tick**; the
first visibly smaller frame is T+162. Transport neither restarts the mesh growth nor produces
an extra flash. The mesh alone does not create a solid spell obstacle.

### 3.2 Blue sparkles

At launch, create **eighteen** blue sparkle sprites, all starting with frame **558**.
Each independently chooses:

- X: aim X + 48 − (random integer modulo 96), giving offsets −47…+48.
- Y: the same independent rule, giving a square distribution.
- Height: ground at that selected X/Y + 16 + (random integer modulo 32), giving 16…47
  units above local ground.

Each stays at its selected 3D point throughout the spell. They do not follow figures, orbit
the arch, drift upwards, resample terrain or inherit the arch's scale changes. They loop
**558→559→560→561**, one frame per tick, synchronised from T. Thus T+179 shows 561.
Their positions may overlap, and they remain at their full sprite size while the arch shrinks.
Do not include neighbouring red/green sparkles in this animation.

### 3.3 Removal and units in transit

At T+180, remove the mesh and all eighteen sparkles together. There is no residual particle
tail. Cancellation at any earlier stage removes everything immediately, skipping the shrink.
It does not release units already inside an arch; that requires the release event of a later
arch. Swallowed units' figures and banners disappear, with no separate per-figure smoke or
travel trail. Released units simply become visible at the positions specified in the gameplay
report. The arch still animates normally when no unit is swallowed or released.

## 4. Skitterleap

### 4.1 Ordinary isolated cast

At launch, create one smoke sprite at each caster figure's current world X/Y and the ground
under that point. All start together, displaying **529, 530, 531, 532** on T…T+3. These
32 × 64 sprites depict grey smoke with orange highlights. There is no random starting phase,
scatter, jitter, height offset, facing variant, mesh or connecting trail.

The departure positions are fixed at launch. Smoke does **not** follow subsequent movement,
formation changes or the teleport. During the four displayed ticks the spell does not itself
hide the caster's figures or give them the lifted state. They can still be drawn through the
smoke; this is not a gradual opacity fade of the figures.

On T+4, the smoke ends and the caster is placed at the destination. There is **no destination
smoke**, arrival flash, second four-frame cycle or lingering departure sprite in this ordinary
case. The leap uses the existing gameplay rules: no destination validation, no facing change,
no formation reset, and no replacement of the unit's movement order.

Cancellation before completion removes the departure smoke immediately and prevents the
teleport. Its dispel position is the **destination**, even though its artwork is at departure.
A failed launch has neither smoke nor teleport.

### 4.2 Overlapping-effect exception — original-game comparison still needed

🟡 The four-tick sequence is not a safe universal assumption for overlapping original spells.
A specific compatibility case to reproduce is: begin with no active spell effects, launch
Sapphire Arch, then cast Skitterleap with a one-figure caster while that arch is still active
and well before it expires.

The expected anomaly is a teleport on Skitterleap's **launch update**, while its four-frame
smoke still plays at departure and one of the existing arch's sparkle animations is replaced
by that smoke. This case has not been observed in a running original-game scene. Broader
combinations of overlapping effects, and casualties changing the figure count during the
four-tick departure, remain open validation cases.

The ordinary per-cast model in §4.1 remains the implementation baseline. Do not silently
generalise it into a claim that every original cast waits four ticks, and do not reproduce
unconfirmed overlap artefacts as the normal spell animation.

## 5. Before/action/after vectors

| Before | Action | Expected after |
|---|---|---|
| Bower take-off at T+18 | Update T+19, then T+20 | Head 192→193→193; unit lifted at T+19; first dust 194 at T+20 at the prior head point |
| Bower's newest deposit is at A; fewer than thirty deposits | Previous head point is exactly 8 away | No new dust; existing dust advances |
| Bower has made thirty deposits; head has moved far beyond the thirtieth | Advance slowly, keeping far from the thirtieth point | Can deposit each tick even when consecutive late deposits are no more than 8 apart |
| Bower dust born at U | Render U+4, then U+5 | Frame 198, then removed |
| Bower's final dust born T+74 | Run through T+80 | Unit landed T+74; last dust frame T+78; removed T+79; effect ends T+80 |
| Bower in flight, unit behind the head | Dispel | Head and dust disappear; unit is restored at its current centre, not the head's newest point |
| Arch just launched | Render T, T+17 and T+18 | Mesh 10%, 95%, 100%; eighteen sparkles run their unchanged four-frame cycle |
| Arch full-sized at T+160 | Update T+161, then T+162 | Swallow event with 100% mesh, then 95%; sparkles do not shrink |
| Arch T+179 | Update T+180 | 10% mesh and frame-561 sparkles removed together; no tail |
| Arch has swallowed a unit | Cancel arch | Art disappears immediately; swallowed unit stays in transit |
| Isolated Skitterleap; caster moves after T | Render T+2 | Frame 531 remains at the original figure ground positions |
| Isolated Skitterleap showing 532 at T+3 | Update T+4 | Caster at destination, departure smoke gone, no arrival animation |
| Isolated Skitterleap with no friendly unit at destination | Dispel from near the destination | Departure art removed; no teleport |

## 6. Corrections and remaining checks

- Frames 194–198 are confirmed Flying Bower dust, not extra vortex phases. The exact tail
  completion is now specified; landing and effect completion are different ticks.
- Bower consumes its take-off wobble on T+18 too. The older T…T+17 range is corrected in
  `spell_channelled_effects.md` §2.2.
- Sapphire Arch's supplementary artwork is **558–561**, assigning four frames previously
  grouped after Madness in the catalogue. Its growth and shrink do not scale those sprites.
- Skitterleap smoke stays at departure and has no arrival counterpart. The overlapping-effect
  case in §4.2 qualifies the older unconditional four-tick statement.
- Following the common trail rules also exposed a Wind Blast correction: its spacing check
  uses the previous jittered **sprite** position, not the fixed obstacle centre. This is corrected
  in `spell_obstacle_visuals.md` §2.2 and `spell_area_effects.md` §1.4.

🟡 No original-game runtime capture was made for this batch. Sprite artwork and Arch texture
bindings were inspected from the installed assets. Scene comparisons remain for Arch material
appearance and orientation, and especially the Skitterleap overlap/casualty cases above.
