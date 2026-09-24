"""A mission's debrief request resolves without a screen and the flow carries on (issue #124), plus the
result-dependent commands `testobjective`, `bonus*` and `addunit` (notes/activity_results.md sections 2.3 and 5,
notes/debrief_evaluation.md section 5, notes/campaign.md sections 2.5 and 3.2)."""
import json
import unittest

from tests.test_post_mission_caravan import RESOURCES as BASE, PostMissionCaravanTests
from whshr.campaign_log import CampaignLogger
from whshr.campaign_state import CampaignState
from whshr.glue_content import GlueContent
from whshr.glue_runtime import Diagnostic, GlueInput, GlueRuntime, StartDebrief
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneMachine

RESOURCES = {
    **BASE,
    "MSCRIPT": "[RUN]\n[START]\nautosave:\nencounterplaygame:bf001\ndebriefwithsummary:7\ngocaravan:select\n[END]",
    "DEBRIEFONLY": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\ndebrief:2\nsetgluestatusmask:1\nsetgluestatus:\n[END]",
    "STALE": ("[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\nsetcurwindow:res=AFTERWINDOW\nplaytext:res=1\n"
              "waitforrelease:\nclosewindow:res=AFTERWINDOW\nwaitforrelease:\n[END]"),
    "BONUS": ("[RUN]\n[START]\nbonusinit:\nbonusadd:4,V\niftruebonusadd:2,V\niffalsebonusadd:1,V\n"
              "bonussubtract:3,V\nsetgluestatusmask:1\ntestobjective:E\niffalsebonusadd:1,V\n"
              "iftruebonusadd:1,V\nendgame:\n[END]"),
    "UNITS": "[RUN]\n[START]\naddunit:5 ; Carroburg Greatswords\naddunit:9\nendgame:\n[END]",
    "TESTS": ("[RUN]\n[START]\nsetgluestatusmask:1\ntestobjective:E\nendgame:\n[END]"),
    "MISSIONTEST": "[RUN]\n[START]\nsetgluestatusmask:1\nsetgluestatus:\ntestmission:\nendgame:\n[END]",
}


def _campaign():
    return CampaignState({"flow_scripts": {"FLOW": ({"action": "add_window", "window": "M"},)},
                          "mission_windows": {"M": ()}}, flow="FLOW")


class DebriefFlowTests(PostMissionCaravanTests):
    # the inherited scenarios belong to test_post_mission_caravan; only its fixtures are reused here
    test_given_a_mission_that_ends_with_a_caravan_request_when_it_finishes_then_the_caravan_is_shown = None
    test_given_the_after_mission_caravan_when_the_select_hotspot_is_released_then_the_map_shows_the_next_step = None
    test_given_the_caravan_when_an_unimplemented_hotspot_is_released_then_it_stays_open = None
    test_given_a_recruit_caravan_when_its_exit_is_released_then_the_script_resumes_after_it = None

    def setUp(self):
        super().setUp()
        self.content = GlueContent.from_data(resources=RESOURCES)
        self.context.glue = self.content
        self.log = CampaignLogger(self.root / "log.jsonl")
        self.context.campaign_log = self.log
        self.addCleanup(self.log.close)

    def _rows(self, kind):
        self.log.close()
        rows = [json.loads(line) for line in (self.root / "log.jsonl").read_text().splitlines()]
        return [row for row in rows if row["type"] == kind]

    def test_given_no_battle_mode_when_a_mission_ends_with_a_debrief_then_the_caravan_follows_and_the_map_advances(self):
        machine, map_scene, campaign = self._play(("missionawindow.0",), False)

        self.assertEqual(self._names(machine.active), ["CARAVANAFTERMISSION"])
        machine.handle(GlueInput("hotspot-release", "UnwindMission"))

        self.assertIs(machine.active, map_scene)
        self.assertEqual(campaign.completed, {601})
        self.assertEqual(self._names(map_scene)[-1], "MISSIONBWINDOW")
        rows = self._rows("debrief")
        self.assertEqual([(row["mode"], row["summary"]) for row in rows], [(7, True)])

    def test_given_a_played_battle_when_the_result_is_dismissed_then_the_debrief_resolves_and_the_flow_goes_on(self):
        from whshr.battle_scene import BattleScene
        from whshr.result_scene import ResultScene

        self.context.no_battle = False
        campaign = self._campaign()
        map_scene = GlueScene("FLOW", campaign)
        machine = SceneMachine(map_scene, self.context)
        self._open(machine, "missionawindow.0", False)
        for _ in range(40):
            if isinstance(machine.active, BattleScene):
                break
            machine.update(0.1)
        self.assertIsInstance(machine.active, BattleScene)
        machine.active.battle.resolve_no_battle()
        machine.update(0.1)
        self.assertIsInstance(machine.active, ResultScene)

        machine.handle("continue")
        machine.update(0.1)

        self.assertEqual(self._names(machine.active), ["CARAVANAFTERMISSION"])
        self.assertEqual(len(self._rows("debrief")), 1)

    def test_given_a_debrief_request_when_it_resolves_then_the_skipped_payment_is_logged_not_applied(self):
        campaign = self._campaign()
        campaign.pending_join.add(5)
        machine = SceneMachine(GlueScene("DEBRIEFONLY", campaign), self.context)

        machine.update(0.1)

        self.assertEqual(campaign.coffers, 500)
        (row,) = self._rows("debrief")
        self.assertEqual((row["mode"], row["debrief_index"], row["summary"], row["applied"]), (4, 1, False, []))
        self.assertTrue(any("final payment" in text for text in row["skipped"]))
        self.assertTrue(any("[5]" in text for text in row["skipped"]))

    def test_given_a_debrief_request_when_it_resolves_then_the_script_resumes_after_it(self):
        machine = SceneMachine(GlueScene("DEBRIEFONLY", _campaign()), self.context)

        machine.update(0.1)

        self.assertEqual(machine.active.runtime.state.status_bits, 1)
        self.assertIsNone(machine.active.runtime.state.pending)


class ResultCommandTests(unittest.TestCase):
    def setUp(self):
        self.content = GlueContent.from_data(resources=RESOURCES)

    def _run(self, program, campaign):
        runtime = GlueRuntime(self.content, campaign)
        return runtime, runtime.start(program)

    def test_given_an_objective_met_when_testobjective_runs_then_the_status_is_set(self):
        campaign = _campaign()
        campaign.objective_results["E"] = (True, (1, 0, 0, 0))

        runtime, effects = self._run("TESTS", campaign)

        self.assertEqual(runtime.state.status_bits, 1)
        self.assertFalse([effect for effect in effects if isinstance(effect, Diagnostic)])

    def test_given_an_objective_not_met_when_testobjective_runs_then_the_status_is_cleared(self):
        campaign = _campaign()
        campaign.objective_results["E"] = (False, (0, 0, 0, 0))

        runtime, _ = self._run("TESTS", campaign)

        self.assertEqual(runtime.state.status_bits, 0)

    def test_given_no_battle_result_when_testobjective_runs_then_it_is_false_with_a_diagnostic(self):
        runtime, effects = self._run("TESTS", _campaign())

        self.assertEqual(runtime.state.status_bits, 0)
        self.assertTrue(any(isinstance(effect, Diagnostic) and "objective" in effect.message for effect in effects))

    def test_given_no_battle_result_when_testmission_runs_then_it_is_lost_and_autosaves(self):
        campaign = _campaign()

        runtime, effects = self._run("MISSIONTEST", campaign)

        self.assertEqual(runtime.state.status_bits, 0)
        self.assertIsNotNone(campaign.autosave_state)
        self.assertTrue(any(isinstance(effect, Diagnostic) for effect in effects))

    def test_given_objective_values_when_the_bonus_commands_run_then_the_counter_follows_their_branches(self):
        campaign = _campaign()
        campaign.bonus_counter = 99
        campaign.objective_results["V"] = (True, (0, 100, 0, 7))  # v1..v4; only v1, v2 and v4 used below
        # bonusinit -> 0; +v4 (7); status is false at start (iftrue skipped, iffalse adds v1 = 0);
        # subtract v3 (0); testobjective E is absent -> false: iffalse adds v1 (0), iftrue skipped.
        runtime, _ = self._run("BONUS", campaign)

        self.assertEqual(campaign.bonus_counter, 7)

    def test_given_a_true_status_when_iftruebonusadd_runs_then_the_value_is_added_and_iffalse_is_skipped(self):
        campaign = _campaign()
        campaign.objective_results["V"] = (True, (10, 20, 30, 40))
        content = GlueContent.from_data(resources={
            "P": ("[RUN]\n[START]\nbonusinit:\nsetgluestatusmask:1\nsetgluestatus:\niftruebonusadd:2,V\n"
                  "iffalsebonusadd:1,V\nbonussubtract:3,V\nclrgluestatus:\niffalsebonusadd:4,V\n"
                  "iftruebonusadd:1,V\nendgame:\n[END]")})

        GlueRuntime(content, campaign).start("P")

        self.assertEqual(campaign.bonus_counter, 20 - 30 + 40)

    def test_given_no_objective_result_when_bonusadd_runs_then_the_counter_is_unchanged_with_a_diagnostic(self):
        content = GlueContent.from_data(resources={"P": "[RUN]\n[START]\nbonusadd:4,V\nendgame:\n[END]"})
        campaign = _campaign()
        campaign.bonus_counter = 3

        effects = GlueRuntime(content, campaign).start("P")

        self.assertEqual(campaign.bonus_counter, 3)
        self.assertTrue(any(isinstance(effect, Diagnostic) for effect in effects))

    def test_given_addunit_lines_when_they_run_then_the_regiments_are_flagged_pending_join(self):
        campaign = _campaign()

        _, effects = self._run("UNITS", campaign)

        self.assertEqual(campaign.pending_join, {5, 9})
        self.assertFalse([effect for effect in effects if isinstance(effect, Diagnostic)])

    def test_given_a_closed_dialogue_window_when_the_script_goes_on_then_its_text_is_cleared(self):
        content = GlueContent.from_data(resources={
            "AFTERWINDOW": "[WINDOW]\n[END]", "STALE": RESOURCES["STALE"]}, strings={"BRTXT": {1: "Ambush!"}})
        runtime = GlueRuntime(content, _campaign())
        runtime.start("STALE")
        runtime.tick(5000)
        self.assertEqual(runtime.state.dialogue_text, "Ambush!")

        runtime.handle(GlueInput("mission-release"))

        self.assertEqual(runtime.state.dialogue_text, "")
        self.assertEqual(runtime.state.dialogue_lines, ())

    def test_given_a_parked_request_with_no_window_shown_when_the_dialogue_is_drawn_then_no_text_remains(self):
        from whshr.frontend.glue_view import _dialogue_state

        content = GlueContent.from_data(resources={
            "AFTERWINDOW": "[WINDOW]\n[END]",
            "P": ("[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\nsetcurwindow:res=AFTERWINDOW\nplaytext:res=1\n"
                  "debrief:1\n[END]")}, strings={"BRTXT": {1: "Ambush!"}})
        runtime = GlueRuntime(content, _campaign())
        runtime.start("P")
        runtime.tick(5000)

        self.assertIsInstance(runtime.state.pending.kind, str)  # the debrief request parked the windows

        self.assertEqual(_dialogue_state(runtime.state), ("", ()))


if __name__ == "__main__":
    unittest.main()
