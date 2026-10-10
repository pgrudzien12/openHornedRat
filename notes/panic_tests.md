# Casualty panic and impact panic: exact rules

Public implementation report (behaviour only), answering the implementer's request to implement the per-quarter
casualty panic test. It refines `game_rules.md` §7 "Panic" (two corrections, also made there) and §8 "Impact".
Companions: `game_rules.md` "The Leadership test", `casualty_bookkeeping.md` §2 (when a model is "killed"),
`unit_removal_broadcast.md` (removal of a wiped-out unit), `spell_effects.md` §3.6 (Burning Head's panic),
`spell_area_effects.md` (held units and Conflagration's fuse panics).

## 0. Shared state (read this first)

- **orgsize**: the unit's organisational size from its `.BTS` / `.MRC` record (`s_orgsize`, `game_rules.md` field
  14), **not** its size at battle load. `q = orgsize >> 2` (integer). If q = 0 (orgsize 0–3, or a file that writes 0
  there) there is **no** casualty panic at all.
- **size**: the models still in the unit. A model leaves the unit only when its **death sequence starts** (after its
  collapse delay: 1 tick for missiles, fire, warpfire, slain outright; staggered up to 72 ticks in close combat,
  `game_rules.md` "Death kinds"). A model that is dying but has not started its sequence still counts.
- **The Leadership test**: pass iff `modifier + (2 … 12 uniform) ≤ effective Ld`. Effective Ld is the leader's Ld if
  the unit has a leader model whose Ld is not 0, otherwise the first model's Ld. "Fight harder" lowers the modifier
  by 1. **No exemption is checked by the test itself.**
- **A failed panic test queues event 0x0C** ("rout") to the unit. It does not start the flight directly. The unit's
  own handler decides (§3).

## 1. Q1, Q5: the casualty test (per death)

When a model is **killed** (its death sequence starts; removals without death never test):

```
before = size before this model leaves; after = before − 1
skip if q == 0
skip if before == orgsize            # a unit at (exactly) full organisational strength never tests on its first loss
if floor(before / q) != floor(after / q):
    test with modifier = 1 − floor(after / q)      # failure → event 0x0C to the unit
```

- One check per killed model, at the moment that model's death sequence starts. **There is no per-tick or
  per-volley limit**: a volley whose victims start their death sequences in the same tick runs one check per
  victim, so it tests once for every quarter boundary it crosses.
- **The first loss from full strength never tests** (correction: `game_rules.md` said "−2 at the first loss below
  16"). For orgsize 16 the boundaries are 12 (modifier −1), 8 (0) and 4 (+1). The −2 step is reached only by a unit
  that starts below orgsize but at 13–15, and even then only when it falls to 11 or less: 15 → 14 → 13 → 12 cross
  nothing.
- A unit **starting below orgsize** (e.g. 12 of 16) tests on its first loss if that loss crosses a boundary: 12 → 11
  crosses 12 → test at −1.
- **Order with removal**: if the killed model was the last one, its check runs first (it crosses into 0, modifier
  +1), then the unit is removed (`unit_removal_broadcast.md`): its queued events, the 0x0C included, are discarded
  and 0x16 is broadcast. A wiped-out unit therefore never visibly routs.

## 2. Q4: the impact panic (missiles, spells)

The impact routine (`game_rules.md` §8 "Impact") has two optional per-weapon flags:

| flag (weapon data) | effect, per unit struck | carried by |
|---|---|---|
| `0x80` impact panic | after the hit on that unit is resolved: **if size ≤ orgsize >> 2**, a panic test at **modifier 0** (failure → 0x0C) | every ordinary missile (bows, crossbows, guns, cannon, mortar, rock lobber, volley gun, Doom Diver; damage flags 0x82), **not** the Gyrocopter bomb; **no spell** (`spell_effects.md` §4) |
| `0x40` forced rout | after the hit: 0x0C queued unconditionally | no ordinary missile and no spell in the public tables 🟡 (not checked exhaustively) |

- **Only direct hits** (impact point inside the unit's footprint, height test passed) ask for it. A unit struck
  only by the **blast margin** gets no impact panic and no forced rout (correction: `game_rules.md` §8 said
  "afterwards" for every struck unit). A direct hit asks even if it wounded nobody.
- It is asked **once per impact per unit**, with the size at that moment. Models killed by this very impact are still
  in the unit (their death sequences start later), so the size is the size **before** this impact's deaths.
- Timeline of one missile kill: impact tick T → impact panic (if size ≤ q); tick T+1 → the victim's death sequence
  starts → casualty check of §1.
- Separate, already public: Burning Head's per-tick panic (modifier 0, `spell_effects.md` §3.6), Conflagration's fuse
  panics, and the Curse's mount panics (`spell_area_effects.md`, `spell_channelled_effects.md` §4).

## 3. Q2, Q3: who is affected, and what a failure does

- **The test runs for everyone** who loses a model as above: routing, hidden, in melee, pursuing (the original's debug
  log even has a pursuing variant), leaving the battle, any class. Only q = 0 (orgsize < 4) and the full-strength
  first loss skip it.
- **The outcome is filtered by the unit's event handler** on 0x0C (library 151/153/155/156, mission handlers via
  152). `RoutAllowed`:
  - an already **broken** unit: nothing (no speech);
  - **`CantBreak`**: no rout, the unit says `React 7` (its "we stand" line);
  - otherwise `React 4` (its rout line) and the **rout script 162** (start of flight, `game_rules.md` "Rout").
  The rout start broadcasts 0x0F to enemies as for any rout, so **pursuit follows exactly as for a failed break
  test**.
  - **Artillery class** (library 154) skips `RoutAllowed` and does not rout on 0x0C.
  - Other psychology (`PsyImmune`, `Frenzy`) is **not** consulted by `RoutAllowed` 🟡 (only broken and `CantBreak`).
- **No battle message** text is printed by the test itself; the only feedback is the React speech above.
- **Held units** (Tangling Thorn): the 0x0C path is the same. What a held unit does in the rout script is described in
  `spell_area_effects.md` §3 (it cannot move off).
- Difference from the engine: route panic (and the impact panic) through **event 0x0C and the handler**, instead of
  calling the rout start directly, so `CantBreak`, broken and artillery behave as above.

## 4. Test vectors (rolls are the uniform 2–12 draw r)

16-model Skaven Clanrats, orgsize 16 (q = 4), Ld 5, starting at full strength (16):

| volley kills (deaths start the same tick) | checks | tests | pass chance |
|---|---|---|---|
| 1 | 16→15: before = orgsize → skip | none | – |
| 4 | 16→15 skip; 15→14, 14→13, 13→12 cross nothing | none | – |
| 5 | as above, then 12→11 crosses (3 → 2) | one test at **−1**: pass iff r ≤ 6 | 5/11 ≈ 45 % |
| later, 8 → 7 | crosses (2 → 1) | test at **0**: r ≤ 5 | 4/11 ≈ 36 % |
| later, 4 → 3 | crosses (1 → 0) | test at **+1**: r ≤ 4 | 3/11 ≈ 27 % |

Same unit starting the battle at **12** (orgsize still 16): its first loss 12 → 11 tests at −1.

20-model unit, orgsize 20 (q = 5), Ld 7, now at 5 models, **direct** cannon hit killing 1:

| tick | event | test |
|---|---|---|
| T (impact) | impact panic: size 5 ≤ 20 >> 2 = 5 | modifier 0: pass iff r ≤ 7 (6/11) |
| T+1 (death sequence starts) | 5 → 4 crosses (1 → 0) | modifier +1: pass iff r ≤ 6 (5/11) |

The same unit struck only by the **blast margin** of a mortar shell, losing 1: no impact panic, then the T+1
casualty test only.

A 3-model unit (orgsize 3, q = 0): never tests casualty panic; it still takes impact panic on a direct hit when
size ≤ 0 >> 2 = 0, i.e. never.

## 5. Corrections made in public notes

- `game_rules.md` §7 "Panic": the full-strength first loss never tests (the "−2" example removed).
- `game_rules.md` §8 "Impact": the 0x80/0x40 follow-ups apply to **direct** hits only.
- `ranged_combat_handoff.md` §3: "after any missile hit" → after a **direct** missile hit.

## 🟡 Open

- Whether any shipped weapon or spell carries the forced-rout flag 0x40.
- Whether `PsyImmune` units are meant to be immune (the original does not check it here).
