import unittest

from whshr.engine import Battle, Regiment


class BattleTests(unittest.TestCase):
    def setUp(self):
        self.player = Regiment("player", "Player", 10, 10, 0, True)
        self.enemy = Regiment("enemy", "Enemy", 30, 30, 0, False)
        self.battle = Battle(100, 100, [self.player, self.enemy], move_speed=60)

    def test_given_player_regiment_when_ordered_inside_field_then_it_moves_and_faces_destination(self):
        self.battle.order_move("player", 70, 10)
        self.battle.tick()

        self.assertEqual((self.player.x, self.player.y), (11, 10))
        self.assertEqual(self.player.direction, 128)
        self.assertTrue(self.player.moving)

    def test_given_nearby_destination_when_tick_reaches_it_then_order_completes_without_overshoot(self):
        self.battle.order_move("player", 10.5, 10)
        self.battle.tick()

        self.assertEqual((self.player.x, self.player.y), (10.5, 10))
        self.assertFalse(self.player.moving)

    def test_given_enemy_or_outside_destination_when_ordered_then_the_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_move("enemy", 20, 20)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.battle.order_move("player", 101, 10)


if __name__ == "__main__":
    unittest.main()
