# Azure Blades, The Flock of Doom, Banner of Wrath, Grudgebringer, Doomwheel bolt aim

Issue #168, part C3. Companions for request C: `notes/spell_area_effects.md` (C1), `notes/spell_channelled_effects.md` (C2),
`notes/spell_blades_flock_items.md` (C3).
Status markers: ✅ established, 🟡 hypothesis, ⬜ unresolved. Companion to `notes/spell_effects.md` (part A: §1 active
effects, §1.7 per-tick order, §2 projectiles and scatter, §4 the magical hit) and `notes/spell_lasting_effects.md`
(part B: §0.1 "the unit under the point", §0.2 spell-entry states, §5 dispel, §7 winds and the item re-arm). Those
sections are reused by reference and not restated. Earlier public rules: `game_rules.md` §8 "Impact" (the blast
path, radius > 0), "Special weapons", "Spells", "Magic items in battle"; `script_magic.md` §2.2 (AI rules);
`script_grid_events.md` §1.3 (event 0x2D, `TakeSpellEventTarget`); `script_behaviours.md` §1.10 (behaviour 26);
`casualty_bookkeeping.md` §2 (kill credit).

Conventions as part A: distances in battle units (24 = 1"), `d` = `trunc(sqrt(dx² + dy²))`, angles in 1/512 turn
(0 = +y, clockwise), `D6` = `rand mod 6 + 1`, "tick T" = the tick of the launch (the effect gets its first update
later in that same tick, part A §1.7). **Unit position** = the front-rank centre; **footprint** = the unit's map
object (centre `(ranks − 1) × 6` behind the unit position for a block) with its **bounding radius** (the box
half-diagonal) — `game_rules.md` "Formations". `SIN[a]`, `COS[a]` = `trunc(256 × sin/cos(2πa/512))`.

---

## 1. The magical hit with radius > 0 ✅

Part A §4 covers radius 0. Azure Blades and The Flock of Doom are the only spells here that call the hit with a
radius > 0; the path is the blast path already public in `game_rules.md` §8 "Impact". Restated precisely, with the
arguments these spells use (point P, height 0, radius R, wound die, S, S vs buildings, saves, magical, messages on):

Every map object is visited in object order; objects of the excluded unit (Azure only) are skipped. For a **unit**
object O (centre C_O, bounding radius r_O, current size n_O, troop T), `d = d(P, C_O)`:

| case | test (strict) | who is struck | per struck model |
|---|---|---|---|
| core | `d < r_O` and height test | **every model** of O, in the unit's model order | `D6 ≥ TO_WOUND[S][T]` → armour save at S (leader: items first) if saves allowed → `MagicResistent` 50 % → `rand mod die + 1` wounds |
| margin | else `d < r_O + R` and height test | `k = trunc((r_O + R − d) × n_O / (r_O + R))`, **k := 1 if k < 2**, then k picks `roster[rand mod n_O]` (repeats allowed) | `D6 ≥ TO_WOUND[S/2][T]` (S/2 truncated) → armour save **at S/2** if saves allowed → `MagicResistent` 50 % → **exactly 1 wound** |
| — | otherwise | nothing | — |

- Messages: `GMTXT 2004` (core) or `GMTXT 2005` (margin) once per struck unit, printed **before** its rolls, whether
  or not anything is wounded. Both spells here have messages on (every tick for Azure Blades: an engine may
  rate-limit the text; it is presentation).
- Random-number order: core, per model: to-wound D6; if it passes, the save D6 (when saves are allowed); if the save
  fails and O is `MagicResistent`, the 50 % draw; if not ignored, the wound draw. Margin, per pick: the model pick,
  then the same sequence without the wound draw. Objects in object order.
- Height 0 (both spells): a ground unit always passes the height test; a unit **in the flying state** (in the air,
  elevation > 0) is **never** struck by these spells.
- Wounds, kill credit and death kind: part A §4.2/§4.4 (all wounds on the picked model, no overflow, lethal-only
  credit to the **caster** unit, death kind 0 for both spells; regenerators get the 4+ roll — `game_rules.md`
  "Regeneration by damage source").
- **Buildings / furniture** (pseudo-units): core → its first model, `D6 ≥ TO_WOUND[S vs buildings][T]`,
  `rand mod die + 1` wounds; margin (`d < r_O + R`) → first model, `D6 ≥ TO_WOUND[(S vs buildings)/2][T]`, 1 wound.
  No save, no `MagicResistent`. Lethal-only credit to the caster.
- **Other solid objects** (scenery, area objects): struck only if `d < r_O` (no margin) — no damage, no consequence
  for these two spells.
- No side test, no panic or rout request (part A §4.4): deaths still trigger the usual casualty panic
  (`game_rules.md` §7.2).
- 🟡 After a radius > 0 test that struck anything, the game runs one more map-wide refresh hook (also used by other
  blasts); it changes no unit and is not traced further.

So a unit **whose footprint circle contains the point** loses its whole front to the rolls (every model rolls), a unit
merely **overlapping** the circle takes a proportional number of weak (S/2, 1 wound) hits.

---

## 2. Azure Blades (code 2) ✅

### 2.1 Launch

- Cost 1, range **unlimited**, the launch arc ±50° applies (skipped in melee) — `game_rules.md` "Checks".
- **Aim point**: player — the wizard's own **unit position** at the moment the button is clicked (no target click;
  the order then goes through the normal cast pose). AI — the current target's aim model (`script_magic.md` §2.2
  rule `trunc(d) ≤ 23`, aim = target).
- **Target** = the unit under the aim point (part B §0.1: nearest reference figure within `max(footprint, 48)`,
  **any side**, any state). None → the launch fails (`GMTXT 2021` for player-army casters, power lost).
  - Player: the wizard's own unit in practice (its leader stands on the unit position once settled); another unit
    is taken only if its reference figure is nearer to that point (e.g. the wizard's leader still walking to its
    slot) 🟡 rare.
  - AI: the enemy target (its aim model is exactly at the point, d = 0).
- Effect: target unit, aim point, timer **180**. A looping blade particle on every model of the target (presentation;
  no random numbers). Nothing on the units changes at launch. **No replacement**: a second Azure Blades by the same
  caster stacks (the player's button stays usable — Azure only marks "cast ordered", which never disables it, part B
  §0.2; the AI will not re-cast while its entry is "active").

### 2.2 Every update

```
if timer == 0: the effect ends (no end step)             # tick T+180
else:
    blades follow the target's models (presentation)
    timer -= 1
    hit(P = the target's CURRENT unit position, height 0, R = the target's CURRENT bounding radius,
        excluded = the target unit, die 1, S 4, S vs buildings 4, saves yes, magical, messages on)   # §1
```

- **180 strikes**, on ticks T, T+1, …, T+179; the effect ends on the update of tick T+180. Strikes run in the effect
  step (after movement and close combat of that tick).
- **Who is struck**: every unit (any side, **including the caster's own unit when it is not the target**), every
  building and object, whose footprint relates to the circle (centre = the target's unit position, radius = the
  target's bounding radius) as in §1: unit position **inside** O's bounding circle → **every model of O, S4, 1 wound,
  armour save at S4**; circles overlapping only → k models at **S2**, 1 wound, save at S2.
- The circle is centred on the **unit position** (front-rank centre), not on the target's footprint centre, so for a
  deep target it reaches `(ranks − 1) × 6` further forward than its footprint and less far behind.
- Units in the flying state are never struck (height 0).
- **Consequence (model-changing)**: in frontal contact with a small unit (a wizard, 1 model), a block of frontage f
  and depth k (both ≥ 1) has its footprint centre at about `6 + 6k` from the wizard's unit position and a bounding
  radius `≈ 6√(f² + k²)`; whenever `f² > 2k + 1` (e.g. 4 wide × 4 deep, 5 × 4, 6 × 3) the wizard's position is inside
  the block's circle and **every model of the block rolls an S4 wound every tick**. A player wizard with Azure Blades
  in base contact destroys an ordinary regiment within a few ticks; narrow/deep blocks only take the margin hits.
- **AI cast (model-changing)**: the target is the enemy the wizard is fighting (rule `trunc(d) ≤ 23`); the circle is
  centred on the enemy, the enemy is excluded, and **the casting wizard's own unit is struck every tick** (it is
  within 23 of the enemy's unit position, so at least in the margin), as are friends sharing the melee. Kill credit
  for its own dead models goes to itself (lethal-only credit = caster) 🟡 consequence for the books
  (`casualty_bookkeeping.md` §2).
- Target routing, broken or hidden: the strikes go on. Target removed from the battle → the effect is cancelled
  (part A §1.4). Caster (Wizard class) removed → cancelled.

### 2.3 End, cancellation, dispel

- No end step (nothing to restore). Cancel by Ctrl+click on the active entry, by dispel, or by the removals of part A
  §1.4: the remaining strikes simply do not happen.
- Dispel position = the **aim point** (where it was cast: the wizard's position at the click, or the AI's aim
  model) — fixed even when the target walks away (part B §5.1). Exempt from a dispel pass protecting the target
  (part B §5.2: effects aimed at P), e.g. a Talisman on the wizard's own unit never removes the wizard's own Azure.

---

## 3. The Flock of Doom (code 15) ✅

### 3.1 Launch

- Cost 2, range 576 (`trunc(d) < 576` from the caster's unit position), arc ±50° (skipped in melee). Aim point = the
  click (the AI never casts it: the inverted area rule, `game_rules.md` "AI casting"). No unit needed, **no scatter**,
  no projectile.
- 20 bird particles are placed around the point: for each bird `x = Px + 32 − (rand mod 64)`, then
  `y = Py + 32 − (rand mod 64)` — **40 random numbers at launch** (presentation, but they matter for replays).
- **No replacement** (stacks). No target unit.

### 3.2 Phases and timing

The effect is driven by the birds' animation: 10 frames swooping in, then three strike cycles of 8 frames, then
4 frames flying off; each frame lasts one update.

| tick | what happens |
|---|---|
| T | launch; first update: birds frame 1 |
| T+10 | **strike 1** at the aim point; birds start the first strike cycle |
| T+18 | **strike 2** |
| T+26 | **strike 3** |
| T+34 | birds start flying off (no strike) |
| T+38 | the effect ends (no end step) |

Each strike: `hit(P = the aim point (fixed), height 0, R = 32, nothing excluded, die D6, S 3, S vs buildings 3,
saves yes, magical, messages on)` (§1):

- units whose footprint circle **contains** the point (`d < r_O`): **every model** rolls `TO_WOUND[3][T]`, armour
  save (no S modifier), `MagicResistent`, then **D6 wounds**;
- units overlapping the 32-radius circle (`d < r_O + 32`): k models at **S1**, 1 wound, save;
- **any side, the caster's own unit included**; buildings: first model S3 D6 / S1 1 wound;
- flying units never.

The point never moves (it does not follow units).

### 3.3 End, cancellation, dispel

- No end step. Ctrl+click, dispel or the caster's removal (Wizard class) cancels it at once: **remaining strikes do
  not happen** (a dispel before T+10 prevents all damage). During T+27…T+38 the effect still exists (it keeps the
  entry "active" and is a dispel candidate) but deals no damage — the "visual tail" of part A §1.5, here 12 ticks.
- Dispel position = the aim point.

---

## 4. Banner of Wrath and Grudgebringer (activated items) ✅

### 4.1 Who triggers them

- **Only the player**, through the item button of a selected player-army unit that carries the item. No shipped
  script sends the item event (0x2D), the AI chooser walks only the spell list, and nothing else launches an item
  effect: **the AI never uses them** (confirms `game_rules.md`). Banner of Wrath occurs only in the `RLTEST*.MRC`
  test armies; Grudgebringer in the campaign armies.
- Any unit class can use them (no "can cast" test, no wizard needed), and **no power is spent** (the item's table
  cost is never paid).

### 4.2 Click path and the "used" state

| step | state change |
|---|---|
| item button click (button usable = not selected and not used) | entry becomes **used** and **selected**; other targeting is cancelled; targeting mode starts |
| target click | selected cleared; an order (item code, point) is given to the selected unit |
| targeting cancelled (other button, cancel) | selected cleared; **used stays** |
| wind of magic (part B §7) | used cleared for every re-usable item of every unit of both sides |

So the use is **consumed on the button click**: cancelling the targeting, a refused order or a failed launch all
waste it until the next wind. The item's "active" state (part B §0.2) is set by a successful launch and cleared at
the effect's end like a spell's, but it never blocks the button (re-usable items ignore it) and there is no
Ctrl+click cancel for items.

🟡 **Ctrl quirk**: a target click with Ctrl held while the player's pool is ≥ 1 (the item's nominal cost, still not
paid) keeps targeting mode on and the item still selected; every further Ctrl+click issues another item order, and
each succeeds (the launch never tests "used"). Derived from the click path, not confirmed in play.

### 4.3 From the order to the launch

1. The order reaches the unit on its next script run. A unit **held by Tangling Thorn refuses it** (no event; the use
   is lost). Unlike a spell order, an item order does **not halt** a moving unit.
2. Event **0x2D** (source none, argument = the item code, point = the click) → handled only by library 152 (every
   mission handler reaches it through libraries 153–156): set the condition, `TakeSpellEventTarget`, keep the target
   across the cast, `CastPending` — **at once**: no cast pose, no "busy casting" test, no turn.
3. `TakeSpellEventTarget` for an item (`script_grid_events.md` §1.3 row 0x2D): pending := the item code; **if the unit
   already has a current target, the target is kept and the clicked point is ignored**; otherwise target := none and
   point := the click.
4. `CastPending` (`script_magic.md` §3.3): aims at the current target's aim model if there is one (and the aim-at-point
   state is off), else at the point. No origin model (no pose).

**Consequence (model-changing)**: a bearer that is attacking, shooting at or fighting a unit fires the item at **that
unit's aim model whatever the player clicked**. Only a unit with no current target fires at the click.

### 4.4 Launch checks and the effect

| | Banner of Wrath | Grudgebringer |
|---|---|---|
| checks | range 576 (`trunc(d) < 576` from the bearer's unit position), launch arc ±50° (skipped while the bearer is in melee) | same |
| failure | `GMTXT 2021` (item name), use stays consumed, no other effect | same |
| effect | exactly **Lightning** (part A §3.1: beam, scatter with the **bearer's BS**, S6, D3, no save, stop on hit) | exactly **Fireball** (part A §3.4: 18 ticks, S4, 1 wound, no save, fire, burns thorns, no terminal impact on ground) |
| start point | the bearer's **leader model** (Lightning quirk with no origin model, part A §2.1); unit position if it has no leader | the bearer's **unit position** |
| innate | **no** | **no** |

Not innate, therefore: dispellable (position = the projectile's current position, part B §5.1), cancelled if the
bearer is a Wizard-class unit removed from the battle (otherwise the bolt flies on), an active hostile effect for the
AI's Dispel rule (part B §5.5), and a successful launch un-hides the bearer. Kill credit: the bearer unit,
lethal-only (`casualty_bookkeeping.md` §2.1 "Spell damage"). Grudgebringer's close-combat bonus (+1 S, +1 WS) is
separate and unaffected.

The Dragon's breath does **not** use the Grudgebringer item effect: it launches the **Fireball** effect innately
(with its own S8 and rout request, `game_rules.md` "Special weapons").

---

## 5. Doomwheel bolt aim (behaviour 26) ✅

Each volley (`script_behaviours.md` §1.10: reload stamp, then three bolts at headings `h` = facing, facing + 128,
facing + 384, mod 512 — ahead, right, left) runs, **per bolt, in this order**:

1. **Distance**: three draws, `D = D6 × D6 × D6 × 12` (12…2592).
2. **Point**: `Q = (x + floor(SIN[h] × D / 256), y + floor(COS[h] × D / 256))` from the Doomwheel's unit position
   (floor = towards −∞ for negative products).
3. **Unit search**: the nearest unit by `d(Q, unit position)` among units with `d ≤ D` (**inclusive**; the radius is
   the bolt's own distance, so the search circle passes through the Doomwheel itself); nearest by strict `<`, ties
   to the earlier unit in the unit list. Candidates: active units of **any side**, broken/routing included, flying
   units included (no height test), **excluding the Doomwheel's own unit, hidden units and units leaving the
   battle**. 🟡 building pseudo-units may qualify (same open item as Fists of Gork). No view or arc test.
4. **Aim point**: found → that unit's **unit position** (front-rank centre — not its footprint centre). None →
   the **fallback**: two more draws, the first for y, the second for x:
   `aim = (x + floor(SIN[h] × 96 / 256) + (r₂ mod 80) − 40, y + floor(COS[h] × 96 / 256) + (r₁ mod 80) − 40)` —
   4" along the heading with up to ±40 jitter, **not** at distance D.
5. **Failure roll** (inside the launch): one draw, `rand mod 6 = 5` → the bolt is not fired (`GMTXT 2021` if the
   Doomwheel is in the player army). So the failure roll comes **after** steps 1–4 (their draws are consumed even
   for a failed bolt).
6. Fired: innate Warp Lightning from the unit position, scatter with the Doomwheel's BS and range 576 (part A §2.2,
   four draws), beam flight (part A §2.3–2.4).

Draws per bolt: 3 + (2 if fallback) + 1 + (4 if fired). The three bolts are fully sequential.

---

## 6. Test vectors

Fixed dice are the values the random source returns (`D6` = `1 + R mod 6`). TO_WOUND: S4 vs T3 → 3+, S3 vs T3 →
4+, S2 vs T3 → 5+, S1 vs T3 → 6+, S2 vs T4 → 6+. Bounding radii are given as inputs.

**Azure Blades**

| before | action | after |
|---|---|---|
| player wizard W (1 model) at unit position (0,0), footprint radius 8; enemy block E 4 wide × 4 deep (16 models, T3, W1, armour 6+), bounding radius 33, footprint centre (0,30) (frontal contact) | player casts Azure Blades (tick 0): target = W (its leader at (0,0)) | each tick 0…179: d((0,0),(0,30)) = 30 < 33 → **core**: 16 models each roll D6 ≥ 3, save 6+ at S4 (impossible), W1 → about 2/3 of E's models die on tick 0; `GMTXT 2004` |
| same, E 3 wide × 4 deep (12 models), bounding radius 30, centre (0,30) | strike | 30 < 30 false; 30 < 30 + 8 → margin, k = trunc((30 + 8 − 30) × 12 / 38) = 2 → two picks at S2 (5+), save at S2, 1 wound; `GMTXT 2005` |
| same, E's centre at (0,38) | strike | 38 < 38 false → E not struck |
| E 4 × 4 as row 1, a friendly regiment F (radius 30) beside W, centre (40,0) | strike | d = 40: margin (40 < 38? no → **not struck**; with F's centre at (36,0): 36 < 38 → k = trunc(2 × n_F / 38) → 1 pick); friends are not exempt |
| AI wizard A (1 model, T4, radius 8) at (0,0) fighting player block P (radius 33, unit position (0,12), footprint centre (0,30)) | A casts Azure at P (rule d = 12 ≤ 23) | target P (excluded); circle centre (0,12), R 33: A's centre d = 12 ≥ 8 → margin, k = trunc((8 + 33 − 12) × 1 / 41) = 0 → 1 pick: **A rolls S2 vs T4 (6+) every tick**; P untouched |
| Azure on W at tick 0 | ticks 0…179 / tick 180 | 180 strikes / effect ends, no message |
| Azure on W at tick 0; Talisman bearer B 70 from the **click point**, W since walked 200 away | B's pass, R mod 100 = 30 | dispelled (100 % aura, 70 < 80 from the aim point); remaining strikes cancelled |
| W casts Azure twice (ticks 0 and 5) | ticks 5…179 | two strikes per tick |

**The Flock of Doom** (aim point (100,100), cast tick 0)

| before | action | after |
|---|---|---|
| — | launch | 40 draws for the bird positions; no strike |
| unit A: 3 models (T3, W1, armour 6+), radius 20, centre (110,100) | strike 1 (tick 10): d = 10 < 20 → core, `GMTXT 2004`; model 1: D6 5 (≥ 4), save D6 3 (< 6, fails), not MR, wound draw → D6 4 → 4 wounds, dies (credit: caster); model 2: D6 2 → nothing; model 3: D6 6, save D6 6 → saved | A loses 1 model |
| unit B: 12 models, radius 30, centre (100,150) | strike: d = 50; 50 < 30 no; 50 < 62 → margin, k = trunc((30 + 32 − 50) × 12 / 62) = 2, `GMTXT 2005` | 2 picks at S1 (6+), save, 1 wound each |
| unit C: radius 30, centre (100,162) | strike: d = 62, 62 < 62 false | not struck |
| the caster's own unit, centre within its radius of (100,100) | strike | struck like anyone (no exclusion) |
| — | ticks 10, 18, 26 / tick 38 | three strikes / effect ends |
| enemy wizard with Dispel Magic 60 from (100,100), pass at tick 3 succeeds | – | Flock dispelled before strike 1: **no damage at all** |

**Items**

| before | action | after |
|---|---|---|
| player unit G (Grudgebringer, leader), unit position (0,0), facing 0, no target, not in melee | item click, target click (0,400) | used; event 0x2D; target none, point (0,400); launch: 400 < 576, bearing 0 → Fireball from (0,0), scattered with G's BS; no power spent; G un-hidden |
| same, G's current target E (leader at (300,300)) | click (0,400) | **aims at (300,300)** (target kept); bearing 64 < 71 and d 424 < 576 → Fireball at E |
| same, E's leader at (450,100) | click anywhere | bearing 110 ≥ 71 (not in melee; d 461 < 576) → **fails**, `GMTXT 2021`, use consumed |
| G in melee with E | click anywhere | arc skipped; fires at E's aim model |
| Banner of Wrath bearer with a leader at (6,0), unit position (0,0) | use at (0,300) | Lightning beam starts at the **leader** (6,0) |
| G held by Tangling Thorn | item click + target click | no event, nothing fired; used until the next wind |
| G used at 30 s; targeting cancelled at 31 s | – | button unusable until the wind at 50 s |
| wind | – | used cleared (both sides) |

**Doomwheel** (unit position (0,0), facing 0; `SIN[0] = 0`, `COS[0] = 256`, `SIN[128] = 256`, `SIN[384] = −256`)

| before | action | after |
|---|---|---|
| E's unit position (30,300); F's (0,−200) | bolt 1 (h 0): draws → D6 3, 4, 2 | D = 288, Q = (0,288); E: d = 32 ≤ 288 ✓; F: 488 ✗ → aim (30,300); fail draw 11 → 11 mod 6 = 5 → **not fired** (draws used: 4) |
| same | bolt 1: D6 3, 4, 2; fail draw 4 | fired at (30,300), 4 scatter draws |
| no unit within 12 of (0,12) | bolt 1: D6 1, 1, 1 | D = 12, Q = (0,12), none → fallback draws r₁ = 50, r₂ = 5 → aim (0 + 0 + 5 − 40, 0 + 96 + 50 − 40) = (−35, 106); then fail draw |
| h = 384 (left), D = 288 | – | Q = (−288, 0) |
| a hidden enemy at Q exactly, a routing friend 100 from Q | bolt with D = 288 | the hidden unit is skipped; the routing **friend** is the target |

---

## 7. Corrections to public notes

1. `game_rules.md` "Spells", **Azure Blades** row: "Range: own unit" → **unlimited**; the target is the unit under
   the aim point (player: the wizard's own unit position → normally its own unit; AI: the enemy in contact). "units
   overlapping the target unit take S4 hits, 1 wound, save" → every tick (180 strikes) a blast centred on the
   target's **unit position** with radius = the target's bounding radius, target excluded: units whose circle
   contains that point → **every model** S4/1 wound/save; overlapping units → k models at **S2**; any side; the
   caster's own unit is struck when it is not the target (always for the AI cast). §2.
2. `game_rules.md` "Spells", **The Flock of Doom** row: "three strikes, radius 32: S3, D6 wounds, save | 3 phases" →
   strikes at the fixed cast point on ticks T+10, T+18, T+26 (effect ends T+38); units containing the point: every
   model S3, D6 wounds, save; units within `32 + footprint`: k models at S1, 1 wound, save; any side, caster
   included; no scatter. §3.
3. `game_rules.md` §8 "Impact", blast margin: add "armour save at S/2 as well" and "`MagicResistent` applies in the
   margin too"; buildings: core uses the wound die, margin 1 wound at (S vs buildings)/2 (as written); scenery has no
   margin; units in the flying state are not struck by height-0 blasts. §1.
4. `game_rules.md` "Magic items in battle": replace "(flag 0x20, re-armed when the power pool is refreshed)" by the
   used/selected states of §4.2 (consumed on the **button click**, lost on cancel/refusal/failure, re-armed at each
   wind for both sides); add: range 24" and ±50° arc from the bearer (arc skipped in melee), **aims at the bearer's
   current target if any, else the click**, no cast pose/busy test, does not halt the unit, held units cannot use it,
   any class, not innate (dispellable, un-hides the bearer, triggers the AI's Dispel rule), Banner from the leader,
   Grudgebringer from the unit position. "The Dragon's breath uses the Grudgebringer effect innately" → the
   **Fireball** effect innately.
5. `game_rules.md` "Special weapons", Doomwheel row: "nearest unit of either side near that point" → nearest unit
   (by unit position; any side; not itself, not hidden, not leaving) within **the bolt's own distance D** of the
   point, inclusive; none → a point 96 ahead along the heading with ±40 jitter. Failure roll after the aim. §5.
6. `notes/spell_effects.md` §3.3: "preceded by its own failure roll" → the failure roll follows the three distance
   dice, the unit search and the fallback draws; "aims at the centre of the unit found" → at its **unit position**;
   "the random fallback point" → §5 step 4. V10 stays valid for the failure draw alone.
7. `script_magic.md` §2.2 Azure row 🟡 "the blades then hit units overlapping the enemy, which can include the
   caster's own side" → confirmed, and the casting wizard itself is always struck (§2.2).
8. `game_rules.md` "Winds of magic and casting", "Azure Blades, Dispel Magic and Fists of Gork need no target" → they
   are aimed at the wizard's unit position at the click (Azure then takes the unit under that point).

## 8. Open items

- 🟡 Ctrl+click repeated item use while the player's pool ≥ 1 (§4.2): confirm under Wine.
- 🟡 Exact stored bounding radius (rounding of the half-diagonal) — decides the core/margin boundary in §2.
- 🟡 Building pseudo-units as Doomwheel search candidates and as Azure Blades targets (shared with part B §0.1).
- 🟡 Whether a routing bearer's interrupt handler still reaches library 152 (item use while fleeing).
- 🟡 Azure Blades on a unit in Flying Bower flight (off the map): the strikes keep using its unit position.
- 🟡 The refresh hook after a radius > 0 impact (§1, last bullet).
- 🟡 Books consequence of the AI wizard crediting its own deaths to itself (§2.2).
