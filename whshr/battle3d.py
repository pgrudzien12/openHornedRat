"""Render a static, textured isometric battle scene to PNG."""

import math
import struct
import json
from pathlib import Path

from . import formation, legacy
from .battlefield import (  # noqa: F401 (DEFAULT_LIGHT and WORLD_PER_MESH are part of this module's interface)
    DEFAULT_LIGHT, WORLD_PER_MESH, container, face_shade, furniture_meshes, mesh_assets, scenery_transform,
    sprite_direction, troop_sprite_files,
)
from .image import load_rgb_palette, write_png
from .paths import Installation
from .script import load_battle
from .sprites import colormap_indices, decode_frame

BACKGROUND = (112, 150, 196)
DEFAULT_YAW = 45.0
DEFAULT_PITCH = 26.565
DEFAULT_DISTANCE = 160.0
DEFAULT_FOV = 50.0
PROJECTIONS = ("orthographic", "perspective")
# Mesh units a sprite's foot point is moved toward the camera for its depth test, so the ground it
# stands on (and a gentle slope just behind it) does not clip the billboard.
SPRITE_DEPTH_BIAS = 1.5


def validate_options(width, height, yaw, pitch, zoom, target_x, target_y, ambient, light, scenery_scale,
                     projection, distance, fov):
    """Reject camera values which would make projection or rasterization undefined."""
    values = (width, height, yaw, pitch, zoom, ambient, scenery_scale, distance, fov, *light)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("camera and lighting values must be finite")
    if target_x is not None and not math.isfinite(target_x):
        raise ValueError("target X must be finite")
    if target_y is not None and not math.isfinite(target_y):
        raise ValueError("target Y must be finite")
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be greater than zero")
    if projection not in PROJECTIONS:
        raise ValueError(f"projection must be one of: {', '.join(PROJECTIONS)}")
    if not 5 <= pitch <= 85:
        raise ValueError("pitch must be between 5 and 85 degrees")
    if zoom <= 0 or scenery_scale <= 0 or distance <= 0:
        raise ValueError("zoom, scenery scale, and distance must be greater than zero")
    if not 1 < fov < 179:
        raise ValueError("FOV must be between 1 and 179 degrees")
    if not 0 <= ambient <= 1:
        raise ValueError("ambient must be between 0 and 1")
    if not any(light):
        raise ValueError("light must not be the zero vector")


class Projection:
    """Orthographic or look-at perspective camera; game-map Y is mesh Z."""

    near = 0.05

    def __init__(self, width, height, field_width, field_height, yaw, pitch, zoom, target_x, target_z,
                 projection="orthographic", distance=DEFAULT_DISTANCE, fov=DEFAULT_FOV, target_height=0.0):
        if projection not in PROJECTIONS:
            raise ValueError(f"projection must be one of: {', '.join(PROJECTIONS)}")
        self.width, self.height = width, height
        self.yaw, self.pitch = math.radians(yaw), math.radians(pitch)
        self.target_x, self.target_z = target_x, target_z
        self.target_height = target_height
        self.projection = projection
        self.perspective = projection == "perspective"
        self.distance = distance
        self.fov = fov
        # Game data is left-handed (Direct3D RM): seen from above with +Z up on screen, +X is right.
        self.right = (-math.cos(self.yaw), 0.0, math.sin(self.yaw))
        self.view_direction = (-math.sin(self.yaw) * math.cos(self.pitch), -math.sin(self.pitch),
                               -math.cos(self.yaw) * math.cos(self.pitch))
        self.up = (-math.sin(self.yaw) * math.sin(self.pitch), math.cos(self.pitch),
                   -math.cos(self.yaw) * math.sin(self.pitch))
        horizontal = (math.sin(self.yaw) * math.cos(self.pitch), math.sin(self.pitch),
                      math.cos(self.yaw) * math.cos(self.pitch))
        self.eye = tuple(target + distance * offset for target, offset in zip(
            (target_x, target_height, target_z), horizontal
        ))
        self.tan_fov_y = math.tan(math.radians(fov) / 2)
        self.tan_fov_x = self.tan_fov_y * width / height
        self.focal_length = height / (2 * self.tan_fov_y)
        span_x, span_z = field_width / WORLD_PER_MESH, field_height / WORLD_PER_MESH
        horizontal = abs(math.cos(self.yaw)) * span_x + abs(math.sin(self.yaw)) * span_z
        vertical = abs(math.sin(self.yaw) * math.sin(self.pitch)) * span_x
        vertical += abs(math.cos(self.yaw) * math.sin(self.pitch)) * span_z
        self.scale = zoom * min(width * 0.92 / horizontal, height * 0.82 / vertical)
        self.cx = width / 2
        self.cy = height / 2

    @staticmethod
    def _dot(left, right):
        return sum(a * b for a, b in zip(left, right))

    def view(self, x, y, z):
        """Return camera-space X, up, and forward depth."""
        if self.perspective:
            relative = (x - self.eye[0], y - self.eye[1], z - self.eye[2])
            return (self._dot(relative, self.right), self._dot(relative, self.up),
                    self._dot(relative, self.view_direction))
        relative = (x - self.target_x, y - self.target_height, z - self.target_z)
        horizontal = relative[0] * math.sin(self.yaw) + relative[2] * math.cos(self.yaw)
        return (self._dot(relative, self.right),
                relative[1] * math.cos(self.pitch) - horizontal * math.sin(self.pitch),
                horizontal * math.cos(self.pitch) + relative[1] * math.sin(self.pitch))

    def project(self, view):
        """Map a camera-space point to screen coordinates and its depth-buffer value."""
        x, up, depth = view
        if self.perspective:
            return (self.cx + x * self.focal_length / depth, self.cy - up * self.focal_length / depth, 1 / depth)
        return (self.cx + x * self.scale, self.cy - up * self.scale, depth)

    def point(self, x, y, z):
        return self.project(self.view(x, y, z))[:2]

    def biased_depth(self, view, bias):
        """Depth-buffer value of a camera-space point moved ``bias`` mesh units toward the camera."""
        if self.perspective:
            return 1 / max(view[2] - bias, self.near)
        return view[2] + bias

    def depth(self, x, y, z):
        return self.project(self.view(x, y, z))[2]

    def clip_near(self, vertices):
        """Clip camera-space vertices and UVs to the perspective view frustum."""
        if not self.perspective:
            return vertices
        planes = (
            lambda view: view[2] - self.near,
            lambda view: view[0] + view[2] * self.tan_fov_x,
            lambda view: view[2] * self.tan_fov_x - view[0],
            lambda view: view[1] + view[2] * self.tan_fov_y,
            lambda view: view[2] * self.tan_fov_y - view[1],
        )
        for plane in planes:
            if not vertices:
                break
            clipped = []
            for previous, current in zip(vertices[-1:] + vertices[:-1], vertices):
                previous_view, previous_uv = previous
                current_view, current_uv = current
                previous_distance, current_distance = plane(previous_view), plane(current_view)
                previous_inside, current_inside = previous_distance >= 0, current_distance >= 0
                if previous_inside != current_inside:
                    fraction = previous_distance / (previous_distance - current_distance)
                    clipped.append((
                        tuple(a + fraction * (b - a) for a, b in zip(previous_view, current_view)),
                        tuple(a + fraction * (b - a) for a, b in zip(previous_uv, current_uv)),
                    ))
                if current_inside:
                    clipped.append(current)
            vertices = clipped
        return vertices


class Renderer:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.pixels = bytearray(bytes(BACKGROUND) * (width * height))
        self.depth = [float("-inf")] * (width * height)

    def triangle(self, points, depths, uv, texture, transparent=False, shade=1.0, perspective=False):
        """Rasterize one textured triangle with depth testing."""
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
                depth = a * depths[0] + b * depths[1] + c * depths[2]
                if depth <= self.depth[py * self.width + px]:
                    continue
                if perspective:
                    u = (a * uv[0][0] * depths[0] + b * uv[1][0] * depths[1] + c * uv[2][0] * depths[2]) / depth
                    v = (a * uv[0][1] * depths[0] + b * uv[1][1] * depths[1] + c * uv[2][1] * depths[2]) / depth
                else:
                    u = a * uv[0][0] + b * uv[1][0] + c * uv[2][0]
                    v = a * uv[0][1] + b * uv[1][1] + c * uv[2][1]
                color = palette[tex_px[(math.floor(v * tex_h) % tex_h) * tex_w + math.floor(u * tex_w) % tex_w]]
                if transparent and color == (0, 0, 0):
                    continue
                pixel = py * self.width + px
                self.depth[pixel] = depth
                index = pixel * 3
                self.pixels[index:index + 3] = bytes(min(255, int(component * shade)) for component in color)

    def sprite(self, pixels, rgb, width, height, anchor_x, bottom_x, bottom_y, scale, depth=None):
        """Draw an upright billboard; with ``depth``, pixels behind the depth buffer are hidden."""
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
                        if depth is not None and depth < self.depth[py * self.width + px]:
                            continue
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


def _triangles(mesh, textures, projection, transform=lambda vertex: vertex,
               normal_transform=lambda normal: normal, scenery=False, ambient=0.45, light=DEFAULT_LIGHT):
    vertices, texcoords = mesh["verts"], mesh["uv"]
    result = []
    for face, texture_index in zip(mesh["faces"], mesh["ftex"]):
        if texture_index >= len(textures):
            continue
        indices, normal_indices = face
        for index in range(1, len(indices) - 1):
            selected = (indices[0], indices[index], indices[index + 1])
            selected_normals = (normal_indices[0], normal_indices[index], normal_indices[index + 1])
            world = [transform(vertices[3 * item:3 * item + 3]) for item in selected]
            vertex_uv = [(texcoords[2 * item], texcoords[2 * item + 1]) for item in selected]
            clipped = projection.clip_near([(projection.view(*vertex), coordinate)
                                            for vertex, coordinate in zip(world, vertex_uv)])
            if len(clipped) < 3:
                continue
            normals = mesh["normals"]
            normal = [sum(normal_transform(normals[3 * item:3 * item + 3])[axis] for item in selected_normals)
                      for axis in range(3)]
            shade = face_shade(normal, ambient, light)
            for clipped_index in range(1, len(clipped) - 1):
                triangle = (clipped[0], clipped[clipped_index], clipped[clipped_index + 1])
                projected = [projection.project(vertex) for vertex, _ in triangle]
                points = [vertex[:2] for vertex in projected]
                depths = [vertex[2] for vertex in projected]
                uv = [coordinate for _, coordinate in triangle]
                result.append((sum(depths) / 3, points, depths, uv, textures[texture_index], scenery, shade))
    return result


def _sprite_frame(files, name, palette, direction=0):
    """Decode an idle pose of a unit from files embedded in SPRITES.PBX."""
    by_name = {filename.casefold(): data for filename, data in files}
    base = name.casefold()
    fol, bop = by_name.get(base + ".fol"), by_name.get(base + ".bop")
    if fol is None or bop is None:
        return None
    records = [struct.unpack_from("<hhhhIB", fol, offset) for offset in range(0, len(fol), 16)]
    frame = 72 + direction if len(records) >= 104 else 0
    record = records[frame]
    offsets = sorted({entry[4] for entry in records}) + [len(bop)]
    colors = by_name.get(base + ".pal", b"")
    maps = [colors[offset:offset + 512] for offset in range(0, len(colors), 512)] if colors else []
    map_index = colormap_indices(records)[frame]
    decoded = decode_frame(bop, record, offsets[offsets.index(record[4]) + 1], maps, map_index)
    return decoded, palette, record[2], record[3], fol[frame * 16 + 3]


def _formation(unit):
    """Return individual soldier positions in mesh units, with the unit anchor at the front-rank centre."""
    positions, count, ranks = formation.unit_layout(unit)
    return [(x / WORLD_PER_MESH, y / WORLD_PER_MESH) for x, y in positions], count, ranks


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
        # NaN (not a crash) when no vertex lies inside GRND.GD; it also fails any "< tolerance" check.
        "rmse": math.sqrt(sum(value * value for value in differences) / len(differences)) if differences else math.nan,
        "max_error": max(map(abs, differences)) if differences else math.nan,
    }


def check_orientation():
    """Check screen orientation without game data: +X right, +Z up, target at the centre."""
    ok = True
    for projection in PROJECTIONS:
        camera = Projection(640, 480, 1600, 1760, 180, 85, 1.0, 100.0, 110.0, projection, target_height=4.0)
        cx, cy = camera.point(100.0, 4.0, 110.0)
        east, north = camera.point(110.0, 4.0, 110.0), camera.point(100.0, 4.0, 120.0)
        checks = {
            "target at centre": abs(cx - camera.cx) < 1e-6 and abs(cy - camera.cy) < 1e-6,
            "+X projects right": east[0] > cx,
            "+Z projects up": north[1] < cy,
        }
        for name, passed in checks.items():
            if not passed:
                print(f"orientation {projection}: {name} failed")
                ok = False
    return ok


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
        container_data = container(packed)
        if not container_data["meshes"]:  # BF004 uses the legacy container layout.
            continue
        comparison = terrain_comparison(container_data["meshes"][0], legacy.module("gd_render").Terrain(gd))
        comparison["mesh"] = directory.name
        results.append(comparison)
    return results


def render(installation, battle_file, output, width=1280, height=900, diagnostic=False,
           yaw=DEFAULT_YAW, pitch=DEFAULT_PITCH, zoom=1.0, target_x=None, target_y=None,
           ambient=0.45, light=DEFAULT_LIGHT, scenery_scale=1.0, projection="orthographic",
           distance=DEFAULT_DISTANCE, fov=DEFAULT_FOV):
    """Render ``battle_file`` (a name or path) to ``output`` and return scene statistics."""
    validate_options(width, height, yaw, pitch, zoom, target_x, target_y, ambient, light, scenery_scale,
                     projection, distance, fov)
    game = Installation(installation)
    battle_path = Path(battle_file)
    if not battle_path.is_file():
        battle_path = game.file_dir("SCRIPT", battle_file)
    battle = load_battle(str(battle_path))
    mesh_dir = game.file_dir("MESH", battle["field"]["mesh"])
    ground, scenery, sprites, terrain = mesh_assets(mesh_dir)
    target_x = battle["field"]["width"] / 2 if target_x is None else target_x
    target_y = battle["field"]["height"] / 2 if target_y is None else target_y
    target_mesh_x, target_mesh_z = target_x / WORLD_PER_MESH, target_y / WORLD_PER_MESH
    target_height = terrain.height(target_mesh_x, target_mesh_z) or 0.0
    projection = Projection(width, height, battle["field"]["width"], battle["field"]["height"], yaw, pitch, zoom,
                            target_mesh_x, target_mesh_z, projection, distance, fov, target_height)
    renderer = Renderer(width, height)
    triangles = _triangles(ground["meshes"][0], _textures(ground), projection, ambient=ambient, light=light)
    mesh_by_name = {mesh["name"].casefold(): mesh for mesh in scenery["meshes"]}
    furniture = furniture_meshes(game)
    missing_scenery = []
    for item in battle["scenery"]:
        mesh_name = furniture.get(item["name"].casefold())
        mesh = mesh_by_name.get((mesh_name or "").casefold())
        if mesh is None:
            missing_scenery.append(item["name"])
            continue
        x, z = item["x"] / WORLD_PER_MESH, item["y"] / WORLD_PER_MESH
        transform, rotate_normal = scenery_transform(item, terrain.height(x, z) or 0.0, scenery_scale)
        triangles += _triangles(mesh, _textures(scenery), projection, transform, rotate_normal, True, ambient, light)
    for _, points, depths, uv, texture, transparent, shade in sorted(triangles, key=lambda item: item[0], reverse=True):
        renderer.triangle(points, depths, uv, texture, transparent, shade, projection.perspective)

    palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    sprite_names = troop_sprite_files(game)
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
    diagnostics = {"battle": battle["file"],
                   "terrain": terrain_comparison(ground["meshes"][0], terrain) if diagnostic else None,
                   "camera": {
                       "projection": projection.projection, "yaw": yaw, "pitch": pitch, "zoom": zoom,
                       "distance": distance, "fov": fov, "target": [target_x, target_y],
                       "look_at": [target_mesh_x, target_height, target_mesh_z], "eye": projection.eye,
                   },
                   "lighting": {"ambient": ambient, "direction": light}, "scenery_scale": scenery_scale,
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
    soldiers, origins = [], []
    for unit in units:
        base = sprite_names.get((unit["sprites"] or "").split(",", 1)[0].casefold())
        direction = sprite_direction(yaw, unit["set"].get("dir"))
        frame = base and _sprite_frame(sprite_files, base, palette, direction)
        if frame is None or "x" not in unit["set"] or "y" not in unit["set"]:
            continue
        positions, count, ranks = _formation(unit)
        x, z = unit["set"]["x"] / WORLD_PER_MESH, unit["set"]["y"] / WORLD_PER_MESH
        for soldier_x, soldier_z in positions:
            view = projection.view(soldier_x, terrain.height(soldier_x, soldier_z) or 0, soldier_z)
            if projection.perspective and view[2] < projection.near:
                continue
            soldiers.append((projection.project(view), view, frame))
        inside = all(terrain_bounds[0] <= soldier_x <= terrain_bounds[1]
                     and terrain_bounds[2] <= soldier_z <= terrain_bounds[3]
                     for soldier_x, soldier_z in positions)
        origins.append((projection.point(x, terrain.height(x, z) or 0, z), inside))
        diagnostics["units"].append({"name": unit["name"], "sprite": unit["sprites"],
                                     "x": unit["set"]["x"], "y": unit["set"]["y"],
                                     "ground_height": terrain.height(x, z), "inside_mesh": inside,
                                     "soldiers": count, "ranks": ranks, "sprite_direction": direction})
        drawn_units += 1
    # Larger depth-buffer values are nearer in both projections: paint far soldiers first, and test the
    # foot point against terrain/scenery so occluders in front hide the billboard.
    for (sx, sy, _), view, frame in sorted(soldiers, key=lambda item: item[0][2]):
        pixels, rgb, sprite_width, sprite_height, anchor_x = frame
        pixel_mesh = formation.SPRITE_PIXEL_WORLD_UNITS / WORLD_PER_MESH
        scale = (projection.focal_length / view[2] if projection.perspective else projection.scale) * pixel_mesh
        renderer.sprite(pixels, rgb, sprite_width, sprite_height, anchor_x, sx, sy, scale,
                        projection.biased_depth(view, SPRITE_DEPTH_BIAS))
    if diagnostic:
        for (sx, sy), inside in origins:
            renderer.cross(sx, sy, (50, 230, 70) if inside else (255, 45, 45), 3)
    write_png(output, width, height, renderer.pixels)
    if diagnostic:
        Path(output).with_suffix(".json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    return {"battle": battle["file"], "output": str(output), "scenery": len(battle["scenery"]),
            "missing_scenery": sorted(set(missing_scenery)), "units": len(units), "drawn_units": drawn_units}
