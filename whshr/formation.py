"""Block formation layout traced in GAMEF.DLL: model positions relative to the unit position.

Rank sizes follow `ComputeFormationSize` (FUN_1002c9e0) and slot offsets the block layout (FUN_1002cf50);
see notes/game_rules.md, "Formations". War machine, monster and wagon layouts are not modelled here.
"""

import math

MODEL_SPACING = 12.0  # BTS world units between models, sideways and front to back
FULL_TURN = 512
# BTS world units covered by one troop sprite pixel. Not traced: measured on a BF001 game screenshot, where
# the model spacing is about 1.43 times the on-screen width of the 18-22 pixel idle frames.
SPRITE_PIXEL_WORLD_UNITS = 0.45


def rank_sizes(models, ranks):
    """Return the model count of each rank, front first; leftover models widen the front ranks."""
    if models <= 0:
        return []
    ranks = max(1, min(models, ranks))
    base, leftover = divmod(models, ranks)
    return [base + (rank < leftover) for rank in range(ranks)]


def block_slots(models, ranks, spacing=MODEL_SPACING):
    """Return (side, forward) slot offsets: the front-rank centre is (0, 0) and later ranks stand behind it."""
    return [((column - (width - 1) / 2) * spacing, -rank * spacing)
            for rank, width in enumerate(rank_sizes(models, ranks)) for column in range(width)]


def place(x, y, direction, slots):
    """Rotate slot offsets by a script facing (0 = +Y, clockwise, 512 per turn) around the unit position."""
    angle = (direction or 0) * math.tau / FULL_TURN
    cos, sin = math.cos(angle), math.sin(angle)
    return [(x + side * cos + forward * sin, y - side * sin + forward * cos) for side, forward in slots]


def footprint(models, ranks, spacing=MODEL_SPACING):
    """Local block half-extents (side, forward) and the footprint centre's forward offset behind the unit
    position: a box of half-extents ``frontage x 6`` and ``ranks x 6``, centred ``(ranks - 1) x 6`` units
    behind the unit position (game_rules.md, "Formations" / `FUN_1002c750`, `FUN_1002c510`).
    """
    sizes = rank_sizes(models, ranks)
    if not sizes:
        return 0.0, 0.0, 0.0
    half = spacing / 2
    return max(sizes) * half, len(sizes) * half, (len(sizes) - 1) * half


def bounding_radius(models, ranks, spacing=MODEL_SPACING):
    """A circle covering the whole footprint; used for regiment picking and simple collisions."""
    half_side, half_forward, _ = footprint(models, ranks, spacing)
    return math.hypot(half_side, half_forward)


def footprint_frame(x, y, direction, models, ranks, spacing=MODEL_SPACING):
    """World-space centre and half-extents of the oriented block footprint (`footprint`), plus the
    frame's rotation cos/sin; shared by `footprint_corners`, `engine.Regiment._footprint` and
    `engine.Regiment.contains`."""
    half_side, half_forward, centre = footprint(models, ranks, spacing)
    angle = (direction or 0) * math.tau / FULL_TURN
    cos, sin = math.cos(angle), math.sin(angle)
    return x - centre * sin, y - centre * cos, half_side, half_forward, cos, sin


def footprint_corners(x, y, direction, models, ranks, spacing=MODEL_SPACING):
    """The four world-space corners of the oriented block footprint, in order around the rectangle
    (for `footprint_gap`'s edge walk)."""
    cx, cy, half_side, half_forward, cos, sin = footprint_frame(x, y, direction, models, ranks, spacing)
    corners = [(cx + side * cos + forward * sin, cy - side * sin + forward * cos)
               for side in (-half_side, half_side) for forward in (-half_forward, half_forward)]
    corners[2], corners[3] = corners[3], corners[2]  # (-,-) (-,+) (+,-) (+,+) -> a simple quad loop
    return corners


def _point_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _polygons_overlap(a, b):
    """SAT overlap test for two convex polygons (a separating axis exists along some edge's normal)."""
    for poly in (a, b):
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            nx, ny = y2 - y1, x1 - x2
            a_proj = [px * nx + py * ny for px, py in a]
            b_proj = [px * nx + py * ny for px, py in b]
            if max(a_proj) < min(b_proj) or max(b_proj) < min(a_proj):
                return False
    return True


def footprint_gap(a_corners, b_corners):
    """Minimum world-unit distance between two oriented block footprints (0 once they overlap):
    the least corner-to-edge distance, checked both ways, which is exact for two convex polygons
    since the closest pair of features between disjoint convex polygons is always a vertex and an
    edge (game_rules.md, "Engagement": close combat requires the footprints to actually touch)."""
    if _polygons_overlap(a_corners, b_corners):
        return 0.0
    best = None
    for corners, other in ((a_corners, b_corners), (b_corners, a_corners)):
        for px, py in corners:
            for i in range(len(other)):
                ax, ay = other[i]
                bx, by = other[(i + 1) % len(other)]
                distance = _point_segment_distance(px, py, ax, ay, bx, by)
                if best is None or distance < best:
                    best = distance
    return best


def unit_size(unit):
    """Return a script unit's (models, ranks); s_side is [side, orgsize, size, ranks] and the current size counts."""
    stats = unit["stats"].get("s_side", [])
    models = int(stats[2] if len(stats) > 2 else stats[1] if len(stats) > 1 else 1)
    ranks = int(stats[3]) if len(stats) > 3 and stats[3] else 1
    return models, ranks


def unit_layout(unit, spacing=MODEL_SPACING):
    """Return a script unit's model positions in BTS world units, its model count and its rank count."""
    position = unit["set"]
    models, ranks = unit_size(unit)
    slots = block_slots(models, ranks, spacing)
    return (place(position["x"], position["y"], position.get("dir"), slots), models,
            len(rank_sizes(models, ranks)))
