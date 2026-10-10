"""Which map objects each consumer tests: projectiles, sight, movement push-apart and route steering.

Public rules: notes/map_objects_and_projectiles.md. Map objects are the battle file's `[OBJECTS]` collision circles,
the spell area objects mirrored into the battle's object lists, and (for projectiles and missile targeting only) the
building-type furniture. Other placed furniture (roads, trees, fences, rocks) is drawn and nothing else (section 1).
"""

import math
from collections.abc import Mapping
from typing import Any

DEFAULT_HEIGHT = 80.0  # section 1.2: an `addobject` without `z`


def _flags(obj: Mapping[str, Any]) -> set[str]:
    return {str(flag).casefold() for flag in obj.get("status") or ()}


def height(obj: Mapping[str, Any]) -> float:
    """The object's height: an explicit engine height (area objects, buildings), else its `z`, else 80 (1.2)."""
    for key in ("height", "z"):
        value = obj.get(key)
        if value is not None:
            return float(value)
    return DEFAULT_HEIGHT


def exists(obj: Mapping[str, Any]) -> bool:
    """Active and not camera-only: every consumer's first condition (section 2)."""
    flags = _flags(obj)
    return "os_active" in flags and "os_camcollide" not in flags


def stops_projectile(obj: Mapping[str, Any], x: float, y: float, projectile_height: float) -> bool:
    """A projectile in flight at (x, y), `projectile_height` above the ground, is stopped (section 2): the object
    exists (being solid is not required), the point is strictly inside its circle and the height is at most its own."""
    if not exists(obj):
        return False
    distance = math.hypot(float(obj.get("x") or 0) - x, float(obj.get("y") or 0) - y)
    return distance < float(obj.get("radius") or 0) and projectile_height <= height(obj)


def blocks_sight(obj: Mapping[str, Any]) -> bool:
    """A sight line can be blocked by the object: it exists and its height is not 0 (section 2)."""
    return exists(obj) and height(obj) != 0


def pushes_units(obj: Mapping[str, Any]) -> bool:
    """Movement push-apart: the object exists and is solid (section 2)."""
    return exists(obj) and "os_solid" in _flags(obj)


def steers_routes(obj: Mapping[str, Any]) -> bool:
    """Route steering: any existing object (section 2)."""
    return exists(obj)
