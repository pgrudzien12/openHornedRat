"""Independent deployment scenarios from notes/deployment.md, using synthetic data."""

import copy
from pathlib import Path
import tempfile
import unittest

from whshr.engine import Battle
from whshr.script import load_battle
from whshr import behaviour, interpreter


class ScriptData:
    """Synthetic script data, never loaded from an original executable."""

    def __init__(self, words):
        self.words = words

    def scripts(self, ids):
        return {i: self.words for i in ids}


def instruction(name):
    return behaviour.OPCODE_FLAG | next(i for i, label in behaviour.OPCODE_NAMES.items() if label == name)


class DeploymentLifecycleTests(unittest.TestCase):
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
