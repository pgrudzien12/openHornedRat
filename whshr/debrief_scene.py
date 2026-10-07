"""Debrief scene: shows the post-battle pages of :class:`whshr.debrief_screen.DebriefScreen` and, on Done (or at
once when the evaluator has nothing to show), applies the completion and resumes the glue script that asked
for it (notes/native-windows.md section 9, issue #123)."""

from typing import Any

from .casualties import commit_wounded
from .debrief import report_for
from .debrief_screen import DebriefScreen
from .glue import MissionRef
from .glue_runtime import StartDebrief
from .glue_scene import GlueScene
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
            self._mission_name_id(), self._string, bonus_counter=campaign.bonus_counter)
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
        if self.screen is not None and event == "page:next":
            self.screen.next()
        elif self.screen is not None and event == "page:back":
            self.screen.back()
        return None

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        if not self.finished and (self.screen is None or self.screen.will_skip()):
            return self._complete()
        return None

    def _complete(self) -> Transition:
        self.finished = True
        self.glue_scene.resolve_debrief(self.effect)
        return Transition(self.glue_scene, "debrief done")
