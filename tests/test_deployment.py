"""Independent deployment scenarios from notes/deployment.md, using synthetic data."""

import copy
from pathlib import Path
import tempfile
import math
import unittest

from whshr.engine import Battle
from whshr.script import load_battle
from whshr import behaviour, interpreter
from whshr import formation
from whshr.rules import Side
from whshr.deployment import Region


def region(x1=0, y1=0, x2=1000, y2=1000, extra=()):
    return {"name": "UnrelatedName", "status": ["bnd_ACTIVE", "bnd_DEPLOYMENT", *extra],
            "lines": [[x1, y1, x2, y1], [x2, y1, x2, y2],
                      [x2, y2, x1, y2], [x1, y2, x1, y1]]}


class DeploymentPlacementTests(unittest.TestCase):
    def test_given_equally_near_segments_then_clipping_uses_first_and_truncates_projected_coordinates(self):
        polygon = Region(((0, 0, 10, 0), (10, 0, 10, 10), (10, 10, 0, 10), (0, 10, 0, 0)), inverted=True)
        self.assertEqual(polygon.clip((5, 5)), (5, 0))
        slope = Region(((-10, -10, 10, 10),), inverted=True)
        self.assertEqual(slope.clip((-3, -2)), (-2, -2))
    def battle(self, boundaries=None, artillery=False):
        data = source(1)
        data["nodes"] = []
        data["merc"]["armies"][0]["units"][0]["set"].update(x=100, y=100, dir=0)
        if artillery:
            data["merc"]["armies"][0]["units"][0]["stats"]["s_side"] = [15, 3, 3, 1]
        data["boundaries"] = [region()] if boundaries is None else boundaries
        return Battle.from_script(data)

    def centre(self, regiment):
        return formation.footprint_frame(*regiment.block())[:2]

    def test_given_first_drag_then_acquisition_overshoots_and_later_updates_use_half_steps(self):
        battle = self.battle()
        r = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(300, 300)
        battle.tick()
        self.assertEqual(self.centre(r), (400, 400))
        battle.tick()
        self.assertEqual(self.centre(r), (350, 350))
        battle.end_deployment_drag()
        battle.tick()
        self.assertEqual(self.centre(r), (350, 350))

    def test_given_off_centre_grab_then_drag_keeps_offset_and_release_retains_position(self):
        battle = self.battle()
        r = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 105, 107)
        battle.update_deployment_drag(125, 127)
        battle.tick()
        self.assertEqual(self.centre(r), (130, 130))
        battle.end_deployment_drag()
        before = self.centre(r)
        battle.tick()
        self.assertEqual(self.centre(r), before)

    def test_given_ctrl_drag_then_centre_stays_while_front_anchor_rotates(self):
        battle = self.battle()
        r = battle.regiments["player0"]
        r.models, r.ranks = 12, 3
        centre = self.centre(r)
        before_anchor = (r.x, r.y)
        battle.begin_deployment_drag("player0", *centre)
        battle.update_deployment_drag(centre[0] + 100, centre[1], rotate=True)
        battle.tick()
        self.assertEqual(r.direction, 128)
        self.assertEqual(self.centre(r), centre)
        self.assertNotEqual((r.x, r.y), before_anchor)

    def test_given_missing_zone_then_translation_waits_but_rotation_still_works(self):
        battle = self.battle([])
        r = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(300, 100)
        battle.tick()
        self.assertEqual(self.centre(r), (100, 100))
        battle.update_deployment_drag(300, 100, rotate=True)
        battle.tick()
        self.assertEqual(r.direction, 128)

    def test_given_remembered_zone_then_outside_target_clips_centre_not_all_soldiers(self):
        battle = self.battle([region(0, 0, 200, 200)])
        r = battle.regiments["player0"]
        r.models, r.ranks = 12, 3
        battle.begin_deployment_drag("player0", *self.centre(r))
        battle.update_deployment_drag(110, 100)
        battle.tick()
        battle.update_deployment_drag(600, 100)
        battle.tick()
        self.assertEqual(self.centre(r)[0], 200)
        self.assertTrue(any(x > 200 for x, _ in r.model_positions()))

    def test_given_released_drag_then_remembered_region_is_shared_by_later_drags(self):
        battle = self.battle([region(0, 0, 200, 200), region(300, 300, 500, 500)])
        r = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(120, 120)
        battle.tick()
        battle.end_deployment_drag()
        battle.begin_deployment_drag("player0", *self.centre(r))
        battle.update_deployment_drag(250, 250)
        battle.tick()
        self.assertEqual(self.centre(r), (190, 190))
        battle.update_deployment_drag(400, 400)
        battle.tick()
        self.assertEqual(self.centre(r), (500, 500))

    def test_given_one_unit_drag_delta_then_neither_position_nor_facing_changes(self):
        battle = self.battle()
        r = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(101, 101, rotate=True)
        battle.tick()
        self.assertEqual((r.x, r.y, r.direction), (100, 100, 0))

    def test_given_artillery_then_direct_translation_and_rotation_are_allowed_but_move_is_refused(self):
        battle = self.battle(artillery=True)
        r = battle.regiments["player0"]
        old = self.centre(r)
        battle.begin_deployment_drag("player0", *old)
        battle.update_deployment_drag(old[0] + 100, old[1])
        battle.tick()
        self.assertNotEqual(self.centre(r), old)
        battle.update_deployment_drag(r.x + 100, r.y, rotate=True)
        battle.tick()
        self.assertNotEqual(r.direction, 0)
        self.assertEqual(len(r.model_positions()), 3)
        with self.assertRaises(ValueError):
            battle.order_move("player0", 500, 500)

    def test_given_enemy_or_ineligible_regiment_then_direct_drag_is_refused(self):
        battle = self.battle()
        r = battle.regiments["player0"]
        for field, value in (("routing", True), ("held", True), ("side", Side.ENEMY)):
            original = getattr(r, field)
            setattr(r, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                battle.begin_deployment_drag("player0", 100, 100)
            setattr(r, field, original)

    def test_given_collision_at_zone_edge_then_correction_can_push_centre_outside_without_final_clamp(self):
        from whshr.engine import Regiment
        battle = self.battle([region(0, 0, 200, 200)])
        r = battle.regiments["player0"]
        battle.regiments["other"] = Regiment("other", "Other", 199, 100, 0, Side.PLAYER)
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(190, 100)
        battle.tick()
        self.assertGreater(self.centre(r)[0], 200)

    def test_given_solid_tree_object_then_deployment_drag_pushes_the_regiment_out(self):
        battle = self.battle()
        regiment = battle.regiments["player0"]
        tree = {"name": "Tree", "x": 190, "y": 100, "radius": 30,
                "status": ["os_active", "os_solid"]}
        battle.objects.append(tree)
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(160, 100)  # first-zone acquisition proposes (190, 100)
        battle.tick()
        cx, cy = self.centre(regiment)
        self.assertAlmostEqual(cy, 100)
        self.assertGreater(cx, 220)
        self.assertGreaterEqual(cx - tree["x"], tree["radius"] + regiment.bounding_radius() - 0.1)

    def test_given_solid_circle_on_the_drag_path_then_the_centre_does_not_end_inside_it(self):
        battle = self.battle()
        regiment = battle.regiments["player0"]
        circle = {"name": "Rock", "x": 250, "y": 100, "radius": 40, "status": ["os_active", "os_solid"]}
        battle.objects.append(circle)
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(200, 100)
        battle.tick()
        cx, cy = self.centre(regiment)
        self.assertGreater(math.hypot(cx - circle["x"], cy - circle["y"]), 0)
        self.assertGreaterEqual(math.hypot(cx - circle["x"], cy - circle["y"]),
                                circle["radius"] / 2)  # half-overlap correction leaves it out of the centre

    def test_given_no_entry_boundary_around_the_drop_point_then_the_centre_is_pushed_out_of_it(self):
        # A closed no-entry (inverse solid) area, not a deployment zone, over where the drag lands; correction follows the clipping.
        area = {"name": "Cliff", "status": ["bnd_ACTIVE", "bnd_INVSOLID"],
                "lines": [[180, 60, 260, 60], [260, 60, 260, 140], [260, 140, 180, 140], [180, 140, 180, 60]]}
        battle = self.battle([region(), area])
        regiment = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(160, 100)  # first-zone acquisition proposes (190, 100), inside the area
        battle.tick()
        centre = self.centre(regiment)
        self.assertLess(centre[0], 190)  # halfway toward the nearest edge, not a full clamp

    def test_given_non_solid_tree_then_deployment_drag_keeps_the_proposed_centre(self):
        for status in (["os_active"], ["os_solid"]):
            with self.subTest(status=status):
                battle = self.battle()
                regiment = battle.regiments["player0"]
                battle.objects.append({"name": "Tree", "x": 190, "y": 100,
                                       "radius": 30, "status": status})
                battle.begin_deployment_drag("player0", 100, 100)
                battle.update_deployment_drag(160, 100)
                battle.tick()
                self.assertEqual(self.centre(regiment), (190, 100))

    def test_given_tree_at_zone_edge_then_solid_push_follows_clipping(self):
        battle = self.battle([region(0, 0, 200, 200)])
        regiment = battle.regiments["player0"]
        battle.objects.append({"name": "Tree", "x": 190, "y": 100, "radius": 30,
                               "status": ["os_active", "os_solid"]})
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(190, 100)
        battle.tick()
        self.assertGreater(self.centre(regiment)[0], 200)

    def test_given_inverted_region_then_outside_is_allowed_and_inside_target_is_clipped(self):
        battle = self.battle([region(200, 200, 400, 400, ["bnd_INVSOLID"])])
        r = battle.regiments["player0"]
        battle.begin_deployment_drag("player0", 100, 100)
        battle.update_deployment_drag(120, 100)
        battle.tick()
        self.assertEqual(self.centre(r), (130, 100))
        battle.update_deployment_drag(300, 300)
        for _ in range(10):
            battle.tick()
        self.assertFalse(200 < r.x < 400 and 200 < r.y < 400)


class ScriptData:
    """Synthetic script data, never loaded from an original executable."""

    def __init__(self, words):
        self.words = words

    def scripts(self, ids):
        return {i: self.words for i in ids}


def instruction(name):
    return behaviour.OPCODE_FLAG | next(i for i, label in behaviour.OPCODE_NAMES.items() if label == name)


class DeploymentLifecycleTests(unittest.TestCase):
    def test_given_hidden_observer_and_hidden_enemy_when_facing_changes_during_battle_then_enemy_is_spotted(self):
        data = source(1)
        data["nodes"] = []
        own = data["merc"]["armies"][0]["units"][0]
        own["hidden"] = True
        own["set"].update(x=100, y=100, dir=256)
        enemy = unit("enemy", 129)
        enemy["hidden"] = True
        enemy["set"].update(x=100, y=900, dir=0)
        data["armies"] = [{"count": 1, "units": [enemy]}]
        battle = Battle.from_script(data)
        battle.start_battle()
        self.assertTrue(battle.regiments["enemy"].hidden)
        battle.regiments["player0"].direction = 0
        battle.tick()
        self.assertFalse(battle.regiments["enemy"].hidden)
        self.assertTrue(battle.regiments["player0"].hidden)
        self.assertEqual([e.code for e in battle.event_bus.unit_states["enemy"].event_queue], [0x1C])
        battle.regiments["player0"].direction = 256
        battle.tick()
        self.assertFalse(battle.regiments["enemy"].hidden)

    def test_given_hidden_player_when_initialized_selected_and_dragged_then_flag_is_preserved(self):
        data = source(1)
        data["boundaries"] = [region()]
        data["merc"]["armies"][0]["units"][0]["hidden"] = True
        words = [instruction("InitUnit"), instruction("WaitForBattleStart"), behaviour.END]
        battle = Battle.from_script(data, script_dll=ScriptData(words))
        regiment = battle.regiments["player0"]
        battle.tick()
        self.assertTrue(regiment.hidden)
        self.assertTrue(regiment.visible_to_player)
        centre = battle.formation_centre(regiment)
        self.assertEqual(battle.regiment_at(*centre), "player0")
        battle.begin_deployment_drag("player0", *centre)
        battle.update_deployment_drag(centre[0] + 100, centre[1])
        battle.tick()
        self.assertNotEqual(battle.formation_centre(regiment), centre)
        self.assertTrue(regiment.hidden)

    def test_given_hidden_enemy_when_ground_geometry_is_picked_then_display_remains_suppressed(self):
        data = source(1)
        enemy = unit("enemy", 129)
        enemy["hidden"] = True
        data["armies"] = [{"count": 1, "units": [enemy]}]
        battle = Battle.from_script(data)
        regiment = battle.regiments["enemy"]
        self.assertFalse(regiment.visible_to_player)
        self.assertEqual(battle.regiment_at(*battle.formation_centre(regiment), player_only=False), "enemy")

    def test_given_route_when_appending_near_endpoints_or_more_than_nine_then_extra_destinations_are_ignored(self):
        battle = Battle.from_script(source(1))
        battle.append_waypoint("player0", 100, 100)
        battle.append_waypoint("player0", 200, 100)
        battle.append_waypoint("player0", 110, 100)
        battle.append_waypoint("player0", 210, 100)
        self.assertEqual(battle.regiments["player0"].waypoints, [(100, 100), (200, 100)])
        for x in range(300, 1100, 100):
            battle.append_waypoint("player0", x, 100)
        self.assertEqual(len(battle.regiments["player0"].waypoints), 9)
        self.assertEqual(battle.regiments["player0"].waypoints[-1], (900, 100))

    def test_given_prepared_route_when_direct_drag_begins_then_it_is_cleared(self):
        battle = Battle.from_script(source(1))
        battle.append_waypoint("player0", 100, 100)
        battle.begin_deployment_drag("player0", *battle.formation_centre(battle.regiments["player0"]))
        self.assertEqual(battle.regiments["player0"].waypoints, [])

    def test_given_allied_wagon_when_dragging_then_authored_position_is_preserved(self):
        data = source(1)
        wagon = unit("wagon", 65)
        wagon["stats"]["s_side"] = [65, 2, 2, 1]
        wagon["stats"]["s_race"] = [56]
        data["armies"] = [{"count": 1, "units": [wagon]}]
        battle = Battle.from_script(data)
        regiment = battle.regiments["wagon"]
        self.assertTrue(regiment.is_wagon)
        before = (regiment.x, regiment.y, regiment.direction)
        with self.assertRaises(ValueError):
            battle.begin_deployment_drag("wagon", regiment.x, regiment.y)
        self.assertEqual((regiment.x, regiment.y, regiment.direction), before)

    def test_given_hidden_regiment_when_script_clears_hidden_flag_then_it_becomes_pickable_during_deployment(self):
        data = source(1)
        data["merc"]["armies"][0]["units"][0]["hidden"] = True
        words = [instruction("ClearUnitFlags"), 0x80000, instruction("WaitForBattleStart"), behaviour.END]
        battle = Battle.from_script(data, script_dll=ScriptData(words))
        self.assertTrue(battle.regiments["player0"].hidden)
        battle.tick()
        self.assertFalse(battle.regiments["player0"].hidden)
        centre = battle.formation_centre(battle.regiments["player0"])
        self.assertEqual(battle.regiment_at(*centre), "player0")

    def test_given_reached_timer_at_start_barrier_then_each_deployment_update_consumes_it_once(self):
        words = [instruction("SetWait"), 20, instruction("WaitForBattleStart"), instruction("Yield"), behaviour.END]
        battle = Battle.from_script(source(1), script_dll=ScriptData(words))
        for _ in range(5):
            battle.tick()
        state = battle.event_bus.unit_states["player0"]
        self.assertEqual(state.wait_remaining, 16)
        battle.start_battle()
        battle.tick()
        self.assertEqual(state.wait_remaining, 15)

    def test_given_nearest_enemy_attack_attempts_then_deployment_refuses_them_and_start_allows_them(self):
        words = [instruction("PushPC"), instruction("AttackNearestEnemy"), instruction("Yield"), instruction("Loop")]
        data = source(1)
        enemy = unit("enemy", 129)
        enemy["set"].update(x=600, y=700)
        data["armies"] = [{"count": 1, "units": [enemy]}]
        battle = Battle.from_script(data, script_dll=ScriptData(words))
        state = battle.event_bus.unit_states["enemy"]
        for _ in range(5):
            battle.tick()
        self.assertEqual([event.code for event in state.event_queue], [])
        self.assertEqual(state.cond_flags, 0)
        battle.start_battle()
        battle.tick()
        # The search queues "attack target" (0x04, source = the pick) to itself; its handler attacks.
        self.assertEqual([(event.code, event.source) for event in state.event_queue][-1:], [(0x04, "player0")])

    def test_given_mission_state_changes_then_they_do_not_start_battle_or_release_its_barrier(self):
        words = [instruction("SetBattleState"), 2, instruction("IfBattleState"), 2,
                 instruction("WaitForBattleStart"), instruction("Yield"), behaviour.END]
        battle = Battle.from_script(source(1), script_dll=ScriptData(words))
        battle.tick()
        self.assertEqual(battle.mission_state, 2)
        self.assertEqual(battle.phase, "deployment")
        self.assertEqual(battle.tick_count, 0)
        self.assertEqual(battle.event_bus.unit_states["player0"].pc, 4)
        self.assertEqual(battle.event_bus.unit_states["player0"].cond_flags, 1)
        battle.start_battle()
        battle.tick()
        self.assertEqual(battle.mission_state, 2)

    def test_given_hidden_enemy_in_view_when_started_then_it_is_revealed_permanently_and_spotting_events_are_posted(self):
        data = source(1)
        data["nodes"] = []
        data["merc"]["armies"][0]["units"][0]["set"].update(x=100, y=100, dir=0)
        enemy = unit("enemy", 129)
        enemy["set"].update(x=100, y=900, dir=0)
        enemy["hidden"] = True
        data["armies"] = [{"count": 1, "units": [enemy]}]
        battle = Battle.from_script(data)
        self.assertFalse(battle.regiments["player0"].hidden)
        self.assertTrue(battle.regiments["enemy"].hidden)
        battle.start_battle()
        self.assertFalse(battle.regiments["enemy"].hidden)
        self.assertEqual(battle.event_bus.unit_states["enemy"].event_queue[0].code, 0x1C)
        battle.regiments["player0"].direction = 256
        battle.refresh_visibility()
        self.assertFalse(battle.regiments["enemy"].hidden)

    def test_given_sight_boundary_between_armies_when_started_then_hidden_enemy_remains_hidden(self):
        data = source(1)
        data["nodes"] = []
        data["merc"]["armies"][0]["units"][0]["set"].update(x=100, y=100, dir=0)
        enemy = unit("enemy", 129)
        enemy["set"].update(x=100, y=900, dir=0)
        enemy["hidden"] = True
        data["armies"] = [{"count": 1, "units": [enemy]}]
        data["boundaries"] = [{"status": ["bnd_ACTIVE", "bnd_SIGHTEDGE"], "lines": [[0, 500, 1000, 500]]}]
        battle = Battle.from_script(data)
        battle.start_battle()
        self.assertTrue(battle.regiments["enemy"].hidden)
        with self.assertRaises(ValueError):
            battle.order_attack("player0", "enemy")
    def test_given_deployment_when_updates_run_then_combat_clock_and_results_wait_for_start(self):
        data = source(1)
        data["armies"] = [{"count": 1, "units": [unit("enemy", 129)]}]
        battle = Battle.from_script(data)
        battle.regiments["enemy"].models = 0
        for _ in range(20):
            battle.tick()
        self.assertEqual(battle.phase, "deployment")
        self.assertEqual(battle.tick_count, 0)
        self.assertEqual(battle.update_count, 20)
        self.assertIsNone(battle.result)
        battle.start_battle()
        battle.tick()
        self.assertEqual(battle.phase, "battle")
        self.assertEqual(battle.tick_count, 1)
        self.assertEqual(battle.result, "victory")

    def test_given_no_deployment_keyword_when_loaded_then_normal_play_begins_directly(self):
        battle = Battle.from_script(source(deploy=False))
        self.assertEqual(battle.phase, "battle")
        battle.tick()
        self.assertEqual(battle.tick_count, 1)

    def test_given_setup_wait_before_start_barrier_when_deploying_then_setup_finishes_but_later_wait_stays_pending(self):
        words = [instruction("SetWait"), 2, instruction("Wait"),
                 instruction("WaitForBattleStart"), instruction("SetWait"), 3,
                 instruction("Wait"), behaviour.END]
        battle = Battle.from_script(source(1), script_dll=ScriptData(words))
        state = battle.event_bus.unit_states["player0"]
        for _ in range(8):
            battle.tick()
        self.assertEqual(state.pc, 3)
        self.assertEqual(state.wait_remaining, 0)
        battle.start_battle()
        battle.tick()
        self.assertEqual(state.pc, 6)
        self.assertGreater(state.wait_remaining, 0)

    def test_given_prepared_route_when_waiting_for_start_then_it_is_retained_and_runs_after_start(self):
        words = [instruction("WaitForBattleStart"), instruction("Yield"), behaviour.END]
        battle = Battle.from_script(source(1), script_dll=ScriptData(words))
        regiment = battle.regiments["player0"]
        before = (regiment.x, regiment.y)
        battle.order_move("player0", 800, 800)
        battle.append_waypoint("player0", 900, 900)
        for _ in range(5):
            battle.tick()
        self.assertEqual((regiment.x, regiment.y), before)
        self.assertEqual(regiment.waypoints, [(800, 800), (900, 900)])
        battle.start_battle()
        battle.tick()
        self.assertNotEqual((regiment.x, regiment.y), before)
        self.assertEqual(regiment.waypoints, [(800, 800), (900, 900)])

    def test_given_deployment_when_combat_or_facing_orders_are_requested_then_they_are_rejected(self):
        data = source(1)
        data["armies"] = [{"count": 1, "units": [unit("enemy", 129)]}]
        battle = Battle.from_script(data)
        for order in (lambda: battle.order_attack("player0", "enemy"),
                      lambda: battle.order_halt("player0"),
                      lambda: battle.order_turn_left("player0"),
                      lambda: battle.order_turn_right("player0"),
                      lambda: battle.order_about_face("player0"),
                      lambda: battle.order_face_point("player0", 900, 900)):
            with self.subTest(order=order), self.assertRaises(ValueError):
                order()

    def test_given_deployment_settings_when_started_then_positions_ranks_and_independent_are_preserved(self):
        battle = Battle.from_script(source(1))
        regiment = battle.regiments["player0"]
        regiment.models = 12
        battle.order_reform("player0", 3)
        battle.toggle_independent("player0")
        before = (regiment.x, regiment.y, regiment.direction, regiment.ranks, regiment.independent,
                  list(regiment.positions))
        battle.start_battle()
        self.assertEqual((regiment.x, regiment.y, regiment.direction, regiment.ranks, regiment.independent,
                          regiment.positions), before)


def unit(identifier, side=1):
    return {"id": identifier, "name": identifier,
            "set": {"x": -10, "y": -20, "dir": 17},
            "stats": {"s_side": [side, 1, 1, 1]}}


def source(size=3, deploy=True):
    return {"field": {"width": 1000, "height": 1000},
            "mission": {"deploy_troops": deploy}, "armies": [],
            "merc": {"armies": [{"count": size,
                                   "units": [unit(f"player{i}") for i in range(size)]}]},
            "nodes": [{"x": 100 + i * 100, "y": 200 + i * 100,
                       "dir": 64 + i, "id": 0, "radius": 100,
                       "status": ["ns_ACTIVE", "NS_STARTPOS"]} for i in range(5)]}


class StartingSlotTests(unittest.TestCase):
    def test_given_player_roster_without_coordinates_when_slots_exist_then_regiments_receive_default_slots(self):
        data = source(2)
        for item in data["merc"]["armies"][0]["units"]:
            item["set"].pop("x")
            item["set"].pop("y")
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["player0", "player1"]),
                         [(400, 500, 67), (500, 600, 68)])

    def positions(self, battle, identifiers):
        return [(battle.regiments[key].x, battle.regiments[key].y,
                 battle.regiments[key].direction) for key in identifiers]

    def test_given_different_army_sizes_when_loaded_then_last_slots_supply_positions_and_facings(self):
        for size in (2, 3, 5):
            with self.subTest(size=size):
                data = source(size)
                battle = Battle.from_script(data)
                self.assertEqual(self.positions(battle, [f"player{i}" for i in range(size)]),
                                 [(n["x"], n["y"], n["dir"]) for n in data["nodes"][-size:]])

    def test_given_reordered_army_when_loaded_then_regiments_receive_slots_in_file_order(self):
        data = source()
        data["merc"]["armies"][0]["units"].reverse()
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["player2", "player1", "player0"]),
                         [(300, 400, 66), (400, 500, 67), (500, 600, 68)])

    def test_given_non_deployment_mission_when_loaded_then_default_slots_still_apply(self):
        battle = Battle.from_script(source(deploy=False))
        self.assertEqual(self.positions(battle, ["player0"]), [(300, 400, 66)])

    def test_given_inactive_and_ordinary_nodes_when_loaded_then_only_active_start_nodes_are_used(self):
        data = source()
        data["nodes"].insert(1, {"x": 1, "y": 2, "dir": 3, "status": ["ns_startpos"]})
        data["nodes"].insert(3, {"x": 4, "y": 5, "dir": 6, "status": ["ns_active"]})
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["player0", "player1", "player2"]),
                         [(300, 400, 66), (400, 500, 67), (500, 600, 68)])

    def test_given_changed_node_metadata_when_loaded_then_slot_assignment_is_unchanged(self):
        data = source()
        for node in data["nodes"]:
            node["status"].append("ns_end")
            node["id"] = 99
            node["radius"] = 1
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["player0", "player1", "player2"]),
                         [(300, 400, 66), (400, 500, 67), (500, 600, 68)])

    def test_given_insufficient_or_missing_slots_when_loaded_then_file_coordinates_are_retained(self):
        for nodes in ([], source()["nodes"][:2]):
            with self.subTest(nodes=nodes):
                data = source()
                data["nodes"] = nodes
                battle = Battle.from_script(data)
                self.assertEqual(self.positions(battle, ["player0", "player1", "player2"]),
                                 [(-10, -20, 17)] * 3)

    def test_given_declared_army_count_when_loaded_then_it_controls_skipping(self):
        data = source(2)
        data["merc"]["armies"][0]["count"] = 3
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["player0", "player1"]),
                         [(300, 400, 66), (400, 500, 67)])

    def test_given_two_player_sections_when_loaded_then_existing_reservations_are_respected(self):
        data = source(2)
        data["merc"]["armies"].append({"count": 5, "units": [unit("second0"), unit("second1")]})
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["player0", "player1", "second0", "second1"]),
                         [(400, 500, 67), (500, 600, 68), (100, 200, 64), (200, 300, 65)])

    def test_given_reserved_tail_slots_when_another_section_loads_then_unavailable_slots_use_file_positions(self):
        data = source(2)
        data["merc"]["armies"].append({"count": 2, "units": [unit("second0")]})
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["second0"]), [(-10, -20, 17)])

    def test_given_enemy_neutral_and_player_units_when_loaded_then_only_players_receive_slots(self):
        data = source(0)
        data["armies"] = [{"count": 3, "units": [unit("enemy", 129), unit("neutral", 65), unit("player")]}]
        battle = Battle.from_script(data)
        self.assertEqual(self.positions(battle, ["enemy", "neutral", "player"]),
                         [(-10, -20, 17), (-10, -20, 17), (300, 400, 66)])

    def test_given_source_data_when_loaded_then_original_army_coordinates_remain_unchanged(self):
        data = source()
        original = copy.deepcopy(data)
        Battle.from_script(data)
        self.assertEqual(data, original)


class DeploymentBoundaryLoadingTests(unittest.TestCase):
    def test_given_renamed_boundary_when_loaded_then_status_and_geometry_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.BTS"
            path.write_text("[BATTLESCRIPT]\n[FIELD]\nset:x=1000\nset:y=1000\n[END]\n"
                            "[BOUNDARIES]\nAddBoundary:ArbitraryName\n"
                            "set:status=bnd_ACTIVE|bnd_DEPLOYMENT|bnd_INVSOLID\n"
                            "AddLine:10,20,30,40\nEndBoundary:\n[END]\n[END]\n")
            boundary = load_battle(path)["boundaries"][0]
            self.assertEqual(boundary["name"], "ArbitraryName")
            self.assertEqual(boundary["status"], ["bnd_ACTIVE", "bnd_DEPLOYMENT", "bnd_INVSOLID"])
            self.assertEqual(boundary["lines"], [[10, 20, 30, 40]])
