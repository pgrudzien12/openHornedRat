"""Which map objects stop projectiles, block sight and push units (notes/map_objects_and_projectiles.md)."""

import unittest

from whshr import map_objects, visibility
from whshr.engine import Battle, Regiment
from whshr.rules import Side

SOLID = ["os_active", "os_solid"]


def collision(z=None, radius=52, status=SOLID, x=0, y=0):
    obj = {"x": x, "y": y, "radius": radius, "status": list(status)}
    if z is not None:
        obj["z"] = z
    return obj


class ProjectileTests(unittest.TestCase):
    """Section 3 vectors: a bolt at (20, 0) and the given height above the ground."""

    def test_a_collision_object_stops_a_bolt_at_or_below_its_z(self):
        obj = collision(z=39)
        self.assertEqual([map_objects.stops_projectile(obj, 20, 0, h) for h in (0, 3, 16, 39, 40)],
                         [True, True, True, True, False])

    def test_a_bolt_exactly_on_the_circle_flies_on(self):
        self.assertFalse(map_objects.stops_projectile(collision(z=39), 52, 0, 3))

    def test_a_flat_object_stops_only_a_ground_level_bolt(self):
        obj = collision(z=0, radius=20, status=["os_active"])
        self.assertEqual([map_objects.stops_projectile(obj, 5, 0, h) for h in (0, 3, 16)], [True, False, False])

    def test_a_camera_only_object_never_stops_a_bolt(self):
        obj = collision(z=150, status=["os_active", "os_camcollide"])
        self.assertFalse(map_objects.stops_projectile(obj, 5, 0, 0))

    def test_an_object_without_z_is_80_high(self):
        self.assertEqual([map_objects.stops_projectile(collision(), 5, 0, h) for h in (3, 16, 80, 81)],
                         [True, True, True, False])

    def test_a_road_piece_is_no_obstacle_but_a_building_still_is(self):
        road = {"name": "PlnStrRoad", "x": 100, "y": 0}
        house = {"name": "WoodShack", "x": 400, "y": 0}
        battle = Battle(1000, 1000, [Regiment("A", "A", 0, 0, 0, Side.PLAYER, models=4)], scenery=[road, house])
        self.assertEqual([obj.get("building") for obj in battle.shooting_objects], ["building:1"])
        self.assertTrue(all(not map_objects.stops_projectile(obj, 100, 0, h)
                            for obj in battle.shooting_objects for h in (0, 3, 16)))
        self.assertTrue(any(map_objects.stops_projectile(obj, 400, 0, 3) for obj in battle.shooting_objects))


class SightAndMovementTests(unittest.TestCase):
    def test_sight_is_blocked_by_an_active_object_even_if_not_solid_but_not_by_a_flat_or_camera_object(self):
        def clear(obj):
            return visibility.clear_ray((-100, 0), (100, 0), [], [obj])

        self.assertFalse(clear(collision(z=39, status=["os_active"])))
        self.assertTrue(clear(collision(z=0)))
        self.assertTrue(clear(collision(z=39, status=["os_active", "os_camcollide"])))

    def test_only_a_solid_object_pushes_units_but_any_existing_one_steers_routes(self):
        passive = collision(z=39, status=["os_active"])
        self.assertEqual((map_objects.pushes_units(passive), map_objects.steers_routes(passive)), (False, True))
        self.assertEqual((map_objects.pushes_units(collision()), map_objects.steers_routes(collision())), (True, True))


if __name__ == "__main__":
    unittest.main()
