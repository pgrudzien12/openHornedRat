import unittest

from whshr.clock import FixedStepClock


class FixedStepClockTests(unittest.TestCase):
    def test_given_fixed_step_when_frame_times_accumulate_then_whole_steps_run_and_the_remainder_carries(self):
        clock = FixedStepClock(0.1)

        first = clock.advance(0.25)
        second = clock.advance(0.05)

        self.assertEqual((first, second), (2, 1))
        self.assertEqual(clock.ticks, 3)
        self.assertEqual(clock.alpha, 0.0)

    def test_given_decimal_frame_times_when_they_sum_to_whole_steps_then_no_step_is_lost_to_rounding(self):
        clock = FixedStepClock(0.1)

        steps = sum(clock.advance(0.1) for _ in range(30))

        self.assertEqual(steps, 30)

    def test_given_long_stall_when_advanced_then_steps_are_capped_and_the_backlog_is_dropped(self):
        clock = FixedStepClock(0.01, max_steps=5)

        stalled = clock.advance(1.0)
        following = clock.advance(0.0)

        self.assertEqual((stalled, following), (5, 0))
        self.assertEqual(clock.dropped_steps, 95)

    def test_given_invalid_durations_when_used_then_they_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            FixedStepClock(0)
        with self.assertRaisesRegex(ValueError, "negative"):
            FixedStepClock(0.1).advance(-0.01)


if __name__ == "__main__":
    unittest.main()
