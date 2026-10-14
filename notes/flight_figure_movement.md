# How a fleeing unit's figures move (GitHub #345)

Public implementation report. It describes what the original game does when a unit runs away, at the level of
individual figures. It answers the BF028 symptom: the sheep ran off as a tidy 3-rank block, while in the original a
fleeing unit dissolves into a shuffling mob that trails behind the unit's position.

Companion reports. These already cover the rest of a flight, and this report does not repeat them:

- `game_rules.md` "Models chase the unit, they are not carried by it": the catch-up walk, the step factor `F`,
  the stagger value, the arrival rule, and the cap removed while broken.
- `game_rules.md` "Formation is what decides all of this" (the rout pause) and "Flight and catching fleeing units":
  flee bearing, flee period re-routing, leaving the table.
- `game_rules.md` "Scripted target and flight opcodes" (`FleeAhead`), `runaway_routers_broken.md` (the broken
  state, `Rally`, every way out of a rout), and `flight_solid_obstacles.md`.

**Correction to `game_rules.md`.** The rout paragraph said each model at rest "is scattered slightly from its
position". That is wrong in two ways. The scatter moves the model's **destination (its slot)**, not the model itself,
and it applies to **every** model, not only those at rest. The scatter is not slight: it is the start of the
re-aiming described in §2. The sentence has been corrected to point here.

## 1. Shared state: a fleeing figure has no formation slot

There is no flight layout: no column, no loose order, and the ranks and frontage are not changed. Instead, the
rout takes the existing slots and **keeps re-rolling them**.

- Every model still has a **destination point stored relative to the unit's anchor**, the same point the catch-up
  walk steers to. Normally this is the formation slot. While the unit flees, the destination is **rewritten at
  random by the flight itself**, again and again. Formation layout code never runs during the flight, so nothing
  restores the slots.
- Each model has a **re-aim timer**. It is the same per-model countdown that holds the rout pause (and the charge
  start freeze). It is decremented once per tick by the catch-up walk. When it reaches 0, the flight re-rolls that
  model's destination and restarts the timer.
- The catch-up walk itself is unchanged: the same heading recomputation, distance budget, 3-unit arrival rule and
  step factor `F` (built from the model's rank index, which it keeps). The `s_rlmv` cap is removed (already
  public). The only other thing the flight touches is the walk's **current speed counter**, which is reset to 0 at
  every re-aim, so each figure stops and accelerates again (+1 per tick) every time it re-aims.
- Figures that have arrived (within 3 units, at rest) are **still moved** while the unit flees. The walk's "skip
  models that are at rest" rule only applies while the unit is halted, re-forming, in melee, held or anchored,
  and a fleeing unit is none of these. So an arrived figure starts walking again as soon as its destination moves
  away, and the anchor moves every tick.

So **the formation lasts only until each figure's first re-aim**. After two or three re-aims (a few seconds) nothing
of the original block is left.

### Your model vs. the original

| Your engine | Original |
|---|---|
| destination = formation slot (ranks/frontage unchanged), relative to anchor and facing | destination = a **random point re-rolled per figure**, drifting to a cloud centred about `2n` units behind the anchor (§2) |
| "slight scatter" ±1 per axis from stagger bits | the **slot** is halved toward the anchor and jittered by up to `±3·⌊n/2⌋` per axis from the battle RNG; applied to **every** model at the rout |
| scatter only at the rout | re-aimed again **every 24–66 ticks per figure** for the whole flight |
| catch-up speed keeps ramping | speed counter **reset to 0 at each re-aim** (stop-start shuffle) |
| at-rest figures (arrived) stay put | at-rest figures keep being moved while fleeing |
| anchor k = 1.5, uncapped catch-up, F step, 3-unit arrival, stale heading | ✅ same |
| leader slot not reserved, ranks/frontage unchanged until rally | ✅ same (irrelevant in practice, the slots are re-rolled) |

## 2. The re-aim (scatter) rule

`n` = the unit's **current** number of models (not its original size). It is applied per axis, x first, then y,
with one draw from the shared battle RNG per axis (MSVC `rand`, `game_rules.md` §4). Destinations are integers in
world units, relative to the anchor:

```
d  = d − trunc(d / 2) + 3 × (trunc(n / 2) − rand() % n)      # each axis; trunc = toward zero
```

So the old destination is **halved toward the anchor**, rounding its magnitude up (7 → 4, −7 → −4, −1 → −1). A
uniform jitter is then added, taking values from `3·(⌊n/2⌋ − n + 1)` to `3·⌊n/2⌋` in steps of 3: −21…+21 for
`n` = 15, and −18…+15 for `n` = 12. The same re-aim also requests the figure's **walk** animation action (action 3).

There are two kinds of re-aim:

1. **At the rout itself** (the rout start, for every model, in model order). The scatter is applied **once**, with
   no shift and no timer change. Models at rest also get the already public rout pause `(stagger & 7) × 3 + 6`, and
   their melee opponents get it too.
2. **During the flight**, every tick, for every model whose re-aim timer is 0:
   - the scatter above, then
   - a **shift of `n` world units straight back along the flight direction**: per axis,
     `trunc(−dir_axis × n / 256)`, where `dir_axis` is the per-axis direction value (scaled by 256) that the
     anchor itself steps along. In other words, the opposite of the anchor's own step direction. Each axis is
     truncated toward zero;
   - the re-aim timer is set to `((stagger & 7) × 3 + 12) × 2` = **24, 30, 36 … 66 ticks**;
   - the catch-up speed counter is set to 0.

The flight direction used is the unit's **current** facing, so after a flee-period re-route the shift follows the
new line. The rout also turns the facing to the flee bearing **instantly**, and the old slots are not rotated with
it. For `FleeFromTarget` (bearing + 180°), the old rear ranks' slots therefore start out *ahead* of the anchor in the
direction of flight. The halving and shifting bring them behind within a couple of re-aims.

### Where the cloud ends up

Ignoring the rounding, the expected destination per re-aim is `m' = m/2 + jitter_mean + shift`, so it settles at
`m = 2 × (jitter_mean + shift)`:

- **along the flight line: about `2n` units behind the anchor** (the anchor is the front-rank centre);
- across it: about 0 for odd `n`. For even `n` the jitter mean is +1.5 per axis, a small bias towards +x/+y;
- per-axis spread: the stationary standard deviation is `√(4/3) × 3·√((n²−1)/12)`, which is **≈ 15 units for
  `n` = 15**, ≈ 12 for 12 and ≈ 4 for 4.

A simulation of destinations alone (heading 0, 12 re-aims from random starts) gives these values:

| `n` | across: mean / sd / range | along (negative = behind): mean / sd / range |
|---|---|---|
| 15 | 0 / 15.4 / −38…38 | −30 / 14.8 / −68…6 |
| 12 | 2.7 / 12.1 / −28…34 | −21 / 12.1 / −51…7 |
| 4 | 3.4 / 4.0 / −6…12 | −5 / 4.0 / −14…4 |

The hard bounds follow from the fixed point of the extremes: across `2·J_min…2·J_max`, along `2·(J_min − n)…2·(J_max − n)`.
For `n` = 15 that is −42…42 across and −72…12 along (±1 for the rounding). A unit that loses models shrinks its cloud as it goes.

**What it looks like.** A 15-sheep flock that was 5 wide and 3 deep becomes a mob roughly 60 × 60 units, centred
about 30 units behind the anchor. Every figure stops and restarts every 2.4–6.6 s, at a moment set by its own
stagger, so the mob mills and shuffles as it runs. It does **not** string out: the walk is uncapped and its speed
counter grows by 1 per tick while the destination is far away, so even rear-rank figures (lowest `F`) catch up
between re-aims. Front-rank figures (highest `F`) simply get there sooner. A figure that is about to re-aim may be
anywhere between its old and its new destination.

## 3. Order within a tick (fleeing unit, not in melee, not halted)

1. Script, then the formation update: the **catch-up walk**. Each model's re-aim/pause timer goes down by 1. A model
   whose rout pause runs out this tick loses its pause lock and **moves this same tick**.
2. The flight handler: flee-period re-route when due (public), **anchor step**, rally attempt when scheduled
   (public), then the **re-aim** of every model whose timer is now 0 (§2).
3. Footprint update.

A rout started by a script opcode runs in step 1's script phase, so models that were moving at the rout (no pause,
timer 0) are scattered twice on the rout tick: once by the rout start and once by the flight's first re-aim.

## 4. Leaving the table

Already public: when the anchor is outside the battle area, the unit sends event 0x0E. What follows has not been
written down before:

- Once the unit's **rear point** (the anchor moved back along the facing by the footprint size) is outside the area
  too, the unit becomes **halted** and enters the **re-form by walking** mode, and **every destination is set to the
  anchor itself** (0, 0). The anchor stops moving and the flight re-aims stop, so the figures walk in to a single
  point just beyond the edge, at the uncapped broken speed.
- The re-form ends when no figure is still walking and no re-aim timer is still counting. Every figure has then
  arrived within 3 units, and timers left over from the flight have run out (at most 66 ticks). The unit is then
  removed alive (every model counts in `s_routed`).

🟡 Whether timers left over from the flight really keep the unit on the table for up to 66 more ticks depends on the
timer also counting as "busy" for the end-of-re-form test. It does in the original's walk, but this was not observed
on screen.

## 5. Rally

There is nothing flight-specific: `Rally` (`runaway_routers_broken.md` §3) clears broken and fleeing, sets halted
and the **re-form by walking** mode, and lays the re-form out at once. This rewrites every destination to a fresh
block layout (script rank count, leader slot reserved again), so the scattered destinations are thrown away. The
figures then walk to their new slots with the **ordinary catch-up walk**. The `s_rlmv` cap is back because broken
is cleared, the at-rest skip applies again because the unit is re-forming, and the end of the walk is the usual
re-form completion (event 0x34). Re-aim timers left over from the flight just count down. They no longer re-aim,
because the flight handler is not running.

## 6. Special cases (question 5)

- **No unit-type, side, morale or script tests** in the rout start's scatter, the flight re-aim or the catch-up walk.
  Sheep, peasants without an attack group, neutral or marked units, `CantRally` units, and units sent off by
  `FleeAhead` instead of a failed break test all scatter and mill the same way. `FleeAhead` *is* the rout
  (`game_rules.md`), so the BF028 sheep flight is an ordinary rout. In the original it would **not** show a formation
  after the first few seconds.
- BF028's Sheep have no `s_race` line ("notype", race Peasant), so they use the block layout. They are not one of
  the classes whose figures are carried rigidly with the unit (artillery, rolling stock, buildings).
- Classes that are carried rigidly (`game_rules.md`, "Exceptions") still get their destinations re-rolled, but
  carrying cancels part of the chase. Anchored war machines cannot rout at all (public).
- `CantRally` only stops the rally attempt (public). It has no effect on figure movement.

## 7. Test vectors

Destinations are relative to the anchor, in world units; `r` is the raw `rand()` result. They use the axis
convention of the anchor step, in which heading 0 moves the anchor along +y.

**Scatter (one axis)**

| Before: `d`, `n` | `r` | After: `d` |
|---|---|---|
| −12, 15 | 3 | −12 + 6 + 3·(7 − 3) = **6** |
| 7, 15 | 14 | 7 − 3 + 3·(7 − 14) = **−17** |
| −7, 15 | 0 | −7 + 3 + 21 = **17** |
| −1, 15 | 7 | −1 − 0 + 0 = **−1** (truncation: the half of −1 is 0) |
| 0, 12 | 11 | 0 + 3·(6 − 11) = **−15** |
| 0, 12 | 0 | **18** (the even-`n` asymmetry: −15…+18) |
| 0, 1 | any | **0** (a single model: the jitter is always 0) |

**Shift (flight re-aim only), `n` = 15 unless stated; heading in 1/512 turns**

| Flight heading | Shift (x, y) |
|---|---|
| 0 | (0, **−15**) |
| 64 (45°) | (**−10**, **−10**): `181 × 15 / 256` = 10.6, truncated to 10, not rounded to 11 |
| 128 (90°) | (−15, 0) |
| 37, `n` = 12 | (−5, −10) |

**Timeline of one figure** (`stagger & 7` = 5, at rest when the unit routs on tick T)

| Tick | Before | Event | After |
|---|---|---|---|
| T (script) | at rest, slot S | rout start | destination = scatter(S); pause 21, locked |
| T (walk) | pause 21 | walk | pause 20, does not move |
| T+20 (walk) | pause 1 | walk | pause 0, unlocked, **moves this tick** |
| T+20 (flight) | timer 0 | re-aim | destination = scatter(d) + shift; timer **54**; speed counter 0 |
| T+74 (flight) | timer 0 | re-aim | next destination; timer 54 again (period 54 ticks for this stagger) |

The same figure moving (not at rest) at the rout: the rout-start scatter on T, then the first flight re-aim also on
T (scatter + shift, timer 54), the next on T+54.

**Invariants an engine can assert** (fleeing unit, `n` models, no re-route, after ≥ 4 re-aims per figure)

| Check | Expected |
|---|---|
| per-figure re-aim interval | exactly `((stagger & 7) × 3 + 12) × 2` ticks, in {24, 30, …, 66} |
| every destination, across the flight line | between `2·J_min` and `2·J_max` of the anchor (−42…+42 for `n` = 15) |
| every destination, along the line | between `2·(J_min − n)` and `2·(J_max − n)` of the anchor (−72…+12 for `n` = 15), where `J_min`/`J_max` are the jitter extremes |
| bounds slack | ±1 for the magnitude-up halving |
| mean destination over the unit | ≈ `2n` behind the anchor for odd `n`, `2n − 3` for even `n` (the +1.5 jitter mean) |
| formation | none: figures' order no longer follows ranks; two figures may share a destination |
| speed counter right after a re-aim | 0 |
| unit at the table edge | all destinations (0, 0); anchor stops; removal only after every figure is within 3 units |

## Open items

- 🟡 §4: the leftover re-aim timers delaying removal (above).
- 🟡 Visual confirmation in a Wine session that a routed regiment mills as a mob, since the trace is unambiguous
  but nobody has looked at it on screen.
