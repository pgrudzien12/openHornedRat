"""The close-combat battle grid, as specified in notes/game_rules.md 5.8.

A fight is not "two footprints overlap": it is a shared 17 x 17 cell record (one cell = one model
spacing) seeded around the first unit that was engaged, on which individual models are placed,
paired with individual enemy models, and only then allowed to strike. Frame, seeding, joining,
owner pairing, arrival and side-only cells are all defined in game_rules.md 5.8; the constants below
are the ones named there.

Deviations from the specification: candidate cells are range-checked and seeding clamps instead of
writing out of bounds (5.8 step 2), and the placeholders listed in 5.8 step 9 are not modelled.
"""

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from . import formation

if TYPE_CHECKING:
    from .engine import Battle, ModelState, Regiment

Cell = tuple[int, int]  # (row, col)
CellOwner = tuple[str, int]  # (regiment identifier, model uid)
EnemyModel = tuple["Regiment", int, "ModelState"]  # (regiment, model index, model)

GRID_SIZE = 17  # cells per side of one battle-grid record (game_rules.md 5.7)
CENTRE = GRID_SIZE // 2
CELL = formation.MODEL_SPACING  # 12 world units, one model per cell
NEAR_DISTANCE = 18.0  # closer than this, all four orthogonal cells are offered, not just two
ARRIVAL_DISTANCE = 3.0  # a model counts as "in hand-to-hand" within this distance of its cell
OWNER_SWITCH_RATIO = 1.5  # the owner pairs like a joiner once it outnumbers the enemy by more than this

# Orthogonal neighbour offsets (row, col), used for the owner's own in-place pairing, which is not
# direction-dependent (game_rules.md 5.8 step 5).
_NEIGHBOURS = ((-1, 0), (0, -1), (0, 1), (1, 0))

# The four ordered (row, col) candidate offsets a joiner tries around its target's cell, indexed by
# `dir` (notes/engine_gaps/engagement_dispersal.md, "Direction-indexed joiner candidate cells").
# dir 0 = approaching the defender's rear, 1 = its front, 2/3 = its two flanks.
_JOIN_OFFSETS = (
    ((1, 0), (0, -1), (0, 1), (-1, 0)),
    ((-1, 0), (0, -1), (0, 1), (1, 0)),
    ((0, 1), (1, 0), (-1, 0), (0, -1)),
    ((0, -1), (1, 0), (-1, 0), (0, 1)),
)

# Composes a joiner's approach arc (0 = front, 1 = rear, 2/3 = flanks) with the defender's own
# direction code into the `dir` that selects a row of `_JOIN_OFFSETS`.
_COMBINE = (
    (1, 0, 3, 2),
    (0, 1, 2, 3),
    (3, 2, 0, 1),
    (2, 3, 1, 0),
)


class BattleGrid:
    """One fight's shared cell map. Cells hold `(regiment_id, model_uid)`; a model's side is implied
    by its regiment, mirroring the original's side-only cell stamp. Cells and pairings name a model by
    its stable `ModelState.uid`, never by its list index, so a casualty cannot silently re-point a
    surviving pairing at a different model."""

    def __init__(self, owner_id: str, x: float, y: float, direction: int, width: int) -> None:
        self.owner_id = owner_id
        self.x = x
        self.y = y
        self.direction = direction
        self.width = max(1, width)
        self.cells: dict[Cell, CellOwner] = {}  # (row, col) -> (regiment_id, model uid)
        # regiment identifier -> its direction code on this grid, used to compose a later joiner's
        # own `dir`; a freshly created grid's owner always carries code 0 (engagement_dispersal.md).
        self.direction_codes: dict[str, int] = {owner_id: 0}

    def cell_world(self, row: int, col: int) -> formation.Point:
        """World position of a cell centre, in the frame the grid was created in."""
        side = (col - self._col_base() - (self.width - 1) / 2) * CELL
        forward = -(row - self._row_base()) * CELL
        return formation.place(self.x, self.y, self.direction, [(side, forward)])[0]

    def _col_base(self) -> int:
        return CENTRE - self.width // 2

    def _row_base(self) -> int:
        return CENTRE - self._ranks // 2

    def seed(self, regiment: "Regiment") -> None:
        """Write the grid-owning regiment's models into cells around the centre (game_rules.md 5.8 step 2)."""
        sizes = formation.rank_sizes(regiment.models, regiment.ranks)
        self.width = max(sizes) if sizes else 1
        self._ranks = len(sizes)
        index = 0
        for rank, size in enumerate(sizes):
            for file_index in range(size):
                row = _clamp(rank + self._row_base())
                col = _clamp(file_index + self._col_base())
                if (row, col) not in self.cells and index < len(regiment.melee_models):
                    model = regiment.melee_models[index]
                    self.cells[(row, col)] = (regiment.identifier, model.uid)
                    model.cell = (row, col)
                index += 1

    _ranks: int = 1

    def occupant(self, row: int, col: int) -> CellOwner | None:
        return self.cells.get((row, col))

    def free(self, row: int, col: int) -> bool:
        return in_bounds(row, col) and (row, col) not in self.cells

    def place(self, row: int, col: int, regiment_id: str, model_uid: int) -> None:
        self.cells[(row, col)] = (regiment_id, model_uid)

    def clear(self, cell: Cell) -> None:
        self.cells.pop(cell, None)


def in_bounds(row: int, col: int) -> bool:
    return 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE


def _clamp(value: int) -> int:
    return max(0, min(GRID_SIZE - 1, value))


def _members(battle: "Battle", group_id: str | None) -> list["Regiment"]:
    """The regiments sharing one fight, in a fixed order (the original walks the global unit array;
    identifier order keeps a replay deterministic)."""
    return [battle.regiments[key] for key in sorted(battle.regiments)
            if battle.regiments[key].melee_group == group_id and battle.regiments[key].active]


def create(battle: "Battle", group_id: str, members: Sequence["Regiment"]) -> BattleGrid:
    """Seed a fresh grid around the unit that was engaged (the defender, if one can be told apart)."""
    owner = _pick_owner(members)
    grid = BattleGrid(owner.identifier, owner.x, owner.y, owner.direction, owner.front_rank_models())
    grid.seed(owner)
    return grid


def _pick_owner(members: Sequence["Regiment"]) -> "Regiment":
    """The grid owner is the unit that was engaged, not the one that charged into it; a unit with no
    attack order of its own is the defender. Ties break on identifier for a deterministic replay."""
    defenders = [r for r in members if r.attack_target is None]
    return min(defenders or members, key=lambda r: r.identifier)


def update(battle: "Battle", group_id: str, grid: BattleGrid, members: Sequence["Regiment"]) -> None:
    """One tick of placement and pairing for every unit on `grid` (game_rules.md 5.8 steps 3-6)."""
    _drop_dead(battle, grid)
    for regiment in members:
        if regiment.identifier == grid.owner_id and not _owner_outnumbers(regiment, members):
            _pair_owner(battle, grid, regiment, members)
        else:
            _pair_joiner(battle, grid, regiment, members)
    _sync_arrival(grid, members)


def _sync_arrival(grid: BattleGrid, members: Sequence["Regiment"]) -> None:
    """Mark every placed model that already stands in its cell as arrived, so a model that is given a
    cell it is practically standing on fights in the same segment instead of waiting a tick for the
    mover to notice (game_rules.md 5.8 step 6)."""
    for regiment in members:
        positions = regiment.model_positions()
        for index, model in enumerate(regiment.melee_models):
            if model.cell is None:
                model.arrived = False
                continue
            wx, wy = grid.cell_world(*model.cell)
            px, py = positions[index]
            model.arrived = math.hypot(wx - px, wy - py) <= ARRIVAL_DISTANCE


def _owner_outnumbers(owner: "Regiment", members: Sequence["Regiment"]) -> bool:
    enemies = sum(r.models for r in members if r.camp != owner.camp)
    return enemies > 0 and owner.models * 2 > enemies * 3


def _drop_dead(battle: "Battle", grid: BattleGrid) -> None:
    """Free the cells of models that died, and unpair whoever was fighting them."""
    for cell, (regiment_id, uid) in list(grid.cells.items()):
        regiment = battle.regiments.get(regiment_id)
        if regiment is None or not regiment.active or regiment.index_of(uid) is None:
            grid.clear(cell)
    for regiment in battle.regiments.values():
        for model in regiment.melee_models:
            if model.opponent is None:
                continue
            enemy_id, enemy_uid = model.opponent
            enemy = battle.regiments.get(enemy_id)
            if enemy is None or not enemy.active or enemy.index_of(enemy_uid) is None:
                model.opponent = None
                model.arrived = False


def _enemy_models_on_grid(battle: "Battle", grid: BattleGrid, regiment: "Regiment",
                          members: Sequence["Regiment"]) -> list[EnemyModel]:
    """Every enemy model that already holds a cell, with its cell and world position."""
    found: list[EnemyModel] = []
    for other in members:
        if other.camp == regiment.camp or not other.active:
            continue
        for index, model in enumerate(other.melee_models):
            if model.cell is not None:
                found.append((other, index, model))
    return found


def _pair_joiner(battle: "Battle", grid: BattleGrid, regiment: "Regiment", members: Sequence["Regiment"]) -> None:
    """Place up to `frontage` free models per tick next to the nearest enemy model."""
    enemies = _enemy_models_on_grid(battle, grid, regiment, members)
    if not enemies:
        return
    budget = max(1, regiment.front_rank_models())
    positions = regiment.model_positions()
    for index, model in enumerate(regiment.melee_models):
        if budget <= 0:
            break
        if model.cell is not None:
            continue
        px, py = positions[index]
        placed = _place_next_to_enemy(grid, regiment, model, px, py, enemies)
        if placed:
            budget -= 1
            model.reserve = False
        else:
            model.reserve = True  # no free cell this tick; retried on a later tick


def _place_next_to_enemy(grid: BattleGrid, regiment: "Regiment", model: "ModelState", px: float, py: float,
                         enemies: Sequence[EnemyModel]) -> bool:
    ordered = sorted(enemies, key=lambda item: (
        math.hypot(*_delta(px, py, item[0], item[1])), item[0].identifier, item[1]))
    for enemy, enemy_index, enemy_model in ordered:
        if enemy_model.cell is None:
            continue
        distance = math.hypot(*_delta(px, py, enemy, enemy_index))
        direction = _direction_for(grid, regiment, enemy, px, py)
        candidates = _candidate_cells(enemy_model.cell, direction, distance)
        for row, col in candidates:
            if not grid.free(row, col):
                continue
            grid.place(row, col, regiment.identifier, model.uid)
            model.cell = (row, col)
            model.arrived = False
            model.at_rest = False
            model.distance_budget = 0.0  # the new cell must replace any pre-contact heading
            model.opponent = (enemy.identifier, enemy_model.uid)
            if enemy_model.opponent is None:
                enemy_model.opponent = (regiment.identifier, model.uid)
                enemy_model.arrived = False
            return True
    return False


def _delta(px: float, py: float, enemy: "Regiment", enemy_index: int) -> tuple[float, float]:
    ex, ey = enemy.model_positions()[enemy_index]
    return ex - px, ey - py


def _direction_for(grid: BattleGrid, regiment: "Regiment", defender: "Regiment", px: float, py: float) -> int:
    """The `dir` a joining regiment uses for every placement against this grid, computed once from
    its first approach and kept afterwards (engagement_dispersal.md "Direction-indexed joiner
    candidate cells", step 2)."""
    stored = grid.direction_codes.get(regiment.identifier)
    if stored is not None:
        return stored
    arc = _arc_code(px, py, defender)
    defender_code = grid.direction_codes.get(defender.identifier, 0)
    direction = _COMBINE[defender_code][arc]
    grid.direction_codes[regiment.identifier] = direction
    return direction


def _arc_code(px: float, py: float, defender: "Regiment") -> int:
    """The joining model's approach arc relative to `defender`'s facing: 0 front, 1 rear, 2/3 the two
    flanks. The front/rear cones are as wide as the defender's own footprint diagonal half-angle
    (engagement_dispersal.md step 1)."""
    cx, cy, half_side, half_forward, _, _ = formation.footprint_frame(
        defender.x, defender.y, defender.direction, defender.models, defender.ranks)
    half_angle = round(math.atan2(half_side, half_forward) * formation.FULL_TURN / math.tau)
    dx, dy = cx - px, cy - py
    bearing = round(math.atan2(dx, dy) * formation.FULL_TURN / math.tau) % formation.FULL_TURN
    rel = (bearing - defender.direction) % formation.FULL_TURN
    half_turn = formation.FULL_TURN // 2
    if rel <= half_angle or rel >= formation.FULL_TURN - half_angle:
        return 1  # rear
    if half_turn - half_angle <= rel <= half_turn + half_angle:
        return 0  # front
    if rel < half_turn:
        return 2  # flank A
    return 3  # flank B


def _candidate_cells(enemy_cell: Cell, direction: int, distance: float) -> list[Cell]:
    """The fixed offsets around `enemy_cell` for `direction`, tried strictly in order; only the first
    two are offered while the attacker is still further than `NEAR_DISTANCE` away
    (engagement_dispersal.md step 4)."""
    row, col = enemy_cell
    offsets = _JOIN_OFFSETS[direction]
    if distance > NEAR_DISTANCE:
        offsets = offsets[:2]
    return [(row + d_row, col + d_col) for d_row, d_col in offsets]


def _pair_owner(battle: "Battle", grid: BattleGrid, regiment: "Regiment", members: Sequence["Regiment"]) -> None:
    """The owner's unpaired models take any enemy model orthogonally adjacent on the grid."""
    for model in regiment.melee_models:
        if model.opponent is not None or model.cell is None:
            continue
        row, col = model.cell
        for d_row, d_col in _NEIGHBOURS:
            occupant = grid.occupant(row + d_row, col + d_col)
            if occupant is None:
                continue
            enemy_id, enemy_uid = occupant
            enemy = battle.regiments.get(enemy_id)
            if enemy is None or enemy.camp == regiment.camp or not enemy.active:
                continue
            enemy_index = enemy.index_of(enemy_uid)
            if enemy_index is None:
                continue
            enemy_model = enemy.melee_models[enemy_index]
            model.opponent = (enemy_id, enemy_uid)
            if enemy_model.opponent is None:
                enemy_model.opponent = (regiment.identifier, model.uid)
                enemy_model.arrived = False
            break


def release(battle: "Battle", regiment: "Regiment") -> None:
    """Unpair and un-cell every model of a regiment that leaves a grid (game_rules.md 5.7, "Leaving").

    Both directions of every pairing have to go: the models this regiment was fighting still hold a
    pointer back at it, and a regiment that later re-joins a fight is placed in fresh cells, so a
    surviving back-pointer would name the right model in the wrong place.
    """
    grid = _grid_of(battle, regiment)
    for model in regiment.melee_models:
        if grid is not None and model.cell is not None:
            grid.clear(model.cell)
        model.cell = None
        model.opponent = None
        model.arrived = False
        model.reserve = False
    for other in battle.regiments.values():
        if other.identifier == regiment.identifier:
            continue
        for model in other.melee_models:
            if model.opponent is not None and model.opponent[0] == regiment.identifier:
                model.opponent = None
                model.arrived = False


def _grid_of(battle: "Battle", regiment: "Regiment") -> BattleGrid | None:
    fight = battle.fights.get(regiment.melee_group)
    return fight.get("grid") if fight else None


def fighting_models(battle: "Battle", regiment: "Regiment") -> list[tuple[int, "ModelState", "Regiment", int]]:
    """The regiment's models that may strike this turn: alive, paired, and arrived in their cell."""
    found: list[tuple[int, "ModelState", "Regiment", int]] = []
    for index, model in enumerate(regiment.melee_models):
        if model.opponent is None or not model.arrived:
            continue
        enemy_id, enemy_uid = model.opponent
        enemy = battle.regiments.get(enemy_id)
        if enemy is None or not enemy.active:
            continue
        enemy_index = enemy.index_of(enemy_uid)
        if enemy_index is None:
            continue
        found.append((index, model, enemy, enemy_index))
    return found


def cell_target(battle: "Battle", regiment: "Regiment", index: int) -> formation.Point | None:
    """World position a model should walk to while engaged, or None when it has no cell yet."""
    grid = _grid_of(battle, regiment)
    if grid is None:
        return None
    model = regiment.melee_models[index]
    if model.cell is None:
        return None
    return grid.cell_world(*model.cell)
