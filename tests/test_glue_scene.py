import unittest

from whshr.campaign_scenes import TroopSelectionScene
from whshr.campaign_state import CampaignState
from whshr.glue_content import GlueContent
from whshr.glue_runtime import ActivityResult, EndGame, GlueInput, OpenWindow, StartBattle, StartMovie, StopMusic
from whshr.glue_scene import GlueScene
from whshr.roster import Regiment, RosterRow
from whshr.scenes import SceneMachine, Transition


class _Context:
    def __init__(self, content):
        self.content = content

    def glue_content(self):
        return self.content


class GlueSceneTests(unittest.TestCase):
    def setUp(self):
        self.context = _Context(GlueContent.from_data(resources={
            "WINDOW": "[WINDOW]\n[POSITION]\nset:palindex=2\n[END]\n[END]",
            "FLOW": "[RUN]\n[START]\nopenwindow:res=WINDOW\nwaitforrelease:\nplaymovie:A2\nendgame:\n[END]",
            "BRIEFING": "[RUN]\n[START]\nwaitforrelease:\n[END]",
            "MAP": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n[MISSION]\nset:res=601\nres:BRIEFING\nsetbattlescript:BF001\ncash:1,100,50\n[END]",
            "MAP_FLOW": "[RUN]\n[START]\nopenwindow:res=MAP\nwaitforrelease:\n[END]",
            "STARTCARAVAN": "[WINDOW]\n[END]",
        }))

    def test_scene_owns_runtime_effects_across_input_and_activity_boundaries(self):
        # Driven directly through GlueScene rather than SceneMachine: a StartMovie effect here
        # is a request for the frontend to start a movie activity (SceneMachine routes it to a
        # MovieScene, notes/glue_engine_integration.md GEI6), not something this scene resolves
        # itself, so it stays queued for the host to take and act on.
        scene = GlueScene("flow")
        scene.enter(self.context)

        self.assertEqual(scene.take_effects(), (OpenWindow("WINDOW", None, 2),))
        scene.handle(GlueInput("mission-release"), self.context)
        movie = scene.take_effects()[0]
        self.assertIsInstance(movie, StartMovie)

        scene.handle(ActivityResult(movie.request_id, "movie"), self.context)
        self.assertEqual(scene.take_effects(), (EndGame(),))

    def test_snapshot_restore_is_available_at_scene_boundary(self):
        scene = GlueScene("FLOW")
        SceneMachine(scene, self.context)
        snapshot = scene.snapshot()
        scene.handle(GlueInput("mission-release"), self.context)

        scene.restore(snapshot)

        self.assertEqual(scene.runtime.state.wait_reason, "mission-release")

    def test_briefing_accept_without_a_campaign_skips_troop_selection_and_starts_the_battle(self):
        # notes/troop_selection.md §1.1: no company file skips the screen and runs Done immediately;
        # a development GlueScene has no CampaignState/company either.
        scene = GlueScene("BRIEFING", accept_battle="bf001")
        scene.enter(self.context)

        transition = scene.handle(GlueInput("panel-action", "open_troop_select"), self.context)
        self.assertIsInstance(transition.scene, TroopSelectionScene)
        selection = transition.scene
        selection.enter(self.context)
        self.assertEqual(selection.phase, "skip")

        done = selection.update(0, self.context)

        self.assertIs(done.scene, scene)
        effects = scene.take_effects()
        self.assertEqual(effects[0], StopMusic())
        self.assertIsInstance(effects[1], StartBattle)
        self.assertEqual(effects[1].battle, "BF001")

    def test_briefing_accept_with_a_campaign_opens_troop_selection_and_commits_on_done(self):
        commander = Regiment(2, "Grudgebringer Cavalry", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=8))
        reserve = Regiment(5, "Reserve", True, 10, 10, 0,
                           RosterRow(5, keep=False, for_hire=True, wizard=False, artillery=False, base_price=10))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP", coffers=500,
                                 company=(commander, reserve))
        map_scene = GlueScene("MAP_FLOW", campaign)
        machine = SceneMachine(map_scene, self.context)
        machine.handle(GlueInput("mission-select", "map.0"))
        machine.handle(GlueInput("panel-action", "open_briefing"))
        briefing_scene = machine.active
        self.assertIsInstance(briefing_scene, GlueScene)

        transition = briefing_scene.handle(GlueInput("panel-action", "accept_briefing"), self.context)
        self.assertIsInstance(transition.scene, TroopSelectionScene)
        selection = transition.scene
        selection.enter(self.context)
        self.assertEqual(selection.model.selection, [2])  # only the always-forced commander at open

        self.assertIsNone(selection.handle("done", self.context))  # P0 -> P1
        self.assertEqual(selection.phase, "march_order")
        done = selection.handle("done", self.context)

        self.assertIs(done.scene, briefing_scene)
        self.assertEqual(campaign.march_units, {2})
        self.assertEqual(campaign.army_units, {2, 5})
        self.assertEqual(campaign.coffers, 510)  # 500 + prepaid 100 - (commander 80 + reserve retainer 10)
        self.assertIn(map_scene.runtime.state.selected_mission, campaign.taken_missions)
        effects = briefing_scene.take_effects()
        self.assertIn(StopMusic(), effects)
        self.assertTrue(any(isinstance(e, StartBattle) and e.battle == "BF001" for e in effects))

    def test_briefing_return_restores_its_configured_scene(self):
        return_scene = object()
        scene = GlueScene("BRIEFING", return_scene=return_scene)
        SceneMachine(scene, self.context)

        transition = scene.handle(GlueInput("panel-action", "return_to_caravan"), self.context)

        self.assertIsInstance(transition, Transition)
        self.assertIs(transition.scene, return_scene)

    def test_generic_map_brief_action_opens_the_selected_generic_briefing(self):
        map_scene = GlueScene("MAP_FLOW")
        machine = SceneMachine(map_scene, self.context)

        self.assertEqual(map_scene.runtime.state.selected_mission.key, "map.0")
        machine.handle(GlueInput("mission-select", "map.0"))
        machine.handle(GlueInput("panel-action", "open_briefing"))

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.program, "BRIEFING")
        self.assertEqual(machine.active.accept_battle, "BF001")
        self.assertIs(machine.active.return_scene, map_scene)

    def test_generic_start_caravan_hotspot_opens_its_flow_program(self):
        caravan = GlueScene(window="STARTCARAVAN")
        machine = SceneMachine(caravan, self.context)

        machine.handle(GlueInput("hotspot-release", "FLOW"))

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.program, "FLOW")

    def test_generic_start_caravan_abort_returns_to_main_menu(self):
        from whshr.campaign_scenes import MainMenuScene

        caravan = GlueScene(window="STARTCARAVAN")
        machine = SceneMachine(caravan, self.context)

        transition = caravan.handle(GlueInput("hotspot-release", "AbortGame"), self.context)

        self.assertIsInstance(transition.scene, MainMenuScene)


if __name__ == "__main__":
    unittest.main()
