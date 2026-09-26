"""The Yes/No confirmation before an Abort leaves (notes/builtin_widgets.md §4.1, notes/activity_results.md §4.3, §6)."""
import unittest

from tests.test_glue_scene import _Context
from whshr.campaign_scenes import TroopSelectionScene
from whshr.campaign_state import CampaignState
from whshr.confirm_scene import FALLBACK_QUESTION, ConfirmScene
from whshr.glue import MissionRef
from whshr.glue_content import GlueContent
from whshr.glue_scene import GlueScene
from whshr.roster import Regiment, RosterRow
from whshr.scenes import Scene, SceneMachine


class Marker(Scene):
    pass


class _Assets(_Context):
    """Enough of SceneAssets for a confirm scene: the glue content and no fonts."""


def regiment(whoami, for_hire=True, hired=True):
    row = RosterRow(whoami, keep=False, for_hire=for_hire, wizard=False, artillery=False, base_price=10)
    return Regiment(whoami, f"Regiment{whoami}", hired, 10, 10, 0, row)


class ConfirmSceneTests(unittest.TestCase):
    def setUp(self):
        self.context = _Assets(GlueContent.from_data(resources={}, strings={"GMTXT": {36070: "Sure?"}}))
        self.parent, self.destination = Marker(), Marker()

    def _machine(self, **kwargs):
        scene = ConfirmScene(self.parent, self.destination, ("GMTXT", 36070), **kwargs)
        return SceneMachine(scene, self.context), scene

    def test_given_yes_then_the_destination_opens_after_the_yes_callback(self):
        calls = []
        machine, _ = self._machine(on_yes=lambda: calls.append("left"))

        machine.handle("yes")

        self.assertIs(machine.active, self.destination)
        self.assertEqual(calls, ["left"])

    def test_given_no_then_the_parent_returns_and_the_yes_callback_never_runs(self):
        calls = []
        machine, _ = self._machine(on_yes=lambda: calls.append("left"))

        machine.handle("no")

        self.assertIs(machine.active, self.parent)
        self.assertEqual(calls, [])

    def test_given_other_events_then_the_box_stays(self):
        machine, scene = self._machine()

        machine.handle("ok")

        self.assertIs(machine.active, scene)

    def test_given_the_question_is_in_the_string_table_then_it_is_used_else_a_fallback(self):
        _, scene = self._machine()
        self.assertEqual(scene.question, "Sure?")

        self.context.content = GlueContent.from_data(resources={})
        self.assertEqual(scene.question, FALLBACK_QUESTION)


class TroopSelectionAbortTests(unittest.TestCase):
    def setUp(self):
        self.context = _Assets(GlueContent.from_data(resources={
            "BRIEFING": "[RUN]\n[START]\nwaitforrelease:\n[END]",
            "MAP": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n[MISSION]\nset:res=601\nres:BRIEFING\n"
                   "setbattlescript:BF001\ncash:1,100,50\n[END]"}))

    def _selection(self, company):
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP", coffers=500,
                                 company=tuple(company))
        parked = GlueScene("BRIEFING", campaign, accept_battle="bf001")
        parked.enter(self.context)
        selection = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)
        selection.enter(self.context)
        return selection, parked

    def test_given_something_selected_when_abort_then_it_asks_and_yes_returns_to_the_parked_scene(self):
        selection, parked = self._selection([regiment(2, for_hire=False)])
        self.assertTrue(selection.selection_model().selection)

        asked = selection.handle("abort", self.context)

        self.assertIsInstance(asked.scene, ConfirmScene)
        self.assertEqual(asked.scene.string, ("BRTXT", 308))
        self.assertIs(asked.scene.handle("yes", self.context).scene, parked)

    def test_given_something_selected_when_abort_is_declined_then_the_selection_screen_returns(self):
        selection, _ = self._selection([regiment(2, for_hire=False)])

        asked = selection.handle("abort", self.context)

        self.assertIs(asked.scene.handle("no", self.context).scene, selection)
        self.assertTrue(selection.selection_model().selection)

    def test_given_nothing_selected_when_abort_then_it_leaves_silently(self):
        selection, parked = self._selection([regiment(2, for_hire=False), regiment(5, hired=False)])
        selection.selection_model().selection.clear()

        left = selection.handle("abort", self.context)

        self.assertIs(left.scene, parked)


if __name__ == "__main__":
    unittest.main()
