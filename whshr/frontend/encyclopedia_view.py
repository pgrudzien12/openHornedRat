# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Installed-art Encyclopedia (campaign bestiary) presentation."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..campaign_scenes import EncyclopediaScene
from ..encyclopedia import ENTRIES
from ..glue_palette import AppPalette
from ..legacy import module
from ..scenes import SceneEvent
from .bitmap_font import BitmapFont
from .fancy_letters import CAPS
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, QuadCache, ScreenQuad, TextLabel
from .scene_view import NativeScreenView

Point = tuple[int, int]
Rgb = tuple[int, int, int]
INK: Rgb = (67, 47, 39)
YELLOW: Rgb = (255, 255, 0)
GREY: Rgb = (192, 192, 192)
BUTTONS = (("book:done", 350, "GreenATab", 304),
           ("book:back", 440, "BlueATab", 301),
           ("book:next", 530, "RedATab", 300))


class EncyclopediaView(NativeScreenView[EncyclopediaScene]):
    def __init__(self, gpu: Gpu, scene: EncyclopediaScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.content = scene.parent.require_runtime().content
        self.palette = AppPalette.select(1, self.content.palette_tables())
        self.body_font = BitmapFont(scene.parent.font(2))
        self.title_font = BitmapFont(scene.parent.font(5))
        self.cache = QuadCache(gpu)
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self.labels: list[tuple[TextLabel, Point]] = []
        self.buttons: list[tuple[pygame.Rect, str]] = []
        self.descriptions: dict[str, str] = {}
        self.pressed: str | None = None
        self.state: tuple[Any, ...] | None = None
        self.refresh()

    def _string(self, table: str, identifier: int) -> str:
        try:
            return self.content.string(table, identifier)
        except (KeyError, ValueError):
            return ""

    def _bitmap(self, name: str, position: Point) -> Point | None:
        quad = self.cache.get(name, lambda: load_optional_bitmap(self.content, name, app_palette=self.palette))
        if quad is None:
            return None
        self.quads.append((quad, position))
        return quad.size

    def _cap(self, letter: str, position: Point) -> Point:
        rect = CAPS.get(letter.upper())
        if rect is None:
            return (0, 0)

        def crop() -> pygame.Surface | None:
            source = load_optional_bitmap(self.content, "FancyLetters", app_palette=self.palette)
            return source.subsurface(pygame.Rect(*rect)).copy() if source is not None else None

        quad = self.cache.get(("cap", letter.upper()), crop)
        if quad is None:
            return (0, 0)
        self.quads.append((quad, position))
        return quad.size

    def _label(self, value: str, position: Point, font: BitmapFont, colour: Rgb = INK,
               width: int = 240, align: str = "left") -> None:
        label = self.gpu.text((max(1, width), font.font.height), font, color=colour, background=None,
                              padding=0, align=align, fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, position))

    def _description(self, name: str) -> str:
        if name not in self.descriptions:
            value = ""
            installation = self.content.installation
            if installation is not None:
                try:
                    image = module("pe_resources").PE(installation.file_dir("DLL", "BKTXT.DLL"))
                    resource = next(row for row in image.resources()
                                    if row.type == 10 and str(row.name).upper() == name.upper())
                    value = image.data(resource).decode("latin-1").split("\x1b", 1)[0].rstrip("\x1a\0\r\n")
                except (FileNotFoundError, OSError, StopIteration, UnicodeDecodeError, ValueError):
                    pass
            self.descriptions[name] = value
        return self.descriptions[name]

    def _title(self, title: str) -> None:
        if not title:
            return
        cap_width, cap_height = CAPS.get(title[0].upper(), (0, 0, 0, 0))[2:]
        lines: list[str] = []
        line = ""
        for word in title[1:].split():
            candidate = f"{line} {word}".strip()
            indent = cap_width if len(lines) * self.title_font.font.height < cap_height else 0
            if line and self.title_font.size(candidate)[0] > 240 - indent:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        height = max(cap_height, len(lines) * self.title_font.font.height - 1)
        y = 410 - height
        width = max((self.title_font.size(value)[0] +
                     (cap_width if index * self.title_font.font.height < cap_height else 0)
                     for index, value in enumerate(lines)), default=cap_width)
        x = 50 + max(0, (240 - width) // 2)
        self._cap(title[0], (x, y))
        for index, value in enumerate(lines):
            indent = cap_width if index * self.title_font.font.height < cap_height else 0
            self._label(value, (x + indent, y + index * self.title_font.font.height), self.title_font,
                        width=290 - x - indent)

    def _page(self, value: str) -> int | None:
        pos = self.scene.page_start
        cap_width = 0
        y = 35
        if self.scene.page == 0 and value:
            cap_width, cap_height = self._cap(value[0], (350, 35))
            y += max(0, cap_height - self.body_font.font.height)
            pos = max(pos, 1)
        first_line = True
        paragraph_indent = 3 * self.body_font.size("X")[0]
        line_height = self.body_font.font.height
        while pos < len(value) and y + line_height <= 410:
            paragraph = False
            while pos < len(value) and value[pos] in " \t\r\n":
                paragraph |= value[pos] in "\r\n"
                pos += 1
            if pos >= len(value):
                break
            indent = cap_width if first_line else paragraph_indent if paragraph else 0
            begin = pos
            limit = 240 - indent
            while pos < len(value):
                if value[pos] in "\r\n":
                    break
                if value[pos] in " \t":
                    end = pos
                    while end < len(value) and value[end] in " \t":
                        end += 1
                    word_end = end
                    while word_end < len(value) and value[word_end] not in " \t\r\n":
                        word_end += 1
                    if word_end > end and self.body_font.size(value[begin:word_end])[0] > limit:
                        break
                pos += 1
            line = value[begin:pos].rstrip(" \t")
            if line:
                self._label(line, (350 + indent, y), self.body_font, width=240 - indent)
                y += line_height
                first_line = False
            elif pos == begin:
                pos += 1
        return pos if value[pos:].strip() else None

    def refresh(self) -> None:
        state = (self.scene.entry, self.scene.page, self.pressed)
        if state == self.state:
            return
        self.state = state
        for label, _ in self.labels:
            label.release()
        self.quads, self.labels, self.buttons = [], [], []
        self._bitmap("EncyBook", (0, 0))
        entry = self.scene.entry
        if entry is not None:
            key, picture, description = ENTRIES[entry]
            self._title(self._string("BKTXT", 100 + key))
            quad = self.cache.get(picture, lambda: load_optional_bitmap(self.content, picture,
                                                                          app_palette=self.palette))
            if quad is not None:
                width, height = quad.size
                self.quads.append((quad, (50 + (240 - width) // 2, 285 - height)))
            self.scene.set_next_start(self._page(self._description(description)))
        for action, x, art, label_id in BUTTONS:
            enabled = action == "book:done" or (self.scene.can_back if action == "book:back" else self.scene.can_next)
            self._bitmap(f"{art}{'Dn0' if enabled and self.pressed == action else 'Up'}", (x, 448))
            ox, oy = (3, 3) if enabled and self.pressed == action else (4, 2)
            y = 448 + (32 - self.body_font.font.height) // 2 + oy
            self._label(self._string("BRTXT", label_id), (x + ox, y), self.body_font,
                        YELLOW if enabled else GREY, width=84, align="center")
            if enabled:
                self.buttons.append((pygame.Rect(x, 448, 84, 32), action))

    def _native_point(self, position: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            point = self._native_point(event.pos)
            self.cursors.show("HANDCURSOR" if any(rect.collidepoint(point) for rect, _ in self.buttons) else None)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = next((action for rect, action in self.buttons if rect.collidepoint(point)), None)
            if self.pressed is not None:
                self._click_cue(4)
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            action, self.pressed = self.pressed, None
            self.refresh()
            if action and any(rect.collidepoint(point) and candidate == action for rect, candidate in self.buttons):
                self._click_cue(3)
                return (action,)
        return ()

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def release(self) -> None:
        for label, _ in self.labels:
            label.release()
        self.cache.release()
        self.cursors.release()
