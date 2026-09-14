"""BDD scenarios for the simple, rule-based enemy AI (whshr.ai)."""
import unittest

from whshr import ai
from whshr.engine import Battle, Regiment


def _regiment(identifier, x, y, player, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    return Regiment(identifier, identifier, x, y, 0, player, models=models, ranks=ranks,
                    speed_per_tick=kwargs.pop("speed_per_tick", 0.0), **kwargs)


class EnemyAiTests(unittest.TestCase):
    def test_given_a_distant_player_regiment_when_deciding_orders_then_the_enemy_holds_position(self):
        player = _regiment("p", 0, 0, True)
        enemy = _regiment("e", 0, ai.ENGAGE_DISTANCE + 50, False)
        battle = Battle(2000, 2000, [player, enemy])

        ai.decide_orders(battle)

        self.assertIsNone(enemy.attack_target)

    def test_given_a_nearby_player_regiment_when_deciding_orders_then_the_enemy_charges_it(self):
        player = _regiment("p", 0, 0, True)
        enemy = _regiment("e", 0, ai.ENGAGE_DISTANCE - 50, False)
        battle = Battle(2000, 2000, [player, enemy])

        ai.decide_orders(battle)

        self.assertEqual(enemy.attack_target, "p")

    def test_given_several_player_regiments_when_deciding_orders_then_the_nearest_one_is_targeted(self):
        near = _regiment("near", 0, 100, True)
        far = _regiment("far", 0, 300, True)
        enemy = _regiment("e", 0, 0, False)
        battle = Battle(2000, 2000, [near, far, enemy])

        ai.decide_orders(battle)

        self.assertEqual(enemy.attack_target, "near")

    def test_given_a_missile_regiment_in_range_when_deciding_orders_then_it_holds_and_does_not_charge(self):
        player = _regiment("p", 0, 100, True)
        archer = _regiment("a", 0, 0, False, missile_range=200.0)
        battle = Battle(2000, 2000, [player, archer])

        ai.decide_orders(battle)

        self.assertIsNone(archer.attack_target)

    def test_given_a_missile_regiment_out_of_range_but_within_engage_distance_when_deciding_then_it_charges(self):
        player = _regiment("p", 0, ai.ENGAGE_DISTANCE - 50, True)
        archer = _regiment("a", 0, 0, False, missile_range=20.0)
        battle = Battle(2000, 2000, [player, archer])

        ai.decide_orders(battle)

        self.assertEqual(archer.attack_target, "p")

    def test_given_a_routing_enemy_when_deciding_orders_then_it_is_left_fleeing_not_re_ordered(self):
        player = _regiment("p", 0, 50, True)
        enemy = _regiment("e", 0, 0, False, routing=True)
        battle = Battle(2000, 2000, [player, enemy])

        ai.decide_orders(battle)

        self.assertIsNone(enemy.attack_target)

    def test_given_no_player_regiments_left_when_deciding_orders_then_nothing_is_ordered(self):
        enemy = _regiment("e", 0, 0, False)
        destroyed_player = _regiment("p", 0, 10, True, models=0)
        battle = Battle(2000, 2000, [enemy, destroyed_player])

        ai.decide_orders(battle)  # must not raise on an empty target list

        self.assertIsNone(enemy.attack_target)


if __name__ == "__main__":
    unittest.main()
