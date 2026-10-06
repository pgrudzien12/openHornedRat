"""Scenarios for whshr.steering (notes/obstacle_steering.md sections 3-5 and 8)."""

from __future__ import annotations

import math
import unittest

from whshr.steering import Footprint, Point, bearing, plan, scan, steer


def _all(_fp: Footprint) -> bool:
    return True


def _anywhere(_p: Point) -> bool:
    return True


def _circle(x: float, y: float, r: float, key: str = "object:0", troops: bool = False) -> Footprint:
    return Footprint(key, x, y, r, troops)


class ScanTests(unittest.TestCase):
    def test_blocking_circle_ahead(self) -> None:
        hit = scan((0, 0), (0, 600), [_circle(10, 200, 50)], 30, _all)
        assert hit is not None
        self.assertAlmostEqual(hit.distance, 200.25, places=1)
        self.assertEqual(hit.combined_radius, 80)
        self.assertEqual(hit.half_width, 33)
        self.assertEqual(hit.bearing, 4)

    def test_bearing_convention(self) -> None:
        self.assertEqual(bearing((0, 0), (0, 5)), 0)
        self.assertEqual(bearing((0, 0), (5, 0)), 128)
        self.assertEqual(bearing((0, 0), (0, -5)), 256)
        self.assertEqual(bearing((0, 0), (-5, 0)), 384)

    def test_corridor_rejects_obstacle_beyond_waypoint(self) -> None:
        # circle contains no waypoint, reach 200 <= d' - R = 220.2 -> ignored
        self.assertIsNone(scan((0, 0), (0, 250), [_circle(10, 300, 50)], 30, _all))

    def test_look_ahead_boundary(self) -> None:
        self.assertIsNone(scan((0, 0), (0, 600), [_circle(0, 260, 50)], 30, _all))
        self.assertIsNone(scan((0, 0), (0, 600), [_circle(0, 256, 50)], 30, _all))
        self.assertIsNotNone(scan((0, 0), (0, 600), [_circle(0, 255, 50)], 30, _all))

    def test_cone_is_strict(self) -> None:
        # off to the side, well outside the cone
        self.assertIsNone(scan((0, 0), (0, 600), [_circle(200, 100, 20)], 10, _all))

    def test_first_in_order_beats_nearer(self) -> None:
        far = _circle(0, 200, 30, "far")
        near = _circle(0, 100, 30, "near")
        hit = scan((0, 0), (0, 600), [far, near], 10, _all)
        assert hit is not None
        self.assertEqual(hit.footprint.key, "far")

    def test_destination_skip_and_troops_exception(self) -> None:
        wp = (0.0, 200.0)
        self.assertIsNone(scan((0, 0), wp, [_circle(0, 205, 30)], 10, _all))
        hit = scan((0, 0), wp, [_circle(0, 205, 30, "t", troops=True)], 10, _all)
        self.assertIsNotNone(hit)

    def test_relationship_filter_applied_last(self) -> None:
        a = _circle(0, 100, 30, "a")
        b = _circle(0, 150, 30, "b")
        hit = scan((0, 0), (0, 600), [a, b], 10, lambda fp: fp.key == "b")
        assert hit is not None
        self.assertEqual(hit.footprint.key, "b")


class SteerTests(unittest.TestCase):
    def test_natural_side_and_geometry(self) -> None:
        st = steer((0, 0), (0, 600), [_circle(10, 200, 50)], 30, _all)
        assert st is not None
        self.assertEqual(st.side, -1)
        self.assertEqual(st.heading, 475)
        self.assertEqual(st.distance, 107)
        self.assertFalse(st.gave_up)
        # D/2 = 107.8 along heading 475 (SIN/COS table rule)
        self.assertAlmostEqual(math.hypot(*st.point), 107.8, delta=2.0)

    def test_nothing_blocks(self) -> None:
        self.assertIsNone(steer((0, 0), (0, 600), [], 30, _all))

    def test_remembered_side_reused(self) -> None:
        st = steer((0, 0), (0, 600), [_circle(10, 200, 50)], 30, _all, remembered_side=1)
        assert st is not None
        self.assertEqual(st.side, 1)
        self.assertEqual(st.heading, (4 + 41) % 512)

    def test_rescan_steers_around_second_obstacle(self) -> None:
        first = _circle(10, 200, 50, "a")
        second = _circle(-66, 135, 40, "b")
        st = steer((0, 0), (0, 600), [first, second], 30, _all)
        assert st is not None
        self.assertEqual(st.side, -1)
        self.assertNotEqual(st.heading, 475)

    def test_full_circle_gives_up(self) -> None:
        ring = [
            _circle(100 * math.sin(2 * math.pi * i / 16), 100 * math.cos(2 * math.pi * i / 16), 40, f"r{i}")
            for i in range(16)
        ]
        st = steer((0, 0), (0, 1000), ring, 10, _all)
        assert st is not None
        self.assertTrue(st.gave_up)
        self.assertEqual(st.heading, 0)


class PlanTests(unittest.TestCase):
    def test_nothing_blocking(self) -> None:
        p = plan((0, 0), 0, (0, 600), [], 30, _all, _anywhere)
        self.assertTrue(p.ok)
        self.assertEqual(p.side, 0)
        self.assertEqual(p.scores, (0, 0))

    def test_outside_edge_start_with_inside_steer_points(self) -> None:
        # start is outside the permitted area; only steer points are tested
        circle = _circle(0, 200, 50)
        p = plan((0, 0), 0, (0, 600), [circle], 30, _all, lambda pt: pt[0] > -500)
        self.assertTrue(p.ok)
        self.assertLess(max(p.scores), 12000)

    def test_both_steer_points_forbidden(self) -> None:
        p = plan((0, 0), 0, (0, 600), [_circle(10, 200, 50)], 30, _all, lambda _pt: False)
        self.assertFalse(p.ok)
        self.assertGreaterEqual(p.scores[0], 12000)
        self.assertGreaterEqual(p.scores[1], 12000)

    def test_forbidden_steer_point_scores_12000(self) -> None:
        # natural side is -1 (x < 0); forbid negative x
        p = plan((0, 0), 0, (0, 600), [_circle(10, 200, 50)], 30, _all, lambda pt: pt[0] >= 0)
        self.assertTrue(p.ok)
        self.assertGreaterEqual(p.scores[0], 12000)
        self.assertLess(p.scores[1], 12000)
        self.assertEqual(p.side, 1)

    def test_tie_picks_opposite_side(self) -> None:
        # every steer point forbidden: both trials end at 12000 + the same waypoint distance
        p = plan((0, 0), 0, (0, 600), [_circle(0, 200, 50)], 30, _all, lambda _pt: False)
        self.assertEqual(p.scores[0], p.scores[1])
        self.assertEqual(p.side, -1)  # natural side is +1, an exact tie goes to the opposite one

    def test_connector_crossing_not_penalised(self) -> None:
        # a permitted() that only forbids the strip x in (-5, 5) between start and
        # steer point; steer points themselves are fine, so nothing is penalised
        def permitted(pt: Point) -> bool:
            return not (-5 < pt[0] < 5)

        p = plan((0, 0), 0, (0, 600), [_circle(10, 200, 50)], 30, _all, permitted)
        self.assertLess(max(p.scores), 12000)

    def test_bf003_wolfriders(self) -> None:
        start = (1113.0, 1420.0)
        wp = (719.0, 970.0)
        circles = [_circle(1074, 1243, 59, "object:b"), _circle(967, 1221, 67, "object:a")]
        # section 3 numbers
        self.assertEqual(bearing(start, wp), 314)
        hit = scan(start, wp, circles, 30, _all)
        assert hit is not None
        self.assertEqual(hit.footprint.key, "object:a")
        self.assertEqual(hit.bearing, 307)
        self.assertEqual(hit.half_width, 32)
        self.assertAlmostEqual(hit.distance, 246.8, places=1)
        st = steer(start, wp, circles, 30, _all, remembered_side=1)
        assert st is not None
        self.assertEqual(st.heading, 347)
        self.assertAlmostEqual(st.point[0], 994, delta=1.5)
        self.assertAlmostEqual(st.point[1], 1362, delta=1.5)
        # the opposite side's first response (the note's 267 / (1095, 1289)); with the nearby
        # second circle also in the list the rescan would deflect it further
        st2 = steer(start, wp, circles[1:], 30, _all, remembered_side=-1)
        assert st2 is not None
        self.assertEqual(st2.heading, 267)
        self.assertAlmostEqual(st2.point[0], 1095, delta=1.5)
        self.assertAlmostEqual(st2.point[1], 1289, delta=1.5)

        def inside(pt: Point) -> bool:
            return pt[0] <= 1080

        p = plan(start, 373, wp, circles, 30, _all, inside)
        self.assertTrue(p.ok)
        self.assertEqual(p.side, 1)
        self.assertLess(p.scores[0], 12000)
        self.assertGreaterEqual(p.scores[1], 12000)
        # both sides east of the edge -> give up
        self.assertFalse(plan(start, 373, wp, circles, 30, _all, lambda _p: False).ok)


if __name__ == "__main__":
    unittest.main()


class CorrectionTests(unittest.TestCase):
    """notes/obstacle_steering.md section 8 rows added with the trial-rescan and turn-cost answers."""

    def test_bf003_trial_two_rescan_is_replaced_by_the_second_circle(self):
        # notes/bf003_wolfriders_route.md section 3 step 5: the opposite side meets (1074, 1243) r 59 on the rescan.
        footprints = [_circle(967, 1221, 67, "object:a"), _circle(1074, 1243, 59, "object:b")]
        st = steer((1113, 1420), (719, 970), footprints, 30, _all, remembered_side=-1, facing=373)
        assert st is not None
        self.assertEqual(st.heading, 222)
        self.assertEqual(st.distance, 100)  # trunc(sqrt(181.2^2 + 89^2) / 2) = trunc(100.9); the report rounds to ~101
        self.assertAlmostEqual(st.point[0], 1153, delta=2)
        self.assertAlmostEqual(st.point[1], 1328, delta=2)

    def test_bf003_plan_still_passes_west(self):
        footprints = [_circle(967, 1221, 67, "object:a"), _circle(1074, 1243, 59, "object:b")]
        result = plan((1113, 1420), 373, (719, 970), footprints, 30, _all, lambda p: p[0] <= 1080)
        self.assertEqual((result.ok, result.side), (True, 1))
        self.assertGreaterEqual(result.scores[1], 12000)

    def test_trial_turn_cost_is_wrapped(self):
        # facing 500, steer heading 10: the turn counts 22, not 490 (cost 4 x turn + steer distance).
        start, waypoint = (0.0, 0.0), (0.0, 400.0)
        circle = _circle(0, 100, 20)
        st = steer(start, waypoint, [circle], 10, _all, remembered_side=1, facing=500)
        assert st is not None
        result = plan(start, 500, waypoint, [circle], 10, _all, _anywhere)
        wrapped = min((st.heading - 500) % 512, 512 - (st.heading - 500) % 512)
        self.assertLess(wrapped, 256)
        self.assertLess(min(result.scores), 4 * 256 + 400 + 200)
