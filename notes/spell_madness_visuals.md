# Madness spell visuals

Public behavioural report for Madness
[#276](https://github.com/pgrudzien12/openHornedRat/issues/276), under
[epic #259](https://github.com/pgrudzien12/openHornedRat/issues/259).

Gameplay is specified in `spell_lasting_effects.md` §1 (the target changes side for 180 ticks).
This report adds the artwork, its position, animation and removal, in the style of
`spell_attached_visuals.md` and `spell_transport_visuals.md`. T means the successful launch tick,
including its effect update. One battle tick is 0.1 seconds. Frame numbers are zero-based indexes
in the installed `SPELLS` assets; distances and heights are in battle units.

## 1. Result

| Spell | Artwork | Placement | Timing |
|---|---|---|---|
| Madness | Sprites **537–540** only (the dark horned head with red eyes and grey sparkles) | **One** sprite per maddened **unit**, at the unit's position, **48** above the local ground; follows the unit | Four-frame loop T…T+179; removed at T+180 or on any earlier end |

- **Nondirectional.** The same frame is shown from every camera angle and unit facing.
- **No other art:** no projectile or beam from the caster, no arrival flash, no mesh, no closing strip.
  The caster's ordinary casting pose is separate. The cast sound is in `spell_sounds.md`
  (effect 12 at the aim point).
- **One sprite per unit, not per figure.** It does not multiply with the target's figure count, and
  casualties do not change it.

### 1.1 Anchor and palette

| Frames | Dimensions | Anchor X/Y | Added bank | Effective colour map |
|---|---|---|---|---|
| 537–540 | 32 × 32 | 16, 32 (bottom centre) | 32 | 34 |

Anchor rule and colour-map decoding as in `spell_attached_visuals.md` §2.2: the frame's own map
nibble (2) plus the bank (32). A decoder that already resolves the full map number must not add the
bank again.

## 2. Position

- **Every effect update**, the sprite is placed at the target **unit's position** (the same point
  used for its orders and range checks, not a figure's position). Its height is the terrain height
  under that point **plus 48**, recomputed every tick. The bottom-centre anchor sits at that point.
- It **follows the unit** while it moves, charges, flees or is pushed, with no trail. It ignores the
  figures' animated vertical displacement and a flier's flight height (a maddened Wyvern's head stays
  48 above the ground under it 🟡: no shipped battle was checked for this case).
- No random jitter.

## 3. Animation and stages

| Tick | Frame |
|---|---|
| T (launch) | 537 |
| T+1 | 538 |
| T+2 | 539 |
| T+3 | 540 |
| T+4 | 537 (loop) |
| T+k, k < 180 | `537 + (k mod 4)` |
| T+179 | 540 |
| T+180 | **none**: the effect ends in this update (side restored, `spell_lasting_effects.md` §1.3) and the sprite is removed before drawing |

- One frame per tick, starting at frame 537 for every cast (no random start phase), no skipped frames.
- Off-screen culling does not stop the loop; a pause stops it with the battle clock.

## 4. Removal

Every end removes the sprite **in that same update**, with no fade, closing animation or tail:

| End | Sprite |
|---|---|
| timer reaches 0 (T+180) | removed |
| dispelled | removed at once, wherever the unit is now (the dispel's *range* is measured from the aim point, `spell_lasting_effects.md` §1.3) |
| Ctrl+click cancel by the caster | removed at once |
| caster removed (Wizard-class casters, part A) | removed at once |
| target removed (all figures dead or the unit leaves the battle) | removed at once |
| target breaks, routs or flees but stays on the field | **not** removed: the head follows the fleeing unit until one of the ends above |
| a second Madness on the same target | the cast fails (already maddened), so **no** second head; the first keeps its phase |
| a failed cast (no hostile unit under the point) | no sprite |

## 5. Frames 541–561 (not Madness)

Madness selects only 537–540. The following frames belong elsewhere:

| Frames | Look | Belongs to |
|---|---|---|
| 541–549 | orange burst and ring | Conflagration of Doom's alternative burst (`spell_area_particle_visuals.md`) |
| 550–553 | red sparkles | 🟡 not selected by any spell (no use found) |
| 554–557 | green sparkles | 🟡 not selected by any spell (no use found) |
| 558–561 | blue sparkles | Sapphire Arch's sparkles (`spell_transport_visuals.md` §1) |

The next spell's art starts at 562.

## 6. Test vectors

Expected state after the tick's effect update, before rendering.

| Before | Action | After |
|---|---|---|
| Hostile unit U at (200, 300), terrain height 10 | Madness succeeds at T | One frame-537 sprite at (200, 300), height 58 |
| Same | Updates T+1, T+2, T+3, T+4 | 538, 539, 540, 537; still one sprite |
| U moves to (230, 300), terrain height 14, during T+10 | Update T+10 | Frame 539 (10 mod 4 = 2) at (230, 300), height 62; nothing left at the old point |
| U has 12 figures, loses 5 | Next update | Still one sprite; no change in phase |
| Madness active | Update T+179 | Frame 540 |
| Madness active | Update T+180 | No sprite; U's side is restored in the same update |
| Madness active since T, frame 538 shown at T+5 | Dispelled before the T+6 update | No sprite from T+6 |
| U maddened | Another wizard casts Madness at U | Cast fails; one head, phase unchanged |
| U maddened | U routs and runs 100 units | Head follows U, loop continues |
| U maddened | U's last figure dies | Head removed in that update |

## 7. Open checks

🟡 No original-game screen capture was made for Madness. A comparison should confirm the head's apparent height
above a unit and on sloped ground. The frame schedule, frame range, anchor and colour map are specified independently of it.

Frames 550–557 (#279): no spell, item, innate attack or ground effect selects them. None of the spells'
first frames points into the range, and no effect names a frame there. They are unused art (probably
spare red/green versions of the 558–561 sparkles); keep them out of every playback.
