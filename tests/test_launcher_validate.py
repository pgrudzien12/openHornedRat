import tempfile
import unittest
from pathlib import Path

from whshr.launcher import validate


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_given_an_empty_directory_when_quick_validated_then_it_fails_without_running_the_full_check(self):
        self.assertFalse(validate.quick_validate(self.root))

    def test_given_a_structurally_incomplete_installation_when_fully_checked_then_it_reports_failure_lines(self):
        (self.root / "FILE" / "BINARY").mkdir(parents=True)
        (self.root / "REMOTE" / "BINARY").mkdir(parents=True)

        passed, lines = validate.full_check(self.root)

        self.assertFalse(passed)
        self.assertTrue(any(line.startswith("ERROR") for line in lines))
