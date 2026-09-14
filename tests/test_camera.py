import unittest

from whshr.camera import MAX_DISTANCE, MIN_PITCH, BattleCamera


def _script(camera=45.0, player_positions=((100, 200), (300, 400))):
    return {
        "field": {"width": 1600, "height": 1760, "camera": camera},
        "armies": [],
        "merc": {"armies": [{"units": [{"set": {"x": x, "y": y}} for x, y in player_positions]}]},
    }


class BattleCameraTests(unittest.TestCase):
    def test_given_battle_when_camera_starts_then_it_looks_at_the_player_units_along_the_field_heading(self):
        camera = BattleCamera.for_battle(_script())

        self.assertEqual((camera.target_x, camera.target_y), (200.0, 300.0))
        self.assertEqual(camera.yaw, 225.0)

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


if __name__ == "__main__":
    unittest.main()
