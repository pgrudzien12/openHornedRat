"""Scene view registry: which view presents which scene type."""

import pygame

from ..battle_scene import BattleScene
from ..campaign_scenes import IntroScene
from .battle_view import BattleView
from .scene_view import PlaceholderView


class IntroView(PlaceholderView):
    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options, "press a key or click to skip")

    def events(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            return ("skip",)
        return ()

    def status(self):
        return (f"intro {self.scene.elapsed_seconds:.1f}/{self.scene.duration_seconds:.1f} s",)


VIEWS = {IntroScene: IntroView, BattleScene: BattleView}


def view_for(gpu, scene, options=None):
    return VIEWS.get(type(scene), PlaceholderView)(gpu, scene, options)
