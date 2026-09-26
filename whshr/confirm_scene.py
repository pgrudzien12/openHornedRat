# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""A Yes/No confirmation box, presentation-independent.

The original asks "Are you sure?" before an Abort leaves troop selection with something selected
(``notes/builtin_widgets.md`` section 4.1, ``BRTXT 308``) and before ``AbortGame`` abandons the campaign
(``notes/activity_results.md`` section 6, ``GMTXT 36070``). Yes carries on to ``yes_scene``; No returns
to ``parent`` unchanged.

Events: ``"yes"``, ``"no"``. The view resolves the question text from ``string`` ((table, id)).
"""

from collections.abc import Callable
from typing import Any

from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .scenes import Scene, SceneAssets, SceneEvent, Transition

# The box's title, as the original's message box shows it (a name, not flavour text).
TITLE = "Warhammer"
# PROVISIONAL: the original's Yes/No captions come from the operating system's message box, not a game string table.
YES_LABEL, NO_LABEL = "Yes", "No"
FALLBACK_QUESTION = "Are you sure?"


class ConfirmScene(Scene):
    def __init__(self, parent: Scene, yes_scene: Scene, string: tuple[str, int],
                 on_yes: Callable[[], None] | None = None, reason: str = "confirmed") -> None:
        self.parent = parent
        self.yes_scene = yes_scene
        self.string = string
        self.on_yes = on_yes
        self.reason = reason
        self.context: SceneAssets | None = None

    def enter(self, context: SceneAssets) -> None:
        self.context = context

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | None:
        if event == "yes":
            if self.on_yes is not None:
                self.on_yes()
            return Transition(self.yes_scene, self.reason)
        if event == "no":
            return Transition(self.parent, "not confirmed")
        return None

    @property
    def question(self) -> str:
        """The question text from the installation's string table, or a plain fallback."""
        if self.context is None:
            raise RuntimeError("the confirm scene has not been entered")
        try:
            return self.context.glue_content().string(*self.string)
        except (KeyError, FileNotFoundError, OSError):
            return FALLBACK_QUESTION

    def font(self, slot: int) -> Any:
        if self.context is None:
            raise RuntimeError("the confirm scene has not been entered")
        return self.context.load(glue_font_asset(slot))

    def glue_content(self) -> GlueContent:
        if self.context is None:
            raise RuntimeError("the confirm scene has not been entered")
        return self.context.glue_content()
