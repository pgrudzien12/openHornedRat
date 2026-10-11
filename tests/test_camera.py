import math
import unittest

from whshr.battlefield import WORLD_PER_MESH
from whshr.camera import BATTLE_DISTANCE, BATTLE_PITCH, MAX_DISTANCE, MIN_DISTANCE, MIN_PITCH, BattleCamera


def _script(camera=45.0, player_positions=((100, 200), (300, 400)), boundaries=()):
    return {
        "field": {"width": 1600, "height": 1760, "camera": camera},
        "armies": [],
        "merc": {"armies": [{"units": [{"id": f"P{index}", "set": {"x": x, "y": y}}
                                       for index, (x, y) in enumerate(player_positions)]}]},
        "boundaries": list(boundaries),
    }


def _camera_square(low=100, high=300, active=True, status="bnd_CAMEDGE"):
    flags = [status]
    if active:
        flags.insert(0, "bnd_ACTIVE")
    return {"status": flags,
            "lines": [[low, low, high, low], [high, low, high, high],
                      [high, high, low, high], [low, high, low, low]]}


class BattleCameraTests(unittest.TestCase):
    def terrain_intersects_rendered_sightline(self, camera, terrain_height):
        target_height = terrain_height(camera.target_x, camera.target_y)
        projection = camera.projection(640, 480, 1600, 1760, target_height)
        eye_x = projection.eye[0] * WORLD_PER_MESH
        eye_y = projection.eye[2] * WORLD_PER_MESH
        steps = max(1, math.ceil(4 * math.dist((camera.target_x, camera.target_y), (eye_x, eye_y))))
        for index in range(1, steps + 1):
            fraction = index / steps
            x = camera.target_x + (eye_x - camera.target_x) * fraction
            y = camera.target_y + (eye_y - camera.target_y) * fraction
            ray_height = target_height + (projection.eye[1] - target_height) * fraction
            if terrain_height(x, y) > ray_height + 1e-6:
                return True
        return False

    def test_given_camera_looking_north_when_panned_right_and_forward_then_target_moves_east_and_north(self):
        camera = BattleCamera(0.0, 0.0, yaw=180.0)

        camera.pan(10, 20)

        self.assertAlmostEqual(camera.target_x, 10)
        self.assertAlmostEqual(camera.target_y, 20)

    def test_given_camera_looking_south_when_panned_forward_then_target_moves_south(self):
        camera = BattleCamera(0.0, 0.0, yaw=0.0)

        camera.pan(0, 20)

        self.assertAlmostEqual(camera.target_x, 0)
        self.assertAlmostEqual(camera.target_y, -20)

    def test_camera_edge_clamps_initial_target_and_pan_but_allows_edge_sliding(self):
        camera = BattleCamera.for_battle(_script(
            camera=0, player_positions=((350, 200),), boundaries=(_camera_square(),)))
        self.assertEqual((camera.target_x, camera.target_y), (300, 200))

        camera.pan(100, 30)
        self.assertEqual((camera.target_x, camera.target_y), (300, 230))
        camera.pan(100, 100)
        self.assertEqual((camera.target_x, camera.target_y), (300, 300))
        camera.pan(-100, -100)
        self.assertEqual((camera.target_x, camera.target_y), (200, 200))

    def test_camera_edge_clamps_direct_focus_and_uses_nearest_active_area(self):
        camera = BattleCamera.for_battle(_script(
            camera=0, player_positions=((200, 200),),
            boundaries=(_camera_square(), _camera_square(500, 700))))
        camera.set_target(650, 650)
        self.assertEqual((camera.target_x, camera.target_y), (650, 650))
        camera.set_target(450, 600)
        self.assertEqual((camera.target_x, camera.target_y), (500, 600))

    def test_rotation_and_pan_into_a_ridge_keep_the_rendered_sightline_clear(self):
        def hill(x, y):
            return 15.0 if 40 <= x <= 90 else 0.0

        rotated = BattleCamera(0, 0, yaw=0, pitch=5, distance=20, terrain_height=hill)
        rotated.set_target(0, 0)
        self.assertFalse(self.terrain_intersects_rendered_sightline(rotated, hill))
        rotated.rotate(90)
        self.assertFalse(self.terrain_intersects_rendered_sightline(rotated, hill))

        panned = BattleCamera(-200, 0, yaw=90, pitch=5, distance=20, terrain_height=hill)
        panned.set_target(-200, 0)
        self.assertFalse(self.terrain_intersects_rendered_sightline(panned, hill))
        panned.pan(0, -200)
        self.assertAlmostEqual(panned.target_x, 0)
        self.assertFalse(self.terrain_intersects_rendered_sightline(panned, hill))

    def test_zooming_out_or_tilting_down_cannot_put_ridge_on_sightline(self):
        def hill(x, y):
            return 15.0 if 40 <= x <= 90 else 0.0

        camera = BattleCamera(0, 0, yaw=90, pitch=85, distance=20, terrain_height=hill)
        camera.set_target(0, 0)
        camera.zoom(10)
        self.assertFalse(self.terrain_intersects_rendered_sightline(camera, hill))
        camera.tilt(-80)
        self.assertFalse(self.terrain_intersects_rendered_sightline(camera, hill))

    def test_inactive_and_non_camera_boundaries_do_not_limit_camera(self):
        camera = BattleCamera.for_battle(_script(
            player_positions=((350, 200),),
            boundaries=(_camera_square(active=False), _camera_square(status="bnd_BATTLEEDGE"))))
        self.assertEqual((camera.target_x, camera.target_y), (350, 200))
        camera.set_target(900, 900)
        self.assertEqual((camera.target_x, camera.target_y), (900, 900))

    def test_given_camera_when_ground_target_is_projected_then_it_is_at_the_screen_centre_with_east_to_the_right(self):
        camera = BattleCamera(800.0, 800.0, yaw=180.0)
        projection = camera.projection(640, 480, 1600, 1760)

        centre = projection.point(100.0, 0.0, 100.0)
        east = projection.point(110.0, 0.0, 100.0)

        self.assertAlmostEqual(centre[0], 320)
        self.assertAlmostEqual(centre[1], 240)
        self.assertGreater(east[0], centre[0])

    def test_given_extreme_controls_when_applied_then_rotation_wraps_and_zoom_and_tilt_stay_in_range(self):
        camera = BattleCamera(0.0, 0.0, yaw=350.0)

        camera.rotate(20)
        camera.zoom(1000)
        camera.tilt(-90)

        self.assertAlmostEqual(camera.yaw, 10)
        self.assertEqual(camera.distance, MAX_DISTANCE)
        self.assertEqual(camera.pitch, MIN_PITCH)
        camera.zoom(0.001)
        self.assertEqual(camera.distance, MIN_DISTANCE)

    def test_given_battle_when_camera_starts_then_it_looks_at_the_first_player_unit_along_the_field_heading(self):
        camera = BattleCamera.for_battle(_script())

        self.assertEqual((camera.target_x, camera.target_y), (100.0, 200.0))
        self.assertEqual(camera.yaw, 225.0)
        self.assertEqual((camera.pitch, camera.distance), (BATTLE_PITCH, BATTLE_DISTANCE))
        self.assertEqual((BATTLE_PITCH, BATTLE_DISTANCE, MIN_DISTANCE, MAX_DISTANCE), (40.0, 40.0, 20.0, 70.0))

    def test_given_deployed_positions_when_camera_starts_then_it_looks_at_the_first_army_unit_where_it_stands(self):
        # The army file's set:x/y is stale; deployment decides where the regiments are.
        camera = BattleCamera.for_battle(_script(), unit_positions={"P1": (700.0, 90.0), "P0": (150.0, 60.0)})

        self.assertEqual((camera.target_x, camera.target_y), (150.0, 60.0))

    def test_given_a_camera_edge_reaching_beyond_the_field_then_the_look_at_point_stays_on_the_field(self):
        # Shipped CameraEdge outlines run about 300 units outside the battlefield.
        camera = BattleCamera.for_battle(_script(boundaries=(_camera_square(-300, 1900),)))

        camera.set_target(-300, -300)
        self.assertEqual((camera.target_x, camera.target_y), (0, 0))
        camera.set_target(1900, 1000)
        self.assertEqual((camera.target_x, camera.target_y), (1600, 1000))

    def test_given_no_player_units_when_camera_starts_then_it_looks_at_the_field_centre(self):
        camera = BattleCamera.for_battle(_script(player_positions=()))

        self.assertEqual((camera.target_x, camera.target_y), (800.0, 880.0))

    def test_camera_edge_confines_only_the_look_at_point_so_the_view_is_not_squeezed(self):
        camera = BattleCamera.for_battle(_script(
            camera=0, player_positions=((200, 200),), boundaries=(_camera_square(),)))
        edge = camera.camera_edges[0]
        for change in (lambda: camera.pan(250, 250), lambda: camera.rotate(110),
                       lambda: camera.zoom(10), lambda: camera.set_target(1000, 1000)):
            change()
            self.assertTrue(camera._allows(edge, (camera.target_x, camera.target_y)))
            self.assertEqual((camera.view_pitch, camera.view_distance), (camera.pitch, camera.distance))
        self.assertFalse(camera._allows(edge, camera.eye_xy()))  # the eye may look in from outside the area

    def test_given_a_map_without_camera_edges_then_the_look_at_point_stays_on_the_field(self):
        camera = BattleCamera.for_battle(_script(player_positions=((350, 200),)))

        camera.set_target(-50, 5000)
        self.assertEqual((camera.target_x, camera.target_y), (0, 1760))
        camera.set_target(2000, 100)
        self.assertEqual((camera.target_x, camera.target_y), (1600, 100))

    def test_terrain_ridge_between_eye_and_target_does_not_intersect_rendered_sightline(self):
        def hill(x, y):
            return 15.0 if 40 <= x <= 90 else 0.0

        self.assertTrue(self.terrain_intersects_rendered_sightline(
            BattleCamera(0, 0, yaw=90, pitch=5, distance=20), hill))  # the chosen view would be blocked
        camera = BattleCamera(0, 0, yaw=90, pitch=5, distance=20, terrain_height=hill)
        self.assertFalse(self.terrain_intersects_rendered_sightline(camera, hill))
        self.assertGreater(camera.view_pitch, camera.pitch)

    def test_narrow_ridge_between_old_fixed_samples_still_blocks_view(self):
        def narrow_ridge(x, y):
            return 15.0 if 12 <= x <= 18 else 0.0

        self.assertTrue(self.terrain_intersects_rendered_sightline(
            BattleCamera(0, 0, yaw=90, pitch=5, distance=20), narrow_ridge))
        camera = BattleCamera(0, 0, yaw=90, pitch=5, distance=20, terrain_height=narrow_ridge)
        self.assertFalse(self.terrain_intersects_rendered_sightline(camera, narrow_ridge))

    def test_camera_eye_cannot_finish_inside_terrain(self):
        def hill_at_eye(x, y):
            return 15.0 if 155 <= x <= 165 else 0.0

        camera = BattleCamera(0, 0, yaw=90, pitch=5, distance=20, terrain_height=hill_at_eye)
        self.assertFalse(self.terrain_intersects_rendered_sightline(camera, hill_at_eye))

    def test_given_a_terrain_lift_when_the_camera_moves_clear_then_the_chosen_view_comes_back(self):
        def hill(x, y):
            return 15.0 if 40 <= x <= 90 else 0.0

        camera = BattleCamera(0, 0, yaw=90, pitch=5, distance=20, terrain_height=hill)
        self.assertGreater(camera.view_pitch, 5)

        camera.set_target(400, 0)  # the hill is now behind the view, not between eye and target

        self.assertEqual((camera.view_pitch, camera.view_distance), (5, 20))
        self.assertEqual((camera.pitch, camera.distance), (5, 20))



if __name__ == "__main__":
    unittest.main()
