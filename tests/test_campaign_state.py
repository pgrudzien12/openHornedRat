import unittest

from whshr.campaign import parse_mission_windows
from whshr.campaign_state import CampaignState, eligible_missions


class CampaignStateTests(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "flow_scripts": {
                "FLOWSCRIPTBP01": (
                    {"action": "set_tentpos", "pos": 0},
                    {"action": "add_window", "window": "FIRST"},
                    {"action": "wait_player_choice"},
                    {"action": "add_window", "window": "SECOND"},
                ),
                "BRANCH": ({"action": "add_window", "window": "BRANCHED"},),
            },
            "mission_windows": {
                "FIRST": [{"name_id": 601, "name": "First", "battle": "BF003"}],
                "SECOND": [
                    {"name_id": 602, "name": "Always", "battle": "BF005"},
                    {"name_id": 603, "name": "Unlocked", "battle": "BF001", "depend": 601},
                    {"name_id": 604, "name": "Unfinished", "battle": "BF006", "inactivedepend": 601},
                ],
                "BRANCHED": [{"name_id": 605, "name": "Branch", "battle": "BF007"}],
            },
        }

    def test_given_a_new_campaign_then_the_first_flow_window_and_500_crowns_are_active(self):
        state = CampaignState(self.graph)

        self.assertEqual((state.flow, state.mission_window, state.coffers), ("FLOWSCRIPTBP01", "FIRST", 500))
        self.assertEqual([mission["battle"] for mission in state.missions], ["BF003"])

    def test_given_a_completed_mission_then_its_dependency_gates_control_the_next_window(self):
        state = CampaignState(self.graph)

        state.complete(state.missions[0])

        self.assertEqual(state.mission_window, "SECOND")
        self.assertEqual([mission["name"] for mission in state.missions], ["Always", "Unlocked"])

    def test_given_a_replacement_flow_then_completion_opens_that_flows_first_window(self):
        state = CampaignState(self.graph)
        state.graph["mission_windows"]["FIRST"][0]["replacescript"] = "BRANCH"

        state.complete(state.missions[0])

        self.assertEqual((state.flow, state.mission_window), ("BRANCH", "BRANCHED"))

    def test_given_missions_with_dependency_gates_then_only_matching_entries_are_eligible(self):
        missions = [{"name": "base"}, {"name": "needs", "depend": 7}, {"name": "not-done", "inactivedepend": 7}]

        self.assertEqual([mission["name"] for mission in eligible_missions(missions, {7})], ["base", "needs"])

    def test_given_a_mission_window_then_its_original_dependency_gates_are_retained(self):
        windows = parse_mission_windows({"MISSIONTESTWINDOW": """
            [MISSION]
                set:res=601
                set:depend=600
                set:inactivedepend=599
            [END]
        """})

        self.assertEqual(windows["MISSIONTESTWINDOW"], [{"name_id": 601, "name": "MISSION_601",
                          "depend": 600, "inactivedepend": 599}])


if __name__ == "__main__":
    unittest.main()
