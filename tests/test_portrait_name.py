"""The speaker's name label on a portrait window while the pointer is over the picture (notes/glue_portraits.md §3.6)."""

from types import SimpleNamespace
import unittest
from unittest import mock

import pygame

from whshr.frontend.glue_view import GlueView
from whshr.frontend.gpu import OUTLINE
from whshr.glue_runtime import GlueRuntime


class FakeFont:
    """PCTEXT stand-in: every character 6 px wide, 12 px high."""

    def __init__(self, _font):
        pass

    def size(self, text):
        return 6 * len(text), 12


class FakeLabel:
    def __init__(self, colour):
        self.colour, self.lines, self.released = colour, None, False

    def set_lines(self, lines):
        self.lines = tuple(lines)

    def release(self):
        self.released = True


def view_with(*portraits):
    view = GlueView.__new__(GlueView)
    view.portrait_names = list(portraits)
    view.pointer, view.name_label, view._drawn_name = None, None, None
    view.scene = SimpleNamespace(font=lambda slot: slot)
    view.gpu = SimpleNamespace(text=lambda size, font, color, **_: FakeLabel(color))
    return view


DIETRICH = ("ScribeWindow", (12, 12, 120, 152), "Dietrich", "red")


class PortraitNameLabelTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("whshr.frontend.glue_view.BitmapFont", FakeFont)
        patcher.start()
        self.addCleanup(patcher.stop)

    def hover(self, view, point):
        view.pointer = point
        view._refresh_portrait_name()
        return view.name_label

    def test_given_the_pointer_on_the_picture_then_the_name_is_centred_on_the_window_above_its_bottom(self):
        view = view_with(DIETRICH)

        label, (x, y) = self.hover(view, (70, 80))

        self.assertEqual((label.lines, label.colour), (("Dietrich",), (255, 0, 0)))
        # tw = 48: x = (144 - 48) // 2 = 48, y = 152 - 12 = 140; the label keeps OUTLINE px around the glyphs.
        self.assertEqual((x + OUTLINE, y + OUTLINE), (48, 140))

    def test_the_picture_box_counts_its_edges_and_nothing_outside(self):
        view = view_with(DIETRICH)
        for point, shown in (((12, 12), True), ((11, 80), False), ((132, 164), True), ((70, 165), False)):
            with self.subTest(point=point):
                self.assertEqual(self.hover(view, point) is not None, shown)

    def test_given_the_pointer_leaves_then_the_label_goes_at_once(self):
        view = view_with(DIETRICH)
        label, _ = self.hover(view, (70, 80))

        self.hover(view, None)

        self.assertIsNone(view.name_label)
        self.assertTrue(label.released)

    def test_given_two_windows_then_only_the_one_under_the_pointer_shows_its_name(self):
        ceridan = ("ceridan2Window", (12, 212, 120, 152), "Ceridan", "lgray")
        view = view_with(DIETRICH, ceridan)

        label, _ = self.hover(view, (70, 300))

        self.assertEqual((label.lines, label.colour), (("Ceridan",), (192, 192, 192)))


class PortraitLabelTextTests(unittest.TestCase):
    def runtime(self, sprite_name=None):
        runtime = GlueRuntime.__new__(GlueRuntime)
        runtime.content = SimpleNamespace(portrait_sprite_name=lambda position: sprite_name)
        runtime.portrait_index = lambda window, index: 2
        return runtime

    def test_the_label_is_the_blocks_name_as_written(self):
        self.assertEqual(self.runtime().portrait_label("BernardIWindow", "Cpt Bernard", 19), "Cpt Bernard")

    def test_a_block_without_a_name_has_no_label(self):
        self.assertIsNone(self.runtime().portrait_label("W", None, 4))
        self.assertIsNone(self.runtime().portrait_label("W", "", 4))

    def test_an_index_minus_one_block_shows_the_speakers_sprite_name(self):
        self.assertEqual(self.runtime("Commander").portrait_label("AmbushWindow", "Commander", -1), "Commander")
        self.assertEqual(self.runtime("Scribe").portrait_label("AmbushWindow", "Commander", -1), "Scribe")


if __name__ == "__main__":
    pygame.init()
    unittest.main()
