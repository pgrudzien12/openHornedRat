# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Credits page: book background, three columns of headings and names, one Done button, the intro tune.

Layout numbers are the native screen's own constants (notes/native-windows.md section 3); text and art
come from the installation at runtime.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..credits_scene import COLUMN_TOP, LINE_INDENT, TITLE_Y, TUNE, CreditsScene
from ..audio_settings import audio_settings
from ..scenes import SceneEvent
from .bitmap_font import BitmapFont
from .dialog_view import DialogView
from .glue_view import _ensure_mixer
from .gpu import Gpu

PALETTE_INDEX = 1
BLACK = (0, 0, 0)
YELLOW = (255, 255, 0)
DONE_ORIGIN, DONE_SIZE = (525, 448), (84, 32)


class CreditsView(DialogView[CreditsScene]):
    def __init__(self, gpu: Gpu, scene: CreditsScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, scene.glue_content(), scene.font(2), PALETTE_INDEX, options)
        self.bold = BitmapFont(scene.font(6))
        self.pressed = False
        self.built: bool | None = None
        self.mixer_ok = _ensure_mixer()
        self._play_tune()
        self.refresh()

    def _play_tune(self) -> None:
        installation = self.content.installation
        if not self.mixer_ok or installation is None or self.scene.tune != TUNE:
            return
        try:
            pygame.mixer.music.load(str(installation.binary_file("MUSIC", f"{TUNE}.MID")))
            pygame.mixer.music.set_volume(audio_settings.volume("music"))
            pygame.mixer.music.play(loops=-1)
        except (FileNotFoundError, AttributeError, pygame.error):
            pass

    def _stop_tune(self) -> None:
        if self.mixer_ok:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass

    def _text(self, value: str, position: tuple[int, int], font: BitmapFont) -> None:
        if not value:
            return
        label = self.gpu.text((font.size(value)[0] + 4, font.font.height), font, color=BLACK, background=None,
                              padding=0)
        label.set_lines((value,))
        self.labels.append((label, position))

    def refresh(self) -> None:
        if self.built == self.pressed:
            return
        self.built = self.pressed
        self._release_contents()
        self._bitmap("TroopBook", (0, 0))
        title = self.scene.title
        self._text(title, ((640 - self.bold.size(title)[0]) // 2, TITLE_Y), self.bold)
        column_y: dict[int, int] = {}
        for section in self.scene.sections:
            y = column_y.get(section.column_x, COLUMN_TOP)
            self._text(section.heading, (section.column_x, y), self.bold)
            y += self.bold.font.height
            for line in section.lines:
                self._text(line, (section.column_x + LINE_INDENT, y), self.font)
                y += self.font.font.height
            column_y[section.column_x] = y
        self._bitmap("GreenATab" + ("Dn0" if self.pressed else "Up"), DONE_ORIGIN)
        offset = 1 if self.pressed else 0
        label = self.scene.done_label
        self._center(label, DONE_ORIGIN[1] + (DONE_SIZE[1] - self.font.font.height) // 2 + offset, YELLOW,
                     x=DONE_ORIGIN[0] + offset, width=DONE_SIZE[0])
        self.buttons.append((pygame.Rect(*DONE_ORIGIN, *DONE_SIZE), "credits:done"))

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._action_at(event.pos) is not None
            if self.pressed:
                self._click_cue(4)
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed, self.pressed = self.pressed, False
            self.refresh()
            if was_pressed and self._action_at(event.pos) == "credits:done":
                self._click_cue(3)
                return ("credits:done",)
        return ()

    def release(self) -> None:
        self._stop_tune()
        super().release()
