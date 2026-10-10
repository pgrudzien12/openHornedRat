"""Original Options backdrop with engine audio level controls."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..audio_settings import CHANNELS, audio_settings
from ..glue_palette import AppPalette
from ..options_scene import OptionsScene
from ..scenes import SceneEvent
from .dialog_view import DialogView
from .gpu import Gpu

WHITE = (255, 255, 255)
BUTTON_SIZE = (41, 41)
ROWS = tuple((name, 203, 106 + index * 54) for index, name in enumerate(CHANNELS))
EXITS = (("options:ok", 203, 335), ("options:cancel", 397, 335))
LABELS = {"music": "Music", "dialogue": "Dialogue", "effects": "Sound Effects"}


class OptionsView(DialogView[OptionsScene]):
    def __init__(self, gpu: Gpu, scene: OptionsScene, options: dict[str, Any] | None = None) -> None:
        content = scene.content()
        super().__init__(gpu, scene, content, scene.font(), -1, options)
        self.palette = AppPalette.select(-1, content.palette_tables(),
                                         embedded=content.bitmap_data("MoreOptionScreen").palette)
        self.pressed: str | None = None
        self.drawn: tuple[Any, ...] | None = None
        self.refresh()

    def _label(self, value: str, x: int, y: int, width: int, align: str) -> None:
        text_width = min(width, self.font.size(value)[0])
        if align == "right":
            x += width - text_width
        label = self.gpu.text((max(1, text_width), self.font.font.height), self.font, color=WHITE,
                              background=None, padding=0)
        label.set_lines((value,))
        self.labels.append((label, (x, y + (41 - self.font.font.height) // 2)))

    def refresh(self) -> None:
        state = (tuple(self.scene.values.items()), self.pressed, self.scene.error)
        if state == self.drawn:
            return
        self.drawn = state
        self._release_contents()
        self._bitmap("MoreOptionScreen", (0, 0))
        for name, x, y in ROWS:
            self._bitmap("OptionButtonDown" if self.pressed == name else "OptionButtonUp", (x, y))
            value = self.scene.values[name]
            self._label(f"{LABELS[name]}: {'Off' if value == 0 else f'{value}%'}", 0, y, 190, "right")
            self.buttons.append((pygame.Rect(x, y, *BUTTON_SIZE), name))
        for action, x, y in EXITS:
            self._bitmap("OptionButtonDown" if self.pressed == action else "OptionButtonUp", (x, y))
            self.buttons.append((pygame.Rect(x, y, *BUTTON_SIZE), action))
        if self.scene.error:
            self._label("Could not save options", 450, 268, 190, "left")

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return ("options:cancel",)
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return ("options:ok",)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._action_at(event.pos)
            if self.pressed is not None:
                self._click_cue(4)
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, self.pressed = self.pressed, None
            self.refresh()
            if pressed is not None and pressed == self._action_at(event.pos):
                self._click_cue(3)
                return (("options:cycle", pressed),) if pressed in CHANNELS else (pressed,)
        return ()

    def release(self) -> None:
        if pygame.mixer.get_init():
            try:
                pygame.mixer.music.set_volume(audio_settings.volume("music"))
            except pygame.error:
                pass
        super().release()
