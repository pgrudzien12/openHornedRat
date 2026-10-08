"""A finished battle hands back to the campaign glue program and the flow advances.

Scenarios for the battle -> campaign hand-off (issues #116, #117): the mission is recorded as
completed, the flow moves on, the same battle is not offered again, and only a standalone battle
ends at the main menu.
"""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from whshr.assets import AssetLocator
from whshr.battle_scene import BATTLE_TICK_SECONDS, BattleScene
from whshr.cache import AssetCache
from whshr.campaign import parse_mission_windows
from whshr.campaign_scenes import MainMenuScene, TroopSelectionScene
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.debrief_scene import DebriefScene
from whshr.glue_content import GlueContent
from whshr.glue_runtime import EndGame, GlueInput
from whshr.glue_scene import GlueScene
from whshr.result_scene import ResultScene
from whshr.rules import Side
from whshr.scenes import SceneAssets, SceneMachine
from tests.test_battle_scene import SCRIPT

RESOURCES = {
    "FLOW": "[RUN]\n[START]\nopenwindow:res=MISSIONAWINDOW\nwaitforrelease:\nopenwindow:res=MISSIONBWINDOW\nwaitforrelease:\nendgame:\n[END]",
    "MISSIONAWINDOW": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
            "[MISSION]\nset:res=601\nres:BRIEF\nsetbattlescript:bf001\nsetmissionscript:MSCRIPT\n[END]",
    # Two records: the first only names a battle (no mission script) and keeps the player on the
    # window; the second has a mission script and releases the flow script (`releaseflag`).
    "MISSIONBWINDOW": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
            "[MISSION]\nset:res=602\nres:BRIEF\nsetbattlescript:bf001\n[END]\n"
            "[MISSION]\nset:res=603\nres:BRIEF\nsetbattlescript:bf001\nsetmissionscript:MSCRIPT\nset:releaseflag=1\n[END]",
    "BRIEF": "[RUN]\n[START]\nwaitforrelease:\n[END]",
    "MSCRIPT": "[RUN]\n[START]\nautosave:\nencounterplaygamewithdebrief:bf001\ngocaravan:select\n[END]",
}


class BattleHandoffTests(unittest.TestCase):
    def test_given_campaign_battle_logging_and_seed_when_battle_starts_then_both_are_preserved(self):
        import json
        self.context.battle_log_dir = Path(self.temporary.name) / "logs"
        self.context.battle_seed = 42
        self._open_mission("MISSIONAWINDOW:601")
        scene = self.machine.active
        self.assertIsInstance(scene, BattleScene)
        self.assertEqual(scene.seed, 42)
        self.assertIsNotNone(scene.logger)
        for _ in range(19):  # snapshots are emitted at segment boundaries
            scene.update(BATTLE_TICK_SECONDS, self.context)
        scene.exit(self.context)
        rows = [json.loads(line) for line in scene.logger.path.read_text().splitlines()]
        self.assertEqual(rows[0]["seed"], 42)
        self.assertTrue(any(row["type"] == "snapshot" for row in rows))

    def test_given_confirmed_campaign_march_when_battle_loads_then_current_army_and_order_determine_slots(self):
        from whshr import roster
        from whshr.troop_selection import Deployment
        from tests.test_roster import MRC
        from tests.test_savegame import ROWS
        from tests.test_deployment import source
        self.campaign.company = roster.parse_company(MRC, ROWS)
        self.campaign.commit_troop_selection(Deployment((14, 2), 0, frozenset((14, 2))))
        data = source(3)
        context = SceneAssets(self.context.locator, self.context.catalog, AssetCache(),
                              {"battle-script": lambda _, path: SimpleNamespace(script=data)})
        scene = BattleScene(glue_scene=self.map_scene)
        scene.enter(context)
        self.assertEqual(list(scene.battle.regiments), ["Cannon<Crew", "Grudgebringer<Cavalry"])
        self.assertEqual([(r.x, r.y) for r in scene.battle.regiments.values()], [(400, 500), (500, 600)])
        self.assertEqual(len(scene.field.script["merc"]["armies"][0]["units"]), 2)
        self.assertEqual(len(data["merc"]["armies"][0]["units"]), 3)
        scene.exit(context)

    def test_given_a_g_battle_when_it_loads_through_the_campaign_then_an_allied_npc_is_built_from_the_company(self):
        from whshr import roster
        from tests.test_roster import MRC
        from tests.test_savegame import ROWS
        from tests.test_npc_merge import NPC_SIDE, source, unit

        self.campaign.company = roster.parse_company(MRC, ROWS)  # Grudgebringer Cavalry (2), Cannon Crew (14, 3 models)
        data = source([["G", 1, 4]], [unit("NPC_Cannon<Crew", 14, 2, NPC_SIDE, x=400, y=500)])
        context = SceneAssets(self.context.locator, self.context.catalog, AssetCache(),
                              {"battle-script": lambda _, path: SimpleNamespace(script=data)})
        scene = BattleScene(glue_scene=self.map_scene)
        scene.enter(context)

        npc = scene.battle.regiments["NPC_Cannon<Crew"]
        self.assertEqual((npc.models, npc.name, npc.whoami), (3, "Cannon Crew", 14))  # the company's current strength
        self.assertEqual(scene.battle.npc_regiments, {"NPC_Cannon<Crew": 14})
        scene.exit(context)

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
        graph = {"flow_scripts": {"FLOW": ({"action": "add_window", "window": "MISSIONAWINDOW"},
                                           {"action": "add_window", "window": "MISSIONBWINDOW"})},
                 "mission_windows": parse_mission_windows(self.content.resources)}
        self.campaign = CampaignState(graph, flow="FLOW")
        self.map_scene = GlueScene("FLOW", self.campaign)
        self.machine = SceneMachine(self.map_scene, self.context)

    def _open_mission(self, key):
        machine = self.machine
        machine.handle(GlueInput("mission-select", key))
        machine.handle(GlueInput("panel-action", "open_briefing"))
        self.assertIsNot(machine.active, self.map_scene)
        machine.handle(GlueInput("panel-action", "accept_briefing"))
        self.assertIsInstance(machine.active, TroopSelectionScene)
        machine.update(0)  # no company file: the screen is skipped and Done runs at once

    def _win(self):
        battle = self.machine.active
        self.assertIsInstance(battle, BattleScene)
        for regiment in battle.battle.regiments.values():
            if regiment.side != Side.PLAYER:
                regiment.models = 0
        self.machine.update(BATTLE_TICK_SECONDS)

    def _play_and_win_first_mission(self):
        self._open_mission("missionawindow.0")
        self._win()
        self.machine.handle("continue")
        self.machine.handle("done")  # the debrief screen closes

    def test_given_a_no_battle_win_when_the_mission_ends_then_it_is_completed_and_the_flow_advances(self):
        self.context.no_battle = True

        self._open_mission("missionawindow.0")
        self.machine.update(BATTLE_TICK_SECONDS)

        self.assertEqual(self.campaign.completed, {601})
        self.assertEqual(self.campaign.mission_window, "MISSIONBWINDOW")
        self.assertEqual(self.campaign.flow_step, 1)
        self.assertIs(self.machine.active, self.map_scene)

    def test_given_a_played_win_when_the_result_is_dismissed_then_the_campaign_continues(self):
        self._open_mission("missionawindow.0")
        self._win()
        self.assertNotIsInstance(self.machine.active, ResultScene)  # straight into the debrief

        self.machine.handle("done")  # the debrief screen closes

        self.assertIs(self.machine.active, self.map_scene)
        self.assertEqual(self.campaign.completed, {601})
        self.assertEqual(self.campaign.flow_step, 1)

    def test_given_a_mission_without_a_script_when_its_battle_is_won_then_it_still_completes(self):
        self._play_and_win_first_mission()

        self._open_mission("missionbwindow.0")  # names a battle only, and does not release the flow
        self._win()
        self.machine.handle("continue")
        self.machine.handle("done")  # the debrief screen closes

        self.assertIs(self.machine.active, self.map_scene)
        self.assertEqual(self.campaign.completed, {601, 602})
        self.assertEqual(self.campaign.mission_window, "MISSIONBWINDOW")
        self.assertNotIn(EndGame(), self.map_scene.effects)  # the flow script is still parked

    def test_given_a_releasing_mission_when_it_is_won_then_the_flow_script_resumes(self):
        self._play_and_win_first_mission()

        self._open_mission("missionbwindow.1")
        self._win()
        self.machine.handle("continue")
        self.machine.handle("done")  # the debrief screen closes

        self.assertEqual(self.campaign.completed, {601, 603})
        self.assertIn(EndGame(), self.map_scene.effects)

    def test_given_a_campaign_battle_when_its_result_is_dismissed_then_the_pending_request_is_resolved(self):
        self._open_mission("missionawindow.0")
        self._win()
        glue = self.machine.active.glue_scene
        self.assertIsNotNone(glue.runtime.state.pending)

        self.machine.handle("continue")
        self.machine.handle("done")  # the debrief screen closes

        self.assertIsNone(glue.runtime.state.pending)

    def test_given_a_campaign_ending_battle_when_it_resolves_then_the_death_movie_leads_to_the_main_menu(self):
        from unittest import mock

        from whshr.scenes import Scene

        created = []

        class StubMovie(Scene):
            def __init__(self, movie, successor=None, **_):
                created.append((movie, successor))

        self._open_mission("missionawindow.0")
        players = sum(1 for r in self.machine.active.battle.regiments.values() if r.side == Side.PLAYER)
        with mock.patch("whshr.casualties.campaign_over_movie", return_value="death02"), \
                mock.patch("whshr.campaign_scenes.MovieScene", StubMovie), \
                mock.patch.object(CampaignState, "ordered_march_units", new_callable=mock.PropertyMock,
                                  return_value=tuple(range(100, 100 + players))):
            self._win()

        self.assertEqual([movie for movie, _ in created], ["death02"])
        self.assertIsInstance(created[0][1], MainMenuScene)
        self.assertEqual(self.campaign.completed, set())  # no debrief, payment or merge
        self.assertIsNone(self.campaign.campaign_over_movie)

    def test_given_a_standalone_battle_when_its_result_is_dismissed_then_it_returns_to_the_main_menu(self):
        scene = BattleScene()
        machine = SceneMachine(scene, self.context)
        for regiment in scene.battle.regiments.values():
            if regiment.side != Side.PLAYER:
                regiment.models = 0
        machine.update(BATTLE_TICK_SECONDS)
        self.assertIsInstance(machine.active, ResultScene)

        machine.handle("continue")
        machine.handle("done")  # the debrief screen closes

        self.assertIsInstance(machine.active, MainMenuScene)


class SkippedDebriefTests(BattleHandoffTests):
    """notes/native-windows.md 9.11 scenario 4: BF001 (debrief index 6) lost, whose evaluator list has no text."""

    # the inherited scenarios belong to BattleHandoffTests; only its fixtures are reused here
    for _name in [name for name in vars(BattleHandoffTests) if name.startswith("test_")]:
        locals()[_name] = None
    del _name

    def setUp(self):
        from unittest import mock

        patcher = mock.patch.dict(RESOURCES, {"MSCRIPT": "[RUN]\n[START]\nautosave:\nsetdebrief:6\n"
                                              "encounterplaygamewithdebrief:bf001\ngocaravan:select\n[END]"})
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def test_given_a_glue_started_defeat_without_debrief_text_then_no_screen_opens_and_the_flow_resumes(self):
        self._open_mission("missionawindow.0")
        for regiment in self.machine.active.battle.regiments.values():
            if regiment.side == Side.PLAYER:
                regiment.models = 0
        self.machine.update(BATTLE_TICK_SECONDS)
        self.assertNotIsInstance(self.machine.active, ResultScene)

        self.machine.update(0.1)  # the debrief has nothing to show: its completion runs at once

        self.assertNotIsInstance(self.machine.active, (ResultScene, DebriefScene))
        self.assertEqual(self.campaign.completed, {601})
        self.assertIsNone(self.map_scene.runtime.state.pending)


if __name__ == "__main__":
    unittest.main()
