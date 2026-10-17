"""The engine's version: derived from release tags, and compared against the latest release."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from whshr import version


@unittest.skipIf(shutil.which("git") is None, "needs git")
class VersionFromGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.commit()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self) -> str:
        self.git("commit", "-q", "--allow-empty", "-m", "change")
        return self.git("rev-parse", "--short=8", "HEAD")

    def test_given_no_release_tag_then_the_version_counts_every_commit(self):
        head = self.commit()

        self.assertEqual(version.from_git(self.repo), f"0.0.0+git2.{head}")

    def test_given_a_tagged_release_then_its_build_carries_the_tag_and_later_builds_count_from_it(self):
        self.git("tag", "-a", "v1.2.0", "-m", "release")
        self.assertEqual(version.from_git(self.repo), "1.2.0")

        head = self.commit()

        self.assertEqual(version.from_git(self.repo), f"1.2.0+git1.{head}")

    def test_given_no_git_checkout_then_there_is_no_git_version(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(version.from_git(plain))


class NewerReleaseTests(unittest.TestCase):
    def test_given_release_and_running_versions_then_only_a_real_newer_release_counts(self):
        cases = {
            ("v1.1.0", "1.0.0"): True,
            ("v1.0.1", "1.0.0+git3.abcdef12"): True,   # a build after 1.0.0 is still older than 1.0.1
            ("v1.0.0", "1.0.0+git12.abcdef12"): False,  # ... and newer than 1.0.0 itself
            ("v1.0.0", "1.0.0-rc1"): True,              # the release beats its release candidate
            ("v1.0.0", "1.0.0"): False,
            ("v1.0", "1.0.0"): False,
            ("v0.9.0", "1.0.0"): False,
            ("v1.1.0-rc1", "1.0.0"): False,             # prereleases are never offered
            ("v1.0.0", version.UNKNOWN): False,         # an unknown build cannot tell
            ("nightly", "1.0.0"): False,
        }
        for (tag, current), expected in cases.items():
            with self.subTest(tag=tag, current=current):
                self.assertIs(version.is_newer_release(tag, current), expected)


if __name__ == "__main__":
    unittest.main()
