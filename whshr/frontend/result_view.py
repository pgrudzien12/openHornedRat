"""Battle result view: title (Victory/Defeat) and a short casualty summary; any key or click dismisses it."""
import pygame

from .scene_view import SceneView

TITLES = {"victory": "Victory!", "defeat": "Defeat..."}


class ResultView(SceneView):
    """Shows `whshr.result_scene.ResultScene`'s outcome; dismissing it returns to the glue program that started the battle, or to the main menu."""

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.title = gpu.text((900, 70), gpu.title_font, background=None)
        self.title.set_lines((TITLES.get(scene.result, scene.result),))
        self.body = gpu.text((700, 400), gpu.small_font)
        self.body.set_lines(tuple(scene.summary))
        self.hint = gpu.text((640, 40), gpu.small_font, background=None)
        target = "continue the campaign" if scene.glue_scene is not None else "return to the main menu"
        self.hint.set_lines((f"Press any key or click to {target}",))

    def events(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            return ("continue",)
        return ()

    def draw(self):
        super().draw()
        width, height = self.gpu.target.size
        self.title.draw((width - self.title.text_size[0]) // 2, 130)
        self.body.draw((width - self.body.text_size[0]) // 2, 230)
        self.hint.draw((width - self.hint.text_size[0]) // 2, height - 60)

    def release(self):
        self.title.release()
        self.body.release()
        self.hint.release()
