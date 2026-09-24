"""Mission payments (issue #124, notes/campaign.md sections 2.3 and 2.5, notes/debrief_evaluation.md section 2):
the `cash` line, the balance-sheet programs, the flawless no-battle result and their use at the debrief."""
import json
import unittest

from tests.test_debrief_flow import RESOURCES, _campaign
from tests.test_post_mission_caravan import PostMissionCaravanTests
from tests.test_troop_selection import regiment
from whshr.campaign_log import CampaignLogger
from whshr.debrief import complete_debrief
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput, GlueRuntime, StartDebrief
from whshr.glue_scene import GlueScene
from whshr.payments import flawless_results, parse_cash, settle
from whshr.scenes import SceneMachine
from whshr.troop_selection import TroopSelection

DEBRIEF = StartDebrief(1, 4, 0, False)


def _met(*values):
    return True, values


class CashLineTests(unittest.TestCase):
    def test_given_a_full_cash_line_when_parsed_then_every_field_and_the_required_letters_are_read(self):
        terms = parse_cash("1,100,400,50,25,A,Q")

        self.assertEqual((terms.type, terms.initial, terms.completion, terms.rate_a, terms.rate_b, terms.letters),
                         (1, 100, 400, 50, 25, ("A", "Q")))

    def test_given_a_four_number_march_line_when_parsed_then_the_marker_is_no_required_letter(self):
        terms = parse_cash("5,0,5000,0,M")

        self.assertEqual((terms.type, terms.completion, terms.rate_b, terms.letters), (5, 5000, 0, ()))

    def test_given_no_cash_line_when_parsed_then_there_are_no_terms(self):
        self.assertIsNone(parse_cash(""))


class BalanceSheetTests(unittest.TestCase):
    def test_given_the_first_mission_sheet_when_all_objectives_hold_then_the_final_payment_excludes_the_initial_one(self):
        terms = parse_cash("1,100,400,50,25,A")
        results = {"A": _met(32, 2, 0, 0), "B": _met(80, 12, 100, 12), "C": _met(80, 7, 100, 7)}

        sheet = settle(terms, results)

        self.assertEqual(sheet.final, 400)  # 100 + 400 - 100 received; villagers and buildings lost nothing
        self.assertEqual(sheet.skipped, [])

    def test_given_lost_villagers_and_buildings_when_settled_then_each_is_charged_at_its_rate(self):
        terms = parse_cash("1,100,400,50,25,A")
        results = {"A": _met(32, 2, 0, 0), "B": _met(80, 12, 83, 10), "C": _met(80, 7, 71, 5)}

        self.assertEqual(settle(terms, results).final, 400 - 50 * 2 - 25 * 2)

    def test_given_a_required_letter_that_failed_when_settled_then_no_completion_payment_is_made(self):
        terms = parse_cash("3,0,1000,0,0,A")

        self.assertEqual(settle(terms, {"A": (False, (0, 0, 0, 0))}).final, 0)
        self.assertEqual(settle(terms, {"A": _met(0, 0, 0, 0)}).final, 1000)

    def test_given_two_required_letters_when_one_fails_then_the_completion_is_withheld(self):
        terms = parse_cash("3,0,800,0,0,A,Q")

        self.assertEqual(settle(terms, {"A": _met(0, 0, 0, 0), "Q": (False, (60, 10, 50, 5))}).final, 0)

    def test_given_penalties_above_the_total_when_settled_then_the_final_payment_is_never_negative(self):
        terms = parse_cash("16,0,100,10,50,A")
        results = {"A": _met(0, 0, 0, 0), "B": _met(0, 10, 0, 0), "C": _met(0, 10, 0, 0)}

        self.assertEqual(settle(terms, results).final, 0)  # 100 - 10*10 - 50*10 < 0

    def test_given_a_type_with_a_prepaid_initial_payment_when_settled_then_the_received_line_subtracts_it(self):
        sheet = settle(parse_cash("8,500,1000,0,0,A"), {"A": _met(0, 0, 0, 0)})

        self.assertEqual([line for line in sheet.lines if line[0] in ("initial", "received")],
                         [("initial", 500), ("received", -500)])
        self.assertEqual(sheet.final, 1000)

    def test_given_bonus_lines_when_settled_then_counter_and_measured_values_are_paid_at_rate_a(self):
        skaven = settle(parse_cash("4,200,200,20,0"), {}, bonus_counter=47)
        lobbers = settle(parse_cash("9,0,1000,300,100"), {"W": _met(32, 3, 0, 3)})
        men = settle(parse_cash("11,0,500,25,0,A"), {"A": _met(0, 0, 0, 0), "Z": (False, (28, 2, 0, 0))})
        dwarfs = settle(parse_cash("17,0,0,200,0"), {"B": _met(0, 12, 0, 12)})

        self.assertEqual(skaven.final, 200 + 20 * 47)
        self.assertEqual(lobbers.final, 300 * 3 + 100)  # all destroyed adds rate B
        self.assertEqual(men.final, 500 + 25 * 28)
        self.assertEqual(dwarfs.final, 200 * 12)

    def test_given_a_line_the_notes_leave_open_when_settled_then_it_is_skipped_with_a_reason(self):
        sheet = settle(parse_cash("14,0,1500,200,0,A"), {"A": _met(0, 0, 0, 0)})

        self.assertEqual(sheet.final, 1500)
        self.assertTrue(any(text.startswith("hiln") for text in sheet.skipped))

    def test_given_a_line_whose_objective_is_absent_when_settled_then_only_that_line_is_skipped(self):
        sheet = settle(parse_cash("10,0,600,10,0,A"), {"A": _met(0, 0, 0, 0)})

        self.assertEqual(sheet.final, 600)
        self.assertTrue(any(text.startswith("livestock") for text in sheet.skipped))

    def test_given_the_march_types_when_settled_then_the_arrival_payment_needs_no_letters(self):
        for kind in (5, 6, 18):
            self.assertEqual(settle(parse_cash(f"{kind},0,2000,0,M"), {}).final, 2000)


class FlawlessResultTests(unittest.TestCase):
    def test_given_battle_objectives_when_flawless_then_win_letters_are_met_with_full_values(self):
        results = flawless_results([["Z", 28, 2], ["A", 32, 2], ["B", 80, 12], ["V", 5, 47], ["W", 32, 3]])

        self.assertEqual(results["A"], (True, (32, 2, 0, 0)))
        self.assertEqual(results["B"], (True, (80, 12, 100, 12)))
        self.assertEqual(results["V"], (True, (5, 47, 0, 47)))  # every Skaven head counted
        self.assertEqual(results["W"], (True, (32, 3, 0, 3)))

    def test_given_the_defeat_letter_when_flawless_then_it_is_not_met_and_carries_the_army_size(self):
        results = flawless_results([["Z", 28, 2], ["G", 1, 4]], player_models=30)

        self.assertEqual(results["Z"], (False, (30, 2, 0, 0)))
        self.assertFalse(results["G"][0])

    def test_given_required_letters_when_flawless_then_they_are_met_even_when_the_battle_lacks_them(self):
        results = flawless_results([], required_letters=("A", "M"))

        self.assertTrue(results["A"][0] and results["M"][0])

    def test_given_a_flawless_result_when_settled_then_the_first_mission_pays_in_full(self):
        results = flawless_results([["Z", 28, 2], ["A", 32, 2], ["B", 80, 12], ["C", 80, 7]], ("A",))

        self.assertEqual(settle(parse_cash("1,100,400,50,25,A"), results).final, 400)


class CompletionTests(unittest.TestCase):
    def _campaign(self, cash):
        campaign = _campaign()
        campaign.begin_mission(parse_cash(cash))
        return campaign

    def test_given_results_when_the_debrief_completes_then_the_final_payment_is_credited_once(self):
        campaign = self._campaign("3,0,1000,0,0,A")
        campaign.objective_results["A"] = _met(0, 0, 0, 0)

        applied, _ = complete_debrief(campaign, DEBRIEF)
        complete_debrief(campaign, DEBRIEF)

        self.assertEqual(campaign.coffers, 1500)
        self.assertIn("final payment: 1000 crowns", applied)

    def test_given_no_objective_results_when_the_debrief_completes_then_nothing_is_paid_and_it_says_why(self):
        campaign = self._campaign("3,0,1000,0,0,A")

        applied, skipped = complete_debrief(campaign, DEBRIEF)

        self.assertEqual((campaign.coffers, applied), (500, []))
        self.assertTrue(any("no objective results" in text for text in skipped))

    def test_given_no_battle_mode_and_no_battle_when_the_debrief_completes_then_it_counts_as_a_flawless_win(self):
        campaign = self._campaign("6,0,2000,0,M")

        complete_debrief(campaign, DEBRIEF, flawless=True)

        self.assertEqual(campaign.coffers, 2500)

    def test_given_a_new_mission_when_it_begins_then_the_old_result_and_payment_flag_are_forgotten(self):
        campaign = self._campaign("3,0,1000,0,0,A")
        campaign.objective_results["A"] = _met(0, 0, 0, 0)
        complete_debrief(campaign, DEBRIEF)

        campaign.begin_mission(parse_cash("3,0,800,0,0,A"))

        self.assertEqual((campaign.objective_results, campaign.mission_paid), ({}, False))


class TroopSelectionPaymentTests(unittest.TestCase):
    def test_given_the_worked_example_when_the_selection_is_confirmed_then_the_coffers_are_280(self):
        # notes/campaign.md 2.2: 500 + 100 initial payment - (cavalry 16 x 12 + infantry 8 x 16 = 320)
        company = [regiment(2, base_price=12, models=16), regiment(3, base_price=16, models=8)]
        selection = TroopSelection(company, coffers=500, prepaid=100)
        selection.toggle(3)

        deployment = selection.confirm()

        self.assertEqual(500 + deployment.money_delta, 280)

    def test_given_a_forced_regiment_dearer_than_the_coffers_when_a_prepaid_payment_covers_it_then_it_is_not_bankrupt(self):
        company = [regiment(2, base_price=10, models=10)]

        self.assertTrue(TroopSelection(company, coffers=50, prepaid=0).bankrupt)
        self.assertFalse(TroopSelection(company, coffers=50, prepaid=50).bankrupt)


class DebriefSceneTests(PostMissionCaravanTests):
    test_given_a_mission_that_ends_with_a_caravan_request_when_it_finishes_then_the_caravan_is_shown = None
    test_given_the_after_mission_caravan_when_the_select_hotspot_is_released_then_the_map_shows_the_next_step = None
    test_given_the_caravan_when_an_unimplemented_hotspot_is_released_then_it_stays_open = None
    test_given_a_recruit_caravan_when_its_exit_is_released_then_the_script_resumes_after_it = None

    def setUp(self):
        super().setUp()
        self.context.glue = GlueContent.from_data(resources=RESOURCES)
        self.log = CampaignLogger(self.root / "log.jsonl")
        self.context.campaign_log = self.log
        self.addCleanup(self.log.close)

    def _rows(self, kind):
        self.log.close()
        rows = [json.loads(line) for line in (self.root / "log.jsonl").read_text().splitlines()]
        return [row for row in rows if row["type"] == kind]

    def test_given_no_battle_mode_when_a_debrief_runs_then_the_flawless_payment_is_credited_and_logged(self):
        self.context.no_battle = True
        campaign = _campaign()
        campaign.begin_mission(parse_cash("1,100,400,50,25,A"))
        SceneMachine(GlueScene("DEBRIEFONLY", campaign), self.context).update(0.1)

        self.assertEqual(campaign.coffers, 900)
        (row,) = self._rows("payment")
        self.assertEqual((row["kind"], row["amount"], row["coffers"]), ("final", 400, 900))
        self.assertIn(["completion", 400], row["lines"])

    def test_given_a_played_battle_without_results_when_a_debrief_runs_then_the_payment_is_skipped_with_a_diagnostic(self):
        self.context.no_battle = False
        campaign = _campaign()
        campaign.begin_mission(parse_cash("1,100,400,50,25,A"))
        SceneMachine(GlueScene("DEBRIEFONLY", campaign), self.context).update(0.1)

        self.assertEqual(campaign.coffers, 500)
        (row,) = self._rows("payment")
        self.assertEqual(row["amount"], 0)
        self.assertTrue(any("no objective results" in text for text in row["skipped"]))

    def test_given_a_flawless_result_when_the_commands_run_then_testobjective_and_bonusadd_see_a_perfect_win(self):
        campaign = _campaign()
        campaign.objective_results = flawless_results([["E", 100, 40], ["V", 5, 47]])
        campaign.flawless_result = True
        resources = {**RESOURCES, "FLAW": "[RUN]\n[START]\nbonusinit:\nbonusadd:4,V\nsetgluestatusmask:1\ntestobjective:E\nendgame:\n[END]"}
        runtime = GlueRuntime(GlueContent.from_data(resources=resources), campaign)

        runtime.start("FLAW")

        self.assertEqual(campaign.bonus_counter, 47)
        self.assertEqual(runtime.state.status_bits, 1)

    def test_given_a_flawless_result_when_testmission_runs_then_the_mission_is_won(self):
        campaign = _campaign()
        campaign.flawless_result = True
        runtime = GlueRuntime(GlueContent.from_data(resources=RESOURCES), campaign)

        runtime.start("MISSIONTEST")

        self.assertEqual(runtime.state.status_bits, 1)


if __name__ == "__main__":
    unittest.main()
