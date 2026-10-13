"""Visibility across a SightEdge area (game_rules.md "Routes, collisions and visibility",
notes/bf014_dragon_mission_audit.md 4).

Given a rectangular SightEdge area whose bottom edge is y = 1832 from x 88 to 1272,
when a unit looks across that edge, then the single line between the two positions decides,
started from inside the area for a looker that stands outside it.
"""

import unittest

from whshr import visibility

AREA = [{"status": ["bnd_ACTIVE", "bnd_AREA", "bnd_SIGHT"], "lines": [
    (88, 8, 1272, 8), (1272, 8, 1272, 1832), (1272, 1832, 88, 1832), (88, 1832, 88, 8)]}]
CONE = 71


class LookerOutsideTheAreaTests(unittest.TestCase):
    def test_looker_just_outside_looks_from_inside_the_edge(self):
        lines = visibility.sight_lines(AREA)
        start = visibility.sight_start((429, 1836), lines)
        self.assertAlmostEqual(start[0], 429)
        self.assertAlmostEqual(start[1], 1827.6)

    def test_looker_just_outside_sees_a_unit_inside(self):
        self.assertTrue(visibility.visible((429, 1836), 257, (845, 1177), 20, CONE, AREA, []))

    def test_looker_beyond_a_corner_starts_from_the_corner_moved_inward(self):
        start = visibility.sight_start((60, 1900), visibility.sight_lines(AREA))
        self.assertAlmostEqual(start[0], 118.8)
        self.assertAlmostEqual(start[1], 1757.2)

    def test_looker_inside_keeps_its_own_position(self):
        self.assertEqual(visibility.sight_start((845, 1177), visibility.sight_lines(AREA)), (845, 1177))


class TargetOutsideTheAreaTests(unittest.TestCase):
    def test_unit_inside_cannot_see_a_target_outside(self):
        self.assertFalse(visibility.visible((845, 1177), 466, (429, 1836), 20, CONE, AREA, []))

    def test_target_footprint_does_not_reach_across_the_edge(self):
        """The side rays sample scenery only; a wide target just past the edge stays unseen."""
        self.assertFalse(visibility.visible((600, 1700), 0, (600, 1840), 60, CONE, AREA, []))

    def test_no_sight_edge_means_visible(self):
        self.assertTrue(visibility.visible((845, 1177), 466, (429, 1836), 20, CONE, [], []))


if __name__ == "__main__":
    unittest.main()
