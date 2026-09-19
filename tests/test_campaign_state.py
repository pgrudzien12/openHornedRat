import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from whshr.briefing import load_briefing
from whshr.campaign import (
    parse_mission_script, parse_mission_windows, parse_window_hotspots, parse_window_portrait, parse_window_ui,
)
from whshr.campaign_state import CampaignState, caravan_scroll_count, eligible_missions


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
                    {"name_id": 603, "name": "Unlocked", "battle": "BF001", "depend": 602},
                    {"name_id": 604, "name": "Unfinished", "battle": "BF006", "inactivedepend": 603},
                ],
                "BRANCHED": [{"name_id": 605, "name": "Branch", "battle": "BF007"}],
            },
        }

    def test_given_a_new_campaign_then_the_first_flow_window_and_500_crowns_are_active(self):
        state = CampaignState(self.graph)

        self.assertEqual((state.flow, state.mission_window, state.coffers), ("FLOWSCRIPTBP01", "FIRST", 500))
        self.assertEqual([mission["battle"] for mission in state.missions], ["BF003"])

    def test_given_duplicate_battle_ids_when_loading_a_briefing_then_the_mission_record_selects_its_own_script(self):
        graph = {"mission_windows": {"FIRST": [
            {"briefing_key": "first.0", "battle": "BF003", "name": "Placeholder", "brief_script": "FIRSTBRIEF"},
            {"briefing_key": "first.1", "battle": "BF003", "name": "Actual mission", "brief_script": "SECONDBRIEF"},
        ]}}
        strings = MagicMock()
        strings.load_strings.return_value = {902: "The selected record's briefing."}

        with tempfile.TemporaryDirectory() as root, \
             patch("whshr.briefing.build_campaign_graph", return_value=graph), \
             patch("whshr.briefing.load_wnd_rcdata", return_value={"SECONDBRIEF": "playtext:res=902"}), \
             patch("whshr.briefing.module", return_value=strings):
            dll = Path(root) / "FILE/DLL"
            dll.mkdir(parents=True)
            (dll / "WND.DLL").touch()
            (dll / "BRTXT.DLL").touch()
            briefing = load_briefing(root, "first.1")

        self.assertEqual(briefing, {
            "battle": "BF003", "title": "Actual mission",
            "lines": [{"speaker_color": None, "text": "The selected record's briefing."}],
        })

    def test_given_a_completed_mission_then_its_dependency_gates_control_the_next_window(self):
        state = CampaignState(self.graph)

        state.complete(state.missions[0])

        self.assertEqual(state.mission_window, "SECOND")
        self.assertEqual([mission["name"] for mission in state.missions], ["Always", "Unfinished"])

    def test_given_a_replacement_flow_then_completion_opens_that_flows_first_window(self):
        state = CampaignState(self.graph)
        state.graph["mission_windows"]["FIRST"][0]["replacescript"] = "BRANCH"

        state.complete(state.missions[0])

        self.assertEqual((state.flow, state.mission_window), ("BRANCH", "BRANCHED"))

    def test_given_dependency_gates_then_they_follow_the_taken_and_on_offer_rules(self):
        missions = [{"name_id": 1, "name": "base"},
                    {"name_id": 2, "name": "needs", "depend": 1},
                    {"name_id": 3, "name": "while-2-hidden", "inactivedepend": 2}]

        self.assertEqual([m["name"] for m in eligible_missions(missions, set())], ["base", "while-2-hidden"])
        # 2 is now on offer, so 3 hides, and 1 (taken) is gone
        self.assertEqual([m["name"] for m in eligible_missions(missions, {1})], ["needs"])
        self.assertEqual([m["name"] for m in eligible_missions(missions, {1, 2})], ["while-2-hidden"])

    def test_given_a_gate_on_a_mission_outside_the_window_then_it_is_ignored(self):
        missions = [{"name_id": 683, "name": "Rescue", "depend": 682}]

        self.assertEqual(len(eligible_missions(missions, set())), 1)

    def test_given_offered_missions_then_scrolls_are_one_fewer_capped_at_three(self):
        self.assertEqual([caravan_scroll_count(n) for n in range(6)], [0, 0, 1, 2, 3, 3])

    def test_given_envoy_to_nuln_then_scrolls_follow_2_0_1_as_missions_are_taken(self):
        window = [{"name_id": 671}, {"name_id": 672, "depend": 671},
                  {"name_id": 673, "inactivedepend": 672}, {"name_id": 628, "inactivedepend": 672}]
        counts = [caravan_scroll_count(len(eligible_missions(window, taken)))
                  for taken in (set(), {671}, {671, 672})]

        self.assertEqual(counts, [2, 0, 1])

    def test_given_a_mission_without_release_flag_then_the_player_stays_on_the_window(self):
        self.graph["mission_windows"]["FIRST"].append({"name_id": 609, "name": "Extra", "battle": "BF009"})
        state = CampaignState(self.graph)

        state.complete(state.missions[0])

        self.assertEqual(state.mission_window, "FIRST")
        self.assertEqual([m["name"] for m in state.missions], ["Extra"])

    def test_given_a_release_flag_then_the_flow_advances(self):
        self.graph["mission_windows"]["FIRST"].append({"name_id": 609, "name": "Extra", "battle": "BF009"})
        self.graph["mission_windows"]["FIRST"][0]["releaseflag"] = 1
        state = CampaignState(self.graph)

        state.complete(state.missions[0])

        self.assertEqual(state.mission_window, "SECOND")

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

    def test_given_a_speaker_window_then_its_position_and_anim_settings_are_data_driven(self):
        portrait = parse_window_portrait({"SCRIBEMWINDOW": """
            [WINDOW]
            [POSITION]
                set:x=450
                set:y=25
                set:vx=144
                set:vy=240
            [END]
            [ANIM]
                set:index=4
                set:bkindex=15
                set:controlpanel=2
                settextcolor:red
                name:Dietrich
            [END]
            [END]
        """}, "scribemwindow")

        self.assertEqual(portrait, {
            "window": "SCRIBEMWINDOW", "position": {"x": 450, "y": 25, "vx": 144, "vy": 240},
            "index": 4, "bkindex": 15, "controlpanel": 2, "text_color": "red", "speaker": "Dietrich",
        })

    def test_given_a_window_with_included_controls_then_its_render_data_and_targets_are_preserved(self):
        wnd = {
            "MAP": """
                [WINDOW]
                [POSITION]
                    set:x=0
                    set:y=0
                    set:vx=640
                    set:vy=480
                    set:palindex=2
                [END]
                [BITMAP]
                    setbitmap:MAP
                    set:x=4
                    set:y=5
                    set:animstartframe=2
                    set:animstopframe=8
                    set:timecnt=90
                [END]
                [INCLUDE]
                    script:CONTROLS
                [END]
                [END]
            """,
            "CONTROLS": """
                [WINDOW]
                [HOTSPOT]
                    set:x=1
                    set:y=2
                    set:vx=3
                    set:vy=4
                    set:res=150
                    script:PopContext
                [END]
                [ANIM]
                    set:index=4
                    set:bkindex=15
                    set:controlpanel=2
                    settextcolor:red
                    name:Dietrich
                [END]
                [END]
            """,
        }

        self.assertEqual(parse_window_ui(wnd, "map"), {
            "window": "MAP", "position": {"x": 0, "y": 0, "vx": 640, "vy": 480, "palindex": 2},
            "bitmaps": [{"bitmap": "MAP", "x": 4, "y": 5, "animstartframe": 2, "animstopframe": 8, "timecnt": 90}],
            "hotspots": [{"x": 1, "y": 2, "vx": 3, "vy": 4, "res": 150, "target": "PopContext", "target_kind": "script"}],
            "anims": [{"index": 4, "bkindex": 15, "controlpanel": 2, "text_color": "red", "name": "Dietrich"}],
        })

    def test_given_a_release_flag_in_a_mission_window_then_it_is_parsed(self):
        windows = parse_mission_windows({"MISSIONTESTWINDOW": "[MISSION]\nset:res=601\nset:releaseflag=1\n[END]"})

        self.assertEqual(windows["MISSIONTESTWINDOW"][0]["releaseflag"], 1)

    def test_given_a_mission_script_then_its_caravan_modes_conditions_and_endgame_are_retained(self):
        parsed = parse_mission_script("""
            gocaravan:resume
            iftruegocaravan:infoREC
            iffalsegocaravan:select
            endgame:
        """)

        self.assertEqual(parsed["summary"]["caravan_entries"], [
            {"mode": "resume"}, {"mode": "inforec", "condition": "true"},
            {"mode": "select", "condition": "false"},
        ])
        self.assertTrue(parsed["summary"]["ends_game"])

    def test_given_caravan_includes_then_hotspots_keep_their_hint_ids_and_geometry(self):
        wnd = {
            "START": """
                [WINDOW]
                [HOTSPOT]
                    set:x=1
                    set:y=2
                    set:vx=3
                    set:vy=4
                    set:res=150
                    res:FlowScript
                [END]
                [INCLUDE]
                    script:Common
                [END]
                [END]
            """,
            "COMMON": """
                [WINDOW]
                [HOTSPOT]
                    set:x=5
                    set:y=6
                    set:vx=7
                    set:vy=8
                    set:res=-1
                [END]
                [END]
            """,
        }

        self.assertEqual(parse_window_hotspots(wnd, "start"), [
            {"x": 1, "y": 2, "vx": 3, "vy": 4, "res": 150},
            {"x": 5, "y": 6, "vx": 7, "vy": 8, "res": -1},
        ])


if __name__ == "__main__":
    unittest.main()
