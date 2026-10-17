"""Tests for the "being charged" event pipeline (issue #3/#46): CallInterruptScript/ReturnInterrupt
and the charge event 0x07 sent by ChargeTarget.

User-reported gap: in the original, a charged unit freezes and waits rather than continuing to
close on its attacker -- with neither piece implemented, both units instead independently charge
each other, which never happens in the original. Two things were needed together:

1. CallInterruptScript/ReturnInterrupt: the interpreter plumbing a script's event-handling frame
   uses to jump into (and return from) the script registered by SetInterruptScript.
2. Event 0x07 ("you are being charged"): without it a charged unit's script had nothing to react to. It is
   sent from the charger's script step (ChargeTarget), never from the battle tick (terror_contact_charge.md 8.5).
"""

import unittest
from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class CallInterruptScriptTests(unittest.TestCase):
    def setUp(self):
        self.interp = interpreter.ScriptInterpreter(None, None, None)

    def test_jumps_into_the_registered_interrupt_script_and_saves_the_return_point(self):
        state = interpreter.UnitScriptState(script_id=0, pc=10, interrupt_script=161)
        result = self.interp.op_CallInterruptScript(state, None, [], "t", 0, None)

        self.assertEqual(state.script_id, 161)
        self.assertEqual(result, 0)
        self.assertEqual(state.interrupt_return, (0, 11))

    def test_falls_through_when_no_interrupt_script_registered(self):
        state = interpreter.UnitScriptState(script_id=0, pc=10, interrupt_script=None)
        result = self.interp.op_CallInterruptScript(state, None, [], "t", 0, None)

        self.assertEqual(result, 11)
        self.assertEqual(state.script_id, 0)  # unchanged
        self.assertIsNone(state.interrupt_return)


class ReturnInterruptTests(unittest.TestCase):
    def setUp(self):
        self.interp = interpreter.ScriptInterpreter(None, None, None)

    def test_resumes_at_the_saved_interrupt_return_point(self):
        state = interpreter.UnitScriptState(script_id=161, pc=5, interrupt_return=(0, 11))
        result = self.interp.op_ReturnInterrupt(state, None, [], "t", 0, None)

        self.assertEqual(state.script_id, 0)
        self.assertEqual(result, 11)
        self.assertIsNone(state.interrupt_return)

    def test_applies_a_pending_switch_instead_of_returning_if_one_was_requested(self):
        # The interrupt handler itself decided to switch scripts (e.g. SwitchScript to a "brace"
        # script) -- that takes priority over resuming the interrupted point.
        state = interpreter.UnitScriptState(script_id=161, pc=5, interrupt_return=(0, 11))
        self.interp.op_SwitchScript(state, 162, [], "t", 0, None)
        result = self.interp.op_ReturnInterrupt(state, None, [], "t", 0, None)

        self.assertEqual(state.script_id, 162)
        self.assertEqual(result, 0)
        self.assertIsNone(state.pending_switch)
        self.assertIsNone(state.interrupt_return)  # discarded, not left dangling

    def test_falls_through_when_not_inside_an_interrupt(self):
        state = interpreter.UnitScriptState(script_id=0, pc=5)
        result = self.interp.op_ReturnInterrupt(state, None, [], "t", 0, None)

        self.assertEqual(result, 6)
        self.assertEqual(state.script_id, 0)

    def test_full_round_trip_through_call_and_return(self):
        state = interpreter.UnitScriptState(script_id=0, pc=10, interrupt_script=161)
        self.interp.op_CallInterruptScript(state, None, [], "t", 0, None)
        self.assertEqual(state.script_id, 161)

        result = self.interp.op_ReturnInterrupt(state, None, [], "t", 0, None)
        self.assertEqual(state.script_id, 0)
        self.assertEqual(result, 11)  # back where CallInterruptScript left off


class ChargeTargetEventTests(unittest.TestCase):
    """Event 0x07 comes only from a script step: ChargeTarget sends it when a charge at a regiment is accepted
    (notes/terror_contact_charge.md 8.5); nothing in the battle tick raises it from attack targets."""

    def setUp(self):
        self.attacker = Regiment("attacker", "Attacker", 0, 0, 0, Side.ENEMY, models=10, ranks=2)
        self.target = Regiment("target", "Target", 100, 0, 0, Side.PLAYER, models=10, ranks=2)
        self.battle = Battle(500, 500, [self.attacker, self.target], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.battle.phase = "battle"
        self.state = self.battle.event_bus.unit_states["attacker"]
        self.state.current_target = ("target", 0)

    def charge(self):
        self.interp.op_ChargeTarget(self.state, None, [], "attacker", 0, self.battle.rng)
        return [(event.code, event.source) for event in self.battle.event_bus.unit_states["target"].event_queue]

    def test_an_accepted_charge_queues_event_7_to_the_target(self):
        self.assertEqual(self.charge(), [(0x07, "attacker")])
        self.assertTrue(self.state.cond_flags)

    def test_a_charge_refused_by_terror_sends_nothing(self):
        self.target.psychology = {"CauseTerror"}
        self.assertEqual(self.charge(), [])
        self.assertFalse(self.state.cond_flags)

    def test_a_braced_charger_sends_nothing(self):
        self.attacker.braced = True
        self.assertEqual(self.charge(), [])

    def test_an_attack_target_set_outside_a_script_step_raises_no_event(self):
        battle = Battle(500, 500, [
            Regiment("attacker", "Attacker", 0, 0, 0, Side.ENEMY, models=10, ranks=2),
            Regiment("target", "Target", 300, 0, 0, Side.PLAYER, models=10, ranks=2),
        ], seed=1995, script_dll=object())  # truthy script_dll: constructs a real interpreter
        battle.regiments["attacker"].attack_target = "target"
        battle.tick()
        self.assertFalse(battle.event_bus.unit_states["target"].event_queue)


if __name__ == "__main__":
    unittest.main()
