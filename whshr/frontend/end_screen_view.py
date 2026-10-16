# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The end picture after a campaign battle (notes/native-windows.md 9.3.1 (b)): one 640x480 ``BITMAP.DLL`` picture
drawn with its own palette; a left-button release or Enter dismisses it."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..debrief_scene import EndScreenScene
from ..scenes import SceneEvent
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, QuadCache
from .scene_view import NativeScreenView


class EndScreenView(NativeScreenView[EndScreenScene]):
    def __init__(self, gpu: Gpu, scene: EndScreenScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.quads = QuadCache(gpu)
        self.background = (0, 0, 0)
        content = scene.glue_scene.runtime.content if scene.glue_scene.runtime is not None else None
        # No application palette: the picture keeps its own colours (palette argument -1, notes/palette_selection.md).
        self.quad = self.quads.get(scene.bitmap, lambda: load_optional_bitmap(content, scene.bitmap)
                                   if content is not None else None)

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return ("dismiss",)
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return ("dismiss",)
        return ()

    def draw(self) -> None:
        super().draw()
        if self.quad is None:
            return
        left, top, scale = self._layout()
        self.quad.draw(left, top, self.quad.size[0] * scale, self.quad.size[1] * scale)

    def release(self) -> None:
        self.quads.release()
