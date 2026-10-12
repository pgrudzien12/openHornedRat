"""Spell sounds: the Curse of Anraheir's loop (notes/spell_sounds.md section 1.1 vectors), the other spells'
sounds (section 2) and the frontend's per-effect handles and pause muting (section 0). Set-up as in test_spell_effects: wizard W at (0, 0)."""

import unittest

from whshr import combat, interpreter, spell_effects
from whshr.frontend.battle_sound import BattleSounds
from whshr.rules import Side

from tests.test_battle_sound import FakeSounds
from tests.test_spell_effects import EffectTestCase, unit

CURSE_CUE = (spell_effects.SPELLS_PACKET, spell_effects.SFX_CURSE)


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
        self.assertEqual([cue for cue, _, _ in self.sounds()], ["loop_stop"])

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



class OtherSpellSoundTests(EffectTestCase):
    """notes/spell_sounds.md section 2: which `spells` effect each spell starts, when and where."""

    def setUp(self):
        self.radii = {"A": 40}

    def starts(self):
        """The sounds started since the last call, as (effect index, position)."""
        start = getattr(self, "seen", 0)
        self.seen = len(self.battle.events)
        return [(event.data["effect"], event.data["position"]) for event in self.battle.events[start:]
                if event.kind == "sound" and event.data["cue"] == "loop_start"]

    def cues(self):
        start = getattr(self, "seen", 0)
        self.seen = len(self.battle.events)
        return [(event.data["cue"], event.data["effect"]) for event in self.battle.events[start:]
                if event.kind == "sound"]

    def test_launch_sounds_at_the_caster(self):
        for code, effect in ((spell_effects.LIGHTNING, spell_effects.SFX_THUNDER),
                             (spell_effects.WARP_LIGHTNING, spell_effects.SFX_THUNDER),
                             (spell_effects.FIREBALL, spell_effects.SFX_FIREBALL),
                             (spell_effects.PIERCING, spell_effects.SFX_FIREBALL),
                             (spell_effects.BURNING_HEAD, spell_effects.SFX_FIREBALL),
                             (spell_effects.GAZE, spell_effects.SFX_GAZE),
                             (spell_effects.SKITTERLEAP, spell_effects.SFX_SKITTERLEAP)):
            with self.subTest(code=code):
                self.make()
                self.seen = 0
                self.launch(code, 0, 400)
                self.assertEqual(self.starts(), [(effect, (0, 0))])

    def test_launch_sounds_at_the_aim_point(self):
        for code, effect in ((spell_effects.FLAMESTORM, spell_effects.SFX_FLAMESTORM),
                             (spell_effects.FLOCK, spell_effects.SFX_FLOCK),
                             (spell_effects.SAPPHIRE_ARCH, spell_effects.SFX_SPELL)):
            with self.subTest(code=code):
                self.make()
                self.seen = 0
                self.launch(code, 100, 400)
                self.assertEqual(self.starts(), [(effect, (100, 400))])

    def test_madness_sounds_at_the_aim_point(self):
        self.make(unit("A", 500, 500, Side.PLAYER), wizard_side=Side.ENEMY)
        self.assertTrue(self.launch(spell_effects.MADNESS, 520, 500))
        self.assertEqual(self.starts(), [(spell_effects.SFX_MADNESS, (520, 500))])

    def test_unit_spells_loop_at_their_target_and_follow_it(self):
        for code in (spell_effects.AZURE_BLADES, spell_effects.ERE_WE_GO, spell_effects.MORK_SAVE_UZ):
            with self.subTest(code=code):
                self.make(unit("A", 0, 300, Side.PLAYER))
                self.seen = 0
                self.assertTrue(self.launch(code, 0, 300))
                self.assertEqual(self.starts(), [(spell_effects.SFX_SPELL, (0, 300))])
                self.battle.regiments["A"].x = 50
                self.update()
                moves = [(event.data["cue"], event.data["position"]) for event in self.battle.events[self.seen:]
                         if event.kind == "sound"]
                self.assertEqual(moves, [("loop_move", (50, 300))])

    def test_silent_spells_start_no_sound(self):
        for code in (spell_effects.STORM, spell_effects.TANGLING_THORN, spell_effects.HUNTING_SPEAR,
                     spell_effects.DISPEL_MAGIC, spell_effects.FISTS, spell_effects.PESTILENT_BREATH):
            with self.subTest(code=code):
                self.make(unit("A", 0, 300))
                self.seen = 0
                self.launch(code, 0, 300)
                self.update(30)
                self.assertEqual(self.starts(), [])

    def test_a_one_shot_is_stopped_when_its_effect_ends(self):
        self.make()
        self.launch(spell_effects.LIGHTNING, 0, 400)
        self.cues()
        for _ in range(100):
            self.update()
            if not self.effects():
                break
        self.assertEqual(self.cues(), [("loop_stop", spell_effects.SFX_THUNDER)])

    def test_the_burning_head_laughs_from_its_first_flight_step_and_carries_the_laugh(self):
        self.make()
        self.launch(spell_effects.BURNING_HEAD, 0, 400)
        self.starts()
        self.update()
        effect = self.effects()[0]
        self.assertEqual(self.starts(), [(spell_effects.SFX_LAUGH, (effect.x, effect.y))])
        self.update()
        self.assertEqual(self.cues(), [("loop_move", spell_effects.SFX_LAUGH)])

    def test_wind_blast_starts_wind1_at_launch_and_a_wind2_loop_per_trail_deposit(self):
        self.make()
        self.launch(spell_effects.WIND_BLAST, 0, 400)
        self.assertEqual(self.starts(), [(spell_effects.SFX_WIND1, (0, 0))])
        self.update(80)
        effect = self.effects()[0]
        self.assertGreater(len(effect.trail), 0)
        self.assertEqual([index for index, _ in self.starts()], [spell_effects.SFX_WIND2] * len(effect.trail))
        spell_effects.cancel_owned(self.battle, "W", spell_effects.WIND_BLAST)
        self.assertEqual([cue for cue, _ in self.cues()], ["loop_stop"] * (1 + len(effect.trail)))

    def test_da_krunch_sounds_when_the_foot_stands(self):
        self.make()
        self.launch(spell_effects.DA_KRUNCH, 0, 400)
        self.assertEqual(self.starts(), [])
        self.update(spell_effects.KRUNCH_STAND)
        self.assertEqual(self.starts(), [])
        self.update()
        self.assertEqual(self.starts(), [(spell_effects.SFX_DA_KRUNCH, (0, 400))])

    def test_conflagration_sounds_when_the_fire_reaches_the_ground(self):
        self.make()
        self.dice(2)  # k = 3: the fall ends at T + 9k + 9 = T + 36
        self.launch(spell_effects.CONFLAGRATION, 0, 400)
        self.update(36)
        self.assertEqual(self.starts(), [])
        self.update()
        self.assertEqual(self.starts(), [(spell_effects.SFX_DOOM, (0, 400))])

    def test_the_flying_bower_winds_stop_at_the_landing(self):
        self.radii = {"W": 16}
        self.make()
        self.launch(spell_effects.FLYING_BOWER, 0, 900)
        self.assertEqual(self.starts(), [(spell_effects.SFX_WIND1, (0, 0))])
        self.update(spell_effects.BOWER_LIFT)
        self.assertEqual(self.starts(), [])
        self.update()
        self.assertEqual([index for index, _ in self.starts()], [spell_effects.SFX_WIND2])
        self.update(spell_effects.BOWER_FLIGHT)
        self.assertEqual(self.cues(), [("loop_move", spell_effects.SFX_WIND2)] * spell_effects.BOWER_FLIGHT)
        self.update()
        self.assertEqual(self.cues(), [("loop_stop", spell_effects.SFX_WIND1), ("loop_stop", spell_effects.SFX_WIND2)])
        self.assertTrue(self.effects())

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
