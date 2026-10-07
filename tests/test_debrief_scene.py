"""Debrief scene and completion (issue #123, notes/native-windows.md 9.9, notes/debrief_evaluation.md 4-6):
the screen opens for a script's debrief request, Done pays and resumes, a screen with nothing to show is skipped,
and Done applies armour rewards, experience and promotions."""
import unittest
from dataclasses import replace
from unittest.mock import patch

from tests.test_debrief_flow import RESOURCES as FLOW_RESOURCES, _campaign
from tests.test_debrief_screen import BF003_TERMS, BF003_WON, unit
from tests.test_post_mission_caravan import PostMissionCaravanTests
from tests.test_troop_selection import regiment
from whshr import debrief_rewards, script
from whshr.debrief import complete_debrief
from whshr.debrief_scene import DebriefScene
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueRuntime, StartDebrief
from whshr.glue_scene import GlueScene
from whshr.payments import CashTerms, played_results
from whshr.scenes import SceneMachine

RESOURCES = {
    **FLOW_RESOURCES,
    "SUMMARY": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\ndebriefwithsummary:17\nsetgluestatusmask:1\nsetgluestatus:\n[END]",
    "LASTBATTLE": "[RUN]\n[START]\nsetgluestatusmask:2000\ntestmission:\nendgame:\n[END]",
    "FINALBATTLE": "[RUN]\n[START]\nsetdebrief:39\nsetgluestatusmask:2000\ntestmission:\nendgame:\n[END]",
}


def campaign_with(results, terms=BF003_TERMS, coffers=500):
    campaign = _campaign()
    campaign.coffers = coffers
    campaign.begin_mission(terms)
    campaign.objective_results = dict(results)
    return campaign


class DebriefSceneTests(PostMissionCaravanTests):
    test_given_a_mission_that_ends_with_a_caravan_request_when_it_finishes_then_the_caravan_is_shown = None
    test_given_the_after_mission_caravan_when_the_select_hotspot_is_released_then_the_map_shows_the_next_step = None
    test_given_the_caravan_when_an_unimplemented_hotspot_is_released_then_it_stays_open = None
    test_given_a_recruit_caravan_when_its_exit_is_released_then_the_script_resumes_after_it = None

    def setUp(self):
        super().setUp()
        self.context.glue = GlueContent.from_data(resources=RESOURCES)

    def test_given_a_debrief_command_when_it_runs_then_the_balance_page_opens_and_pays_only_on_done(self):
        self.context.no_battle = False
        campaign = campaign_with(BF003_WON)
        machine = SceneMachine(GlueScene("DEBRIEFONLY", campaign), self.context)

        machine.update(0.1)

        self.assertIsInstance(machine.active, DebriefScene)
        self.assertEqual(machine.active.screen.page, "p4")
        self.assertEqual(campaign.coffers, 500)
        machine.handle("done")
        self.assertEqual(campaign.coffers, 900)
        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.runtime.state.status_bits, 1)  # the script resumed after the debrief

    def test_given_paging_events_when_they_arrive_then_the_screen_pages_and_done_pays_once(self):
        self.context.no_battle = False
        campaign = campaign_with(BF003_WON)
        scene = DebriefScene(GlueScene("DEBRIEFONLY", campaign), StartDebrief(1, 7, 1, True))
        scene.glue_scene.enter(self.context)
        scene.enter(self.context)

        scene.handle("page:next", self.context)
        self.assertEqual(scene.screen.page, "p4")
        scene.handle("page:back", self.context)

        self.assertEqual(scene.screen.page, "p2")

    def test_given_a_summary_whose_outcome_has_no_text_then_the_screen_is_skipped_and_the_script_resumes(self):
        self.context.no_battle = False
        campaign = campaign_with({"Z": (False, (10, 1, 0, 0))}, terms=CashTerms(0))
        machine = SceneMachine(GlueScene("SUMMARY", campaign), self.context)

        machine.update(0.1)
        machine.update(0.1)

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.runtime.state.status_bits, 1)

    def test_given_no_battle_mode_then_no_screen_opens(self):
        self.context.no_battle = True
        campaign = campaign_with(BF003_WON)
        machine = SceneMachine(GlueScene("DEBRIEFONLY", campaign), self.context)

        machine.update(0.1)

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(campaign.coffers, 900)


class CompletionTests(unittest.TestCase):
    def test_given_a_battle_without_debrief_when_it_completes_then_nothing_is_paid(self):
        campaign = campaign_with(BF003_WON)

        complete_debrief(campaign, StartDebrief(1, 6, 0, False))

        self.assertEqual(campaign.coffers, 500)
        self.assertFalse(campaign.mission_paid)

    def test_given_a_battle_with_debrief_when_it_completes_then_the_final_payment_is_credited(self):
        campaign = campaign_with(BF003_WON)

        complete_debrief(campaign, StartDebrief(1, 2, 1, False))

        self.assertEqual(campaign.coffers, 900)

    def test_given_a_played_defeat_when_it_completes_then_the_completion_payment_is_lost(self):
        results = played_results([("A", 32, 2), ("Z", 28, 2)], victory=False, required_letters=("A",),
                                 player_models=28, regiments_lost=2)
        campaign = campaign_with(results)

        complete_debrief(campaign, StartDebrief(1, 2, 1, False))

        self.assertEqual(campaign.coffers, 500)  # 100 already received cancels the initial; the 400 needs A


class PlayedResultTests(unittest.TestCase):
    OBJECTIVES = [("A", 32, 2), ("B", 80, 12), ("Z", 28, 2)]

    def test_given_a_victory_then_every_measured_letter_is_met_and_z_is_not(self):
        results = played_results(self.OBJECTIVES, victory=True, player_models=28)

        self.assertEqual([results[letter][0] for letter in "ABZ"], [True, True, False])

    def test_given_a_defeat_then_z_is_met_with_the_lost_regiments_and_nothing_else(self):
        results = played_results(self.OBJECTIVES, victory=False, player_models=28, regiments_lost=2)

        self.assertEqual([results[letter][0] for letter in "ABZ"], [False, False, True])
        self.assertEqual(results["Z"][1], (28, 2, 2, 0))

    def test_given_a_defeat_when_the_mission_defines_no_z_then_z_is_still_recorded(self):
        self.assertTrue(played_results([("A", 1, 1)], victory=False, player_models=5)["Z"][0])


class RewardTests(unittest.TestCase):
    def make(self, whoami=5, experience=0, wizard=False, spells=(), race=None, missile=None):
        base = regiment(whoami, base_price=20)
        row = replace(base.row, wizard=wizard)
        raw = None
        if wizard or race is not None or missile is not None:
            commands = "".join(f"addspell:{spell}\n" for spell in spells)
            stats = "setstats:s_move=4,3,0,3,3,1,3,1,7\n"
            if race is not None:
                stats += f"setstats:s_race={race}\n"
            if missile is not None:
                stats += f"setstats:S_BalWeap={missile}\n"
            tree = script.parse_text(f"[MERCARMY]\n[UNITS]\naddunit:Wizard\n{commands}"
                                     f"{stats}endunit:\n[END]\n[END]", "wizard")
            raw = tree["children"][0]["children"][0]
        return replace(base, row=row, experience=experience, profile=(4, 3, 0, 3, 3, 1, 3, 1, 7),
                       leader_profile=(4, 4, 0, 3, 3, 1, 3, 1, 7), leader_name="Leader", armour=2,
                       leader_armour=2, raw=raw)

    def test_given_experience_crossing_2000_then_ws_is_raised_and_price_and_worth_rise(self):
        company, applied, skipped = debrief_rewards.apply_rewards(
            [self.make()], [unit(whoami=5, experience=2100, experience_start=1900)], 1, False)

        (updated,) = company
        self.assertEqual((updated.profile[1], updated.leader_profile[1]), (4, 5))
        self.assertEqual((updated.row.base_price, updated.points), (25, 7))
        self.assertEqual(updated.experience, 2100)
        self.assertIn("Regiment5: +1 s_wepn", applied)
        self.assertEqual(skipped, [])

    def test_archers_and_artillery_gain_bs_instead_of_ws_at_2000(self):
        for shooter in (self.make(race=3 * 8), self.make(race=4 * 8),
                        self.make(race=1 * 8, missile=2)):
            with self.subTest(race=script.unit_view(shooter.raw)["stats"]):
                promoted, applied, _ = debrief_rewards.promote(shooter, 1900, 2100)

                self.assertEqual(promoted.profile[1:3], (3, 1))
                self.assertEqual(script.unit_view(promoted.raw)["profile"]["BS"], 1)
                self.assertEqual(promoted.leader_profile[1:3], (4, 1))
                self.assertIn("Regiment5: +1 s_bals", applied)

    def test_shooting_regiment_still_gains_strength_at_4000(self):
        shooter = self.make(race=3 * 8)

        promoted, applied, _ = debrief_rewards.promote(shooter, 1900, 4100)

        self.assertEqual(promoted.profile[1:4], (3, 1, 4))
        self.assertEqual(applied, ["Regiment5: +1 s_bals", "Regiment5: +1 s_strn"])

    def test_given_doubled_experience_then_the_gain_counts_twice_and_may_cross_two_thresholds(self):
        company, _, _ = debrief_rewards.apply_rewards(
            [self.make()], [unit(whoami=5, experience=2100, experience_start=1500)], 2, False)

        self.assertEqual(company[0].experience, 1500 + 600 * 2)
        self.assertEqual(company[0].profile[1], 4)  # 2700 crosses only 2000

    def test_given_no_threshold_crossed_then_no_stat_changes(self):
        company, _, _ = debrief_rewards.apply_rewards(
            [self.make()], [unit(whoami=5, experience=1500, experience_start=1000)], 1, False)

        self.assertEqual(company[0].profile, self.make().profile)

    def test_wizard_crossing_1000_learns_an_unknown_spell_and_gains_price_and_worth(self):
        wizard = self.make(wizard=True, spells=("GeneralDispel", "BrightFireball"))
        with patch("whshr.debrief_rewards.random.choice", return_value=6):
            company, applied, skipped = debrief_rewards.apply_rewards(
                [wizard], [unit(whoami=5, experience=1200, experience_start=900)], 1, False)

        promoted = company[0]
        self.assertEqual(script.unit_view(promoted.raw)["spells"],
                         ["GeneralDispel", "BrightFireball", "BrightPiercingBoltsOfBurning"])
        self.assertEqual((promoted.experience, promoted.points, promoted.row.base_price), (1200, 7, 35))
        self.assertEqual(promoted.profile, wizard.profile)
        self.assertIn("Regiment5: learned BrightPiercingBoltsOfBurning", applied)
        self.assertEqual(skipped, [])

    def test_wizard_crossing_multiple_thresholds_learns_until_five_spell_limit(self):
        wizard = self.make(wizard=True, spells=("GeneralDispel", "AmberFlyingBower", "AmberTanglingThorn"))
        with patch("whshr.debrief_rewards.random.choice", side_effect=lambda candidates: candidates[0]):
            promoted, _, _ = debrief_rewards.promote(wizard, 900, 3900)

        self.assertEqual(script.unit_view(promoted.raw)["spells"],
                         ["GeneralDispel", "AmberFlyingBower", "AmberTanglingThorn",
                          "AmberHuntingSpear", "AmberCurseOfAnraheir"])
        self.assertEqual((promoted.points, promoted.row.base_price), (14, 50))

    def test_wizard_without_a_known_college_does_not_gain_an_unrelated_spell(self):
        wizard = self.make(wizard=True, spells=("GeneralDispel",))

        promoted, applied, skipped = debrief_rewards.promote(wizard, 900, 1100)

        self.assertEqual(promoted, wizard)
        self.assertEqual(applied, [])
        self.assertIn("no known spell college", skipped[0])

    def test_given_an_armour_program_then_a_listed_regiment_with_models_gains_one_armour_on_troops_and_leader(self):
        company, applied, _ = debrief_rewards.apply_rewards(
            [self.make(whoami=4), self.make(whoami=5)], [unit(whoami=4), unit(whoami=5)], 1, True)

        self.assertEqual([(r.armour, r.leader_armour) for r in company], [(3, 3), (2, 2)])
        self.assertIn("Regiment4: +1 armour", applied)

    def test_given_an_armour_regiment_with_no_models_then_it_gains_nothing(self):
        company, _, _ = debrief_rewards.apply_rewards([self.make(whoami=4)], [unit(whoami=4, models=0)], 1, True)

        self.assertEqual(company[0].armour, 2)


class TestMissionTests(unittest.TestCase):
    def run_script(self, results, program="LASTBATTLE"):
        campaign = campaign_with(results)
        runtime = GlueRuntime(GlueContent.from_data(resources=RESOURCES), campaign)
        runtime.start(program)
        return runtime

    def test_given_a_lost_battle_when_testmission_runs_then_the_status_is_cleared(self):
        runtime = self.run_script({"Z": (True, (10, 1, 1, 0))})

        self.assertEqual(runtime.state.status_bits, 0)

    def test_given_a_survived_battle_when_testmission_runs_then_the_evaluator_sets_the_status(self):
        runtime = self.run_script({"Z": (False, (10, 1, 0, 0))})

        self.assertEqual(runtime.state.status_bits, 0x2000)

    def test_given_the_final_battle_when_c_is_met_then_only_the_first_ending_bit_is_set(self):
        runtime = self.run_script({"Z": (False, (10, 1, 0, 0)), "C": (True, (0, 0, 0, 0))}, "FINALBATTLE")

        self.assertEqual(runtime.state.status_bits & 0xC000, 0x4000)


if __name__ == "__main__":
    unittest.main()
