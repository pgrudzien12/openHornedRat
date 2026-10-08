"""Tests for pre-emptive event dispatch (notes/game_rules.md, "Event dispatch is pre-emptive, not
polled"): a unit with a registered interrupt script (SetInterruptScript) and a queued, unconsumed
event must have that interrupt script forced onto its PC before its main script runs any instruction
that tick -- regardless of what the main script's PC currently sits on, since real scripts idle in a
`Wait`-only loop that never itself calls GetEvent/CaseEvent/CallInterruptScript.

This closes the user-reported gap traced in this project's own recorded battle logs: a charged unit's
event queue held a real, unconsumed event 0x07 the whole time it sat in its idle `Wait` loop, but
without pre-emption nothing ever consumed it, so the unit never braced.
"""

import unittest

from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class _FakeScriptDll:
    """A minimal stand-in for behaviour.ScriptDll: scripts(ids) -> {id: [word, ...]}."""

    def __init__(self, scripts):
        self._scripts = scripts

    def scripts(self, ids):
        return {i: self._scripts[i] for i in ids}


def _word(opcode):
    return behaviour.OPCODE_FLAG | opcode


class PreemptForPendingEventTests(unittest.TestCase):
    """Unit tests directly against the preemption helper (no real script execution)."""

    def setUp(self):
        self.interp = interpreter.ScriptInterpreter(None, None, None)

    def test_a_queued_event_with_a_registered_interrupt_script_forces_entry(self):
        state = interpreter.UnitScriptState(script_id=100, pc=43, interrupt_script=101)
        state.event_queue.append(interpreter.Event(code=0x07, source="charger"))

        self.interp._preempt_for_pending_event(state)

        self.assertEqual(state.script_id, 101)
        self.assertEqual(state.pc, 0)
        self.assertEqual(state.interrupt_return, (100, 43))

    def test_no_interrupt_script_registered_is_a_no_op(self):
        state = interpreter.UnitScriptState(script_id=100, pc=43, interrupt_script=None)
        state.event_queue.append(interpreter.Event(code=0x07, source="charger"))

        self.interp._preempt_for_pending_event(state)

        self.assertEqual(state.script_id, 100)
        self.assertIsNone(state.interrupt_return)

    def test_no_pending_event_is_a_no_op(self):
        state = interpreter.UnitScriptState(script_id=100, pc=43, interrupt_script=101)

        self.interp._preempt_for_pending_event(state)

        self.assertEqual(state.script_id, 100)
        self.assertIsNone(state.interrupt_return)

    def test_already_inside_a_handler_with_a_queued_event_nests_a_second_entry(self):
        # notes/unit_script_control.md 1, "Event handlers can nest": the interrupted point of the outer handler is
        # kept and resumed when the nested one returns.
        state = interpreter.UnitScriptState(script_id=101, pc=5, interrupt_script=101,
                                             interrupt_return=(100, 43))
        state.event_queue.append(interpreter.Event(code=0x39, source="rally"))

        self.interp._preempt_for_pending_event(state)

        self.assertEqual((state.script_id, state.pc), (101, 0))
        self.assertEqual(state.interrupt_return, (101, 5))
        self.assertEqual(state.outer_returns, [(100, 43)])

    def test_already_inside_a_handler_with_nothing_queued_is_not_re_entered(self):
        state = interpreter.UnitScriptState(script_id=101, pc=5, interrupt_script=101,
                                             interrupt_return=(100, 43))
        state.current_event = interpreter.Event(code=0x39, source="rally")  # taken by GetEvent already

        self.interp._preempt_for_pending_event(state)

        self.assertEqual((state.script_id, state.pc, state.interrupt_return), (101, 5, (100, 43)))
        self.assertEqual(state.outer_returns, [])

    def test_an_already_popped_current_event_also_forces_entry(self):
        # GetEvent (or run()'s own auto-pop) may have already moved the event out of the queue and
        # onto current_event before ConsumeEvent ran; that still counts as pending.
        state = interpreter.UnitScriptState(script_id=100, pc=43, interrupt_script=101,
                                             current_event=interpreter.Event(code=0x07, source="c"))

        self.interp._preempt_for_pending_event(state)

        self.assertEqual(state.script_id, 101)


class RunPreemptsAnIdlingUnitTests(unittest.TestCase):
    """Integration test at the run() level: a unit stuck in an indefinite Wait-only loop (the real
    shape of BF003's PLAYER_SCRIPT idle body, per the traced battle log) must still enter its
    interrupt script the same tick an event arrives, without ever executing GetEvent itself."""

    def setUp(self):
        self.regiment = Regiment("t", "T", 0, 0, 0, Side.PLAYER, models=5, ranks=1)
        self.battle = Battle(500, 500, [self.regiment], seed=1995)
        # Main script (100): just Wait forever (0x1C = Wait per behaviour.py's opcode table), never
        # touching GetEvent/CaseEvent/CallInterruptScript -- the real shape traced in the battle log.
        main_words = [_word(0x1C), behaviour.END]
        # Interrupt script (101): GetEvent, ConsumeEvent, ReturnInterrupt -- the documented frame
        # (game_rules.md: "GetEvent; CaseEvent a...Break;...;ConsumeEvent; loop"). GetEvent is what
        # actually drains the queue into current_event; the interpreter itself no longer does this
        # implicitly (that shim used to clobber a real event: op_GetEvent's own "queue empty" branch
        # would blank out current_event a preemption had *already* populated from the queue).
        interrupt_words = [_word(0x68), _word(0x69), _word(0x14), behaviour.END]
        self.script_dll = _FakeScriptDll({100: main_words, 101: interrupt_words})
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, self.script_dll)
        self.state = self.battle.event_bus.unit_states["t"]
        self.state.script_id = 100
        self.state.interrupt_script = 101

    def test_given_no_event_when_run_then_it_stays_in_the_main_script(self):
        self.interp.run("t", self.state, 0, self.battle.rng)
        self.assertEqual(self.state.script_id, 100)

    def test_the_interrupt_scripts_own_getevent_actually_sees_the_real_event(self):
        # Regression: run() used to pre-pop the queue into current_event on its own, so by the time
        # the interrupt script's own GetEvent ran, the queue looked empty and GetEvent's "nothing
        # queued" branch blanked current_event back out -- FearWhenCharged then always saw event
        # code 0, never 0x07, and a charged unit could never brace. Confirmed against a real BF003
        # playthrough (Grudgebringer Cavalry never braced despite Goblin Stickers charging it).
        self.state.event_queue.append(interpreter.Event(code=0x07, source="charger"))
        seen = {}
        orig_get_event = interpreter.ScriptInterpreter.op_GetEvent

        def spy(self, state, operand, script_words, unit_id, tick_count, rng):
            result = orig_get_event(self, state, operand, script_words, unit_id, tick_count, rng)
            seen["code"] = state.current_event.code
            return result

        interpreter.ScriptInterpreter.op_GetEvent = spy
        try:
            self.interp.run("t", self.state, 0, self.battle.rng)
        finally:
            interpreter.ScriptInterpreter.op_GetEvent = orig_get_event

        self.assertEqual(seen.get("code"), 0x07)

    def test_given_a_pending_event_when_run_then_it_enters_the_interrupt_script_and_returns(self):
        self.state.event_queue.append(interpreter.Event(code=0x07, source="charger"))

        self.interp.run("t", self.state, 0, self.battle.rng)

        # ConsumeEvent + ReturnInterrupt run within the same tick and resume the main script exactly
        # where it was (Wait's pc, unconsumed), not skipping past it.
        self.assertEqual(self.state.script_id, 100)
        self.assertIsNone(self.state.interrupt_return)
        self.assertEqual(self.state.current_event.code, 0)
        self.assertEqual(len(self.state.event_queue), 0)


if __name__ == "__main__":
    unittest.main()
