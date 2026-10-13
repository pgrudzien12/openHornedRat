"""Regression vectors for dragon display culling."""
from types import SimpleNamespace
import unittest

from whshr import dragon_mesh, picking
from whshr.battle3d import Projection
from whshr.camera import BattleCamera
from whshr.engine import Battle, Regiment
from whshr.frontend.battle_view import BattleView
from whshr.rules import Side


class DragonDisplayBoundsTests(unittest.TestCase):
    def test_visible_reference_below_camera_target_survives_camera_pan(self):
        unit = Regiment('d', 'd', 1120, 600, 384, Side.ENEMY, models=1, ranks=1, sprite='MeshDragon')
        battle = Battle(2000, 1840, [unit])
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(battle=battle, field=SimpleNamespace(
            width=2000, height=1840, dragon_meshes={1: {}}, ground_height=lambda x, y: 0))
        view.gpu = SimpleNamespace(target=SimpleNamespace(size=(1280, 800)))
        view.camera = BattleCamera(880, 480, yaw=0, pitch=40, distance=60)
        projection = view.camera.projection(1280, 800, 2000, 1840, 0)
        point = projection.view(140, 0, 75)
        px, py, _ = projection.project(point)
        self.assertTrue(0 < px < 1280 and 0 < py < 620)
        rect = picking.view_rect(projection, 1280, 800, (110, 60), lambda x, y: 0)
        battle.view_rect = tuple(v * 8 for v in rect)
        self.assertFalse(dragon_mesh.visible(battle, unit))  # old far-corner drawing box culled it
        self.assertTrue(dragon_mesh.visible(battle, unit, view._dragon_view_rect()))
        self.assertEqual(battle.view_rect, tuple(v * 8 for v in rect))  # script reaction state unchanged

    def test_render_rectangle_includes_near_corners_without_changing_default_script_box(self):
        projection = Projection(1280, 800, 250, 230, 0, 40, 1, 110, 60, projection='perspective', distance=60)
        script = picking.view_rect(projection, 1280, 800, (110, 60), lambda x, y: 0)
        render = picking.view_rect(projection, 1280, 800, (110, 60), lambda x, y: 0, include_near=True)
        self.assertEqual(script[3], 70)
        self.assertGreater(render[3], 75)

    def test_low_pitch_view_keeps_a_distant_on_screen_dragon(self):
        """At a low pitch the top screen corners see the sky; the drawing box reaches the horizon there."""
        unit = Regiment('d', 'd', 1120, 600, 384, Side.ENEMY, models=1, ranks=1, sprite='MeshDragon')
        battle = Battle(1360, 1920, [unit])
        camera = BattleCamera(300, 1600, yaw=0, pitch=10, distance=40)
        projection = camera.projection(1280, 800, 1360, 1920, 0)
        px, py, _ = projection.project(projection.view(1120 / 8, 0, 600 / 8))
        self.assertTrue(0 <= px <= 1280 and 0 <= py <= 800)
        script = picking.view_rect(projection, 1280, 800, (300 / 8, 1600 / 8), lambda x, y: 0)
        render = picking.view_rect(projection, 1280, 800, (300 / 8, 1600 / 8), lambda x, y: 0, include_near=True)
        self.assertFalse(dragon_mesh.visible(battle, unit, tuple(v * 8 for v in script)))
        self.assertTrue(dragon_mesh.visible(battle, unit, tuple(v * 8 for v in render)))


