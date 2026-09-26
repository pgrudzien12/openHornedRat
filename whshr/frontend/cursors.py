# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Runtime decoder for the game's own Win32 cursor resources (never substitute copied artwork).

Two sources are used across the front-end: ``WHSHR.EXE``'s named cursor groups
(``notes/troop_selection.md`` Section 2, e.g. ``SWORDCURSOR``) and ``GMCUR.DLL``'s 4 numbered battle
cursor groups, IDs 100-103 (``notes/pe_resources.md``, ``notes/game_rules.md`` "Feedback").
"""

import struct
from typing import Any, Protocol

import pygame

from ..legacy import module
from ..paths import Installation


class GameCursors:
    """Loads and caches cursors from one PE file's ``RT_GROUP_CURSOR`` resources, by name or by
    numeric group ID."""

    def __init__(self, installation: Installation, dll: str = "WHSHR.EXE") -> None:
        self.installation = installation
        self.dll = dll
        self._cursors: dict[str | int, pygame.cursors.Cursor | bool] = {}
        self._resources: tuple[tuple[Any, ...], Any] | None = None

    def set(self, key: str | int) -> None:
        if key not in self._cursors:
            try:
                self._cursors[key] = self._load(key)
            except (FileNotFoundError, IndexError, OSError, StopIteration, ValueError, struct.error, pygame.error):
                self._cursors[key] = False
        cursor = self._cursors[key]
        try:
            # A cursor that cannot be loaded leaves the system arrow rather than the previous, unrelated one.
            pygame.mouse.set_cursor(cursor if isinstance(cursor, pygame.cursors.Cursor) else pygame.SYSTEM_CURSOR_ARROW)
        except pygame.error:
            pass

    def _load(self, key: str | int) -> pygame.cursors.Cursor:
        if self._resources is None:
            # WHSHR.EXE is the game's main executable, at the installation root; every other
            # resource DLL (GMCUR.DLL included) lives under FILE/DLL (whshr.paths.Installation;
            # matches how every other *.DLL resource load in this codebase resolves its path).
            path = (self.installation.require(self.dll) if self.dll.upper() == "WHSHR.EXE"
                   else self.installation.file_dir("DLL", self.dll))
            image = module("pe_resources").PE(path)
            self._resources = tuple(image.resources()), image
        resources, image = self._resources
        matches = str(key).upper() if isinstance(key, str) else key
        group = next(resource for resource in resources
                    if resource.type == 12 and
                    (str(resource.name).upper() == matches if isinstance(key, str) else resource.name == matches))
        group_data = image.data(group)
        count = struct.unpack_from("<H", group_data, 4)[0]
        if count < 1:
            raise ValueError(f"empty cursor group {key}")
        member = struct.unpack_from("<H", group_data, 18)[0]
        cursor = next(resource for resource in resources if resource.type == 1 and resource.name == member)
        return _cursor_from_dib(image.data(cursor))


def _cursor_from_dib(data: bytes) -> pygame.cursors.Cursor:
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


class HotspotCursors(Protocol):
    """The cursor data of a glue hotspot (``whshr.glue_render.RenderHotspot``)."""

    @property
    def cursor(self) -> str | None: ...

    @property
    def alt_cursor(self) -> str | None: ...


def cursor_for_hotspots(hovered: HotspotCursors | None, pressed: HotspotCursors | None) -> str | None:
    """Which named cursor a glue screen shows (issue #150; notes/glue_keywords.md §3.5): the pressed hotspot's
    ``altcursor``, else the hovered hotspot's ``cursor``, else ``None`` (the normal arrow). Pure data, no pygame."""
    if pressed is not None and pressed.alt_cursor:
        return pressed.alt_cursor
    if hovered is not None and hovered.cursor:
        return hovered.cursor
    return None


_UNSET = object()


class CursorController:
    """The one owner of a screen's mouse cursor: shows the game's own named cursors, remembers what is shown so
    a screen can call it on every mouse event cheaply, and puts the arrow back when the screen goes away.

    ``default`` is the cursor of the screen's plain state (``None``: the system arrow). Without an installation
    (or when a named cursor cannot be loaded) the system arrow is used."""

    def __init__(self, installation: Installation | None, default: str | None = None, dll: str = "WHSHR.EXE") -> None:
        self.default = default
        self.cursors = GameCursors(installation, dll) if installation is not None else None
        self._shown: object = _UNSET

    def show(self, name: str | None) -> None:
        """Show ``name`` (``None``: the default cursor)."""
        name = name or self.default
        if name == self._shown:
            return
        self._shown = name
        if name is not None and self.cursors is not None:
            self.cursors.set(name)
        else:
            self._arrow()

    def update(self, hovered: HotspotCursors | None, pressed: HotspotCursors | None) -> None:
        """Apply the glue hotspot rule of :func:`cursor_for_hotspots`."""
        self.show(cursor_for_hotspots(hovered, pressed))

    def release(self) -> None:
        """The screen is going away: do not leak its cursor into the next scene."""
        self._shown = _UNSET
        self._arrow()

    @staticmethod
    def _arrow() -> None:
        try:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
        except pygame.error:
            pass
