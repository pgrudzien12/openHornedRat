"""A failed close-combat break test is a rout request to the unit, which its handler filters
(notes/panic_tests.md 3, game_rules.md 6.2 "Break test", GitHub #300)."""

import unittest
from unittest.mock import patch

from whshr import combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side

FAIL, PASS = 12, 2  # flat 2-12 rolls against Ld 7 and modifier 0


def unit(**extra) -> Regiment:
    regiment = Regiment("U", "Unit", 500, 500, 0, Side.ENEMY, models=10, ranks=2, **extra)
    regiment.leadership = 7
    return regiment


def break_test(regiment: Regiment, roll: int, scripted: bool) -> Battle:
    battle = Battle(1000, 1000, [regiment], seed=1995)
    battle.phase = "battle"
    if scripted:
        battle.interpreter = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
    with patch.object(combat, "_2_to_12", return_value=roll):
        combat._break_test(regiment, 0, "fight", combat._empty_breakdown(), battle)
    return battle


def tests(battle: Battle) -> list[dict[str, object]]:
    return [event.data for event in battle.events if event.kind == "leadership_test"]


def rout_requests(battle: Battle) -> int:
    return [event.code for event in battle.event_bus.unit_states["U"].event_queue].count(0x0C)


class ScriptedBreakTests(unittest.TestCase):
    """With behaviour scripts the test only posts 0x0C; the unit's own handler decides."""

    def test_a_failed_test_posts_the_rout_event_and_does_not_rout_by_itself(self):
        battle = break_test(unit(), FAIL, scripted=True)
        self.assertEqual(rout_requests(battle), 1)
        self.assertFalse(battle.regiments["U"].routing)

    def test_a_cant_break_unit_still_rolls_and_its_failure_is_left_to_its_handler(self):
        battle = break_test(unit(psychology=frozenset({"CantBreak"})), FAIL, scripted=True)
        self.assertEqual([(t["roll"], t["passed"], t["cant_break"]) for t in tests(battle)], [(FAIL, False, True)])
        self.assertEqual(rout_requests(battle), 1)

    def test_artillery_failing_is_sent_the_rout_event_too(self):
        battle = break_test(unit(hud_class="art"), FAIL, scripted=True)
        self.assertEqual(rout_requests(battle), 1)
        self.assertFalse(battle.regiments["U"].routing)

    def test_a_passed_test_posts_nothing(self):
        battle = break_test(unit(), PASS, scripted=True)
        self.assertEqual(rout_requests(battle), 0)


class UnscriptedBreakTests(unittest.TestCase):
    """Without scripts the engine applies the handler's filter itself."""

    def test_a_failed_test_routs_an_ordinary_unit(self):
        self.assertTrue(break_test(unit(), FAIL, scripted=False).regiments["U"].routing)

    def test_a_cant_break_unit_holds(self):
        battle = break_test(unit(psychology=frozenset({"CantBreak"})), FAIL, scripted=False)
        self.assertFalse(battle.regiments["U"].routing)
        self.assertEqual(len(tests(battle)), 1)  # it rolled

    def test_artillery_does_not_rout(self):
        self.assertFalse(break_test(unit(hud_class="art"), FAIL, scripted=False).regiments["U"].routing)


class BrokenUnitTests(unittest.TestCase):
    def test_an_already_broken_unit_is_not_tested(self):
        for scripted in (False, True):
            with self.subTest(scripted=scripted):
                battle = break_test(unit(routing=True), FAIL, scripted=scripted)
                self.assertEqual(tests(battle), [])
                if scripted:
                    self.assertEqual(rout_requests(battle), 0)


if __name__ == "__main__":
    unittest.main()
