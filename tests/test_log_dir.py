"""Where battle and campaign logs go by default: the checkout's logs/, or beside the saves in a package."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from whshr.__main__ import default_log_dir
from whshr.user_dirs import default_save_dir

CHECKOUT = Path(__file__).resolve().parents[1]


class DefaultLogDirTests(unittest.TestCase):
    def test_given_a_source_checkout_then_logs_go_to_its_logs_folder(self):
        self.assertEqual(default_log_dir(frozen=False), CHECKOUT / "logs")

    def test_given_a_packaged_engine_then_logs_sit_beside_the_saves(self):
        self.assertEqual(default_log_dir(frozen=True), default_save_dir().parent / "logs")

    @unittest.skipUnless(sys.platform.startswith("linux"), "XDG_DATA_HOME applies on Linux")
    def test_given_a_packaged_engine_on_linux_with_xdg_data_home_then_logs_follow_it(self):
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/data"}):
            self.assertEqual(default_log_dir(frozen=True), Path("/data/ohr/logs"))


if __name__ == "__main__":
    unittest.main()
