"""Tests for IfThreatOutweighsWorth and its supporting UnitScore-based threat scoring
(game_rules.md: "worth x (range - d) / round(range / 4)", "unit worth = size x s_pntval x
12 artillery / 8 wizard / 4 monster / 1"), the last gap found in a real, won BF003 playthrough.

This is the actual decision gate documented as behaviour 15 (TrackThreat)'s core logic: "keep the
best threat and attack it when its score exceeds the unit's worth." Confirmed used by Goblin
Wolfriders' real script in the sequence Query 1 / IfThreatOutweighsWorth / SendEventSelfIfTrue /
AttackNearestFlag40Unit.
"""

import unittest
from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class UnitWorthTests(unittest.TestCase):
    def test_default_class_multiplier_is_one(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=10, points=5, hud_class="inf")
        self.assertEqual(interpreter.ScriptInterpreter._unit_worth(regiment), 50)

    def test_artillery_multiplier_is_twelve(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=2, points=10, hud_class="art")
        self.assertEqual(interpreter.ScriptInterpreter._unit_worth(regiment), 2 * 10 * 12)

    def test_wizard_multiplier_is_eight(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=1, points=20, hud_class="wiz")
        self.assertEqual(interpreter.ScriptInterpreter._unit_worth(regiment), 1 * 20 * 8)

    def test_monster_multiplier_is_four(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=1, points=15, hud_class="mon")
        self.assertEqual(interpreter.ScriptInterpreter._unit_worth(regiment), 1 * 15 * 4)

    def test_unknown_class_defaults_to_one(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=3, points=4, hud_class=None)
        self.assertEqual(interpreter.ScriptInterpreter._unit_worth(regiment), 12)


class ThreatScoreTests(unittest.TestCase):
    def setUp(self):
        self.regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=10, points=5, hud_class="inf")
        self.battle = Battle(2000, 2000, [self.regiment], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_same_side_scores_zero(self):
        friend = Regiment("friend", "F", 10, 0, 0, Side.ENEMY, models=10, points=5, hud_class="inf")
        self.assertEqual(self.interp._threat_score(self.regiment, friend, threat_range=100), 0.0)

    def test_routing_enemy_scores_zero(self):
        enemy = Regiment("enemy", "E", 10, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        enemy.routing = True
        self.assertEqual(self.interp._threat_score(self.regiment, enemy, threat_range=100), 0.0)

    def test_cant_melee_enemy_scores_zero(self):
        enemy = Regiment("enemy", "E", 10, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf",
                          psychology=frozenset({"CantMelee"}))
        self.assertEqual(self.interp._threat_score(self.regiment, enemy, threat_range=100), 0.0)

    def test_beyond_range_scores_zero(self):
        enemy = Regiment("enemy", "E", 500, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        self.assertEqual(self.interp._threat_score(self.regiment, enemy, threat_range=100), 0.0)

    def test_a_valid_enemy_in_range_scores_positive(self):
        enemy = Regiment("enemy", "E", 50, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        score = self.interp._threat_score(self.regiment, enemy, threat_range=100)
        self.assertGreater(score, 0.0)

    def test_closer_enemy_scores_higher(self):
        near = Regiment("near", "N", 20, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        far = Regiment("far", "Fr", 80, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        near_score = self.interp._threat_score(self.regiment, near, threat_range=100)
        far_score = self.interp._threat_score(self.regiment, far, threat_range=100)
        self.assertGreater(near_score, far_score)

    def test_a_target_that_is_already_charging_this_unit_scores_higher(self):
        enemy = Regiment("enemy", "E", 50, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        baseline = self.interp._threat_score(self.regiment, enemy, threat_range=100)
        enemy.attack_target = "r"
        boosted = self.interp._threat_score(self.regiment, enemy, threat_range=100)
        self.assertEqual(boosted, baseline * 4.0)

    def test_zero_threat_range_never_divides_by_zero(self):
        enemy = Regiment("enemy", "E", 1, 0, 0, Side.PLAYER, models=10, points=5, hud_class="inf")
        self.assertEqual(self.interp._threat_score(self.regiment, enemy, threat_range=0), 0.0)


class IfThreatOutweighsWorthTests(unittest.TestCase):
    def setUp(self):
        self.regiment = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=5, points=5, hud_class="inf")

    def _battle_with(self, *extra_regiments):
        battle = Battle(2000, 2000, [self.regiment, *extra_regiments], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        return battle, interp

    def test_no_threat_range_set_means_no_threat(self):
        battle, interp = self._battle_with(
            Regiment("enemy", "E", 10, 0, 0, Side.PLAYER, models=20, points=20, hud_class="inf"))
        state = battle.event_bus.unit_states["r"]
        state.threat_range = 0

        interp.op_IfThreatOutweighsWorth(state, None, [], "r", 0, None)

        self.assertEqual(state.cond_flags, 0)

    def test_no_enemies_means_no_threat(self):
        battle, interp = self._battle_with()
        state = battle.event_bus.unit_states["r"]
        state.threat_range = 100

        interp.op_IfThreatOutweighsWorth(state, None, [], "r", 0, None)

        self.assertEqual(state.cond_flags, 0)

    def test_a_much_bigger_nearby_enemy_outweighs_a_small_units_worth(self):
        # r's own worth: 5 models x 5 points x 1 = 25. A big, close, valuable enemy should outscore it.
        battle, interp = self._battle_with(
            Regiment("enemy", "E", 10, 0, 0, Side.PLAYER, models=30, points=30, hud_class="inf"))
        state = battle.event_bus.unit_states["r"]
        state.threat_range = 200

        interp.op_IfThreatOutweighsWorth(state, None, [], "r", 0, None)

        self.assertEqual(state.cond_flags, 1)

    def test_a_tiny_distant_enemy_does_not_outweigh_a_valuable_units_worth(self):
        # r's worth here: 5 models x 5 points x 1 = 25. A single weak model near the edge of a wide
        # threat range should not be worth engaging.
        battle, interp = self._battle_with(
            Regiment("weak", "W", 190, 0, 0, Side.PLAYER, models=1, points=1, hud_class="inf"))
        state = battle.event_bus.unit_states["r"]
        state.threat_range = 200

        interp.op_IfThreatOutweighsWorth(state, None, [], "r", 0, None)

        self.assertEqual(state.cond_flags, 0)


if __name__ == "__main__":
    unittest.main()
