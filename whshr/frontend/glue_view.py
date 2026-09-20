"""First generic pygame adapter for static ``GlueScene`` windows.

This is intentionally narrow: bitmap composition and hotspot hit-testing are
shared now; text, portraits and executable-owned widgets remain separate
adapters until their renderer rules are moved out of compatibility views.
"""

import pygame

from ..glue_render import build_render_model
from ..glue_runtime import GlueInput
from .glue_bitmap import load_bitmap
from .gpu import ScreenQuad
from .scene_view import NativeScreenView


class GlueView(NativeScreenView):
    """Draw static runtime windows and translate click/release hotspots."""

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.models = ()
        self.quads = []
        self.pressed = None
        self.refresh()

    def refresh(self):
        """Rebuild GPU quads after the runtime changes its active windows."""
        for quad, _ in self.quads:
            quad.release()
        self.models = tuple(build_render_model(self.scene.runtime.content, window)
                            for window in self.scene.runtime.state.windows)
        self.quads = []
        for model in self.models:
            for bitmap in model.bitmaps:
                surface = load_bitmap(self.scene.runtime.content, bitmap.name)
                quad = ScreenQuad(self.gpu, surface.get_size())
                quad.write(pygame.image.tobytes(surface, "RGBA"))
                self.quads.append((quad, (model.x + bitmap.x, model.y + bitmap.y)))

    @staticmethod
    def hotspot_at(models, point):
        """Return the last-painted hotspot at native coordinates, if any."""
        for model in reversed(models):
            for hotspot in reversed(model.hotspots):
                if pygame.Rect(model.x + hotspot.x, model.y + hotspot.y,
                               hotspot.width, hotspot.height).collidepoint(point):
                    return hotspot
        return None

    def _native_point(self, pos):
        left, top, scale = self._layout()
        return (pos[0] - left) / scale, (pos[1] - top) / scale

    def events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self.hotspot_at(self.models, self._native_point(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, self.pressed = self.pressed, None
            released = self.hotspot_at(self.models, self._native_point(event.pos))
            if pressed is not None and pressed == released:
                return (GlueInput("hotspot-release", pressed.target),)
        return ()

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)

    def release(self):
        for quad, _ in self.quads:
            quad.release()
        self.quads = []
