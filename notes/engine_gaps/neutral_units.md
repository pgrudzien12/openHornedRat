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

## Findings (Resolved via Task #8) ✅

**RESOLVED:** `notes/neutral_units.md` documents complete survey of all 54 battles.

**Key findings:**
- **Neutral IS a real third side:** bit 6 (0x40) set in s_side, distinct from player (neither bit) and enemy (bit 7)
- **27 battles have NPC units** (101 total placements); 10 have peasants specifically
- **Peasants use type code 0x0E, side 0x4E**; other NPCs use 0x40–0x53 range
- **NPC units in "NPC units" .BTS section,** structurally separated from enemies
- **Behavior is script-driven:** each NPC runs an assigned mission script (scripts 2–8), not hardcoded neutral AI
- **Different NPC categories:** peasants, dwarves, mercenaries, wizards, supply units, artillery

**Three-way side system (2-bit side code, bits 7,6):**
- PLAYER: bits 7,6 = 00
- NEUTRAL: bits 7,6 = 01
- ENEMY: bits 7,6 = 10
- RESERVED: bits 7,6 = 11 (no units found)

See `notes/neutral_units.md` for full data, type codes, and implementation guidance.

## Implementation notes

- Until the `.BTS` survey above is done, don't guess a specific "neutral AI behaviour" — this is a
  research task, not an implementation one, and should stay blocked on it.
- Once the side model is known, `whshr.engine.Battle` likely needs a side enum richer than
  `regiment.player: bool` (at minimum: player / enemy / neutral, with room for the allied-flag transition),
  and `whshr/ai.py` needs a neutral-specific policy (e.g. no offensive orders unless provoked) instead of
  reusing the generic enemy AI.
