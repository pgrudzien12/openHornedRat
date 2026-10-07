# Lasting spell effects, unit-state spells, dispel and the winds of magic

Issue #168, part B. Status markers: ✅ established, 🟡 hypothesis, ⬜ unresolved. Companion: `notes/spell_effects.md`
(part A: the active-effect list, the magical hit, the bolt/beam spells).

Part A (`notes/spell_effects.md`) holds the effect framework (what an active effect holds and why it is kept, removal
on caster death) and the magical hit. Read first, do not re-derive:
`game_rules.md` §8 "Winds of magic and casting", "Spells", "Dispel and anti-magic", "Magic items in battle", "Death
kinds"; `script_magic.md` §0 (shared state), §0.4 (launch interface), §2.2/§2.3 (AI choice);
`script_animation_sound.md` §3 (`IfCasting`, `IfCastingAnimation`); `script_queries.md` §9 (`Query 22`);
`casualty_bookkeeping.md` §2 (kill credit).

Conventions: distances in battle units (24 = 1"), Euclidean and **truncated** to an integer unless stated. "Tick T" =
the tick in which the effect is launched (by `CastPending` in the unit-script phase). Within a tick the effect
update runs **after** all units' scripts, movement and close combat, so an effect gets its first update in tick T
itself. An **active effect** has: owner (caster unit), spell code, target unit (if any), aim point (the launch
point), a timer and a phase (part A). "Reference figure" of a unit = its leader, or (no leader) a fixed front figure
(🟡 as in `script_magic.md` §3.3).

## 0. Two shared helpers

### 0.1 "The unit under the point" (Azure Blades, Ere We Go, Mork Save Uz, Madness, Hunting Spear, Curse)

Among the units on the battle's unit list that are **active** (not removed), regardless of **side, hidden, broken,
routing or class**:

- d = trunc(distance from the point to the unit's **reference figure**);
- the unit qualifies if `d < max(its footprint radius, 48)` (strict);
- the qualifying unit with the **smallest d** is taken (strict `<`: on a tie the earlier unit in the unit list wins).

Only after this choice does Madness test "hostile" and "not already maddened" (§1.1): a friendly unit nearer the
point than the intended enemy makes the cast **fail**; the spell does not look for the next candidate.

### 0.2 Spell-entry states (the "magic panel" without a panel)

Each spell entry of a unit's spell list carries three independent yes/no states that matter:

| state | set by | cleared by | gameplay effect |
|---|---|---|---|
| **selected** | the player clicking the spell's button; the launch of **Dispel Magic** | the target click of a targeted spell (and cancelling its targeting) — **never for Dispel Magic** (§5.4) | the player's button is **unusable** while selected; the AI's Dispel rule rejects a selected Dispel entry |
| **cast ordered** | the target click (and the no-target click of Azure Blades / Fists of Gork) | a successful launch; a failed launch; `DropPendingSpell`; `IfCasting R=1` on refusal | **none** (only how the button is drawn) |
| **active** | a successful launch of any spell but Dispel Magic | the end/cancel of the **last** active effect of that spell owned by the unit; also briefly by a Mork Save Uz dispel (§5.3) | the AI chooser skips an entry with an active effect (`script_magic.md` §2.2 rule 2); Ctrl+click on an active entry cancels the owner's effects of that spell |

Button usable = **not selected and cost ≤ the side's pool**. "Cast ordered" never makes a button unusable.

## 1. Madness (code 25)

### 1.1 Launch

Range 24" (576), launch arc ±50° (skipped in melee), cost 2 (`game_rules.md`). Aim point = the click (player) or
the target's reference figure (AI). Then:

1. The unit under the point (§0.1). **Fail** if none, if it already is the target of an active Madness effect
   ("maddened" — this is the state the AI chooser reads, §1.4), or if it is **not hostile** to the caster
   (hostile = one of the two is player-army or allied and the other is enemy-army; neutral/furniture is never
   hostile). Failure: as every launch failure (power lost; `GMTXT 2021` for player-army casters).
2. Success, all in the same tick T:
   - the effect is created with target = that unit, timer **180**; a particle sits above the unit and follows it;
   - **event 0x31** ("you are maddened", no source unit, no parameters) is queued to the target (not queued if the
     target is a building pseudo-unit 🟡);
   - the target's **side is saved** (the whole side value, including its low bits) and then swapped:
     **player army or allied → enemy army; enemy army → allied side** (not the player's army, so the player never
     gains command of it); a neutral/furniture side is unchanged (cannot happen, step 1 rejects it);
   - the target leaves the "under the player's direct command" state (🟡 the state a player-army unit enters when
     the player issues it an order; it only drives which order panel is shown);
   - if the target is the player's currently selected unit the panel is refreshed (UI only);
   - the caster stops being hidden (true of every successful launch, part A).
3. Nothing else changes at launch: no grid/melee change, target, threat, movement and stats are untouched.

### 1.2 What the maddened unit does (scripts)

All four library morale layers handle event 0x31 the same way (153 → script 167 infantry/default, 154 and 156 →
128 artillery and shooters, 155 → 149 wizards):

```
SendEventToOwnSide 22      # own side = the NEW side: its former enemies are told it "left" them
LeaveSharedGrid            # it leaves any close-combat grid
Yield
SetUnitFlags2 64           # the scripted "maddened" behaviour flag (below)
loop every 10 ticks:
    if not held (Tangling Thorn) [128: and not an anchored war machine]: AttackNearestEnemy
    while the maddened flag is set
Restart
```

- Event 0x16 to its new side runs `Query 22` in every unit of that side (`script_queries.md` §9): a unit that had it
  as current target drops it (out of melee → event 0x19, rally/re-form; in melee → switch to another hostile
  opponent on its grid or leave the grid).
- `AttackNearestEnemy` uses the new side, so it attacks its **former friends**.
- Its **old friends are not told anything**; they now see a hostile unit and react through their normal threat and
  targeting rules.
- A mission handler that does not pass event 0x31 to the library layers leaves the unit on its old script (side
  still swapped). All shipped handlers fall through to the library 🟡 (no mission script catches 0x31 itself).
- The maddened flag set by the script is **not** what "maddened" means for the AI and for re-casting; those test for
  an active Madness effect on the unit (§1.4).

### 1.3 End

Each effect update: timer > 0 → timer − 1 (and the particle follows the unit). The update that finds the timer at 0
(tick **T+180**) ends the effect. End (also reached by dispel, Ctrl+click cancel, recast replacement does not apply,
or part A's removal on caster/target removal):

- the scripted maddened flag is cleared (so the 10-tick loop exits at its next test);
- the **saved side is written back** (whatever the side is at that moment — a `SetSide` during the madness is
  overwritten);
- **event 0x32** is queued to the unit → library 152 → script 168: `SendEventToOwnSide 22` (now its original side,
  which may have targeted it meanwhile), `LeaveSharedGrid`, `Yield`, `GotoScript 163` (rally, wait while re-forming,
  re-form to script ranks, `Restart`).

The "under direct command" state is **not** restored (the player has to order the unit again).

Edge cases:

| case | behaviour |
|---|---|
| target in melee at launch | stays on the grid until its script runs `LeaveSharedGrid` (its next script step); its opponents, now on its side, drop it via `Query 22` |
| target broken/routing | allowed (no test); whether its flight script accepts the switch to 167/149/128 depends on its switch-refusal state 🟡 |
| caster removed | per part A the caster's effects are cancelled through the end step → side restored, 0x32 sent. 🟡 part A: this removal applies only to Wizard-class casters (a monster-mounted shaman's Madness would run to its timer) |
| target removed | per part A effects on a removed unit are cancelled (end step on a dead unit; harmless) |
| a second Madness on it | fails (already maddened), whichever side casts it |
| dispel | normal dispel rules (§5); the effect position is the **aim point** (where it was cast), not the unit's current position |

### 1.4 "maddened(unit)" for the engine

`maddened(U)` = some active Madness effect has target U. It is what the AI rule "target not already maddened" and the
launch check read. Today's engine stub (always false) should become this query.

## 2. Skitterleap (code 23)

- Range unlimited; the launch **arc applies** (±50° of facing from the caster's centre to the aim point), skipped
  only while the caster is in melee. Aim point = the click, or the AI's escape point (`script_magic.md` §2.2).
- Launch: the effect's target = the caster's own unit; a 4-frame vanishing particle is started on **every model**
  of the caster. No timer, no movement order, no halt.
- Updates: each tick every model's particle advances one frame; the effect is done when the particles have run out:
  launch tick T → frames on T, T+1, T+2, T+3 → done on the update of **tick T+4**.
- On that update the caster is **placed at the aim point**: its centre := the point exactly (fractions cleared), its
  map footprint moves with it. **Facing, formation, models' offsets, waypoints/destination, target, melee/grid
  membership and all flags are untouched** — no event is sent. 🟡 a unit teleported out of melee is still a grid
  member until the normal melee rules drop it (not traced).
- **No destination checks** at all: not the map edge, not impassable ground, not other units. (The player can only
  click on the map; the AI point can be off the map 🟡 — later edge correction only runs for moving units.)
- **Dispel or cancel before tick T+4 → no teleport** (the effect has no end step for this spell). The effect's
  position for dispel is the aim point (the **destination**), so a dispeller within 80 of the landing point can
  stop the leap.

**AI consequence (model-changing):** the AI picks Skitterleap when the target is closer than its threat range and
aims at a point *directly away* from the target (`script_magic.md` §2.2). Library 134 tests range/arc against the
**target** (in front), turns towards it if needed, and `CastPending` then launches at the point behind the wizard:
the launch arc fails (the point is ~180° off the facing) and the paid power is lost. **The AI Skitterleap only
succeeds while the wizard is in melee** (arc skipped), i.e. it is an escape-from-melee spell in practice.

## 3. Ere We Go! (code 18) and Mork Save Uz! (code 21)

Shared launch (Azure Blades too): the unit under the point (§0.1, **any side**); none → fail. Timer **180**; a
particle on every model of the target, following it. Range Ere We Go 36" (864), Mork Save Uz 24" (576); arc ±50°.

| | Ere We Go | Mork Save Uz |
|---|---|---|
| at launch | target **T := T + 1**; its current I is **saved**; **I := 20** | nothing on the unit |
| every update while active | timer − 1 | a dispel pass around the target (§5), then timer − 1 |
| ends | the update finding timer 0 (tick T+180) | same |
| end step | **T := T − 1**; **I := the saved value** | nothing |

- The effect is applied in tick T; close combat runs before effects in a tick, so the unit fights with I = 20 in
  ticks T+1 … T+180 (180 ticks) and is restored at the end of tick T+180. I = 20 means it makes **no close-combat
  attacks** (`game_rules.md` §5.1).
- **Stacking**: the restore is "decrement T, write back the saved I", so overlapping effects misbehave:

| before | action | after |
|---|---|---|
| T 4, I 3 | Ere We Go #1 (tick 0) | T 5, I 20 (saved 3) |
| T 5, I 20 | Ere We Go #2 (tick 50) | T 6, I 20 (saved 20) |
| T 6, I 20 | #1 ends (tick 180) | T 5, **I 3** |
| T 5, I 3 | #2 ends (tick 230) | T 4, **I 20 for the rest of the battle** |
| T 4, I 3 | Ere We Go (tick 0), Curse of Anraheir (tick 10: saves I 20, halves to 10) | T 5, I 10 |
| T 5, I 10 | Ere We Go ends (tick 180) | T 4, I 3 |
| T 4, I 3 | Curse ends (dispel, tick 300) | I := **20** (permanent) |

  The AI cannot stack its own (entry "active"), but two different casters, or AI + player, can.
- The target may be **hostile**: a player can cast Ere We Go on an enemy regiment to stop it striking for 180 ticks
  (it also gets T + 1). Mork Save Uz can likewise be put on any unit.
- AI aim: the chooser aims at a friend's **unit centre** (`script_magic.md` §2.2), but the launch takes the unit
  whose **reference figure** is nearest that point (§0.1); when the friend is locked in melee the enemy's leader can
  be the nearer figure, and the spell then lands on the enemy 🟡 (geometry-dependent).
- 🟡 T is not capped: a T 10 unit becomes T 11, beyond the to-wound chart's last column (behaviour of the chart
  lookup then undefined; never in shipped data).

The Mork Save Uz aura is centred on the **target unit's current centre** (it moves with the unit) — see §5.

## 4. Fists of Gork (code 20)

- Player: no target click; the aim point is the **caster's own centre** at the click. AI: the aim point is the
  current target's reference figure (aim-at-point off). Range unlimited; arc ±50° (the player's own-centre point
  always passes; skipped in melee). Timer **180**. The point is **fixed** for the whole effect — it does not follow
  the caster or the target.
- Every update: timer 0 → end (and the caster's models are told to return to their standing action). Otherwise, if
  `timer mod 4 = 0` (timer values 180, 176, …, 4 → **45 strikes**, on ticks T, T+4, …, T+176), one strike, then
  timer − 1.
- **Strike victim**: the nearest unit whose **centre** is within **16** of the aim point (`trunc(d) ≤ 16`,
  inclusive; nearest by strict `<`, ties to the earlier unit). Candidates: active units of **any side** (friends
  included), **excluding the caster's own unit**, hidden units and units leaving the battle; broken/routing units
  are candidates. 🟡 building pseudo-units may qualify. None → nothing happens.
- **Strike**: roll D6 (`r`). If `r ≥` to-wound(S6, victim unit's T) — S6 row: T 0–4 → 2, T5 → 3, T6 → 4, T7 → 5,
  T8–9 → 6, T10 → impossible — then repeat: give **1 wound to a uniformly random model** of the victim (its current
  models; the same model can be picked again); if `r ≠ 6` stop; else roll a new `r` and continue **only on another
  6**. So: no wound on a failed roll; exactly 1 wound on a success of 2–5; on a first 6, 1 + (number of further
  consecutive 6s) wounds.
- Wounds are added **directly**: no armour save, no `MagicResistent` check, no message, no panic, no kill credit
  written and no death kind written. A model whose wounds reach its W dies through the normal "wounds reached W" path
  in its next model update, with its stored death kind (ordinary for a fresh model, staggered collapse delay) and
  whatever kill credit it already carried (`casualty_bookkeeping.md` §2.1: usually none → the caster gets **no
  kill/experience**). A pick of a model already at W wastes the wound 🟡.
- Random-number order per strike: D6; then per wound: model pick, then (only after a 6) the next D6.
- **Practical effect**: a player-cast Fists aims at the caster's own centre and excludes the caster's unit, so it
  only hurts a unit whose centre comes within 16 of that spot — rare. The AI version aims at the enemy's leader,
  which is usually within 16 of the enemy's own centre only for shallow formations 🟡. Model it as specified; do
  not "fix" it.

## 5. Dispel: auras, schedule and what a dispel undoes

### 5.1 One dispel pass (shared by all sources)

A pass has a **protected unit** P, a chance c %, and optionally an owning effect (Dispel Magic / Mork Save Uz). For
each effect slot in list order, if the effect is

1. active, 2. **not innate**, 3. **not a Dispel Magic** (Mork Save Uz effects *are* dispellable),
4. **not launched with the "undispellable" marker** (spell code + 512; only shipped use: BF035's scripted Skitterleap
   `535`, `script_magic.md` §3.1), 5. **not owned by P** and **not targeted at P**,

then roll `rand % 100 < c` (**rolled for every such effect anywhere on the map**, before the distance test — this
consumes random numbers even when nothing is near), and if it succeeds and `trunc(distance(effect position, P's
current centre)) < 80`, the effect is **dispelled**:

- it is cancelled through its end step (below), its projectile/particles/area object removed (part A);
- battle message **`GMTXT 2006`** "<spell> has been dispelled by <P's name>" is shown to the player, whatever the
  sides involved (one message per dispelled effect).

Effect position: the projectile's **current** position for the projectile spells (Wind Blast, Lightning, Piercing
Bolts, Burning Head, Fireball, Flying Bower, Gaze of Mork, Warp Lightning, Pestilent Breath, warpfire and the two
item bolts); the **aim point** (launch point) for every other spell, including unit-target ones (Madness, Ere We Go,
Curse, Azure Blades, Mork Save Uz, Hunting Spear's record) and Skitterleap (its destination).

There is **no side test**.

### 5.2 Sources and schedules

Order inside the effect update of a tick: (a) item auras, unit list order, one pass per qualifying item; (b) Dispel
Magic and Mork Save Uz passes, effect list order; (c) every effect's own update. Nothing of (a)/(b) runs in a tick
in which no effect is active.

| source | P | c | schedule | lifetime |
|---|---|---|---|---|
| Dispel Magic | the **caster's** unit (current centre) | 50 | timer starts 180 at launch; pass when `timer mod 3 = 0` → ticks T, T+3, …, T+177 (**60 passes**); timer − 1 every tick without a successful pass | ends on the update finding timer 0 (T+180), **or immediately after the first pass that dispelled ≥ 1 effect** (several may go in that one pass) |
| Mork Save Uz | the **target** unit (current centre) | 50 | every update, ticks T … T+180 (**181 passes**) | 180-tick timer (§3); a successful pass does not end it |
| Banner of Arcane Protection | the bearer's unit | 50 | every tick | whole battle |
| Talisman of Obsidian | the bearer's unit | 100 | every tick | whole battle |

- 🟡 item auras do not check that the bearer's unit is still alive (a destroyed unit would keep projecting the aura
  at its last position if its item list survives; not confirmed).
- Exemption by P: a wizard's Dispel never removes its own spells nor a Curse/Madness/Ere We Go **on its own unit**;
  a Mork Save Uz exempts effects owned by or aimed at **its target**, but **not** the shaman's own other spells
  (e.g. the shaman's Gaze of Mork beam passing within 80 of the protected unit is dispelled on 50 %).

### 5.3 What a dispelled (or cancelled) effect undoes

| spell | end step |
|---|---|
| Madness | side restored, scripted maddened flag cleared, event 0x32 (§1.3) |
| Ere We Go | T − 1, I := saved (§3) |
| Curse of Anraheir | movement rate and I := the values saved at its launch |
| Tangling Thorn | every unit whose centre is within 64 of the thorn's point is released, whatever held it (`notes/spell_area_effects.md` §3.4) |
| Storm of Shemtek | caster's models unfrozen, told to stand; caster no longer channelling |
| Flying Bower | mid-flight: the unit is put down at its **current flight position**; during take-off: nothing (`notes/spell_channelled_effects.md` §2.4) |
| Skitterleap | nothing — the teleport simply never happens |
| Fists of Gork, Mork Save Uz, Azure Blades, projectiles | nothing beyond removal (Fists: no "return to stand") |
| any | the owner's entry loses "active" if this was its last effect of that spell |

Mork Save Uz quirk: when its pass dispels something, its **own** entry's "active" state is cleared although the
aura keeps running — the AI may then cast a second Mork Save Uz, and Ctrl+click no longer cancels it.

### 5.4 Dispel Magic: once per battle (model-changing)

- Clicking Dispel Magic (player) and launching it (any caster) put the Dispel entry in the **selected** state, and
  nothing ever clears it for Dispel Magic. So **each wizard can cast Dispel Magic once per battle**: afterwards the
  player's button stays unusable and the AI's Dispel rule rejects the entry. (This also holds after a *failed*
  player order: the click alone selects it.)
- No message, sound or event marks the Dispel's own end.

### 5.5 The AI's Dispel rule restated

Choose Dispel Magic (aim = own centre, aim at point) iff the cost fits the pool **and**:
1. the Dispel entry is not selected (= this wizard has not cast Dispel Magic this battle, §5.4);
2. the wizard owns no active Dispel Magic effect;
3. take the **first** active effect in list order whose **owner is hostile** to the wizard (current sides) and which
   is not a Dispel Magic; its owner must be **not hidden** and **able to see** the wizard (standard view cone).
   Only that first effect is examined. It may be one Dispel cannot touch (innate — Doomwheel, Dragon breath,
   warpfire —, undispellable, aimed at the wizard's own unit) or one far beyond 80 units: the rule does not check.

## 6. Channelling and the Flying Bower flight (script-observable part only)

Already public (`script_animation_sound.md` §3, `script_grid_events.md`): **channelling** = the unit owns an active
Storm of Shemtek or Flying Bower effect; `IfCastingAnimation` and (Wizard class only) `IfCasting` are true while
channelling, and the busy gates of `FearWhenCharged` and `EnemyRouted` (and library 103/155 `IfCasting 0 0`
wrappers) then ignore charges, threats and routs. Additions:

- During the Flying Bower flight the caster's unit is **lifted**: it is not drawn and cannot engage or be engaged,
  but its footprint moves with it and other searches, missiles and targeting still find it (`notes/spell_channelled_effects.md` §2.3). Units
  inside a Sapphire Arch are in the same lifted state.
- If the caster was **in melee** when the flight starts, it leaves its grid and **event 0x0F** (source = the
  caster's unit) is sent to every unit of the opposite side, which the morale layers treat like "an opponent routed"
  (`EnemyRouted`, `game_rules.md` "Opcode 0x53"). Brace is cleared.
- The engine's `channelling` flag should be the query "owns an active Storm/Bower effect", not a stored bool.

## 7. The 50-second wind

- **Clock**: its own millisecond clock, started at 0 when the battle window opens, advanced after every tick by the
  real elapsed time **only while the battle is not paused**. Not the tick counter: with frame lag fewer ticks fit in
  50 s. At the nominal 10 ticks/s, 50 s ≈ 500 ticks.
- **Check**: at the start of each 100-ms timer step (before that tick's battle update), if ≥ 1000 ms of the clock
  have passed since the previous check. A check fires a wind when `clock − 50000 × floor(last_wind / 50000) ≥ 50000`
  (`last_wind` starts at 0), then `last_wind := clock`. So winds fall at the **first check at or after each
  multiple of 50 s** (≤ ~1 s late, no drift). Tick-exact engine rule at 100 ms/tick: checks at the start of ticks
  11, 21, 31, …; winds at the start of ticks **501, 1001, 1501, …** (counting the first tick as 1).
- **Both pools at once**, player first: player := Wind(player); then the re-arm (below); then enemy := Wind(enemy).
- **Wind(cur)**, with `R` = a fresh uniform random integer:

```
if cur == 0:        new = R mod 8            (0..7)
elif cur < 4:       new = cur + R mod 4      (cur..cur+3)
else:               new = cur - 4 + R mod 8  (cur-4..cur+3)
pool = clamp(new, 1, 8)
```

  So 0 → 1 (2/8) or 2..7 (1/8 each); 1–3 never drop; 8 → 4..7 (1/8 each) or 8 (4/8); never 0 after a wind.
- **Initial pools**: player := 1 + R mod 8, then enemy := 1 + R mod 8, when the battle window is created (before any
  script runs). The engine's "rolled 1..8 at first use" gives the same distribution but a different random-number
  order (matters only for replays).
- **Magic-item re-arm** on each wind: for **every unit of both sides**, each re-usable activated item (Banner of
  Wrath, Grudgebringer) loses its "used" state.
- Debug modes (Count/Fixed) as in `game_rules.md`; not reachable without debug key combinations.

## 8. Panel side effects as engine state

| path | observable state change |
|---|---|
| `IfCasting 1 1` true (busy wizard refuses a cast order) | the ordered spell's entry loses "cast ordered" (unless it is the pending spell); **no gameplay effect**; power not refunded |
| `DropPendingSpell` | the pending spell's entry loses "cast ordered"; pending := none; no gameplay effect, no refund. 🟡 with no spell pending the entry lookup is ill-defined (never shipped) |
| failed `CastPending` / failed launch | the spell's entry loses "cast ordered"; `GMTXT 2021` for player-army casters; no refund |
| successful launch | entry: "cast ordered" cleared, "active" set (Dispel Magic: "selected" set instead) |

The engine can therefore model only **selected** (Dispel Magic once-per-battle lock, plus the player's targeting
mode) and **active** (AI rule 2, Ctrl+click cancel); "cast ordered" is cosmetic.

## 9. Test vectors

Fixed dice are given as the values the random source returns (`D6` = 1 + R mod 6 as used by the game).

**Madness**

| before | action | after |
|---|---|---|
| enemy wizard W; player regiment P (reference figure at (500,500), footprint radius 40) | W launches Madness at (520,500) | d 20 < 48 → P; hostile, not maddened → effect (timer 180); P's side := enemy; 0x31 queued to P |
| same, but player regiment Q's figure at (515,500) | launch at (520,500) | Q is nearer (5) → Q maddened, not P |
| allied regiment A (figure at (518,500)) nearer than P | **player** wizard launches at (520,500) | A taken, A not hostile to the player's wizard → **fail**, power lost, `GMTXT 2021` |
| P maddened by W | another enemy wizard launches Madness at P | fail (already maddened) |
| player wizard maddens enemy regiment E | – | E's side := **allied**; player cannot order it |
| P maddened at tick 100 | ticks 100…279 | P on the enemy side; script 167 every 10 ticks attacks the nearest unit hostile to the enemy side |
| P maddened at tick 100 | tick 280 effect update | side restored; 0x32 → script 168 → rally/re-form/restart |
| P maddened at tick 100; a mission `SetSide 64` on P at tick 150 | tick 280 | side := the value saved at tick 100 (the `SetSide` is lost) |
| P maddened; Mork Save Uz on regiment M centred 70 from the **aim point**; dice R mod 100 = 30 | M's pass | 30 < 50 and 70 < 80 → dispelled: side restored at once, 0x32, `GMTXT 2006` |
| same, P has since walked 300 away, M stays | M's pass | still measured from the aim point → dispelled |

**Skitterleap**

| before | action | after |
|---|---|---|
| player wizard Z at (0,0) facing 0, not in melee | launch at (0, 900) | arc 0 → ok (range unlimited); particles start; tick T…T+3 animate |
| same | tick T+4 update | Z's centre = (0,900), facing 0, formation and destination unchanged |
| same | Talisman bearer 60 from (0,900) during T…T+3 | 100 % pass → dispelled, Z stays at (0,0) |
| AI wizard W at (0,0) facing 0, threat range 240, enemy H at (0,200), W not in melee | choose Skitterleap → point (0,−216); `CastPending` | bearing to point 256 ≥ 71 → **launch fails**, power lost |
| same, W in melee | `CastPending` | arc skipped → succeeds; W appears at (0,−216) on tick T+4 |

**Ere We Go / Mork Save Uz** — see the stacking table in §3, plus:

| before | action | after |
|---|---|---|
| enemy regiment E (T 3, I 2), player wizard casts Ere We Go on E at tick 0 | ticks 1…180 close combat | E: T 4, I 20 → makes no attacks; tick 180 end → T 3, I 2 |
| Mork Save Uz on regiment M at tick 0 | ticks 0…180 | 181 passes at 50 % around M's current centre; a pass removing an effect clears the shaman's entry "active" |

**Fists of Gork**

| before | action | after |
|---|---|---|
| AI shaman S, target E (T 3, 10 models, W 1); aim at E's leader at (400,400); E's centre (400,410) | strike, D6 = 4 | 4 ≥ 2 → 1 wound to a random model; it dies on its next model update; no credit |
| same | strike, D6 = 6, 6, 3 | 2 wounds (first 6 → wound, next 6 → wound, 3 stops) |
| same | strike, D6 = 1 | nothing |
| victim T 8 | D6 = 5 / 6 | nothing / ≥ 1 wound |
| E's centre at (400,417) | strike | d 17 > 16 → nothing (unless another unit's centre is within 16) |
| E's centre at (400,416) | strike | d 16 ≤ 16 → E is the victim |
| launched tick 0 | – | strikes on ticks 0, 4, …, 176 (45); end on tick 180, caster's models told to stand |

**Dispel Magic**

| before | action | after |
|---|---|---|
| player wizard D casts Dispel Magic at tick 0; enemy Flamestorm aim point 70 from D; R mod 100 = 60 | tick 0 pass | 60 ≥ 50 → nothing; timer 179 |
| same | tick 3 pass, R mod 100 = 10 | dispelled (`GMTXT 2006`), Dispel effect ends at once |
| D afterwards | player clicks Dispel again | button unusable (entry selected) for the rest of the battle |
| D's own Curse on D's unit | D's pass | never dispelled (aimed at P) |
| two enemy Fireballs in flight, 50 and 90 from D, both rolls succeed | one pass | the one at 50 dispelled, the one at 90 not (90 ≥ 80); Dispel ends |
| 3 enemy effects active anywhere | one pass | 3 random numbers consumed (one per eligible effect), distance tested after |
| BF035 scripted Skitterleap (code 535) beside a Talisman | aura passes | never dispelled (marker) |

**Winds**

| before | action | after |
|---|---|---|
| clock 49 990, last wind 0 | check (≥ 1 s since last check) | no wind |
| clock 50 080 | check | wind; last_wind 50 080; next wind at the first check with clock ≥ 100 000 |
| pool 0, R mod 8 = 0 / 1 / 7 | wind | 1 / 1 / 7 |
| pool 2, R mod 4 = 3 | wind | 5 |
| pool 6, R mod 8 = 0 / 7 | wind | 2 / 8 (6 − 4 + 7 = 9 → 8) |
| pool 8, R mod 8 = 5 | wind | 8 (9 → 8) |
| Grudgebringer used at 30 s | wind at 50 s | usable again (both sides' items re-armed) |
| battle paused 20 s at 40 s | – | the first wind at 70 s wall time (50 s of unpaused clock) |

## Corrections to public notes

1. `game_rules.md` "Winds of magic and casting": "an empty pool becomes 1–7, otherwise current − 4 … current + 3, at
   least 1" is **wrong for pools 1–3** (they become current … current + 3, never lower) and omits the upper clamp
   (results above 8 become 8). Also "every 50 s of unpaused real time" should add: winds fall at multiples of 50 s of
   that clock, checked at most once per second at the start of a tick (§7).
2. `game_rules.md` "Spells", Madness row: "friends drop it as a target" → its **new** side-mates (its former
   enemies) are told to drop it (event 0x16 sent by the maddened unit's own script after the swap); an enemy unit
   becomes **allied**, not player-army; the end restores the side saved at launch and re-forms the unit (§1).
3. `game_rules.md` "Spells", Fists of Gork row: the victim is the nearest unit whose **centre** is within 16
   (inclusive) of the **aim point** (the caster's own centre for the player, the target's figure for the AI),
   excluding the caster's unit; "a 6 chains" = after a first 6, each further consecutive 6 adds a wound (§4).
4. `game_rules.md` "Spells", Ere We Go: "T +1 and I := 20 (both restored)" → T is **decremented** and I written
   back from the value saved at that cast; overlapping casts leave I = 20 permanently (definite, not 🟡) (§3).
5. `game_rules.md` "Spells", Skitterleap "teleports to the point": add the 4-tick delay, no checks, launch arc applies,
   and "the AI's Skitterleap only succeeds in melee" (§2). Same in `script_magic.md` §2.3 ("Skitterleap (escape)").
6. `game_rules.md` "Dispel and anti-magic": "other dispels … are skipped" → only **Dispel Magic** effects are
   skipped; Mork Save Uz effects can be dispelled. Add: Dispel Magic ends after its first successful pass; usable
   **once per battle per wizard**; the chance roll is made per eligible effect before the distance test (§5).
7. `script_magic.md` §3.1: the `+512` marker of `SetSpellIfAffordable 535` also makes the launched effect
   **undispellable** (not "no other use found").
8. `script_magic.md` §3.4 and `script_animation_sound.md` §3.2 ("panel entry made usable again", "the button … is
   not left locked"): the state cleared is only the cosmetic "cast ordered" mark; the button never depended on it
   (§8). Availability depends on "selected" and the pool.
9. `script_magic.md` §2.2 Dispel rule: add "the Dispel entry is not selected (never cast this battle)" and that the
   examined effect may be innate or out of reach (§5.5).
10. Engine model: `maddened(target)` = an active Madness effect on it; `channelling` = owns an active Storm/Bower
    effect; Madness swaps enemy → **allied** (not player).

## Open items 🟡

- Building pseudo-units as candidates of the unit-under-point search and of Fists of Gork.
- A broken/routing unit receiving event 0x31: whether its current script lets the switch to the madness loop happen.
- Skitterleap out of melee-grid membership after the teleport (grid membership is not touched by the spell).
- Item aura of a destroyed bearer unit.
- Flying Bower dispelled mid-flight: exact restore position (take-off point assumed); full Bower/Storm effects are
  a later batch.
- The "under the player's direct command" state cleared by Madness: confirm it has no effect beyond the order panel.
- Caster-removal cancellation applies to Wizard-class casters only (part A §1.4): kill credit and end steps of a
  removed monster-class shaman's effects (e.g. its Madness runs to its timer).
