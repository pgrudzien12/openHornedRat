import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_given_a_missing_module_when_checking_dependencies_then_it_is_reported_unavailable(self):
        available = engine_launch.engine_dependencies_available(
            Path(sys.executable), modules=("definitely_not_a_real_module_xyz",),
        )

        self.assertFalse(available)

    def test_given_present_modules_when_checking_dependencies_then_they_are_reported_available(self):
        available = engine_launch.engine_dependencies_available(Path(sys.executable), modules=("os",))

        self.assertTrue(available)
