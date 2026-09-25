# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Pygame adapter for the original 1-bit Windows FNT game fonts."""

from collections.abc import Sequence
from typing import Any

import pygame


class BitmapFont:
    """Expose a parsed ``fon_parse.Font`` through pygame's small font API."""

    def __init__(self, font: Any) -> None:  # a parsed fon_parse.Font
        self.font = font

    def size(self, text: str) -> tuple[int, int]:
        return sum(self.font.glyphs[self.font.code_for(ch)].width for ch in text), self.font.height

    def render(self, text: str, _antialias: bool, color: Sequence[int]) -> pygame.Surface:
        width, height, pixels = self.font.render(text)
        surface = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
        for y in range(height):
            for x in range(width):
                if pixels[y * width + x]:
                    surface.set_at((x, y), color)
        return surface
