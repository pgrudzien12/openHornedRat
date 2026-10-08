"""Placed buildings as script-targetable pseudo-units (GitHub issue #173).

Behaviour source: notes/battle_end_objectives.md 12.1 (which furniture becomes a building, its wounds-to-destroy W),
notes/threat_events_nodes.md part A 5 (``AttackUnitAtNode``) and part C (side code 32),
notes/ranged_combat_handoff.md (missile damage against buildings).

A building is not a regiment: it runs no script, belongs to no army and never receives events. It has a footprint
(a circle around the piece), a wounds-to-destroy count and a running wound tally on its first owning model. It is
addressed by an identifier of the form ``building:N`` (N = index in file order) so that an event source can name it.

PROVISIONAL: the footprint radius of a placed piece (the report gives it only as a size in 8-unit cells that the
engine does not parse) and the toughness a missile wound roll uses against it are engine choices; neither is
recorded in a public report yet.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

PREFIX = "building:"
SIDE_CODE = 0x20  # absolute side code script operands use for building/furniture pseudo-units
NODE_REACH_FLOOR = 48  # AttackUnitAtNode looks within max(footprint radius, 48) of the node
BUILDING_TOUGHNESS = 5  # PROVISIONAL: toughness a missile wound roll uses against a building

# Wounds needed to destroy the first model (notes/battle_end_objectives.md 12.1). Types not listed are not buildings.
WOUNDS_TO_DESTROY: dict[str, int] = {
    **dict.fromkeys(("Tudor2Stry", "Yelo2Stry", "StnYelo2Stry"), 5),
    **dict.fromkeys(("TudorChimney", "BalconyHouse", "WaterMill", "SmithyHut", "BrewerySmall"), 4),
    **dict.fromkeys(("Brck2Stry", "Crypt", "NiteCrypt", "WatchTower", "Farm", "WindMill", "Tavern", "StnFarmHouse",
                     "AngRoofHouse", "BreweryMain"), 6),
    **dict.fromkeys(("WoodShack", "BlackWoodShack", "Barn1", "BreweryShed"), 3),
    "Well2": 2, "Menhir": 4,
    **dict.fromkeys(("HumanTent", "NiteHumanTent", "BlackOrcTent", "OrcBoyzTent", "B_OrcBoyzTent", "GrsOrcBoyzTent",
                     "GrsBlackOrcTent"), 1),
    **dict.fromkeys(("SkavBase10FR", "SkavBase10FL", "SkavBase20FLR", "SkavBase20FaR", "SkavBase20x10",
                     "SkavBase20FaL"), 5),
}
SINGLE_MODEL_TYPES = frozenset(("WoodShack", "BlackWoodShack", "Barn1", "BreweryShed", "Well2", "HumanTent",
                                "NiteHumanTent", "BlackOrcTent", "OrcBoyzTent", "B_OrcBoyzTent", "GrsOrcBoyzTent",
                                "GrsBlackOrcTent", "Menhir", "SkavBase10FR", "SkavBase10FL", "SkavBase20FLR",
                                "SkavBase20FaR", "SkavBase20x10", "SkavBase20FaL"))


def footprint_radius(name: str) -> float:
    """PROVISIONAL footprint radius of a placed piece (towers, houses and walls are large)."""
    return 24.0 if any(word in name.casefold() for word in ("tower", "house", "wall")) else 12.0


@dataclass
class Building:
    """One placed building: footprint, wounds needed to destroy it and the wounds taken so far."""

    identifier: str
    name: str
    x: float
    y: float
    radius: float
    wounds_to_destroy: int
    wounds_taken: int = 0
    models: int = 1
    destroyed: bool = False

    @property
    def side_code(self) -> int:
        return SIDE_CODE

    @property
    def standing(self) -> bool:
        """Counts for the "protect the buildings" objective: not destroyed (a multi-piece building keeps its
        models count at 0 once destroyed, a single-piece one is removed)."""
        return not self.destroyed

    def take_wounds(self, wounds: int) -> bool:
        """Add wounds to the first model; returns True when this call destroys the building."""
        if self.destroyed:
            return False
        self.wounds_taken += wounds
        if self.wounds_taken >= self.wounds_to_destroy:
            self.destroyed = True
            self.models = 0
            return True
        return False


def from_scenery(scenery: Iterable[Mapping[str, Any]]) -> list[Building]:
    """Building pseudo-units for the furniture whose type is a building type, in file order. The identifier index
    is the piece's position among all furniture entries, so it matches the scenery list."""
    buildings: list[Building] = []
    for index, item in enumerate(scenery):
        name = str(item.get("name", ""))
        wounds = WOUNDS_TO_DESTROY.get(name)
        if wounds is None:
            continue
        models = 1 if name in SINGLE_MODEL_TYPES else max(1, wounds // 2)
        buildings.append(Building(f"{PREFIX}{index}", name, float(item.get("x") or 0), float(item.get("y") or 0),
                                  footprint_radius(name), wounds, models=models))
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
