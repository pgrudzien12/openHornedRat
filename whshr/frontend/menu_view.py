"""Main menu and mission briefing views."""

import pygame

from .bitmap_font import BitmapFont
from .gpu import ScreenQuad
from .glue_bitmap import load_bitmap
from .scene_view import SceneView


def _wrap(font, text, max_width):
    """Split ``text`` into lines that each fit ``max_width`` pixels in ``font``."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class MainMenuView(SceneView):
    """The original OPTIONSCREEN menu, with its paired round button sprites."""

    NATIVE_SIZE = (640, 480)

    # Only the campaign flow's New Campaign and Exit actions have scene
    # implementations today.  The other original controls still react visually.
    SHORTCUTS = {pygame.K_n: "new_campaign", pygame.K_RETURN: "new_campaign",
                 pygame.K_KP_ENTER: "new_campaign", pygame.K_q: "quit", pygame.K_ESCAPE: "quit"}
    TARGET_ACTIONS = {"newgame": "new_campaign", "exitprocess": "quit"}

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.screen = self._load_quad(gpu, "OPTIONSCREEN.png")
        self.button_up = self._load_quad(gpu, "OPTIONBUTTONUP.png", transparent_blue=True)
        self.button_down = self._load_quad(gpu, "OPTIONBUTTONDOWN.png", transparent_blue=True)
        self.hotspots = tuple((scene.menu_ui or {}).get("hotspots", ()))
        self.pressed = None

    def _load_quad(self, gpu, filename, transparent_blue=False):
        """Read a cached extractor PNG into a GPU texture.

        The two button resources use pure blue as a legacy chroma key rather
        than PNG alpha, so turn that colour transparent before upload.
        """
        surface = load_bitmap(self.scene.installation, filename.removesuffix(".png"))
        width, height = surface.get_size()
        rgba = bytearray(pygame.image.tobytes(surface, "RGBA"))
        if transparent_blue:
            for offset in range(0, len(rgba), 4):
                if rgba[offset:offset + 3] == b"\x00\x00\xff":
                    rgba[offset + 3] = 0
        quad = ScreenQuad(gpu, (width, height))
        quad.write(rgba)
        return quad

    def _layout(self):
        """Return the centered, aspect-preserving original-screen rectangle."""
        screen_width, screen_height = self.gpu.target.size
        native_width, native_height = self.NATIVE_SIZE
        scale = min(screen_width / native_width, screen_height / native_height)
        width, height = native_width * scale, native_height * scale
        return (screen_width - width) / 2, (screen_height - height) / 2, scale

    def _button_at(self, pos):
        left, top, scale = self._layout()
        native_x, native_y = ((pos[0] - left) / scale, (pos[1] - top) / scale)
        for index, hotspot in enumerate(self.hotspots):
            if pygame.Rect(hotspot["x"], hotspot["y"], hotspot["vx"], hotspot["vy"]).collidepoint(native_x, native_y):
                return index
        return None

    def events(self, event):
        if event.type == pygame.KEYDOWN:
            action = self.SHORTCUTS.get(event.key)
            if action:
                return (action,)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._button_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            index, self.pressed = self.pressed, None
            if index is not None and index == self._button_at(event.pos):
                action = self.TARGET_ACTIONS.get(self.hotspots[index].get("target", "").lower())
                return (action,) if action else ()
        return ()

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        self.screen.draw(left, top, self.NATIVE_SIZE[0] * scale, self.NATIVE_SIZE[1] * scale)
        for index, hotspot in enumerate(self.hotspots):
            sprite = self.button_down if index == self.pressed else self.button_up
            sprite.draw(left + hotspot["x"] * scale, top + hotspot["y"] * scale,
                        hotspot["vx"] * scale, hotspot["vy"] * scale)

    def release(self):
        self.screen.release()
        self.button_up.release()
        self.button_down.release()


class BriefingView(SceneView):
    """Shows the mission title and spoken briefing lines; Start Battle enters the battle itself."""

    BODY_SIZE = (900, 480)
    BODY_WIDTH = 860

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        briefing = scene.briefing
        self.font = BitmapFont(scene.font)
        self.title = gpu.text((900, 24), self.font, background=None)
        self.title.set_lines((briefing["title"],))
        wrapped = []
        for line in briefing["lines"]:
            wrapped.extend(_wrap(self.font, line["text"], self.BODY_WIDTH))
            wrapped.append("")
        self.body = gpu.text(self.BODY_SIZE, self.font)
        self.body.set_lines(wrapped)
        self.hint = gpu.text((640, 20), self.font, background=None)
        self.hint.set_lines(("Press Enter or click to start the battle",))

    def events(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return ("start_battle",)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return ("start_battle",)
        return ()

    def status(self):
        return (f"briefing {self.scene.battle_id}, {len(self.scene.briefing['lines'])} lines",)

    def draw(self):
        super().draw()
        width, height = self.gpu.target.size
        self.title.draw((width - self.title.text_size[0]) // 2, 40)
        self.body.draw((width - self.BODY_SIZE[0]) // 2, 120)
        self.hint.draw((width - self.hint.text_size[0]) // 2, height - 60)

    def release(self):
        self.title.release()
        self.body.release()
        self.hint.release()
