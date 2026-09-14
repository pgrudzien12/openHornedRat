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

    def test_given_no_frame_count_when_elapsed_time_exceeds_the_film_then_the_index_keeps_growing(self):
        # Without a frame count the index is unbounded: a scene that keeps ticking after the film's
        # own end (the engine deliberately does, so its own timeline stays the single end-of-playback
        # authority) must not silently freeze here.
        self.assertEqual(frame_index_at(1000.0), 8000)

    def test_given_a_scene_time_past_the_last_video_frame_then_the_frame_index_stays_at_the_last_frame(self):
        # A1.SI: 722 frames at 125 ms = 90.25 s of video inside a longer, 96.5 s Omni timeline
        # (notes/si_omni.md). Once the scene clock runs past the film, playback must hold the last
        # frame rather than reading past it (or, worse, wrapping back to the start).
        self.assertEqual(frame_index_at(90.25, frame_count=722), 721)
        self.assertEqual(frame_index_at(96.5, frame_count=722), 721)
        self.assertEqual(frame_index_at(1000.0, frame_count=722), 721)

    def test_given_a_frame_count_when_elapsed_time_is_still_within_the_film_then_it_is_not_clamped(self):
        self.assertEqual(frame_index_at(2.0, frame_count=722), 16)


if __name__ == "__main__":
    unittest.main()
