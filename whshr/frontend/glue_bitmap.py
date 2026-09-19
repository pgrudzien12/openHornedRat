"""Load glue RT_BITMAP resources directly from an installed game."""

import struct

import pygame

from ..legacy import module


def load_bitmap(installation, name):
    """Return an RGBA surface for a named resource in FILE/DLL/BITMAP.DLL."""
    pe = module("pe_resources").PE(str(installation.file_dir("DLL", "BITMAP.DLL")))
    resource = next((r for r in pe.resources() if r.type == 2 and str(r.name).upper() == name.upper()), None)
    if resource is None:
        raise FileNotFoundError(f"BITMAP.DLL has no bitmap resource {name!r}")
    dib = pe.data(resource)
    header, width, height, _planes, bpp, compression, _size, _x, _y, colors, _ = struct.unpack_from("<IiiHHIIiiII", dib)
    if header != 40 or compression != 0 or bpp != 8:
        raise ValueError(f"unsupported glue bitmap {name!r}: {bpp} bpp, compression {compression}")
    height, colors = abs(height), colors or 256
    palette = [(dib[40 + 4 * i + 2], dib[40 + 4 * i + 1], dib[40 + 4 * i]) for i in range(colors)]
    offset, stride, rgba = 40 + 4 * colors, (width + 3) & ~3, bytearray(width * height * 4)
    for y in range(height):
        source = offset + (height - 1 - y) * stride
        for x in range(width):
            red, green, blue = palette[dib[source + x]]
            rgba[4 * (y * width + x):4 * (y * width + x + 1)] = bytes((red, green, blue, 255))
    return pygame.image.frombuffer(rgba, (width, height), "RGBA").copy()
