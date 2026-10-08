"""TakeEventTarget, ChargeForward, CheckCollisions and SwitchOpponentInGrid (notes/script_grid_events.md).

Vectors follow the report's tables: unit A at (0, 0), enemy block B at (0, 200) facing A.
"""

import unittest
from unittest import mock

from whshr import behaviour, interpreter, navigation
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side


def take_words(opcode):
    return [behaviour.OPCODE_FLAG | opcode]


class GridTestCase(unittest.TestCase):
    def setUp(self):
        self.a = Regiment("A", "A", 0, 0, 0, Side.PLAYER, models=10, ranks=2, unit_class=5)
        self.b = Regiment("B", "B", 0, 200, 256, Side.ENEMY, models=10, ranks=2)
        self.c = Regiment("C", "C", 300, 0, 0, Side.ENEMY, models=10, ranks=2)
        self.battle = Battle(2000, 2000, [self.a, self.b, self.c], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["A"]

    def take(self, event, opcode=0x3A):
        self.state.current_event = event
        self.state.pc = 0
        self.interp.op_TakeEventTarget(self.state, None, take_words(opcode), "A", 0, None)
        return bool(self.state.cond_flags)

    def target(self):
        return self.state.current_target[0] if self.state.current_target else None


class TakeEventTargetTests(GridTestCase):
    def test_distinct_opcode_names_dispatch_to_the_shared_rule(self):
        self.assertEqual(
            [behaviour.opcode_name(opcode) for opcode in (0x3A, 0x88, 0xAF)],
            ["TakeEventTarget", "TakeRangedEventTarget", "TakeSpellEventTarget"],
        )
        for opcode, event in ((0x88, Event(code=0x1F, source="B")),
                              (0xAF, Event(code=0x2B, parameter=22, x=5, y=5))):
            with self.subTest(opcode=opcode):
                self.setUp()
                self.state.current_event = event
                self.assertEqual(self.interp._dispatch(
                    self.state, opcode, take_words(opcode), "A", 0, self.battle.rng), 1)
                self.assertTrue(self.state.cond_flags)

    def test_attack_event_takes_the_source_and_drops_a_pending_spell(self):
        self.a.braced = True
        self.state.pending_spell = 22
        self.assertTrue(self.take(Event(code=0x04, source="B")))
        self.assertEqual((self.target(), self.a.braced, self.state.pending_spell), ("B", False, None))
        self.assertIsNotNone(self.state.approach_point)

    def test_attack_event_from_a_broken_unit_is_refused_by_0x3a_only(self):
        self.b.routing = True
        self.assertFalse(self.take(Event(code=0x04, source="B")))
        self.assertIsNone(self.target())
        self.assertTrue(self.take(Event(code=0x1F, source="B"), opcode=0x88))
        self.assertEqual(self.target(), "B")

    def test_a_busy_taker_refuses_but_the_pending_spell_is_still_overwritten(self):
        for busy in ("attack_target", "in_melee", "routing"):
            with self.subTest(busy=busy):
                self.setUp()
                setattr(self.a, busy, "C" if busy == "attack_target" else True)
                self.state.current_target, self.state.pending_spell = ("C", 0), 22
                self.assertFalse(self.take(Event(code=0x04, source="B")))
                self.assertEqual((self.target(), self.state.pending_spell), ("C", None))

    def test_cast_order_is_a_ground_order_even_in_melee(self):
        self.a.in_melee = True
        self.state.current_target = ("C", 0)
        self.assertTrue(self.take(Event(code=0x2B, parameter=22, x=5, y=5), opcode=0xAF))
        self.assertEqual((self.target(), self.state.target_point, self.state.pending_spell), (None, (5.0, 5.0), 22))

    def test_item_marked_ground_order_keeps_an_existing_target(self):
        self.state.current_target = ("C", 0)
        self.assertTrue(self.take(Event(code=0x2D, parameter=0x105, x=10, y=10), opcode=0xAF))
        self.assertEqual((self.target(), self.state.target_point, self.state.pending_spell), ("C", None, 0x105))
        self.state.current_target = None
        self.take(Event(code=0x2D, parameter=0x105, x=10, y=10), opcode=0xAF)
        self.assertEqual(self.state.target_point, (10.0, 10.0))

    def test_self_click_with_minus_one_keeps_the_target(self):
        self.state.current_target = ("C", 0)
        self.assertTrue(self.take(Event(code=0x2A, parameter=-1, x=-1, y=-1), opcode=0xAF))
        self.assertEqual((self.target(), self.state.pending_spell), ("C", None))

    def test_deployment_changes_nothing(self):
        self.battle.phase = "deployment"
        self.state.pending_spell = 22
        self.assertFalse(self.take(Event(code=0x04, source="B")))
        self.assertEqual((self.target(), self.state.pending_spell), (None, 22))


class ChargeForwardTests(GridTestCase):
    def test_charges_twelve_times_s_rlmv_ahead_and_clears_fear_passed(self):
        self.a.direction = 128
        self.state.fear_passed = True
        with mock.patch.object(interpreter.ScriptInterpreter, "_s_rlmv", staticmethod(lambda unit: 11)):
            self.interp.op_ChargeForward(self.state, None, [], "A", 0, None)
        self.assertEqual((self.a.target_x, self.a.target_y), (132, 0))
        self.assertEqual((bool(self.state.cond_flags), self.state.fear_passed), (True, False))
        self.assertEqual([event.code for event in self.battle.event_bus.unit_states["B"].event_queue], [])

    def test_anchored_unit_refuses(self):
        self.a.hud_class = "art"
        self.interp.op_ChargeForward(self.state, None, [], "A", 0, None)
        self.assertFalse(self.state.cond_flags)

    def square(self, flag, x1=-50, y1=-50, x2=50, y2=50):
        return {"status": ["bnd_ACTIVE", flag],
                "lines": [[x1, y1, x2, y1], [x2, y1, x2, y2], [x2, y2, x1, y2], [x1, y2, x1, y1]]}

    def charge_forward(self, boundaries):
        self.battle.navigation_boundaries = navigation.boundaries_from_views(boundaries)
        self.interp.op_ChargeForward(self.state, None, [], "A", 0, None)

    def test_unit_inside_an_inverse_solid_area_halts_and_reforms_without_charging(self):
        self.charge_forward([self.square("bnd_INVSOLID")])
        self.assertFalse(self.state.cond_flags)
        self.assertIsNone(self.a.target_x)
        self.assertFalse(self.a.free_charging)

    def test_unit_outside_a_solid_area_is_refused(self):
        self.charge_forward([self.square("bnd_SOLID", 500, 500, 600, 600)])
        self.assertFalse(self.state.cond_flags)
        self.assertFalse(self.a.free_charging)

    def test_unit_outside_the_battle_edge_is_refused(self):
        self.charge_forward([self.square("bnd_BATTLEEDGE", 500, 500, 600, 600)])
        self.assertFalse(self.state.cond_flags)

    def test_unit_on_open_ground_inside_solid_and_edge_areas_charges(self):
        self.charge_forward([self.square("bnd_SOLID"), self.square("bnd_BATTLEEDGE")])
        self.assertTrue(self.state.cond_flags)
        self.assertTrue(self.a.free_charging)

    def test_sight_edge_and_line_boundaries_do_not_block(self):
        self.charge_forward([self.square("bnd_SIGHTEDGE", 500, 500, 600, 600)])
        self.assertTrue(self.state.cond_flags)


class CheckCollisionsTests(GridTestCase):
    def test_nothing_touching_is_false(self):
        self.interp.op_CheckCollisions(self.state, None, [], "A", 0, None)
        self.assertFalse(self.state.cond_flags)

    def test_touching_a_terror_enemy_targets_it_and_queues_flight_without_engaging(self):
        self.b.y, self.b.psychology = 5, frozenset({"CauseTerror"})
        self.interp.op_CheckCollisions(self.state, None, [], "A", 0, self.battle.rng)
        self.assertEqual((bool(self.state.cond_flags), self.target()), (True, "B"))
        self.assertEqual([event.code for event in self.state.event_queue], [0x0D])
        self.assertFalse(self.a.in_melee)


class SwitchOpponentTests(GridTestCase):
    def test_switches_to_the_first_other_enemy_in_the_same_fight(self):
        for unit in (self.a, self.b, self.c):
            unit.in_melee, unit.melee_group = True, "g"
        self.state.current_target = ("B", 0)
        self.interp.op_SwitchOpponentInGrid(self.state, None, [], "A", 0, None)
        self.assertEqual((self.target(), bool(self.state.cond_flags)), ("C", True))

    def test_no_other_enemy_is_false(self):
        self.a.in_melee, self.a.melee_group = True, "g"
        self.b.in_melee, self.b.melee_group = True, "g"
        self.state.current_target = ("B", 0)
        self.interp.op_SwitchOpponentInGrid(self.state, None, [], "A", 0, None)
        self.assertFalse(self.state.cond_flags)

    def test_outside_melee_the_condition_is_not_written(self):
        self.state.cond_flags = 1
        self.interp.op_SwitchOpponentInGrid(self.state, None, [], "A", 0, None)
        self.assertTrue(self.state.cond_flags)


if __name__ == "__main__":
    unittest.main()
