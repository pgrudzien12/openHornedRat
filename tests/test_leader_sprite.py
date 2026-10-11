"""The leader figure is drawn and animated with the leader block's own sprite set (notes/leader_figure_sprite.md)."""
import math
import unittest

from whshr import animation, combat
from whshr.engine import Battle, Regiment, has_leader_figure, wagon_layout_direction
from whshr.rules import Side


def cavalry(leader_sprite: str | None = "MercCaptain", has_leader: bool = True) -> tuple[Battle, Regiment]:
    regiment = Regiment("r", "Grudgebringer Cavalry", 500, 500, 0, Side.PLAYER, models=6, ranks=2,
                        sprite="BorderHorse", leader_sprite=leader_sprite, has_leader=has_leader)
    battle = Battle(2000, 2000, [regiment], seed=1995)
    battle.tick()
    return battle, regiment


def leader_index(regiment: Regiment) -> int:
    index = regiment.living_leader_index
    assert index is not None
    return index


def cart(leader_sprite: str = "Wagon") -> Regiment:
    regiment = Regiment("c", "Horse and cart", 500, 500, 384, Side.PLAYER, models=2, ranks=2,
                        sprite="PackPony", leader_sprite=leader_sprite, has_leader=True, unit_class=7)
    Battle(2000, 2000, [regiment], seed=1995).tick()
    return regiment


class LeaderFigureSpriteTests(unittest.TestCase):
    def test_given_a_leader_block_sprite_when_loaded_then_only_the_leader_figure_uses_it(self):
        _battle, regiment = cavalry()

        sprites = [regiment.model_sprite(model) for model in regiment.melee_models]

        self.assertEqual(sprites[leader_index(regiment)], "MercCaptain")
        self.assertEqual(sprites.count("MercCaptain"), 1)
        self.assertEqual(sprites.count("BorderHorse"), len(sprites) - 1)

    def test_given_no_leader_figure_when_loaded_then_every_figure_uses_the_troop_set(self):
        _battle, regiment = cavalry(has_leader=False)

        self.assertEqual({regiment.model_sprite(model) for model in regiment.melee_models}, {"BorderHorse"})

    def test_given_a_leader_block_with_a_void_sprite_then_the_unit_has_no_leader_figure(self):
        self.assertFalse(has_leader_figure({"sprites": "VoidType,0"}))
        self.assertFalse(has_leader_figure({}))
        self.assertTrue(has_leader_figure({"sprites": "MercCaptain,0"}))

    def test_given_a_leader_set_of_another_family_then_the_leader_animates_with_its_own_family(self):
        _battle, regiment = cavalry(leader_sprite="Peasants")
        leader = regiment.melee_models[leader_index(regiment)]
        trooper = next(model for model in regiment.melee_models if model is not leader)

        self.assertEqual(regiment.model_family(leader), "peasants")
        self.assertEqual(regiment.model_family(trooper), animation.DEFAULT_FAMILY)

    def test_given_the_leader_killed_when_it_collapses_then_its_corpse_uses_the_leader_set(self):
        battle, regiment = cavalry()
        index = leader_index(regiment)

        combat.kill_models(regiment, [index], battle)
        for _ in range(40):
            battle.tick()

        self.assertEqual([corpse.sprite for corpse in regiment.corpses], ["MercCaptain"])

    def test_given_the_leader_dead_then_no_surviving_figure_takes_the_leader_set(self):
        battle, regiment = cavalry()

        combat.kill_models(regiment, [leader_index(regiment)], battle)
        for _ in range(40):
            battle.tick()
        battle.reform_to_ranks(regiment, 2)

        self.assertIsNone(regiment.living_leader_index)
        self.assertEqual({regiment.model_sprite(model) for model in regiment.melee_models}, {"BorderHorse"})

    def test_given_a_trooper_killed_then_its_corpse_uses_the_troop_set(self):
        battle, regiment = cavalry()
        trooper = next(i for i in range(len(regiment.melee_models)) if i != leader_index(regiment))

        combat.kill_models(regiment, [trooper], battle)
        for _ in range(40):
            battle.tick()

        self.assertEqual([corpse.sprite for corpse in regiment.corpses], ["BorderHorse"])


if __name__ == "__main__":
    unittest.main()


class WagonTeamTests(unittest.TestCase):
    def test_given_a_cart_unit_then_the_wagon_is_the_rear_figure_and_the_team_leads(self):
        regiment = cart()

        self.assertEqual([regiment.model_sprite(model) for model in regiment.melee_models], ["PackPony", "Wagon"])
        self.assertEqual(regiment.living_leader_index, 1)

    def test_given_a_cart_unit_then_the_team_animates_as_horses_and_the_wagon_as_a_wagon(self):
        regiment = cart()

        families = [regiment.model_family(model) for model in regiment.melee_models]

        self.assertEqual(families, ["standard_infantry", "wagons"])

    def test_given_caravan_or_war_wagon_leaders_then_they_use_their_single_look(self):
        for sprite in ("Caravan", "MrtWagon"):
            regiment = cart(sprite)
            table = animation.family_table(regiment.model_family(regiment.melee_models[1]))
            self.assertEqual(animation.script_group(table[animation.WALK], 29), 0)
            self.assertEqual(animation.script_group(table[animation.WALK], 2), 0)


class WagonCameraLayoutTests(unittest.TestCase):
    """notes/wagon_camera_snap.md 3: the camera only re-places a two-figure wagon's figures."""

    def test_layout_direction_follows_the_camera_shifted_grid(self):
        for view, expected in ((0, 128), (10, 74), (20, 84), (64, 128)):
            self.assertEqual(wagon_layout_direction(100, view), expected)

    def test_given_a_driving_wagon_then_the_layout_tilts_but_the_facing_stays(self):
        expected = {0: 128, 4: 132, 32: 160, 36: 100, 40: 104}
        for view, direction in expected.items():
            self.assertEqual(wagon_layout_direction(128, view), direction)

    def test_given_a_turning_camera_then_the_cart_keeps_its_facing_and_drives_as_far_as_with_a_still_camera(self):
        def drive(rotate: bool) -> tuple[float, float, float]:
            regiment = Regiment("c", "Horse and cart", 500, 500, 128, Side.PLAYER, models=2, ranks=2,
                                sprite="PackPony", leader_sprite="Wagon", has_leader=True, unit_class=7)
            battle = Battle(2000, 2000, [regiment], seed=1995)
            battle.order_move("c", 700, 500)
            for tick in range(10):
                if rotate:
                    battle.set_view_angle(tick * 4)
                battle.tick()
            return regiment.x, regiment.y, regiment.direction

        self.assertEqual(drive(True), drive(False))

    def test_given_a_cart_then_team_and_wagon_stand_22_apart_with_the_team_in_front(self):
        regiment = cart()
        team, wagon = regiment.positions
        self.assertAlmostEqual(math.dist(team, wagon), 22)
        self.assertLess(team[0], wagon[0])  # facing 384 is -X: the team is further along it
