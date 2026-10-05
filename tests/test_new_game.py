"""New Game: the name prompt and the campaign file reset (notes/native-windows.md §7)."""
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
from whshr.glue_scene import GlueScene
from whshr.glue_state import decode_state, encode_state
from whshr.name_prompt_scene import NamePromptScene
from whshr.new_game import NAME_LIMIT, accepts_character, filter_name
from whshr.scenes import SceneAssets, SceneMachine
from tests.test_savegame import GRAPH, MRC, ROWS

CARAVAN = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n[END]"


LEADER = "addleader:Captain_Ulrich\nsetstats:s_side=2,12,12,4\nendleader:\n"
COMPANY = MRC.replace("banner:COMM,0\n", "banner:COMM,0\n" + LEADER, 1)


def commander():
    return next(r for r in roster.parse_company(COMPANY, ROWS) if r.whoami == roster.ALWAYS_FORCED_WHOAMI)


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.save_dir = self.root / "saves"
        self.context = SceneAssets(AssetLocator(self.root), build(self.root), AssetCache(), {}, save_dir=self.save_dir)
        self.context.glue = GlueContent.from_data(resources={"STARTCARAVAN": CARAVAN, "MAINMENU": "[WINDOW]\n[END]"})

    def campaign(self):
        company = roster.parse_company(COMPANY, ROWS)
        return CampaignState(GRAPH, mission_window="MAP", company=company, master=company)


class NameFilterTests(unittest.TestCase):
    def test_given_characters_then_only_the_documented_set_is_accepted(self):
        self.assertTrue(all(accepts_character(c) for c in "aZ5 !\"'(),.:;?"))
        self.assertFalse(any(accepts_character(c) for c in ("_", "<", "-", "/", "é", "", "ab")))

    def test_given_long_text_then_it_is_filtered_and_cut_to_fifteen_characters(self):
        self.assertEqual(filter_name("Ab_c<d-e/f" + "x" * 30), ("Abcdef" + "x" * 30)[:NAME_LIMIT])


class NamePromptTests(Fixture):
    def _prompt(self):
        campaign = self.campaign()
        prompt = NamePromptScene(campaign)
        prompt.enter(self.context)
        return prompt, campaign

    def _type(self, prompt, text):
        for char in text:
            prompt.handle(f"text:{char}", self.context)

    def test_given_the_prompt_then_the_default_is_the_commanders_leader_name(self):
        prompt, _ = self._prompt()
        self.assertEqual(prompt.text, commander().leader_name)

    def test_given_selected_default_when_typing_then_the_first_character_replaces_it(self):
        prompt, _ = self._prompt()
        self._type(prompt, "Bob_<-é")
        self.assertEqual(prompt.text, "Bob")

    def test_given_more_than_fifteen_characters_then_the_rest_is_refused(self):
        prompt, _ = self._prompt()
        self._type(prompt, "x" * 20)
        self.assertEqual(prompt.text, "x" * NAME_LIMIT)

    def test_given_selected_default_when_backspace_then_the_box_empties(self):
        prompt, _ = self._prompt()
        prompt.handle("edit:backspace", self.context)
        self.assertEqual(prompt.text, "")

    def test_given_enter_then_the_name_is_stored_saved_and_the_caravan_starts_over_the_menu_frame(self):
        prompt, campaign = self._prompt()
        machine = SceneMachine(prompt, self.context)
        self._type(prompt, "Dieter Brau")

        machine.handle("ok")

        self.assertEqual(campaign.commander_name, "Dieter Brau")
        self.assertIn("addleader:Dieter_Brau", roster.company_text(campaign.company))
        self.assertFalse(self.save_dir.exists(), "campaign state lives in the JSON slots, not in loose files")
        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.window, "STARTCARAVAN")
        self.assertEqual([frame.kind for frame in machine.active.runtime.state.context_stack], ["WINDOW"])
        self.assertEqual(machine.active.runtime.state.context_stack[0].current_window_name, "MAINMENU")

    def test_given_escape_then_the_game_still_starts_with_the_default_name(self):
        prompt, campaign = self._prompt()
        default = campaign.commander_name
        machine = SceneMachine(prompt, self.context)
        self._type(prompt, "Other")

        machine.handle("cancel")

        self.assertEqual(campaign.commander_name, default)
        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(len(machine.active.runtime.state.context_stack), 1)

    def test_given_a_window_frame_on_the_stack_then_the_interpreter_state_round_trips(self):
        prompt, _ = self._prompt()
        machine = SceneMachine(prompt, self.context)
        machine.handle("ok")

        state = machine.active.runtime.state

        self.assertEqual(decode_state(encode_state(state)).context_stack, state.context_stack)


class MainMenuNewGameTests(Fixture):
    def test_given_the_main_menu_when_new_campaign_then_the_name_prompt_opens_on_a_fresh_campaign(self):
        campaign = self.campaign()
        original = CampaignState.from_installation
        CampaignState.from_installation = classmethod(lambda cls, *a, **k: campaign)
        self.addCleanup(setattr, CampaignState, "from_installation", original)
        machine = SceneMachine(MainMenuScene(), self.context)

        machine.handle("new_campaign")

        self.assertIsInstance(machine.active, NamePromptScene)
        self.assertIs(machine.active.campaign, campaign)
        self.assertFalse(self.save_dir.exists())
