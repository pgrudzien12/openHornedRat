"""Deployment geometry and transient drag data, from notes/deployment.md §§2–3."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

Point = tuple[float, float]
Segment = tuple[float, float, float, float]


@dataclass(frozen=True)
class Region:
    lines: tuple[Segment, ...]
    inverted: bool = False

    def contains(self, point: Point) -> bool:
        """Polygon membership; exact on-edge parity remains a research confirmation."""
        x, y = point
        inside = False
        for x1, y1, x2, y2 in self.lines:
            # Include the edge for predictable clipping; not a claim of original edge parity.
            cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
            if abs(cross) < 1e-9 and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
                return True
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return not inside if self.inverted else inside

    def clip(self, point: Point) -> Point:
        if self.contains(point):
            return point
        x, y = point
        closest = point
        best = math.inf
        for x1, y1, x2, y2 in self.lines:
            dx, dy = x2 - x1, y2 - y1
            length2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2)) if length2 else 0.0
            projected = (x1 + t * dx, y1 + t * dy)
            distance2 = (x - projected[0]) ** 2 + (y - projected[1]) ** 2
            if distance2 < best:
                best, closest = distance2, projected
        return float(math.trunc(closest[0])), float(math.trunc(closest[1]))


def regions(boundaries: Iterable[Mapping[str, Any]]) -> list[Region]:
    result: list[Region] = []
    for boundary in boundaries:
        flags = {str(flag).casefold() for flag in boundary.get("status") or ()}
        if not {"bnd_active", "bnd_deployment"}.issubset(flags):
            continue
        raw_lines: Sequence[Sequence[float]] = boundary.get("lines") or ()
        lines = tuple((float(line[0]), float(line[1]), float(line[2]), float(line[3]))
                      for line in raw_lines if len(line) == 4)
        if lines:
            result.append(Region(lines, "bnd_invsolid" in flags))
    return result


# Engine design choice (deliberately not the original's spacing): world units between flags along a zone edge.
FLAG_SPACING = 96.0


def flag_positions(zones: Iterable[Region], spacing: float = FLAG_SPACING) -> list[Point]:
    """Flag poles marking the perimeter of the deployment zones: one at the start of every edge, then every
    `spacing` world units along it (the end of an edge is the start of the next, so corners get a pole)."""
    result: list[Point] = []
    for zone in zones:
        for x1, y1, x2, y2 in zone.lines:
            length = math.hypot(x2 - x1, y2 - y1)
            count = max(1, math.ceil(length / spacing))
            result.extend((x1 + (x2 - x1) * i / count, y1 + (y2 - y1) * i / count) for i in range(count))
    return result


@dataclass
class Drag:
    regiment_id: str
    offset: Point
    target: Point
    rotate: bool = False
