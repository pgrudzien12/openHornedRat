"""Debrief scene: shows the post-battle pages of :class:`whshr.debrief_screen.DebriefScreen` and, on Done (or at
once when the evaluator has nothing to show), applies the completion and resumes the glue script that asked
for it (notes/native-windows.md section 9, issue #123)."""

from typing import Any

from .campaign_state import CampaignState
from .casualties import commit_wounded
from .debrief import report_for
from .debrief_rules import end_screen
from .debrief_screen import DebriefScreen
from .glue import MissionRef
from .glue_runtime import StartDebrief
from .glue_scene import GlueScene
from .objectives import item_text_id
from .payments import CashTerms
from .scenes import Quit, Scene, SceneAssets, SceneEvent, Transition


class DebriefScene(Scene):
    """One debrief request of a glue scene; ``screen`` is ``None`` when there is no campaign to report on."""

    def __init__(self, glue_scene: GlueScene, effect: StartDebrief) -> None:
        self.glue_scene = glue_scene
        self.effect = effect
        self.screen: DebriefScreen | None = None
        self.context: SceneAssets | None = None
        self.finished = False

    def enter(self, context: SceneAssets) -> None:
        self.context = context
        campaign = self.glue_scene.campaign
        if self.screen is not None or campaign is None:
            return
        terms: CashTerms | None = campaign.mission_cash
        self.screen = DebriefScreen(
            self.effect.mode, report_for(campaign), self.effect.debrief_index, terms, campaign.coffers,
            self._mission_name_id(), self._string, bonus_counter=campaign.bonus_counter,
            item_name=self._item_name)
        self.glue_scene.require_runtime().apply_evaluation_status(self.screen.evaluation)
        if not self.screen.will_skip() and ("commit", 0) in (self.screen.evaluation.program or ()):
            # The mission-text page (shown first) commits this battle's wounded (notes/casualty_bookkeeping.md 3.4).
            commit_wounded(campaign)

    def _mission_name_id(self) -> int | None:
        """The ``BRTXT`` id of the mission title: the record's own ``set:res`` (notes/native-windows.md 9.3.4)."""
        ref = getattr(self.glue_scene.campaign, "selected_mission", None)
        if not isinstance(ref, MissionRef):
            return None
        try:
            record = self.glue_scene.require_runtime().content.mission(ref)
        except (KeyError, TypeError):
            return None
        for field in record.fields:
            if field.command == "set" and "=" in field.argument:
                key, value = field.argument.split("=", 1)
                if key.casefold() == "res":
                    try:
                        return int(value.split(None, 1)[0])
                    except ValueError:
                        return None
        return None

    def _item_name(self, table_index: int) -> str | None:
        """The name of a found item for the "have found" line on the mission-text page (``None`` if unnamed)."""
        return self._string("GMTXT", item_text_id(table_index)) or None

    def _string(self, table: str, text_id: int, *arguments: Any) -> str:
        try:
            value = self.glue_scene.require_runtime().content.string(table, int(text_id))
        except (KeyError, TypeError, ValueError):
            return ""
        try:
            return value % arguments
        except (TypeError, ValueError):
            return value

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if self.finished:
            return None
        if event == "done":
            return self._complete()
        if self.screen is not None and isinstance(event, tuple) and len(event) == 2 and event[0] == "view-unit":
            return self._open_roster_book(float(event[1]))
        if self.screen is not None and event == "page:next":
            self.screen.next()
        elif self.screen is not None and event == "page:back":
            self.screen.back()
        return None

    @property
    def campaign(self) -> CampaignState | None:
        return self.glue_scene.campaign

    def _open_roster_book(self, y: float) -> Transition | None:
        """Ctrl+click on a P3 row: the roster book, view only, over the battle's unit list and opened at that unit
        (notes/native-windows.md 9.3.5). The book shows each regiment as the debrief reports it (models still
        standing or routed, experience with this battle's gain, wounded by option ``dead``); nothing is written."""
        from .campaign_scenes import ArmyRecordsScene
        from .roster import with_experience, with_models
        from .roster_book import RosterBook

        campaign = self.campaign
        whoami = self.screen.unit_at(y) if self.screen is not None else None
        if campaign is None or self.screen is None or whoami is None:
            return None
        company = {regiment.whoami: regiment for regiment in campaign.company}
        units = [unit for unit in self.screen.report.units if unit.whoami in company]
        if whoami not in {unit.whoami for unit in units}:
            return None
        regiments = [with_experience(with_models(company[unit.whoami], unit.shown_models), unit.experience)
                     for unit in units]
        wounded = {unit.whoami: unit.wounded(self.screen.dead_percent) for unit in units}
        model = RosterBook(regiments, coffers=campaign.coffers, reinforcements={}, pays=False, wounded=wounded)
        return Transition(ArmyRecordsScene(self, whoami, model, view_only=True), "roster book opened (view only)")

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        if not self.finished and (self.screen is None or self.screen.will_skip()):
            return self._complete()
        return None

    def _complete(self) -> Transition:
        self.finished = True
        self.glue_scene.resolve_debrief(self.effect)
        return Transition(self.glue_scene, "debrief done")


# PROVISIONAL: how long the end picture stays up when nobody clicks.  The original shows it while the front end
# re-initialises and then about one timer tick (notes/native-windows.md 9.3.1, hold time still open); this stands in
# for that re-initialisation time.
END_SCREEN_HOLD = 1.5


def post_battle_transition(glue_scene: GlueScene, effect: StartDebrief, no_battle: bool = False) -> Transition | None:
    """Where a debrief request goes after any end picture: a battle that lost the campaign plays its death movie and
    returns to the main menu with no debrief, payment or merge (notes/native-windows.md 9.9.5); otherwise the
    debrief screen opens.  ``None`` in no-battle mode, where the request completes without a screen."""
    from .campaign_scenes import MainMenuScene, MovieScene

    campaign = glue_scene.campaign
    movie = campaign.campaign_over_movie if campaign is not None and effect.mode in (2, 6) else None
    if campaign is not None and movie is not None:
        campaign.campaign_over_movie = None
        return Transition(MovieScene(movie, successor=MainMenuScene()), "campaign over")
    if no_battle:
        return None
    return Transition(DebriefScene(glue_scene, effect), "debrief opened")


class EndScreenScene(Scene):
    """The end picture between a campaign battle and its debrief (notes/native-windows.md 9.3.1 (b)): the
    evaluator's key picks the neutral, success or failure picture (whshr.debrief_rules.end_screen); a click or
    Enter, or the hold time, goes on to the post-battle step."""

    def __init__(self, glue_scene: GlueScene, effect: StartDebrief) -> None:
        self.glue_scene = glue_scene
        self.effect = effect
        campaign = glue_scene.campaign
        self.bitmap = end_screen(effect.debrief_index, dict(campaign.objective_results) if campaign else {})
        self.elapsed = 0.0
        self.finished = False

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if event == "dismiss" and not self.finished:
            return self._finish()
        return None

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        self.elapsed += seconds
        if not self.finished and self.elapsed >= END_SCREEN_HOLD:
            return self._finish()
        return None

    def _finish(self) -> Transition:
        self.finished = True
        transition = post_battle_transition(self.glue_scene, self.effect)
        if transition is not None:
            return transition
        self.glue_scene.resolve_debrief(self.effect)
        return Transition(self.glue_scene, "end screen closed")
