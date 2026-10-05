"""Spotting geometry from the public rules' Routes, collisions and visibility section."""

from collections.abc import Sequence
import math

from .deployment import Point, Segment
from .script import View


def crosses(first: Segment, second: Segment) -> bool:
    ax, ay, bx, by = first
    cx, cy, dx, dy = second
    divisor = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
    if abs(divisor) < 1e-9:
        return False
    t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / divisor
    u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / divisor
    return 0 <= t <= 1 and 0 <= u <= 1


def clear_ray(start: Point, end: Point, boundaries: Sequence[View], objects: Sequence[View]) -> bool:
    ray = (*start, *end)
    for boundary in boundaries:
        flags = {str(flag).casefold() for flag in boundary.get("status") or ()}
        if "bnd_active" in flags and ("bnd_sight" in flags or "bnd_sightedge" in flags):
            lines: Sequence[Sequence[float]] = boundary.get("lines") or ()
            if any(crosses(ray, (line[0], line[1], line[2], line[3])) for line in lines if len(line) == 4):
                return False
    sx, sy = start
    ex, ey = end
    length2 = (ex - sx) ** 2 + (ey - sy) ** 2
    if length2 == 0:
        return True
    for obj in objects:
        flags = {str(flag).casefold() for flag in obj.get("status") or ()}
        if not {"os_active", "os_solid"}.issubset(flags):
            continue
        x, y = float(obj.get("x") or 0), float(obj.get("y") or 0)
        rects: Sequence[Sequence[float]] = obj.get("rects") or ()
        if rects:
            angle = float(obj.get("dir") or 0) * math.tau / 512
            cos, sin = math.cos(angle), math.sin(angle)
            local_start = ((sx - x) * cos - (sy - y) * sin, (sx - x) * sin + (sy - y) * cos)
            local_end = ((ex - x) * cos - (ey - y) * sin, (ex - x) * sin + (ey - y) * cos)
            for rect in rects:
                if len(rect) != 4:
                    continue
                x1, y1, x2, y2 = rect
                if any(x1 <= px <= x2 and y1 <= py <= y2 for px, py in (local_start, local_end)):
                    return False
                edges = ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1))
                if any(crosses((*local_start, *local_end), edge) for edge in edges):
                    return False
        else:
            radius = float(obj.get("radius") or 0)
            t = max(0.0, min(1.0, ((x - sx) * (ex - sx) + (y - sy) * (ey - sy)) / length2))
            if (sx + t * (ex - sx) - x) ** 2 + (sy + t * (ey - sy) - y) ** 2 < radius * radius:
                return False
    return True


def visible(start: Point, facing: float, target: Point, radius: float, half_cone: float,
            boundaries: Sequence[View], objects: Sequence[View]) -> bool:
    dx, dy = target[0] - start[0], target[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance < 1e-9:
        return True
    heading = math.atan2(dx, dy) * 512 / math.tau
    if abs((heading - facing + 256) % 512 - 256) > half_cone:
        return False
    side_x, side_y = dy * radius / distance, -dx * radius / distance
    return any(clear_ray(start, (target[0] + side_x * side, target[1] + side_y * side), boundaries, objects)
               for side in (0, -1, 1))
