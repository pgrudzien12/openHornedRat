import unittest

from whshr.smacker import frame_index_at


class FrameIndexTests(unittest.TestCase):
    def test_given_elapsed_time_when_the_due_frame_is_requested_then_it_matches_the_8fps_cadence(self):
        self.assertEqual(frame_index_at(0.0), 0)
        self.assertEqual(frame_index_at(0.124), 0)
        self.assertEqual(frame_index_at(0.125), 1)
        self.assertEqual(frame_index_at(2.0), 16)

    def test_given_negative_elapsed_time_when_the_due_frame_is_requested_then_it_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            frame_index_at(-0.001)


if __name__ == "__main__":
    unittest.main()
