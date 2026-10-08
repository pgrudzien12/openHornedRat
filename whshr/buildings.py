"""Placed buildings as script-targetable pseudo-units (GitHub issues #173, #185).

Behaviour source: notes/building_units.md (footprint rectangle, toughness, melee, collision, destruction),
notes/battle_end_objectives.md 12.1 (which furniture becomes a building), notes/threat_events_nodes.md part A 5
(``AttackUnitAtNode``) and part C (side code 32), notes/ranged_combat_handoff.md (missile damage).

A building is not a regiment here: it runs no script, belongs to no army and never receives events. It has a
rectangular footprint (centred on the furniture position and turned by its direction), a wounds-to-destroy count and
a running wound tally on its first model. It is addressed by an identifier of the form ``building:N`` (N = index in
file order among the furniture) so that an event source can name it.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

PREFIX = "building:"
SIDE_CODE = 0x20  # absolute side code script operands use for building/furniture pseudo-units
NODE_REACH_FLOOR = 48  # AttackUnitAtNode looks within max(footprint radius, 48) of the node
MISSILE_TOUGHNESS = 0  # notes/building_units.md 3: missiles wound a building as if its toughness were 0
AUTOMATIC_WOUND_STRENGTH = 8  # at this strength and above a missile wound needs no roll (notes/building_units.md 3)
CELL = 12  # footprint grid cell


@dataclass(frozen=True)
class BuildingType:
    """One row of notes/building_units.md section 2: size in 8-unit cells, wounds, toughness and the ruin piece."""

    width: int
    depth: int
    height: int  # world units
    wounds: int  # W: wounds on the first model that destroy the building
    toughness: int  # T of the first model in close combat
    models: int
    ruin: tuple[int, int, int]  # ruin piece width, depth (cells) and height (world units)

    @property
    def half_extents(self) -> tuple[int, int]:
        """Half of the footprint rectangle, sideways and front-to-back (12-unit cells, one extra cell each way)."""
        return (CELL // 2 * (-(-8 * self.width // CELL) + 1), CELL // 2 * (-(-8 * self.depth // CELL) + 1))

    @property
    def radius(self) -> int:
        """Circle used by broad collision, reach and steering tests."""
        hx, hy = self.half_extents
        return int(math.hypot(hx, hy)) - CELL


def _t(w: int, d: int, height: int, wounds: int, toughness: int, models: int,
       ruin: tuple[int, int, int] | None = None) -> BuildingType:
    return BuildingType(w, d, height, wounds, toughness, models, ruin or (w, d, height))


_TENT = _t(6, 6, 40, 1, 1, 1)
_SKAV_20 = _t(21, 21, 120, 5, 5, 1)
TYPES: dict[str, BuildingType] = {
    "Tudor2Stry": _t(7, 4, 88, 5, 5, 2, (9, 4, 88)), "Yelo2Stry": _t(7, 4, 88, 5, 4, 2, (9, 4, 88)),
    "StnYelo2Stry": _t(7, 4, 88, 5, 5, 2, (9, 4, 88)), "TudorChimney": _t(9, 4, 88, 4, 4, 2, (9, 4, 48)),
    "BalconyHouse": _t(6, 6, 96, 4, 4, 2, (7, 6, 96)), "WaterMill": _t(9, 9, 64, 4, 4, 2),
    "SmithyHut": _t(11, 13, 72, 4, 4, 2), "BrewerySmall": _t(6, 8, 56, 4, 4, 2),
    "Brck2Stry": _t(7, 4, 88, 6, 5, 3, (9, 4, 88)), "Crypt": _t(6, 13, 96, 6, 5, 3),
    "NiteCrypt": _t(6, 13, 96, 6, 5, 3), "WatchTower": _t(5, 6, 96, 6, 4, 3), "Farm": _t(16, 16, 88, 6, 5, 3, (16, 16, 56)),
    "WindMill": _t(6, 6, 96, 6, 5, 3, (6, 6, 80)), "Tavern": _t(17, 9, 96, 6, 5, 3, (17, 9, 0)),
    "StnFarmHouse": _t(4, 7, 104, 6, 5, 3), "AngRoofHouse": _t(13, 9, 72, 6, 4, 3),
    "BreweryMain": _t(11, 15, 136, 6, 5, 3), "WoodShack": _t(8, 4, 64, 3, 3, 1, (9, 5, 32)),
    "BlackWoodShack": _t(9, 5, 64, 3, 3, 1), "Barn1": _t(12, 6, 80, 3, 3, 1), "BreweryShed": _t(8, 6, 56, 3, 3, 1),
    "Well2": _t(2, 2, 24, 2, 2, 1, (2, 2, 16)),
    "HumanTent": _TENT, "NiteHumanTent": _TENT, "OrcBoyzTent": _TENT, "B_OrcBoyzTent": _TENT,
    "GrsOrcBoyzTent": _TENT, "GrsBlackOrcTent": _TENT, "BlackOrcTent": _t(7, 7, 48, 1, 1, 1, (6, 6, 40)),
    "Menhir": _t(4, 4, 120, 4, 4, 1),
    "SkavBase10FR": _t(11, 11, 64, 5, 5, 1), "SkavBase10FL": _t(11, 11, 64, 5, 5, 1),
    "SkavBase20FLR": _SKAV_20, "SkavBase20FaR": _SKAV_20, "SkavBase20FaL": _SKAV_20,
    "SkavBase20x10": _t(21, 11, 120, 5, 5, 1),
}
DEFAULT_SCENERY_RADIUS = 12.0  # PROVISIONAL footprint radius of non-building furniture
LARGE_SCENERY_RADIUS = 24.0  # PROVISIONAL: towers, houses and walls that are not buildings


def footprint_radius(name: str) -> float:
    """Circle radius of a furniture piece: the building table's radius, else a PROVISIONAL guess."""
    kind = TYPES.get(name)
    if kind is not None:
        return float(kind.radius)
    return LARGE_SCENERY_RADIUS if any(w in name.casefold() for w in ("tower", "house", "wall")) \
        else DEFAULT_SCENERY_RADIUS


@dataclass
class Building:
    """One placed building: footprint rectangle, wounds needed to destroy it and the wounds taken so far."""

    identifier: str
    name: str
    x: float
    y: float
    radius: float
    wounds_to_destroy: int
    wounds_taken: int = 0
    models: int = 1
    destroyed: bool = False
    direction: int = 0  # furniture `dir`, 1/512 turn, 0 = +Y, clockwise
    half_x: float = 0.0  # half-extent sideways
    half_y: float = 0.0  # half-extent front-to-back
    toughness: int = 0  # close-combat T of the first model
    height: int = 0
    pieces: int = 1  # models at the start of the battle: the kills a destroyer is credited with
    credit: str | None = None  # regiment that last wounded the first model (kill credit on destruction)

    @property
    def side_code(self) -> int:
        return SIDE_CODE

    @property
    def standing(self) -> bool:
        """Counts for the "protect the buildings" objective: not destroyed."""
        return not self.destroyed

    def take_wounds(self, wounds: int, source: str | None = None, lethal_only: bool = False) -> bool:
        """Add wounds to the first model; returns True when this call destroys the building. `source` is the
        regiment credited: every wound credits it, except that a lethal-only source (missiles, spells) is credited
        only by the wound that destroys the building (notes/casualty_bookkeeping.md 2.1)."""
        if self.destroyed:
            return False
        self.wounds_taken += wounds
        destroyed = self.wounds_taken >= self.wounds_to_destroy
        if source is not None and (destroyed or not lethal_only):
            self.credit = source
        if destroyed:
            self.destroyed = True
            self.models = 0
        return destroyed

    def _local(self, px: float, py: float) -> tuple[float, float]:
        """A world point in the building's own frame: x sideways, y front-to-back."""
        angle = self.direction * math.tau / 512
        dx, dy = px - self.x, py - self.y
        sin, cos = math.sin(angle), math.cos(angle)
        return dx * cos - dy * sin, dx * sin + dy * cos

    def contains(self, px: float, py: float) -> bool:
        """Whether a world point lies inside the footprint rectangle."""
        lx, ly = self._local(px, py)
        return abs(lx) <= self.half_x and abs(ly) <= self.half_y

    def penetration(self, px: float, py: float, radius: float) -> tuple[float, float] | None:
        """The world-space push that moves a circle clear of the footprint rectangle, or None when it does not
        overlap. A centre inside the rectangle is pushed out along the nearest side."""
        lx, ly = self._local(px, py)
        nearest_x = max(-self.half_x, min(self.half_x, lx))
        nearest_y = max(-self.half_y, min(self.half_y, ly))
        gap_x, gap_y = lx - nearest_x, ly - nearest_y
        distance = math.hypot(gap_x, gap_y)
        if distance >= radius:
            return None
        if distance > 1e-9:
            push_x, push_y = gap_x / distance * (radius - distance), gap_y / distance * (radius - distance)
        else:
            to_x, to_y = self.half_x - abs(lx), self.half_y - abs(ly)
            if to_x <= to_y:
                push_x, push_y = math.copysign(to_x + radius, lx or 1.0), 0.0
            else:
                push_x, push_y = 0.0, math.copysign(to_y + radius, ly or 1.0)
        angle = self.direction * math.tau / 512
        sin, cos = math.sin(angle), math.cos(angle)
        return push_x * cos + push_y * sin, -push_x * sin + push_y * cos


def from_scenery(scenery: Iterable[Mapping[str, Any]]) -> list[Building]:
    """Building pseudo-units for the furniture whose type is a building type, in file order. The identifier index
    is the piece's position among all furniture entries, so it matches the scenery list."""
    buildings: list[Building] = []
    for index, item in enumerate(scenery):
        name = str(item.get("name", ""))
        kind = TYPES.get(name)
        if kind is None:
            continue
        hx, hy = kind.half_extents
        buildings.append(Building(f"{PREFIX}{index}", name, float(item.get("x") or 0), float(item.get("y") or 0),
                                  float(kind.radius), kind.wounds, models=kind.models,
                                  direction=int(item.get("dir") or 0) % 512, half_x=float(hx), half_y=float(hy),
                                  toughness=kind.toughness, height=kind.height, pieces=kind.models))
    return buildings


def nearest_to_point(buildings: Iterable[Building], x: float, y: float) -> Building | None:
    """The standing building whose centre is within max(footprint radius, 48) of the point; nearest wins and ties
    go to the first in file order (AttackUnitAtNode, notes/threat_events_nodes.md part A 5)."""
    best: Building | None = None
    best_distance = 0.0
    for building in buildings:
        if building.destroyed:
            continue
        distance = ((building.x - x) ** 2 + (building.y - y) ** 2) ** .5
        if distance >= max(building.radius, NODE_REACH_FLOOR):
            continue
        if best is None or distance < best_distance:
            best, best_distance = building, distance
    return best


def at_position(buildings: Iterable[Building], x: float, y: float) -> Building | None:
    """The standing building placed exactly at a point (a Fire order's clicked object), or None."""
    return next((b for b in buildings if not b.destroyed and b.x == x and b.y == y), None)
