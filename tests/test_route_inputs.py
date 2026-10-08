import math
"""BDD scenarios for the route-planning inputs (notes/obstacle_steering.md sections 2, 3, 5, 6 and
notes/bf003_peasant_move_obstruction.md): reference point, unit relationship filter, route pause."""
import unittest

from whshr import interpreter
from whshr.engine import Battle, MOVING_FREELY_K, Regiment, speed_per_tick
from whshr.rules import Side


def _reg(identifier, x, y, side=Side.PLAYER, direction=0, **kwargs):
    models = kwargs.pop("models", 1)
    ranks = kwargs.pop("ranks", 1)
    return Regiment(identifier, identifier, x, y, direction, side, models=models, ranks=ranks, **kwargs)


class RouteReferencePointTests(unittest.TestCase):
    def test_given_block_facing_plus_y_then_reference_is_front_rank_not_centre(self):
        block = _reg("a", 100, 100, direction=0, models=20, ranks=4)
        self.assertEqual(Battle.route_reference_point(block), (100, 100))
        centre = Battle.formation_centre(block)
        self.assertAlmostEqual(centre[1], 100 - 18)
        self.assertNotEqual(Battle.route_reference_point(block), centre)

    def test_given_block_facing_plus_x_then_reference_is_front_rank_not_centre(self):
        block = _reg("a", 100, 100, direction=128, models=20, ranks=4)
        self.assertEqual(Battle.route_reference_point(block), (100, 100))
        self.assertAlmostEqual(Battle.formation_centre(block)[0], 100 - 18)


class RouteUnitRelationTests(unittest.TestCase):
    def setUp(self):
        self.speed = speed_per_tick(4, 3)  # s_rlmv = 11.0
        self.s_rlmv = self.speed * 16 / MOVING_FREELY_K
        self.mover = _reg("mover", 100, 100, speed_per_tick=self.speed)
        self.ally = _reg("ally", 160, 100, Side.NEUTRAL, speed_per_tick=self.speed)
        self.enemy = _reg("enemy", 160, 100, Side.ENEMY, speed_per_tick=self.speed)
        self.battle = Battle(1000, 1000, [self.mover, self.ally, self.enemy])

    def rel(self, other, trial=False):
        return self.battle.route_unit_relation(self.mover, other, trial)

    def test_wagon_is_never_blocked(self):
        wagon = _reg("wagon", 100, 100, unit_class=7, models=2, speed_per_tick=self.speed)
        self.assertTrue(wagon.is_wagon)
        self.assertEqual(self.battle.route_unit_relation(wagon, self.enemy, False), "ignore")

    def test_unit_at_or_beyond_threat_range_is_ignored(self):
        self.battle.event_bus.unit_states["mover"] = interpreter.UnitScriptState(script_id=0)
        self.battle.event_bus.unit_states["mover"].threat_range = 60
        self.assertEqual(self.rel(self.enemy), "ignore")  # distance exactly 60
        self.battle.event_bus.unit_states["mover"].threat_range = 61
        self.assertEqual(self.rel(self.enemy), "block")

    def test_unit_leaving_battle_is_ignored(self):
        state = interpreter.UnitScriptState(script_id=0)
        state.unit_flags = interpreter.LEAVING_BATTLE_FLAG
        self.battle.event_bus.unit_states["enemy"] = state
        self.assertEqual(self.rel(self.enemy), "ignore")

    def test_enemy_blocks_except_in_trials_hidden_or_broken(self):
        self.assertEqual(self.rel(self.enemy), "block")
        self.assertEqual(self.rel(self.enemy, trial=True), "ignore")
        self.enemy.hidden = True
        self.assertEqual(self.rel(self.enemy), "ignore")
        self.enemy.hidden = False
        self.enemy.routing = True
        self.assertEqual(self.rel(self.enemy), "ignore")

    def test_current_target_or_group_never_blocks(self):
        self.mover.attack_target = "ally"
        self.assertEqual(self.rel(self.ally), "ignore")
        self.mover.attack_target = None
        self.mover.melee_group = self.ally.melee_group = "g"
        self.assertEqual(self.rel(self.ally), "ignore")

    @staticmethod
    def _move(unit):
        """Give a unit a move along its facing: its effective speed is then its travel speed (section 6)."""
        angle = unit.direction * math.tau / 512
        unit.target_x, unit.target_y = unit.x + 100 * math.sin(angle), unit.y + 100 * math.cos(angle)

    def test_similar_direction_blocks_only_when_mover_is_faster(self):
        self.ally.direction = 63
        self.assertEqual(self.rel(self.ally), "ignore")  # both stationary
        self._move(self.mover)
        self.assertEqual(self.rel(self.ally), "block")
        self._move(self.ally)
        self.assertEqual(self.rel(self.ally), "ignore")  # equally fast

    def test_opposing_direction_faster_mover_blocks(self):
        self.ally.direction = 64
        self._move(self.mover)
        self.assertEqual(self.rel(self.ally), "block")

    def test_a_stationary_friend_never_pauses_a_moving_mover(self):
        self.ally.direction = 256
        self._move(self.mover)
        self.assertEqual(self.rel(self.ally), "block")

    def test_a_near_friend_moving_as_fast_pauses_the_mover(self):
        self.ally.direction = 256
        self._move(self.mover)
        self._move(self.ally)
        self.assertEqual(self.rel(self.ally), "pause")

    # notes/convoy_jam_and_melee_obstacles.md B.1-B.2: a friendly unit in melee or braced has effective speed 0.
    def test_a_friend_fighting_in_melee_is_an_obstacle_not_a_pause_even_with_its_attack_target(self):
        self.ally.direction = 128
        self._move(self.mover)
        self.ally.attack_target, self.ally.in_melee = "enemy", True
        self.assertEqual(self.battle.route_effective_speed(self.ally), 0.0)
        self.assertEqual(self.rel(self.ally), "block")

    def test_a_braced_friend_is_an_obstacle_not_a_pause(self):
        self.ally.direction = 128
        self._move(self.mover)
        self.ally.braced = True
        self.assertEqual(self.rel(self.ally), "block")

    def test_a_friend_that_broke_while_braced_moves_at_flight_speed(self):
        self.ally.braced, self.ally.routing = True, True
        self.assertGreater(self.battle.route_effective_speed(self.ally), 0.0)

    def test_a_friend_still_charging_across_the_path_pauses_the_mover(self):
        self.ally.direction = 128
        self._move(self.mover)
        self.ally.attack_target = "enemy"  # charging, not yet in contact: charge speed
        self.assertGreater(self.battle.route_effective_speed(self.ally), self.battle.route_effective_speed(self.mover))
        self.assertEqual(self.rel(self.ally), "pause")

    def test_the_plan_at_a_new_order_treats_the_mover_as_stationary(self):
        self.ally.direction = 256
        self._move(self.mover)
        self.assertEqual(self.battle.route_unit_relation(self.mover, self.ally, True, mover_speed=0.0), "pause")

    def test_opposing_direction_near_unit_pauses_using_s_rlmv_not_frontage(self):
        self.ally.direction = 256
        self.assertEqual(self.s_rlmv, 11.0)
        # distance 60 < 16 * 11 = 176 (frontage 1 would give only 16)
        self.assertEqual(self.rel(self.ally), "pause")
        self.ally.x = 100 + 175
        self.assertEqual(self.rel(self.ally), "pause")
        self.ally.x = 100 + 176
        self.assertEqual(self.rel(self.ally), "block")

    def test_octagonal_distance_is_used(self):
        self.ally.direction = 256
        self.ally.x, self.ally.y = 100 + 120, 100 + 120  # 120 + 60 = 180 >= 176
        self.assertEqual(self.rel(self.ally), "block")


class RoutePauseTests(unittest.TestCase):
    def setUp(self):
        self.speed = speed_per_tick(4, 3)
        self.player = _reg("player", 10, 10, speed_per_tick=self.speed)
        self.far = _reg("far", 990, 990, Side.ENEMY, speed_per_tick=self.speed)
        self.battle = Battle(1000, 1000, [self.player, self.far])
        self.battle.order_move("player", 10, 500)
        for _ in range(30):
            self.battle.tick()

    def test_paused_regiment_stays_put_for_exactly_the_pause_then_resumes(self):
        self.battle.pause_route(self.player)
        self.assertEqual(self.player.route_pause_ticks, 54)
        before = (self.player.x, self.player.y)
        for _ in range(54):
            self.battle.tick()
            self.assertEqual((self.player.x, self.player.y), before)
            self.assertEqual((self.player.target_x, self.player.target_y), (10, 500))
        self.assertEqual(self.player.route_pause_ticks, 0)
        self.battle.tick()
        self.assertNotEqual((self.player.x, self.player.y), before)
        self.assertTrue(self.player.moving)

    def test_new_order_and_halt_clear_the_pause(self):
        self.battle.pause_route(self.player)
        self.battle.order_move("player", 500, 10)
        self.assertEqual(self.player.route_pause_ticks, 0)
        self.battle.pause_route(self.player)
        self.battle.order_halt("player")
        self.assertEqual(self.player.route_pause_ticks, 0)

    def test_pause_counter_is_dropped_when_regiment_has_no_order(self):
        self.battle.order_halt("player")
        self.battle.pause_route(self.player, 5)
        self.battle.tick()
        self.assertEqual(self.player.route_pause_ticks, 0)


if __name__ == "__main__":
    unittest.main()
