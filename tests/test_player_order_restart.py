"""Player orders against a running fire loop (notes/player_missile_orders.md 1.1 and 1.2): Move, Face point and the
turns restart the script at its restart point, drop the target and discard queued events, so the unit does not fire
on arrival; Halt ends the loop on its next pass but keeps the target; Ranks leave the loop running. Synthetic scripts
in the library's shape (idle loop at the restart point, a keep-firing loop)."""

import unittest

from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side
from tests.script_helpers import FakeDll, word

MAIN, FIRE = 100, 108
KEEP_FIRING = interpreter.SHOOTING_SEQUENCE_FLAG2
SCRIPTS = {
    # idle: SetRestartPoint; PushPC; SetWait 100; Wait; Yield; Loop
    MAIN: [word("SetRestartPoint"), word("PushPC"), word("SetWait"), 100, word("Wait"), word("Yield"), word("Loop"),
           behaviour.END],
    # fire loop: ResetStack; SetUnitFlags2 4; PushPC; Yield; TestUnitFlags2 4; LoopIfTrue; ClearUnitFlags2 4; Restart
    FIRE: [word("ResetStack"), word("SetUnitFlags2"), KEEP_FIRING, word("PushPC"), word("Yield"),
           word("TestUnitFlags2"), KEEP_FIRING, word("LoopIfTrue"), word("ClearUnitFlags2"), KEEP_FIRING,
           word("Restart"), behaviour.END],
}


class FireLoopOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shooter = Regiment("xb", "Crossbows", 100, 500, 128, Side.PLAYER, models=8, ranks=2, hud_class="arch")
        self.enemy = Regiment("enemy", "Enemy", 400, 500, 384, Side.ENEMY, models=8, ranks=2)
        self.battle = Battle(1000, 1000, [self.shooter, self.enemy], seed=1995, script_dll=FakeDll(SCRIPTS),
                             script_ids={"xb": MAIN, "enemy": MAIN})
        self.state = self.battle.event_bus.unit_states["xb"]
        self.battle.tick()  # the idle loop saves its restart point
        self.restart_pc = self.state.restart_pc
        self.state.script_id, self.state.pc = FIRE, 0
        self.state.current_target = ("enemy", 0)
        self.battle.tick()  # now inside the keep-firing loop

    def _in_fire_loop(self) -> bool:
        return self.state.script_id == FIRE and bool(self.state.unit_flags2 & KEEP_FIRING)

    def test_given_a_fire_loop_when_moved_then_the_script_restarts_idle_without_a_target(self) -> None:
        self.assertTrue(self._in_fire_loop())
        self.state.event_queue.append(interpreter.Event(code=34, source="xb"))  # a volley pose already posted
        self.battle.order_move("xb", 150, 700)
        self.assertEqual((self.state.script_id, self.state.pc), (MAIN, self.restart_pc))
        self.assertIsNone(self.state.current_target)
        self.assertEqual(len(self.state.event_queue), 0)
        for _ in range(5):
            self.battle.tick()
        self.assertEqual(self.state.script_id, MAIN)
        self.assertTrue(self.shooter.moving)

    def test_given_a_fire_loop_when_turned_about_then_the_script_restarts_without_a_target(self) -> None:
        self.battle.order_about_face("xb")
        self.assertEqual((self.state.script_id, self.state.pc), (MAIN, self.restart_pc))
        self.assertIsNone(self.state.current_target)

    def test_given_a_fire_loop_when_facing_a_point_then_the_script_restarts(self) -> None:
        self.battle.order_face_point("xb", 100, 900)
        self.assertEqual(self.state.script_id, MAIN)
        self.assertIsNone(self.state.current_target)

    def test_given_a_fire_loop_when_halted_then_the_loop_ends_next_pass_but_keeps_the_target(self) -> None:
        self.battle.order_halt("xb")
        self.assertFalse(self.state.unit_flags2 & KEEP_FIRING)
        self.battle.tick()
        self.assertEqual(self.state.script_id, MAIN)
        self.assertEqual(self.state.current_target, ("enemy", 0))

    def test_given_a_fire_loop_when_ranks_change_then_the_loop_keeps_running(self) -> None:
        self.battle.order_reform("xb", 3)
        for _ in range(3):
            self.battle.tick()
        self.assertTrue(self._in_fire_loop())
        self.assertEqual(self.state.current_target, ("enemy", 0))


if __name__ == "__main__":
    unittest.main()
