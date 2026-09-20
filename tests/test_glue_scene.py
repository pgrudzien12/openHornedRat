import unittest

from whshr.glue_content import GlueContent
from whshr.glue_runtime import ActivityResult, EndGame, GlueInput, OpenWindow, StartBattle, StartMovie, StopMusic
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneMachine


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
        }))

    def test_scene_owns_runtime_effects_across_input_and_activity_boundaries(self):
        scene = GlueScene("flow")
        machine = SceneMachine(scene, self.context)

        self.assertEqual(scene.take_effects(), (OpenWindow("WINDOW", None, 2),))
        machine.handle(GlueInput("mission-release"))
        movie = scene.take_effects()[0]
        self.assertIsInstance(movie, StartMovie)

        machine.handle(ActivityResult(movie.request_id, "movie"))
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

        scene.handle(GlueInput("panel-action", "accept_briefing"), self.context)

        effects = scene.take_effects()
        self.assertEqual(effects[0], StopMusic())
        self.assertIsInstance(effects[1], StartBattle)
        self.assertEqual(effects[1].battle, "BF001")


if __name__ == "__main__":
    unittest.main()
