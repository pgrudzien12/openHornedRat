"""Animation requests, casting-state queries and sound cues (notes/script_animation_sound.md).

Vectors are the report's sections 2.6 and 3.4; the engine tests tick a battle so the models' own
animation programs reach their event steps.
"""

import unittest

from tests.script_helpers import word
from whshr import animation, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side

SHOOT, STAND, FIGHT, WALK = animation.SHOOT, animation.STAND, animation.FIGHT, animation.WALK


class AnimationTestCase(unittest.TestCase):
    def setUp(self):
        self.unit = Regiment("u", "U", 500, 500, 0, Side.ENEMY, models=10, ranks=2, unit_class=1)
        self.battle = Battle(2000, 2000, [self.unit], seed=1995)
        self.unit.model_positions()
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["u"]
        self.state.script_dll = None

    def call(self, name, *operands):
        self.state.pc = 0
        words = [word(name), *operands]
        return getattr(self.interp, "op_" + name)(
            self.state, operands[0] if operands else None, words, "u", 0, None)

    def request(self):
        return (self.state.anim_event, self.state.anim_divisor, self.state.anim_countdown)

    def posted(self):
        return [event.code for event in self.state.event_queue]


class RequestTests(AnimationTestCase):
    def test_play_unit_animation_counts_down_from_the_model_count_and_keeps_the_condition(self):
        self.state.cond_flags = 1
        self.assertEqual(self.call("PlayUnitAnimation", 7, 34, 4), 4)
        self.assertEqual((self.unit.script_action, self.request(), self.state.cond_flags), (7, (34, 4, 10), 1))

    def test_event_steps_post_on_the_2nd_6th_and_10th_arrival(self):
        self.call("PlayUnitAnimation", 7, 34, 4)
        arrivals = []
        for arrival in range(1, 11):
            before = len(self.posted())
            self.battle.event_bus.animation_event_step("u")
            if len(self.posted()) > before:
                arrivals.append(arrival)
        self.assertEqual((arrivals, self.request()), ([2, 6, 10], (34, 4, 0)))
        self.battle.event_bus.animation_event_step("u")  # countdown 0: inert
        self.assertEqual(len(self.posted()), 3)

    def test_if_animation_done_vectors(self):
        rows = [((34, 4, 7), 0, 7, True, (0, 0, 0)), ((34, 4, 7), 2, 7, False, (34, 4, 7)),
                ((34, 4, 0), 10, 7, True, (34, 4, 0)), ((0, 0, 0), 0, 7, True, (0, 0, 0)),
                ((34, 4, 3), 0, 0, False, (34, 4, 3))]
        for request, posing, operand, cond, after in rows:
            with self.subTest(request=request, posing=posing, operand=operand):
                for index, model in enumerate(self.unit.melee_models):
                    model.action = SHOOT if index < posing else STAND
                self.state.anim_event, self.state.anim_divisor, self.state.anim_countdown = request
                self.call("IfAnimationDone", operand)
                self.assertEqual((bool(self.state.cond_flags), self.request()), (cond, after))

    def test_queued_pose_does_not_count_as_playing(self):
        self.unit.melee_models[0].pending_action = SHOOT
        self.state.anim_event, self.state.anim_divisor, self.state.anim_countdown = 34, 4, 5
        self.call("IfAnimationDone", 7)
        self.assertEqual((bool(self.state.cond_flags), self.request()), (True, (0, 0, 0)))

    def test_play_leader_animation_needs_a_leader(self):
        self.state.anim_event, self.state.anim_divisor, self.state.anim_countdown = 34, 4, 6
        self.assertEqual(self.call("PlayLeaderAnimation", 7, 44), 3)
        self.assertEqual(self.request(), (34, 4, 6))
        self.unit.has_leader = True
        self.call("PlayLeaderAnimation", 7, 44)
        self.assertEqual((self.request(), self.unit.melee_models[0].own_request, self.unit.script_action),
                         ((44, 1, 1), 7, 0))

    def test_clear_animation_request_leaves_the_poses(self):
        self.unit.melee_models[0].action = SHOOT
        self.state.anim_event, self.state.anim_divisor, self.state.anim_countdown = 34, 4, 6
        self.call("ClearAnimationRequest")
        self.assertEqual((self.request(), self.unit.melee_models[0].action), ((0, 0, 0), SHOOT))
        self.battle.event_bus.animation_event_step("u")
        self.assertEqual(self.posted(), [])


class EngineAnimationTests(AnimationTestCase):
    def test_leader_cast_pose_posts_its_event_at_the_event_step(self):
        self.unit.has_leader = True
        self.call("PlayLeaderAnimation", 7, 44)
        for _ in range(8):
            self.battle._step_animations(self.unit)
        self.assertEqual(self.posted(), [44])
        self.assertNotEqual(self.unit.melee_models[1].action, SHOOT)  # only the leader posed

    def test_set_action_state_sticks_until_the_unit_changes_state(self):
        self.call("SetActionState", FIGHT)
        for _ in range(3):
            self.battle._step_animations(self.unit)
        self.assertTrue(all(model.action == FIGHT for model in self.unit.melee_models))
        self.unit.target_x, self.unit.target_y = 900.0, 500.0  # a move starts: state change
        self.battle._step_animations(self.unit)
        self.assertEqual(self.unit.script_action, 0)
        self.assertFalse(any(model.action == FIGHT for model in self.unit.melee_models))

    def test_model_in_a_one_shot_queues_the_broadcast(self):
        model = self.unit.melee_models[0]
        animation.step(model, SHOOT, self.battle.rng, self.unit.animation_family)
        self.call("SetActionState", STAND)
        self.battle._step_animations(self.unit)
        self.assertEqual((model.action, model.pending_action), (SHOOT, STAND))


class CastingStateTests(AnimationTestCase):
    def wizard(self):
        self.unit.unit_class = interpreter.WIZARD_CLASS

    def cond(self, name, *operands):
        self.call(name, *operands)
        return bool(self.state.cond_flags)

    def test_vectors(self):
        self.wizard()
        self.assertFalse(self.cond("IfCasting", 0, 0))
        self.state.pending_spell = 3
        self.assertTrue(self.cond("IfCasting", 0, 0))
        self.assertFalse(self.cond("IfCastingAnimation", 0))
        self.state.pending_spell = None
        self.state.channelling = True
        self.assertEqual((self.cond("IfCastingAnimation", 0), self.cond("IfCasting", 0, 0)), (True, True))

    def test_archers_mid_volley_are_in_the_cast_pose_but_never_casting(self):
        self.unit.unit_class = 3
        self.unit.melee_models[4].action = SHOOT
        self.assertEqual((self.cond("IfCastingAnimation", 0), self.cond("IfCasting", 0, 0)), (True, False))

    def test_messages(self):
        self.wizard()
        self.state.pending_spell = 3
        self.call("IfCasting", 1, 1)
        self.call("TurningToCastMessage", 0)
        self.call("TurningToCastMessage", 1)
        self.assertEqual([event.data["text_id"] for event in self.battle.events if event.kind == "message"],
                         [2014, 2010])

    def test_turning_message_keeps_the_condition(self):
        self.state.cond_flags = 1
        self.call("TurningToCastMessage", 0)
        self.assertTrue(self.state.cond_flags)


class SoundTests(AnimationTestCase):
    def cues(self):
        return [(event.data["cue"], event.data["packet"], event.data["effect"], event.data["position"])
                for event in self.battle.events if event.kind == "sound"]

    def test_sound_cues_change_no_script_state(self):
        self.state.cond_flags = 1
        self.assertEqual(self.call("PlaySoundAtUnit", 6, 5), 3)
        self.assertEqual(self.call("PlaySound", 11, 0), 3)
        self.assertEqual(self.cues(), [("at_unit", 6, 5, (500, 500)), ("play", 11, 0, None)])
        self.assertTrue(self.state.cond_flags)

    def test_loop_sound_start_move_stop(self):
        self.assertEqual(self.call("MoveUnitSound", 1), 2)  # empty handle: nothing
        self.assertEqual(self.call("StartUnitLoopSound", 14, 0, 1), 4)
        self.call("MoveUnitSound", 1)
        self.call("StopUnitLoopSound")
        self.call("StopUnitLoopSound")
        self.assertEqual([cue[0] for cue in self.cues()], ["loop_start", "loop_move", "loop_stop", "loop_stop"])


if __name__ == "__main__":
    unittest.main()
