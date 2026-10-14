"""A unit whose last enemy leaves its grid (notes/lone_unit_on_grid.md): alone, it hears 0x30 outside the grid's
creation segment and stays in melee until its script leaves; with others still on the grid, the pairing step either
keeps it there or makes it leave with no target. Nothing geometric decides it. Deliberate deviation: the leaver gets
0x30 (re-form) instead of the original's target-less 0x19, which left it idling un-re-formed (report section 0.7)."""

import unittest

from whshr import behaviour, combat
from whshr.combat import ALONE_ON_GRID_EVENT, OPPONENT_GONE_EVENT, SEGMENT_TICKS, segment_state
from whshr.engine import Battle, Regiment
from whshr.rules import Side
from tests.script_helpers import FakeDll, word
from tests.test_enemy_routed import SCRIPTS as ROUT_SCRIPTS

MAIN = 100
EDGE = {"status": ["bnd_ACTIVE", "bnd_BATTLEEDGE"],
        "lines": [[0, 0, 1000, 0], [1000, 0, 1000, 1000], [1000, 1000, 0, 1000], [0, 1000, 0, 0]]}


def unit(identifier, x, y, side, direction=0):
    return Regiment(identifier, identifier, x, y, direction, side, models=4, ranks=1)


class Case(unittest.TestCase):
    def build(self, *regiments, scripts=None):
        self.battle = Battle(1000, 1000, list(regiments), seed=1995, boundaries=[EDGE],
                             script_dll=FakeDll(scripts or ROUT_SCRIPTS),
                             script_ids={r.identifier: MAIN for r in regiments})
        self.interp = self.battle.interpreter
        for state in self.battle.event_bus.unit_states.values():
            state.interrupt_script = 151

    def state(self, identifier):
        return self.battle.event_bus.unit_states[identifier]

    def engage(self, joiner, owner, tick=SEGMENT_TICKS * 3):
        """A grid made on `tick` (by default at the start of a segment); event queues emptied afterwards."""
        self.battle.tick_count = tick
        self.assertTrue(self.interp._engage(joiner, owner))
        combat.resolve_contacts(self.battle)
        self.assertTrue(joiner.in_melee and owner.in_melee)

    def next_segment(self):
        self.battle.tick_count += SEGMENT_TICKS

    def clear_queues(self):
        for state in self.battle.event_bus.unit_states.values():
            state.event_queue.clear()

    def queued(self, identifier):
        return [event.code for event in self.state(identifier).event_queue]


class AloneOnTheGridTests(Case):
    def setUp(self):
        self.a = unit("a", 500, 500, Side.PLAYER)
        self.e = unit("e", 500, 512, Side.ENEMY, direction=256)
        self.build(self.a, self.e)
        self.engage(self.e, self.a)
        self.clear_queues()

    def test_vector_2_a_rout_of_an_enemy_that_was_not_the_target_leaves_the_unit_alone_with_0x30(self):
        self.state("a").current_target = None
        self.next_segment()
        combat.start_rout(self.e, self.battle)
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.a.in_melee)
        self.assertIn(ALONE_ON_GRID_EVENT, self.queued("a"))
        self.assertNotIn(OPPONENT_GONE_EVENT, self.queued("a"))

    def test_vector_3_no_0x30_in_the_creation_segment_then_one_from_its_first_tick_after(self):
        segment = segment_state(self.battle.tick_count)[2]
        self.battle.tick_count += SEGMENT_TICKS - 7  # 7 ticks of the creation segment remain
        self.state("a").current_target = None
        combat.start_rout(self.e, self.battle)
        self.clear_queues()
        for _ in range(7):
            self.assertEqual(segment_state(self.battle.tick_count)[2], segment)
            combat.resolve_contacts(self.battle)
            self.assertEqual(self.queued("a"), [])
            self.assertTrue(self.a.in_melee)
            self.battle.tick_count += 1
        combat.resolve_contacts(self.battle)
        self.assertEqual(self.queued("a"), [ALONE_ON_GRID_EVENT])

    def test_0x30_repeats_every_tick_until_the_script_leaves_the_grid(self):
        self.state("a").current_target = None
        self.next_segment()
        combat.start_rout(self.e, self.battle)
        self.clear_queues()
        for _ in range(3):
            combat.resolve_contacts(self.battle)
        self.assertEqual(self.queued("a"), [ALONE_ON_GRID_EVENT] * 3)
        self.interp.op_LeaveSharedGrid(self.state("a"), None, [], "a", 0, self.battle.rng)
        self.clear_queues()
        combat.resolve_contacts(self.battle)
        self.assertFalse(self.a.in_melee)
        self.assertEqual(self.queued("a"), [])

    def test_vector_1_the_routed_target_is_left_to_the_rout_handler(self):
        self.state("a").current_target = ("e", 0)
        self.next_segment()
        combat.start_rout(self.e, self.battle)
        combat.resolve_contacts(self.battle)
        self.assertEqual(self.queued("a"), [0x0F])  # handled before any pairing step: no 0x30, no 0x19
        self.assertTrue(self.a.in_melee)

    def test_vector_4_a_wiped_out_target_holds_the_unit_until_its_removal_is_handled(self):
        self.state("a").current_target = ("e", 0)
        self.next_segment()
        self.e.models = 0
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.a.in_melee)
        self.assertEqual(self.queued("a"), [])  # still collapsing: on the grid until the 0x16 broadcast
        self.battle._announce_removal(self.e)
        combat.resolve_contacts(self.battle)
        self.assertEqual(self.queued("a"), [0x16])  # Query 22 decides first
        self.assertTrue(self.a.in_melee)

    def test_vector_5_a_wiped_out_enemy_that_was_not_the_target_leaves_the_unit_alone(self):
        self.state("a").current_target = None
        self.next_segment()
        self.e.models = 0
        self.battle._announce_removal(self.e)
        self.clear_queues()
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.a.in_melee)
        self.assertEqual(self.queued("a"), [ALONE_ON_GRID_EVENT])

    def test_vector_6_a_quiet_script_removal_leaves_the_unit_alone_whatever_its_target(self):
        self.state("a").current_target = ("e", 0)
        self.next_segment()
        self.battle.remove_from_play(self.e)
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.a.in_melee)
        self.assertEqual(self.queued("a"), [ALONE_ON_GRID_EVENT])


class FriendsLeftOnTheGridTests(Case):
    """Vectors 7 and 8: A and B (mine) and router R; targets none."""

    def setUp(self):
        self.a = unit("a", 480, 500, Side.PLAYER)
        self.b = unit("b", 530, 500, Side.PLAYER)
        self.r = unit("r", 505, 512, Side.ENEMY, direction=256)
        self.build(self.a, self.b, self.r)
        self.engage(self.a, self.r)
        self.assertTrue(self.interp._engage(self.b, self.r))
        combat.resolve_contacts(self.battle)
        self.assertEqual(self.a.melee_group, self.b.melee_group)
        self.grid = self.battle.fights[self.a.melee_group]["grid"]
        self.state("a").current_target = self.state("b").current_target = None
        self.next_segment()
        self.clear_queues()

    def test_vector_7_the_joiner_first_in_unit_order_leaves_with_no_target_the_owner_is_then_alone(self):
        self.grid.owner_id = "b"
        combat.start_rout(self.r, self.battle)
        self.clear_queues()
        combat.resolve_contacts(self.battle)
        self.assertFalse(self.a.in_melee)
        self.assertIsNone(self.a.melee_group)
        self.assertIsNone(self.state("a").current_target)
        self.assertEqual(self.queued("a"), [ALONE_ON_GRID_EVENT])  # deviation: the original sends 0x19
        self.assertTrue(self.b.in_melee)
        self.assertEqual(self.queued("b"), [ALONE_ON_GRID_EVENT])

    def test_vector_8_an_owner_with_no_target_does_nothing_until_it_is_alone(self):
        self.grid.owner_id = "a"
        combat.start_rout(self.r, self.battle)
        self.clear_queues()
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.a.in_melee)
        self.assertEqual(self.queued("a"), [])
        self.assertFalse(self.b.in_melee)
        self.assertEqual(self.queued("b"), [ALONE_ON_GRID_EVENT])  # deviation: the original sends 0x19
        combat.resolve_contacts(self.battle)
        self.assertEqual(self.queued("a"), [ALONE_ON_GRID_EVENT])


class StuckUnitTests(Case):
    """The engine used to drop a unit out of melee silently when a non-target opponent routed, leaving its script in
    the in-melee idle loop for good; now its library 0x30 handling re-forms it (report section 7, row (c))."""

    def test_a_unit_whose_untargeted_opponent_routs_leaves_the_grid_and_re_forms(self):
        handler = [word("PushPC"), word("GetEvent"),
                   word("CaseEvent"), 48, word("LeaveSharedGrid"), word("SwitchScript"), 163, word("Break"),
                   behaviour.BREAK_LABEL, behaviour.LABEL, word("ConsumeEvent"), word("LoopIfTrue"),
                   word("ReturnInterrupt"), behaviour.END]
        a = unit("a", 500, 500, Side.PLAYER)
        e = unit("e", 500, 512, Side.ENEMY, direction=256)
        self.build(a, e, scripts={**ROUT_SCRIPTS, 151: handler})
        self.engage(e, a)
        self.state("a").current_target = None
        combat.start_rout(e, self.battle)
        for _ in range(SEGMENT_TICKS + 2):
            self.battle.tick()
        self.assertFalse(a.in_melee)
        self.assertEqual(self.state("a").script_id, 163)


class LeaverReFormsTests(Case):
    """The deviation end to end: the unit that leaves a grid with friends still on it re-forms (163)."""

    def test_both_friends_end_in_the_re_form_script_once_their_router_has_gone(self):
        handler = [word("PushPC"), word("GetEvent"),
                   word("CaseEvent"), 48, word("LeaveSharedGrid"), word("SwitchScript"), 163, word("Break"),
                   behaviour.BREAK_LABEL, behaviour.LABEL, word("ConsumeEvent"), word("LoopIfTrue"),
                   word("ReturnInterrupt"), behaviour.END]
        a, b = unit("a", 480, 500, Side.PLAYER), unit("b", 530, 500, Side.PLAYER)
        r = unit("r", 505, 512, Side.ENEMY, direction=256)
        self.build(a, b, r, scripts={**ROUT_SCRIPTS, 151: handler})
        self.engage(a, r)
        self.assertTrue(self.interp._engage(b, r))
        combat.resolve_contacts(self.battle)
        self.state("a").current_target = self.state("b").current_target = None
        combat.start_rout(r, self.battle)
        for _ in range(2 * SEGMENT_TICKS):
            self.battle.tick()
        self.assertFalse(a.in_melee or b.in_melee)
        self.assertEqual((self.state("a").script_id, self.state("b").script_id), (163, 163))


if __name__ == "__main__":
    unittest.main()
