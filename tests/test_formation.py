import unittest

from whshr.formation import (block_slots, clamp_ranks, place, rank_range, rank_sizes,
                             reform_assignment, reform_slot_order)


class FormationTests(unittest.TestCase):
    def test_given_models_that_do_not_fill_ranks_when_formed_then_leftovers_widen_the_front_ranks(self):
        self.assertEqual(rank_sizes(18, 4), [5, 5, 4, 4])
        self.assertEqual(rank_sizes(13, 5), [3, 3, 3, 2, 2])

    def test_given_more_ranks_than_models_when_formed_then_every_rank_holds_a_model(self):
        self.assertEqual(rank_sizes(3, 4), [1, 1, 1])

    def test_given_block_when_formed_then_front_rank_is_centred_on_the_unit_and_ranks_stand_behind(self):
        slots = block_slots(5, 2)

        self.assertEqual(slots, [(-12.0, 0), (0.0, 0), (12.0, 0), (-6.0, -12.0), (6.0, -12.0)])

    def test_given_quarter_turn_facing_when_placed_then_rear_rank_stands_west_of_the_front(self):
        front, rear = place(100, 200, 128, [(0, 0), (0, -12)])

        self.assertEqual((round(front[0], 6), round(front[1], 6)), (100, 200))
        self.assertEqual((round(rear[0], 6), round(rear[1], 6)), (88, 200))


class RankClampTests(unittest.TestCase):
    """game_rules.md "Formation changes": min = max(1, trunc(0.75 * sqrt(models))), clamped to
    [min, models // min]."""

    def test_given_the_documented_model_counts_when_computing_the_range_then_it_matches_the_worked_examples(self):
        self.assertEqual(rank_range(8), (2, 4))
        self.assertEqual(rank_range(18), (3, 6))
        self.assertEqual(rank_range(24), (3, 8))
        self.assertEqual(rank_range(32), (4, 8))

    def test_given_a_request_outside_the_range_when_clamped_then_it_is_pulled_to_the_nearest_bound(self):
        self.assertEqual(clamp_ranks(18, 1), 3)
        self.assertEqual(clamp_ranks(18, 99), 6)
        self.assertEqual(clamp_ranks(18, 4), 4)


class ReformSlotOrderTests(unittest.TestCase):
    """game_rules.md "Formation changes": slots are filled front rank first, centre outward."""

    def test_given_a_five_wide_rank_when_ordered_then_the_centre_column_comes_first(self):
        order = reform_slot_order(5, 1)

        self.assertEqual(order, [(0.0, 0.0), (-12.0, 0.0), (12.0, 0.0), (-24.0, 0.0), (24.0, 0.0)])

    def test_given_several_ranks_when_ordered_then_the_front_rank_is_exhausted_before_the_next(self):
        order = reform_slot_order(9, 3)

        front, second, third = order[0:3], order[3:6], order[6:9]
        self.assertTrue(all(forward == 0.0 for _side, forward in front))
        self.assertTrue(all(forward == -12.0 for _side, forward in second))
        self.assertTrue(all(forward == -24.0 for _side, forward in third))


class ReformAssignmentTests(unittest.TestCase):
    """game_rules.md "Formation changes": nearest octagonal distance, front-rank-centre first, and
    the leader model is handed that slot directly."""

    def test_given_models_already_on_target_when_reslotted_then_each_keeps_its_own_slot(self):
        positions = [(0, 0), (12, 0), (-12, 0), (6, -12), (-6, -12)]

        assignment = reform_assignment(0, 0, 0, 5, 1, positions)

        self.assertEqual(assignment, [(0.0, 0.0), (12.0, 0.0), (-12.0, 0.0), (24.0, 0.0), (-24.0, 0.0)])

    def test_given_a_model_far_from_every_slot_when_reslotted_then_it_still_takes_the_nearest_one(self):
        # Two models: one sits exactly on the only other rank's slot, the other is far east of both.
        positions = [(0, -12), (500, 0)]

        assignment = reform_assignment(0, 0, 0, 2, 2, positions)

        self.assertIn((0.0, 0.0), assignment)  # front-rank centre still gets assigned to someone
        self.assertIn((0.0, -12.0), assignment)

    def test_given_a_named_leader_when_reslotted_then_it_takes_the_front_rank_centre_directly(self):
        # The named leader sits far from the centre slot, and every other model already stands on a
        # remaining slot; an ordinary nearest search would not pick the leader for the centre, but it
        # is handed that slot regardless.
        positions = [(500, 500), (-12, 0), (12, 0), (-24, 0), (24, 0)]

        assignment = reform_assignment(0, 0, 0, 5, 1, positions, leader_index=0)

        self.assertEqual(assignment[0], (0.0, 0.0))

    def test_given_no_leader_identity_when_reslotted_then_the_model_nearest_the_centre_slot_stands_in(self):
        positions = [(0, 0), (-12, 0), (12, 0), (-24, 0), (24, 0)]

        assignment = reform_assignment(0, 0, 0, 5, 1, positions)

        self.assertEqual(assignment[0], (0.0, 0.0))  # the model already at the centre slot stands in


if __name__ == "__main__":
    unittest.main()
