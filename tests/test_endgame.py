"""``endgame`` returns to the main menu; the caravan's AbortGame asks BRTXT 308 first
(notes/glue_interpreter.md section 8.5, notes/native-windows.md section 13; issues #125, #160)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_battle_scene import SCRIPT
from tests.test_post_mission_caravan import RESOURCES as CARAVANS
from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign_scenes import MainMenuScene
from whshr.catalog import build
from whshr.confirm_scene import ConfirmScene
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneAssets, SceneMachine

RESOURCES = {
    **CARAVANS,
    "ENDSCRIPT": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\nendgame:\n[END]",
    "ENDLATER": "[RUN]\n[START]\nendgame:\nopenwindow:res=AFTERWINDOW\n[END]",
}


class EndGameTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(),
                                   {"battle-script": lambda _, path: SimpleNamespace(script=SCRIPT)})
        self.context.glue = GlueContent.from_data(resources=RESOURCES)
        self.context.no_battle = True

    def test_given_scripts_ending_with_endgame_when_they_run_then_the_main_menu_is_shown(self) -> None:
        for program in ("ENDSCRIPT", "ENDLATER"):
            with self.subTest(program=program):
                machine = SceneMachine(GlueScene(program), self.context)

                self.assertIsInstance(machine.active, MainMenuScene)

    def test_given_a_command_line_log_dir_and_seed_when_endgame_returns_to_the_menu_then_they_are_kept(self) -> None:
        self.context.battle_log_dir = "logs"
        self.context.battle_seed = 42

        machine = SceneMachine(GlueScene("ENDSCRIPT"), self.context)

        assert isinstance(machine.active, MainMenuScene)
        self.assertEqual((machine.active.log_dir, machine.active.seed), ("logs", 42))

    def test_given_a_caravan_when_abort_is_asked_then_the_question_is_brtxt_308_and_yes_lands_on_the_menu(self) -> None:
        for program in ("INFOSCRIPT", "RECRUITSCRIPT"):
            with self.subTest(program=program):
                machine = SceneMachine(GlueScene(program), self.context)

                machine.handle(GlueInput("hotspot-release", "AbortGame"))

                assert isinstance(machine.active, ConfirmScene)
                self.assertEqual(machine.active.string, ("BRTXT", 308))
                machine.handle("yes")
                self.assertIsInstance(machine.active, MainMenuScene)


if __name__ == "__main__":
    unittest.main()
