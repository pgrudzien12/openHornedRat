"""Launcher screens: what the user sees when moving between the launch and installation screens."""

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from whshr.launcher.gui import LauncherApp
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


if __name__ == "__main__":
    unittest.main()
