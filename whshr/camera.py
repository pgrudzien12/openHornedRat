# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle camera state and controls, independent of any renderer (BTS world units and degrees)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import math
from typing import Any

from .battle3d import DEFAULT_FOV, Projection
from .battlefield import WORLD_PER_MESH
from .navigation import Boundary, boundaries_from_views

# Engine camera rules (user decisions, not measured original values): pitch and distance start at 40 (mesh units),
# the distance is held within 20..70; the pitch range only bounds the temporary terrain lift and the tilt keys.
BATTLE_PITCH, BATTLE_DISTANCE = 40.0, 40.0
MIN_DISTANCE, MAX_DISTANCE = 20.0, 70.0
MIN_PITCH, MAX_PITCH = 5.0, 85.0
NORTH_YAW = 180.0
TERRAIN_PITCH_STEP = 5.0  # how far the view pitch rises per trial while terrain blocks the sightline
TERRAIN_DISTANCE_FACTOR = 0.8  # then how much the view distance shrinks per trial


def initial_yaw(field_camera: float | None) -> float:
    """Working hypothesis: [FIELD] Camera is the view heading clockwise from north (notes/battle_viewer.md)."""
    return (NORTH_YAW + field_camera) % 360 if field_camera is not None else NORTH_YAW


@dataclass
class BattleCamera:
    """A perspective look-at camera around a ground target; ``yaw`` 180 looks north with +X to the right.

    ``pitch`` and ``distance`` are the values the player chose. The rendered ``view_pitch``/``view_distance`` start
    from them on every camera change and are lifted or shortened only while terrain would block the sightline, so
    such a change is temporary: it goes away as soon as the camera moves somewhere the chosen view is clear.
    Only the look-at point is confined: to the map's active CameraEdge areas and to ``bounds`` (the field)."""

    target_x: float
    target_y: float
    yaw: float = NORTH_YAW
    pitch: float = BATTLE_PITCH
    distance: float = BATTLE_DISTANCE
    fov: float = DEFAULT_FOV
    camera_edges: tuple[Boundary, ...] = ()
    terrain_height: Callable[[float, float], float] | None = None
    bounds: tuple[float, float, float, float] | None = None  # (min x, min y, max x, max y), used without edges
    view_pitch: float = field(init=False)
    view_distance: float = field(init=False)

    def __post_init__(self) -> None:
        self.view_pitch, self.view_distance = self.pitch, self.distance
        self.update()

    @classmethod
    def for_battle(cls, script: Mapping[str, Any],
                   terrain_height: Callable[[float, float], float] | None = None,
                   unit_positions: Mapping[str, tuple[float, float]] | None = None) -> "BattleCamera":
        """Look at the player's first unit along the battle's initial heading; without player units, at the field
        centre. The original centres on the selected unit when the battle view opens (no data key sets the point),
        and the first unit of the player army stands in for it. `unit_positions` (regiment id -> position) gives the
        units' actual places, which deployment sets; the army file's own `set:x/y` is only the fallback."""
        field_view = script["field"]
        units = [unit for army in (script["merc"] or {}).get("armies", []) for unit in army["units"]]
        placed = [unit_positions[unit["id"]] for unit in units
                  if unit_positions is not None and unit.get("id") in unit_positions]
        listed = [(unit["set"]["x"], unit["set"]["y"]) for unit in units if "x" in unit["set"] and "y" in unit["set"]]
        if placed or listed:
            x, y = (placed or listed)[0]
        else:
            x, y = field_view["width"] / 2, field_view["height"] / 2
        edges = tuple(boundary for boundary in boundaries_from_views(script.get("boundaries") or ())
                      if boundary.camera_edge)
        return cls(float(x), float(y), initial_yaw(field_view.get("camera")), camera_edges=edges,
                   terrain_height=terrain_height,
                   bounds=(0.0, 0.0, float(field_view["width"]), float(field_view["height"])))

    def set_target(self, x: float, y: float) -> None:
        """Move the ground look-at point, kept inside the camera area (its outline included)."""
        self.target_x, self.target_y = self._confine((x, y))
        self.update()

    def _confine(self, point: tuple[float, float]) -> tuple[float, float]:
        """Inside the CameraEdge areas and inside ``bounds``. The shipped CameraEdge outlines reach about 300 units
        beyond the battlefield (BF001: -300..1900 x -300..2060 around a 1600 x 1760 field), so the field rectangle
        is what keeps the look-at point on the map; the outline still trims it where it runs inside the field."""
        if self.camera_edges and not any(self._allows(edge, point) for edge in self.camera_edges):
            point = min((edge.nearest(point) for edge in self.camera_edges),
                        key=lambda candidate: math.dist(point, candidate))
        if self.bounds is not None:
            low_x, low_y, high_x, high_y = self.bounds
            point = min(max(point[0], low_x), high_x), min(max(point[1], low_y), high_y)
        return point

    @staticmethod
    def _allows(edge: Boundary, point: tuple[float, float]) -> bool:
        return edge.contains(point) or math.dist(point, edge.nearest(point)) < 1e-7

    def eye_xy(self) -> tuple[float, float]:
        """The rendered eye's ground position (BTS world units)."""
        horizontal = self.view_distance * WORLD_PER_MESH * math.cos(math.radians(self.view_pitch))
        yaw = math.radians(self.yaw)
        return self.target_x + horizontal * math.sin(yaw), self.target_y + horizontal * math.cos(yaw)

    def _terrain_blocks_view(self) -> bool:
        if self.terrain_height is None:
            return False
        eye_x, eye_y = self.eye_xy()
        target_height = self.terrain_height(self.target_x, self.target_y)
        rise = self.view_distance * math.sin(math.radians(self.view_pitch))
        horizontal = math.dist((self.target_x, self.target_y), (eye_x, eye_y))
        # Use world-unit spacing so a short ridge near the sightline does not
        # fall between coarse fixed trial points.
        steps = max(16, math.ceil(horizontal))
        for index in range(1, steps + 1):
            fraction = index / steps
            x = self.target_x + (eye_x - self.target_x) * fraction
            y = self.target_y + (eye_y - self.target_y) * fraction
            if self.terrain_height(x, y) > target_height + rise * fraction:
                return True
        return False

    def update(self) -> None:
        """Recompute the rendered view from the chosen pitch and distance: raise the pitch, then shorten the distance,
        only as far as needed to keep terrain off the sightline."""
        self.target_x, self.target_y = self._confine((self.target_x, self.target_y))
        self.view_pitch, self.view_distance = self.pitch, self.distance
        while self._terrain_blocks_view():
            if self.view_pitch < MAX_PITCH:
                self.view_pitch = min(MAX_PITCH, self.view_pitch + TERRAIN_PITCH_STEP)
            elif self.view_distance > 1.0:
                self.view_distance = max(1.0, self.view_distance * TERRAIN_DISTANCE_FACTOR)
            else:
                return

    def pan(self, right: float, forward: float) -> None:
        """Move the ground target by BTS world units along screen right and the horizontal look direction."""
        yaw = math.radians(self.yaw)
        # Screen right is (-cos yaw, sin yaw) and the horizontal look direction (-sin yaw, -cos yaw) in X/Y.
        self.set_target(self.target_x - math.cos(yaw) * right - math.sin(yaw) * forward,
                        self.target_y + math.sin(yaw) * right - math.cos(yaw) * forward)

    def rotate(self, degrees: float) -> None:
        self.yaw = (self.yaw + degrees) % 360
        self.update()

    def tilt(self, degrees: float) -> None:
        self.pitch = min(MAX_PITCH, max(MIN_PITCH, self.pitch + degrees))
        self.update()

    def zoom(self, factor: float) -> None:
        """Multiply the eye distance; factors below 1 move closer."""
        if factor <= 0:
            raise ValueError("zoom factor must be positive")
        self.distance = min(MAX_DISTANCE, max(MIN_DISTANCE, self.distance * factor))
        self.update()

    def projection(self, width: int, height: int, field_width: float, field_height: float,
                   target_height: float = 0.0, eye_lift: float = 0.0) -> Projection:
        """The verified viewer camera model for this state (mesh units, left-handed world). `eye_lift` is a
        presentation-only vertical eye offset applied after the terrain lift (notes/camera_shake.md 1)."""
        return Projection(width, height, field_width, field_height, self.yaw, self.view_pitch, 1.0,
                          self.target_x / WORLD_PER_MESH, self.target_y / WORLD_PER_MESH, "perspective",
                          self.view_distance, self.fov, target_height, eye_lift)
