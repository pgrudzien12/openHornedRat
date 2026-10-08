"""The player's Attack order with scripts running (notes/attack_order_flow.md): the order is event 0x04, the handler
takes the target and starts the approach walk (an ordinary follow-unit move, not a charge), the charge starts only when
the charge-reach test passes, and the charge itself is a straight run. Synthetic scripts in the report's shape."""

import unittest
from unittest import mock

from whshr import behaviour, buildings, interpreter
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


class AttackOrderGateAndHandOverTests(unittest.TestCase):
    """notes/attack_order_flow.md 1 and 3: the order gate, the hand-over to the straight run, and the snap heading."""

    def run_order(self, battle, player):
        """Order the attack and run to the first movement update; return the identifiers of the facing-changing snaps."""
        snaps = []
        original = Battle._snap_order_turn

        def spy(regiment, goal):
            before = regiment.direction
            original(regiment, goal)
            if regiment.direction != before:
                snaps.append(regiment.identifier)

        with mock.patch.object(Battle, "_snap_order_turn", staticmethod(spy)):
            battle.order_attack("player", "enemy")
            for _ in range(5):
                battle.tick()
                if player.turn_order_key is not None:
                    break
        return snaps

    def battle(self, *regiments):
        battle = Battle(1000, 1000, list(regiments), seed=1995, script_dll=FakeDll(SCRIPTS),
                        script_ids={r.identifier: MAIN for r in regiments})
        battle.event_bus.unit_states["player"].interrupt_script = HANDLER
        return battle

    def test_given_a_straight_ahead_charge_or_melee_then_an_attack_click_is_dropped(self):
        for state in ("free_charging", "in_melee"):
            with self.subTest(state=state):
                player = unit("player", 100, 500, Side.PLAYER)
                battle = self.battle(player, unit("enemy", 400, 500, Side.ENEMY, direction=384))
                setattr(player, state, True)
                battle.order_attack("player", "enemy")
                self.assertEqual(len(battle.event_bus.unit_states["player"].event_queue), 0)

    def test_given_the_charge_takes_over_then_no_approach_route_is_left(self):
        player = unit("player", 100, 500, Side.PLAYER)
        battle = self.battle(player, unit("enemy", 400, 500, Side.ENEMY, direction=384))
        battle.order_attack("player", "enemy")
        for _ in range(200):
            battle.tick()
            if player.attack_target is not None:
                break
        self.assertEqual(player.attack_target, "enemy")
        self.assertIsNone(player.target_x)
        self.assertEqual(player.waypoints, [])
        self.assertIsNone(player.avoid_target)

    def test_given_a_steering_first_plan_then_the_move_start_snap_uses_the_steer_heading(self):
        # Facing 0, target at bearing about 94: a turn under 97 alone would not snap. A friend just left of that line
        # (bearing about 80) makes the first plan steer right to about 134, a turn of 97-192, so the unit snaps 90
        # degrees to 128.
        player = unit("player", 500, 500, Side.PLAYER, direction=0)
        enemy = unit("enemy", 722, 612, Side.ENEMY, direction=384)
        friend = unit("friend", 566, 544, Side.PLAYER, direction=0)
        snaps = self.run_order(self.battle(player, enemy, friend), player)
        self.assertIsNotNone(player.avoid_target)
        self.assertEqual(snaps, ["player"])  # exactly once
        self.assertTrue(120 <= player.direction <= 140, player.direction)  # snapped to 128, then wheeling on

    def test_given_a_raw_bearing_that_would_snap_but_a_steer_heading_that_does_not_then_there_is_no_snap(self):
        # Target at bearing about 100 (a turn that would snap 90 degrees); a friend just right of the line (bearing
        # about 110) makes the first plan steer left (about 20-60), so the unit must not snap at all, not even a snap
        # toward the raw bearing that the first update then snaps back.
        player = unit("player", 500, 500, Side.PLAYER, direction=0)
        enemy = unit("enemy", 735, 584, Side.ENEMY, direction=384)
        friend = unit("friend", 578, 518, Side.PLAYER, direction=0)
        snaps = self.run_order(self.battle(player, enemy, friend), player)
        self.assertIsNotNone(player.avoid_target)
        self.assertEqual(snaps, [])
        self.assertLess(player.direction, 90)


class ChargeStartCleanupTests(unittest.TestCase):
    """notes/attack_order_flow.md 1: every charge is a straight run; it keeps no route pause or approach route."""

    def test_given_a_route_pause_when_a_straight_ahead_charge_is_ordered_then_the_pause_ends(self):
        player = unit("player", 100, 500, Side.PLAYER)
        battle = Battle(1000, 1000, [player], seed=1995)  # no scripts: the order charges directly
        player.route_pause_ticks = 40
        battle.order_charge_forward("player")
        self.assertTrue(player.free_charging)
        self.assertEqual(player.route_pause_ticks, 0)

    def test_given_a_building_target_when_the_charge_starts_then_no_approach_route_or_pause_is_left(self):
        player = unit("player", 100, 500, Side.PLAYER)
        battle = Battle(1000, 1000, [player], seed=1995, script_dll=FakeDll(SCRIPTS), script_ids={"player": MAIN})
        battle.buildings = buildings.from_scenery([{"name": "Farm", "x": 300, "y": 500}])
        battle.building_index = {b.identifier: b for b in battle.buildings}
        state = battle.event_bus.unit_states["player"]
        state.current_target = (battle.buildings[0].identifier, 0)
        player.target_x, player.target_y, player.avoid_target, player.route_pause_ticks = 300, 500, (150, 520), 20
        battle.interpreter.op_ChargeTarget(state, None, [], "player", 0, battle.rng)
        self.assertEqual(player.attack_target, battle.buildings[0].identifier)
        self.assertEqual((player.target_x, player.avoid_target, player.route_pause_ticks), (None, None, 0))


class HighPrioritySwitchLockTests(unittest.TestCase):
    """notes/script_grid_events.md 1: only an IfSwitchScriptHigh request locks the pending switch."""

    def test_given_a_pending_high_priority_switch_then_a_later_normal_switch_does_not_replace_it(self):
        player = unit("player", 100, 500, Side.PLAYER)
        battle = Battle(1000, 1000, [player], seed=1995, script_dll=FakeDll(SCRIPTS), script_ids={"player": MAIN})
        state = battle.event_bus.unit_states["player"]
        battle.interpreter.op_IfSwitchScriptHigh(state, APPROACH, [], "player", 0, battle.rng)
        battle.interpreter.op_SwitchScript(state, 163, [], "player", 0, battle.rng)
        self.assertEqual((state.pending_switch, state.pending_switch_high), (APPROACH, True))

    def test_given_a_pending_normal_switch_then_a_later_switch_still_replaces_it(self):
        player = unit("player", 100, 500, Side.PLAYER)
        battle = Battle(1000, 1000, [player], seed=1995, script_dll=FakeDll(SCRIPTS), script_ids={"player": MAIN})
        state = battle.event_bus.unit_states["player"]
        battle.interpreter.op_SwitchScript(state, 163, [], "player", 0, battle.rng)
        battle.interpreter.op_SwitchScript(state, APPROACH, [], "player", 0, battle.rng)
        self.assertEqual(state.pending_switch, APPROACH)


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
