"""Launcher screens: what the user sees when moving between the launch and installation screens."""

import json
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from whshr.launcher.gui import LauncherApp, validating_text
from whshr.launcher.theme import ImageButton


def make_root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as error:  # no display available
        raise unittest.SkipTest(f"the launcher window needs a display: {error}") from error
    return root


def widgets(parent: tk.Misc):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


class ChangeInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = Path(self.temp.name) / "WARFB"
        for folder in ("FILE/BINARY", "REMOTE/BINARY"):
            (self.game / folder).mkdir(parents=True)
        self.config = Path(self.temp.name) / "launcher.json"
        self.config.write_text(json.dumps({"installation_path": str(self.game)}), encoding="utf-8")
        self.root = make_root()
        self.app = LauncherApp(self.root, config_path=self.config)
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self.temp.cleanup()

    def press(self, label: str):
        button = next(widget for widget in widgets(self.root) if isinstance(widget, ImageButton)
                      and label in [widget.itemcget(item, "text") for item in widget.find_all()
                                    if widget.type(item) == "text"])
        button.event_generate("<ButtonPress-1>", x=5, y=5)
        button.event_generate("<ButtonRelease-1>", x=5, y=5)
        self.root.update()

    def test_given_a_recognized_installation_when_change_is_pressed_then_its_path_is_already_filled_in(self):
        self.press("Change...")
        entries = [widget for widget in widgets(self.root) if isinstance(widget, tk.Entry)]
        self.assertEqual([entry.get() for entry in entries], [str(self.game)])

    def status_texts(self) -> list[str]:
        return [widget.cget("text") for widget in widgets(self.root)
                if isinstance(widget, tk.Label) and widget.cget("text").startswith("Validating")]

    def test_given_a_slow_validation_when_it_runs_then_validating_shows_until_it_finishes(self):
        release = threading.Event()

        def slow_check(_path):  # stands in for the real installation check, which takes seconds
            release.wait(5)
            return False, ["a check failed"]

        self.press("Change...")
        with mock.patch("whshr.launcher.validate.full_check", slow_check):
            self.press("Validate & continue")
            self.assertEqual(self.status_texts(), ["Validating."])
            release.set()
            deadline = time.monotonic() + 5
            while self.status_texts() and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.02)
        self.assertEqual(self.status_texts(), [])


class ValidatingTextTests(unittest.TestCase):
    def test_given_successive_animation_steps_then_the_dots_grow_from_one_to_three_and_repeat(self):
        self.assertEqual([validating_text(step) for step in range(5)],
                         ["Validating.", "Validating..", "Validating...", "Validating.", "Validating.."])


if __name__ == "__main__":
    unittest.main()
