"""Condition word, repeat loops, event queue opcodes and IfGotoScript (notes/unit_script_control.md).

Vectors are the report's before/instruction/after tables; end-to-end tests run real word sequences
through ScriptInterpreter.run.
"""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side

END = behaviour.END


class ControlTestCase(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, Side.ENEMY, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["t"]
        self.state.script_id = 1
        self.counts = {}

    def call(self, name, operand=None):
        return getattr(self.interp, "op_" + name)(self.state, operand, [], "t", 0, None)

    def run_words(self, words, scripts=None):
        self.state.script_dll = FakeDll(scripts if scripts is not None else words + [END])
        self.state.pc = 0
        self.interp.run("t", self.state, 1, self.battle.rng)

    def count(self, name):
        """Count how often the named opcode's handler runs from now on."""
        original = getattr(self.interp, "op_" + name)

        def counting(*args):
            self.counts[name] = self.counts.get(name, 0) + 1
            return original(*args)
        setattr(self.interp, "op_" + name, counting)


class ConditionWordTests(ControlTestCase):
    def test_set_clear_test_vectors(self):
        rows = [(0x0018, "SetCondFlags", 4, 0x001C), (0x001C, "SetCondFlags", 0x8001, 0x0001),
                (0x001C, "ClearCondFlags", 8, 0x0014)]
        for before, name, operand, after in rows:
            self.state.cond_bits = before
            self.call(name, operand)
            self.assertEqual(self.state.cond_bits, after, (before, name, operand))

    def test_test_cond_flags_is_any_bit_and_writes_bit_two_only(self):
        self.state.cond_bits = 0x0010
        self.call("TestCondFlags", 16)
        self.assertEqual(self.state.cond_bits, 0x0014)
        self.state.cond_bits = 0x0004
        self.call("TestCondFlags", 16)
        self.assertEqual(self.state.cond_bits, 0x0000)

    def test_the_condition_is_bit_two_of_the_word(self):
        self.call("SetCondFlags", 4)
        self.assertTrue(self.state.cond_flags)
        self.call("TestUnitFlags", 1)  # no such unit flag: the result overwrites the condition
        self.assertEqual(self.state.cond_bits & 4, 0)

    def test_condition_does_not_survive_a_tick_but_other_bits_do(self):
        self.state.cond_bits = 0x0004 | 0x0010
        self.run_words([word("Yield")])
        self.assertEqual(self.state.cond_bits, 0x0010)

    def test_if_goto_script_reads_a_condition_set_by_set_cond_flags(self):
        scripts = {1: [word("SetCondFlags"), 4, word("IfGotoScript"), 2, END],
                   2: [word("SetUnitFlags2"), 0x40, END]}
        self.run_words(None, scripts)
        self.assertEqual(self.state.unit_flags2, 0x40)


class RepeatTests(ControlTestCase):
    def test_vectors(self):
        self.state.pc = 15
        self.assertEqual(self.call("RepeatStart", 2), 17)
        self.assertEqual(self.state.return_stack, [(17, 2, interpreter.REPEAT_ENTRY)])
        self.state.pc = 28
        self.assertEqual(self.call("RepeatNext"), 17)
        self.assertEqual(self.state.return_stack, [(17, 1, interpreter.REPEAT_ENTRY)])
        self.assertEqual(self.call("RepeatNext"), 29)
        self.assertEqual(self.state.return_stack, [])

    def test_body_runs_exactly_n_times(self):
        self.count("SetUnitFlags2")
        self.run_words([word("RepeatStart"), 3, word("SetUnitFlags2"), 1, word("RepeatNext"), word("Yield")])
        self.assertEqual(self.counts["SetUnitFlags2"], 3)
        self.assertEqual(self.state.return_stack, [])

    def test_nested_repeats_multiply(self):
        self.count("SetUnitFlags2")
        self.run_words([word("RepeatStart"), 2, word("RepeatStart"), 3, word("SetUnitFlags2"), 1,
                        word("RepeatNext"), word("RepeatNext"), word("Yield")])
        self.assertEqual(self.counts["SetUnitFlags2"], 6)

    def test_repeat_inside_a_push_pc_loop_keeps_the_loop_entry(self):
        """Script 105's shape: PushPC; RepeatStart 2; ...; RepeatNext; ...; Loop."""
        self.state.pc = 0
        self.call("PushPC")
        self.call("RepeatStart", 2)
        self.state.pc = 10
        self.call("RepeatNext")
        self.call("RepeatNext")
        self.assertEqual(self.state.return_stack, [(1,)])


class EventTests(ControlTestCase):
    def queue(self, *codes):
        for code in codes:
            self.state.event_queue.append(Event(code=code))

    def test_get_event_takes_the_most_recent_event_first(self):
        self.queue(1, 2, 3)
        self.call("GetEvent")
        self.assertEqual(self.state.current_event.code, 3)

    def test_consume_event_condition_is_queue_not_empty(self):
        self.queue(1, 2)
        self.call("GetEvent")
        self.call("ConsumeEvent")
        self.assertTrue(self.state.cond_flags)
        self.call("GetEvent")
        self.call("ConsumeEvent")
        self.assertFalse(self.state.cond_flags)

    def test_drain_events_vectors(self):
        self.state.current_event = Event(code=9)
        self.call("DrainEvents")  # empty queue: nothing changes
        self.assertEqual(self.state.current_event.code, 9)
        self.assertFalse(self.state.cond_flags)
        self.queue(1, 2, 3)  # head (newest) is 3; the oldest, 1, is taken last
        self.call("DrainEvents")
        self.assertEqual(self.state.current_event.code, 1)
        self.assertEqual(len(self.state.event_queue), 0)
        self.assertTrue(self.state.cond_flags)

    def test_handler_epilogue_after_drain_ends_the_loop(self):
        """CaseEvent arm `DrainEvents; Break` then `ConsumeEvent; LoopIfTrue`: the loop is not taken."""
        self.queue(4, 5, 6)
        self.call("GetEvent")
        self.call("DrainEvents")
        self.call("ConsumeEvent")
        self.assertFalse(self.state.cond_flags)

    def test_clear_event_forgets_only_the_current_event(self):
        self.state.current_event = Event(code=7)
        self.queue(1)
        self.state.cond_flags = True
        self.call("ClearEvent")
        self.assertEqual(self.state.current_event.code, 0)
        self.assertEqual(len(self.state.event_queue), 1)
        self.assertTrue(self.state.cond_flags)


class IfGotoScriptTests(ControlTestCase):
    def test_true_switches_immediately_and_runs_the_new_script_in_the_same_tick(self):
        scripts = {1: [word("SetCondFlags"), 4, word("PushPC"), word("IfGotoScript"), 2, word("SetUnitFlags2"), 1, END],
                   2: [word("SetUnitFlags2"), 0x40, END]}
        self.run_words(None, scripts)
        self.assertEqual(self.state.script_id, 2)
        self.assertEqual(self.state.unit_flags2, 0x40)  # the old script's tail never ran
        self.assertEqual(len(self.state.return_stack), 1)  # stack untouched
        self.assertFalse(self.state.pending_switch)

    def test_false_continues_after_the_operand(self):
        scripts = {1: [word("IfGotoScript"), 2, word("SetUnitFlags2"), 1, END],
                   2: [word("SetUnitFlags2"), 0x40, END]}
        self.run_words(None, scripts)
        self.assertEqual(self.state.script_id, 1)
        self.assertEqual(self.state.unit_flags2, 1)

    def test_if_not_goto_script_is_the_mirror(self):
        scripts = {1: [word("IfNotGotoScript"), 2, END], 2: [word("SetUnitFlags2"), 0x40, END]}
        self.run_words(None, scripts)
        self.assertEqual(self.state.unit_flags2, 0x40)


if __name__ == "__main__":
    unittest.main()
