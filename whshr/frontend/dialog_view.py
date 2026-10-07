# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Shared drawing helpers of the native 640x480 dialogs (Load/Save, confirmation): pictures and centred
text at native coordinates, mouse points mapped back to native pixels, and release of the GPU objects."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..glue_palette import AppPalette
from ..scenes import Scene
from .bitmap_font import BitmapFont
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, QuadCache, ScreenQuad, TextLabel
from .scene_view import NativeScreenView

Point = tuple[int, int]
Rgb = tuple[int, int, int]


class DialogView[S: Scene](NativeScreenView[S]):
    """A native screen made of pictures, text labels and rectangular buttons."""

    def __init__(self, gpu: Gpu, scene: S, content: Any, font: Any, palette_index: int,
                 options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.content = content
        self.font = BitmapFont(font)
        self.palette = AppPalette.select(palette_index, content.palette_tables())
        self.bitmap_quads = QuadCache(gpu)
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self._uncached_quads: list[ScreenQuad] = []
        self.labels: list[tuple[TextLabel, Point]] = []
        self.buttons: list[tuple[pygame.Rect, str]] = []

    def _native_point(self, position: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def _action_at(self, position: Sequence[float]) -> str | None:
        point = self._native_point(position)
        return next((action for rect, action in reversed(self.buttons) if rect.collidepoint(point)), None)

    def _bitmap(self, name: str, position: Point) -> None:
        quad = self.bitmap_quads.get(name, lambda: load_optional_bitmap(self.content, name, app_palette=self.palette))
        if quad is not None:
            self.quads.append((quad, position))

    def _append(self, surface: pygame.Surface, position: Point) -> None:
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self._uncached_quads.append(quad)
        self.quads.append((quad, position))

    def _center(self, value: str, y: int, colour: Rgb, *, x: int, width: int) -> None:
        label = self.gpu.text((width, self.font.font.height), self.font, color=colour, background=None,
                              padding=0, align="center", fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def _release_contents(self) -> None:
        for quad in self._uncached_quads:
            quad.release()
        for label, _ in self.labels:
            label.release()
        self.quads, self._uncached_quads, self.labels, self.buttons = [], [], [], []

    def release(self) -> None:
        self._release_contents()
        self.bitmap_quads.release()
