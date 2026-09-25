# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle camera state and controls, independent of any renderer (BTS world units and degrees)."""

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from .battle3d import DEFAULT_DISTANCE, DEFAULT_FOV, DEFAULT_PITCH, Projection
from .battlefield import WORLD_PER_MESH

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

    @classmethod
    def for_battle(cls, script: Mapping[str, Any]) -> "BattleCamera":
        """Look at the player's starting units along the battle's initial heading."""
        field = script["field"]
        player = [unit["set"] for army in (script["merc"] or {}).get("armies", []) for unit in army["units"]
                  if "x" in unit["set"] and "y" in unit["set"]]
        if player:
            x = sum(position["x"] for position in player) / len(player)
            y = sum(position["y"] for position in player) / len(player)
        else:
            x, y = field["width"] / 2, field["height"] / 2
        return cls(float(x), float(y), initial_yaw(field.get("camera")))

    def pan(self, right: float, forward: float) -> None:
        """Move the ground target by BTS world units along screen right and the horizontal look direction."""
        yaw = math.radians(self.yaw)
        # Screen right is (-cos yaw, sin yaw) and the horizontal look direction (-sin yaw, -cos yaw) in X/Y.
        self.target_x += -math.cos(yaw) * right - math.sin(yaw) * forward
        self.target_y += math.sin(yaw) * right - math.cos(yaw) * forward

    def rotate(self, degrees: float) -> None:
        self.yaw = (self.yaw + degrees) % 360

    def tilt(self, degrees: float) -> None:
        self.pitch = min(MAX_PITCH, max(MIN_PITCH, self.pitch + degrees))

    def zoom(self, factor: float) -> None:
        """Multiply the eye distance; factors below 1 move closer."""
        if factor <= 0:
            raise ValueError("zoom factor must be positive")
        self.distance = min(MAX_DISTANCE, max(MIN_DISTANCE, self.distance * factor))

    def projection(self, width: int, height: int, field_width: float, field_height: float,
                   target_height: float = 0.0) -> Projection:
        """The verified viewer camera model for this state (mesh units, left-handed world)."""
        return Projection(width, height, field_width, field_height, self.yaw, self.pitch, 1.0,
                          self.target_x / WORLD_PER_MESH, self.target_y / WORLD_PER_MESH, "perspective",
                          self.distance, self.fov, target_height)
