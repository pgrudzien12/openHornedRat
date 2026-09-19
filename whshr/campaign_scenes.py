"""Initial campaign scenes backed by the original-install asset catalog."""

from .assets import AssetId
from .battle_scene import BattleScene, FIRST_BATTLE
from .campaign_state import CampaignState
from .engine import DEFAULT_SEED
from .legacy import module
from .portraits import dietrich_portrait
from .scenes import Quit, Scene, SceneManifest, Transition
from .si import load_si, walk_objects

INTRO_CUTSCENE = AssetId("vanilla", "cutscene", "a1")
INTRO_MEDIA = AssetId("vanilla", "cutscene", "a1-media")
MAIN_MENU = AssetId("vanilla", "ui", "main-menu")
ANIMATION_TEXT = AssetId("vanilla", "text", "anim")
SUBTITLE_FONT = AssetId("vanilla", "font", "subtext")
CARAVAN_FONT = AssetId("vanilla", "font", "pcsubt")
OPENING_TEXT_IDS = (1100, 1101, 1102)


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


class OpeningNarrationScene(Scene):
    """The text-only prologue shown before the A1 opening cutscene."""

    manifest = SceneManifest(immediate=(ANIMATION_TEXT, SUBTITLE_FONT),
                             prefetch=(INTRO_CUTSCENE, INTRO_MEDIA))

    def __init__(self, successor=None, log_dir=None, seed=DEFAULT_SEED):
        self.successor = successor or IntroScene(log_dir=log_dir, seed=seed)
        self.texts = None
        self.subtitle_font = None
        self.text = None

    def enter(self, context):
        self.texts = context.load(ANIMATION_TEXT)
        self.subtitle_font = context.load(SUBTITLE_FONT)
        self.text = "".join(self.texts[text_id] for text_id in OPENING_TEXT_IDS)

    def handle(self, event, context):
        if event == "continue":
            return Transition(self.successor, "opening narration dismissed")
        if event == "skip":
            return Transition(self.successor.successor, "intro skipped")
        return None


class IntroScene(Scene):
    """Play the verified A1 game-intro timeline, then proceed to the main menu."""

    manifest = SceneManifest(immediate=(INTRO_CUTSCENE, INTRO_MEDIA, ANIMATION_TEXT, SUBTITLE_FONT),
                             prefetch=(MAIN_MENU,))

    def __init__(self, successor=None, log_dir=None, seed=DEFAULT_SEED):
        self.successor = successor or MainMenuScene(log_dir=log_dir, seed=seed)
        self.elapsed_seconds = 0.0
        self.duration_seconds = None
        self.container = None
        self.media = None
        self.texts = None
        self.subtitle_font = None

    def enter(self, context):
        self.container = context.load(INTRO_CUTSCENE)
        self.duration_seconds = omni_duration_seconds(self.container)
        self.media = context.load(INTRO_MEDIA)
        self.texts = context.load(ANIMATION_TEXT)
        self.subtitle_font = context.load(SUBTITLE_FONT)

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
    """The main menu: New Campaign enters Dietrich's caravan; Quit ends the application."""

    manifest = SceneManifest(immediate=(MAIN_MENU,))

    def __init__(self, briefing=None, log_dir=None, seed=DEFAULT_SEED, campaign=None):
        self.briefing = briefing
        self.log_dir, self.seed = log_dir, seed
        self.campaign = campaign

    def handle(self, event, context):
        if event == "new_campaign":
            if self.campaign is None:
                # Tests and development callers may still inject one focused
                # briefing; a real installation derives the full initial flow.
                self.campaign = (
                    CampaignState.single_mission(self.briefing) if self.briefing is not None
                    else CampaignState.from_installation(context.locator.installation)
                )
            # StartCaravan's resource starts the first parked flow script.
            # Later ``gocaravan`` calls must supply their own continuation.
            return Transition(CaravanScene(self.campaign, continuation="open_mission_map"),
                              "new campaign started")
        if event == "quit":
            return Quit("player quit from the main menu")
        return None


class CaravanScene(Scene):
    """Campaign hub in Dietrich's caravan before the first mission is chosen.

    Coffers and mission availability are data-driven; save slots and book-page
    browsing remain presentation hooks until their persistence/views are added.
    """

    manifest = SceneManifest(immediate=(CARAVAN_FONT,))

    def __init__(self, campaign, has_message=False, mode="start", continuation=None):
        self.campaign = campaign
        self.has_message = has_message
        self.mode = mode.lower()
        # This is deliberately supplied by the glue-script runner.  A caravan
        # does not itself imply that the parked map/list should open: ``resume``
        # and recruit modes continue their mission, while info modes unwind to
        # whatever their enclosing script specifies next.
        self.continuation = continuation
        self.dietrich_mode = None  # ``reading`` / ``talking`` while his close-up is open
        self.selected_book = None
        self.save_requested = False
        self.font = None

    def enter(self, context):
        self.font = context.load(CARAVAN_FONT)

    @property
    def gold(self):
        return self.campaign.coffers

    @property
    def missions(self):
        return self.campaign.missions

    @property
    def scroll_count(self):
        return self.campaign.scroll_count

    @property
    def can_select_mission(self):
        """Whether this caravan's hotspot has resolved to the map/list."""
        return self.continuation == "open_mission_map"

    def handle(self, event, context):
        if event == "open_mission_map" and self.can_select_mission:
            return Transition(MissionMapScene(self.campaign), "campaign map opened")
        if event == "exit_campaign":
            return Transition(MainMenuScene(), "campaign exited")
        if event == "speak_to_dietrich":
            self.dietrich_mode = "talking" if self.has_message else "reading"
        elif event == "dismiss_dietrich":
            self.dietrich_mode = None
        elif event.startswith("browse_book:"):
            self.selected_book = event.removeprefix("browse_book:")
        elif event == "save_campaign":
            self.save_requested = True
        return None


class MissionMapScene(Scene):
    """The parked campaign map and its interactive mission-scroll list.

    In the original glue flow this window remains alive while the briefing,
    troop selection, and battle are pushed above it.  This scene represents
    that parked choice point; campaign state remains uncommitted until the
    later troop-selection implementation accepts the briefing.
    """

    def __init__(self, campaign):
        self.campaign = campaign
        self.dietrich_portrait = None
        self.portrait_window = campaign.map_portrait_window
        self.selected_index = None

    def enter(self, context):
        # Portrait FOL/BOP files are not required by the minimal test fixture
        # or every partial installation, so leave the panel absent if either
        # source file has not been extracted from an installed game.
        try:
            if self.portrait_window is not None and self.portrait_window.get("index") == 4:
                self.dietrich_portrait = dietrich_portrait(
                    context.locator.installation, self.portrait_window.get("bkindex", 15)
                )
        except FileNotFoundError:
            self.dietrich_portrait = None

    @property
    def missions(self):
        return self.campaign.missions

    @property
    def selected_mission(self):
        if self.selected_index is None or self.selected_index >= len(self.missions):
            return None
        return self.missions[self.selected_index]

    def handle(self, event, context):
        if event == "return_to_caravan":
            # Esc only closes the list view; it does not change the parked
            # StartCaravan continuation that opened it.
            return Transition(CaravanScene(self.campaign, continuation="open_mission_map"),
                              "campaign map dismissed")
        if event.startswith("select_mission:"):
            index = int(event.removeprefix("select_mission:"))
            if not 0 <= index < len(self.missions):
                return None
            self.selected_index = index
            return None
        if event == "open_briefing":
            mission = self.selected_mission
            if mission is None:
                return None
            briefing = mission.get("briefing") or BriefingScene(
                AssetId("vanilla", "battle", mission["battle"].casefold())
            )
            return Transition(briefing, f"campaign mission briefing opened: {mission['name']}")
        if event == "open_troop_select" and self.selected_mission is not None:
            return Transition(TroopSelectScene(self.campaign, self.selected_mission),
                              f"campaign troop selection opened: {self.selected_mission['name']}")
        return None


class TroopSelectScene(Scene):
    """Built-in troop-selection window placeholder, reached by the map's Accept control."""

    def __init__(self, campaign, mission):
        self.campaign = campaign
        self.mission = mission


class BriefingScene(Scene):
    """Show one battle's campaign briefing text; Start Battle enters the battle itself."""

    def __init__(self, battle, log_dir=None, seed=DEFAULT_SEED):
        self.battle_id = battle
        self.briefing_id = briefing_asset_for(battle)
        self.manifest = SceneManifest(immediate=(self.briefing_id,), prefetch=(battle,))
        self.briefing = None
        self.log_dir = log_dir
        self.seed = seed

    def enter(self, context):
        self.briefing = context.load(self.briefing_id)

    def handle(self, event, context):
        if event == "start_battle":
            return Transition(BattleScene(self.battle_id, log_dir=self.log_dir, seed=self.seed),
                              "briefing accepted")
        return None


def default_scene_loaders():
    """Return loaders currently needed by the implemented campaign scenes."""
    return {
        "omni-si": lambda _record, path: load_si(path),
        "pe-string-table": lambda _record, path: module("pe_missions").load_strings(str(path)),
        "warhammer-fon": lambda _record, path: module("fon_parse").load_fon(str(path)).fonts[0],
    }
