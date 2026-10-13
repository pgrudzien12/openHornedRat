"""Regression vectors for near-camera culling and Fireball art for dragon flames."""
from array import array
from types import SimpleNamespace
import unittest

from whshr import dragon_mesh, picking
from whshr.battle3d import Projection
from whshr.camera import BattleCamera
from whshr.engine import Battle, Regiment
from whshr.frontend.battle_view import BattleView
from whshr.frontend.spell_visuals import DragonFlameFlights, FireballVisuals
from whshr.ranged import InnateProjectile
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


class DragonFireballArtTests(unittest.TestCase):
    def setUp(self):
        self.adapter = DragonFlameFlights()
        self.visuals = FireballVisuals()

    def step(self, flames, ground=lambda x, y: 0):
        flights = self.adapter.sample(flames, ground)
        self.visuals.advance(flights)
        return flights, self.visuals.sprites()

    def test_every_flame_has_a_fireball_head_and_trail_with_independent_identity(self):
        flames = [InnateProjectile('d', 14, 100, 200, 50, 200, x=100, y=200, z=40) for _ in range(4)]
        flights, sprites = self.step(flames)
        self.assertEqual(len({f.serial for f in flights}), 4)
        self.assertTrue(all(f.serial < 0 for f in flights))  # no collision with cast Fireball ids
        self.assertEqual([s.frame for s in sprites], [125] * 8)
        for flame in flames:
            flame.x -= 10
        _, sprites = self.step(flames)
        self.assertEqual([s.frame for s in sprites[:4]], [126] * 4)
        self.assertTrue(any(s.x == 100 for s in sprites))  # trail at previous point

    def test_last_projectile_position_starts_one_explosion_and_trail_can_finish(self):
        flame = InnateProjectile('d', 14, 100, 200, 50, 200, x=100, y=200, z=40)
        flights, _ = self.step([flame])
        serial = flights[0].serial
        flame.x, flame.z = 50, 20  # simulation advances even the projectile removed this tick
        ending, sprites = self.step([])
        self.assertEqual((ending[0].serial, ending[0].x, ending[0].ending), (serial, 50, True))
        self.assertTrue(any(s.frame == 177 and s.x == 50 for s in sprites))
        ending, _ = self.step([])
        self.assertEqual(ending, [])  # no repeated explosion reset
        for _ in range(21):
            self.step([])
        self.assertEqual(self.visuals.sprites(), [])

    def test_absolute_height_is_preserved_and_other_innate_weapons_are_ignored(self):
        flame = InnateProjectile('d', 14, 100, 200, 50, 200, x=100, y=200, z=48)
        warpfire = InnateProjectile('w', 15, 0, 0, 0, 100)
        flights, sprites = self.step([flame, warpfire], ground=lambda x, y: 23)
        self.assertEqual(len(flights), 1)
        self.assertEqual(sprites[0].height + 23, 48)

    def test_renderer_no_longer_emits_fire_mesh_wall_for_dragon_flames(self):
        # A fire mesh is deliberately present: it must not be used as the dragon's visual.
        field = SimpleNamespace(effect_meshes={'fire1': {}}, ground_texture_count=0, scenery_texture_count=1)
        battle = SimpleNamespace(regiments={}, control_piece=None, projectiles=[], impact_effects=[],
                                 innate_projectiles=[InnateProjectile('d', 14, 0, 0, 100, 0)])
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=field, battle=battle)
        view.effect_capacity = 65536
        self.assertEqual(view._effect_vertices(), array('f'))
