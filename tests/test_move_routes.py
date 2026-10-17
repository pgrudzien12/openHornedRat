"""Player move routes: clicked stops, Append rules, patrol loops and minimap route markers (notes/move_routes.md)."""

import unittest

from whshr.engine import Battle, Regiment
from whshr.frontend.hud import ROUTE_ARROW_BASE, ROUTE_END_FRAME, ROUTE_LABEL_BASE, route_marker_frames
from whshr.rules import Side


def deployment_battle() -> Battle:
    return Battle(1000, 1000, [Regiment("R", "R", 100, 100, 0, Side.PLAYER, hud_class="inf"),
                               Regiment("E", "E", 900, 900, 0, Side.ENEMY)], deploy=True)


def field_battle() -> Battle:
    return Battle(2000, 2000, [Regiment("R", "R", 100, 100, 0, Side.PLAYER, hud_class="inf"),
                               Regiment("E", "E", 1900, 1900, 0, Side.ENEMY)], seed=1995)


class AppendStopTests(unittest.TestCase):
    """§3 and the §6.1 deployment vectors; P, Q, S lie well apart."""

    P, Q, S = (400.0, 100.0), (400.0, 400.0), (100.0, 400.0)

    def prepared(self) -> Battle:
        battle = deployment_battle()
        battle.order_move("R", *self.P)
        self.assertTrue(battle.append_waypoint("R", *self.Q))
        self.assertTrue(battle.append_waypoint("R", *self.S))
        return battle

    def test_given_move_and_two_ctrl_clicks_then_the_route_holds_three_stops(self):
        self.assertEqual(self.prepared().regiments["R"].route_stops, [self.P, self.Q, self.S])

    def test_given_a_click_just_inside_17_of_the_last_stop_then_it_is_refused(self):
        battle = self.prepared()
        self.assertFalse(battle.append_waypoint("R", self.S[0] - 16.9, self.S[1]))
        self.assertEqual(battle.regiments["R"].route_stops, [self.P, self.Q, self.S])

    def test_given_a_click_at_17_from_the_last_stop_then_it_is_added(self):
        battle = self.prepared()
        self.assertTrue(battle.append_waypoint("R", self.S[0] - 17.0, self.S[1]))
        self.assertEqual(len(battle.regiments["R"].route_stops), 4)

    def test_given_a_click_just_inside_16_of_the_first_stop_then_the_route_closes_into_a_loop(self):
        battle = self.prepared()
        self.assertFalse(battle.append_waypoint("R", self.P[0], self.P[1] - 15.9))
        regiment = battle.regiments["R"]
        self.assertEqual(regiment.route_stops, [self.P, self.Q, self.S])
        self.assertEqual(regiment.route_markers(), [(self.P, self.Q), (self.Q, self.S), (self.S, self.P)])

    def test_given_a_click_at_16_from_the_first_stop_then_it_is_an_ordinary_stop(self):
        battle = self.prepared()
        self.assertTrue(battle.append_waypoint("R", self.P[0], self.P[1] - 16.0))
        self.assertEqual(len(battle.regiments["R"].route_stops), 4)
        self.assertEqual(battle.regiments["R"].route_markers()[-1][1], None)

    def test_given_no_route_in_deployment_then_an_added_stop_is_a_plain_go_to_point(self):
        battle = deployment_battle()
        self.assertTrue(battle.append_waypoint("R", *self.P))
        self.assertEqual(battle.regiments["R"].route_stops, [self.P])

    def test_given_no_route_in_battle_then_an_added_stop_does_nothing_and_append_stays_on(self):
        battle = field_battle()
        self.assertTrue(battle.append_waypoint("R", *self.P))
        self.assertEqual(battle.regiments["R"].route_stops, [])
        self.assertFalse(battle.regiments["R"].moving)

    def test_given_the_deployment_move_button_then_the_prepared_route_is_cleared(self):
        battle = self.prepared()
        battle.prepare_deployment_move("R")
        self.assertEqual(battle.regiments["R"].route_stops, [])
        self.assertEqual(battle.regiments["R"].waypoints, [])

    def test_given_a_prepared_route_then_a_press_on_the_regiment_clears_it(self):
        battle = self.prepared()
        battle.begin_deployment_drag("R", 100, 100)
        self.assertEqual(battle.regiments["R"].route_markers(), [])


class RouteTravelTests(unittest.TestCase):
    """§3 arrival and loops, §6.2."""

    def run_until(self, battle: Battle, done, limit: int = 4000) -> None:  # type: ignore[no-untyped-def]
        for _ in range(limit):
            if done():
                return
            battle.tick(0.05)
        self.fail("condition not reached")

    def test_given_two_stops_when_the_first_is_reached_then_it_is_removed_and_the_regiment_goes_on(self):
        battle = field_battle()
        battle.order_move("R", 100, 500)
        battle.append_waypoint("R", 500, 500)
        regiment = battle.regiments["R"]
        self.run_until(battle, lambda: regiment.route_stops == [(500.0, 500.0)])
        self.assertTrue(regiment.moving)
        self.assertEqual(regiment.route_markers(), [((500.0, 500.0), None)])

    def test_given_a_patrol_loop_then_a_reached_stop_goes_to_the_back(self):
        battle = field_battle()
        a, b, c = (100.0, 500.0), (500.0, 500.0), (500.0, 100.0)
        battle.order_move("R", *a)
        battle.append_waypoint("R", *b)
        battle.append_waypoint("R", *c)
        self.assertFalse(battle.append_waypoint("R", a[0] + 5, a[1]))
        regiment = battle.regiments["R"]
        self.run_until(battle, lambda: regiment.route_stops[0] == b)
        self.assertEqual(regiment.route_stops, [b, c, a])
        self.assertEqual(regiment.route_markers()[-1], (a, b))
        self.run_until(battle, lambda: regiment.route_stops[0] == a)
        self.assertTrue(regiment.moving)
        self.assertEqual(regiment.route_stops, [a, b, c])

    def test_given_a_face_point_order_then_the_route_is_cleared(self):
        battle = field_battle()
        battle.order_move("R", 100, 500)
        battle.append_waypoint("R", 500, 500)
        battle.order_face_point("R", 300, 100)
        self.assertEqual(battle.regiments["R"].route_markers(), [])


class RouteMarkerFrameTests(unittest.TestCase):
    """§4: label 160 + n, arrow 119 + k toward the next stop, end dot on the last."""

    def test_given_an_open_route_then_each_stop_has_a_label_and_the_last_an_end_dot(self):
        battle = field_battle()
        battle.order_move("R", 100, 500)  # straight up the +Y axis from the regiment
        battle.append_waypoint("R", 500, 500)  # due +X: a quarter turn clockwise from +Y
        frames = route_marker_frames(battle.regiments["R"])
        self.assertEqual(frames, [((100.0, 500.0), ROUTE_LABEL_BASE + 1, ROUTE_ARROW_BASE + 2),
                                  ((500.0, 500.0), ROUTE_LABEL_BASE + 2, ROUTE_END_FRAME)])

    def test_given_an_enemy_or_a_routing_regiment_then_no_markers_are_drawn(self):
        battle = field_battle()
        battle.order_move("R", 100, 500)
        regiment = battle.regiments["R"]
        regiment.routing = True
        self.assertEqual(route_marker_frames(regiment), [])
        self.assertEqual(route_marker_frames(battle.regiments["E"]), [])


if __name__ == "__main__":
    unittest.main()
