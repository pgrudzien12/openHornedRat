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

**Implemented (Task #9):** `whshr.rules.Side` (player/neutral/enemy, decoded from the `s_side` bit
pattern above via `rules.side_of_code`) replaced `Regiment.player: bool` throughout the engine
(`engine.py`, `combat.py`, `ai.py`, `battle_grid.py`, `interpreter.py`, the HUD and log/debug
modules). `Battle.from_script` now reads each `.BTS` army unit's own `s_side` byte instead of treating
every non-`.MRC` unit as an enemy, so neutral units (peasants, dwarven allies, ...) load as
`Side.NEUTRAL` rather than being folded into the enemy roster.

- `whshr/ai.py`'s placeholder AI (only used for scriptless/synthetic battles; a real `.BTS` battle is
  always script-driven) now gives orders to `Side.ENEMY` regiments only -- neutral regiments hold
  position, per the "no offensive orders unless provoked" guidance below.
- `rules.hostile_sides(side)` gates every other *autonomous, unscripted* targeting decision (the AI's
  engage check, `combat.resolve_shooting`'s target search, `interpreter.LibraryBehaviors.track_threat`'s
  player-guard) to the default player/enemy hostility; neutral is hostile to nobody by default.
- Explicit script opcodes (`TargetNearestEnemy`, `AttackNearestEnemy`, `AttackNthNearestEnemy`, ...)
  keep the plain "different side" search, since a script naming a target has already made the decision
  -- not gated by `hostile_sides`. `AttackNearestFlag40Unit` (side flag 0x40) is now implemented for
  real, filtering for `Side.NEUTRAL` specifically, instead of the previous silent fallback to
  `AttackNearestEnemy`.
- Close-combat contact (`combat.resolve_contacts`'s touching test, `battle_grid`'s pairing,
  `Battle._resolve_collisions`'s push-apart) stays a plain "different side" rule: once two regiments of
  any two different sides physically touch, they can fight, regardless of `hostile_sides`.
- **Still open:** the runtime allied-flag transition (`0x100`, "Objective G") is not implemented --
  `SetSide` (opcode 0xDF) has no handler yet, and its operand encoding is not a documented public fact.
  Combat-result credit for neutral kills (who gets credit in the debrief) is also still open, per the
  survey's own open questions above.
