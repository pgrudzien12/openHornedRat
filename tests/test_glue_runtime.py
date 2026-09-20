import unittest

from whshr.glue_content import GlueContent
from whshr.glue_runtime import (
    ActivityResult,
    EndGame,
    EnterCaravan,
    GlueInput,
    GlueRuntime,
    OpenWindow,
    StartBattle,
    StartDebrief,
    StartDialogue,
    StartMovie,
    StopSpeech,
    UpdateWindow,
)


class GlueRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.content = GlueContent.from_data(resources={
            "MAIN": "[WINDOW]\n[POSITION]\nset:palindex=2\n[END]\n[END]",
            "CHILD": "[WINDOW]\n[END]",
            "FLOW": "[RUN]\n[START]\nopenwindow:res=MAIN\nwaitforrelease:\nsetgluestatusmask:4\nsetgluestatus:\niftruegosub:SUB\nendgame:\n[END]",
            "SUB": "[RUN]\n[START]\nopensubwindow:res=CHILD\nreturn:\n[END]",
            "MOVIE": "[RUN]\n[START]\nplaymovie:A2\nplaygamewithdebrief:bf001,3\n[END]",
            "TALK": "[RUN]\n[START]\nqueuetoplaytext:res=7\nendgame:\n[END]",
            "CARAVAN": "[RUN]\n[START]\ngocaravan:select\nendgame:\n[END]",
            "LOOP": "[WINDOW]\n[BITMAP]\nsetbitmap:Cell\nset:animstartframe=1\nset:animstopframe=-1\n[END]\n[END]",
            "FINITE": "[WINDOW]\n[BITMAP]\nsetbitmap:Cell\nset:animstartframe=1\nset:animstopframe=0\n[END]\n[END]",
            "ANIM_LOOP": "[RUN]\n[START]\nopenwindow:res=MAIN\nsetcurwindow:res=MAIN\naddanimobject:res=LOOP\nendgame:\n[END]",
            "ANIM_FINITE": "[RUN]\n[START]\nopenwindow:res=MAIN\nsetcurwindow:res=MAIN\naddanimobject:res=FINITE\nendgame:\n[END]",
            "MOVIE_CONTEXT": "[RUN]\n[START]\nopenwindow:res=MAIN\nplaymovie:A2\nwaitforrelease:\n[END]",
            "DEBRIEF": "[RUN]\n[START]\nsetdebrief:5\ndebriefwithsummary:0\nendgame:\n[END]",
        })

    def test_given_a_waiting_flow_when_mission_release_arrives_then_it_runs_the_subroutine_and_ends(self):
        runtime = GlueRuntime(self.content)

        effects = runtime.start("FLOW")
        self.assertEqual(effects, (OpenWindow("MAIN", None, 2),))
        self.assertEqual(runtime.state.wait_reason, "mission-release")

        effects = runtime.handle(GlueInput("mission-release"))

        self.assertEqual(effects, (OpenWindow("CHILD", "MAIN", 2), EndGame()))
        self.assertIsNone(runtime.state.current)
        self.assertEqual(runtime.state.status_bits, 4)

    def test_given_a_movie_then_its_completion_resumes_the_same_script_at_its_battle_request(self):
        runtime = GlueRuntime(self.content)

        effects = runtime.start("MOVIE")
        movie = effects[0]
        self.assertIsInstance(movie, StartMovie)

        effects = runtime.resume(ActivityResult(movie.request_id, "movie"))
        battle = effects[0]
        self.assertIsInstance(battle, StartBattle)
        self.assertEqual((battle.battle, battle.debrief_index, battle.with_debrief), ("BF001", 2, True))

        effects = runtime.resume(ActivityResult(battle.request_id, "battle"))
        self.assertEqual(effects, ())
        self.assertIsNone(runtime.state.current)

    def test_given_a_dialogue_when_speech_is_disabled_then_queue_to_play_text_continues_without_a_wait(self):
        runtime = GlueRuntime(self.content, speech_enabled=False)

        effects = runtime.start("TALK")

        self.assertEqual(effects, (EndGame(),))

    def test_given_a_dialogue_when_speech_is_enabled_then_completion_continues_the_program(self):
        runtime = GlueRuntime(self.content)

        effects = runtime.start("TALK")
        dialogue = effects[0]
        self.assertIsInstance(dialogue, StartDialogue)
        self.assertEqual(dialogue.string_id, 7)

        self.assertEqual(runtime.resume(ActivityResult(dialogue.request_id, "dialogue")), (EndGame(),))

    def test_given_a_pending_dialogue_when_an_empty_release_drains_it_then_speech_stops_and_the_script_continues(self):
        runtime = GlueRuntime(self.content)
        runtime.start("TALK")

        effects = runtime.handle(GlueInput("dialogue-drain"))

        self.assertEqual(effects, (StopSpeech(), EndGame()))
        self.assertIsNone(runtime.state.pending)
        self.assertIsNone(runtime.state.current)

    def test_given_a_caravan_request_when_started_then_it_remains_suspended_until_its_host_resumes_it(self):
        runtime = GlueRuntime(self.content)

        effects = runtime.start("CARAVAN")
        request = effects[0]
        self.assertIsInstance(request, EnterCaravan)
        self.assertEqual(request.mode, "select")

        self.assertEqual(runtime.resume(ActivityResult(request.request_id, "caravan")), (EndGame(),))

    def test_given_a_movie_context_when_it_finishes_then_the_parked_window_and_next_instruction_are_restored(self):
        runtime = GlueRuntime(self.content)

        effects = runtime.start("MOVIE_CONTEXT")
        movie = effects[-1]
        self.assertIsInstance(movie, StartMovie)
        self.assertEqual(runtime.state.windows, [])
        self.assertEqual(runtime.state.palette_id, 2)
        self.assertEqual(len(runtime.state.context_stack), 1)

        self.assertEqual(runtime.resume(ActivityResult(movie.request_id, "movie")), ())
        self.assertEqual([window.name for window in runtime.state.windows], ["MAIN"])
        self.assertEqual(runtime.state.palette_id, 2)
        self.assertEqual(runtime.state.wait_reason, "mission-release")
        self.assertEqual(len(runtime.state.context_stack), 0)

    def test_given_a_summary_debrief_when_its_argument_is_zero_then_the_prior_evaluator_is_preserved(self):
        runtime = GlueRuntime(self.content)

        debrief = runtime.start("DEBRIEF")[0]

        self.assertIsInstance(debrief, StartDebrief)
        self.assertEqual((debrief.mode, debrief.debrief_index, debrief.summary), (7, 4, True))
        self.assertEqual(runtime.resume(ActivityResult(debrief.request_id, "debrief")), (EndGame(),))

    def test_given_a_snapshot_at_a_wait_then_restoring_it_preserves_the_next_effect(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")
        snapshot = runtime.snapshot()
        resumed = runtime.handle(GlueInput("mission-release"))

        runtime.restore(snapshot)

        self.assertEqual(runtime.handle(GlueInput("mission-release")), resumed)

    def test_looping_addanimobject_does_not_park_the_script(self):
        runtime = GlueRuntime(self.content)

        self.assertEqual(runtime.start("ANIM_LOOP"), (OpenWindow("MAIN", None, 2), UpdateWindow("MAIN"), EndGame()))

    def test_finite_addanimobject_parks_until_the_animation_finishes(self):
        runtime = GlueRuntime(self.content)

        self.assertEqual(runtime.start("ANIM_FINITE"), (OpenWindow("MAIN", None, 2), UpdateWindow("MAIN")))
        self.assertEqual(runtime.state.wait_reason, "animation-finished")

        self.assertEqual(runtime.tick(50), ())
        self.assertEqual(runtime.tick(50), (EndGame(),))
        self.assertIsNone(runtime.state.current)


if __name__ == "__main__":
    unittest.main()
