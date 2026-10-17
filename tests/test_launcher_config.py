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


class ConfigLocationTests(unittest.TestCase):
    HOME = Path("/home/tester")

    def test_given_each_platform_then_the_config_file_follows_its_convention(self):
        cases = {
            ("linux", ()): self.HOME / ".config/ohr/config.json",
            ("linux", (("XDG_CONFIG_HOME", "/cfg"),)): Path("/cfg/ohr/config.json"),
            ("linux", (("XDG_CONFIG_HOME", "relative"),)): self.HOME / ".config/ohr/config.json",
            ("darwin", ()): self.HOME / "Library/Application Support/ohr/config.json",
            ("win32", (("APPDATA", "C:/Roam"),)): Path("C:/Roam/ohr/config.json"),
        }
        for (platform, environ), expected in cases.items():
            with self.subTest(platform=platform, environ=environ):
                self.assertEqual(config.config_path(dict(environ), platform, self.HOME), expected)


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.legacy = self.home / ".ohr"
        (self.legacy / "logs").mkdir(parents=True)
        config.save_config(config.LauncherConfig(installation_path="/games/WARFB"), self.legacy / "config.json")
        (self.legacy / "logs" / "campaign-20261012-224001.jsonl").write_text("{}\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def migrate(self, platform="linux"):
        return config.migrate_legacy_files({}, platform, self.home)

    def test_given_an_old_home_folder_when_migrating_then_settings_and_logs_move_and_the_folder_goes(self):
        self.migrate()

        moved = config.load_config(config.config_path({}, "linux", self.home))
        self.assertEqual(moved.installation_path, "/games/WARFB")
        self.assertTrue((self.home / ".local/share/ohr/logs/campaign-20261012-224001.jsonl").is_file())
        self.assertFalse(self.legacy.exists())

    def test_given_settings_already_in_the_new_place_when_migrating_then_they_are_kept(self):
        current = config.config_path({}, "linux", self.home)
        config.save_config(config.LauncherConfig(installation_path="/newer/WARFB"), current)

        self.migrate()

        self.assertEqual(config.load_config(current).installation_path, "/newer/WARFB")
        self.assertTrue((self.legacy / "config.json").is_file(), "the old file is left, not lost")

    def test_given_an_identical_copy_already_in_the_new_place_when_migrating_then_the_old_one_goes(self):
        current = config.config_path({}, "linux", self.home)
        current.parent.mkdir(parents=True)
        current.write_bytes((self.legacy / "config.json").read_bytes())

        self.migrate()

        self.assertEqual(config.load_config(current).installation_path, "/games/WARFB")
        self.assertFalse(self.legacy.exists())

    def test_given_a_second_start_when_migrating_again_then_nothing_happens(self):
        self.migrate()

        self.assertEqual(self.migrate(), [])

    def test_given_windows_when_migrating_then_nothing_moves(self):
        self.assertEqual(self.migrate("win32"), [])
        self.assertTrue((self.legacy / "config.json").is_file())
