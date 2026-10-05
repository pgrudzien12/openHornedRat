"""Acceptance cases from notes/movement_boundaries_route_finding.md."""

import unittest

from whshr.engine import Battle, Regiment
from whshr.navigation import boundaries_from_views, point_route
from whshr.rules import Side


def square(status, low=100, high=300):
    return {"name": "ArbitraryName", "status": ["bnd_ACTIVE", status],
            "lines": [[low, low, high, low], [high, low, high, high],
                      [high, high, low, high], [low, high, low, low]]}


def rectangle(status, left, bottom, right, top):
    return {"status": ["bnd_ACTIVE", status],
            "lines": [[left, bottom, right, bottom], [right, bottom, right, top],
                      [right, top, left, top], [left, top, left, bottom]]}


def guide(x1, y1, x2, y2):
    return {"status": ["bnd_ACTIVE", "bnd_LINE"], "lines": [[x1, y1, x2, y2]]}


class BoundaryGeometryTests(unittest.TestCase):
    def test_half_open_containment_and_inversion(self):
        solid, inverse = boundaries_from_views([square("bnd_SOLID"), square("bnd_INVSOLID")])
        for point, inside in [((100, 200), True), ((200, 300), True),
                              ((300, 200), False), ((200, 100), False),
                              ((100, 300), True)]:
            self.assertEqual(solid.contains(point), inside)
            self.assertEqual(inverse.forbidden(point), inside)

    def test_line_status_alone_does_not_block(self):
        line = {"name": "Nav1", "status": ["bnd_ACTIVE", "bnd_LINE"],
                "lines": [[200, 100, 200, 300]]}
        boundary = boundaries_from_views([line])[0]
        self.assertTrue(boundary.guide)
        self.assertFalse(boundary.solid or boundary.inverse)
        self.assertEqual(point_route((150, 200), (250, 200), [boundary]), [(250, 200)])

    def test_open_solid_line_uses_parity_without_implicit_closure(self):
        view = {"name": "Anything", "status": ["bnd_ACTIVE", "bnd_SOLID"],
                "lines": [[200, 100, 200, 300]]}
        boundary = boundaries_from_views([view])[0]
        self.assertTrue(boundary.contains((150, 200)))
        self.assertFalse(boundary.contains((250, 200)))
        self.assertFalse(boundary.contains((150, 350)))

    def test_guide_supplies_waypoints_around_inverted_area(self):
        guide = {"name": "Nav1", "status": ["bnd_ACTIVE", "bnd_LINE"],
                 "lines": [[90, 310, 310, 310]]}
        route = point_route((50, 200), (350, 200), boundaries_from_views([
            square("bnd_INVSOLID"), guide]))
        self.assertEqual(route, [(90, 310), (310, 310), (350, 200)])

    def test_equal_guide_lengths_keep_first_boundary_entry(self):
        regions = [rectangle("bnd_SOLID", 0, 0, 600, 600),
                   rectangle("bnd_INVSOLID", 250, 150, 350, 450)]
        upper, lower = guide(200, 500, 400, 500), guide(200, 100, 400, 100)
        first = point_route((100, 300), (500, 300), boundaries_from_views([*regions, upper, lower]))
        second = point_route((100, 300), (500, 300), boundaries_from_views([*regions, lower, upper]))
        self.assertEqual(first, [(200, 500), (400, 500), (500, 300)])
        self.assertEqual(second, [(200, 100), (400, 100), (500, 300)])
        farther = guide(200, 550, 400, 550)
        shorter = point_route((100, 300), (500, 300),
                              boundaries_from_views([*regions, farther, lower]))
        self.assertEqual(shorter, second)
        clear = point_route((100, 300), (500, 300),
                            boundaries_from_views([regions[0], upper, lower]))
        self.assertEqual(clear, [(500, 300)])

    def test_guide_attachments_can_be_inside_segments(self):
        regions = [rectangle("bnd_SOLID", 0, 0, 600, 600),
                   rectangle("bnd_INVSOLID", 250, 150, 350, 450),
                   guide(100, 500, 500, 500)]
        route = point_route((200, 300), (400, 300), boundaries_from_views(regions))
        self.assertEqual(route, [(200, 500), (400, 500), (400, 300)])


class BattleNavigationTests(unittest.TestCase):
    def test_forbidden_centre_is_corrected_halfway_each_tick(self):
        unit = Regiment("u", "U", 330, 200, 0, Side.PLAYER, models=1, ranks=1)
        battle = Battle(500, 500, [unit], boundaries=[square("bnd_SOLID")])
        positions = []
        for _ in range(5):
            battle.tick()
            positions.append(unit.x)
        self.assertEqual(positions, [315, 308, 304, 302, 301])

    def test_solid_object_pushes_overlapping_formation(self):
        unit = Regiment("u", "U", 200, 200, 0, Side.PLAYER, models=1, ranks=1)
        obj = {"x": 200, "y": 200, "radius": 30,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj])
        battle.tick()
        self.assertGreaterEqual(abs(unit.x - 200), 30 + unit.bounding_radius())

    def test_point_order_uses_guide_and_reaches_destination(self):
        unit = Regiment("u", "U", 50, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=5)
        guide = {"name": "Nav1", "status": ["bnd_ACTIVE", "bnd_LINE"],
                 "lines": [[90, 310, 310, 310]]}
        battle = Battle(500, 500, [unit], boundaries=[square("bnd_INVSOLID"), guide])
        battle.order_move("u", 350, 200)
        self.assertEqual((unit.target_x, unit.target_y), (90, 310))
        self.assertEqual(unit.waypoints, [(310, 310), (350, 200)])
        for _ in range(300):
            battle.tick()
            if not unit.moving and not unit.waypoints:
                break
        self.assertAlmostEqual(unit.x, 350)
        self.assertAlmostEqual(unit.y, 200)

    def test_solid_object_causes_local_detour_without_becoming_a_waypoint(self):
        unit = Regiment("u", "U", 100, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=5)
        obj = {"x": 200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj])
        battle.order_move("u", 350, 200)
        battle.tick()
        self.assertIsNotNone(unit.avoid_target)
        self.assertGreater(unit.avoid_target[1], 200)  # equal trial scores retain second side
        for _ in range(100):
            battle.tick()
        self.assertEqual((unit.x, unit.y), (350, 200))

    def test_obstruction_scan_uses_authored_object_order(self):
        obstacles = [("far", (300, 100), 20), ("near", (170, 100), 20)]
        found = Battle._first_route_obstacle((100, 100), (400, 100), obstacles, 6)
        self.assertEqual(found[0], "far")

    def test_both_detours_outside_permitted_area_stop_the_move(self):
        unit = Regiment("u", "U", 80, 100, 128, Side.PLAYER, models=1, ranks=1)
        obj = {"x": 250, "y": 100, "radius": 110,
               "status": ["os_active", "os_solid"]}
        narrow = Battle(500, 200, [unit], objects=[obj],
                        boundaries=[rectangle("bnd_SOLID", 0, 0, 500, 200)])
        narrow.order_move("u", 420, 100)
        narrow.tick()
        self.assertFalse(unit.moving)

        unit = Regiment("u", "U", 80, 100, 128, Side.PLAYER, models=1, ranks=1)
        wider = Battle(500, 400, [unit], objects=[obj],
                       boundaries=[rectangle("bnd_SOLID", 0, 0, 500, 400)])
        wider.order_move("u", 420, 100)
        wider.tick()
        self.assertTrue(unit.moving)
        self.assertIsNotNone(unit.avoid_target)
        self.assertGreater(unit.avoid_target[1], 100)

    def test_trial_cost_above_5999_alone_does_not_reject_move(self):
        unit = Regiment("u", "U", 100, 200, 128, Side.PLAYER, models=1, ranks=1)
        obj = {"x": 6200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(10000, 400, [unit], objects=[obj],
                        boundaries=[rectangle("bnd_SOLID", 0, 0, 10000, 400)])
        battle.order_move("u", 9000, 200)
        battle.tick()
        self.assertTrue(unit.moving)
        self.assertIsNotNone(unit.avoid_target)

    def test_routing_departure_and_removal_use_battle_edge(self):
        unit = Regiment("u", "U", 290, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=20)
        edge = square("bnd_BATTLEEDGE")
        battle = Battle(500, 500, [unit], boundaries=[edge])
        unit.routing = True
        unit.flee_x, unit.flee_y = 1000, 200
        for _ in range(200):
            battle.tick()
            if unit.fled:
                break
        self.assertTrue(unit.flight_departed)
        self.assertTrue(unit.flight_complete)
        self.assertTrue(unit.fled)


if __name__ == "__main__":
    unittest.main()
