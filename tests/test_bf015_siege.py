"""BF015/BF017 siege behaviour from notes/bf015_gate_npc_column.md: the gate's control piece, node placement, the
not-shown script flag and arrival while steering."""

import math
import unittest

from whshr import control_piece, interpreter
from whshr.engine import Battle, Regiment
from whshr.nodes import ScriptNode
from whshr.rules import Side

GATE = {"name": "ZhufWallEnt", "x": 920, "y": 2040, "dir": 0}


def _siege_battle(*regiments: Regiment) -> Battle:
    return Battle(2000, 2240, list(regiments) or [Regiment("u", "U", 100, 100, 0, Side.PLAYER)],
                  scenery=[{"name": "Rock1", "x": 0, "y": 0}, GATE])


class ControlPieceTests(unittest.TestCase):
    """Q1 1.2 and the 1.5 test vectors."""

    def test_given_a_zhufbar_gate_when_the_battle_loads_then_the_state_is_1_and_the_doors_are_closed(self):
        battle = _siege_battle()
        assert battle.control_piece is not None
        self.assertEqual((battle.mission_state, battle.control_piece.swing_frame()), (1, 0))

    def test_given_no_gate_piece_then_the_state_starts_at_0_and_stays_as_scripts_set_it(self):
        battle = Battle(500, 500, [Regiment("u", "U", 100, 100, 0, Side.PLAYER)])
        battle.mission_state = 2
        battle.tick(0.1)
        self.assertIsNone(battle.control_piece)
        self.assertEqual(battle.mission_state, 2)

    def test_given_an_open_request_then_state_4_comes_at_the_end_of_tick_t_plus_49(self):
        piece = control_piece.from_scenery([GATE])
        assert piece is not None
        state = piece.step(2)  # end of tick T: frame 0, opening
        self.assertEqual((state, piece.swing_frame()), (3, 0))
        frames: dict[int, int] = {}
        for tick in range(1, 50):
            state = piece.step(state)
            frames[tick] = piece.swing_frame()
            if tick < 49:
                self.assertEqual(state, 3, tick)
        self.assertEqual(state, 4)
        self.assertEqual((frames[3], frames[45], frames[48]), (1, 15, 15))
        self.assertAlmostEqual(piece.door_turn() * 360, 15 / 63 * 360)  # about 85.7 degrees

    def test_given_a_shut_request_then_the_doors_close_and_7_comes_at_the_end(self):
        piece = control_piece.from_scenery([GATE])
        assert piece is not None
        state = piece.step(5)
        self.assertEqual((state, piece.swing_frame()), (6, 15))
        for _ in range(49):
            state = piece.step(state)
        self.assertEqual((state, piece.swing_frame()), (7, 0))

    def test_given_a_script_opens_the_gate_then_later_scripts_that_tick_still_read_2(self):
        battle = _siege_battle()
        battle.mission_state = 2  # a script's SetBattleState 2 during tick T
        self.assertEqual(battle.mission_state, 2)  # what IfBattleState reads for units later in tick T
        battle.tick(0.1)
        self.assertEqual(battle.mission_state, 3)
        for _ in range(49):
            battle.tick(0.1)
        self.assertEqual(battle.mission_state, 4)

    def test_given_a_portcullis_then_closing_sets_7_at_once_and_6_once_shut(self):
        piece = control_piece.from_scenery([{"name": "PortcullisEnt", "x": 400, "y": 1760, "dir": 384}])
        assert piece is not None
        state = piece.step(2)
        for _ in range(30):
            state = piece.step(state)
        self.assertEqual((state, piece.portcullis_lift()), (4, 10.0))
        state = piece.step(5)
        self.assertEqual(state, 7)
        for _ in range(30):
            state = piece.step(state)
        self.assertEqual((state, piece.portcullis_lift()), (6, 0.0))


class NodePlacementTests(unittest.TestCase):
    """Q2: PlaceAtNode carries the figures; TeleportToNode leaves them where they stand."""

    def setUp(self):
        self.unit = Regiment("col", "Column", 1642, 1826, 26, Side.NEUTRAL, models=12, ranks=3)
        nodes = [ScriptNode(507, 24, radius=137, direction=26), ScriptNode(500, 500, direction=128),
                 ScriptNode(10, 10, active=False)]
        self.battle = Battle(2000, 2240, [self.unit], nodes={i: (n.x, n.y) for i, n in enumerate(nodes)},
                             script_nodes=nodes)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["col"]
        self.unit.model_positions()

    def test_given_a_column_off_the_map_when_placed_at_node_15_then_every_figure_stands_there_at_once(self):
        self.interp.op_PlaceAtNode(self.state, 0, [], "col", 0, None)
        self.assertEqual((self.unit.x, self.unit.y, self.unit.direction), (507, 24, 26))
        self.assertTrue(all(math.dist(p, (507, 24)) < 60 for p in self.unit.positions))
        self.assertTrue(all(model.at_rest for model in self.unit.melee_models))
        self.assertFalse(self.unit.reforming)

    def test_given_a_node_with_another_facing_then_placement_takes_it_but_keeps_the_old_arrangement(self):
        before = [(x - self.unit.x, y - self.unit.y) for x, y in self.unit.positions]
        self.interp.op_PlaceAtNode(self.state, 1, [], "col", 0, None)
        after = [(x - 500, y - 500) for x, y in self.unit.positions]
        self.assertEqual(self.unit.direction, 128)
        for (bx, by), (ax, ay) in zip(before, after):
            self.assertAlmostEqual(bx, ax)
            self.assertAlmostEqual(by, ay)

    def test_given_a_teleport_then_the_figures_keep_their_world_positions_and_must_walk(self):
        before = list(self.unit.positions)
        self.interp.op_TeleportToNode(self.state, 1, [], "col", 0, None)
        self.assertEqual((self.unit.x, self.unit.y, self.unit.direction), (500, 500, 128))
        self.assertEqual(self.unit.positions, before)
        self.assertFalse(any(model.at_rest for model in self.unit.melee_models))

    def test_given_an_anchored_war_machine_then_place_at_node_still_moves_it(self):
        # notes/bf017_merged_mortars.md 3: no anchor test in PlaceAtNode.
        self.unit.hud_class = "art"
        self.assertTrue(self.unit.anchored)
        self.interp.op_PlaceAtNode(self.state, 0, [], "col", 0, None)
        self.assertEqual((self.unit.x, self.unit.y), (507, 24))

    def test_given_an_inactive_node_then_neither_placement_does_anything(self):
        self.interp.op_PlaceAtNode(self.state, 2, [], "col", 0, None)
        self.interp.op_TeleportToNode(self.state, 2, [], "col", 0, None)
        self.assertEqual((self.unit.x, self.unit.y), (1642, 1826))
        self.assertIsNone(self.state.current_node)


class NotShownFlagTests(unittest.TestCase):
    """Q3: script flag 0x10000000 takes the unit off the display and out of contact; 0x20000000 drops the marker."""

    def test_given_the_waiting_column_flags_then_it_is_not_drawn_until_they_are_cleared(self):
        unit = Regiment("col", "Column", 1642, 1826, 26, Side.NEUTRAL, models=12, ranks=3)
        battle = Battle(2000, 2240, [unit])
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["col"]
        interp.op_SetUnitFlags(state, 0x30000000, [], "col", 0, None)
        self.assertFalse(unit.visible_to_player)
        self.assertTrue(battle.minimap_marker_suppressed(unit))
        interp.op_ClearUnitFlags(state, 0x30000000, [], "col", 0, None)
        self.assertTrue(unit.visible_to_player)
        self.assertFalse(battle.minimap_marker_suppressed(unit))


class DeploymentSpottingTests(unittest.TestCase):
    """Owner's decision: nothing is spotted during deployment; the first spotting pass runs at Start."""

    def test_given_a_hidden_enemy_in_view_when_a_regiment_is_placed_during_deployment_then_it_stays_hidden(self):
        wolves = Regiment("wolves", "Wolves", 194, 106, 128, Side.PLAYER, models=10, ranks=2)
        archers = Regiment("archers", "Archers", 600, 106, 384, Side.ENEMY, models=10, ranks=2, hidden=True)
        battle = Battle(2000, 2240, [wolves, archers], deploy=True)
        battle.refresh_visibility()
        self.assertTrue(archers.hidden)
        battle.start_battle()
        self.assertFalse(archers.hidden)


class SteeringArrivalTests(unittest.TestCase):
    """Q4: the 32-unit arrival test measures to the waypoint, not to the steer point."""

    def test_given_a_single_figure_closing_on_a_wagon_ahead_then_it_keeps_moving_to_its_far_node(self):
        hero = Regiment("hero", "Hero", 748, 890, 31, Side.PLAYER, models=1, ranks=1)
        wagon = Regiment("wagon", "Wagon", 760, 951, 31, Side.NEUTRAL, models=2, ranks=2)
        battle = Battle(2000, 2240, [hero, wagon])
        battle.order_move("hero", 1000, 1940)
        for _ in range(40):
            battle.tick(0.1)
        self.assertIsNotNone(hero.target_x)
        self.assertGreater(math.dist((hero.x, hero.y), (748, 890)), 20)


if __name__ == "__main__":
    unittest.main()
