"""Main menu and mission briefing views."""

from pathlib import Path

import pygame

from .gpu import ScreenQuad
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
    # These are the top-left origins of the five left/right pairs in the original
    # 640x480 screen.  The artwork itself supplies the text and recessed wells.
    BUTTON_ROWS = (181, 233, 285, 337, 389)
    BUTTON_COLUMNS = (98, 501)
    BUTTON_SIZE = (41, 41)
    MENU_ASSET_DIR = Path(__file__).resolve().parents[2] / "extracted/pe_resources/BITMAP/bitmap"

    # Only the campaign flow's New Campaign and Exit actions have scene
    # implementations today.  The other original controls still react visually.
    BUTTONS = (("new_campaign", (pygame.K_n, pygame.K_RETURN, pygame.K_KP_ENTER)),
               (None, ()),
               (None, ()),
               (None, ()),
               ("quit", (pygame.K_q, pygame.K_ESCAPE)))

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.screen = self._load_quad(gpu, "OPTIONSCREEN.png")
        self.button_up = self._load_quad(gpu, "OPTIONBUTTONUP.png", transparent_blue=True)
        self.button_down = self._load_quad(gpu, "OPTIONBUTTONDOWN.png", transparent_blue=True)
        self.pressed = None

    @classmethod
    def _load_quad(cls, gpu, filename, transparent_blue=False):
        """Read a cached extractor PNG into a GPU texture.

        The two button resources use pure blue as a legacy chroma key rather
        than PNG alpha, so turn that colour transparent before upload.
        """
        path = cls.MENU_ASSET_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"main-menu artwork not found: {path}; run the resource extractor into extracted/"
            )
        surface = pygame.image.load(str(path))
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
        for index, row in enumerate(self.BUTTON_ROWS):
            for column in self.BUTTON_COLUMNS:
                if pygame.Rect(column, row, *self.BUTTON_SIZE).collidepoint(native_x, native_y):
                    return index
        return None

    def events(self, event):
        if event.type == pygame.KEYDOWN:
            for action, keys in self.BUTTONS:
                if event.key in keys:
                    return (action,)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._button_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            index, self.pressed = self.pressed, None
            if index is not None and index == self._button_at(event.pos):
                action = self.BUTTONS[index][0]
                return (action,) if action else ()
        return ()

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        self.screen.draw(left, top, self.NATIVE_SIZE[0] * scale, self.NATIVE_SIZE[1] * scale)
        for index, row in enumerate(self.BUTTON_ROWS):
            sprite = self.button_down if index == self.pressed else self.button_up
            for column in self.BUTTON_COLUMNS:
                sprite.draw(left + column * scale, top + row * scale,
                            self.BUTTON_SIZE[0] * scale, self.BUTTON_SIZE[1] * scale)

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
        self.title = gpu.text((900, 60), gpu.title_font, background=None)
        self.title.set_lines((briefing["title"],))
        wrapped = []
        for line in briefing["lines"]:
            wrapped.extend(_wrap(gpu.small_font, line["text"], self.BODY_WIDTH))
            wrapped.append("")
        self.body = gpu.text(self.BODY_SIZE, gpu.small_font)
        self.body.set_lines(wrapped)
        self.hint = gpu.text((640, 40), gpu.small_font, background=None)
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
