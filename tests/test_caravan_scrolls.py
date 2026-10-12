"""Caravan scroll pile: drawn from the missions the map will offer (notes/campaign.md sections 7.2, 7.4, 7.6).

The engine deliberately does not copy the original's stale cached count (user decision): the pile always shows
the missions on offer, counted live, in the window the player returns to.
"""
import unittest

from whshr.campaign_state import CampaignState
from whshr.frontend.glue_view import _bitmap_visible
from whshr.glue import MissionRef
from whshr.glue_content import GlueContent
from whshr.glue_render import RenderBitmap
from whshr.glue_runtime import GlueRuntime
from whshr.savegame import campaign_to_dict, restore_campaign

# The section 7.6 "Envoy" shape: 671, 672 (depend 671), 673 (inactivedepend 672), 628 (inactivedepend 672, releases).
ENVOY = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
         "[MISSION]\nset:res=671\n[END]\n"
         "[MISSION]\nset:res=672\nset:depend=671\n[END]\n"
         "[MISSION]\nset:res=673\nset:inactivedepend=672\n[END]\n"
         "[MISSION]\nset:res=628\nset:inactivedepend=672\nset:releaseflag=1\n[END]")
# The next chapter, reusing name ids 671 and 628 as the shipped windows do.
NEXT = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
        "[MISSION]\nset:res=671\n[END]\n"
        "[MISSION]\nset:res=628\n[END]")
# A one-mission chapter and a replacement flow's window.
SINGLE = "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n[MISSION]\nset:res=690\n[END]"
SIDE = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
        "[MISSION]\nset:res=691\n[END]\n[MISSION]\nset:res=692\n[END]\n[MISSION]\nset:res=693\n[END]\n"
        "[MISSION]\nset:res=694\n[END]")
MAP = "[WINDOW]\n[END]"
MARK = "[WINDOW]\n[END]"
# A briefing that opens its own map window and adds a mark to it (no [MISSION] records).
BRIEF_FLOW = "[RUN]\n[START]\nopenwindow:res=MAP\nsetcurwindow:res=MAP\naddobject:res=MARK\nwaitforrelease:\n[END]"
SCROLLS = (RenderBitmap("CarScroll1", animation=(("depend", 4),)),
           RenderBitmap("CarScroll2", animation=(("depend", 3),)),
           RenderBitmap("CarScroll3", animation=(("depend", 2),)))


def _mission(window: str, index: int, name_id: int, **extra: object) -> dict[str, object]:
    return {"name_id": name_id, "mission_ref": MissionRef(window, index), **extra}


GRAPH = {
    "flow_scripts": {
        "FLOW": [{"action": "add_window", "window": "ENVOY"}, {"action": "add_window", "window": "SINGLE"},
                 {"action": "add_window", "window": "NEXT"}],
        "SIDEFLOW": [{"action": "add_window", "window": "SIDE"}],
    },
    "mission_windows": {
        "ENVOY": [_mission("ENVOY", 0, 671), _mission("ENVOY", 1, 672, depend=671),
                  _mission("ENVOY", 2, 673, inactivedepend=672),
                  _mission("ENVOY", 3, 628, inactivedepend=672, releaseflag=1)],
        "SINGLE": [_mission("SINGLE", 0, 690)],
        "NEXT": [_mission("NEXT", 0, 671), _mission("NEXT", 1, 628)],
        "SIDE": [_mission("SIDE", i, 691 + i) for i in range(4)],
    },
}


def _campaign(window: str = "ENVOY", step: int = 0) -> CampaignState:
    content = GlueContent.from_data(resources={"ENVOY": ENVOY, "NEXT": NEXT, "SINGLE": SINGLE, "SIDE": SIDE,
                                               "MAP": MAP, "MARK": MARK, "BRIEF_FLOW": BRIEF_FLOW})
    return CampaignState(GRAPH, flow="FLOW", flow_step=step, mission_window=window, content=content)


def _drawn(campaign: object) -> list[str]:
    return [bitmap.name for bitmap in SCROLLS if _bitmap_visible(bitmap, campaign)]  # type: ignore[arg-type]


class Counted:
    def __init__(self, count: int) -> None:
        self.scroll_count = count


class ScrollPileTests(unittest.TestCase):
    def test_scrolls_fill_in_reverse_order_as_the_count_grows(self):
        expected = {0: [], 1: [], 2: ["CarScroll3"], 3: ["CarScroll2", "CarScroll3"],
                    4: ["CarScroll1", "CarScroll2", "CarScroll3"], 6: ["CarScroll1", "CarScroll2", "CarScroll3"]}
        for count, drawn in expected.items():
            with self.subTest(count=count):
                self.assertEqual(_drawn(Counted(count)), drawn)

    def test_a_bitmap_with_depend_zero_or_without_depend_is_always_drawn(self):
        self.assertTrue(_bitmap_visible(RenderBitmap("Any", animation=(("depend", 0),)), Counted(0)))  # type: ignore[arg-type]
        self.assertTrue(_bitmap_visible(RenderBitmap("CarScroll1"), Counted(0)))  # type: ignore[arg-type]

    def test_without_a_campaign_every_scroll_is_drawn(self):
        self.assertEqual(len(_drawn(None)), 3)


class ScrollCountTests(unittest.TestCase):
    def test_worked_example_counts_three_then_one_then_two_as_missions_are_released(self):
        campaign = _campaign()
        self.assertEqual(campaign.scroll_count, 3)
        campaign.complete(GRAPH["mission_windows"]["ENVOY"][0])
        self.assertEqual(campaign.scroll_count, 1)
        campaign.complete(GRAPH["mission_windows"]["ENVOY"][1])
        self.assertEqual(campaign.scroll_count, 2)

    def test_given_a_mission_is_picked_but_not_taken_then_it_still_counts(self):
        campaign = _campaign()
        campaign.select_mission(MissionRef("ENVOY", 0))
        self.assertEqual(campaign.scroll_count, 3)

    def test_given_an_after_mission_caravan_with_missions_left_then_the_current_list_is_counted(self):
        campaign = _campaign()
        campaign.mark_mission_taken(MissionRef("ENVOY", 0))  # played, not released yet
        self.assertEqual(campaign.scroll_count, 1)

    def test_given_an_after_mission_caravan_of_a_releasing_mission_then_the_next_chapter_is_counted(self):
        campaign = _campaign()
        campaign.mark_mission_taken(MissionRef("ENVOY", 3))  # releaseflag: the flow moves on to SINGLE
        self.assertEqual(campaign.upcoming_mission_window(), "SINGLE")
        self.assertEqual(campaign.scroll_count, 1)

    def test_given_the_last_mission_of_a_chapter_was_played_then_the_next_chapter_is_counted(self):
        campaign = _campaign("SINGLE", step=1)
        campaign.mark_mission_taken(MissionRef("SINGLE", 0))
        self.assertEqual(campaign.upcoming_mission_window(), "NEXT")
        self.assertEqual(campaign.scroll_count, 2)

    def test_given_a_mission_with_a_replacement_flow_then_that_flows_window_is_counted(self):
        campaign = _campaign("SINGLE", step=1)
        campaign.graph = {**GRAPH, "mission_windows": {
            **GRAPH["mission_windows"], "SINGLE": [_mission("SINGLE", 0, 690, replacescript="SIDEFLOW")]}}
        campaign.mark_mission_taken(MissionRef("SINGLE", 0))
        self.assertEqual(campaign.scroll_count, 4)

    def test_given_the_same_name_id_was_finished_in_another_window_then_this_window_still_counts_it(self):
        campaign = _campaign("NEXT", step=2)
        campaign.completed.update({671, 628})
        campaign.taken_missions.update({MissionRef("ENVOY", 0), MissionRef("ENVOY", 3)})
        campaign.released_missions.update({MissionRef("ENVOY", 0), MissionRef("ENVOY", 3)})
        self.assertEqual(campaign.scroll_count, 2)

    def test_a_briefing_that_marks_its_own_map_does_not_change_the_count(self):
        campaign = _campaign()
        GlueRuntime(campaign.content, campaign).start("BRIEF_FLOW")  # type: ignore[arg-type]
        self.assertEqual(campaign.scroll_count, 3)


class ReleasedMissionSaveTests(unittest.TestCase):
    def test_released_missions_survive_a_save_and_load(self):
        campaign = _campaign()
        campaign.complete(GRAPH["mission_windows"]["ENVOY"][0])
        campaign.mark_mission_taken(MissionRef("ENVOY", 1))
        loaded = _campaign()

        restore_campaign(loaded, campaign_to_dict(campaign), repair_stalled=False)

        self.assertEqual(loaded.released_missions, {MissionRef("ENVOY", 0)})
        self.assertEqual(loaded.pending_release(), GRAPH["mission_windows"]["ENVOY"][1])

    def test_an_older_save_treats_the_uncompleted_taken_mission_of_its_window_as_pending(self):
        campaign = _campaign("SINGLE", step=1)
        campaign.mark_mission_taken(MissionRef("SINGLE", 0))
        data = campaign_to_dict(campaign)
        del data["released_missions"]
        loaded = _campaign()

        restore_campaign(loaded, data, repair_stalled=False)

        self.assertEqual(loaded.released_missions, set())
        self.assertEqual(loaded.scroll_count, 2)


if __name__ == "__main__":
    unittest.main()
