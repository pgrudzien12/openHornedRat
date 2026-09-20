"""Campaign map and mission-scroll selection view."""

import pygame

from .bitmap_font import BitmapFont
from ..controlpanel import button_y, control_panel
from .gpu import ScreenQuad
from .glue_bitmap import load_bitmap
from .scene_view import NativeScreenView


class MissionMapView(NativeScreenView):
    """Present the original map artwork with data-driven selectable scrolls."""

    SCROLL_ORIGIN = (30, 15)
    SCROLL_SIZE = (144, 88)
    ROW_PITCH = 90  # The glue layout rounds the 88-pixel scroll artwork to 90 pixels.
    SCROLL_TEXT_X = 10  # FUN_0044d2b2: row label x offset inside Scroll0/Scroll1.
    SCROLL_TEXT_WIDTH = SCROLL_SIZE[0] - 2 * SCROLL_TEXT_X
    TEXT_HEIGHT = 12
    FRAME_ORIGIN = (4, 4)
    PORTRAIT_ORIGIN = (12, 12)
    PANEL_ORIGIN = (4, 164)
    BUTTON_X = 9

    @staticmethod
    def _wrap_mission_name(font, name, width=SCROLL_TEXT_WIDTH):
        """Wrap BRTXT's one-line mission name inside a scroll's text column."""
        words, lines, current = name.split(), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or font.size(candidate)[0] <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.map = self._load_quad(gpu, "MAP")
        self.scrolls = (self._load_quad(gpu, "SCROLL0", colorkey=True), self._load_quad(gpu, "SCROLL1", colorkey=True))
        self.portrait_window = scene.portrait_window
        self.panel = control_panel(self.portrait_window.get("controlpanel", 0) if self.portrait_window else 0)
        self.frame = {
            name: self._load_quad(gpu, name, colorkey=True)
            for name in ("FRAMETOP", "FRAMELEFT", "FRAMERIGHT", self.panel.bitmap)
        }
        self.button_up = self._load_quad(gpu, "FRAMEBUTTONUP", colorkey=True)
        self.button_down = self._load_quad(gpu, "FRAMEBUTTONDN", colorkey=True)
        portrait = scene.speaker_portrait
        self.map_panel = self.portrait_window is not None
        self.button_slots = tuple(reversed(range(self.panel.slot_count)))
        # The map/list uses compact black PCTEXT glyphs from glue font 2.
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
        self.labels = [gpu.text((self.SCROLL_TEXT_WIDTH, 64), self.text_font, color=(0, 0, 0), background=None,
                                padding=0, align="left", fixed_width=True)
                       for _ in scene.missions]
        self.button_labels = [gpu.text((119, self.TEXT_HEIGHT), self.text_font, color=self.button_color, background=None,
                                       padding=0, align="center", fixed_width=True)
                              for _ in self.button_slots]
        self._set_labels()
        self._button_selection = object()
        self._set_button_labels()

    def _load_quad(self, gpu, resource_name, colorkey=False):
        surface = load_bitmap(self.scene.content, resource_name)
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
            lines = self._wrap_mission_name(self.text_font, mission["name"])
            # This format is created by MissionWindow's executable-owned row
            # painter, not by the WND record: name, then a newline and the
            # initial/completion payment with a slash separator.
            if initial or completion:
                lines.append(f"{initial}/{completion}")
            elif cash.get("type") == 15:
                lines.append(self.scene.campaign.hint(612))
            label.set_lines(lines)

    def _set_button_labels(self):
        for index, (label, slot) in enumerate(zip(self.button_labels, self.button_slots)):
            label.set_color(self.button_color if self._button_enabled(index) else (192, 192, 192))
            label.set_lines((self.scene.campaign.hint(self.panel.labels[slot]),))
        self._button_selection = self.scene.selected_index

    def _button_enabled(self, index):
        """Known slot actions need a selected mission except Caravan."""
        slot = self.button_slots[index]
        action = self.panel.actions[slot] if slot < len(self.panel.actions) else None
        return action == "return_to_caravan" or (action is not None and self.scene.selected_mission is not None)

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
        for index, slot in enumerate(self.button_slots):
            if pygame.Rect(x + self.BUTTON_X, window_y + button_y(self.portrait_window.get("controlpanel", 0), slot),
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
                return (self.panel.actions[self.button_slots[button]],)
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
            self.frame[self.panel.bitmap].draw(left + (x + 4) * scale, top + (y + 164) * scale,
                                                136 * scale, self.panel.height * scale)
            for index, (slot, label) in enumerate(zip(self.button_slots, self.button_labels)):
                button = self.button_down if index == self.pressed else self.button_up
                y_pos = button_y(self.portrait_window.get("controlpanel", 0), slot)
                button.draw(left + (x + self.BUTTON_X) * scale, top + (y + y_pos) * scale, 119 * scale, 20 * scale)
                label.draw(left + (x + self.BUTTON_X) * scale, top + (y + y_pos + 4) * scale,
                           119 * scale, self.TEXT_HEIGHT * scale)
        for index, label in enumerate(self.labels):
            x, y = self.SCROLL_ORIGIN[0], self.SCROLL_ORIGIN[1] + index * self.ROW_PITCH
            self.scrolls[index == self.scene.selected_index].draw(left + x * scale, top + y * scale,
                                                       self.SCROLL_SIZE[0] * scale, self.SCROLL_SIZE[1] * scale)
            label.draw(left + (x + self.SCROLL_TEXT_X) * scale, top + (y + 10) * scale,
                       self.SCROLL_TEXT_WIDTH * scale, 64 * scale)

    def release(self):
        for quad in (self.map, *self.scrolls, *self.frame.values(), self.button_up, self.button_down):
            quad.release()
        if self.dietrich is not None:
            self.dietrich.release()
        for label in self.labels:
            label.release()
        for label in self.button_labels:
            label.release()
