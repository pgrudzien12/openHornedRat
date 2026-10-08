"""The two caravans the panel buttons open over a running screen (notes/mission_selection.md 4.2,
notes/activity_results.md 6): the map's Caravan button opens CaravanSelectMission and panel 9's Caravan button
CaravanContinueMission; their exit hotspots PopContext and PopContextCheckResume return to the screen they were
opened over and release nothing."""

import unittest

from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene


class _Context:
    def __init__(self, content):
        self.content = content

    def glue_content(self):
        return self.content


def caravan(exit_name):
    return f"[WINDOW]\n[POSITION]\nset:palindex=3\n[END]\n[HOTSPOT]\nset:x=1\nset:y=1\nset:vx=9\nset:vy=9\nres:{exit_name}\n[END]"


RESOURCES = {
    "MAPWINDOW": "[WINDOW]\n[POSITION]\nset:palindex=2\n[END]\n[END]",
    "FLOW": "[RUN]\n[START]\nopenwindow:res=MAPWINDOW\nwaitforrelease:\nendgame:\n[END]",
    # A mission script showing its map, then going on to the next step once it is resumed.
    "MISSION": "[RUN]\n[START]\nopenwindow:res=MAPWINDOW\nwaitforresume:\nendgame:\n[END]",
    "CARAVANSELECTMISSION": caravan("PopContext"),
    "CARAVANCONTINUEMISSION": caravan("PopContextCheckResume"),
    "STARTCARAVAN": "[WINDOW]\n[END]",
    "TALKING": "[RUN]\n[START]\nopenwindow:res=MAPWINDOW\nplaytext:1\nwaitforresume:\nendgame:\n[END]",
    "SCRIPTED": "[RUN]\n[START]\ngocaravan:selectmission\nendgame:\n[END]",
}


def scene_for(program, **extra):
    scene = GlueScene(program)
    scene.enter(_Context(GlueContent.from_data(resources={**RESOURCES, **extra})))
    scene.take_effects()
    return scene


def windows(scene):
    return [window.name for window in scene.runtime.state.windows]


class MapCaravanButtonTests(unittest.TestCase):
    def test_the_caravan_button_opens_caravan_select_mission_over_the_map(self):
        scene = scene_for("FLOW")
        self.assertEqual(windows(scene), ["MAPWINDOW"])

        scene.handle(GlueInput("panel-action", "return_to_caravan"), scene.context)

        self.assertEqual(windows(scene), ["CARAVANSELECTMISSION"])
        self.assertEqual(scene.runtime.state.pending.kind, "caravan")

    def test_pop_context_returns_to_the_map_and_releases_nothing(self):
        scene = scene_for("FLOW")
        scene.handle(GlueInput("panel-action", "return_to_caravan"), scene.context)

        scene.handle(GlueInput("hotspot-release", "PopContext"), scene.context)

        self.assertEqual(windows(scene), ["MAPWINDOW"])
        self.assertIsNone(scene.runtime.state.pending)
        self.assertEqual(scene.runtime.state.wait_reason, "mission-release")  # the flow script is still parked

    def test_without_the_window_in_the_installation_the_old_behaviour_is_kept(self):
        content = {key: value for key, value in RESOURCES.items() if key != "CARAVANSELECTMISSION"}
        scene = GlueScene("FLOW")
        scene.enter(_Context(GlueContent.from_data(resources=content)))

        scene.handle(GlueInput("panel-action", "return_to_caravan"), scene.context)

        self.assertIsNone(scene.runtime.state.pending)


class MissionCaravanButtonTests(unittest.TestCase):
    def test_panel_9_caravan_button_opens_caravan_continue_mission(self):
        scene = scene_for("MISSION")

        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)

        self.assertEqual(windows(scene), ["CARAVANCONTINUEMISSION"])

    def test_pop_context_check_resume_returns_to_the_mission_screen_still_waiting(self):
        scene = scene_for("MISSION")
        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)

        scene.handle(GlueInput("hotspot-release", "PopContextCheckResume"), scene.context)

        self.assertEqual(windows(scene), ["MAPWINDOW"])
        self.assertIsNone(scene.runtime.state.pending)
        self.assertEqual(scene.runtime.state.wait_reason, "panel-resume")  # the parked script stays parked

    def test_the_caravan_button_works_while_paused_and_the_pause_stays_on_after_closing(self):
        scene = scene_for("MISSION")
        scene.handle(GlueInput("panel-action", "toggle_pause"), scene.context)
        self.assertTrue(scene.runtime.state.paused)

        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)
        scene.handle(GlueInput("hotspot-release", "PopContextCheckResume"), scene.context)

        self.assertTrue(scene.runtime.state.paused)
        self.assertEqual(windows(scene), ["MAPWINDOW"])

    def test_panel_9_pause_toggles_the_pause(self):
        from whshr.controlpanel import control_panel
        self.assertEqual(control_panel(9).actions[2], "toggle_pause")
        scene = scene_for("MISSION")

        scene.handle(GlueInput("panel-action", "toggle_pause"), scene.context)
        self.assertTrue(scene.runtime.state.paused)
        scene.handle(GlueInput("panel-action", "toggle_pause"), scene.context)
        self.assertFalse(scene.runtime.state.paused)

    def test_a_second_press_while_the_caravan_is_open_opens_nothing_more(self):
        scene = scene_for("MISSION")
        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)
        depth = len(scene.runtime.state.context_stack)

        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)

        self.assertEqual(len(scene.runtime.state.context_stack), depth)


class ReviewFindingTests(unittest.TestCase):
    def test_a_script_cannot_name_a_panel_only_caravan(self):
        from whshr.glue_runtime import EndGame
        scene = GlueScene("SCRIPTED")
        scene.enter(_Context(GlueContent.from_data(resources=RESOURCES)))
        effects = scene.take_effects()

        self.assertIsNone(scene.runtime.state.pending)  # not suspended: an unknown name resumes at once
        self.assertIn(EndGame(), effects)

    def test_a_repeated_map_caravan_press_while_it_is_open_is_a_no_op(self):
        scene = scene_for("FLOW")
        scene.handle(GlueInput("panel-action", "return_to_caravan"), scene.context)
        depth = len(scene.runtime.state.context_stack)
        scene.runtime.state.paused = True  # a pause the fall-through path would have cleared

        scene.handle(GlueInput("panel-action", "return_to_caravan"), scene.context)

        self.assertEqual(len(scene.runtime.state.context_stack), depth)
        self.assertTrue(scene.runtime.state.paused)
        self.assertEqual(windows(scene), ["CARAVANSELECTMISSION"])

    def test_panel_9_caravan_press_during_dialogue_opens_the_caravan_at_once(self):
        scene = scene_for("TALKING")
        self.assertEqual(scene.runtime.state.pending.kind, "dialogue")

        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)

        self.assertEqual(windows(scene), ["CARAVANCONTINUEMISSION"])
        self.assertIsNone(scene.runtime.state.pending.underlying)  # drained, not kept

    def test_when_paused_the_dialogue_is_kept_under_the_caravan_and_comes_back(self):
        scene = scene_for("TALKING")
        scene.handle(GlueInput("panel-action", "toggle_pause"), scene.context)
        typed = scene.runtime.state.dialogue_typed

        scene.handle(GlueInput("panel-action", "open_caravan_continue"), scene.context)
        self.assertEqual(scene.runtime.state.pending.underlying.kind, "dialogue")
        scene.handle(GlueInput("hotspot-release", "PopContextCheckResume"), scene.context)

        self.assertEqual(scene.runtime.state.pending.kind, "dialogue")
        self.assertEqual(scene.runtime.state.dialogue_typed, typed)
        self.assertTrue(scene.runtime.state.paused)
        self.assertEqual(windows(scene), ["MAPWINDOW"])


if __name__ == "__main__":
    unittest.main()
