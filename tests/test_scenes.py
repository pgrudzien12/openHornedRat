import unittest

from whshr.assets import AssetId
from whshr.scenes import Quit, Scene, SceneMachine, SceneManifest, Transition


class Intro(Scene):
    manifest = SceneManifest(
        immediate=(AssetId("vanilla", "cutscene", "intro"),),
        prefetch=(AssetId("vanilla", "ui", "main-menu"),),
    )

    def enter(self, context):
        context.append("intro entered")

    def exit(self, context):
        context.append("intro exited")

    def handle(self, event, context):
        if event == "skip":
            return Transition(Menu(), "intro skipped")
        return None


class Menu(Scene):
    manifest = SceneManifest(immediate=(AssetId("vanilla", "ui", "main-menu"),))

    def enter(self, context):
        context.append("menu entered")


class TimedScene(Scene):
    def __init__(self):
        self.remaining = 1.0

    def update(self, seconds, context):
        super().update(seconds, context)
        self.remaining -= seconds
        if self.remaining <= 0:
            return Transition(Menu(), "timer elapsed")
        return None


class QuittableMenu(Scene):
    def __init__(self):
        self.handled_after_quit = False

    def handle(self, event, context):
        if event == "quit":
            return Quit("player quit")
        self.handled_after_quit = True
        return None


class SceneMachineTests(unittest.TestCase):
    def test_given_intro_when_player_skips_then_menu_becomes_active_after_intro_exits(self):
        events = []
        machine = SceneMachine(Intro(), events)

        machine.handle("skip")

        self.assertIsInstance(machine.active, Menu)
        self.assertEqual(events, ["intro entered", "intro exited", "menu entered"])
        self.assertEqual(machine.history[0].reason, "intro skipped")

    def test_given_timed_scene_when_time_elapses_then_its_successor_becomes_active(self):
        machine = SceneMachine(TimedScene(), [])

        machine.update(0.4)
        self.assertIsInstance(machine.active, TimedScene)
        machine.update(0.6)

        self.assertIsInstance(machine.active, Menu)
        self.assertEqual(machine.history[0].reason, "timer elapsed")

    def test_given_overlapping_manifest_when_constructed_then_ambiguous_loading_is_rejected(self):
        asset = AssetId("vanilla", "palette", "standard")

        with self.assertRaisesRegex(ValueError, "immediate and prefetched"):
            SceneManifest(immediate=(asset,), prefetch=(asset,))

    def test_given_negative_scene_time_when_updated_then_the_invalid_transition_is_rejected(self):
        machine = SceneMachine(TimedScene(), [])

        with self.assertRaisesRegex(ValueError, "must not be negative"):
            machine.update(-0.1)

    def test_given_a_scene_when_it_requests_quit_then_the_machine_records_it_without_switching_scenes(self):
        scene = QuittableMenu()
        machine = SceneMachine(scene, [])

        machine.handle("quit")

        self.assertIs(machine.active, scene)
        self.assertEqual(machine.quit.reason, "player quit")
        self.assertEqual(machine.history, [])

    def test_given_a_machine_that_has_quit_when_given_more_events_then_the_scene_no_longer_receives_them(self):
        scene = QuittableMenu()
        machine = SceneMachine(scene, [])
        machine.handle("quit")

        machine.handle("anything")
        machine.update(0.1)

        self.assertFalse(scene.handled_after_quit)


if __name__ == "__main__":
    unittest.main()
