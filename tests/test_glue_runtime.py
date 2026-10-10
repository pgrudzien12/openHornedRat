import unittest

from whshr.campaign_state import CampaignState
from whshr.glue_content import GlueContent
from whshr.glue_runtime import (
    ActivityResult,
    Autosave,
    EndGame,
    EnterCaravan,
    GlueInput,
    GlueRuntime,
    OpenWindow,
    PlayMusic,
    PlayClickCue,
    StartBattle,
    StopMusic,
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
            "MUSIC": "[RUN]\n[START]\nplaymidi:sighted\nwaitforrelease:\nstopmidi:\nendgame:\n[END]",
            "TWO_SPEAKERS": ("[RUN]\n[START]\nsettextcolor:red\nqueuetoplaytext:res=1\n"
                             "settextcolor:green\nqueuetoplaytext:res=2\nendgame:\n[END]"),
            "CARAVAN": "[RUN]\n[START]\ngocaravan:select\nendgame:\n[END]",
            "LOOP": "[WINDOW]\n[BITMAP]\nsetbitmap:Cell\nset:animstartframe=1\nset:animstopframe=-1\n[END]\n[END]",
            "FINITE": "[WINDOW]\n[BITMAP]\nsetbitmap:Cell\nset:animstartframe=1\nset:animstopframe=0\n[END]\n[END]",
            "ANIM_LOOP": "[RUN]\n[START]\nopenwindow:res=MAIN\nsetcurwindow:res=MAIN\naddanimobject:res=LOOP\nendgame:\n[END]",
            "ANIM_FINITE": "[RUN]\n[START]\nopenwindow:res=MAIN\nsetcurwindow:res=MAIN\naddanimobject:res=FINITE\nendgame:\n[END]",
            "MOVIE_CONTEXT": "[RUN]\n[START]\nopenwindow:res=MAIN\nplaymovie:A2\nwaitforrelease:\n[END]",
            "PANEL": "[RUN]\n[START]\nopenwindow:res=MAIN\nwaitforrelease:\nendgame:\n[END]",
            "DEBRIEF": "[RUN]\n[START]\nsetdebrief:5\ndebriefwithsummary:0\nendgame:\n[END]",
            "MISSIONS": "[WINDOW]\n[MISSION]\nset:res=601\n[END]\n[END]",
            "MISSION_FLOW": "[RUN]\n[START]\nopenwindow:res=MISSIONS\nwaitforrelease:\n[END]",
            "CAMPAIGN": ("[RUN]\n[START]\nsetgluestatusmask:4\ntestforunitinarmy:3\n"
                         "iftrueaddcash:20\ntestforunitinmarch:7\niftrueaddcash:30\n"
                         "addtroop:3=2\nunitjoinmission:5\nunitleavemission:7\nautosave:\nendgame:\n[END]"),
        })

    def test_click_cues_are_runtime_effects_from_hotspot_and_panel_input(self):
        runtime = GlueRuntime(self.content)

        self.assertEqual(runtime.handle(GlueInput("hotspot-press", cue=4)), (PlayClickCue(4),))
        self.assertEqual(runtime.handle(GlueInput("hotspot-release-cue", cue=3)), (PlayClickCue(3),))
        self.assertEqual(runtime.handle(GlueInput("panel-press")), (PlayClickCue(4),))
        self.assertEqual(runtime.handle(GlueInput("panel-release-cue")), (PlayClickCue(3),))
        self.assertEqual(runtime.handle(GlueInput("hotspot-press")), ())
        runtime.speech_enabled = False
        self.assertEqual(runtime.handle(GlueInput("panel-press")), ())

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

    def test_given_a_pending_dialogue_a_tick_types_it_then_resumes_the_script_on_its_own(self):
        # notes/briefing_dialogue.md §3.5: a 25 ms timer types the text and resumes the script by
        # itself once typing and its hold finish - no click is required. Previously nothing drove
        # this at all, so any script with dialogue before further work (e.g. a trail marker placed
        # afterwards) would park forever without a synthetic drain.
        content = self.content.overlay(strings={"BRTXT": {7: "Hi"}})
        runtime = GlueRuntime(content)
        runtime.start("TALK")
        self.assertEqual(runtime.state.dialogue_text, "Hi")

        self.assertEqual(runtime.tick(40), ())  # under one char step, still typing
        self.assertEqual(runtime.state.dialogue_typed, 0)
        self.assertEqual(runtime.tick(10), ())  # first character typed (40 + 10 = 50 ms)
        self.assertEqual(runtime.state.dialogue_typed, 1)
        self.assertEqual(runtime.tick(50), ())  # second (last) character typed, hold starts
        self.assertEqual(runtime.state.dialogue_typed, 2)
        self.assertIsNotNone(runtime.state.pending)

        self.assertEqual(runtime.tick(700), ())  # under the hold
        self.assertIsNotNone(runtime.state.pending)
        self.assertEqual(runtime.tick(50), (StopSpeech(), EndGame()))
        self.assertIsNone(runtime.state.pending)
        self.assertIsNone(runtime.state.current)

    def test_playmidi_and_stopmidi_emit_music_effects(self):
        runtime = GlueRuntime(self.content)

        self.assertEqual(runtime.start("MUSIC"), (PlayMusic("sighted"),))

        self.assertEqual(runtime.handle(GlueInput("mission-release")), (StopMusic(), EndGame()))

    def test_panel_pause_toggles_and_stops_the_timer_from_advancing_anything(self):
        runtime = GlueRuntime(self.content)
        runtime.start("PANEL")
        runtime.start("ANIM_LOOP")  # gives tick() something to advance

        self.assertEqual(runtime.handle(GlueInput("panel-action", "toggle_pause")), ())
        self.assertTrue(runtime.state.paused)
        self.assertEqual(runtime.tick(1000), ())  # no effects, no animator progress, while paused
        self.assertEqual(runtime.handle(GlueInput("panel-action", "toggle_pause")), ())
        self.assertFalse(runtime.state.paused)

    def test_panel_abort_ends_the_script_and_restores_a_pushed_context_if_there_is_one(self):
        runtime = GlueRuntime(self.content)
        runtime.start("PANEL")
        runtime.push_context()  # simulate having been reached from a parked map, as real flow does

        effects = runtime.handle(GlueInput("panel-action", "abort_briefing"))

        self.assertEqual(effects, (StopSpeech(), StopMusic()))  # no EndGame: a context was restored
        self.assertEqual(runtime.state.context_stack, [])  # the pushed context was consumed

    def test_panel_abort_with_nothing_pushed_behaves_like_endgame(self):
        runtime = GlueRuntime(self.content)
        runtime.start("PANEL")

        effects = runtime.handle(GlueInput("panel-action", "abort_briefing"))

        self.assertEqual(effects, (StopSpeech(), StopMusic(), EndGame()))

    def test_panel_action_reports_a_diagnostic_instead_of_doing_nothing_silently(self):
        runtime = GlueRuntime(self.content)
        runtime.start("PANEL")

        effects = runtime.handle(GlueInput("panel-action", "open_briefing"))

        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].message, "'open_briefing' is not yet implemented")

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

    def test_a_finished_animation_keeps_its_held_last_frame_available_to_a_renderer(self):
        # notes/campaign_tent.md §5.3: a finite animation ends holding its last frame. A renderer
        # looks the current frame up by the object's identity in state.animations; if the entry
        # were dropped once finished, the object would fall back to its (non-bitmap) base name and
        # disappear instead of staying drawn where it was placed.
        runtime = GlueRuntime(self.content)
        runtime.start("ANIM_FINITE")

        runtime.tick(50)
        runtime.tick(50)
        self.assertEqual(len(runtime.state.animations), 1)
        self.assertTrue(runtime.state.animations[0].animator.finished)

        runtime.tick(50)  # further ticks must not drop or re-fire the held animation
        self.assertEqual(len(runtime.state.animations), 1)

    def test_a_speaker_colour_change_clears_the_dialogue_box_instead_of_mixing_colours(self):
        content = self.content.overlay(strings={"BRTXT": {1: "Hello", 2: "Hi there"}})
        runtime = GlueRuntime(content)
        runtime.start("TWO_SPEAKERS")
        self.assertEqual(runtime.state.dialogue_text, "Hello")
        self.assertEqual(runtime.state.dialogue_line_colour, "red")

        runtime.handle(GlueInput("dialogue-drain"))  # first speaker's line completes

        # Second speaker's line is queued under a different colour: the first speaker's now
        # fully-typed line must not carry over into history under the new colour.
        self.assertEqual(runtime.state.dialogue_lines, ())
        self.assertEqual(runtime.state.dialogue_text, "Hi there")
        self.assertEqual(runtime.state.dialogue_line_colour, "green")

    def test_mission_selection_accepts_only_rows_from_active_windows(self):
        runtime = GlueRuntime(self.content)
        runtime.start("MISSION_FLOW")

        runtime.handle(GlueInput("mission-select", "missions.0"))
        self.assertEqual(runtime.state.selected_mission.key, "missions.0")

        runtime.handle(GlueInput("mission-select", "other.0"))
        self.assertEqual(runtime.state.selected_mission.key, "missions.0")

    def test_campaign_commands_update_campaign_state_and_autosave_after_the_command(self):
        campaign = CampaignState(
            {"flow_scripts": {"FLOW": ({"action": "add_window", "window": "MISSIONS"},)},
             "mission_windows": {"MISSIONS": ()}},
            flow="FLOW", army_units={3}, march_units={7}, coffers=500,
        )
        runtime = GlueRuntime(self.content, campaign)

        effects = runtime.start("CAMPAIGN")

        self.assertEqual(effects, (Autosave(), EndGame()))
        self.assertEqual(campaign.coffers, 550)
        self.assertEqual(campaign.reinforcements, {3: 2})
        self.assertEqual(campaign.march_units, {5})
        self.assertEqual(runtime.state.status_bits, 4)
        self.assertIsNotNone(campaign.autosave_state)
        self.assertEqual(campaign.autosave_state.current.pc, 9)

    def test_mission_selection_is_shared_with_campaign_state(self):
        campaign = CampaignState(
            {"flow_scripts": {"FLOW": ({"action": "add_window", "window": "MISSIONS"},)},
             "mission_windows": {"MISSIONS": ()}}, flow="FLOW",
        )
        runtime = GlueRuntime(self.content, campaign)
        runtime.start("MISSION_FLOW")

        runtime.handle(GlueInput("mission-select", "missions.0"))

        self.assertEqual(campaign.selected_mission, runtime.state.selected_mission)


if __name__ == "__main__":
    unittest.main()
