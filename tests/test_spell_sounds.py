"""Spell sounds: the Curse of Anraheir's loop (notes/spell_sounds.md section 1.1 vectors) and the frontend's
per-effect loop handles and pause muting (section 0). Set-up as in test_spell_effects: wizard W at (0, 0)."""

import unittest

from whshr import combat, interpreter, spell_effects
from whshr.frontend.battle_sound import BattleSounds
from whshr.rules import Side

from tests.test_battle_sound import FakeSounds
from tests.test_spell_effects import EffectTestCase, unit

CURSE_CUE = (spell_effects.SPELLS_PACKET, spell_effects.CURSE_LOOP)


class CurseLoopTests(EffectTestCase):
    def setUp(self):
        self.radii = {"A": 40, "B": 40}

    def sounds(self):
        """The sound cues since the last call, as (cue, handle, position)."""
        start = getattr(self, "seen", 0)
        self.seen = len(self.battle.events)
        return [(event.data["cue"], event.data["handle"], event.data["position"])
                for event in self.battle.events[start:] if event.kind == "sound"]

    def curse(self, x, y, caster=None):
        self.sounds()
        return self.launch(spell_effects.CURSE, x, y, caster)

    def test_a_curse_starts_its_loop_at_the_target_centre_on_launch(self):
        self.make(unit("A", 0, 300))
        self.assertTrue(self.curse(0, 300))
        cues = self.sounds()
        self.assertEqual([(cue, position) for cue, _, position in cues], [("loop_start", (0, 300))])
        event = next(event for event in self.battle.events if event.kind == "sound")
        self.assertEqual((event.data["packet"], event.data["effect"]), CURSE_CUE)

    def test_a_failed_curse_launch_is_silent(self):
        self.make(unit("A", 0, 300))
        self.assertFalse(self.curse(2000, 2000))
        self.assertEqual(self.sounds(), [])

    def test_the_loop_follows_the_cursed_unit(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.battle.regiments["A"].y = 340
        self.sounds()
        self.update()
        self.assertEqual([(cue, position) for cue, _, position in self.sounds()], [("loop_move", (0, 340))])

    def test_a_failed_mounted_panic_test_stops_the_loop_in_that_step(self):
        self.make(unit("A", 0, 300, leadership=7, mount=1))
        self.curse(0, 300)
        self.battle.tick_count = 0  # segment 10
        self.sounds()
        self.dice(9)
        self.update()
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_move", "loop_stop"])

    def test_a_passed_mounted_panic_test_keeps_the_loop(self):
        self.make(unit("A", 0, 300, leadership=7, mount=1))
        self.curse(0, 300)
        self.battle.tick_count = 0
        self.sounds()
        self.dice(4)
        self.update()
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_move"])

    def test_an_unmounted_curse_loops_with_no_end(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.sounds()
        self.update(combat.SEGMENTS_PER_TURN * 30)
        self.assertNotIn("loop_stop", [cue for cue, _, _ in self.sounds()])

    def test_a_recast_on_another_unit_stops_the_old_loop_then_starts_the_new_one(self):
        self.make(unit("A", 0, 300), unit("B", 300, 300))
        self.curse(0, 300)
        old = self.sounds()[0][1]
        self.w.direction = 0
        self.curse(300, 300)
        cues = self.sounds()
        self.assertEqual([(cue, position) for cue, _, position in cues], [("loop_stop", None), ("loop_start", (300, 300))])
        self.assertEqual(cues[0][1], old)
        self.assertNotEqual(cues[1][1], old)

    def test_a_recast_on_the_same_unit_restarts_a_new_loop(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        old = self.sounds()[0][1]
        self.curse(0, 300)
        cues = self.sounds()
        self.assertEqual([cue for cue, _, _ in cues], ["loop_stop", "loop_start"])
        self.assertNotEqual(cues[1][1], old)

    def test_a_failed_recast_keeps_the_old_loop(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.assertFalse(self.curse(2000, 2000))
        self.assertEqual(self.sounds(), [])
        self.assertEqual(len(self.effects()), 1)

    def test_two_wizards_curses_play_two_independent_loops_even_on_one_unit(self):
        w2 = unit("W2", 100, 0, Side.PLAYER, models=1, unit_class=interpreter.WIZARD_CLASS)
        self.make(unit("A", 0, 300), w2)
        self.curse(0, 300)
        self.curse(0, 300, caster=w2)
        cues = self.sounds()
        self.assertEqual([cue for cue, _, _ in cues], ["loop_start"])
        self.assertEqual(len(self.effects()), 2)
        self.update()
        handles = {handle for cue, handle, _ in self.sounds() if cue == "loop_move"}
        self.assertEqual(len(handles), 2)

    def test_removing_the_target_stops_the_loop(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.battle.remove_from_play(self.battle.regiments["A"])
        self.sounds()
        self.update()
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_stop"])

    def test_removing_the_wizard_caster_stops_the_loop(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.battle.remove_from_play(self.w)
        self.sounds()
        self.update()
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_stop"])

    def test_a_routing_caster_keeps_the_loop(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.w.routing = True
        self.sounds()
        self.update()
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_move"])

    def test_dispelling_the_curse_stops_the_loop(self):
        self.radii = {"A": 40, "S": 10}
        self.make(unit("A", 0, 300), unit("S", 0, 330, Side.ENEMY, models=1))
        self.curse(0, 300)
        self.sounds()
        self.assertTrue(spell_effects.dispel_pass(self.battle, self.battle.regiments["S"], 100, None))
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_stop"])

    def test_cancelling_the_curse_with_ctrl_click_stops_the_loop(self):
        self.make(unit("A", 0, 300))
        self.curse(0, 300)
        self.sounds()
        self.assertEqual(spell_effects.cancel_owned(self.battle, "W", spell_effects.CURSE), 1)
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_stop"])


class FakeChannel:
    def __init__(self):
        self.busy, self.stopped, self.paused = True, False, False

    def get_busy(self):
        return self.busy

    def stop(self):
        self.stopped, self.busy = True, False

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    def queue(self, sound):
        pass


class PausableSounds(FakeSounds):
    def _play(self, packet, index, loop):
        channel = FakeChannel()
        self.played.append((packet, index, loop, channel))
        return channel


def spell_cue(kind, handle, regiment="W"):
    from types import SimpleNamespace
    return SimpleNamespace(kind="sound", data={"cue": kind, "packet": CURSE_CUE[0], "effect": CURSE_CUE[1],
                                               "regiment": regiment, "handle": handle})


class SpellLoopPlaybackTests(unittest.TestCase):
    def test_each_spell_effect_keeps_its_own_loop_handle(self):
        sounds = PausableSounds()
        sounds.handle([spell_cue("loop_start", "spell 0"), spell_cue("loop_start", "spell 1")])
        first, second = sounds.played[0][3], sounds.played[1][3]
        self.assertFalse(first.stopped)
        sounds.handle([spell_cue("loop_stop", "spell 0")])
        self.assertEqual((first.stopped, second.stopped), (True, False))

    def test_spell_loops_are_looped_plays(self):
        sounds = PausableSounds()
        sounds.handle([spell_cue("loop_start", "spell 0")])
        self.assertTrue(sounds.played[0][2])

    def test_pause_mutes_running_loops_and_resume_continues_them(self):
        sounds = PausableSounds()
        sounds.handle([spell_cue("loop_start", "spell 0")])
        channel = sounds.played[0][3]
        sounds.set_paused(True)
        self.assertEqual((channel.paused, channel.stopped), (True, False))
        sounds.handle([spell_cue("loop_start", "spell 1")])
        self.assertTrue(sounds.played[1][3].paused)
        sounds.set_paused(False)
        self.assertEqual((channel.paused, sounds.played[1][3].paused), (False, False))

    def test_the_spells_packet_is_always_available(self):
        self.assertIn(CURSE_CUE[0], BattleSounds(None, ()).available)


if __name__ == "__main__":
    unittest.main()
