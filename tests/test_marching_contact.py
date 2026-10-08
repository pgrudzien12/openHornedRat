"""The two-regiment worked example of notes/script_behaviours.md 2.8: hostile regiments marching into each other,
no charge, with the standard contact handler (events 0x0B -> Query 8, 0x0A -> the melee idle script).

The engine runs all scripts, then all movement, then one collision pass per update, where the original interleaves
them unit by unit, so the pass-then-handler sequence of the report's update t / t+1 takes one update more here:
the vectors below are the report's states at the same milestones.
"""

import unittest

from tests.script_helpers import FakeDll, word
from whshr.engine import Battle, Regiment
from whshr.rules import Side

LABEL = 0x1ABC
HANDLER = [word("PushPC"), word("GetEvent"),
           word("CaseEvent"), 0x0B, word("Query"), 8, word("Break"), LABEL,
           word("CaseEvent"), 0x0A, word("SwitchScript"), 165, word("Break"), LABEL,
           word("CaseEvent"), 0x07, word("Break"), LABEL,
           LABEL & ~0x1000, word("ConsumeEvent"), word("LoopIfTrue"), word("ReturnInterrupt")]
MAIN = [word("SetInterruptScript"), 2, word("PushPC"), word("Yield"), word("Loop")]
MELEE_IDLE = [word("PushPC"), word("Yield"), word("Loop")]


def pending(battle, identifier):
    return sorted(event.code for event in battle.event_bus.unit_states[identifier].event_queue)


class MarchingIntoEachOtherTests(unittest.TestCase):
    def setUp(self):
        # A (earlier in unit order) has just stepped so that the footprints touch: its re-check state is on.
        self.a = Regiment("A", "A", 500, 500, 0, Side.PLAYER, models=16, ranks=4, points=10)
        self.b = Regiment("B", "B", 500, 508, 256, Side.ENEMY, models=16, ranks=4, points=10)
        dll = FakeDll({1: MAIN, 2: HANDLER, 165: MELEE_IDLE})
        self.battle = Battle(2000, 2000, [self.a, self.b], seed=1995, script_dll=dll, script_ids={"A": 1, "B": 1})
        self.a.target_x, self.a.target_y = 500, 600
        self.b.target_x, self.b.target_y = 500, 460
        self.a.collision_recheck = True
        self.state_a = self.battle.event_bus.unit_states["A"]
        self.state_b = self.battle.event_bus.unit_states["B"]

    def test_the_first_pass_queues_0x0b_to_both_regiments(self):
        self.battle.tick()
        self.assertEqual((pending(self.battle, "A"), pending(self.battle, "B")), ([0x0B], [0x0B]))
        self.assertEqual((self.state_a.contact_record, self.state_b.contact_record), ("B", "A"))
        self.assertFalse(self.a.in_melee or self.b.in_melee)

    def test_the_handlers_pick_targets_and_charge_the_other_with_0x07(self):
        self.battle.tick()
        self.battle.tick()
        self.assertEqual(self.state_b.current_target, ("A", 0))
        self.assertEqual(self.state_a.current_target, ("B", 0))
        self.assertIn(0x07, pending(self.battle, "A"))  # B's target choice told A it is "being charged"

    def test_both_end_up_on_one_grid_with_the_earlier_unit_as_joiner_and_the_melee_script(self):
        for _ in range(3):
            self.battle.tick()
        self.assertTrue(self.a.in_melee and self.b.in_melee)
        self.assertEqual(self.a.melee_group, self.b.melee_group)
        self.assertGreater(self.a.charge_counter, 0)  # the joiner gets floor(1.5 x frontage)
        self.assertEqual(self.b.charge_counter, 0)
        self.assertEqual((self.state_a.script_id, self.state_b.script_id), (165, 165))
        self.assertTrue(self.state_a.contact_latch and self.state_b.contact_latch)

    def test_a_marching_pair_that_never_touches_raises_nothing(self):
        self.b.y = 700
        self.battle.tick()
        self.assertEqual((pending(self.battle, "A"), pending(self.battle, "B")), ([], []))


if __name__ == "__main__":
    unittest.main()
