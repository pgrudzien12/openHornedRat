from pathlib import Path
import tempfile
import unittest

from whshr.assets import AssetId, AssetLocator
from whshr.battle_scene import BattleScene
from whshr.cache import AssetCache
from whshr.campaign_scenes import (
    BriefingScene, MainMenuScene, MissionMapScene, MovieScene, OpeningNarrationScene,
    TroopSelectScene, briefing_asset_for,
)
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.glue_runtime import EndGame
from whshr.glue_scene import GlueScene
from whshr.glue_content import GlueContent
from whshr.scenes import SceneAssets, SceneMachine

BF001 = AssetId("vanilla", "battle", "bf001")


class MovieSceneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self._write("FILE/SCRIPT/BF001.BTS", b"[BATTLESCRIPT]\n[END]\n")
        self._write("FILE/BINARY/STANDARD.PAL", b"palette")
        self._write("FILE/BINARY/PCSUBT.FON", b"MZ")
        self._write("FILE/BINARY/PCTEXTA.FON", b"MZ")
        self._write("FILE/BINARY/GLUE/PCTEXT.FON", b"MZ")
        self._write("FILE/DLL/ANTXT.DLL", b"MZ")
        self._write("FILE/BINARY/GLUE/SUBTEXT.FON", b"MZ")
        self._write("REMOTE/BINARY/ANIM/A1.SI", b"container")
        self._write("FILE/DLL/WND.DLL", b"MZ")
        self.container = {
            "root": {
                "start": 0, "duration": 0,
                "children": [{"start": 0, "duration": 1_000}, {"start": 500, "duration": 1_250}],
            }
        }
        self.media = {"objects": {1: {"smk": {}, "blob": b"fake-smk"}}}
        self.texts = {
            1100: "Stormclouds gather over the Border Princes, ",
            1101: "unnoticed by the reclusive Wizard engrossed in the study of his profound discovery - ",
            1102: "an ancient crystal of Elven origin, together with something far more sinister...",
        }
        self.subtitle_font = object()
        self.briefing = {"battle": "BF001", "title": "Sven Carlsson", "lines": []}
        self.loaded = []
        self.context = SceneAssets(
            AssetLocator(self.root), build(self.root), AssetCache(),
            {
                "omni-si": self._loader(self.container),
                "omni-si-media": self._loader(self.media),
                "pe-string-table": self._loader(self.texts),
                "warhammer-fon": self._loader(self.subtitle_font),
                "campaign-briefing": self._loader(self.briefing),
            },
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _loader(self, value):
        def load(_record, path):
            self.loaded.append(path)
            return value
        return load

    def test_given_intro_when_entered_then_its_original_container_and_media_are_loaded(self):
        intro = MovieScene("a1", successor=MainMenuScene())
        SceneMachine(intro, self.context)

        self.assertEqual(intro.duration_seconds, 1.75)
        self.assertIs(intro.media, self.media)
        self.assertIs(intro.texts, self.texts)
        self.assertIs(intro.subtitle_font, self.subtitle_font)
        self.assertEqual(self.loaded, [self.root / "REMOTE/BINARY/ANIM/A1.SI"] * 2 +
                         [self.root / "FILE/DLL/ANTXT.DLL", self.root / "FILE/BINARY/GLUE/SUBTEXT.FON"])

    def test_given_opening_narration_when_clicked_then_the_intro_cutscene_becomes_active(self):
        machine = SceneMachine(OpeningNarrationScene(), self.context)

        self.assertEqual(machine.active.text, "".join(self.texts[text_id] for text_id in (1100, 1101, 1102)))
        machine.handle("continue")

        self.assertIsInstance(machine.active, MovieScene)
        self.assertEqual(machine.history[-1].reason, "opening narration dismissed")

    def test_given_opening_narration_when_the_intro_is_skipped_then_the_menu_becomes_active(self):
        machine = SceneMachine(OpeningNarrationScene(), self.context)

        machine.handle("skip")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[-1].reason, "intro skipped")

    def test_given_intro_when_player_skips_then_main_menu_becomes_active(self):
        machine = SceneMachine(MovieScene("a1", successor=MainMenuScene()), self.context)

        machine.handle("skip")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "movie skipped")

    def test_given_intro_when_its_timeline_ends_then_main_menu_becomes_active(self):
        machine = SceneMachine(MovieScene("a1", successor=MainMenuScene()), self.context)

        machine.update(1.75)

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "movie completed")

    def test_given_the_intro_timeline_when_its_end_passes_in_small_steps_then_the_main_menu_becomes_active(self):
        # The real engine never hands a scene one big jump: it ticks in small fixed steps (clock.py,
        # 10 ms). Playtesting report: the intro looped instead of stopping; reproduce the same
        # incremental-update pattern here rather than the single machine.update(1.75) above.
        machine = SceneMachine(MovieScene("a1", successor=MainMenuScene()), self.context)
        step = 0.01
        for _ in range(174):  # 1.74 s, just short of the 1.75 s timeline
            machine.update(step)

        self.assertIsInstance(machine.active, MovieScene, "must not finish before its own timeline")

        machine.update(step)  # crosses the 1.75 s end

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[-1].reason, "movie completed")

    def test_given_main_menu_when_new_campaign_is_chosen_then_the_initial_glue_flow_becomes_active(self):
        briefing_scene = BriefingScene({"briefing_key": "test.0", "battle": "BF001"})
        self.context.glue = GlueContent.from_data(resources={
            "FLOWSCRIPTBP01": "[RUN]\n[START]\nendgame:\n[END]",
        })
        machine = SceneMachine(MainMenuScene(briefing_scene), self.context)

        machine.handle("new_campaign")

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.window, "STARTCARAVAN")
        self.assertIs(machine.active.campaign, machine.initial.campaign)
        self.assertEqual(machine.history[0].reason, "new campaign started")

    def test_given_a_selected_map_mission_when_accept_is_pressed_then_troop_selection_opens(self):
        campaign = CampaignState.single_mission(BriefingScene({"briefing_key": "test.0", "battle": "BF001"}))
        machine = SceneMachine(MissionMapScene(campaign), self.context)
        machine.handle("select_mission:0")

        machine.handle("open_troop_select")

        self.assertIsInstance(machine.active, TroopSelectScene)
        self.assertEqual(machine.active.mission["battle"], "BF001")

    def test_given_a_selected_mission_with_a_glue_briefing_then_the_generic_scene_receives_its_battle(self):
        campaign = CampaignState(
            {"flow_scripts": {"FLOW": ({"action": "add_window", "window": "MAP"},)},
             "mission_windows": {"MAP": [{"name": "Test", "name_id": 1,
                                             "brief_script": "BRIEFING", "battle": "BF001"}]}},
            flow="FLOW",
        )
        scene = MissionMapScene(campaign)
        scene.selected_index = 0

        transition = scene.handle("open_briefing", self.context)

        self.assertIsInstance(transition.scene, GlueScene)
        self.assertEqual((transition.scene.program, transition.scene.accept_battle), ("BRIEFING", "BF001"))
        self.assertIs(transition.scene.return_scene, scene)

    def test_given_a_glue_playmovie_then_the_scene_machine_starts_a_movie_and_resumes_the_glue_scene(self):
        self._write("REMOTE/BINARY/ANIM/A2.SI", b"container")
        context = SceneAssets(self.context.locator, build(self.root), self.context.cache, self.context.loaders,
                              glue=GlueContent.from_data(resources={
                                  "FLOW": "[RUN]\n[START]\nplaymovie:A2\nendgame:\n[END]",
                              }))
        machine = SceneMachine(GlueScene("FLOW"), context)

        self.assertIsInstance(machine.active, MovieScene)
        self.assertEqual(machine.active.movie, "A2")
        self.assertEqual(machine.history[-1].reason, "glue movie started")

        machine.update(machine.active.duration_seconds)

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.take_effects(), (EndGame(),))

    def test_given_main_menu_when_quit_is_chosen_then_the_application_receives_a_quit_signal(self):
        machine = SceneMachine(MainMenuScene(), self.context)

        machine.handle("quit")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.quit.reason, "player quit from the main menu")
        self.assertEqual(machine.history, [])

    def test_given_mission_briefing_when_entered_then_its_campaign_text_is_loaded(self):
        mission = {"briefing_key": "test.0", "battle": "BF001"}
        scene = BriefingScene(mission)

        SceneMachine(scene, self.context)

        self.assertEqual(scene.briefing_id, briefing_asset_for(mission))
        self.assertEqual(scene.briefing, self.briefing)
        self.assertEqual(scene.installation.root, self.root)

    def test_given_mission_briefing_when_battle_is_started_then_it_transitions_to_that_battle(self):
        scene = BriefingScene({"briefing_key": "test.0", "battle": "BF001"})
        SceneMachine(scene, self.context)

        transition = scene.handle("start_battle", self.context)

        self.assertIsInstance(transition.scene, BattleScene)
        self.assertEqual(transition.scene.battle_id, BF001)
        self.assertEqual(transition.reason, "briefing accepted")


if __name__ == "__main__":
    unittest.main()
