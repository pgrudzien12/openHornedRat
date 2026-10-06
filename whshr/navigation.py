"""Movement regions and authored route guides (public movement boundary report)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

Point = tuple[float, float]
Segment = tuple[float, float, float, float]


@dataclass(frozen=True)
class Boundary:
    lines: tuple[Segment, ...]
    solid: bool = False
    inverse: bool = False
    battle_edge: bool = False
    guide: bool = False

    def contains(self, point: Point) -> bool:
        # Rightward ray parity. The endpoint Y convention is half-open: testing
        # just below a vertex includes the top and excludes the bottom of a box.
        x, y = point
        y = math.nextafter(y, -math.inf)
        inside = False
        for x1, y1, x2, y2 in self.lines:
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside

    def forbidden(self, point: Point) -> bool:
        return self.contains(point) if self.inverse else not self.contains(point)

    def nearest(self, point: Point) -> Point:
        px, py = point
        best = point
        distance = math.inf
        for x1, y1, x2, y2 in self.lines:
            dx, dy = x2 - x1, y2 - y1
            length2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length2)) if length2 else 0.0
            candidate = x1 + t * dx, y1 + t * dy
            d2 = (candidate[0] - px) ** 2 + (candidate[1] - py) ** 2
            if d2 < distance:
                best, distance = candidate, d2
        return best


def boundaries_from_views(views: Sequence[Mapping[str, Any]]) -> list[Boundary]:
    result = []
    for view in views:
        flags = {str(flag).casefold() for flag in view.get("status") or ()}
        if "bnd_active" not in flags:
            continue
        lines = tuple(tuple(float(v) for v in line) for line in view.get("lines") or () if len(line) == 4)
        if not lines:
            continue
        result.append(Boundary(lines, "bnd_solid" in flags, "bnd_invsolid" in flags,
                               "bnd_battleedge" in flags, "bnd_line" in flags))
    return result


def crossing(first: Point, last: Point, segment: Segment) -> tuple[float, Point] | None:
    ax, ay = first
    bx, by = last
    cx, cy, dx, dy = segment
    ux, uy = bx - ax, by - ay
    vx, vy = dx - cx, dy - cy
    det = ux * vy - uy * vx
    if abs(det) < 1e-12:
        return None
    wx, wy = cx - ax, cy - ay
    t = (wx * vy - wy * vx) / det
    s = (wx * uy - wy * ux) / det
    if 0 <= t <= 1 and 0 <= s <= 1:
        return t, (ax + t * ux, ay + t * uy)
    return None


def first_crossing(first: Point, last: Point, regions: Sequence[Boundary]) -> tuple[Boundary, Point] | None:
    best: tuple[Boundary, Point] | None = None
    best_t = math.inf
    for region in regions:
        if not (region.solid or region.inverse or region.battle_edge):
            continue
        for line in region.lines:
            hit = crossing(first, last, line)
            if hit is not None and 1e-8 < hit[0] < best_t:
                best_t, best = hit[0], (region, hit[1])
    return best


def point_route(start: Point, goal: Point, boundaries: Sequence[Boundary]) -> list[Point]:
    """Use an authored line guide when a direct point route crosses a movement region.

    This deliberately searches only supplied guides, not an inferred navigation mesh.
    If none is usable, keep the requested point. Per-tick boundary correction
    can then slide the regiment along the obstruction or hold it there.
    """
    if first_crossing(start, goal, boundaries) is None:
        return [goal]
    best_route: list[Point] | None = None
    best_length = math.inf
    for guide in boundaries:
        if not guide.guide:
            continue
        vertices = [guide.lines[0][:2], *[(line[2], line[3]) for line in guide.lines]]
        if any(a[2:] != b[:2] for a, b in zip(guide.lines, guide.lines[1:])):
            continue
        start_attachment, start_index = _nearest_on_guide(start, guide.lines)
        goal_attachment, goal_index = _nearest_on_guide(goal, guide.lines)
        if start_index < goal_index:
            route = [start_attachment, *vertices[start_index + 1:goal_index + 1], goal_attachment]
        elif start_index > goal_index:
            route = [start_attachment, *reversed(vertices[goal_index + 1:start_index + 1]), goal_attachment]
        else:
            route = [start_attachment, goal_attachment]
        route = [point for index, point in enumerate(route) if index == 0 or point != route[index - 1]]
        if (first_crossing(start, route[0], boundaries) is not None
                or first_crossing(route[-1], goal, boundaries) is not None
                or any(first_crossing(a, b, boundaries) is not None for a, b in zip(route, route[1:]))):
            continue
        candidate = [*route, goal]
        length = sum(math.dist(a, b) for a, b in zip([start, *candidate], candidate))
        if length < best_length:  # exact tie preserves the first guide in file order
            best_route, best_length = candidate, length
    if best_route is not None:
        return best_route
    return [goal]


def _nearest_on_guide(point: Point, lines: Sequence[Segment]) -> tuple[Point, int]:
    px, py = point
    nearest = point
    best_distance = math.inf
    best_index = 0
    for index, (x1, y1, x2, y2) in enumerate(lines):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length2)) if length2 else 0.0
        candidate = x1 + t * dx, y1 + t * dy
        distance = (candidate[0] - px) ** 2 + (candidate[1] - py) ** 2
        if distance < best_distance:
            nearest, best_distance, best_index = candidate, distance, index
    return nearest, best_index
