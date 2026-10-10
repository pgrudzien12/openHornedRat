"""Casualty and impact panic (notes/panic_tests.md): a unit tests Leadership when its losses cross a quarter of its
organisational size, and on a direct missile hit while at a quarter or less; a failure is a rout request."""

import unittest

from whshr import animation, combat, interpreter, ranged
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def clanrats(models: int = 16, orgsize: int = 16, leadership: int = 5) -> Regiment:
    unit = Regiment("R", "Clanrats", 500, 500, 0, Side.ENEMY, models=models, ranks=4, orgsize=orgsize)
    unit.leadership = leadership
    return unit


class PanicTestCase(unittest.TestCase):
    def build(self, unit: Regiment, scripted: bool = False) -> None:
        self.unit = unit
        self.battle = Battle(1000, 1000, [unit], seed=1995)
        self.battle.phase = "battle"
        if scripted:
            self.battle.interpreter = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def panic_events(self) -> list[dict[str, object]]:
        return [event.data for event in self.battle.events if event.kind == "panic_test"]

    def volley(self, kills: int) -> list[dict[str, object]]:
        """Kill `kills` models with missiles; their death sequences start on the next tick."""
        combat.kill_models(self.unit, range(kills), self.battle, animation.DEATH_MISSILE, killer="S")
        self.battle.tick()
        return self.panic_events()


class CasualtyPanicTests(PanicTestCase):
    def test_given_full_strength_when_one_model_dies_then_no_test(self):
        self.build(clanrats())
        self.assertEqual(self.volley(1), [])

    def test_given_full_strength_when_four_die_then_no_boundary_is_crossed(self):
        self.build(clanrats())
        self.assertEqual(self.volley(4), [])

    def test_given_full_strength_when_five_die_then_one_test_at_minus_one(self):
        self.build(clanrats())
        self.assertEqual([event["modifier"] for event in self.volley(5)], [-1])

    def test_given_eight_left_when_one_dies_then_a_test_at_zero(self):
        self.build(clanrats(models=8))
        self.assertEqual([event["modifier"] for event in self.volley(1)], [0])

    def test_given_four_left_when_one_dies_then_a_test_at_plus_one(self):
        self.build(clanrats(models=4))
        self.assertEqual([event["modifier"] for event in self.volley(1)], [1])

    def test_given_a_unit_starting_below_its_orgsize_then_its_first_loss_can_test(self):
        self.build(clanrats(models=12))
        self.assertEqual([event["modifier"] for event in self.volley(1)], [-1])

    def test_given_an_orgsize_not_a_multiple_of_four_then_the_minus_two_step_exists(self):
        self.build(clanrats(models=16, orgsize=18))
        self.assertEqual([event["modifier"] for event in self.volley(1)], [-2])

    def test_given_an_orgsize_under_four_then_never_a_casualty_test(self):
        self.build(clanrats(models=3, orgsize=3))
        self.assertEqual(self.volley(2), [])

    def test_given_a_close_combat_death_then_the_test_waits_for_the_collapse(self):
        self.build(clanrats(models=8))
        combat.kill_models(self.unit, [0], self.battle, animation.DEATH_ORDINARY)
        delay = self.unit.dying[0].ticks_left
        self.assertGreater(delay, 1)
        self.battle.tick()
        self.assertEqual(self.panic_events(), [])
        for _ in range(delay - 1):
            self.battle.tick()
        self.assertEqual([event["modifier"] for event in self.panic_events()], [0])

    def test_given_a_routing_unit_then_it_still_tests(self):
        self.build(clanrats(models=8))
        self.unit.routing = True
        self.assertEqual(len(self.volley(1)), 1)


class FailureTests(PanicTestCase):
    def fail_every_test(self) -> None:
        self.unit.leadership = 1  # no 2-12 roll passes

    def test_given_scripts_when_the_test_fails_then_the_unit_is_sent_the_rout_event(self):
        self.build(clanrats(models=8), scripted=True)
        self.fail_every_test()
        self.volley(1)
        state = self.battle.event_bus.unit_states["R"]
        self.assertIn(0x0C, [event.code for event in state.event_queue])
        self.assertFalse(self.unit.routing)

    def test_given_no_scripts_when_the_test_fails_then_the_unit_routs(self):
        self.build(clanrats(models=8))
        self.fail_every_test()
        self.volley(1)
        self.assertTrue(self.unit.routing)

    def test_given_no_scripts_and_cant_break_when_the_test_fails_then_it_holds(self):
        unit = clanrats(models=8)
        unit.psychology = frozenset({"CantBreak"})
        self.build(unit)
        self.fail_every_test()
        self.volley(1)
        self.assertFalse(self.unit.routing)


class ImpactPanicTests(PanicTestCase):
    def shot(self, code: int = 11) -> ranged.Projectile:
        return ranged.Projectile("C", code, 0, 0, 0, 500, 500, 0, 0, 1, 1)

    def test_given_a_quarter_strength_unit_when_hit_directly_then_an_impact_test_at_zero(self):
        self.build(clanrats(models=5, orgsize=20))
        ranged._damage_unit(self.battle, self.unit, self.shot(), True)
        self.assertEqual([(event["cause"], event["modifier"]) for event in self.panic_events()], [("impact", 0)])

    def test_given_a_quarter_strength_unit_when_only_the_blast_margin_hits_then_no_impact_test(self):
        self.build(clanrats(models=5, orgsize=20))
        ranged._damage_unit(self.battle, self.unit, self.shot(), False)
        self.assertEqual(self.panic_events(), [])

    def test_given_more_than_a_quarter_left_when_hit_directly_then_no_impact_test(self):
        self.build(clanrats(models=6, orgsize=20))
        ranged._damage_unit(self.battle, self.unit, self.shot(), True)
        self.assertEqual(self.panic_events(), [])

    def test_given_the_gyrocopter_bomb_then_no_impact_test(self):
        self.build(clanrats(models=5, orgsize=20))
        ranged._damage_unit(self.battle, self.unit, self.shot(code=17), True)
        self.assertEqual(self.panic_events(), [])


if __name__ == "__main__":
    unittest.main()
