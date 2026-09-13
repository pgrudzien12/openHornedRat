from pathlib import Path
import tempfile
import unittest

from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign_scenes import IntroScene, MainMenuScene
from whshr.catalog import build
from whshr.game import start
from whshr.scenes import SceneAssets, SceneMachine


class IntroSceneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self._write("FILE/SCRIPT/BF001.BTS", b"[BATTLESCRIPT]\n[END]\n")
        self._write("FILE/BINARY/STANDARD.PAL", b"palette")
        self._write("REMOTE/BINARY/ANIM/A1.SI", b"container")
        self.container = {
            "root": {
                "start": 0, "duration": 0,
                "children": [{"start": 0, "duration": 1_000}, {"start": 500, "duration": 1_250}],
            }
        }
        self.loaded = []
        self.context = SceneAssets(
            AssetLocator(self.root), build(self.root), AssetCache(),
            {"omni-si": self._load_container},
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _load_container(self, _, path):
        self.loaded.append(path)
        return self.container

    def test_given_intro_when_entered_then_its_original_container_defines_the_playback_duration(self):
        intro = IntroScene()
        SceneMachine(intro, self.context)

        self.assertEqual(intro.duration_seconds, 1.75)
        self.assertEqual(self.loaded, [self.root / "REMOTE/BINARY/ANIM/A1.SI"])

    def test_given_intro_when_player_skips_then_main_menu_becomes_active(self):
        machine = SceneMachine(IntroScene(), self.context)

        machine.handle("skip")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "intro skipped")

    def test_given_intro_when_its_timeline_ends_then_main_menu_becomes_active(self):
        machine = SceneMachine(IntroScene(), self.context)

        machine.update(1.75)

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "intro completed")

    def test_given_game_start_when_intro_is_skipped_then_scene_machine_reaches_main_menu(self):
        machine = start(self.root, skip_intro=True, loaders={"omni-si": self._load_container})

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "intro skipped")


if __name__ == "__main__":
    unittest.main()
