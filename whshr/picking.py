# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Screen-to-ground picking: a camera ray intersected with a terrain height field.

Pure geometry, the inverse of the verified `battle3d.Projection` perspective camera; no gameplay rule
lives here. Mesh-space coordinates in, mesh-space coordinates out (BTS world units are the caller's
concern, as in `battlefield.WORLD_PER_MESH`).
"""

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .battle3d import Projection

Vec3 = tuple[float, float, float]
HeightAt = Callable[[float, float], float]  # (mesh x, mesh z) -> terrain height

DEFAULT_STEP = 4.0  # mesh units per ray-march step (about half a metre); small enough for a foot soldier
DEFAULT_MAX_DISTANCE = 4000.0  # mesh units, matches the battle view's far plane
BISECTION_STEPS = 24  # halves a `DEFAULT_STEP` step down to a sub-millimetre-equivalent precision


def screen_ray(projection: "Projection", pixel_x: float, pixel_y: float) -> tuple[Vec3, Vec3]:
    """Return (origin, direction) of the camera ray through a screen pixel centre, in mesh-space units.

    ``direction`` is a unit vector; ``projection`` must be a perspective `battle3d.Projection`.
    """
    if not projection.perspective:
        raise ValueError("picking needs a perspective projection")
    ndc_x = (2 * (pixel_x + 0.5) / projection.width - 1) * projection.tan_fov_x
    ndc_y = (1 - 2 * (pixel_y + 0.5) / projection.height) * projection.tan_fov_y
    rx, ry, rz = projection.right
    ux, uy, uz = projection.up
    fx, fy, fz = projection.view_direction
    dx = rx * ndc_x + ux * ndc_y + fx
    dy = ry * ndc_x + uy * ndc_y + fy
    dz = rz * ndc_x + uz * ndc_y + fz
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    eye_x, eye_y, eye_z = projection.eye
    return (eye_x, eye_y, eye_z), (dx / length, dy / length, dz / length)


def intersect_ground(origin: Vec3, direction: Vec3, height_at: HeightAt, max_distance: float = DEFAULT_MAX_DISTANCE,
                     step: float = DEFAULT_STEP) -> tuple[float, float] | None:
    """March a ray until it crosses a height field and bisect the crossing to the (x, z) ground point.

    ``height_at(x, z)`` returns the terrain height at a mesh-space point. Returns None when the ray never
    crosses the field within ``max_distance`` (looking at the sky, or moving away from the ground).
    """
    ox, oy, oz = origin
    dx, dy, dz = direction

    def height_diff(t: float) -> float:
        return (oy + dy * t) - height_at(ox + dx * t, oz + dz * t)

    previous_t, previous_diff = 0.0, height_diff(0.0)
    if previous_diff == 0.0:
        return ox, oz
    t = step
    while t <= max_distance:
        diff = height_diff(t)
        if diff == 0.0:
            return ox + dx * t, oz + dz * t
        if (diff < 0) != (previous_diff < 0):
            lo, hi, lo_diff = previous_t, t, previous_diff
            for _ in range(BISECTION_STEPS):
                mid = (lo + hi) / 2
                mid_diff = height_diff(mid)
                if (mid_diff < 0) == (lo_diff < 0):
                    lo, lo_diff = mid, mid_diff
                else:
                    hi = mid
            return ox + dx * hi, oz + dz * hi
        previous_t, previous_diff = t, diff
        t += step
    return None


def pick_ground(projection: "Projection", pixel_x: float, pixel_y: float, height_at: HeightAt,
                max_distance: float = DEFAULT_MAX_DISTANCE, step: float = DEFAULT_STEP) -> tuple[float, float] | None:
    """Ground point (mesh-space x, z) under a screen pixel, or None if the ray never meets the field."""
    origin, direction = screen_ray(projection, pixel_x, pixel_y)
    return intersect_ground(origin, direction, height_at, max_distance, step)


VIEW_MARGIN = 10.0  # mesh units added on every side of the view rectangle (notes/react_portrait.md section 5)


def view_rect(projection: "Projection", width: int, height: int, camera_ground: tuple[float, float],
              height_at: HeightAt, margin: float = VIEW_MARGIN) -> tuple[float, float, float, float]:
    """Map-aligned (min x, min z, max x, max z) box around the camera's ground position and the ground under the
    far (top) screen corners, enlarged by `margin` (notes/react_portrait.md section 5). A corner whose ray never
    meets the ground is skipped. Mesh-space in and out."""
    xs, zs = [camera_ground[0]], [camera_ground[1]]
    for pixel_x in (0.0, float(width)):
        ground = pick_ground(projection, pixel_x, 0.0, height_at)
        if ground is not None:
            xs.append(ground[0])
            zs.append(ground[1])
    return min(xs) - margin, min(zs) - margin, max(xs) + margin, max(zs) + margin
