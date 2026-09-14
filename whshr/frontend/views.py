"""Scene views: draw a presentation-independent scene and translate raw input into its scene events."""

import pygame

from ..campaign_scenes import IntroScene


class SceneView:
    """Base view. A view owns GPU resources for one scene instance and releases them when replaced."""

    background = (18, 18, 24)

    def __init__(self, gpu, scene):
        self.gpu = gpu
        self.scene = scene

    def events(self, event):
        """Return the scene events produced by one pygame event."""
        return ()

    def status(self):
        """Extra debug overlay lines."""
        return ()

    def draw(self):
        self.gpu.target.clear(self.background)

    def release(self):
        """Release GPU resources owned by this view."""


class PlaceholderView(SceneView):
    """Names a scene whose real presentation is not implemented yet."""

    def __init__(self, gpu, scene, hint=""):
        super().__init__(gpu, scene)
        self.label = gpu.text((720, 120), gpu.title_font, background=None)
        self.label.set_lines((type(scene).__name__, hint))

    def draw(self):
        super().draw()
        (width, height), (text_width, text_height) = self.gpu.target.size, self.label.text_size
        self.label.draw((width - text_width) // 2, (height - text_height) // 2)

    def release(self):
        self.label.release()


class IntroView(PlaceholderView):
    def __init__(self, gpu, scene):
        super().__init__(gpu, scene, "press a key or click to skip")

    def events(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            return ("skip",)
        return ()

    def status(self):
        return (f"intro {self.scene.elapsed_seconds:.1f}/{self.scene.duration_seconds:.1f} s",)


VIEWS = {IntroScene: IntroView}


def view_for(gpu, scene):
    return VIEWS.get(type(scene), PlaceholderView)(gpu, scene)
