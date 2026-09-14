import math
import unittest

from whshr.engine import Battle, Regiment, TICK_SECONDS, speed_per_tick


class BattleTests(unittest.TestCase):
    def setUp(self):
        # M4 I3, matching the game_rules.md worked example: s_rlmv = trunc(4.8*4+3)/2 = 11.
        self.speed = speed_per_tick(4, 3)
        self.player = Regiment("player", "Player", 10, 10, 0, True, models=1, ranks=1,
                               speed_per_tick=self.speed)
        self.enemy = Regiment("enemy", "Enemy", 30, 30, 0, False, models=1, ranks=1,
                              speed_per_tick=self.speed)
        self.battle = Battle(100, 100, [self.player, self.enemy])

    def test_given_player_regiment_when_ordered_inside_field_then_it_moves_and_faces_destination(self):
        self.battle.order_move("player", 70, 10)
        self.battle.tick()

        step = self.speed
        self.assertAlmostEqual(self.player.x, 10 + step)
        self.assertAlmostEqual(self.player.y, 10)
        self.assertEqual(self.player.direction, 128)
        self.assertTrue(self.player.moving)
        self.assertTrue(self.player.walking)

    def test_given_nearby_destination_when_tick_reaches_it_then_order_completes_without_overshoot(self):
        self.battle.order_move("player", self.player.x + self.speed / 2, self.player.y)
        self.battle.tick()

        self.assertAlmostEqual(self.player.x, 10 + self.speed / 2)
        self.assertFalse(self.player.moving)

    def test_given_enemy_or_outside_destination_when_ordered_then_the_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_move("enemy", 20, 20)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.battle.order_move("player", 101, 10)

    def test_given_documented_movement_stat_when_computing_speed_then_it_matches_the_worked_example(self):
        # game_rules.md: "An M4 I3 infantry unit covers about 9.8 inches per turn moving freely."
        per_turn_inches = speed_per_tick(4, 3) * 190 / 24  # 190 ticks per turn, 24 world units per inch
        self.assertAlmostEqual(per_turn_inches, 9.8, places=1)

    def test_given_a_regiment_without_a_decoded_profile_when_built_then_it_gets_the_documented_placeholder(self):
        self.assertEqual(speed_per_tick(None, None), speed_per_tick(4, 3))


class FormationMovementTests(unittest.TestCase):
    """Models walk to their formation slots instead of teleporting with the block."""

    def setUp(self):
        self.speed = speed_per_tick(4, 3)
        self.regiment = Regiment("player", "Player", 0, 0, 0, True, models=6, ranks=2,
                                 speed_per_tick=self.speed)
        self.battle = Battle(1000, 1000, [self.regiment])

    def test_given_a_regiment_when_it_first_ticks_then_models_start_already_in_formation(self):
        self.battle.tick()

        self.assertEqual(len(self.regiment.model_positions()), 6)
        self.assertFalse(self.regiment.walking)

    def test_given_a_turning_order_when_ticked_once_then_models_have_not_yet_reached_their_new_slots(self):
        # A destination to the side turns the block, so a rigid teleport and a catch-up walk disagree.
        self.battle.order_move("player", 500, 0)

        self.battle.tick()

        positions, ideal = self.regiment.model_positions(), formation_positions(self.regiment)
        distances = [math.hypot(x - ix, y - iy) for (x, y), (ix, iy) in zip(positions, ideal)]
        self.assertTrue(any(distance > 1.0 for distance in distances))
        self.assertTrue(self.regiment.walking)

    def test_given_a_regiment_walking_to_a_far_order_when_many_ticks_pass_then_it_settles_back_in_formation(self):
        self.battle.order_move("player", 500, 0)
        for _ in range(2000):
            self.battle.tick()

        self.assertFalse(self.regiment.moving)
        self.assertFalse(self.regiment.walking)
        expected = formation_positions(self.regiment)
        for (x, y), (ex, ey) in zip(self.regiment.model_positions(), expected):
            self.assertAlmostEqual(x, ex, places=2)
            self.assertAlmostEqual(y, ey, places=2)


def formation_positions(regiment):
    from whshr import formation
    return formation.place(regiment.x, regiment.y, regiment.direction,
                           formation.block_slots(regiment.models, regiment.ranks))


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.player = Regiment("player", "Player", 100, 100, 0, True, models=18, ranks=4)
        self.enemy = Regiment("enemy", "Enemy", 300, 300, 0, False, models=18, ranks=4)
        self.battle = Battle(1000, 1000, [self.player, self.enemy])

    def test_given_a_point_inside_a_player_regiment_when_picked_then_its_identifier_is_returned(self):
        self.assertEqual(self.battle.regiment_at(100, 100), "player")

    def test_given_a_point_inside_an_enemy_regiment_when_picked_then_it_is_not_selectable(self):
        self.assertIsNone(self.battle.regiment_at(300, 300))

    def test_given_an_empty_point_when_picked_then_nothing_is_returned(self):
        self.assertIsNone(self.battle.regiment_at(500, 500))


class CollisionTests(unittest.TestCase):
    """Simple, deterministic collisions: regiments do not end up walking through each other."""

    def test_given_two_regiments_ordered_into_each_other_when_ticked_then_their_footprints_stop_overlapping(self):
        left = Regiment("left", "Left", 0, 0, 0, True, models=18, ranks=4, speed_per_tick=5.0)
        right = Regiment("right", "Right", 200, 0, 0, True, models=18, ranks=4, speed_per_tick=5.0)
        battle = Battle(1000, 1000, [left, right])
        battle.order_move("left", 300, 0)
        battle.order_move("right", 0, 0)

        for _ in range(80):
            battle.tick()

        distance = math.hypot(right.x - left.x, right.y - left.y)
        self.assertGreaterEqual(distance, left.bounding_radius() + right.bounding_radius() - 1e-6)

    def test_given_regiments_deployed_overlapping_when_no_orders_are_given_then_neither_is_pushed(self):
        # BF001 deploys the Grudgebringer cavalry and infantry closer than their bounding circles.
        cavalry = Regiment("cavalry", "Cavalry", 1090, 639, 0, True, models=12, ranks=3)
        infantry = Regiment("infantry", "Infantry", 1112, 585, 0, True, models=16, ranks=4)
        battle = Battle(1600, 1760, [cavalry, infantry])

        for _ in range(10):
            battle.tick()

        self.assertEqual((cavalry.x, cavalry.y, infantry.x, infantry.y), (1090, 639, 1112, 585))
        self.assertFalse(cavalry.walking or infantry.walking)

    def test_given_regiment_ordered_into_a_standing_one_when_ticked_then_only_the_moving_regiment_gives_way(self):
        standing = Regiment("standing", "Standing", 200, 0, 0, True, models=18, ranks=4, speed_per_tick=5.0)
        walker = Regiment("walker", "Walker", 0, 0, 0, True, models=18, ranks=4, speed_per_tick=5.0)
        battle = Battle(1000, 1000, [standing, walker])
        battle.order_move("walker", 400, 0)

        for _ in range(80):
            battle.tick()

        self.assertEqual((standing.x, standing.y), (200, 0))
        distance = math.hypot(standing.x - walker.x, standing.y - walker.y)
        self.assertGreaterEqual(distance, standing.bounding_radius() + walker.bounding_radius() - 1e-6)


class AttackOrderTests(unittest.TestCase):
    def setUp(self):
        self.player = Regiment("player", "Player", 0, 0, 0, True, models=10, ranks=2, speed_per_tick=5.0)
        self.enemy = Regiment("enemy", "Enemy", 300, 0, 0, False, models=10, ranks=2, speed_per_tick=5.0)
        self.battle = Battle(1000, 1000, [self.player, self.enemy])

    def test_given_a_player_regiment_when_ordered_to_attack_an_enemy_then_it_charges_toward_it(self):
        self.battle.order_attack("player", "enemy")
        self.battle.tick()

        self.assertEqual(self.player.attack_target, "enemy")
        self.assertGreater(self.player.x, 0)  # moved toward the enemy
        self.assertIsNone(self.player.target_x)  # not an ordinary move order

    def test_given_an_attack_order_against_a_player_regiment_then_it_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "enemy regiment"):
            self.battle.order_attack("player", "player")

    def test_given_a_non_player_regiment_when_ordered_to_attack_then_it_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_attack("enemy", "player")

    def test_given_two_regiments_charging_each_other_when_they_touch_then_they_enter_melee(self):
        self.battle.order_attack("player", "enemy")
        self.enemy.attack_target = "player"  # enemy is not player-controlled: drive it directly for the test

        for _ in range(80):
            self.battle.tick()
            if self.player.in_melee:
                break

        self.assertTrue(self.player.in_melee)
        self.assertTrue(self.enemy.in_melee)
        self.assertFalse(self.player.moving)


class BattleOutcomeTests(unittest.TestCase):
    """A full, deterministic battle resolves to a win or lose condition and stops simulating."""

    def test_given_an_overwhelming_player_force_when_battle_runs_then_it_ends_in_victory(self):
        player = Regiment("player", "Player", 0, 0, 0, True, models=40, ranks=4, speed_per_tick=6.0,
                          ws=6, strength=6, attacks=3, leadership=9)
        enemy = Regiment("enemy", "Enemy", 60, 0, 0, False, models=5, ranks=1, speed_per_tick=6.0,
                         ws=1, toughness=1, leadership=2)
        battle = Battle(1000, 1000, [player, enemy], seed=7)
        battle.order_attack("player", "enemy")

        for _ in range(500):
            battle.tick()
            if battle.result is not None:
                break

        self.assertEqual(battle.result, "victory")
        self.assertLess(battle.tick_count, 500)
        # the battle stops simulating once resolved: later ticks are no-ops
        ticks_at_result = battle.tick_count
        battle.tick()
        self.assertEqual(battle.tick_count, ticks_at_result + 1)
        self.assertEqual(battle.events, [])

    def test_given_an_overwhelming_enemy_force_when_battle_runs_then_it_ends_in_defeat(self):
        player = Regiment("player", "Player", 0, 0, 0, True, models=5, ranks=1, speed_per_tick=6.0,
                          ws=1, toughness=1, leadership=2)
        enemy = Regiment("enemy", "Enemy", 60, 0, 0, False, models=40, ranks=4, speed_per_tick=6.0,
                         ws=6, strength=6, attacks=3, leadership=9)
        battle = Battle(1000, 1000, [player, enemy], seed=11)
        enemy.attack_target = "player"

        for _ in range(500):
            battle.tick()
            if battle.result is not None:
                break

        self.assertEqual(battle.result, "defeat")


if __name__ == "__main__":
    unittest.main()
