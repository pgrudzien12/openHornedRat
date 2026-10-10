"""The battle compass: heading tape, wind strip and lightning warning (notes/battle_compass.md)."""

import unittest

from tests.test_hud import pygame  # noqa: F401  (the HUD module needs pygame or its stub)
from whshr.frontend import hud


class HeadingTapeTests(unittest.TestCase):
    def test_the_report_vectors(self):
        # yaw 180 looks at minimap-up: N centred; 0 looks south.
        for yaw, src_x in ((0, 83), (45, 114), (90, 146), (180, 210), (270, 18), (359, 81)):
            with self.subTest(yaw=yaw):
                self.assertEqual(hud.heading_tape_offset(yaw), src_x)

    def test_the_slice_wraps_past_the_tapes_right_edge(self):
        width, height = 4, 1
        rgba = bytes(value for column in range(width) for value in (column, 0, 0, 255))
        self.assertEqual(hud.wrapped_slice(rgba, width, height, 3, 3)[::4], bytes((3, 0, 1)))


class WindStripTests(unittest.TestCase):
    def test_the_report_vectors(self):
        for ms, src_x in ((0, 232), (25000, 103), (40000, 180), (49999, 231), (50000, 232)):
            with self.subTest(ms=ms):
                self.assertEqual(hud.wind_strip_offset(ms), src_x)

    def test_lightning_flickers_only_in_the_last_ten_seconds(self):
        self.assertIsNone(hud.lightning_frame(39999))
        self.assertEqual(hud.lightning_frame(40000), hud.LIGHTNING_STEPS[0])
        self.assertIsNone(hud.lightning_frame(41000))
        self.assertEqual(hud.lightning_frame(42000), hud.LIGHTNING_STEPS[2])
        self.assertIsNone(hud.lightning_frame(50000))  # the next cycle starts calm


if __name__ == "__main__":
    unittest.main()
