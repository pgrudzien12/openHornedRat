"""Initial campaign scenes backed by the original-install asset catalog."""

from .assets import AssetId
from .battle_scene import BattleScene, FIRST_BATTLE
from .scenes import Quit, Scene, SceneManifest, Transition
from .si import load_si, walk_objects

INTRO_CUTSCENE = AssetId("vanilla", "cutscene", "a1")
INTRO_MEDIA = AssetId("vanilla", "cutscene", "a1-media")
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


def briefing_asset_for(battle_id):
    """Return the logical asset ID of the campaign briefing text for one battle asset ID."""
    return AssetId("vanilla", "briefing", battle_id.name)


class IntroScene(Scene):
    """Play the verified A1 game-intro timeline, then proceed to the main menu."""

    manifest = SceneManifest(immediate=(INTRO_CUTSCENE, INTRO_MEDIA), prefetch=(MAIN_MENU,))

    def __init__(self, successor=None):
        self.successor = successor or MainMenuScene()
        self.elapsed_seconds = 0.0
        self.duration_seconds = None
        self.container = None
        self.media = None

    def enter(self, context):
        self.container = context.load(INTRO_CUTSCENE)
        self.duration_seconds = omni_duration_seconds(self.container)
        self.media = context.load(INTRO_MEDIA)

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


class MainMenuScene(Scene):
    """The main menu: New Campaign enters the first mission briefing; Quit ends the application."""

    manifest = SceneManifest(immediate=(MAIN_MENU,))

    def __init__(self, briefing=None):
        self.briefing = briefing or BriefingScene(FIRST_BATTLE)

    def handle(self, event, context):
        if event == "new_campaign":
            return Transition(self.briefing, "new campaign started")
        if event == "quit":
            return Quit("player quit from the main menu")
        return None


class BriefingScene(Scene):
    """Show one battle's campaign briefing text; Start Battle enters the battle itself."""

    def __init__(self, battle):
        self.battle_id = battle
        self.briefing_id = briefing_asset_for(battle)
        self.manifest = SceneManifest(immediate=(self.briefing_id,), prefetch=(battle,))
        self.briefing = None

    def enter(self, context):
        self.briefing = context.load(self.briefing_id)

    def handle(self, event, context):
        if event == "start_battle":
            return Transition(BattleScene(self.battle_id), "briefing accepted")
        return None


def default_scene_loaders():
    """Return loaders currently needed by the implemented campaign scenes."""
    return {"omni-si": lambda _record, path: load_si(path)}
