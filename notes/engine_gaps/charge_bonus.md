# Gap: charge bonus rules (the charge counter)

**Symptom**: the engine's charge bonus is close but not exact — it's granted from the wrong count
(shrinks as casualties mount, when it shouldn't), and it's consumed at half the documented rate, so
in a long fight it both over- and under-shoots the "opening exchange only" effect the original
produces.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Charge" (under Mounts/close
combat), marked ✅.

- **Granted amount**: `charge counter = floor(1.5 × frontage)`, where `frontage` is the unit's
  **formed** frontage — casualties never reduce it (only a re-form would). Current engine
  (`whshr/combat.py:398`) instead uses `regiment.front_rank_models()`, the *live* front-rank count,
  which shrinks as the unit takes casualties — the wrong input. `regiment.frontage` (the formed value,
  already stored and already used correctly for the rank bonus, `combat.py:143`) is the right field.
- **The charge counter is not the charging flag, and not a duration.** "Charging" is movement/order
  state, cleared the instant engagement happens. The counter is a separate **budget of attacks**, set
  once at the instant of engagement, and nothing decrements it with time — it survives until spent,
  including into a later, unrelated engagement if the fight it was granted for ends first. Already
  matched in the current engine (nothing resets `charge_counter` on leaving a fight).
- **It gives +1 Strength while non-zero** (a mount uses its charge-strength stat instead of normal S
  — out of scope here, see "Scope boundary" below).
- **Consumed at two points, not one**: the attack resolution that grants the +1 S decrements it, *and*
  the per-model melee round decrements it again after that model's attacks (rider's and mount's, where
  mounted) have been resolved. For a foot model this is **two decrements per fighting model per
  round**, not the one the current engine applies (`combat.py:461-463`). A mounted model drains it
  faster still (rider and mount each run their own attack resolution) — deferred, see scope below.
  Net effect: the bonus covers only the **opening exchange** (order of the first half-frontage to
  frontage of models to actually land attacks), not a fixed model count. 🟡 The exact number of
  beneficiaries per formation is not confirmed against a live fight in the public report either.
- **Re-engaging an opponent you are already fighting grants zero** (`Engage`, not `EngageCharging`,
  stores 0) — not modelled today; the current engine grants a fresh counter to any regiment newly
  joining a melee group with a matching `attack_target`, without checking whether that opponent is one
  it was already fighting in a previous stint on the same grid.
- **A unit that joins an ongoing fight also gets a counter** (whichever side is newly joining a grid,
  brand new or already under way) — already correctly matched (existing code comment: "whether the
  fight is brand new or a third regiment joining one already under way").
- 🟡 **Open decision, not a confirmed fact**: the report flags a "probable bug" in the original where a
  charging monster's own melee round never decrements its counter, so it effectively keeps +1 S for
  the rest of the fight. Flagged low-confidence in the source research; an engine choice (replicate for
  fidelity, or treat as a bug not worth reproducing) rather than something to silently implement.

## Scope boundary

`whshr/combat.py`'s own module docstring already states mounts are not modelled ("No hatred re-rolls,
magic items, mounts or monster return blows"). The rider/mount dual-attack-resolution detail (a
mounted model draining the counter faster than a foot model) is therefore out of scope until mounts
exist in this engine at all — a separate, larger, already-acknowledged simplification. This gap's
tasks are scoped to foot models.

## Open questions

Tracked as [epic #57](https://github.com/pgrudzien12/openHornedRat/issues/57) (tasks #58-#60), under a
new `area:combat` label since this is a close-combat rule, not a formation/movement one.

- **Replicate the monster charge-bonus quirk, or not?** The source research flags this as a "probable
  bug" in the original with low confidence, not a confirmed intended rule. Settling method: an engine
  choice, decided by asking rather than defaulting either way — see task #60.

Nothing else is open — fully specified for foot models above.

## Implementation notes

Suggested breakdown (three GitHub tasks):

1. **Fix the granted amount**: `whshr/combat.py:398`, use `regiment.frontage` instead of
   `regiment.front_rank_models()`. One-line, no research needed.
2. **Fix the consumption rate and add the re-engage check**: decrement `charge_counter` twice per
   attacking foot model per round (once per the existing +1 S grant, once more at the end of that
   model's melee-round resolution) instead of once; and grant zero charge counter when a regiment
   newly joins a melee group against an opponent it was already recorded as fighting in a previous
   stint on the same grid (needs tracking the last-fought-opponent identifier per regiment, compared
   at grant time). Mount-specific faster draining stays deferred per the scope boundary above.
3. **Verification, and an explicit decision on the monster quirk**: tests confirming the bonus only
   covers roughly the opening exchange (not a fixed model count) at the corrected 2x drain rate,
   that re-engaging the same opponent gives no bonus, and that an unspent counter survives into a
   later, different engagement. Separately, get an explicit answer (not a default assumption) on
   whether to replicate the original's "monster charge bonus never depletes" quirk.

## Decision: monster charge-bonus quirk (default, not confirmed with the owner)

Resolved in task #60 **without asking** (owner unavailable): the engine does **not** reproduce the
"charging monster never decrements its counter" behaviour. Reasoning from observable behaviour: it would
make a monster keep +1 Strength for an entire fight, while every other unit's bonus fades after the
opening exchange; the source flags it as a low-confidence probable bug, and nothing in the data suggests
the designers wanted a permanent monster bonus. The engine also has no monster formation type yet, so
nothing is lost today. Any monster therefore drains the counter like a foot model. This is a default
decision and can be overruled: if reproduction is wanted later, add it when monster formations exist.
