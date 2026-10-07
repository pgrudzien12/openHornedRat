import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from whshr.launcher import engine_launch


class EngineLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository_root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_given_no_venv_when_resolving_the_engine_python_then_the_launchers_own_interpreter_is_used(self):
        found = engine_launch.find_engine_python(self.repository_root)

        self.assertEqual(found, Path(sys.executable))

    def test_given_a_venv_when_resolving_the_engine_python_then_its_interpreter_is_used(self):
        relative = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        venv_python = self.repository_root / ".venv" / relative
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()

        found = engine_launch.find_engine_python(self.repository_root)

        self.assertEqual(found, venv_python)

    def test_frozen_launcher_uses_its_own_executable_even_if_a_venv_exists(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", "/Applications/OHR.app/Contents/MacOS/ohr-engine"):
            found = engine_launch.find_engine_python(self.repository_root)

        self.assertEqual(found, Path("/Applications/OHR.app/Contents/MacOS/ohr-engine"))

    def test_given_a_missing_module_when_checking_dependencies_then_it_is_reported_unavailable(self):
        available = engine_launch.engine_dependencies_available(
            Path(sys.executable), modules=("definitely_not_a_real_module_xyz",),
        )

        self.assertFalse(available)

    def test_given_present_modules_when_checking_dependencies_then_they_are_reported_available(self):
        available = engine_launch.engine_dependencies_available(Path(sys.executable), modules=("os",))

        self.assertTrue(available)

    def test_frozen_launcher_uses_bundled_dependencies(self):
        with patch.object(sys, "frozen", True, create=True):
            self.assertTrue(engine_launch.engine_dependencies_available("/Applications/OHR.app/Contents/MacOS/ohr-engine"))


class BuildCommandTests(unittest.TestCase):
    def test_given_no_battle_or_options_when_building_the_command_then_it_is_a_plain_engine_start(self):
        command = engine_launch.build_command("/game", python_path="py")

        self.assertEqual(command, ["py", "-m", "whshr", "engine", "/game"])

    def test_given_a_battle_and_all_options_when_building_the_command_then_every_flag_is_present(self):
        options = engine_launch.LaunchOptions(no_battles=True, trace=True, skip_intro=True)

        command = engine_launch.build_command("/game", "BF001", options, python_path="py")

        self.assertEqual(command, ["py", "-m", "whshr", "engine", "/game", "--battle", "BF001",
                                   "--skip-intro", "--no-battle"])

    def test_frozen_launcher_starts_the_bundled_engine_mode(self):
        with patch.object(sys, "frozen", True, create=True):
            command = engine_launch.build_command("/game", "BF001", python_path="/Applications/OHR.app/Contents/MacOS/ohr-engine")

        self.assertEqual(command, ["/Applications/OHR.app/Contents/MacOS/ohr-engine", "--engine", "/game",
                                   "--battle", "BF001"])

    def test_given_trace_when_building_the_environment_then_the_trace_variable_is_set(self):
        traced = engine_launch.build_environment(engine_launch.LaunchOptions(trace=True), base={})
        plain = engine_launch.build_environment(engine_launch.LaunchOptions(), base={})

        self.assertEqual(traced["WHSHR_TRACE_SCRIPTS"], "1")
        self.assertNotIn("WHSHR_TRACE_SCRIPTS", plain)

    def test_given_any_options_when_building_the_environment_then_the_checkout_is_on_the_import_path(self):
        environment = engine_launch.build_environment(base={"PYTHONPATH": "/other"})

        self.assertEqual(environment["PYTHONPATH"].split(os.pathsep),
                         [str(engine_launch.REPOSITORY_ROOT), "/other"])

    def test_frozen_launcher_does_not_add_a_source_checkout_to_pythonpath(self):
        with patch.object(sys, "frozen", True, create=True):
            environment = engine_launch.build_environment(base={})

        self.assertNotIn("PYTHONPATH", environment)
