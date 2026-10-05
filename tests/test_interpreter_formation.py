"""Formation, rally and grid opcodes (notes/movement_formation.md Part B), using the report's vectors."""

import unittest
import unittest.mock

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side


class FormationTestCase(unittest.TestCase):
    def build(self, models=18, ranks=6, script_ranks=4, side=Side.ENEMY, with_other=False):
        self.unit = Regiment("u", "U", 0, 0, 0, side, models=models, ranks=ranks)
        self.unit.script_ranks = script_ranks
        regiments = [self.unit]
        if with_other:
            self.other = Regiment("x", "X", 300, 0, 256, Side.PLAYER, models=10, ranks=2)
            regiments.append(self.other)
        self.battle = Battle(3000, 3000, regiments, seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["u"]

    def op(self, name, operand=None):
        pc = self.state.pc
        result = getattr(self.interp, "op_" + name)(self.state, operand, [], "u", 0, None)
        return result - pc


class ReformTests(FormationTestCase):
    def test_reform_to_script_ranks_vectors(self):
        self.build(models=18, ranks=6, script_ranks=4)
        self.op("ReformToScriptRanks")
        self.assertEqual((self.unit.ranks, self.unit.frontage, self.unit.reforming), (4, 5, True))
        self.build(models=18, ranks=3, script_ranks=8)
        self.op("ReformToScriptRanks")
        self.assertEqual((self.unit.ranks, self.unit.frontage), (6, 3))  # clamped to 18 div 3

    def test_reform_is_refused_while_charging_routing_held_or_in_a_fight(self):
        for refusal in ("attack_target", "routing", "held", "in_melee"):
            self.build()
            setattr(self.unit, refusal, "x" if refusal == "attack_target" else True)
            self.op("ReformToScriptRanks")
            self.assertEqual(self.unit.ranks, 6, refusal)
            self.assertFalse(self.unit.reforming, refusal)

    def test_reform_does_not_halt_or_write_the_condition(self):
        self.build()
        self.unit.target_x, self.unit.target_y = 100.0, 50.0
        self.state.cond_flags = True
        self.op("ReformToScriptRanks")
        self.assertEqual((self.unit.target_x, self.unit.target_y), (100.0, 50.0))
        self.assertTrue(self.state.cond_flags)

    def test_set_ranks_vectors(self):
        self.build(models=16, ranks=4)
        self.assertEqual(self.op("SetRanks", 6), 2)
        self.assertEqual((self.unit.ranks, self.unit.frontage), (6, 3))
        self.assertEqual(self.unit.script_ranks, 4)  # the script's own count is untouched
        self.build(models=16, ranks=4)
        self.unit.held = True
        self.op("SetRanks", 6)
        self.assertEqual(self.unit.ranks, 4)

    def test_wait_while_reforming_follows_the_reform(self):
        self.build()
        self.op("ReformToScriptRanks")
        self.interp._mirror_engine_flags("u", self.state)
        self.assertTrue(self.state.unit_flags & interpreter.REFORMING_FLAG)
        self.unit.reforming = False
        self.interp._mirror_engine_flags("u", self.state)
        self.assertFalse(self.state.unit_flags & interpreter.REFORMING_FLAG)

    def test_reinforcement_idiom_runs_end_to_end(self):
        """ReformToScriptRanks; ResetModelAnimations; Yield; WaitWhileUnitFlags 8 holds until settled."""
        self.build()
        self.state.script_id = 1
        self.state.script_dll = FakeDll([word("ReformToScriptRanks"), word("ResetModelAnimations"), word("Yield"),
                                         word("WaitWhileUnitFlags"), 8, word("SetUnitFlags2"), 0x40,
                                         behaviour.END])
        self.interp.run("u", self.state, 1, self.battle.rng)   # tick 1: re-form starts, then Yield
        self.assertEqual(self.state.unit_flags2, 0)
        self.interp.run("u", self.state, 2, self.battle.rng)   # tick 2: still re-forming, the wait holds
        self.assertEqual(self.state.unit_flags2, 0)
        self.unit.reforming = False                            # the models settle
        self.interp.run("u", self.state, 3, self.battle.rng)
        self.assertEqual(self.state.unit_flags2, 0x40)


class StaggerTests(FormationTestCase):
    def test_pause_lengths_follow_the_stagger_number(self):
        self.build(models=2, ranks=1)
        self.unit.model_positions()
        for model, stagger in zip(self.unit.melee_models, (0x0007, 0x001D)):
            model.stagger = stagger
        self.op("ResetModelAnimations")
        self.assertEqual([m.freeze_ticks for m in self.unit.melee_models], [16, 28])

    def test_pauses_are_even_and_between_2_and_32(self):
        self.build(models=16, ranks=4)
        self.op("ResetModelAnimations")
        for model in self.unit.melee_models:
            self.assertIn(model.freeze_ticks, range(2, 33, 2))


class RallyTests(FormationTestCase):
    def test_rally_vector(self):
        self.build(models=16, ranks=4, script_ranks=4)
        self.unit.routing = True
        self.unit.rally_next_segment = 5
        self.unit.target_x, self.unit.target_y = 90.0, 90.0
        self.unit.braced = True
        self.state.cond_flags = True
        self.assertEqual(self.op("Rally"), 1)
        self.assertFalse(self.unit.routing)
        self.assertFalse(self.unit.braced)
        self.assertIsNone(self.unit.target_x)
        self.assertEqual((self.unit.ranks, self.unit.frontage), (4, 4))
        self.assertTrue(self.state.cond_flags)

    def test_rally_while_held_yields_without_advancing(self):
        self.build(models=16, ranks=4)
        self.unit.routing = True
        self.unit.held = True
        self.interp._should_yield = False
        self.assertEqual(self.op("Rally"), 0)
        self.assertTrue(self.interp._should_yield)
        self.assertFalse(self.unit.routing)

    def test_rally_keeps_the_target_and_the_fight(self):
        self.build(with_other=True)
        self.state.current_target = ("x", 0)
        self.unit.in_melee = True
        self.op("Rally")
        self.assertEqual(self.state.current_target, ("x", 0))
        self.assertTrue(self.unit.in_melee)

    def test_rally_clears_a_models_pause(self):
        self.build(models=4, ranks=2)
        self.op("ResetModelAnimations")
        self.op("Rally")
        self.assertTrue(all(m.freeze_ticks == 0 for m in self.unit.melee_models))


class FlankRearTests(FormationTestCase):
    def charged_by(self, charger_at, passed):
        self.build(models=16, ranks=4, with_other=True)  # u faces +Y at (0,0)
        self.other.x, self.other.y = charger_at
        self.state.current_event = Event(code=8, source="x")
        with unittest.mock.patch("whshr.combat.leadership_test", return_value=passed) as test:
            self.op("FlankRearTest")
        return test

    def test_frontal_charge_needs_no_test(self):
        test = self.charged_by((0, 300), passed=False)
        self.assertTrue(self.state.cond_flags)
        test.assert_not_called()
        self.assertEqual(len(self.state.event_queue), 0)

    def test_rear_charge_is_tested_and_failure_routs_the_unit(self):
        test = self.charged_by((0, -300), passed=False)
        test.assert_called_once()
        self.assertFalse(self.state.cond_flags)
        self.assertEqual([e.code for e in self.state.event_queue], [0x0C])

    def test_rear_charge_passes_the_test(self):
        self.charged_by((0, -300), passed=True)
        self.assertTrue(self.state.cond_flags)
        self.assertEqual(len(self.state.event_queue), 0)

    def test_no_sender_means_no_test(self):
        self.build()
        self.state.cond_flags = False
        self.op("FlankRearTest")
        self.assertTrue(self.state.cond_flags)


class GridTests(FormationTestCase):
    def engaged(self):
        self.build(with_other=True)
        self.state.current_target = ("x", 0)
        self.unit.in_melee = True
        self.unit.melee_group = "g"
        self.unit.melee_touching = frozenset({"x"})

    def test_leave_shared_grid_reports_that_it_left(self):
        self.engaged()
        self.op("LeaveSharedGrid")
        self.assertTrue(self.state.cond_flags)
        self.assertFalse(self.unit.in_melee)
        self.assertIsNone(self.unit.melee_group)
        self.assertEqual(self.state.current_target, ("x", 0))  # the target is kept

    def test_leave_shared_grid_off_the_grid_is_false_and_changes_nothing(self):
        self.build()
        self.state.cond_flags = True
        self.op("LeaveSharedGrid")
        self.assertFalse(self.state.cond_flags)

    def test_leave_grid_does_not_write_the_condition(self):
        self.engaged()
        self.state.cond_flags = False
        self.op("LeaveGrid")
        self.assertFalse(self.unit.in_melee)
        self.assertFalse(self.state.cond_flags)

    def test_if_engaged_with_kind_is_false_for_regiments(self):
        self.engaged()
        self.state.cond_flags = True
        self.assertEqual(self.op("IfEngagedWithKind", 128), 2)
        self.assertFalse(self.state.cond_flags)


if __name__ == "__main__":
    unittest.main()
