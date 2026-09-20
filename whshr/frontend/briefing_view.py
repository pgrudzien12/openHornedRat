"""Data-driven presentation of a campaign briefing glue script."""

import pygame

from ..controlpanel import button_y, control_panel
from .bitmap_font import BitmapFont
from .gpu import ScreenQuad
from .glue_bitmap import TENT_POSITIONS, bitmap_frame_name, load_bitmap
from .scene_view import SceneView


COLORS = {"red": (220, 30, 30), "green": (40, 180, 60), "black": (0, 0, 0)}
# These are glue-renderer rules, not per-briefing content; see
# notes/briefing_dialogue.md §3.3.  The map window supplies its dimensions.
DIALOGUE_FONT_SLOT = 4
DIALOGUE_LEFT_MARGIN = 0.05
DIALOGUE_WIDTH = 0.90
DIALOGUE_BOTTOM_BASELINE = 1.5
DIALOGUE_LINE_SPACING = 1.10


def _wrap(font, text, width):
    """Wrap one queued BRTXT sentence into the script's two-line caption area."""
    words, lines, current = text.split(), [], ""
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


class BriefingView(SceneView):
    """Render the map, overlays and speakers opened by one briefing script.

    Portrait artwork is selected by the verified glue index table.
    """

    FRAME_ORIGIN = (4, 4)
    PORTRAIT_ORIGIN = (12, 12)
    PANEL_ORIGIN = (4, 164)

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.font = BitmapFont(scene.font)  # glue slot 4: speech subtitles, 22 px native
        self.ui_font = BitmapFont(scene.ui_font)  # glue slot 2: map labels and panel buttons, 12 px native
        layout = scene.briefing
        self.map_ui = layout.get("map")
        # Minimal transcript fixtures retain the previous, text-only display.
        self.transcript_only = self.map_ui is None
        if self.transcript_only:
            self.title = gpu.text((900, 24), self.font, background=None)
            self.title.set_lines((layout["title"],))
            self.body = gpu.text((900, 480), self.font, background=None)
            self.body.set_lines(tuple(line["text"] for line in layout["lines"]))
            return
        position = self.map_ui["position"]
        self.native_size = (position["vx"], position["vy"])
        self.dialogue_width = round(self.native_size[0] * DIALOGUE_WIDTH)
        self.dialogue_left = round(self.native_size[0] * DIALOGUE_LEFT_MARGIN)
        self.dialogue_lines = layout.get("text_lines", 1)
        self.dialogue_height = round(self.font.font.height * self.dialogue_lines * DIALOGUE_LINE_SPACING)
        self.dialogue_top = (self.native_size[1] - round(self.font.font.height * DIALOGUE_BOTTOM_BASELINE)
                             - self.dialogue_height)
        self.map = self._quad("MAP")
        self.overlays = [(self._quad(bitmap_frame_name(spec), True), spec, after) for spec, after in self._bitmap_specs()]
        self.portraits = [self._portrait(window) for window in layout.get("portraits", ())]
        self.map_labels = []
        for spec in self.map_ui["texts"]:
            if spec.get("text"):
                # This is declared by the map resource.  The current campaign
                # maps all select slot 2; fail visibly rather than silently
                # rendering a future window in the wrong font.
                if spec.get("font", 2) != 2:
                    raise ValueError(f"briefing map text requests unsupported glue font {spec['font']}")
                label = gpu.text((spec.get("vx", 160), 20), self.ui_font,
                                 color=COLORS.get(spec.get("color"), (0, 0, 0)), background=None,
                                 padding=0, align="center" if spec.get("format") == 1 else "left", fixed_width=True)
                label.set_lines((spec["text"],))
                self.map_labels.append((label, spec))
        # The glue window uses a transparent subtitle block from 5% to 95%
        # of its own width, anchored against its bottom edge.
        self.dialogue = gpu.text((self.dialogue_width, self.dialogue_height), self.font, background=None, padding=0)
        self._set_dialogue()

    def _bitmap_specs(self):
        # The map window includes title/crosses. Animated objects accumulate as
        # the script reaches them, so only show ones after completed turns.
        for spec in self.map_ui["bitmaps"]:
            yield spec, 0
        for object_ in self.scene.briefing.get("objects", ()):
            for spec in object_["bitmaps"]:
                spec = spec.copy()
                if spec.get("position_source") == "tentpos":
                    tentpos = self.scene.briefing.get("tentpos")
                    if tentpos is None and self.scene.campaign is not None:
                        tentpos = self.scene.campaign.tentpos
                    spec["x"], spec["y"] = TENT_POSITIONS[tentpos or 0]
                yield spec, object_["after_turn"]

    def _quad(self, name, colorkey=False):
        surface = load_bitmap(self.scene.content, name)
        if colorkey:
            surface = surface.convert()
            surface.set_colorkey((0, 0, 255))
            surface = surface.convert_alpha()
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        return quad

    def _portrait(self, window):
        portrait = None
        try:
            width, height, rgba = self.scene.content.portrait_data(window["index"], window["bkindex"])
            portrait = ScreenQuad(self.gpu, (width, height))
            portrait.write(rgba)
        except (FileNotFoundError, ValueError, KeyError):
            pass
        panel = control_panel(window.get("controlpanel", 0))
        frame = {name: self._quad(name, True) for name in ("FRAMETOP", "FRAMELEFT", "FRAMERIGHT", panel.bitmap)}
        labels = []
        for label_id in panel.labels:
            label = self.gpu.text((119, 12), self.ui_font, color=(0, 0, 0), background=None,
                                  padding=0, align="center", fixed_width=True)
            label.set_lines((self.scene.briefing.get("strings", {}).get(label_id, ""),))
            labels.append(label)
        return window, portrait, panel, frame, labels

    def _layout(self):
        width, height = self.gpu.target.size
        native_width, native_height = self.native_size
        scale = min(width / native_width, height / native_height)
        return (width - native_width * scale) / 2, (height - native_height * scale) / 2, scale

    def _set_dialogue(self):
        turns = self.scene.briefing.get("turns", ())
        if not turns or self.scene.dialogue_finished:
            self.dialogue.set_lines(())
            return
        turn = turns[self.scene.turn_index]
        self.dialogue.set_color(COLORS.get(turn.get("speaker_color"), (235, 230, 210)))
        text = turn["lines"][0][:self.scene.characters_visible]
        self.dialogue.set_lines(_wrap(self.font, text, self.dialogue_width))

    def events(self, event):
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            action = self._panel_action(event.pos)
            if action:
                return (action,)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return ("fast_forward_dialogue",)
        return ()

    def _panel_action(self, pos):
        if self.transcript_only:
            return None
        left, top, scale = self._layout()
        point = ((pos[0] - left) / scale, (pos[1] - top) / scale)
        for window, _, panel, _, _ in self.portraits:
            x, y = window["position"]["x"], window["position"]["y"]
            for slot, action in enumerate(panel.actions):
                if action and pygame.Rect(x + 9, y + button_y(window.get("controlpanel", 0), slot), 119, 20).collidepoint(point):
                    return action
        return None

    def status(self):
        turns = self.scene.briefing.get("turns", ())
        return (f"briefing {self.scene.battle_id}, dialogue {min(self.scene.turn_index + 1, len(turns))}/{len(turns)}",)

    def draw(self):
        super().draw()
        if self.transcript_only:
            width, _ = self.gpu.target.size
            self.title.draw((width - self.title.text_size[0]) // 2, 40)
            self.body.draw((width - 900) // 2, 100)
            return
        left, top, scale = self._layout()
        self.map.draw(left, top, self.native_size[0] * scale, self.native_size[1] * scale)
        for quad, spec, after in self.overlays:
            if after <= self.scene.turn_index:
                quad.draw(left + spec.get("x", 0) * scale, top + spec.get("y", 0) * scale,
                          quad.size[0] * scale, quad.size[1] * scale)
        for window, portrait, panel, frame, labels in self.portraits:
            x, y = window["position"]["x"], window["position"]["y"]
            if portrait is not None:
                portrait.draw(left + (x + 12) * scale, top + (y + 12) * scale, 120 * scale, 152 * scale)
            frame["FRAMETOP"].draw(left + (x + 4) * scale, top + (y + 4) * scale, 136 * scale, 8 * scale)
            frame["FRAMELEFT"].draw(left + (x + 4) * scale, top + (y + 12) * scale, 8 * scale, 152 * scale)
            frame["FRAMERIGHT"].draw(left + (x + 132) * scale, top + (y + 12) * scale, 8 * scale, 152 * scale)
            frame[panel.bitmap].draw(left + (x + 4) * scale, top + (y + 164) * scale, 136 * scale, panel.height * scale)
            for slot, label in enumerate(labels):
                y_button = button_y(window.get("controlpanel", 0), slot)
                label.draw(left + (x + 9) * scale, top + (y + y_button + 4) * scale, 119 * scale, 12 * scale)
        for label, spec in self.map_labels:
            label.draw(left + spec.get("x", 0) * scale, top + spec.get("y", 0) * scale,
                       spec.get("vx", 160) * scale, 20 * scale)
        self._set_dialogue()
        self.dialogue.draw(left + self.dialogue_left * scale, top + self.dialogue_top * scale,
                           self.dialogue_width * scale, self.dialogue_height * scale)

    def release(self):
        if self.transcript_only:
            self.title.release(); self.body.release()
            return
        self.map.release()
        for quad, _, _ in self.overlays:
            quad.release()
        for _, portrait, _, frame, labels in self.portraits:
            if portrait is not None:
                portrait.release()
            for quad in frame.values():
                quad.release()
            for label in labels:
                label.release()
        for label, _ in self.map_labels:
            label.release()
        self.dialogue.release()
