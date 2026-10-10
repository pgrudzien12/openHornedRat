"""The "unit removed" broadcast, event 0x16 (notes/unit_removal_broadcast.md): a unit wiped out tells every other unit
in the battle once its last model has collapsed, so a shooter's script drops it as a target (the BF006 crossbows that
kept firing at an empty spot); a script's RemoveFromBattle is quiet."""

import unittest

from whshr import animation, combat
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class RemovalBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.shooters = Regiment("S", "Crossbows", 100, 100, 0, Side.PLAYER, models=10, ranks=2)
        self.ally = Regiment("A", "Cart", 300, 100, 0, Side.NEUTRAL, models=2, ranks=1, unit_class=7)
        self.goblins = Regiment("X", "Goblins", 100, 400, 256, Side.ENEMY, models=1, ranks=1)
        self.reserve = Regiment("H", "Reserve", 900, 900, 256, Side.ENEMY, models=10, ranks=2)
        self.reserve.hidden = True
        self.battle = Battle(1000, 1000, [self.shooters, self.ally, self.goblins, self.reserve], seed=1995)
        self.battle.phase = "battle"

    def removals(self, unit_id: str) -> list[str | None]:
        return [event.source for event in self.battle.event_bus.unit_states[unit_id].event_queue
                if event.code == 0x16]

    def kill_last_model(self, death_kind: int) -> None:
        combat.kill_models(self.goblins, [0], battle=self.battle, death_kind=death_kind, killer="S")

    def test_given_the_last_model_shot_then_every_other_unit_hears_of_the_removal_on_the_next_tick(self):
        self.kill_last_model(animation.DEATH_MISSILE)
        self.battle.tick()
        for unit_id in ("S", "A", "H"):
            self.assertEqual(self.removals(unit_id), ["X"], unit_id)
        self.assertEqual(self.removals("X"), [])

    def test_given_the_broadcast_went_out_then_it_is_not_repeated(self):
        self.kill_last_model(animation.DEATH_MISSILE)
        for _ in range(5):
            self.battle.tick()
        self.assertEqual(self.removals("S"), ["X"])

    def test_given_a_close_combat_death_then_the_broadcast_waits_for_the_collapse(self):
        self.kill_last_model(animation.DEATH_ORDINARY)
        delay = self.goblins.dying[0].ticks_left
        self.assertGreater(delay, 1)
        for _ in range(delay - 1):
            self.battle.tick()
        self.assertEqual(self.removals("S"), [])
        for _ in range(2):
            self.battle.tick()
        self.assertEqual(self.removals("S"), ["X"])

    def test_given_a_unit_with_models_left_then_nothing_is_broadcast(self):
        self.battle.tick()
        self.assertEqual(self.removals("S"), [])

    def test_given_a_script_removes_the_unit_then_the_removal_is_quiet(self):
        self.battle.remove_from_play(self.goblins)
        self.battle.tick()
        self.assertEqual(self.removals("S"), [])

    def test_given_the_broadcast_then_no_target_is_cleared_directly(self):
        state = self.battle.event_bus.unit_states["S"]
        state.current_target = ("X", 0)
        self.kill_last_model(animation.DEATH_MISSILE)
        self.battle.tick()
        self.assertEqual(state.current_target, ("X", 0))


if __name__ == "__main__":
    unittest.main()
