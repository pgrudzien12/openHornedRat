# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Text-only opening narration before the first cutscene."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..campaign_scenes import OpeningNarrationScene
from ..scenes import SceneEvent
from .bitmap_font import BitmapFont
from .gpu import Gpu
from .scene_view import SceneView


class OpeningNarrationView(SceneView[OpeningNarrationScene]):
    """Present the original ANTXT prologue in the original SUBTEXT face."""

    NATIVE_WIDTH = 500

    def __init__(self, gpu: Gpu, scene: OpeningNarrationScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.font = BitmapFont(scene.subtitle_font)
        self.body = gpu.text((self.NATIVE_WIDTH, 180), self.font, color=(255, 250, 225),
                             background=None, padding=0, align="center")
        self.body.set_lines(self._wrap(scene.text or ""))

    def _wrap(self, text: str) -> tuple[str, ...]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or self.font.size(candidate)[0] <= self.NATIVE_WIDTH:
                current = candidate
            else:
                lines.append(current)
                current = word
        return (*lines, current) if current else tuple(lines)

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.MOUSEBUTTONDOWN:
            return ("continue",)
        if event.type == pygame.KEYDOWN:
            return ("continue",)
        return ()

    def draw(self) -> None:
        super().draw()
        screen_width, screen_height = self.gpu.target.size
        text_width, text_height = self.body.text_size
        # SUBTEXT's native lowercase x-height is 11 pixels.  Draw its raster
        # at 1:1: scaling would widen the glyphs as well as making the text
        # visibly softer than the original text-only screen.
        self.body.draw((screen_width - text_width) / 2,
                       (screen_height - text_height) / 2)

    def release(self) -> None:
        self.body.release()
