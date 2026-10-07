"""Three audio controls in the original Options window layout."""

from typing import Any

from .audio_settings import CHANNELS, LEVELS, audio_settings
from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .scenes import Scene, SceneAssets, SceneEvent, Transition


class OptionsScene(Scene):
    def __init__(self, parent: Scene) -> None:
        self.parent = parent
        self.values = {name: 100 for name in CHANNELS}
        self.context: SceneAssets | None = None
        self.error: str | None = None

    def enter(self, context: SceneAssets) -> None:
        self.context = context
        audio_settings.configure(getattr(context, "save_dir", None))
        self.values = audio_settings.values.copy()

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | None:
        if isinstance(event, tuple) and len(event) == 2 and event[0] == "options:cycle":
            name = event[1]
            if name in CHANNELS:
                current = LEVELS.index(self.values[name])
                self.values[name] = LEVELS[(current + 1) % len(LEVELS)]
        elif event == "options:cancel":
            return Transition(self.parent, "options cancelled")
        elif event == "options:ok":
            try:
                audio_settings.save(self.values)
            except OSError as error:
                self.error = str(error)
                return None
            return Transition(self.parent, "options saved")
        return None

    def content(self) -> GlueContent:
        if self.context is None:
            raise RuntimeError("options scene has not been entered")
        return self.context.glue_content()

    def font(self) -> Any:
        if self.context is None:
            raise RuntimeError("options scene has not been entered")
        return self.context.load(glue_font_asset(6))
