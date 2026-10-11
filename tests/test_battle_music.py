"""Battlefield music lifecycle vectors from notes/battle_music.md, with a fake audio device."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame

from whshr.audio_settings import audio_settings
from whshr.frontend.battle_music import BattleMusic
from whshr.frontend.battle_view import BattleView
from whshr.paths import Installation


class MusicDevice:
    """A tune has a position that only advances while audible; pause never rewinds it."""

    def __init__(self):
        self.track = "CAMPAIGN.MID"
        self.playing = True
        self.paused = False
        self.position = 40.0
        self.volume = 1.0
        self.starts = []
        self.fail_load = False

    def stop(self):
        self.playing = False
        self.position = 0.0

    def unload(self):
        self.track = None

    def load(self, path):
        if self.fail_load:
            raise pygame.error("unsupported MIDI")
        Path(path).read_bytes()
        self.track = Path(path).name
        self.position = 0.0

    def play(self):
        self.position = 0.0
        self.playing = True
        self.paused = False
        self.starts.append(self.track)

    def set_volume(self, value):
        self.volume = value

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    def get_busy(self):
        return self.playing and not self.paused

    def advance(self, seconds):
        if self.get_busy() and self.volume > 0:
            self.position += seconds


class BattleMusicTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        music_dir = self.root / "FILE" / "BINARY" / "MUSIC"
        music_dir.mkdir(parents=True)
        self.track = music_dir / "BATTLE.MID"
        self.track.write_bytes(b"synthetic MIDI fixture for fake device")
        self.installation = Installation(self.root)
        self.device = MusicDevice()
        self.addCleanup(patch.stopall)
        patch("whshr.frontend.battle_music.pygame.mixer.music", self.device).start()
        patch("whshr.frontend.battle_music.pygame.mixer.get_init", return_value=(44100, -16, 2)).start()
        patch.object(audio_settings, "values", {"music": 100, "dialogue": 100, "effects": 100}).start()

    def test_given_campaign_music_when_entering_deployment_then_battle_starts_from_the_beginning(self):
        BattleMusic(self.installation)
        self.assertEqual(self.device.track, "BATTLE.MID")
        self.assertTrue(self.device.get_busy())
        self.assertEqual(self.device.position, 0.0)

    def test_given_a_completed_tune_when_the_next_completion_check_arrives_then_it_repeats(self):
        music = BattleMusic(self.installation)
        self.device.playing = False
        music.update(2.4, paused=False)
        self.assertFalse(self.device.get_busy())
        music.update(0.1, paused=False)
        self.assertTrue(self.device.get_busy())
        self.assertEqual(self.device.starts, ["BATTLE.MID", "BATTLE.MID"])

    def test_given_ordinary_pause_when_resuming_then_the_same_position_continues(self):
        music = BattleMusic(self.installation)
        self.device.advance(30)
        music.update(0, paused=True)
        self.device.advance(300)
        music.update(300, paused=True)
        self.assertEqual(self.device.position, 30)
        self.assertFalse(self.device.get_busy())
        music.update(0, paused=False)
        self.device.advance(5)
        self.assertEqual(self.device.position, 35)
        self.assertEqual(self.device.starts, ["BATTLE.MID"])

    def test_given_music_disabled_on_entry_when_enabled_in_deployment_then_it_begins(self):
        audio_settings.values["music"] = 0
        music = BattleMusic(self.installation)
        self.assertEqual(self.device.track, "BATTLE.MID")
        self.assertFalse(self.device.get_busy())
        music.update(100, paused=False)
        self.assertEqual(self.device.starts, [])
        audio_settings.values["music"] = 50
        music.update(0, paused=False)
        self.assertTrue(self.device.get_busy())
        self.assertEqual(self.device.volume, 0.5)
        self.assertEqual(self.device.position, 0)

    def test_given_a_playing_tune_when_disabled_and_reenabled_then_it_resumes_without_restarting(self):
        music = BattleMusic(self.installation)
        self.device.advance(30)
        audio_settings.values["music"] = 0
        music.update(0, paused=False)
        self.device.advance(50)
        audio_settings.values["music"] = 75
        music.update(0, paused=True)
        self.assertFalse(self.device.get_busy())
        music.update(0, paused=False)
        self.assertTrue(self.device.get_busy())
        self.assertEqual(self.device.position, 30)
        self.assertEqual(self.device.volume, 0.75)
        self.assertEqual(self.device.starts, ["BATTLE.MID"])

    def test_given_missing_battle_music_when_entering_then_prior_music_stops_and_no_tick_retries(self):
        self.track.unlink()
        music = BattleMusic(self.installation)
        self.assertFalse(self.device.get_busy())
        self.assertIsNone(self.device.track)
        self.track.write_bytes(b"now available")
        music.update(100, paused=False)
        self.assertFalse(self.device.get_busy())
        BattleMusic(self.installation)
        self.assertTrue(self.device.get_busy())

    def test_given_an_unplayable_tune_when_entering_then_the_battle_remains_silent(self):
        self.device.fail_load = True
        music = BattleMusic(self.installation)
        music.update(100, paused=False)
        self.assertFalse(self.device.get_busy())
        self.assertIsNone(self.device.track)

    def test_given_no_audio_device_when_entering_then_music_does_not_block_the_battle(self):
        patch("whshr.frontend.battle_music.pygame.mixer.get_init", return_value=None).start()
        patch("whshr.frontend.battle_music.pygame.mixer.init", side_effect=pygame.error("no device")).start()
        music = BattleMusic(self.installation)
        music.update(100, paused=False)
        music.release()
        self.assertEqual(self.device.starts, [])

    def test_given_battle_music_when_leaving_and_reentering_then_the_old_tune_is_released_and_restarts(self):
        music = BattleMusic(self.installation)
        self.device.advance(80)
        music.release()
        self.assertFalse(self.device.get_busy())
        self.assertIsNone(self.device.track)
        music.release()
        BattleMusic(self.installation)
        music.update(100, paused=False)  # a disposed owner cannot affect the next scene
        self.assertEqual(self.device.position, 0)
        self.assertTrue(self.device.get_busy())

    def test_given_battle_phase_changes_when_the_view_refreshes_then_playback_does_not_restart(self):
        view = BattleView.__new__(BattleView)
        view.music = BattleMusic(self.installation)
        battle = SimpleNamespace(phase="deployment", paused=False, result=None, can_leave=False, in_melee=False)
        view.scene = SimpleNamespace(battle=battle)
        self.device.advance(20)
        for changes in ({"phase": "battle"}, {"in_melee": True}, {"in_melee": False},
                        {"can_leave": True, "decision": "victory"}, {"decision": "defeat"}, {"decision": "U"}):
            for name, value in changes.items():
                setattr(battle, name, value)
            view.refresh()
        self.assertEqual(self.device.position, 20)
        self.assertEqual(self.device.starts, ["BATTLE.MID"])
        battle.paused = True
        view.refresh()
        self.assertFalse(self.device.get_busy())
        battle.paused = False
        view.refresh()
        self.assertTrue(self.device.get_busy())
        self.assertEqual(self.device.position, 20)
        battle.result = "victory"  # departure, rather than merely deciding the objective
        view.refresh()
        self.assertFalse(self.device.get_busy())
        self.assertIsNone(self.device.track)

    def test_given_the_tent_when_clicked_then_music_stops_before_the_final_result(self):
        from tests.test_hud import _hud, _panel_pos
        from tests.test_objectives import at_boundary, make, regiment
        from whshr.battle_scene import BattleScene
        from whshr.rules import Side

        player = regiment("player", Side.PLAYER)
        battle = make([["A", 32, 2]], player)
        at_boundary(battle)
        self.assertTrue(battle.can_leave)
        scene = BattleScene()
        scene.battle = battle
        view = BattleView.__new__(BattleView)
        view.scene = scene
        view.hud = _hud(regiments=[player])
        view.hud.battle = battle
        view.camera = SimpleNamespace()
        view.cursors = None
        view._cursor_mode = None
        view.order_mode = None
        view.music = BattleMusic(self.installation)

        events = view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=_panel_pos(view.hud, 12, 119), mod=0))

        self.assertEqual(events, (("leave_battle",),))
        self.assertIsNone(battle.result)
        self.assertFalse(self.device.get_busy())
        self.assertIsNone(self.device.track)
        for event in events:
            scene.handle(event, SimpleNamespace())
        self.assertEqual(battle.result, "victory")

    def test_given_a_playing_view_when_released_without_a_result_then_music_stops(self):
        view = BattleView.__new__(BattleView)
        view.music = BattleMusic(self.installation)
        view.gpu = SimpleNamespace(ctx=SimpleNamespace(release=lambda resource: None))
        view.hud = SimpleNamespace(release=lambda: None)
        view.cursors = None
        for name in ("mesh", "effects", "sprites", "vertex_buffer", "effect_buffer", "instance_buffer",
                     "camera_buffer", "textures", "atlas", "palette"):
            setattr(view, name, object())

        view.release()

        self.assertFalse(self.device.get_busy())
        self.assertIsNone(self.device.track)


if __name__ == "__main__":
    unittest.main()
