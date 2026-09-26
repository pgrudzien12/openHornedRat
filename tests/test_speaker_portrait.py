"""`[ANIM] index=-1` shows the player's current commander (notes/glue_portraits.md §1.4)."""
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from whshr.campaign_state import CampaignState
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueRuntime
from whshr.paths import Installation
from whshr.portraits import PORTRAIT_SPRITES, first_leader_speaker, speaker_position
from whshr.roster import Regiment, RosterRow

WINDOWS = {
    "SPEAKERWINDOW": "[WINDOW]\n[POSITION]\nset:x=10\nset:y=20\n[END]\n"
                     "[ANIM]\nset:index=-1\nset:bkindex=8\nset:sequence=1\nname:Someone\n[END]\n[END]",
    "FIXEDWINDOW": "[WINDOW]\n[POSITION]\nset:x=10\nset:y=20\n[END]\n"
                   "[ANIM]\nset:index=2\nset:bkindex=8\nset:sequence=1\nname:Commander\n[END]\n[END]",
}
SETS = {"commander": "COMM", "scribe": "SCRI", "gotrek": "GOTR"}


def regiment(leader_portrait, whoami=1):
    row = RosterRow(whoami, keep=False, for_hire=False, wizard=False, artillery=False, base_price=10)
    return Regiment(whoami, f"Unit {whoami}", True, 10, 10, 0, row, leader_portrait=leader_portrait)


class SpeakerSelectionTests(unittest.TestCase):
    def test_given_a_marching_roster_then_the_first_regiment_with_a_leader_portrait_speaks(self):
        self.assertEqual(first_leader_speaker(["VoidType", "Gotrek", "Commander"], SETS), "GOTR")

    def test_given_regiments_without_a_leader_portrait_then_they_are_skipped(self):
        self.assertEqual(first_leader_speaker([None, "VoidType", "Commander"], SETS), "COMM")
        self.assertIsNone(first_leader_speaker([None, "VoidType"], SETS))

    def test_given_a_portrait_variant_suffix_then_the_name_is_matched_without_it(self):
        self.assertEqual(first_leader_speaker(["Commander,1"], SETS), "COMM")

    def test_given_a_speaker_in_the_resident_list_then_its_position_is_found(self):
        self.assertEqual(speaker_position("COMM"), 2)
        self.assertEqual(speaker_position("GOTR"), 10)

    def test_given_no_speaker_or_one_missing_from_the_list_then_position_four_scribe_is_used(self):
        self.assertEqual(PORTRAIT_SPRITES[speaker_position(None)], "SCRI")
        self.assertEqual(speaker_position("NOSUCHSET"), 4)

    def test_given_unavailable_frames_then_the_next_available_position_is_used(self):
        self.assertEqual(speaker_position("COMM", lambda position: position >= 6), 6)
        self.assertEqual(speaker_position("GOTR", lambda position: position in (1,)), 1)  # wraps around


class SpeakerStateTests(unittest.TestCase):
    def _campaign(self):
        graph = {"flow_scripts": {"F": ({"action": "add_window", "window": "W"},)}, "mission_windows": {"W": []}}
        return CampaignState(graph, flow="F", portrait_sets=SETS)

    def test_given_no_roster_loaded_then_there_is_no_speaker(self):
        self.assertIsNone(self._campaign().current_speaker)

    def test_given_troop_selection_is_committed_then_the_first_marching_leader_is_the_speaker(self):
        campaign = self._campaign()
        campaign.company = (regiment("VoidType", 1), regiment("Gotrek", 2), regiment("Commander", 3))

        campaign.commit_troop_selection(SimpleNamespace(money_delta=0, units=(3, 1, 2), hired=(1, 2, 3)))

        self.assertEqual(campaign.current_speaker, "COMM")  # marching order, not company order

    def test_given_a_roster_regiment_type_the_field_read_is_the_leader_portrait(self):
        self.assertIn("leader_portrait", Regiment.__dataclass_fields__)

    def test_given_a_later_change_of_the_march_set_then_the_speaker_only_moves_on_roster_load(self):
        campaign = self._campaign()
        campaign.refresh_speaker([regiment("Gotrek")])

        campaign.join_mission(9)
        campaign.leave_mission(9)

        self.assertEqual(campaign.current_speaker, "GOTR")


class FixtureMixin:
    """A temporary installation holding tiny sprite sets, and windows using index -1 or 2."""

    def make_content(self, sets=("BACKALL", "COMM", "SCRI", "DWA1")):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        binary = Path(temporary.name) / "FILE/BINARY"
        binary.mkdir(parents=True)
        palette = bytearray(256 * 4)
        for index in range(256):
            palette[index * 4:index * 4 + 4] = bytes((index, index, (index + 1) % 256, (index + 2) % 256))
        (binary / "STANDARD.PAL").write_bytes(palette)
        for number, name in enumerate(sets):
            frames = 20 if name == "BACKALL" else 8
            fol, bop = bytearray(), bytearray()
            for frame in range(frames):
                fol += struct.pack("<hhhhIB", 0, 0, 2, 2, len(bop), 1) + b"\0\0\0"
                bop += bytes((number + 1, frame % 200 + 1, 0, number + 2))
            (binary / f"{name}.FOL").write_bytes(fol)
            (binary / f"{name}.BOP").write_bytes(bop)
        content = GlueContent.from_data(resources=WINDOWS)
        content.installation = Installation(temporary.name)
        return content


class IndexMinusOneRuntimeTests(FixtureMixin, unittest.TestCase):
    def _runtime(self, speaker, **kwargs):
        runtime = GlueRuntime(self.make_content(**kwargs), SimpleNamespace(current_speaker=speaker))
        return runtime

    def test_given_the_commander_is_speaker_then_an_index_minus_one_window_behaves_as_position_two(self):
        runtime = self._runtime("COMM")
        runtime.start_window("SPEAKERWINDOW")

        self.assertEqual(runtime.portrait_index("SPEAKERWINDOW", -1), 2)
        self.assertEqual(runtime.state.portrait_speakers["SPEAKERWINDOW"], (2, "COMM"))

    def test_given_index_minus_one_then_it_renders_and_animates_like_the_fixed_index_block(self):
        runtime = self._runtime("COMM")
        runtime.start_window("SPEAKERWINDOW")
        fixed = self._runtime("COMM")
        fixed.start_window("FIXEDWINDOW")
        first, second = runtime.state.portrait_animators["SPEAKERWINDOW"], fixed.state.portrait_animators["FIXEDWINDOW"]
        for _ in range(60):
            first.advance(55)
            second.advance(55)
            self.assertEqual((first.mouth_frame, first.eye_frame), (second.mouth_frame, second.eye_frame))
        self.assertEqual(runtime.content.portrait_data(runtime.portrait_index("SPEAKERWINDOW", -1), 8),
                         fixed.content.portrait_data(fixed.portrait_index("FIXEDWINDOW", 2), 8))

    def test_given_no_campaign_then_the_scribe_at_position_four_is_shown(self):
        runtime = GlueRuntime(self.make_content())
        runtime.start_window("SPEAKERWINDOW")

        self.assertEqual(runtime.portrait_index("SPEAKERWINDOW", -1), 4)

    def test_given_a_speaker_outside_the_list_then_the_scribe_is_shown(self):
        runtime = self._runtime("NOSUCHSET")
        runtime.start_window("SPEAKERWINDOW")

        self.assertEqual(runtime.portrait_index("SPEAKERWINDOW", -1), 4)

    def test_given_missing_frames_for_the_speaker_then_the_next_available_position_is_used(self):
        runtime = self._runtime("COMM", sets=("BACKALL", "SCRI", "DWA1"))
        runtime.start_window("SPEAKERWINDOW")

        self.assertEqual(runtime.portrait_index("SPEAKERWINDOW", -1), 4)  # 3 (SKA4) is missing too, SCRI is next

    def test_given_the_speaker_changes_while_the_window_is_open_then_the_portrait_stays(self):
        campaign = SimpleNamespace(current_speaker="COMM")
        runtime = GlueRuntime(self.make_content(sets=("BACKALL", "COMM", "SCRI", "DWA1", "GOTR")), campaign)
        runtime.start_window("SPEAKERWINDOW")

        campaign.current_speaker = "GOTR"

        self.assertEqual(runtime.portrait_index("SPEAKERWINDOW", -1), 2)

    def test_given_a_fixed_index_then_it_is_returned_unchanged(self):
        runtime = self._runtime("COMM")
        self.assertEqual(runtime.portrait_index("ANY", 7), 7)
        self.assertEqual(runtime.portrait_index("ANY", None), None)


@unittest.skipUnless(os.environ.get("WARFB"), "needs an original installation (WARFB)")
class ShippedRosterSpeakerTests(unittest.TestCase):
    def test_given_the_shipped_roster_then_the_ambush_window_shows_the_commander(self):
        from whshr.roster import load_company

        content = GlueContent(os.environ["WARFB"])
        campaign = CampaignState({"flow_scripts": {"F": ({"action": "add_window", "window": "W"},)},
                                  "mission_windows": {"W": []}}, flow="F", content=content)
        company = load_company(content.installation)
        campaign.refresh_speaker(company)
        runtime = GlueRuntime(content, campaign)
        runtime.start_window("AMBUSHWINDOW")

        self.assertEqual(campaign.current_speaker, "COMM")
        self.assertEqual(runtime.portrait_index("AMBUSHWINDOW", -1), 2)


if __name__ == "__main__":
    unittest.main()
