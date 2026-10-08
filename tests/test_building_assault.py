"""Charging, fighting and destroying a building without scripts (notes/building_units.md 4-7)."""

import unittest

from whshr.engine import Battle, Regiment
from whshr.rules import Side

HUT = [{"name": "WoodShack", "x": 1000, "y": 1300, "dir": 0}]  # +-42 x +-24, W 3, T 3


def regiment(identifier="P", x=1000, y=900, models=20, side=Side.PLAYER, facing=0):
    return Regiment(identifier, identifier, x, y, facing, side, models=models, ranks=2, unit_class=1)


def battle_with(*regiments, scenery=HUT):
    battle = Battle(3000, 3000, list(regiments), seed=1995, scenery=scenery)
    battle.phase = "battle"
    return battle


def run(battle, ticks):
    for _ in range(ticks):
        battle.tick()


class AssaultTests(unittest.TestCase):
    def test_a_charge_on_a_building_ends_in_an_assault_that_destroys_it(self):
        unit = regiment()
        battle = battle_with(unit)
        battle.order_attack_building("P", "building:0")
        run(battle, 1500)
        building = battle.buildings[0]
        self.assertTrue(building.destroyed)
        self.assertIsNone(unit.assaulting_building)
        self.assertIsNone(unit.attack_target)

    def test_the_assault_starts_on_contact_with_the_target_building(self):
        unit = regiment()
        battle = battle_with(unit)
        battle.order_attack_building("P", "building:0")
        for _ in range(1500):
            battle.tick()
            if unit.assaulting_building:
                break
        self.assertEqual(unit.assaulting_building, "building:0")
        self.assertIsNone(unit.attack_target)

    def test_a_walking_regiment_is_pushed_clear_of_a_building_footprint(self):
        unit = regiment(y=1200)
        battle = battle_with(unit)
        unit.target_x, unit.target_y = 1000, 1400  # walk straight through the hut
        run(battle, 600)
        building = battle.buildings[0]
        self.assertIsNone(unit.assaulting_building)
        self.assertIsNone(building.penetration(*Battle.formation_centre(unit), unit.bounding_radius() - 1))
        self.assertFalse(building.destroyed)

    def test_a_charge_that_touches_a_non_target_building_ends_there(self):
        unit, enemy = regiment(), regiment("E", 1000, 2200, side=Side.ENEMY, facing=256)
        battle = battle_with(unit, enemy)
        unit.attack_target = unit.charge_started_target = "E"  # a charge under way, straight through the hut
        run(battle, 1500)
        self.assertIsNone(unit.attack_target)
        self.assertIsNone(unit.assaulting_building)
        self.assertLess(unit.y, 1300)

    def test_a_destroyed_building_still_pushes_regiments_apart(self):
        unit = regiment(y=1200)
        battle = battle_with(unit)
        battle.destroy_building(battle.buildings[0])
        unit.target_x, unit.target_y = 1000, 1400
        run(battle, 600)
        building = battle.buildings[0]
        self.assertIsNone(building.penetration(*Battle.formation_centre(unit), unit.bounding_radius() - 1))

    def test_a_destroyed_building_cannot_be_ordered_against(self):
        battle = battle_with(regiment())
        battle.destroy_building(battle.buildings[0])
        with self.assertRaises(ValueError):
            battle.order_attack_building("P", "building:0")

    def test_the_fall_releases_every_assaulting_regiment(self):
        first, second = regiment("P"), regiment("Q", 1040, 900)
        battle = battle_with(first, second)
        first.assaulting_building = second.assaulting_building = "building:0"
        battle.destroy_building(battle.buildings[0])
        self.assertEqual((first.assaulting_building, second.assaulting_building), (None, None))


if __name__ == "__main__":
    unittest.main()
