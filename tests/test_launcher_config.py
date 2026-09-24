import tempfile
import unittest
from pathlib import Path

from whshr.launcher import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "nested" / "config.json"

    def tearDown(self):
        self.temporary.cleanup()

    def test_given_no_config_file_when_loaded_then_it_returns_an_empty_config(self):
        loaded = config.load_config(self.path)

        self.assertIsNone(loaded.installation_path)

    def test_given_a_saved_config_when_loaded_then_it_round_trips(self):
        config.save_config(config.LauncherConfig(installation_path="/games/whshr"), self.path)

        loaded = config.load_config(self.path)

        self.assertEqual(loaded.installation_path, "/games/whshr")
        self.assertTrue(self.path.is_file())

    def test_given_a_corrupted_config_file_when_loaded_then_it_falls_back_to_an_empty_config(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")

        loaded = config.load_config(self.path)

        self.assertIsNone(loaded.installation_path)
