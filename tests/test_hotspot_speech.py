"""A clicked caravan hotspot speaks its click-speech lines; hovering shows only the normal hint
(notes/glue_keywords.md `set:clickres` / `set:clickrescnt`, notes/briefing_dialogue.md)."""
import unittest

from whshr.glue_content import GlueContent
from whshr.glue_render import build_render_model
from whshr.glue_runtime import GlueInput, GlueRuntime, HotspotSpeech, PlaySpeech, WindowInstance

WINDOW = """[WINDOW]
[POSITION]
set:x=0
set:y=0
set:vx=640
set:vy=480
[HOTSPOT]
set:x=1
set:y=1
set:vx=9
set:vy=9
set:res=160
cursor:HandOpenCursor
set:clickres=955
set:clickrescnt=2
script:null.wnd
res:DietrichSpeech
[HOTSPOT]
set:x=20
set:y=1
set:vx=9
set:vy=9
set:res=155
altcursor:HandCursor
[HOTSPOT]
set:x=40
set:y=1
set:vx=9
set:vy=9
set:res=150
cursor:HandCursor
script:pop.wnd
res:UnwindMission
[END]"""
STRINGS = {"BRTXT": {150: "select", 155: "Stop that", 160: "talk", 955: "Line one", 956: "Line two"}}


class HotspotSpeechTests(unittest.TestCase):
    def setUp(self):
        self.content = GlueContent.from_data(resources={"CARAVAN": WINDOW, "FLOW": "[RUN]\n[START]\nopenwindow:res=CARAVAN\n[END]"},
                                             strings=STRINGS)

    def _hotspots(self):
        return build_render_model(self.content, WindowInstance("CARAVAN", None, 0, [])).hotspots

    def test_given_click_speech_data_when_the_window_is_built_then_click_text_is_kept_apart_from_the_hint(self):
        talk, reaction, exit_ = self._hotspots()

        self.assertEqual((talk.hint_id, talk.click_text, talk.click_count), (160, 955, 3))  # clickrescnt=2 counts the lines after the first
        self.assertEqual((reaction.hint_id, reaction.click_text, reaction.click_count), (None, 155, 1))
        self.assertEqual((exit_.hint_id, exit_.click_text), (150, None))

    def test_given_a_reaction_hotspot_when_hovered_then_no_hint_is_shown(self):
        from whshr.frontend.glue_view import _caravan_hint
        campaign = type("Campaign", (), {"coffers": 1, "hint": lambda self, hint, *a: f"hint{hint}"})()
        from whshr.glue_render import GlueRenderModel
        model = GlueRenderModel("CARAVANAFTERMISSION", 0, 0, 640, 480, 0, (), (), self._hotspots(), (), ())
        talk, reaction, _ = self._hotspots()

        self.assertEqual(_caravan_hint(campaign, (model,), talk), "hint160")
        self.assertIsNone(_caravan_hint(campaign, (model,), reaction))

    def test_given_a_click_when_the_lines_play_then_each_is_typed_in_turn_and_the_box_clears(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")

        effects = runtime.handle(GlueInput("hotspot-speech", "955:2"))

        self.assertEqual(effects, (HotspotSpeech(955, 2), PlaySpeech(955)))
        self.assertEqual(runtime.state.dialogue_text, "Line one")
        seen = []
        for _ in range(400):
            runtime.tick(100)
            seen.append(runtime.state.dialogue_text)
        self.assertIn("Line two", seen)
        self.assertEqual(seen[-1], "")
        self.assertFalse(runtime.state.speech_active)

    def test_given_a_speech_in_progress_when_clicked_again_then_the_click_is_ignored(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")
        runtime.handle(GlueInput("hotspot-speech", "955:2:DietrichSpeech"))

        for target in ("955:2:DietrichSpeech", "155:1"):
            self.assertEqual(runtime.handle(GlueInput("hotspot-speech", target)), ())  # neither a skip nor a restart

        self.assertTrue(runtime.state.speech_active)
        self.assertEqual(runtime.state.dialogue_text, "Line one")
        self.assertEqual(runtime.state.speech_lines, (956,))

    def test_given_a_finished_run_when_clicked_again_then_it_restarts_at_the_first_line(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")
        runtime.handle(GlueInput("hotspot-speech", "955:1:DietrichSpeech"))
        for _ in range(400):
            runtime.tick(100)

        effects = runtime.handle(GlueInput("hotspot-speech", "955:1:DietrichSpeech"))

        self.assertEqual(effects, (HotspotSpeech(955, 1), PlaySpeech(955)))

    def test_given_names_when_the_window_is_built_then_the_res_name_and_not_clickres_routes_the_click(self):
        content = GlueContent.from_data(resources={"CARAVAN": WINDOW.replace("res:UnwindMission", "res:DietrichRead")
                                                   .replace("set:clickres=955\nset:clickrescnt=2\n", "")
                                                   .replace("[HOTSPOT]\nset:x=20", "[HOTSPOT]\nset:clickres=955\nset:x=20")
                                                   .replace("altcursor:HandCursor", "cursor:HandCursor\nres:Other")},
                                        strings=STRINGS)

        first, other, third = build_render_model(content, WindowInstance("CARAVAN", None, 0, [])).hotspots

        self.assertEqual((first.click_text, first.click_count, first.speech_variant), (0, 1, "DietrichSpeech"))  # no clickres: id 0
        self.assertEqual((other.click_text, other.speech_variant), (None, None))  # clickres alone does not speak
        self.assertEqual((third.click_text, third.speech_variant), (0, "DietrichRead"))

    def test_given_a_run_when_it_plays_then_the_eyes_and_mouth_animate_until_the_last_line_ends(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")

        runtime.handle(GlueInput("hotspot-speech", "955:2:DietrichSpeech"))

        eyes, mouth = runtime.state.speech_overlays["TalkEyesCell"], runtime.state.speech_overlays["DietMouthCell"]
        self.assertEqual((eyes.display_name, mouth.display_name), ("TalkEyesCell1", "DietMouthCell5"))  # shown at once
        for _ in range(3):  # one 50 ms step per call; a cell shows for three steps
            runtime.tick(50)
        self.assertEqual((eyes.display_name, mouth.display_name), ("TalkEyesCell0", "DietMouthCell4"))
        for _ in range(3):
            runtime.tick(50)
        self.assertEqual(mouth.display_name, "DietMouthCell3")
        self.assertEqual(eyes.display_name, "TalkEyesCell0")  # held for the 3.15 s eye pause
        for _ in range(400):
            runtime.tick(100)
        self.assertEqual(runtime.state.speech_overlays, {})

    def test_given_the_reading_name_when_clicked_then_the_eyes_and_the_book_play(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")

        runtime.handle(GlueInput("hotspot-speech", "955:1:DietrichRead"))

        self.assertEqual({name: a.display_name for name, a in runtime.state.speech_overlays.items()},
                         {"ReadEyesCell": "ReadEyesCell1", "DietBookCell": "DietBookCell11"})

    def test_given_a_paused_window_when_time_passes_then_the_overlays_hold(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")
        runtime.handle(GlueInput("hotspot-speech", "955:1:DietrichSpeech"))
        runtime.state.paused = True

        runtime.tick(1000)

        self.assertEqual(runtime.state.speech_overlays["DietMouthCell"].display_name, "DietMouthCell5")


if __name__ == "__main__":
    unittest.main()
