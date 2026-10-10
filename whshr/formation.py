"""Block formation layout: model positions relative to the unit position.

Rank sizes and slot offsets follow notes/game_rules.md, "Formations". War machine, monster and wagon layouts are not modelled here.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

Point = tuple[float, float]
Block = tuple[float, float, float, int, int]  # (x, y, direction, models, ranks)
Frame = tuple[float, float, float, float, float, float]  # centre x/y, half side/forward, cos, sin

MODEL_SPACING = 12.0  # BTS world units between models, sideways and front to back
FULL_TURN = 512
# BTS world units covered by one troop sprite pixel. Not traced: measured on a BF001 game screenshot, where
# the model spacing is about 1.43 times the on-screen width of the 18-22 pixel idle frames.
SPRITE_PIXEL_WORLD_UNITS = 0.45


def rank_sizes(models: int, ranks: int) -> list[int]:
    """Return the model count of each rank, front first; leftover models widen the front ranks."""
    if models <= 0:
        return []
    ranks = max(1, min(models, ranks))
    base, leftover = divmod(models, ranks)
    return [base + (rank < leftover) for rank in range(ranks)]


def block_slots(models: int, ranks: int, spacing: float = MODEL_SPACING) -> list[Point]:
    """Return (side, forward) slot offsets: the front-rank centre is (0, 0) and later ranks stand behind it."""
    return [((column - (width - 1) / 2) * spacing, -rank * spacing)
            for rank, width in enumerate(rank_sizes(models, ranks)) for column in range(width)]


def place(x: float, y: float, direction: float | None, slots: Sequence[Point]) -> list[Point]:
    """Rotate slot offsets by a script facing (0 = +Y, clockwise, 512 per turn) around the unit position."""
    angle = (direction or 0) * math.tau / FULL_TURN
    cos, sin = math.cos(angle), math.sin(angle)
    return [(x + side * cos + forward * sin, y - side * sin + forward * cos) for side, forward in slots]


def footprint(models: int, ranks: int, spacing: float = MODEL_SPACING) -> tuple[float, float, float]:
    """Local block half-extents (side, forward) and the footprint centre's forward offset behind the unit
    position: a box of half-extents ``frontage x 6`` and ``ranks x 6``, centred ``(ranks - 1) x 6`` units
    behind the unit position (game_rules.md, "Formations").
    """
    sizes = rank_sizes(models, ranks)
    if not sizes:
        return 0.0, 0.0, 0.0
    half = spacing / 2
    return max(sizes) * half, len(sizes) * half, (len(sizes) - 1) * half


def bounding_radius(models: int, ranks: int, spacing: float = MODEL_SPACING) -> float:
    """A circle covering the whole footprint; used for regiment picking and simple collisions."""
    half_side, half_forward, _ = footprint(models, ranks, spacing)
    return math.hypot(half_side, half_forward)


def footprint_frame(x: float, y: float, direction: float | None, models: int, ranks: int,
                    spacing: float = MODEL_SPACING) -> Frame:
    """World-space centre and half-extents of the oriented block footprint (`footprint`), plus the
    frame's rotation cos/sin; shared by `footprint_corners`, `engine.Regiment._footprint` and
    `engine.Regiment.contains`."""
    half_side, half_forward, centre = footprint(models, ranks, spacing)
    angle = (direction or 0) * math.tau / FULL_TURN
    cos, sin = math.cos(angle), math.sin(angle)
    return x - centre * sin, y - centre * cos, half_side, half_forward, cos, sin


def footprint_corners(x: float, y: float, direction: float | None, models: int, ranks: int,
                      spacing: float = MODEL_SPACING) -> list[Point]:
    """The four world-space corners of the oriented block footprint, in order around the rectangle
    (for `footprint_gap`'s edge walk)."""
    cx, cy, half_side, half_forward, cos, sin = footprint_frame(x, y, direction, models, ranks, spacing)
    corners = [(cx + side * cos + forward * sin, cy - side * sin + forward * cos)
               for side in (-half_side, half_side) for forward in (-half_forward, half_forward)]
    corners[2], corners[3] = corners[3], corners[2]  # (-,-) (-,+) (+,-) (+,+) -> a simple quad loop
    return corners


def penetrates(a: Block, b: Block, spacing: float = MODEL_SPACING) -> bool:
    """True when two blocks are in contact (game_rules.md, "What triggers engagement").

    Each argument is a ``(x, y, direction, models, ranks)`` tuple. The point of this test, and the
    reason it replaced a proximity margin, is that the original needs the two footprints to **really
    overlap**: it has no "reach" constant and no facing requirement for engagement.

    Broad phase is the original's own: the bounding circles of the two *map objects* must overlap.
    For the narrow phase the original tests whether any of one block's four rotated corners lies
    strictly inside the other's box; that is exact for the barely-touching poses its per-tick
    rollback produces (contact is always the last pose before an overlap), but it misses deeper
    overlaps that no corner witnesses -- two equally wide blocks meeting head on put their corners
    exactly on each other's edge. This engine has no rollback yet, so blocks can reach those poses,
    and a full separating-axis test is used instead: it agrees with the corner test wherever the
    corner test is meaningful, and still answers "overlapping" where it is not.
    """
    a_frame = footprint_frame(*a, spacing)
    b_frame = footprint_frame(*b, spacing)
    distance = math.hypot(a_frame[0] - b_frame[0], a_frame[1] - b_frame[1])
    if int(distance) - bounding_radius(a[3], a[4], spacing) - bounding_radius(b[3], b[4], spacing) >= 0:
        return False  # broad phase: bounding circles do not overlap
    return _polygons_overlap(footprint_corners(*a, spacing), footprint_corners(*b, spacing))


def boxes_overlap(a: Block, b: Block, spacing: float = MODEL_SPACING) -> bool:
    """The narrow phase alone: whether the two blocks' oriented footprint boxes overlap (the same
    separating-axis test `penetrates` uses after its broad phase)."""
    return _polygons_overlap(footprint_corners(*a, spacing), footprint_corners(*b, spacing))


def turn_pivot_shift(direction: float | None, new_direction: float | None, models: int, ranks: int,
                     spacing: float = MODEL_SPACING) -> Point:
    """The offset a block's anchor must move by so that an in-place turn pivots about the **block
    centre**, not about the anchor (game_rules.md, "A turn always moves the unit position to keep the
    pivot still").

    The anchor sits ``(ranks - 1) x 6`` in front of the block centre along the facing, so keeping the
    centre fixed means putting the anchor back that far along the *new* facing. Without this a turning
    block swings its own footprint away and can lose contact with a unit it is touching, which the
    original never does.
    """
    _, _, offset = footprint(models, ranks, spacing)
    old = (direction or 0) * math.tau / FULL_TURN
    new = (new_direction or 0) * math.tau / FULL_TURN
    return (offset * (math.sin(new) - math.sin(old)), offset * (math.cos(new) - math.cos(old)))


def turn_corner_shift(direction: float, new_direction: float, frontage: int, turn_sign: int,
                      spacing: float = MODEL_SPACING) -> Point:
    """Move the anchor while a block turns gradually around its inner front corner.

    `turn_sign` is +1 for clockwise and -1 for counterclockwise. The corner is half a
    frontage from the front-rank centre (game_rules.md, "Turning, wheeling and reversing").
    """
    half_frontage = (frontage - 1) * spacing / 2
    old = direction * math.tau / FULL_TURN
    new = new_direction * math.tau / FULL_TURN
    return (turn_sign * half_frontage * (math.cos(old) - math.cos(new)),
            turn_sign * half_frontage * (math.sin(new) - math.sin(old)))


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _polygons_overlap(a: Sequence[Point], b: Sequence[Point]) -> bool:
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


def footprint_gap(a_corners: Sequence[Point], b_corners: Sequence[Point]) -> float:
    """Minimum world-unit distance between two oriented block footprints (0 once they overlap):
    the least corner-to-edge distance, checked both ways, which is exact for two convex polygons
    since the closest pair of features between disjoint convex polygons is always a vertex and an
    edge (game_rules.md, "Engagement": close combat requires the footprints to actually touch)."""
    if _polygons_overlap(a_corners, b_corners):
        return 0.0
    best = math.inf
    for corners, other in ((a_corners, b_corners), (b_corners, a_corners)):
        for px, py in corners:
            for i in range(len(other)):
                ax, ay = other[i]
                bx, by = other[(i + 1) % len(other)]
                distance = _point_segment_distance(px, py, ax, ay, bx, by)
                best = min(best, distance)
    return best


def rank_range(models: int) -> tuple[int, int]:
    """Allowed rank-count range for a re-form request (game_rules.md, "Formation changes: how the
    figures re-sort themselves"): clamped to ``[min, models // min]`` with
    ``min = max(1, trunc(0.75 * sqrt(models)))``. Matches the documented examples: 8 models -> 2-4
    ranks, 18 -> 3-6, 24 -> 3-8, 32 -> 4-8."""
    if models <= 0:
        return 1, 1
    minimum = max(1, math.trunc(0.75 * math.sqrt(models)))
    return minimum, max(minimum, models // minimum)


def clamp_ranks(models: int, ranks: int) -> int:
    """Clamp a requested rank count into `rank_range`'s allowed span."""
    minimum, maximum = rank_range(models)
    return max(minimum, min(maximum, ranks))


def reform_slot_order(models: int, ranks: int, spacing: float = MODEL_SPACING) -> list[Point]:
    """Slot offsets in re-slotting search order: front rank first, each rank's columns centre
    outward (game_rules.md, "Formation changes"). Same offsets as `block_slots`, reordered."""
    order: list[Point] = []
    for rank, width in enumerate(rank_sizes(models, ranks)):
        centre = (width - 1) / 2
        columns = sorted(range(width), key=lambda column: abs(column - centre))
        order.extend(((column - centre) * spacing, -rank * spacing) for column in columns)
    return order


def _octagonal_distance(ax: float, ay: float, bx: float, by: float) -> float:
    """The re-slotting search's distance metric: `larger + smaller / 2` of the two axis deltas
    (game_rules.md, "Formation changes"), not true Euclidean distance."""
    dx, dy = abs(ax - bx), abs(ay - by)
    larger, smaller = (dx, dy) if dx >= dy else (dy, dx)
    return larger + smaller / 2


def reform_assignment(x: float, y: float, direction: float | None, models: int, ranks: int,
                      positions: Sequence[Point], leader_index: int | None = None,
                      spacing: float = MODEL_SPACING, farthest: bool = False) -> list[Point | None]:
    """Re-slot every model of a re-forming unit (game_rules.md, "Formation changes"): process the new
    shape's slots front rank first, centre outward; each slot after the first takes the not-yet-placed
    model nearest to it by `_octagonal_distance`, scanning every remaining model and stopping early on
    an exact match. The front-rank centre (the first slot) is handed to `leader_index` directly, with
    no search, if it names a still-unplaced model; otherwise (no persistent leader identity to hand
    it to) it falls back to the model that is itself nearest that slot, which is the documented
    fallback for a codebase without a leader-model concept.

    With `farthest=True` (war machine crews) every slot after the first instead takes the
    not-yet-placed model *farthest* from it; the first slot (the machine) is unchanged.

    Returns a list of local `(side, forward)` slot offsets index-parallel with `positions`, meant to be
    turned into world targets each tick with `place(x, y, direction, ...)` so they track a moving or
    turning anchor for as long as the re-form is in progress.
    """
    slot_offsets = reform_slot_order(models, ranks, spacing)
    slot_targets = place(x, y, direction, slot_offsets)
    assigned: list[Point | None] = [None] * len(positions)
    remaining = list(range(len(positions)))

    def _take_nearest(target: Point, far: bool = False) -> int:
        best_index: int | None = None
        best_distance: float | None = None
        for index in remaining:
            px, py = positions[index]
            distance = _octagonal_distance(px, py, target[0], target[1])
            if best_distance is None or (distance > best_distance if far else distance < best_distance):
                best_index, best_distance = index, distance
                if distance == 0 and not far:
                    break
        if best_index is None:
            raise ValueError("no unplaced model left to take")
        remaining.remove(best_index)
        return best_index

    if slot_offsets and remaining:
        if leader_index is not None and leader_index in remaining:
            leader = leader_index
            remaining.remove(leader)
        else:
            leader = _take_nearest(slot_targets[0])
        assigned[leader] = slot_offsets[0]
        slot_offsets, slot_targets = slot_offsets[1:], slot_targets[1:]

    for offset, target in zip(slot_offsets, slot_targets):
        if not remaining:
            break
        assigned[_take_nearest(target, farthest)] = offset

    return assigned


def unit_size(unit: Mapping[str, Any]) -> tuple[int, int]:
    """Return a script unit's (models, ranks); s_side is [side, orgsize, size, ranks] and the current size counts."""
    stats = unit["stats"].get("s_side", [])
    models = int(stats[2] if len(stats) > 2 else stats[1] if len(stats) > 1 else 1)
    ranks = int(stats[3]) if len(stats) > 3 and stats[3] else 1
    return models, ranks


def unit_layout(unit: Mapping[str, Any], spacing: float = MODEL_SPACING) -> tuple[list[Point], int, int]:
    """Return a script unit's model positions in BTS world units, its model count and its rank count."""
    position = unit["set"]
    models, ranks = unit_size(unit)
    slots = block_slots(models, ranks, spacing)
    return (place(position["x"], position["y"], position.get("dir"), slots), models,
            len(rank_sizes(models, ranks)))
