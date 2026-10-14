"""A wiped-out unit stays in the battle until its last model's death sequence starts
(notes/unit_removal_broadcast.md 2, 4 vectors (a) and (a'), 5.1; GitHub #302)."""

import unittest

from whshr import animation, combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def make(scripted: bool = True) -> Battle:
    x = Regiment("X", "Goblins", 500, 500, 0, Side.ENEMY, models=3, ranks=1)
    s = Regiment("S", "Crossbows", 500, 200, 0, Side.PLAYER, models=10, ranks=2)
    battle = Battle(1000, 1000, [x, s], seed=1995)
    battle.phase = "battle"
    if scripted:
        battle.interpreter = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
    return battle


def removals(battle: Battle) -> list[str | None]:
    return [event.source for event in battle.event_bus.unit_states["S"].event_queue if event.code == 0x16]


class CloseCombatWipeTests(unittest.TestCase):
    """(a'): the last model killed in close combat collapses after a staggered delay; until then X is in."""

    def test_the_unit_stays_in_the_battle_while_its_last_models_collapse(self):
        battle = make()
        x = battle.regiments["X"]
        combat.kill_models(x, range(3), battle, animation.DEATH_ORDINARY, killer="S")
        self.assertEqual(x.models, 0)
        self.assertTrue(x.dying)
        self.assertTrue(x.active)  # a valid target, counted by searches, keeping its footprint
        self.assertFalse(x.destroyed)
        self.assertEqual(removals(battle), [])

    def test_it_is_removed_and_announced_once_the_last_death_sequence_starts(self):
        battle = make()
        x = battle.regiments["X"]
        combat.kill_models(x, range(3), battle, animation.DEATH_ORDINARY, killer="S")
        ticks = 0
        while x.dying and ticks < 200:
            self.assertTrue(x.active)
            battle.tick()
            ticks += 1
        self.assertFalse(x.dying)
        self.assertFalse(x.active)
        self.assertTrue(x.destroyed)
        self.assertEqual(removals(battle), ["X"])


class MissileWipeTests(unittest.TestCase):
    """(a): a missile death collapses after 1 tick, so X is removed on the next tick."""

    def test_a_missile_wipe_removes_the_unit_on_the_next_tick(self):
        battle = make()
        x = battle.regiments["X"]
        combat.kill_models(x, range(3), battle, animation.DEATH_MISSILE, killer="S")
        self.assertTrue(x.active)
        battle.tick()
        self.assertFalse(x.active)
        self.assertEqual(removals(battle), ["X"])


class PartialLossTests(unittest.TestCase):
    def test_a_unit_with_standing_models_is_never_destroyed(self):
        battle = make(scripted=False)
        x = battle.regiments["X"]
        combat.kill_models(x, range(2), battle, animation.DEATH_ORDINARY, killer="S")
        for _ in range(100):
            battle.tick()
        self.assertEqual(x.models, 1)
        self.assertTrue(x.active)


if __name__ == "__main__":
    unittest.main()
