import unittest

from whshr.formation import block_slots, place, rank_sizes


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


if __name__ == "__main__":
    unittest.main()
