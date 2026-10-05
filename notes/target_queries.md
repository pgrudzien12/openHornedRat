# Unit-script target and range queries

Public implementation report (batch 3 of the interpreter requests, GitHub #3). Companion to
`unit_script_control.md` (condition word) and `game_rules.md` §8 (shooting). Behaviour only.

**Read in `game_rules.md` rather than re-deriving:**
- the weapon range table by missile code (§8.3, "Code | Weapon | Range ..."): bow 576, crossbow 720, and so on;
- which missile code a unit uses (§8.1): Archers use their own `S_BalWeap`, Artillery the leader's, and any other
  class the leader's if non-zero, else its own;
- `IsVisible` ("Routes, collisions and visibility"): scenery rays and `SightEdge`, no range limit, no height;
- the broken flag `0x2000` of `unit_flags`;
- coordinates and facing (`FORMATS.md` "Coordinates"): 512 units per turn, **0 = +Y, increasing clockwise**
  (128 = +X).

## 1. Shared geometry

All the queries below use the unit's **regiment position** (centre) and the target's regiment position. There is
no footprint or edge distance.

- **Distance** `d = trunc(√(Δx² + Δy²))` (Euclidean, centre to centre, truncated).
- **Bearing** from the unit to a point, in 1/512 turn, 0 = +Y, clockwise:
  `bearing = trunc(256 − 256 × atan2(Δx, −Δy) / π)` with `Δ = point − unit`. The result is in 0..511. For
  `Δ = (0, 0)` it gives 256 (straight behind a unit facing 0).
- **In arc**: the circular difference between the unit's `facing` and `bearing` (`min(|f − b|, 512 − |f − b|)`) is
  **strictly less than 64** (±45°, open interval).
- **In weapon range**: `d < range` (strict), where `range` comes from the unit's missile code via the §8.3 table.
  A unit with no missile code, or a code without a range, has range 0 and is **never** in range.
- **Target**: "the target" is always the unit's **current target** (`current_target`), never the event source.
  `InArcAndRange` and `TargetValid` alone also fall back to the **target point**, the ground or building point of a
  fire order, when there is no target unit. Its coordinates use −1 for "none", and both must be ≥ 0.
- **Message operand**: where an opcode has an operand, a non-zero value makes a failure post the player message
  (GMTXT 2002 "not in line of sight" for the arc, 2001 for the range). Zero is silent. It never changes the result.
  The player-order fire scripts pass 1, the AI scripts 0.
- **Every query writes the condition** (bit 2): true or false, including **false when there is no target**.

Truncation matters at the arc edge: a target at `Δ = (100, 99)` from a unit facing 0 has bearing 64 (out), while
`Δ = (99, 100)` has bearing 63 (in). An engine that rounds instead of truncating will differ by one unit there.

## 2. Opcodes

| Opcode | Len | Test (condition := ...) | No target |
|---|---|---|---|
| `InArc` 0x73 | 2 (operand unused) | target position in arc | false |
| `InRange` 0x72 | 2 (message operand) | `d < range` | false |
| `InArcAndRange` 0x71 | 2 (message operand) | in arc (skipped when the target stands exactly on the unit's position), then `d < range`; the arc is tested first and a failure stops there | false, unless a target point is set: then the same test on the point |
| `BrokenTargetInRange` 0x78 | 1 | **true if the target is not broken**; if it is broken: `d < range` (silent) | false |
| `IfTargetNotBroken` 0xD1 | 1 | the target exists and is not broken (`0x2000` clear) | false |
| `IfTargetVisible` 0xE3 | 1 | `IsVisible` from the unit to the target **with the unit treated as facing the target**, so the view cone never fails and only scenery and `SightEdge` decide. The facing is restored afterwards (no visible turn). | false |
| `TargetValid` 0x74 | 1 | line-of-fire safety check (§3) on the target unit, or on the target point when there is no target unit **or** `unit_flags2` bit 0x10 ("aim at the point") is set | false when neither a target unit nor a target point is available |

`unit_flags2 & 0x10` is set by the game when it picks an area aim point for the unit, and cleared when
`FireAtTarget`/`CastPending` launch. No shipped script sets it (🟡 exact trigger).

`BrokenTargetInRange` reads as "is the target still worth shooting": a fleeing target stays valid only while it is
inside weapon range. Its name is misleading, so implement it as written above.

`InArc` has no same-position exception: a target exactly on the unit's position has bearing 256, so it is in arc
only for a unit facing 193..319.

## 3. `TargetValid` 0x74 — is it safe to shoot at the aim point?

Aim point: the target unit's position, or the target point (see §1). Two independent checks:

1. **Independent units only** (unit flag bit 27, the "independent" toggle): the shot is refused if any **other
   friendly unit** (not the shooter, not the target, not hostile to the shooter) has its centre within
   `its footprint radius + max(blast radius, 24)` of the aim point. The blast radius comes from the §8.3 table (0 for
   bows and crossbows, 24 for cannons, mortar and volley gun, 60 for the rock lobber).
   🟡 "Friendly" here also passes an allegiance-table test between the two units' sub-sides that is not yet
   described publicly; treat every non-hostile unit as friendly.
2. **Crossbows (missile code 2) only**: the shot is refused if any unit **not hostile** to the shooter stands on
   the line of fire to the aim point (the missile-obstruction line test of "Routes, collisions and visibility").
   This is the rule already noted in §8.1.

If neither check refuses, the condition is true. A shooter that is neither independent nor a crossbow unit always
gets true when it has a target. `TargetValid` does not test range, arc or the broken flag.

`TargetGone` (0x56) does not share this logic: it is the close-combat "opponent gone" handler documented in
`game_rules.md` (event 0x19, "opponent gone").

## 4. Test vectors

The unit is at (0, 0) with a bow (range 576) unless stated otherwise. Facing 0 = +Y, 128 = +X.

| Before | Instruction | Condition after |
|---|---|---|
| facing 128, target at (500, 0) | `InArcAndRange 0` | true |
| facing 128, target at (576, 0) | `InArcAndRange 0` | false (d = 576, not < 576) |
| facing 0, target at (100, 99) | `InArcAndRange 1` | false (bearing 64, arc; message 2002) |
| facing 0, target at (99, 100) | `InArc 0` | true (bearing 63) |
| facing 0, target at (0, −300) | `InArc 0` | false (bearing 256) |
| facing 0, no target, target point (0, 400) | `InArcAndRange 0` | true |
| no target, no target point | `InArcAndRange 0` / `InRange 0` / `InArc 0` | false |
| facing 256, target at (0, −575) | `InRange 0` | true (d = 575; arc not tested) |
| melee unit (no missile code), target at (10, 0) | `InRange 0` | false (range 0) |
| target not broken, at (5000, 0) | `BrokenTargetInRange` | true |
| target broken, at (400, 0) | `BrokenTargetInRange` | true |
| target broken, at (700, 0) | `BrokenTargetInRange` | false |
| target broken | `IfTargetNotBroken` | false |
| target behind the unit, clear line | `IfTargetVisible` | true (the cone is ignored) |
| target behind a wood (scenery on all three sample rays) | `IfTargetVisible` | false |
| crossbow unit, friendly unit on the line to the target | `TargetValid` | false |
| bow unit (not independent), friendly unit on the line | `TargetValid` | true |
| independent cannon unit, friendly unit with radius 30 at 40 from the aim point | `TargetValid` | false (40 < 30 + max(24, 24)) |

Names used below follow `game_rules.md`: `move_state`, `s_rlmv` (speed stat), map object (footprint), `diag_angle`,
`AttackDirection`, `EffectRange`. A facing `f` looks along `(sin f, cos f)`.

✅ **Aim point settled (batch 4):** for a frontal charge the aim point is on the target's **far** side (facing + 256),
as §5.1 says. `AttackDirection` codes 0/4 are the front arc, which also agrees with the flank-test table. The
`game_rules.md` sentence has been corrected. The worked example is in `movement_formation.md` Part A §5.

## 5. `IfTargetInChargeReach` (0x4D)

**Length:** 1 word, no operand. **Target:** the unit's current target unit. The opcode does not check for a
missing target. Scripts only run it after `MoveToTarget` has succeeded, so an engine may treat "no target"
as condition false. 🟡 The original does not handle that case at all.

### 5.1 The aim point and the reach distance

The test does not measure to the target's position. It measures to an **aim point** P, built from the
target's map object (centre C, bounding radius r = box half-diagonal, facing f_t):

- **Block-formation targets** (Infantry, Cavalry, Archers, Wizard, Special, notype: every formation kind except
  war machine, monster and wagon): P is placed **on the far side of the target**, r from its centre along
  the target axis that is closest to the charger's line of approach. Compute
  `AttackDirection(charger, target)`. This is the eight-code value already used for flank and rear charges. It comes
  from the bearing from the charger's unit position to C, taken relative to f_t, and from the target's
  `diag_angle`. Then:

  | attack direction | charger is in the target's… | aim angle a | P lies at the target's… |
  |---|---|---|---|
  | 0 / 4 | front arc | f_t + 256 | rear edge |
  | 1 / 5 | rear arc | f_t | front edge |
  | 2 / 6 | flank (bearing − f_t between `diag_angle` and 256 − `diag_angle`) | f_t + 128 | opposite flank |
  | 3 / 7 | other flank | f_t − 128 | opposite flank |

  `P = C + (trunc(SIN[a] × r / 256), trunc(COS[a] × r / 256))`. `SIN`/`COS` are the game's 512-entry tables,
  `trunc(256 × sin/cos(2π a / 512))`, and the divisions truncate toward zero. 🟡 The product `SIN[a] × r` is held in
  16 bits, so it wraps for r > 127. That needs a block of about 20 × 4 or larger and does not occur in practice.
- **Other targets** (war machine, monster, wagon footprints): **P = C**, the target's centre.

The reach distance is

```
d     = trunc( sqrt( (P.x − U.x)² + (P.y − U.y)² ) )      U = the charging unit's position (its front-rank centre)
reach = d − r
in reach  ⇔  reach < 12 × s_rlmv                          (strict)
```

Consequences:

- For a non-block target, `reach` is the straight-line distance from the charger's front-rank centre to the
  target's bounding circle.
- For a block target attacked head-on, P sits r beyond the centre, so `d − r` is the distance to the **target's
  centre**, not to its facing edge. The test therefore needs the charger to be about half the target's depth
  closer than a pure edge-distance test would. Off-axis approaches measure slightly more than the centre distance.
- The threshold is `12 × s_rlmv` and not the charge budget `12 × (s_rlmv + 1)` that `StartCharge` gives the
  charge ("Charge" in `game_rules.md`). The script gate is therefore 12 world units (half an inch) stricter than
  the distance a charge can actually cover.
- The distance is a straight line to the aim point. It is not a route length: the test requires the route to
  be a single unobstructed leg (see below).

### 5.2 Conditions, in order

Any failure writes the condition **false**. Passing all of them writes it **true**.

1. **Re-forming** (`unit_flags & 0x8`, models walking to new slots, the flag that `WaitWhileUnitFlags 0x4008`
   waits on) → false. This is the only check that comes **before** the side effects below.
2. *(side effect)* The aim point P is written as the unit's **final waypoint**. See 5.3.
3. *(side effect)* The step planner refreshes the heading and distance to the unit's **first** waypoint and
   re-runs the per-tick obstruction test on that line, as ordinary movement does each tick ("Routes, collisions
   and visibility" in `game_rules.md`).
4. **Turn needed ≥ 32** (22.5°) → false. The turn is the absolute difference, folded to 0…256, between the unit's
   current facing and the heading of the first leg. If step 3 found an obstruction, the deflected heading is used
   instead, but check 5 rejects that case anyway. The unit must therefore already face the aim point to within
   ±22.5°. The opcode never turns it.
5. **Path obstructed** (step 3 found a blocking map object or unit footprint on the line, so the unit would
   steer around it) → false.
6. **Target is charging** (the target's `move_state` charge bit 0x40, set by `StartCharge`) → false.
7. **Unit busy**: `unit_flags` has any of 0x8 (re-forming), 0x80 (charging), 0x200 (in melee), 0x800000 (step 3
   found a **friendly** unit, other than the target, in the way) or 0x1000000 (one-tick contact latch: it is
   touching an enemy and engagement is pending) → false.
8. **Re-form queued** (`move_state & 0x1`, set after a gradual turn) → false.
9. **Waypoint count ≠ 1** → false. After step 2 the count is at least 1, so this rejects units that are
   following a multi-waypoint route.
10. **Out of reach**: `d − r ≥ 12 × s_rlmv` → false.
11. **Standing on blocked ground**: the unit's own position lies inside a region of mask `0xB0` (`SOLID`,
    outside an `INVSOLID`, `BATTLEEDGE`; the same mask routes use) → false. Only the charger's position is
    tested. The target and the line to it are not.

Several other conditions are **not** tested here. These belong to the contact/engagement rules, not to this
gate: the target being broken, hidden or out of sight, the line of sight, and whether the target is an enemy.

### 5.3 Side effects (even when the result is false)

Any unit that passes check 1 keeps the following changes, even when the condition comes out false:

- **Final waypoint replaced.** With n waypoints queued, the last one (slot n) is overwritten with P and the
  count stays n. With none queued, P becomes waypoint 1 and the count becomes 1. A unit already moving to its
  target (`MoveToTarget` → single waypoint at the target's centre) is thus re-aimed at P while it walks. A
  charging unit, or one on a longer route, has its **final destination changed to P** and then fails a
  later check.
- **Planner state refreshed**, the same as one ordinary planning step:
  - the cached bearing and distance to waypoint 1;
  - the "obstructed / steering around" movement bit (`move_state & 0x10`) and its deflected heading;
  - `unit_flags 0x800000`, the friendly-unit-in-the-way flag (cleared first, set again if found);
  - the turn-direction bit `unit_flags 0x20` (set when the needed turn is clockwise, 0 < Δ ≤ 256);
  - the steering side, reset when the line is clear.
- **No other effects:** facing, position, orders, `move_state` movement bits (other than 0x10), the target link
  and the target are untouched. The opcode does not start a move or a charge. That happens in the script
  that `IfGotoScript 160` jumps to.

### 5.4 How the scripts use it

Library scripts 105, 158 and 159 (and 6 mission scripts) use the same pattern: `MoveToTarget`, then a loop of
`SetWait 10 / IfTargetInChargeReach / IfGotoScript 160 / Wait`. The unit walks at its target and re-tests about
every 10 ticks. As soon as it is in reach, facing the aim point and unobstructed, it switches to the charge
script. Because of the side effect, each test also re-aims the walk at the current aim point.

### 5.5 Test vectors

In every row: unit U at (0,0), `unit_flags` = 0, `move_state` = 0, no obstruction, U on passable ground.

| Before | Instruction | After |
|---|---|---|
| U facing 128 (+x), s_rlmv 11, no waypoints. Target: monster footprint centre (130,0), r 10, not charging. | `IfTargetInChargeReach` | P = (130,0); d = 130, reach 120 < 132 → **true**. Waypoints = [(130,0)], count 1. |
| Same, target at (150,0). | `IfTargetInChargeReach` | reach 140 ≥ 132 → **false**. Waypoints = [(150,0)], count 1 (side effect persists). |
| U facing 128, s_rlmv 18 (cavalry). Target: block, map-object centre (200,0), facing 384 (towards U), 8 wide × 4 deep → half-extents 48 × 24, r 53. | `IfTargetInChargeReach` | Front arc → a = 384+256 ≡ 128; P = (253,0); d = 253, reach 200 < 216 → **true**. |
| Same block target, s_rlmv 11. | `IfTargetInChargeReach` | reach 200 ≥ 132 → **false** (the target's front face is only 176 away). Waypoint 1 = (253,0). |
| Same as row 1, but U facing 192 (+x turned 45° clockwise). | `IfTargetInChargeReach` | turn needed 64 ≥ 32 → **false**. Waypoint 1 = (130,0). |
| Same as row 1, but U has 3 waypoints queued. | `IfTargetInChargeReach` | waypoint 3 := (130,0), count stays 3 → **false**. |
| Same as row 1, but `unit_flags` = 0x80 (U already charging). | `IfTargetInChargeReach` | **false**, yet the final waypoint is now (130,0). |
| Same as row 1, but `unit_flags` = 0x8 (re-forming). | `IfTargetInChargeReach` | **false**, no side effects. |
| Same as row 1, but the target's `move_state` has 0x40 (the target is charging). | `IfTargetInChargeReach` | **false**. |

🟡 The block radius in rows 3–4 assumes r = trunc(√(48² + 24²)) = 53. `game_rules.md` gives the radius as the box
half-diagonal, but its exact rounding was not re-checked.


## 6. `PendingInRangeArc` (0x94) and `PendingInRange` (0x95)

**Length: 2 words each.** The opcode is followed by one operand.

**Operand = "report failure" flag.** When it is non-zero and the **range** test fails, the game prints the
standard out-of-range message (`GMTXT 2001`, the one used for shooting). No message is printed for an arc
failure. Library scripts pass 0 except in one place (script 132, `PendingInRangeArc 1`).

**What "pending" means.** It is the unit's **pending spell**: the spell code stored when a cast order arrives
(player click or AI choice, event 0x2B). It is used by `CastPending` (op 147) and cleared to "none" by
`CastPending` and `DropPendingSpell` (op 170).

**Which point is tested:**

1. If the unit has a target unit: the target's **unit position** (its front-rank centre for a block, not its
   map-object centre).
2. Otherwise the stored target **point**, if both coordinates are ≥ 0.
3. Otherwise → condition **false**. Without a target the condition is still written.

**Range:** `trunc(Euclidean distance from the caster's unit position to the point) < range`, strict. The range
is `EffectRange(pending spell)`, i.e. the public spell range table: 24" = 576, 18" = 432, 36" = 864, 6" = 144,
Wind Blast a random (4…24)" re-rolled at every test, and "unlimited" for spells without a range. With no
pending spell, the range is the largest finite `EffectRange` among the unit's own spells of the targeted
kind. 🟡 That fallback is not used by the shipped scripts' normal flow.

**Arc (0x94 only):** the bearing from the caster's position to the point must be **strictly within ±70/512 of
the caster's facing** (half-width 71: circular difference < 71, about ±49.9°). This is the same ±50° as the
`LaunchEffect` casting check. Two exceptions:

- a point exactly at the caster's position always passes;
- **while the caster is in melee** (`unit_flags & 0x200`) the arc test is **skipped** and 0x94 behaves like 0x95.
  (`game_rules.md` "Casting" says an engaged wizard's spell is cancelled when the target is outside the arc. That
  must come from the scripts or from `LaunchEffect`'s own arc check, not from this opcode.)

**Side effects:** none, apart from the optional message. No turn, no state change.

| Before | Instruction | After |
|---|---|---|
| Caster at (0,0) facing 0 (+y), not in melee, pending Lightning (24" = 576). Target unit position (0,500). | `PendingInRangeArc 0` | 500 < 576, bearing 0 → **true** |
| Same, target at (400,400) (bearing 64 = 45°, distance 565). | `PendingInRangeArc 0` / `PendingInRange 0` | arc 64 < 71 → **true** / **true** |
| Same, target at (500,0) (bearing 128). | `PendingInRangeArc 0` | 128 ≥ 71 → **false**. With `unit_flags` 0x200 (in melee) → **true**. |
| Same, target at (0,600). | `PendingInRange 1` | 600 ≥ 576 → **false**, out-of-range message printed. |
| No target unit, target point (−1,−1). | `PendingInRange 0` | **false** |

