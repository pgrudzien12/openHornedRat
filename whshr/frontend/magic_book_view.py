# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""The two-tab Magic Book, drawn from the player's installed book resources."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..campaign_scenes import MagicBookScene
from ..glue_palette import AppPalette
from ..legacy import module
from ..magic_book import ENTRIES
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
BUTTONS = (("book:spells", 14, "VioletATab", 334),
           ("book:items", 104, "GreenATab", 335),
           ("book:done", 350, "GreenATab", 304),
           ("book:back", 440, "BlueATab", 301),
           ("book:next", 530, "RedATab", 300))

class MagicBookView(NativeScreenView[MagicBookScene]):
    def __init__(self, gpu: Gpu, scene: MagicBookScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.content = scene.parent.require_runtime().content
        self.palette = AppPalette.select(1, self.content.palette_tables())
        self.body_font = BitmapFont(scene.parent.font(2))
        self.title_font = BitmapFont(scene.parent.font(5))
        self.emphasis_font = BitmapFont(scene.parent.font(6))
        self.cache = QuadCache(gpu)
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self.labels: list[tuple[TextLabel, Point]] = []
        self.buttons: list[tuple[pygame.Rect, str]] = []
        self.pressed: str | None = None
        self.state: tuple[Any, ...] | None = None
        self.descriptions: dict[str, str] = {}
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
        key = ("cap", letter.upper())

        def crop() -> pygame.Surface | None:
            source = load_optional_bitmap(self.content, "FancyLetters", app_palette=self.palette)
            return source.subsurface(pygame.Rect(*rect)).copy() if source is not None else None

        quad = self.cache.get(key, crop)
        if quad is None:
            return (0, 0)
        self.quads.append((quad, position))
        return quad.size

    def _label(self, value: str, position: Point, font: BitmapFont, colour: Rgb = INK,
               width: int = 240, align: str = "left") -> None:
        label = self.gpu.text((width, font.font.height), font, color=colour, background=None,
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

    def _title(self, title: str, picture_height: int) -> None:
        if not title:
            return
        cap_size = CAPS.get(title[0].upper(), (0, 0, 0, 0))[2:]
        cap_width, cap_height = cap_size
        words = title[1:].split()
        lines: list[str] = []
        line = ""
        for word in words:
            proposed = f"{line} {word}".strip()
            limit = 240 - (cap_width if len(lines) * self.title_font.font.height < cap_height else 0)
            if line and self.title_font.size(proposed)[0] > limit:
                lines.append(line)
                line = word
            else:
                line = proposed
        if line:
            lines.append(line)
        block_height = max(cap_height, len(lines) * self.title_font.font.height)
        y = 288 if picture_height <= 246 else int((375 - (block_height + picture_height + 5)) / 2 + 35 + picture_height + 5)
        total_width = max((self.title_font.size(line)[0] +
                           (cap_width if index * self.title_font.font.height < cap_height else 0)
                           for index, line in enumerate(lines)), default=cap_width)
        x = 50 + max(0, (240 - total_width) // 2)
        self._cap(title[0], (x, y))
        for index, line in enumerate(lines):
            indent = cap_width if index * self.title_font.font.height < cap_height else 0
            self._label(line, (x + indent, y + index * self.title_font.font.height), self.title_font,
                        width=max(1, 290 - x - indent))

    def _markup_width(self, value: str, emph: bool) -> int:
        width = 0
        for char in value:
            if char == "@":
                emph = True
            elif char == "#":
                emph = False
            else:
                width += (self.emphasis_font if emph else self.body_font).size(char)[0]
        return width

    def _markup(self, value: str, x: int, y: int, emph: bool) -> None:
        run = ""
        for char in value + "\0":
            if char in "@#\0":
                if run:
                    font = self.emphasis_font if emph else self.body_font
                    self._label(run, (x, y), font, width=max(1, 590 - x))
                    x += font.size(run)[0]
                    run = ""
                if char != "\0":
                    emph = char == "@"
            else:
                run += char

    def _page(self, value: str) -> int | None:
        page = self.scene.page
        start = self.scene.page_start
        cap_width = 0
        y = 35
        if self.scene.book == 1 and page == 0 and value:
            cap_width, cap_height = self._cap(value[0], (350, 35))
            y += max(0, cap_height - self.body_font.font.height)
            start = max(start, 1)
        pos = start
        first_line = True
        while pos < len(value) and y + self.body_font.font.height <= 410:
            while pos < len(value) and value[pos] in " \t\r\n":
                pos += 1
            if pos >= len(value):
                break
            begin = pos
            emph = value[:begin].count("@") > value[:begin].count("#")
            limit = 240 - (cap_width if first_line else 0)
            while pos < len(value):
                if value[pos] in "\r\n":
                    break
                if value[pos] in " \t" and self._markup_width(value[begin:pos], emph) > 0:
                    end = pos
                    while end < len(value) and value[end] in " \t":
                        end += 1
                    word_end = end
                    while word_end < len(value) and value[word_end] not in " \t\r\n":
                        word_end += 1
                    if self._markup_width(value[begin:word_end], emph) > limit:
                        break
                pos += 1
            line = value[begin:pos].rstrip(" \t")
            if line:
                self._markup(line, 350 + (cap_width if first_line else 0), y, emph)
                y += self.body_font.font.height
                first_line = False
            elif pos == begin:
                pos += 1
        while pos < len(value) and value[pos] in " \t\r\n":
            pos += 1
        return pos if pos < len(value) else None

    def _enabled(self, action: str) -> bool:
        return ({"book:spells": bool(self.scene.known[0]) and self.scene.book != 0,
                 "book:items": bool(self.scene.known[1]) and self.scene.book != 1,
                 "book:back": self.scene.can_back, "book:next": self.scene.can_next}
                .get(action, True))

    def _native_point(self, position: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def refresh(self) -> None:
        state = (self.scene.book, self.scene.entry, self.scene.page, self.pressed)
        if state == self.state:
            return
        self.state = state
        for label, _ in self.labels:
            label.release()
        self.quads, self.labels, self.buttons = [], [], []
        self._bitmap("EncyBook", (0, 0))
        entry = self.scene.entry
        if entry is not None:
            picture, description = ENTRIES[self.scene.book][entry]
            quad = self.cache.get(picture, lambda: load_optional_bitmap(self.content, picture,
                                                                          app_palette=self.palette))
            if quad is not None:
                width, height = quad.size
                title_id = 200 + 50 * self.scene.book + entry
                title = self._string("BKTXT", title_id)
                title_height = max(CAPS.get(title[:1].upper(), (0, 0, 0, 0))[3], self.title_font.font.height)
                y = 282 - height if height <= 246 else int((375 - (title_height + height + 5)) / 2 + 35)
                self.quads.append((quad, (50 + (240 - width) // 2, y)))
                self._title(title, height)
            self.scene.set_next_start(self._page(self._description(description)))
        for action, x, art, label_id in BUTTONS:
            enabled = self._enabled(action)
            pressed = enabled and self.pressed == action
            self._bitmap(f"{art}{'Dn0' if pressed else 'Up'}", (x, 448))
            ox, oy = (3, 3) if pressed else (4, 2)
            y = 448 + (32 - self.body_font.font.height) // 2 + oy
            self._label(self._string("BRTXT", label_id), (x + ox, y), self.body_font,
                        YELLOW if enabled else GREY, width=84, align="center")
            if enabled:
                self.buttons.append((pygame.Rect(x, 448, 84, 32), action))

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
