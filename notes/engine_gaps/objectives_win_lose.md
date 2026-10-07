# Gap: mission objectives & win/lose conditions

**Symptom**: the engine's `ResultScene` (`whshr/result_scene.py`) only ever shows a flat "victory" or
"defeat" once one side fully routs, with a casualty summary. It ignores each mission's actual `.BTS`
objective letters (capture a point, protect the forest, get past the dragon, survive N turns…), so every
battle plays the same win condition regardless of its design.

## Status (implemented)

`whshr/objectives.py` implements `notes/battle_end_objectives.md`, the in-battle reference that supersedes the
older readings below where they disagree:
- the evaluation list: Z first, then the `.BTS` letters in file order;
- counts taken at load;
- segment-boundary checks before any unit moves;
- **no automatic end**: the deciding letter prints "Mission complete.", plays the speech cue and swaps the pause
  button for the tent;
- the final pass and the `Result:` records when the player leaves through the tent (`Battle.leave`).

The debrief receives the measured records instead of the outcome-derived ones (`payments.played_results` is kept
only for mission-less battles).

Engine approximations, named in the code:
- nothing damages buildings or knocks trees down yet, so C and Q stay at 100%;
- O reads "leader killed" as "regiment wiped out";
- G's "handled by the cleanup pass" is read as "removed".

The frontend shows the book button's objective list, plays the decision speech (`whshr/frontend/battle_sound.py`)
and draws the K/X Sparkle marker. The frame timing of the marker and positional sound are provisional.

## Known facts

From `notes/game_rules.md` §"Missions and objectives" (largely ✅, already public):

- Each `.BTS` defines a subset of **objective letters** (A–Z) as 40-byte records: whether the letter is
  defined, flags, an in-battle caption text id, an evaluator function id, a "met" flag, and two numbers
  `a, b`. Flags: `0x1` ends the battle when met, `0x2` evaluated every tick, `0x4` no caption in the
  end-of-battle list, `0x8` evaluated in a separate slower pass, `0x10` still evaluated after the battle is
  decided, `0x20` custom debrief line.
- **Battle-ending letters catalogued so far**: A (eliminate the enemy — the flat rule the engine uses
  today), F (BF009), H (BF015, BF017), N (get past the Dragon, BF014), and Z (a silent loss condition).
- **Which of those five is active is per-mission data, not a fixed pair** — do not hardcode "A ends in
  victory, Z ends in defeat" as the win/lose rule for every battle. Z is declared in 50/54 campaign battles
  (close to universal; treat "player army eliminated → defeat" as the default and special-case the other 4),
  and A in 47/54, but 3 missions **replace** A rather than also declaring it (BF009 uses F instead — the
  identical check in its own slot; BF014 uses N instead — A's check plus "a unit reached the target node"),
  and 2 siege missions (BF015, BF017) declare **both A and H together**, so either can end the battle,
  whichever is met first. An implementer must read each mission's own declared objective letters (already
  available from `whscript.py`'s `.BTS` parsing) rather than assume every battle uses the same two letters.
- Opcode `222` (`IfObjective n`) lets a unit's behaviour script branch on whether a given letter is
  currently defined — i.e. the bytecode interpreter (see `mission_scripts.md`) and the objective system are
  linked, not independent.
- Objective G ("Inside the gates!") is fully documented end-to-end as a worked example: threat behaviour
  12, an interior node, an event, and a side flip when a unit "gets inside the walls" (§"Objective G").
- Post-battle debrief evaluation (a separate, later pass) is already fully decoded in
  `notes/debrief_evaluation.md` (41 records, 8 evaluators, every `Result:` value) — that pass is about
  campaign consequences (pay, promotions, casualties), not the in-battle win/lose moment this gap is about.

## Open questions

- ✅ **Resolved**: all 26 remaining objective-letter evaluators have been read and are documented in
  `notes/game_rules.md` §"Missions and objectives" (the per-letter table). Only A, F, H, N and Z can end
  the battle; B/C/D/E/Q are real population-percentage or loss-threshold checks; several letters that read
  as real conditions from their debrief text (S, T, V, W) are unconditional stubs in the shipped code, and
  R/L/M are inert; Y mirrors a shared flag rather than computing anything itself.
- ✅ **Resolved**: for the threshold-style evaluators, `a` (from `Objective:L,a,b`) is the mission-authored
  threshold compared against the live count each tick/slow-pass, and `b` is silently overwritten at battle
  start with a freshly computed baseline population/count — the `.BTS` author's `b` value is discarded. Only
  `a` matters past battle start.

## Implementation notes

- `Battle` should carry the mission's parsed objective records (already available from `whscript.py`'s
  `.BTS` parsing) and re-evaluate flag-`0x2` objectives every tick, flag-`0x8` ones on a slower cadence,
  ending the battle on the first met objective that has flag `0x1` — mirroring the original's tick/slow-pass
  split. Only A, F, H, N, Z can end the battle (the only letters ever seen with flag `0x1`), so the engine
  only strictly needs those five implemented to reach behavioural parity on ending a battle; B/C/D/E/Q/G/H
  affect the debrief wording and (for G) an in-battle side-swap, not whether the battle ends.
- Now that every evaluator's behaviour is public (`notes/game_rules.md` §"Missions and objectives"),
  implement in this rough priority order: **A, Z** (generic elim/survive — needed by nearly every mission,
  already implemented as the flat rule); **N** (A's logic plus "a unit reached the target node" — needs a
  node-containment primitive already required elsewhere, `terrain_navigation.md`); **H** (a single state
  check on the siege gate object); **F** (identical to A, just a second instance — free once A exists);
  **B, C, D, E, Q** (all the same shape: percentage-of-population-remaining or count-of-loss against a
  threshold — one small generic helper covers all five); **G** (needs the node/event/side-flip mechanic from
  `notes/mission_scripts.md`, already itself fully documented, plus this evaluator's own roster-merge and
  two-unit-class met-check); **K, X** (reach-a-node-and-collect-an-item, shared logic); **O, P** (named-unit
  lookup + a status-flag or presence check). **S, T, V, W, Y, R, L, M** need no evaluator logic at all — S
  and T always read as "met" once evaluated, V and W always read as "met" but exist only to compute a
  debrief number, R/L/M never read as "met," and Y only mirrors another flag; an engine can hardcode these
  outcomes rather than port the (non-)logic.
- `ResultScene` needs the objective's own caption text (already routed through `GMTXT 33000 + L - 'A'`, a
  public fact) instead of a generic victory/defeat string, so the player sees *why* the battle ended.
- Caution for anyone tempted to treat the debrief text as ground truth for what an evaluator "really" does:
  several letters (S, T, V, W) have debrief wording that describes a real condition (capture, rescue, kill
  count) while their evaluator is an unconditional stub. Implement exactly what the table in
  `notes/game_rules.md` says the evaluator does, not what the flavour text implies, unless a later research
  pass finds the real condition elsewhere (e.g. in a mission's own bytecode via `IfObjective`/unit tags).
