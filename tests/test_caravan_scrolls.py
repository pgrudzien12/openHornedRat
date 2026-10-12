"""Caravan scroll pile: a cached count of missions on offer, notes/campaign.md sections 7.4-7.6."""
import unittest

from whshr.campaign_state import CampaignState
from whshr.frontend.glue_view import _bitmap_visible
from whshr.glue import MissionRef
from whshr.glue_content import GlueContent
from whshr.glue_render import RenderBitmap
from whshr.glue_runtime import GlueRuntime
from whshr.savegame import campaign_to_dict

# The section 7.6 "Envoy" shape: 1, 2 (depend on 1), 3 (inactivedepend on 2), 4 (inactivedepend on 2, releases).
ENVOY = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
         "[MISSION]\nset:res=671\n[END]\n"
         "[MISSION]\nset:res=672\nset:depend=671\n[END]\n"
         "[MISSION]\nset:res=673\nset:inactivedepend=672\n[END]\n"
         "[MISSION]\nset:res=628\nset:inactivedepend=672\nset:releaseflag=1\n[END]")
# Another window reusing name ids 671 and 628, as the shipped windows do.
OTHER = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
         "[MISSION]\nset:res=671\n[END]\n"
         "[MISSION]\nset:res=628\n[END]")
MAP = "[WINDOW]\n[END]"
FLOW = "[RUN]\n[START]\nopenwindow:res=MAP\nsetcurwindow:res=MAP\naddobject:res=ENVOY\nwaitforrelease:\n[END]"
# The three caravan scroll bitmaps and their set:depend values (section 7.4).
SCROLLS = (RenderBitmap("CarScroll1", animation=(("depend", 4),)),
           RenderBitmap("CarScroll2", animation=(("depend", 3),)),
           RenderBitmap("CarScroll3", animation=(("depend", 2),)))


def _content() -> GlueContent:
    return GlueContent.from_data(resources={"ENVOY": ENVOY, "OTHER": OTHER, "MAP": MAP, "FLOW": FLOW})


def _campaign(window: str = "ENVOY") -> CampaignState:
    return CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window=window, content=_content())


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


class OfferedCountTests(unittest.TestCase):
    def test_worked_example_counts_three_then_one_then_two(self):
        campaign = _campaign()
        self.assertEqual(campaign.recount_offered(), 3)
        campaign.mark_mission_taken(MissionRef("ENVOY", 0))
        self.assertEqual(campaign.recount_offered(), 1)
        campaign.mark_mission_taken(MissionRef("ENVOY", 1))
        self.assertEqual(campaign.recount_offered(), 2)

    def test_given_a_mission_is_taken_then_the_cached_count_waits_for_the_next_recount(self):
        campaign = _campaign()
        campaign.recount_offered()
        campaign.mark_mission_taken(MissionRef("ENVOY", 0))  # troop selection's Done, before the release

        self.assertEqual(campaign.scroll_count, 3)

    def test_given_the_same_name_id_was_finished_in_another_window_then_this_window_still_counts_it(self):
        campaign = _campaign("OTHER")
        campaign.completed.update({671, 628})
        campaign.mark_mission_taken(MissionRef("ENVOY", 0))
        campaign.mark_mission_taken(MissionRef("ENVOY", 3))

        self.assertEqual(campaign.recount_offered(), 2)

    def test_given_no_count_was_taken_yet_then_the_current_window_is_counted(self):
        self.assertEqual(_campaign().scroll_count, 3)

    def test_the_release_step_recounts_the_released_missions_window(self):
        campaign = _campaign()
        campaign.recount_offered()
        mission = {"name_id": 671, "mission_ref": MissionRef("ENVOY", 0)}

        campaign.complete(mission)

        self.assertEqual(campaign.scroll_count, 1)

    def test_adding_a_mission_window_takes_its_count(self):
        campaign = _campaign("OTHER")
        campaign.offered_count = 0
        runtime = GlueRuntime(campaign.content, campaign)  # type: ignore[arg-type]

        runtime.start("FLOW")

        self.assertEqual(campaign.scroll_count, 3)

    def test_the_cached_count_is_saved_with_the_campaign(self):
        campaign = _campaign()
        campaign.offered_count = 2
        self.assertEqual(campaign_to_dict(campaign)["offered_count"], 2)


if __name__ == "__main__":
    unittest.main()
