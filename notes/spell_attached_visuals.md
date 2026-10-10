# Spell visuals attached to figures

Public behavioural report for [#268](https://github.com/pgrudzien12/openHornedRat/issues/268),
with the shared cases [#261](https://github.com/pgrudzien12/openHornedRat/issues/261),
[#271](https://github.com/pgrudzien12/openHornedRat/issues/271),
[#274](https://github.com/pgrudzien12/openHornedRat/issues/274), and the absence of separate effect art in
[#270](https://github.com/pgrudzien12/openHornedRat/issues/270) and
[#273](https://github.com/pgrudzien12/openHornedRat/issues/273).
Part of [epic #259](https://github.com/pgrudzien12/openHornedRat/issues/259).

Gameplay remains specified by `spell_channelled_effects.md` §4 (Curse),
`spell_blades_flock_items.md` §2 (Azure Blades), and `spell_lasting_effects.md` §§3–5
(Ere We Go, Mork Save Uz, Fists of Gork, Dispel). This report supplies their presentation.
Frame numbers are zero-based indexes in the installed `SPELLS.FOL`/`SPELLS.BOP` assets.
T is the launch tick, whose effect update runs after launch. One battle tick is 0.1 seconds.

## 1. Result table

| Spell | Frames actually selected | Animation | Placement | Colour-map bank |
|---|---|---|---|---|
| Curse of Anraheir | 229–260 appearance; 261–292 loop | Four phases per stage, eight directions per phase; one phase per tick | One spirit at each target figure's ground position | +0: effective maps 14 and 15 |
| Azure Blades | 387–390 | Four-frame loop, one frame per tick | One blue sparkle sprite per target figure, 16 battle units above local ground | +16: effective map 20 |
| Ere We Go! | 470–473 | Four-frame loop, one frame per tick | One red sparkle sprite per target figure, at local ground | +16: effective map 26 |
| Mork Save Uz! | 486–489 | Four-frame loop, one frame per tick | One green sparkle sprite per target figure, at local ground | +16: effective map 29 |
| Dispel Magic | None | No separate effect animation | No sprite, mesh, aura ring or success flash | Not applicable |
| Fists of Gork | None | No separate effect animation | No fist sprite, mesh or impact flash | Not applicable |

The four visible effects use sprite artwork, with no mesh, projectile, trail or additional flash.
The spell's normal casting pose is separate from this table. Dispel messages, wounds, casualties and
changes to the caster's action still occur as specified by the gameplay reports.

## 2. Shared presentation rules

### 2.1 State and position

Each visible spell instance needs its target unit, animation age, current figure positions and
its active/ended state. The Curse additionally needs each spirit's loop phase and the target unit's
current facing. Presentation never changes the spell's target or duration.

Use each figure's current world X/Y, including its displacement within the formation. Recompute the
terrain height under that point every tick, then add the height in §1. The effect follows movement,
turning and changes of formation; it is not left at the cast point. It does not use the figure's animated
vertical displacement or the unit's flight height to raise the sprite. Azure's 16-unit lift is fixed.
There is no random positional jitter in these four effects.

The number of sprites follows the target's current figure count. After casualties, remove the excess
sprites on the next effect update; do not leave a spirit over a corpse or play a death/fade animation.
Animation progress is maintained in the target's current figure order: after that order changes, a
survivor can inherit another spirit's loop phase. Independent curses keep independent animation state.

Off-screen animation continues to advance. Moving the camera back does not replay the appearance
sequence or reset the loops. A pause does not advance the battle tick or these animations.

### 2.2 Anchors and colours

Read each selected frame's own `.FOL` anchor. For battle sprites, byte 3 supplies the horizontal anchor
and byte 2 its distance above the bottom edge: anchor `(byte3, frame height − byte2)`.
The selected frames in this report all have byte 2 equal to zero, so they use the bottom edge:

| Frames | Asset dimensions | Anchor in asset pixels |
|---|---|---|
| Curse appearance, 229–260 | 64 × 64 | (32, 64) |
| Curse loop, 261–292 | 32 × 64 | (16, 64) |
| Azure, Ere We Go, Mork Save Uz | 32 × 32 | (16, 32) |

The sprite rectangle is anchored there; its opaque pixels need not touch the anchor. Preserve the
asset's transparent padding. In particular, the Curse's change in frame width does not move its
world anchor or double its scale.

The effective colour map is the frame's `.FOL` colour-map nibble plus the spell's bank in §1.
See `btp_sprite_leftovers.md` §3 and `FORMATS.md` for map decoding. A decoder that already resolves
the full map number must not add the bank a second time. The inspected artwork is white/grey skeletal
spirits for the Curse, blue sparkles for Azure, red for Ere We Go and green for Mork Save Uz.

### 2.3 Removal and failed casts

When a spell ends, remove all its sprites in that same effect update. There is no fade, closing strip,
explosion or surviving visual tail. This covers dispelling, cancellation, target removal and other
end conditions in the gameplay reports. If cancellation happens before this tick's effect update,
the spell contributes no sprite that tick.

A failed launch contributes no new art. In particular, an unsuccessful Curse cast aimed at empty
ground leaves the caster's previous Curse and its current animation intact. A successful replacement
removes the old Curse and starts a fresh appearance sequence on the new target.

## 3. Curse of Anraheir

### 3.1 Appearance and loop

All target figures begin with appearance phase 0 together. The four phases are:

| Tick | Phase | Eight direction frames |
|---|---|---|
| T | Appearance 0 | 229–236 |
| T+1 | Appearance 1 | 237–244 |
| T+2 | Appearance 2 | 245–252 |
| T+3 | Appearance 3 | 253–260 |
| T+4 onward | Loop phase 0, 1, 2 or 3 | 261–268, 269–276, 277–284, 285–292 respectively |

At T+4, replace the appearance with the loop in the same tick, with no blank frame. Each remaining
figure consumes one random draw, in figure order. If `r` is that draw modulo 4, its first loop phase
is `3 − r`: remainders 0, 1, 2, 3 produce phases 3, 2, 1, 0. Each subsequent tick advances one phase,
wrapping 3 to 0. There is no further random draw on ordinary loop wraps.

Thus the figures begin together, then become partly staggered. The loop repeats every four ticks
(0.4 seconds). It continues until the Curse ends; finishing the appearance or a loop does not end
the gameplay effect. For an unmounted target there is no natural timeout.

### 3.2 Direction

Both stages use eight directions. The selected frame is `stage first + 8 × phase + direction`, where
direction is the usual camera-relative octant used for battle figures. Read the **unit's current
facing**, not each figure's individual facing and not the bearing from the caster to the target.
Turning the unit or rotating the camera can change the direction without restarting the phase.

For an existing renderer, reuse its battle-figure direction selection (`battle_viewer.md`,
"Playtesting: troop sprite facing"). Nearest-octant boundaries are halfway between the 45° views.

**Frames 293–356 are not selected by this Curse sequence.** They are another similar-looking
64-frame block in the asset, but their adjacency does not make them a third stage, disappearance
animation or alternate zoom level for this spell. Their other possible use remains 🟡.

### 3.3 Ending during an update

The mounted target's panic check occurs after its spirits advance. A failed check ends the Curse and
removes those spirits in the same update; the completed tick has no remaining Curse sprites. A Curse
that ends before T+4 need not consume any loop-start random draws. A failure at T+4 happens after the
loop-start draws have already occurred.

## 4. Azure Blades, Ere We Go! and Mork Save Uz!

These three begin directly in a four-frame loop. Every figure of one cast has the same phase:
phase 0 at T, phase 1 at T+1, phase 2 at T+2, phase 3 at T+3, phase 0 again at T+4.
They do not randomise their starting phase and have no directional frame variants.

The full visible lifetime, absent earlier cancellation, is T through T+179 inclusive. T+179 shows
the fourth frame; T+180 removes the sprites. Turning the target changes positions within its
formation, but does not select a different sparkle view or reset the loop.

Use Azure's actual resolved target. A player's no-target Azure order normally resolves onto the
caster, while the AI can aim it at its melee target (`spell_blades_flock_items.md` §2). The graphics
follow that resolved unit. Ere We Go and Mork Save Uz also follow the resolved unit, regardless of side.

**Ere We Go uses only 470–473.** Frames 474–485 are not later stages or variants of its loop.
Frames 474–479 form the brown dust used by Da Krunch; preserve this fact for #272.
The similar green strip 480–485 still has an unresolved use 🟡.

## 5. Dispel Magic and Fists of Gork

Neither creates a separate spell sprite or effect mesh at launch, while active, on success, or at
expiry. Their zero first-frame value must not be interpreted as a request to play `SPELLS` frame 0.

Dispel Magic removes the cancelled effect's visuals immediately and can display the established
dispel message. It has no visible expanding aura or flash of its own, including when it finds no
eligible spell. See `spell_lasting_effects.md` §5 for its once-per-battle selection lock and duration.

Fists of Gork performs its periodic wound checks without drawing a fist or hit particle. Its
no-victim case is also silent visually. At normal expiry the caster returns to its standing action
as already described in `spell_lasting_effects.md` §4; that action belongs to the figure animation.

## 6. Before/action/after vectors

The frame expectations below are the result after the tick's effect update, before rendering.
Use an unmounted Curse target unless the row explicitly says otherwise.

| Before state | Action | After state / expected art |
|---|---|---|
| One uncursed target figure; camera-relative direction 2 | Successful Curse at T | One spirit, frame 231, at the figure's ground point |
| Same figure and direction | Updates T+1, T+2, T+3 | Frames 239, 247, 255 |
| Same; loop-start random remainder 0 | Update T+4 | Frame 287: loop phase 3, direction 2; no blank tick |
| Same | Update T+5 | Frame 263: loop phase 0, direction 2 |
| Four figures; direction 0; random remainders 0, 1, 2, 3 | Update T+4 | Frames 285, 277, 269, 261 respectively; four random draws |
| Same figures, no changes | Update T+8 | Same four frames; no new random draws |
| Spirit in loop phase 2, direction 1 (frame 278) | Turn so direction becomes 3 on the next tick | Next phase 3, frame 288; appearance does not restart |
| Cursed unit moves a figure from (100,100) to (112,100), terrain height changes from 8 to 12 | Next update | Spirit follows to (112,100), height 12; no trail at its old position |
| Twelve cursed figures | Two figures removed before effect update | Ten spirits at current surviving figure positions; no corpse spirits |
| Mounted cursed target, segment 10, looping spirits | Panic check fails | Curse ends; zero spirits after this update |
| Caster has an active Curse | New cast has no unit under its aim point | No new sprite; old Curse continues its existing phase |
| Same | Successful new Curse on another unit | Old sprites removed; new target starts appearance phase 0 |
| Three target figures, terrain height 12 | Azure at T | Three frame-387 sprites, all at height 28 |
| Same, Azure still active | Update T+4 | Three frame-387 sprites again; no phase randomisation |
| Ere We Go active since T | Update T+179, then T+180 | Frame 473 on each figure, then none; frames 474–485 never enter this loop |
| Mork Save Uz active since T | Updates T, T+1, T+2, T+3, T+4 | 486, 487, 488, 489, 486 on every target figure |
| Any of the four visible spells active | Dispel before its effect update | All its sprites gone that tick; no exit strip or dispeller flash |
| Curse goes off-screen during appearance | Return after T+8 | Current loop phase; no replay of appearance |
| Dispel Magic finds no eligible effect | Cast and advance to expiry | No separate spell art at any stage |
| Fists of Gork has an eligible victim / has no victim | Periodic strike tick | No fist or impact particle in either case; gameplay resolves separately |

## 7. Changes to the implementation model and open checks

- The current frontend models projectile spell visuals. Add attached figure effects with their own lifecycle;
  a projectile position or a single marker at the target centre does not describe these spells.
- Curse requires two directional stages, a single random phase selection per spirit at T+4, and immediate
  cleanup. The previous "about 4 ticks" statement in `spell_channelled_effects.md` §4.1 is now exact.
- Narrow the catalogue ranges for Curse and Ere We Go to the frames in §1. Consecutive asset blocks can
  contain art for other spells or variants that this spell never selects.
- Dispel Magic and Fists of Gork require no new battlefield effect art. Preserve their ordinary figure
  animations and gameplay feedback.
- The shared sprite anchor rule confirms the bottom-edge interpretation previously marked provisional
  for Fireball in `bf003_playtest_fireball_grid_pursuit.md` §8.3.

🟡 No original-game screen recording was made for this batch. A visual comparison should check the
Curse's apparent orientation and overlap with figures as the camera rotates, and rendering on sloped
terrain. The frame schedule, selected ranges, colour maps and anchors above are specified independently
of that screen comparison.

🟡 A target gaining figures while already affected is outside the normal casualty path and is not
specified here. Do not infer a fresh appearance sequence for such figures from the removal rule.

🟡 The uses of frames 293–356 and 480–485 remain open; neither block belongs in the respective spell's
confirmed animation. Da Krunch's complete dust placement and timing remain with #272.
