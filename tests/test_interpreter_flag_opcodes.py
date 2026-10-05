"""Secondary unit flags, WaitWhileUnitFlags, YieldIfTrue and Nop (issue #3, mission_scripts.md).

Behaviour comes from the opcode names and the public control-opcode summary in game_rules.md; the
multi-bit mask semantics of the Wait* family stay PROVISIONAL (see the handler docstrings).
"""

import unittest

from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class FlagOpcodeTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, Side.ENEMY, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["t"]
        self.interp._should_yield = False

    def call(self, name, operand=None):
        return getattr(self.interp, "op_" + name)(self.state, operand, [], "t", 0, None)

    def test_flags2_set_test_clear_round_trip(self):
        self.call("SetUnitFlags2", 0x21)
        self.assertEqual(self.state.unit_flags2, 0x21)
        self.call("TestUnitFlags2", 0x20)
        self.assertTrue(self.state.cond_flags)
        self.call("ClearUnitFlags2", 0x20)
        self.call("TestUnitFlags2", 0x20)
        self.assertFalse(self.state.cond_flags)
        self.assertEqual(self.state.unit_flags2, 0x01)

    def test_flags2_do_not_touch_primary_flags(self):
        self.call("SetUnitFlags2", 0x8)
        self.assertEqual(self.state.unit_flags, 0)

    def test_wait_while_unit_flags_blocks_until_cleared(self):
        self.state.unit_flags = 8
        self.assertEqual(self.call("WaitWhileUnitFlags", 8), self.state.pc)
        self.assertTrue(self.interp._should_yield)
        self.interp._should_yield = False
        self.state.unit_flags = 0
        self.assertEqual(self.call("WaitWhileUnitFlags", 8), self.state.pc + 2)
        self.assertFalse(self.interp._should_yield)

    def test_flags2_waits_are_mirror_images(self):
        self.assertEqual(self.call("WaitUntilUnitFlags2", 4), self.state.pc)
        self.assertEqual(self.call("WaitWhileUnitFlags2", 4), self.state.pc + 2)
        self.state.unit_flags2 = 4
        self.assertEqual(self.call("WaitUntilUnitFlags2", 4), self.state.pc + 2)
        self.assertEqual(self.call("WaitWhileUnitFlags2", 4), self.state.pc)

    def test_yield_if_true_only_yields_on_true(self):
        self.state.cond_flags = 0
        self.assertEqual(self.call("YieldIfTrue"), self.state.pc + 1)
        self.assertFalse(self.interp._should_yield)
        self.state.cond_flags = 1
        self.assertEqual(self.call("YieldIfTrue"), self.state.pc + 1)
        self.assertTrue(self.interp._should_yield)

    def test_nop_advances_only(self):
        self.assertEqual(self.call("Nop"), self.state.pc + 1)
        self.assertFalse(self.interp._should_yield)


if __name__ == "__main__":
    unittest.main()
