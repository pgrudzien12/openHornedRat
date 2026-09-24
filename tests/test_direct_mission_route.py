"""A mission started straight from the map ends in the same campaign state as one started from its
briefing (issue #124), and a glue scene with nothing left to show falls back to the map."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign import parse_mission_windows
from whshr.campaign_log import CampaignLogger
from whshr.campaign_scenes import TroopSelectionScene
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneAssets, SceneMachine
from tests.test_battle_scene import SCRIPT

RESOURCES = {
    "FLOW": "[RUN]\n[START]\nopenwindow:res=MISSIONAWINDOW\nwaitforrelease:\nopenwindow:res=MISSIONBWINDOW\nwaitforrelease:\nendgame:\n[END]",
    "MISSIONAWINDOW": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
            "[MISSION]\nset:res=601\nres:BRIEF\nsetbattlescript:bf001\nsetmissionscript:MSCRIPT\n[END]",
    "MISSIONBWINDOW": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
            "[MISSION]\nset:res=602\nres:BRIEF\nsetbattlescript:bf001\nsetmissionscript:MSCRIPT\n[END]",
    "BRIEF": "[RUN]\n[START]\nwaitforrelease:\n[END]",
    "MSCRIPT": "[RUN]\n[START]\nautosave:\nencounterplaygamewithdebrief:bf001\ngocaravan:select\n[END]",
    "EMPTY": "[RUN]\n[START]\n[END]",
}


class DirectMissionRouteTests(unittest.TestCase):
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
                                   {"battle-script": lambda _, path: SimpleNamespace(script=SCRIPT)})
        self.context.glue = self.content
        self.context.no_battle = True
        self.root = root

    def _campaign(self):
        graph = {"flow_scripts": {"FLOW": ({"action": "add_window", "window": "MISSIONAWINDOW"},
                                           {"action": "add_window", "window": "MISSIONBWINDOW"})},
                 "mission_windows": parse_mission_windows(self.content.resources)}
        return CampaignState(graph, flow="FLOW")

    def _open(self, machine, key, direct):
        machine.handle(GlueInput("mission-select", key))
        if direct:
            machine.handle(GlueInput("panel-action", "open_troop_select"))
        else:
            machine.handle(GlueInput("panel-action", "open_briefing"))
            machine.handle(GlueInput("panel-action", "accept_briefing"))
        self.assertIsInstance(machine.active, TroopSelectionScene)
        for _ in range(4):  # no company file: the screen is skipped and Done runs at once
            machine.update(0.1)

    def _play(self, keys, direct):
        """Play the missions in order (the last one by the given route) and return the end state."""
        campaign = self._campaign()
        map_scene = GlueScene("FLOW", campaign)
        machine = SceneMachine(map_scene, self.context)
        for key in keys[:-1]:
            self._open(machine, key, False)
        self._open(machine, keys[-1], direct)
        return machine, map_scene, campaign

    def test_given_either_route_when_a_mission_ends_then_the_campaign_state_is_the_same(self):
        for keys in (("missionawindow.0",), ("missionawindow.0", "missionbwindow.0")):
            with self.subTest(missions=keys):
                results = []
                for direct in (False, True):
                    machine, map_scene, campaign = self._play(keys, direct)
                    results.append((set(campaign.completed), campaign.flow_step, campaign.mission_window,
                                   machine.active is map_scene))
                self.assertEqual(results[0], results[1])
                self.assertTrue(results[1][0])
                self.assertTrue(results[1][3])

    def test_given_the_direct_route_when_the_mission_ends_then_the_map_shows_the_next_window(self):
        machine, map_scene, campaign = self._play(("missionawindow.0",), True)

        self.assertEqual(campaign.completed, {601})
        self.assertEqual(map_scene.runtime.state.windows[-1].name, "MISSIONBWINDOW")

    def test_given_a_glue_scene_with_nothing_to_show_when_it_is_active_then_the_map_is_shown_and_logged(self):
        campaign = self._campaign()
        log = CampaignLogger(self.root / "log.jsonl")
        self.context.campaign_log = log
        machine = SceneMachine(GlueScene("EMPTY", campaign), self.context)

        machine.update(0.1)

        self.assertEqual(machine.active.program, "FLOW")
        self.assertTrue(machine.active.runtime.state.windows)
        log.close()
        rows = [json.loads(line) for line in (self.root / "log.jsonl").read_text().splitlines()]
        self.assertTrue(any(row["type"] == "diagnostic" for row in rows))


if __name__ == "__main__":
    unittest.main()
