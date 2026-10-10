"""Building pseudo-units (GitHub issue #173): creation from furniture, missile damage, destruction, the fire order
event and the node-area side-32 query (notes/battle_end_objectives.md 12.1, notes/ranged_combat_handoff.md)."""

import unittest

from whshr import buildings, interpreter, objectives
from whshr.engine import Battle, Regiment
from whshr.nodes import ScriptNode
from whshr.ranged import Projectile
from whshr import ranged
from whshr.rules import Side

SCENERY = [{"name": "Tree1", "x": 10, "y": 10}, {"name": "Farm", "x": 500, "y": 500},
           {"name": "WoodShack", "x": 900, "y": 900}, {"name": "HumanTent", "x": 100, "y": 100}]


def battle(scenery=SCENERY):
    shooter = Regiment("S", "S", 0, 0, 0, Side.PLAYER, models=5, ranks=1, unit_class=1)
    return Battle(2000, 2000, [shooter], seed=1995, scenery=scenery)


def cannonball(x, y, strength=6, wounds=6, radius=0):
    return Projectile(source="S", code=0, x0=x, y0=y, z0=0, x1=x, y1=y, z1=0, radius=radius, strength=3,
                      wounds=wounds, building_strength=strength, x=x, y=y)


class CreationTests(unittest.TestCase):
    def test_only_building_type_furniture_becomes_a_building(self):
        b = battle()
        self.assertEqual([x.name for x in b.buildings], ["Farm", "WoodShack", "HumanTent"])

    def test_identifier_is_the_furniture_position_and_wounds_follow_the_type(self):
        b = battle()
        self.assertEqual([(x.identifier, x.wounds_to_destroy, x.models) for x in b.buildings],
                         [("building:1", 6, 3), ("building:2", 3, 1), ("building:3", 1, 1)])

    def test_objective_count_drops_when_a_building_is_destroyed(self):
        b = battle()
        self.assertEqual(objectives.building_count(b), 3)
        b.destroy_building(b.buildings[0])
        self.assertEqual(objectives.building_count(b), 2)


class FootprintTests(unittest.TestCase):
    """Vectors from notes/building_units.md section 2 and 8."""

    def test_footprint_rectangle_radius_and_toughness_follow_the_type_table(self):
        for name, half, radius, toughness in (("Tudor2Stry", (36, 24), 31, 5), ("Farm", (72, 72), 89, 5),
                                              ("Well2", (18, 18), 13, 2), ("SmithyHut", (54, 60), 68, 4),
                                              ("SkavBase20FaL", (90, 90), 115, 5), ("WoodShack", (42, 24), 36, 3)):
            with self.subTest(name=name):
                building = buildings.from_scenery([{"name": name, "x": 500, "y": 500}])[0]
                self.assertEqual(((building.half_x, building.half_y), building.radius, building.toughness),
                                 (half, radius, toughness))

    def test_a_circle_is_pushed_clear_of_a_turned_rectangle(self):
        farm = buildings.from_scenery([{"name": "Tudor2Stry", "x": 0, "y": 0, "dir": 128}])[0]  # turned 90 degrees
        self.assertIsNone(farm.penetration(60, 0, 10))  # long side (36) now points along y, short (24) along x
        push = farm.penetration(30, 0, 10)
        self.assertAlmostEqual(push[0], 4.0, places=6)
        self.assertAlmostEqual(push[1], 0.0, places=6)
        self.assertIsNone(farm.penetration(0, 40, 2))  # beyond the long half-extent of 36 along y
        self.assertIsNotNone(farm.penetration(0, 30, 10))

    def test_a_centre_inside_the_rectangle_is_pushed_out_along_the_nearest_side(self):
        farm = buildings.from_scenery([{"name": "Tudor2Stry", "x": 0, "y": 0}])[0]
        push = farm.penetration(0, 20, 5)
        self.assertEqual(push[0], 0.0)
        self.assertGreater(push[1], 0)

    def test_missile_toughness_is_zero_and_strength_eight_wounds_automatically(self):
        b = battle()
        tent = b.buildings[2]
        for _ in range(20):  # strength 10 never needs a roll: every hit wounds at least once
            tent.wounds_taken, tent.destroyed = 0, False
            ranged._damage_buildings(b, cannonball(tent.x, tent.y, strength=10, wounds=1), flight=False)
            self.assertTrue(tent.destroyed)


class DamageTests(unittest.TestCase):
    def test_wounds_accumulate_until_the_building_is_destroyed(self):
        farm = battle().buildings[0]
        self.assertFalse(farm.take_wounds(5))
        self.assertTrue(farm.take_wounds(1))
        self.assertEqual((farm.destroyed, farm.models), (True, 0))

    def test_a_direct_cannon_hit_can_destroy_a_tent_and_event_0x18_reaches_scripted_units(self):
        b = battle()
        tent = b.buildings[2]
        for _ in range(60):
            ranged._damage_buildings(b, cannonball(tent.x, tent.y), flight=False)
            if tent.destroyed:
                break
        self.assertTrue(tent.destroyed)
        queue = b.event_bus.unit_states["S"].event_queue
        self.assertIn((0x18, "building:3"), [(e.code, e.source) for e in queue])
        solid = [o for o in b.shooting_objects if o.get("building") == "building:3"]
        self.assertEqual(solid[0]["status"], ["os_active", "os_solid"])  # the ruin keeps blocking

    def test_a_missile_without_building_strength_does_no_damage(self):
        b = battle()
        farm = b.buildings[0]
        ranged._damage_buildings(b, cannonball(farm.x, farm.y, strength=0), flight=False)
        self.assertEqual(farm.wounds_taken, 0)

    def test_a_miss_outside_footprint_and_blast_does_no_damage(self):
        b = battle()
        farm = b.buildings[0]
        for _ in range(30):
            ranged._damage_buildings(b, cannonball(farm.x + 200, farm.y, radius=20), flight=False)
        self.assertEqual(farm.wounds_taken, 0)

    def test_blast_margin_wounds_once_per_hit_at_half_strength(self):
        b = battle()
        farm = b.buildings[0]
        for _ in range(40):
            ranged._damage_buildings(b, cannonball(farm.x + farm.radius + 5, farm.y, radius=20, wounds=6),
                                     flight=False)
        self.assertTrue(0 < farm.wounds_taken <= 40 and farm.wounds_taken < 6 or farm.destroyed)

    def test_a_destroyed_building_takes_no_more_damage(self):
        b = battle()
        tent = b.buildings[2]
        b.destroy_building(tent)
        before = len(b.events)
        ranged._damage_buildings(b, cannonball(tent.x, tent.y), flight=False)
        self.assertEqual(len(b.events), before)


class KillCreditTests(unittest.TestCase):
    """notes/casualty_bookkeeping.md 2.1: +1 kill per piece, no experience; lethal-only sources are credited only
    by the destroying wound, melee by any wound."""

    def test_the_destroyer_gains_a_kill_per_piece_and_no_experience(self):
        b = battle()
        farm = b.buildings[0]  # three pieces
        farm.take_wounds(6, "S", lethal_only=True)
        b.destroy_building(farm)
        self.assertEqual((b.regiments["S"].kills, b.regiments["S"].experience_gained), (3, 0))

    def test_a_single_piece_building_is_worth_one_kill(self):
        b = battle()
        tent = b.buildings[2]
        tent.take_wounds(1, "S", lethal_only=True)
        b.destroy_building(tent)
        self.assertEqual(b.regiments["S"].kills, 1)

    def test_a_non_lethal_missile_wound_leaves_the_credit_and_a_melee_wound_takes_it(self):
        farm = battle().buildings[0]
        farm.take_wounds(1, "M", lethal_only=True)
        self.assertIsNone(farm.credit)
        farm.take_wounds(1, "M")
        self.assertEqual(farm.credit, "M")
        farm.take_wounds(1, "S", lethal_only=True)
        self.assertEqual(farm.credit, "M")
        farm.take_wounds(5, "S", lethal_only=True)
        self.assertEqual(farm.credit, "S")

    def test_a_building_destroyed_with_no_credit_pays_nothing(self):
        b = battle()
        b.destroy_building(b.buildings[0])
        self.assertEqual(b.regiments["S"].kills, 0)


class OrderTests(unittest.TestCase):
    def test_fire_order_at_a_building_carries_the_building_as_source(self):
        b = battle()
        b.interpreter = object()  # only its presence matters: the order becomes an event
        index = next(i for i, o in enumerate(b.shooting_objects) if o.get("building") == "building:1")
        b._post_fire_event(b.regiments["S"], "building", None, None, index)
        event = b.event_bus.unit_states["S"].event_queue[-1]
        self.assertEqual((event.code, event.source), (0x1E, "building:1"))


class SideCodeTests(unittest.TestCase):
    def test_nearest_picks_the_closest_and_ties_go_to_file_order(self):
        items = buildings.from_scenery([{"name": "Farm", "x": 1010, "y": 1000}, {"name": "Farm", "x": 990, "y": 1000},
                                        {"name": "Farm", "x": 1100, "y": 1000}])
        self.assertEqual(buildings.nearest_to_point(items, 1000, 1000).identifier, "building:0")


if __name__ == "__main__":
    unittest.main()
