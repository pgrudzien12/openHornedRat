"""Text-only opening narration before the first cutscene."""

import pygame

from .bitmap_font import BitmapFont
from .scene_view import SceneView


class OpeningNarrationView(SceneView):
    """Present the original ANTXT prologue in the original SUBTEXT face."""

    NATIVE_WIDTH = 500

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.font = BitmapFont(scene.subtitle_font)
        self.body = gpu.text((self.NATIVE_WIDTH, 180), self.font, color=(255, 250, 225),
                             background=None, padding=0, align="center")
        self.body.set_lines(self._wrap(scene.text))

    def _wrap(self, text):
        words, lines, current = text.split(), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or self.font.size(candidate)[0] <= self.NATIVE_WIDTH:
                current = candidate
            else:
                lines.append(current)
                current = word
        return (*lines, current) if current else tuple(lines)

    def events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            return ("continue",)
        if event.type == pygame.KEYDOWN:
            return ("continue",)
        return ()

    def draw(self):
        super().draw()
        screen_width, screen_height = self.gpu.target.size
        text_width, text_height = self.body.text_size
        # SUBTEXT's native lowercase x-height is 11 pixels.  Draw its raster
        # at 1:1: scaling would widen the glyphs as well as making the text
        # visibly softer than the original text-only screen.
        self.body.draw((screen_width - text_width) / 2,
                       (screen_height - text_height) / 2)

    def release(self):
        self.body.release()
