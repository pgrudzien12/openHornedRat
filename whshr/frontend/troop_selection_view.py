# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Native P0/P1/P5 troop-book presentation (``notes/troop_selection.md`` §§2--5, §7).

The screen is deliberately a renderer: selection, affordability and marching order remain in
``TroopSelectionScene`` / ``TroopSelection``.  Its fixed layout constants are gathered here,
because this is a front-end-owned window rather than a WND.DLL-defined one.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..campaign_scenes import TroopSelectionScene
from ..glue_palette import AppPalette
from ..scenes import SceneEvent
from ..script import resource_name
from ..troop_selection import TroopRow, TroopSelection, STATUS_AVAILABLE, STATUS_DESTROYED, STATUS_EXCLUDED, STATUS_NOT_HIRED
from .bitmap_font import BitmapFont
from .cursors import CursorController
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, ScreenQuad, TextLabel
from .scene_view import NativeScreenView


# notes/troop_selection.md §§2--5, §7.  Coordinates are native 640x480 pixels.
Rgb = tuple[int, int, int]
Point = tuple[int, int]
BLACK, BLUE, GREY, RED, YELLOW = (0, 0, 0), (0, 0, 180), (127, 127, 127), (255, 0, 0), (255, 255, 0)
BUTTONS: tuple[tuple[str, int, str, int], ...] = (
    ("abort", 225, "BrownATab", 307), ("done", 325, "GreenATab", 304),
    ("page:back", 425, "BlueATab", 301), ("page:next", 525, "RedATab", 300),
)
BUTTON_Y, BUTTON_SIZE = 448, (84, 32)
P0_ROWS, P1_ROWS = 6, 7
# notes/troop_selection.md §2: the named cursor groups of the game's executable (loaded at runtime, never copied).
CURSORS: dict[str, str] = {
    "default": "SWORDCURSOR", "help": "HELPCURSOR", "toggle": "PENCILCURSOR", "no_toggle": "NOPENCILCURSOR",
    "scroll_up": "UPARROWCURSOR", "scroll_down": "DOWNARROWCURSOR", "grab_open": "HANDOPENCURSOR",
    "grab_closed": "HANDCLOSECURSOR",
}

STATUS_TEXT: dict[str, int] = {STATUS_NOT_HIRED: 415, STATUS_EXCLUDED: 416, STATUS_DESTROYED: 417}


class TroopSelectionView(NativeScreenView[TroopSelectionScene]):
    """Draw troop-book pages and translate their documented mouse input."""

    def __init__(self, gpu: Gpu, scene: TroopSelectionScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self.labels: list[tuple[TextLabel, Point]] = []
        self.buttons: list[tuple[pygame.Rect, str]] = []
        self.rows: list[tuple[pygame.Rect, int]] = []
        self.carried_quads: list[tuple[ScreenQuad, Point]] = []
        self.carried_labels: list[tuple[TextLabel, Point]] = []
        self.banner_surfaces: dict[str, pygame.Surface | None] = {}
        self.state: tuple[Any, ...] | None = None
        self.hover_march_index: int | None = None
        self.pointer: tuple[float, float] | None = None
        self.scroll_direction: str | None = None
        self.scroll_elapsed = 0.0
        self.pressed_button: str | None = None
        # Mode 0 without a company immediately transitions on the next scene tick (§1.1).
        # Do not require render-only fonts/resources during that one-frame handoff.
        if scene.phase == "skip":
            return
        self.content = scene.glue_scene.require_runtime().content
        self.body_font = BitmapFont(scene.glue_scene.font(2))
        self.heading_font = BitmapFont(scene.glue_scene.font(4))
        self.palette = AppPalette.select(1, self.content.palette_tables())
        self.banner_files: dict[str, str] | None = None
        if self.content.installation is None:
            raise RuntimeError("troop selection needs an installation")
        self.cursors = CursorController(self.content.installation, default=CURSORS["default"])
        self.cursors.show(None)
        self.refresh()

    def _model(self) -> TroopSelection:
        model = self.scene.model
        if model is None:
            raise RuntimeError("troop selection has no model")
        return model

    def refresh(self) -> None:
        if self.scene.phase == "skip":
            return
        model = self.scene.model
        state = (self.scene.phase, self.scene.page, self.scene.march_offset, self.scene.picked_whoami,
                 self.hover_march_index, self.pressed_button,
                 tuple(model.selection) if model else (), model.total_cost if model else 0)
        if state == self.state:
            return
        self.state = state
        self._release_contents()
        self._bitmap("TroopBook", (0, 0))
        if self.scene.phase == "select":
            self._p0()
            self._buttons()
        elif self.scene.phase == "march_order":
            self._p1()
            self._buttons()
        elif self.scene.phase == "bankrupt":
            self._p5()
        else:
            return

    def _p0(self) -> None:
        model, height = self._model(), self.body_font.font.height
        self._heading(self._title(400), 25)
        for x, text_id in ((345, 409), (425, 410), (505, 413)):
            self._label(self._string("BKTXT", text_id), x, 50, BLACK)
        start = self.scene.page * P0_ROWS
        for row_index, whoami in enumerate(tuple(model.company)[start:start + P0_ROWS]):
            row = model.row(whoami)
            y = 50 + height + 4 * height * row_index
            self._regiment(row, y, 45, p1=False)
            self.rows.append((pygame.Rect(45, y - height, 550, 4 * height), whoami))
        shown = min(P0_ROWS, max(0, len(model.company) - start))
        total_y = 50 + 4 * height * shown
        self._label_right(self._string("BRTXT", 303), 495, total_y, BLACK)
        total_colour = RED if not model.affordable else BLACK
        self._label(f"{model.total_cost} {self._string('BKTXT', 414)}", 505, total_y, total_colour)
        if model.roster_full:
            self._label(self._string("BKTXT", 613), 45, 400 - 2 * height, BLACK)
        coffers = self.scene.campaign.coffers if self.scene.campaign is not None else 0
        self._center(self._string("BKTXT", 5006, coffers + model.prepaid), 400 - 2 * height, BLACK)
        self._center(self._string("BRTXT", 314), 400, BLUE)
        self._center(self._string("BRTXT", 316), 400 + height, BLUE)

    def _p1(self) -> None:
        model, height = self._model(), self.body_font.font.height
        self._heading(self._title(401), 25)
        for visible, whoami in enumerate(model.selection[self.scene.march_offset:self.scene.march_offset + P1_ROWS]):
            index = self.scene.march_offset + visible
            y = 50 + height + 4 * height * visible
            strip = "BookScroll1" if index == self.hover_march_index else "BookScroll0"
            if whoami != self.scene.picked_whoami:
                self._bitmap(strip, (145, y - 10))
                self._bitmap("BookScroll2", (83, y - 10))
                self._center(str(index + 1), y, BLACK, x=83, width=56)
                self._regiment(model.row(whoami), y, 157, p1=True)
            self.rows.append((pygame.Rect(83, y - height, 482, 4 * height), index))
        # notes/troop_selection.md §5.2: "the strip (BookScroll0) with its contents follows the
        # cursor while the original row is hidden". Built once here (only when picked_whoami
        # changes, since this is part of refresh()'s diffed rebuild); draw() repositions the
        # already-built pieces from the live pointer every frame instead of rebuilding GPU
        # textures on every mouse-move event (that rebuild was the cause of a severe FPS drop).
        if self.scene.picked_whoami is not None:
            self._build_carried_regiment(self.scene.picked_whoami)
        else:
            self.carried_quads, self.carried_labels = [], []
        self._center(self._string("BRTXT", 315), 400, BLUE)
        self._center(self._string("BRTXT", 316), 400 + height, BLUE)

    def _build_carried_regiment(self, whoami: int) -> None:
        """Draw ``whoami``'s row at y=0 into ``self.carried_quads``/``carried_labels``, so their
        stored position *is* an offset from the row's own origin (85, 157) for draw() to add the
        live pointer-derived y to, every frame, without rebuilding GPU textures."""
        saved_quads, saved_labels = self.quads, self.labels
        self.quads, self.labels = [], []
        self._bitmap("BookScroll0", (145, -10))
        self._regiment(self._model().row(whoami), 0, 157, p1=True)
        self.carried_quads, self.carried_labels = self.quads, self.labels
        self.quads, self.labels = saved_quads, saved_labels

    def _p5(self) -> None:
        """Draw the bankruptcy page; notes/troop_selection.md §7.

        The availability test and its displayed coffer amount both include the already
        evaluated initial payment, as on P0's coffer line (§3.5).
        """
        height = self.body_font.font.height
        model = self._model()
        heading_y = 50 + 8 * height
        self._center(self._string("BKTXT", 601), heading_y, BLACK, font=self.heading_font)
        self._center(self._string("BKTXT", 602, model.coffers + model.prepaid),
                     heading_y + self.heading_font.font.height, BLACK)
        self._center(self._string("BKTXT", 603, model.forced_cost),
                     heading_y + self.heading_font.font.height + height, BLACK)
        self._button("done", 325, "GreenATab", 304, True)

    def _regiment(self, row: TroopRow, y: int, x: int, *, p1: bool) -> None:
        regiment, height = row.regiment, self.body_font.font.height
        name_colour = GREY if row.status == STATUS_NOT_HIRED else RED if row.status == STATUS_DESTROYED else BLACK
        skull = min(4, (regiment.points & 31) * 4 // 31)
        self._bitmap_centered(f"Skull{skull}", (x + 20, y + 12))
        self._banner(regiment.banner, (x + 35, y))
        self._label(f"{regiment.name} {regiment.models} ({regiment.orgsize})", x + 60, y, name_colour)
        self._label(f"{self._string('BRTXT', 200 + regiment.weapon_name)}/"
                    f"{self._string('BRTXT', 100 + regiment.armour)}", x + 60, y + height, name_colour)
        if not p1:
            if row.status == STATUS_AVAILABLE:
                for value, column in ((row.price, 345), (row.retainer, 425), (row.total, 505)):
                    self._label(f"{value} {self._string('BKTXT', 414)}", column, y, BLACK)
            else:
                self._label(self._string("BKTXT", self._status_text(row)), 345, y,
                            RED if row.status == STATUS_DESTROYED else GREY)
        # The mark is painted last, over the icon/text edge (notes §3.3).
        if row.selected and not p1:
            self._bitmap("RingMark", (x, y - height))

    @staticmethod
    def _status_text(row: TroopRow) -> int:
        """The three documented special excluded-regiment labels (§3.4)."""
        if row.status != STATUS_EXCLUDED:
            return STATUS_TEXT[row.status]
        if row.regiment.whoami in (29, 31):
            return 418
        if row.regiment.whoami in (13, 36, 37):
            return 420
        return 416

    def _buttons(self) -> None:
        for action, x, art, text_id in BUTTONS:
            enabled = self._enabled(action)
            self._button(action, x, art, text_id, enabled)

    def _button(self, action: str, x: int, art: str, text_id: int, enabled: bool) -> None:
        pressed = enabled and action == self.pressed_button
        self._bitmap(f"{art}Dn0" if pressed else f"{art}Up", (x, BUTTON_Y))
        # The pressed label moves button left, matching the tab art's inset.
        offset_x, offset_y = (0, 3) if pressed else (4, 3)
        label_y = BUTTON_Y + (BUTTON_SIZE[1] - self.body_font.font.height) // 2 + offset_y
        self._center(self._string("BRTXT", text_id), label_y, YELLOW if enabled else (192, 192, 192),
                     x=x + offset_x, width=BUTTON_SIZE[0])
        if enabled:
            self.buttons.append((pygame.Rect(x, BUTTON_Y, *BUTTON_SIZE), action))

    def _enabled(self, action: str) -> bool:
        model = self._model()
        if action == "abort":
            return True
        if action == "done":
            return bool(model.selection) and model.affordable if self.scene.phase == "select" else True
        if action == "page:next":
            return self.scene.phase == "select" and self.scene.page < self.scene.page_count - 1
        return self.scene.phase == "select" and self.scene.page > 0 or self.scene.phase == "march_order"

    def _title(self, text_id: int) -> str:
        mission_id = self._mission_title_id()
        mission = self._string("BRTXT", mission_id) if mission_id is not None else ""
        return self._string("BKTXT", text_id, mission)

    def _mission_title_id(self) -> int | None:
        """Read ``set:res`` rather than the later ``res:`` launch target (§1.1)."""
        for field in self.scene.record.fields if self.scene.record is not None else ():
            if field.command != "set" or "=" not in field.argument:
                continue
            key, value = field.argument.split("=", 1)
            if key.casefold() != "res":
                continue
            try:
                return int(value.split(None, 1)[0])
            except ValueError:
                return None
        return None

    def _string(self, table: str, text_id: int, *args: Any) -> str:
        try:
            value = self.content.string(table, int(text_id))
        except (KeyError, TypeError, ValueError):
            return ""
        try:
            return value % args if args else value
        except (TypeError, ValueError):
            return value

    def _bitmap(self, name: str, position: Point) -> None:
        surface = load_optional_bitmap(self.content, name, app_palette=self.palette)
        if surface is None:
            return
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self.quads.append((quad, position))

    def _bitmap_centered(self, name: str, center: Point) -> None:
        surface = load_optional_bitmap(self.content, name, app_palette=self.palette)
        if surface is None:
            return
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self.quads.append((quad, (center[0] - quad.size[0] // 2, center[1] - quad.size[1] // 2)))

    def _banner(self, name: str | None, position: Point) -> None:
        """Draw frame 1, the documented 16x24 row marker, from a resident banner set (§3.3)."""
        if not name or self.content.installation is None:
            return
        resource = resource_name(name)
        if resource is None:
            return
        if self.banner_files is None:
            from ..battlefield import resource_files
            self.banner_files = resource_files(self.content.installation, {"banners"})
        base = self.banner_files.get(resource.casefold())
        if base is None:
            return
        if base not in self.banner_surfaces:
            surface: pygame.Surface | None
            try:
                from ..portraits import load_sprite_sheet
                sheet = load_sprite_sheet(self.content.installation, base)
                frame = sheet.frames[1]
                rgba = self.palette.rgba(frame.pixels)
                surface = pygame.image.frombuffer(rgba, (frame.width, frame.height), "RGBA").copy()
            except (FileNotFoundError, IndexError, OSError, ValueError):
                surface = None
            self.banner_surfaces[base] = surface
        loaded = self.banner_surfaces[base]
        if loaded is None:
            return
        quad = ScreenQuad(self.gpu, loaded.get_size())
        quad.write(pygame.image.tobytes(loaded, "RGBA"))
        self.quads.append((quad, position))

    def _heading(self, value: str, y: int) -> None:
        # P0/P1 titles use the same body slot as their rows (§2); P5 passes slot 4 explicitly.
        self._center(value, y, BLACK)

    def _label(self, value: str, x: int, y: int, colour: Rgb, *, align: str = "left", width: int = 640) -> None:
        label = self.gpu.text((width, self.body_font.font.height), self.body_font, color=colour, background=None,
                              padding=0, align=align, fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _label_right(self, value: str, right: int, y: int, colour: Rgb) -> None:
        """Right-anchor text using the GPU label's supported left alignment."""
        width, _ = self.body_font.size(value)
        self._label(value, right - width, y, colour)

    def _center(self, value: str, y: int, colour: Rgb, *, x: int = 0, width: int = 640,
                font: BitmapFont | None = None) -> None:
        font = font or self.body_font
        label = self.gpu.text((width, font.font.height), font, color=colour, background=None,
                              padding=0, align="center", fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _native_point(self, position: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.MOUSEMOTION:
            point = self._native_point(event.pos)
            self._update_march_hover(point)
            self._set_cursor_at(point)
            return ()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            point = self._native_point(event.pos)
            direction = self._scroll_direction_at(point)
            if direction is not None:
                self.scroll_direction, self.scroll_elapsed = direction, 0.0
                return (f"scroll:{direction}",)
            self.pressed_button = next((action for rect, action in self.buttons if rect.collidepoint(point)), None)
            if self.pressed_button is not None:
                self.refresh()
                return ()
            if self.scene.phase == "march_order" and not pygame.key.get_mods() & pygame.KMOD_CTRL:
                # notes/troop_selection.md §5.2: "pressing on a row picks that regiment up" /
                # "a second click drops it" - both ends of the pick-up/drop pair fire on press,
                # not release.
                for rect, value in self.rows:
                    if rect.collidepoint(point):
                        picking_up = self.scene.picked_whoami is None
                        self._set_cursor("grab_closed" if picking_up else "grab_open")
                        return (f"pickup:{value}" if picking_up else f"drop:{value}",)
            return ()
        if event.type != pygame.MOUSEBUTTONUP or event.button != 1:
            return ()
        self.scroll_direction, self.scroll_elapsed = None, 0.0
        point = self._native_point(event.pos)
        pressed_button, self.pressed_button = self.pressed_button, None
        if pressed_button is not None:
            self.refresh()
            if any(rect.collidepoint(point) and action == pressed_button for rect, action in self.buttons):
                return (pressed_button,)
            return ()
        for rect, action in self.buttons:
            if rect.collidepoint(point):
                return (action,)
        for rect, value in self.rows:
            if rect.collidepoint(point):
                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    whoami = value if self.scene.phase == "select" else self._model().selection[value]
                    return (f"book:{whoami}",)
                if self.scene.phase == "select":
                    return (f"toggle:{value}",)
                # march_order rows pick up/drop on MOUSEBUTTONDOWN, above.
        return ()

    def _set_cursor_at(self, point: tuple[float, float]) -> None:
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._set_cursor("help")
            return
        if self.scene.phase == "select":
            whoami = next((whoami for rect, whoami in self.rows if rect.collidepoint(point)), None)
            if whoami is not None:
                self._set_cursor("toggle" if self._model().toggleable(whoami) else "no_toggle")
                return
        elif self.scene.phase == "march_order":
            direction = self._scroll_direction_at(point)
            if direction is not None:
                self._set_cursor("scroll_up" if direction == "up" else "scroll_down")
                return
            if any(rect.collidepoint(point) for rect, _ in self.rows):
                self._set_cursor("grab_closed" if self.scene.picked_whoami is not None else "grab_open")
                return
        self._set_cursor("default")

    def _set_cursor(self, name: str) -> None:
        self.cursors.show(CURSORS[name])

    def _update_march_hover(self, point: tuple[float, float]) -> None:
        self.scroll_direction = self._scroll_direction_at(point)
        self.pointer = point  # cheap; draw() alone consumes this to move the carried strip
        carrying = self.scene.phase == "march_order" and self.scene.picked_whoami is not None
        next_hover = next((index for rect, index in self.rows if rect.collidepoint(point)), None) if carrying else None
        if next_hover != self.hover_march_index:
            self.hover_march_index = next_hover
            self.refresh()

    def _scroll_direction_at(self, point: tuple[float, float]) -> str | None:
        if self.scene.phase != "march_order" or len(self._model().selection) <= P1_ROWS:
            return None
        x, y = point
        if not 95 <= x <= 565:
            return None
        if y < 51:
            return "up"
        if 420 <= y <= 440:
            return "down"
        return None

    def animate(self, seconds: float) -> None:
        if self.scroll_direction is None:
            return
        self.scroll_elapsed += seconds
        while self.scroll_elapsed >= 0.25:
            self.scroll_elapsed -= 0.25
            self.scene.handle(f"scroll:{self.scroll_direction}", None)
            self.refresh()

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)
        self._draw_carried(left, top, scale)

    def _draw_carried(self, left: float, top: float, scale: float) -> None:
        if not self.carried_quads and not self.carried_labels:
            return
        height = self.body_font.font.height
        row_top, row_bottom = 50 + height, 50 + height + 4 * height * (P1_ROWS - 1)
        carried_y = max(row_top, min((self.pointer or (0, row_top))[1] - 2 * height, row_bottom))
        for quad, (ox, oy) in self.carried_quads:
            quad.draw(left + ox * scale, top + (carried_y + oy) * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (ox, oy) in self.carried_labels:
            label.draw(left + ox * scale, top + (carried_y + oy) * scale, label.size[0] * scale, label.size[1] * scale)

    def _release_contents(self) -> None:
        for quad, _ in self.quads:
            quad.release()
        for label, _ in self.labels:
            label.release()
        for quad, _ in self.carried_quads:
            quad.release()
        for label, _ in self.carried_labels:
            label.release()
        self.quads, self.labels, self.buttons, self.rows = [], [], [], []
        self.carried_quads, self.carried_labels = [], []

    def release(self) -> None:
        self._release_contents()
        if hasattr(self, "cursors"):
            self.cursors.release()
