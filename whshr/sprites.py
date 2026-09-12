"""FOL/BOP sprite decoding and sheet rendering helpers."""

import os
import struct

from .image import load_rgb_palette, write_png


def unzero(seg):
    """Zero RLE: 00 NN = NN zero bytes, 00 00 = end, any other byte = literal."""
    out, i = bytearray(), 0
    while True:
        if seg[i] == 0:
            n = seg[i + 1]
            i += 2
            if n == 0:
                return bytes(out), i
            out += bytes(n)
        else:
            out.append(seg[i])
            i += 1


def colormap_indices(recs):
    """Return the full color map index for each frame record."""
    out, wraps, prev = [], 0, None
    for record in recs:
        if (record[5] & 0x0F) not in (2, 4):
            out.append(None)
            continue
        number = record[5] >> 4
        if prev is not None and number < prev:
            wraps += 1
        out.append(number + 16 * wraps)
        prev = number
    return out


def decode_frame(bop, rec, seg_end, colormaps, map_index=None):
    """Decode a frame to palette indices, with zero as transparent."""
    _, _, width, height, offset, flags = rec[:6]
    kind, segment = flags & 0x0F, bop[offset:seg_end]
    if kind == 1:
        return list(segment[:width * height])
    bytes_per_row = (width + 1) // 2
    packed = unzero(segment)[0] if kind == 4 else segment[:bytes_per_row * height]
    cmap_index = flags >> 4 if map_index is None else map_index
    cmap = colormaps[cmap_index] if cmap_index < len(colormaps) else None
    pixels = []
    for row in range(height):
        for column in range(width):
            byte = packed[row * bytes_per_row + column // 2]
            if cmap:
                pixels.append(cmap[byte * 2 + (column & 1)])
            else:
                pixels.append(((byte >> 4) if column % 2 == 0 else (byte & 15)) * 16)
    return pixels


def main(bindir, name, first=0, count=24, out=None, cols=8, scale=3):
    """Decode selected frames and write a PNG sheet."""
    fol = open(f"{bindir}/{name}.FOL", 'rb').read()
    bop = open(f"{bindir}/{name}.BOP", 'rb').read()
    palette_path = f"{bindir}/{name}.PAL"
    palette_data = open(palette_path, 'rb').read() if os.path.exists(palette_path) else b''
    colormaps = (
        [palette_data[i:i + 512] for i in range(0, len(palette_data), 512)]
        if palette_data and len(palette_data) % 512 == 0 else []
    )
    rgb_palette = load_rgb_palette(f"{bindir}/STANDARD.PAL")

    records = [
        struct.unpack_from('<hhhhIB', fol, i * 16)
        for i in range(len(fol) // 16)
    ]
    maps = colormap_indices(records)
    offsets = sorted(set(record[4] for record in records)) + [len(bop)]
    selected = records[first:first + count]
    cell_width = max(record[2] for record in selected) + 2
    cell_height = max(record[3] for record in selected) + 2
    width, height = cell_width * cols, cell_height * ((len(selected) + cols - 1) // cols)
    image = [(40, 40, 48)] * (width * height)
    for index, record in enumerate(selected):
        segment_end = offsets[offsets.index(record[4]) + 1]
        pixels = decode_frame(
            bop, record, segment_end, colormaps, maps[first + index]
        )
        origin_x = (index % cols) * cell_width + 1
        origin_y = (index // cols) * cell_height + 1
        for row in range(record[3]):
            for column in range(record[2]):
                value = pixels[row * record[2] + column]
                if value:
                    image[(origin_y + row) * width + origin_x + column] = rgb_palette[value]
    rgb = bytearray()
    for row in range(height * scale):
        for column in range(width * scale):
            rgb += bytes(image[(row // scale) * width + column // scale])
    write_png(out or f"{name.lower()}.png", width * scale, height * scale, rgb)
