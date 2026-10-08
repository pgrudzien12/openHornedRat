"""Damage of scripted attacks (GitHub issue #169): the squig hopper's landing (notes/script_spawn_move.md 5) and the
contact attacks of nearby chargers on a Behaviour 14 unit (notes/script_behaviours.md 1.6, 1.11)."""

import math
import unittest
from unittest import mock

from tests.script_helpers import FakeDll, word
from whshr import behaviour, combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side

IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


def regiment(identifier, x, y, side, models=10, ranks=2, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=models, ranks=ranks, **extra)


def battle_of(*units, scenery=()):
    battle = Battle(3000, 3000, list(units), seed=1995, script_dll=FakeDll(IDLE), scenery=list(scenery))
    battle.phase = "battle"
    return battle, interpreter.ScriptInterpreter(battle, battle.event_bus, None)


def models_within(unit, point, reach):
    return [i for i, (x, y) in enumerate(unit.model_positions()) if math.hypot(x - point[0], y - point[1]) <= reach]


class SquigLandingTests(unittest.TestCase):
    def setUp(self):
        self.hopper = regiment("H", 1000, 1000, Side.ENEMY, models=1, ranks=1, strength=5, unit_class=1)
        self.victim = regiment("V", 1000, 1014, Side.PLAYER, strength=3, toughness=3, unit_class=1)

    def release(self, battle, interp, counter=4):
        state = battle.event_bus.unit_states["H"]
        state.hop_counter = counter
        state.current_target = ("V", 0)
        interp.op_FanaticRelease(state, None, [word("FanaticRelease")], "H", 0, battle.rng)
        return state

    def test_given_enemy_models_within_reach_when_the_squig_lands_then_they_are_wounded_and_the_counter_holds(self):
        battle, interp = battle_of(self.hopper, self.victim)
        in_reach = models_within(self.victim, (1000, 1000), 12)
        self.assertTrue(0 < len(in_reach) < 10)
        with mock.patch.object(combat, "_d6", return_value=6):
            state = self.release(battle, interp)
        self.assertEqual((self.victim.models, bool(state.cond_flags), state.hop_counter), (10 - len(in_reach), True, 4))

    def test_given_nothing_in_reach_when_the_squig_lands_then_the_counter_drops_and_the_last_miss_is_false(self):
        far = regiment("V", 1000, 1500, Side.PLAYER)
        battle, interp = battle_of(self.hopper, far)
        for counter, expected in ((4, True), (1, False), (0, True)):
            with self.subTest(counter=counter):
                state = self.release(battle, interp, counter)
                self.assertEqual(bool(state.cond_flags), expected)
        self.assertEqual(battle.event_bus.unit_states["H"].hop_counter, 255)  # 0 wrapped to 255

    def test_given_a_failed_wound_roll_then_the_landing_is_a_miss(self):
        battle, interp = battle_of(self.hopper, self.victim)
        with mock.patch.object(combat, "_d6", return_value=1):
            state = self.release(battle, interp, 1)
        self.assertEqual((self.victim.models, bool(state.cond_flags), state.hop_counter), (10, False, 0))

    def test_given_a_rolling_stock_unit_underfoot_then_it_counts_as_a_hit_without_harm(self):
        wagon = regiment("V", 1000, 1010, Side.PLAYER, models=2, ranks=1, unit_class=7)
        battle, interp = battle_of(self.hopper, wagon)
        state = self.release(battle, interp)
        self.assertEqual((bool(state.cond_flags), state.hop_counter, wagon.models), (True, 4, 2))

    def test_given_a_standing_building_under_the_leader_then_it_counts_as_a_hit(self):
        battle, interp = battle_of(self.hopper, regiment("V", 1000, 1500, Side.PLAYER),
                                   scenery=[{"name": "Menhir", "x": 1000, "y": 1005}])
        self.assertEqual(len(battle.buildings), 1)  # Menhir is a building type
        state = self.release(battle, interp)
        self.assertEqual((bool(state.cond_flags), state.hop_counter), (True, 4))

    def test_given_an_active_map_object_under_the_leader_then_it_counts_as_a_hit(self):
        battle, interp = battle_of(self.hopper, regiment("V", 1000, 1500, Side.PLAYER))
        battle.objects.append({"x": 1000, "y": 1005, "radius": 30, "status": ["os_active"]})
        self.assertEqual(battle.buildings, [])
        state = self.release(battle, interp)
        self.assertEqual((bool(state.cond_flags), state.hop_counter), (True, 4))

    def test_given_the_hopper_itself_in_reach_then_it_never_hurts_itself(self):
        battle, interp = battle_of(self.hopper, self.victim)
        with mock.patch.object(combat, "_d6", return_value=6):
            self.release(battle, interp)
        self.assertEqual(self.hopper.models, 1)

    def test_given_no_target_then_event_0x01_is_posted_whatever_the_result(self):
        battle, interp = battle_of(self.hopper, regiment("V", 1000, 1500, Side.PLAYER))
        state = battle.event_bus.unit_states["H"]
        state.hop_counter, state.current_target = 2, None
        interp.op_FanaticRelease(state, None, [word("FanaticRelease")], "H", 0, battle.rng)
        self.assertEqual((state.hop_counter, [event.code for event in state.event_queue]), (1, [0x01]))

    def test_given_an_inactive_map_object_under_the_leader_then_it_is_not_a_hit(self):
        battle, interp = battle_of(self.hopper, regiment("V", 1000, 1500, Side.PLAYER))
        battle.objects.append({"x": 1000, "y": 1000, "radius": 30, "status": ["os_solid"]})
        state = self.release(battle, interp)
        self.assertEqual((bool(state.cond_flags), state.hop_counter), (True, 3))  # a miss: the counter dropped

    def test_given_cavalry_in_reach_then_the_wider_reach_of_18_applies(self):
        cavalry = regiment("V", 1000, 1030, Side.PLAYER, strength=3, toughness=3, unit_class=2)
        battle, interp = battle_of(self.hopper, cavalry)
        wider = models_within(cavalry, (1000, 1000), 18)
        narrower = models_within(cavalry, (1000, 1000), 12)
        self.assertGreater(len(wider), len(narrower))
        with mock.patch.object(combat, "_d6", return_value=6):
            self.release(battle, interp)
        self.assertEqual(cavalry.models, 10 - len(wider))


class ThreatInReachTests(unittest.TestCase):
    """notes/script_behaviours.md 1.6 and the 1.11 vectors for code 14."""

    def setUp(self):
        self.peasant = regiment("S", 1000, 1000, Side.NEUTRAL)
        self.charger = regiment("F", 1000, 1020, Side.NEUTRAL, attack_target="ghost")
        self.battle, self.interp = battle_of(self.peasant, self.charger)
        self.state = self.battle.event_bus.unit_states["S"]
        self.state.threat_range = 160

    def spent(self):
        return self.charger.contact_attack_segment == self.battle.tick_count // combat.SEGMENT_TICKS

    def run_code_14(self):
        self.interp._threat_in_reach(self.peasant, self.state)
        return [event.code for event in self.state.event_queue]

    def test_given_a_friendly_charger_in_range_when_it_wounds_then_its_attacks_are_spent_and_0x03_is_queued(self):
        with mock.patch.object(combat, "_d6", return_value=6):
            codes = self.run_code_14()
        self.assertEqual(codes, [0x03])
        self.assertLess(self.peasant.models, 10)
        self.assertTrue(self.spent())

    def test_given_a_friendly_charger_whose_attacks_wound_nothing_then_there_is_no_0x03(self):
        with mock.patch.object(combat, "_d6", return_value=1):
            codes = self.run_code_14()
        self.assertEqual((codes, self.peasant.models), ([], 10))
        self.assertTrue(self.spent())

    def test_given_spent_attacks_then_a_second_run_in_the_segment_attacks_nothing(self):
        with mock.patch.object(combat, "_d6", return_value=6):
            self.run_code_14()
            models = self.peasant.models
            self.run_code_14()
        self.assertEqual(self.peasant.models, models)

    def test_given_a_unit_that_is_not_charging_or_pursuing_then_it_makes_no_contact_attacks(self):
        self.charger.attack_target = None
        with mock.patch.object(combat, "_d6", return_value=6):
            codes = self.run_code_14()
        self.assertEqual((codes, self.peasant.models), ([], 10))
        self.assertFalse(self.spent())

    def test_given_a_pursuing_unit_then_it_attacks_too(self):
        self.charger.attack_target, self.charger.pursuing = None, True
        with mock.patch.object(combat, "_d6", return_value=6):
            codes = self.run_code_14()
        self.assertEqual(codes, [0x03])

    def test_given_a_charger_out_of_range_then_nothing_happens(self):
        self.charger.y = 1300
        with mock.patch.object(combat, "_d6", return_value=6):
            codes = self.run_code_14()
        self.assertEqual((codes, self.peasant.models), ([], 10))
        self.assertFalse(self.spent())

    def test_given_a_hostile_unit_near_but_no_wound_then_test_two_still_queues_0x03(self):
        self.charger.side = Side.ENEMY
        with mock.patch.object(combat, "_d6", return_value=1):
            codes = self.run_code_14()
        self.assertEqual(codes, [0x03])

    def test_given_a_standing_victim_then_the_battle_log_does_not_call_it_fleeing(self):
        with mock.patch.object(combat, "_d6", return_value=6):
            self.run_code_14()
        texts = [str(event) for event in self.battle.events if event.kind == "contact_attack"]
        self.assertTrue(texts)
        self.assertTrue(all("fleeing" not in text for text in texts))

    def test_given_a_routing_victim_then_the_battle_log_keeps_the_fleeing_wording(self):
        self.peasant.routing = True
        with mock.patch.object(combat, "_d6", return_value=6):
            combat.contact_attack(self.battle, self.charger, self.peasant)
        texts = [str(event) for event in self.battle.events if event.kind == "contact_attack"]
        self.assertTrue(texts)
        self.assertTrue(all("fleeing" in text for text in texts))

    def test_given_spent_contact_attacks_then_the_segment_pass_skips_that_attacker(self):
        routing = regiment("R", 1000, 1010, Side.PLAYER)
        routing.routing = True
        self.charger.side, self.charger.attack_target = Side.ENEMY, "R"
        self.battle.regiments["R"] = routing
        self.charger.contact_attack_segment = self.battle.tick_count // combat.SEGMENT_TICKS
        with mock.patch.object(combat, "_d6", return_value=6):
            combat.resolve_contact_attacks(self.battle)
        self.assertEqual(routing.models, 10)


if __name__ == "__main__":
    unittest.main()
