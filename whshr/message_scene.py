"""An OK-only error box (``notes/native-windows.md`` section 8.3.8-8.3.9).

The original reports a failed save or load in a system message box with the caption "Error" and one OK
button, and carries on afterwards. The scene shows ``caption`` and ``text`` and, on ``"ok"`` (or Esc/Enter in
the view), moves on to ``next_scene``.
"""

from typing import Any

from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .scenes import Scene, SceneAssets, SceneEvent, Transition


class MessageScene(Scene):
    def __init__(self, next_scene: Scene, caption: str, text: str) -> None:
        self.next_scene = next_scene
        self.caption = caption
        self.text = text
        self.context: SceneAssets | None = None

    def enter(self, context: SceneAssets) -> None:
        self.context = context

    def font(self, slot: int) -> Any:
        """One glue font slot, loaded through the scene's assets (for the view)."""
        if self.context is None:
            raise RuntimeError("the message box has not been entered")
        return self.context.load(glue_font_asset(slot))

    def glue_content(self) -> GlueContent:
        if self.context is None:
            raise RuntimeError("the message box has not been entered")
        return self.context.glue_content()

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | None:
        if event == "ok":
            return Transition(self.next_scene, "message dismissed")
        return None
