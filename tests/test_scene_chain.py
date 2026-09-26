"""Saving and loading mid-campaign scenes: a mission script with its caravan open, and the map parked beneath it
(notes/save_resume.md, engine version)."""
import tempfile
import unittest
from pathlib import Path

from tests.test_savegame import MRC, ROWS, TWO_WINDOWS, FIRST, committed_campaign
from whshr import roster
from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.load_save_scene import LOAD, LoadSaveScene
from whshr.savegame import SaveStore
from whshr.scenes import SceneAssets, SceneMachine

WINDOW = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n[END]\n"
HOTSPOTS = "[HOTSPOT]\nset:x=1\nset:y=1\nset:vx=9\nset:vy=9\nscript:pop.wnd\nres:%s\n[END]\n"
RESOURCES = {
    "MAPWIN": WINDOW,
    "MAPFLOW": "[RUN]\n[START]\nopenwindow:res=MAPWIN\nwaitforrelease:\n[END]",
    "CARAVANAFTERMISSION": WINDOW + HOTSPOTS % "LoadSaveWindow" + HOTSPOTS % "UnwindMission",
    "INFOCARAVANTLK": WINDOW + HOTSPOTS % "LoadSaveWindow" + HOTSPOTS % "PopAndResume",
    "SELECTSCRIPT": "[RUN]\n[START]\nopenwindow:res=MAPWIN\ngocaravan:select\nopenwindow:res=MAPWIN\n[END]",
    "TALKSCRIPT": "[RUN]\n[START]\ngocaravan:infoTLK\nopenwindow:res=MAPWIN\n[END]",
}


class SceneChainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.save_dir = root / "saves"
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(), {}, save_dir=self.save_dir)
        self.context.glue = GlueContent.from_data(resources=RESOURCES)
        self.store = SaveStore(self.save_dir)

    def _mission_caravan(self, script):
        """The player is in ``script``'s caravan; the map that launched the mission is parked beneath."""
        campaign = committed_campaign()
        campaign.save_dir = self.save_dir
        parked_map = GlueScene("MAPFLOW", campaign)
        parked_map.enter(self.context)
        mission = GlueScene(script, campaign, accept_mission=FIRST, return_scene=parked_map)
        return SceneMachine(mission, self.context), mission, campaign

    def _save(self, machine, slot=0):
        machine.handle(GlueInput("hotspot-release", "LoadSaveWindow"))
        for event in (f"slot:{slot}", "ok", "ok"):
            machine.handle(event)

    def _load(self, slot=0):
        """A new session: the load dialog on a fresh campaign of the same game."""
        fresh = CampaignState(TWO_WINDOWS, flow="F", company=roster.parse_company(MRC, ROWS), save_dir=self.save_dir)
        dialog = LoadSaveScene(LOAD, GlueScene(window="STARTCARAVAN"),
                               new_campaign=lambda context, directory: fresh)
        machine = SceneMachine(dialog, self.context)
        machine.handle(f"slot:{slot}")
        machine.handle("ok")
        return machine, fresh

    def test_given_the_after_mission_caravan_when_saved_and_loaded_then_the_same_caravan_is_open_with_the_map_beneath(self):
        machine, mission, _ = self._mission_caravan("SELECTSCRIPT")
        self._save(machine)
        self.assertIs(machine.active, mission)

        loaded, campaign = self._load()

        scene = loaded.active
        self.assertIsInstance(scene, GlueScene)
        self.assertEqual((scene.program, scene.accept_mission), ("SELECTSCRIPT", FIRST))
        self.assertEqual(scene.runtime.state.pending.kind, "caravan")
        self.assertEqual(scene.runtime.state.pending.mode, "select")
        self.assertEqual([w.name for w in scene.runtime.state.windows], ["CARAVANAFTERMISSION"])
        self.assertEqual(scene.return_scene.program, "MAPFLOW")
        self.assertEqual(scene.return_scene.runtime.state.wait_reason, "mission-release")
        self.assertIs(scene.campaign, campaign)
        self.assertIs(scene.return_scene.campaign, campaign)

    def test_given_a_loaded_after_mission_caravan_when_left_then_the_mission_is_released_on_the_map(self):
        machine, _, _ = self._mission_caravan("SELECTSCRIPT")
        self._save(machine)
        loaded, campaign = self._load()

        loaded.handle(GlueInput("hotspot-release", "UnwindMission"))

        self.assertEqual(loaded.active.program, "MAPFLOW")
        self.assertEqual(campaign.mission_window, "W2")
        self.assertEqual([m["name_id"] for m in campaign.missions], [602])

    def test_given_a_mid_mission_caravan_when_saved_and_loaded_then_the_script_carries_on_after_it(self):
        machine, _, _ = self._mission_caravan("TALKSCRIPT")
        self._save(machine)

        loaded, campaign = self._load()

        self.assertEqual(loaded.active.runtime.state.pending.mode, "infotlk")
        loaded.handle(GlueInput("hotspot-release", "PopAndResume"))
        self.assertEqual(loaded.active.program, "TALKSCRIPT")
        self.assertEqual([w.name for w in loaded.active.runtime.state.windows], ["MAPWIN"])
        self.assertIsNone(loaded.active.runtime.state.pending)

    def test_given_a_save_of_the_start_caravan_then_it_loads_as_that_caravan(self):
        campaign = committed_campaign()
        campaign.taken_missions.clear()
        campaign.save_dir = self.save_dir
        self.context.glue = GlueContent.from_data(resources={**RESOURCES, "STARTCARAVAN": WINDOW + HOTSPOTS % "LoadSaveWindow"})
        machine = SceneMachine(GlueScene(window="STARTCARAVAN", campaign=campaign), self.context)
        self._save(machine)

        loaded, _ = self._load()

        self.assertEqual(loaded.active.window, "STARTCARAVAN")
        self.assertEqual([w.name for w in loaded.active.runtime.state.windows], ["STARTCARAVAN"])

    def test_given_an_older_save_without_scenes_then_the_start_caravan_opens(self):
        self.store.write(0, "old", committed_campaign())  # no scene given: no chain
        self.context.glue = GlueContent.from_data(resources={**RESOURCES, "STARTCARAVAN": WINDOW})

        loaded, _ = self._load()

        self.assertEqual(loaded.active.window, "STARTCARAVAN")

    def test_given_a_damaged_scene_chain_then_the_load_reports_it_and_stays_in_the_dialog(self):
        machine, _, _ = self._mission_caravan("SELECTSCRIPT")
        self._save(machine)
        import json
        path = self.store.path(0)
        data = json.loads(path.read_text())
        data["scenes"]["scenes"][0]["state"]["$type"] = "Evil"
        path.write_text(json.dumps(data))

        loaded, _ = self._load()

        self.assertIsInstance(loaded.active, LoadSaveScene)
        self.assertIn("damaged", loaded.active.error)


if __name__ == "__main__":
    unittest.main()
