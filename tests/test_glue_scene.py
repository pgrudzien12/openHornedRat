import unittest

from whshr.glue_content import GlueContent
from whshr.glue_runtime import ActivityResult, EndGame, GlueInput, OpenWindow, StartBattle, StartMovie, StopMusic
from whshr.glue_scene import GlueScene
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
            "MAP": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n[MISSION]\nset:res=601\nres:BRIEFING\nsetbattlescript:BF001\n[END]",
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

    def test_briefing_accept_starts_the_configured_battle(self):
        scene = GlueScene("BRIEFING", accept_battle="bf001")
        SceneMachine(scene, self.context)

        scene.handle(GlueInput("panel-action", "open_troop_select"), self.context)

        effects = scene.take_effects()
        self.assertEqual(effects[0], StopMusic())
        self.assertIsInstance(effects[1], StartBattle)
        self.assertEqual(effects[1].battle, "BF001")

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
