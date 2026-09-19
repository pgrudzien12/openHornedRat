"""Dietrich's caravan campaign hub and the reading/talking close-ups."""

from pathlib import Path

import pygame

from .bitmap_font import BitmapFont
from .gpu import ScreenQuad
from .scene_view import SceneView


COLOR_KEY = (0, 0, 255)  # palette index 0: the transparent colour of glue sprites


class CaravanView(SceneView):
    """Present the original caravan artwork at its native 640×480 composition."""

    NATIVE_SIZE = (640, 480)
    ART_DIR = Path(__file__).resolve().parents[2] / "extracted/pe_resources/BITMAP/bitmap"
    CANDLE_POS = (184, 160)
    LAMP_POS = (232, 96)
    HINT_BOTTOM_MARGIN = 10
    ANIMATION_FPS = 8
    PAGE_HOLD_SECONDS = 3.0
    BLINK_PERIOD_SECONDS = 2.0
    SCROLLS = ((pygame.Rect(521, 271, 28, 28), "CARSCROLL1.png"),
               (pygame.Rect(556, 279, 28, 28), "CARSCROLL2.png"),
               (pygame.Rect(521, 314, 28, 28), "CARSCROLL3.png"))
    # WND resource target -> engine event. Rectangles and hint ids remain in
    # WND; only the bridge to implemented engine actions lives here.
    TARGET_ACTIONS = {
        "abortgame": "exit_campaign",
        "armybook": "browse_book:troop roster",
        "encyclopediabook": "browse_book:bestiary",
        "loadsavewindow": "save_campaign",
        "magicbook": "browse_book:magic",
        "popcontext": "open_mission_map",
    }
    NO_TARGET_ACTIONS = {155: "speak_to_dietrich"}

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.read_background = self._load_quad(gpu, "READBACKGROUNDPIC.png")
        self.talk_background = self._load_quad(gpu, "TALKBACKGROUNDPIC.png")
        self.scrolls = [self._load_quad(gpu, filename, colorkey=True) for _, filename in self.SCROLLS]
        self.candles = [self._load_quad(gpu, f"CARCANDLECELL{index}.png") for index in range(6)]
        self.lamps = [self._load_quad(gpu, f"CARLAMPCELL{index}.png") for index in range(6)]
        self.read_books = [self._load_quad(gpu, f"DIETBOOKCELL{index}.png") for index in range(12)]
        self.read_eyes = [self._load_quad(gpu, f"READEYESCELL{index}.png") for index in range(3)]
        self.talk_mouths = [self._load_quad(gpu, f"DIETMOUTHCELL{index}.png") for index in range(6)]
        self.talk_eyes = [self._load_quad(gpu, f"TALKEYESCELL{index}.png") for index in range(3)]
        self.elapsed = 0.0
        self.hover = None
        # PCSUBT is taller than the old temporary tooltip canvas; leave room
        # for its entire descender row before scaling it with the artwork.
        self.hint = gpu.text((640, 32), BitmapFont(scene.font), color=(220, 30, 30),
                             background=None, padding=0, align="center", fixed_width=True)

    @classmethod
    def _load_quad(cls, gpu, filename, colorkey=False):
        path = cls.ART_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"caravan artwork not found: {path}; run the resource extractor into extracted/"
            )
        surface = pygame.image.load(str(path))
        if colorkey:
            surface = surface.convert()
            surface.set_colorkey(COLOR_KEY)
            surface = surface.convert_alpha()
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

    def _hotspot_at(self, point):
        """Return the topmost WND-defined caravan hotspot under a native point."""
        for hotspot in reversed(self.scene.campaign.hotspots):
            if {"x", "y", "vx", "vy"} <= hotspot.keys() and pygame.Rect(
                    hotspot["x"], hotspot["y"], hotspot["vx"], hotspot["vy"]
            ).collidepoint(point):
                return hotspot
        return None

    def _hint(self, hint_id, *format_args):
        """Read tooltip text from BRTXT; presentation never embeds original English."""
        return self.scene.campaign.hint(hint_id, *format_args)

    def _hub_action_at(self, pos):
        hotspot = self._hotspot_at(self._native_point(pos))
        if hotspot is None:
            return None
        target = hotspot.get("target", "").lower()
        action = ("open_mission_map" if target.startswith("flowscript")
                  else self.TARGET_ACTIONS.get(target, self.NO_TARGET_ACTIONS.get(hotspot.get("res"))))
        if action == "open_mission_map" and (not self.scene.can_select_mission or not self.scene.missions):
            return None
        return action

    def _set_hover(self, pos):
        hotspot = self._hotspot_at(self._native_point(pos))
        hint_id = 402 if hotspot and hotspot.get("res") == -1 else (hotspot or {}).get("res")
        self.hover = self._hint(hint_id, self.scene.gold) if hint_id is not None else None
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

    def _page_frame(self):
        """Turn DIETBOOKCELL11 down to 0, then leave the new page visible."""
        turn_seconds = len(self.read_books) / self.ANIMATION_FPS
        phase = self.elapsed % (turn_seconds + self.PAGE_HOLD_SECONDS)
        if phase < turn_seconds:
            return len(self.read_books) - 1 - int(phase * self.ANIMATION_FPS)
        return 0

    def _read_eye_frame(self):
        """READEYESCELL2 -> 1 -> 0 is one blink; the open-eye frame rests between blinks."""
        phase = self.elapsed % self.BLINK_PERIOD_SECONDS
        frame = int(phase * self.ANIMATION_FPS)
        return len(self.read_eyes) - 1 - frame if frame < len(self.read_eyes) else 0

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        width, height = self.NATIVE_SIZE[0] * scale, self.NATIVE_SIZE[1] * scale
        frame = int(self.elapsed * self.ANIMATION_FPS)
        page_frame = self._page_frame()
        eye_frame = self._read_eye_frame()
        if self.scene.dietrich_mode == "reading":
            self.read_background.draw(left, top, width, height)
            self.read_books[page_frame].draw(
                left + 296 * scale, top + 260 * scale, 148 * scale, 108 * scale
            )
            self.read_eyes[eye_frame].draw(
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
        self.read_books[page_frame].draw(
            left + 296 * scale, top + 260 * scale, 148 * scale, 108 * scale
        )
        self.read_eyes[eye_frame].draw(
            left + 312 * scale, top + 208 * scale, 44 * scale, 16 * scale
        )
        self.candles[frame % len(self.candles)].draw(
            left + self.CANDLE_POS[0] * scale, top + self.CANDLE_POS[1] * scale, 24 * scale, 48 * scale
        )
        self.lamps[frame % len(self.lamps)].draw(
            left + self.LAMP_POS[0] * scale, top + self.LAMP_POS[1] * scale, 8 * scale, 16 * scale
        )
        # CarScroll3/2/1 appear at 2/3/4 offered missions (WND ``[BITMAP] set:depend``).
        for index in range(len(self.SCROLLS) - 1, len(self.SCROLLS) - 1 - self.scene.scroll_count, -1):
            rect = self.SCROLLS[index][0]
            self.scrolls[index].draw(left + rect.x * scale, top + rect.y * scale,
                                     rect.width * scale, rect.height * scale)
        if self.hover:
            _, hint_height = self.hint.text_size
            self.hint.draw(left, top + height - (hint_height + self.HINT_BOTTOM_MARGIN) * scale,
                           width, self.hint.size[1] * scale)

    def release(self):
        for quad in (
            self.read_background, self.talk_background, *self.scrolls, *self.candles, *self.lamps,
            *self.read_books, *self.read_eyes, *self.talk_mouths, *self.talk_eyes,
        ):
            quad.release()
        self.hint.release()
