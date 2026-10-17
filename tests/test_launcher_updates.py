"""The launcher's update check against the latest GitHub release."""

import json
import unittest

from whshr.launcher import updates


def answer(**release):
    def fetch(url, timeout):
        assert url == updates.LATEST_RELEASE_API and timeout > 0
        return json.dumps(release).encode()
    return fetch


class NewerReleaseTests(unittest.TestCase):
    def test_given_a_newer_release_then_it_is_offered_with_its_page(self):
        found = updates.newer_release("1.0.0", answer(tag_name="v1.1.0", html_url="https://github.com/x/releases/v1.1.0"), {})

        self.assertEqual(found, updates.Release("v1.1.0", "https://github.com/x/releases/v1.1.0"))
        self.assertIn("1.1.0", updates.notice_text(found))

    def test_given_the_running_release_or_an_older_one_then_nothing_is_offered(self):
        for tag in ("v1.0.0", "v0.9.0"):
            with self.subTest(tag):
                self.assertIsNone(updates.newer_release("1.0.0", answer(tag_name=tag, html_url="https://x"), {}))

    def test_given_a_draft_or_prerelease_then_nothing_is_offered(self):
        for flag in ("draft", "prerelease"):
            with self.subTest(flag):
                fetch = answer(tag_name="v2.0.0", html_url="https://x", **{flag: True})
                self.assertIsNone(updates.newer_release("1.0.0", fetch, {}))

    def test_given_no_network_or_a_strange_answer_then_nothing_is_offered(self):
        def offline(url, timeout):
            raise OSError("offline")

        def garbage(url, timeout):
            return b"<html>"

        for fetch in (offline, garbage, answer(message="API rate limit exceeded")):
            with self.subTest(fetch):
                self.assertIsNone(updates.newer_release("1.0.0", fetch, {}))

    def test_given_a_release_page_that_is_not_https_then_the_releases_page_is_linked(self):
        found = updates.newer_release("1.0.0", answer(tag_name="v1.1.0", html_url="javascript:alert(1)"), {})

        self.assertEqual(found.url, updates.RELEASES_PAGE)

    def test_given_the_check_is_turned_off_then_nothing_is_asked(self):
        def must_not_fetch(url, timeout):
            raise AssertionError("the check is off")

        self.assertIsNone(updates.newer_release("1.0.0", must_not_fetch, {updates.DISABLE_ENV: "1"}))


if __name__ == "__main__":
    unittest.main()
