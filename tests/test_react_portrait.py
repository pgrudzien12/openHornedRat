"""Leader-portrait pop-up and the "on screen" rule for reactions (notes/react_portrait.md, vectors in section 6)."""

import unittest

from tests.script_helpers import word
from whshr import interpreter, picking
from whshr.engine import Battle, Regiment
from whshr.portrait_popup import POPUP_TICKS, PortraitPopup, overlay_frames
from whshr.rules import Side

TEXTS = {34103: "Retreat", 34102: "Advance", 34002: "Charge", 34303: "Squeak", 34100: "a", 34101: "b"}


def unit(identifier, x, y, side=Side.PLAYER, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=10, ranks=2, points=10, **extra)


class PopupTests(unittest.TestCase):
    def test_first_reaction_takes_the_panel_for_25_ticks(self):
        popup = PortraitPopup()
        self.assertTrue(popup.offer("A", 4))
        for _ in range(POPUP_TICKS - 1):
            popup.tick()
        self.assertTrue(popup.active)
        popup.tick()
        self.assertFalse(popup.active)  # back to the compass at tick 25

    def test_later_reaction_does_not_replace_or_restart_it(self):
        popup = PortraitPopup()
        popup.offer("A", 4)
        for _ in range(5):
            popup.tick()
        self.assertFalse(popup.offer("C", 1))
        self.assertEqual((popup.unit_id, popup.ticks_left), ("A", 20))

    def test_next_reaction_shows_once_the_popup_closed(self):
        popup = PortraitPopup()
        popup.offer("A", 4)
        for _ in range(POPUP_TICKS):
            popup.tick()
        self.assertTrue(popup.offer("C", 1))
        self.assertEqual(popup.unit_id, "C")

    def test_expression_five_or_more_is_ignored(self):
        popup = PortraitPopup()
        self.assertFalse(popup.offer("A", 5))
        self.assertFalse(popup.active)


class OverlayTests(unittest.TestCase):
    def test_eight_frame_shout_mouth_sequence(self):  # expression 4: 3x1, 4x5, 1x1, hold
        mouth = [overlay_frames(4, 8, age)[1] for age in range(9)]
        self.assertEqual(mouth, [3, 4, 4, 4, 4, 4, 1, 1, 1])

    def test_six_frame_sheet_uses_its_own_set(self):  # expression 0: 1x1, 3x4, 1x1
        self.assertEqual([overlay_frames(0, 6, age)[1] for age in range(7)], [1, 3, 3, 3, 3, 1, 1])

    def test_seven_frame_phrase(self):  # expression 1: 5, 3, 1, 4x4, 1
        self.assertEqual([overlay_frames(1, 7, age)[1] for age in range(9)], [5, 3, 1, 4, 4, 4, 4, 1, 1])

    def test_eyes_blink_and_loop(self):  # expression 0: open x2, closed x2, open x5, closed x2, open x11
        eyes = [overlay_frames(0, 8, age)[0] for age in range(22)]
        self.assertEqual(eyes[:4], [2, 2, 7, 7])
        self.assertEqual(eyes[9:11], [7, 7])
        self.assertEqual(eyes[21], 2)
        self.assertEqual(overlay_frames(0, 8, 22)[0], 2)  # loops back to the start
        self.assertEqual(overlay_frames(0, 6, 2)[0], 5)  # closed frame is the last one

    def test_every_mouth_sequence_ends_at_rest(self):
        for count in (6, 7, 8):
            for expression in range(5):
                self.assertEqual(overlay_frames(expression, count, 24)[1], 1)


class ReactionPopupTests(unittest.TestCase):
    def setUp(self):
        self.a = unit("A", 0, 0, race=0)
        self.c = unit("C", 50, 0, race=0)
        self.battle = Battle(5000, 5000, [self.a, self.c], seed=1995)
        self.battle.text_resources = dict(TEXTS)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def react(self, identifier, code):
        self.interp.react(identifier, code)

    def test_unselected_player_unit_takes_the_panel_with_its_expression(self):
        self.react("A", 4)
        self.assertEqual((self.battle.portrait_popup.unit_id, self.battle.portrait_popup.expression), ("A", 4))

    def test_second_unit_gets_text_but_no_portrait(self):
        self.react("A", 4)
        self.react("C", 3)
        self.assertEqual(self.battle.portrait_popup.unit_id, "A")
        self.assertEqual([e.data["sender"] for e in self.battle.events if e.kind == "react"], ["A", "C"])

    def test_popup_closes_after_25_battle_ticks(self):
        self.react("A", 4)
        for _ in range(POPUP_TICKS):
            self.battle.tick()
        self.assertFalse(self.battle.portrait_popup.active)
        self.react("C", 3)
        self.assertEqual(self.battle.portrait_popup.unit_id, "C")

    def test_dropped_enemy_reaction_gives_no_portrait(self):
        enemy = unit("E", 0, 0, Side.ENEMY, race=0)
        battle = Battle(5000, 5000, [enemy], seed=1995)
        battle.text_resources = dict(TEXTS)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        interp.react("E", 1)  # marked "not for enemy units"
        self.assertFalse(battle.portrait_popup.active)


class OnScreenTests(unittest.TestCase):
    def make(self, view_rect, **extra):
        self.enemy = unit("E", 100, 100, Side.ENEMY, race=4, **extra)
        self.battle = Battle(5000, 5000, [self.enemy], seed=1995)
        self.battle.text_resources = dict(TEXTS)
        self.battle.set_view_rect(view_rect)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.battle.tick()  # the mark is refreshed at the end of a tick

    def shouts(self):
        self.interp.react("E", 2)
        return any(e.kind == "react" for e in self.battle.events)

    def test_enemy_inside_the_view_rectangle_reacts_and_gets_a_portrait(self):
        self.make((0, 0, 500, 500))
        self.assertTrue(self.shouts())
        self.assertEqual(self.battle.portrait_popup.unit_id, "E")

    def test_enemy_outside_the_view_rectangle_is_dropped_not_deferred(self):
        self.make((1000, 1000, 2000, 2000))
        self.assertFalse(self.shouts())
        self.assertFalse(self.battle.portrait_popup.active)
        self.battle.set_view_rect((0, 0, 500, 500))
        self.assertFalse(any(e.kind == "react" for e in self.battle.events))

    def test_hidden_enemy_in_view_is_never_on_screen(self):
        self.make((0, 0, 500, 500), hidden=True)
        self.assertFalse(self.shouts())

    def test_mark_is_the_previous_ticks_value(self):
        self.make((1000, 1000, 2000, 2000))
        self.battle.set_view_rect((0, 0, 500, 500))  # the camera moved, but no tick has run yet
        self.assertFalse(self.shouts())
        self.battle.tick()
        self.assertTrue(self.shouts())

    def test_headless_battle_falls_back_to_visible_to_player(self):
        enemy = unit("E", 100, 100, Side.ENEMY, race=4)
        battle = Battle(5000, 5000, [enemy], seed=1995)
        self.assertTrue(battle.on_screen(enemy))
        enemy.hidden = True
        self.assertFalse(battle.on_screen(enemy))

    def test_player_unit_reacts_wherever_it_is(self):
        player = unit("P", 4000, 4000, race=0)
        battle = Battle(5000, 5000, [player], seed=1995)
        battle.text_resources = dict(TEXTS)
        battle.set_view_rect((0, 0, 500, 500))
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        battle.tick()
        interp.react("P", 2)
        self.assertTrue(any(e.kind == "react" for e in battle.events))


class ViewRectTests(unittest.TestCase):
    class FakeProjection:
        pass

    def test_box_covers_camera_and_far_corners_plus_margin(self):
        original = picking.pick_ground
        corners = {0.0: (-30.0, 80.0), 640.0: (50.0, 90.0)}
        picking.pick_ground = lambda projection, px, py, height_at, **kw: corners[px]
        try:
            rect = picking.view_rect(self.FakeProjection(), 640, 480, (10.0, 20.0), lambda x, z: 0.0, margin=5.0)
        finally:
            picking.pick_ground = original
        self.assertEqual(rect, (-35.0, 15.0, 55.0, 95.0))


if __name__ == "__main__":
    unittest.main()
