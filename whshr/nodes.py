"""Waypoint nodes of a battle's ``[NODES]`` table and the scatter-destination rule.

Behaviour source: notes/scatter_models_to_node.md (public report for GitHub issue #47).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
import random

from .formation import FULL_TURN, Point
from .script import View

DEFAULT_RADIUS = 16  # a node without a `radius` keyword (notes/scatter_models_to_node.md, "Answer")


@dataclass(frozen=True)
class ScriptNode:
    """One ``[NODES]`` entry, in BTS world coordinates."""

    x: float
    y: float
    node_id: int = 0  # the entry's own `id` keyword; not unique (nearly every node has id 0)
    radius: int = DEFAULT_RADIUS
    active: bool = True  # carries `ns_active` in its status


def from_views(views: Iterable[View]) -> list[ScriptNode]:
    """Build the node table from `whshr.script.load_battle`'s ``nodes`` list, keeping list order.

    Entries without both coordinates are skipped.
    """
    nodes: list[ScriptNode] = []
    for view in views:
        x, y = view.get("x"), view.get("y")
        if x is None or y is None:
            continue
        radius = view.get("radius")
        status = {str(flag).casefold() for flag in view.get("status") or ()}
        nodes.append(ScriptNode(float(x), float(y), int(view.get("id") or 0),
                                DEFAULT_RADIUS if radius is None else int(radius), "ns_active" in status))
    return nodes


def scatter_destinations(nodes: Sequence[ScriptNode], node_id: int, count: int,
                         rng: random.Random) -> list[tuple[int, Point]]:
    """Up to `count` scatter destinations as ``(list index of the chosen node, (x, y))``.

    notes/scatter_models_to_node.md, "Behaviour": the scan runs in list order over active nodes whose
    id equals `node_id`, each destination resuming just after the previous one's node and wrapping
    around, so destinations alternate between every node that shares the id. Each destination lies at
    a distance uniform over the integers ``0 .. radius - 1`` (the centre for radius 0, an engine choice: the
    original has no guard) and a uniform angle in 512 steps, drawn in that order. Stops early when no active node has the id.
    """
    destinations: list[tuple[int, Point]] = []
    start = 0
    for _ in range(count):
        chosen = next((index % len(nodes) for index in range(start, start + len(nodes))
                       if nodes[index % len(nodes)].active and nodes[index % len(nodes)].node_id == node_id),
                      None)
        if chosen is None:
            break
        node = nodes[chosen]
        distance = rng.randrange(node.radius) if node.radius > 0 else 0
        angle = rng.randrange(FULL_TURN)
        # notes/script_spawn_move.md 8.3: (COS[a] * d >> 8, -(SIN[a] * d) >> 8) with truncated tables and
        # floor shifts.
        cos_a = int(256 * math.cos(angle * math.tau / FULL_TURN))
        sin_a = int(256 * math.sin(angle * math.tau / FULL_TURN))
        destinations.append((chosen, (node.x + ((cos_a * distance) >> 8), node.y + ((-(sin_a * distance)) >> 8))))
        start = chosen + 1
    return destinations
