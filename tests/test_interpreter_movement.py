"""Movement, facing and charge-reach opcodes (notes/movement_formation.md Part A, target_queries.md 5).

Vectors are the reports' before/instruction/after tables. Facing 0 = +Y, 128 = +X.
"""

import unittest
import unittest.mock

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import MOVING_FREELY_K, Battle, Regiment
from whshr.rules import Side


def speed_for(s_rlmv):
    return s_rlmv * MOVING_FREELY_K / 16


class MovementTestCase(unittest.TestCase):
    def build(self, unit_at=(0, 0), facing=128, target_at=(300, 0), target_facing=0, s_rlmv=11,
              unit_models=1, unit_ranks=1, target_models=1, target_ranks=1, target_class=None, with_target=True):
        self.unit = Regiment("u", "U", unit_at[0], unit_at[1], facing, Side.ENEMY, models=unit_models, ranks=unit_ranks)
        self.unit.speed_per_tick = speed_for(s_rlmv)
        regiments = [self.unit]
        if with_target:
            self.target = Regiment("x", "X", target_at[0], target_at[1], target_facing, Side.PLAYER,
                                   models=target_models, ranks=target_ranks)
            self.target.hud_class = target_class
            regiments.append(self.target)
        self.battle = Battle(3000, 3000, regiments, seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["u"]
        self.state.current_target = ("x", 0) if with_target else None

    def put_target_centre_at(self, x, y):
        """Place the target so that its object (block) centre is exactly (x, y)."""
        cx, cy = self.battle.formation_centre(self.target)
        self.target.x += x - cx
        self.target.y += y - cy

    def op(self, name, operand=None):
        getattr(self.interp, "op_" + name)(self.state, operand, [], "u", 0, None)
        return bool(self.state.cond_flags)


class MoveToTargetTests(MovementTestCase):
    def test_reform_block_then_move_to_target_in_one_script_update(self):
        # Library script 159 uses this sequence when a Wolfrider selects infantry.
        self.build(unit_at=(838, 1190), facing=296, target_at=(827, 985),
                   target_facing=472, s_rlmv=20, unit_models=12, unit_ranks=3,
                   target_models=16, target_ranks=4)
        self.state.script_dll = FakeDll([word("ReformBlock"), word("MoveToTarget"),
                                         word("Yield"), behaviour.END])
        self.interp.run("u", self.state, 0, self.battle.rng)

        self.assertTrue(self.state.cond_flags)
        self.assertIsNotNone(self.unit.target_x)
        self.assertTrue(self.unit.reforming)

    def test_wolfriders_charge_infantry_after_moving_reform(self):
        # The BF003 library attack path: walk, wait for the re-form, test charge reach.
        self.build(unit_at=(838, 1190), facing=296, target_at=(827, 985),
                   target_facing=472, s_rlmv=20, unit_models=12, unit_ranks=3,
                   target_models=16, target_ranks=4)
        scripts = {
            159: [word("ReformBlock"), word("MoveToTarget"), word("Yield"),
                  word("WaitWhileUnitFlags"), 8, word("PushPC"), word("SetWait"), 10,
                  word("IfTargetInChargeReach"), word("IfGotoScript"), 160,
                  word("Wait"), word("Loop"), behaviour.END],
            160: [word("ChargeTarget"), word("Yield"), behaviour.END],
        }
        self.state.script_id = 159
        self.state.script_dll = FakeDll(scripts)
        self.battle.interpreter = self.interp

        for _ in range(80):
            self.battle.tick()
            if self.unit.attack_target == self.target.identifier:
                break

        self.assertEqual(self.unit.attack_target, self.target.identifier)
        self.assertEqual(self.state.script_id, 160)

    def test_walks_to_the_targets_object_centre(self):
        self.build()
        self.assertTrue(self.op("MoveToTarget"))
        self.assertEqual((self.unit.target_x, self.unit.target_y), (300, 0))

    def test_unit_at_rest_snaps_a_right_angle_towards_the_target(self):
        self.build(facing=0, unit_models=4, unit_ranks=2)
        self.assertTrue(self.op("MoveToTarget"))
        self.assertEqual(self.unit.direction, 128)

    def test_refused_while_reforming_or_without_a_target(self):
        self.build()
        self.unit.reforming = True
        self.assertFalse(self.op("MoveToTarget"))
        self.assertIsNone(self.unit.target_x)
        self.build(with_target=False)
        self.assertFalse(self.op("MoveToTarget"))

    def test_the_destination_does_not_track_a_moving_target(self):
        self.build()
        self.op("MoveToTarget")
        self.target.x = 900
        self.assertEqual(self.unit.target_x, 300)

    def test_refresh_route_is_a_no_op_that_keeps_the_condition(self):
        self.build()
        self.op("MoveToTarget")
        self.state.cond_flags = True
        self.target.x = 900
        self.assertTrue(self.op("RefreshRouteToTarget"))
        self.assertEqual(self.unit.target_x, 300)


class HaltedSignalTests(MovementTestCase):
    def test_idle_unit_is_halted_and_moving_unit_is_not(self):
        self.build()
        self.interp._mirror_engine_flags("u", self.state)
        self.assertTrue(self.state.unit_flags & interpreter.ARRIVED_FLAG)
        self.op("MoveToTarget")
        self.interp._mirror_engine_flags("u", self.state)
        self.assertFalse(self.state.unit_flags & interpreter.ARRIVED_FLAG)
        self.unit.target_x = self.unit.target_y = None
        self.interp._mirror_engine_flags("u", self.state)
        self.assertTrue(self.state.unit_flags & interpreter.ARRIVED_FLAG)


class TurnTests(MovementTestCase):
    def test_turn_to_face_target_vectors(self):
        self.build(facing=0, target_at=(100, 10))  # bearing 119: far outside 16
        self.unit.target_x, self.unit.target_y = 50.0, 50.0
        self.assertTrue(self.op("TurnToFaceTarget"))
        self.assertIsNone(self.unit.target_x)      # a turn order stops the unit
        self.assertIsNotNone(self.unit.turn_order_key)

    def test_turn_to_face_target_is_false_within_16(self):
        self.build(facing=0, target_at=(10, 100))  # bearing 3
        self.assertFalse(self.op("TurnToFaceTarget"))
        self.assertIsNone(self.unit.turn_order_key)

    def test_quarter_turn_clockwise_vector(self):
        self.build(facing=0, target_at=(100, 10), unit_models=20, unit_ranks=4)  # 5 wide x 4 deep
        self.assertTrue(self.op("QuarterTurnToTarget"))
        self.assertEqual(self.unit.direction, 128)
        self.assertEqual((round(self.unit.x), round(self.unit.y)), (24, -18))
        self.assertEqual(self.unit.ranks, 5)

    def test_quarter_turn_anticlockwise_vector(self):
        self.build(facing=0, target_at=(-100, 10), unit_models=20, unit_ranks=4)
        self.assertTrue(self.op("QuarterTurnToTarget"))
        self.assertEqual(self.unit.direction, 384)
        self.assertEqual((round(self.unit.x), round(self.unit.y)), (-24, -18))

    def test_target_behind_gives_an_about_face(self):
        self.build(facing=0, target_at=(10, -100), unit_models=20, unit_ranks=4)
        self.assertTrue(self.op("QuarterTurnToTarget"))
        self.assertEqual(self.unit.direction, 256)
        self.assertEqual((round(self.unit.x), round(self.unit.y)), (0, -36))

    def test_target_within_64_changes_nothing(self):
        self.build(facing=0, target_at=(60, 100), unit_models=20, unit_ranks=4)  # bearing 30
        self.assertFalse(self.op("QuarterTurnToTarget"))
        self.assertEqual(self.unit.direction, 0)

    def test_quarter_turn_reports_true_even_when_the_turn_is_refused(self):
        self.build(facing=0, target_at=(100, 10), unit_models=20, unit_ranks=4)
        self.unit.routing = True
        self.assertTrue(self.op("QuarterTurnToTarget"))
        self.assertEqual(self.unit.direction, 0)

    def test_about_face_and_its_refusal_while_reforming(self):
        self.build(facing=0, unit_models=20, unit_ranks=4)
        self.op("AboutFace")
        self.assertEqual((self.unit.direction, round(self.unit.y)), (256, -36))
        self.build(facing=0, unit_models=20, unit_ranks=4)
        self.unit.reforming = True
        self.op("AboutFace")
        self.assertEqual(self.unit.direction, 0)

    def test_quarter_turn_operand_picks_the_direction(self):
        self.build(facing=0, unit_models=20, unit_ranks=4)
        self.op("QuarterTurn", 0x20)
        self.assertEqual(self.unit.direction, 128)
        self.build(facing=0, unit_models=20, unit_ranks=4)
        self.op("QuarterTurn", 0)
        self.assertEqual(self.unit.direction, 384)


class FleeBackwardTests(MovementTestCase):
    def test_flees_directly_away_from_its_facing_and_clears_the_target(self):
        self.build(facing=100)
        self.assertTrue(self.op("FleeBackward"))
        self.assertEqual(self.unit.direction, 356)
        self.assertTrue(self.unit.routing)
        self.assertIsNone(self.state.current_target)


class CircleTests(MovementTestCase):
    def test_vector(self):
        self.build(unit_at=(0, -200), target_at=(0, 0), facing=0)
        self.assertTrue(self.op("CircleAroundTarget"))
        self.assertEqual((self.unit.target_x, self.unit.target_y), (-39, -197))

    def test_refused_while_reforming_or_without_a_target(self):
        self.build(unit_at=(0, -200), target_at=(0, 0))
        self.unit.reforming = True
        self.assertFalse(self.op("CircleAroundTarget"))
        self.build(with_target=False)
        self.assertFalse(self.op("CircleAroundTarget"))


class ChargeReachTests(MovementTestCase):
    def monster(self, at, s_rlmv=11, radius=10):
        self.build(facing=128, target_at=at, s_rlmv=s_rlmv, target_class="mon")
        patcher = unittest.mock.patch.object(Regiment, "bounding_radius", return_value=radius)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_monster_in_reach_vector(self):
        self.monster((130, 0))
        self.assertTrue(self.op("IfTargetInChargeReach"))
        self.assertEqual((self.unit.target_x, self.unit.target_y), (130, 0))

    def test_out_of_reach_is_false_but_the_destination_is_still_re_aimed(self):
        self.monster((150, 0))
        self.assertFalse(self.op("IfTargetInChargeReach"))
        self.assertEqual((self.unit.target_x, self.unit.target_y), (150, 0))

    def test_facing_more_than_a_sixteenth_of_a_turn_off_the_aim_point_is_false(self):
        self.monster((130, 0))
        self.unit.direction = 192
        self.assertFalse(self.op("IfTargetInChargeReach"))

    def test_charging_unit_fails_and_keeps_its_charge(self):
        self.monster((130, 0))
        self.unit.attack_target = "x"
        self.assertFalse(self.op("IfTargetInChargeReach"))
        self.assertIsNone(self.unit.target_x)

    def test_reforming_unit_fails_with_no_side_effect(self):
        self.monster((130, 0))
        self.unit.reforming = True
        self.assertFalse(self.op("IfTargetInChargeReach"))
        self.assertIsNone(self.unit.target_x)

    def test_target_that_is_charging_fails(self):
        self.monster((130, 0))
        self.target.attack_target = "u"
        self.assertFalse(self.op("IfTargetInChargeReach"))

    def block(self, s_rlmv):
        self.build(facing=128, target_at=(200, 0), target_facing=384, s_rlmv=s_rlmv,
                   target_models=32, target_ranks=4)  # 8 wide x 4 deep, facing the charger
        self.put_target_centre_at(200, 0)

    def test_frontal_charge_on_a_block_aims_at_the_far_side(self):
        self.block(18)
        aim = self.interp._charge_aim_point(self.unit, self.target)
        radius = int(self.target.bounding_radius())
        self.assertEqual((round(aim[0]), round(aim[1])), (200 + radius, 0))

    def test_cavalry_reaches_the_block_and_infantry_does_not(self):
        self.block(18)
        self.assertTrue(self.op("IfTargetInChargeReach"))
        self.block(11)
        self.assertFalse(self.op("IfTargetInChargeReach"))

    def test_flank_and_rear_aim_points(self):
        # Target turned to face +Y at (0,0): a charger at (-150,-10) is on the left flank (rear half),
        # a charger at (-30,-150) is behind it.
        self.build(unit_at=(-150, -10), target_at=(0, 0), target_facing=0, target_models=32, target_ranks=4)
        self.put_target_centre_at(0, 0)
        radius = int(self.target.bounding_radius())
        aim = self.interp._charge_aim_point(self.unit, self.target)
        self.assertEqual((round(aim[0]), round(aim[1])), (radius, 0))
        self.unit.x, self.unit.y = -30, -150
        aim = self.interp._charge_aim_point(self.unit, self.target)
        self.assertEqual((round(aim[0]), round(aim[1])), (0, radius))


class ApproachTests(MovementTestCase):
    def test_vectors(self):
        for target_at, expected in (((200, 60), True), ((200, 90), False)):
            self.build(facing=128, target_at=target_at, target_class="mon")
            self.state.threat_range = 240
            self.assertEqual(self.op("ApproachTargetInReach"), expected, target_at)
            self.assertEqual((self.unit.target_x, self.unit.target_y), target_at)

    def test_no_target_is_false(self):
        self.build(with_target=False)
        self.assertFalse(self.op("ApproachTargetInReach"))


if __name__ == "__main__":
    unittest.main()
