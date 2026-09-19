"""Dietrich's caravan campaign hub and the reading/talking close-ups."""

from pathlib import Path

import pygame

from .gpu import ScreenQuad
from .scene_view import SceneView


class CaravanView(SceneView):
    """Present the original caravan artwork at its native 640×480 composition."""

    NATIVE_SIZE = (640, 480)
    ART_DIR = Path(__file__).resolve().parents[2] / "extracted/pe_resources/BITMAP/bitmap"
    CANDLE_POS = (184, 160)
    LAMP_POS = (232, 96)
    BOOKS = (
        ("magic", pygame.Rect(0, 190, 166, 51)),
        ("troop roster", pygame.Rect(0, 244, 166, 48)),
        ("bestiary", pygame.Rect(0, 292, 166, 56)),
    )
    GOLD_RECT = pygame.Rect(240, 360, 132, 48)
    MISSION_RECT = pygame.Rect(296, 323, 150, 56)  # the open campaign ledger on the desk
    DIETRICH_RECT = pygame.Rect(208, 140, 205, 190)
    EXIT_RECT = pygame.Rect(55, 56, 84, 184)  # the hourglass
    SAVE_RECT = pygame.Rect(560, 270, 60, 45)  # scroll on the lower-right shelf

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.hub = self._load_quad(gpu, "CARAVAN.png")
        self.read_background = self._load_quad(gpu, "READBACKGROUNDPIC.png")
        self.talk_background = self._load_quad(gpu, "TALKBACKGROUNDPIC.png")
        self.candles = [self._load_quad(gpu, f"CARCANDLECELL{index}.png") for index in range(6)]
        self.lamps = [self._load_quad(gpu, f"CARLAMPCELL{index}.png") for index in range(6)]
        self.read_books = [self._load_quad(gpu, f"DIETBOOKCELL{index}.png") for index in range(12)]
        self.read_eyes = [self._load_quad(gpu, f"READEYESCELL{index}.png") for index in range(3)]
        self.talk_mouths = [self._load_quad(gpu, f"DIETMOUTHCELL{index}.png") for index in range(6)]
        self.talk_eyes = [self._load_quad(gpu, f"TALKEYESCELL{index}.png") for index in range(3)]
        self.elapsed = 0.0
        self.hover = None
        self.hint = gpu.text((260, 36), gpu.small_font, background=(0, 0, 0, 180))

    @classmethod
    def _load_quad(cls, gpu, filename):
        path = cls.ART_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"caravan artwork not found: {path}; run the resource extractor into extracted/"
            )
        surface = pygame.image.load(str(path))
        quad = ScreenQuad(gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        return quad

    def _layout(self):
        screen_width, screen_height = self.gpu.target.size
        native_width, native_height = self.NATIVE_SIZE
        scale = min(screen_width / native_width, screen_height / native_height)
        width, height = native_width * scale, native_height * scale
        return (screen_width - width) / 2, (screen_height - height) / 2, scale

    def _native_point(self, pos):
        left, top, scale = self._layout()
        return (pos[0] - left) / scale, (pos[1] - top) / scale

    def _hub_action_at(self, pos):
        point = self._native_point(pos)
        if self.MISSION_RECT.collidepoint(point):
            return "select_mission"
        if self.GOLD_RECT.collidepoint(point):
            return None
        for name, rect in self.BOOKS:
            if rect.collidepoint(point):
                return f"browse_book:{name}"
        if self.EXIT_RECT.collidepoint(point):
            return "exit_campaign"
        if self.SAVE_RECT.collidepoint(point):
            return "save_campaign"
        if self.DIETRICH_RECT.collidepoint(point):
            return "speak_to_dietrich"
        return None

    def _set_hover(self, pos):
        point = self._native_point(pos)
        if self.GOLD_RECT.collidepoint(point):
            self.hover = f"Gold: {self.scene.gold}"
        else:
            self.hover = None
        self.hint.set_lines((self.hover,) if self.hover else ())

    def events(self, event):
        if self.scene.dietrich_mode:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return ("dismiss_dietrich",)
            return ()
        if event.type == pygame.MOUSEMOTION:
            self._set_hover(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self._hub_action_at(event.pos)
            return (action,) if action else ()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return ("exit_campaign",)
        return ()

    def animate(self, seconds):
        self.elapsed += seconds

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        width, height = self.NATIVE_SIZE[0] * scale, self.NATIVE_SIZE[1] * scale
        frame = int(self.elapsed * 8)
        if self.scene.dietrich_mode == "reading":
            self.read_background.draw(left, top, width, height)
            self.read_books[frame % len(self.read_books)].draw(
                left + 296 * scale, top + 260 * scale, 148 * scale, 108 * scale
            )
            self.read_eyes[frame % len(self.read_eyes)].draw(
                left + 312 * scale, top + 208 * scale, 44 * scale, 16 * scale
            )
            return
        if self.scene.dietrich_mode == "talking":
            self.talk_background.draw(left, top, width, height)
            self.talk_mouths[frame % len(self.talk_mouths)].draw(
                left + 288 * scale, top + 220 * scale, 68 * scale, 48 * scale
            )
            self.talk_eyes[frame % len(self.talk_eyes)].draw(
                left + 300 * scale, top + 200 * scale, 44 * scale, 16 * scale
            )
            return
        self.hub.draw(left, top, width, height)
        self.candles[frame % len(self.candles)].draw(
            left + self.CANDLE_POS[0] * scale, top + self.CANDLE_POS[1] * scale, 24 * scale, 48 * scale
        )
        self.lamps[frame % len(self.lamps)].draw(
            left + self.LAMP_POS[0] * scale, top + self.LAMP_POS[1] * scale, 8 * scale, 16 * scale
        )
        if self.hover:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            self.hint.draw(mouse_x + 12, mouse_y + 12)

    def release(self):
        for quad in (
            self.hub, self.read_background, self.talk_background, *self.candles, *self.lamps,
            *self.read_books, *self.read_eyes, *self.talk_mouths, *self.talk_eyes,
        ):
            quad.release()
        self.hint.release()
