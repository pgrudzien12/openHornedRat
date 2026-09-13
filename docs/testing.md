# Behaviour-driven development rules

Tests specify observable game and asset-pipeline behaviour. They are executable
examples of what the player, mod author, or command-line user can rely on; they
must not prescribe a particular internal implementation.

## Rules

1. Write the scenario before implementing a new behaviour or fixing a regression.
2. Name tests as a readable Given/When/Then statement, for example
   `test_given_player_regiment_when_ordered_inside_field_then_it_moves_and_faces_destination`.
3. Exercise public behaviour only: public simulation methods, public loaders, CLI
   commands, serialized catalog output, or visible renderer state.
4. Assert outcomes, not mechanisms. Check a regiment's resulting position, facing,
   state, and emitted events; do not assert which helper was called, which cache
   container was used, how many private methods ran, or how state is stored.
5. Use small synthetic installations and battle data for format and asset scenarios.
   Test the real local installation separately as a manual/regression validation,
   never as a committed fixture.
6. Make simulation examples deterministic: fixed tick durations, explicit inputs,
   explicit random seeds, and no wall-clock assertions.
7. Test an edge case whenever it represents a player-visible rule: invalid orders,
   blocked destinations, depleted units, missing required assets, incompatible
   installations, and interrupted scene transitions.
8. Prefer one scenario per behaviour. Parameterize only truly identical rules with
   several meaningful inputs.
9. Do not use mocks to verify call sequences. Fakes are allowed only at a system
   boundary (filesystem, clock, renderer, audio device) and tests must still assert
   the externally visible outcome.
10. A refactor that preserves behaviour must keep BDD tests unchanged. If a test
    must change merely because private code moved or was renamed, replace it with
    an outcome-level scenario.

## Scenario format

Use standard-library `unittest` for now. Each test should make its Given/When/Then
structure clear through setup and assertion grouping:

```python
def test_given_player_regiment_when_ordered_inside_field_then_it_moves_and_faces_destination(self):
    # Given
    battle = Battle(100, 100, [Regiment("player", "Player", 10, 10, 0, True)])

    # When
    battle.order_move("player", 70, 10)
    battle.tick(seconds=1 / 60)

    # Then
    regiment = battle.regiments["player"]
    self.assertEqual((regiment.x, regiment.y), (11, 10))
    self.assertEqual(regiment.direction, 128)
```

The comment labels are optional when the test name and structure already state the
scenario clearly. Do not add a Gherkin parser or a separate BDD framework unless
the standard test runner can no longer express scenarios clearly.

## Acceptance scenarios by subsystem

| Subsystem | Examples of observable rules |
|---|---|
| Asset locator | An asset in `UPDATE/BINARY` overrides the identically named `FILE/BINARY` asset; an absent required path reports a useful installation error. |
| Asset catalog | A selected installation exposes stable logical IDs for supported assets, and catalog output contains metadata but no original asset bytes. |
| Cache | Re-requesting an unchanged logical asset returns equivalent decoded content; a changed source is reloaded before use. |
| Scene transitions | Skipping the intro reaches the menu; selecting a mission briefing resolves its battle; leaving battle releases battle-scoped resources without losing campaign state. |
| Movement | A player regiment reaches a valid order destination at its defined speed and faces travel direction; enemy regiments reject player orders; blocked orders preserve a clear observable state. |
| Combat | Given fixed statistics, dice seed, formation, and range, an attack produces the documented casualties, morale result, and emitted battle events. |

## Validation layers

- **Unit-level scenarios:** fast deterministic business rules for simulation, catalog,
  loading, and scene state.
- **Integration scenarios:** a synthetic installation flows through locator, catalog,
  loader, and scene setup without original game data.
- **Original-install regression:** `python3 -m whshr check <WARFB>` and selected
  manual SDL2/OpenGL visual checks validate reverse-engineering against a legally
  owned local copy. These are not a replacement for portable behavioural tests.
