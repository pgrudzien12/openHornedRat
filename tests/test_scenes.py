import unittest

from whshr.assets import AssetId
from whshr.scenes import Scene, SceneMachine, SceneManifest, Transition


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


if __name__ == "__main__":
    unittest.main()
