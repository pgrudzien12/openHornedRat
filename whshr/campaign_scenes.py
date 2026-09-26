# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Initial campaign scenes backed by the original-install asset catalog."""
from collections.abc import Mapping
from typing import Any

from .assets import AssetId
from .battle_scene import BattleScene
from .campaign_state import CampaignState
from .glue_content import GlueContent
from .paths import Installation
from .campaign import parse_window_ui
from .engine import DEFAULT_SEED
from .glue_runtime import ActivityResult
from .glue_scene import GlueScene
from .glue_fonts import glue_font_asset
from . import payments
from .legacy import module
from .cache import Loader
from .glue import MissionRecord, MissionRef
from .scenes import Quit, Scene, SceneAssets, SceneEvent, SceneManifest, Transition
from .si import load_si, walk_objects
from .roster_book import BookModel
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


def omni_duration_seconds(container: Mapping[str, Any]) -> float:
    """Return the final scheduled Omni object end in seconds."""
    if "root" not in container:
        raise ValueError("Omni container has no root object")
    end_ms = max(
        (object_["start"] + object_["duration"] for object_ in walk_objects(container["root"])),
        default=0,
    )
    return end_ms / 1000


def briefing_asset_for(mission: Mapping[str, Any]) -> AssetId:
    """Return the briefing asset for one exact campaign mission record."""
    mission_ref = mission.get("mission_ref")
    return AssetId("vanilla", "briefing", mission_ref.key if mission_ref is not None
                   else mission["briefing_key"])


class OpeningNarrationScene(Scene):
    """The text-only prologue shown before the A1 opening cutscene."""

    manifest = SceneManifest(immediate=(ANIMATION_TEXT, SUBTITLE_FONT),
                             prefetch=(INTRO_CUTSCENE, INTRO_MEDIA))

    def __init__(self, successor: "MovieScene | None" = None, log_dir: Any = None, seed: int = DEFAULT_SEED) -> None:
        self.successor: MovieScene = successor or MovieScene("a1", successor=MainMenuScene(log_dir=log_dir, seed=seed))
        self.texts: Any = None
        self.subtitle_font: Any = None
        self.text: str | None = None

    def enter(self, context: SceneAssets) -> None:
        self.texts = context.load(ANIMATION_TEXT)
        self.subtitle_font = context.load(SUBTITLE_FONT)
        self.text = "".join(self.texts[text_id] for text_id in OPENING_TEXT_IDS)

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if event == "continue":
            return Transition(self.successor, "opening narration dismissed")
        if event == "skip":
            after_intro = self.successor.successor
            if after_intro is None:
                return None
            return Transition(after_intro, "intro skipped")
        return None


class MovieScene(Scene):
    """Play one Omni cutscene timeline (notes/si_omni.md) end-to-end, then hand control back.

    Two mutually exclusive completion routes: a fixed ``successor`` scene (the boot-time A1
    intro), or a parked ``glue_scene`` resumed with an ``ActivityResult`` (``playmovie`` and
    its variants, notes/glue_interpreter.md §8.3). ``fade`` is accepted but has no observable
    original effect (notes/glue_interpreter.md §8.3: fade variants unused by shipped scripts).
    """

    def __init__(self, movie: str, successor: Scene | None = None, glue_scene: GlueScene | None = None,
                 request_id: int | None = None, fade: bool = False) -> None:
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
        self.duration_seconds: float | None = None
        self.container: Any = None
        self.media: Any = None
        self.texts: Any = None
        self.subtitle_font: Any = None

    def enter(self, context: SceneAssets) -> None:
        self.container = context.load(self.cutscene_id)
        self.duration_seconds = omni_duration_seconds(self.container)
        self.media = context.load(self.media_id)
        self.texts = context.load(ANIMATION_TEXT)
        self.subtitle_font = context.load(SUBTITLE_FONT)

    def _finish(self, reason: str) -> Transition:
        if self.glue_scene is not None:
            self.glue_scene.complete_activity(ActivityResult(self.request_id or 0, "movie"))
            return Transition(self.glue_scene, reason)
        if self.successor is None:
            raise RuntimeError("MovieScene has neither a glue scene nor a successor")
        return Transition(self.successor, reason)

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if event == "skip":
            return self._finish("movie skipped")
        return None

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        self.elapsed_seconds += seconds
        if self.duration_seconds is not None and self.elapsed_seconds >= self.duration_seconds:
            return self._finish("movie completed")
        return None


class MainMenuScene(Scene):
    """The main menu: New Campaign enters Dietrich's caravan; Quit ends the application."""

    manifest = SceneManifest(immediate=(MAIN_MENU,))

    def __init__(self, briefing: Any = None, log_dir: Any = None, seed: int = DEFAULT_SEED,
                 campaign: CampaignState | None = None) -> None:
        self.briefing = briefing
        self.log_dir, self.seed = log_dir, seed
        self.campaign = campaign
        self.menu_ui: dict[str, Any] | None = None
        self.content: GlueContent | None = None
        self.installation: Installation | None = None

    def enter(self, context: SceneAssets | None) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
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

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if event == "new_campaign":
            if self.campaign is None:
                # Tests and development callers may still inject one focused
                # briefing; a real installation derives the full initial flow.
                self.campaign = (
                    CampaignState.single_mission(self.briefing) if self.briefing is not None
                    else CampaignState.from_installation(context.locator.installation, self.content,
                                                         save_dir=getattr(context, "save_dir", None))
                )
            return Transition(GlueScene(campaign=self.campaign, window="STARTCARAVAN"), "new campaign started")
        if event == "load_game":
            from .load_save_scene import LOAD, LoadSaveScene
            return Transition(LoadSaveScene(LOAD, self), "load dialog opened")
        if event == "credits":
            from .credits_scene import CreditsScene
            return Transition(CreditsScene(self), "credits opened")
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

    def __init__(self, campaign: CampaignState) -> None:
        self.campaign = campaign
        self.speaker_portrait: Any = None
        self.portrait_window = campaign.map_portrait_window
        self.selected_index: int | None = None
        self.installation: Installation | None = None
        self.content: GlueContent | None = None
        self.font: Any = None

    def enter(self, context: SceneAssets) -> None:
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
    def missions(self) -> tuple[dict[str, Any], ...]:
        return self.campaign.missions

    @property
    def selected_mission(self) -> dict[str, Any] | None:
        if self.selected_index is None or self.selected_index >= len(self.missions):
            return None
        return self.missions[self.selected_index]

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
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

    def __init__(self, campaign: CampaignState | None, mission: Any) -> None:
        self.campaign = campaign
        self.mission = mission


class BriefingScene(Scene):
    """Run the selected mission's data-defined map briefing before troop selection."""

    def __init__(self, mission: dict[str, Any], log_dir: Any = None, seed: int = DEFAULT_SEED,
                 campaign: CampaignState | None = None) -> None:
        self.mission = mission
        self.campaign = campaign
        self.battle_id = AssetId("vanilla", "battle", mission["battle"].casefold())
        self.briefing_id = briefing_asset_for(mission)
        self.manifest = SceneManifest(immediate=(self.briefing_id, BRIEFING_FONT, PCTEXT_FONT),
                                      prefetch=(self.battle_id,))
        self.briefing: dict[str, Any] = {}
        self.font: Any = None
        self.ui_font: Any = None
        self.installation: Installation | None = None
        self.content: GlueContent | None = None
        self.turn_index = 0
        self.characters_visible = 0
        self.dialogue_elapsed = 0.0
        self.dialogue_finished = False
        self.paused = False
        self.portraits: tuple[Any, ...] = ()
        self.log_dir = log_dir
        self.seed = seed

    def enter(self, context: SceneAssets) -> None:
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

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
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

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
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

    P0/P1/P5 are presented by ``frontend.troop_selection_view``; Ctrl-click parks this scene
    beneath :class:`ArmyRecordsScene` (notes/troop_selection.md §8).
    """

    def __init__(self, campaign: CampaignState | None, mission_ref: MissionRef | None, battle: str,
                 glue_scene: GlueScene) -> None:
        self.campaign = campaign
        self.mission_ref = mission_ref
        self.battle = battle
        self.glue_scene = glue_scene
        self.model: TroopSelection | None = None
        self.phase = "select"
        self.page = 0
        self.march_offset = 0
        self.picked_whoami: int | None = None
        self.record: MissionRecord | None = None
        self.context: SceneAssets | None = None
        self.destination: Scene = glue_scene  # where Done/skip lands: the scene running the mission

    def enter(self, context: SceneAssets) -> None:
        # Army Records returns to this exact scene instance.  It must not rebuild the
        # selection model or lose P0/P1 page state on that return.
        self.context = context
        if self.model is not None:
            return
        if not self.campaign or not self.campaign.company:
            # notes/troop_selection.md §1.1: no company file skips the screen and runs Done immediately.
            if self.campaign:
                self.campaign.begin_mission(self._payment_terms())
            self._start_mission()
            self.phase = "skip"
            return
        if self.mission_ref is None:
            raise ValueError("troop selection needs a mission reference")
        self.record = self.glue_scene.require_runtime().content.mission(self.mission_ref)
        self.campaign.begin_mission(payments.mission_terms(self.record))
        forced = _unit_ids(self.record, "forceunits")
        excluded = _unit_ids(self.record, "excludeunits")
        self.model = TroopSelection(self.campaign.company, forced=forced, excluded=excluded,
                                    coffers=self.campaign.coffers, prepaid=_prepaid_payment(self.record),
                                    reinforcements=self.campaign.reinforcements)
        if self.model.bankrupt:
            self.phase = "bankrupt"

    def _payment_terms(self) -> payments.CashTerms | None:
        try:
            if self.mission_ref is None:
                return None
            return payments.mission_terms(self.glue_scene.require_runtime().content.mission(self.mission_ref))
        except (KeyError, TypeError, AttributeError, RuntimeError):
            return None

    def _start_mission(self) -> None:
        """Done: run the mission's own script when its record names one (it starts the battle and
        carries the flow on afterwards); a record with only a battle starts that battle directly
        (notes/troop_selection.md §6).

        A mission started straight from the mission map runs on its own scene whose ``return_scene`` is
        that map, exactly like one started from a briefing: the map's release wait stays open until the
        mission ends, and the mission's release then completes it and advances the flow."""
        script = ""
        values: dict[str, int | str] = {}
        if self.mission_ref is not None:
            try:
                values = self.glue_scene.require_runtime().content.mission(self.mission_ref).values
                script = str(values.get("setmissionscript", ""))
            except (KeyError, TypeError):
                script = ""
        host = self.glue_scene
        if script and host.accept_mission is None and host.return_scene is None and self.mission_ref is not None:
            self.destination = GlueScene(script, self.campaign, accept_battle=self.battle,
                                         accept_mission=self.mission_ref, return_scene=host)
        elif script:
            host.start_mission_script(script)
        elif self.mission_ref is not None and self.battle:
            # No mission script: the record's own battle, debrief and completion run on a scene of their
            # own, the same from the briefing and straight from the map (notes/activity_results.md 2.4).
            debrief = str(values.get("debrief", "")).strip() or None
            self.destination = GlueScene(record_battle=self.battle, record_debrief=debrief, campaign=self.campaign,
                                         accept_mission=self.mission_ref,
                                         return_scene=host.return_scene or host)
        else:
            self.glue_scene.start_battle(self.battle)

    def handle(self, event: SceneEvent, context: SceneAssets | None) -> Transition | Quit | None:
        if self.phase == "skip":
            return Transition(self.destination, "troop selection skipped (no company)")
        if self.phase == "bankrupt":
            # notes/troop_selection.md §§4.4, 7: P5 has no Abort, paging, or row actions.
            # Its ultimate campaign-ending destination is open; retain the current parked-scene
            # return until that behaviour is specified.
            if event == "done":
                return Transition(self.glue_scene, "troop selection bankrupt")
            return None
        model = self.selection_model()
        campaign = self.campaign
        if event == "abort":
            if not model.selection:  # nothing selected: aborts silently (notes/builtin_widgets.md section 4.1)
                return Transition(self.glue_scene, "troop selection aborted")
            from .confirm_scene import ConfirmScene
            return Transition(ConfirmScene(self, self.glue_scene, ("BRTXT", 308), reason="troop selection aborted"),
                              "abort confirmation opened")
        if event == "page:next" and self.phase == "select":
            self.page = min(self.page + 1, self.page_count - 1)
            return None
        if event == "page:back":
            if self.phase == "select":
                self.page = max(0, self.page - 1)
            elif self.phase == "march_order":
                self.phase = "select"
                self.page = self.page_count - 1
                self.picked_whoami = None
            return None
        if isinstance(event, str) and event.startswith("toggle:"):
            model.toggle(int(event.split(":", 1)[1]))
            return None
        if isinstance(event, str) and event.startswith("book:"):
            whoami = int(event.split(":", 1)[1])
            if whoami in model.company:
                return Transition(ArmyRecordsScene(self, whoami), "army records opened")
            return None
        if isinstance(event, str) and event.startswith("pickup:") and self.phase == "march_order":
            index = int(event.split(":", 1)[1])
            if 0 <= index < len(model.selection):
                self.picked_whoami = model.selection[index]
            return None
        if isinstance(event, str) and event.startswith("drop:") and self.phase == "march_order":
            index = int(event.split(":", 1)[1])
            if self.picked_whoami is not None:
                model.move(self.picked_whoami, index)
                self.picked_whoami = None
            return None
        if event in ("scroll:up", "scroll:down") and self.phase == "march_order":
            delta = -1 if event == "scroll:up" else 1
            self.march_offset = max(0, min(self.march_offset + delta, self.max_march_offset))
            return None
        if isinstance(event, str) and event.startswith("move:"):
            whoami, index = event.split(":", 1)[1].split(",")
            model.move(int(whoami), int(index))
            return None
        if event == "done":
            if self.phase == "select":
                if model.selection:
                    self.phase = "march_order"
                return None
            if campaign is None:
                return None
            deployment = model.confirm()
            campaign.commit_troop_selection(deployment)
            log = getattr(getattr(self, "context", None), "campaign_log", None)
            if log is not None:
                try:
                    log.write("payment", kind="initial", amount=model.prepaid, mission_fee=model.total_cost,
                              coffers=campaign.coffers)
                except Exception:
                    pass
            if self.mission_ref is not None:
                campaign.mark_mission_taken(self.mission_ref)
            self._start_mission()
            return Transition(self.destination, "troop selection done")
        return None

    @property
    def page_count(self) -> int:
        """P0 pages include every company file record; notes/troop_selection.md §3.1."""
        return max(1, (len(self.selection_model().company) + 5) // 6)

    @property
    def max_march_offset(self) -> int:
        """Keep P1's final seven-row viewport full where possible (§5.1)."""
        return max(0, len(self.selection_model().selection) - 7)

    def selection_model(self) -> TroopSelection:
        """The P0/P1 model; only absent while the screen is skipped (no company)."""
        if self.model is None:
            raise RuntimeError("troop selection has no model")
        return self.model

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        if self.phase == "skip":
            return Transition(self.destination, "troop selection skipped (no company)")
        return None


class ArmyRecordsScene(Scene):
    """One-regiment-per-page Army Records screen (notes/builtin_widgets.md §2, notes/troop_selection.md §8).

    Two parents open it: the troop-selection screen (Ctrl+click; the book edits that screen's model) and
    a caravan (``ArmyBook`` / ``HireOnlyArmyBook`` hotspots; the caller passes a
    :class:`~whshr.roster_book.RosterBook`). The scene owns only the page and the Stat/Info mode; hiring,
    the reinforcement offer and the coffers belong to the model, and Done/Abort hand the outcome to the
    campaign state.
    """

    def __init__(self, parent: "TroopSelectionScene | GlueScene", whoami: int, model: BookModel | None = None) -> None:
        self.parent = parent
        self.whoami = whoami
        if model is None:
            if not isinstance(parent, TroopSelectionScene):
                raise ValueError("a caravan book needs its own roster model")
            model = parent.selection_model()
        self.model: BookModel = model
        self.hired_at_open = dict(self.model.hired)

    @property
    def glue_scene(self) -> GlueScene:
        return self.parent.glue_scene if isinstance(self.parent, TroopSelectionScene) else self.parent

    @property
    def campaign(self) -> CampaignState | None:
        return self.parent.campaign

    @property
    def company_ids(self) -> tuple[int, ...]:
        return tuple(self.model.company)

    @property
    def index(self) -> int:
        return self.company_ids.index(self.whoami)

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if event == "book:done":
            if self.campaign is not None:
                self.campaign.apply_army_book(self.model)
            return Transition(self.parent, "army records closed")
        if event == "book:abort":
            self.model.restore_book_hired(self.hired_at_open)
            self.model.ledger.revert()
            if self.campaign is not None:
                self.campaign.abort_army_book(self.model)
            return Transition(self.parent, "army records aborted")
        if event == "book:hire-fire":
            self.model.toggle_hired(self.whoami)
            return None
        ledger = self.model.ledger
        if event == "reinf:up":
            ledger.increase(self.whoami)
            return None
        if event == "reinf:down":
            ledger.decrease(self.whoami)
            return None
        if event == "reinf:take":
            ledger.take(self.whoami)
            return None
        if event in ("book:previous", "book:first", "book:last", "book:next"):
            if event == "book:first":
                target = 0
            elif event == "book:last":
                target = len(self.company_ids) - 1
            else:
                target = self.index + (-1 if event == "book:previous" else 1)
            self.whoami = self.company_ids[max(0, min(target, len(self.company_ids) - 1))]
        return None


def _unit_ids(mission_record: MissionRecord, command: str) -> tuple[int, ...]:
    """The whoami ids of a mission record's ``forceunits``/``excludeunits`` lines; an argument may list several ids."""
    return tuple(int(part) for field in mission_record.fields if field.command == command
                 for part in field.argument.split(",") if part.strip())


def _prepaid_payment(mission_record: MissionRecord) -> int:
    """The initial cash payment, credited at troop-selection Done; notes/campaign.md §2.2-2.3."""
    terms = payments.mission_terms(mission_record)
    return terms.initial if terms else 0


def default_scene_loaders() -> dict[str, Loader]:
    """Return loaders currently needed by the implemented campaign scenes."""
    return {
        "omni-si": lambda _record, path: load_si(path),
        "pe-string-table": lambda _record, path: module("pe_missions").load_strings(str(path)),
        "warhammer-fon": lambda _record, path: module("fon_parse").load_fon(str(path)).fonts[0],
    }
