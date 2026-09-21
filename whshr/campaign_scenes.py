"""Initial campaign scenes backed by the original-install asset catalog."""

from .assets import AssetId
from .battle_scene import BattleScene, FIRST_BATTLE
from .campaign_state import CampaignState
from .campaign import parse_window_ui
from .engine import DEFAULT_SEED
from .glue_runtime import ActivityResult
from .glue_scene import GlueScene
from .glue_fonts import glue_font_asset
from .legacy import module
from .scenes import Quit, Scene, SceneManifest, Transition
from .si import load_si, walk_objects
from .troop_selection import TroopSelection

INTRO_CUTSCENE = AssetId("vanilla", "cutscene", "a1")
INTRO_MEDIA = AssetId("vanilla", "cutscene", "a1-media")
MAIN_MENU = AssetId("vanilla", "ui", "main-menu")
ANIMATION_TEXT = AssetId("vanilla", "text", "anim")
SUBTITLE_FONT = AssetId("vanilla", "font", "subtext")
PCTEXTA_FONT = AssetId("vanilla", "font", "pctexta")
PCTEXT_FONT = glue_font_asset(2)
BRIEFING_FONT = glue_font_asset(4)
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


def briefing_asset_for(mission):
    """Return the briefing asset for one exact campaign mission record."""
    mission_ref = mission.get("mission_ref")
    return AssetId("vanilla", "briefing", mission_ref.key if mission_ref is not None
                   else mission["briefing_key"])


class OpeningNarrationScene(Scene):
    """The text-only prologue shown before the A1 opening cutscene."""

    manifest = SceneManifest(immediate=(ANIMATION_TEXT, SUBTITLE_FONT),
                             prefetch=(INTRO_CUTSCENE, INTRO_MEDIA))

    def __init__(self, successor=None, log_dir=None, seed=DEFAULT_SEED):
        self.successor = successor or MovieScene("a1", successor=MainMenuScene(log_dir=log_dir, seed=seed))
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


class MovieScene(Scene):
    """Play one Omni cutscene timeline (notes/si_omni.md) end-to-end, then hand control back.

    Two mutually exclusive completion routes: a fixed ``successor`` scene (the boot-time A1
    intro), or a parked ``glue_scene`` resumed with an ``ActivityResult`` (``playmovie`` and
    its variants, notes/glue_interpreter.md §8.3). ``fade`` is accepted but has no observable
    original effect (notes/glue_interpreter.md §8.3: fade variants unused by shipped scripts).
    """

    def __init__(self, movie, successor=None, glue_scene=None, request_id=None, fade=False):
        if (successor is None) == (glue_scene is None):
            raise ValueError("MovieScene needs exactly one successor or glue_scene")
        self.movie = str(movie)
        self.cutscene_id = AssetId("vanilla", "cutscene", self.movie.casefold())
        self.media_id = AssetId("vanilla", "cutscene", f"{self.movie.casefold()}-media")
        self.successor = successor
        self.glue_scene = glue_scene
        self.request_id = request_id
        self.fade = fade
        self.manifest = SceneManifest(immediate=(self.cutscene_id, self.media_id, ANIMATION_TEXT, SUBTITLE_FONT),
                                      prefetch=(MAIN_MENU,) if glue_scene is None else ())
        self.elapsed_seconds = 0.0
        self.duration_seconds = None
        self.container = None
        self.media = None
        self.texts = None
        self.subtitle_font = None

    def enter(self, context):
        self.container = context.load(self.cutscene_id)
        self.duration_seconds = omni_duration_seconds(self.container)
        self.media = context.load(self.media_id)
        self.texts = context.load(ANIMATION_TEXT)
        self.subtitle_font = context.load(SUBTITLE_FONT)

    def _finish(self, reason):
        if self.glue_scene is not None:
            self.glue_scene.complete_activity(ActivityResult(self.request_id, "movie"))
            return Transition(self.glue_scene, reason)
        return Transition(self.successor, reason)

    def handle(self, event, context):
        if event == "skip":
            return self._finish("movie skipped")
        return None

    def update(self, seconds, context):
        super().update(seconds, context)
        self.elapsed_seconds += seconds
        if self.elapsed_seconds >= self.duration_seconds:
            return self._finish("movie completed")
        return None


class MainMenuScene(Scene):
    """The main menu: New Campaign enters Dietrich's caravan; Quit ends the application."""

    manifest = SceneManifest(immediate=(MAIN_MENU,))

    def __init__(self, briefing=None, log_dir=None, seed=DEFAULT_SEED, campaign=None):
        self.briefing = briefing
        self.log_dir, self.seed = log_dir, seed
        self.campaign = campaign
        self.menu_ui = None
        self.content = None

    def enter(self, context):
        if context is None:
            return
        self.installation = context.locator.installation
        self.content = context.glue_content()
        try:
            wnd_path = context.locator.installation.file_dir("DLL", "WND.DLL")
            if wnd_path.stat().st_size < 64:
                return
            self.menu_ui = parse_window_ui(self.content.resources, "MAINMENU")
        except (FileNotFoundError, OSError, ValueError):
            # Focused scene tests can supply a minimal placeholder WND.DLL.
            self.menu_ui = None

    def handle(self, event, context):
        if event == "new_campaign":
            if self.campaign is None:
                # Tests and development callers may still inject one focused
                # briefing; a real installation derives the full initial flow.
                self.campaign = (
                    CampaignState.single_mission(self.briefing) if self.briefing is not None
                    else CampaignState.from_installation(context.locator.installation, self.content)
                )
            return Transition(GlueScene(campaign=self.campaign, window="STARTCARAVAN"), "new campaign started")
        if event == "quit":
            return Quit("player quit from the main menu")
        return None


class MissionMapScene(Scene):
    """The parked campaign map and its interactive mission-scroll list.

    In the original glue flow this window remains alive while the briefing,
    troop selection, and battle are pushed above it.  This scene represents
    that parked choice point; campaign state remains uncommitted until the
    later troop-selection implementation accepts the briefing.
    """

    # MissionWindow's built-in row painter and ScribeMWindow's buttons both
    # select glue font 2, PCTEXT.FON (not the briefing's PCTEXTA.FON).
    manifest = SceneManifest(immediate=(PCTEXT_FONT,))

    def __init__(self, campaign):
        self.campaign = campaign
        self.speaker_portrait = None
        self.portrait_window = campaign.map_portrait_window
        self.selected_index = None
        self.installation = None
        self.content = None
        self.font = None

    def enter(self, context):
        self.installation = context.locator.installation
        self.content = self.campaign.content or context.glue_content()
        self.campaign.content = self.content
        self.font = context.load(PCTEXT_FONT)
        # Portrait FOL/BOP files are not required by the minimal test fixture
        # or every partial installation, so leave the panel absent if either
        # source file has not been extracted from an installed game.
        try:
            if self.portrait_window is not None:
                self.speaker_portrait = self.content.portrait_data(
                    self.portrait_window["index"], self.portrait_window["bkindex"]
                )
        except (FileNotFoundError, ValueError):
            self.speaker_portrait = None

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
            return Transition(GlueScene(campaign=self.campaign, window="STARTCARAVAN"),
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
            if mission.get("brief_script") and mission.get("battle"):
                return Transition(GlueScene(mission["brief_script"], self.campaign,
                                            accept_battle=mission["battle"], return_scene=self),
                                  f"campaign mission briefing opened: {mission['name']}")
            briefing = mission.get("briefing") or BriefingScene(
                mission, campaign=self.campaign
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
    """Run the selected mission's data-defined map briefing before troop selection."""

    def __init__(self, mission, log_dir=None, seed=DEFAULT_SEED, campaign=None):
        self.mission = mission
        self.campaign = campaign
        self.battle_id = AssetId("vanilla", "battle", mission["battle"].casefold())
        self.briefing_id = briefing_asset_for(mission)
        self.manifest = SceneManifest(immediate=(self.briefing_id, BRIEFING_FONT, PCTEXT_FONT),
                                      prefetch=(self.battle_id,))
        self.briefing = None
        self.font = None
        self.ui_font = None
        self.installation = None
        self.content = None
        self.turn_index = 0
        self.characters_visible = 0
        self.dialogue_elapsed = 0.0
        self.dialogue_finished = False
        self.paused = False
        self.portraits = ()
        self.log_dir = log_dir
        self.seed = seed

    def enter(self, context):
        self.installation = context.locator.installation
        self.content = ((self.campaign.content if self.campaign is not None else None)
                        or context.glue_content())
        if self.campaign is not None:
            self.campaign.content = self.content
        self.briefing = context.load(self.briefing_id)
        self.font = context.load(BRIEFING_FONT)
        self.ui_font = context.load(PCTEXT_FONT)
        # Older focused fixtures deliberately contain only a transcript.  The
        # real loader supplies the full glue-derived layout.
        self.portraits = tuple(self.briefing.get("portraits", ()))

    def handle(self, event, context):
        if event in ("continue_briefing", "fast_forward_dialogue"):
            turns = self.briefing.get("turns", ())
            if not self.dialogue_finished and turns:
                self.characters_visible = len(turns[self.turn_index]["lines"][0])
                self.dialogue_elapsed = 0.75
            return None
        if event == "toggle_pause":
            self.paused = not self.paused
            return None
        if event == "accept_briefing":
            return Transition(TroopSelectScene(self.campaign, self.mission), "briefing accepted")
        if event == "abort_briefing" and self.campaign is not None:
            return Transition(MissionMapScene(self.campaign), "briefing aborted")
        if event == "start_battle":
            # Compatibility bridge for the direct-development shortcut.  The
            # normal UI uses continue_briefing and reaches TroopSelect first.
            return Transition(BattleScene(self.battle_id, log_dir=self.log_dir, seed=self.seed),
                              "briefing accepted")
        return None

    def update(self, seconds, context):
        if self.paused or self.dialogue_finished:
            return None
        turns = self.briefing.get("turns", ())
        if not turns:
            self.dialogue_finished = True
            return None
        text = turns[self.turn_index]["lines"][0]
        self.dialogue_elapsed += seconds
        # The glue timer types one character every two 25 ms ticks, then holds
        # for 30 ticks before clearing (notes/briefing_dialogue.md §3.5).
        self.characters_visible = min(len(text), int(self.dialogue_elapsed / 0.05))
        if self.characters_visible == len(text) and self.dialogue_elapsed >= len(text) * 0.05 + 0.75:
            self.turn_index += 1
            self.characters_visible = 0
            self.dialogue_elapsed = 0.0
            self.dialogue_finished = self.turn_index >= len(turns)
        return None


class TroopSelectionScene(Scene):
    """The front-end-owned troop-selection screen, reached by Accept (notes/troop_selection.md).

    Core in-memory flow only (notes/glue_engine_integration.md GEI7): the real P0/P1 view, the
    bankruptcy page's presentation, and the roster book are deferred to GEI7b-GEI7d.
    """

    def __init__(self, campaign, mission_ref, battle, glue_scene):
        self.campaign = campaign
        self.mission_ref = mission_ref
        self.battle = battle
        self.glue_scene = glue_scene
        self.model = None
        self.phase = "select"

    def enter(self, context):
        if not self.campaign or not self.campaign.company:
            # notes/troop_selection.md §1.1: no company file skips the screen and runs Done immediately.
            self.glue_scene.start_battle(self.battle)
            self.phase = "skip"
            return
        record = self.glue_scene.runtime.content.mission(self.mission_ref)
        forced = tuple(int(field.argument) for field in record.fields if field.command == "forceunits")
        excluded = tuple(int(field.argument) for field in record.fields if field.command == "excludeunits")
        self.model = TroopSelection(self.campaign.company, forced=forced, excluded=excluded,
                                    coffers=self.campaign.coffers, prepaid=_prepaid_payment(record))
        if self.model.bankrupt:
            self.phase = "bankrupt"

    def handle(self, event, context):
        if self.phase == "skip":
            return Transition(self.glue_scene, "troop selection skipped (no company)")
        if event == "abort":
            return Transition(self.glue_scene, "troop selection aborted")
        if self.phase == "bankrupt":
            # notes/troop_selection.md §7: only Done exists; its exact destination is still open (🟡).
            if event == "done":
                return Transition(self.glue_scene, "troop selection bankrupt")
            return None
        if isinstance(event, str) and event.startswith("toggle:"):
            self.model.toggle(int(event.split(":", 1)[1]))
            return None
        if isinstance(event, str) and event.startswith("move:"):
            whoami, index = event.split(":", 1)[1].split(",")
            self.model.move(int(whoami), int(index))
            return None
        if event == "done":
            if self.phase == "select":
                if self.model.selection:
                    self.phase = "march_order"
                return None
            deployment = self.model.confirm()
            self.campaign.commit_troop_selection(deployment)
            self.campaign.mark_mission_taken(self.mission_ref)
            self.glue_scene.start_battle(self.battle)
            return Transition(self.glue_scene, "troop selection done")
        return None

    def update(self, seconds, context):
        super().update(seconds, context)
        if self.phase == "skip":
            return Transition(self.glue_scene, "troop selection skipped (no company)")
        return None


def _prepaid_payment(mission_record):
    """The initial cash payment, credited at troop-selection Done; notes/campaign.md §2.2-2.3."""
    cash = next((field.argument for field in mission_record.fields if field.command == "cash"), None)
    if not cash:
        return 0
    parts = [part.strip() for part in cash.split(",")]
    try:
        return int(parts[1])
    except (IndexError, ValueError):
        return 0


def default_scene_loaders():
    """Return loaders currently needed by the implemented campaign scenes."""
    return {
        "omni-si": lambda _record, path: load_si(path),
        "pe-string-table": lambda _record, path: module("pe_missions").load_strings(str(path)),
        "warhammer-fon": lambda _record, path: module("fon_parse").load_fon(str(path)).fonts[0],
    }
