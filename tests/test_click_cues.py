"""Mouse click cue behaviour of glue hotspots and native dialog buttons."""

import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


@unittest.skipUnless(importlib.util.find_spec("pygame"), "pygame is unavailable")
class ClickCueTests(unittest.TestCase):
    def test_cues_use_speech_recordings_and_skip_when_speech_is_off_or_playing(self):
        from whshr.frontend.click_cues import play_click_cue, set_speech_sound
        installation = Mock()
        sound = Mock()
        with (patch("whshr.frontend.click_cues.audio_settings.volume", return_value=1.0) as volume,
              patch("whshr.frontend.click_cues.load_speech", return_value=b"wav") as load,
              patch("whshr.frontend.click_cues.pygame.mixer.get_init", return_value=True),
              patch("whshr.frontend.click_cues.pygame.mixer.Sound", return_value=sound) as make_sound):
            play_click_cue(installation, 4)
            load.assert_called_once_with(installation, 4)
            make_sound.assert_called_once()
            sound.play.assert_called_once_with()
            volume.return_value = 0.0
            play_click_cue(installation, 3)
            volume.return_value = 1.0
            play_click_cue(installation, 3, speech_playing=True)
            play_click_cue(installation, 3, speech_enabled=False)
            active_speech = Mock()
            active_speech.get_num_channels.return_value = 1
            set_speech_sound(active_speech)
            try:
                play_click_cue(installation, 3)
            finally:
                set_speech_sound(None)
            self.assertEqual(load.call_count, 1)

    def test_load_save_buttons_play_press_and_inside_release_only(self):
        import pygame
        from whshr.frontend.load_save_view import LoadSaveView
        cues: list[int] = []
        view = SimpleNamespace(pressed=None, scene=SimpleNamespace(editing=False),
                               _action_at=lambda pos: "ok" if pos[0] < 10 else None,
                               _click_cue=cues.append, refresh=lambda: None)
        down = lambda x: pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, 0))
        up = lambda x: pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, 0))

        self.assertEqual(LoadSaveView.events(view, down(0)), ())
        self.assertEqual(LoadSaveView.events(view, up(20)), ())
        self.assertEqual(cues, [4])
        self.assertEqual(LoadSaveView.events(view, down(0)), ())
        self.assertEqual(LoadSaveView.events(view, up(0)), ("ok",))
        self.assertEqual(cues, [4, 4, 3])

    def test_glue_release_uses_hotspot_under_pointer_even_when_press_was_elsewhere(self):
        import pygame
        from whshr.frontend.glue_view import GlueView
        from whshr.glue_render import RenderHotspot
        pressed = RenderHotspot(0, 0, 10, 10, None, "one", None, None, None, downsfx=4, upsfx=3)
        released = RenderHotspot(10, 0, 10, 10, None, "two", None, None, None, downsfx=4, upsfx=3)
        cues: list[int] = []
        view = SimpleNamespace(models=(), pressed=None, _pressed_button=None, cursors=Mock(),
                               _native_point=lambda pos: pos, _mission_at=lambda point: None,
                               _panel_button_at=lambda point: None,
                               hotspot_at=lambda models, point: pressed if point[0] < 10 else released,
                               _play_click_cue=cues.append)
        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(15, 5))

        self.assertEqual(GlueView.events(view, down), ())
        self.assertEqual(GlueView.events(view, up), ())
        self.assertEqual(cues, [4, 3])
