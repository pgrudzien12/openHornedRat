"""Dragging a regiment near a view edge during deployment pans the camera, and the regiment follows the ground under
the unmoved cursor, so it can be carried past the visible field without letting go of it."""

import importlib.util
import unittest
from types import SimpleNamespace

if importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl"):
    from whshr.camera import BattleCamera
    from whshr.frontend.battle_view import EDGE_SCROLL_MARGIN, BattleView, edge_scroll

WIDTH, HEIGHT, PANEL_TOP = 640, 480, 304
MARGIN = EDGE_SCROLL_MARGIN * HEIGHT if importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl") else 0


class _FakeHud:
    def panel_top(self):
        return PANEL_TOP


class _FakeBattle:
    def __init__(self, phase: str) -> None:
        self.phase = phase
        self.drags: list[tuple[float, float, bool]] = []

    def update_deployment_drag(self, x, y, rotate=False):
        self.drags.append((x, y, rotate))


@unittest.skipUnless(importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl"),
                     "pygame/zengl unavailable")
class EdgeScrollStrengthTests(unittest.TestCase):
    def test_given_a_cursor_in_the_middle_then_nothing_pans(self):
        self.assertEqual(edge_scroll((320, 150), WIDTH, PANEL_TOP, MARGIN), (0.0, 0.0))

    def test_given_a_cursor_at_each_edge_then_the_pan_points_towards_that_edge_at_full_strength(self):
        self.assertEqual(edge_scroll((0, 150), WIDTH, PANEL_TOP, MARGIN), (-1.0, 0.0))
        self.assertEqual(edge_scroll((WIDTH, 150), WIDTH, PANEL_TOP, MARGIN), (1.0, 0.0))
        self.assertEqual(edge_scroll((320, 0), WIDTH, PANEL_TOP, MARGIN), (0.0, 1.0))  # top: forward
        self.assertEqual(edge_scroll((320, PANEL_TOP), WIDTH, PANEL_TOP, MARGIN), (0.0, -1.0))  # panel top: back

    def test_given_a_cursor_halfway_into_the_band_then_the_pan_is_half_strength(self):
        right, forward = edge_scroll((WIDTH - MARGIN / 2, 150), WIDTH, PANEL_TOP, MARGIN)
        self.assertAlmostEqual(right, 0.5)
        self.assertEqual(forward, 0.0)

    def test_given_a_cursor_over_the_command_panel_then_it_pans_back_at_full_strength(self):
        self.assertEqual(edge_scroll((320, 400), WIDTH, PANEL_TOP, MARGIN), (0.0, -1.0))

    def test_given_a_corner_then_both_axes_pan(self):
        self.assertEqual(edge_scroll((0, 0), WIDTH, PANEL_TOP, MARGIN), (-1.0, 1.0))


@unittest.skipUnless(importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl"),
                     "pygame/zengl unavailable")
class DeploymentDragEdgeScrollTests(unittest.TestCase):
    def _view(self, phase="deployment", surface="main", pixel=(WIDTH - 1.0, 150.0)):
        view = BattleView.__new__(BattleView)
        view.camera = BattleCamera(800.0, 800.0, yaw=180.0, bounds=(0.0, 0.0, 1600.0, 1600.0))
        view.scene = SimpleNamespace(battle=_FakeBattle(phase))
        view.hud = _FakeHud()
        view.gpu = SimpleNamespace(target=SimpleNamespace(size=(WIDTH, HEIGHT)))
        view._drag_surface = surface
        view._drag_pixel = pixel
        # The ground under the cursor: stands in for picking, offset from the look-at point.
        view._drag_events = lambda _pixel, rotate: (("drag_to", view.camera.target_x + 10.0,
                                                    view.camera.target_y, rotate),)
        return view

    def test_given_a_regiment_dragged_to_the_right_edge_then_the_camera_pans_and_the_regiment_follows(self):
        view = self._view()
        before = (view.camera.target_x, view.camera.target_y)

        view._edge_scroll_drag(0.5)

        self.assertNotEqual((view.camera.target_x, view.camera.target_y), before)
        self.assertEqual(view.scene.battle.drags, [(view.camera.target_x + 10.0, view.camera.target_y, False)])

    def test_given_the_cursor_away_from_the_edges_then_the_camera_stays_and_no_drag_update_is_sent(self):
        view = self._view(pixel=(320.0, 150.0))
        before = (view.camera.target_x, view.camera.target_y)

        view._edge_scroll_drag(0.5)

        self.assertEqual((view.camera.target_x, view.camera.target_y), before)
        self.assertEqual(view.scene.battle.drags, [])

    def test_given_no_drag_a_minimap_drag_or_the_battle_phase_then_the_edge_does_not_pan(self):
        for view in (self._view(surface=None), self._view(surface="minimap"), self._view(phase="battle")):
            before = (view.camera.target_x, view.camera.target_y)
            view._edge_scroll_drag(0.5)
            self.assertEqual((view.camera.target_x, view.camera.target_y), before)
            self.assertEqual(view.scene.battle.drags, [])


if __name__ == "__main__":
    unittest.main()
