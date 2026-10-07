# Spell effects: the active-effect list, the magical hit, bolts and beams

Issue #168, part A. Status markers: ✅ established, 🟡 hypothesis, ⬜ unresolved. Companion: `notes/spell_lasting_effects.md`
(part B: Madness, Skitterleap, Ere We Go, Mork Save Uz, Fists of Gork, dispel, the winds, spell-entry states). Earlier public
rules: `game_rules.md` "Winds of magic and casting", "Spells", "Dispel and anti-magic"; `script_magic.md`;
`casualty_bookkeeping.md` §2.

Scope: the shared effect framework, one magical hit on one unit,
and the projectile spells Warp Lightning, Gaze of Mork, Lightning, Fireball, Hunting Spear, Pestilent Breath (spell and
behaviour 27), Piercing Bolts of Burning and The Burning Head. Lasting/unit-state spells, dispel and the winds are in
`notes/spell_lasting_effects.md` (part B); this report only names the effect fields they use.

Read first, not repeated here: `game_rules.md` "Winds of magic and casting", "Spells", "Dispel and anti-magic",
"Death kinds", §8 "Impact" and the wound/save tables, §7.2 "Panic"; `script_magic.md` §0 and §3.3 (`CastPending`);
`casualty_bookkeeping.md` §2 (kill credit); `script_behaviours.md` §1.10 (behaviours 26/27 and their aim points);
`obstacle_steering.md` (obstacle scan, steer point).

Conventions: distances in world units (24 = 1"), `d` = `trunc(sqrt(dx² + dy²))` (all distances in this report are
truncated this way), angles in 1/512 turn, one tick = one battle update. "rand" = one draw from the game's random
generator (non-negative); `D6` = `rand mod 6 + 1`; "even rand" = `rand mod 2 = 0`. Every draw named in this report
consumes a random number in the order given, which matters for deterministic replays.

---

## 1. Active effects (framework) ✅

### 1.1 What an active effect holds

Every launch that succeeds creates one **active effect**, which lives until its spell has run its course (including the
visual tail, §1.5) or is cancelled (§1.4). Keeping the effect as a live object, rather than resolving a spell in one
step, matters because almost every rule acts on it while it lasts:

- the spell's own behaviour runs from it, tick by tick (flight, timers, phases, auras, end step and stat restores);
- dispel finds and removes effects, measured from the effect's position (`spell_lasting_effects.md` §5);
- the caster's "spell active" state (§1.3) comes from it, and the AI refuses to re-cast a spell while it is active;
- the AI's Dispel choice looks for a hostile active effect (`spell_lasting_effects.md` §5.5);
- cancellation acts on it: replacement by a new cast, Ctrl+click, the caster's or target's removal (§1.4).

Fields an engine needs (names are ours; how effects are stored is the engine's choice):

| field | meaning |
|---|---|
| spell code | effect code 1–27, or an item code (Banner of Wrath = Lightning, Grudgebringer = Fireball) |
| owner | the **caster unit** (always the launching unit, also for innate effects) |
| innate | launched by a special weapon or a behaviour (Doomwheel bolts, Dragon breath, warpfire, steam gun, behaviour-27 breath) rather than cast; innate effects skip the caster, range and arc checks, are never cancelled or dispelled (§1.4) and never touch the spell list (§1.3) |
| undispellable | set when the launched code carries the "marker" value 512 (shipped once: BF035's `SetSpellIfAffordable 535` = Skitterleap + 512, `script_magic.md` §3.1). The dispel scan skips such effects (part B).  |
| aim point | the (x, y) handed to the launch, **before** scatter (§2.2) (Flying Bower: after its own nudge) |
| target unit | for unit-target spells only (Hunting Spear here; Azure Blades, Curse, Ere We Go, Mork Save Uz, Madness in part B) |
| projectile | at most one flying object (start, scattered destination, flight counter, height, S/strengths/wound die/saves/damage type, stop-on-hit, impact behaviour) — §2 |
| value, timer, phase | per-spell counters (Hunting Spear strike strength and leg clock, Storm bolt count, durations…); the **phase** counts the effect's stages (flight → impact flash → end) |
| visual parts | trail and flash particles, sounds — presentation, but see §1.5: they keep the effect alive |

The **origin model** is *not* stored: it is only used to place the projectile's start (§2.1).

### 1.2 What is an effect, and the original's capacity limit

**Each** launch is one effect, cast or innate: each Lightning/Fireball/…, each Doomwheel bolt (3 per volley), **each**
Dragon breath flame (4–9 per breath) and warpfire flame (1–6), each steam-gun shot, each behaviour-27 breath, item
effects, and every lasting spell until it ends. Not effects of their own: ordinary missiles, area objects (they are map
objects owned by an effect), Storm of Shemtek's successive bolts and Hunting Spear's legs (they belong to their
spell's one effect).

The original allows at most 64 effects at the same time; a launch beyond that fails like any failed launch
(`GMTXT 2021` for player-army casters, innate launches included). The cap is practically unreachable in normal play
and is not a game rule: an engine may use any capacity or none.

### 1.3 "This caster has an active effect of this spell" (the spell-list state of `script_magic.md` §0.1)

- It is a state of **(caster, spell code)**, recorded on the **first** entry of the caster's spell list (item list for
  item codes) whose code matches. Two list entries with the same code share one state on the first entry.
- **Set** at every successful **non-innate** launch (for Dispel Magic the "selected" state is set instead — part B).
- **Cleared** when a non-innate effect of that caster and code ends or is cancelled **and** no other in-use effect of
  the same caster and code remains (stacked casts keep it set until the last one ends).
- Consequence: the AI chooser (which refuses entries in this state) cannot re-cast a bolt spell until the previous one
  has fully ended, **including its visual tail** (§1.5).

### 1.4 How an effect ends or is removed

Natural end: each spell runs through its phases (§3); when the last phase is done the effect's end routine runs
(stat restores etc. for part-B spells; nothing for bolts), its sounds stop, the effect is gone and §1.3 is updated.

Cancellation (immediate, same end routine, projectile/particles/area objects removed at once, no impact, no message
except dispel's own) happens to **non-innate** effects only:

| trigger | which effects |
|---|---|
| a new launch of Wind Blast, Flamestorm, Tangling Thorn **or Curse of Anraheir** by the same caster; Ctrl+click on the spell button | the caster's previous effects of that code |
| dispel (part B) | per its rules |
| a Fireball-type impact near a Tangling Thorn (§3.4) | that thorn |
| **the caster unit is removed from the battle** (destroyed, fled off the field, removed by a script) **and its class is Wizard** | **all** of its effects — bolts in flight vanish with no impact |
| **a unit is removed from the battle** | every effect whose **target unit** is that unit (e.g. a Hunting Spear chasing it) |

Not triggers: the caster routing/being broken, fighting in melee, losing models, being out of range afterwards; the
target routing. A **monster-class spellcaster** (leader missile code 16, e.g. a Wyvern-riding shaman) is **not** class
Wizard: its effects are *not* cancelled when it is removed and run to their natural end (🟡 their kills are then
credited to a unit no longer on the field).

### 1.5 Visual tail

After the decisive moment, bolts stay active while their impact flash / trail particles finish (Lightning, Gaze,
Warp Lightning, Banner of Wrath: one flash; Fireball, Grudgebringer, warpfire, Burning Head: until every trail
particle has finished). During the tail the effect still holds the §1.3 state and is still a dispel candidate
(part B). It deals no more damage. 🟡 the tail length is the particle animation's
(a few ticks); an engine may use a fixed short tail (e.g. 8 ticks) and keep it data-driven.

### 1.6 Launch side effects ✅

- A successful launch (cast **or** innate) makes the caster unit **no longer hidden** (as if spotted, but without the
  spotting events).
- The launch itself moves nothing: the effect's first update happens later in the **same tick** (§1.7), so the
  projectile's first tested position is its start point.

### 1.7 Per-tick order

One battle update: (segment bookkeeping) → **every unit in table order** (behaviour script — where `CastPending`
launches —, movement, models) → **ordinary missiles** → **active effects** → model deaths/corpses → housekeeping.
Inside the effect step: (1) the item dispel auras, (2) the Dispel Magic / Mork Save Uz auras, (3) every effect
advances once. The order of effects among themselves is not specified (the original's is not launch order); an
engine may choose any fixed order. A projectile therefore moves and tests after every unit has moved this tick.

---

## 2. Projectile mechanics shared by the bolt spells ✅

### 2.1 Start point, aim point and heights

- **Start**: the origin model's position (unit position + model offset) if an origin model is given, else the
  caster unit's position. The origin model is the model that posted the casting event: the cast pose is played by the
  **leader model**, so normal casts start at the leader. A cast made without the pose (wizard in melee, item use by
  script 152) has no origin model → unit position. **Quirk (Lightning and Banner of Wrath only):** these two use the
  leader *only when no origin model was given* and the unit position otherwise — the reverse of every other spell.
  Hunting Spear always starts at the unit position; Doomwheel bolts and the behaviour-27 breath start at the unit
  position.
- **Aim point** given by `CastPending`: a unit target is aimed at that unit's **aim model** = its leader model, or
  without a leader the roster entry number `frontage − 1` (counting from 0; entry 0 if that is not below the unit's
  size). Resolves the 🟡 in `script_magic.md` §3.3. A ground click is the clicked point.
- **Aim height** (height of the destination above its ground): if a **flying** unit object stands at the aim point,
  half its height plus its elevation; otherwise none. Then a per-spell floor (table §3.0).
- **Height rule** (all projectiles, also ordinary missiles): the height above the ground under the projectile is
  `L + line(t) − ground(here) + arc(t)`, where `line` runs from `ground(start) + L` to `ground(destination) + A`,
  L = launch height, A = aim height. On flat ground that is `2L` at the start and `L + A` at the end (the launch
  height counts twice). Effective heights on flat ground: Lightning, Gaze of Mork 8; Warp Lightning 0 → 4;
  Piercing Bolts, Burning Head, Pestilent Breath 16; Fireball arc 0 → 9 → −1 (§3.4); Hunting Spear 8 above the
  ground everywhere (terrain-following).

### 2.2 Scatter (spell bolts scatter like missiles)

Every bolt spell except Hunting Spear is scattered at launch exactly like a missile (`game_rules.md` §8.3), using the
**caster unit's own BS** and the spell's range:

```
step   = trunc(8 × d(start, aim) / spell range)          # range 576 Lightning/Gaze/Warp/Fireball, 432 Piercing/Burning Head, 144 Pestilent
for x then y:
    off  = (rand mod (11 − min(BS, 10))) × (+1 if next rand is even else −1) × step
destination = aim + (off_x, off_y);    then the aim height is re-read at the destination's ground
```

Draw order: x magnitude, x sign, y magnitude, y sign (four draws even when the magnitude range is 1). Wizards have BS
3–4 (offsets 0…7× or 0…6× the step); monster shamans with BS 0 use 0…10×. **There is no casting roll, but a bolt can
land beside its target.** Innate launches scatter too (Doomwheel: its own BS and range 576 even when the bolt
distance is much longer; behaviour-27 breath: range 144 against distances up to ~760, so a large step).

### 2.3 Flight and the in-flight test

Each tick the projectile takes its next position `dest + trunc((start − dest) × r / N)` per axis (r = remaining
ticks, counting down from N; the **first** tested position, r = N, is the start point), then runs one **in-flight
impact test** there (§4) with: the caster's own unit **excluded**, **no messages**, radius 0.

- Units, buildings and solid objects (scenery, and spell **area objects**: Tangling Thorn, Flamestorm column, Wind
  Blast trail, Da Krunch) can be struck. A projectile that **stops on hit** ends as soon as its in-flight test hits
  anything (a unit, even if every roll failed, a building, or a solid object at a height it reaches).
- A projectile whose height above the ground under it would be **negative** is removed at once, without impact:
  **hills and ridges between caster and target stop bolts** (the launch has no line-of-sight check, the flight has
  this one).
- Flight length: **beams** (Lightning, Gaze of Mork, Warp Lightning, Banner of Wrath): `N = 1 + trunc(d(start,
  destination) / 20)` — just under 20 units per tick; **fixed 18 ticks** for Piercing Bolts, Burning Head, Fireball,
  Grudgebringer, Pestilent Breath; Hunting Spear §3.5.

### 2.4 Terminal impact

- **Beams**: on the first tick whose position is closer than **40** (`d < 40`) to the destination, after that tick's
  in-flight test, a **terminal impact** at the destination (height 0, nothing excluded — the caster's own unit can be
  hit —, messages on), then the effect goes to its flash tail. Because a beam moves < 20 per tick, this happens at the
  latest at r = 2 (one or two ticks before the nominal end). A beam stopped in flight earlier makes **no** terminal
  impact; if it is stopped on the same tick it comes within 40, **both** happen (two hits that tick).
- **18-tick projectiles**: at r = 0 the in-flight test runs at the destination, then (if the projectile is still alive
  and not below ground) the terminal impact at the destination (height 0, nothing excluded, messages on). For
  pass-through projectiles (Burning Head, Pestilent Breath) a unit at the destination is therefore hit **twice** on the
  last tick. **Fireball** never reaches its terminal impact against a ground point (§3.4).
- If nothing is at the destination, the terminal impact simply hits nothing.

### 2.5 Pass-through rule

Projectiles that do not stop (Gaze of Mork, Burning Head, Pestilent Breath, steam gun) run one in-flight test per
tick: every unit whose footprint contains the current point (§4.1) takes **one** hit that tick, so a unit is hit once
per tick the projectile spends inside it (≈ footprint diameter / speed). Friendly units are hit like enemies; only the
caster's own unit is spared in flight.

---

## 3. Per spell

### 3.0 Summary table

| Spell (code) | start | launch / aim height floor | flight | stop on hit | S (vs buildings) | wounds | save | damage type (death kind) | impact behaviour |
|---|---|---|---|---|---|---|---|---|---|
| Lightning (5), Banner of Wrath (item) | unit position, or leader if no origin model (§2.1 quirk) | 4 / 4 | beam | yes | 6 (6) | D3 | no | 0 | plain |
| Gaze of Mork (17) | origin model | 4 (flying caster: its elevation) / 4 | beam | **no** | 6 (6) | 1 | **yes** | 0 | plain |
| Warp Lightning (22), Doomwheel bolt | origin model (Doomwheel: unit position) | 0 / 4 | beam | yes | 5 (5) | D6 | no | 0 | plain |
| Piercing Bolts of Burning (6) | origin model | 8 / 8 | 18 ticks | yes | 4 (4) | 1 | no | 1 fire | plain (does **not** burn thorns) |
| The Burning Head (7) | origin model | 8 / 8 | 18 ticks | **no** | 4 (4) | 1 | yes | 1 fire | plain + **panic** (§3.6) |
| Fireball (10), Grudgebringer (item) | origin model | 0 / 0, arc +1 per tick | 18 ticks | yes | 4 (4) | 1 | no | 1 fire | plain + **burns thorns** (§3.4) |
| Pestilent Breath (24), spell and behaviour 27 | origin model (behaviour: unit position) | 8 / 8 | 18 ticks | **no** | 3 (3) | 1 | no | 0 | plain |
| Hunting Spear (13) | unit position | 8 above ground (terrain-following) | 9-tick legs re-aimed every 3 ticks | yes | 6…1 (same) | D3 | no | 0 | homing + strike chain (§3.5) |

"Plain" = the magical hit of §4. All are magical (`MagicResistent` applies), radius 0, never order a rout, never
request the impact panic test of ordinary missiles (§4.4).

### 3.1 Lightning, Banner of Wrath

Beam (§2.3–2.4). Typical sequence: scattered destination; one test per tick along the line; first unit/building/solid
object struck stops it (one random model of a unit: S6, D3 wounds, no save); otherwise the terminal impact at the
destination when within 40. Stopped or terminal → flash tail → end.

### 3.2 Gaze of Mork

Beam that passes through: one S6 hit with armour save on **every** unit the beam crosses, once per tick inside each,
plus the terminal impact within 40 of the destination (which can also hit the caster's own unit if the destination
lies in its footprint). Only terrain ends it early.

### 3.3 Warp Lightning (spell and Doomwheel)

As Lightning but S5, **D6** wounds, launched from height 0. As a spell it never fails. Each **Doomwheel bolt** (three
per volley, `game_rules.md` "Special weapons") is an innate launch preceded by its own failure roll: `rand mod 6 = 5`
→ that bolt is not fired (1 in 6), `GMTXT 2021` if the Doomwheel is in the player army; nothing else happens (the
machine is not harmed, the other bolts roll independently, the reload stamp already happened). A fired bolt aims at
the centre of the unit found (or the random fallback point) and is scattered with the Doomwheel's BS (§2.2).

### 3.4 Fireball, Grudgebringer

18 ticks; height `arc(t)` = +1 per tick while `2r > N`, −1 per tick afterwards (with N = 18: 1, 2 … 9, 8 … 0, −1),
so it flies low (≤ 9). Against a ground destination the final tick's height is −1: the in-flight test **still runs at
the destination** (a ground unit there is hit, silently, caster excluded) and then the projectile is removed for
being below ground, so **no terminal impact and no "direct hit" message**. Against a flying unit (aim height > 0) the
terminal impact happens normally.

**Burning thorns** (also Dragon breath and warpfire flames, which share this behaviour): whenever one of its impact
tests hits anything, every active Tangling Thorn (any caster, any side) whose **cast point** is closer than **32**
(`min(radius, 24) + 32` with radius 0) to the impact point is **cancelled** at once (held units released by the
thorn's end routine; no dispel message). The thorn's own area object (radius 32, height 16) is a solid object, so a
Fireball flying into a thorn is stopped by it and burns it. Piercing Bolts and Burning Head, although fire, do **not**
burn thorns.

### 3.5 Hunting Spear

Launch: the target unit = the unit under the aim point (**any side**, any state; nearest by distance from the point to
the unit's aim model, which must be `< max(footprint radius, 48)`; none → launch fails). Strength S = 6, the effect
lasts at most **180** ticks (the timer drops by 1 every tick it runs). The first leg goes from the caster's unit
position to the **aim point**; later legs go to the target unit's **current position** (its centre).

Every tick:
1. timer = 0 → the effect ends (projectile removed, no impact).
2. Leg clock −1 (it is 9 after every (re)launch). If the leg clock is now a multiple of 3 (every third tick): the leg
   is abandoned and **re-aimed** (step 5) without loss of S.
3. Otherwise the spear advances one step of its current 9-tick leg and runs an in-flight test (radius 0, S current,
   D3 wounds, no save, caster's unit excluded, silent). A hit **stops** the leg.
4. On the tick **after** a leg stopped (a leg never runs to its end — it is re-aimed after three positions — so it
   never makes a terminal impact): if the spear's position is **inside the target's footprint**
   (`d < footprint radius` to the target's centre), the **strike chain**: impact tests at the spear's point with
   strength S, S−1, …, 1 (S strikes; 6 when it arrived unhurt), D3 wounds each, no save, silent, nothing excluded —
   each strike hits **one random model of every unit whose footprint contains the point** (target, its melee
   opponents, the caster's own unit if there). Then the effect ends. Otherwise S := S − 1 (an obstacle or another unit
   took the hit); S = 0 → the effect ends; else re-aim.
5. **Re-aim**: a new 9-tick leg from the spear's current position to the target's current position; if the
   obstacle scan of `obstacle_steering.md` (applied to that leg, ignoring the target itself) finds any map object in
   the way, the leg aims at the scan's **steer point** instead (🟡 steer side as in that report). The new leg is
   stepped once immediately (its first position is the current one, so that point is tested twice).

Consequences: the spear covers **2/9 of the remaining distance every 3 ticks** (a geometric approach, not a fixed
speed): about 28 ticks from 24" to a 40-radius target (vector V5). It usually steers around units in the way; each
thing it still strikes costs 1 S. A target moving away at more than about `footprint / 13.5` units per tick is
**never caught** (🟡 derived: equilibrium gap ≈ 13.5 × speed) and the spear expires after 180 ticks. The arrival hit
(step 3) plus the chain give 1 + S hits in total. Edge: a stopped spear exactly on the target's footprint
boundary (`d = footprint radius`) gets neither the chain (needs `<`) nor a new leg (needs `>`): the effect just ends.

**Quirk (🟡 high-ground bug, from the effect's data flow):** the strike-chain tests are made at the spear's
*absolute* height (ground + 8) instead of its height above the ground, while units are hit only at heights up to
their own height above the ground. On raised terrain (ground higher than the unit's height − 8) **every strike of
the chain misses**; only the arrival hit lands. On flat low ground the chain works as described.

### 3.6 The Burning Head

18 ticks, passes through, S4 1 wound with armour save, fire. Whenever one of its impact tests hits anything (any unit
other than the caster's in flight, a building, a solid object; at the destination also the caster's own unit), every
unit whose footprint contains the point **inclusively** (`d ≤ footprint radius`, no side test, the caster's own unit
included even in flight) takes a **panic test at modifier 0** (`game_rules.md` §7.1; failure → rout event). This
repeats on **every tick** the head is inside a unit, and twice on the last tick at the destination (in-flight test
and terminal impact). No test when the head hits nothing.

### 3.7 Pestilent Breath (spell and behaviour 27)

18 ticks, passes through, S3 1 wound, no save, damage type 0. The spell (cost 1, range 144) starts at the origin
model; the behaviour-27 breath (`script_behaviours.md` §1.10: its aim point is always towards +x, +y) is an innate
launch from the unit position, scattered with range 144 (§2.2), not dispellable, and plays a screen shake when it
finishes (presentation). Both hit every unit crossed once per tick, plus the terminal impact.

### 3.8 Piercing Bolts of Burning

18 ticks, stops on hit, S4 1 wound, no save, fire death. Terminal impact at the destination if it was not stopped.

### 3.9 Shift-key variants (all 🟡 developer toggle)

With Shift physically held at launch: Lightning, Gaze, Warp Lightning and Banner of Wrath become plain 18-tick
projectiles launched from height 0 (Gaze: from the flying elevation or 0) with the ordinary r = 0 terminal impact
(no 40-unit rule); Fireball, Piercing Bolts and Burning Head only change graphics/tail; damage values never change.
Hunting Spear and Pestilent Breath have no variant. An engine may ignore Shift.

---

## 4. One magical hit on one unit ✅

An impact test has: caster (credited unit), excluded unit (in flight only), point (x, y), height, radius (0 for every
spell here), wound die, S, S against buildings, saves allowed, damage type, messages on/off. It visits **every map
object** in object-table order; **each unit is hit at most once per test**.

### 4.1 Which units

A unit is struck when `d(point, unit centre) < unit footprint radius` (strict) **and** the height test passes: a
ground unit if `height ≤ its object height`; a flying unit if `its elevation ≤ height ≤ elevation + object height`.
(The engine's 24-unit band is an engine choice; the original uses each unit object's own height, 🟡 values not
tabulated.) With radius 0 there is no blast margin and no `GMTXT 2005`.

### 4.2 Per struck unit (radius 0)

```
model  = roster[rand mod size]                 # any model, leader/champion included, uniform
need   = TO_WOUND[S][unit T]                   # the unit's troop T, for every model (also the leader)
if D6 < need: no effect (still counts as a hit)
elif saves allowed and armour_save_fails(model's armour code, S, damage type) is false: saved
                                               # leader: armour items applied first; game_rules.md 5.3
elif unit is MagicResistent and next rand is even: ignored (50%)
else:
    model.wounds += rand mod wound_die + 1     # all wounds on this one model; excess is lost (no overflow)
    if model.wounds >= model W: credited unit := caster; cause of death := damage type   # lethal-only credit
```

Regeneration (armour code 6) follows `game_rules.md` "Regeneration by damage source" (no-save spells wound
regenerators normally; Gaze of Mork allows the 4+ roll; Burning Head, fire with a save, never wounds them).
`GMTXT 2004` ("Direct hit on the %s!") is printed for every unit struck by a **terminal** impact (messages on), whether
or not a wound resulted; in-flight tests and Hunting Spear strikes are silent.

### 4.3 Buildings, rolling stock, scenery

- **Buildings/furniture** (pseudo-units): struck under the same geometry; the building's **first model** takes
  `D6 ≥ TO_WOUND[S vs buildings][T]` and `rand mod die + 1` wounds; no save, no `MagicResistent`, lethal-only credit
  to the caster. All spells here have S vs buildings = S.
- **Rolling stock and war machines** are ordinary unit objects for impacts (🟡 not separately traced).
- **Other solid objects** (trees, walls, area objects): no damage, but a hit for stop-on-hit purposes and for the
  Fireball/Burning Head side effects.

### 4.4 Consequences

- Death: the model dies with its cause of death = damage type (`game_rules.md` "Death kinds": 0 ordinary staggered
  collapse for Lightning, Gaze, Warp Lightning, Hunting Spear, Pestilent Breath; 1 fire for Piercing Bolts, Burning
  Head, Fireball). Kill credit and `s_kills`/`s_Exp`: `casualty_bookkeeping.md` §2.1 ("Spell damage", lethal-only).
- Morale: each **death** runs the per-quarter casualty panic of `game_rules.md` §7.2 like any other death. The
  separate "≤ ¼ strength after an impact" test of ordinary missiles is **never** requested by these spells, and none
  forces a rout. The only extra morale effect is Burning Head's panic (§3.6).
- No side test anywhere: friendly and allied units are hit like enemies.

---

## 5. Test vectors

Common: caster W at (0,0) facing +y, leader at (0,0); flat ground at height 0; footprints in brackets.

**V1 — Warp Lightning, T3 no-save target.** Target unit E: 10 models, T3, W1, footprint 40, centre and leader at
(0,400). W's BS = 10 (scatter magnitude always 0; still 4 draws). d = 400, N = 21, positions y(r) = 400 − trunc(400 r / 21):
0, 20, 39, 58, 77, 96, 115, 134, 153, 172, 191, 210, 229, 248, 267, 286, 305, 324, 343, 362 (r = 21 … 2).
| update (cast tick = 1) | draws | result |
|---|---|---|
| launch | 4 scatter draws | destination (0,400) |
| 1–19 (y 0 … 343) | none | nothing inside E (y must be > 360) |
| 20 (y 362, r 2) | in-flight: pick 27 → model 7; to-wound D6 = 2 (S5 vs T3 needs 2+); no save; not MR; wounds rand 3 → 4 | model 7 takes 4 wounds (excess lost), dies, credited to W, death kind 0; the beam stops. **Same tick** d(362, 400) = 38 < 40 → terminal impact at (0,400): E struck again (new pick and rolls), `GMTXT 2004` |
| 21… | — | flash tail, then the effect ends and W's "Warp Lightning active" state clears |

**V2 — Gaze of Mork through two units.** BS 10, destination (0,400), N = 21. A: centre (0,150) [30]; B: centre
(0,300) [30]. Positions as V1. A is hit at y = 134, 153, 172 (3 ticks, one model each, S6 1 wound, save at the S6
modifier); B at y = 286, 305, 324 (3 ticks); terminal at (0,400) when y = 362: hits nothing. 6 hits, no message.

**V3 — scatter.** Caster BS 3, aim (0,400), Lightning (range 576): step = trunc(8 × 400 / 576) = 5; draws 13, 4, 7, 3
→ x off = (13 mod 8 = 5) × (+1) × 5 = +25, y off = 7 × (−1) × 5 = −35 → destination (25,365); d = 365 → N = 19.

**V4 — MagicResistent target.** As V1 but E is MagicResistent: to-wound passes, MR draw 8 (even) → ignored: no wound,
no credit, **the bolt is still stopped** (a struck unit is a hit). With MR draw 9 (odd) → wound roll as V1.

**V5 — Hunting Spear, stationary target.** E centre (0,360) [40], leader (0,360), aim (0,360). Tick 1 = cast tick.
| tick | event | spear y |
|---|---|---|
| 1, 2 | leg 1 steps (r 9, 8) | 0, 40 |
| 3 | re-aim (from 40), immediate step | 40 |
| 4, 5 / 6 | 76, 112 / re-aim | 112 |
| 7, 8 / 9 | 140, 168 / re-aim | … |
| 10–27 | 190, 211; 228, 245; 258, 271; 281, 291; 299, 307; 313, 319 (re-aims at 12, 15, 18, 21, 24, 27) | 319 (d 41, not inside) |
| 28 | step to 324: d 36 < 40 → in-flight hit on E (S6, D3, no save); leg stops | 324 |
| 29 | inside E's footprint → strike chain S6, S5, S4, S3, S2, S1 at (0,324), each one random model of every unit containing the point; effect ends | — |
Same on ground at height 40 with E's object height < 48: tick 28 hit lands, all six chain strikes miss (§3.5 quirk).

**V6 — Hunting Spear blocked.** As V5 with an unrelated unit F [30] centred at (0,200) and the steer point unusable
(🟡 geometry): the spear strikes F (S6) → next tick not inside E → S = 5, re-aim from there; arriving later at E:
arrival hit S5, chain S5…S1 (5 strikes).

**V7 — Fireball at empty ground.** Aim (0,300), BS 10, N = 18. Heights 1…9…0, −1. 19 in-flight tests at
y = trunc steps from 0 to 300; the last (y = 300, height −1) hits nothing; no terminal impact, no message; tail; end.
Same with a ground unit centred at (0,300): it is struck by the last in-flight test (silent), caster's own unit would
not be.

**V8 — Fireball into a thorn.** Thorn cast at (0,200) (area object radius 32, height 16). Fireball aimed at (0,300):
positions y = 300 − trunc(300 r / 18) = 0, 17, 34, 50, 67, 84, 100, 117, 134, 150, 167, 184 … ; y = 167 is 33 from the
thorn's centre (outside); y = 184 (r 7, arc height 6 ≤ 16) is inside the area object → struck → Fireball stops; the
impact point is 16 from the cast point < 32 → the thorn is cancelled, held units released.

**V9 — Burning Head panic.** Head passes through unit X (Ld 7) [40] for 4 ticks: each tick one X model takes S4/save;
then X tests panic: draw 4 → 4 mod 11 + 2 = 6 ≤ 7 pass; draw 9 → 11 > 7 fail → rout event. A unit Y whose
footprint also contains the point (`d ≤ footprint`) tests too, also if Y is the caster's own unit.

**V10 — Doomwheel bolt roll.** Draw 5 → 5 mod 6 = 5 → bolt not fired, `GMTXT 2021` (player army only). Draw 11 →
5 → not fired. Draw 4 → fired.

**V11 — bolt over a ridge.** Lightning from (0,0) to (0,400) over flat ground 0 except a ridge of height 20 at
y 180–220: the beam's height above the ground there would be 8 − 20 < 0, so at y = 191 (the first position on the
ridge) it is removed: no impact, no terminal, flash tail at the destination (visual only).


---

## 6. Where the original differs from the current engine model

| engine today | original |
|---|---|
| launch appends a "spell" event only | creates an active effect that lives until the spell ends (§1.1); innate launches too |
| no per-caster "effect active" state | §1.3 (caster, code), cleared only when the last one (with its visual tail) ends |
| nothing happens when the caster dies | a destroyed/fled/removed **Wizard** unit cancels all its effects (bolts vanish); target removal cancels effects on that target |
| launch does not reveal | a launch un-hides the caster |
| (ordinary missiles) linear segment test vs bounding radius with a 24 band | spells test the **point** at each tick position (`d < footprint`), with each unit object's own height; no segment sweep — a fast beam can skip a thin footprint (step < 20, so only footprints under 10 wide) |
| no spell scatter | bolts scatter with the caster's BS, step `8 × d / range` |
| no terrain blocking | negative height above ground removes the projectile (ridges block) |
| innate 14/15 projectiles 9 ticks | spell bolts: beams `1 + d/20` ticks with the 40-unit terminal rule; others 18 ticks |
| — | Fireball has no terminal impact on ground points; Hunting Spear homing/strike chain; Burning Head panic; thorn burning |

---

## 7. Corrections to public notes

1. `game_rules.md` "Winds of magic and casting", "Checks": "No line of sight, no casting roll, no miscast" stays true
   for the **launch**, but add: bolt spells **scatter** with the caster's BS (§2.2) and their projectile is **stopped by
   terrain** above its path and by solid objects, including spell area objects (§2.3). "Unit-target spells need a unit
   under the point" → precise rule §3.5 (aim model within `max(footprint, 48)`, nearest, **any side**, any state).
2. `game_rules.md` "Spells", Hunting Spear row "at the target strikes 6 times at S6…S1": the strike chain is S, S−1…1
   with the spear's *current* S (an arrival hit precedes it), each strike hits every unit containing the point, and it
   misses entirely on raised ground (§3.5). Legs re-aim every 3 ticks (2/9 of the gap); intermediate hits cost 1 S.
3. `game_rules.md` "Spells", Fireball row "burns Tangling Thorns": only when one of its impact tests hits something
   within 32 of the thorn's cast point (flying into the thorn qualifies); Piercing Bolts/Burning Head never burn
   thorns. Add: a Fireball aimed at the ground has **no terminal impact** (last in-flight test only, silent).
4. `game_rules.md` "Spells", Burning Head row "units it is inside take a panic test": only on ticks when the head's
   impact hits something; then every unit whose footprint contains the point **inclusively**, any side, **including
   the caster's own unit**, at modifier 0, repeated every such tick.
5. `game_rules.md` "Spells" table: Lightning/Gaze/Warp Lightning flight is `1 + trunc(d/20)` ticks with the terminal
   impact at < 40 from the (scattered) destination; Piercing Bolts, Burning Head, Fireball, Pestilent Breath 18 ticks.
6. `script_magic.md` §3.3 `CastPending`: "origin model = … else the caster's leader" is wrong: without a posting model
   there is **no** origin model (start = unit position), except Lightning/Banner of Wrath which do the reverse
   (§2.1). The aim figure without a leader is resolved (§2.1).
7. `script_magic.md` §3.1 ("no other use found" for the +512 marker): BF035's `SetSpellIfAffordable 535`
   (Skitterleap + 512) launches an **undispellable** Skitterleap (§1.1).
8. `game_rules.md` §8 "Impact" (applies to missiles too): the to-wound T is the **unit's** T for every model including
   the leader; the armour code is the struck model's own; the `MagicResistent` roll comes **after** a failed save and
   before the wound die; wounds never overflow to another model.
9. `game_rules.md` "Spells" (stacking note): **Curse of Anraheir** also replaces the same caster's previous Curse
   (not only Wind Blast, Flamestorm and Tangling Thorn) — part B to confirm the consequences.
10. `ranged_combat_handoff.md` §3 "Doomwheel lightning and Pestilent Breath … belong to separate behaviour work": now
   specified here (§3.3, §3.7); each is an active effect like a cast spell.

## 8. Open items

- 🟡 Unit object heights per unit type (the height test of §4.1); the engine keeps its 24-unit band until measured.
- 🟡 Visual tail lengths (flash/trail particles) — they delay the end of the effect (§1.5).
- 🟡 Hunting Spear detour: which steer side the scan picks for a leg (reuse `obstacle_steering.md`); confirm the
  high-ground strike-chain miss under Wine (cast at a unit standing on a hill).
- 🟡 Which map objects are ignored entirely by impact tests (a class of objects is skipped; probably corpses/decals).
- 🟡 Kill credit and effects of a removed monster-class caster (§1.4).
- Wine check suggested: Fireball at an empty point shows no "Direct hit" message even when a unit stands there.
