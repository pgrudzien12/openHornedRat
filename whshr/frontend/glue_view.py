"""First generic pygame adapter for static ``GlueScene`` windows.

This is intentionally narrow: bitmap composition and hotspot hit-testing are
shared now; text, portraits and executable-owned widgets remain separate
adapters until their renderer rules are moved out of compatibility views.
"""

import pygame

from ..glue_render import build_render_model
from ..glue_runtime import GlueInput
from ..glue_palette import AppPalette
from .bitmap_font import BitmapFont
from .glue_bitmap import load_optional_bitmap
from .gpu import ScreenQuad
from .scene_view import NativeScreenView


class GlueView(NativeScreenView):
    """Draw static runtime windows and translate click/release hotspots."""

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.models = ()
        self.quads = []
        self.text_labels = []
        self.dialogue_label = None
        self.dialogue_state = None
        self.pressed = None
        self.refresh()

    def refresh(self):
        """Rebuild GPU quads after the runtime changes its active windows."""
        models = tuple(build_render_model(self.scene.runtime.content, window, self.scene.runtime.state.object_positions)
                       for window in self.scene.runtime.state.windows)
        frames = {(animation.window_name, animation.object_name): animation.animator.display_name
                  for animation in self.scene.runtime.state.animations}
        palette = self._palette(models)
        dialogue_state = _dialogue_state(self.scene.runtime.state)
        if (models, frames, palette, dialogue_state) == (
            self.models, getattr(self, "frames", {}), getattr(self, "palette", None), self.dialogue_state
        ):
            return
        for quad, _ in self.quads:
            quad.release()
        for label, _ in self.text_labels:
            label.release()
        self.models = models
        self.frames = frames
        self.palette = palette
        self.dialogue_state = dialogue_state
        self.quads = []
        self.text_labels = []
        for model in self.models:
            for bitmap in model.bitmaps:
                name = frames.get((model.name, bitmap.object_name), bitmap.name)
                surface = load_optional_bitmap(self.scene.runtime.content, name, app_palette=palette)
                if surface is None:
                    continue
                quad = ScreenQuad(self.gpu, surface.get_size())
                quad.write(pygame.image.tobytes(surface, "RGBA"))
                self.quads.append((quad, (model.x + bitmap.x, model.y + bitmap.y)))
            for text in model.texts:
                value = resolve_text(self.scene.runtime.content, text)
                if value is None:
                    continue
                try:
                    font = BitmapFont(self.scene.font(text.font or 2))
                except (KeyError, ValueError):
                    continue
                self.text_labels.append(_place_text(self.gpu, font, value, text, model))
        self._refresh_dialogue(dialogue_state)

    def _refresh_dialogue(self, dialogue_state):
        """Rebuild the bottom-anchored briefing dialogue block (notes/briefing_dialogue.md §3.3)."""
        if self.dialogue_label is not None:
            self.dialogue_label[0].release()
            self.dialogue_label = None
        window_name, lines, colour = dialogue_state
        if not lines:
            return
        model = next((model for model in self.models if model.name == window_name), None)
        if model is None:
            return
        try:
            font = BitmapFont(self.scene.font(4))
        except (KeyError, ValueError):
            return
        line_height = max(1, font.font.height)
        left = model.x + max(0, round(model.width * 0.05))
        width = max(1, round(model.width * 0.90))  # wrap width, §3.3; the label itself is sized to fit
        wrapped = [physical for logical in lines for physical in _wrap(font, logical, width)]
        top = model.y + model.height - round(1.5 * line_height) - (len(wrapped) - 1) * line_height
        label = self.gpu.text((width, max(1, len(wrapped)) * line_height), font,
                              color=_TEXT_COLOURS.get(colour, (0, 0, 0)), background=None, padding=0,
                              outline=True)
        label.set_lines(wrapped)
        self.dialogue_label = (label, (left, top))

    def _palette(self, models):
        """Select the one application palette active for the runtime windows."""
        palette_id = self.scene.runtime.state.palette_id
        embedded = None
        if palette_id < 0 and models and models[0].bitmaps:
            embedded = self.scene.runtime.content.bitmap_data(models[0].bitmaps[0].name).palette
        return AppPalette.select(palette_id, self.scene.runtime.content.palette_tables(), embedded=embedded)

    @staticmethod
    def hotspot_at(models, point):
        """Return the last-painted hotspot at native coordinates, if any."""
        for model in reversed(models):
            for hotspot in reversed(model.hotspots):
                if pygame.Rect(model.x + hotspot.x, model.y + hotspot.y,
                               hotspot.width, hotspot.height).collidepoint(point):
                    return hotspot
        return None

    def _native_point(self, pos):
        left, top, scale = self._layout()
        return (pos[0] - left) / scale, (pos[1] - top) / scale

    def events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self.hotspot_at(self.models, self._native_point(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, self.pressed = self.pressed, None
            released = self.hotspot_at(self.models, self._native_point(event.pos))
            if pressed is not None and pressed == released:
                return (GlueInput("hotspot-release", pressed.target),)
            if pressed is None and released is None:
                return (GlueInput("dialogue-drain"),)
        return ()

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.text_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        if self.dialogue_label is not None:
            label, (x, y) = self.dialogue_label
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def release(self):
        for quad, _ in self.quads:
            quad.release()
        for label, _ in self.text_labels:
            label.release()
        if self.dialogue_label is not None:
            self.dialogue_label[0].release()
            self.dialogue_label = None
        self.quads = []
        self.text_labels = []


# notes/briefing_dialogue.md §3.4, the front-end's settextcolor name -> RGB table.
_TEXT_COLOURS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 255, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "magenta": (255, 0, 255), "cyan": (0, 255, 255),
    "gray": (127, 127, 127), "lgray": (192, 192, 192), "dkred": (127, 0, 0), "dkgreen": (0, 127, 0),
    "dkblue": (0, 0, 127), "olive": (127, 127, 0), "purple": (127, 0, 127), "drab": (0, 127, 127),
}


def _place_text(gpu, font, value, text, model):
    """Build and position one glue text label per its ``format`` (notes/glue_keywords.md §3.4).

    ``vx``/``vy`` change meaning by format: for 1 (map titles) ``vy`` is a *y offset*, not a box
    height, so feeding it straight to the label's canvas size (the previous behaviour) clipped
    the glyphs to a few pixels and made the text disappear. Only the shipped formats (1, 6, 7, 8)
    are implemented; anything else falls back to format 3's plain ``(x, y)`` placement.
    """
    fmt = text.format if text.format is not None else 3
    line_height = max(1, font.font.height)
    origin_x, origin_y = model.x + text.x, model.y + text.y
    if fmt == 1:
        width = max(1, text.width)
        label = gpu.text((width, line_height), font, color=_TEXT_COLOURS.get(text.colour, (0, 0, 0)),
                         background=None, padding=0, align="center", fixed_width=True)
        label.set_lines((value,))
        return label, (origin_x, origin_y + text.height)
    # Only formats 1 and 7 use vx as a width to bound the label; 3/5/6/8 draw at their natural
    # content width, so a small vx (a real value there, just not a size - e.g. a format 6 town
    # label's vx=10) must not clip the canvas, or only the first letter or two survives.
    canvas_width = max(1, text.width) if fmt == 7 else 640
    label = gpu.text((canvas_width, line_height), font,
                     color=_TEXT_COLOURS.get(text.colour, (0, 0, 0)), background=None, padding=0,
                     outline=fmt == 6)
    label.set_lines((value,))
    content_width, content_height = label.text_size
    if fmt in (5, 6):  # right edge at x, top at y (6 additionally draws a 1 px outline)
        return label, (origin_x - content_width, origin_y)
    if fmt == 7:  # right edge at x + vx, centred vertically in vy
        return label, (origin_x + text.width - content_width, origin_y + (text.height - content_height) // 2)
    if fmt == 8:  # left edge at x, centred vertically in vy
        return label, (origin_x, origin_y + (text.height - content_height) // 2)
    return label, (origin_x, origin_y)  # format 3 (and unused 0/2/4): plain (x, y)


def _wrap(font, text, width):
    """Greedy word-wrap: a new word joins the current line unless it would exceed ``width`` (§3.3)."""
    words = text.split(" ")
    lines, current = [], words[0] if words else ""
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.size(candidate)[0] <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _dialogue_state(state):
    """The (window, visible lines, colour) fingerprint refresh() diffs against, per §3.3's ring buffer."""
    typed = state.dialogue_text[:state.dialogue_typed]
    lines = (*state.dialogue_lines, typed) if typed else state.dialogue_lines
    return state.dialogue_window_name, lines, state.dialogue_colour


def resolve_text(content, text):
    """Resolve one glue text record without importing pygame or a scene context."""
    if text.string_id is None:
        return None
    try:
        return content.string(text.table or "BRTXT", text.string_id)
    except KeyError:
        return None
