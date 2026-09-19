"""The close-combat battle grid traced in `GAMEF.DLL` (notes/game_rules.md 5.7).

A fight is not "two footprints overlap": it is a shared 17 x 17 cell record (one cell = one model
spacing) seeded around the first unit that was engaged, on which individual models are placed,
paired with individual enemy models, and only then allowed to strike.

What is reproduced here, and where it comes from:

- **Cell frame** (`FUN_10008a50`): the grid axes follow the owner's facing at creation and the cell
  pitch is `formation.MODEL_SPACING`, so cell `(row, col)` maps back onto the owner's own block slots.
- **Seeding** (`CreateGridTroops`, `FUN_100086d0`): the owner's models are written at
  `col = file + (8 - frontage // 2)`, `row = rank + (8 - ranks // 2)`.
- **Joining** (`PairJoiningModels`, `FUN_100060c0` -> `PlaceModelAdjacent`, `FUN_10007bb0`): at most
  `frontage` free models per tick, each into a free cell orthogonally adjacent to its nearest enemy
  model; only the cell facing the attacker plus one flank are offered while the model is more than
  `NEAR_DISTANCE` away, all four closer in. Models that find no cell become reserves and are retried
  on later ticks (the original defers them the same way; they are never written off after one failure).
- **Owner pairing** (`PairOwnerModels`, `FUN_100059c0`): the owner's unpaired models take any enemy
  model at Manhattan distance 1; the owner switches to the joining procedure once it outnumbers the
  enemy by more than 1.5x.
- **Arrival** (`ModelArrivedInCombat`, `FUN_10005450`): a model fights only once it holds an opponent
  *and* has walked within `ARRIVAL_DISTANCE` of its cell.
- **Cells carry only the side, never the unit** (`FUN_10007da0` stamps `s_side & 0xE1 | 1`), so allied
  units sharing a grid fill one undivided pool of free cells, in a fixed per-tick unit order.
- **Bounds**: candidate cells are range-checked to `0..GRID_SIZE-1` and an out-of-range model is simply
  deferred, matching the traced per-tick placement. The original's *unchecked* initial footprint write
  (game_rules.md 5.7, the out-of-bounds hazard) is deliberately not reproduced: seeding clamps instead.

Deliberately not modelled (documented placeholders, as elsewhere in this engine): war machine, monster
and wagon block layouts (every unit is seeded and placed as troops), `s_pntval` opponent stealing, and
the original's exact per-tick model walking speed.
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
# attacker comes from and index 1 its first flank; `PlaceModelAdjacent` offers only those two while
# the model is still far away.
_NEIGHBOURS = ((-1, 0), (0, -1), (0, 1), (1, 0))


class BattleGrid:
    """One fight's shared cell map. Cells hold `(regiment_id, model_index)`; a model's side is implied
    by its regiment, mirroring the original's side-only cell stamp."""

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
        """Write the grid-owning regiment's models into cells around the centre (`CreateGridTroops`)."""
        sizes = formation.rank_sizes(regiment.models, regiment.ranks)
        self.width = max(sizes) if sizes else 1
        self._ranks = len(sizes)
        index = 0
        for rank, size in enumerate(sizes):
            for file_index in range(size):
                row = _clamp(rank + self._row_base())
                col = _clamp(file_index + self._col_base())
                if (row, col) not in self.cells:
                    self.cells[(row, col)] = (regiment.identifier, index)
                    regiment.melee_models[index].cell = (row, col)
                index += 1

    _ranks = 1

    def occupant(self, row, col):
        return self.cells.get((row, col))

    def free(self, row, col):
        return in_bounds(row, col) and (row, col) not in self.cells

    def place(self, row, col, regiment_id, model_index):
        self.cells[(row, col)] = (regiment_id, model_index)

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
    """One tick of placement and pairing for every unit on `grid` (`EngageTroops`, `FUN_10005750`)."""
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
    mover to notice (`ModelArrivedInCombat` runs off the same distance test)."""
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
    enemies = sum(r.models for r in members if r.player != owner.player)
    return enemies and owner.models * 2 > enemies * 3


def _drop_dead(battle, grid):
    """Free the cells of models that died, and unpair whoever was fighting them."""
    for cell, (regiment_id, index) in list(grid.cells.items()):
        regiment = battle.regiments.get(regiment_id)
        if regiment is None or not regiment.active or index >= len(regiment.melee_models):
            grid.clear(cell)
    for regiment in battle.regiments.values():
        for model in regiment.melee_models:
            if model.opponent is None:
                continue
            enemy_id, enemy_index = model.opponent
            enemy = battle.regiments.get(enemy_id)
            if enemy is None or not enemy.active or enemy_index >= len(enemy.melee_models):
                model.opponent = None
                model.arrived = False


def _enemy_models_on_grid(battle, grid, regiment, members):
    """Every enemy model that already holds a cell, with its cell and world position."""
    found = []
    for other in members:
        if other.player == regiment.player or not other.active:
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
        placed = _place_next_to_enemy(grid, regiment, index, model, px, py, enemies)
        if placed:
            budget -= 1
            model.reserve = False
        else:
            model.reserve = True  # no free cell this tick; retried on a later tick


def _place_next_to_enemy(grid, regiment, index, model, px, py, enemies):
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
            grid.place(row, col, regiment.identifier, index)
            model.cell = (row, col)
            model.arrived = False
            model.opponent = (enemy.identifier, enemy_index)
            if enemy_model.opponent is None:
                enemy_model.opponent = (regiment.identifier, index)
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
    for index, model in enumerate(regiment.melee_models):
        if model.opponent is not None or model.cell is None:
            continue
        row, col = model.cell
        for d_row, d_col in _NEIGHBOURS:
            occupant = grid.occupant(row + d_row, col + d_col)
            if occupant is None:
                continue
            enemy_id, enemy_index = occupant
            enemy = battle.regiments.get(enemy_id)
            if enemy is None or enemy.player == regiment.player or not enemy.active:
                continue
            enemy_model = enemy.melee_models[enemy_index]
            model.opponent = (enemy_id, enemy_index)
            if enemy_model.opponent is None:
                enemy_model.opponent = (regiment.identifier, index)
                enemy_model.arrived = False
            break


def release(battle, regiment):
    """Unpair and un-cell every model of a regiment that leaves a grid (`LeaveBattleGrid`)."""
    grid = _grid_of(battle, regiment)
    for model in regiment.melee_models:
        if grid is not None and model.cell is not None:
            grid.clear(model.cell)
        model.cell = None
        model.opponent = None
        model.arrived = False
        model.reserve = False


def _grid_of(battle, regiment):
    fight = battle.fights.get(regiment.melee_group)
    return fight.get("grid") if fight else None


def fighting_models(battle, regiment):
    """The regiment's models that may strike this turn: alive, paired, and arrived in their cell."""
    found = []
    for index, model in enumerate(regiment.melee_models):
        if model.opponent is None or not model.arrived:
            continue
        enemy_id, enemy_index = model.opponent
        enemy = battle.regiments.get(enemy_id)
        if enemy is None or not enemy.active or enemy_index >= len(enemy.melee_models):
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
