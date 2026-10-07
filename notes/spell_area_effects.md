# Area spells: Wind Blast, Flamestorm, Tangling Thorn, Da Krunch, Conflagration of Doom

Issue #168, part C1. Companions for request C: `notes/spell_area_effects.md` (C1), `notes/spell_channelled_effects.md` (C2),
`notes/spell_blades_flock_items.md` (C3).
Status markers: ✅ established, 🟡 hypothesis, ⬜ unresolved. Companions: `notes/spell_effects.md`
(part A: active effects §1, projectiles §2, the magical hit §4) and `notes/spell_lasting_effects.md` (part B: unit under the
point §0.1, spell-entry states §0.2, dispel §5).

Read first, not repeated here: `spell_effects.md` §1 (active effects, cancellation §1.4, per-tick order §1.7), §2.1–§2.3
(start point, scatter, flight, in-flight test), §4 (one magical hit); `game_rules.md` §8 "Impact" (radius blasts: direct
hit = every model, blast margin = some models at S/2, `GMTXT 2004`/`2005`), "Death kinds", §7.1/§7.2 (Leadership test,
casualty panic); `spell_lasting_effects.md` §0.2, §5; `obstacle_steering.md` §3 (obstacle scan); `game_rules.md`
"Routes, collisions and visibility" (collision pass, the visibility test); `casualty_bookkeeping.md` §2.1 (credit);
`movement_formation.md` Part B (rank orders, `Rally`); `unit_script_control.md` (`TestUnitFlags2`).

Conventions as in part A: distances in battle units (24 = 1"), `d` = `trunc(sqrt(dx² + dy²))`, "centre" = the unit's
footprint centre, "footprint" = its collision radius. **T** = the tick of the launch (`CastPending`, unit phase); the
effect's first update is in tick T itself (after all units, part A §1.7). "rand" = one draw of the game's generator.
Draws marked *presentation* only move particles in the original; an engine need not make them.

---

## 0. Area objects (shared) ✅

Four of these spells place **area objects**: invisible circular map objects with a radius and a height, owned by the
effect. They are not units and take no damage.

| spell | area object | where | exists |
|---|---|---|---|
| Wind Blast | up to 30 **trail discs**, radius 16, height 16 | along the gust's path (§1.4) | from when dropped until the effect is cancelled (§1.5) |
| Flamestorm | radius 16, height 80 | the aim point | from T until the effect is cancelled (it has no natural end) |
| Tangling Thorn | radius 32, height 16 | the aim point | from T until the effect is cancelled (no natural end) |
| Da Krunch | radius 32, height 40 | the aim point | ticks T+10 … T+46 (removed in T+47) |

What an area object does (exactly what any solid scenery footprint of that size does):

- **Movement**: the obstacle scan treats it as a scenery footprint that **always blocks** (no relationship filter), and
  ignores it like any non-troop footprint when it contains the mover's waypoint (`obstacle_steering.md` §3 rules 2, 6).
  Routes bend around it.
- **Collision pass**: a moving unit overlapping it is pushed out by half the overlap per pass, like solid scenery; a
  **charging** unit that touches it within ±45° of its facing ends its charge (event 0x09). Rolling stock is never pushed
  by it. A stationary unit that happens to overlap a new area object is only pushed once it moves (the collision pass
  runs for moving units only).
- **Sight lines**: it counts as scenery in the visibility line test (spotting hidden units, "is my target visible"
  for AI shooting/casting) and in the missile line test — at **any** height (the line test ignores heights).
- **Impacts** (ordinary missiles and spell projectiles): a solid object that is struck when the impact point lies inside
  its radius (`d < radius`) at a height ≤ its height (`spell_effects.md` §2.3, §4.3). Stop-on-hit projectiles end there
  (a Lightning bolt at height 8 is stopped by a thorn or a trail disc; arrows arcing above 16 pass over them).
- It is removed when the owning effect is cancelled or dispelled (part A §1.4) — for Flamestorm, Tangling Thorn and Wind
  Blast that is the **only** way it ever goes away (§1.5, §2.4, §3.4).

---

## 1. Wind Blast (code 1) ✅

Cost 2. Never chosen by the AI (`script_magic.md` §2.2). Launch arc ±50° (skipped in melee) as every spell.

### 1.1 Range

The range is **re-drawn every time it is asked for**: `range = 96 × (1 + rand mod 6)` = 4", 8", 12", 16", 20" or 24"
(multiples of 4" only). The launch check draws one and fails (as every out-of-range launch, part B §8: power lost)
unless `d(caster centre, aim point) < range` (strict). Any other range query on a spell list
that contains Wind Blast (the AI's range tests, the maximum-spell-range query) also consumes one draw
(`script_magic.md` §2.2 already says so for the chooser).

### 1.2 Launch (tick T)

1. The caster's previous Wind Blast effects are **cancelled** (their gust and all their trail discs vanish). Only after
   a successful range/arc check: a failed launch leaves the old blast in place.
2. A **second** range draw `R2` (same formula) is the range used for the scatter: `step = trunc(8 × d(start, aim) / R2)`,
   then the four scatter draws of part A §2.2 with the caster's BS. So the scatter has nothing to do with the range that
   was checked: a 24" (576) aim scattered with `R2` = 96 has a step of 48, i.e. up to 7 × 48 = 336 units off with BS 3.
3. Start point: the origin model as part A §2.1 (the leader for a normal cast).

### 1.3 The gust (ticks T … T+54)

- Flight `N = 54` ticks: positions at `r = 54 … 0` on ticks T … T+54 (`dest + trunc((start − dest) × r / 54)` per axis),
  so the speed is `d(start, dest) / 54` per tick (≈ 11 units for a 24" blast).
- **Jitter**: each tick, after the line position, `x += rand mod 8`, then `y += rand mod 8` (two draws, offsets 0…7,
  never negative — the gust wobbles towards +x/+y of its line). The jitter is not cumulative.
- **Height**: always 0 above the ground under it (it follows the terrain; hills never stop it).
- **In-flight test** every tick at the jittered point (part A §2.3): radius 0, S3 (3 vs buildings), 1 wound, armour save
  allowed, damage type 0, magical, the caster's own unit excluded, silent. So each **ground** unit whose footprint
  contains the point (`d < footprint`) loses **one random model's** roll per tick; airborne units are never touched
  (height 0); buildings take the first-model roll. It **passes through** everything (never stops on a hit).
- **Terminal impact** on tick T+54 at the scattered destination **without** jitter: radius 0, same values, nothing
  excluded (the caster's own unit can be hit), `GMTXT 2004` for each unit struck.
- **No push-back**: Wind Blast moves no unit, knocks nothing down and orders no rout. Its only lasting effect on
  movement is the trail (§1.4).

### 1.4 The trail

From the update of tick **T+5** onward (the first five updates drop nothing), after each step the gust drops a **trail
disc** at its **previous tick's** position (the position tested on the tick before, jitter included) when

- the blast has no disc yet, or
- the last dropped disc is **more than 16** away from that position (`d > 16`; at `d ≤ 16` nothing is dropped);

and the blast has fewer than 30 discs (the original stops adding discs after 30; later parts of a long path get none —
an engine may keep or drop this cap). Each disc is an area object, radius 16, height 16 (§0). The update of tick T+55
(after the last step) can still drop one disc at the T+54 position. A typical 20" blast leaves a line of ≈ 25–30 discs
about 17–20 units apart.

### 1.5 The effect never ends by itself (model-changing)

When the gust has finished, the effect **does not end**: it stays active with no further damage, its trail visuals
looping, for the rest of the battle. Consequences:

- the trail discs are **permanent obstacles** until the effect is cancelled: the same caster's next Wind Blast,
  Ctrl+click on the caster's Wind Blast button, a dispel (the effect's position is the gust's **last position**, near
  the destination, `spell_lasting_effects.md` §5.1), or the removal of a Wizard-class caster (part A §1.4);
- the caster's Wind Blast entry stays "active" (part B §0.2) — harmless for the player, whose button stays usable.

---

## 2. Flamestorm (code 9) ✅

Cost 3, range 24" (576, strict), arc ±50°. The AI casts it under the arc rule (`script_magic.md` §2.2); since the effect
never ends, **each AI wizard casts Flamestorm at most once** while it lasts (entry "active").

### 2.1 Launch (tick T)

The caster's previous Flamestorm effects are cancelled. The area object (radius 16, height 80) is placed at the **aim
point** (no scatter) at once. A held Shift key only changes the graphics.

### 2.2 Growth (ticks T … T+17)

Flames grow (presentation draws only). **No damage.**

### 2.3 Burning (from tick T+18, every tick, forever)

From T+18 on, every tick makes one **impact at the aim point** with radius 16 (the radius-blast rules of `game_rules.md`
§8 "Impact"):

| value | |
|---|---|
| S / S vs buildings | 4 / 4 |
| wound die | 1 (exactly 1 wound per wounding roll) |
| armour save | none |
| damage type | 1 (fire: death kind 1) |
| magical | yes (`MagicResistent` ignores half) |
| excluded | only the Flamestorm's own area object — **not** the caster's unit |
| height | 0: every ground unit qualifies, airborne units never |

So, **every tick**:

- a unit whose footprint contains the point (`d < footprint`) — **every model** rolls `TO_WOUND[4][T]`, then the
  `MagicResistent` roll, then 1 wound;
- a unit whose footprint edge is within 16 (`footprint ≤ d < footprint + 16`) — `n = max(1, trunc((footprint + 16 −
  d) × size / (footprint + 16)))` random models (repetition allowed) roll `TO_WOUND[2][T]` for 1 wound each;
- a building in the same geometry — its first model, S4 (inside) or S2 (margin), 1 wound.

The burning comes in 19-tick **columns**: ticks T+18 … T+36 are the first column, T+37 … T+55 the second, and so on.
On the **last tick of each column** (T+36, T+55, T+74, … = T+18+19j+18) a second, **terminal** impact with the same
values follows the ordinary one: that tick hits twice, and the terminal impact prints `GMTXT 2004` (inside) or
`GMTXT 2005` (margin) for every unit it strikes; the other impacts are silent. The first column differs only in its
graphics (it rises from below the ground). The original also spends presentation draws every tick (flame particles).

Kill credit lethal-only to the caster (`casualty_bookkeeping.md` §2.1); each death runs the casualty panic of §7.2. It
does **not** burn Tangling Thorns (it is not a Fireball-type impact, part A §3.4).

### 2.4 End

**None.** The Flamestorm burns until it is cancelled: the caster's next Flamestorm, Ctrl+click, dispel (position = the
aim point), removal of a Wizard-class caster. On cancel the area object and the flames vanish at once.

---

## 3. Tangling Thorn (code 12) ✅

Cost 3, range 24" (576), arc ±50°. The AI effectively never casts it (inverted area rule, `game_rules.md` "AI casting").

### 3.1 Launch (tick T)

1. The caster's previous Tangling Thorn effects are cancelled (their release, §3.4, runs first).
2. Presentation: 20 thorn sprites around the point (40 draws in the original).
3. The area object (radius 32, height 16) is placed at the aim point.
4. **Entangle**, once, at the launch: every unit on the map whose **centre** is strictly within 32 of the aim point
   (`d < 32`, centre distance — the footprint size does not matter) and which is a **ground unit** at that moment (not
   airborne; buildings excluded) is
   - **halted** exactly as by the `HaltAndReform` opcode (refused, i.e. nothing, for a broken or pursuing unit), then
   - put in the **held** state.

   No side test: the caster's own unit, friends, hidden, broken and routing units and units in melee are all held if
   their centre is inside. Units that walk into the thorn later are **not** held (they collide with its area object).

### 3.2 Growth and duration

The thorns grow for 6 ticks (T … T+5) and then stay. There is **no timer that ends the spell**: the effect lasts until
it is cancelled (§3.4). (The original merely refreshes the static thorn graphics every 91 ticks; nothing observable.)

### 3.3 The held state

What a held unit **cannot** do (each item is refused — nothing happens, the script's condition is false where it has one):

| action | source of the refusal |
|---|---|
| any move: player move/attack orders, `MoveToTarget`, `MoveToNode` and other routed moves | the route start is refused |
| start a **charge** (player order, `ChargeForward`, AI charge) | refused |
| start a **pursuit** | refused |
| **turn**: `TurnToFaceTarget`, `QuarterTurnToTarget`, `AboutFace`, `QuarterTurn`, player turn orders | refused |
| change ranks: player rank buttons, `SetRanks`, `ReformToScriptRanks`, `ReformBlock` | refused (`movement_formation.md` §1–§2) |
| finish a `Rally` | loops without advancing until released (`movement_formation.md` §4 step 5) |
| **shoot**: `ReadyToFire` is false | `script_shooting.md` |
| **cast**: a player's cast order is refused when it reaches the wizard (the power paid on the click is lost); the AI wizard scripts skip casting while held (below) | |
| **start a rout**: `FleeFromTarget` / `FleeAhead` are refused — see below | |

What it **still does**: fight in close combat (strike and be struck), be charged and engaged, take hits, test morale,
lose models, be targeted; a rout or pursuit that was already under way when the thorn grew is **not** stopped by the
hold (🟡 the flight and pursuit steps have no hold test). Its figures do not re-shuffle in the formation (like a
halted unit).

**Failing a morale/panic test while held** (model-changing, 🟡 traced only through the library): the rout event runs
library script 162 (`FleeFromTarget`, else `FleeAhead`, then an endless `Yield` loop). Both flee opcodes are refused, so
the unit **does not become broken and does not flee**; `FleeAhead` drops its target and the unit then idles in that
loop (no behaviour script, no shooting or casting) until some other event switches its script. It still fights if
engaged.

**What scripts observe**: the held state is the script-visible operand value **8** of `TestUnitFlags2`
(`unit_script_control.md`); value **9** tests "held or anchored war machine". Shipped uses (library, every DLL):
casting scripts 129, 132, 137, 138 skip their cast while held; behaviour/threat scripts 118–126 and 143–147 skip their
step when held or anchored; the maddened loops 128, 149, 167 do not attack while held (part B §1.2); BF029 script 0
waits in a 5-tick loop while held. No shipped script sets or clears the held state itself.

### 3.4 End (release)

The effect ends **only** by cancellation: the same caster's next thorn, Ctrl+click, dispel (position = the aim point),
a Fireball-type impact within 32 of the cast point (part A §3.4), removal of a Wizard-class caster. Its end step then:

- removes the area object;
- **releases**: every ground unit (not airborne) whose centre is **strictly within 64** of the thorn's point loses the
  held state — **whichever thorn held it**. No event, no re-form, no other change.

Consequences: a unit held by another thorn is released too if it stands within 64 of the ending thorn; a held unit
that has been pushed more than 64 away (only by collisions) is never released 🟡; a script waiting in a `Rally` or a
"while held" loop continues on the next tick.

---

## 4. Da Krunch (code 19) ✅

Cost 3, range 24" (576), arc ±50°. The AI effectively never casts it (inverted area rule).

### 4.1 Timeline (launch tick T)

| ticks | what happens |
|---|---|
| T … T+9 | the foot falls at the aim point (no scatter; the original still makes the 4 scatter draws). Foot height on these ticks: 120, 106, 93, 80, 66, 53, 40, 26, 13, 0 (`trunc(120 r / 9)`, r = 9 … 0). Each tick: one **crush test** at that height; on T+9 also the terminal crush test (height 0) |
| T+10 | the foot stands: area object radius 32, height 40, screen shake (presentation draws) |
| T+11 … T+46 | standing (36 updates) |
| T+47 | the area object is removed; the foot starts lifting (lift test, §4.3) |
| T+47 … T+56 | lift tests at heights 0, 14, 27, 40, 54, 67, 80, 94, 107, 120; terminal lift test on T+56 at height 0 |
| T+57 | the effect ends |

### 4.2 The crush test

Every map object whose footprint **reaches within 32** of the point — `d < footprint + 32` (strict, centre distance
truncated) — and whose **object height is at least the foot's current height**:

- **units** (any side, the caster's own, hidden, broken, routing, airborne included): **every model is slain
  outright** — no to-wound roll, save, `MagicResistent` or wound die; credited to the caster; death kind 2;
- **buildings**: destroyed (their first model slain, death kind 2, credited to the caster);
- scenery and other area objects: nothing.

So everything in reach is crushed on the first tick the foot is low enough for it, **at the latest on T+9** (height 0).
No message. Repeated tests on already-slain units change nothing. Kill and casualty counting follow
`casualty_bookkeeping.md` §2.1 (no exclusion; the caster can crush and credit itself).

### 4.3 The lift (harmless in practice)

The lift's tests are ordinary magical impacts at the point with radius 32, **S0** (and 0 vs buildings), wound die **0**,
no save, damage type 0, silent in flight; the terminal one on T+56 prints `GMTXT 2004`/`2005` for units it strikes. In
practice nothing is in reach (everything was crushed, and movers were pushed out of the area object until T+47). If a
unit is in reach: margin models roll `TO_WOUND[0][T]` (T0 4+, T1 5+, T2 and T3 6+, T4+ impossible) for 1 wound; a model
**inside** that passes the same roll would need a wound die of 0, which is undefined (🟡 in the original most likely a
fault; never observed). Engine: treat the lift as harmless (skip its tests) or give inside hits 1 wound — say which.

### 4.4 Dispel and cancel

Effect position = the aim point. Cancelled during T … T+8: no crush at all (the foot vanishes). During the standing
phase: the area object vanishes early, no lift.

---

## 5. Conflagration of Doom (code 8) ✅

Cost 3, range **unlimited**, arc ±50° (skipped in melee). The AI effectively never casts it (inverted rule, radius 56).

### 5.1 Launch (tick T)

One draw: `k = 1 + rand mod 6`. **The same k** sets both

- the radius `R = 8k + 8` (16, 24, 32, 40, 48 or 56), and
- the fuse `9k` ticks (9 … 54).

Nothing else happens at the launch (no area object, no scatter).

### 5.2 Fuse: panic tests

On ticks **T, T+9, …, T+9(k−1)** (k tests in all), every unit on the battle's unit list that is active — any side, the
caster's own unit, hidden, broken and routing units included (🟡 building pseudo-units are not tested) — whose
**centre** is within R of the aim point, **inclusive** (`d ≤ R`), takes a **panic test at modifier 0**, in unit-list
order, exactly as Burning Head's (part A §3.6: `game_rules.md` §7.1 Leadership test; failure → rout event). A unit that
leaves the radius is no longer tested; one that enters is.

### 5.3 The fall (ticks T+9k … T+9k+9)

The fire comes down over 10 ticks. Each of these ticks makes a **fall test** at the aim point, and the last one (T+9k+9)
is followed by the **finale** (terminal test). Both "slay outright": the first `n` models of the unit's model list
(🟡 formation order, front rank first) get lethal wounds — no to-wound roll, save, `MagicResistent` or wound die —
credited to the caster, **death kind 1 (fire)**. No side test, no exclusion (the caster's unit too).

**Fall test** (each of the 10 ticks; no height test):

| object | condition | result |
|---|---|---|
| unit | the point lies inside its footprint: `d < footprint` | `n = max(1, trunc(size × (R − d) / R))` (so `n = 1` when `d ≥ R`) |
| building | `d < footprint` | destroyed (first model slain, kind 1) |

**Finale** (on T+9k+9, after that tick's fall test):

| object | condition | result |
|---|---|---|
| unit | `d < footprint + R` (strict) | `d + footprint < R` (footprint entirely inside): **all** models; otherwise `n = max(1, trunc(size × (R − d + footprint) / (2 × footprint)))` |
| building | `d < footprint + R` | destroyed |

`size` = the unit's current number of models at that test. The fall and the finale shake the screen (presentation).
🟡 Whether consecutive fall ticks kill *new* models depends on when slain models leave the model list: a slain model
leaves its unit when its death sequence starts (1-tick collapse for kind 1, `game_rules.md` "Death kinds"), so in the
original the next fall tick may pick the same, already slain models again. Engine recommendation: remove slain models
before the next tick's effect step, so that every fall tick takes the next `n` living models.

### 5.4 After the fall, dispel

A flash and embers follow (≈ 10 + up to 36 ticks, presentation; the effect is still active and dispellable then, with
no consequence). Effect position = the aim point: **a dispel during the fuse prevents the fall** (and stops further
panic tests); a dispel during the fall stops the remaining fall ticks and the finale.

---

## 6. Summary: replacement, dispel position, end

| spell | replaces caster's previous | dispel / cancel position | natural end | what cancelling undoes |
|---|---|---|---|---|
| Wind Blast | yes | the gust's current (or last) position | **never** | gust and trail discs removed |
| Flamestorm | yes | aim point | **never** | area object and flames removed |
| Tangling Thorn | yes | aim point | **never** | area object removed; units within 64 released |
| Da Krunch | no (stacks) | aim point | T+57 | no further crush/lift; area object removed |
| Conflagration of Doom | no (stacks) | aim point | after the fall and its tail | no further panic tests, fall or finale |

All five are ordinary non-innate effects for Ctrl+click and for the removal of a Wizard-class caster (part A §1.4),
and set the caster's entry "active" (part B §0.2) for as long as they live — permanently for the first three.

---

## 7. Test vectors

Flat ground, height 0. Caster W (Wizard, BS 3) at (0,0) facing +y; "fp" = footprint radius.

**Wind Blast**

| before | action | after |
|---|---|---|
| aim (0,300) | launch; range draw `rand mod 6` = 2 | range 288; d 300 ≥ 288 → **fail**, power lost; W's previous blast (if any) untouched |
| aim (0,300) | range draw 4 → 480; R2 draw 0 → 96 | ok; previous blast cancelled; step = trunc(8 × 300 / 96) = 25; scatter magnitudes 0…7 × 25 |
| gust start (0,0), dest (0,540) (BS 10, no scatter) | ticks T … T+54 | position at r: `(0, 540 − 10r)` + jitter; e.g. r = 54 on T → (0,0)+(j,j') |
| unit E fp 40 centred (0,270), T3, 20 models, Sv 5+ | gust passes | on every tick whose jittered point is within 40 of (0,270) (r = 24 … 30, ≈ 7 ticks) one random model of E: S3 vs T3 needs 4+, armour save allowed, 1 wound |
| same, T+54 | terminal at (0,540) | nothing there → no hit, no message |
| — | ticks T+5 … T+55 | discs at the previous ticks' points, one roughly every 2 ticks (spacing > 16), radius 16 height 16 |
| trail laid | tick T+200 | the effect is still active; discs still block movement and sight |
| W casts Wind Blast again (range ok) | launch | the old effect and all its discs vanish, then the new gust starts |
| regiment marching along the trail line | movement | steers around the discs (scenery); if it overlaps one, it is pushed out by half the overlap per tick; a charge running into a disc ahead ends (event 0x09) |

**Flamestorm**

| before | action | after |
|---|---|---|
| aim (0,400) | launch at T | area object r16 h80 at (0,400); ticks T … T+17 no damage |
| unit A fp 30 centred (0,410), 16 models T3 | tick T+18 | d 10 < 30: every model rolls 3+ (S4 vs T3), no save, MR if any, 1 wound each — expected ≈ 11 wounds |
| unit B fp 30 centred (0,440), 20 models | tick T+18 | d 40: margin (40 < 46): n = max(1, trunc((46 − 40) × 20 / 46)) = 2 models roll 4+ (S2 vs T3) for 1 wound |
| unit C fp 30 centred (0,446) | any tick | d 46 = 30 + 16 → not hit |
| as A | tick T+36 | two impacts (ordinary + terminal), terminal prints `GMTXT 2004` for A, `2005` for B |
| A stays | ticks T+18 … | hit every tick (A is destroyed within a few ticks unless it moves away) |
| W's own unit, fp 40 centred (0,380) | tick T+18 | d 20 < 40 → hit like anyone else |
| Flamestorm at tick 1000 | no dispel, W alive | still burning; the AI wizard W does not cast Flamestorm again |
| W (Wizard) destroyed | removal | Flamestorm cancelled: no more impacts, area object gone |

**Tangling Thorn**

| before | action | after |
|---|---|---|
| enemy regiment E centre (0,431), fp 50; aim (0,400) | launch | d 31 < 32 → E halted and held |
| E centre (0,432) | launch | d 32 → not held, although its footprint covers the point |
| W's own unit centre (20,400) | launch at (0,400) | d 20 → W's unit is held too |
| E held | E's script `MoveToTarget` / player orders E to move or charge | refused, nothing happens |
| E held, attacked in melee | close combat | E fights normally |
| E held, archer regiment | `ReadyToFire` | false; it does not shoot |
| E held fails a panic test | rout event → library 162 | not broken, does not flee; drops target, idles |
| E held at d 31 from thorn A (caster W1); thorn B (caster W2) at (60,431), d 60 from E | B dispelled | E is released (60 < 64) although thorn A remains |
| E held by A, d 31 | A cancelled by W's next thorn at (0,1000) | E released (31 < 64); the new thorn holds units near (0,1000) |
| thorn at (0,400) cast at tick 0 | tick 5000, nothing cancelled | still active, E still held |
| Fireball impact at (0,420) hitting E | fire impact 20 from the cast point | thorn cancelled, E released |

**Da Krunch**

| before | action | after |
|---|---|---|
| aim (0,300); unit E fp 40 centred (0,371), 30 models | tick when foot height ≤ E's object height (at the latest T+9) | d 71 < 72 → all 30 slain (death kind 2), W credited |
| E centred (0,372) | crush tests | d 72 = 40 + 32 → untouched |
| building fp 30 centred (40,300) | crush | d 40 < 62 → destroyed |
| W's own unit fp 40 centred (0,250) | crush | d 50 < 72 → W's unit crushed too (credited to itself) |
| launch at T | T+10 … T+46 | area object r32 h40 at (0,300) blocks movement and sight; removed on T+47 |
| a Talisman bearer's unit centred 60 from (0,300) (aura 100 %) | effect step of tick T | the aura passes run **before** the effects advance (part A §1.7): the effect is dispelled before its first crush test — no crush at all |

**Conflagration of Doom**

| before | action | after |
|---|---|---|
| launch at T, draw `rand mod 6` = 1 | — | k = 2: R = 24, fuse 18: panic tests on T and T+9; fall T+18 … T+27; finale T+27 |
| unit P centre 24 from the point, Ld 7 | panic tick, LD draw → 9 > 7 | fails → rout event (even P = W's own unit) |
| unit Q centre 25 from the point | panic tick | 25 > 24 → no test |
| unit A fp 40, 20 models, point 10 from its centre | each fall tick | n = trunc(20 × 14 / 24) = 11 first models slain (fire) |
| unit B fp 40, point 30 from its centre (R 24) | each fall tick | n = max(1, trunc(20 × (−6) / 24)) = 1 |
| unit C fp 10, 5 models, centre 5 from the point | finale | 5 + 10 = 15 < 24 → all 5 slain |
| unit D fp 40, 20 models, centre 30 | finale | 30 < 64 → n = trunc(20 × (24 − 30 + 40) / 80) = 8 |
| unit F fp 40, 20 models, centre 60 | finale | 60 < 64 → n = max(1, trunc(20 × 4 / 80)) = 1 |
| unit G fp 40, centre 64 | finale | 64 = 40 + 24 → untouched |
| k = 6 | — | R 56, fuse 54, 6 panic tests (T, T+9 … T+45), fall T+54 … T+63 |
| Dispel Magic within 80 of the point succeeds on T+12 | — | effect cancelled: no more panic tests, no fall |

---

## 8. Where the original differs from the current engine model

Nothing of these spells exists in the engine yet. What it needs beyond the part A/B framework:

- **area objects** as live map footprints owned by an effect (radius, height; scenery-class for the obstacle scan,
  collision push, sight lines and impact tests), removed with the effect;
- **effects without a natural end** (Wind Blast after its gust, Flamestorm, Tangling Thorn): kept until cancelled;
  replacement on recast; Ctrl+click; Wizard-caster removal;
- Wind Blast: random range per query, independent scatter range, jitter, trail rule;
- the radius-16 Flamestorm impact every tick from T+18 plus the 19-tick terminal;
- the **held** state with its refusal list (§3.3), entangle-by-centre at launch, release-within-64;
- "slay outright" (lethal wounds without rolls) for Da Krunch (all models) and Conflagration (first `n` models);
- Conflagration's single D6 for radius and fuse, inclusive panic radius, the fall's per-tick rule and the finale formula.

---

## 9. Corrections to public notes

1. `game_rules.md` "Spells", **Wind Blast** row: range is `4 × (1 + rand mod 6)` inches (4, 8 … 24"), **re-drawn at
   every range query**; the scatter uses a second independent draw; duration "flight" is wrong — the gust lasts 55 ticks
   but the effect, and its **permanent trail of up to 30 solid discs** (radius 16, height 16), stays until cancelled.
   Add the jitter (gust wobbles 0–7 units towards +x/+y). "Replaces the previous blast" ✅.
2. `game_rules.md` "Spells", **Flamestorm** row: "every 18 ticks every model inside radius 16" is wrong — from 18 ticks
   after the cast it is a radius-16 blast **every tick** (direct hit: every model S4; margin: some models S2), plus a
   messaged terminal impact every 19 ticks; the caster's unit is not excluded; "🟡 no end" → ✅ no end.
3. `game_rules.md` "Spells", **Tangling Thorn** row: "units within 32" → units whose **centre** is within 32 (strict)
   **at the cast** (later arrivals are not held); duration "growth + 90 ticks" is wrong → **no natural end** (until
   recast, Ctrl+click, dispel, fire or the caster's removal); the end releases every unit within 64 of the thorn,
   including units held by other thorns; held also forbids moving, charging, turning, rank changes and **starting a rout
   or pursuit** (a held unit failing a panic test stays and idles).
4. `game_rules.md` "Spells", **Da Krunch** row: duration "≈ 45 ticks" → 57 ticks (fall 10, stand 37, lift 10); the crush
   needs `d < footprint + 32` and the foot's height ≤ the unit's object height (always met at T+9); the area object
   (radius 32, height 40) exists only while the foot stands (T+10 … T+46).
5. `game_rules.md` "Spells", **Conflagration of Doom** row: the radius and the fuse come from **one** D6 (`R = 8k + 8`,
   fuse `9k`, k panic tests, inclusive radius on the centre); the fall lasts 10 ticks, each tick slaying models of units
   whose footprint contains the point, then the finale; slain models are the **first n** of the model list.
6. `game_rules.md` "Death kinds": the **Conflagration finale** is listed under kind 2 — it is **kind 1 (fire)**, like
   all Conflagration damage. Da Krunch kind 2 ✅.
7. `game_rules.md` "Spells", area-object paragraph: "temporary solid scenery" → Wind Blast trails, Flamestorm and Tangling
   Thorn objects are **not** temporary (they last until the effect is cancelled); give the sizes of §0. Push-back acts on
   moving units only.
8. `movement_formation.md` Part B §0 ("held … halted, cannot shoot, cast or change ranks"): add — cannot move, charge,
   turn, start a pursuit or start a rout (§3.3).
9. `script_magic.md` (library script listing: "137: TestUnitFlags2 8 (held by Tangling Thorn?)"): confirmed, drop the "?".
10. `spell_lasting_effects.md` §5.3, Tangling Thorn row "held units released": every ground unit whose centre is within
    64 of the thorn's point, whatever held it.
11. `casualty_bookkeeping.md` §2.1, "Conflagration of Doom finale" row: the credit is also set by each of the 10 fall
    ticks, not only by the finale.

## 10. Open items

- 🟡 Unit object heights (part A open item): decide on which fall tick Da Krunch crushes tall vs short units (all are
  crushed by T+9 regardless).
- 🟡 Model-list order for Conflagration's "first n" (front rank first? leader position?).
- 🟡 Timing of model removal after a slay (whether consecutive Conflagration fall ticks kill new models in the original).
- 🟡 A held unit after a failed panic test: which later events can pull it out of library 162's idle loop.
- 🟡 A rout or pursuit already under way when a thorn holds the unit: confirm it continues (no hold test found in the
  flight/pursuit steps).
- 🟡 Building pseudo-units in Conflagration's panic list (assumed not tested).
- 🟡 Da Krunch lift: the inside hit with wound die 0 (§4.3) — never observed; Wine check: cast Da Krunch, walk a T3
  regiment onto the point before the foot lifts.
- Wine checks suggested: a Flamestorm left burning for several minutes (no end); a Wind Blast trail still blocking a
  regiment long after the gust; a thorn-held regiment failing a panic test (does not flee).
