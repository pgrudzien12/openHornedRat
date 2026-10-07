"""Custom audio controls in the game's original Options window."""

import json
import importlib.util
from pathlib import Path
import tempfile
import unittest

from whshr.audio_settings import AudioSettings, audio_settings
from whshr.campaign_scenes import MainMenuScene
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.options_scene import OptionsScene
from whshr.scenes import Scene, SceneMachine


class Context:
    def __init__(self, save_dir: Path) -> None:
        self.save_dir = save_dir
        self.content = GlueContent.from_data(resources={
            "STARTCARAVAN": "[WINDOW]\n[END]",
        })

    def glue_content(self) -> GlueContent:
        return self.content


class OptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.context = Context(Path(self.directory.name))

    def tearDown(self) -> None:
        audio_settings.configure(None)
        self.directory.cleanup()

    def test_saved_levels_survive_reopening_and_cancel_discards_edits(self) -> None:
        parent = Scene()
        machine = SceneMachine(OptionsScene(parent), self.context)
        machine.handle(("options:cycle", "music"))  # 100 -> Off
        machine.handle(("options:cycle", "dialogue"))
        machine.handle("options:ok")

        self.assertIs(machine.active, parent)
        self.assertEqual(json.loads((self.context.save_dir / "options.json").read_text()),
                         {"music": 0, "dialogue": 0, "effects": 100})
        self.assertEqual(audio_settings.volume("music"), 0)

        reopened = SceneMachine(OptionsScene(parent), self.context)
        self.assertEqual(reopened.active.values["dialogue"], 0)
        reopened.handle(("options:cycle", "dialogue"))
        reopened.handle("options:cancel")
        self.assertEqual(audio_settings.volume("dialogue"), 0)
        self.assertEqual(json.loads((self.context.save_dir / "options.json").read_text())["dialogue"], 0)

    def test_levels_cycle_through_five_choices(self) -> None:
        scene = OptionsScene(Scene())
        scene.enter(self.context)
        values = []
        for _ in range(5):
            scene.handle(("options:cycle", "effects"), self.context)
            values.append(scene.values["effects"])
        self.assertEqual(values, [0, 25, 50, 75, 100])

    def test_missing_or_invalid_settings_use_full_volume(self) -> None:
        settings = AudioSettings()
        settings.configure(self.context.save_dir)
        self.assertEqual(settings.values, {"music": 100, "dialogue": 100, "effects": 100})
        (self.context.save_dir / "options.json").write_text('{"music": 25, "dialogue": 42, "effects": false}')
        settings.configure(self.context.save_dir)
        self.assertEqual(settings.values, {"music": 25, "dialogue": 100, "effects": 100})

    def test_caravan_and_mission_panel_open_options_and_return_to_same_scene(self) -> None:
        for event in (GlueInput("hotspot-release", "OptionsDialog"),
                      GlueInput("panel-action", "open_options")):
            with self.subTest(event=event):
                parent = GlueScene(window="STARTCARAVAN")
                machine = SceneMachine(parent, self.context)
                machine.handle(event)
                self.assertIsInstance(machine.active, OptionsScene)
                machine.handle("options:cancel")
                self.assertIs(machine.active, parent)

    def test_main_menu_opens_options(self) -> None:
        transition = MainMenuScene().handle("options", self.context)
        self.assertIsInstance(transition.scene, OptionsScene)


@unittest.skipUnless(importlib.util.find_spec("pygame"), "Pygame is not installed")
class OptionsInputTests(unittest.TestCase):
    def test_button_cycles_only_on_release_inside_and_escape_cancels(self) -> None:
        import pygame
        from whshr.frontend.options_view import OptionsView

        view = OptionsView.__new__(OptionsView)
        view.pressed = None
        view.refresh = lambda: None
        view._action_at = lambda position: "music" if position[0] < 100 else None

        self.assertEqual(view.events(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))), ())
        self.assertEqual(view.events(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(200, 10))), ())
        view.events(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10)))
        self.assertEqual(view.events(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(10, 10))),
                         (("options:cycle", "music"),))
        self.assertEqual(view.events(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)),
                         ("options:cancel",))


if __name__ == "__main__":
    unittest.main()
