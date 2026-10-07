# Unit-script magic: spell choice, pending spell, casting

Public implementation report, batch 7 of the interpreter requests (GitHub #3). Behaviour only. Companion to
`script_animation_sound.md` (batch 6: cast pose, `IfCasting`, `IfCastingAnimation`, event 0x2C),
`target_queries.md` §6 (`PendingInRange*` geometry), `threat_events_nodes.md` (§0 sides and "hostile"),
`unit_script_control.md` and `game_rules.md`. Script listings come from `python3 -m whshr scripts <installation>`.

**Read in `game_rules.md` rather than re-deriving:**
- "Winds of magic and casting": the two power pools (0–8, player and enemy; the allied side uses the player's),
  the 50 s wind, spell costs, the player's click path (cost paid on the click), the launch checks
  (who can cast, range from the unit centre, ±50° arc, unit-target spells need a unit under
  the point), no casting roll, `GMTXT 2021` on failure;
- "Spells" (per-spell ranges and effects), "Dispel and anti-magic", "AI casting";
- "Who shoots, orders and volleys" (special shooters, used by `IsSpecialShooter` below).

Opcode lengths are from `whshr/behaviour.py` `LENGTHS`. Counts are uses across all mission DLLs (the shared library
100–170 counted once per DLL). Spell codes below are the effect codes 1–25 in the cost table of `game_rules.md`
(1 Wind Blast, 2 Azure Blades, 3 Storm of Shemtek, 4 Sapphire Arch, 5 Lightning, 6 Piercing Bolts, 7 Burning Head,
8 Conflagration, 9 Flamestorm, 10 Fireball, 11 Flying Bower, 12 Tangling Thorn, 13 Hunting Spear, 14 Curse of
Anraheir, 15 Flock of Doom, 16 Dispel Magic, 17 Gaze of Mork, 18 Ere We Go, 19 Da Krunch, 20 Fists of Gork,
21 Mork Save Uz, 22 Warp Lightning, 23 Skitterleap, 24 Pestilent Breath, 25 Madness).

## 0. Shared state (read this first)

### 0.1 Per unit

| state | meaning |
|---|---|
| **pending spell** | a spell code, or *none*. Set by a cast order or a `Choose…`/`SetSpellIfAffordable` opcode, cleared to *none* by `CastPending` (success **or** failure) and `DropPendingSpell`. A failed `Choose…` also sets it to *none*. |
| **current target** | the same unit slot used by shooting and melee (`unit_script_control.md`). The `ChooseEnemy…` opcodes **write** it; `ChooseSpellForTarget…` read it. |
| **target point** | (x, y), "unset" when a coordinate is negative. Written by `SetCastPointNode`, by a ground-point cast order and by the chooser for the spells listed in §2.3. |
| **aim at point** | a yes/no state: when set, `CastPending` aims at the target point even though a current target exists. Set by the chooser for Dispel Magic, Ere We Go, Mork Save Uz and Skitterleap; cleared **only** by `CastPending` (a later choice of another spell, or `DropPendingSpell`, leaves it on, so the next cast would aim at the old point 🟡 edge case). **Not** read by `PendingInRange*` (they always test the current target when there is one, `target_queries.md` §6). |
| **threat range** | the first operand of `SetThreatRange` (`game_rules.md` "Unit behaviour scripts and events"); only used here by the Skitterleap rule. |
| **spell list** | up to 5 entries from the unit's `addspell:` lines, **in file order** (the order matters: the AI takes the first acceptable entry). Each entry carries "has an active effect cast by this unit" and, for Dispel, "selected" states. |

### 0.2 Per side: the power pools

Two pools, **player** and **enemy**, each always clamped to **0…8** on every write. A unit uses the **enemy pool if
it is in the enemy army, otherwise the player pool** (player army and allied side share it). Payment subtracts the
cost (clamped at 0). Nothing in this batch ever **refunds** power: a spell paid for and then dropped, refused or
failed is lost.

### 0.3 When the cost is paid

| path | when paid |
|---|---|
| player clicks a spell button | on the click (`game_rules.md`), before any script runs |
| `ChooseEnemyAndSpellPay`, `ChooseEnemyOfClassAndSpellPay`, `ChooseSpellForTargetPay` | **when the spell is chosen**, before the turn, the range re-test and the cast pose |
| `ChooseEnemyAndSpell`, `ChooseSpellForTarget` ("no Pay") | **never**: the spell is chosen and later cast for free |
| `SetSpellIfAffordable` | **never**: it only checks the pool |
| `CastPending` | **never** (it only launches) |

So "Pay" vs "no Pay" is exactly "subtract the cost from the side's pool on success" vs "don't". The no-Pay forms are
shipped only 3 times (BF004_3 twice, BF029 once): scripted free casts.

### 0.4 The "launch" request that `CastPending` hands to the spell module

The spell module needs only: **spell code, caster unit, origin model, aim point (x, y)**, and returns success or
failure. It does **not** get a target unit: spells aimed at a unit find it themselves as the unit under the aim
point (`game_rules.md` "Checks"). Minimal interface:

```
launch(spell, caster, origin_model, x, y) -> bool
  fails (and does nothing) if: caster cannot cast; aim point out of the spell's range from the
  caster's centre or outside ±50° of its facing (arc skipped while the caster is in melee); a unit-target spell finds
  no unit under the point (Madness: no hostile, not-already-mad unit)
  on failure: the spell's panel entry is made usable again; GMTXT 2021 only if the caster is in the player army
```

## 1. Summary table

| op | name | words | operands | writes | condition | uses |
|---|---|---|---|---|---|---|
| 0x9C | `ChooseEnemyAndSpellPay` | 1 | – | target, spell, maybe point/aim, pool | chosen | 101 (lib 137, 139) |
| 0x9D | `ChooseEnemyOfClassAndSpellPay` | 2 | class code | same | chosen | 16 |
| 0x98 | `ChooseEnemyAndSpell` | 1 | – | target, spell, maybe point/aim | chosen | 2 (BF004_3) |
| 0xA2 | `ChooseSpellForTargetPay` | 1 | – | spell, maybe point/aim, pool | chosen | 362 (lib 129, 138, 140, 143, 144, 145) |
| 0x99 | `ChooseSpellForTarget` | 1 | – | spell, maybe point/aim | chosen | 1 (BF029) |
| 0xA0 | `SetSpellIfAffordable` | 2 | spell code | spell (only if affordable) | affordable | 1 (BF035) |
| 0xA1 | `SetCastPointNode` | 2 | map node | target := none, point := node | **no** | 1 (BF035) |
| 0x93 | `CastPending` | 1 | – | launches; spell := none; aim := no; maybe target := none | launched | 90 (lib 133, 142) |
| 0xAA | `DropPendingSpell` | 1 | – | spell := none; panel entry usable | **no** | 90 (lib 132) |
| 0x95 / 0x94 | `PendingInRange` / `PendingInRangeArc` | 2 | report flag | – | in range (/arc) | 294 / 271 |
| 0x96 | `TargetInCastArc` | 2 | ignored | – | in arc | 1 (BF029) |
| 0x97 | `PendingReachesBrokenTarget` | 1 | – | – | see §5 | 45 (lib 146) |
| 0x9A | `IfEnemyPower` | 2 | n | – | enemy pool ≥ n | 2 (BF026, BF034) |
| 0xAC | `AddEnemyPower` | 2 | n | enemy pool += n (clamped) | **no** | 1 (BF035) |
| 0x79 | `IsSpecialShooter` | 1 | – | – | special shooter | 90 (lib 115, 117) |

None of these instructions yields. "Condition: no" means the previous condition survives.

## 2. The `Choose…` family

### 2.1 Target choice (`ChooseEnemy…` only)

The nearest unit by distance between unit positions (whole field, **no range limit, no visibility test, no
`SetThreatRange`**) among units that are:
- **hostile** to the chooser (`threat_events_nodes.md` §0),
- active, **not hidden, not broken, not leaving the battle**, not buildings/furniture,
- of the operand's class for 0x9D (the operand is the class code `class × 8` as in `s_race & 0xF8`: shipped
  **16** Cavalry, **24** Archers, **32** Artillery, **40** Wizard; 0 would mean any class).

Ties: the **first** unit in unit-table order keeps it (strict "closer than"). No deployment special case.

The found unit is **written to current target before the spell choice**. If no unit is found, or the spell choice
then fails, **current target is set to none** and pending spell to none. So a failed `ChooseEnemyAndSpellPay` clears
the unit's target (library 137 then re-finds one with `TargetNearestEnemy`).

### 2.2 Spell choice (all five `Choose…` opcodes)

Input: the chooser, the target (`ChooseSpellForTarget…`: the current target; none → fail at once).
Walk the chooser's spell list **in order** and take the **first** entry that passes all of:

1. its cost ≤ the chooser's side pool;
2. the entry has **no effect of this spell already active** that this unit cast (no stacking by the AI);
3. the **target unit's position** is within the spell's range from the chooser (`trunc(d) < range`, same test as
   `PendingInRange`, ranges from the "Spells" table; "unlimited" spells always pass). Wind Blast's range is a fresh
   random roll each time, so **evaluating a Wind Blast entry consumes a random number** even though it is never
   chosen (matters for deterministic replays);
4. the spell's own rule:

| spell | rule | aim |
|---|---|---|
| Wind Blast, Sapphire Arch | **never chosen** | – |
| Storm of Shemtek, Lightning, Piercing Bolts, Burning Head, Flamestorm, Fireball, Hunting Spear, Curse of Anraheir, Gaze of Mork, Warp Lightning, Pestilent Breath | target in the **AI arc** | target |
| Madness | target in the AI arc **and** the target is not already maddened | target |
| Azure Blades | `trunc(d) ≤ 23` | target (the blades then hit units overlapping the enemy, including the casting wizard itself, `notes/spell_blades_flock_items.md` §2) |
| Fists of Gork | `trunc(d) < 16` | target 🟡 |
| Conflagration of Doom | **no non-friend unit within 56** of the target (`trunc(d) < 56`) | target |
| Flying Bower, Tangling Thorn, Flock of Doom, Da Krunch | no non-friend unit within 32 of the target | target |
| Ere We Go, Mork Save Uz | some **non-hostile** unit (not the chooser, not the target; not hidden, not leaving) within 24 (`≤ 24`) of the target's position; the nearest one | **point** = that friend's position, aim at point |
| Skitterleap | `trunc(d) <` the chooser's **threat range** | **point** = chooser position + `floor(0.9 × threat range)` (integer `threat_range × 9 / 10`) in the direction **from the target to the chooser** (jump away), aim at point |
| Dispel Magic | (target ignored) the Dispel entry is not "selected" (this wizard has not cast Dispel Magic this battle, `notes/spell_lasting_effects.md` §5.4), no Dispel of this unit is running, **and** the **first** active effect in the effect list that was cast by a unit hostile to the chooser and is not itself a Dispel has a caster that is **not hidden** and **can see the chooser** (standard view cone, `game_rules.md` "Routes, collisions and visibility") | **point** = chooser's own position, aim at point |

**AI arc**: the bearing from the chooser to the target position differs from the chooser's facing by **less than
55/512 of a turn** (≈ ±38.7°), a narrower arc than the launch test's 71/512 (±50°), so a wizard always turns first
when the target is near the edge. A target exactly at the chooser's position passes. Unlike `PendingInRangeArc`, this
arc is **not** skipped in melee.

**Area rule (inverted, `game_rules.md` "AI casting")**: "non-friend" = any unit that is hostile, or that is not
hostile but whose race pairing with the chooser is not the "friend" pairing (🟡 the race-pair table also marks
some same-side pairs as non-friends). The target itself is hostile and at distance 0, so the test fails for every
ordinary target. The exception is a target that is temporarily **not counted as a ground unit** (a state some
units enter during parts of their own animation, 🟡 e.g. airborne fliers); in shipped play these five spells are
effectively never chosen by the AI.

On success: pending spell := the code, condition true, and with "Pay" the cost is subtracted from the side pool
(the player pool's spell buttons are refreshed). The target point and aim-at-point state are written **only** for
the four "point" spells; for every other spell the old target point is left as it was (and is not used, because the
current target exists and aim-at-point is off).

On failure: pending spell := none, condition false, nothing paid.

### 2.3 Which spells the AI can actually cast in shipped data

Enemy-army wizards (battle and army files):

| list (in file order) | units | castable by the AI |
|---|---|---|
| Dispel, Warp Lightning, Madness, Pestilent Breath, Skitterleap (or Madness before Warp Lightning in 2) | 11 + 2 army-file | Dispel (if hostile magic is up), **Warp Lightning**, **Madness**, Pestilent Breath (6"), **Skitterleap** (escape; succeeds only while the wizard is in melee, `notes/spell_lasting_effects.md` §2) |
| Orc/Goblin shamans: Dispel + four of Da Krunch, Gaze of Mork, Fists of Gork, Ere We Go, Mork Save Uz | 8 | Dispel, **Gaze of Mork**, Fists of Gork, Ere We Go / Mork Save Uz (on a friend fighting the target); Da Krunch never |
| Skitterleap only | 1 (BF035, scripted teleport §6) | Skitterleap |

Allied-side wizards: Amber (Tangling Thorn, Flying Bower, Flock of Doom, Hunting Spear) → only **Hunting Spear** in
practice; Bright (Fireball) → **Fireball**.

Player wizards also run these choosers when given an attack/search order (library 129–136, `game_rules.md` "AI
casting"), paying from the player pool: Amber lists → Hunting Spear, Curse of Anraheir; Bright lists → Piercing
Bolts, Burning Head, Flamestorm, Fireball (not Conflagration); Celestial lists → Lightning, Azure Blades, Storm of
Shemtek (not Wind Blast, Sapphire Arch); the `GeneralDispel` entries → Dispel.

**Suggested effect priority:** Warp Lightning, Gaze of Mork, Hunting Spear, Fireball, Lightning (plain bolts/beams),
Madness, Skitterleap, Dispel Magic, Ere We Go / Mork Save Uz, Fists of Gork, Pestilent Breath; then the
player-only spells.

## 3. Other opcodes

### 3.1 `SetSpellIfAffordable code` (0xA0, 2 words)

If the side pool ≥ the cost of spell `code` (looked up in the spell table, ignoring two high marker bits of the code;
it does **not** need to be in the unit's spell list): pending spell := `code`, condition true. Otherwise condition
false and the pending spell is unchanged. **Nothing is paid.** Shipped once: BF035 `535` = Skitterleap with a marker
bit (512 + 23). The marker has no visible effect except that `EffectRange` does not recognise the code, so the cast
has **unlimited range** (the ±50° arc still applies), and the launched effect is **undispellable** (`notes/spell_effects.md` §1.1, `notes/spell_lasting_effects.md` §5.1).

### 3.2 `SetCastPointNode node` (0xA1, 2 words)

Current target := none; target point := the position of map node `node`. Condition not written. Does not touch the
pending spell or aim-at-point (not needed: without a target `CastPending` uses the point).

### 3.3 `CastPending` (0x93, 1 word)

```
if pending spell is none: condition false; nothing else (target, aim state untouched).
else:
  if a current target exists and aim-at-point is off: aim = the target's leader figure (without a leader: roster
       entry frontage − 1, or entry 0 if that is not below the unit's size; `notes/spell_effects.md` §2.1) position
  elif target point is set: aim = target point
  else: fail
  launched = launch(spell, caster, origin model = the model whose event triggered the cast, else none
                    (start = unit position; Lightning/Banner of Wrath do the reverse, `notes/spell_effects.md` §2.1), aim)   # §0.4
  condition := launched
  aim-at-point := off
  if the unit is in the "cast-only target" state (the state library 155 sets with `SetUnitFlags 0x4000000` before
     the scripted cast scripts 131/135): current target := none
  pending spell := none
```

Success and failure both clear the pending spell; failure loses the power (no refund). Note the aim point for a unit
target is the target's leader figure, while `PendingInRange*` test the target's unit position; at the edge of range
the opcode can pass and the launch still fail (🟡 rare).

### 3.4 `DropPendingSpell` (0xAA, 1 word)

Clears the pending spell's cosmetic "cast ordered" mark (button availability never depended on it, `notes/spell_lasting_effects.md` §8),
then pending spell := none. **No refund.** Target, target point and aim-at-point are untouched;
condition not written. Shipped only in library 132: a cast order for a wizard **in melee** whose target is in range
but outside the arc, and a cast order whose target is out of range (`game_rules.md` "Casting").

### 3.5 `IfEnemyPower n` (0x9A) and `AddEnemyPower n` (0xAC)

`IfEnemyPower n`: condition = **enemy** pool ≥ n, whatever the unit's side. Shipped `2` (BF026, BF034).
`AddEnemyPower n`: enemy pool := clamp(pool + n, 0, 8); no condition. Shipped `4` (BF035, just before the free
Skitterleap — a gift, not a payment). The related player-pool and subtract opcodes (0x9B, 0xAB, 0xAD, 0xAE) are not
shipped.

### 3.6 `TargetInCastArc` (0x96, 2 words)

Condition = there is a current target and its unit position is within the **launch arc** (difference from facing
< 71/512, ±50°; a target exactly at the unit's position passes). No current target → false. The arc is **not**
skipped in melee. Operand ignored. Shipped once (BF029, operand 0).

### 3.7 `IsSpecialShooter` (0x79, 1 word) — not magic

Condition = the unit's missile code is **14, 15 or 17**, the "special shooters" of `game_rules.md` "Who shoots"
(they fire their own routine at once; 17 = Gyrocopter bomb). The missile code is read as in that section
(Archers: the unit's `S_BalWeap`; Artillery: the leader's; others: the leader's if non-zero, else the unit's).
Used by library 115/117 to choose `FireAtTarget` instead of a volley.

## 4. The cast order path (player), for completeness

The cast order is taken by `TakeEventTarget` (0xAF, library 155 case 0x2B, after `IfCasting 1 1` returned false):
pending spell := the order's spell. **Correction (batch 9, `script_grid_events.md`):** a player cast order (event
0x2B) never names a unit — its source is always none — so it always takes the ground branch: current target := none and
target point := the click (for an **item** with an existing target, the target is kept). Then library 132 runs (range,
arc, turn, cast pose; `script_animation_sound.md` §3.5).

## 5. `PendingReachesBrokenTarget` (0x97, 1 word)

```
no current target         -> false
target is broken          -> condition = target's position within the pending spell's range (no arc, no message)
otherwise                 -> true
```

Used in library 146 (the "halt and get ready to cast" step of the advancing-wizard loops 143/144): a routing target
keeps running, so the wizard only makes its quarter turn towards it when the spell can still reach it.

## 6. Test vectors

Pools: P = player, E = enemy. Wizard W in the enemy army at (0,0) facing 0 (+y), threat range 240.

| before | instruction | after |
|---|---|---|
| E = 2; W list [Dispel, Warp Lightning(2), Madness(2), Pestilent Breath(1), Skitterleap(1)]; nearest hostile H at (0,400), not mad; no hostile magic active | `ChooseEnemyAndSpellPay` | target H; Dispel rejected (no hostile effect); Warp Lightning: 400 < 576, bearing 0 → chosen; pending 22; **E = 0**; cond true |
| same, H at (300,300) (bearing 64) | `ChooseEnemyAndSpellPay` | Warp Lightning: 64 ≥ 55 → rejected; Madness rejected (arc); Pestilent Breath: 424 ≥ 144 → rejected; Skitterleap: 424 ≥ 240 → rejected → target **none**, pending none, E = 2, cond false |
| same, H at (0,200) | `ChooseEnemyAndSpellPay` | Warp Lightning chosen (arc ok, 200 < 576) — the list order wins over Skitterleap |
| E = 1, H at (0,200) | `ChooseEnemyAndSpellPay` | Warp Lightning (2) unaffordable; Madness unaffordable; Pestilent Breath 200 ≥ 144 rejected; Skitterleap 200 < 240 → chosen; point = (0, −216) (0.9 × 240 = 216 away from H); aim at point; E = 0 |
| E = 1, H at (0,240) | `ChooseEnemyAndSpellPay` | Skitterleap: 240 < 240 false → rejected (strict) |
| E = 3, Orc shaman list [Dispel, Da Krunch(3), Gaze(2), Ere We Go(2), Mork Save Uz(1)], H at (0,300), a friendly regiment F at (10,310) | `ChooseEnemyAndSpellPay` | Da Krunch rejected (H itself is a non-friend within 32); Gaze of Mork in arc → chosen, E = 1 |
| as above but H at (200,200) (outside the AI arc) | `ChooseEnemyAndSpellPay` | Gaze rejected (arc); Ere We Go: F within 24 of H? F at (10,310) is 152 from H → no; Mork Save Uz same → target none, cond false |
| W's current target H, pending none, E = 0 | `ChooseSpellForTargetPay` | nothing affordable → pending none, cond false; **target kept** |
| W's current target H, E = 0 | `ChooseSpellForTarget` (no Pay) | still needs cost ≤ pool → false. "No Pay" never casts beyond the pool |
| E = 5, pending none | `SetSpellIfAffordable 535` | pending 535 (Skitterleap, unlimited range), cond true, E = 5 |
| E = 0 | `SetSpellIfAffordable 535` | cond false, pending unchanged |
| any | `SetCastPointNode 35` | target none, point = node 35; condition unchanged |
| E = 7 | `AddEnemyPower 4` | E = 8 (clamped) |
| E = 2 | `IfEnemyPower 2` / `IfEnemyPower 3` | true / false |
| pending 22, target H in range and arc | `CastPending` | launch at H's leader figure; cond true; pending none; aim off |
| pending 22, target H **out of range** (paid already) | `CastPending` | launch fails; cond false; pending none; **power not refunded**; message 2021 only for a player-army caster |
| pending none | `CastPending` | cond false; nothing else |
| pending 16 (Dispel), aim at point, point = own position, target H | `CastPending` | launches at the own position (aim-at-point wins over the target) |
| pending 13, target H | `DropPendingSpell` | pending none; target H kept; condition unchanged; no refund |
| target H broken, pending 22, H at distance 600 | `PendingReachesBrokenTarget` | false (600 ≥ 576) |
| target H not broken, any distance | `PendingReachesBrokenTarget` | true |
| no target | `PendingReachesBrokenTarget` / `TargetInCastArc 0` | false / false |
| target at bearing 70, W in melee | `TargetInCastArc 0` / `PendingInRangeArc 0` | **true** / true (arc 70 < 71) |
| target at bearing 71, W in melee | `TargetInCastArc 0` / `PendingInRangeArc 0` | **false** / true (arc skipped in melee) |
| unit with missile code 17 | `IsSpecialShooter` | true |

## 7. Worked example: the computer wizard loop (library 137 → 134 → 142 → 133)

A computer Skaven wizard in its attack behaviour runs library 137 every pass:

```
137: TestUnitFlags2 8 (held by Tangling Thorn) → skip everything
     IfCastingAnimation 0 → busy → skip
     ChooseEnemyAndSpellPay
     If   GosubScript 134
     Else TargetNearestEnemy; If TurnToFaceTarget; If WaitUntilUnitFlags 16 ...
134: PendingInRangeArc 0 → GosubScript 142
     else PendingInRange 0 → GosubScript 141 (turn: `TurningToCastMessage` is not used here); PendingInRangeArc 0 → 142
142: TestUnitFlags 512 (in melee) → ClearEvent; CastPending           # instant cast in melee
     else PlayLeaderAnimation 7 44                                  # cast pose; event 0x2C → 155 → 133 CastPending
```

1. Tick t: not busy; `ChooseEnemyAndSpellPay` picks the nearest hostile H as target and Warp Lightning (in the 55/512
   arc and in range), pays 2 from the enemy pool. Pending = 22.
2. 134: `PendingInRangeArc 0` true (71/512 arc) → 142: not in melee → `PlayLeaderAnimation 7 44`: the leader
   enters the cast pose in this tick's model update; `IfCasting`/`IfCastingAnimation` are now true.
3. A few ticks later the leader's event step posts 0x2C; library 155 → 133 → `CastPending`: launch at H, pending
   none.
4. Next passes: `IfCastingAnimation 0` stays true until the pose ends, so no new choice; then the loop repeats
   with whatever power is left. With the pool at 0, `ChooseEnemyAndSpellPay` fails, **clears the target**, and the
   `Else` branch re-acquires the nearest enemy and turns to face it.
5. If H was outside the 55/512 AI arc, nothing affordable passes, the target is cleared and re-found, and the
   wizard turns to face it; the next pass then chooses normally.

**Quirk in the advancing loops 143/144** (from the listings plus the pay rule): the loop calls
`ChooseSpellForTargetPay` (paying), on success halts via 146, leaves the loop because the unit is now halted, and
then calls `ChooseSpellForTargetPay` **again** before 142. The second call pays a second time (the first pending
spell is simply overwritten), or fails if the pool is now too low, in which case nothing is cast and the first
payment is lost. 🟡 confirm in play; implement it as the scripts say.

## 8. Corrections and refinements to `game_rules.md`

- "Checks": the failure message `GMTXT 2021` is shown **only for player-army casters**; allied and enemy failures are
  silent. Updated there.
- "AI casting": the area-spell rule rejects every ordinary target; the only exception is a target temporarily not
  counted as a ground unit (§2.2). Added there.

## 9. Open items 🟡

- Race-pair "friend" table: which same-side race pairs count as non-friends (only matters for the area rule).
- Which units enter the "not counted as a ground unit" state and when (exceptions to the area rule).
- Exact aim figure of `CastPending` for a target without a leader.
- The one extra state that stops a cast order from taking its unit target (§4).
- The double payment in 143/144 (§7): confirm in the running game.
