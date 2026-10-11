"""The battle view's camera controls: the panel's rotate and zoom buttons held with either mouse button, and the
right mouse button on the minimap pointing the camera."""

import importlib.util
import unittest
from types import SimpleNamespace

if importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl"):
    import pygame

    from whshr.camera import MAX_DISTANCE, MIN_DISTANCE, BattleCamera
    from whshr.frontend.battle_view import BattleView


class _FakeHud:
    """Only what the camera controls touch: a fixed button under (0, 0) and a 100x100 minimap at (500, 0) that
    maps one pixel to 10 world units."""

    def __init__(self, button: str | None = None) -> None:
        self.button = button
        self.pressed: str | None = None

    def hit_test(self, pos):
        return self.button if tuple(pos) == (0, 0) else None

    def set_pressed(self, name):
        self.pressed = name

    def minimap_position(self, pos):
        x, y = pos
        return ((x - 500) * 10.0, y * 10.0) if 500 <= x < 600 and 0 <= y < 100 else None

    def occupies(self, pos):
        return tuple(pos) == (0, 0) or self.minimap_position(pos) is not None

    def click_minimap_tab(self, pos):
        return None

    def minimap_regiment_at(self, pos):
        return None


@unittest.skipUnless(importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl"),
                     "pygame/zengl unavailable")
class CameraControlTests(unittest.TestCase):
    def _view(self, button=None):
        view = BattleView.__new__(BattleView)
        view.camera = BattleCamera(500.0, 500.0, yaw=180.0, bounds=(0.0, 0.0, 1600.0, 1600.0))
        view.scene = SimpleNamespace(battle=SimpleNamespace(phase="battle"))
        view.hud = _FakeHud(button)
        view._right_down = None
        view._right_minimap = False
        view._camera_hold = None
        view._drag_surface = None
        view.order_mode = None
        view.gpu = SimpleNamespace(target=SimpleNamespace(size=(640, 480)))
        return view

    @staticmethod
    def _press(view, button, pos=(0, 0)):
        return view.events(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))

    @staticmethod
    def _release(view, button, pos=(0, 0)):
        return view.events(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))

    def test_given_the_rotate_button_held_with_left_or_right_then_the_view_turns_opposite_ways_while_pressed(self):
        view = self._view("camera_rotate")

        self._press(view, 1)
        self.assertEqual(view.hud.pressed, "camera_rotate")  # the darker, pressed frame
        view._apply_camera_hold(0.5)
        left = view.camera.yaw
        self._release(view, 1)
        self.assertIsNone(view.hud.pressed)
        view._apply_camera_hold(0.5)
        self.assertEqual(view.camera.yaw, left)  # released: no more turning

        self._press(view, 3)
        self.assertEqual(view.hud.pressed, "camera_rotate")
        view._apply_camera_hold(0.5)
        self._release(view, 3)
        self.assertIsNone(view.hud.pressed)

        self.assertNotEqual(left, 180.0)
        self.assertAlmostEqual(view.camera.yaw, 180.0)  # right undoes left

    def test_given_the_zoom_button_held_then_left_moves_closer_and_right_further_within_the_limits(self):
        view = self._view("camera_zoom")

        self._press(view, 1)
        self.assertEqual(view.hud.pressed, "camera_zoom")
        view._apply_camera_hold(0.2)
        self.assertLess(view.camera.distance, 40.0)
        view._apply_camera_hold(100.0)
        self.assertEqual(view.camera.distance, MIN_DISTANCE)
        self._release(view, 1)

        self._press(view, 3)
        view._apply_camera_hold(100.0)
        self.assertEqual(view.camera.distance, MAX_DISTANCE)
        self._release(view, 3)
        self.assertIsNone(view.hud.pressed)

    def test_given_a_right_click_on_the_minimap_then_the_camera_looks_at_that_spot(self):
        view = self._view()

        self.assertEqual(self._press(view, 3, (520, 30)), ())
        self.assertEqual((view.camera.target_x, view.camera.target_y), (200.0, 300.0))
        self._release(view, 3, (520, 30))
        self.assertEqual((view.camera.target_x, view.camera.target_y), (200.0, 300.0))

    def test_given_a_right_drag_from_the_minimap_then_the_look_at_point_follows_the_cursor(self):
        view = self._view()
        self._press(view, 3, (520, 30))

        view.events(pygame.event.Event(pygame.MOUSEMOTION, pos=(560, 70), rel=(40, 40), buttons=(0, 0, 1)))
        self.assertEqual((view.camera.target_x, view.camera.target_y), (600.0, 700.0))
        view.events(pygame.event.Event(pygame.MOUSEMOTION, pos=(700, 70), rel=(140, 0), buttons=(0, 0, 1)))
        self.assertEqual((view.camera.target_x, view.camera.target_y), (600.0, 700.0))  # off the map: stays
        self._release(view, 3, (700, 70))

        view.events(pygame.event.Event(pygame.MOUSEMOTION, pos=(530, 10), rel=(-170, -60), buttons=(0, 0, 1)))
        self.assertNotEqual((view.camera.target_x, view.camera.target_y), (300.0, 100.0))  # a new 3D drag, not minimap

    def test_the_battle_background_is_black(self):
        self.assertEqual(BattleView.background, (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
