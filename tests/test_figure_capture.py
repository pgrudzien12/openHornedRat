"""BDD scenarios for the F2 figure capture debugging aid (whshr.figure_capture), per docs/testing.md."""
import tempfile
import unittest
from pathlib import Path

from whshr import figure_capture
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def _regiment(identifier, x, y, side, **kwargs):
    kwargs.setdefault("speed_per_tick", 1.5)
    return Regiment(identifier, identifier, x, y, 0, side, models=kwargs.pop("models", 6),
                    ranks=kwargs.pop("ranks", 2), **kwargs)


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.cavalry = _regiment(figure_capture.DEFAULT_UNIT, 100, 100, Side.PLAYER)
        self.infantry = _regiment("Infantry", 300, 100, Side.PLAYER)
        self.enemy = _regiment("Goblins", 600, 600, Side.ENEMY)
        self.battle = Battle(1000, 1000, [self.infantry, self.cavalry, self.enemy], seed=1995)

    def _capture(self, unit_id, ticks=figure_capture.CAPTURE_TICKS):
        return figure_capture.FigureCapture(self.directory, "bf001", self.battle, unit_id, ticks=ticks)

    def _files(self):
        return sorted(self.directory.glob("capture-*.log"))


class CaptureUnitTests(_Fixture):
    def test_given_a_selected_regiment_when_capturing_then_it_is_followed(self):
        self.assertEqual(figure_capture.capture_unit(self.battle, "Infantry"), "Infantry")

    def test_given_no_selection_when_capturing_then_the_default_cavalry_is_followed(self):
        self.assertEqual(figure_capture.capture_unit(self.battle, None), figure_capture.DEFAULT_UNIT)

    def test_given_no_selection_and_no_default_unit_when_capturing_then_the_first_player_regiment_is_followed(self):
        battle = Battle(1000, 1000, [_regiment("Goblins", 0, 0, Side.ENEMY), _regiment("Infantry", 300, 0, Side.PLAYER)],
                        seed=1995)
        self.assertEqual(figure_capture.capture_unit(battle, None), "Infantry")


class CaptureFileTests(_Fixture):
    def test_given_a_running_capture_when_ticks_pass_then_nothing_is_written_until_it_finishes(self):
        capture = self._capture("Infantry", ticks=3)
        for _ in range(2):
            self.battle.tick()
            capture.observe(self.battle)

        self.assertEqual(self._files(), [])
        self.assertFalse(capture.done)

        self.battle.tick()
        capture.observe(self.battle)

        self.assertTrue(capture.done)
        self.assertEqual(len(self._files()), 1)

    def test_given_a_finished_capture_then_it_lists_every_figure_on_every_tick(self):
        capture = self._capture("Infantry", ticks=4)
        while not capture.done:
            self.battle.tick()
            capture.observe(self.battle)

        text = self._files()[0].read_text(encoding="utf-8")
        self.assertEqual(text.count("== tick"), 5)  # the starting state plus four ticks
        figure_lines = [line for line in text.splitlines() if line.startswith("   #")]
        self.assertEqual(len(figure_lines), 4 * self.infantry.models)  # figures are placed on the first tick
        self.assertIn("figures not placed yet", text)
        self.assertIn("slot:", text)
        self.assertIn("end of capture", text)

    def test_given_a_moving_regiment_when_captured_then_figures_show_distance_moved(self):
        self.battle.order_move("Infantry", 300, 300)
        capture = self._capture("Infantry", ticks=5)
        while not capture.done:
            self.battle.tick()
            capture.observe(self.battle)

        text = self._files()[0].read_text(encoding="utf-8")
        self.assertIn("walk(", text)
        self.assertIn("target 300.0,300.0", text)

    def test_given_a_running_capture_when_extended_then_it_records_for_longer(self):
        capture = self._capture("Infantry", ticks=3)
        self.battle.tick()
        capture.observe(self.battle)

        capture.extend(self.battle, ticks=3)
        ticks = 1
        while not capture.done:
            self.battle.tick()
            capture.observe(self.battle)
            ticks += 1

        self.assertEqual(ticks, 6)
        text = self._files()[0].read_text(encoding="utf-8")
        self.assertIn("capture extended at tick 1 by 3 ticks", text)
        self.assertIn("ticks 0..6 ", text)

    def test_given_a_finished_capture_when_extended_then_nothing_changes(self):
        capture = self._capture("Infantry", ticks=1)
        self.battle.tick()
        capture.observe(self.battle)

        capture.extend(self.battle)

        self.assertTrue(capture.done)
        self.assertNotIn("extended", self._files()[0].read_text(encoding="utf-8"))

    def test_given_a_capture_cut_short_when_closed_then_the_partial_capture_is_written_once(self):
        capture = self._capture("Infantry")
        self.battle.tick()
        capture.observe(self.battle)

        capture.close()
        capture.close()

        files = self._files()
        self.assertEqual(len(files), 1)
        self.assertNotIn("end of capture", files[0].read_text(encoding="utf-8"))

    def test_given_a_capture_when_running_then_the_battle_is_unchanged(self):
        twin = Battle(1000, 1000, [_regiment("Infantry", 300, 100, Side.PLAYER),
                                   _regiment(figure_capture.DEFAULT_UNIT, 100, 100, Side.PLAYER),
                                   _regiment("Goblins", 600, 600, Side.ENEMY)], seed=1995)
        for battle in (self.battle, twin):
            battle.order_move("Infantry", 300, 300)
        capture = self._capture("Infantry", ticks=10)
        for _ in range(10):
            self.battle.tick()
            twin.tick()
            capture.observe(self.battle)

        self.assertEqual(self.battle.snapshot(), twin.snapshot())
        self.assertEqual(self.infantry.positions, twin.regiments["Infantry"].positions)


if __name__ == "__main__":
    unittest.main()
