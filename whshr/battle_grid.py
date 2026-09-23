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

from . import formation

GRID_SIZE = 17  # cells per side of one battle-grid record (game_rules.md 5.7)
CENTRE = GRID_SIZE // 2
CELL = formation.MODEL_SPACING  # 12 world units, one model per cell
NEAR_DISTANCE = 18.0  # closer than this, all four orthogonal cells are offered, not just two
ARRIVAL_DISTANCE = 3.0  # a model counts as "in hand-to-hand" within this distance of its cell
OWNER_SWITCH_RATIO = 1.5  # the owner pairs like a joiner once it outnumbers the enemy by more than this

# Orthogonal neighbour offsets (row, col), ordered so that index 0 is the cell on the side the
# attacker comes from and index 1 its first flank; only those two are offered while the model is
# still far away (game_rules.md 5.8 step 3).
_NEIGHBOURS = ((-1, 0), (0, -1), (0, 1), (1, 0))


class BattleGrid:
    """One fight's shared cell map. Cells hold `(regiment_id, model_uid)`; a model's side is implied
    by its regiment, mirroring the original's side-only cell stamp. Cells and pairings name a model by
    its stable `ModelState.uid`, never by its list index, so a casualty cannot silently re-point a
    surviving pairing at a different model."""

    def __init__(self, owner_id, x, y, direction, width):
        self.owner_id = owner_id
        self.x = x
        self.y = y
        self.direction = direction
        self.width = max(1, width)
        self.cells = {}  # (row, col) -> (regiment_id, model_index)

    def cell_world(self, row, col):
        """World position of a cell centre, in the frame the grid was created in."""
        side = (col - self._col_base() - (self.width - 1) / 2) * CELL
        forward = -(row - self._row_base()) * CELL
        return formation.place(self.x, self.y, self.direction, [(side, forward)])[0]

    def _col_base(self):
        return CENTRE - self.width // 2

    def _row_base(self):
        return CENTRE - self._ranks // 2

    def seed(self, regiment):
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

    _ranks = 1

    def occupant(self, row, col):
        return self.cells.get((row, col))

    def free(self, row, col):
        return in_bounds(row, col) and (row, col) not in self.cells

    def place(self, row, col, regiment_id, model_uid):
        self.cells[(row, col)] = (regiment_id, model_uid)

    def clear(self, cell):
        self.cells.pop(cell, None)


def in_bounds(row, col):
    return 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE


def _clamp(value):
    return max(0, min(GRID_SIZE - 1, value))


def _members(battle, group_id):
    """The regiments sharing one fight, in a fixed order (the original walks the global unit array;
    identifier order keeps a replay deterministic)."""
    return [battle.regiments[key] for key in sorted(battle.regiments)
            if battle.regiments[key].melee_group == group_id and battle.regiments[key].active]


def create(battle, group_id, members):
    """Seed a fresh grid around the unit that was engaged (the defender, if one can be told apart)."""
    owner = _pick_owner(members)
    grid = BattleGrid(owner.identifier, owner.x, owner.y, owner.direction, owner.front_rank_models())
    grid.seed(owner)
    return grid


def _pick_owner(members):
    """The grid owner is the unit that was engaged, not the one that charged into it; a unit with no
    attack order of its own is the defender. Ties break on identifier for a deterministic replay."""
    defenders = [r for r in members if r.attack_target is None]
    return min(defenders or members, key=lambda r: r.identifier)


def update(battle, group_id, grid, members):
    """One tick of placement and pairing for every unit on `grid` (game_rules.md 5.8 steps 3-6)."""
    _drop_dead(battle, grid)
    for regiment in members:
        if regiment.identifier == grid.owner_id and not _owner_outnumbers(regiment, members):
            _pair_owner(battle, grid, regiment, members)
        else:
            _pair_joiner(battle, grid, regiment, members)
    _sync_arrival(grid, members)


def _sync_arrival(grid, members):
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


def _owner_outnumbers(owner, members):
    enemies = sum(r.models for r in members if r.side != owner.side)
    return enemies and owner.models * 2 > enemies * 3


def _drop_dead(battle, grid):
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


def _enemy_models_on_grid(battle, grid, regiment, members):
    """Every enemy model that already holds a cell, with its cell and world position."""
    found = []
    for other in members:
        if other.side == regiment.side or not other.active:
            continue
        for index, model in enumerate(other.melee_models):
            if model.cell is not None:
                found.append((other, index, model))
    return found


def _pair_joiner(battle, grid, regiment, members):
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


def _place_next_to_enemy(grid, regiment, model, px, py, enemies):
    ordered = sorted(enemies, key=lambda item: (
        math.hypot(*_delta(px, py, item[0], item[1])), item[0].identifier, item[1]))
    for enemy, enemy_index, enemy_model in ordered:
        if enemy_model.cell is None:
            continue
        distance = math.hypot(*_delta(px, py, enemy, enemy_index))
        candidates = _candidate_cells(grid, enemy_model.cell, px, py, distance)
        for row, col in candidates:
            if not grid.free(row, col):
                continue
            grid.place(row, col, regiment.identifier, model.uid)
            model.cell = (row, col)
            model.arrived = False
            model.opponent = (enemy.identifier, enemy_model.uid)
            if enemy_model.opponent is None:
                enemy_model.opponent = (regiment.identifier, model.uid)
                enemy_model.arrived = False
            return True
    return False


def _delta(px, py, enemy, enemy_index):
    ex, ey = enemy.model_positions()[enemy_index]
    return ex - px, ey - py


def _candidate_cells(grid, enemy_cell, px, py, distance):
    """Orthogonal neighbours of `enemy_cell`, nearest-to-the-attacker first; only the first two are
    offered while the attacker is still further than `NEAR_DISTANCE` away."""
    row, col = enemy_cell
    scored = []
    for d_row, d_col in _NEIGHBOURS:
        cell = (row + d_row, col + d_col)
        if not in_bounds(*cell):
            continue
        wx, wy = grid.cell_world(*cell)
        scored.append((math.hypot(wx - px, wy - py), cell))
    scored.sort()
    cells = [cell for _, cell in scored]
    return cells if distance <= NEAR_DISTANCE else cells[:2]


def _pair_owner(battle, grid, regiment, members):
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
            if enemy is None or enemy.side == regiment.side or not enemy.active:
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


def release(battle, regiment):
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


def _grid_of(battle, regiment):
    fight = battle.fights.get(regiment.melee_group)
    return fight.get("grid") if fight else None


def fighting_models(battle, regiment):
    """The regiment's models that may strike this turn: alive, paired, and arrived in their cell."""
    found = []
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


def cell_target(battle, regiment, index):
    """World position a model should walk to while engaged, or None when it has no cell yet."""
    grid = _grid_of(battle, regiment)
    if grid is None:
        return None
    model = regiment.melee_models[index]
    if model.cell is None:
        return None
    return grid.cell_world(*model.cell)
