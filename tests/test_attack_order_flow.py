"""The player's Attack order with scripts running (notes/attack_order_flow.md): the order is event 0x04, the handler
takes the target and starts the approach walk (an ordinary follow-unit move, not a charge), the charge starts only when
the charge-reach test passes, and the charge itself is a straight run. Synthetic scripts in the report's shape."""

import unittest

from whshr import behaviour
from whshr.engine import Battle, Regiment
from whshr.rules import Side
from tests.script_helpers import FakeDll, word

MAIN, HANDLER, APPROACH, CHARGE = 100, 101, 105, 160
SCRIPTS = {
    MAIN: [word("Wait"), behaviour.END],
    HANDLER: [word("GetEvent"), word("TakeEventTarget"), word("IfSwitchScriptHigh"), APPROACH,
              word("ConsumeEvent"), word("ReturnInterrupt"), behaviour.END],
    APPROACH: [word("MoveToTarget"), word("PushPC"), word("SetWait"), 10, word("IfTargetInChargeReach"),
               word("IfGotoScript"), CHARGE, word("Wait"), word("Loop"), behaviour.END],
    CHARGE: [word("ChargeTarget"), word("PushPC"), word("Yield"), word("Loop"), behaviour.END],
}


def unit(identifier, x, y, side, direction=128, **kwargs):
    return Regiment(identifier, identifier, x, y, direction, side, models=kwargs.pop("models", 8),
                    ranks=kwargs.pop("ranks", 2), **kwargs)


class AttackOrderFlowTests(unittest.TestCase):
    def setUp(self):
        self.player = unit("player", 100, 500, Side.PLAYER)
        self.enemy = unit("enemy", 400, 500, Side.ENEMY, direction=384)
        self.battle = Battle(1000, 1000, [self.player, self.enemy], seed=1995, script_dll=FakeDll(SCRIPTS),
                             script_ids={"player": MAIN, "enemy": MAIN})
        self.state = self.battle.event_bus.unit_states["player"]
        self.state.interrupt_script = HANDLER

    def test_given_an_attack_order_then_the_unit_walks_toward_the_target_without_charging(self):
        self.battle.order_attack("player", "enemy")
        self.assertIsNone(self.player.attack_target)  # the order is only an event so far
        self.battle.tick()
        self.assertEqual(self.state.script_id, APPROACH)
        self.assertEqual(self.state.current_target[0], "enemy")
        self.assertTrue(self.player.moving)
        self.assertIsNone(self.player.attack_target)

    def test_given_the_approach_reaches_charge_reach_then_the_charge_starts(self):
        self.battle.order_attack("player", "enemy")
        for _ in range(200):
            self.battle.tick()
            if self.player.attack_target is not None:
                break
        self.assertEqual(self.player.attack_target, "enemy")
        self.assertEqual(self.state.script_id, CHARGE)
        self.assertLess(self.enemy.x - self.player.x, 300)  # it walked closer first

    def test_given_a_charging_unit_when_attack_is_clicked_again_then_the_order_is_dropped(self):
        self.player.attack_target = "enemy"
        self.battle.order_attack("player", "enemy")
        self.assertEqual(len(self.state.event_queue), 0)

    def test_given_a_friendly_unit_not_in_the_fight_on_the_line_then_the_approach_steers_round_it(self):
        friend = unit("friend", 200, 500, Side.PLAYER, direction=128)
        self.battle = Battle(1000, 1000, [self.player, friend, self.enemy], seed=1995, script_dll=FakeDll(SCRIPTS),
                             script_ids={"player": MAIN, "friend": MAIN, "enemy": MAIN})
        self.state = self.battle.event_bus.unit_states["player"]
        self.state.interrupt_script = HANDLER
        self.battle.order_attack("player", "enemy")
        steered = False
        for _ in range(20):
            self.battle.tick()
            steered = steered or self.player.avoid_target is not None
        self.assertTrue(steered)


class ApproachObstacleTests(unittest.TestCase):
    """notes/attack_order_flow.md 2: the approach route ignores the target and every unit on its combat grid."""

    def test_given_units_fighting_the_target_then_they_are_not_route_obstacles_but_other_units_are(self):
        player = unit("player", 100, 500, Side.PLAYER)
        enemy = unit("enemy", 400, 500, Side.ENEMY, direction=384)
        friend = unit("friend", 386, 500, Side.PLAYER, direction=128)
        bystander = unit("bystander", 200, 600, Side.PLAYER)
        battle = Battle(1000, 1000, [player, friend, enemy, bystander], seed=1995)
        battle.order_attack("friend", "enemy")
        for _ in range(30):
            battle.tick()
            if friend.in_melee:
                break
        self.assertTrue(friend.in_melee)
        self.assertEqual(friend.melee_group, enemy.melee_group)
        player.route_follows_unit = True
        battle.event_bus.unit_states["player"].current_target = ("enemy", 0)
        _, units = battle._route_footprints(player, ("move", (enemy.x, enemy.y)))
        self.assertEqual(sorted(other.identifier for other in units.values()), ["bystander"])


class StraightChargeRunTests(unittest.TestCase):
    def test_given_a_charge_with_a_friendly_unit_on_the_line_then_it_does_not_steer(self):
        player = unit("player", 100, 500, Side.PLAYER)
        friend = unit("friend", 160, 500, Side.PLAYER, direction=128)
        enemy = unit("enemy", 300, 500, Side.ENEMY, direction=384)
        battle = Battle(1000, 1000, [player, friend, enemy], seed=1995)
        battle.order_attack("player", "enemy")  # no scripts: the order charges directly
        for _ in range(10):
            battle.tick()
            self.assertIsNone(player.avoid_target)
            self.assertEqual(player.route_pause_ticks, 0)


if __name__ == "__main__":
    unittest.main()
