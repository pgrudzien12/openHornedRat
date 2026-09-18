import pygame

from .gpu import ScreenQuad

def frame_rgba(frame, palette):
    """Convert a decoded indexed frame to top-down RGBA for a ScreenQuad."""
    rgba = bytearray(frame.width * frame.height * 4)
    for offset, index in enumerate(frame.pixels):
        rgba[offset * 4:offset * 4 + 4] = (*palette[index], 0 if index == 0 else 255)
    return bytes(rgba)


class Hud:
    """Battle chrome built from the game's BACKALL and ICONS sprite sheets."""

    def __init__(self, gpu, field):
        self.gpu, self.field = gpu, field
        self.font = pygame.font.Font(None, 22)
        self.color = (235, 230, 210)
        portrait_bg = field.script["field"].get("portrait_bg")
        self.background = self._quad(self._sheet(portrait_bg) or self._sheet("backall"), 0)
        self.portrait = None
        self.buttons = []
        icons = self._sheet("icons")
        if icons:
            # ICONS starts with the standard 60x60 command glyphs. Keep this list
            # data-driven so installations with a shorter sheet still render.
            for index in range(min(8, len(icons.frames))):
                self.buttons.append((self._quad(icons, index), index))
        self.caption = gpu.text((260, 48), self.font, color=self.color, background=(0, 0, 0, 170))
        self.selected = None

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
        self.selected = regiment_id
        state = self._regiment(regiment_id)
        sheet = self._sheet(state.portrait) if state else None
        if sheet is None and state:
            sheet = self._sheet(state.banner)
        if self.portrait:
            self.portrait.release()
        self.portrait = self._quad(sheet, 0)
        self.caption.set_lines((state.name if state else f"Regiment {regiment_id}",))

    def _regiment(self, identifier):
        # The HUD is intentionally tolerant of synthetic scenes used by tests.
        return getattr(self, "battle", None).regiments.get(identifier) if getattr(self, "battle", None) else None

    def bind_battle(self, battle):
        self.battle = battle

    def draw(self, width, height):
        if self.background:
            self.background.draw(16, height - 168, 240, 152)
        if self.portrait:
            self.portrait.draw(32, height - 160, 120, 120)
        for index, (button, _) in enumerate(self.buttons):
            button.draw(280 + index * 64, height - 72, 56, 56)
        if self.selected:
            self.caption.draw(32, height - 38)

    def release(self):
        for quad in ([self.background, self.portrait, self.caption] + [button for button, _ in self.buttons]):
            if quad:
                quad.release()
