"""PNG and palette helpers used by the asset decoders."""

import struct
import zlib
from collections.abc import Sequence
from os import PathLike


def load_rgb_palette(path: str | PathLike[str]) -> list[tuple[int, int, int]]:
    """Read the game's four-byte indexed RGB palette."""
    with open(path, 'rb') as source:
        data = source.read()
    palette: list[tuple[int, int, int]] = [(255, 0, 255)] * 256
    for i in range(0, len(data) - 3, 4):
        palette[data[i]] = (data[i + 1], data[i + 2], data[i + 3])
    return palette


def write_png(path: str | PathLike[str], width: int, height: int, rgb: Sequence[int]) -> None:
    """Write an RGB byte sequence as a non-interlaced PNG."""
    raw = b''.join(
        b'\0' + bytes(rgb[row * width * 3:(row + 1) * width * 3])
        for row in range(height)
    )
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw))
        + chunk(b'IEND', b'')
    )
