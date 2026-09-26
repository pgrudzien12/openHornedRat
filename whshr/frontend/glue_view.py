# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""First generic pygame adapter for static ``GlueScene`` windows.

This is intentionally narrow: bitmap composition and hotspot hit-testing are
shared now; text, portraits and executable-owned widgets remain separate
adapters until their renderer rules are moved out of compatibility views.
"""

import io
import sys
from collections.abc import Iterable, Sequence
from typing import Any

import pygame

from ..campaign_state import CampaignState, is_caravan_window, offered_refs
from ..glue import MissionRecord, MissionRef
from ..glue_content import GlueContent
from ..glue_scene import GlueScene
from ..scenes import SceneEvent
from ..speech import load_speech
from ..controlpanel import button_y, control_panel
from ..glue_animation import GlueBitmapAnimator
from ..glue_render import GlueRenderModel, RenderBitmap, RenderHotspot, RenderText, build_render_model
from ..glue_runtime import Diagnostic, GlueInput, GlueRuntimeState, PlayMusic, PlaySpeech, StopMusic, StopSpeech
from ..glue_palette import AppPalette
from .bitmap_font import BitmapFont
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, ScreenQuad, TextLabel
from .scene_view import NativeScreenView

Point = tuple[int, int]
Rgb = tuple[int, int, int]
Models = tuple[GlueRenderModel, ...]
Frames = dict[tuple[str, str | int | None], str]  # (window, object name or bitmap index) -> current frame name
MissionRow = tuple[MissionRef, str, str, int, int, bool]  # reference, title, payment, x, y, selected

MIXER_CHANNELS = 8  # matches movie_view's cutscene mixer; music runs on pygame's separate music channel
MUSIC_VOLUME = 1  # engine-level mix setting, not game data: setmidivolume/setwavvolume are unused by any
                     # script (notes/briefing_dialogue.md §2.1) and default 100, so there is no data value to read
MISSION_ROW_HEIGHT = 88
MISSION_TEXT_INSET = 12
HINT_BOTTOM_MARGIN = 10


def _ensure_mixer() -> bool:
    """Best-effort mixer setup; audio stays silently unavailable without a usable audio device."""
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        if pygame.mixer.get_num_channels() < MIXER_CHANNELS:
            pygame.mixer.set_num_channels(MIXER_CHANNELS)
        return True
    except pygame.error:
        return False


class GlueView(NativeScreenView[GlueScene]):
    """Draw static runtime windows and translate click/release hotspots."""

    def __init__(self, gpu: Gpu, scene: GlueScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.models: Models = ()
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self.portrait_quads: list[tuple[ScreenQuad, Point]] = []
        self.text_labels: list[tuple[TextLabel, Point]] = []
        self.dialogue_labels: list[tuple[TextLabel, Point]] = []
        self.dialogue_state: tuple[str, tuple[Any, ...]] | None = None
        self.panel_quads: list[tuple[ScreenQuad, Point]] = []
        self.panel_labels: list[tuple[TextLabel, Point]] = []
        self.panel_buttons: list[tuple[str, pygame.Rect, str]] = []
        self.mission_quads: list[tuple[ScreenQuad, Point]] = []
        self.mission_labels: list[tuple[TextLabel, Point]] = []
        self.mission_rows: list[tuple[pygame.Rect, MissionRef]] = []
        self.hint_label: TextLabel | None = None
        self.hover_hint: str | None = None
        self.bitmap_animators: dict[tuple[str, int], GlueBitmapAnimator] = {}
        self.music_name: str | None = None
        self._music_ok = _ensure_mixer()
        self._speech_sound: pygame.mixer.Sound | None = None
        self.pressed: RenderHotspot | None = None
        self._pressed_button: str | None = None
        # Change fingerprints of the refresh groups (see `refresh`).
        self._bitmap_models: Models = ()
        self.frames: Frames = {}
        self.palette: AppPalette | None = None
        self._portrait_animations: tuple[Any, ...] = ()
        self._portrait_palette: AppPalette | None = None
        self.portraits: tuple[Any, ...] = ()
        self._panel_state: tuple[Any, ...] | None = None
        self._mission_state: tuple[Any, ...] | None = None
        self._drawn_hint: str | None = None
        self.refresh()

    def refresh(self) -> None:
        """Rebuild GPU quads after the runtime changes its active windows.

        Split into independent groups so a portrait's mouth/eye frame or a typing dialogue line -
        which change almost every tick - only rebuild their own small quads, not every bitmap on
        screen (the 640x480 map foremost): re-decoding that on every blink was the actual cost
        behind a briefing running at a few FPS.
        """
        self._process_music()
        runtime = self.scene.require_runtime()
        models = tuple(build_render_model(runtime.content, window, runtime.state.object_positions)
                       for window in runtime.state.windows)
        frames: Frames = {(animation.window_name, animation.object_name): animation.animator.display_name
                          for animation in runtime.state.animations}
        frames.update(self._static_animation_frames(models, frames))
        palette = self._palette(models)
        self.models = models
        self._refresh_bitmaps(models, frames, palette)
        self._refresh_portraits(models, palette)
        self._refresh_panel(models, palette)
        self._refresh_missions(models, palette)
        self._refresh_dialogue(_dialogue_state(runtime.state))

    def _static_animation_frames(self, models: Models, runtime_frames: Frames) -> Frames:
        active: dict[tuple[str, int], GlueBitmapAnimator] = {}
        frames: Frames = {}
        for model in models:
            for index, bitmap in enumerate(model.bitmaps):
                key = (model.name, index)
                if (model.name, bitmap.object_name) in runtime_frames or not bitmap.animation:
                    continue
                spec = {"bitmap": bitmap.name, **dict(bitmap.animation)}
                animator = self.bitmap_animators.get(key)
                if animator is None:
                    animator = GlueBitmapAnimator(spec)
                active[key] = animator
                if animator.display_name == bitmap.name and "animstartframe" in spec:
                    frames[key] = f"{bitmap.name}{spec['animstartframe']}"
                else:
                    frames[key] = animator.display_name
        self.bitmap_animators = active
        return frames

    def _process_music(self) -> None:
        """Drain playmidi/stopmidi/diagnostic effects (notes/briefing_dialogue.md §2.1: replace abruptly, loop forever)."""
        for effect in self.scene.take_effects():
            if isinstance(effect, Diagnostic):
                print(format_diagnostic(effect), file=sys.stderr)
            elif isinstance(effect, PlayMusic):
                self.music_name = effect.name
                if not self._music_ok:
                    continue
                try:
                    installation = self.scene.require_runtime().content.installation
                    if installation is None:
                        continue
                    path = installation.binary_file("MUSIC", f"{effect.name}.MID")
                    pygame.mixer.music.load(str(path))
                    pygame.mixer.music.set_volume(MUSIC_VOLUME)
                    pygame.mixer.music.play(loops=-1)
                except (FileNotFoundError, AttributeError, pygame.error):
                    pass
            elif isinstance(effect, PlaySpeech):
                self._play_speech(effect.string_id)
            elif isinstance(effect, StopSpeech):
                self._stop_speech()
            elif isinstance(effect, StopMusic):
                self.music_name = None
                if self._music_ok:
                    try:
                        pygame.mixer.music.stop()
                    except pygame.error:
                        pass

    def _play_speech(self, string_id: int) -> None:
        """Play the recording of a text line, replacing the previous clip (notes/briefing_dialogue.md §3.2);
        a missing or unreadable clip leaves the line as text only."""
        self._stop_speech()
        installation = self.scene.require_runtime().content.installation
        if not self._music_ok or installation is None:
            return
        data = load_speech(installation, string_id)
        if data is None:
            return
        try:
            self._speech_sound = pygame.mixer.Sound(io.BytesIO(data))
            self._speech_sound.play()
        except pygame.error:
            self._speech_sound = None

    def _stop_speech(self) -> None:
        if self._speech_sound is not None:
            self._speech_sound.stop()
            self._speech_sound = None

    def _refresh_bitmaps(self, models: Models, frames: Frames, palette: AppPalette) -> None:
        if (models, frames, palette) == (self._bitmap_models, self.frames, self.palette):
            return
        content = self.scene.require_runtime().content
        for quad, _ in self.quads:
            quad.release()
        for label, _ in self.text_labels:
            label.release()
        self._bitmap_models, self.frames, self.palette = models, frames, palette
        self.quads, self.text_labels = [], []
        for model in models:
            for index, bitmap in enumerate(model.bitmaps):
                if not _bitmap_visible(bitmap, self.scene.campaign):
                    continue
                name = frames.get((model.name, bitmap.object_name), frames.get((model.name, index), bitmap.name))
                surface = load_optional_bitmap(content, name, app_palette=palette)
                if surface is None:
                    continue
                quad = ScreenQuad(self.gpu, surface.get_size())
                quad.write(pygame.image.tobytes(surface, "RGBA"))
                self.quads.append((quad, (model.x + bitmap.x, model.y + bitmap.y)))
            for text in model.texts:
                value = resolve_text(content, text)
                if value is None:
                    continue
                try:
                    font = BitmapFont(self.scene.font(text.font or 2))
                except (KeyError, ValueError):
                    continue
                self.text_labels.append(_place_text(self.gpu, font, value, text, model))

    def _refresh_portraits(self, models: Models, palette: AppPalette) -> None:
        runtime = self.scene.require_runtime()
        portraits = tuple(sorted((name, animator.mouth_frame, animator.eye_frame)
                                 for name, animator in runtime.state.portrait_animators.items()))
        animations = tuple((model.name, animation) for model in models for animation in model.animations
                           if animation.index is not None)
        if (animations, palette, portraits) == (self._portrait_animations, self._portrait_palette, self.portraits):
            return
        for quad, _ in self.portrait_quads:
            quad.release()
        self._portrait_animations, self._portrait_palette, self.portraits = animations, palette, portraits
        self.portrait_quads = []
        for model_name, animation in animations:
            model = next(model for model in models if model.name == model_name)
            animator = runtime.state.portrait_animators.get(model_name)
            index = runtime.portrait_index(model_name, animation.index)
            try:
                if animator is not None:
                    width, height, rgba = runtime.content.portrait_frame(
                        index, animation.bkindex or 0, animator.mouth_frame, animator.eye_frame,
                        rgb_palette=palette.colours)
                else:
                    width, height, rgba = runtime.content.portrait_data(
                        index, animation.bkindex or 0, rgb_palette=palette.colours)
            except (ValueError, FileNotFoundError, KeyError):
                continue
            quad = ScreenQuad(self.gpu, (width, height))
            quad.write(rgba)
            # The portrait sits inside the frame at a fixed offset, not at the [ANIM] block's own
            # x/y (always 0,0 in the data); notes/mission_selection.md §9.3.
            self.portrait_quads.append((quad, (model.x + 12, model.y + 12)))

    def _refresh_panel(self, models: Models, palette: AppPalette) -> None:
        """Draw the speaker frame and its control-panel buttons (notes/mission_selection.md §9.3-9.4).

        Button geometry, panel bitmaps and BRTXT label ids come from ``whshr.controlpanel`` (also
        used by the legacy briefing view); only "toggle_pause"/"abort_briefing" (panel 1's Pause
        and Abort) map onto runtime behaviour that exists, so those are the only clickable actions
        wired here - every panel still renders in full, per that module's traced/labelled slots.
        """
        animations = tuple((model.name, animation) for model in models for animation in model.animations
                           if animation.index is not None)
        runtime = self.scene.require_runtime()
        paused = runtime.state.paused
        state = (animations, palette, paused)
        if state == self._panel_state:
            return
        for quad, _ in self.panel_quads:
            quad.release()
        for label, _ in self.panel_labels:
            label.release()
        self._panel_state = state
        self.panel_quads, self.panel_labels, self.panel_buttons = [], [], []
        font: BitmapFont | None
        try:
            font = BitmapFont(self.scene.font(2))
        except (KeyError, ValueError):
            font = None
        content = runtime.content
        for model_name, animation in animations:
            model = next(model for model in models if model.name == model_name)
            origin = (model.x, model.y)
            panel = control_panel(animation.controlpanel or 0)
            for name, (dx, dy) in (("FRAMETOP", (4, 4)), ("FRAMELEFT", (4, 12)), ("FRAMERIGHT", (132, 12)),
                                   (panel.bitmap, (4, 164))):
                self._add_panel_bitmap(content, name, (origin[0] + dx, origin[1] + dy), palette)
            if font is None:
                continue
            for slot, (label_id, action) in enumerate(zip(panel.labels, panel.actions or (None,) * len(panel.labels))):
                y = button_y(animation.controlpanel or 0, slot)
                if action == "toggle_pause":
                    label_id = 312 if paused else 310
                self._add_panel_bitmap(content, "FRAMEBUTTONUP", (origin[0] + 9, origin[1] + y), palette)
                # notes/mission_selection.md §9.4 says the ANIM block's own settextcolor, but that
                # field isn't threaded through RenderAnimation yet; black matches what's actually
                # observed and is FrameButtonUp's own default label colour either way.
                label = self.gpu.text((119, 20), font, color=(0, 0, 0), background=None, padding=0,
                                      align="center", fixed_width=True)
                try:
                    label.set_lines((content.string("BRTXT", label_id),))
                except KeyError:
                    label.set_lines(())
                # TextLabel only centres horizontally; nudge down to vertically centre the text
                # in the 20px button (it draws from the top otherwise, reading too high).
                label_y = origin[1] + y + max(0, (20 - font.font.height) // 2)
                self.panel_labels.append((label, (origin[0] + 9, label_y)))
                if action:
                    rect = pygame.Rect(origin[0] + 9, origin[1] + y, 119, 20)
                    self.panel_buttons.append((model.name, rect, action))

    def _refresh_missions(self, models: Models, palette: AppPalette) -> None:
        runtime = self.scene.require_runtime()
        rows = _mission_rows(runtime.content, models, runtime.state.selected_mission,
                             getattr(self.scene.campaign, "taken_missions", None))
        state = (rows, palette)
        if state == self._mission_state:
            return
        for quad, _ in self.mission_quads:
            quad.release()
        for label, _ in self.mission_labels:
            label.release()
        self._mission_state = state
        self.mission_quads, self.mission_labels, self.mission_rows = [], [], []
        try:
            font = BitmapFont(self.scene.font(2))
        except (KeyError, ValueError):
            return
        content = runtime.content
        for reference, title, payment, x, y, selected in rows:
            surface = load_optional_bitmap(content, "Scroll0" if selected else "Scroll1", app_palette=palette)
            if surface is not None:
                quad = ScreenQuad(self.gpu, surface.get_size())
                quad.write(pygame.image.tobytes(surface, "RGBA"))
                self.mission_quads.append((quad, (x, y)))
                width, height = surface.get_size()
            else:
                width, height = 320, MISSION_ROW_HEIGHT
            lines = _wrap(font, title, max(1, width - 2 * MISSION_TEXT_INSET))
            if payment:
                lines.append(payment)
            text = self.gpu.text((max(1, width - 2 * MISSION_TEXT_INSET), max(1, height - 8)), font, color=(0, 0, 0),
                                 background=None, padding=0, fixed_width=True)
            text.set_lines(tuple(lines))
            self.mission_labels.append((text, (x + MISSION_TEXT_INSET, y + 4 + font.font.height // 2)))
            self.mission_rows.append((pygame.Rect(x, y, width, height), reference))

    def _refresh_hint(self) -> None:
        hint = self.hover_hint
        if hint == self._drawn_hint:
            return
        if self.hint_label is not None:
            self.hint_label.release()
        self._drawn_hint = hint
        self.hint_label = None
        if not hint:
            return
        try:
            font = BitmapFont(self.scene.font(4))
        except (KeyError, ValueError):
            return
        self.hint_label = self.gpu.text((640, 32), font, color=(220, 30, 30), background=None,
                                        padding=0, align="center", fixed_width=True)
        self.hint_label.set_lines((hint,))

    def _add_panel_bitmap(self, content: GlueContent, name: str, position: Point, palette: AppPalette) -> None:
        surface = load_optional_bitmap(content, name, app_palette=palette)
        if surface is None:
            return
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self.panel_quads.append((quad, position))

    def _refresh_dialogue(self, dialogue_state: tuple[str, tuple[Any, ...]]) -> None:
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

    def _palette(self, models: Models) -> AppPalette:
        """Select the one application palette active for the runtime windows."""
        runtime = self.scene.require_runtime()
        palette_id = runtime.state.palette_id
        embedded = None
        if palette_id < 0 and models and models[0].bitmaps:
            embedded = runtime.content.bitmap_data(models[0].bitmaps[0].name).palette
        return AppPalette.select(palette_id, runtime.content.palette_tables(), embedded=embedded)

    @staticmethod
    def hotspot_at(models: Sequence[GlueRenderModel], point: tuple[float, float]) -> RenderHotspot | None:
        """Return the last-painted hotspot at native coordinates, if any."""
        for model in reversed(models):
            for hotspot in reversed(model.hotspots):
                if pygame.Rect(model.x + hotspot.x, model.y + hotspot.y,
                               hotspot.width, hotspot.height).collidepoint(point):
                    return hotspot
        return None

    def _native_point(self, pos: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (pos[0] - left) / scale, (pos[1] - top) / scale

    def _panel_button_at(self, point: tuple[float, float]) -> str | None:
        for _, rect, action in reversed(self.panel_buttons):
            if rect.collidepoint(point):
                return action
        return None

    def _mission_at(self, point: tuple[float, float]) -> MissionRef | None:
        for rect, reference in reversed(self.mission_rows):
            if rect.collidepoint(point):
                return reference
        return None

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.MOUSEMOTION:
            hotspot = self.hotspot_at(self.models, self._native_point(event.pos))
            self.hover_hint = _caravan_hint(self.scene.campaign, self.models, hotspot)
            self._refresh_hint()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            point = self._native_point(event.pos)
            mission = self._mission_at(point)
            if mission is not None:
                self._pressed_button = None
                self.pressed = None
                return (GlueInput("mission-select", mission.key),)
            self._pressed_button = self._panel_button_at(point)
            self.pressed = None if self._pressed_button is not None else self.hotspot_at(self.models, point)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            point = self._native_point(event.pos)
            pressed_button, self._pressed_button = self._pressed_button, None
            pressed, self.pressed = self.pressed, None
            released_button = self._panel_button_at(point)
            if pressed_button is not None and pressed_button == released_button:
                return (GlueInput("panel-action", pressed_button),)
            released = self.hotspot_at(self.models, point)
            if pressed is not None and pressed == released and pressed.click_text is not None:
                return (GlueInput("hotspot-speech", f"{pressed.click_text}:{pressed.click_count}"),)
            if pressed is not None and pressed == released:
                return (GlueInput("hotspot-release", pressed.target),)
            if pressed is None and released is None and pressed_button is None and released_button is None:
                return (GlueInput("dialogue-drain"),)
        return ()

    def animate(self, seconds: float) -> None:
        changed = any(animator.tick(round(seconds * 1000)).redrawn for animator in self.bitmap_animators.values())
        if changed:
            self.refresh()

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for quad, (x, y) in self.portrait_quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for quad, (x, y) in self.panel_quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for quad, (x, y) in self.mission_quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.text_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        for label, (x, y) in self.panel_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        for label, (x, y) in self.mission_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        for label, (x, y) in self.dialogue_labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        if self.hint_label is not None:
            _, hint_height = self.hint_label.text_size
            self.hint_label.draw(left, top + (self.NATIVE_SIZE[1] - hint_height - HINT_BOTTOM_MARGIN) * scale,
                                 self.hint_label.size[0] * scale, self.hint_label.size[1] * scale)

    def release(self) -> None:
        for quad, _ in self.quads:
            quad.release()
        for quad, _ in self.portrait_quads:
            quad.release()
        for quad, _ in self.panel_quads:
            quad.release()
        for quad, _ in self.mission_quads:
            quad.release()
        for label, _ in self.text_labels:
            label.release()
        for label, _ in self.panel_labels:
            label.release()
        for label, _ in self.mission_labels:
            label.release()
        for label, _ in self.dialogue_labels:
            label.release()
        if self.hint_label is not None:
            self.hint_label.release()
        self.dialogue_labels = []
        self.quads = []
        self.portrait_quads = []
        self.panel_quads = []
        self.panel_labels = []
        self.mission_quads = []
        self.mission_labels = []
        self.mission_rows = []
        self.text_labels = []
        self.hint_label = None


# notes/briefing_dialogue.md §3.4, the front-end's settextcolor name -> RGB table.
_TEXT_COLOURS: dict[str, Rgb] = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 255, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "magenta": (255, 0, 255), "cyan": (0, 255, 255),
    "gray": (127, 127, 127), "lgray": (192, 192, 192), "dkred": (127, 0, 0), "dkgreen": (0, 127, 0),
    "dkblue": (0, 0, 127), "olive": (127, 127, 0), "purple": (127, 0, 127), "drab": (0, 127, 127),
}


def _place_text(gpu: Gpu, font: BitmapFont, value: str, text: RenderText,
                model: GlueRenderModel) -> tuple[TextLabel, Point]:
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
        label = gpu.text((width, line_height), font, color=_TEXT_COLOURS.get(text.colour or "", (0, 0, 0)),
                         background=None, padding=0, align="center", fixed_width=True)
        label.set_lines((value,))
        return label, (origin_x, origin_y + text.height)
    # Only formats 1 and 7 use vx as a width to bound the label; 3/5/6/8 draw at their natural
    # content width, so a small vx (a real value there, just not a size - e.g. a format 6 town
    # label's vx=10) must not clip the canvas, or only the first letter or two survives.
    canvas_width = max(1, text.width) if fmt == 7 else 640
    label = gpu.text((canvas_width, line_height), font,
                     color=_TEXT_COLOURS.get(text.colour or "", (0, 0, 0)), background=None, padding=0,
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


def _wrap(font: BitmapFont, text: str, width: int) -> list[str]:
    """Greedy word-wrap: a new word joins the current line unless it would exceed ``width`` (§3.3)."""
    words = text.split(" ")
    lines: list[str] = []
    current = words[0] if words else ""
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.size(candidate)[0] <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _dialogue_state(state: GlueRuntimeState) -> tuple[str, tuple[Any, ...]]:
    """The (window, (text, colour) lines) fingerprint refresh() diffs against, §3.3's ring buffer."""
    if not state.windows:
        return "", ()  # nothing is open (a request parked the windows): no stale text
    typed = state.dialogue_text[:state.dialogue_typed]
    current = (typed, state.dialogue_line_colour) if typed else None
    lines = (*state.dialogue_lines, current) if current else state.dialogue_lines
    return state.dialogue_window_name, lines


def _bitmap_visible(bitmap: RenderBitmap, campaign: CampaignState | None) -> bool:
    """Apply a bitmap's campaign-count dependency when a campaign is active."""
    if not bitmap.name.casefold().startswith("carscroll"):
        return True
    depend = dict(bitmap.animation).get("depend")
    if depend is None or campaign is None:
        return True
    try:
        return int(depend) <= len(campaign.missions)
    except (TypeError, ValueError, AttributeError):
        return True


def _caravan_hint(campaign: CampaignState | None, models: Iterable[GlueRenderModel],
                  hotspot: RenderHotspot | None) -> str | None:
    """Resolve a caravan hotspot hint, including the coffer value placeholder."""
    if campaign is None or hotspot is None or not any(is_caravan_window(model.name) for model in models):
        return None
    hint_id = 402 if hotspot.hint_id == -1 else hotspot.hint_id
    if hint_id is None:
        return None
    return campaign.hint(hint_id, campaign.coffers) if hint_id == 402 else campaign.hint(hint_id)


def _mission_rows(content: GlueContent, models: Iterable[GlueRenderModel], selected: MissionRef | None,
                  taken: Iterable[MissionRef] | None = None) -> tuple[MissionRow, ...]:
    """Rows on offer; ``taken=None`` (no campaign) shows every record ungated."""
    rows: list[MissionRow] = []
    for model in models:
        for mission_list in model.mission_lists:
            y = model.y + mission_list.y
            windows = {reference.window for reference in mission_list.missions}
            offered: set[Any] = set()
            for window in windows:
                records = [record for record in content.window(window).records if isinstance(record, MissionRecord)]
                offered.update(offered_refs(records, taken or ()))
            for reference in mission_list.missions:
                if taken is not None and reference not in offered:
                    continue
                record = content.mission(reference)
                try:
                    name_id = next(int(field.argument.split("=", 1)[1].split(None, 1)[0])
                                   for field in record.fields
                                   if field.command == "set" and field.argument.casefold().startswith("res="))
                    label = content.string("BRTXT", name_id)
                except (KeyError, StopIteration, TypeError, ValueError):
                    label = reference.key
                rows.append((reference, label, _mission_payment(record), model.x + mission_list.x, y,
                             reference == selected))
                y += MISSION_ROW_HEIGHT
    return tuple(rows)


def _mission_payment(record: MissionRecord) -> str:
    cash = next((field.argument for field in record.fields if field.command == "cash"), "")
    parts = [part.strip() for part in cash.split(",")]
    if len(parts) < 3:
        return ""
    try:
        return f"({int(parts[1])}, {int(parts[2])})"
    except ValueError:
        return ""


def format_diagnostic(diagnostic: Diagnostic) -> str:
    """Render one interpreter ``Diagnostic`` as a single log line."""
    return f"glue: {diagnostic.location}: {diagnostic.message}"


def resolve_text(content: GlueContent, text: RenderText) -> str | None:
    """Resolve one glue text record without importing pygame or a scene context."""
    if text.string_id is None:
        return None
    try:
        return content.string(text.table or "BRTXT", text.string_id)
    except KeyError:
        return None
