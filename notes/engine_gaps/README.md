# Engine gaps — from a battle demo to a playable mission

`notes/game_rules.md` and `notes/campaign.md` are the reference reports for *what the original computes*
(stats, combat math, morale, shooting, behaviour bytecode, objectives, save/campaign state). This directory
is a second layer on top of them: one file per **feature the real-time engine (`whshr/engine.py` and
friends) is still missing** to turn the current battle prototype into something that follows a mission's
story rather than a flat skirmish.

Each file:

- **Known facts** — pointers into the existing public reports (`game_rules.md` §, `campaign.md` §,
  `behaviour.py`/`formation.py` docstrings) so an implementer does not have to re-derive them.
- **Open questions** — what is still unknown, genuinely blocking the feature, with a settling method
  (Wine session, data grep, or "decide as an engine choice since the original is silent").
- **Implementation notes** — a behavioural sketch of what the engine should do, written independently of
  any disassembly (per `CLAUDE.md`'s research/implementation boundary — this file is itself the public
  hand-off, so it must stay in "what happens", not "how the original's code does it").

This directory doesn't move or duplicate the WFB rule math (to-hit charts, morale formulas, etc.) — that
stays the authoritative version in `game_rules.md`. It only exists for engine-integration topics that were
scattered across `game_rules.md`'s behaviour-script and objectives sections and needed their own place to
grow. GitHub issues (epics tagged `area:*`, tasks tagged `track:research`/`track:implementation`) track the
work; each epic links back to one file here.

## Gaps tracked here

| File | Gap | Epic |
|---|---|---|
| [`mission_scripts.md`](mission_scripts.md) | No in-engine interpreter for the original's unit-behaviour bytecode; units don't patrol, ambush, wait for triggers, or arrive as scripted reinforcements | Mission scripts & scripted events |
| [`deployment.md`](deployment.md) | No pre-battle deployment stage; player units are placed at their `.BTS` positions instead of hidden + player-placed | Pre-battle deployment |
| [`neutral_units.md`](neutral_units.md) | No third-party/neutral faction handling; a mission's non-player, non-enemy units (e.g. peasants) currently fight as ordinary enemies | Neutral units & side relations |
| [`terrain_navigation.md`](terrain_navigation.md) | No terrain-aware movement blocking or off-table removal; routed units can enter terrain the original would block and never leave the field | Terrain navigation & unit removal |
| [`objectives_win_lose.md`](objectives_win_lose.md) | Battle end condition is a flat "one side fully routed" instead of the mission's own `.BTS` objective letters | Mission objectives & win/lose |
| [`formation_movement.md`](formation_movement.md) | Units turn/reverse by snapping instead of wheeling; ranks don't hold shape while turning | Formation & movement fidelity |
