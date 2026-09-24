"""A mission record with a battle but no mission script completes after its battle (issue #124,
notes/activity_results.md sections 2.4 and 5): debrief, completion, replacement flow, caravan, map."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_battle_scene import SCRIPT
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

RECORD = "[MISSION]\nset:res={id}\nres:BRIEF\nsetbattlescript:bf001\ndebrief:{debrief}\n{extra}[END]"
WINDOW = "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
RESOURCES = {
    "FLOWONE": "[RUN]\n[START]\nopenwindow:res=MISSIONAWINDOW\nwaitforrelease:\nendgame:\n[END]",
    "FLOWTWO": "[RUN]\n[START]\nopenwindow:res=MISSIONBWINDOW\nwaitforrelease:\nendgame:\n[END]",
    "MISSIONAWINDOW": WINDOW + RECORD.format(id=701, debrief=5, extra="replacescript:FLOWTWO\n"),
    "MISSIONBWINDOW": WINDOW + RECORD.format(id=702, debrief=6, extra="")
                      + RECORD.format(id=703, debrief=7, extra=""),
    "BRIEF": "[RUN]\n[START]\nwaitforrelease:\n[END]",
}


class ScriptlessMissionTests(unittest.TestCase):
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
        self.log = CampaignLogger(root / "log.jsonl")
        self.context.campaign_log = self.log
        self.root = root

    def _play(self, direct):
        graph = {"flow_scripts": {"FLOWONE": ({"action": "add_window", "window": "MISSIONAWINDOW"},),
                                  "FLOWTWO": ({"action": "add_window", "window": "MISSIONBWINDOW"},)},
                 "mission_windows": parse_mission_windows(self.content.resources)}
        campaign = CampaignState(graph, flow="FLOWONE")
        map_scene = GlueScene("FLOWONE", campaign)
        machine = SceneMachine(map_scene, self.context)
        machine.handle(GlueInput("mission-select", "missionawindow.0"))
        if direct:
            machine.handle(GlueInput("panel-action", "open_troop_select"))
        else:
            machine.handle(GlueInput("panel-action", "open_briefing"))
            machine.handle(GlueInput("panel-action", "accept_briefing"))
        self.assertIsInstance(machine.active, TroopSelectionScene)
        for _ in range(4):
            machine.update(0.1)
        return machine, map_scene, campaign

    def _debriefs(self):
        self.log.close()
        rows = [json.loads(line) for line in (self.root / "log.jsonl").read_text().splitlines()]
        return [row["debrief_index"] for row in rows if row["type"] == "debrief"]

    def test_given_either_route_when_the_battle_ends_then_it_is_debriefed_completed_and_the_flow_advances(self):
        for direct in (False, True):
            with self.subTest(direct=direct):
                machine, map_scene, campaign = self._play(direct)

                self.assertEqual(campaign.completed, {701})
                self.assertEqual(campaign.flow, "FLOWTWO")
                self.assertIs(machine.active, map_scene)
                self.assertEqual(map_scene.runtime.state.windows[-1].name, "MISSIONBWINDOW")
                self.assertEqual(self._debriefs(), [4])  # the record's `debrief` 5 is evaluator index 4

    def test_given_the_map_after_a_scriptless_mission_when_the_next_one_is_chosen_then_the_panel_actions_open_it(self):
        for direct in (False, True):
            with self.subTest(direct=direct):
                machine, map_scene, campaign = self._play(direct)

                machine.handle(GlueInput("mission-select", "missionbwindow.1"))
                machine.handle(GlueInput("panel-action", "open_briefing"))
                self.assertIsInstance(machine.active, GlueScene)
                self.assertEqual(machine.active.accept_mission.window, "MISSIONBWINDOW")
                machine.handle(GlueInput("panel-action", "accept_briefing"))
                self.assertIsInstance(machine.active, TroopSelectionScene)
                for _ in range(4):
                    machine.update(0.1)
                self.assertEqual(len(campaign.completed), 2)
                self.assertIn(701, campaign.completed)
                self.assertIs(machine.active, map_scene)
                self.assertIn(self._debriefs(), ([4, 5], [4, 6]))


if __name__ == "__main__":
    unittest.main()
