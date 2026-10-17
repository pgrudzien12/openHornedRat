"""Programs the packaged launcher starts (innoextract, the browser) get the system's library search path."""

import os
import unittest
from unittest import mock

from whshr.launcher.external import external_environment, external_process_environment

BUNDLED = {"LD_LIBRARY_PATH": "/opt/ohr-engine/_internal", "PATH": "/usr/bin"}


class ExternalEnvironmentTests(unittest.TestCase):
    def test_given_a_packaged_launcher_then_the_library_path_from_before_the_launch_comes_back(self):
        environment = external_environment({**BUNDLED, "LD_LIBRARY_PATH_ORIG": "/usr/local/lib"}, frozen=True)

        self.assertEqual(environment["LD_LIBRARY_PATH"], "/usr/local/lib")
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", environment)
        self.assertEqual(environment["PATH"], "/usr/bin")

    def test_given_a_packaged_launcher_started_without_a_library_path_then_none_is_passed_on(self):
        self.assertNotIn("LD_LIBRARY_PATH", external_environment(BUNDLED, frozen=True))

    def test_given_a_source_checkout_then_the_environment_is_passed_on_unchanged(self):
        self.assertEqual(external_environment(BUNDLED, frozen=False), BUNDLED)

    def test_given_a_packaged_launcher_when_opening_the_browser_then_the_bundled_path_is_hidden_only_meanwhile(self):
        with mock.patch.dict(os.environ, BUNDLED, clear=True), mock.patch("sys.frozen", True, create=True):
            with external_process_environment():
                self.assertNotIn("LD_LIBRARY_PATH", os.environ)
            self.assertEqual(os.environ["LD_LIBRARY_PATH"], BUNDLED["LD_LIBRARY_PATH"])


if __name__ == "__main__":
    unittest.main()
