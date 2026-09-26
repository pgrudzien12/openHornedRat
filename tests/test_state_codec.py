"""The save-game codec for the interpreter's state: lossless for what a save needs, closed to anything else."""
import json
import unittest

from whshr.glue import MissionRef
from whshr.glue_animation import GlueBitmapAnimator
from whshr.glue_runtime import (ContextSnapshot, GlueRuntimeState, InstructionTrace, PendingRequest, RuntimeAnimation,
                                ScriptFrame, WindowInstance)
from whshr.glue_state import decode_state, encode_state
from whshr.portraits import PortraitAnimator
from whshr.state_codec import Codec, CodecError


def busy_state():
    state = GlueRuntimeState(current=ScriptFrame("MISSION", 7, True), call_stack=[ScriptFrame("SUB", 2)])
    state.windows = [WindowInstance("MAPWINDOW", None, 2, ["MISSIONLIST"]), WindowInstance("SCRIBE", "MAPWINDOW", 2)]
    state.variables["tentpos"] = 3
    state.status_bits = 0b101
    state.selected_mission = MissionRef("map", 4)
    state.pending = PendingRequest(9, "caravan", True, "select")
    state.next_request_id = 10
    state.context_stack = [ContextSnapshot("RUN", ScriptFrame("FLOW", 30), [], [WindowInstance("MAP", None, 2)], "MAP", 2)]
    state.object_positions[("MAPWINDOW", "TENT")] = (12, 34)
    state.dialogue_lines = (("hello", "black"), ("there", "red"))
    state.animations = [RuntimeAnimation("MAPWINDOW", GlueBitmapAnimator({"bitmap": "Tent", "animstartframe": 5,
                                                                          "animstopframe": 0, "timecnt": 3}), True, "TENT")]
    state.portrait_animators["PORTRAIT"] = PortraitAnimator(2)
    state.portrait_speakers["PORTRAIT"] = (3, "CARLSSON")
    state.trace.append(InstructionTrace("x", "y", "z"))
    return state


class InterpreterStateTests(unittest.TestCase):
    def _round_trip(self, state):
        return decode_state(json.loads(json.dumps(encode_state(state))))

    def test_given_a_busy_state_when_round_tripped_through_json_then_it_is_equal_except_the_trace(self):
        original = busy_state()

        restored = self._round_trip(original)

        original.trace = []
        for name in vars(original):
            if name in ("animations", "portrait_animators"):  # animator objects have no equality; tested below
                continue
            with self.subTest(name):
                self.assertEqual(getattr(restored, name), getattr(original, name))

    def test_given_animations_then_their_counters_survive_and_keep_running_identically(self):
        original = busy_state()
        for _ in range(5):
            original.animations[0].animator.tick(30)
        restored = self._round_trip(original)

        for _ in range(10):
            a = original.animations[0].animator.tick(20)
            b = restored.animations[0].animator.tick(20)
            self.assertEqual(a, b)
        self.assertEqual(vars(restored.animations[0].animator), vars(original.animations[0].animator))

    def test_given_a_portrait_animator_then_it_resumes_where_it_was(self):
        original = busy_state()
        original.portrait_animators["PORTRAIT"].advance(400)
        restored = self._round_trip(original)

        self.assertEqual(vars(restored.portrait_animators["PORTRAIT"]), vars(original.portrait_animators["PORTRAIT"]))

    def test_given_a_speech_in_progress_then_it_is_not_resumed(self):
        original = busy_state()
        original.speech_lines, original.speech_active = (1, 2), True

        restored = self._round_trip(original)

        self.assertEqual((restored.speech_lines, restored.speech_active), ((), False))

    def test_given_types_outside_the_registry_then_neither_saving_nor_loading_accepts_them(self):
        with self.assertRaises(CodecError):
            Codec([ScriptFrame]).encode(WindowInstance("W", None, 0))
        with self.assertRaises(CodecError):
            Codec([ScriptFrame]).decode({"$type": "os.system", "fields": {}})
        with self.assertRaises(CodecError):
            Codec([ScriptFrame]).decode({"unexpected": 1})

    def test_given_fields_the_loader_does_not_know_are_missing_then_the_class_defaults_are_used(self):
        data = encode_state(GlueRuntimeState())
        del data["fields"]["waits_passed"]

        self.assertEqual(decode_state(data).waits_passed, 0)


if __name__ == "__main__":
    unittest.main()
