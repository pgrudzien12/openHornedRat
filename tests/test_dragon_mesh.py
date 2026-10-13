"""Synthetic mesh vectors for notes/bf014_dragon_rendering.md; no original assets."""
from array import array
import math
import random
from types import SimpleNamespace
import unittest

from whshr import animation, dragon_mesh, interpreter
from whshr.battlefield import VERTEX_FLOATS, load_dragon_meshes
from whshr.engine import Battle, ModelState, Regiment
from whshr.rules import Side


def triangle(pose):
    return dict(verts=[0, 0, 0, pose, 0, 0, 0, 1, 1], normals=[0, 1, 0], uv=[0, 0, 1, 0, 0, 1],
                faces=[([0, 1, 2], [0, 0, 0])], ftex=[0])


class Entry(random.Random):
    def __init__(self, entry):
        super().__init__(0)
        self.entry = entry

    def randrange(self, *args):
        return self.entry


class DragonMeshTests(unittest.TestCase):
    def setUp(self):
        self.unit = Regiment('dragon', 'dragon', 1120, 600, 384, Side.ENEMY, models=1, ranks=1,
                             sprite='MeshDragon', leader_sprite='MeshDragon', has_leader=True)
        self.battle = Battle(2000, 2000, [self.unit])
        self.unit.model_positions()
        self.model = self.unit.melee_models[0]
        self.field = SimpleNamespace(dragon_meshes={i: triangle(i) for i in range(1, 5)},
                                     ground_texture_count=3, scenery_texture_count=1,
                                     ground_height=lambda x, y: 2)

    def geometry(self):
        return dragon_mesh.unit_vertices(self.field, self.battle, self.unit)

    def test_mesh_draws_without_sprite_sheet_and_only_once_with_same_leader_resource(self):
        vertices = array('f')
        dragon_mesh.append_vertices(self.field, self.battle, vertices)
        self.assertEqual(len(vertices), 3 * VERTEX_FLOATS)
        self.assertEqual(vertices[5], 3)  # embedded scenery texture, after the ground layers
        self.assertEqual(vertices[3:5].tolist(), [0, 0])  # top-origin UV preserved

    def test_coarse_yaw_authored_pivot_height_and_natural_scale(self):
        place, normal = dragon_mesh.transform(1120, 600, 2, 16, 384)
        self.assertEqual(place((0, 0, 0)), (140, 4, 75))
        angle = math.radians(274.2857142857143)
        v = place((0, 0, 1))
        self.assertAlmostEqual(v[0], 140 + math.sin(angle))
        self.assertAlmostEqual(v[2], 75 + math.cos(angle))
        self.assertEqual(normal((0, 1, 0)), (0, 1, 0))
        self.assertEqual(place((0, 11, 0))[1], 15)  # no recenter or extra scale

    def test_exclusion_leaves_mesh_visible_but_actual_removal_hides_it(self):
        state = self.battle.event_bus.unit_states['dragon']
        runner = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        runner.op_ExcludeFromArmy(state, None, [], 'dragon', 0, self.battle.rng)
        self.assertTrue(self.geometry())
        self.battle.remove_from_play(self.unit)
        self.assertFalse(self.geometry())

    def test_hidden_and_no_display_suppress_mesh_independently(self):
        self.unit.hidden = True
        self.assertFalse(self.geometry())
        self.unit.hidden = False
        state = self.battle.event_bus.unit_states['dragon']
        state.unit_flags |= interpreter.NOT_SHOWN_FLAG
        self.assertFalse(self.geometry())
        state.unit_flags &= ~interpreter.NOT_SHOWN_FLAG
        self.assertTrue(self.geometry())

    def test_camera_rectangle_uses_inclusive_reference_position_and_no_map_edge_gate(self):
        self.battle.view_rect = (1120, 600, 1200, 700)
        self.assertTrue(self.geometry())
        self.battle.view_rect = (1121, 600, 1200, 700)
        self.assertFalse(self.geometry())
        self.unit.x = -10
        self.battle.view_rect = (-20, 0, 0, 700)
        self.assertTrue(self.geometry())  # no dragon-specific map-edge hide

    def test_reading_geometry_never_advances_animation_or_draws_randomness(self):
        animation.request_mesh_breath(self.model, 2, Entry(0))
        state = self.battle.rng.getstate()
        pc = self.model.action_pc
        first = self.geometry()
        for _ in range(5):
            self.assertEqual(self.geometry(), first)
        self.assertEqual(self.model.action_pc, pc)
        self.assertEqual(self.battle.rng.getstate(), state)

    def test_hidden_breath_advances_and_reveal_uses_current_pose(self):
        animation.request_mesh_breath(self.model, 0, Entry(3))
        self.unit.hidden = True
        for _ in range(4):
            self.battle._step_animations(self.unit)
        self.unit.hidden = False
        self.assertEqual(animation.mesh_dragon_pose(self.model), 3)
        for _ in range(4):
            self.battle._step_animations(self.unit)
        self.assertEqual(animation.mesh_dragon_pose(self.model), 1)

    def test_frontend_picks_textured_mesh_without_a_sprite_and_respects_occlusion(self):
        from whshr.battle3d import Projection
        from whshr.frontend.battle_view import BattleView
        self.field.sprite_sheet = lambda resource: None
        self.field.vertices = array('f')
        self.field.effect_meshes = {}
        self.field.texture_size = (1, 1)
        self.field.texture_layers = [bytes((100, 100, 100, 255))] * 4
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=self.field, battle=self.battle)
        view.camera = SimpleNamespace(yaw=0)
        view._effect_vertices = lambda: self.geometry()
        projection = Projection(640, 480, 250, 250, 0, 45, 1, 140, 75,
                                projection='perspective', distance=20, target_height=2)
        geometry = self.geometry()
        centre = [sum(geometry[i + axis] for i in (0, 7, 14)) / 3 for axis in range(3)]
        px, py, _ = projection.project(projection.view(*centre))
        pixel = (px - 0.5, py - 0.5)
        self.assertEqual(view._figure_hits(pixel, projection), [(self.unit, (1120, 600))])
        # A solid triangle nearer the eye hides the dragon under the shared mesh depth test.
        self.field.vertices = array('f', geometry)
        for i in (0, 7, 14):
            for axis in range(3):
                self.field.vertices[i + axis] += (projection.eye[axis] - centre[axis]) * 0.2
        self.assertEqual(view._figure_hits(pixel, projection), [])


    def test_missing_pose_fails_with_host_diagnostic_instead_of_substitution(self):
        del self.field.dragon_meshes[1]
        with self.assertRaisesRegex(ValueError, 'pose 1'):
            self.geometry()

    def test_pose_resources_resolve_through_furniture_table_without_sprite_files(self):
        meshes = {f'pose{i}.xof': triangle(i) for i in range(1, 5)}
        names = {f'dragonframe{i}': f'pose{i}.XOF' for i in range(1, 5)}
        self.assertEqual(load_dragon_meshes(meshes, names)[4], triangle(4))
        del meshes['pose3.xof']
        with self.assertRaisesRegex(ValueError, 'DragonFrame3'):
            load_dragon_meshes(meshes, names)


class DragonAnimationTests(unittest.TestCase):
    def test_neutral_actions_hold_pose_one(self):
        for action in (1, 2, 3, 5, 6):
            model = ModelState(action=action)
            for _ in range(30):
                animation.step(model, action, Entry(0), 'mesh_dragon')
                self.assertEqual(animation.mesh_dragon_pose(model), 1)

    def test_fight_cycle_is_discrete_with_two_updates_per_pose_and_random_entry(self):
        for entry in (0, 7, 15):
            model = ModelState()
            shown = []
            for _ in range(24):
                animation.step(model, animation.FIGHT, Entry(entry), 'mesh_dragon')
                shown.append(animation.mesh_dragon_pose(model))
            expected = animation.DRAGON_FIGHT[entry:] + animation.DRAGON_FIGHT[:entry]
            self.assertEqual(tuple(shown), expected)

    def test_breath_pose_lasts_seven_to_ten_updates_and_drops_competing_requests(self):
        for sector, pose in enumerate((3, 2, 4)):
            for entry in range(4):
                model = ModelState()
                rng = Entry(entry)
                animation.request_mesh_breath(model, sector, rng)
                self.assertEqual(animation.mesh_dragon_pose(model), pose)
                for tick in range(10 - entry):
                    self.assertTrue(animation.one_shot_running(model, 'mesh_dragon'))
                    animation.request_mesh_breath(model, (sector + 1) % 3, rng)
                    self.assertEqual(model.action_pc, tick)  # no restart
                    animation.step(model, animation.WALK, rng, 'mesh_dragon')
                    self.assertIsNone(model.pending_action)
                self.assertEqual(animation.mesh_dragon_pose(model), 1)
                animation.step(model, animation.STAND, rng, 'mesh_dragon')
                self.assertEqual(model.action, animation.STAND)

class DragonBreathTests(unittest.TestCase):
    def test_raw_bearing_boundaries_and_wraparound(self):
        from whshr.ranged import dragon_breath_sector
        for facing, bearing, expected in ((384, 256, None), (384, 257, 0), (384, 340, 0),
                                          (384, 341, 1), (384, 425, 1), (384, 426, 2),
                                          (384, 510, 2), (384, 511, 3), (256, 384, None),
                                          (500, 20, None), (10, 500, None), (0, 0, 1)):
            with self.subTest(facing=facing, bearing=bearing):
                self.assertEqual(dragon_breath_sector(bearing, facing), expected)

    def test_accepted_breath_requests_pose_and_launches_from_offset_without_waiting(self):
        from whshr.ranged import launch_shot
        for bearing, sector, pose in ((300, 0, 3), (384, 1, 2), (450, 2, 4)):
            unit = Regiment('d', 'd', 1000, 1000, 384, Side.ENEMY, models=1, ranks=1,
                            sprite='MeshDragon', shooting_code=14, unit_class=1)
            battle = Battle(2000, 2000, [unit])
            angle = bearing * math.tau / 512
            aim = (1000 + 200 * math.sin(angle), 1000 + 200 * math.cos(angle))
            launch_shot(battle, unit, (1000, 1000), aim)
            self.assertGreaterEqual(len(battle.innate_projectiles), 4)
            self.assertEqual(animation.mesh_dragon_pose(unit.melee_models[0]), pose)
            direction = (384 + (sector - 1) * 64) * math.tau / 512
            for flame in battle.innate_projectiles:
                self.assertAlmostEqual(flame.x0, 1000 + 72 * math.sin(direction))
                self.assertAlmostEqual(flame.y0, 1000 + 72 * math.cos(direction))
            self.assertEqual(unit.direction, 384)

    def test_rejected_wraparound_shot_leaves_prior_sector_and_action_intact(self):
        from whshr.ranged import launch_shot
        unit = Regiment('d', 'd', 1000, 1000, 500, Side.ENEMY, models=1, ranks=1,
                        sprite='MeshDragon', shooting_code=14, unit_class=1)
        battle = Battle(2000, 2000, [unit])
        unit.model_positions()
        model = unit.melee_models[0]
        animation.request_mesh_breath(model, 2, Entry(0))
        model.action_pc = 2
        angle = 20 * math.tau / 512
        launch_shot(battle, unit, (1000, 1000), (1000 + 200 * math.sin(angle), 1000 + 200 * math.cos(angle)))
        self.assertFalse(battle.innate_projectiles)
        self.assertEqual((model.action, model.action_pc, model.breath_sector), (animation.SHOOT, 2, 2))

    def test_sector_three_uses_default_pose_and_documented_host_origin_policy(self):
        from whshr.ranged import launch_shot
        unit = Regiment('d', 'd', 1000, 1000, 384, Side.ENEMY, models=1, ranks=1,
                        sprite='MeshDragon', shooting_code=14, unit_class=1)
        battle = Battle(2000, 2000, [unit])
        angle = 511.5 * math.tau / 512
        launch_shot(battle, unit, (1000, 1000), (1000 + 200 * math.sin(angle), 1000 + 200 * math.cos(angle)))
        self.assertEqual(unit.melee_models[0].breath_sector, 3)
        self.assertEqual(animation.mesh_dragon_pose(unit.melee_models[0]), 2)
        self.assertGreaterEqual(len(battle.innate_projectiles), 4)
        self.assertEqual((battle.innate_projectiles[0].x0, battle.innate_projectiles[0].y0), (1000, 1000))
