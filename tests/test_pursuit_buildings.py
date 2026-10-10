"""Pursuit and buildings (notes/bf003_playtest_fireball_grid_pursuit.md 5): a pursuer is not charging; touching a
building only pushes it clear, with no contact event and no latch, and later move orders are obeyed."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side

IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]
HOUSE = {"name": "WoodShack", "x": 1000, "y": 1030}


def make(scripted):
    cav = Regiment("cav", "Cavalry", 1000, 1000, 0, Side.PLAYER, models=16, ranks=4, points=10)
    fug = Regiment("fug", "Fugitives", 1000, 1500, 0, Side.ENEMY, models=8, ranks=2, routing=True)
    battle = Battle(3000, 3000, [cav, fug], seed=1995, script_dll=FakeDll(IDLE) if scripted else None,
                    scenery=[HOUSE, {"name": "Farm", "x": 2500, "y": 2500}])
    battle.phase = "battle"
    if scripted:
        interpreter.ScriptInterpreter(battle, battle.event_bus, None)
    return battle, cav, fug


class PursuerAndBuildingTests(unittest.TestCase):
    def test_a_pursuer_overlapping_a_house_is_pushed_clear_and_keeps_pursuing(self):
        for scripted in (False, True):
            battle, cav, _ = make(scripted)
            cav.attack_target, cav.pursuing = "fug", True
            cav.collision_recheck = True
            self.assertTrue(battle.overlaps_building(cav))
            battle._correct_buildings(cav)
            self.assertFalse(battle.overlaps_building(cav))
            self.assertEqual((cav.pursuing, cav.attack_target), (True, "fug"))
            if scripted:
                state = battle.event_bus.unit_states["cav"]
                self.assertEqual([e.code for e in state.event_queue], [])
                self.assertFalse(state.contact_latch)

    def test_a_pursuer_is_not_charging_but_an_attack_order_and_a_free_charge_are(self):
        _, cav, _ = make(False)
        cav.attack_target = "fug"
        self.assertTrue(cav.charging)
        cav.pursuing = True
        self.assertFalse(cav.charging)
        cav.attack_target, cav.pursuing, cav.free_charging = None, False, True
        self.assertTrue(cav.charging)

    def test_a_move_order_after_the_push_is_obeyed(self):
        battle, cav, _ = make(True)
        cav.attack_target, cav.pursuing = "fug", True
        cav.collision_recheck = True
        battle._correct_buildings(cav)
        cav.pursuing, cav.attack_target = False, None  # the pursuit ends by its own rules
        battle.order_move("cav", 1000, 700)
        start = (cav.x, cav.y)
        for _ in range(20):
            battle.tick()
        self.assertFalse(battle.event_bus.unit_states["cav"].contact_latch)
        self.assertNotEqual((cav.x, cav.y), start)

    def test_a_real_charge_into_a_non_target_house_still_gets_contact(self):
        battle, cav, _ = make(True)
        cav.attack_target = cav.charge_started_target = "fug"
        cav.collision_recheck = True
        before = (cav.x, cav.y)
        battle._correct_buildings(cav)
        state = battle.event_bus.unit_states["cav"]
        self.assertEqual([e.code for e in state.event_queue], [0x0B])
        self.assertEqual((cav.x, cav.y), before)

    def test_a_real_charge_without_scripts_into_a_non_target_house_still_ends(self):
        battle, cav, _ = make(False)
        cav.attack_target = cav.charge_started_target = "fug"
        battle._correct_buildings(cav)
        self.assertIsNone(cav.attack_target)


if __name__ == "__main__":
    unittest.main()
