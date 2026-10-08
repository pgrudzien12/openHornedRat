"""Threat search, weapon-target search, nearest pick, the attack-the-nearest family and ReactToThreat
(notes/threat_events_nodes.md, part A). Vectors are the report's tables."""

import unittest
from unittest import mock

from whshr import buildings, interpreter
from whshr.nodes import ScriptNode
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side

BOW = 576.0


def unit(identifier, x, y, side=Side.PLAYER, facing=0, unit_class=1, **extra):
    return Regiment(identifier, identifier, x, y, facing, side, models=5, ranks=1, unit_class=unit_class, **extra)


class SearchTestCase(unittest.TestCase):
    def make(self, searcher, *others, phase="battle"):
        self.s = searcher
        self.battle = Battle(10000, 10000, [searcher, *others], seed=1995)
        self.battle.phase = phase
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states[searcher.identifier]

    def call(self, name, operand=None):
        return getattr(self.interp, "op_" + name)(self.state, operand, [], self.s.identifier, 0, None)

    def target(self):
        return self.state.current_target[0] if self.state.current_target else None

    def picked(self):
        return [(event.code, event.source) for event in self.state.event_queue]


class ThreatSearchTests(SearchTestCase):
    """Searcher S: bow, R = 576 -> r = 216, keep radius 360; at (0, 0) facing +Y."""

    def searcher(self):
        return unit("S", 0, 0, Side.ENEMY, missile_range=BOW)

    def test_facing_hostile_within_three_eighths_of_range_is_the_threat(self):
        self.make(self.searcher(), unit("E1", 0, 200, facing=256))
        self.call("FindThreatNear")
        self.assertEqual((self.state.threat, self.state.cond_flags, self.state.current_target), ("E1", 1, None))

    def test_nearest_candidate_blind_to_the_searcher_gives_none_without_fallback(self):
        self.make(self.searcher(), unit("E1", 0, 200, facing=0), unit("E2", 0, 210, facing=256))
        self.call("FindThreatNear")
        self.assertEqual((self.state.threat, self.state.cond_flags), (None, 0))

    def test_radius_is_inclusive(self):
        for y, expected in ((216, "E1"), (217, None)):
            with self.subTest(y=y):
                self.make(self.searcher(), unit("E1", 0, y, facing=256))
                self.call("FindThreatNear")
                self.assertEqual(self.state.threat, expected)

    def test_broken_and_hidden_units_are_no_threat(self):
        for flag in ("routing", "hidden"):
            with self.subTest(flag=flag):
                self.make(self.searcher(), unit("E1", 0, 200, facing=256, **{flag: True}))
                self.call("FindThreatNear")
                self.assertIsNone(self.state.threat)

    def test_find_new_threat_reports_only_a_change_and_keeps_the_slot_on_failure(self):
        far = unit("E1", 0, 200, facing=256)
        self.make(self.searcher(), far)
        self.state.threat = "E1"
        self.call("FindNewThreatNear")
        self.assertEqual((self.state.threat, self.state.cond_flags), ("E1", 0))
        far.y = 300
        self.call("FindNewThreatNear")
        self.assertEqual((self.state.threat, self.state.cond_flags), ("E1", 0))

    def test_find_new_threat_takes_a_different_threat(self):
        self.make(self.searcher(), unit("E1", 0, 1000, facing=256), unit("E3", 0, 100, facing=256))
        self.state.threat = "E1"
        self.call("FindNewThreatNear")
        self.assertEqual((self.state.threat, self.state.cond_flags), ("E3", 1))

    def test_keep_threat_is_strict_at_five_eighths(self):
        for y, expected in ((359, "E1"), (360, None)):
            with self.subTest(y=y):
                self.make(self.searcher(), unit("E1", 0, y, facing=256))
                self.state.threat = "E1"
                self.call("KeepThreat")
                self.assertEqual((self.state.threat, bool(self.state.cond_flags)), (expected, expected is not None))


class WeaponTargetSearchTests(SearchTestCase):
    """S: bow R = 576 at (0, 0)."""

    def searcher(self, **extra):
        return unit("S", 0, 0, Side.ENEMY, facing=256, missile_range=BOW, **extra)

    def test_any_range_ignores_facing_and_skips_broken_units(self):
        self.make(self.searcher(), unit("E1", 0, 100, routing=True), unit("E2", 0, 3000))
        self.call("FindTargetAnyRange")
        self.assertEqual((self.target(), self.state.cond_flags), ("E2", 1))

    def test_unit_at_distance_zero_is_skipped_and_the_target_cleared(self):
        self.make(self.searcher(), unit("E1", 0, 0))
        self.state.current_target = ("E1", 0)
        self.call("FindTargetAnyRange")
        self.assertEqual((self.target(), self.state.cond_flags), (None, 0))

    def test_of_class_range_is_inclusive(self):
        for y, expected in ((576, "A"), (577, None)):
            with self.subTest(y=y):
                self.make(self.searcher(), unit("A", 0, y, unit_class=3), unit("I", 0, 100, unit_class=1))
                self.call("FindTargetOfClass", 24)
                self.assertEqual(self.target(), expected)

    def test_of_class_any_range_clears_the_target_when_none(self):
        self.make(self.searcher(), unit("I", 0, 100))
        self.state.current_target = ("I", 0)
        self.call("FindTargetOfClassAnyRange", 32)
        self.assertEqual((self.target(), self.state.cond_flags), (None, 0))

    def test_find_new_target(self):
        e1, e2 = unit("E1", 0, 300), unit("E2", 0, 5000)
        self.make(self.searcher(), e1, e2)
        self.state.current_target = ("E1", 0)
        self.call("FindNewTarget")
        self.assertEqual((self.target(), self.state.cond_flags), ("E1", 0))
        e2.y = 100
        self.call("FindNewTarget")
        self.assertEqual((self.target(), self.state.cond_flags), ("E2", 1))
        e1.y = e2.y = 4000
        self.call("FindNewTarget")
        self.assertEqual((self.target(), self.state.cond_flags), ("E2", 0))

    def test_independent_crowding_check_uses_the_candidate_x_and_searcher_y(self):
        with mock.patch.object(Regiment, "bounding_radius", lambda self: 30.0):
            self.make(self.searcher(independent=True), unit("E", 0, 400), unit("F", 0, 40, Side.ENEMY))
            self.call("FindTargetAnyRange")
            self.assertEqual((self.target(), self.state.cond_flags), (None, 0))
            self.make(self.searcher(independent=True), unit("E", 0, 400), unit("F", 0, 390, Side.ENEMY))
            self.call("FindTargetAnyRange")
            self.assertEqual(self.target(), "E")

    def test_crowding_check_is_skipped_for_a_unit_that_is_not_independent(self):
        with mock.patch.object(Regiment, "bounding_radius", lambda self: 30.0):
            self.make(self.searcher(), unit("E", 0, 400), unit("F", 0, 40, Side.ENEMY))
            self.call("FindTargetAnyRange")
            self.assertEqual(self.target(), "E")


class NearestPickTests(SearchTestCase):
    def test_of_class_picks_the_class_over_a_nearer_unit(self):
        self.make(unit("S", 0, 0, Side.ENEMY), unit("W", 2000, 0, unit_class=5), unit("I", 100, 0))
        self.call("TargetNearestEnemyOfClass", 40)
        self.assertEqual((self.target(), self.state.cond_flags), ("W", 1))

    def test_no_match_keeps_the_target(self):
        self.make(unit("S", 0, 0, Side.ENEMY), unit("I", 100, 0))
        self.state.current_target = ("I", 0)
        self.call("TargetNearestEnemyOfClass", 40)
        self.assertEqual((self.target(), self.state.cond_flags), ("I", 0))

    def test_retarget_reports_only_a_change(self):
        self.make(unit("S", 0, 0, Side.ENEMY), unit("E1", 0, 500), unit("E2", 0, 300))
        self.state.current_target = ("E1", 0)
        self.call("RetargetNearestEnemy")
        self.assertEqual((self.target(), self.state.cond_flags), ("E2", 1))
        self.call("RetargetNearestEnemy")
        self.assertEqual((self.target(), self.state.cond_flags), ("E2", 0))

    def test_retarget_with_only_ineligible_units_keeps_the_target(self):
        self.make(unit("S", 0, 0, Side.ENEMY), unit("E1", 0, 500, routing=True), unit("E2", 0, 300, hidden=True))
        self.state.current_target = ("E1", 0)
        self.call("RetargetNearestEnemy")
        self.assertEqual((self.target(), self.state.cond_flags), ("E1", 0))

    def test_ties_go_to_the_first_in_order(self):
        self.make(unit("S", 0, 0, Side.ENEMY), unit("E1", 300, 0), unit("E2", 0, 300))
        self.call("RetargetNearestEnemy")
        self.assertEqual(self.target(), "E1")


class AttackNearestFamilyTests(SearchTestCase):
    """Searcher S in the enemy army at (0, 0) facing +X."""

    def searcher(self):
        return unit("S", 0, 0, Side.ENEMY, facing=128)

    def test_of_class_queues_an_attack_event_and_leaves_the_target(self):
        self.make(self.searcher(), unit("C1", 0, 800, unit_class=2), unit("C2", 0, 100, unit_class=2, hidden=True),
                  unit("I", 0, 50))
        self.call("AttackNearestEnemyOfClass", 16)
        self.assertEqual((self.picked(), self.state.cond_flags, self.state.current_target), ([(4, "C1")], 1, None))

    def test_refused_in_deployment(self):
        self.make(self.searcher(), unit("C1", 0, 800, unit_class=2), phase="deployment")
        self.call("AttackNearestEnemyOfClass", 16)
        self.assertEqual((self.picked(), self.state.cond_flags), ([], 0))

    def test_axis_key_prefers_the_unit_furthest_towards_plus_x_or_plus_y(self):
        self.make(self.searcher(), unit("A", 300, 0), unit("B", 0, -100), unit("C", -50, -400))
        self.call("AttackNearestEnemyByAxis")
        self.assertEqual(self.picked(), [(4, "A")])
        self.make(self.searcher(), unit("A", 300, 0), unit("D", 0, 600))
        self.call("AttackNearestEnemyByAxis")
        self.assertEqual(self.picked(), [(4, "D")])

    def test_visible_axis_ignores_units_outside_the_view_cone(self):
        self.make(self.searcher(), unit("A", 300, 0), unit("D", 0, 600))
        self.call("AttackNearestVisibleEnemyByAxis")
        self.assertEqual(self.picked(), [(4, "A")])

    def test_ties_go_to_the_last_in_order(self):
        self.make(self.searcher(), unit("P1", 200, 0), unit("P2", 0, 200))
        self.call("AttackNearestEnemyOfClass", 0)
        self.assertEqual(self.picked(), [(4, "P2")])

    def test_main_enemy_skips_the_allied_side(self):
        self.make(self.searcher(), unit("P", 900, 0), unit("L", 100, 0, Side.NEUTRAL))
        self.call("AttackNearestMainEnemy")
        self.assertEqual(self.picked(), [(4, "P")])
        self.make(self.searcher(), unit("L", 100, 0, Side.NEUTRAL))
        self.call("AttackNearestVisibleMainEnemy")
        self.assertEqual((self.picked(), self.state.cond_flags), ([], 0))

    def test_allied_searcher_takes_enemy_army_units_only(self):
        self.make(unit("S", 0, 0, Side.NEUTRAL), unit("P", 100, 0), unit("E", 900, 0, Side.ENEMY))
        self.call("AttackNearestEnemyOfClass", 0)
        self.assertEqual(self.picked(), [(4, "E")])

    def test_player_searcher_also_takes_allied_units(self):
        self.make(unit("S", 0, 0, Side.PLAYER), unit("L", 100, 0, Side.NEUTRAL), unit("E", 900, 0, Side.ENEMY))
        self.call("AttackNearestEnemyOfClass", 0)
        self.assertEqual(self.picked(), [(4, "L")])

    def make_with_building(self, searcher, name, x, y, node=(1000, 1000), **extra):
        self.make(searcher)
        self.battle.script_nodes = [ScriptNode(node[0], node[1])]
        self.battle.buildings = buildings.from_scenery([{"name": name, "x": x, "y": y}])
        self.battle.building_index = {b.identifier: b for b in self.battle.buildings}

    def test_attack_unit_at_node_with_no_building_is_false(self):
        self.make(self.searcher(), unit("P", 0, 0))
        self.battle.script_nodes = [ScriptNode(30, 30)]
        self.call("AttackUnitAtNode", 0)
        self.assertEqual((self.picked(), self.state.cond_flags), ([], 0))

    def test_attack_unit_at_node_queues_attack_event_naming_the_building(self):
        self.make_with_building(self.searcher(), "Farm", 1030, 1000)
        self.call("AttackUnitAtNode", 0)
        self.assertEqual((self.picked(), self.state.cond_flags), ([(4, "building:0")], 1))

    def test_attack_unit_at_node_reach_is_at_least_48_for_a_small_building(self):
        for x, expected in ((1040, True), (1050, False)):
            with self.subTest(x=x):
                self.make_with_building(self.searcher(), "WoodShack", x, 1000)
                self.battle.buildings[0].radius = 20
                self.call("AttackUnitAtNode", 0)
                self.assertEqual(bool(self.state.cond_flags), expected)

    def test_attack_unit_at_node_ignores_regiments_at_the_node(self):
        self.make(self.searcher(), unit("E", 1000, 1000, Side.PLAYER))
        self.battle.script_nodes = [ScriptNode(1000, 1000)]
        self.call("AttackUnitAtNode", 0)
        self.assertEqual(self.state.cond_flags, 0)

    def test_attack_unit_at_node_fails_for_a_held_unit_and_for_a_destroyed_building(self):
        self.make_with_building(self.searcher(), "Farm", 1030, 1000)
        self.s.held = True
        self.call("AttackUnitAtNode", 0)
        self.assertEqual(self.picked(), [])
        self.s.held = False
        self.battle.buildings[0].destroyed = True
        self.call("AttackUnitAtNode", 0)
        self.assertEqual((self.picked(), self.state.cond_flags), ([], 0))

    def test_take_event_target_from_a_building_targets_it_and_aims_at_its_centre(self):
        self.make_with_building(self.searcher(), "Farm", 1030, 1000)
        self.state.current_event = Event(code=0x04, source="building:0")
        self.call("TakeEventTarget")
        self.assertEqual((self.state.current_target, self.state.approach_point, self.state.cond_flags),
                         (("building:0", 0), (1030.0, 1000.0), 1))

    def targeting_building(self, x, y):
        self.make_with_building(unit("S", 0, 0, Side.PLAYER), "Farm", x, y)
        self.battle.regiments["S"].x = self.battle.regiments["S"].y = 0
        self.state.current_target = ("building:0", 0)

    def test_move_to_target_walks_at_the_building_centre(self):
        self.targeting_building(0, 300)
        self.call("MoveToTarget")
        self.assertEqual((self.state.cond_flags, (self.s.target_x, self.s.target_y)), (1, (0.0, 300.0)))

    def test_charge_reach_to_a_building_is_measured_from_its_radius(self):
        # Farm radius 89; infantry reach is 12 x s_rlmv, so a centre 150 away is in reach, 600 away is not.
        for y, expected in ((150, 1), (600, 0)):
            with self.subTest(y=y):
                self.targeting_building(0, y)
                self.call("IfTargetInChargeReach")
                self.assertEqual(self.state.cond_flags, expected)
                self.assertEqual((self.s.target_x, self.s.target_y), (0.0, float(y)))

    def test_charge_target_orders_the_charge_on_a_standing_building_only(self):
        self.targeting_building(0, 300)
        self.call("ChargeTarget")
        self.assertEqual(self.s.attack_target, "building:0")
        self.s.attack_target = None
        self.battle.buildings[0].destroyed = True
        self.call("ChargeTarget")
        self.assertIsNone(self.s.attack_target)


class ReactToThreatTests(SearchTestCase):
    """S independent and idle at (0, 0) facing +Y; threat T at 40 degrees off its facing, score 120."""

    def setup_threat(self, angle_units=57, **threat_extra):
        import math
        angle = angle_units * math.tau / 512
        self.t = unit("T", 300 * math.sin(angle), 300 * math.cos(angle), Side.ENEMY, facing=256, **threat_extra)
        self.make(unit("S", 0, 0, Side.PLAYER, independent=True), self.t)
        self.state.threat, self.state.threat_score = "T", 120.0

    def test_switches_to_a_visible_higher_scoring_threat(self):
        self.setup_threat()
        self.call("ReactToThreat")
        self.assertEqual((self.target(), self.state.threat, self.state.cond_flags), ("T", None, 1))
        self.assertIsNotNone(self.state.approach_point)
        self.assertEqual(self.picked(), [])

    def test_threat_charging_this_unit_queues_you_are_being_charged(self):
        self.setup_threat()
        self.t.attack_target = "S"
        self.call("ReactToThreat")
        self.assertEqual((self.target(), self.state.cond_flags, self.picked()), ("T", 0, [(7, "T")]))

    def test_threat_outside_sixty_degrees_changes_nothing(self):
        self.setup_threat(angle_units=100)  # about 70 degrees
        self.call("ReactToThreat")
        self.assertEqual((self.target(), self.state.threat, self.state.cond_flags), (None, "T", 0))

    def test_equal_score_does_not_switch(self):
        self.setup_threat()
        other = unit("E", 0, 50, Side.ENEMY)
        self.battle.regiments["E"] = other
        self.state.current_target = ("E", 0)
        self.state.threat_range = 100
        with mock.patch.object(interpreter.ScriptInterpreter, "_threat_score", lambda *args: 120.0):
            self.call("ReactToThreat")
        self.assertEqual((self.target(), self.state.cond_flags), ("E", 0))

    def test_in_melee_the_unit_withdraws_and_routs(self):
        self.setup_threat()
        self.s.in_melee = True
        self.call("ReactToThreat")
        self.assertTrue(self.s.routing)
        self.assertEqual((self.target(), self.state.threat, self.state.cond_flags), (None, "T", 0))

    def test_broken_unit_or_fanatic_threat_is_refused(self):
        self.setup_threat(psychology=frozenset({"CantMelee"}))
        self.call("ReactToThreat")
        self.assertEqual(self.state.cond_flags, 0)
        self.setup_threat()
        self.s.routing = True
        self.call("ReactToThreat")
        self.assertEqual((self.target(), self.state.cond_flags), (None, 0))

    def test_approach_point_is_one_footprint_radius_out_on_the_near_side(self):
        with mock.patch.object(Regiment, "bounding_radius", lambda self: 40.0):
            self.make(unit("S", 0, 0, Side.PLAYER, independent=True), unit("T", 0, 300, Side.ENEMY, facing=256))
            self.state.threat, self.state.threat_score = "T", 120.0
            self.call("ReactToThreat")
        x, y = self.state.approach_point
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 260.0)


class ReactEnemySpottedTests(SearchTestCase):
    def test_changes_no_script_state(self):
        self.make(unit("S", 0, 0), unit("E", 0, 100, Side.ENEMY))
        self.state.current_event = Event(code=0x1C, source="E")
        self.state.cond_flags = 1
        self.call("ReactEnemySpotted")
        self.assertEqual((self.state.cond_flags, self.state.current_target, self.state.threat), (1, None, None))


if __name__ == "__main__":
    unittest.main()
