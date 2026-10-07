"""BDD scenarios for kill credit: which unit gains s_kills and s_Exp when a model leaves its regiment
(notes/casualty_bookkeeping.md 2.0-2.6, test vectors of 2.6)."""
import unittest

from whshr import combat
from whshr.engine import Battle, Regiment
from whshr.interpreter import ScriptInterpreter, UnitScriptState
from whshr.rules import Side


def _regiment(identifier, side, models=10, points=0, x=0.0, y=0.0):
    regiment = Regiment(identifier, identifier, x, y, 0, side, models=models, ranks=2, points=points)
    regiment.model_positions()
    return regiment


class KillCreditTests(unittest.TestCase):
    def test_given_a_close_combat_kill_then_the_striking_unit_gains_a_kill_and_the_victims_points(self):
        victim = _regiment("v", Side.ENEMY, models=10, points=15)
        striker = _regiment("x", Side.PLAYER, x=500.0)
        striker.kills, striker.experience_gained = 3, 40
        battle = Battle(2000, 2000, [victim, striker], seed=1995)

        combat.kill_models(victim, [0], battle=battle, killer="x")

        self.assertEqual(victim.models, 9)
        self.assertEqual((striker.kills, striker.experience_gained), (4, 55))

    def test_given_a_wounded_troll_when_another_unit_lands_the_lethal_hit_then_that_unit_is_credited(self):
        troll = _regiment("t", Side.ENEMY, models=1, points=50)
        melee = _regiment("x", Side.PLAYER, x=500.0)
        archers = _regiment("y", Side.PLAYER, x=-500.0)
        melee.kills, melee.experience_gained = 3, 40
        battle = Battle(2000, 2000, [troll, melee, archers], seed=1995)
        troll.melee_models[0].credit = "x"  # wounded earlier in close combat by X

        combat.kill_models(troll, [0], battle=battle, killer="y")

        self.assertEqual((archers.kills, archers.experience_gained), (1, 50))
        self.assertEqual((melee.kills, melee.experience_gained), (3, 40))

    def test_given_a_troll_wounded_in_melee_when_it_routs_off_the_map_then_the_melee_unit_gets_the_kill(self):
        troll = _regiment("t", Side.ENEMY, models=1, points=50)
        melee = _regiment("x", Side.PLAYER, x=500.0)
        melee.kills, melee.experience_gained = 3, 40
        battle = Battle(2000, 2000, [troll, melee], seed=1995)
        troll.melee_models[0].credit = "x"

        battle.remove_from_play(troll)

        self.assertTrue(troll.fled)
        self.assertEqual((melee.kills, melee.experience_gained), (4, 90))

    def test_given_a_unit_with_no_credited_models_when_it_routs_off_the_map_then_nobody_is_credited(self):
        troll = _regiment("t", Side.ENEMY, models=1, points=50)
        archers = _regiment("y", Side.PLAYER, x=500.0)
        battle = Battle(2000, 2000, [troll, archers], seed=1995)

        battle.remove_from_play(troll)

        self.assertEqual((archers.kills, archers.experience_gained), (0, 0))

    def test_given_a_pursuer_cutting_down_two_routers_when_the_rest_flee_then_only_the_two_are_credited(self):
        routers = _regiment("e", Side.ENEMY, models=15, points=12)
        pursuer = _regiment("p", Side.PLAYER, x=500.0)
        battle = Battle(2000, 2000, [routers, pursuer], seed=1995)

        combat.kill_models(routers, [0, 1], battle=battle, killer="p")
        battle.remove_from_play(routers)
        battle.remove_from_play(routers)  # leaving twice pays nothing more

        self.assertEqual((pursuer.kills, pursuer.experience_gained), (2, 24))

    def test_given_friendly_fire_then_the_firing_unit_is_credited_with_no_side_check(self):
        friend = _regiment("f", Side.PLAYER, models=10, points=10)
        cannon = _regiment("c", Side.PLAYER, x=500.0)
        battle = Battle(2000, 2000, [friend, cannon], seed=1995)

        combat.kill_models(friend, [0], battle=battle, killer="c")

        self.assertEqual((cannon.kills, cannon.experience_gained), (1, 10))

    def test_given_a_caster_slaying_its_own_unit_then_it_credits_itself(self):
        wizard = _regiment("w", Side.PLAYER, models=1, points=40)
        battle = Battle(2000, 2000, [wizard], seed=1995)

        combat.kill_models(wizard, [0], battle=battle, killer="w")

        self.assertEqual((wizard.kills, wizard.experience_gained), (1, 40))

    def test_given_a_misfire_then_the_crew_it_kills_credit_nobody_even_if_wounded_before(self):
        crew = _regiment("c", Side.PLAYER, models=3, points=9)
        enemy = _regiment("x", Side.ENEMY, x=500.0)
        battle = Battle(2000, 2000, [crew, enemy], seed=1995)
        crew.melee_models[0].credit = "x"

        combat.kill_models(crew, [0], battle=battle, clear_credit=True)

        self.assertEqual((enemy.kills, enemy.experience_gained), (0, 0))

    def test_given_a_building_with_no_points_when_destroyed_then_the_shooter_gains_a_kill_but_no_experience(self):
        building = _regiment("b", Side.ENEMY, models=1, points=0)
        cannon = _regiment("c", Side.PLAYER, x=500.0)
        cannon.kills, cannon.experience_gained = 2, 20
        battle = Battle(2000, 2000, [building, cannon], seed=1995)

        combat.kill_models(building, [0], battle=battle, killer="c")

        self.assertEqual((cannon.kills, cannon.experience_gained), (3, 20))

    def test_given_a_script_removal_then_the_unit_leaves_alive_and_pays_its_stale_credits(self):
        troll = _regiment("t", Side.ENEMY, models=1, points=50)
        melee = _regiment("x", Side.PLAYER, x=500.0)
        battle = Battle(2000, 2000, [troll, melee], seed=1995)
        troll.melee_models[0].credit = "x"
        interpreter = ScriptInterpreter(battle, battle.event_bus, None)

        interpreter.op_RemoveFromBattle(UnitScriptState(), None, [], "t", 0, battle.rng)

        self.assertTrue(troll.fled)
        self.assertEqual((melee.kills, melee.experience_gained), (1, 50))


if __name__ == "__main__":
    unittest.main()
