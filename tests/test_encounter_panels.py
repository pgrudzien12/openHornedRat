"""Encounter and ambush windows progress (notes/activity_results.md sections 2.4 and 3), headless."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from whshr.assets import AssetLocator
from whshr.battle_scene import BATTLE_TICK_SECONDS, BattleScene
from whshr.cache import AssetCache
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.controlpanel import control_panel
from whshr.glue_content import GlueContent
from whshr.glue_runtime import (
    ActivityResult, CloseWindow, Diagnostic, GlueInput, GlueRuntime, PlayMusic, StartBattle,
)
from whshr.glue_scene import GlueScene
from whshr.result_scene import ResultScene
from whshr.rules import Side
from whshr.scenes import SceneAssets, SceneMachine
from tests.test_battle_scene import SCRIPT

RESOURCES = {
    "AMBUSH": "[WINDOW]\n[END]",
    # Mission script shaped like a chapter mission with a standard ambush sub-flow.
    "MISSION": ("[RUN]\n[START]\nsettextalign:left\nenablebook:0=26\naddmidiobject:looking\n"
                "setbattlescript:bf001\ngosub:ENCOUNTER\nsetgluestatusmask:2\nsetgluestatus:\nendgame:\n[END]"),
    "ENCOUNTER": ("[RUN]\n[START]\nopenwindow:res=AMBUSH\nsettextalign:left\nsetgluestatusmask:80\nclrgluestatus:\n"
                  "waitforresume:\nclosewindow:res=AMBUSH\nreturn:\n[END]"),
    "NOBATTLE": "[RUN]\n[START]\nopenwindow:res=AMBUSH\nwaitforresume:\nclosewindow:res=AMBUSH\nendgame:\n[END]",
    "ATTACKMASK": ("[RUN]\n[START]\nsetbattlescript:bf001\nsetgluestatusmask:80\nclrgluestatus:\n"
                   "waitforresume:\nendgame:\n[END]"),
}


class ControlPanelActionTests(unittest.TestCase):
    def test_given_the_encounter_panels_then_their_buttons_have_the_documented_actions(self):
        self.assertEqual(control_panel(3).actions, ("encounter_battle",))  # Defend
        self.assertEqual(control_panel(4).actions, ("encounter_evade", "encounter_attack_status"))
        self.assertEqual(control_panel(7).actions[0], "encounter_evade")  # Decline
        self.assertEqual(control_panel(8).actions, ("encounter_battle",))  # Attack!

    def test_given_the_still_unknown_panels_then_their_buttons_stay_disabled(self):
        for value in (5, 6, 9, 10):
            self.assertEqual(control_panel(value).actions, ())


class EncounterRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.content = GlueContent.from_data(resources=RESOURCES)

    def _parked(self, program):
        runtime = GlueRuntime(self.content)
        runtime.start(program)
        self.assertEqual(runtime.state.wait_reason, "panel-resume")
        return runtime

    def test_given_an_encounter_window_when_defend_is_pressed_then_a_battle_starts_without_debrief(self):
        runtime = self._parked("ATTACKMASK")

        effects = runtime.handle(GlueInput("panel-action", "encounter_battle"))

        battle = [effect for effect in effects if isinstance(effect, StartBattle)]
        self.assertEqual(len(battle), 1)
        self.assertEqual((battle[0].battle, battle[0].with_debrief, battle[0].encounter), ("BF001", False, True))
        self.assertEqual(runtime.state.status_bits, 0)  # Defend never touches the status
        self.assertEqual(len(runtime.state.context_stack), 1)

    def test_given_attack_on_panel_four_then_the_status_bits_are_set_under_the_mask_before_the_battle(self):
        runtime = self._parked("ATTACKMASK")

        effects = runtime.handle(GlueInput("panel-action", "encounter_attack_status"))

        self.assertEqual(runtime.state.status_bits, 0x80)
        self.assertTrue(any(isinstance(effect, StartBattle) for effect in effects))

    def test_given_evade_then_the_script_resumes_and_the_status_is_untouched(self):
        runtime = self._parked("ATTACKMASK")

        effects = runtime.handle(GlueInput("panel-action", "encounter_evade"))

        self.assertEqual(runtime.state.status_bits, 0)
        self.assertFalse(any(isinstance(effect, StartBattle) for effect in effects))
        self.assertIsNone(runtime.state.current)  # ran to its endgame
        self.assertEqual(runtime.state.context_stack, [])

    def test_given_no_battle_name_when_an_encounter_starts_then_it_is_reported_and_the_script_goes_on(self):
        runtime = self._parked("NOBATTLE")

        effects = runtime.handle(GlueInput("panel-action", "encounter_battle"))

        self.assertTrue(any(isinstance(effect, Diagnostic) for effect in effects))
        self.assertFalse(any(isinstance(effect, StartBattle) for effect in effects))
        self.assertIsNone(runtime.state.wait_reason)

    def test_given_the_encounter_battle_ends_then_the_parked_script_resumes_after_its_wait(self):
        runtime = GlueRuntime(self.content)
        runtime.start("MISSION")
        self.assertEqual(runtime.state.wait_reason, "panel-resume")
        effects = runtime.handle(GlueInput("panel-action", "encounter_attack_status"))
        request = next(effect for effect in effects if isinstance(effect, StartBattle))
        self.assertEqual(runtime.state.windows, [])  # hidden while the battle runs

        effects = runtime.resume(ActivityResult(request.request_id, "battle"))

        self.assertIn(CloseWindow("AMBUSH"), effects)  # the script closed its window after the wait
        self.assertEqual(runtime.state.status_bits, 0x82)  # mission's own later step continued
        self.assertIsNone(runtime.state.current)
        self.assertEqual(runtime.state.context_stack, [])
        self.assertFalse(runtime.state.caravan_after_battle)

    def test_given_a_pending_dialogue_when_a_button_is_pressed_then_the_text_drains_and_the_action_runs(self):
        content = GlueContent.from_data(resources={
            **RESOURCES, "TALKING": ("[RUN]\n[START]\nsetbattlescript:bf001\nplaytext:res=1\n"
                                     "waitforresume:\nendgame:\n[END]")})
        runtime = GlueRuntime(content)
        runtime.start("TALKING")
        self.assertEqual(runtime.state.pending.kind, "dialogue")

        effects = runtime.handle(GlueInput("panel-action", "encounter_battle"))

        self.assertTrue(any(isinstance(effect, StartBattle) for effect in effects))

    def test_given_a_running_battle_when_a_button_is_pressed_again_then_nothing_happens(self):
        runtime = self._parked("ATTACKMASK")
        runtime.handle(GlueInput("panel-action", "encounter_battle"))

        self.assertEqual(runtime.handle(GlueInput("panel-action", "encounter_battle")), ())
        self.assertEqual(len(runtime.state.context_stack), 1)

    def test_given_the_selected_mission_names_a_battle_then_it_is_the_fallback_encounter_battle(self):
        content = GlueContent.from_data(resources={
            **RESOURCES,
            "MW": "[WINDOW]\n[MISSION]\nset:res=601\nsetbattlescript:bf007\n[END]\n[END]",
        })
        runtime = GlueRuntime(content)
        runtime.start("NOBATTLE")
        runtime.state.selected_mission = content.window("MW").records[0].mission_ref

        effects = runtime.handle(GlueInput("panel-action", "encounter_battle"))

        self.assertEqual(next(e for e in effects if isinstance(e, StartBattle)).battle, "BF007")

    def test_given_the_bookkeeping_commands_then_they_are_stored_and_not_reported(self):
        campaign = CampaignState({"flow_scripts": {"MISSION": ({"action": "add_window", "window": "W"},)},
                                  "mission_windows": {"W": ()}}, flow="MISSION")
        runtime = GlueRuntime(self.content, campaign)

        effects = runtime.start("MISSION")

        self.assertEqual(runtime.state.battle_script, "BF001")
        self.assertEqual(runtime.state.text_align, 0)
        self.assertEqual(campaign.book_flags, {0: {26}})
        self.assertIn(PlayMusic("looking"), effects)
        self.assertFalse([effect for effect in effects if isinstance(effect, Diagnostic)])

    def test_given_settextalign_values_then_only_center_and_right_change_the_alignment(self):
        content = GlueContent.from_data(resources={
            "A": "[RUN]\n[START]\nsettextalign:center\nwaitforresume:\n[END]",
            "B": "[RUN]\n[START]\nsettextalign:right\nwaitforresume:\n[END]",
            "C": "[RUN]\n[START]\nsettextalign:sideways\nwaitforresume:\n[END]"})
        aligns = []
        for program in "ABC":
            runtime = GlueRuntime(content)
            runtime.start(program)
            aligns.append(runtime.state.text_align)
        self.assertEqual(aligns, [1, 2, 0])


class EncounterSceneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.content = GlueContent.from_data(resources=RESOURCES)
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(),
                                   {"battle-script": lambda _, path: SimpleNamespace(script=SCRIPT)})
        self.context.glue = self.content
        self.scene = GlueScene("MISSION")
        self.machine = SceneMachine(self.scene, self.context)

    def _press(self, action):
        self.machine.handle(GlueInput("panel-action", action))
        self.machine.update(0)  # the host picks up the battle request

    def test_given_a_played_encounter_when_the_result_is_dismissed_then_the_script_resumes(self):
        self._press("encounter_battle")
        self.assertIsInstance(self.machine.active, BattleScene)
        for regiment in self.machine.active.battle.regiments.values():
            if regiment.side != Side.PLAYER:
                regiment.models = 0
        self.machine.update(BATTLE_TICK_SECONDS)
        self.assertIsInstance(self.machine.active, ResultScene)

        self.machine.handle("continue")
        self.machine.handle("done")  # the debrief screen closes

        self.assertIs(self.machine.active, self.scene)
        self.assertIsNone(self.scene.runtime.state.pending)
        self.assertIsNone(self.scene.runtime.state.current)  # AMBUSH closed, MISSION ran on to its end
        self.assertEqual(self.scene.runtime.state.status_bits, 0x2)

    def test_given_a_no_battle_run_when_the_encounter_starts_then_the_script_resumes_without_a_result_screen(self):
        self.context.no_battle = True
        self._press("encounter_battle")

        self.machine.update(BATTLE_TICK_SECONDS)

        self.assertIs(self.machine.active, self.scene)
        self.assertIsNone(self.scene.runtime.state.current)
        self.assertEqual(self.scene.runtime.state.context_stack, [])
