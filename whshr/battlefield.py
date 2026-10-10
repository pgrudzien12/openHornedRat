# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle scene data shared by the viewers and the engine: terrain, scenery, troop sprites, world conventions.

A battlefield is decoded once on the CPU. Renderers only upload it (the engine) or rasterize it (the
static viewers); none of them re-derive placements, frame selection or lighting on their own.
"""

from array import array
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import functools
import math
from os import PathLike
from pathlib import Path
import struct
from typing import Any

from . import legacy, pbx
from .image import load_rgb_palette
from .paths import Installation
from .script import View, load_battle, resource_name
from .sprites import colormap_indices, decode_frame

Vec3 = tuple[float, float, float]
Mesh = dict[str, Any]  # a parsed PBX mesh (whshr.pbx.parse_mesh)
Texture = dict[str, Any]  # a parsed PBX texture
Container = dict[str, Any]  # a parsed PBX container (whshr.pbx.parse_container)
Item = Mapping[str, Any]  # a scenery/furniture placement from the battle script
VertexFn = Callable[[Sequence[float]], Vec3]
NormalFn = Callable[[Sequence[float]], Vec3]

WORLD_PER_MESH = 8.0  # BTS world units per mesh (PBX/GD) unit
FULL_TURN = 512  # script `dir` units per turn: 0 = +Y, clockwise
DIRECTIONS = 8
DEFAULT_AMBIENT = 0.45
DEFAULT_LIGHT: Vec3 = (-0.4, 0.8, -0.3)
# Group order of the standard directional unit sets (notes/animations.md).
ACTION_GROUPS: dict[str, int] = {"move": 0, "dead": 1, "attack": 2, "stand": 3, "shoot": 4}
# Baked static geometry, one vertex: mesh-space position, texture UV, texture-array layer, flat shade.
VERTEX_FORMAT = "3f 2f 1f 1f"
VERTEX_FLOATS = 7
ATLAS_WIDTH = 2048


def container(path: str | PathLike[str]) -> Container:
    data, _ = pbx.pbx_rnc.unpack_pbx(str(path))
    return pbx.parse_container(data)


@functools.lru_cache(maxsize=4)
def mesh_assets(mesh_dir: Path) -> tuple[Container, Container, Container, Any]:
    """Decode a MESH directory once per process: (GRND, SCENERY, SPRITES containers, GRND.GD terrain)."""
    ground, scenery, sprites = (container(mesh_dir / f"{name}.PBX") for name in ("GRND", "SCENERY", "SPRITES"))
    return ground, scenery, sprites, legacy.module("gd_render").Terrain(mesh_dir / "GRND.GD")


@functools.lru_cache(maxsize=2)
def exe_tables(exe_path: Path) -> Any:
    return legacy.module("spritemap_build").read_tables(exe_path.read_bytes())


def furniture_meshes(game: Installation) -> dict[str, str]:
    """Script furniture name (casefolded) -> scenery mesh name in SCENERY.PBX."""
    _, furniture, _ = exe_tables(game.require("WHSHR.EXE"))
    return {entry["name"].casefold(): entry["file"] + ".XOF" for entry in furniture if entry["file"]}


def sprite_files(game: Installation, category: str) -> dict[str, str]:
    """Sprite resources in one sprite-table category -> FOL/BOP/PAL file base."""
    return resource_files(game, {category})


def resource_files(game: Installation, categories: Iterable[str] | None = None) -> dict[str, str]:
    """Return sprite resources by name, optionally restricted to sprite-table categories."""
    table = legacy.module("spritemap_build")
    records = [dict(entry) for entry in exe_tables(game.require("WHSHR.EXE"))[0]]  # assign_categories mutates.
    table.assign_categories(records)
    wanted = set(categories) if categories is not None else None
    return {entry["name"].casefold(): entry["file"] for entry in records
            if entry["file"] and (wanted is None or entry["category"] in wanted)}


def sprite_direction(camera_yaw: float, script_dir: float | None) -> int:
    """Directional frame (0-7) of a unit with script ``dir`` seen by a camera with ``camera_yaw`` degrees.

    Frame 0 shows the unit's back and the frames run clockwise on screen, like script dir: frame 2 faces
    screen-right, 4 the viewer and 6 screen-left (proven on labelled BRDHRS sheets, notes/animations.md).
    The frame is therefore the unit dir relative to the camera's screen-up heading (yaw + 180 degrees).
    The zero offset is derived, not observed (notes/battle_viewer.md).
    """
    heading = (camera_yaw + 180) * FULL_TURN / 360
    return math.floor(((script_dir or 0) - heading + 32) / 64) % DIRECTIONS


def view_angle(camera_yaw: float) -> int:
    """Camera rotation as a script `dir` value (1/512 turns): the camera's screen-up heading."""
    return round((camera_yaw + 180) * FULL_TURN / 360) % FULL_TURN


def scenery_transform(item: Item, ground_height: float, scale: float = 1.0) -> tuple[VertexFn, NormalFn]:
    """Return (vertex, normal) transforms placing a scenery mesh at a script ``placefurniture`` item.

    Script dir turns clockwise seen from above (as for unit formations): local +Z faces (sin a, cos a) and
    local +X faces (cos a, -sin a). Verified against BF035/BF036 plan maps.
    """
    angle = item["dir"] * math.tau / FULL_TURN
    x, z = item["x"] / WORLD_PER_MESH, item["y"] / WORLD_PER_MESH
    cos, sin = math.cos(angle), math.sin(angle)

    def vertex(position: Sequence[float]) -> Vec3:
        vx, vy, vz = position
        vx, vy, vz = vx * scale, vy * scale, vz * scale
        return (x + vx * cos + vz * sin, ground_height + vy, z - vx * sin + vz * cos)

    def normal(direction: Sequence[float]) -> Vec3:
        nx, ny, nz = direction
        return (nx * cos + nz * sin, ny, -nx * sin + nz * cos)

    return vertex, normal


def face_shade(normal: Sequence[float], ambient: float = DEFAULT_AMBIENT, light: Sequence[float] = DEFAULT_LIGHT) -> float:
    """Ambient plus Lambert diffuse brightness of a face with an unnormalized normal."""
    length = math.sqrt(sum(component * component for component in normal)) or 1
    light_length = math.sqrt(sum(component * component for component in light))
    diffuse = max(0, sum(a * b for a, b in zip(normal, light)) / length / light_length)
    return ambient + (1 - ambient) * diffuse


def bake_mesh(mesh: Mesh, layer_offset: int, layer_count: int, vertex: VertexFn | None = None,
              normal: NormalFn | None = None, ambient: float = DEFAULT_AMBIENT,
              light: Sequence[float] = DEFAULT_LIGHT, out: array[float] | None = None) -> array[float]:
    """Append a PBX mesh as world-space triangles in ``VERTEX_FORMAT``; polygons are fanned."""
    vertex = vertex or (lambda position: (position[0], position[1], position[2]))
    normal = normal or (lambda direction: (direction[0], direction[1], direction[2]))
    out = array("f") if out is None else out
    positions, texcoords, normals = mesh["verts"], mesh["uv"], mesh["normals"]
    for (indices, normal_indices), texture in zip(mesh["faces"], mesh["ftex"]):
        if texture >= layer_count:
            continue
        for index in range(1, len(indices) - 1):
            selected = (indices[0], indices[index], indices[index + 1])
            selected_normals = (normal_indices[0], normal_indices[index], normal_indices[index + 1])
            summed = [sum(normal(normals[3 * item:3 * item + 3])[axis] for item in selected_normals)
                      for axis in range(3)]
            shade = face_shade(summed, ambient, light)
            for item in selected:
                out.extend((*vertex(positions[3 * item:3 * item + 3]), texcoords[2 * item], texcoords[2 * item + 1],
                            layer_offset + texture, shade))
    return out


def texture_layers(textures: Iterable[Texture], size: tuple[int, int], transparent_black: bool = False) -> list[bytes]:
    """RGBA texture-array layers of one ``size``; smaller textures are tiled by texel repetition.

    Repeating each texel is exact under nearest sampling and keeps UV wrapping, so every mesh texture fits
    one texture array. Black scenery texels are transparent (alpha 0).
    """
    width, height = size
    layers: list[bytes] = []
    for texture in textures:
        w, h = texture["w"], texture["h"]
        if width % w or height % h:
            raise ValueError(f"texture {texture.get('name')} ({w}x{h}) does not tile a {width}x{height} layer")
        repeat_x, repeat_y = width // w, height // h
        colors = [bytes((*rgb, 0 if transparent_black and tuple(rgb) == (0, 0, 0) else 255)) * repeat_x
                  for rgb in texture["palette"]]
        colors += [bytes((0, 0, 0, 0 if transparent_black else 255)) * repeat_x] * max(0, 256 - len(colors))
        pixels = texture["pixels"]
        layers.append(b"".join(
            b"".join(colors[index] for index in pixels[row * w:(row + 1) * w]) * repeat_y for row in range(h)
        ))
    return layers


@dataclass
class SpriteFrame:
    width: int
    height: int
    anchor_x: int  # foot anchor column
    anchor_y: int  # foot anchor row, counted from the top
    pixels: bytes  # palette indices, row 0 at the top, 0 = transparent


@dataclass
class SpriteSheet:
    """One FOL/BOP directional set: frames, animation groups and, once packed, atlas rectangles."""

    name: str
    frames: list[SpriteFrame]
    groups: list[tuple[int, int]]  # (first frame, frame count) runs of one colour-map nibble
    rects: list[tuple[int, int, int, int] | None] = field(default_factory=list[tuple[int, int, int, int] | None])  # (x, y, width, height) per frame in the atlas

    def _group(self, action: str) -> tuple[int, int]:
        group = ACTION_GROUPS[action]
        if group < len(self.groups) and self.groups[group][1] >= DIRECTIONS:
            return self.groups[group]
        # Nonstandard layouts: fall back to the longest group.
        return max(self.groups, key=lambda item: item[1])

    def phases(self, action: str) -> int:
        return max(1, self._group(action)[1] // DIRECTIONS)

    def frame_index(self, action: str | int, phase: int, direction: int) -> int:
        """``frame = group_start + phase * 8 + direction`` for an action of the standard layout."""
        if isinstance(action, int):  # a first-frame number from a costume-variant family table
            return min(action + phase * DIRECTIONS + direction % DIRECTIONS, len(self.frames) - 1)
        start, count = self._group(action)
        if count < DIRECTIONS:
            return start + direction % count
        return start + (phase % self.phases(action)) * DIRECTIONS + direction % DIRECTIONS


def read_sprite_sheet(name: str, fol: bytes, bop: bytes, colors: bytes = b"") -> SpriteSheet:
    """Decode every frame of a FOL/BOP pair with its optional 512-byte colour maps."""
    if len(fol) % 16:
        raise ValueError(f"{name}.FOL size is not a multiple of 16 bytes: {len(fol)}")
    records = [struct.unpack_from("<hhhhIB", fol, offset) for offset in range(0, len(fol), 16)]
    if not records:
        raise ValueError(f"{name}.FOL has no frames")
    maps = [colors[offset:offset + 512] for offset in range(0, len(colors), 512)] if len(colors) % 512 == 0 else []
    map_indices = colormap_indices(records)
    offsets = sorted({record[4] for record in records}) + [len(bop)]
    ends = dict(zip(offsets, offsets[1:]))
    frames: list[SpriteFrame] = []
    groups: list[list[int]] = []
    for index, record in enumerate(records):
        width, height = record[2], record[3]
        pixels = decode_frame(bop, record, ends[record[4]], maps, map_indices[index])
        # In directional FOL entries byte 3 is the horizontal anchor and byte 2 is measured up from the bottom.
        frames.append(SpriteFrame(width, height, fol[index * 16 + 3], height - fol[index * 16 + 2],
                                  bytes(pixels).ljust(width * height, b"\0")[:width * height]))
        nibble = record[5] >> 4
        if groups and groups[-1][0] == nibble:
            groups[-1][2] += 1
        else:
            groups.append([nibble, index, 1])
    return SpriteSheet(name, frames, [(start, count) for _, start, count in groups])


def pack_atlas(sizes: Iterable[tuple[int, int]], width: int = ATLAS_WIDTH,
               padding: int = 1) -> tuple[int, list[tuple[int, int]]]:
    """Shelf-pack (width, height) rectangles in order; return (used height, top-left positions)."""
    x = y = shelf = 0
    positions: list[tuple[int, int]] = []
    for w, h in sizes:
        if w > width:
            raise ValueError(f"a {w} pixel wide frame does not fit a {width} pixel atlas")
        if x + w > width:
            x, y, shelf = 0, y + shelf + padding, 0
        positions.append((x, y))
        x += w + padding
        shelf = max(shelf, h)
    return y + shelf, positions


def build_atlas(sheets: Sequence[SpriteSheet], width: int = ATLAS_WIDTH) -> tuple[tuple[int, int], bytes]:
    """Pack all frames of ``sheets`` into one palette-index image and set each sheet's ``rects``."""
    frames = [(sheet, index, frame) for sheet in sheets for index, frame in enumerate(sheet.frames)]
    used, positions = pack_atlas([(frame.width, frame.height) for _, _, frame in frames], width)
    height = max(used, 1)
    atlas = bytearray(width * height)
    for sheet in sheets:
        sheet.rects = [None] * len(sheet.frames)
    for (sheet, index, frame), (x, y) in zip(frames, positions):
        for row in range(frame.height):
            start = (y + row) * width + x
            atlas[start:start + frame.width] = frame.pixels[row * frame.width:(row + 1) * frame.width]
        sheet.rects[index] = (x, y, frame.width, frame.height)
    return (width, height), bytes(atlas)


@dataclass
class Battlefield:
    """Everything needed to present one battle: script, terrain, baked static geometry and sprites."""

    script: dict[str, Any]
    terrain: Any  # gd_render.Terrain
    vertices: array[float]
    texture_size: tuple[int, int]
    texture_layers: list[bytes]
    palette: list[tuple[int, int, int]]
    atlas_size: tuple[int, int]
    atlas: bytes
    sheets: dict[str, SpriteSheet]  # troop sprite resource name (casefolded) -> SpriteSheet
    ui_sheets: dict[str, SpriteSheet]  # global HUD and per-unit portrait/banner sheets
    missing_scenery: list[str]
    effect_meshes: dict[str, Mesh] = field(default_factory=dict)
    ground_texture_count: int = 0
    scenery_texture_count: int = 0

    @property
    def width(self) -> int:
        return self.script["field"]["width"]

    @property
    def height(self) -> int:
        return self.script["field"]["height"]

    def ground_height(self, x: float, y: float) -> float:
        """Terrain height in mesh units under a BTS world point (0 outside GRND.GD)."""
        return self.terrain.height(x / WORLD_PER_MESH, y / WORLD_PER_MESH) or 0.0

    def sprite_sheet(self, resource: str | None) -> SpriteSheet | None:
        return self.sheets.get((resource or "").casefold())


def script_units(script: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [unit for army in script["armies"] + (script["merc"] or {}).get("armies", []) for unit in army["units"]]


def _sprite_file(game: Installation, bundled: Mapping[str, bytes], filename: str, required: bool = True) -> bytes:
    data = bundled.get(filename.casefold())
    if data is not None:
        return data
    try:
        return game.binary_file(filename).read_bytes()
    except FileNotFoundError:
        if required:
            raise
        return b""


def load_battlefield(installation: Installation | str | PathLike[str], battle_file: str | PathLike[str],
                     ambient: float = DEFAULT_AMBIENT, light: Sequence[float] = DEFAULT_LIGHT,
                     player_army: View | None = None) -> Battlefield:
    """Load a battle script and decode its terrain, scenery and troop sprites (per-battle bundle, then BINARY)."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    path = Path(battle_file)
    if not path.is_file():
        path = game.file_dir("SCRIPT", str(battle_file))
    script = load_battle(str(path))
    if player_army is not None:
        script["merc"] = player_army
    ground, scenery, sprites, terrain = mesh_assets(game.file_dir("MESH", script["field"]["mesh"]))

    size = (max(texture["w"] for texture in ground["textures"] + scenery["textures"]),
            max(texture["h"] for texture in ground["textures"] + scenery["textures"]))
    layers = texture_layers(ground["textures"], size) + texture_layers(scenery["textures"], size, True)
    vertices = bake_mesh(ground["meshes"][0], 0, len(ground["textures"]), ambient=ambient, light=light)
    meshes = {mesh["name"].casefold(): mesh for mesh in scenery["meshes"]}
    furniture = furniture_meshes(game)
    missing: list[str] = []
    for item in script["scenery"]:
        mesh = meshes.get((furniture.get(item["name"].casefold()) or "").casefold())
        if mesh is None:
            missing.append(item["name"])
            continue
        x, z = item["x"] / WORLD_PER_MESH, item["y"] / WORLD_PER_MESH
        vertex, normal = scenery_transform(item, terrain.height(x, z) or 0.0)
        bake_mesh(mesh, len(ground["textures"]), len(scenery["textures"]), vertex, normal, ambient, light, vertices)

    bundled = {name.casefold(): data for name, data in sprites["files"]}
    names = sprite_files(game, "troops")
    ui_names = resource_files(game, {"portraits", "banners", "backgrounds", "special", "terrain"})
    sheets: dict[str, SpriteSheet] = {}
    by_base: dict[str, SpriteSheet | None] = {}
    for unit in script_units(script):
        resource = resource_name(unit["sprites"]) or ""
        base = names.get(resource.casefold())
        if base is None:
            continue
        if base not in by_base:
            try:
                by_base[base] = read_sprite_sheet(base, _sprite_file(game, bundled, base + ".FOL"),
                                                  _sprite_file(game, bundled, base + ".BOP"),
                                                  _sprite_file(game, bundled, base + ".PAL", required=False))
            except FileNotFoundError:
                by_base[base] = None
        loaded = by_base[base]
        if loaded is not None:
            sheets[resource.casefold()] = loaded
    ui_sheets: dict[str, SpriteSheet] = {}
    ui_by_base: dict[str, SpriteSheet | None] = {}

    def load_ui(base: str | None) -> None:
        if not base or base in ui_by_base:
            return
        try:
            ui_by_base[base] = read_sprite_sheet(
                base, _sprite_file(game, bundled, base + ".FOL"),
                _sprite_file(game, bundled, base + ".BOP"),
                _sprite_file(game, bundled, base + ".PAL", required=False),
            )
        except (FileNotFoundError, ValueError):
            ui_by_base[base] = None

    # These are engine-global assets rather than files listed in SPRITES.PBX.
    load_ui("ICONS")
    load_ui("BACKALL")
    load_ui("GENBATT")  # battle-effects set: burning figures and charred corpses (animation.BURN_SEQUENCES)
    load_ui("SPELLS")  # effect set 2: spell visuals, drawn in the world (Fireball head, trail, explosion)
    load_ui("SPARKLE")  # effect set 3: the item marker of objectives K/X (notes/battle_end_objectives.md 12.2)
    planmap = script["field"].get("planmap")
    load_ui(planmap)
    portrait_bg = script["field"].get("portrait_bg")
    load_ui(portrait_bg)
    ui_resources: list[tuple[str, str | None]] = []
    banner_bases: dict[str, None] = {}
    for unit in script_units(script):
        banner = resource_name(unit.get("banner"))
        for resource in (banner, resource_name((unit.get("leader") or {}).get("portrait"))):
            if resource:
                base = ui_names.get(resource.casefold())
                load_ui(base)
                ui_resources.append((resource, base))
                if resource == banner and base:
                    banner_bases[base] = None
    for resource, base in (("ICONS", "ICONS"), ("BACKALL", "BACKALL"), ("GENBATT", "GENBATT"),
                           ("SPELLS", "SPELLS"), ("SPARKLE", "SPARKLE"),
                           (planmap, planmap),
                           (portrait_bg, portrait_bg), *ui_resources):
        loaded_ui = ui_by_base.get(base) if base is not None else None
        if resource and loaded_ui is not None:
            ui_sheets[resource.casefold()] = loaded_ui
    # Banner frame 2 is an in-world regiment marker, so these sheets also need atlas rectangles.
    if ui_by_base.get("GENBATT") is not None:
        banner_bases["GENBATT"] = None
    if ui_by_base.get("SPELLS") is not None:
        banner_bases["SPELLS"] = None  # drawn in the world, so it needs atlas rectangles too
    if ui_by_base.get("SPARKLE") is not None:
        banner_bases["SPARKLE"] = None  # drawn in the world, so it needs atlas rectangles too
    atlas_sheets = [sheet for sheet in by_base.values() if sheet is not None]
    for base in banner_bases:
        banner_sheet = ui_by_base.get(base)
        if banner_sheet is not None:
            atlas_sheets.append(banner_sheet)
    atlas_size, atlas = build_atlas(atlas_sheets)
    palette = load_rgb_palette(game.binary_file((script["field"]["palette"] or "standard") + ".PAL"))
    effects = {mesh["name"].split(".")[0].casefold(): mesh for mesh in scenery["meshes"]
               if mesh["name"].casefold().startswith(("arrows", "boltbur", "flames", "fire", "ex", "spear",
                                                         "light", "wlight", "gaze"))}
    return Battlefield(script, terrain, vertices, size, layers, palette, atlas_size, atlas, sheets, ui_sheets,
                       sorted(set(missing)), effects, len(ground["textures"]), len(scenery["textures"]))
