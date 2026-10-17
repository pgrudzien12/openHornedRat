"""Poking the rat on the launcher portrait types the caravan's reaction line, then clears it."""

import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from whshr.launcher import reaction, updates
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
    with_update = False

    def check(self):
        return self.release

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

        self.release = updates.Release("v9.0.0", "https://example.invalid/release")
        # Short timings keep the scenario quick; the rates themselves are covered by ReactionLineTests.
        for target, value in (("whshr.launcher.reaction.CHAR_MILLISECONDS", 5),
                              ("whshr.launcher.reaction.HOLD_MILLISECONDS", 100),
                              ("whshr.launcher.gui.NOTICE_RETURN_MS", 200)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = LauncherApp(self.root, config_path=config, reaction_text=fake_text,
                               update_check=self.check if self.with_update else None)
        if self.app.portrait is None:
            raise unittest.SkipTest("the portrait art is missing")
        self.root.update()

    def tearDown(self):
        for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.tk.call("after", "cancel", job)  # typing and polling timers must not fire into a destroyed window
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


class UpdateNoticeTests(PortraitPokeTests):
    """With a newer release out, its notice holds the portrait's line until the rat is poked."""

    with_update = True

    def setUp(self):
        super().setUp()
        self.notice = updates.notice_text(self.release)

    def test_given_a_newer_release_then_its_notice_is_typed_and_stays(self):
        self.wait_for({self.notice})
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            self.root.update()
        self.assertEqual(self.shown(), {self.notice})

    def test_given_the_notice_when_the_rat_is_poked_then_the_reaction_replaces_it_and_the_notice_returns(self):
        self.wait_for({self.notice})
        left, top, right, bottom = FACE_BOX
        self.poke((left + right) // 2, (top + bottom) // 2)

        self.wait_for({"Hey you"})
        self.wait_for({""})
        self.wait_for({self.notice})

    def test_given_the_notice_when_it_is_clicked_then_the_release_page_opens(self):
        self.wait_for({self.notice})
        left, top, right, bottom = self.app.portrait.bbox(self.app.portrait.find_all()[-1])

        with mock.patch("whshr.launcher.gui.webbrowser.open") as opened:
            self.poke((left + right) // 2, (top + bottom) // 2)

        opened.assert_called_once_with(self.release.url)

    def test_given_the_portrait_away_from_the_face_when_poked_then_nothing_is_said(self):
        self.skipTest("covered by PortraitPokeTests; here the notice occupies the line")

    def test_given_the_face_when_poked_then_the_line_is_typed_in_red_and_then_cleared(self):
        self.skipTest("covered by PortraitPokeTests; here the notice returns after the reaction")


if __name__ == "__main__":
    unittest.main()
