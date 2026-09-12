"""Render a static, textured isometric battle scene to PNG."""

import math
import os
import struct
import json
from pathlib import Path

from . import legacy, pbx
from .image import load_rgb_palette, write_png
from .paths import Installation
from .script import load_battle
from .sprites import colormap_indices, decode_frame

WORLD_PER_MESH = 8.0
BACKGROUND = (112, 150, 196)


def _container(path):
    data, _ = pbx.pbx_rnc.unpack_pbx(str(path))
    return pbx.parse_container(data)


def _furniture(game):
    tables = legacy.module("spritemap_build")
    _, furniture, _ = tables.read_tables(game.require("WHSHR.EXE").read_bytes())
    return {entry["name"].casefold(): entry["file"] + ".XOF" for entry in furniture if entry["file"]}


class Projection:
    """Orthographic view from the south-west, with game-map Y represented by mesh Z."""

    def __init__(self, width, height, field_width, field_height):
        self.width, self.height = width, height
        span = max(field_width, field_height) / WORLD_PER_MESH
        # The visible diamond is twice the map span in the projection's vertical axis.
        self.scale = min(width / (span * 1.65), height / (span * 1.25))
        self.cx = width / 2
        self.cy = height * 0.37

    def point(self, x, y, z):
        return (self.cx + (x - z) * self.scale * 0.82,
                self.cy + (x + z) * self.scale * 0.39 - y * self.scale * 0.78)

    @staticmethod
    def depth(x, y, z):
        return x + z + y * 0.25


class Renderer:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.pixels = bytearray(bytes(BACKGROUND) * (width * height))

    def triangle(self, points, uv, texture, transparent=False, shade=1.0):
        """Rasterize one textured triangle. Geometry is painter-sorted by the caller."""
        (x0, y0), (x1, y1), (x2, y2) = points
        determinant = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(determinant) < 1e-8:
            return
        xmin = max(0, int(math.floor(min(x0, x1, x2))))
        xmax = min(self.width - 1, int(math.ceil(max(x0, x1, x2))))
        ymin = max(0, int(math.floor(min(y0, y1, y2))))
        ymax = min(self.height - 1, int(math.ceil(max(y0, y1, y2))))
        tex_w, tex_h, tex_px, palette = texture
        for py in range(ymin, ymax + 1):
            for px in range(xmin, xmax + 1):
                sx, sy = px + 0.5, py + 0.5
                a = ((y1 - y2) * (sx - x2) + (x2 - x1) * (sy - y2)) / determinant
                b = ((y2 - y0) * (sx - x2) + (x0 - x2) * (sy - y2)) / determinant
                c = 1 - a - b
                if a < 0 or b < 0 or c < 0:
                    continue
                u = a * uv[0][0] + b * uv[1][0] + c * uv[2][0]
                v = a * uv[0][1] + b * uv[1][1] + c * uv[2][1]
                color = palette[tex_px[(int(v * tex_h) % tex_h) * tex_w + int(u * tex_w) % tex_w]]
                if transparent and color == (0, 0, 0):
                    continue
                index = (py * self.width + px) * 3
                self.pixels[index:index + 3] = bytes(min(255, int(component * shade)) for component in color)

    def sprite(self, pixels, rgb, width, height, anchor_x, bottom_x, bottom_y, scale):
        left = int(round(bottom_x - anchor_x * scale))
        top = int(round(bottom_y - height * scale))
        for sy in range(height):
            py0, py1 = int(top + sy * scale), int(top + (sy + 1) * scale)
            if py1 <= 0 or py0 >= self.height:
                continue
            for sx in range(width):
                value = pixels[sy * width + sx]
                if not value:
                    continue
                px0, px1 = int(left + sx * scale), int(left + (sx + 1) * scale)
                for py in range(max(0, py0), min(self.height, py1)):
                    for px in range(max(0, px0), min(self.width, px1)):
                        index = (py * self.width + px) * 3
                        self.pixels[index:index + 3] = bytes(rgb[value])

    def cross(self, x, y, color, radius=4):
        for delta in range(-radius, radius + 1):
            for px, py in ((int(x + delta), int(y)), (int(x), int(y + delta))):
                if 0 <= px < self.width and 0 <= py < self.height:
                    index = (py * self.width + px) * 3
                    self.pixels[index:index + 3] = bytes(color)


def _textures(container):
    return [(item["w"], item["h"], item["pixels"], item["palette"]) for item in container["textures"]]


def _triangles(mesh, textures, projection, transform=lambda vertex: vertex, scenery=False):
    vertices, texcoords = mesh["verts"], mesh["uv"]
    result = []
    for face, texture_index in zip(mesh["faces"], mesh["ftex"]):
        if texture_index >= len(textures):
            continue
        indices = face[0]
        for index in range(1, len(indices) - 1):
            selected = (indices[0], indices[index], indices[index + 1])
            world = [transform(vertices[3 * item:3 * item + 3]) for item in selected]
            points = [projection.point(*item) for item in world]
            uv = [(texcoords[2 * item], texcoords[2 * item + 1]) for item in selected]
            depth = sum(projection.depth(*item) for item in world) / 3
            result.append((depth, points, uv, textures[texture_index], scenery))
    return result


def _sprite_frame(files, name, palette):
    """Decode the first idle pose of a unit from files embedded in SPRITES.PBX."""
    by_name = {filename.casefold(): data for filename, data in files}
    base = name.casefold()
    fol, bop = by_name.get(base + ".fol"), by_name.get(base + ".bop")
    if fol is None or bop is None:
        return None
    records = [struct.unpack_from("<hhhhIB", fol, offset) for offset in range(0, len(fol), 16)]
    frame = 72 if len(records) >= 104 else 0
    record = records[frame]
    offsets = sorted({entry[4] for entry in records}) + [len(bop)]
    colors = by_name.get(base + ".pal", b"")
    maps = [colors[offset:offset + 512] for offset in range(0, len(colors), 512)] if colors else []
    map_index = colormap_indices(records)[frame]
    decoded = decode_frame(bop, record, offsets[offsets.index(record[4]) + 1], maps, map_index)
    return decoded, palette, record[2], record[3], fol[frame * 16 + 3]


def terrain_comparison(mesh, terrain):
    """Compare each GRND.PBX vertex with the plane height at its X/Z coordinates."""
    vertices = mesh["verts"]
    differences, outside = [], 0
    for x, y, z in zip(vertices[::3], vertices[1::3], vertices[2::3]):
        ground = terrain.height(x, z)
        if ground is None:
            outside += 1
        else:
            differences.append(y - ground)
    return {
        "vertices": len(vertices) // 3, "compared": len(differences), "outside_gd": outside,
        "rmse": math.sqrt(sum(value * value for value in differences) / len(differences)),
        "max_error": max(map(abs, differences)),
    }


def check_terrain(installation, battle=None):
    """Check that GRND.PBX mesh heights agree with GRND.GD for one or all mesh directories."""
    game = Installation(installation)
    mesh_root = game.file_dir("MESH")
    names = [battle] if battle else sorted(path.name for path in mesh_root.iterdir() if path.is_dir())
    results = []
    for name in names:
        directory = game.find("FILE", "MESH", name)
        if directory is None:
            raise FileNotFoundError(f"MESH/{name} not found")
        gd, packed = directory / "GRND.GD", directory / "GRND.PBX"
        if not gd.is_file() or not packed.is_file():
            continue
        container = _container(packed)
        if not container["meshes"]:  # BF004 uses the legacy container layout.
            continue
        comparison = terrain_comparison(container["meshes"][0], legacy.module("gd_render").Terrain(gd))
        comparison["mesh"] = directory.name
        results.append(comparison)
    return results


def render(installation, battle_file, output, width=1280, height=900, diagnostic=False):
    """Render ``battle_file`` (a name or path) to ``output`` and return scene statistics."""
    game = Installation(installation)
    battle_path = Path(battle_file)
    if not battle_path.is_file():
        battle_path = game.file_dir("SCRIPT", battle_file)
    battle = load_battle(str(battle_path))
    mesh_dir = game.file_dir("MESH", battle["field"]["mesh"])
    ground, scenery, sprites = (_container(mesh_dir / f"{name}.PBX") for name in ("GRND", "SCENERY", "SPRITES"))
    terrain = legacy.module("gd_render").Terrain(mesh_dir / "GRND.GD")
    projection = Projection(width, height, battle["field"]["width"], battle["field"]["height"])
    renderer = Renderer(width, height)
    triangles = _triangles(ground["meshes"][0], _textures(ground), projection)
    mesh_by_name = {mesh["name"].casefold(): mesh for mesh in scenery["meshes"]}
    furniture = _furniture(game)
    missing_scenery = []
    for item in battle["scenery"]:
        mesh_name = furniture.get(item["name"].casefold())
        mesh = mesh_by_name.get((mesh_name or "").casefold())
        if mesh is None:
            missing_scenery.append(item["name"])
            continue
        angle = item["dir"] * math.tau / 512
        x, z = item["x"] / WORLD_PER_MESH, item["y"] / WORLD_PER_MESH
        ground_height = terrain.height(x, z) or 0.0

        def transform(vertex, angle=angle, x=x, z=z, ground_height=ground_height):
            vx, vy, vz = vertex
            return (x + vx * math.cos(angle) - vz * math.sin(angle),
                    ground_height + vy, z + vx * math.sin(angle) + vz * math.cos(angle))

        triangles += _triangles(mesh, _textures(scenery), projection, transform, scenery=True)
    for _, points, uv, texture, transparent in sorted(triangles, key=lambda item: item[0], reverse=True):
        renderer.triangle(points, uv, texture, transparent)

    palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    table = legacy.module("spritemap_build")
    sprite_records, _, _ = table.read_tables(game.require("WHSHR.EXE").read_bytes())
    table.assign_categories(sprite_records)
    sprite_names = {entry["name"].casefold(): entry["file"] for entry in sprite_records
                    if entry["category"] == "troops" and entry["file"]}
    units = [unit for army in battle["armies"] + (battle["merc"] or {}).get("armies", [])
             for unit in army["units"]]
    sprite_files = list(sprites["files"])
    bundled = {name.casefold() for name, _ in sprite_files}
    for name in {sprite_names.get((unit["sprites"] or "").split(",", 1)[0].casefold()) for unit in units} - {None}:
        for suffix in (".FOL", ".BOP", ".PAL"):
            filename = name + suffix
            if filename.casefold() in bundled:
                continue
            try:
                sprite_files.append((filename, game.binary_file(filename).read_bytes()))
                bundled.add(filename.casefold())
            except FileNotFoundError:
                pass
    drawn_units = 0
    diagnostics = {"battle": battle["file"], "terrain": terrain_comparison(ground["meshes"][0], terrain),
                   "scenery": [], "units": []}
    mesh_x = ground["meshes"][0]["verts"][::3]
    mesh_z = ground["meshes"][0]["verts"][2::3]
    terrain_bounds = (min(mesh_x), max(mesh_x), min(mesh_z), max(mesh_z))
    if diagnostic:
        for item in battle["scenery"]:
            x, z = item["x"] / WORLD_PER_MESH, item["y"] / WORLD_PER_MESH
            sx, sy = projection.point(x, terrain.height(x, z) or 0, z)
            renderer.cross(sx, sy, (255, 0, 255))
            diagnostics["scenery"].append({**item, "mesh": furniture.get(item["name"].casefold()),
                                           "ground_height": terrain.height(x, z)})
    for unit in sorted(units, key=lambda item: item["set"].get("x", 0) + item["set"].get("y", 0), reverse=True):
        base = sprite_names.get((unit["sprites"] or "").split(",", 1)[0].casefold())
        frame = base and _sprite_frame(sprite_files, base, palette)
        if frame is None or "x" not in unit["set"] or "y" not in unit["set"]:
            continue
        pixels, rgb, sprite_width, sprite_height, anchor_x = frame
        x, z = unit["set"]["x"] / WORLD_PER_MESH, unit["set"]["y"] / WORLD_PER_MESH
        sx, sy = projection.point(x, terrain.height(x, z) or 0, z)
        renderer.sprite(pixels, rgb, sprite_width, sprite_height, anchor_x, sx, sy, projection.scale / 6)
        inside = terrain_bounds[0] <= x <= terrain_bounds[1] and terrain_bounds[2] <= z <= terrain_bounds[3]
        if diagnostic:
            renderer.cross(sx, sy, (50, 230, 70) if inside else (255, 45, 45), 3)
        diagnostics["units"].append({"name": unit["name"], "sprite": unit["sprites"],
                                     "x": unit["set"]["x"], "y": unit["set"]["y"],
                                     "ground_height": terrain.height(x, z), "inside_mesh": inside})
        drawn_units += 1
    write_png(output, width, height, renderer.pixels)
    if diagnostic:
        Path(output).with_suffix(".json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    return {"battle": battle["file"], "output": str(output), "scenery": len(battle["scenery"]),
            "missing_scenery": sorted(set(missing_scenery)), "units": len(units), "drawn_units": drawn_units}
