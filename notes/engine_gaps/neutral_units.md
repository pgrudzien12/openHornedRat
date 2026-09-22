# Gap: neutral units & side relations

**Symptom**: in the first mission, neutral units (peasants) attack the player. The engine currently only
models two sides (`regiment.player: bool`), so anything not flagged player is treated as a hostile enemy —
there is no third relation (neutral, or "become allied mid-battle").

## Known facts

- `PEASANT` is a real sprite/animation set (`notes/animations.md`: 312 frames, 3 recolours × 4 actions —
  move/dead/attack?/stand?), so peasants are ordinary battle units by asset structure, not a special case
  at the sprite level.
- The behaviour bytecode has a documented **side-switching** mechanism: objective G ("Inside the gates!",
  `notes/game_rules.md` §"Objective G") sets a unit's side to allied (flag `0x100`, "allied side") when it
  reaches an interior node — proof the original's side model is not a hardcoded binary and mid-battle
  allegiance changes exist as a general mechanism, not just for objective G.
- `whoami` (0–37) is the persistent regiment identity used across the campaign layer (roster, hiring,
  `.BTS` `set:whoami`); it is a *roster slot*, not itself a side flag. The side/allegiance value units
  actually carry at runtime (beyond the player/enemy/`0x100`-allied bit already found) is not itself fully
  catalogued as a public fact yet — game_rules.md's behaviour-script section only documents "own side" vs
  "enemy side" event routing and the one allied-flag case.
- `.BTS` per-unit fields include a `whoami`/army id already parsed by `whscript.py`, but which battles
  place peasants and what side value/AI behaviour they're given has not been surveyed as a public fact.

## Open questions

- Which `.BTS` files place peasant (or other clearly-neutral) units, and what side/behaviour script do
  they carry there? A grep over parsed `.BTS` files for the peasant unit type, cross-checked against each
  file's per-unit side field, would answer this without needing a running game.
- Is "neutral" a real third side value in the original, or are peasants simply enemy-side units with a
  distinct AI behaviour (e.g. `RunAway`, since 206 "run away" already exists) that only look neutral
  because they never charge? This changes the engine's data model significantly and should be settled
  before implementing it.
- Do neutral units ever change sides during a battle (flee to become non-combatants, or join the player)
  beyond the one objective-G mechanism already documented?

## Implementation notes

- Until the `.BTS` survey above is done, don't guess a specific "neutral AI behaviour" — this is a
  research task, not an implementation one, and should stay blocked on it.
- Once the side model is known, `whshr.engine.Battle` likely needs a side enum richer than
  `regiment.player: bool` (at minimum: player / enemy / neutral, with room for the allied-flag transition),
  and `whshr/ai.py` needs a neutral-specific policy (e.g. no offensive orders unless provoked) instead of
  reusing the generic enemy AI.
