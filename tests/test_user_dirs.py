"""Where saves live: flag, then OSH_SAVE_DIR, then the platform's per-user data directory."""
import unittest
from pathlib import Path

from whshr.user_dirs import default_save_dir, resolve_save_dir

HOME = Path("/home/tester")


class DefaultSaveDirTests(unittest.TestCase):
    def test_given_linux_without_xdg_then_local_share(self):
        self.assertEqual(default_save_dir({}, "linux", HOME), HOME / ".local/share/ohr/saves")

    def test_given_linux_with_absolute_xdg_data_home_then_it_is_used(self):
        self.assertEqual(default_save_dir({"XDG_DATA_HOME": "/data"}, "linux", HOME), Path("/data/ohr/saves"))

    def test_given_linux_with_relative_xdg_data_home_then_it_is_ignored(self):
        self.assertEqual(default_save_dir({"XDG_DATA_HOME": "rel"}, "linux", HOME), HOME / ".local/share/ohr/saves")

    def test_given_windows_then_appdata(self):
        self.assertEqual(default_save_dir({"APPDATA": "C:/Roam"}, "win32", HOME), Path("C:/Roam/ohr/saves"))

    def test_given_windows_without_appdata_then_roaming_under_home(self):
        self.assertEqual(default_save_dir({}, "win32", HOME), HOME / "AppData/Roaming/ohr/saves")

    def test_given_macos_then_application_support(self):
        self.assertEqual(default_save_dir({}, "darwin", HOME), HOME / "Library/Application Support/ohr/saves")


class ResolveSaveDirTests(unittest.TestCase):
    def test_given_flag_and_env_then_the_flag_wins(self):
        self.assertEqual(resolve_save_dir("/flag", {"OSH_SAVE_DIR": "/env"}, "linux", HOME), Path("/flag"))

    def test_given_only_env_then_env_wins_over_the_platform_default(self):
        self.assertEqual(resolve_save_dir(None, {"OSH_SAVE_DIR": "/env"}, "linux", HOME), Path("/env"))

    def test_given_empty_env_then_the_platform_default(self):
        self.assertEqual(resolve_save_dir(None, {"OSH_SAVE_DIR": ""}, "linux", HOME), HOME / ".local/share/ohr/saves")


if __name__ == "__main__":
    unittest.main()
