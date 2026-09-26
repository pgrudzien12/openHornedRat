"""The Load / Save dialog and its entry points (notes/builtin_widgets.md §6)."""
import tempfile
import unittest
from pathlib import Path

from whshr import roster
from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign_scenes import MainMenuScene
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.load_save_scene import DEFAULT_DESCRIPTION, LOAD, SAVE, LoadSaveScene
from whshr.savegame import AUTOSAVE_SLOT, SaveStore
from whshr.scenes import SceneAssets, SceneMachine
from tests.test_savegame import GRAPH, MRC, ROWS

CARAVAN = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n[END]\n" \
          "[HOTSPOT]\nset:x=1\nset:y=1\nset:vx=9\nset:vy=9\nscript:pop.wnd\nres:LoadSaveWindow\n[END]"


def campaign(save_dir=None, **fields):
    company = roster.parse_company(MRC, ROWS)
    return CampaignState(GRAPH, mission_window="MAP", company=company, master=company, save_dir=save_dir, **fields)


MISSION_RESOURCES = {
    "CARAVANAFTERMISSION": CARAVAN, "INFOCARAVANTLK": CARAVAN,
    "SELECTSCRIPT": "[RUN]\n[START]\ngocaravan:select\n[END]",
    "TALKSCRIPT": "[RUN]\n[START]\ngocaravan:infoTLK\n[END]",
}


class LoadSaveFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.save_dir = root / "saves"
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(), {}, save_dir=self.save_dir)
        self.context.glue = GlueContent.from_data(resources={"STARTCARAVAN": CARAVAN, "MAINMENU": "[WINDOW]\n[END]",
                                                             **MISSION_RESOURCES})
        self.store = SaveStore(self.save_dir)


class LoadSaveTests(LoadSaveFixture):
    def _dialog(self, mode, state=None):
        """(machine, parent): Save is reached through the caravan's hotspot, Load is the machine's first scene."""
        parent = GlueScene(window="STARTCARAVAN", campaign=state)
        if mode == LOAD:
            dialog = LoadSaveScene(LOAD, parent, new_campaign=lambda context, directory: campaign(directory))
            return SceneMachine(dialog, self.context), parent
        machine = SceneMachine(parent, self.context)
        machine.handle(GlueInput("hotspot-release", "LoadSaveWindow"))
        return machine, parent

    # -- entry points --------------------------------------------------------------------------

    def test_given_the_caravan_save_hotspot_then_the_save_dialog_opens_and_cancel_returns_to_the_same_caravan(self):
        machine, caravan = self._dialog(SAVE, campaign())

        self.assertIsInstance(machine.active, LoadSaveScene)
        self.assertEqual(machine.active.mode, SAVE)
        machine.handle("cancel")

        self.assertIs(machine.active, caravan)

    def test_given_a_caravan_without_a_campaign_then_the_save_hotspot_opens_nothing(self):
        machine, caravan = self._dialog(SAVE)

        self.assertIs(machine.active, caravan)

    def test_given_a_gocaravan_opened_caravan_then_its_save_hotspot_also_opens_the_dialog(self):
        """Not just the caravan opened directly from ``STARTCARAVAN``: one a mission script opened with
        ``gocaravan`` (issue: player report of the caravan's Save/Troop-Book/Abort review)."""
        self.context.glue = GlueContent.from_data(resources={
            "SCRIPT": "[RUN]\n[START]\ngocaravan:infoABC\n[END]", "INFOCARAVANABC": CARAVAN,
            "MAINMENU": "[WINDOW]\n[END]"})
        state = campaign()
        machine = SceneMachine(GlueScene("SCRIPT", state), self.context)

        machine.handle(GlueInput("hotspot-release", "LoadSaveWindow"))

        self.assertIsInstance(machine.active, LoadSaveScene)
        self.assertEqual(machine.active.mode, SAVE)

    def test_given_the_main_menu_when_load_game_then_the_load_dialog_opens(self):
        menu = MainMenuScene()
        machine = SceneMachine(menu, self.context)

        machine.handle("load_game")

        self.assertIsInstance(machine.active, LoadSaveScene)
        self.assertEqual(machine.active.mode, LOAD)
        machine.handle("cancel")
        self.assertIs(machine.active, menu)

    # -- the dialog ----------------------------------------------------------------------------

    def test_given_no_selection_then_ok_does_nothing(self):
        machine, _ = self._dialog(SAVE, campaign())

        machine.handle("ok")

        self.assertFalse(machine.active.editing)
        self.assertFalse(machine.active.ok_enabled)

    def test_given_the_save_dialog_then_the_automatic_slot_cannot_be_selected(self):
        machine, _ = self._dialog(SAVE, campaign())

        machine.handle(f"slot:{AUTOSAVE_SLOT}")

        self.assertIsNone(machine.active.selected)
        self.assertEqual(machine.active.visible_slots, (0, 1, 2, 3, 4))

    def test_given_a_selected_slot_when_ok_then_the_description_prompt_opens_with_a_default(self):
        machine, _ = self._dialog(SAVE, campaign())

        machine.handle("slot:2")
        machine.handle("ok")

        self.assertTrue(machine.active.editing)
        self.assertEqual(machine.active.text, DEFAULT_DESCRIPTION)

    def test_given_the_prompt_when_typing_then_the_text_is_capped_at_25_characters_and_backspace_works(self):
        machine, _ = self._dialog(SAVE, campaign())
        machine.handle("slot:0")
        machine.handle("ok")
        for _ in range(len(DEFAULT_DESCRIPTION)):
            machine.handle("edit:backspace")

        for character in "abcdefghijklmnopqrstuvwxyz0123":
            machine.handle(f"text:{character}")
        machine.handle("edit:backspace")

        self.assertEqual(machine.active.text, "abcdefghijklmnopqrstuvwx")

    def test_given_a_description_when_confirmed_then_the_slot_is_written_and_the_caravan_returns(self):
        state = campaign(coffers=321)
        machine, caravan = self._dialog(SAVE, state)
        machine.handle("slot:1")
        machine.handle("ok")
        for _ in DEFAULT_DESCRIPTION:
            machine.handle("edit:backspace")
        for character in "Before Nuln":
            machine.handle(f"text:{character}")

        machine.handle("ok")

        self.assertIs(machine.active, caravan)
        self.assertEqual(self.store.info(1).description, "Before Nuln")
        fresh = campaign()
        self.store.load_into(1, fresh)
        self.assertEqual(fresh.coffers, 321)

    def test_given_the_prompt_when_cancelled_then_the_dialog_stays_and_nothing_is_written(self):
        machine, _ = self._dialog(SAVE, campaign())
        machine.handle("slot:1")
        machine.handle("ok")

        machine.handle("cancel")

        self.assertIsInstance(machine.active, LoadSaveScene)
        self.assertFalse(machine.active.editing)
        self.assertIsNone(self.store.info(1))

    def test_given_an_occupied_slot_when_saving_then_its_description_is_the_prompts_starting_text(self):
        self.store.write(3, "Old save", campaign())
        machine, _ = self._dialog(SAVE, campaign())

        machine.handle("slot:3")
        machine.handle("ok")

        self.assertEqual(machine.active.text, "Old save")

    def test_given_the_load_dialog_then_an_empty_slot_can_be_selected_but_ok_stays_disabled(self):
        machine, _ = self._dialog(LOAD)

        machine.handle("slot:2")
        machine.handle("ok")

        self.assertEqual(machine.active.selected, 2)
        self.assertFalse(machine.active.ok_enabled)
        self.assertIsInstance(machine.active, LoadSaveScene)

    def test_given_the_load_dialog_then_the_automatic_slot_is_listed(self):
        machine, _ = self._dialog(LOAD)

        self.assertEqual(machine.active.visible_slots, (0, 1, 2, 3, 4, AUTOSAVE_SLOT))

    def test_given_a_saved_game_when_loaded_then_the_caravan_opens_on_the_restored_campaign(self):
        saved = campaign(coffers=999, flow="FLOWB")
        self.store.write(4, "Saved", saved)
        machine, _ = self._dialog(LOAD)

        machine.handle("slot:4")
        machine.handle("ok")

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.window, "STARTCARAVAN")
        self.assertEqual((machine.active.campaign.coffers, machine.active.campaign.flow), (999, "FLOWB"))
        self.assertEqual(machine.active.campaign.save_dir, self.save_dir)

    def test_given_a_damaged_save_when_loaded_then_the_dialog_stays_with_a_message(self):
        self.save_dir.mkdir(parents=True)
        self.store.path(0).write_text('{"version": 1, "campaign": {}}')
        machine, _ = self._dialog(LOAD)
        machine.handle("slot:0")

        machine.handle("ok")

        self.assertIsInstance(machine.active, LoadSaveScene)
        self.assertIn("damaged", machine.active.error)

    def test_given_no_save_directory_then_the_dialog_opens_disabled_with_a_message(self):
        self.context.save_dir = None
        machine, caravan = self._dialog(SAVE, campaign())

        machine.handle("slot:0")
        machine.handle("ok")

        self.assertTrue(machine.active.error)
        self.assertFalse(machine.active.editing)
        machine.handle("cancel")
        self.assertIs(machine.active, caravan)


class MissionCaravanSaveTests(LoadSaveFixture):
    """Saving from a mission's caravans: the finished mission is recorded released; a mid-mission caravan refuses."""

    def _mission_caravan(self, script):
        from tests.test_savegame import FIRST, committed_campaign

        state = committed_campaign()
        state.save_dir = self.save_dir
        scene = GlueScene(script, state, accept_mission=FIRST)
        machine = SceneMachine(scene, self.context)
        machine.handle(GlueInput("hotspot-release", "LoadSaveWindow"))
        return machine, state

    def test_given_the_after_mission_caravan_when_saved_then_the_slot_records_the_mission_released(self):
        from tests.test_savegame import TWO_WINDOWS

        machine, state = self._mission_caravan("SELECTSCRIPT")
        for event in ("slot:0", "ok", "ok"):
            machine.handle(event)

        loaded = CampaignState(TWO_WINDOWS, flow="F", company=state.company)
        self.store.load_into(0, loaded)
        self.assertEqual(loaded.mission_window, "W2")
        self.assertEqual(state.mission_window, "W1")  # the open caravan's own campaign is not advanced by saving

    def test_given_a_mid_mission_caravan_when_saving_then_the_dialog_refuses_with_a_message(self):
        machine, _ = self._mission_caravan("TALKSCRIPT")

        machine.handle("slot:0")
        machine.handle("ok")

        self.assertIn("middle of a mission", machine.active.error)
        self.assertFalse(machine.active.editing)
        self.assertIsNone(self.store.info(0))


if __name__ == "__main__":
    unittest.main()
