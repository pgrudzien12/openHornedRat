# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Base scene views: a view draws one scene instance and translates raw input into its scene events."""
from collections.abc import Sequence
from typing import Any

import pygame

from ..scenes import Scene, SceneEvent
from .cursors import CursorController
from .gpu import Gpu


class SceneView[S: Scene]:
    """Base view. A view owns GPU resources for one scene instance and releases them when replaced."""

    background: tuple[int, int, int] = (18, 18, 24)

    def __init__(self, gpu: Gpu, scene: S, options: dict[str, Any] | None = None) -> None:
        self.gpu = gpu
        self.scene = scene
        self.options = options or {}

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        """Return the scene events produced by one pygame event."""
        return ()

    def refresh(self) -> None:
        """Rebuild presentation state after the scene changed underneath the view (default: nothing to do)."""

    def animate(self, seconds: float) -> None:
        """Advance presentation-only state (camera, animation clocks) by the frame duration."""

    def status(self) -> Sequence[str]:
        """Extra debug overlay lines."""
        return ()

    def draw(self) -> None:
        self.gpu.target.clear(self.background)

    def release(self) -> None:
        """Release GPU resources owned by this view."""


class NativeScreenView[S: Scene](SceneView[S]):
    """A view that presents a fixed 640x480 original screen, centered and scaled to the window.

    The scale is snapped to an integer so every original-game pixel is blown up by a whole
    number of screen pixels: nearest-neighbor magnification at a fractional scale duplicates
    source pixels unevenly and visibly distorts the small hand-drawn bitmap fonts (see
    notes/fonts_glue.md). Snapping trades that distortion for letterboxing when the window
    isn't an exact multiple of the native size, which keeps every resolution pixel-perfect.
    """

    NATIVE_SIZE = (640, 480)

    def __init__(self, gpu: Gpu, scene: S, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        # Every native screen starts on the game's default cursor (the sword); views with cursor rules of their own
        # (glue hotspots, troop selection) replace this controller with theirs.
        self.cursors = CursorController(self.options.get("installation"))
        self.cursors.show(None)

    def _layout(self) -> tuple[float, float, float]:
        screen_width, screen_height = self.gpu.target.size
        native_width, native_height = self.NATIVE_SIZE
        exact = min(screen_width / native_width, screen_height / native_height)
        scale = max(1, round(exact))
        while scale > 1 and (native_width * scale > screen_width or native_height * scale > screen_height):
            scale -= 1
        if native_width * scale > screen_width or native_height * scale > screen_height:
            # The window is smaller than the native screen even at 1x: shrink to fit exactly
            # instead of clipping. Below-native windows are rare (small capture sizes); pixel
            # snapping only matters once there is room to snap to.
            scale = exact
        return ((screen_width - native_width * scale) / 2,
                (screen_height - native_height * scale) / 2, scale)


class PlaceholderView(SceneView[Scene]):
    """Names a scene whose real presentation is not implemented yet."""

    def __init__(self, gpu: Gpu, scene: Scene, options: dict[str, Any] | None = None, hint: str = "") -> None:
        super().__init__(gpu, scene, options)
        self.label = gpu.text((720, 120), gpu.title_font, background=None)
        self.label.set_lines((type(scene).__name__, hint))

    def draw(self) -> None:
        super().draw()
        (width, height), (text_width, text_height) = self.gpu.target.size, self.label.text_size
        self.label.draw((width - text_width) // 2, (height - text_height) // 2)

    def release(self) -> None:
        self.label.release()
