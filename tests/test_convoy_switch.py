"""A switch to the script a unit is already running (notes/convoy_jam_and_melee_obstacles.md A.1-A.3): a wagon re-sent
event 0x27 while it is in its halt script must reach the halt instead of restarting the script's first Yield."""

import unittest

from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side
from tests.script_helpers import FakeDll, word

HALT_SCRIPT = [word("Yield"), word("HaltAndReform"), word("PushPC"), word("SetWait"), 20, word("Wait"),
               word("CheckCollisions"), word("LoopIfTrue"), word("Restart"), behaviour.END]
WAIT_PC = 5


def handler(switch: str) -> list[int]:
    return [word("GetEvent"), word(switch), 166, word("ConsumeEvent"), word("ReturnInterrupt"), behaviour.END]


class ConvoyHaltScriptTests(unittest.TestCase):
    def setUp(self, switch: str = "SwitchScript"):
        self.cart = Regiment("cart", "Cart", 100, 100, 0, Side.NEUTRAL, models=2, ranks=1)
        self.battle = Battle(1000, 1000, [self.cart], seed=1995)
        self.dll = FakeDll({3: [word("Wait"), behaviour.END], 6: handler(switch), 166: HALT_SCRIPT})
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, self.dll)
        self.state = self.battle.event_bus.unit_states["cart"]
        self.state.script_id, self.state.pc, self.state.interrupt_script = 3, 0, 6
        self.cart.target_x, self.cart.target_y = 100, 900  # still under its move order

    def tick(self, tick: int) -> None:
        self.state.event_queue.append(interpreter.Event(code=0x27))  # the mutual re-check: 0x27 every update
        self.interp.run("cart", self.state, tick, self.battle.rng)

    def test_given_first_0x27_then_the_halt_script_starts_at_its_yield_and_the_cart_still_moves(self):
        self.tick(1)
        self.assertEqual((self.state.script_id, self.state.pc), (166, 1))
        self.assertIsNotNone(self.cart.target_x)

    def test_given_0x27_again_next_tick_then_the_switch_is_ignored_and_the_cart_halts(self):
        self.tick(1)
        self.tick(2)
        self.assertEqual((self.state.script_id, self.state.pc), (166, WAIT_PC))
        self.assertIsNone(self.cart.target_x)
        self.assertIsNone(self.state.interrupt_return)

    def test_given_0x27_every_tick_then_the_cart_stays_in_its_wait(self):
        for tick in range(1, 8):
            self.tick(tick)
        self.assertEqual((self.state.script_id, self.state.pc), (166, WAIT_PC))
        self.assertIsNone(self.cart.target_x)

    def test_given_a_high_priority_switch_to_the_running_script_then_it_restarts_at_the_start(self):
        self.setUp("IfSwitchScriptHigh")
        self.tick(1)
        self.tick(2)
        self.assertEqual((self.state.script_id, self.state.pc), (166, 1))
        self.assertIsNotNone(self.cart.target_x)


class HighPrioritySwitchLockTests(unittest.TestCase):
    """notes/script_grid_events.md 1: only an IfSwitchScriptHigh request locks the pending switch."""

    def test_given_a_pending_high_priority_switch_then_a_later_normal_switch_does_not_replace_it(self):
        state = interpreter.UnitScriptState(script_id=3)
        interp = interpreter.ScriptInterpreter(None, None, None)
        interp.op_IfSwitchScriptHigh(state, 105, [], "u", 0, None)
        interp.op_SwitchScript(state, 163, [], "u", 0, None)
        self.assertEqual((state.pending_switch, state.pending_switch_high), (105, True))

    def test_given_a_pending_normal_switch_then_a_later_switch_still_replaces_it(self):
        state = interpreter.UnitScriptState(script_id=3)
        interp = interpreter.ScriptInterpreter(None, None, None)
        interp.op_SwitchScript(state, 163, [], "u", 0, None)
        interp.op_SwitchScript(state, 105, [], "u", 0, None)
        self.assertEqual(state.pending_switch, 105)

if __name__ == "__main__":
    unittest.main()
