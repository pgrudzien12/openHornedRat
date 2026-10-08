# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Native debrief pages P2/P3/P4 (notes/native-windows.md section 9).

A renderer only: the pages, button states and every drawing position come from ``DebriefScreen``; this view
paints its drawing list on the 640x480 window and turns clicks on the Next/Back/Done buttons into scene events.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..debrief_scene import DebriefScene
from ..audio_settings import audio_settings
from ..debrief_screen import Text
from ..glue_palette import AppPalette
from ..scenes import SceneEvent
from ..script import resource_name
from .bitmap_font import BitmapFont
from .cursors import CursorController
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, QuadCache, ScreenQuad, TextLabel
from .scene_view import NativeScreenView

Point = tuple[int, int]
YELLOW, LIGHT_GREY = (255, 255, 0), (192, 192, 192)
# notes/native-windows.md 9.3.3: (action, x, bitmap prefix, BRTXT label id); Abort never exists in a debrief.
BUTTONS: tuple[tuple[str, int, str, int], ...] = (
    ("done", 325, "GreenATab", 304), ("page:back", 425, "BlueATab", 301), ("page:next", 525, "RedATab", 300))
BUTTON_Y, BUTTON_SIZE = 448, (84, 32)
LABEL_OFFSET_RELEASED, LABEL_OFFSET_PRESSED = (4, 2), (3, 3)
BACKGROUND, SKULL_CENTER_X, BANNER_X = "TroopBook", 65, 80
DEFAULT_CURSOR, HELP_CURSOR = "SWORDCURSOR", "HELPCURSOR"
# notes/native-windows.md 9.3.1: the tune of each screen state, loaded from the installation's music directory.
TUNES = {"win": "WIN", "lose": "LOSE", "tactical": "TACTICAL"}


class DebriefView(NativeScreenView[DebriefScene]):
    """Draw the debrief pages and translate their documented mouse input."""

    def __init__(self, gpu: Gpu, scene: DebriefScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.bitmap_quads = QuadCache(gpu)
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self.labels: list[tuple[TextLabel, Point]] = []
        self.buttons: list[tuple[pygame.Rect, str]] = []
        self.banner_surfaces: dict[str, pygame.Surface | None] = {}
        self.banner_files: dict[str, str] | None = None
        self.pressed_button: str | None = None
        self.state: tuple[Any, ...] | None = None
        self.music_started = False
        self.active = scene.screen is not None and not scene.screen.will_skip()
        if not self.active:  # a screen with nothing to show closes on the scene's first tick
            return
        self.content = scene.glue_scene.require_runtime().content
        self.fonts = {2: BitmapFont(scene.glue_scene.font(2)), 4: BitmapFont(scene.glue_scene.font(4))}
        scene.screen.body_height = self.fonts[2].font.height
        scene.screen.heading_height = self.fonts[4].font.height
        self.palette = AppPalette.select(1, self.content.palette_tables())
        self.cursors = CursorController(self.content.installation, default=DEFAULT_CURSOR)
        self.cursors.show(None)
        self._play_tune()
        self.refresh()

    def _play_tune(self) -> None:
        screen = self.scene.screen
        installation = self.content.installation
        if screen is None or installation is None or not pygame.mixer.get_init():
            return
        try:
            path = installation.binary_file("MUSIC", f"{TUNES[screen.music()]}.MID")
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(audio_settings.volume("music"))
            pygame.mixer.music.play(loops=-1)
            self.music_started = True
        except (FileNotFoundError, AttributeError, pygame.error):
            pass

    def refresh(self) -> None:
        screen = self.scene.screen
        if screen is None or not self.active:
            return
        state = (screen.page, screen.unit_page, self.pressed_button)
        if state == self.state:
            return
        self.state = state
        self._release_contents()
        self._bitmap(BACKGROUND, (0, 0))
        layout = screen.layout()
        for row in layout.rows:
            self._bitmap_centered(f"Skull{row.skull}", (SKULL_CENTER_X, row.y + 12))
            self._banner(row.banner, (BANNER_X, row.y))
        for item in layout.texts:
            self._text(item)
        enabled = screen.buttons()
        for action, x, art, text_id in BUTTONS:
            self._button(action, x, art, text_id, {"done": enabled.done, "page:next": enabled.next,
                                                   "page:back": enabled.back}[action])

    def _text(self, item: Text) -> None:
        font = self.fonts[item.font]
        if item.align == "center":
            self._label(item.text, 0, item.y, item.colour, font, align="center")
        elif item.align == "right":
            self._label(item.text, item.x - font.size(item.text)[0], item.y, item.colour, font)
        else:
            self._label(item.text, item.x, item.y, item.colour, font)

    def _button(self, action: str, x: int, art: str, text_id: int, enabled: bool) -> None:
        pressed = enabled and action == self.pressed_button
        self._bitmap(f"{art}Dn0" if pressed else f"{art}Up", (x, BUTTON_Y))
        offset_x, offset_y = LABEL_OFFSET_PRESSED if pressed else LABEL_OFFSET_RELEASED
        font = self.fonts[2]
        label_y = BUTTON_Y + (BUTTON_SIZE[1] - font.font.height) // 2 + offset_y
        self._label(self._string("BRTXT", text_id), x + offset_x, label_y, YELLOW if enabled else LIGHT_GREY, font,
                    align="center", width=BUTTON_SIZE[0])
        if enabled:
            self.buttons.append((pygame.Rect(x, BUTTON_Y, *BUTTON_SIZE), action))

    def _string(self, table: str, text_id: int) -> str:
        try:
            return self.content.string(table, int(text_id))
        except (KeyError, TypeError, ValueError):
            return ""

    def _label(self, value: str, x: int, y: int, colour: tuple[int, int, int], font: BitmapFont, *,
               align: str = "left", width: int = 640) -> None:
        label = self.gpu.text((width, font.font.height), font, color=colour, background=None, padding=0,
                              align=align, fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _bitmap(self, name: str, position: Point) -> None:
        quad = self.bitmap_quads.get(name, lambda: load_optional_bitmap(self.content, name, app_palette=self.palette))
        if quad is not None:
            self.quads.append((quad, position))

    def _bitmap_centered(self, name: str, center: Point) -> None:
        quad = self.bitmap_quads.get(name, lambda: load_optional_bitmap(self.content, name, app_palette=self.palette))
        if quad is not None:
            width, height = quad.size
            self.quads.append((quad, (center[0] - width // 2, center[1] - height // 2)))

    def _quad(self, surface: pygame.Surface, position: Point, key: str) -> None:
        quad = self.bitmap_quads.get(("banner", key), lambda: surface)
        if quad is not None:
            self.quads.append((quad, position))

    def _banner(self, name: str | None, position: Point) -> None:
        """Frame 1 of a resident banner set, the 16x24 row marker (notes/troop_selection.md 3.3)."""
        if not name or self.content.installation is None:
            return
        resource = resource_name(name)
        if resource is None:
            return
        if self.banner_files is None:
            from ..battlefield import resource_files
            self.banner_files = resource_files(self.content.installation, {"banners"})
        base = self.banner_files.get(resource.casefold())
        if base is None:
            return
        if base not in self.banner_surfaces:
            surface: pygame.Surface | None
            try:
                from ..portraits import load_sprite_sheet
                frame = load_sprite_sheet(self.content.installation, base).frames[1]
                surface = pygame.image.frombuffer(self.palette.rgba(frame.pixels), (frame.width, frame.height),
                                                  "RGBA").copy()
            except (FileNotFoundError, IndexError, OSError, ValueError):
                surface = None
            self.banner_surfaces[base] = surface
        loaded = self.banner_surfaces[base]
        if loaded is not None:
            self._quad(loaded, position, base)

    def _native_point(self, position: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if not self.active:
            return ()
        if event.type == pygame.MOUSEMOTION:
            self.cursors.show(HELP_CURSOR if pygame.key.get_mods() & pygame.KMOD_CTRL else DEFAULT_CURSOR)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            point = self._native_point(event.pos)
            self.pressed_button = next((action for rect, action in self.buttons if rect.collidepoint(point)), None)
            if self.pressed_button is not None:
                self._click_cue(4)
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            point = self._native_point(event.pos)
            pressed, self.pressed_button = self.pressed_button, None
            self.refresh()
            if pressed is not None and any(rect.collidepoint(point) and action == pressed
                                           for rect, action in self.buttons):
                self._click_cue(3)
                return (pressed,)
        return ()

    def animate(self, seconds: float) -> None:
        self.refresh()

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def _release_contents(self) -> None:
        for label, _ in self.labels:
            label.release()
        self.quads, self.labels, self.buttons = [], [], []

    def release(self) -> None:
        self._release_contents()
        self.bitmap_quads.release()
        if self.music_started:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass
        if hasattr(self, "cursors"):
            self.cursors.release()
