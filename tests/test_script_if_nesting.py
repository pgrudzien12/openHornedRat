"""If/IfNot blocks nest: a false condition skips to the Else or EndIf of its own block, never to one that
belongs to an If nested inside it (the shooting step of the shared fire loop has exactly this shape)."""

import unittest

from whshr import interpreter

from tests.script_helpers import word


def _nested_script() -> list[int]:
    # 0 If / 1 If / 2 Yield / 3 Else / 4 Yield / 5 EndIf / 6 Else / 7 Yield / 8 EndIf / 9 Yield
    return [word("If"), word("If"), word("Yield"), word("Else"), word("Yield"), word("EndIf"),
            word("Else"), word("Yield"), word("EndIf"), word("Yield")]


class FalseIfSkipsItsOwnBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.interp = interpreter.ScriptInterpreter(None, None, None)
        self.state = interpreter.UnitScriptState()
        self.state.pc = 0

    def test_given_a_false_if_wrapping_a_nested_if_else_then_it_jumps_to_its_own_else(self) -> None:
        self.state.cond_flags = 0
        self.assertEqual(self.interp.op_If(self.state, None, _nested_script(), "u", 0, None), 7)

    def test_given_a_true_ifnot_wrapping_a_nested_if_else_then_it_jumps_to_its_own_else(self) -> None:
        self.state.cond_flags = 1
        self.assertEqual(self.interp.op_IfNot(self.state, None, _nested_script(), "u", 0, None), 7)

    def test_given_a_false_inner_if_then_it_jumps_to_the_inner_else(self) -> None:
        self.state.pc, self.state.cond_flags = 1, 0
        self.assertEqual(self.interp.op_If(self.state, None, _nested_script(), "u", 0, None), 4)

    def test_given_a_false_if_without_else_then_it_jumps_past_its_endif(self) -> None:
        script = [word("If"), word("If"), word("Else"), word("EndIf"), word("EndIf"), word("Yield")]
        self.state.cond_flags = 0
        self.assertEqual(self.interp.op_If(self.state, None, script, "u", 0, None), 5)

    def test_given_a_true_if_then_it_falls_through(self) -> None:
        self.state.cond_flags = 1
        self.assertEqual(self.interp.op_If(self.state, None, _nested_script(), "u", 0, None), 1)


if __name__ == "__main__":
    unittest.main()
