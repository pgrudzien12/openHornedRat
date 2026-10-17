"""The end picture between a campaign battle and its debrief (issue #123, notes/native-windows.md 9.3.1 (b),
notes/debrief_evaluation.md 4.2 and 4.4)."""
import unittest
from unittest import mock

from tests.test_debrief_scene import campaign_with
from tests.test_debrief_screen import BF003_WON
from whshr.debrief_rules import END_SCREEN_FAILURE, END_SCREEN_NEUTRAL, END_SCREEN_SUCCESS, end_screen
from whshr.debrief_scene import END_SCREEN_HOLD, DebriefScene, EndScreenScene
from whshr.glue_runtime import StartDebrief
from whshr.glue_scene import GlueScene

MET, UNMET = (True, (0, 0, 0, 0)), (False, (0, 0, 0, 0))
# Table rows (setdebrief:n records n - 1) with each end-screen key.
KEY_0, KEY_Z, KEY_SMALL_Z, KEY_A, KEY_T_KIND_4 = 0, 1, 2, 7, 22


class EndScreenChoiceTests(unittest.TestCase):
    def test_the_key_of_the_evaluator_row_picks_the_picture(self):
        cases = (
            # (row, objective results, picture)
            (KEY_Z, {"Z": MET}, END_SCREEN_FAILURE),
            (KEY_Z, {"Z": UNMET}, END_SCREEN_SUCCESS),
            (KEY_SMALL_Z, {"Z": MET}, END_SCREEN_FAILURE),
            (KEY_SMALL_Z, {"Z": UNMET}, END_SCREEN_NEUTRAL),
            (KEY_A, {"Z": UNMET, "A": MET}, END_SCREEN_SUCCESS),
            (KEY_A, {"Z": UNMET, "A": UNMET}, END_SCREEN_NEUTRAL),
            (KEY_A, {"Z": UNMET}, END_SCREEN_NEUTRAL),  # A absent
            (KEY_T_KIND_4, {"Z": UNMET, "G": UNMET}, END_SCREEN_SUCCESS),  # T = 1
            (KEY_T_KIND_4, {"Z": UNMET, "G": MET}, END_SCREEN_FAILURE),  # T = 0
            (KEY_0, {"Z": MET}, END_SCREEN_NEUTRAL),
            (KEY_0, {"Z": UNMET}, END_SCREEN_NEUTRAL),
        )
        for row, results, picture in cases:
            with self.subTest(row=row, results=results):
                self.assertEqual(end_screen(row, results), picture)

    def test_a_row_outside_the_table_shows_the_neutral_picture(self):
        self.assertEqual(end_screen(99, {"Z": MET}), END_SCREEN_NEUTRAL)


class EndScreenSceneTests(unittest.TestCase):
    def setUp(self):
        self.campaign = campaign_with(BF003_WON)
        self.glue = GlueScene("DEBRIEFONLY", self.campaign)
        self.scene = EndScreenScene(self.glue, StartDebrief(1, 2, KEY_Z, False))

    def test_given_a_won_battle_then_the_success_picture_is_chosen_from_the_campaign_results(self):
        self.assertEqual(self.scene.bitmap, END_SCREEN_SUCCESS)

    def test_given_the_end_picture_when_it_is_dismissed_then_the_debrief_opens(self):
        transition = self.scene.handle("dismiss", None)

        self.assertIsInstance(transition.scene, DebriefScene)
        self.assertIs(transition.scene.glue_scene, self.glue)
        self.assertIsNone(self.scene.handle("dismiss", None))  # only once

    def test_given_the_end_picture_when_nobody_clicks_then_it_closes_after_the_hold_time(self):
        self.assertIsNone(self.scene.update(END_SCREEN_HOLD / 2, None))

        transition = self.scene.update(END_SCREEN_HOLD / 2, None)

        self.assertIsInstance(transition.scene, DebriefScene)

    def test_given_a_campaign_ending_battle_when_the_picture_closes_then_the_death_movie_plays_instead(self):
        self.campaign.campaign_over_movie = "death01"
        with mock.patch("whshr.campaign_scenes.MovieScene") as movie:
            self.scene.handle("dismiss", None)

        self.assertEqual(movie.call_args.args, ("death01",))
        self.assertIsNone(self.campaign.campaign_over_movie)
