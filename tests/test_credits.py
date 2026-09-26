"""The Credits page opened from the main menu (notes/native-windows.md section 3)."""
import unittest

from tests.test_glue_scene import _Context
from whshr.credits_scene import HEADING_BASE, SECTION_LINES, TITLE_ID, CreditsScene
from whshr.glue_content import GlueContent
from whshr.scenes import Scene, SceneMachine

IDS = {TITLE_ID, *(HEADING_BASE + n for n in range(28)), *(i for lines in SECTION_LINES for i in lines)}


class Marker(Scene):
    pass


class CreditsSceneTests(unittest.TestCase):
    def setUp(self):
        strings = {"BKTXT": {i: f"text{i}" for i in IDS}, "BRTXT": {304: "Done"}}
        self.parent = Marker()
        self.scene = CreditsScene(self.parent)
        self.machine = SceneMachine(self.scene, _Context(GlueContent.from_data(resources={}, strings=strings)))

    def test_given_entry_then_28_sections_a_title_and_the_tune_are_shown(self):
        self.assertEqual(len(self.scene.sections), 28)
        self.assertEqual(self.scene.title, f"text{TITLE_ID}")
        self.assertEqual(self.scene.tune, "intro3")

    def test_given_the_id_table_then_every_id_exists_in_the_string_table(self):
        self.assertTrue(all(section.heading and all(section.lines) for section in self.scene.sections))
        self.assertLessEqual(max(len(lines) for lines in SECTION_LINES), 8)

    def test_given_done_then_the_main_menu_returns_and_the_tune_stops(self):
        self.machine.handle("credits:done")

        self.assertIs(self.machine.active, self.parent)
        self.assertIsNone(self.scene.tune)

    def test_given_other_events_then_the_page_stays(self):
        self.machine.handle("ok")

        self.assertIs(self.machine.active, self.scene)


if __name__ == "__main__":
    unittest.main()
