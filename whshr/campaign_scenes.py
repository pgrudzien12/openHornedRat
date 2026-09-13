"""Initial campaign scenes backed by the original-install asset catalog."""

from .assets import AssetId
from .scenes import Scene, SceneManifest, Transition
from .si import load_si, walk_objects

INTRO_CUTSCENE = AssetId("vanilla", "cutscene", "a1")
MAIN_MENU = AssetId("vanilla", "ui", "main-menu")


def omni_duration_seconds(container):
    """Return the final scheduled Omni object end in seconds."""
    if "root" not in container:
        raise ValueError("Omni container has no root object")
    end_ms = max(
        (object_["start"] + object_["duration"] for object_ in walk_objects(container["root"])),
        default=0,
    )
    return end_ms / 1000


class MainMenuScene(Scene):
    """The initial menu state; its visual asset loader follows in the next increment."""

    manifest = SceneManifest(immediate=(MAIN_MENU,))


class IntroScene(Scene):
    """Play the verified A1 game-intro timeline, then proceed to the main menu."""

    manifest = SceneManifest(immediate=(INTRO_CUTSCENE,), prefetch=(MAIN_MENU,))

    def __init__(self, successor=None):
        self.successor = successor or MainMenuScene()
        self.elapsed_seconds = 0.0
        self.duration_seconds = None
        self.container = None

    def enter(self, context):
        self.container = context.load(INTRO_CUTSCENE)
        self.duration_seconds = omni_duration_seconds(self.container)

    def handle(self, event, context):
        if event == "skip":
            return Transition(self.successor, "intro skipped")
        return None

    def update(self, seconds, context):
        super().update(seconds, context)
        self.elapsed_seconds += seconds
        if self.elapsed_seconds >= self.duration_seconds:
            return Transition(self.successor, "intro completed")
        return None


def default_scene_loaders():
    """Return loaders currently needed by the implemented campaign scenes."""
    return {"omni-si": lambda _record, path: load_si(path)}
