# Channelled, flight, portal and curse spells: Storm of Shemtek, Flying Bower, Sapphire Arch, Curse of Anraheir

Issue #168, part C2. Companions for request C: `notes/spell_area_effects.md` (C1), `notes/spell_channelled_effects.md` (C2),
`notes/spell_blades_flock_items.md` (C3).
Status markers: ✅ established, 🟡 hypothesis or partly traced,
⬜ unresolved.

Read first, not repeated here: `notes/spell_effects.md` §1 (active effects, cancellation §1.4, per-tick order §1.7),
§2 (projectiles: start, heights, scatter §2.2, flight §2.3, terminal impact §2.4), §4 (the magical hit);
`notes/spell_lasting_effects.md` §0.1 (the unit under the point), §0.2 (spell-entry states), §5 (dispel), §6
(channelling); `game_rules.md` "Spells", §7 "The Leadership test", "Battle clock", "Death kinds";
`casualty_bookkeeping.md` §2; `flight_solid_obstacles.md` §3; `script_magic.md` §2.2.

Conventions as in `spell_effects.md`: distances in battle units (24 = 1"), `d` = `trunc(sqrt(dx² + dy²))`, angles in
1/512 turn, "rand" = one draw of the game's generator, `D6` = `rand mod 6 + 1`. **Tick T** = the tick in which the
effect is launched (by `CastPending`, in the unit phase); the effect's first update runs later in tick T (§1.7).
"Effect step" = the active-effects stage of a tick. "Hostile" = the side rule of `spell_lasting_effects.md` §1.1
(player-army or allied against enemy-army; neutral and furniture are never hostile), evaluated with the units'
**current** sides.

Fields of the active effect used here (names ours): owner (caster unit), aim point, target unit, value, timer, phase,
projectile.

---

## 1. Storm of Shemtek (code 3) — channelled bolts

Cost 3, range 24" (576), arc ±50° (skipped in melee), point target (`game_rules.md`). No unit is needed under the
point.

### 1.1 Launch ✅

- `value` := **2D6** = `(rand mod 6) + (rand mod 6) + 2` (first die drawn first). The Storm fires **value + 1** bolts
  (3 … 13), confirming the "2D6+1" of `game_rules.md`.
- The target unit starts as **none**. No projectile yet.
- A wind-up animation starts at the caster's first model (presentation, but see §1.3 for its timing).
- The caster is **channelling** from now until the effect ends (`spell_lasting_effects.md` §6).

### 1.2 Choosing each bolt's target ✅

Done anew for **every** bolt, at the moment it is launched. "Previous target" = the unit the previous bolt was aimed
at (none for bolt 1, and none if the previous choice found nothing).

1. If `d(caster's centre, aim point) > caster's footprint radius` (strict): the **nearest hostile unit** whose centre
   is within **80** of the aim point (`d ≤ 80`, inclusive).
2. Otherwise (the point lies inside or on the caster's own footprint), or if step 1 found nothing: the **nearest
   hostile unit** whose centre is within **576** (24") of the **caster's centre** (`d ≤ 576`).
3. Candidates in both searches: active units, hostile to the caster, **not the caster's own unit**, **not the
   previous target**, not hidden, not leaving the battle. Broken and routing units are candidates. Nearest by strict
   `<`; on a tie the earlier unit in the unit list wins. 🟡 Building pseudo-units as candidates (as for §0.1).
4. The found unit becomes the effect's target unit and the bolt is aimed at its **centre** (not its aim model). If
   nothing is found the target becomes **none** and the bolt is aimed at the **aim point** itself.

**Model-changing consequence: bolts never strike the same unit twice in a row.** With two enemies near the point
the bolts alternate between them; with one enemy A near the point, the bolts alternate between A and the nearest
other enemy within 24" of the caster, or, if there is none, between A and the bare aim point (a bolt at empty ground,
whose terminal impact hits whatever stands there — friends included).

### 1.3 Bolt flight and timing ✅ (wind-up 🟡)

Each bolt is a **beam** exactly like Lightning (`spell_effects.md` §2–§4, §3.1): start = the caster's **first model**
(first roster entry) at that moment; launch and aim height 4 (effective 8 above flat ground); scattered with the
caster's BS and step `trunc(8 × d(start, aim) / 576)` (4 draws, §2.2); flight `N = 1 + trunc(d / 20)` ticks; one
in-flight test per tick (caster's unit excluded, silent); **stops on hit**; terminal impact when `d < 40` from the
scattered destination (nothing excluded, `GMTXT 2004` per unit struck); removed without impact if it would go below
the ground. Hit: **S6 (S6 against buildings), D3 wounds, no save, damage type 0**, magical, radius 0 (§4).

Difference from Lightning: **bolts 2 … last arc upwards**: their height above the line gains +1 per tick while
`2r > N` and loses 1 per tick afterwards (the Fireball arc of §3.4, peak ≈ N/2 above the beam). Bolt 1 flies flat.
An arched bolt can pass over a ground unit whose object height is below its height mid-flight (🟡 unit object heights
are an open item of part A), and clears ridges more easily.

Schedule (all in effect steps):

| step | tick |
|---|---|
| launch, `value` rolled | T |
| wind-up | W ticks: bolt 1 is launched in the effect step of tick **T + W** |
| bolt k launched in tick `L` | first flight position (the start point) tested in tick `L + 1`; the bolt ends in tick `E` (stopped, below ground, or terminal impact) |
| flash after each bolt | 7 ticks: the next bolt is launched in tick **E + 7** |
| after the last bolt's flash (tick E_last + 7) | a short closing animation; the effect **ends in tick E_last + 8** (🟡 E_last + 9, see below) |

**Wind-up (🟡):** the wind-up is meant to last **4 ticks** (W = 4), but the original is inconsistent: in many casts it
is skipped (W = 0, bolt 1 leaves in tick T), and the closing animation lasts 1 or 2 ticks. Engine suggestion: W = 4
and a 1-tick close; keep both as named constants.

Per-bolt cycle on a clear line: `(N − 1) + 7` ticks (terminal at r = 2, see `spell_effects.md` §2.4). A full 24"
Storm with 13 bolts therefore lasts about 13 × 35 ≈ 450 ticks (≈ 2.4 turns).

### 1.4 The caster while channelling ✅ / 🟡

- **Channelling** (owns an active Storm effect) is true from tick T to the end: `IfCasting`, `IfCastingAnimation`,
  the library busy gates and `GMTXT 2014` refusals as in `spell_lasting_effects.md` §6. The AI cannot re-cast Storm
  (entry "active", §0.2) and does not pick another spell while busy.
- The caster's models are **frozen** in their pose (action requests dropped, `script_animation_sound.md` §0). 🟡 The
  freeze itself comes from the casting animation data, not from the spell; the spell's **end step** unfreezes every
  model of the caster and requests action 1 (stand) for the unit.
- The spell itself does not halt, hold or re-face the unit and does not stop its script. 🟡 Whether a moved
  channelling wizard keeps firing from its new position: yes as far as the spell is concerned (each bolt starts at the
  first model's current position, and no range/arc test is repeated), but the shipped scripts keep a busy wizard
  waiting (`IfCastingAnimation`).
- Bolts are not re-checked against range or arc after the launch.

### 1.5 End, cancellation, dispel ✅

- Natural end: after the last bolt (§1.3). End step: unfreeze, stand request, channelling ends (the owner's entry loses
  "active" if no other Storm of this caster is running).
- Cancelled (end step runs, any bolt in flight vanishes without impact) by: dispel, Ctrl+click, removal of a
  Wizard-class caster (`spell_effects.md` §1.4) and — **model-changing** — **removal from the battle of the unit
  currently recorded as the Storm's target** (the unit the latest bolt was aimed at, until the next bolt's choice
  replaces it). A bolt that destroys its target therefore usually ends the whole Storm, unless the next bolt's
  choice happens before the destroyed unit leaves the battle (dying models collapse with a delay, `game_rules.md`
  "Death kinds").
- No replacement: a second Storm by the same caster stacks (only reachable by the player; the AI refuses).
- Dispel position = the **aim point** (`spell_lasting_effects.md` §5.1). A dispel aura protecting unit P skips the
  Storm while P is its current target (P = target unit, §5.1 rule 5).
- No `GMTXT` message of its own besides the bolts' `GMTXT 2004`.

### 1.6 Test vectors (Storm)

Common: caster W (wizard, BS 10 so scatter offsets are 0, footprint radius 16) at (0,0) facing +y, its first model
at (0,0); flat ground; W is player army.

| before | action | after |
|---|---|---|
| — | launch, draws 3, 4 | value = 3 + 4 + 2 = 9 → **10 bolts** |
| — | launch, draws 0, 0 / 5, 5 | 3 bolts / 13 bolts |
| enemies A centre (0,450), B (30,400), C (0,480); aim (0,400) | bolts 1…4 | d: A 50, B 30, C 80 (inclusive). Bolt 1 → B; bolt 2 (B excluded) → A; bolt 3 → B; bolt 4 → A … C is never chosen while A and B stay |
| only enemy A (0,450) near the point; enemy D at (0,300) (100 from the point, 300 from W) | bolts 1…4 | A, D, A, D |
| only enemy A anywhere within 24" | bolts 1…4 | A; none → aim (0,400) (target cleared); A; aim point … |
| aim point (5,5) (inside W's footprint) | each bolt | step 1 skipped: nearest enemy within 576 of W (alternating as above) |
| enemy E hidden at (0,400) | bolt | E is not a candidate |
| W at (0,0); target A (footprint 20) at (0,400), no wind-up (W = 0), no hits on the way | bolt 1 | launched tick T; N = 21; positions y = 0, 20, 39 … from T+1; at T+20 y = 362, d 38 < 40 → terminal impact at (0,400): A struck (S6, D3, no save), `GMTXT 2004`; flash T+21…T+26; bolt 2 launched T+27 |
| same, value 2 (3 bolts), A the only enemy: bolt 2 excludes A and finds nothing → aimed at the aim point (0,400) = A's centre, so the geometry (and the hit on A) is the same | whole Storm | bolt ends at T+20, T+47, T+74; effect ends T+82; W channelling T…T+82 |
| bolt 1 kills A's last model; A removed at T+25 | — | A was still the recorded target → Storm cancelled at T+25: no more bolts, W unfrozen |
| enemy Talisman bearer M 60 from the aim point, M is not the target | M's aura pass | `rand mod 100` < 100 → Storm dispelled, bolt in flight vanishes, W unfrozen |

---

## 2. The Flying Bower (code 11) — flight of the caster's unit

Cost 1, range unlimited, arc ±50° (skipped in melee), point target; the aim point is clicked by the player or chosen
by the AI (`script_magic.md` §2.2).

### 2.1 Launch: the nudge ✅

After the range and arc checks pass, the aim point is **nudged**, once, at the launch (never re-checked later):

1. **Areas**: if the point lies inside any **solid, inverse-solid or BattleEdge** area (`game_rules.md`
   "Boundaries"), it is moved to the nearest allowed point (the same snap as `flight_solid_obstacles.md` §3 step 2,
   applied to each such area in turn). If it was moved at all, it is then moved **1 more unit per axis**: `+1` on an
   axis where the total displacement is ≥ 0 (also when it did not move along that axis), `−1` where it is negative.
   Then truncated to integers.
2. **Footprints**, one pass in map-object order: for each active **scenery object, building, spell area object**, and
   each **unit footprint on the caster's side** (enemy army vs everyone else; the caster's own unit excluded):
   `overlap = object footprint radius − d(point, object centre) + trunc(caster footprint radius / 2)`. If `overlap > 0`
   the point is moved **directly away from the object's centre** by `overlap` (per axis `trunc(trunc(256 × cos or sin of the
   direction) × overlap / 256)`, toward zero, with directions in 1/512 turn; a point exactly on the centre is pushed towards +y). Later objects can
   push it back into earlier ones; there is no re-check, and **enemy units never push** (a Bower can land on an enemy).

The nudged point is the effect's aim point (`spell_effects.md` §1.1) and the landing point.

### 2.2 Phases and timing ✅

| phase | ticks | what happens |
|---|---|---|
| take-off | T … T+18 (19 updates) | a harmless visual projectile runs from the origin model (the leader for a normal cast; the unit position without a posting model) to the unit's centre, fixed 18-tick flight. The unit is still on the map and fights normally. |
| lift | effect step of **T+19** | the flight projectile is created from the unit's centre to the aim point, scattered with the caster's BS and a **fixed step of 8** (offset 0…7 × 8 per axis for BS 3; 4 draws), 54-tick flight, ground-hugging (height 0 above the terrain, never stopped by terrain), passes through everything; it takes its first step at once. The unit is **lifted** (§2.3); if it was in melee it **leaves its grid and event 0x0F** (source = the caster's unit) goes to every unit of the opposite side (`spell_lasting_effects.md` §6); brace is cleared. |
| flight | T+20 … T+74 | each effect step: the unit's centre (and its map footprint) := the flight projectile's position of the previous step, then the projectile advances one step, with a random wobble of `rand mod 8` added to x and to y (2 draws per step). |
| landing | effect step of **T+74** | the unit's centre := the **aim point exactly** (fractions cleared), it is put back on the map (§2.3 ends). Facing, formation, model offsets, orders, waypoints, target and flags are **not** changed; no event is sent. |
| tail | a few ticks after T+74 | the trail particles fade (part A §1.5); then the effect ends. |

The caster is **channelling** from T to the end of the tail (`spell_lasting_effects.md` §6).

Random numbers consumed, in order: launch: 4 scatter draws (all offsets 0) for the take-off; T…T+17: 2 wobble draws
per step (`rand mod 4`); T+19: 4 scatter draws, then 2 wobble draws (`rand mod 8`) per flight step up to T+73.

### 2.3 What "lifted" means ✅ (consequences 🟡)

While lifted (end of T+19 to T+74):

- its models are **not drawn**;
- it is in the **cannot-engage** state: the contact handler ignores it as a contacting unit and as a contacted object
  (`script_queries.md` §6), so it neither starts nor joins a melee;
- **nothing else ignores it**: the unit stays active, its script runs, its map footprint exists and travels with it.
  Distance-based searches, targeting, spotting, missiles and impact tests are not told about the flight (🟡 their
  practical effect — e.g. an arrow volley hitting a Bower in mid-flight — was not run under Wine). This corrects
  `spell_lasting_effects.md` §6 ("no footprint: not found by searches, contact, collision or targeting").
- 🟡 The unit's own movement handler still runs (any active move or charge), but the effect step overwrites the
  position every tick; after landing the unit **resumes whatever order it had** (e.g. continues to its old
  destination). Not traced: the collision pass while lifted.

### 2.4 End, cancellation, dispel ✅

- Dispel position = the **current** projectile position (take-off projectile, then flight projectile, then its last
  position), so dispellers along the flight path can bring it down.
- Cancelled (dispel, Ctrl+click, removal of a Wizard-class caster):
  - **during take-off** (T … T+19 before the lift): nothing happens to the unit; no flight.
  - **during the flight**: the unit is put back on the map **where it is now** — its current centre, i.e. the
    flight position reached one step before the projectile's current position (wobble included). This corrects the
    "take-off position" of `spell_lasting_effects.md` §5.3. No re-nudge: it can come down in a river, on a unit, or
    off the edge.
  - during the tail: nothing (already landed).
- No replacement; casts stack (one unit can only fly once at a time in practice: the AI refuses while active and the
  player's second cast would fight over the position — 🟡 not traced).

### 2.5 Shift variant (🟡 developer toggle, ignore)

With Shift held at the launch the flight projectile hits **S3, 1 wound, save, damage type 0** on every unit it passes
(once per tick inside a footprint, caster's unit excluded in flight, plus a terminal impact). Normally it does no
damage at all. Same physical-keyboard caveat as `spell_effects.md` §3.9; an engine may ignore it.

### 2.6 Test vectors (Bower)

| before | action | after |
|---|---|---|
| wizard Z (footprint 16, BS 3) at (0,0), leader at (0,0), click (0,900), open ground | launch tick T | aim (0,900) unchanged; take-off T…T+18 |
| same; flight scatter draws 13, 4, 7, 3 | T+19 | flight destination (0 + 5×8, 900 − 7×8) = (40, 844); Z lifted |
| same | T+20 … T+73 | Z's centre follows the flight line towards (40,844) plus wobble, one step behind |
| same | T+74 | Z's centre = (0,900) exactly; drawn again; can engage again |
| Z in melee with enemy G at T+19 | lift | Z leaves the grid; event 0x0F (source Z) to every enemy-side unit; G's morale layer treats it as "opponent routed" |
| click (10,900) inside friendly regiment F (centre (0,900), radius 40) | nudge | overlap = 40 − 10 + 8 = 38 → point pushed east to (48,900) |
| click exactly on F's centre (0,900) | nudge | pushed towards +y: (0, 948) |
| click (10,900) inside enemy regiment E | nudge | not moved: Z lands overlapping E |
| click in a river 5 units from the bank, bank to the south (−y) | nudge | snapped to the bank point, then x + 1 (no x displacement) and y − 1 |
| enemy Talisman bearer 60 from the flight projectile at T+40 | aura pass | dispelled: Z put back at its current flight position, drawn, can engage |
| dispel at T+10 | — | Z stays where it is; no flight |

---

## 3. Sapphire Arch (code 4) — the portal

Cost 2, range 24" (576), arc ±50° (skipped in melee), point target, **never chosen by the AI** (`script_magic.md`
§2.2). The aim point is not nudged.

### 3.1 Launch and schedule ✅

- Timer 180. The portal animation uses 18 particles placed at random around the point: **54 random draws** at the
  launch (per particle: `rand mod 96` for x, `rand mod 96` for y, `rand mod 32` for height; matters for replays).
- Effect updates (timer counted down after each update; it is 180 in tick T):

| tick | step |
|---|---|
| **T+20** | **release**: every unit currently inside an arch (any caster, any side, swallowed by any earlier arch) reappears here (§3.3) |
| **T+161** | **swallow**: units near the point vanish into the arch (§3.2) |
| **T+180** | the effect ends (no end step) |

### 3.2 Swallow (tick T+161) ✅

For every **active** unit of the unit list, in list order:

- the **caster's own unit**, and any unit that carries a **transport stamp** (it was swallowed or released by an arch
  earlier and has not lost the stamp since): the stamp is **erased** and the unit is skipped (not swallowed);
- otherwise, if `d(unit centre, aim point) ≤ 48` (inclusive, truncated): the unit is **swallowed**:
  - if it is the player's selected unit it is deselected (UI);
  - it is moved to `(−r, −r)` where r = its footprint radius (just outside the map's corner), fractions cleared;
  - it enters the **in-an-arch** state (models not drawn, banner not drawn, cannot engage — the same lifted state
    as the Bower, §2.3, plus "in an arch");
  - it receives a **transport stamp**: the battle clock at this moment (turn, segment, tick counter of the segment)
    and its **offset** = its centre − this arch's aim point (|offset| ≤ 48 per the test).

No side, state or class test: friends, enemies, hidden, broken, routing and units in melee are all swallowed (🟡 a unit
in melee keeps its grid membership: nothing removes it from the grid; consequences not traced). 🟡 Building
pseudo-units (as for §0.1).

**What "vanished" means** (✅ code reading, consequences 🟡): the unit stays an **active unit** of its side. Only
drawing, the banner and engagement (contact) ignore it. Its **script keeps running**, it can receive and send events,
it keeps its target, it **counts as present** for every objective that counts units (it is neither removed nor
dead; an "eliminate the enemy" objective is not met while an enemy unit is in an arch), and an area objective sees it
at `(−r,−r)`, i.e. outside every area. Whole-field searches (e.g. `AttackNearestEnemy`) can pick it and send a unit
walking to the corner, where it can never engage. 🟡 If its script moves it, it walks invisibly from the corner (and
the boundary correction pushes it onto the map); a routing unit there runs its flight logic from the corner (fled
removal not traced). Nothing in the arch rules ends this state except a later arch's release.

### 3.3 Release (tick T+20 of any later arch) ✅

For every active unit in the in-an-arch state, in unit-list order:

1. it is placed at **this arch's aim point + its stored offset** (fractions cleared; facing, formation, orders and
   flags otherwise unchanged; **no checks** for map edges, solid areas or other units — several released units can
   overlap);
2. it leaves the in-an-arch state (drawn again, can engage again);
3. **expiry test**: with `M(clock) = 18 × (10 × turn − segment) − tick counter` (the battle clock of `game_rules.md`:
   segments count 10 → 1, the tick counter of a segment 18 → 0), the unit is **killed** if
   `M(now) − M(stamp) > 900`. M advances by 1 on every tick **except segment-boundary ticks**, so the limit is
   **900 ticks not counting boundary ticks ≈ 950 ticks = 50 segments = 5 turns** (not "900 ticks").
   Killed = every model of the unit gets lethal wounds at once, **no kill credit** (cleared), death kind **2**
   (slain outright, 1-tick collapse) — at the **new** arch's position. Bookkeeping: `casualty_bookkeeping.md` §2
   (Sapphire Arch row: `s_calualties` +1 per model).
4. The stamp is **kept**. Consequence: a unit released by an arch is **never swallowed by that same arch** 141 ticks
   later (its stamp is erased instead), and it can be swallowed again only by a later arch.

**Stamp-erasure quirk (✅, model-changing for long battles):** a unit still inside an arch when another arch performs
its swallow step loses its stamp (first bullet of §3.2). Its expiry is then measured from the **battle start**
(`M(stamp) = 0`): released after `M(now) > 900` (about 5 turns into the battle) it is killed however short its
stay was; released earlier it survives however long its stay was.

**At the end of the battle** units still in an arch are just active, undamaged units (🟡 no end-of-battle pass treats
them specially): they count as present/surviving for the final objective evaluation and the debrief.

### 3.4 Dispel, cancel ✅

Dispel position = the **aim point**. A dispel or Ctrl+click cancel simply ends the effect (no end step): cancelled
before T+20 → no release; before T+161 → no swallow. Units already in an arch stay there. Removal of a Wizard-class
caster cancels it the same way. No replacement; several arches can run at once and each releases everyone.

### 3.5 Test vectors (Arch)

Common: player wizard W at (100,100); battle clock as `game_rules.md`.

| before | action | after |
|---|---|---|
| Arch A cast at tick 0 at (500,500); P centre (530,530), Q (534,534), R (535,535), all footprint 40 | tick 161 | P (d 42) and Q (d 48) swallowed; R (d 49) stays. P at (−40,−40), offset (30,30) |
| W itself within 48 of the point | tick 161 | W never swallowed by its own arch |
| P swallowed at turn 3, segment 7, counter 10 (M = 404); Arch B cast at (900,200) | B's release at turn 8, segment 7, counter 10 (950 ticks later, M = 1304) | P placed at (930,230); ΔM = 900 → **survives** |
| same, release one tick later (counter 9) | release | ΔM = 901 → P placed at (930,230) and **all its models killed**, no credit, death kind 2 |
| P released by B at tick X (stamp kept) and still within 48 of B's point | B's swallow at X+141 | P's stamp erased, **not** swallowed |
| P swallowed by A; Arch C cast (and its swallow step runs) while P is still away; release by a later arch D at turn 4 | D's release | P lost its stamp at C's swallow: M(now) = 18 × (40 − s) − c ≤ 900 → survives |
| same, release from turn 6, segment 9 (its second tick) on | D's release | M(now) > 900 → killed (turn 6 segment 10: M = 900 − counter ≤ 900 → survives) |
| Arch A dispelled at tick 100 | — | no swallow; units released at tick 20 stay released |
| enemy unit E in an arch; every other enemy destroyed | objective "eliminate the enemy" | not met while E is in the arch |

---

## 4. The Curse of Anraheir (code 14) — halved movement and Initiative

Cost 3, range 24" (576), arc ±50° (skipped in melee), unit target.

### 4.1 Launch ✅

1. The target = the **unit under the point** (`spell_lasting_effects.md` §0.1: any side, any state, reference figure
   within `max(footprint, 48)`, nearest). None → the launch **fails** (power lost, `GMTXT 2021` for player-army
   casters) and nothing else happens (the caster's previous Curse is **kept**).
2. The caster's previous Curse effect(s) are **cancelled** (`spell_effects.md` §1.4), running their end step (their
   targets' values restored, §4.4) — before anything is read from the new target.
3. The target's current **speed stat `s_rlmv`** and **Initiative I** are saved in the effect, then halved:
   `s_rlmv := floor(s_rlmv / 2)`, `I := floor(I / 2)`. Nothing else changes (M, the stat lines, T, A are untouched;
   `s_rlmv` is not recomputed from M and I, it is halved separately).
4. A spirit per target model follows that figure at ground level. Appearance frames 229–260 play on T…T+3;
   at **T+4**, each remaining spirit draws **one random number**, in model order, to choose its starting
   phase in the loop at frames 261–292. Both stages are directional. Exact timing, placement and cleanup:
   `spell_attached_visuals.md` §3.

Consequences: half movement, charge and flight speed (everything derived from `s_rlmv`); half Initiative for the
strike segment (`game_rules.md` §5.1): **I 1 becomes 0, and a unit with I 0 makes no close-combat attacks at all**
(no segment is 0); I 3 → 1, I 4 → 2.

### 4.2 Every update ✅

From tick T on, every effect step:

- if the target's **`s_mount` ≠ 0** (Warhorse, War Boar, Giant Wolf, Cave Squig — the unit's own stat line) **and the
  current segment is 10**, the target takes a **Leadership (panic) test at modifier 0** (`game_rules.md` §7 "The
  Leadership test": pass iff `rand mod 11 + 2 ≤ effective Ld`, +1 Ld with the "fight harder" state);
- on a **failure** the target receives the rout event 0x0C (as every failed panic test) **and the Curse ends in the
  same effect step** (end step §4.4).

Segment 10 is the first segment of every turn: **19 ticks**, so a mounted target takes **19 tests per turn**, one per
tick, and none in the other 171 ticks. (The battle's very first segment is segment 1, so the first window opens at
the start of turn 1.) There is no state test: a target that is already broken or routing is tested too, and a
failure sends it 0x0C again and ends the Curse (🟡 what 0x0C does to a unit already routing is its script's business).

### 4.3 No other end ✅

There is **no timer**. The Curse ends only by:

| cause | |
|---|---|
| failed mounted test | §4.2 |
| dispel | position = the **aim point** where it was cast (not the unit's current position); the target's own auras never dispel it (target = P) |
| Ctrl+click | the owner's Curses |
| a new Curse by the **same caster** (successful target found) | §4.1 step 2 — on any target, including the same unit |
| removal of a **Wizard-class** caster, or removal of the **target** | `spell_effects.md` §1.4 |

Unmounted targets therefore stay cursed for the rest of the battle unless one of these happens. This settles
`game_rules.md` R52 for the Curse (code reading; a Wine check is still welcome).

### 4.4 End step ✅

`s_rlmv := saved s_rlmv`, `I := saved I` — written back unconditionally, overwriting anything that changed them in
between (another Curse, Ere We Go). No event, no message, no reform.

### 4.5 Test vectors (Curse)

| before | action | after |
|---|---|---|
| E: I 4, `s_rlmv` 9, T 3, unmounted | Curse on E (tick 0) | I 2, `s_rlmv` 4; saved (4, 9) |
| E: I 1, `s_rlmv` 7 | Curse | I 0 → E makes **no** close-combat attacks; `s_rlmv` 3 |
| E cursed by W (saved (4, 9)) | W curses F (I 3, `s_rlmv` 8) | E back to (4, 9) first; F: I 1, `s_rlmv` 4 |
| E cursed by W | W curses E again | restored to (4, 9), then halved again → (2, 4); not cumulative |
| E cursed by W | W's new Curse aimed at empty ground (no unit under the point) | fails: E stays cursed |
| E cursed by W1 (saved (4, 9) → (2, 4)) then by W2 (saved (2, 4) → (1, 2)) | W1's Curse dispelled | E (4, 9) although W2's is still active |
| same | then W2's ends | E (2, 4) **for the rest of the battle** |
| E: T 3, I 4. Curse (saved I 4 → 2), then Ere We Go (saved I 2; T 4, I 20) | Curse dispelled | I := 4 (E now **strikes** although Ere We Go is active), T 4 |
| same | Ere We Go ends | T 3, I := 2 permanently |
| mounted E (`s_mount` 1, Ld 7) cursed; segment 5 | any tick | no test |
| same, segment 10, draws 4, 9 | two ticks | 4 mod 11 + 2 = 6 ≤ 7 pass; 9 mod 11 + 2 = 11 > 7 **fail** → 0x0C to E, Curse ends, I and `s_rlmv` restored in that tick |
| mounted E already routing, cursed | segment 10, a failed test | 0x0C again, Curse ends |
| Talisman bearer's own unit cursed | its aura passes | never dispelled (target = protected unit) |
| Curse cast at (300,300) on E; E walks 400 away; enemy Dispel Magic wizard 50 from (300,300) | dispel pass succeeds | Curse dispelled (measured from the cast point) |

---

## 5. Implementer's model (summary)

| spell | effect fields | lifetime | end step |
|---|---|---|---|
| Storm | value (bolts left), target (previous bolt's target), phase, projectile | until value + 1 bolts and their flashes are done | unfreeze + stand; channelling ends |
| Bower | aim (nudged), phase (take-off/flight/tail), projectile | T … T+74 + tail | if in flight: put back on the map at the current position |
| Arch | aim, timer 180 | T … T+180 | none; releases at T+20, swallows at T+161 |
| Curse | target, saved (`s_rlmv`, I) | until a failed mounted test or a cancellation | restore saved values |

Engine state needed beyond the effect list: per unit, **lifted** (Bower, Arch), **in an arch**, the **transport
stamp** (clock value + offset, erasable), and "channelling" as the query "owns an active Storm or Bower".

## Corrections to public notes

1. `game_rules.md` "Spells", Storm of Shemtek row: "at the nearest enemy near the point" → nearest hostile, not
   hidden, not leaving, centre within **80** (inclusive) of the aim point **excluding the previous bolt's target**;
   otherwise the nearest such unit within 24" of the caster; otherwise the bare aim point. Each bolt is a scattered
   Lightning-type beam (bolts 2+ arc), 7-tick gap between bolts; the Storm is cancelled when its current target is
   removed from the battle (§1).
2. `game_rules.md` "Spells", Sapphire Arch row: "killed if gone more than 900 ticks" → more than 900 non-boundary
   ticks (≈ 950 ticks, 50 segments), measured from a stamp that a later arch's swallow step can erase (then from the
   battle start); "every other unit within 48 units" → every active unit with its centre within 48 (inclusive)
   except the caster's own and except units carrying a stamp; "vanishes" → still an active unit (script running,
   counted for objectives), only not drawn and unable to engage; released units keep their offset, no placement
   checks, no re-swallow by the same arch (§3).
3. `game_rules.md` "Spells", Flying Bower row: add the nudge (§2.1), the 19-tick take-off, 55 ticks lifted, landing
   exactly on the nudged point without facing/formation change, and that it can be dispelled along its path (§2).
4. `game_rules.md` "Spells", Curse row: halving is `floor` on `s_rlmv` and I (I 1 → 0 = no attacks); "mounted
   targets take a panic test each tick of segment 10" = 19 tests per turn, on `s_mount ≠ 0`; "the curse ends when one
   routs" → ends when a **test fails** (even if already routing); no other end — the 🟡 can be dropped (R52).
5. `spell_lasting_effects.md` §5.3 Flying Bower row: a mid-flight cancel puts the unit back **at its current flight
   position**, not at the take-off position; a take-off-phase cancel does nothing.
6. `spell_lasting_effects.md` §6: "no footprint: not found by searches, contact, collision or targeting" → only
   **drawing** and **engagement/contact** ignore a lifted unit; its footprint moves with it and other searches do not
   exclude it (§2.3). Also add: the same lifted state is held by units inside a Sapphire Arch (§3.2).
7. `game_rules.md` R70 / `script_queries.md` §6 ("🟡 other writers not searched"): the cannot-engage state has
   exactly two sources, the Flying Bower flight and the Sapphire Arch.
8. `spell_effects.md` §1.4 table: add the Storm consequence of "target unit removed" (the Storm's target is its
   latest bolt's target).

## Open items

- 🟡 Storm wind-up/closing durations (original defect, §1.3) — choose a constant.
- 🟡 Source of the Storm caster's model freeze (casting animation data) and whether a player can move a channelling
  wizard.
- 🟡 Unit object heights vs arched Storm bolts (part A open item).
- 🟡 Swallowed units: melee grid membership, scripted movement from the corner, routing units in an arch, buildings.
- 🟡 Bower: missiles and impacts on a unit in flight; the collision pass while lifted; orders resumed after landing;
  landing overlapping an enemy (contact on the next collision).
- 🟡 Arch swallowing a Bower in flight: the unit stays "in an arch" after landing (the landing clears only the lifted
  state) and is never released by a later arch (release needs both states). Edge case, not run.
- 🟡 Event 0x0C from the Curse test to a unit that is already routing.
