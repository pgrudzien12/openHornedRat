"""Three audio controls, the engine difficulty level (whshr.difficulty) and, on an installation with MP3 music, the
music source (whshr.music_source) in the original Options window layout."""

from typing import Any

from .audio_settings import CHANNELS, LEVELS, audio_settings
from .difficulty import LEVELS as DIFFICULTY_LEVELS, difficulty_setting
from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .music_source import SOURCES as MUSIC_SOURCES, has_mp3_music, music_source_setting
from .scenes import Scene, SceneAssets, SceneEvent, Transition


class OptionsScene(Scene):
    def __init__(self, parent: Scene) -> None:
        self.parent = parent
        self.values = {name: 100 for name in CHANNELS}
        self.difficulty = difficulty_setting.level
        self.music_source = music_source_setting.source
        self.mp3_music = False  # the music source control is offered only when the installation has MP3 music
        self.context: SceneAssets | None = None
        self.error: str | None = None

    def enter(self, context: SceneAssets) -> None:
        self.context = context
        audio_settings.configure(getattr(context, "save_dir", None))
        self.values = audio_settings.values.copy()
        save_dir = getattr(context, "save_dir", None)
        if save_dir is not None:
            difficulty_setting.configure(save_dir)
            music_source_setting.configure(save_dir)
        self.difficulty = difficulty_setting.level
        self.music_source = music_source_setting.source
        self.mp3_music = has_mp3_music(context.glue_content().installation)

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | None:
        if isinstance(event, tuple) and len(event) == 2 and event[0] == "options:cycle":
            name = event[1]
            if name in CHANNELS:
                current = LEVELS.index(self.values[name])
                self.values[name] = LEVELS[(current + 1) % len(LEVELS)]
            elif name == "difficulty":
                current = DIFFICULTY_LEVELS.index(self.difficulty)
                self.difficulty = DIFFICULTY_LEVELS[(current + 1) % len(DIFFICULTY_LEVELS)]
            elif name == "music_source" and self.mp3_music:
                current = MUSIC_SOURCES.index(self.music_source)
                self.music_source = MUSIC_SOURCES[(current + 1) % len(MUSIC_SOURCES)]
        elif event == "options:cancel":
            return Transition(self.parent, "options cancelled")
        elif event == "options:ok":
            try:
                audio_settings.save(self.values)
                difficulty_setting.save(self.difficulty)
                if self.mp3_music:
                    music_source_setting.save(self.music_source)
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
