"""First generic pygame adapter for static ``GlueScene`` windows.

This is intentionally narrow: bitmap composition and hotspot hit-testing are
shared now; text, portraits and executable-owned widgets remain separate
adapters until their renderer rules are moved out of compatibility views.
"""

import pygame

from ..glue_render import build_render_model
from ..glue_runtime import GlueInput, PlayMusic, StopMusic
from ..glue_palette import AppPalette
from .bitmap_font import BitmapFont
from .glue_bitmap import load_optional_bitmap
from .gpu import ScreenQuad
from .scene_view import NativeScreenView

MIXER_CHANNELS = 8  # matches intro_view's cutscene mixer; music runs on pygame's separate music channel


def _ensure_mixer():
    """Best-effort mixer setup; audio stays silently unavailable without a usable audio device."""
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        if pygame.mixer.get_num_channels() < MIXER_CHANNELS:
            pygame.mixer.set_num_channels(MIXER_CHANNELS)
        return True
    except pygame.error:
        return False


class GlueView(NativeScreenView):
    """Draw static runtime windows and translate click/release hotspots."""

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.models = ()
        self.quads = []
        self.portrait_quads = []
        self.text_labels = []
        self.dialogue_labels = []
        self.dialogue_state = None
        self.music_name = None
        self._music_ok = _ensure_mixer()
        self.pressed = None
        self.refresh()

    def refresh(self):
        """Rebuild GPU quads after the runtime changes its active windows.

        Split into independent groups so a portrait's mouth/eye frame or a typing dialogue line -
        which change almost every tick - only rebuild their own small quads, not every bitmap on
        screen (the 640x480 map foremost): re-decoding that on every blink was the actual cost
        behind a briefing running at a few FPS.
        """
        self._process_music()
        models = tuple(build_render_model(self.scene.runtime.content, window, self.scene.runtime.state.object_positions)
                       for window in self.scene.runtime.state.windows)
        frames = {(animation.window_name, animation.object_name): animation.animator.display_name
                  for animation in self.scene.runtime.state.animations}
        palette = self._palette(models)
        self.models = models
        self._refresh_bitmaps(models, frames, palette)
        self._refresh_portraits(models, palette)
        self._refresh_dialogue(_dialogue_state(self.scene.runtime.state))

    def _process_music(self):
        """Drain playmidi/stopmidi effects (notes/briefing_dialogue.md §2.1: replace abruptly, loop forever)."""
        for effect in self.scene.take_effects():
            if isinstance(effect, PlayMusic):
                self.music_name = effect.name
                if not self._music_ok:
                    continue
                try:
                    path = self.scene.runtime.content.installation.binary_file("MUSIC", f"{effect.name}.MID")
                    pygame.mixer.music.load(str(path))
                    pygame.mixer.music.play(loops=-1)
                except (FileNotFoundError, AttributeError, pygame.error):
                    pass
            elif isinstance(effect, StopMusic):
                self.music_name = None
                if self._music_ok:
                    try:
                        pygame.mixer.music.stop()
                    except pygame.error:
                        pass

    def _refresh_bitmaps(self, models, frames, palette):
        if (models, frames, palette) == (getattr(self, "_bitmap_models", ()), getattr(self, "frames", {}),
                                          getattr(self, "palette", None)):
            return
        for quad, _ in self.quads:
            quad.release()
        for label, _ in self.text_labels:
            label.release()
        self._bitmap_models, self.frames, self.palette = models, frames, palette
        self.quads, self.text_labels = [], []
        for model in models:
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

    def _refresh_portraits(self, models, palette):
        portraits = tuple(sorted((name, animator.mouth_frame, animator.eye_frame)
                                 for name, animator in self.scene.runtime.state.portrait_animators.items()))
        animations = tuple((model.name, animation) for model in models for animation in model.animations
                           if animation.index is not None)
        if (animations, palette, portraits) == (
            getattr(self, "_portrait_animations", ()), getattr(self, "_portrait_palette", None),
            getattr(self, "portraits", ())
        ):
            return
        for quad, _ in self.portrait_quads:
            quad.release()
        self._portrait_animations, self._portrait_palette, self.portraits = animations, palette, portraits
        self.portrait_quads = []
        for model_name, animation in animations:
            model = next(model for model in models if model.name == model_name)
            animator = self.scene.runtime.state.portrait_animators.get(model_name)
            try:
                if animator is not None:
                    width, height, rgba = self.scene.runtime.content.portrait_frame(
                        animation.index, animation.bkindex or 0, animator.mouth_frame, animator.eye_frame,
                        rgb_palette=palette.colours)
                else:
                    width, height, rgba = self.scene.runtime.content.portrait_data(
                        animation.index, animation.bkindex or 0, rgb_palette=palette.colours)
            except (ValueError, FileNotFoundError, KeyError):
                continue
            quad = ScreenQuad(self.gpu, (width, height))
            quad.write(rgba)
            self.portrait_quads.append((quad, (model.x + animation.x, model.y + animation.y)))

    def _refresh_dialogue(self, dialogue_state):
        """Rebuild the bottom-anchored briefing dialogue block (notes/briefing_dialogue.md §3.3).

        Each logical line keeps the settextcolor it was queued under (one label per line) so an
        older line from a previous speaker never gets repainted in the new speaker's colour.
        """
        if dialogue_state == self.dialogue_state:
            return
        self.dialogue_state = dialogue_state
        for label, _ in self.dialogue_labels:
            label.release()
        self.dialogue_labels = []
        window_name, lines = dialogue_state
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
        width = max(1, round(model.width * 0.90))  # wrap width, §3.3; each label is sized to fit
        physical = [(row, colour) for text, colour in lines for row in _wrap(font, text, width)]
        top = model.y + model.height - round(1.5 * line_height) - (len(physical) - 1) * line_height
        for row, colour in physical:
            label = self.gpu.text((width, line_height), font, color=_TEXT_COLOURS.get(colour, (0, 0, 0)),
                                  background=None, padding=0, outline=True)
            label.set_lines((row,))
            self.dialogue_labels.append((label, (left, top)))
            top += line_height

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
        for quad, (x, y) in self.portrait_quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.text_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        for label, (x, y) in self.dialogue_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def release(self):
        for quad, _ in self.quads:
            quad.release()
        for quad, _ in self.portrait_quads:
            quad.release()
        for label, _ in self.text_labels:
            label.release()
        for label, _ in self.dialogue_labels:
            label.release()
        self.dialogue_labels = []
        self.quads = []
        self.portrait_quads = []
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
    """The (window, (text, colour) lines) fingerprint refresh() diffs against, §3.3's ring buffer."""
    typed = state.dialogue_text[:state.dialogue_typed]
    current = (typed, state.dialogue_line_colour) if typed else None
    lines = (*state.dialogue_lines, current) if current else state.dialogue_lines
    return state.dialogue_window_name, lines


def resolve_text(content, text):
    """Resolve one glue text record without importing pygame or a scene context."""
    if text.string_id is None:
        return None
    try:
        return content.string(text.table or "BRTXT", text.string_id)
    except KeyError:
        return None
