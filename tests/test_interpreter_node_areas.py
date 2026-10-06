"""Node-area queries IfInNodeArea, IfAnyUnitInNodeArea, IfSideUnitInNodeArea
(notes/threat_events_nodes.md, part C). Vectors are the report's section 5 tables."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.nodes import ScriptNode
from whshr.rules import Side

END = behaviour.END
# Node positions 0..23 of the vectors: 3 = (920, 540) r 66, 5 = (100, 100) r 16, 23 = (1444, 684) r 686;
# node 4 has id 3, so a lookup by `id` instead of position would pick the wrong circle.
NODES = [ScriptNode(0.0, 0.0, 0, 0)] * 24
NODES[3] = ScriptNode(920.0, 540.0, 0, 66)
NODES[4] = ScriptNode(5000.0, 5000.0, 3, 10)
NODES[5] = ScriptNode(100.0, 100.0, 0, 16)
NODES[23] = ScriptNode(1444.0, 684.0, 0, 686)


class NodeAreaTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = Regiment("r", "Runner", 3000, 3000, 0, Side.ENEMY, models=5, ranks=1)
        self.other = Regiment("o", "Other", 3500, 3500, 0, Side.PLAYER, models=5, ranks=1)
        self.battle = Battle(6000, 6000, [self.runner, self.other], seed=1995, script_nodes=NODES)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["r"]

    def cond(self, name, *operands):
        words = [word(name), *operands]
        self.state.pc = 0
        getattr(self.interp, "op_" + name)(self.state, operands[0], words, "r", 0, None)
        return bool(self.state.cond_flags)

    def place(self, regiment, x, y):
        regiment.x, regiment.y = float(x), float(y)


class IfInNodeAreaTests(NodeAreaTestCase):
    def test_vectors(self):
        rows = [((899, 572), 3, True), ((116, 101), 5, False), ((116, 100), 5, True)]
        for position, node, expected in rows:
            with self.subTest(position=position, node=node):
                self.place(self.runner, *position)
                self.assertEqual(self.cond("IfInNodeArea", node), expected)

    def test_node_is_a_file_position_not_its_id(self):
        self.place(self.runner, 920, 540)
        self.assertTrue(self.cond("IfInNodeArea", 3))
        self.assertFalse(self.cond("IfInNodeArea", 4))

    def test_missing_node_is_false(self):
        self.place(self.runner, 0, 0)
        self.assertFalse(self.cond("IfInNodeArea", 99))

    def test_writes_false_over_a_true_condition_inside_a_script(self):
        self.state.script_id, self.state.pc = 1, 0
        self.state.script_dll = FakeDll([word("SetCondFlags"), 4, word("IfInNodeArea"), 3,
                                         word("SendEventSelfIfFalse"), 9, END])
        self.interp.run("r", self.state, 1, self.battle.rng)
        self.assertEqual([event.code for event in self.state.event_queue], [9])


class IfAnyUnitInNodeAreaTests(NodeAreaTestCase):
    def test_any_side_counts(self):
        self.place(self.other, 899, 572)
        self.assertTrue(self.cond("IfAnyUnitInNodeArea", 3))

    def test_running_unit_counts(self):
        self.place(self.runner, 920, 540)
        self.assertTrue(self.cond("IfAnyUnitInNodeArea", 3))

    def test_routed_unit_on_the_field_counts_but_one_that_fled_off_does_not(self):
        self.place(self.other, 930, 560)
        self.other.routing = True
        self.assertTrue(self.cond("IfAnyUnitInNodeArea", 3))
        self.other.fled = True
        self.assertFalse(self.cond("IfAnyUnitInNodeArea", 3))

    def test_hidden_unit_counts(self):
        self.place(self.other, 930, 560)
        self.other.hidden = True
        self.assertTrue(self.cond("IfAnyUnitInNodeArea", 3))


class IfSideUnitInNodeAreaTests(NodeAreaTestCase):
    def test_player_unit_inside_and_skips_four_words(self):
        self.place(self.other, 2000, 800)
        self.assertTrue(self.cond("IfSideUnitInNodeArea", 0, 23, 0x2000))
        self.assertEqual(self.interp.op_IfSideUnitInNodeArea(
            self.state, 0, [word("IfSideUnitInNodeArea"), 0, 23, 0x2000], "r", 0, None), 4)

    def test_broken_unit_is_excluded_only_when_asked(self):
        self.place(self.other, 2000, 800)
        self.other.routing = True
        self.assertFalse(self.cond("IfSideUnitInNodeArea", 0, 23, 0x2000))
        self.assertTrue(self.cond("IfSideUnitInNodeArea", 0, 23, 0))

    def test_side_is_absolute_not_relative_to_the_caller(self):
        cart = Regiment("c", "Cart", 2100, 801, 0, Side.NEUTRAL, models=1, ranks=1)
        self.battle = Battle(6000, 6000, [self.runner, cart], seed=1995, script_nodes=NODES)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["r"]
        self.place(self.runner, 1444, 684)
        self.assertFalse(self.cond("IfSideUnitInNodeArea", 0, 23, 0x2000))
        self.assertTrue(self.cond("IfSideUnitInNodeArea", 64, 23, 0x2000))
        self.assertTrue(self.cond("IfSideUnitInNodeArea", 128, 23, 0x2000))  # the running enemy unit itself

    def test_side_code_with_low_bits_never_matches(self):
        self.place(self.runner, 1444, 684)
        self.assertFalse(self.cond("IfSideUnitInNodeArea", 129, 23, 0))

    def test_hidden_exclusion(self):
        self.place(self.other, 2000, 800)
        self.other.hidden = True
        self.assertFalse(self.cond("IfSideUnitInNodeArea", 0, 23, 0x80000))


if __name__ == "__main__":
    unittest.main()
