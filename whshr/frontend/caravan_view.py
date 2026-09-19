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
        ("magic", pygame.Rect(0, 246, 164, 46)),
        ("troop roster", pygame.Rect(0, 299, 164, 47)),
        ("bestiary", pygame.Rect(0, 349, 180, 42)),
    )
    GOLD_RECT = pygame.Rect(235, 360, 95, 55)
    MISSION_RECT = pygame.Rect(480, 250, 160, 110)
    DIETRICH_RECT = pygame.Rect(270, 150, 95, 110)
    EXIT_RECT = pygame.Rect(0, 0, 244, 171)
    SAVE_RECT = pygame.Rect(450, 85, 190, 180)
    SCROLLS = ((pygame.Rect(521, 271, 28, 28), "CARSCROLL1.png"),
               (pygame.Rect(556, 279, 28, 28), "CARSCROLL2.png"),
               (pygame.Rect(521, 314, 28, 28), "CARSCROLL3.png"))

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.read_background = self._load_quad(gpu, "READBACKGROUNDPIC.png")
        self.talk_background = self._load_quad(gpu, "TALKBACKGROUNDPIC.png")
        self.scrolls = [self._load_quad(gpu, filename) for _, filename in self.SCROLLS]
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

    def _hotspot_rect(self, hint_id, fallback):
        """Use the original WND hotspot geometry, retaining a test fallback."""
        hotspot = self.scene.campaign.hotspot(hint_id)
        if hotspot is None:
            return fallback
        return pygame.Rect(hotspot["x"], hotspot["y"], hotspot["vx"], hotspot["vy"])

    def _hint(self, hint_id, *format_args):
        text = self.scene.campaign.hint(hint_id, *format_args)
        return text or ({150: "Click here to select mission.", 151: "Click here to view Troop Roster.",
                         152: "Click here to view Battle Bestiary.", 157: "Click here to Save game.",
                         158: "Click here to view Magic Book.", 159: "Click here to Abort Campaign.",
                         160: "Click here to talk to Dietrich.",
                         402: f"We have {self.scene.gold} gold crowns."}[hint_id])

    def _hub_action_at(self, pos):
        point = self._native_point(pos)
        for index, (rect, _filename) in enumerate(self.SCROLLS[:len(self.scene.missions)]):
            if rect.collidepoint(point):
                return f"select_mission:{index}"
        if self._hotspot_rect(150, self.MISSION_RECT).collidepoint(point):
            return "select_mission:0" if self.scene.missions else None
        if self._hotspot_rect(-1, self.GOLD_RECT).collidepoint(point):
            return None
        for name, rect in self.BOOKS:
            hint_id = {"magic": 158, "troop roster": 151, "bestiary": 152}[name]
            if self._hotspot_rect(hint_id, rect).collidepoint(point):
                return f"browse_book:{name}"
        if self._hotspot_rect(159, self.EXIT_RECT).collidepoint(point):
            return "exit_campaign"
        if self._hotspot_rect(157, self.SAVE_RECT).collidepoint(point):
            return "save_campaign"
        if self._hotspot_rect(160, self.DIETRICH_RECT).collidepoint(point):
            return "speak_to_dietrich"
        return None

    def _set_hover(self, pos):
        point = self._native_point(pos)
        self.hover = None
        if self._hotspot_rect(-1, self.GOLD_RECT).collidepoint(point):
            self.hover = self._hint(402, self.scene.gold)
        for index, (rect, _filename) in enumerate(self.SCROLLS[:len(self.scene.missions)]):
            if rect.collidepoint(point):
                self.hover = self._hint(150)
        if self.hover is None:
            for name, fallback in self.BOOKS:
                hint_id = {"magic": 158, "troop roster": 151, "bestiary": 152}[name]
                if self._hotspot_rect(hint_id, fallback).collidepoint(point):
                    self.hover = self._hint(hint_id)
                    break
        if self.hover is None:
            for hint_id, fallback in ((150, self.MISSION_RECT), (157, self.SAVE_RECT),
                                      (159, self.EXIT_RECT), (160, self.DIETRICH_RECT)):
                if self._hotspot_rect(hint_id, fallback).collidepoint(point):
                    self.hover = self._hint(hint_id)
                    break
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
        self.read_background.draw(left, top, width, height)
        self.read_books[frame % len(self.read_books)].draw(
            left + 296 * scale, top + 260 * scale, 148 * scale, 108 * scale
        )
        self.read_eyes[frame % len(self.read_eyes)].draw(
            left + 312 * scale, top + 208 * scale, 44 * scale, 16 * scale
        )
        self.candles[frame % len(self.candles)].draw(
            left + self.CANDLE_POS[0] * scale, top + self.CANDLE_POS[1] * scale, 24 * scale, 48 * scale
        )
        self.lamps[frame % len(self.lamps)].draw(
            left + self.LAMP_POS[0] * scale, top + self.LAMP_POS[1] * scale, 8 * scale, 16 * scale
        )
        for index, (rect, _filename) in enumerate(self.SCROLLS[:len(self.scene.missions)]):
            self.scrolls[index].draw(left + rect.x * scale, top + rect.y * scale,
                                     rect.width * scale, rect.height * scale)
        if self.hover:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            self.hint.draw(mouse_x + 12, mouse_y + 12)

    def release(self):
        for quad in (
            self.read_background, self.talk_background, *self.scrolls, *self.candles, *self.lamps,
            *self.read_books, *self.read_eyes, *self.talk_mouths, *self.talk_eyes,
        ):
            quad.release()
        self.hint.release()
