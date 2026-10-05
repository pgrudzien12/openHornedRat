"""SkipIfTrue: conditional forward skip by a count of words (notes/skip_if_true.md)."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side

class SkipIfTrueTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, Side.ENEMY, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["t"]
        self.state.script_id = 1

    def run_script(self, cond, words):
        self.state.script_dll = FakeDll(words + [behaviour.END])
        self.state.pc = 0
        # The condition is reset at every tick start, so scripts set it themselves.
        if cond:
            self.state.script_dll = FakeDll([word("SetCondFlags"), 4] + words + [behaviour.END])
        self.interp.run("t", self.state, 1, self.battle.rng)

    def marker(self, bit):
        return [word("SetUnitFlags2"), bit]

    def test_true_condition_skips_exactly_n_words(self):
        # Skip one two-word marker (N = 2): only the second marker runs.
        self.run_script(1, [word("SkipIfTrue"), 2] + self.marker(0x10) + self.marker(0x20))
        self.assertEqual(self.state.unit_flags2, 0x20)

    def test_false_condition_runs_the_following_words(self):
        self.run_script(0, [word("SkipIfTrue"), 2] + self.marker(0x10) + self.marker(0x20))
        self.assertEqual(self.state.unit_flags2, 0x30)

    def test_n_counts_words_not_instructions(self):
        # Two two-word markers are four words, so N = 4 (not 2) skips both.
        self.run_script(1, [word("SkipIfTrue"), 4] + self.marker(0x10) + self.marker(0x20) + self.marker(0x40))
        self.assertEqual(self.state.unit_flags2, 0x40)

    def test_zero_is_a_no_op(self):
        self.run_script(1, [word("SkipIfTrue"), 0] + self.marker(0x10))
        self.assertEqual(self.state.unit_flags2, 0x10)

    def test_condition_is_not_consumed(self):
        for cond in (0, 1):
            self.run_script(cond, [word("SkipIfTrue"), 0])
            self.assertEqual(bool(self.state.cond_flags), bool(cond))

    def test_negative_n_jumps_backwards_over_already_run_words(self):
        # Marker, then clear cond and re-enter: SkipIfTrue -4 would loop forever if cond stayed true,
        # so only check the handler's landing point.
        self.state.pc = 6
        self.state.cond_flags = 1
        self.assertEqual(self.interp.op_SkipIfTrue(self.state, 0xFFFC, [], "t", 0, None), 4)

    def test_library_script_162_shape(self):
        """FleeFromTarget; SkipIfTrue 1; FleeAhead; PushPC ...: true lands on PushPC (word 4)."""
        words = [word("FleeFromTarget"), word("SkipIfTrue"), 1, word("FleeAhead"), word("PushPC")]
        self.state.pc = 1
        self.state.cond_flags = 1
        self.assertEqual(self.interp.op_SkipIfTrue(self.state, 1, words, "t", 0, None), 4)
        self.state.cond_flags = 0
        self.assertEqual(self.interp.op_SkipIfTrue(self.state, 1, words, "t", 0, None), 3)


if __name__ == "__main__":
    unittest.main()
