"""The frozen executable opens the launcher while retaining direct engine use."""

import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


ENTRYPOINT = Path(__file__).resolve().parents[1] / "packaging" / "entrypoint.py"


class PackageEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.main = runpy.run_path(str(ENTRYPOINT), run_name="package_test")["main"]

    def test_no_arguments_open_launcher(self):
        with patch("whshr.launcher.gui.main") as launcher:
            self.assertEqual(self.main([]), 0)
        launcher.assert_called_once_with()

    def test_engine_switch_runs_bundled_engine(self):
        with patch("whshr.__main__.main", return_value=0) as engine:
            self.assertEqual(self.main(["--engine", "/game"]), 0)
        engine.assert_called_once_with(["engine", "/game"])

    def test_existing_path_argument_remains_engine_command(self):
        with patch("whshr.__main__.main", return_value=0) as engine:
            self.assertEqual(self.main(["/game"]), 0)
        engine.assert_called_once_with(["engine", "/game"])
