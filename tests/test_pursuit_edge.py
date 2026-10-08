"""Pursuit and the map edge (notes/pursuit_map_edge.md): the edge correction only pushes a pursuer, and the
once-per-segment pursuit update stops it at the edge, when its target is gone or when its chase budget runs out.
Vectors follow section 7 with the BattleEdge's east side at x = 1160."""

import math
import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour
from whshr.engine import Battle, Regiment
from whshr.rules import Side

EDGE = {"status": ["bnd_ACTIVE", "bnd_BATTLEEDGE"],
        "lines": [[0, 0, 1160, 0], [1160, 0, 1160, 2000], [1160, 2000, 0, 2000], [0, 2000, 0, 0]]}
IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


def pursuer_and_fugitive(front_x, scripted=False):
    cavalry = Regiment("cav", "Cavalry", front_x, 1130, 128, Side.PLAYER, models=8, ranks=2)
    fugitive = Regiment("fug", "Fugitives", front_x + 120, 1130, 128, Side.ENEMY, models=8, ranks=2, routing=True)
    battle = Battle(2000, 2000, [cavalry, fugitive], seed=1995, boundaries=[EDGE],
                    script_dll=FakeDll(IDLE) if scripted else None)
    battle.phase = "battle"
    cavalry.attack_target, cavalry.pursuing = "fug", True
    return battle, cavalry, fugitive


class SegmentUpdateTests(unittest.TestCase):
    def test_probe_inside_the_edge_keeps_pursuing(self):
        battle, cavalry, _ = pursuer_and_fugitive(1120)
        radius = int(cavalry.bounding_radius())
        cavalry.x = 1158 - radius  # probe at x 1158: inside
        battle._update_pursuits()
        self.assertTrue(cavalry.pursuing)
        self.assertEqual(cavalry.attack_target, "fug")

    def test_probe_outside_the_edge_stops_the_pursuit_and_re_forms(self):
        battle, cavalry, _ = pursuer_and_fugitive(1120)
        cavalry.x = 1165 - int(cavalry.bounding_radius())  # probe at x 1165: outside
        battle._update_pursuits()
        self.assertEqual((cavalry.pursuing, cavalry.attack_target), (False, None))
        self.assertTrue(cavalry.reforming)

    def test_scripted_pursuer_gets_the_stop_pursuing_event(self):
        battle, cavalry, _ = pursuer_and_fugitive(1120, scripted=True)
        cavalry.x = 1165 - int(cavalry.bounding_radius())
        battle._update_pursuits()
        self.assertEqual([e.code for e in battle.event_bus.unit_states["cav"].event_queue], [0x10])
        self.assertTrue(cavalry.pursuing)  # its library handler stops it (React 17, re-form)

    def test_a_target_no_longer_routing_stops_the_pursuit(self):
        battle, cavalry, fugitive = pursuer_and_fugitive(900)
        fugitive.routing = False  # rallied
        battle._update_pursuits()
        self.assertFalse(cavalry.pursuing)

    def test_a_battle_without_battle_edge_stops_at_the_first_probe(self):
        cavalry = Regiment("cav", "Cavalry", 500, 500, 128, Side.PLAYER, models=8, ranks=2)
        fugitive = Regiment("fug", "Fugitives", 600, 500, 128, Side.ENEMY, models=8, ranks=2, routing=True)
        battle = Battle(2000, 2000, [cavalry, fugitive], seed=1995)
        cavalry.attack_target, cavalry.pursuing = "fug", True
        battle._update_pursuits()
        self.assertFalse(cavalry.pursuing)

    def test_chase_budget_runs_out_when_the_gap_does_not_close(self):
        battle, cavalry, _ = pursuer_and_fugitive(900)
        battle._update_pursuits()  # first check: budget min(2 x 120, 120) = 120
        self.assertEqual(cavalry.pursuit_budget, 120)
        for _ in range(29):  # the gap stays 120: -4 per segment
            battle._update_pursuits()
        self.assertTrue(cavalry.pursuing)
        battle._update_pursuits()
        self.assertFalse(cavalry.pursuing)

    def test_always_pursue_ignores_the_budget(self):
        battle, cavalry, _ = pursuer_and_fugitive(900)
        cavalry.psychology = frozenset({"AlwaysPursue"})
        for _ in range(40):
            battle._update_pursuits()
        self.assertTrue(cavalry.pursuing)


class EdgeCorrectionTests(unittest.TestCase):
    def test_correction_only_pushes_a_pursuer(self):
        battle, cavalry, _ = pursuer_and_fugitive(1180)
        centre_before = battle.formation_centre(cavalry)[0]
        battle._correct_boundaries(cavalry)
        self.assertLess(battle.formation_centre(cavalry)[0], centre_before)
        self.assertEqual((cavalry.pursuing, cavalry.attack_target), (True, "fug"))

    def test_correction_ends_a_charge(self):
        battle, cavalry, _ = pursuer_and_fugitive(1180)
        cavalry.pursuing = False
        cavalry.charge_started_target = "fug"
        battle._correct_boundaries(cavalry)
        self.assertIsNone(cavalry.attack_target)


class OrderGateTests(unittest.TestCase):
    def test_orders_are_ignored_while_pursuing(self):
        battle, cavalry, _ = pursuer_and_fugitive(900)
        for order in (lambda: battle.order_move("cav", 500, 1130), lambda: battle.order_halt("cav"),
                      lambda: battle.order_attack("cav", "fug")):
            with self.assertRaises(ValueError):
                order()
        self.assertEqual((cavalry.pursuing, cavalry.attack_target), (True, "fug"))

    def test_after_the_pursuit_a_unit_just_outside_the_edge_accepts_a_move(self):
        battle, cavalry, _ = pursuer_and_fugitive(1161)
        cavalry.pursuing, cavalry.attack_target = False, None
        battle.order_move("cav", 900, 1130)
        for _ in range(20):
            battle.tick()
        self.assertLess(cavalry.x, 1150)
        self.assertTrue(math.isfinite(cavalry.y))


if __name__ == "__main__":
    unittest.main()


class PursuitStepTests(unittest.TestCase):
    """game_rules.md "Unit speed" / R39: a pursuer moves at the pursuit step, min(24 * s_rlmv, 10 * distance) / 256
    world units per tick -- at most 1.5 * s_rlmv / 16, the fugitive's own factor, not the charge speed."""

    def _pursuer(self, gap):
        cavalry = Regiment("cav", "Cavalry", 300, 300, 128, Side.PLAYER, models=8, ranks=2,
                           speed_per_tick=20 * 1.8 / 16)  # s_rlmv 20
        fugitive = Regiment("fug", "Fugitives", 300 + gap, 300, 128, Side.ENEMY, models=8, ranks=2, routing=True)
        battle = Battle(2000, 2000, [cavalry, fugitive], seed=1995)
        battle.phase = "battle"
        battle.tick_count = 1  # off the segment boundary
        cavalry.attack_target, cavalry.pursuing = "fug", True
        cavalry.charge_started_target = "fug"
        return battle, cavalry

    def test_given_a_distant_fugitive_when_pursued_then_the_pursuer_moves_1_5_s_rlmv_over_16(self):
        battle, cavalry = self._pursuer(200)

        battle.tick()

        self.assertAlmostEqual(cavalry.x - 300, 1.5 * 20 / 16, places=5)

    def test_given_a_close_fugitive_when_pursued_then_the_step_is_ten_times_the_distance_over_256(self):
        battle, cavalry = self._pursuer(20)

        battle.tick()

        self.assertAlmostEqual(cavalry.x - 300, 10 * 20 / 256, places=5)
