"""Dynamic MeshDragon visuals from notes/bf014_dragon_rendering.md; no sprite substitution."""
from __future__ import annotations

from array import array
from collections.abc import Sequence
import math
from typing import TYPE_CHECKING

from . import animation, interpreter
from .battlefield import Mesh, NormalFn, VertexFn, WORLD_PER_MESH, bake_mesh

if TYPE_CHECKING:
    from .battlefield import Battlefield
    from .engine import Battle, ModelState, Regiment


def transform(x: float, y: float, ground: float, height: float, heading: float) -> tuple[VertexFn, NormalFn]:
    """Authored pivot and natural size, with the mesh's coarse visual yaw (§2)."""
    angle = math.floor((heading % 512) / 8) * math.tau / 63
    cos, sin = math.cos(angle), math.sin(angle)

    def rotate(v: Sequence[float]) -> tuple[float, float, float]:
        return v[0] * cos + v[2] * sin, v[1], -v[0] * sin + v[2] * cos

    def place(v: Sequence[float]) -> tuple[float, float, float]:
        vx, vy, vz = rotate(v)
        return x / WORLD_PER_MESH + vx, ground + height / WORLD_PER_MESH + vy, y / WORLD_PER_MESH + vz

    return place, rotate


def visible(battle: Battle, unit: Regiment, display_rect: tuple[float, float, float, float] | None = None) -> bool:
    """Cull by the reference position, independently of mesh extent and model-update timing (§4)."""
    if not unit.active or not unit.visible_to_player:
        return False
    state = battle.event_bus.unit_states.get(unit.identifier)
    if state is not None and state.unit_flags & interpreter.NOT_SHOWN_FLAG:
        return False
    rect = display_rect if display_rect is not None else battle.view_rect
    return rect is None or rect[0] <= unit.x <= rect[2] and rect[1] <= unit.y <= rect[3]


def model_vertices(field: Battlefield, unit: Regiment, model: ModelState, x: float, y: float) -> array[float]:
    pose = animation.mesh_dragon_pose(model)
    mesh: Mesh | None = field.dragon_meshes.get(pose)
    if mesh is None:
        # Defensive host policy, rather than the original's unestablished unsafe failure path (§5).
        raise ValueError(f"MeshDragon pose {pose} is unavailable")
    heading = unit.direction if model.drawn_facing is None else model.drawn_facing
    place, rotate = transform(x, y, field.ground_height(x, y), model.height_above_ground, heading)
    return bake_mesh(mesh, field.ground_texture_count, field.scenery_texture_count, place, rotate)


def unit_vertices(field: Battlefield, battle: Battle, unit: Regiment,
                  display_rect: tuple[float, float, float, float] | None = None) -> array[float]:
    vertices = array('f')
    if visible(battle, unit, display_rect):
        for (x, y), model in zip(unit.seeded_positions(), unit.melee_models):
            if (unit.model_sprite(model) or '').casefold() == 'meshdragon':
                vertices.extend(model_vertices(field, unit, model, x, y))
    return vertices


def uses_mesh(unit: Regiment) -> bool:
    return any((resource or "").casefold() == "meshdragon" for resource in (unit.sprite, unit.leader_sprite))


def append_vertices(field: Battlefield, battle: Battle, vertices: array[float],
                    display_rect: tuple[float, float, float, float] | None = None) -> None:
    for unit in battle.regiments.values():
        if uses_mesh(unit):
            vertices.extend(unit_vertices(field, battle, unit, display_rect))
