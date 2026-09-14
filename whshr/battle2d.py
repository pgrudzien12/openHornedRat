"""Render a static top-down game-view battle viewport from 2D game assets."""

import math
import struct
from pathlib import Path

from . import formation, legacy
from .image import load_rgb_palette, write_png
from .paths import Installation
from .script import load_battle
from .sprites import colormap_indices, decode_frame

DEFAULT_WIDTH = 544
DEFAULT_HEIGHT = 386
DEFAULT_ZOOM = 1.0
DEFAULT_SPACING = formation.MODEL_SPACING
BACKGROUND = (24, 26, 32)


def _battle_path(game, battle_file):
    path = Path(battle_file)
    return path if path.is_file() else game.file_dir("SCRIPT", battle_file)


def _records(fol):
    if len(fol) % 16:
        raise ValueError(f"FOL size is not a multiple of 16 bytes: {len(fol)}")
    return [struct.unpack_from("<hhhhIB", fol, offset) for offset in range(0, len(fol), 16)]


def _frame_end(records, bop_length, offset):
    offsets = sorted({record[4] for record in records}) + [bop_length]
    return offsets[offsets.index(offset) + 1]


def _load_planmap(game, name):
    """Load the first ``loadplanmap`` frame as indexed pixels and its RGB palette."""
    base = name.split(",", 1)[0].strip()
    fol_path = game.binary_file(base + ".FOL")
    bop_path = game.binary_file(base + ".BOP")
    fol, bop = fol_path.read_bytes(), bop_path.read_bytes()
    records = _records(fol)
    if not records:
        raise ValueError(f"{fol_path} has no frames")
    palette_path = game.find("UPDATE", "BINARY", base + ".PAL") or game.find("FILE", "BINARY", base + ".PAL")
    maps = []
    if palette_path:
        data = palette_path.read_bytes()
        if len(data) % 512 == 0:
            maps = [data[offset:offset + 512] for offset in range(0, len(data), 512)]
    record = records[0]
    pixels = decode_frame(
        bop, record, _frame_end(records, len(bop), record[4]), maps, colormap_indices(records)[0]
    )
    return record[2], record[3], pixels


class SpriteSet:
    """A directional 2D sprite set loaded from the preferred BINARY directory."""

    def __init__(self, game, base, palette):
        self.base = base
        self.palette = palette
        self.fol = game.binary_file(base + ".FOL").read_bytes()
        self.bop = game.binary_file(base + ".BOP").read_bytes()
        self.records = _records(self.fol)
        self.maps = []
        palette_path = game.find("UPDATE", "BINARY", base + ".PAL") or game.find("FILE", "BINARY", base + ".PAL")
        if palette_path:
            data = palette_path.read_bytes()
            if len(data) % 512 == 0:
                self.maps = [data[offset:offset + 512] for offset in range(0, len(data), 512)]
        self.map_indices = colormap_indices(self.records)

    def _groups(self):
        groups = []
        for index, record in enumerate(self.records):
            color_map = record[5] >> 4
            if groups and groups[-1][0] == color_map:
                groups[-1][2] += 1
            else:
                groups.append([color_map, index, 1])
        return groups

    def idle_frame(self, direction):
        """Return an idle frame, falling back gracefully for nonstandard unit layouts."""
        if len(self.records) >= 104:
            frame = 72 + direction
        else:
            groups = self._groups()
            # Standard sets have move/dead/attack/stand as their first four groups.
            group = groups[3] if len(groups) >= 4 and groups[3][2] >= 8 else max(groups, key=lambda item: item[2])
            frame = group[1] + direction % group[2]
        record = self.records[frame]
        pixels = decode_frame(
            self.bop, record, _frame_end(self.records, len(self.bop), record[4]), self.maps, self.map_indices[frame]
        )
        # In directional FOL entries b3 is the horizontal anchor and b2 is measured up from the bottom.
        return {
            "pixels": pixels,
            "width": record[2],
            "height": record[3],
            "anchor_x": self.fol[frame * 16 + 3],
            "anchor_y": record[3] - self.fol[frame * 16 + 2],
            "frame": frame,
        }


def _troop_sprite_files(game):
    table = legacy.module("spritemap_build")
    records, _, _ = table.read_tables(game.require("WHSHR.EXE").read_bytes())
    table.assign_categories(records)
    return {
        record["name"].casefold(): record["file"]
        for record in records
        if record["category"] == "troops" and record["file"]
    }


def _frame_direction(script_dir, offset):
    """Map clockwise BTS direction units onto the counter-clockwise sprite frame order."""
    return (offset - int(((script_dir or 0) + 32) // 64)) % 8


def _formation(unit, spacing):
    """Return soldier anchors in BTS world coordinates, with the unit anchor at the front-rank centre."""
    return formation.unit_layout(unit, spacing)


class Viewport:
    """Top-down viewport: BTS X grows right and BTS Y grows upward."""

    def __init__(self, width, height, target_x, target_y, zoom):
        self.width, self.height = width, height
        self.target_x, self.target_y, self.zoom = target_x, target_y, zoom
        self.pixels = bytearray(bytes(BACKGROUND) * (width * height))

    def point(self, x, y):
        return (self.width / 2 + (x - self.target_x) * self.zoom,
                self.height / 2 + (self.target_y - y) * self.zoom)

    def planmap(self, image, field_width, field_height, palette):
        """Sample the entire plan map in world coordinates, without stretching the viewport."""
        map_width, map_height, indices = image
        for screen_y in range(self.height):
            world_y = self.target_y + (self.height / 2 - screen_y) / self.zoom
            if not 0 <= world_y < field_height:
                continue
            map_y = min(int((field_height - world_y) * map_height / field_height), map_height - 1)
            for screen_x in range(self.width):
                world_x = self.target_x + (screen_x - self.width / 2) / self.zoom
                if not 0 <= world_x < field_width:
                    continue
                map_x = min(int(world_x * map_width / field_width), map_width - 1)
                color = palette[indices[map_y * map_width + map_x]]
                offset = (screen_y * self.width + screen_x) * 3
                self.pixels[offset:offset + 3] = bytes(color)

    def sprite(self, frame, palette, x, y):
        """Composite an indexed sprite, scaled together with the world map."""
        anchor_x, anchor_y = self.point(x, y)
        scale = self.zoom * formation.SPRITE_PIXEL_WORLD_UNITS
        left, top = anchor_x - frame["anchor_x"] * scale, anchor_y - frame["anchor_y"] * scale
        x0, x1 = max(0, math.floor(left)), min(self.width, math.ceil(left + frame["width"] * scale))
        y0, y1 = max(0, math.floor(top)), min(self.height, math.ceil(top + frame["height"] * scale))
        pixels, sprite_width = frame["pixels"], frame["width"]
        for screen_y in range(y0, y1):
            source_y = min(int((screen_y - top) / scale), frame["height"] - 1)
            for screen_x in range(x0, x1):
                source_x = min(int((screen_x - left) / scale), sprite_width - 1)
                value = pixels[source_y * sprite_width + source_x]
                if value:
                    offset = (screen_y * self.width + screen_x) * 3
                    self.pixels[offset:offset + 3] = bytes(palette[value])


def render(installation, battle_file, output, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
           target_x=None, target_y=None, zoom=DEFAULT_ZOOM, spacing=DEFAULT_SPACING,
           direction_offset=0):
    """Render a 2D battle viewport and return its assets and unit-rendering statistics."""
    game = Installation(installation)
    battle_path = _battle_path(game, battle_file)
    battle = load_battle(str(battle_path))
    field = battle["field"]
    if not field["planmap"]:
        raise ValueError(f"{battle_path.name} has no loadplanmap field")
    if not field["width"] or not field["height"]:
        raise ValueError(f"{battle_path.name} has no battlefield dimensions")
    player_positions = [
        unit["set"] for army in (battle["merc"] or {}).get("armies", [])
        for unit in army["units"] if "x" in unit["set"] and "y" in unit["set"]
    ]
    default_target_x = (sum(unit["x"] for unit in player_positions) / len(player_positions)
                        if player_positions else field["width"] / 2)
    default_target_y = (sum(unit["y"] for unit in player_positions) / len(player_positions)
                        if player_positions else field["height"] / 2)
    target_x = default_target_x if target_x is None else target_x
    target_y = default_target_y if target_y is None else target_y
    palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    viewport = Viewport(width, height, target_x, target_y, zoom)
    viewport.planmap(_load_planmap(game, field["planmap"]), field["width"], field["height"], palette)

    sprite_files, cache = _troop_sprite_files(game), {}
    units = [unit for army in battle["armies"] + (battle["merc"] or {}).get("armies", [])
             for unit in army["units"]]
    placements, rendered, missing = [], [], []
    for unit in units:
        position = unit["set"]
        resource = (unit["sprites"] or "").split(",", 1)[0].strip()
        base = sprite_files.get(resource.casefold())
        if base is None or "x" not in position or "y" not in position:
            missing.append(unit["name"])
            continue
        try:
            sprite = cache.setdefault(base, SpriteSet(game, base, palette))
            direction = _frame_direction(position.get("dir"), direction_offset)
            frame = sprite.idle_frame(direction)
        except (FileNotFoundError, ValueError, IndexError) as error:
            missing.append(f"{unit['name']} ({error})")
            continue
        soldiers, count, ranks = _formation(unit, spacing)
        placements.extend((soldier_y, soldier_x, frame, soldier_x, soldier_y)
                          for soldier_x, soldier_y in soldiers)
        rendered.append({"name": unit["name"], "sprite": base, "frame": frame["frame"],
                         "direction": direction, "soldiers": count, "ranks": ranks})
    # Higher map Y is farther away on screen, so paint it first to let nearer sprites overlap it.
    for _, _, frame, soldier_x, soldier_y in sorted(placements, key=lambda item: (item[0], item[1]), reverse=True):
        viewport.sprite(frame, palette, soldier_x, soldier_y)
    write_png(output, width, height, viewport.pixels)
    return {
        "battle": battle["file"], "output": str(output), "planmap": field["planmap"],
        "units": len(units), "drawn_units": len(rendered), "soldiers": len(placements),
        "missing_units": missing, "target": (target_x, target_y), "zoom": zoom, "rendered": rendered,
    }
