# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle camera state and controls, independent of any renderer (BTS world units and degrees)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from typing import Any

from .battle3d import DEFAULT_DISTANCE, DEFAULT_FOV, DEFAULT_PITCH, Projection
from .battlefield import WORLD_PER_MESH
from .navigation import Boundary, boundaries_from_views

MIN_DISTANCE, MAX_DISTANCE = 20.0, 600.0  # mesh units, as in viewer-web
MIN_PITCH, MAX_PITCH = 5.0, 85.0
NORTH_YAW = 180.0


def initial_yaw(field_camera: float | None) -> float:
    """Working hypothesis: [FIELD] Camera is the view heading clockwise from north (notes/battle_viewer.md)."""
    return (NORTH_YAW + field_camera) % 360 if field_camera is not None else NORTH_YAW


@dataclass
class BattleCamera:
    """A perspective look-at camera around a ground target; ``yaw`` 180 looks north with +X to the right."""

    target_x: float
    target_y: float
    yaw: float = NORTH_YAW
    pitch: float = DEFAULT_PITCH
    distance: float = DEFAULT_DISTANCE
    fov: float = DEFAULT_FOV
    camera_edges: tuple[Boundary, ...] = ()
    terrain_height: Callable[[float, float], float] | None = None

    @classmethod
    def for_battle(cls, script: Mapping[str, Any],
                   terrain_height: Callable[[float, float], float] | None = None) -> "BattleCamera":
        """Look at the player's starting units along the battle's initial heading."""
        field = script["field"]
        player = [unit["set"] for army in (script["merc"] or {}).get("armies", []) for unit in army["units"]
                  if "x" in unit["set"] and "y" in unit["set"]]
        if player:
            x = sum(position["x"] for position in player) / len(player)
            y = sum(position["y"] for position in player) / len(player)
        else:
            x, y = field["width"] / 2, field["height"] / 2
        edges = tuple(boundary for boundary in boundaries_from_views(script.get("boundaries") or ())
                      if boundary.camera_edge)
        camera = cls(float(x), float(y), initial_yaw(field.get("camera")),
                     camera_edges=edges, terrain_height=terrain_height)
        camera.set_target(float(x), float(y))
        return camera

    def set_target(self, x: float, y: float) -> None:
        """Keep the ground look-at point in a camera area, including its outline.

        This is an engine choice: the public report identifies CameraEdge's role
        but does not measure the original camera's exact limiting behavior.
        """
        point = x, y
        if self.camera_edges and not any(self._allows(edge, point) for edge in self.camera_edges):
            point = min((edge.nearest(point) for edge in self.camera_edges),
                        key=lambda candidate: math.dist(point, candidate))
        self.target_x, self.target_y = point
        self._constrain_view()

    @staticmethod
    def _allows(edge: Boundary, point: tuple[float, float]) -> bool:
        return edge.contains(point) or math.dist(point, edge.nearest(point)) < 1e-7

    def _eye_xy(self) -> tuple[float, float]:
        horizontal = self.distance * WORLD_PER_MESH * math.cos(math.radians(self.pitch))
        yaw = math.radians(self.yaw)
        return self.target_x + horizontal * math.sin(yaw), self.target_y + horizontal * math.cos(yaw)

    def _terrain_blocks_view(self) -> bool:
        if self.terrain_height is None:
            return False
        eye_x, eye_y = self._eye_xy()
        target_height = self.terrain_height(self.target_x, self.target_y)
        rise = self.distance * math.sin(math.radians(self.pitch))
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

    def _constrain_view(self) -> None:
        """Keep the eye in the camera area and above sampled terrain on its sightline."""
        for _ in range(32):
            if self.camera_edges:
                target = self.target_x, self.target_y
                area = next((edge for edge in self.camera_edges if self._allows(edge, target)), None)
                if area is None:
                    area = min(self.camera_edges,
                               key=lambda edge: math.dist(target, edge.nearest(target)))
                    target = area.nearest(target)
                    self.target_x, self.target_y = target
                eye = self._eye_xy()
                if not self._allows(area, eye):
                    if self.pitch < MAX_PITCH:
                        self.pitch = min(MAX_PITCH, self.pitch + 5)
                        continue
                    if self.distance > MIN_DISTANCE:
                        self.distance = max(MIN_DISTANCE, self.distance * 0.8)
                        continue
                    nearest = area.nearest(eye)
                    self.target_x += nearest[0] - eye[0]
                    self.target_y += nearest[1] - eye[1]
                    if not self._allows(area, (self.target_x, self.target_y)):
                        self.distance = max(1.0, self.distance / 2)
                    continue
            if self._terrain_blocks_view():
                if self.pitch < MAX_PITCH:
                    self.pitch = min(MAX_PITCH, self.pitch + 5)
                else:
                    self.distance = max(1.0, self.distance * 0.8)
                continue
            return

    def pan(self, right: float, forward: float) -> None:
        """Move the ground target by BTS world units along screen right and the horizontal look direction."""
        yaw = math.radians(self.yaw)
        # Screen right is (-cos yaw, sin yaw) and the horizontal look direction (-sin yaw, -cos yaw) in X/Y.
        self.set_target(self.target_x - math.cos(yaw) * right - math.sin(yaw) * forward,
                        self.target_y + math.sin(yaw) * right - math.cos(yaw) * forward)

    def rotate(self, degrees: float) -> None:
        self.yaw = (self.yaw + degrees) % 360
        self._constrain_view()

    def tilt(self, degrees: float) -> None:
        self.pitch = min(MAX_PITCH, max(MIN_PITCH, self.pitch + degrees))
        self._constrain_view()

    def zoom(self, factor: float) -> None:
        """Multiply the eye distance; factors below 1 move closer."""
        if factor <= 0:
            raise ValueError("zoom factor must be positive")
        self.distance = min(MAX_DISTANCE, max(MIN_DISTANCE, self.distance * factor))
        self._constrain_view()

    def projection(self, width: int, height: int, field_width: float, field_height: float,
                   target_height: float = 0.0) -> Projection:
        """The verified viewer camera model for this state (mesh units, left-handed world)."""
        return Projection(width, height, field_width, field_height, self.yaw, self.pitch, 1.0,
                          self.target_x / WORLD_PER_MESH, self.target_y / WORLD_PER_MESH, "perspective",
                          self.distance, self.fov, target_height)
