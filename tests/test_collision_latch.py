"""Re-form completion event 0x34 and the contact latch's movement rule (notes/movement_formation.md 1.2, 9;
notes/script_behaviours.md 2.5)."""

import unittest

from whshr.engine import Battle, Regiment
from whshr.rules import Side


def unit(identifier, x, y, facing=0, side=Side.PLAYER):
    return Regiment(identifier, identifier, x, y, facing, side, models=16, ranks=4, points=10)


def codes(battle, identifier):
    return [event.code for event in battle.event_bus.unit_states[identifier].event_queue]


class ReformCompletionTests(unittest.TestCase):
    def test_settled_reform_sends_event_0x34_to_the_unit(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        battle.reform_to_ranks(regiment, 2)
        self.assertTrue(regiment.reforming)
        for _ in range(400):
            battle.tick()
            if not regiment.reforming:
                break
        self.assertFalse(regiment.reforming)
        self.assertIn(0x34, codes(battle, "A"))

    def test_no_event_while_the_reform_is_still_running(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        battle.reform_to_ranks(regiment, 2)
        battle.tick()
        self.assertTrue(regiment.reforming)
        self.assertNotIn(0x34, codes(battle, "A"))

    def test_engagement_ending_a_reform_does_not_send_it(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        battle.reform_to_ranks(regiment, 2)
        battle.end_reform_for_engagement(regiment)
        self.assertNotIn(0x34, codes(battle, "A"))


class LatchMovementTests(unittest.TestCase):
    def make(self):
        # Two facing hostile blocks whose footprints overlap; A holds the latch.
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 500, 506, facing=256, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.event_bus.unit_states["A"].contact_latch = True
        return battle, a, b

    def test_latched_ordinary_move_that_still_overlaps_is_undone_and_halts(self):
        battle, a, b = self.make()
        before = (a.x, a.y)
        a.target_x, a.target_y = 500, 540  # further into B
        battle.tick()
        self.assertEqual((a.x, a.y), before)
        self.assertIsNone(a.target_x)
        self.assertTrue(a.reforming or not a.waypoints)
        self.assertTrue(battle.event_bus.unit_states["A"].contact_latch)

    def test_latched_charger_does_not_advance(self):
        battle, a, b = self.make()
        before = (a.x, a.y)
        a.attack_target = "B"
        for _ in range(3):
            battle.tick()
        self.assertEqual((a.x, a.y), before)
        self.assertEqual(a.attack_target, "B")

    def test_latched_move_that_steps_clear_stands_and_releases_the_latch(self):
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 500, 510, facing=256, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.event_bus.unit_states["A"].contact_latch = True
        # B is far enough away after one step only if the step is large; move A away and move B away too
        b.x, b.y = 500, 700
        a.target_x, a.target_y = 500, 300
        battle.tick()
        self.assertFalse(battle.event_bus.unit_states["A"].contact_latch)
        self.assertNotEqual((a.x, a.y), (500, 500))

    def test_unlatched_move_is_not_rolled_back(self):
        battle, a, b = self.make()
        battle.event_bus.unit_states["A"].contact_latch = False
        a.target_x, a.target_y = 500, 540
        battle.tick()
        self.assertNotEqual((a.x, a.y), (500, 500))


if __name__ == "__main__":
    unittest.main()
