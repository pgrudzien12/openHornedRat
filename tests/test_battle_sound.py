"""Battle sound cues (notes/script_animation_sound.md §4, notes/sfx.md): which effects a cue plays, pitch
resampling, PlaySound's no-restart rule, loop handles and the loaded-packet gate. The mixer is replaced by fakes."""

import random
import unittest
from types import SimpleNamespace

from whshr.frontend.battle_sound import BattleSounds, members, resample


class FakeChannel:
    def __init__(self):
        self.busy, self.stopped, self.queued = True, False, []

    def get_busy(self):
        return self.busy

    def stop(self):
        self.stopped, self.busy = True, False

    def queue(self, sound):
        self.queued.append(sound)


class FakeSounds(BattleSounds):
    """Records what would play instead of touching the mixer."""

    def __init__(self, loaded=("buttonfx", "Battle2")):
        super().__init__(None, loaded, random.Random(1))
        self.enabled = True
        self.played = []

    def _play(self, packet, index, loop):
        channel = FakeChannel()
        self.played.append((packet, index, loop, channel))
        return channel


def cue(kind, packet, effect, regiment="r"):
    return SimpleNamespace(kind="sound", data={"cue": kind, "packet": packet, "effect": effect, "regiment": regiment})


class EffectChoiceTests(unittest.TestCase):
    EFFECTS = [{"index": 0, "name": "Shot"}, {"index": 1, "name": "Arrow"},
               {"index": 2, "name": "Volley", "list_names": ["Shot", "Arrow"], "flag_names": ["LIST"]},
               {"index": 3, "name": "Either", "list_names": ["Shot", "Arrow"], "flag_names": ["LIST", "RANDOM"]}]

    def test_a_plain_effect_plays_itself(self):
        self.assertEqual(members(self.EFFECTS[0], self.EFFECTS, random.Random(1)), [0])

    def test_a_list_plays_its_members_in_turn(self):
        self.assertEqual(members(self.EFFECTS[2], self.EFFECTS, random.Random(1)), [0, 1])

    def test_a_random_list_plays_one_member(self):
        chosen = members(self.EFFECTS[3], self.EFFECTS, random.Random(1))
        self.assertEqual(len(chosen), 1)
        self.assertIn(chosen[0], (0, 1))

    def test_resampling_at_a_higher_pitch_shortens_the_sound(self):
        stereo = list(range(20))  # 10 frames, 2 channels
        self.assertEqual(list(resample(stereo, 2, 2.0)), [0, 1, 4, 5, 8, 9, 12, 13, 16, 17])
        self.assertEqual(len(resample(stereo, 2, 0.5)), 40)


class CueTests(unittest.TestCase):
    def test_the_decision_speech_plays_from_the_always_loaded_race_packet(self):
        sounds = FakeSounds()
        sounds.handle([cue("play", 5, 9)])
        self.assertEqual([(p, i, loop) for p, i, loop, _ in sounds.played], [(5, 9, False)])

    def test_a_packet_the_battle_did_not_load_stays_silent(self):
        sounds = FakeSounds()
        sounds.handle([cue("play", 11, 0)])
        self.assertEqual(sounds.played, [])
        sounds = FakeSounds(("buttonfx", "Battle2", "Zhufbar"))
        sounds.handle([cue("global", 11, 0)])
        self.assertEqual(len(sounds.played), 1)

    def test_play_does_not_restart_an_effect_still_playing(self):
        sounds = FakeSounds()
        sounds.handle([cue("play", 5, 9), cue("play", 5, 9)])
        self.assertEqual(len(sounds.played), 1)
        sounds.played[0][3].busy = False
        sounds.handle([cue("play", 5, 9)])
        self.assertEqual(len(sounds.played), 2)

    def test_at_unit_copies_overlap(self):
        sounds = FakeSounds()
        sounds.handle([cue("at_unit", 6, 5), cue("at_unit", 6, 5)])
        self.assertEqual(len(sounds.played), 2)

    def test_a_charge_loop_is_stopped_by_its_handle(self):
        sounds = FakeSounds()
        sounds.handle([cue("charge_start", 2, 1, "a"), cue("charge_start", 2, 1, "b")])
        self.assertEqual([loop for _, _, loop, _ in sounds.played], [True, True])
        sounds.handle([cue("charge_stop", 2, 1, "a")])
        self.assertEqual([channel.stopped for *_, channel in sounds.played], [True, False])

    def test_a_new_loop_replaces_the_units_previous_one(self):
        sounds = FakeSounds(("MoleMach",))
        sounds.handle([cue("loop_start", 14, 0), cue("loop_start", 14, 1)])
        self.assertEqual([channel.stopped for *_, channel in sounds.played], [True, False])


if __name__ == "__main__":
    unittest.main()
