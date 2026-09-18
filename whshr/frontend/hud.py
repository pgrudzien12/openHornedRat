"""Battle HUD: selected-unit panel, command buttons and battlefield minimap."""

import pygame

from .gpu import ScreenQuad


# Visually verified ICONS.FOL pairs. Paired entries are raised and pressed versions.
ICON_INDEX = {
    "move": (0, 1), "attack": (2, 3), "shoot": (4, 5), "special": (6, 7),
    "halt": (37, 38), "hourglass": (46, 47),
}

BUTTON_SIZE = 48
MINIMAP_SIZE = (200, 144)


def frame_rgba(frame, palette):
    """Convert a decoded indexed frame to top-down RGBA for a ScreenQuad."""
    rgba = bytearray(frame.width * frame.height * 4)
    for offset, index in enumerate(frame.pixels):
        rgba[offset * 4:offset * 4 + 4] = (*palette[index], 0 if index == 0 else 255)
    return bytes(rgba)


class Hud:
    """Battle chrome built from the game's banner, portrait and ICONS sheets."""

    def __init__(self, gpu, field):
        self.gpu, self.field = gpu, field
        self.font = pygame.font.Font(None, 22)
        self.color = (235, 230, 210)
        portrait_bg = field.script["field"].get("portrait_bg")
        self.background = self._quad(self._sheet(portrait_bg) or self._sheet("backall"), 0)
        self.banner = self.portrait = None
        self.icons = self._sheet("icons")
        self.button_icons = {
            action: (self._quad(self.icons, pair[0]), self._quad(self.icons, pair[1]))
            for action, pair in ICON_INDEX.items() if len(pair) == 2
        }
        self.caption = gpu.text((96, 144), pygame.font.Font(None, 18),
                                color=self.color, background=(0, 0, 0, 170))
        self.minimap = ScreenQuad(gpu, MINIMAP_SIZE)
        self.selected = None
        self.battle = None
        self._draw_size = None

    def _sheet(self, name):
        return self.field.ui_sheets.get(name.casefold()) if name else None

    def _quad(self, sheet, index):
        if sheet is None or index >= len(sheet.frames):
            return None
        frame = sheet.frames[index]
        quad = ScreenQuad(self.gpu, (frame.width, frame.height))
        quad.write(frame_rgba(frame, self.field.palette))
        return quad

    def set_portrait(self, regiment_id):
        """Compatibility name for selecting the HUD regiment."""
        self.set_selected(regiment_id)

    def set_selected(self, regiment_id):
        """Select a regiment and rebuild only its portrait/banner art when it changes."""
        if regiment_id == self.selected:
            return
        self.selected = regiment_id
        state = self._regiment(regiment_id)
        for quad in (self.banner, self.portrait):
            if quad:
                quad.release()
        self.banner = self._quad(self._sheet(state.banner), 0) if state else None
        self.portrait = self._quad(self._sheet(state.portrait), 0) if state else None
        self.caption.set_lines(self.current_stats_lines())

    def current_stats_lines(self):
        """Return the selected regiment's current HUD readout.

        The engine tracks casualties as whole models, not individual wounds, so
        ``W`` is the profile's wounds-per-model value.
        """
        state = self._regiment(self.selected) if self.selected is not None else None
        if state is None:
            return ()
        original = state.original_models if state.original_models is not None else state.models
        return (
            state.name,
            f"{state.models}/{original} models",
            f"Wounds {state.models * state.wounds}",
            f"WS{state.ws} BS{state.bs} S{state.strength} T{state.toughness}",
            f"W{state.wounds} I{state.initiative} A{state.attacks} Ld{state.leadership}",
            self._state_label(state),
        )

    @staticmethod
    def _state_label(state):
        if state.routing:
            return "Routing"
        if state.in_melee:
            return "Fighting"
        if state.moving:
            return "Moving"
        return "Standing"

    def _regiment(self, identifier):
        return self.battle.regiments.get(identifier) if self.battle is not None else None

    def bind_battle(self, battle):
        self.battle = battle

    def _button_layout(self, width, height):
        """The four currently modelled command slots in the bottom-right panel."""
        right, top, step = width - 16, height - 172, 52
        return {
            "move": (right - 104, top), "attack": (right - 52, top),
            "halt": (right - 78, top + step),
            "shoot": (right - 104, top + step * 2),
        }

    def _button_enabled(self, action, state):
        if state is None or not state.player or not state.active or state.routing or state.in_melee:
            return False
        if action in {"move", "attack"}:
            return True
        if action == "halt":
            return state.moving
        if action == "shoot":
            return state.missile_range is not None and state.reload_ticks <= 0
        return False

    @staticmethod
    def _contains(pos, rect):
        left, top, width, height = rect
        return left <= pos[0] < left + width and top <= pos[1] < top + height

    def _minimap_rect(self, width, height):
        return (width - MINIMAP_SIZE[0] - 16, 16, *MINIMAP_SIZE)

    def occupies(self, pos):
        """Whether *pos* lands on any HUD chrome, including non-actionable pixels."""
        if self._draw_size is None:
            return False
        width, height = self._draw_size
        if self._contains(pos, self._minimap_rect(width, height)):
            return True
        if self.selected is not None and self._contains(pos, (16, height - 168, 240, 152)):
            return True
        return any(self._contains(pos, (*origin, BUTTON_SIZE, BUTTON_SIZE))
                   for origin in self._button_layout(width, height).values())

    def minimap_position(self, pos):
        """Convert a minimap pixel to BTS world coordinates, or return ``None`` off-map."""
        if self._draw_size is None:
            return None
        left, top, width, height = self._minimap_rect(*self._draw_size)
        if not self._contains(pos, (left, top, width, height)):
            return None
        x = (pos[0] - left) / (width - 1) * self.field.width
        y = (1 - (pos[1] - top) / (height - 1)) * self.field.height
        return (x, y)

    def hit_test(self, pos):
        """Return an enabled semantic command under *pos*, otherwise ``None``."""
        if self._draw_size is None:
            return None
        state = self._regiment(self.selected)
        for action, (left, top) in self._button_layout(*self._draw_size).items():
            if (left <= pos[0] < left + BUTTON_SIZE and top <= pos[1] < top + BUTTON_SIZE
                    and action in {"move", "attack", "halt"}
                    and self._button_enabled(action, state)):
                return action
        return None

    def _minimap_rgba(self):
        """Rasterize active regiment positions into a cheap CPU-side minimap."""
        width, height = MINIMAP_SIZE
        pixels = bytearray((29, 37, 31, 255)) * (width * height)

        def fill(left, top, size, color):
            fill_rect(left, top, size, size, color)

        def fill_rect(left, top, rect_width, rect_height, color):
            for y in range(max(0, top), min(height, top + rect_height)):
                for x in range(max(0, left), min(width, left + rect_width)):
                    offset = (y * width + x) * 4
                    pixels[offset:offset + 4] = bytes(color)

        fill_rect(0, 0, width, 1, (176, 157, 97, 255))
        fill_rect(0, height - 1, width, 1, (176, 157, 97, 255))
        fill_rect(0, 0, 1, height, (176, 157, 97, 255))
        fill_rect(width - 1, 0, 1, height, (176, 157, 97, 255))
        if self.battle is None or not self.field.width or not self.field.height:
            return bytes(pixels)
        for regiment in self.battle.regiments.values():
            if not regiment.active:
                continue
            x = round(regiment.x / self.field.width * (width - 1))
            y = round((1 - regiment.y / self.field.height) * (height - 1))
            color = (65, 139, 221, 255) if regiment.player else (205, 62, 54, 255)
            fill(x - 2, y - 2, 5, color)
            if regiment.identifier == self.selected:
                fill(x - 3, y - 3, 7, (244, 231, 127, 255))
                fill(x - 1, y - 1, 3, color)
        return bytes(pixels)

    def draw(self, width, height):
        self._draw_size = (width, height)
        self.minimap.write(self._minimap_rgba())
        self.minimap.draw(*self._minimap_rect(width, height)[:2])

        if self.selected is not None:
            panel = self.banner or self.background
            if panel:
                panel.draw(16, height - 168, 240, 152)
            if self.portrait:
                self.portrait.draw(32, height - 160, 120, 120)
            self.caption.set_lines(self.current_stats_lines())
            self.caption.draw(156, height - 160)

        state = self._regiment(self.selected)
        for action, (left, top) in self._button_layout(width, height).items():
            icon_pair = self.button_icons.get(action)
            if not icon_pair or not icon_pair[0] or state is None or not state.player or not state.active:
                continue
            enabled = self._button_enabled(action, state)
            icon_pair[0].draw(left, top, BUTTON_SIZE, BUTTON_SIZE,
                              tint=(1, 1, 1, 1) if enabled else (0.38, 0.38, 0.38, 0.82))

    def release(self):
        quads = [self.background, self.banner, self.portrait, self.caption, self.minimap]
        quads.extend(quad for pair in self.button_icons.values() for quad in pair)
        for quad in quads:
            if quad:
                quad.release()
