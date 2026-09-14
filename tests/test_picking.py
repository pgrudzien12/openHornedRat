import unittest

from whshr.battle3d import Projection
from whshr.picking import intersect_ground, pick_ground


def _flat(height):
    return lambda x, z: height


def _looking_down(target_x=0.0, target_z=0.0, pitch=80.0, distance=100.0, target_height=0.0):
    """A perspective camera centred above (target_x, target_height, target_z), looking mostly straight down."""
    return Projection(640, 480, 1600, 1760, yaw=180.0, pitch=pitch, zoom=1.0, target_x=target_x,
                      target_z=target_z, projection="perspective", distance=distance, fov=50.0,
                      target_height=target_height)


class IntersectGroundTests(unittest.TestCase):
    def test_given_a_ray_starting_on_flat_ground_when_intersected_then_it_returns_its_own_point(self):
        point = intersect_ground((10.0, 0.0, 5.0), (0.0, -1.0, 0.0), _flat(0.0))

        self.assertEqual(point, (10.0, 5.0))

    def test_given_a_ray_moving_away_from_the_ground_when_intersected_then_it_finds_no_crossing(self):
        point = intersect_ground((0.0, 10.0, 0.0), (0.0, 1.0, 0.0), _flat(0.0))

        self.assertIsNone(point)

    def test_given_a_downward_ray_over_a_sloped_field_when_intersected_then_it_lands_on_the_slope(self):
        # height_at(x, z) = 0.1 * x: a gentle ramp: the ray starts above (20, 0) and falls straight down.
        point = intersect_ground((20.0, 50.0, 0.0), (0.0, -1.0, 0.0), lambda x, z: 0.1 * x)

        self.assertIsNotNone(point)
        x, z = point
        self.assertAlmostEqual(x, 20.0, places=1)
        self.assertAlmostEqual(z, 0.0, places=1)


class PickGroundTests(unittest.TestCase):
    def test_given_a_camera_looking_straight_down_when_the_screen_centre_is_picked_then_it_hits_the_target(self):
        projection = _looking_down(target_x=30.0, target_z=-15.0)

        ground = pick_ground(projection, 320, 240, _flat(0.0))

        self.assertIsNotNone(ground)
        x, z = ground
        self.assertAlmostEqual(x, 30.0, delta=0.5)
        self.assertAlmostEqual(z, -15.0, delta=0.5)

    def test_given_an_off_centre_pixel_when_picked_then_the_ground_point_moves_away_from_the_target(self):
        projection = _looking_down()

        centre = pick_ground(projection, 320, 240, _flat(0.0))
        off_centre = pick_ground(projection, 500, 240, _flat(0.0))

        self.assertIsNotNone(centre)
        self.assertIsNotNone(off_centre)
        self.assertNotAlmostEqual(centre[0], off_centre[0], places=1)

    def test_given_an_orthographic_projection_when_picked_then_it_is_rejected(self):
        projection = Projection(640, 480, 1600, 1760, yaw=180.0, pitch=45.0, zoom=1.0, target_x=0.0, target_z=0.0)

        with self.assertRaises(ValueError):
            pick_ground(projection, 320, 240, _flat(0.0))


if __name__ == "__main__":
    unittest.main()
