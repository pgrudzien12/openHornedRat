# The Plague Monks' breath on screen, and the exact Pestilent Breath stage timing

Public implementation report (behaviour only). It covers what the **innate breath of the Plague Monks** (periodic
behaviour 27, `script_behaviours.md` §1.10) draws, and how that compares with the cast spell **Pestilent Breath**
(`spell_visuals.md` §2.6). Gameplay (flight, scatter, hits) is in `spell_effects.md` §2–3 and §3.7. Companions:
`gyrocopter_steam_gun.md` §6 (the steam gun, which uses the same drawing with other frames), `FORMATS.md` (`.FOL`
anchors, colour maps), `battle_end_objectives.md` (objective letter Q, standing trees), `sprite_names.md`
(furniture table).

**Short answer.** The Plague Monks' breath **is the Pestilent Breath effect (spell code 24)**. It shows `SPELLS`
**533–536** at colour bank **+32**, never 591–598. Its head, trail, stage formula, timing and removal are **the
same** as the cast spell's. There are only three differences: the start point, cancellation, and one end step that
only the innate breath has. On the tick after the cloud finishes, the innate breath **fells every standing pine
tree within 64** of the cloud's last position. The "screen shake when it finishes" in `spell_effects.md` §3.7 is
wrong: no shake is started. Frames 591–594 belong to the **Gyrocopter steam gun** (effect code 27). Frames 595–598
are **Flamestorm's** default column (`spell_obstacle_visuals.md`). `SPELLS` has no frames 599 or 600; the set ends
at 598.

## 1. Result tables

| | Plague Monks (behaviour 27, innate) | cast Pestilent Breath (spell 24) |
|---|---|---|
| effect launched | Pestilent Breath (24), innate: no caster figure, no power cost | Pestilent Breath (24) |
| artwork | head and trail: `SPELLS` 533–536 | same |
| start point | the **unit position** (regiment position) | the origin model (normally the leader; unit position when cast without the pose), `spell_effects.md` §2.1 |
| launch / aim height | 8 / 8 (aim: half height + elevation of a flying unit at the aim point, if that is more) | same |
| flight | 18 ticks, 19 positions, `spell_effects.md` §2.3 | same |
| head frame | `533 + s`, stage s from flight progress (§3) | same |
| trail | static, frozen puffs, one per tick the head has moved (§3.2) | same |
| end | head gone the tick after the finish; puffs removed one per tick, oldest first (§4) | same |
| extra end step | **fells pine trees within 64** of the cloud's last position, once (§4.2) | none |
| cancellation | **never**: not by dispel, not by Ctrl+click, not when the Plague Monks die or flee | cancelled like any cast spell: head and all puffs vanish at once (§4.1) |
| Shift variant | none | none |
| sound | silent (`spell_sounds.md`) | silent |

| frames | size | anchor (x, y) | FOL map nibble | added bank | effective colour map | used by |
|---|---|---|---|---|---|---|
| 533–536 | 32 × 32 | 16, 32 (bottom centre) | 1 | +32 | **33** | Pestilent Breath, both kinds |
| 591–594 | 32 × 32 | 16, 32 | 9 | +32 | 41 | steam gun only (`gyrocopter_steam_gun.md` §6.1) |
| 595–598 | 128 × 128 | 64, 128 | 10 | 0 | 10 | Flamestorm only (`spell_obstacle_visuals.md`) |

The art for 533–536 is a cloud of small skulls. It grows from a single skull (533) to a large cluster (536). The
frames are not directional and do not cycle on their own. Each one is selected by the stage (§3).

## 2. Placement

- **Start (innate):** the Plague Monks' **unit position** at launch, not any figure. The aim is the point
  `(x + off, y + off)` of `script_behaviours.md` §1.10, scattered as in `spell_effects.md` §2.2 (range 144).
  The start ground and the destination ground are sampled at launch.
- **Head:** drawn every flight tick at the projectile's position `dest + trunc((start − dest) × r / 18)` (per axis,
  r = remaining positions, 18 → 0) and at absolute height `8 + line(r)`. Here
  `line(r) = Ad + trunc((Ls − Ad) × r / 18)`, `Ls = ground(start) + 8`, `Ad = ground(destination) + A`, and A is
  the aim height (8, or more for a flying unit at the aim). On flat ground the head is 16 above the ground for its
  whole flight. No jitter, no arc.
- **Trail puff:** left at the head's **previous** position, at absolute height `8 + line(r′)`. Here r′ is the
  remaining-position count after the current tick's step (§3.2 lists it per puff). On flat ground, or when the
  start and destination grounds are equal, this is the head's own height there. On a slope it can be off by a
  couple of units. Puffs do not follow anything; they are fixed where they were left.
- One head and at most 19 puffs per breath. Several breaths can be in the air at once. Each is independent.

## 3. Animation and stages

### 3.1 Head (both kinds, N = 18)

Stage s on the tick when the head is drawn with r positions left: **s = 0 while `4(18 − r) ≤ 18`, 1 while
`≤ 36`, 2 while `≤ 54`, else 3** (strict "greater than" moves it up).

**There is no one-tick lag.** The game updates the stage at the end of each tick, but it uses the remaining count
of the *next* position. So the frame drawn at a position always matches the table for that position's r. The
🟡 in `spell_visuals.md` §2.6 is settled: the table there is exact.

Exact tick → frame vector (launch tick T, whose update draws the head at the start):

| tick | T…T+4 | T+5…T+9 | T+10…T+13 | T+14…T+18 | T+19 |
|---|---|---|---|---|---|
| r at the drawn position | 18…14 | 13…9 | 8…5 | 4…0 | — |
| `4(18 − r)` | 0…16 | 20…36 | 40…52 | 56…72 | — |
| head frame | **533** ×5 | **534** ×5 | **535** ×4 | **536** ×5 | none (head gone) |

As one list, T…T+18: `533 533 533 533 533 534 534 534 534 534 535 535 535 535 536 536 536 536 536`.

### 3.2 Trail (both kinds)

On each tick, the puff left at the previous position gets **the frame the head shows on that same tick**. That is
one tick later than when the head was at that spot. So a puff can be one stage ahead of the head frame that was drawn
there. Puffs never animate. A puff is **skipped** when the previous position is the same point as the newest puff
(distance below 1 unit). This always happens on T+1, because the head has not moved yet. It also happens whenever
two consecutive integer positions coincide, which is common for very short flights.

Uninterrupted flight with distinct positions, 19 puffs:

| puff | left on tick | at position (r) | frame | r′ for its height |
|---|---|---|---|---|
| 1 | T | 18 (start) | 533 | 17 |
| — | T+1 | (none: same point) | — | — |
| 2–4 | T+2…T+4 | 17…15 | 533 | 15…13 |
| 5–9 | T+5…T+9 | 14…10 | 534 | 12…8 |
| 10–13 | T+10…T+13 | 9…6 | 535 | 7…4 |
| 14–18 | T+14…T+18 | 5…1 | 536 | 3…0 (T+18: 0) |
| 19 | T+19 | 0 (destination) | 536 | 0 |

The path is lined, from the start, by four 533 puffs, five 534, four 535 and six 536. That is the "growing cloud".

## 4. Removal

### 4.1 Every end

Let F be the tick the cloud **finishes**. Normally that is T+18, the terminal impact at r = 0. If the cloud goes
below the terrain earlier (`spell_effects.md` §2.3), F is that tick, and there is no terminal impact.

| end | innate (Plague Monks) | cast spell |
|---|---|---|
| normal finish | F: head drawn at r = 0 (a cloud that went below ground is **not** drawn on F). F+1: head gone; last puff left at that position; **pines felled** (§4.2); puff 1 removed. Then one more puff removed per tick, oldest first. With n puffs, the last one is visible on F+n−1 and gone on F+n; the effect ends on F+n+1 | same, without the tree step |
| dispel, Ctrl+click cancel | **not possible**: innate effects are never cancelled (`spell_effects.md` §1.4) | head and **all** puffs vanish on the cancelling update, no tail |
| a second breath / recast | independent: an earlier breath is not removed | independent: recasting Pestilent Breath does not cancel the earlier one |
| caster dies / is removed mid-flight | **no change**: the breath flies on and ends normally, puffs and trees included. A rout or flight of the Plague Monks changes nothing either | a wizard caster's removal cancels it: everything vanishes at once |
| launch refused | no breath, no art (the original's limit on simultaneous effects; an engine need not copy it) | as for the spell |

A puff removed in an update is **not drawn** in that update, following the shared rule "removed in the same
update, no tail". Normal timeline with 19 puffs (F = T+18):

| tick | visible |
|---|---|
| T | head 533 at the start + puff 1 (same point) |
| T+1 | head 533; puff 1 |
| T+k, 2 ≤ k ≤ 18 | head (§3.1) + puffs 1…k |
| T+19 | no head; puffs 2…19 (18 puffs); **innate: pines felled now** |
| T+19+m, 0 ≤ m ≤ 17 | puffs m+2…19 (18 − m puffs) |
| T+36 | puff 19 only (the destination puff) |
| T+37 | nothing |
| T+38 | effect over (gameplay end) |

### 4.2 The innate breath fells pine trees

Once, on F+1, before the first puff is removed: every **standing pine tree** whose scenery piece is within
**64** of the cloud's **last position** (the destination, or the point where it went below ground) is felled.
"Within" means `trunc(√(dx² + dy²)) ≤ 64` between the tree's placed position and that point. That is integer
distance truncated, inclusive.

- Pine trees are the 18 furniture types `TriPineLrg`, `TriPineMed`, `TriPineSml`, `PineSml`, `PineLrg`, `Pine` and
  their `Nite…` and `Snw…` variants. In the furniture table (`sprite_names.md`) these are records 87–104.
- Felling swaps the piece to its **dead variant, record + 59** (`D_TriPineLrg` … `D_SnwPine`, records 146–163;
  meshes `TPINEL_D` etc. in the battle's `SCENERY.PBX`). This is the same "+ 59" rule as the building ruins
  (`building_ruins.md` §1). If the battle lacks that mesh, the tree stays standing. A tree that is already felled
  is not felled again.
- No sound, no message and no camera shake come with it. The cast Pestilent Breath does **not** do this.
- This is the answer to the 🟡 "what knocks a tree down" of objective **Q** (`battle_end_objectives.md`, BF024, the
  Plague Monks' mission). Other tree-fellers use the same rule with their own radius: area blasts that hit
  something, the Conflagration of Doom fall and the Da Krunch foot. Their radii are not covered here.

## 5. Ownership of neighbouring frames

- 533–536: Pestilent Breath, cast and innate. No other user found.
- 537–540: Madness (`spell_madness_visuals.md`); 541–561 belong to other effects listed there. Not part of the breath.
- 562–590: the warpfire flames (`spell_doomwheel_visuals.md` §5). Not part of the breath.
- 591–594: **steam gun only** (effect 27, first frame 591, bank +32). No Plague Monk launch selects them. The issue's
  "591–598" is wrong.
- 595–598: Flamestorm's default column, bank 0, map 10 (`spell_obstacle_visuals.md`).
- 599–600: **do not exist**. `SPELLS.FOL` has 599 frames (0–598), the same in `FILE` and `UPDATE`.

## 6. Test vectors

| before | action | after |
|---|---|---|
| Plague Monks P at (1000, 1000), flat ground 0; behaviour 27 draws off = 200, scatter 0 | breath launched on T | effect 24; head 533 at (1000, 1000), height 16 above ground; puff 1 there, 533; no sound |
| same | T+4 / T+5 | head at r = 14: 533 / r = 13: 534 (no lag) |
| same | T+9 / T+10 / T+13 / T+14 | 534 / 535 / 535 / 536 |
| same | T+18 | head 536 at (1200, 1200); terminal impact; 18 puffs |
| same, a `Pine` at (1250, 1240) (d = 64) and a `PineLrg` at (1250, 1241) (d = 64.7, trunc 64) and a `Pine` at (1260, 1240) (d = 72.1) | T+19 | head gone; puff 19 at (1200, 1200) frame 536; the first two trees become `D_Pine` / `D_PineLrg`; the third stays; puff 1 not drawn |
| same | T+36 / T+37 / T+38 | only puff 19 / nothing / effect ended |
| same, P destroyed on T+6 | T+6…T+38 | nothing changes: flight, puffs, felling and removal as above |
| same, a Dispel Magic cast at the cloud on T+8 | dispel | the breath is not a candidate (innate): unchanged |
| a wizard casts Pestilent Breath with the same geometry and pines | T+19 | same art and timeline; **no** trees felled |
| same cast, wizard killed on T+6 | T+6 | head and all puffs vanish in that update; nothing later |
| P breathes with off = 0 (`h` = 0): aim = unit position, scatter step 0 | T…T+18 | head stays at the unit position and grows 533→536 on the §3.1 ticks; **one** puff (533) only; T+19 head gone, pines within 64 of the unit position felled, puff 1 removed (not drawn); T+20 effect over |
| grounds: start 0, destination 36, A = 8 | T+2 puff 2 at r = 17 | puff height `8 + line(15)` = 8 + 44 + trunc(−36 × 15 / 18) = 22 absolute; the head was drawn there at `8 + line(17)` = 18 |
| cloud goes below a ridge at r = 7 (tick T+11) | T+11 / T+12 | T+11: in-flight test at the r = 7 point, then the head is removed without being drawn (no terminal impact); puff at the r = 8 point (535); T+12 head gone, last puff at the r = 7 point, innate fells pines within 64 of that point, removal starts |

## 7. Differences from the current public text and engine model, and open items

- `spell_effects.md` §3.7: "plays a screen shake when it finishes (presentation)" is **wrong**. The innate breath
  fells pine trees within 64 of its last position on the tick after it finishes (§4.2), and nothing shakes. This
  agrees with `camera_shake.md` §5, which lists no breath. Replace the sentence.
- `spell_visuals.md` §2.6: the stage table is **exact**. Remove the 🟡 "may lag one tick". Add that the trail puff
  carries the head's frame **of the tick it is left**, which is the next tick after the head was there (§3.2), that
  T+1 leaves no puff, and point here for the timeline. The same lag 🟡 in `gyrocopter_steam_gun.md` §6.1 and its
  open items can also be removed: the steam gun shares this stage update.
- Issue #278 "SPELLS 591–598 (bank +32)": wrong. The breath uses 533–536 at bank +32 (map 33). 591–594 is the steam
  gun; 595–598 is Flamestorm.
- `battle_end_objectives.md` Q: the 🟡 "what knocks a tree down" is now answered in part (§4.2). **Lead, not
  verified:** both of Q's counts are taken at the end over the pieces whose *current* type is a pine. A felled tree
  has the dead type, so it may drop out of both the tree count and the standing count. Q's ratio might then not
  fall when trees are felled. This needs its own check before anything is written into Q.
- Engine model: if the engine draws the behaviour-27 breath with other frames, or shakes the camera at its end,
  that is wrong. The breath needs the same code path as the cast spell, plus the tree-felling end step, the
  unit-position start and immunity to cancellation.
- 🟡 Not seen on screen: no capture of the original was made. Check in BF024 under Wine for the puff colour (map 33)
  and for trees turning into their dead meshes near the end of a breath.
- 🟡 Whether a felled tree also loses its collision circle or sight blocking was not traced (only the piece and the
  tree counts were).
