"""Tests for the "being charged" event pipeline (issue #3/#46): CallInterruptScript/ReturnInterrupt
and ScriptInterpreter.raise_charge_events.

User-reported gap: in the original, a charged unit freezes and waits rather than continuing to
close on its attacker -- with neither piece implemented, both units instead independently charge
each other, which never happens in the original. Two things were needed together:

1. CallInterruptScript/ReturnInterrupt: the interpreter plumbing a script's event-handling frame
   uses to jump into (and return from) the script registered by SetInterruptScript.
2. raise_charge_events: nothing in the engine ever raised event 0x07 ("you are being charged") in
   the first place, so even with (1) working, a charged unit's script had nothing to react to.
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


class RaiseChargeEventsTests(unittest.TestCase):
    def setUp(self):
        self.attacker = Regiment("attacker", "Attacker", 0, 0, 0, Side.ENEMY, models=10, ranks=2)
        self.target = Regiment("target", "Target", 100, 0, 0, Side.PLAYER, models=10, ranks=2)
        self.battle = Battle(500, 500, [self.attacker, self.target], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_a_fresh_charge_queues_event_7_to_the_target(self):
        self.attacker.attack_target = "target"
        self.interp.raise_charge_events()

        target_state = self.battle.event_bus.unit_states["target"]
        self.assertEqual(len(target_state.event_queue), 1)
        event = target_state.event_queue[0]
        self.assertEqual(event.code, 0x07)
        self.assertEqual(event.source, "attacker")

    def test_no_attack_target_means_no_event(self):
        self.interp.raise_charge_events()
        target_state = self.battle.event_bus.unit_states["target"]
        self.assertEqual(len(target_state.event_queue), 0)

    def test_sustained_charge_does_not_reraise_every_tick(self):
        self.attacker.attack_target = "target"
        self.interp.raise_charge_events()
        self.interp.raise_charge_events()  # same target, "next tick"
        self.interp.raise_charge_events()

        target_state = self.battle.event_bus.unit_states["target"]
        self.assertEqual(len(target_state.event_queue), 1)  # only the first tick raised it

    def test_switching_targets_reraises_for_the_new_target(self):
        other = Regiment("other", "Other", -100, 0, 0, Side.PLAYER, models=10, ranks=2)
        battle = Battle(500, 500, [self.attacker, self.target, other], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)

        self.attacker.attack_target = "target"
        interp.raise_charge_events()
        self.attacker.attack_target = "other"
        interp.raise_charge_events()

        self.assertEqual(len(battle.event_bus.unit_states["target"].event_queue), 1)
        self.assertEqual(len(battle.event_bus.unit_states["other"].event_queue), 1)

    def test_losing_and_reacquiring_the_same_target_reraises(self):
        self.attacker.attack_target = "target"
        self.interp.raise_charge_events()
        self.attacker.attack_target = None
        self.interp.raise_charge_events()
        self.attacker.attack_target = "target"
        self.interp.raise_charge_events()

        target_state = self.battle.event_bus.unit_states["target"]
        self.assertEqual(len(target_state.event_queue), 2)

    def test_wired_into_battle_tick_end_to_end(self):
        """Full path: an opcode sets attack_target within charge reach, Battle.tick() raises the
        charge event without any extra wiring at the call site."""
        battle = Battle(500, 500, [
            Regiment("attacker", "Attacker", 0, 0, 0, Side.ENEMY, models=10, ranks=2),
            Regiment("target", "Target", 50, 0, 0, Side.PLAYER, models=10, ranks=2),
        ], seed=1995, script_dll=object())  # truthy script_dll: constructs a real interpreter
        battle.regiments["attacker"].attack_target = "target"

        battle.tick()

        target_state = battle.event_bus.unit_states["target"]
        # The blocks overlap, so the contact pass also sends the reciprocal contact event 0x0B
        # (notes/script_behaviours.md 2.2); the charge event is raised once.
        self.assertEqual(sorted(event.code for event in target_state.event_queue), [0x07, 0x0B])

    def test_far_away_attack_target_does_not_yet_raise_the_event(self):
        # game_rules.md "Charge": a real charge only reaches `12 * (s_rlmv + 1)` units -- picking a
        # target from across the battlefield must not brace it for the whole approach.
        self.attacker.attack_target = "target"
        self.target.x = self.attacker.x + self.attacker.charge_reach + 1
        self.interp.raise_charge_events()

        target_state = self.battle.event_bus.unit_states["target"]
        self.assertEqual(len(target_state.event_queue), 0)

    def test_closing_into_charge_reach_raises_the_event_once(self):
        self.attacker.attack_target = "target"
        self.target.x = self.attacker.x + self.attacker.charge_reach + 50
        self.interp.raise_charge_events()  # still out of reach: no event yet
        self.target.x = self.attacker.x + self.attacker.charge_reach - 1
        self.interp.raise_charge_events()  # now in reach: fires
        self.interp.raise_charge_events()  # still the same target, in reach: does not refire

        target_state = self.battle.event_bus.unit_states["target"]
        self.assertEqual(len(target_state.event_queue), 1)


if __name__ == "__main__":
    unittest.main()
