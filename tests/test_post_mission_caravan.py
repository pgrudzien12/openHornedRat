"""A mission script's caravan request shows the requested caravan window; the exit hotspot then
resumes or unwinds the parked script (notes/activity_results.md section 6.2, issue #120)."""
import json
import unittest

from tests.test_direct_mission_route import RESOURCES as BASE, DirectMissionRouteTests
from whshr.campaign_log import CampaignLogger
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneMachine

CARAVAN = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\nset:palindex=3\n[END]\n" \
          "[HOTSPOT]\nset:x=1\nset:y=1\nset:vx=9\nset:vy=9\nscript:pop.wnd\nres:%s\n[END]"
RESOURCES = {
    **BASE,
    "CARAVANAFTERMISSION": CARAVAN % "UnwindMission",
    "CARAVANAFTERENCOUNTER": CARAVAN % "UnwindMission",
    "CARAVANRECRUITANDRESUME": CARAVAN % "PopAndResume",
    "INFOCARAVANABC": CARAVAN % "UnwindMission",
    "AFTERWINDOW": "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=1\nset:vy=1\n[END]",
    "RECRUITSCRIPT": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\ngocaravan:recruit\nopenwindow:res=AFTERWINDOW\n[END]",
    "RESUMESCRIPT": "[RUN]\n[START]\ngocaravan:resume\nopenwindow:res=AFTERWINDOW\n[END]",
    "INFOSCRIPT": "[RUN]\n[START]\ngocaravan:infoABC\n[END]",
    "UNKNOWNSCRIPT": "[RUN]\n[START]\ngocaravan:nonsense\nopenwindow:res=AFTERWINDOW\n[END]",
}


class PostMissionCaravanTests(DirectMissionRouteTests):
    # the inherited scenarios belong to test_direct_mission_route; only the fixtures are reused here
    test_given_either_route_when_a_mission_ends_then_the_campaign_state_is_the_same = None
    test_given_the_direct_route_when_the_mission_ends_then_the_map_shows_the_next_window = None
    test_given_a_glue_scene_with_nothing_to_show_when_it_is_active_then_the_map_is_shown_and_logged = None

    def setUp(self):
        super().setUp()
        self.content = GlueContent.from_data(resources=RESOURCES)
        self.context.glue = self.content

    def _names(self, scene):
        return [window.name for window in scene.runtime.state.windows]

    def test_given_a_mission_that_ends_with_a_caravan_request_when_it_finishes_then_the_caravan_is_shown(self):
        for direct in (False, True):
            with self.subTest(direct=direct):
                machine, map_scene, campaign = self._play(("missionawindow.0",), direct)

                self.assertIsNot(machine.active, map_scene)
                self.assertEqual(self._names(machine.active), ["CARAVANAFTERMISSION"])
                self.assertEqual(campaign.completed, set())

    def test_given_the_after_mission_caravan_when_the_select_hotspot_is_released_then_the_map_shows_the_next_step(self):
        for direct in (False, True):
            with self.subTest(direct=direct):
                machine, map_scene, campaign = self._play(("missionawindow.0",), direct)

                machine.handle(GlueInput("hotspot-release", "UnwindMission"))

                self.assertIs(machine.active, map_scene)
                self.assertEqual(campaign.completed, {601})
                self.assertEqual(self._names(map_scene)[-1], "MISSIONBWINDOW")

    def test_given_the_caravan_when_an_unimplemented_hotspot_is_released_then_it_stays_open(self):
        machine, map_scene, campaign = self._play(("missionawindow.0",), False)

        machine.handle(GlueInput("hotspot-release", "ArmyBook"))

        self.assertEqual(self._names(machine.active), ["CARAVANAFTERMISSION"])
        self.assertEqual(campaign.completed, set())

    def test_given_a_recruit_caravan_when_its_exit_is_released_then_the_script_resumes_after_it(self):
        machine = SceneMachine(GlueScene("RECRUITSCRIPT"), self.context)
        scene = machine.active

        self.assertEqual(self._names(scene), ["CARAVANRECRUITANDRESUME"])
        machine.handle(GlueInput("hotspot-release", "PopAndResume"))

        self.assertIs(machine.active, scene)
        self.assertEqual(self._names(scene), ["AFTERWINDOW", "AFTERWINDOW"])
        self.assertIsNone(scene.runtime.state.pending)
        self.assertIsNone(scene.runtime.state.current)

    def test_given_an_info_caravan_when_requested_then_its_window_is_taken_from_the_letters(self):
        machine = SceneMachine(GlueScene("INFOSCRIPT"), self.context)

        self.assertEqual(self._names(machine.active), ["INFOCARAVANABC"])

    def test_given_an_unknown_caravan_name_when_requested_then_the_script_goes_on_at_once(self):
        machine = SceneMachine(GlueScene("UNKNOWNSCRIPT"), self.context)

        self.assertEqual(self._names(machine.active), ["AFTERWINDOW"])
        self.assertIsNone(machine.active.runtime.state.pending)

    def test_given_a_resume_caravan_when_its_exit_is_released_then_the_parked_context_is_restored(self):
        machine = SceneMachine(GlueScene("RESUMESCRIPT"), self.context)

        self.assertEqual(self._names(machine.active), ["CARAVANAFTERENCOUNTER"])
        self.assertEqual(len(machine.active.runtime.state.context_stack), 1)
        machine.handle(GlueInput("hotspot-release", "UnwindMission"))

        self.assertEqual(machine.active.runtime.state.context_stack, [])
        self.assertIsNone(machine.active.runtime.state.pending)

    def test_given_a_campaign_log_when_the_caravan_is_shown_then_its_request_is_logged_once(self):
        log = CampaignLogger(self.root / "log.jsonl")
        self.context.campaign_log = log
        machine, map_scene, campaign = self._play(("missionawindow.0",), False)
        machine.handle(GlueInput("hotspot-release", "UnwindMission"))
        log.close()

        rows = [json.loads(line) for line in (self.root / "log.jsonl").read_text().splitlines()]
        requests = [row for row in rows if row["type"] == "activity_request" and row.get("kind") == "caravan"]
        self.assertEqual([row["mode"] for row in requests], ["select"])
        resolved = [row for row in rows if row["type"] == "wait_resolved" and row.get("kind") == "caravan"]
        self.assertEqual(len(resolved), 1)

    def test_given_the_map_after_a_caravan_when_its_caravan_button_is_pressed_then_that_caravan_returns(self):
        for mode, window in (("select", "CARAVANAFTERMISSION"), ("infoABC", "INFOCARAVANABC")):
            with self.subTest(mode=mode):
                script = RESOURCES["MSCRIPT"].replace("gocaravan:select", f"gocaravan:{mode}")
                self.context.glue = GlueContent.from_data(resources={**RESOURCES, "MSCRIPT": script})
                machine, map_scene, campaign = self._play(("missionawindow.0",), False)
                caravan = machine.active
                machine.handle(GlueInput("hotspot-release", "UnwindMission"))
                self.assertIs(machine.active, map_scene)

                machine.handle(GlueInput("panel-action", "return_to_caravan"))

                self.assertIs(machine.active, caravan)
                self.assertEqual(self._names(caravan), [window])
                self.assertEqual(len(caravan.runtime.state.context_stack), 1)
                self.assertEqual(campaign.completed, {601})

    def test_given_repeated_round_trips_when_the_caravan_is_left_again_then_nothing_leaks_or_completes_twice(self):
        machine, map_scene, campaign = self._play(("missionawindow.0",), False)
        caravan = machine.active
        for _ in range(3):
            machine.handle(GlueInput("hotspot-release", "UnwindMission"))
            self.assertIs(machine.active, map_scene)
            self.assertEqual(self._names(map_scene)[-1], "MISSIONBWINDOW")
            machine.handle(GlueInput("panel-action", "return_to_caravan"))
            self.assertIs(machine.active, caravan)
            self.assertEqual(len(caravan.runtime.state.context_stack), 1)
        machine.handle(GlueInput("hotspot-release", "UnwindMission"))

        self.assertEqual(caravan.runtime.state.context_stack, [])
        self.assertEqual(campaign.completed, {601})
        self.assertEqual(len(map_scene.runtime.state.context_stack), 0)


if __name__ == "__main__":
    unittest.main()
