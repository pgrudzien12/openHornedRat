"""Glue screens apply the cursors their hotspot data names (issue #150; notes/glue_keywords.md §3.5): the pressed
hotspot's ``altcursor``, else the hovered hotspot's ``cursor``, else the arrow; one controller owns the cursor."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame

from whshr.frontend.cursors import CursorController, cursor_for_hotspots
from whshr.frontend.glue_view import GlueView
from whshr.glue_content import GlueContent
from whshr.glue_render import build_render_model
from whshr.glue_runtime import WindowInstance
from whshr.paths import Installation

HOTSPOTS = """[HOTSPOT]
set:x=%d
set:y=1
set:vx=9
set:vy=9
%s
[HOTSPOT]
set:x=%d
set:y=1
set:vx=9
set:vy=9
%s
"""
GRAB_PAIR = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n" + HOTSPOTS % (
    1, "cursor:HandOpenCursor\naltcursor:HandCloseCursor\nres:GRAB", 20, "cursor:HandCursor\nres:POINT") + "[END]"
REACTION = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n" + HOTSPOTS % (
    1, "set:res=155\naltcursor:HandCursor", 20, "cursor:HandCursor\nres:POINT") + "[END]"
RESOURCES = {"GRABWINDOW": GRAB_PAIR, "REACTIONWINDOW": REACTION}
STRINGS = {"BRTXT": {155: "Stop that"}}


def hotspots(window):
    content = GlueContent.from_data(resources=RESOURCES, strings=STRINGS)
    return build_render_model(content, WindowInstance(window, None, 0, [])).hotspots


class HotspotCursorDataTests(unittest.TestCase):
    def test_given_a_grab_pair_hotspot_then_both_cursors_are_kept(self):
        grab, point = hotspots("GRABWINDOW")

        self.assertEqual((grab.cursor, grab.alt_cursor), ("HandOpenCursor", "HandCloseCursor"))
        self.assertEqual((point.cursor, point.alt_cursor), ("HandCursor", None))

    def test_given_a_press_only_reaction_hotspot_then_it_has_an_altcursor_and_no_hover_cursor(self):
        reaction, point = hotspots("REACTIONWINDOW")

        self.assertEqual((reaction.cursor, reaction.alt_cursor), (None, "HandCursor"))
        self.assertEqual((point.cursor, point.alt_cursor), ("HandCursor", None))


class CursorRuleTests(unittest.TestCase):
    def test_given_hotspots_then_the_pressed_altcursor_wins_over_the_hovered_cursor(self):
        grab, point = hotspots("GRABWINDOW")
        reaction, _ = hotspots("REACTIONWINDOW")

        self.assertIsNone(cursor_for_hotspots(None, None))
        self.assertEqual(cursor_for_hotspots(grab, None), "HandOpenCursor")  # hover
        self.assertEqual(cursor_for_hotspots(grab, grab), "HandCloseCursor")  # pressed
        self.assertEqual(cursor_for_hotspots(point, None), "HandCursor")
        self.assertEqual(cursor_for_hotspots(point, point), "HandCursor")  # no altcursor: the hover cursor stays
        self.assertIsNone(cursor_for_hotspots(reaction, None))  # reaction: the arrow until pressed
        self.assertEqual(cursor_for_hotspots(reaction, reaction), "HandCursor")
        self.assertIsNone(cursor_for_hotspots(None, None))  # leaving every hotspot restores the arrow


class CursorControllerTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("pygame.mouse.set_cursor")
        self.set_cursor = patcher.start()
        self.addCleanup(patcher.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.empty_installation = Installation(temporary.name)  # exists, but has no game files

    def _controller(self, default=None):
        controller = CursorController(self.empty_installation, default=default)
        controller.cursors = SimpleNamespace(names=[], set=lambda name: controller.cursors.names.append(name))
        return controller

    def test_given_the_same_cursor_twice_then_it_is_set_once(self):
        controller = self._controller()

        controller.show("HandCursor")
        controller.show("HandCursor")
        controller.show("HandOpenCursor")

        self.assertEqual(controller.cursors.names, ["HandCursor", "HandOpenCursor"])

    def test_given_nothing_to_show_then_the_default_or_the_arrow_is_used(self):
        plain = self._controller()
        plain.show("HandCursor")
        plain.show(None)
        self.set_cursor.assert_called_with(pygame.SYSTEM_CURSOR_ARROW)

        sword = self._controller(default="SWORDCURSOR")
        sword.show(None)
        self.assertEqual(sword.cursors.names, ["SWORDCURSOR"])

    def test_given_a_screen_going_away_then_the_arrow_is_restored_and_the_next_show_is_applied(self):
        controller = self._controller()
        controller.show("HandCursor")

        controller.release()
        self.set_cursor.assert_called_with(pygame.SYSTEM_CURSOR_ARROW)
        controller.show("HandCursor")

        self.assertEqual(controller.cursors.names, ["HandCursor", "HandCursor"])

    def test_given_a_cursor_that_cannot_be_loaded_then_the_system_arrow_is_used(self):
        controller = CursorController(self.empty_installation)

        controller.show("HandCursor")  # no WHSHR.EXE there: the load fails

        self.set_cursor.assert_called_with(pygame.SYSTEM_CURSOR_ARROW)

    def test_given_no_installation_then_the_arrow_is_used(self):
        controller = CursorController(None)

        controller.show("HandCursor")

        self.set_cursor.assert_called_with(pygame.SYSTEM_CURSOR_ARROW)


class GlueViewCursorTests(unittest.TestCase):
    """The view feeds hover and press into the controller, on more than one window."""

    def _view(self, window):
        view = GlueView.__new__(GlueView)
        model = build_render_model(GlueContent.from_data(resources=RESOURCES, strings=STRINGS),
                                   WindowInstance(window, None, 0, []))
        view.models = (model,)
        view.mission_rows, view.panel_buttons = [], []
        view.pressed, view._pressed_button = None, None
        view.hover_hint = None
        view.scene = SimpleNamespace(campaign=None)
        view.cursors = SimpleNamespace(shown=[], update=lambda hovered, pressed: view.cursors.shown.append(
            cursor_for_hotspots(hovered, pressed)))
        view._native_point = lambda position: position
        view._refresh_hint = lambda: None
        return view

    @staticmethod
    def _event(kind, position):
        return SimpleNamespace(type=kind, pos=position, button=1)

    def test_given_a_grab_hotspot_then_hover_shows_open_press_shows_closed_release_shows_open_again(self):
        view = self._view("GRABWINDOW")
        over = (5, 5)

        view.events(self._event(pygame.MOUSEMOTION, over))
        view.events(self._event(pygame.MOUSEBUTTONDOWN, over))
        view.events(self._event(pygame.MOUSEBUTTONUP, over))
        view.events(self._event(pygame.MOUSEMOTION, (300, 300)))

        self.assertEqual(view.cursors.shown, ["HandOpenCursor", "HandCloseCursor", "HandOpenCursor", None])

    def test_given_a_reaction_hotspot_then_the_hand_shows_only_while_pressed(self):
        view = self._view("REACTIONWINDOW")
        over = (5, 5)

        view.events(self._event(pygame.MOUSEMOTION, over))
        view.events(self._event(pygame.MOUSEBUTTONDOWN, over))
        view.events(self._event(pygame.MOUSEBUTTONUP, over))

        self.assertEqual(view.cursors.shown, [None, "HandCursor", None])


WARFB = os.environ.get("WARFB")


@unittest.skipUnless(WARFB and Path(WARFB).is_dir(), "WARFB is not set")
class RealCursorDataTests(unittest.TestCase):
    def test_given_the_installation_then_every_cursor_the_scripts_name_decodes_and_only_three_names_occur(self):
        from whshr.frontend.cursors import GameCursors

        content = GlueContent(Installation(WARFB))
        names = set()
        for resource in content.resources.values():
            for record in getattr(resource, "records", ()):
                for field in getattr(record, "fields", ()):
                    if field.command in ("cursor", "altcursor"):
                        names.add(field.argument)
        cursors = GameCursors(Installation(WARFB))

        self.assertEqual(names, {"HandCursor", "HandOpenCursor", "HandCloseCursor"})
        for name in names:
            self.assertIsNotNone(cursors._load(name))  # decodes from the game's own cursor resources


if __name__ == "__main__":
    unittest.main()
