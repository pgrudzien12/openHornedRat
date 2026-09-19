"""Campaign map and mission-scroll selection view."""

from pathlib import Path

import pygame

from .bitmap_font import BitmapFont
from .gpu import ScreenQuad
from .scene_view import SceneView


class MissionMapView(SceneView):
    """Present the original map artwork with data-driven selectable scrolls."""

    NATIVE_SIZE = (640, 480)
    ART_DIR = Path(__file__).resolve().parents[2] / "extracted/pe_resources/BITMAP/bitmap"
    SCROLL_ORIGIN = (30, 15)
    SCROLL_SIZE = (144, 88)
    ROW_PITCH = 90  # The glue layout rounds the 88-pixel scroll artwork to 90 pixels.
    TEXT_HEIGHT = 12
    FRAME_ORIGIN = (4, 4)
    PORTRAIT_ORIGIN = (12, 12)
    PANEL_ORIGIN = (4, 164)
    BUTTON_X = 9
    BUTTON_Y = (168, 188, 208)  # Brief, Accept, Caravan: panel slots top to bottom.
    BUTTONS = (("Brief", "open_briefing"), ("Accept", "open_troop_select"),
               ("Caravan", "return_to_caravan"))

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.map = self._load_quad(gpu, "MAP.png")
        self.scrolls = (self._load_quad(gpu, "SCROLL0.png", colorkey=True),
                        self._load_quad(gpu, "SCROLL1.png", colorkey=True))
        self.frame = {
            name: self._load_quad(gpu, f"{name}.png", colorkey=True)
            for name in ("FRAMETOP", "FRAMELEFT", "FRAMERIGHT", "FRAMEBOTTOM", "FRAMEPANEL3")
        }
        self.button_up = self._load_quad(gpu, "FRAMEBUTTONUP.png", colorkey=True)
        self.button_down = self._load_quad(gpu, "FRAMEBUTTONDN.png", colorkey=True)
        portrait = scene.dietrich_portrait
        self.portrait_window = scene.portrait_window
        self.map_panel = self.portrait_window is not None and self.portrait_window.get("controlpanel") in (2, 10)
        # The map/list uses compact black PCTEXTA glyphs.  Keep the working
        # height at eight pixels until the original font-2 renderer is traced.
        self.button_color = (0, 0, 0)
        self.text_font = BitmapFont(scene.font)
        self.dietrich = None
        if portrait is not None:
            width, height, rgba = portrait
            self.dietrich = ScreenQuad(gpu, (width, height))
            self.dietrich.write(rgba)
        self.hovered = None
        self.pressed = None
        # Mission-window scripts define their origin but no text placement or
        # colour.  The original executable owns those values; retain this
        # deliberately isolated approximation until that renderer is traced.
        self.labels = [gpu.text((120, self.TEXT_HEIGHT), self.text_font, color=(0, 0, 0), background=None,
                                padding=0, align="center", fixed_width=True)
                       for _ in scene.missions]
        self.button_labels = [gpu.text((119, self.TEXT_HEIGHT), self.text_font, color=self.button_color, background=None,
                                       padding=0, align="center", fixed_width=True)
                              for _ in self.BUTTONS]
        self._set_labels()
        self._button_selection = object()
        self._set_button_labels()

    @classmethod
    def _load_quad(cls, gpu, filename, colorkey=False):
        path = cls.ART_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"map artwork not found: {path}; run the resource extractor into extracted/")
        surface = pygame.image.load(str(path))
        if colorkey:
            surface = surface.convert()
            surface.set_colorkey((0, 0, 255))
            surface = surface.convert_alpha()
        quad = ScreenQuad(gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        return quad

    def _set_labels(self):
        missions = self.scene.missions
        for label, mission in zip(self.labels, missions):
            cash = mission.get("cash") or {}
            initial, completion = cash.get("initial"), cash.get("completion")
            payment = f" ({initial}, {completion})" if initial is not None and completion is not None else ""
            label.set_lines((f"{mission['name']}{payment}",))

    def _set_button_labels(self):
        for index, (label, (fallback, _action), resource_id) in enumerate(
                zip(self.button_labels, self.BUTTONS, (313, 309, 333))):
            label.set_color(self.button_color if self._button_enabled(index) else (192, 192, 192))
            label.set_lines((self.scene.campaign.hint(resource_id) or fallback,))
        self._button_selection = self.scene.selected_index

    def _button_enabled(self, index):
        """Caravan is always available; Brief/Accept require a current mission."""
        return index == 2 or self.scene.selected_mission is not None

    def _layout(self):
        screen_width, screen_height = self.gpu.target.size
        native_width, native_height = self.NATIVE_SIZE
        scale = min(screen_width / native_width, screen_height / native_height)
        return ((screen_width - native_width * scale) / 2,
                (screen_height - native_height * scale) / 2, scale)

    def _mission_at(self, pos):
        left, top, scale = self._layout()
        point = ((pos[0] - left) / scale, (pos[1] - top) / scale)
        for index in range(len(self.scene.missions)):
            rect = pygame.Rect(self.SCROLL_ORIGIN[0], self.SCROLL_ORIGIN[1] + index * self.ROW_PITCH,
                               *self.SCROLL_SIZE)
            if rect.collidepoint(point):
                return index
        return None

    def _button_at(self, pos):
        if not self.map_panel:
            return None
        left, top, scale = self._layout()
        point = ((pos[0] - left) / scale, (pos[1] - top) / scale)
        x, window_y = self.portrait_window["position"]["x"], self.portrait_window["position"]["y"]
        for index, button_y in enumerate(self.BUTTON_Y):
            if pygame.Rect(x + self.BUTTON_X, window_y + button_y,
                           119, 20).collidepoint(point):
                return index
        return None

    def events(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return ("return_to_caravan",)
            if event.key in (pygame.K_UP, pygame.K_DOWN) and self.scene.missions:
                direction = -1 if event.key == pygame.K_UP else 1
                selected = self.scene.selected_index
                return (f"select_mission:{((selected if selected is not None else 0) + direction) % len(self.scene.missions)}",)
        elif event.type == pygame.MOUSEMOTION:
            hovered = self._mission_at(event.pos)
            if hovered is not None:
                return (f"select_mission:{hovered}",)
            self.hovered = self._button_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._button_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            index = self._mission_at(event.pos)
            if index is not None:
                return (f"select_mission:{index}",)
            pressed, self.pressed = self.pressed, None
            button = self._button_at(event.pos)
            if pressed == button and button is not None and self._button_enabled(button):
                return (self.BUTTONS[button][1],)
        return ()

    def status(self):
        return (f"mission map {self.scene.campaign.mission_window}, {len(self.scene.missions)} offered",)

    def draw(self):
        super().draw()
        if self._button_selection != self.scene.selected_index:
            self._set_button_labels()
        left, top, scale = self._layout()
        width, height = self.NATIVE_SIZE[0] * scale, self.NATIVE_SIZE[1] * scale
        self.map.draw(left, top, width, height)
        if self.dietrich is not None and self.portrait_window is not None:
            x, y = self.portrait_window["position"]["x"], self.portrait_window["position"]["y"]
            x += self.PORTRAIT_ORIGIN[0]
            y += self.PORTRAIT_ORIGIN[1]
            self.dietrich.draw(left + x * scale, top + y * scale, 120 * scale, 152 * scale)
        if self.map_panel:
            x, y = self.portrait_window["position"]["x"], self.portrait_window["position"]["y"]
            self.frame["FRAMETOP"].draw(left + (x + 4) * scale, top + (y + 4) * scale, 136 * scale, 8 * scale)
            self.frame["FRAMELEFT"].draw(left + (x + 4) * scale, top + (y + 12) * scale, 8 * scale, 152 * scale)
            self.frame["FRAMERIGHT"].draw(left + (x + 132) * scale, top + (y + 12) * scale, 8 * scale, 152 * scale)
            self.frame["FRAMEPANEL3"].draw(left + (x + 4) * scale, top + (y + 164) * scale, 136 * scale, 68 * scale)
            self.frame["FRAMEBOTTOM"].draw(left + (x + 4) * scale, top + (y + 164) * scale, 136 * scale, 8 * scale)
            for index, (button_y, label) in enumerate(zip(self.BUTTON_Y, self.button_labels)):
                button = self.button_down if index == self.pressed else self.button_up
                button.draw(left + (x + self.BUTTON_X) * scale, top + (y + button_y) * scale, 119 * scale, 20 * scale)
                label.draw(left + (x + self.BUTTON_X) * scale, top + (y + button_y + 4) * scale,
                           119 * scale, self.TEXT_HEIGHT * scale)
        for index, label in enumerate(self.labels):
            x, y = self.SCROLL_ORIGIN[0], self.SCROLL_ORIGIN[1] + index * self.ROW_PITCH
            self.scrolls[index == self.scene.selected_index].draw(left + x * scale, top + y * scale,
                                                       self.SCROLL_SIZE[0] * scale, self.SCROLL_SIZE[1] * scale)
            label.draw(left + (x + 12) * scale, top + (y + 38) * scale,
                       120 * scale, self.TEXT_HEIGHT * scale)

    def release(self):
        for quad in (self.map, *self.scrolls, *self.frame.values(), self.button_up, self.button_down):
            quad.release()
        if self.dietrich is not None:
            self.dietrich.release()
        for label in self.labels:
            label.release()
        for label in self.button_labels:
            label.release()
