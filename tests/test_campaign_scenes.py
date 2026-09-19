from pathlib import Path
import tempfile
import unittest

from whshr.assets import AssetId, AssetLocator
from whshr.battle_scene import BattleScene
from whshr.cache import AssetCache
from whshr.campaign_scenes import (
    BriefingScene, CaravanScene, IntroScene, MainMenuScene, OpeningNarrationScene, briefing_asset_for,
)
from whshr.catalog import build
from whshr.scenes import SceneAssets, SceneMachine

BF001 = AssetId("vanilla", "battle", "bf001")


class IntroSceneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self._write("FILE/SCRIPT/BF001.BTS", b"[BATTLESCRIPT]\n[END]\n")
        self._write("FILE/BINARY/STANDARD.PAL", b"palette")
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
        intro = IntroScene()
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

        self.assertIsInstance(machine.active, IntroScene)
        self.assertEqual(machine.history[-1].reason, "opening narration dismissed")

    def test_given_opening_narration_when_the_intro_is_skipped_then_the_menu_becomes_active(self):
        machine = SceneMachine(OpeningNarrationScene(), self.context)

        machine.handle("skip")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[-1].reason, "intro skipped")

    def test_given_intro_when_player_skips_then_main_menu_becomes_active(self):
        machine = SceneMachine(IntroScene(), self.context)

        machine.handle("skip")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "intro skipped")

    def test_given_intro_when_its_timeline_ends_then_main_menu_becomes_active(self):
        machine = SceneMachine(IntroScene(), self.context)

        machine.update(1.75)

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[0].reason, "intro completed")

    def test_given_the_intro_timeline_when_its_end_passes_in_small_steps_then_the_main_menu_becomes_active(self):
        # The real engine never hands a scene one big jump: it ticks in small fixed steps (clock.py,
        # 10 ms). Playtesting report: the intro looped instead of stopping; reproduce the same
        # incremental-update pattern here rather than the single machine.update(1.75) above.
        machine = SceneMachine(IntroScene(), self.context)
        step = 0.01
        for _ in range(174):  # 1.74 s, just short of the 1.75 s timeline
            machine.update(step)

        self.assertIsInstance(machine.active, IntroScene, "must not finish before its own timeline")

        machine.update(step)  # crosses the 1.75 s end

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.history[-1].reason, "intro completed")

    def test_given_main_menu_when_new_campaign_is_chosen_then_the_caravan_becomes_active(self):
        briefing_scene = BriefingScene(BF001)
        machine = SceneMachine(MainMenuScene(briefing_scene), self.context)

        machine.handle("new_campaign")

        self.assertIsInstance(machine.active, CaravanScene)
        self.assertIs(machine.active.briefing, briefing_scene)
        self.assertEqual(machine.history[0].reason, "new campaign started")

    def test_given_the_caravan_when_its_mission_is_chosen_then_the_briefing_becomes_active(self):
        briefing_scene = BriefingScene(BF001)
        machine = SceneMachine(CaravanScene(briefing_scene), self.context)

        machine.handle("select_mission")

        self.assertIs(machine.active, briefing_scene)
        self.assertEqual(machine.active.briefing, self.briefing)
        self.assertEqual(machine.history[0].reason, "first campaign mission selected")

    def test_given_the_caravan_when_dietrich_has_no_message_then_he_reads(self):
        caravan = CaravanScene(BriefingScene(BF001))

        caravan.handle("speak_to_dietrich", self.context)

        self.assertEqual(caravan.dietrich_mode, "reading")

    def test_given_the_caravan_when_dietrich_has_a_message_then_he_talks(self):
        caravan = CaravanScene(BriefingScene(BF001), has_message=True)

        caravan.handle("speak_to_dietrich", self.context)

        self.assertEqual(caravan.dietrich_mode, "talking")

    def test_given_main_menu_when_quit_is_chosen_then_the_application_receives_a_quit_signal(self):
        machine = SceneMachine(MainMenuScene(), self.context)

        machine.handle("quit")

        self.assertIsInstance(machine.active, MainMenuScene)
        self.assertEqual(machine.quit.reason, "player quit from the main menu")
        self.assertEqual(machine.history, [])

    def test_given_mission_briefing_when_entered_then_its_campaign_text_is_loaded(self):
        scene = BriefingScene(BF001)

        SceneMachine(scene, self.context)

        self.assertEqual(scene.briefing_id, briefing_asset_for(BF001))
        self.assertEqual(scene.briefing, self.briefing)

    def test_given_mission_briefing_when_battle_is_started_then_it_transitions_to_that_battle(self):
        scene = BriefingScene(BF001)
        SceneMachine(scene, self.context)

        transition = scene.handle("start_battle", self.context)

        self.assertIsInstance(transition.scene, BattleScene)
        self.assertEqual(transition.scene.battle_id, BF001)
        self.assertEqual(transition.reason, "briefing accepted")


if __name__ == "__main__":
    unittest.main()
