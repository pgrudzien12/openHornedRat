"""A clicked caravan hotspot speaks its click-speech lines; hovering shows only the normal hint
(notes/glue_keywords.md `set:clickres` / `set:clickrescnt`, notes/briefing_dialogue.md)."""
import unittest

from whshr.glue_content import GlueContent
from whshr.glue_render import build_render_model
from whshr.glue_runtime import GlueInput, GlueRuntime, HotspotSpeech, WindowInstance

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

        self.assertEqual((talk.hint_id, talk.click_text, talk.click_count), (160, 955, 2))
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

        self.assertEqual(effects, (HotspotSpeech(955, 2),))
        self.assertEqual(runtime.state.dialogue_text, "Line one")
        seen = []
        for _ in range(400):
            runtime.tick(100)
            seen.append(runtime.state.dialogue_text)
        self.assertIn("Line two", seen)
        self.assertEqual(seen[-1], "")
        self.assertFalse(runtime.state.speech_active)

    def test_given_a_speech_in_progress_when_clicked_again_then_it_is_ignored(self):
        runtime = GlueRuntime(self.content)
        runtime.start("FLOW")
        runtime.handle(GlueInput("hotspot-speech", "955:1"))

        self.assertEqual(runtime.handle(GlueInput("hotspot-speech", "155:1")), ())
        self.assertEqual(runtime.state.dialogue_text, "Line one")


if __name__ == "__main__":
    unittest.main()
