"""Poking the rat on the launcher portrait types the caravan's reaction line, then clears it."""

import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

from whshr.launcher import reaction
from whshr.launcher.gui import FACE_BOX, LauncherApp


class ReactionLineTests(unittest.TestCase):
    def test_given_a_line_when_time_passes_then_it_types_at_twenty_characters_a_second_holds_and_clears(self):
        line = reaction.ReactionLine("Hey you")  # 7 characters: typed after 350 ms, cleared 750 ms later

        self.assertEqual(line.advance(0), "")
        self.assertEqual(line.advance(100), "He")
        self.assertEqual(line.advance(250), "Hey you")
        self.assertEqual(line.advance(749), "Hey you")
        self.assertIsNone(line.advance(1))

    def test_given_no_readable_installation_when_loading_the_line_then_there_is_none(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(reaction.load_reaction_text(empty))


class PortraitPokeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:  # no display available
            raise unittest.SkipTest(f"the launcher window needs a display: {error}") from error
        self.temp = tempfile.TemporaryDirectory()
        config = Path(self.temp.name) / "launcher.json"
        config.write_text(json.dumps({"installation_path": "/games/WARFB"}), encoding="utf-8")
        self.asked: list[str] = []

        def fake_text(path):  # stands in for reading the line from the installation
            self.asked.append(path)
            return "Hey you"

        self.app = LauncherApp(self.root, config_path=config, reaction_text=fake_text)
        if self.app.portrait is None:
            raise unittest.SkipTest("the portrait art is missing")
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self.temp.cleanup()

    def shown(self) -> set[str]:
        canvas = self.app.portrait
        return {canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"}

    def wait_for(self, texts: set[str], seconds: float = 5) -> None:
        deadline = time.monotonic() + seconds
        while self.shown() != texts and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertEqual(self.shown(), texts)

    def poke(self, x: int, y: int) -> None:
        self.app.portrait.event_generate("<ButtonPress-1>", x=x, y=y)
        self.root.update()

    def test_given_the_face_when_poked_then_the_line_is_typed_in_red_and_then_cleared(self):
        left, top, right, bottom = FACE_BOX
        self.poke((left + right) // 2, (top + bottom) // 2)

        self.wait_for({"Hey you"})
        self.assertIn(reaction.REACTION_COLOUR, {self.app.portrait.itemcget(item, "fill")
                                                 for item in self.app.portrait.find_all()
                                                 if self.app.portrait.type(item) == "text"})
        self.wait_for({""})
        self.assertEqual(self.asked, ["/games/WARFB"])

    def test_given_the_portrait_away_from_the_face_when_poked_then_nothing_is_said(self):
        self.poke(FACE_BOX[2] + 50, FACE_BOX[3] + 200)

        self.assertEqual(self.shown(), {""})


if __name__ == "__main__":
    unittest.main()
