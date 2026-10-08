"""The --debug win key through the mission's objectives (Battle.win_by_objectives, Objectives.complete)."""

import unittest

from tests.test_objectives import make, regiment
from whshr.rules import Side


def battle_with(entries, extra=()):
    player = regiment("p", Side.PLAYER, 16)
    enemy = regiment("e", Side.ENEMY, 20, x=500, y=500)
    return make(entries, player, enemy, *extra), player, enemy


class ObjectiveWinTests(unittest.TestCase):
    def test_the_enemy_is_destroyed_a_decides_and_the_battle_is_left_as_a_victory(self):
        battle, player, enemy = battle_with([["A", 20, 1]])

        self.assertTrue(battle.win_by_objectives([["A", 20, 1]]))

        self.assertEqual(battle.result, "victory")
        self.assertEqual(battle.objectives.decided, "A")
        self.assertTrue(battle.objectives.get("A").met)
        self.assertEqual(player.models, 16)  # nobody on the player's side is touched

    def test_the_battle_ends_with_the_objectives_records_not_a_flawless_stand_in(self):
        battle, _, _ = battle_with([["A", 20, 1]])

        battle.win_by_objectives([["A", 20, 1]])

        results = battle.objectives.results()
        self.assertEqual(results["A"][0], True)
        self.assertEqual(results["Z"][0], False)  # the loss letter is never marked completed

    def test_every_other_letter_is_marked_completed_with_values_filled_in(self):
        entries = [["A", 20, 1], ["B", 80, 12]]
        battle, _, _ = battle_with(entries)

        battle.win_by_objectives(entries)

        met, values = battle.objectives.results()["B"]
        self.assertTrue(met)
        self.assertEqual(values[:2], (80, 12))

    def test_a_mission_whose_ending_letter_is_not_a_plain_elimination_still_ends(self):
        # N needs a unit at a node: no enemy kill decides it, so it is met by fiat.
        battle, _, _ = battle_with([["N", 20, 1]])

        battle.win_by_objectives([["N", 20, 1]])

        self.assertEqual(battle.result, "victory")
        self.assertTrue(battle.objectives.get("N").met)
        self.assertEqual(battle.objectives.decided, "N")

    def test_a_battle_without_objectives_or_already_over_is_left_alone(self):
        battle, _, _ = battle_with([["A", 20, 1]])
        battle.result = "defeat"
        self.assertFalse(battle.win_by_objectives())
        self.assertEqual(battle.result, "defeat")
        battle.objectives = None
        battle.result = None
        self.assertFalse(battle.win_by_objectives())

    def test_the_decision_message_cue_and_result_survive_the_next_tick(self):
        battle, _, _ = battle_with([["A", 20, 1]])
        battle.win_by_objectives([["A", 20, 1]])

        battle.tick()  # the settlement tick replaces `events` with the pending feedback

        kinds = [event.kind for event in battle.events]
        for expected in ("objective_decided", "message", "sound", "result"):
            self.assertIn(expected, kinds)

    def test_the_final_pass_runs_once(self):
        battle, _, _ = battle_with([["A", 20, 1]])
        battle.win_by_objectives([["A", 20, 1]])

        self.assertTrue(battle.objectives.finished)


if __name__ == "__main__":
    unittest.main()
