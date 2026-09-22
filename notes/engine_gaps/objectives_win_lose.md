# Gap: mission objectives & win/lose conditions

**Symptom**: the engine's `ResultScene` (`whshr/result_scene.py`) only ever shows a flat "victory" or
"defeat" once one side fully routs, with a casualty summary. It ignores each mission's actual `.BTS`
objective letters (capture a point, protect the forest, get past the dragon, survive N turns…), so every
battle plays the same win condition regardless of its design.

## Known facts

From `notes/game_rules.md` §"Missions and objectives" (largely ✅, already public):

- Each `.BTS` defines a subset of **objective letters** (A–Z) as 40-byte records: whether the letter is
  defined, flags, an in-battle caption text id, an evaluator function id, a "met" flag, and two numbers
  `a, b`. Flags: `0x1` ends the battle when met, `0x2` evaluated every tick, `0x4` no caption in the
  end-of-battle list, `0x8` evaluated in a separate slower pass, `0x10` still evaluated after the battle is
  decided, `0x20` custom debrief line.
- **Battle-ending letters catalogued so far**: A (eliminate the enemy — the flat rule the engine uses
  today), F (BF009), H (BF015, BF017), N (get past the Dragon, BF014), and Z (a silent loss condition).
- Opcode `222` (`IfObjective n`) lets a unit's behaviour script branch on whether a given letter is
  currently defined — i.e. the bytecode interpreter (see `mission_scripts.md`) and the objective system are
  linked, not independent.
- Objective G ("Inside the gates!") is fully documented end-to-end as a worked example: threat behaviour
  12, an interior node, an event, and a side flip when a unit "gets inside the walls" (§"Objective G").
- Post-battle debrief evaluation (a separate, later pass) is already fully decoded in
  `notes/debrief_evaluation.md` (41 records, 8 evaluators, every `Result:` value) — that pass is about
  campaign consequences (pay, promotions, casualties), not the in-battle win/lose moment this gap is about.

## Open questions

- **26 of the objective letters' evaluator functions were never read** (game_rules.md: "the 26 evaluator
  functions... were not read"): what each evaluator actually counts (kills, models present in a region,
  turns survived, a captured node, etc.) beyond the five battle-ending letters above and G. This is the
  main blocker — most missions' true win condition is still unknown.
- Whether the two stored numbers `a, b` per objective are a generic "compare current count against target"
  pair for every evaluator, or vary in meaning per letter (the current guess is 🟡, unconfirmed per-letter).

## Implementation notes

- `Battle` should carry the mission's parsed objective records (already available from `whscript.py`'s
  `.BTS` parsing) and re-evaluate flag-`0x2` objectives every tick, flag-`0x8` ones on a slower cadence,
  ending the battle on the first met objective that has flag `0x1` — mirroring the original's tick/slow-pass
  split even before every evaluator's meaning is known.
- For letters whose evaluator is still unknown, fall back to the current flat rout rule *for that letter
  only*, rather than blocking the whole feature on decoding all 26 evaluators — implement letters as their
  semantics are settled (A, F, H, N, Z, G first, since those are already public facts), and track the rest
  as follow-up research tasks per letter or per mission as missions are brought online.
- `ResultScene` needs the objective's own caption text (already routed through `GMTXT 33000 + L - 'A'`, a
  public fact) instead of a generic victory/defeat string, so the player sees *why* the battle ended.
