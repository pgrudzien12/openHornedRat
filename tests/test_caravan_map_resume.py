"""Reopening the mission map from the caravan resumes the campaign's saved position (issue #119).

The map hotspot must not restart the flow script: it replays the script's set-up and stops on
the mission window the campaign is at, offering only missions that are not finished yet.
"""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign import parse_mission_windows
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneAssets, SceneMachine

MISSION = "[MISSION]\nset:res={id}\nres:BRIEF{id}\nsetbattlescript:bf001\n{extra}[END]\n"
WINDOW = "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"


def _flow(*windows):
    body = "".join(f"openwindow:res={w}\nwaitforrelease:\n" for w in windows)
    return f"[RUN]\n[START]\n{body}endgame:\n[END]"


RESOURCES = {
    "STARTCARAVAN": "[WINDOW]\n[END]",
    "FLOWONE": _flow("MISSIONAWINDOW", "MISSIONBWINDOW", "MISSIONCWINDOW"),
    "FLOWTWO": _flow("MISSIONDWINDOW", "MISSIONEWINDOW"),
    "MISSIONAWINDOW": WINDOW + MISSION.format(id=601, extra="set:releaseflag=1\n"),
    "MISSIONBWINDOW": WINDOW + MISSION.format(id=602, extra="") + MISSION.format(id=603, extra="set:releaseflag=1\n"),
    "MISSIONCWINDOW": WINDOW + MISSION.format(id=604, extra="replacescript:FLOWTWO\n"),
    "MISSIONDWINDOW": WINDOW + MISSION.format(id=605, extra="set:releaseflag=1\n"),
    "MISSIONEWINDOW": WINDOW + MISSION.format(id=606, extra=""),
    "BRIEF601": "[RUN]\n[START]\nwaitforrelease:\n[END]",
    "BRIEF602": "[RUN]\n[START]\nwaitforrelease:\n[END]",
    "BRIEF603": "[RUN]\n[START]\nwaitforrelease:\n[END]",
}


def graph_for(content):
    def steps(*windows):
        return tuple(step for w in windows for step in ({"action": "add_window", "window": w},
                                                        {"action": "wait_player_choice"}))
    return {"flow_scripts": {"FLOWONE": steps("MISSIONAWINDOW", "MISSIONBWINDOW", "MISSIONCWINDOW"),
                             "FLOWTWO": steps("MISSIONDWINDOW", "MISSIONEWINDOW")},
            "mission_windows": parse_mission_windows(content.resources)}


class CaravanMapResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.content = GlueContent.from_data(resources=RESOURCES)
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(),
                                   {"battle-script": lambda _, path: SimpleNamespace(script=None)})
        self.context.glue = self.content
        self.campaign = CampaignState(graph_for(self.content), flow="FLOWONE")

    def _finish(self, window, index):
        """Finish one record of a window the way the mission release step does."""
        return self.campaign.complete(self.campaign.graph["mission_windows"][window][index])

    def _open_map_from_caravan(self):
        caravan = GlueScene(campaign=self.campaign, window="STARTCARAVAN")
        machine = SceneMachine(caravan, self.context)
        machine.handle(GlueInput("hotspot-release", "FLOWONE"))
        self.assertIsNot(machine.active, caravan)
        return machine

    def _selected(self, machine):
        return machine.active.runtime.state.selected_mission.key

    def _mission_window(self, machine):
        return machine.active.runtime.state.windows[-1].name

    def test_given_nothing_finished_when_the_map_opens_then_it_starts_at_the_first_window(self):
        machine = self._open_map_from_caravan()
        self.assertEqual(self._mission_window(machine), "MISSIONAWINDOW")
        self.assertEqual(self._selected(machine), "missionawindow.0")

    def test_given_a_finished_first_mission_when_the_map_reopens_then_the_next_window_is_offered(self):
        _, released = self._finish("MISSIONAWINDOW", 0)
        self.assertTrue(released)
        machine = self._open_map_from_caravan()
        self.assertEqual(self._mission_window(machine), "MISSIONBWINDOW")
        self.assertEqual(self._selected(machine), "missionbwindow.0")

    def test_given_one_of_two_missions_finished_when_the_map_reopens_then_only_the_other_is_offered(self):
        self._finish("MISSIONAWINDOW", 0)
        self._finish("MISSIONBWINDOW", 0)
        machine = self._open_map_from_caravan()
        self.assertEqual(self._selected(machine), "missionbwindow.1")
        machine.handle(GlueInput("mission-select", "missionbwindow.0"))
        self.assertEqual(self._selected(machine), "missionbwindow.1")

    def test_given_a_finished_mission_when_briefing_then_the_chosen_mission_is_briefed(self):
        self._finish("MISSIONAWINDOW", 0)
        self._finish("MISSIONBWINDOW", 0)
        machine = self._open_map_from_caravan()
        machine.handle(GlueInput("panel-action", "open_briefing"))
        self.assertEqual(machine.active.program, "BRIEF603")

    def test_given_a_later_flow_step_when_the_map_reopens_then_it_resumes_there(self):
        self._finish("MISSIONAWINDOW", 0)
        self._finish("MISSIONBWINDOW", 0)
        self._finish("MISSIONBWINDOW", 1)
        machine = self._open_map_from_caravan()
        self.assertEqual(self._mission_window(machine), "MISSIONCWINDOW")

    def test_given_a_replaced_flow_when_the_map_reopens_then_the_chain_resumes_on_the_current_flow(self):
        for window, index in (("MISSIONAWINDOW", 0), ("MISSIONBWINDOW", 0), ("MISSIONBWINDOW", 1),
                              ("MISSIONCWINDOW", 0)):
            self._finish(window, index)
        self.assertEqual(self.campaign.flow, "FLOWTWO")
        machine = self._open_map_from_caravan()
        self.assertEqual(self._mission_window(machine), "MISSIONDWINDOW")
        self._finish("MISSIONDWINDOW", 0)
        machine = self._open_map_from_caravan()
        self.assertEqual(self._mission_window(machine), "MISSIONEWINDOW")
        self.assertEqual(self._selected(machine), "missionewindow.0")


if __name__ == "__main__":
    unittest.main()
