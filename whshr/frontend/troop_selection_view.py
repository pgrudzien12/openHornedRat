"""Native P0/P1/P5 troop-book presentation (``notes/troop_selection.md`` §§2--5, §7).

The screen is deliberately a renderer: selection, affordability and marching order remain in
``TroopSelectionScene`` / ``TroopSelection``.  Its fixed layout constants are gathered here,
because this is a front-end-owned window rather than a WND.DLL-defined one.
"""

import struct

import pygame

from ..glue_palette import AppPalette
from ..legacy import module
from ..script import resource_name
from ..troop_selection import STATUS_AVAILABLE, STATUS_DESTROYED, STATUS_EXCLUDED, STATUS_NOT_HIRED
from .bitmap_font import BitmapFont
from .glue_bitmap import load_optional_bitmap
from .gpu import ScreenQuad
from .scene_view import NativeScreenView


# notes/troop_selection.md §§2--5, §7.  Coordinates are native 640x480 pixels.
BLACK, BLUE, GREY, RED, YELLOW = (0, 0, 0), (0, 0, 180), (127, 127, 127), (255, 0, 0), (255, 255, 0)
BUTTONS = (
    ("abort", 225, "BrownATab", 307), ("done", 325, "GreenATab", 304),
    ("page:back", 425, "BlueATab", 301), ("page:next", 525, "RedATab", 300),
)
BUTTON_Y, BUTTON_SIZE = 448, (84, 32)
P0_ROWS, P1_ROWS = 6, 7
STATUS_TEXT = {STATUS_NOT_HIRED: 415, STATUS_EXCLUDED: 416, STATUS_DESTROYED: 417}


class GameCursors:
    """Runtime decoder for the named EXE cursor groups in notes/troop_selection.md §2."""

    def __init__(self, installation):
        self.installation = installation
        self._cursors = {}
        self._resources = None

    def set(self, name):
        if name not in self._cursors:
            try:
                self._cursors[name] = self._load(name)
            except (FileNotFoundError, IndexError, OSError, StopIteration, ValueError, struct.error, pygame.error):
                self._cursors[name] = False
        cursor = self._cursors[name]
        if cursor:
            try:
                pygame.mouse.set_cursor(cursor)
            except pygame.error:
                pass

    def _load(self, name):
        if self._resources is None:
            image = module("pe_resources").PE(self.installation.require("WHSHR.EXE"))
            self._resources = tuple(image.resources()), image
        resources, image = self._resources
        group = next(resource for resource in resources
                     if resource.type == 12 and str(resource.name).upper() == name)
        group_data = image.data(group)
        count = struct.unpack_from("<H", group_data, 4)[0]
        if count < 1:
            raise ValueError(f"empty cursor group {name}")
        member = struct.unpack_from("<H", group_data, 18)[0]
        cursor = next(resource for resource in resources if resource.type == 1 and resource.name == member)
        return _cursor_from_dib(image.data(cursor))


def _cursor_from_dib(data):
    """Convert a Win32 monochrome cursor resource to pygame's colour-cursor form."""
    hotspot_x, hotspot_y = struct.unpack_from("<HH", data)
    data = data[4:]
    header, width, doubled_height, planes, bpp, compression, *_ = struct.unpack_from("<IiiHHIIiiII", data)
    if header != 40 or planes != 1 or bpp != 1 or compression != 0 or doubled_height <= 0:
        raise ValueError("unsupported cursor DIB")
    height = doubled_height // 2
    palette_count = 2
    palette = tuple((data[40 + index * 4 + 2], data[40 + index * 4 + 1], data[40 + index * 4])
                    for index in range(palette_count))
    offset = 40 + 4 * palette_count
    stride = (width + 31) // 32 * 4
    if len(data) < offset + stride * doubled_height:
        raise ValueError("truncated cursor DIB")
    surface = pygame.Surface((width, height), pygame.SRCALPHA, 32)
    for y in range(height):
        # The XOR and AND halves of an icon/cursor DIB are both bottom-up.
        source_y = height - 1 - y
        xor = data[offset + source_y * stride:offset + (source_y + 1) * stride]
        and_offset = offset + stride * height
        and_ = data[and_offset + source_y * stride:and_offset + (source_y + 1) * stride]
        for x in range(width):
            xor_bit = (xor[x // 8] >> (7 - x % 8)) & 1
            and_bit = (and_[x // 8] >> (7 - x % 8)) & 1
            if and_bit and not xor_bit:
                surface.set_at((x, y), (0, 0, 0, 0))
            elif and_bit:
                # Win32's invert-screen pixels have no exact alpha equivalent; use white.
                surface.set_at((x, y), (255, 255, 255, 255))
            else:
                surface.set_at((x, y), (*palette[xor_bit], 255))
    return pygame.cursors.Cursor((min(hotspot_x, width - 1), min(hotspot_y, height - 1)), surface)


class TroopSelectionView(NativeScreenView):
    """Draw troop-book pages and translate their documented mouse input."""

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.quads, self.labels, self.buttons, self.rows = [], [], [], []
        self.banner_surfaces = {}
        self.state = None
        self.hover_march_index = None
        self.pointer = None
        self.scroll_direction = None
        self.scroll_elapsed = 0.0
        self.pressed_button = None
        # Mode 0 without a company immediately transitions on the next scene tick (§1.1).
        # Do not require render-only fonts/resources during that one-frame handoff.
        if scene.phase == "skip":
            return
        self.content = scene.glue_scene.runtime.content
        self.body_font = BitmapFont(scene.glue_scene.font(2))
        self.heading_font = BitmapFont(scene.glue_scene.font(4))
        self.palette = AppPalette.select(1, self.content.palette_tables())
        self.banner_files = None
        self.cursors = GameCursors(self.content.installation)
        self._set_cursor("SWORDCURSOR")
        self.refresh()

    def refresh(self):
        if self.scene.phase == "skip":
            return
        model = self.scene.model
        state = (self.scene.phase, self.scene.page, self.scene.march_offset, self.scene.picked_whoami,
                 self.hover_march_index, self.pressed_button,
                 self.pointer if self.scene.picked_whoami is not None else None,
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

    def _p0(self):
        model, height = self.scene.model, self.body_font.font.height
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
        self._center(self._string("BKTXT", 5006, self.scene.campaign.coffers + model.prepaid), 400 - 2 * height, BLACK)
        self._center(self._string("BRTXT", 314), 400, BLUE)
        self._center(self._string("BRTXT", 316), 400 + height, BLUE)

    def _p1(self):
        model, height = self.scene.model, self.body_font.font.height
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
        if self.scene.picked_whoami is not None and self.pointer is not None:
            # notes/troop_selection.md §5.2: "the strip (BookScroll0) with its contents follows
            # the cursor while the original row is hidden" - only x=145/157 are fixed; y tracks
            # the cursor, clamped to the visible row band.
            row_top, row_bottom = 50 + height, 50 + height + 4 * height * (P1_ROWS - 1)
            y = max(row_top, min(self.pointer[1] - 2 * height, row_bottom))
            self._bitmap("BookScroll0", (145, y - 10))
            self._regiment(model.row(self.scene.picked_whoami), y, 157, p1=True)
        self._center(self._string("BRTXT", 315), 400, BLUE)
        self._center(self._string("BRTXT", 316), 400 + height, BLUE)

    def _p5(self):
        """Draw the bankruptcy page; notes/troop_selection.md §7.

        The availability test and its displayed coffer amount both include the already
        evaluated initial payment, as on P0's coffer line (§3.5).
        """
        height = self.body_font.font.height
        heading_y = 50 + 8 * height
        self._center(self._string("BKTXT", 601), heading_y, BLACK, font=self.heading_font)
        self._center(self._string("BKTXT", 602, self.scene.model.coffers + self.scene.model.prepaid),
                     heading_y + self.heading_font.font.height, BLACK)
        self._center(self._string("BKTXT", 603, self.scene.model.forced_cost),
                     heading_y + self.heading_font.font.height + height, BLACK)
        self._button("done", 325, "GreenATab", 304, True)

    def _regiment(self, row, y, x, *, p1):
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
    def _status_text(row):
        """The three documented special excluded-regiment labels (§3.4)."""
        if row.status != STATUS_EXCLUDED:
            return STATUS_TEXT[row.status]
        if row.regiment.whoami in (29, 31):
            return 418
        if row.regiment.whoami in (13, 36, 37):
            return 420
        return 416

    def _buttons(self):
        for action, x, art, text_id in BUTTONS:
            enabled = self._enabled(action)
            self._button(action, x, art, text_id, enabled)

    def _button(self, action, x, art, text_id, enabled):
        pressed = enabled and action == self.pressed_button
        self._bitmap(f"{art}Dn0" if pressed else f"{art}Up", (x, BUTTON_Y))
        # The pressed label moves button left, matching the tab art's inset.
        offset_x, offset_y = (0, 3) if pressed else (4, 3)
        label_y = BUTTON_Y + (BUTTON_SIZE[1] - self.body_font.font.height) // 2 + offset_y
        self._center(self._string("BRTXT", text_id), label_y, YELLOW if enabled else (192, 192, 192),
                     x=x + offset_x, width=BUTTON_SIZE[0])
        if enabled:
            self.buttons.append((pygame.Rect(x, BUTTON_Y, *BUTTON_SIZE), action))

    def _enabled(self, action):
        model = self.scene.model
        if action == "abort":
            return True
        if action == "done":
            return bool(model.selection) and model.affordable if self.scene.phase == "select" else True
        if action == "page:next":
            return self.scene.phase == "select" and self.scene.page < self.scene.page_count - 1
        return self.scene.phase == "select" and self.scene.page > 0 or self.scene.phase == "march_order"

    def _title(self, text_id):
        mission_id = self._mission_title_id()
        mission = self._string("BRTXT", mission_id) if mission_id is not None else ""
        return self._string("BKTXT", text_id, mission)

    def _mission_title_id(self):
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

    def _string(self, table, text_id, *args):
        try:
            value = self.content.string(table, int(text_id))
        except (KeyError, TypeError, ValueError):
            return ""
        try:
            return value % args if args else value
        except (TypeError, ValueError):
            return value

    def _bitmap(self, name, position):
        surface = load_optional_bitmap(self.content, name, app_palette=self.palette)
        if surface is None:
            return
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self.quads.append((quad, position))

    def _bitmap_centered(self, name, center):
        surface = load_optional_bitmap(self.content, name, app_palette=self.palette)
        if surface is None:
            return
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self.quads.append((quad, (center[0] - quad.size[0] // 2, center[1] - quad.size[1] // 2)))

    def _banner(self, name, position):
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
        surface = self.banner_surfaces.get(base)
        if surface is None:
            try:
                from ..portraits import load_sprite_sheet
                sheet = load_sprite_sheet(self.content.installation, base)
                frame = sheet.frames[1]
                rgba = self.palette.rgba(frame.pixels)
                surface = pygame.image.frombuffer(rgba, (frame.width, frame.height), "RGBA").copy()
            except (FileNotFoundError, IndexError, OSError, ValueError):
                surface = False
            self.banner_surfaces[base] = surface
        if surface is False:
            return
        quad = ScreenQuad(self.gpu, surface.get_size())
        quad.write(pygame.image.tobytes(surface, "RGBA"))
        self.quads.append((quad, position))

    def _heading(self, value, y):
        # P0/P1 titles use the same body slot as their rows (§2); P5 passes slot 4 explicitly.
        self._center(value, y, BLACK)

    def _label(self, value, x, y, colour, *, align="left", width=640):
        label = self.gpu.text((width, self.body_font.font.height), self.body_font, color=colour, background=None,
                              padding=0, align=align, fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _label_right(self, value, right, y, colour):
        """Right-anchor text using the GPU label's supported left alignment."""
        width, _ = self.body_font.size(value)
        self._label(value, right - width, y, colour)

    def _center(self, value, y, colour, *, x=0, width=640, font=None):
        font = font or self.body_font
        label = self.gpu.text((width, font.font.height), font, color=colour, background=None,
                              padding=0, align="center", fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _native_point(self, position):
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def events(self, event):
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
                    whoami = value if self.scene.phase == "select" else self.scene.model.selection[value]
                    return (f"book:{whoami}",)
                if self.scene.phase == "select":
                    return (f"toggle:{value}",)
                picking_up = self.scene.picked_whoami is None
                self._set_cursor("HANDCLOSECURSOR" if picking_up else "HANDOPENCURSOR")
                return (f"pickup:{value}" if picking_up else f"drop:{value}",)
        return ()

    def _set_cursor_at(self, point):
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._set_cursor("HELPCURSOR")
            return
        if self.scene.phase == "select":
            whoami = next((whoami for rect, whoami in self.rows if rect.collidepoint(point)), None)
            if whoami is not None:
                self._set_cursor("PENCILCURSOR" if self.scene.model.toggleable(whoami) else "NOPENCILCURSOR")
                return
        elif self.scene.phase == "march_order":
            direction = self._scroll_direction_at(point)
            if direction is not None:
                self._set_cursor("UPARROWCURSOR" if direction == "up" else "DOWNARROWCURSOR")
                return
            if any(rect.collidepoint(point) for rect, _ in self.rows):
                self._set_cursor("HANDCLOSECURSOR" if self.scene.picked_whoami is not None else "HANDOPENCURSOR")
                return
        self._set_cursor("SWORDCURSOR")

    def _set_cursor(self, name):
        self.cursors.set(name)

    def _update_march_hover(self, point):
        self.scroll_direction = self._scroll_direction_at(point)
        carrying = self.scene.phase == "march_order" and self.scene.picked_whoami is not None
        next_hover = next((index for rect, index in self.rows if rect.collidepoint(point)), None) if carrying else None
        moved = carrying and point != self.pointer
        self.pointer = point
        if next_hover != self.hover_march_index or moved:
            self.hover_march_index = next_hover
            self.refresh()

    def _scroll_direction_at(self, point):
        if self.scene.phase != "march_order" or len(self.scene.model.selection) <= P1_ROWS:
            return None
        x, y = point
        if not 95 <= x <= 565:
            return None
        if y < 51:
            return "up"
        if 420 <= y <= 440:
            return "down"
        return None

    def animate(self, seconds):
        if self.scroll_direction is None:
            return
        self.scroll_elapsed += seconds
        while self.scroll_elapsed >= 0.25:
            self.scroll_elapsed -= 0.25
            self.scene.handle(f"scroll:{self.scroll_direction}", None)
            self.refresh()

    def draw(self):
        super().draw()
        left, top, scale = self._layout()
        for quad, (x, y) in self.quads:
            quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
        for label, (x, y) in self.labels:
            label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def _release_contents(self):
        for quad, _ in self.quads:
            quad.release()
        for label, _ in self.labels:
            label.release()
        self.quads, self.labels, self.buttons, self.rows = [], [], [], []

    def release(self):
        self._release_contents()
        if hasattr(self, "cursors"):
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
            except pygame.error:
                pass
