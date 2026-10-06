"""Flight round solid areas (notes/flight_solid_obstacles.md): a routing regiment re-routes each flee period from its
current facing and is never pushed by boundaries; a pursuer aims at the fugitive's leading edge and a solid line
never ends a pursuit. Vectors follow section 7 with a river (solid area) west of x = 216."""

import unittest

from whshr.engine import Battle, Regiment
from whshr.rules import Side

# A solid area's polygon is the allowed ground; like BF003's RiverEdge, the river lies outside it (west of x = 216).
RIVER = {"status": ["bnd_ACTIVE", "bnd_AREA", "bnd_SOLID"],
         "lines": [[216, -200, 1640, -200], [1640, -200, 1640, 2000], [1640, 2000, 216, 2000], [216, 2000, 216, -200]]}
EDGE = {"status": ["bnd_ACTIVE", "bnd_AREA", "bnd_BATTLEEDGE"],
        "lines": [[16, 16, 1424, 16], [1424, 16, 1424, 1664], [1424, 1664, 16, 1664], [16, 1664, 16, 16]]}


def fugitive(x, y, facing):
    unit = Regiment("w", "Wolfriders", x, y, facing, Side.ENEMY, models=4, ranks=2, routing=True)
    battle = Battle(1440, 1680, [unit], seed=1995, boundaries=[RIVER, EDGE])
    battle.phase = "battle"
    return battle, unit


class FleeRerouteTests(unittest.TestCase):
    def test_head_on_into_the_river_swings_clockwise_along_the_bank(self):
        battle, unit = fugitive(260, 1000, 384)
        battle._reroute_flight(unit)
        self.assertEqual(unit.direction, 509)
        self.assertGreater(unit.flee_y, 1000)  # runs along the bank towards +Y
        self.assertGreater(unit.flee_x, 216)

    def test_a_clear_way_keeps_the_heading(self):
        battle, unit = fugitive(240, 1250, 509)
        battle._reroute_flight(unit)
        self.assertEqual(unit.direction, 509)

    def test_routing_units_are_never_pushed_out_of_a_solid_area(self):
        battle, unit = fugitive(213, 1050, 384)
        battle._correct_boundaries(unit)
        self.assertEqual((unit.x, unit.y), (213, 1050))

    def test_the_fugitive_escapes_along_the_bank_instead_of_being_pinned(self):
        battle, unit = fugitive(260, 1000, 384)
        unit.flee_x, unit.flee_y = -1000.0, 1000.0  # the old fixed bearing straight into the river
        for _ in range(200):
            battle.tick()
        self.assertGreater(unit.y, 1150)

    def test_a_flee_step_ahead_of_an_enemy_unit_steers_round_it(self):
        battle, unit = fugitive(600, 1000, 0)
        blocker = Regiment("e", "Enemy", 600, 1100, 0, Side.PLAYER, models=10, ranks=2)
        battle = Battle(1440, 1680, [unit, blocker], seed=1995, boundaries=[RIVER, EDGE])
        battle._reroute_flight(unit)
        self.assertNotEqual(unit.direction, 0)


class PursuerTests(unittest.TestCase):
    def test_pursuer_is_pushed_out_of_the_river_and_keeps_pursuing(self):
        pursuer = Regiment("c", "Cavalry", 205, 1100, 0, Side.PLAYER, models=8, ranks=2)
        target = Regiment("w", "Wolfriders", 240, 1300, 0, Side.ENEMY, models=4, ranks=2, routing=True)
        battle = Battle(1440, 1680, [pursuer, target], seed=1995, boundaries=[RIVER, EDGE])
        pursuer.attack_target, pursuer.pursuing = "w", True
        centre_before = battle.formation_centre(pursuer)[0]
        battle._correct_boundaries(pursuer)
        self.assertGreater(battle.formation_centre(pursuer)[0], centre_before)
        battle._update_pursuits()
        self.assertEqual((pursuer.pursuing, pursuer.attack_target), (True, "w"))

    def test_the_chase_point_is_the_fugitives_leading_edge(self):
        pursuer = Regiment("c", "Cavalry", 600, 800, 0, Side.PLAYER, models=8, ranks=2)
        target = Regiment("w", "Wolfriders", 600, 1000, 0, Side.ENEMY, models=4, ranks=2, routing=True)
        battle = Battle(1440, 1680, [pursuer, target], seed=1995, boundaries=[EDGE])
        pursuer.attack_target, pursuer.pursuing = "w", True
        battle._update_pursuits()
        centre = battle.formation_centre(target)
        self.assertAlmostEqual(pursuer.pursuit_point[0], centre[0], delta=0.01)
        self.assertAlmostEqual(pursuer.pursuit_point[1], centre[1] + int(target.bounding_radius()), delta=0.01)


if __name__ == "__main__":
    unittest.main()
