import unittest

from whshr.glue_animation import GlueBitmapAnimator


class GlueBitmapAnimatorTests(unittest.TestCase):
    def test_looping_caravan_cell_descends_and_restarts_after_each_frame_period(self):
        animator = GlueBitmapAnimator({"bitmap": "CarLampCell", "animstartframe": 2,
                                       "animstopframe": -1, "timecnt": 1})

        self.assertFalse(animator.tick(50).redrawn)  # initial delay
        self.assertEqual(animator.tick(50).bitmap, "CarLampCell2")
        self.assertFalse(animator.tick(50).redrawn)
        self.assertEqual(animator.tick(50).bitmap, "CarLampCell1")
        animator.tick(50)
        self.assertEqual(animator.tick(50).bitmap, "CarLampCell0")
        animator.tick(50)
        self.assertEqual(animator.tick(50).bitmap, "CarLampCell2")

    def test_loop_delay_holds_the_last_frame_before_restart(self):
        animator = GlueBitmapAnimator({"bitmap": "EyeCell", "animstartframe": 1,
                                       "animstopframe": -1, "timecnt": 0, "looptimecnt": 2})

        self.assertEqual(animator.tick(50).bitmap, "EyeCell1")
        self.assertEqual(animator.tick(50).bitmap, "EyeCell0")
        self.assertFalse(animator.tick(50).redrawn)
        self.assertFalse(animator.tick(50).redrawn)
        self.assertEqual(animator.tick(50).bitmap, "EyeCell1")

    def test_finite_animation_holds_its_last_drawn_frame_then_reports_completion(self):
        animator = GlueBitmapAnimator({"bitmap": "Trail1", "animstartframe": 2,
                                       "animstopframe": 0, "timecnt": 0})

        self.assertEqual(animator.tick(50).bitmap, "Trail2")
        self.assertEqual(animator.tick(50).bitmap, "Trail1")
        update = animator.tick(50)
        self.assertEqual((update.bitmap, update.redrawn, update.finished), ("Trail1", False, True))

    def test_late_timer_tick_runs_at_most_one_step(self):
        animator = GlueBitmapAnimator({"bitmap": "Cell", "animstartframe": 2,
                                       "animstopframe": -1, "timecnt": 0})

        self.assertEqual(animator.tick(200).bitmap, "Cell2")
        self.assertEqual(animator.current, 1)

    def test_sub_timer_frame_durations_accumulate_into_one_animation_step(self):
        animator = GlueBitmapAnimator({"bitmap": "Cell", "animstartframe": 2,
                                       "animstopframe": -1, "timecnt": 0})

        updates = [animator.tick(16) for _ in range(4)]

        self.assertEqual([update.redrawn for update in updates], [False, False, False, True])
        self.assertEqual(updates[-1].bitmap, "Cell2")

    def test_display_name_uses_the_start_frame_before_the_first_timer_step(self):
        animator = GlueBitmapAnimator({"bitmap": "TrailCell", "animstartframe": 3, "animstopframe": 0})

        self.assertEqual(animator.display_name, "TrailCell3")
        animator.tick(50)
        self.assertEqual(animator.display_name, "TrailCell3")


if __name__ == "__main__":
    unittest.main()
