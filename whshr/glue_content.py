# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Lazy repository for imported campaign programs, windows, strings and bitmaps."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
import struct
from os import PathLike
from typing import Any

from .assets import AssetId
from .glue import (GlueProgram, GlueResource, MissionRecord, MissionRef, WindowDefinition,
                   parse_glue_resources)
from .legacy import module
from .paths import Installation

Rgb = tuple[int, int, int]
RgbPalette = Sequence[Rgb]


@dataclass(frozen=True)
class IndexedBitmap:
    """Headless 8-bit bitmap pixels in top-to-bottom row order."""

    width: int
    height: int
    pixels: bytes
    palette: tuple[tuple[int, int, int], ...]


def decode_indexed_dib(data: bytes | bytearray, name: str = "<bitmap>") -> IndexedBitmap:
    """Decode one uncompressed Windows 8-bit DIB without importing pygame."""
    data = bytes(data)
    if len(data) < 40:
        raise ValueError(f"truncated glue bitmap {name!r}")
    header, width, signed_height, planes, bpp, compression, _size, _x, _y, colors, _important = \
        struct.unpack_from("<IiiHHIIiiII", data)
    if header != 40 or planes != 1 or compression != 0 or bpp != 8 or width <= 0 or signed_height == 0:
        raise ValueError(
            f"unsupported glue bitmap {name!r}: {bpp} bpp, compression {compression}, "
            f"header {header}, planes {planes}"
        )
    height = abs(signed_height)
    colors = colors or 256
    palette_end = 40 + colors * 4
    stride = (width + 3) & ~3
    if colors > 256 or palette_end + stride * height > len(data):
        raise ValueError(f"truncated glue bitmap {name!r}")
    palette = tuple((data[40 + i * 4 + 2], data[40 + i * 4 + 1], data[40 + i * 4])
                    for i in range(colors))
    rows: list[bytes] = []
    for output_y in range(height):
        source_y = output_y if signed_height < 0 else height - 1 - output_y
        start = palette_end + source_y * stride
        row = data[start:start + width]
        if row and max(row) >= colors:
            raise ValueError(f"glue bitmap {name!r} references a missing palette entry")
        rows.append(row)
    return IndexedBitmap(width, height, b"".join(rows), palette)


class GlueContent:
    """One-time indexes over an installation, with optional non-destructive overrides."""

    def __init__(self, installation: Installation | str | PathLike[str] | None = None, *,
                 resources: Mapping[str, Any] | None = None, bitmaps: Mapping[str, Any] | None = None,
                 strings: Mapping[str, Mapping[int, str]] | None = None,
                 palettes: Mapping[str, RgbPalette] | None = None, parent: "GlueContent | None" = None) -> None:
        self.installation = (installation if isinstance(installation, Installation)
                             else Installation(installation) if installation is not None else None)
        self._resource_source = resources
        self._bitmap_source = {str(name).upper(): value for name, value in (bitmaps or {}).items()}
        self._string_source = {str(name).upper(): dict(values) for name, values in (strings or {}).items()}
        self._palette_source = {str(name).upper(): value for name, value in (palettes or {}).items()}
        self._parent = parent
        self._resources: dict[str, GlueResource] | None = None
        self._bitmap_pe: Any = None
        self._bitmap_resources: dict[str, Any] | None = None
        self._decoded_bitmaps: dict[str, IndexedBitmap] = {}
        self._strings: dict[str, dict[int, str]] = {}
        self._sprite_sheets: dict[str, Any] = {}
        self._palette: list[Rgb] | None = None
        self._palette_tables: dict[str, RgbPalette] | None = None
        self._portraits: dict[tuple[int, int, Any], Any] = {}

    @classmethod
    def from_data(cls, *, resources: Mapping[str, Any] | None = None, bitmaps: Mapping[str, Any] | None = None,
                  strings: Mapping[str, Mapping[int, str]] | None = None,
                  palettes: Mapping[str, RgbPalette] | None = None) -> "GlueContent":
        """Build portable synthetic content for tests and tools."""
        return cls(resources=resources or {}, bitmaps=bitmaps or {}, strings=strings or {}, palettes=palettes or {})

    def overlay(self, *, resources: Mapping[str, Any] | None = None, bitmaps: Mapping[str, Any] | None = None,
                strings: Mapping[str, Mapping[int, str]] | None = None,
                palettes: Mapping[str, RgbPalette] | None = None) -> "GlueContent":
        """Return a repository where supplied logical resources override this one."""
        return type(self)(resources=resources or {}, bitmaps=bitmaps or {}, strings=strings or {},
                          palettes=palettes or {}, parent=self)

    @property
    def resources(self) -> dict[str, GlueResource]:
        if self._resources is None:
            if self._resource_source is not None:
                local = parse_glue_resources(self._resource_source)
            elif self.installation is not None:
                from .campaign import load_wnd_rcdata
                local = parse_glue_resources(
                    load_wnd_rcdata(self.installation.file_dir("DLL", "WND.DLL"))
                )
            else:
                local = {}
            if self._parent is None:
                self._resources = local
            else:
                self._resources = {**self._parent.resources, **local}
        return self._resources

    def program(self, name: str) -> GlueProgram:
        resource = self._resource(name)
        if not isinstance(resource, GlueProgram):
            raise TypeError(f"glue resource {name!r} is not a program")
        return resource

    def window(self, name: str) -> WindowDefinition:
        resource = self._resource(name)
        if not isinstance(resource, WindowDefinition):
            raise TypeError(f"glue resource {name!r} is not a window")
        return resource

    def mission(self, reference: MissionRef) -> MissionRecord:
        """Resolve a stable :class:`MissionRef` to its typed source record.

        Mission-list widgets retain references rather than copied dictionaries,
        so content overrides and future campaign-state projections share one
        authoritative record.
        """
        if not isinstance(reference, MissionRef):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("mission reference must be a MissionRef")
        records = tuple(record for record in self.window(reference.window).records
                        if isinstance(record, MissionRecord))
        try:
            return records[reference.record_index]
        except IndexError:
            raise KeyError(f"glue mission not found: {reference.key}") from None

    def _resource(self, name: str) -> GlueResource:
        key = str(name).upper()
        try:
            return self.resources[key]
        except KeyError:
            raise KeyError(f"glue resource not found: {name!r}") from None

    def string(self, table: str, identifier: int) -> str:
        table = str(table).upper()
        local = self._string_table(table)
        if identifier in local:
            return local[identifier]
        if self._parent is not None:
            return self._parent.string(table, identifier)
        raise KeyError(f"{table} has no string {identifier}")

    def string_asset(self, table: str) -> AssetId:
        return AssetId("vanilla", "string", str(table).casefold())

    def strings(self, table: str) -> dict[int, str]:
        table = str(table).upper()
        inherited = self._parent.strings(table) if self._parent is not None else {}
        return {**inherited, **self._string_table(table)}

    def _string_table(self, table: str) -> dict[int, str]:
        if table in self._strings:
            return self._strings[table]
        if table in self._string_source:
            values = self._string_source[table]
        elif self.installation is not None:
            path = self.installation.file_dir("DLL", f"{table}.DLL")
            values = module("pe_missions").load_strings(str(path))
        else:
            values = {}
        self._strings[table] = values
        return values

    def bitmap(self, name: str) -> AssetId:
        """Return the stable logical identifier for a named glue bitmap."""
        logical_name = re.sub(r"[^a-z0-9_.-]+", "-", str(name).casefold()).strip("-")
        return AssetId("vanilla", "bitmap", logical_name)

    def bitmap_data(self, name: str) -> IndexedBitmap:
        key = str(name).upper()
        if key in self._decoded_bitmaps:
            return self._decoded_bitmaps[key]
        if key in self._bitmap_source:
            source = self._bitmap_source[key]
            bitmap = source if isinstance(source, IndexedBitmap) else decode_indexed_dib(source, name)
        else:
            source = self._installed_bitmap(key)
            if source is None and self._parent is not None:
                return self._parent.bitmap_data(key)
            if source is None:
                raise FileNotFoundError(f"BITMAP.DLL has no bitmap resource {name!r}")
            bitmap = decode_indexed_dib(source, name)
        self._decoded_bitmaps[key] = bitmap
        return bitmap

    def _installed_bitmap(self, key: str) -> bytes | None:
        if self.installation is None:
            return None
        if self._bitmap_resources is None:
            pe_cls = module("pe_resources").PE
            self._bitmap_pe = pe_cls(str(self.installation.file_dir("DLL", "BITMAP.DLL")))
            self._bitmap_resources = {
                str(resource.name).upper(): resource
                for resource in self._bitmap_pe.resources()
                if resource.type == 2
            }
        resource = self._bitmap_resources.get(key)
        return self._bitmap_pe.data(resource) if resource is not None else None

    def font(self, slot: int) -> AssetId:
        return AssetId("vanilla", "font", f"glue{int(slot)}")

    def portrait(self, index: int, bkindex: int) -> tuple[AssetId, AssetId]:
        """Return logical references for a portrait foreground/background pair."""
        from .portraits import PORTRAIT_SPRITES
        try:
            sprite = PORTRAIT_SPRITES[int(index)].casefold()
        except KeyError:
            raise ValueError(f"no verified portrait sprite mapping for glue index {index}") from None
        return (AssetId("vanilla", "portrait", sprite),
                AssetId("vanilla", "portrait", f"backall.{int(bkindex)}"))

    def portrait_available(self, position: int) -> bool:
        """Whether the sprite set at resident-list ``position`` and the backdrop set can be loaded."""
        from .portraits import PORTRAIT_SPRITES
        try:
            self._portrait_sources(int(position), 0, None)
        except (ValueError, FileNotFoundError, KeyError, OSError, IndexError):
            return False
        return int(position) in PORTRAIT_SPRITES

    def resolve_speaker_position(self, speaker: str | None) -> int:
        """List position an ``index=-1`` block behaves as for ``speaker`` (notes/glue_portraits.md §1.4)."""
        from .portraits import speaker_position
        return speaker_position(speaker, self.portrait_available)

    def _portrait_sources(self, index: int, bkindex: int, rgb_palette: RgbPalette | None) -> tuple[Any, Any, Any]:
        """Resolve the palette, background frame and speaker sprite sheet for one portrait."""
        if self.installation is None:
            if self._parent is not None:
                return self._parent._portrait_sources(index, bkindex, rgb_palette)
            raise FileNotFoundError("portrait data needs an original installation")
        from .image import load_rgb_palette
        from .portraits import PORTRAIT_SPRITES, load_sprite_sheet
        try:
            sprite_name = PORTRAIT_SPRITES[index]
        except KeyError:
            raise ValueError(f"no verified portrait sprite mapping for glue index {index}") from None
        if rgb_palette is not None:
            palette = rgb_palette
        else:
            if self._palette is None:
                self._palette = load_rgb_palette(self.installation.binary_file("STANDARD.PAL"))
            palette = self._palette
        for name in ("BACKALL", sprite_name):
            if name not in self._sprite_sheets:
                self._sprite_sheets[name] = load_sprite_sheet(self.installation, name)
        return palette, self._sprite_sheets["BACKALL"].frames[bkindex], self._sprite_sheets[sprite_name]

    def portrait_data(self, index: int, bkindex: int, *, rgb_palette: Any = None) -> Any:
        """Decode and cache the stopped-pose composite used by current views.

        ``BACKALL`` frames 16/17 need the map screen's palette pair, not ``STANDARD.PAL``
        (notes/glue_portraits.md §2.1); pass the caller's resolved ``AppPalette.colours`` as
        ``rgb_palette`` to get that (harmless for every other frame, which renders identically
        under either — the note verifies this).
        """
        key = int(index), int(bkindex), rgb_palette
        if key in self._portraits:
            return self._portraits[key]
        from .portraits import compose_portrait
        palette, background, sheet = self._portrait_sources(key[0], key[1], rgb_palette)
        result = compose_portrait(palette, background, sheet.frames[0])
        self._portraits[key] = result
        return result

    def portrait_frame(self, index: int, bkindex: int, mouth_frame: int, eye_frame: int, *, rgb_palette: Any = None) -> Any:
        """Composite one live animation frame (base + mouth/eye overlay); not cached, it changes every tick."""
        from .portraits import compose_talking_portrait
        palette, background, sheet = self._portrait_sources(int(index), int(bkindex), rgb_palette)
        return compose_talking_portrait(palette, background, sheet.frames[0], sheet, mouth_frame, eye_frame)

    def speech(self, identifier: str | int) -> AssetId:
        return AssetId("vanilla", "speech", str(identifier).casefold())

    def music(self, name: str, device: str = "gm") -> AssetId:
        return AssetId("vanilla", "music", f"{str(name).casefold()}-{str(device).casefold()}")

    def palette_tables(self) -> dict[str, RgbPalette]:
        """Return named glue palette records for :class:`whshr.glue_palette.AppPalette`."""
        if self._palette_tables is not None:
            return dict(self._palette_tables)
        local = dict(self._palette_source)
        if self.installation is not None:
            from .glue_palette import PALETTE_NAMES
            from .image import load_rgb_palette
            for name in ("STANDARD", *(f"GLUE{name}" for name in PALETTE_NAMES),
                         *(f"WIND{name}" for name in PALETTE_NAMES)):
                if name not in local:
                    path = (self.installation.binary_file("STANDARD.PAL") if name == "STANDARD"
                            else self.installation.binary_file("GLUE", f"{name}.PAL"))
                    local[name] = load_rgb_palette(path)
        inherited = self._parent.palette_tables() if self._parent is not None else {}
        self._palette_tables = {**inherited, **local}
        return dict(self._palette_tables)
