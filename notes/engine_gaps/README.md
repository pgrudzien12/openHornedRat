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
| [`formation_movement.md`](formation_movement.md) | Units turn/reverse by snapping instead of wheeling; no per-formation turn exceptions (monsters, wagons); no break-and-turn stagger pause on rout | Formation & movement fidelity |
| [`formation_resort.md`](formation_resort.md) | Rank changes/re-forms aren't a distinct process: no nearest-match re-slotting, no flat-speed re-form mover, no place-swap rule | Formation re-sorting |
| [`figure_animation.md`](figure_animation.md) | One shared `(action, phase)` per regiment instead of per-model state: no random entry/desync, no staggered collapse on death, no drawn-facing slew | Figure animation |
| [`model_movement.md`](model_movement.md) | Every model walks to its slot at one flat speed; no rank-dependent catch-up rate, charge stretch, stagger, or concertina recovery | Model movement fidelity |
| [`engagement_dispersal.md`](engagement_dispersal.md) | Joiner candidate cells use a runtime distance sort instead of the documented per-direction table; no "at rest"/re-aim wiring between engagement placement and the (not yet implemented) catch-up walk | Engagement asymmetry |
| [`charge_bonus.md`](charge_bonus.md) | Charge counter is granted from the live (casualty-shrunk) front rank instead of the formed frontage, and consumed at half the documented rate; no re-engage-same-opponent check | Charge bonus rules |
| [`mounted_units.md`](mounted_units.md) | Mounts aren't modelled at all: no mount-derived movement speed, no extra mount attack sequence in close combat | Mounted units |
