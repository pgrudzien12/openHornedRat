"""Obstacle scan, steering response and two-trial route plan for moving regiments.

Pure geometry, no engine imports.  Implements ``notes/obstacle_steering.md``
sections 3 (scan), 4 (steering response) and 5 (route plan).  Angles are in
1/512 of a turn, 0 = +Y, clockwise (128 = +X).

PROVISIONAL choices (the note leaves these open):
- the running turn total of section 4 adds the plain, unwrapped |previous H - new H|,
  starting from the facing (the note marks the first baseline open);
- a hard cap of 64 rescans per steering call is treated like the full-circle
  give-up (safety net, not from the note);
- the give-up turn-back heading of a trial is applied by ``plan``;
- a give-up ``Steer`` returned to a live caller carries the straight heading to
  the waypoint, the reference point as its point and the last stored distance;
- inside a trial the chosen side is forced for every steering response of that
  trial, not only the first;
- trial give-up point: reference point + 2 * stored distance along facing + 256,
  halved by the table rule (i.e. the stored distance is used as D/2);
- the trial turn cost is the wrapped smallest angle between H and the facing (0..256);
- a trial that ends at the 5,999 limit keeps its score and adds the waypoint
  distance like any other; the loop is also capped at 1000 steps.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Point = tuple[float, float]

_TURN = 512
_HALF = 256
_LOOK_AHEAD = 256.0
_TRIAL_LIMIT = 5999
_FORBIDDEN = 12000.0
_MAX_STEERS = 64
_MAX_TRIAL_STEPS = 1000

_SIN: tuple[int, ...] = tuple(int(256 * math.sin(2 * math.pi * a / _TURN)) for a in range(_TURN))
_COS: tuple[int, ...] = tuple(int(256 * math.cos(2 * math.pi * a / _TURN)) for a in range(_TURN))


@dataclass(frozen=True)
class Footprint:
    key: str
    x: float
    y: float
    radius: float
    troops: bool = False


@dataclass(frozen=True)
class Hit:
    footprint: Footprint
    bearing: int
    half_width: int
    distance: float
    combined_radius: float


@dataclass(frozen=True)
class Steer:
    heading: int
    point: Point
    distance: int
    side: int
    gave_up: bool


@dataclass(frozen=True)
class Plan:
    ok: bool
    side: int
    scores: tuple[float, float]


def bearing(start: Point, end: Point) -> int:
    """Bearing from ``start`` to ``end`` in 1/512 turns (note section 8 formula)."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return int(256 - 256 * math.atan2(dx, -dy) / math.pi) % _TURN


def _diff(a: int, b: int) -> int:
    """Smaller absolute angular difference."""
    d = (a - b) % _TURN
    return min(d, _TURN - d)


def _point_along(ref: Point, heading: int, full_length: float) -> Point:
    """Reference point plus ``full_length / 2`` along ``heading`` (table rule, section 4)."""
    h = heading % _TURN
    return (ref[0] + _SIN[h] * full_length / 512, ref[1] + _COS[h] * full_length / 512)


def scan(
    ref: Point,
    waypoint: Point,
    footprints: Sequence[Footprint],
    own_radius: float,
    blocks: Callable[[Footprint], bool],
    steer_heading: int | None = None,
    steer_distance: float | None = None,
) -> Hit | None:
    """Return the first blocking footprint in sequence order (section 3), or None."""
    steering = steer_heading is not None
    wp_dist = math.hypot(waypoint[0] - ref[0], waypoint[1] - ref[1])
    ref_heading = steer_heading if steer_heading is not None else bearing(ref, waypoint)
    for fp in footprints:
        centre = (fp.x, fp.y)
        # 2. destination footprint
        to_wp = math.hypot(fp.x - waypoint[0], fp.y - waypoint[1])
        if to_wp <= fp.radius and not fp.troops:
            continue
        # 3. look-ahead
        d = math.hypot(fp.x - ref[0], fp.y - ref[1])
        if d >= _LOOK_AHEAD:
            continue
        # 4. corridor
        combined = fp.radius + own_radius
        d_eff = max(d, combined)
        if steering and steer_distance is not None:
            reach = steer_distance
        else:
            reach = wp_dist - int(to_wp)
        if reach <= d_eff - combined:
            continue
        # 5. cone
        ratio = min(1.0, combined / d_eff) if d_eff > 0 else 1.0
        half = int(math.asin(ratio) * 256 / math.pi)
        b = bearing(ref, centre)
        if not _diff(ref_heading, b) < half:
            continue
        # 6. relationship filter
        if not blocks(fp):
            continue
        return Hit(fp, b, half, d_eff, combined)
    return None


def steer(
    ref: Point,
    waypoint: Point,
    footprints: Sequence[Footprint],
    own_radius: float,
    blocks: Callable[[Footprint], bool],
    remembered_side: int = 0,
    facing: int = 0,
) -> Steer | None:
    """Steering response (section 4); None when nothing blocks. Each rescan starts again from ``ref`` with the
    current steer heading and distance, and a later blocker's response replaces the earlier one."""
    hit = scan(ref, waypoint, footprints, own_radius, blocks)
    if hit is None:
        return None
    wp_heading = bearing(ref, waypoint)
    side = remembered_side
    if side == 0:
        side = 1 if (wp_heading - hit.bearing) % _TURN <= _HALF else -1
    total = 0
    prev = facing % _TURN
    stored = 0
    for _ in range(_MAX_STEERS):
        heading = (hit.bearing + side * ((5 * hit.half_width) >> 2)) % _TURN
        full = math.sqrt(hit.distance**2 + hit.combined_radius**2)
        stored = int(full / 2)
        total += abs(heading - prev)
        prev = heading
        if total > _TURN:
            return Steer(wp_heading, ref, stored, side, True)
        nxt = scan(ref, waypoint, footprints, own_radius, blocks, heading, stored)
        if nxt is None:
            return Steer(heading, _point_along(ref, heading, full), stored, side, False)
        hit = nxt
    return Steer(wp_heading, ref, stored, side, True)


def _trial(
    start: Point,
    facing: int,
    waypoint: Point,
    footprints: Sequence[Footprint],
    own_radius: float,
    blocks: Callable[[Footprint], bool],
    permitted: Callable[[Point], bool],
    side: int,
) -> float:
    pos = start
    face = facing
    score = 0.0
    for _ in range(_MAX_TRIAL_STEPS):
        st = steer(pos, waypoint, footprints, own_radius, blocks, remembered_side=side, facing=face)
        if st is None:
            break
        heading = st.heading
        point = st.point
        if st.gave_up:
            heading = (face + _HALF) % _TURN
            point = _point_along(pos, heading, 2 * st.distance)
        if not permitted(point):
            score = _FORBIDDEN
            break
        score += 4 * _diff(heading, face) + st.distance
        pos = point
        face = heading
        if score > _TRIAL_LIMIT:
            break
    return score + math.hypot(waypoint[0] - pos[0], waypoint[1] - pos[1])


def plan(
    start: Point,
    facing: int,
    waypoint: Point,
    footprints: Sequence[Footprint],
    own_radius: float,
    blocks: Callable[[Footprint], bool],
    permitted: Callable[[Point], bool],
) -> Plan:
    """Two-trial route plan (section 5)."""
    hit = scan(start, waypoint, footprints, own_radius, blocks)
    if hit is None:
        return Plan(True, 0, (0.0, 0.0))
    natural = 1 if (bearing(start, waypoint) - hit.bearing) % _TURN <= _HALF else -1
    first = _trial(start, facing, waypoint, footprints, own_radius, blocks, permitted, natural)
    second = _trial(start, facing, waypoint, footprints, own_radius, blocks, permitted, -natural)
    side = natural if first < second else -natural
    ok = not (first >= _FORBIDDEN and second >= _FORBIDDEN)
    return Plan(ok, side, (first, second))
