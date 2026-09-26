"""``gomissionselect``: a run that ends with the flag raised performs the mission release step instead
of falling back to a blank map (notes/glue_interpreter.md §9.3; player report: stuck at Nuln with no
mission after `SZMission5`'s `gocaravan:infoena` / `gomissionselect:` ending)."""
import unittest

from tests.test_direct_mission_route import RESOURCES as BASE, DirectMissionRouteTests
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput, GlueRuntime, MissionSelectRequested
from whshr.glue_scene import GlueScene

CARAVAN = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n[END]\n" \
          "[HOTSPOT]\nset:x=1\nset:y=1\nset:vx=9\nset:vy=9\nscript:pop.wnd\nres:%s\n[END]"
RESOURCES = {
    **BASE,
    "INFOCARAVANENA": CARAVAN % "PopAndResume",
    # Same shape as SZMission5's ending: an info caravan, then gomissionselect as the very last statement.
    "MSCRIPT": "[RUN]\n[START]\nautosave:\nencounterplaygamewithdebrief:bf001\ngocaravan:infoena\ngomissionselect:\n[END]",
}


class MissionSelectFlagTests(unittest.TestCase):
    """Unit-level behaviour of the flag itself, independent of the scene machine."""

    def _runtime(self, program="[RUN]\n[START]\ngomissionselect:\n[END]"):
        content = GlueContent.from_data(resources={"P": program})
        runtime = GlueRuntime(content)
        return runtime, runtime.start("P")

    def test_given_gomissionselect_as_the_last_statement_then_the_run_ending_reports_it(self):
        runtime, effects = self._runtime()

        self.assertIn(MissionSelectRequested(), effects)
        self.assertFalse(runtime.state.gomissionselect_pending)  # consumed, not left set for a later run

    def test_given_no_gomissionselect_then_a_run_ending_reports_nothing(self):
        _, effects = self._runtime("[RUN]\n[START]\n[END]")

        self.assertNotIn(MissionSelectRequested(), effects)

    def test_given_gomissionselect_followed_by_a_wait_then_nothing_fires_until_the_run_truly_ends(self):
        runtime, effects = self._runtime("[RUN]\n[START]\ngomissionselect:\nwaitforresume:\n[END]")

        self.assertNotIn(MissionSelectRequested(), effects)
        self.assertTrue(runtime.state.gomissionselect_pending)
        effects = runtime.handle(GlueInput("panel-resume", None))
        self.assertIn(MissionSelectRequested(), effects)


class MissionSelectSceneTests(DirectMissionRouteTests):
    # the inherited scenarios belong to test_direct_mission_route; only the fixtures are reused here
    test_given_either_route_when_a_mission_ends_then_the_campaign_state_is_the_same = None
    test_given_the_direct_route_when_the_mission_ends_then_the_map_shows_the_next_window = None
    test_given_a_glue_scene_with_nothing_to_show_when_it_is_active_then_the_map_is_shown_and_logged = None

    def setUp(self):
        super().setUp()
        self.content = GlueContent.from_data(resources=RESOURCES)
        self.context.glue = self.content

    def test_given_a_mission_script_ending_with_gomissionselect_then_the_map_is_shown_with_the_mission_released(self):
        machine, map_scene, campaign = self._play(("missionawindow.0",), True)
        self.assertEqual([window.name for window in machine.active.runtime.state.windows], ["INFOCARAVANENA"])

        machine.handle(GlueInput("hotspot-release", "PopAndResume"))

        self.assertIs(machine.active, map_scene)  # not a fresh fallback map (issue: stuck at Nuln)
        self.assertEqual(campaign.completed, {601})
        self.assertEqual(map_scene.runtime.state.windows[-1].name, "MISSIONBWINDOW")

    def test_given_the_briefing_route_then_gomissionselect_also_releases_the_mission(self):
        machine, _map_scene, campaign = self._play(("missionawindow.0",), False)

        machine.handle(GlueInput("hotspot-release", "PopAndResume"))

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(campaign.completed, {601})


if __name__ == "__main__":
    unittest.main()
