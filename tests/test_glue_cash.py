"""The ``cash`` command inside a running script (notes/glue_interpreter.md section 9, notes/campaign.md 2.5): it
stores the payment program on the mission in progress, the same line a mission record carries."""

import unittest

from whshr.campaign_state import CampaignState
from whshr.glue_content import GlueContent
from whshr.glue_runtime import Diagnostic, GlueRuntime
from whshr.payments import CashTerms, parse_cash

GRAPH = {"flow_scripts": {"FLOW": ({"action": "add_window", "window": "MISSIONS"},)},
         "mission_windows": {"MISSIONS": ()}}


def run(line, campaign=None):
    content = GlueContent.from_data(resources={"P": f"[RUN]\n[START]\n{line}\nendgame:\n[END]"})
    campaign = campaign if campaign is not None else CampaignState(GRAPH, flow="FLOW", coffers=500)
    return campaign, GlueRuntime(content, campaign).start("P")


class CashCommandTests(unittest.TestCase):
    def test_a_full_line_becomes_the_missions_payment_terms(self):
        campaign, effects = run("cash:1,100,400,50,25,A")

        self.assertEqual(campaign.mission_cash, CashTerms(1, 100, 400, 50, 25, ("A",)))
        self.assertFalse(any(isinstance(effect, Diagnostic) for effect in effects))

    def test_it_replaces_the_terms_the_mission_record_gave(self):
        campaign = CampaignState(GRAPH, flow="FLOW", coffers=500)
        campaign.begin_mission(parse_cash("1,100,400,50,25,A"))

        run("cash:3,0,800,0,0,B", campaign)

        self.assertEqual(campaign.mission_cash, CashTerms(3, 0, 800, 0, 0, ("B",)))

    def test_a_four_number_line_leaves_rate_b_zero_and_no_required_letter(self):
        campaign, _ = run("cash:5,0,5000,0,M")

        self.assertEqual(campaign.mission_cash, CashTerms(5, 0, 5000, 0, 0, ()))

    def test_a_line_without_a_numeric_type_is_reported_and_changes_nothing(self):
        campaign = CampaignState(GRAPH, flow="FLOW", coffers=500)
        campaign.begin_mission(parse_cash("1,100,400,50,25,A"))

        _, effects = run("cash:x,1,2", campaign)

        self.assertEqual(campaign.mission_cash, CashTerms(1, 100, 400, 50, 25, ("A",)))
        self.assertTrue(any(isinstance(effect, Diagnostic) and effect.location == "cash" for effect in effects))

    def test_without_a_campaign_it_is_reported_not_fatal(self):
        content = GlueContent.from_data(resources={"P": "[RUN]\n[START]\ncash:1,1,1,1,1,A\nendgame:\n[END]"})

        effects = GlueRuntime(content).start("P")

        self.assertTrue(any(isinstance(effect, Diagnostic) for effect in effects))

    def test_it_does_not_touch_the_coffers(self):
        campaign, _ = run("cash:1,100,400,50,25,A")

        self.assertEqual(campaign.coffers, 500)


if __name__ == "__main__":
    unittest.main()
