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
