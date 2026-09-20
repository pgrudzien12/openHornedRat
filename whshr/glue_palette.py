"""The one indexed application palette used by the glue front end.

This is deliberately independent of pygame and installation paths.  A content
loader supplies named ``STANDARD``, ``GLUE*`` and ``WIND*`` palette records;
the renderer supplies indexed pixels and looks colours up here.
"""

from dataclasses import dataclass


SYSTEM_COLOURS = (
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128),
    (128, 0, 128), (0, 128, 128), (192, 192, 192), (192, 220, 192), (166, 202, 240),
)
SYSTEM_TAIL_COLOURS = (
    (255, 251, 240), (160, 160, 164), (128, 128, 128), (255, 0, 0), (0, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255), (255, 255, 255),
)
PALETTE_NAMES = ("BOOK", "MAP", "CAR", "MIND", "END", "TITL", "GAME", "OPT", "BK2")


def _records(values):
    """Normalise a file's indexed records into a mapping without file I/O."""
    if isinstance(values, dict):
        return {int(index): tuple(colour) for index, colour in values.items()}
    return {index: tuple(colour) for index, colour in enumerate(values)}


@dataclass(frozen=True)
class AppPalette:
    """An immutable palette result and the selection that produced it."""

    palette_id: int | str
    colours: tuple[tuple[int, int, int], ...]

    @classmethod
    def select(cls, palette_id, tables, *, embedded=None):
        """Build the palette selected by a top-level window or built-in screen.

        ``tables`` maps names such as ``STANDARD``, ``GLUEMAP`` and ``WINDMAP``
        to indexed RGB records.  Negative ids select ``embedded``; a missing
        embedded palette falls back to STANDARD, matching restoration's safe
        compatibility behaviour.
        """
        tables = {str(name).upper(): _records(records) for name, records in tables.items()}
        standard = tables.get("STANDARD", {})
        colours = [standard.get(index, (0, 0, 0)) for index in range(256)]
        try:
            selection = int(palette_id)
        except (TypeError, ValueError):
            selection = 0
        if selection < 0 and embedded is not None:
            source = _records(embedded)
            for index in range(10, 246):
                if index in source:
                    colours[index] = source[index]
        elif 1 <= selection <= len(PALETTE_NAMES):
            name = PALETTE_NAMES[selection - 1]
            for index, colour in tables.get(f"GLUE{name}", {}).items():
                if 10 <= index <= 105:
                    colours[index] = colour
            for index, colour in tables.get(f"WIND{name}", {}).items():
                if 106 <= index <= 245:
                    colours[index] = colour
        for index, colour in enumerate(SYSTEM_COLOURS):
            colours[index] = colour
        for index, colour in enumerate(SYSTEM_TAIL_COLOURS, 246):
            colours[index] = colour
        return cls(selection if selection >= 0 else "embedded", tuple(colours))

    def rgba(self, pixels, *, transparent_index=0):
        """Map indexed pixels to RGBA bytes without making a pygame surface."""
        rgba = bytearray(len(pixels) * 4)
        for offset, index in enumerate(pixels):
            red, green, blue = self.colours[index]
            rgba[offset * 4:offset * 4 + 4] = bytes((red, green, blue,
                                                       0 if index == transparent_index else 255))
        return bytes(rgba)
