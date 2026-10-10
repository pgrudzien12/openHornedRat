"""Acceptance cases from notes/movement_boundaries_route_finding.md."""

import math
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from whshr.battle_log import BattleLogger
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
    def test_blocked_route_records_one_warning_with_obstacle_and_boundary_context(self):
        # Both trial steer points lie outside the narrow solid corridor (notes/obstacle_steering.md section 5);
        # the unit itself also starts outside it.
        unit = Regiment("u", "U", 80, -1, 128, Side.PLAYER, models=1, ranks=1)
        obj = {"x": 250, "y": 100, "radius": 110, "status": ["os_active", "os_solid"]}
        edge = rectangle("bnd_SOLID", 0, 0, 500, 200)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "battle.jsonl"
            logger = BattleLogger(path)
            battle = Battle(500, 200, [unit], objects=[obj], boundaries=[edge], script_logger=logger)
            battle.order_move("u", 420, 100)
            battle.tick()
            self.assertFalse(unit.moving)
            battle.order_move("u", 420, 100)
            battle.tick()
            logger.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]

        self.assertEqual(len(records), 1)
        warning = records[0]
        self.assertEqual((warning["type"], warning["code"]), ("warning", "route_blocked"))
        self.assertEqual((warning["unit_id"], warning["obstacle"]), ("u", "object:0"))
        self.assertEqual(warning["target"], [420, 100])
        self.assertEqual(warning["tick"], 0)
        self.assertTrue(warning["outside_boundary"])
        self.assertTrue(all(score >= 12000 for score in warning["detour_scores"]))

    def test_forbidden_centre_is_corrected_halfway_each_tick(self):
        unit = Regiment("u", "U", 330, 200, 0, Side.PLAYER, models=1, ranks=1)
        battle = Battle(500, 500, [unit], boundaries=[square("bnd_SOLID")])
        unit.collision_recheck = True  # it has just stepped in: a unit standing still since load has no pass
        positions = []
        for _ in range(5):
            battle.tick()
            positions.append(unit.x)
        self.assertEqual(positions, [315, 308, 304, 302, 301])

    def test_a_unit_standing_still_since_load_is_not_corrected(self):
        # notes/hidden_reserves_off_field.md 0, 3: no collision re-check state, so no pass and no correction.
        unit = Regiment("u", "U", 330, 200, 0, Side.ENEMY, models=1, ranks=1)
        battle = Battle(500, 500, [unit], boundaries=[square("bnd_SOLID")])
        for _ in range(5):
            battle.tick()
        self.assertEqual((unit.x, unit.y), (330, 200))

    def test_hidden_enemy_or_allied_units_wait_in_a_solid_pocket_uncorrected(self):
        # notes/hidden_reserves_off_field.md 1 and 6: the skip covers hidden enemy/allied units only.
        for side, hidden, corrected in ((Side.ENEMY, True, False), (Side.NEUTRAL, True, False),
                                        (Side.PLAYER, True, True), (Side.ENEMY, False, True)):
            with self.subTest(side=side, hidden=hidden):
                unit = Regiment("u", "U", 330, 200, 0, side, models=1, ranks=1, hidden=hidden)
                battle = Battle(500, 500, [unit], boundaries=[square("bnd_SOLID")])
                unit.collision_recheck = True  # e.g. it has just turned
                battle.tick()
                self.assertEqual(unit.x != 330, corrected)

    def test_a_revealed_reserve_is_corrected_again(self):
        unit = Regiment("u", "U", 330, 200, 0, Side.ENEMY, models=1, ranks=1, hidden=True)
        battle = Battle(500, 500, [unit], boundaries=[square("bnd_SOLID")])
        unit.collision_recheck = True
        battle.tick()
        self.assertEqual(unit.x, 330)
        unit.hidden = False  # spotted
        unit.collision_recheck = True
        battle.tick()
        self.assertEqual(unit.x, 315)

    def test_solid_object_pushes_overlapping_formation(self):
        unit = Regiment("u", "U", 200, 200, 0, Side.PLAYER, models=1, ranks=1)
        obj = {"x": 200, "y": 200, "radius": 30,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj])
        unit.collision_recheck = True  # it has just stepped
        battle.tick()
        self.assertAlmostEqual(abs(unit.x - 200), (30 + unit.bounding_radius()) / 2)

    def test_no_guide_keeps_requested_destination_behind_boundary(self):
        unit = Regiment("u", "U", 200, 200, 128, Side.PLAYER, models=1, ranks=1)
        battle = Battle(500, 500, [unit], boundaries=[square("bnd_SOLID")])
        battle.order_move("u", 400, 200)
        self.assertEqual((unit.target_x, unit.target_y), (400, 200))
        for _ in range(120):
            battle.tick()
        self.assertEqual((unit.target_x, unit.target_y), (400, 200))
        self.assertLess(unit.x, 310)

    def test_open_solid_line_does_not_replace_no_guide_target(self):
        unit = Regiment("u", "U", 150, 200, 128, Side.PLAYER, models=1, ranks=1)
        wall = {"status": ["bnd_ACTIVE", "bnd_SOLID"],
                "lines": [[200, 100, 200, 300]]}
        battle = Battle(500, 500, [unit], boundaries=[wall])
        battle.order_move("u", 250, 200)
        self.assertEqual((unit.target_x, unit.target_y), (250, 200))

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
        # notes/movement_formation.md 1.4: the last leg halts within 32 units of its point.
        self.assertFalse(unit.moving)
        self.assertLessEqual(math.dist((unit.x, unit.y), (350, 200)), 32)
        self.assertGreater(unit.y, 200)  # came down the guide's far leg, not straight across

    def test_solid_object_causes_local_detour_without_becoming_a_waypoint(self):
        unit = Regiment("u", "U", 100, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=5)
        obj = {"x": 200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj])
        battle.order_move("u", 350, 200)
        battle.tick()
        self.assertIsNotNone(unit.avoid_target)  # steering round the circle (notes/obstacle_steering.md section 4)
        for _ in range(100):
            battle.tick()
        self.assertFalse(unit.moving)
        self.assertLessEqual(math.dist((unit.x, unit.y), (350, 200)), 32)  # movement_formation.md 1.4

    def test_moving_object_recalculates_detour_and_clear_path_resumes_direct_move(self):
        unit = Regiment("u", "U", 100, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=0)
        obj = {"x": 200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj])
        battle.order_move("u", 350, 200)
        battle.tick()
        first = unit.avoid_target
        self.assertIsNotNone(first)
        obj["x"] = 210
        battle.tick()
        self.assertNotEqual(unit.avoid_target, first)
        obj["y"] = 350
        battle.tick()
        self.assertIsNone(unit.avoid_target)
        self.assertEqual((unit.target_x, unit.target_y), (350, 200))

    def test_moving_obstacle_keeps_the_remembered_steering_side(self):
        # notes/obstacle_steering.md sections 1 and 6: the plan runs at the order; live steering keeps its side.
        unit = Regiment("u", "U", 100, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=0)
        obj = {"x": 200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj])
        battle.order_move("u", 350, 200)
        battle.tick()
        side = unit.route_side
        below = unit.avoid_target[1] < 200
        obj["y"] = 195 if below else 205
        battle.tick()
        self.assertEqual((unit.route_side, unit.avoid_target[1] < 200), (side, below))

    def test_stationary_bf003_infantry_accepts_move_past_near_peasants(self):
        # The logged infantry centre is almost tangent to the first Peasant
        # footprint. Both regiments have zero anchor travel speed at order time.
        infantry = Regiment("infantry", "Infantry", 657.8680830763195, 615.935870876748,
                            379.9609375, Side.PLAYER, models=16, ranks=4, speed_per_tick=5)
        peasants = Regiment("peasants", "Peasants", 645, 670, 485, Side.NEUTRAL,
                            models=5, ranks=2)
        battle = Battle(1440, 1680, [infantry, peasants],
                        boundaries=[rectangle("bnd_BATTLEEDGE", 0, 0, 1440, 1680)])
        destination = (535.0819672131148, 968.9302325581397)
        self.assertEqual(infantry.bounding_radius(), 33)
        self.assertEqual(peasants.bounding_radius(), 21)
        self.assertEqual(battle._steering_target(infantry, destination, ("move", *destination)), destination)

        battle.order_move("infantry", *destination)
        for _ in range(120):
            battle.tick()
            if not infantry.moving:
                break
        self.assertFalse(infantry.moving)
        self.assertLessEqual(math.dist((infantry.x, infantry.y), destination), 32)  # movement_formation.md 1.4

    def test_same_side_route_filter_uses_speed_heading_and_octagonal_nearness(self):
        mover = Regiment("m", "Mover", 100, 200, 128, Side.PLAYER, models=1, ranks=1)
        ally = Regiment("a", "Ally", 200, 200, 128, Side.NEUTRAL, models=1, ranks=1)
        battle = Battle(500, 500, [mover, ally])
        goal = (350, 200)
        key = ("move", *goal)
        self.assertEqual(battle._steering_target(mover, goal, key), goal)
        mover.target_x, mover.target_y = goal  # moving: its effective speed beats the stationary ally
        mover.route_planned_for = (key, goal)  # live steering, not the plan at the order
        self.assertIsNotNone(battle._steering_target(mover, goal, key))
        self.assertIsNotNone(mover.avoid_target)

        mover.target_x = mover.target_y = None
        mover.route_planned_for = None
        ally.direction = 0  # differing headings: nearby slower units are passed over
        ally.x = 115
        self.assertEqual(battle._steering_target(mover, goal, key), goal)
        ally.x = 300  # beyond 16 x s_rlmv (notes/obstacle_steering.md section 6): a slower unit obstructs
        mover.route_planned_for = None
        battle._steering_target(mover, goal, key)
        self.assertIsNotNone(mover.avoid_target)

    def test_regiment_collision_uses_stored_integer_radii(self):
        mover = Regiment("m", "Mover", 100, 100, 0, Side.PLAYER, models=1, ranks=1,
                         target_x=200, target_y=100)
        ally = Regiment("a", "Ally", 116, 100, 0, Side.NEUTRAL, models=1, ranks=1)
        battle = Battle(500, 500, [mover, ally])
        mover.collision_recheck = True  # it has just stepped
        self.assertEqual(mover.bounding_radius() + ally.bounding_radius(), 16)
        # Broad phase only: the narrow (box) phase is assumed to pass, so the circle test alone decides.
        boxes = mock.patch("whshr.formation.boxes_overlap", return_value=True)
        boxes.start()
        self.addCleanup(boxes.stop)
        battle._resolve_collisions()
        self.assertEqual(mover.x, 100)
        ally.x = 115
        mover.collision_recheck = True
        battle._resolve_collisions()
        self.assertLess(mover.x, 100)

    def test_routing_unit_steers_around_solid_scenery(self):
        unit = Regiment("u", "U", 100, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=5, routing=True, flee_x=1000, flee_y=200)
        obj = {"x": 200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [unit], objects=[obj],
                        boundaries=[rectangle("bnd_BATTLEEDGE", 0, 0, 500, 500)])
        battle.tick()
        self.assertIsNotNone(unit.avoid_target)
        self.assertNotEqual(unit.y, 200)
        for _ in range(100):
            battle.tick()
        self.assertGreater(unit.x, 300)

    def test_frontal_scenery_contact_ends_charge_and_pushes_half_overlap(self):
        charger = Regiment("c", "C", 190, 200, 128, Side.PLAYER, models=1, ranks=1,
                           speed_per_tick=0, attack_target="e", charge_started_target="e")
        enemy = Regiment("e", "E", 400, 200, 0, Side.ENEMY, models=1, ranks=1)
        obj = {"x": 200, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [charger, enemy], objects=[obj])
        charger.collision_recheck = True  # it has just stepped
        battle.tick()
        self.assertIsNone(charger.attack_target)
        self.assertTrue(any(event.kind == "charge_end" for event in battle.events))
        target_events = battle.event_bus.unit_states["e"].event_queue
        self.assertEqual([(event.code, event.source) for event in target_events], [(0x09, "c")])

    def test_non_battleedge_boundary_ends_charge(self):
        charger = Regiment("c", "C", 305, 200, 128, Side.PLAYER, models=1, ranks=1,
                           speed_per_tick=0, attack_target="e", charge_started_target="e")
        enemy = Regiment("e", "E", 450, 200, 0, Side.ENEMY, models=1, ranks=1)
        battle = Battle(500, 500, [charger, enemy], boundaries=[square("bnd_SOLID")])
        charger.collision_recheck = True  # it has just stepped
        battle.tick()
        self.assertIsNone(charger.attack_target)
        self.assertTrue(any(event.kind == "charge_end" for event in battle.events))
        target_events = battle.event_bus.unit_states["e"].event_queue
        self.assertEqual([(event.code, event.source) for event in target_events], [(0x09, "c")])

    def test_obstruction_during_approach_does_not_end_charge_order(self):
        for boundary, objects in [([square("bnd_SOLID")], []),
                                  ([], [{"x": 200, "y": 200, "radius": 40,
                                         "status": ["os_active", "os_solid"]}])]:
            with self.subTest(boundary=bool(boundary)):
                x = 305 if boundary else 190
                charger = Regiment("c", "C", x, 200, 128, Side.PLAYER, models=1,
                                   ranks=1, speed_per_tick=0, attack_target="e")
                enemy = Regiment("e", "E", 450, 200, 0, Side.ENEMY, models=1, ranks=1)
                battle = Battle(500, 500, [charger, enemy], boundaries=boundary, objects=objects)
                battle.tick()
                self.assertEqual(charger.attack_target, "e")
                self.assertIsNone(charger.charge_started_target)
                self.assertFalse(any(event.kind == "charge_end" for event in battle.events))
                self.assertFalse(any(event.code == 0x09 for event in
                                     battle.event_bus.unit_states["e"].event_queue))

    def test_scenery_contact_behind_charger_keeps_charge(self):
        charger = Regiment("c", "C", 210, 200, 128, Side.PLAYER, models=1, ranks=1,
                           speed_per_tick=0, attack_target="e")
        enemy = Regiment("e", "E", 400, 200, 0, Side.ENEMY, models=1, ranks=1)
        obj = {"x": 190, "y": 200, "radius": 40,
               "status": ["os_active", "os_solid"]}
        battle = Battle(500, 500, [charger, enemy], objects=[obj])
        battle.tick()
        self.assertEqual(charger.attack_target, "e")
        self.assertFalse(any(event.kind == "charge_end" for event in battle.events))

    def test_friendly_push_translates_models_with_the_anchor(self):
        standing = Regiment("s", "S", 200, 200, 0, Side.PLAYER, models=1, ranks=1)
        moving = Regiment("m", "M", 210, 200, 0, Side.PLAYER, models=1, ranks=1,
                          target_x=350, target_y=200)
        battle = Battle(500, 500, [standing, moving])
        moving.collision_recheck = True  # it has just stepped
        before = moving.model_positions()[0]
        old_x, old_y = moving.x, moving.y
        battle._resolve_collisions()
        self.assertNotEqual((moving.x, moving.y), (old_x, old_y))
        self.assertAlmostEqual(moving.positions[0][0], before[0] + moving.x - old_x)
        self.assertAlmostEqual(moving.positions[0][1], before[1] + moving.y - old_y)

    def test_player_peasant_overlap_pushes_the_moving_regiment(self):
        # notes/bf003_peasant_move_obstruction.md acceptance case 4: an actual overlap pushes the normally
        # active pair; route filtering is not collision immunity.
        peasants = Regiment("p", "Peasants", 200, 200, 0, Side.NEUTRAL, models=5, ranks=2)
        infantry = Regiment("i", "Infantry", 215, 200, 0, Side.PLAYER, models=1, ranks=1,
                            target_x=350, target_y=200)
        battle = Battle(500, 500, [peasants, infantry])
        infantry.collision_recheck = True  # it has just stepped
        old = (infantry.x, infantry.y)
        battle._resolve_collisions()
        self.assertNotEqual((infantry.x, infantry.y), old)

    def test_any_allied_unit_gives_the_same_route_decision_as_peasants(self):
        # Acceptance case 5: the rule is about side, state and footprint, not about Peasants.
        decisions = []
        for name, sprite in (("Peasants", "peasant"), ("Allied Dwarfs", "dwarf")):
            mover = Regiment("m", "Infantry", 100, 200, 128, Side.PLAYER, models=1, ranks=1)
            ally = Regiment("a", name, 200, 200, 384, Side.NEUTRAL, models=5, ranks=2, sprite=sprite)
            battle = Battle(500, 500, [mover, ally])
            goal = (350, 200)
            decisions.append((battle.route_unit_relation(mover, ally, False),
                              battle._steering_target(mover, goal, ("move", *goal))))
        self.assertEqual(decisions[0], decisions[1])

    def test_obstruction_scan_uses_authored_object_order(self):
        from whshr import steering
        obstacles = [steering.Footprint("far", 300, 100, 20), steering.Footprint("near", 170, 100, 20)]
        found = steering.scan((100, 100), (400, 100), obstacles, 6, lambda footprint: True)
        self.assertEqual(found.footprint.key if found else None, "far")

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
        self.assertTrue(unit.moving)  # out of the 256 look-ahead at the order: no detour yet
        unit.x = 6000.0
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

    def test_a_routed_unit_leaves_the_table_and_broadcasts_its_departure(self):
        # notes/movement_boundaries_route_finding.md, flight: on the departure check every other unit (either side,
        # but not the fugitive itself) drops it as a target and gets event 0x0E (source = the fugitive); the unit is
        # removed from play later.
        unit = Regiment("u", "U", 290, 200, 128, Side.PLAYER, models=1, ranks=1, speed_per_tick=20)
        chaser = Regiment("c", "C", 100, 100, 0, Side.ENEMY, models=1, ranks=1, speed_per_tick=0)
        bystander = Regiment("b", "B", 100, 400, 0, Side.PLAYER, models=1, ranks=1, speed_per_tick=0)  # same side
        chaser.attack_target = "u"
        battle = Battle(500, 500, [unit, chaser, bystander], boundaries=[square("bnd_BATTLEEDGE")])
        battle.event_bus.unit_states["c"].current_target = ("u", 0)
        unit.routing = True
        unit.flee_x, unit.flee_y = 1000, 200
        for _ in range(200):
            battle.tick()
            if unit.fled:
                break
        self.assertTrue(unit.fled and not unit.active)
        self.assertIsNone(chaser.attack_target)
        self.assertIsNone(battle.event_bus.unit_states["c"].current_target)
        for identifier in ("c", "b"):
            self.assertEqual([(e.code, e.source) for e in battle.event_bus.unit_states[identifier].event_queue
                              if e.code == 0x0E], [(0x0E, "u")])
        self.assertEqual([e.code for e in battle.event_bus.unit_states["u"].event_queue if e.code == 0x0E], [])
        self.assertEqual([e.data["regiment"] for e in battle.events if e.kind == "fled"], ["u"])

    def test_routing_without_battle_edge_completes_at_first_edge_check(self):
        unit = Regiment("u", "U", 200, 200, 128, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=0, routing=True, flee_x=1000, flee_y=200)
        battle = Battle(500, 500, [unit])
        battle.tick()
        self.assertTrue(unit.flight_departed)
        self.assertTrue(unit.flight_complete)
        self.assertFalse(unit.fled)
        battle.tick()
        self.assertTrue(unit.fled)


if __name__ == "__main__":
    unittest.main()


class MarkedUnitCollisionTests(unittest.TestCase):
    def test_a_marked_unit_is_not_pushed_and_does_not_push(self):
        # notes/script_behaviours.md 2.2: a marked (leaving the battle) unit, such as BF003's peasants, is not touched
        # by the collision pass, so a moving regiment walks through it instead of being shoved back every tick.
        from whshr import interpreter
        peasants = Regiment("p", "Peasants", 200, 200, 0, Side.NEUTRAL, models=5, ranks=2)
        infantry = Regiment("i", "Infantry", 215, 200, 0, Side.PLAYER, models=1, ranks=1,
                            target_x=350, target_y=200)
        battle = Battle(500, 500, [peasants, infantry])
        battle.event_bus.unit_states["p"].unit_flags |= interpreter.LEAVING_BATTLE_FLAG
        old = (infantry.x, infantry.y)
        battle._resolve_collisions()
        self.assertEqual((infantry.x, infantry.y), old)


class ReformCasualtyTests(unittest.TestCase):
    def test_a_casualty_during_a_re_form_does_not_crash_its_completion(self):
        # Playtest crash: KeyError on a slot of the old layout when the re-form completed after a model died.
        from whshr import combat
        unit = Regiment("u", "U", 500, 500, 0, Side.PLAYER, models=12, ranks=3, speed_per_tick=2.25)
        battle = Battle(1000, 1000, [unit], seed=1995)
        unit.model_positions()
        battle.reform_to_ranks(unit, 2)
        for _ in range(3):
            battle.tick()
        self.assertTrue(unit.reforming)
        combat.kill_models(unit, [0], battle, 2)
        survivor_ids = {model.uid for model in unit.melee_models}
        for _ in range(600):
            battle.tick()
            if not unit.reforming:
                break
        self.assertFalse(unit.reforming)
        self.assertEqual(len(unit.positions), unit.models)
        self.assertEqual({model.uid for model in unit.melee_models}, survivor_ids)
        self.assertEqual(sum(event.kind == "reform_complete" for event in battle.events), 1)
