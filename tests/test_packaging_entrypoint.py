"""The frozen executable opens the launcher while retaining direct engine use."""

import importlib.util
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


ENTRYPOINT = Path(__file__).resolve().parents[1] / "packaging" / "entrypoint.py"


class PackageEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.main = runpy.run_path(str(ENTRYPOINT), run_name="package_test")["main"]

    @unittest.skipIf(importlib.util.find_spec("tkinter") is None, "the launcher GUI needs tkinter")
    def test_no_arguments_open_launcher(self):
        with patch("whshr.launcher.gui.main") as launcher:
            self.assertEqual(self.main([]), 0)
        launcher.assert_called_once_with()

    def test_version_switch_prints_the_version_also_through_the_macos_wrapper(self):
        for args in (["--version"], ["--engine", "--version"]):
            with self.subTest(args), patch("whshr.__main__.main") as engine, \
                    patch("builtins.print") as printed:
                self.assertEqual(self.main(args), 0)
            engine.assert_not_called()
            self.assertIn("Open Horned Rat", printed.call_args.args[0])

    def test_engine_switch_runs_bundled_engine(self):
        with patch("whshr.__main__.main", return_value=0) as engine:
            self.assertEqual(self.main(["--engine", "/game"]), 0)
        engine.assert_called_once_with(["engine", "/game"])

    def test_existing_path_argument_remains_engine_command(self):
        with patch("whshr.__main__.main", return_value=0) as engine:
            self.assertEqual(self.main(["/game"]), 0)
        engine.assert_called_once_with(["engine", "/game"])
