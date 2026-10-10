"""The close-combat battle grid, as specified in notes/game_rules.md 5.8.

A fight is not "two footprints overlap": it is a shared 17 x 17 cell record (one cell = one model
spacing) seeded around the first unit that was engaged, on which individual models are placed,
paired with individual enemy models, and only then allowed to strike. Frame, seeding, joining,
owner pairing, arrival and side-only cells are all defined in game_rules.md 5.8; the constants below
are the ones named there.

notes/grid_gap_closing.md refines it: fighting starts with an arrival event (never a standing distance test),
back-pairing does not wake a model, the joining procedure re-collects every unpaired model each tick, the owner's
unpaired models move beside engaged comrades as reserves, and a unit that loses a model releases its reserves.

Deviations from the specification: candidate cells are range-checked and seeding clamps instead of
writing out of bounds (5.8 step 2), the placeholders listed in 5.8 step 9 are not modelled, a model that
gets a new opponent is always woken (grid_gap_closing.md 6 recommends it over the original), and the owner's
same-row lower-column case uses the symmetric cells.
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

    def __init__(self, owner_id: str, x: float, y: float, direction: float, width: int) -> None:
        self.owner_id = owner_id
        self.x = x
        self.y = y
        self.direction = direction
        self.width = max(1, width)
        self.cells: dict[Cell, CellOwner] = {}  # (row, col) -> (regiment_id, model uid)
        # regiment identifier -> its direction code on this grid, used to compose a later joiner's
        # own `dir`; a freshly created grid's owner always carries code 0 (engagement_dispersal.md).
        self.direction_codes: dict[str, int] = {owner_id: 0}
        # regiment identifier -> its model count at its last pass, to release reserves after a loss.
        self.model_counts: dict[str, int] = {}

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
    """One tick of placement and pairing for every unit on `grid` (game_rules.md "Battle grid procedure",
    refined by notes/grid_gap_closing.md 2): reserve release, then the owner's pass (or the joining procedure once
    it outnumbers the enemy) and every other unit's joining pass, in member order."""
    _drop_dead(battle, grid)
    _release_reserves(grid, members)
    for regiment in members:
        if regiment.identifier == grid.owner_id and not _owner_outnumbers(regiment, members):
            _pair_owner(battle, grid, regiment, members)
        else:
            _pair_joiner(battle, grid, regiment, members)


def _release_reserves(grid: BattleGrid, members: Sequence["Regiment"]) -> None:
    """A unit that lost a model since its last pass releases every reserve, so they are searched again
    (notes/grid_gap_closing.md 2.3): this is how waiting models move up when a comrade falls."""
    for regiment in members:
        previous = grid.model_counts.get(regiment.identifier)
        if previous is not None and regiment.models < previous:
            for model in regiment.melee_models:
                model.reserve = False
        grid.model_counts[regiment.identifier] = regiment.models


def on_arrival(battle: "Battle", regiment: "Regiment", model: "ModelState") -> None:
    """The walk mover found an awake model within `ARRIVAL_DISTANCE` of its cell (notes/grid_gap_closing.md 0, 3,
    4). Arrival is an event, never a standing distance test: a reserve stops being one (it is searched again
    later); a paired model starts fighting and wakes its opponent if that opponent has none (it is paired back) or
    already names this model but is not fighting yet. Not modelled: the higher-`s_pntval`/war-machine steal."""
    if model.reserve:
        model.reserve = False
        return
    if model.opponent is None:
        return
    model.arrived = True
    enemy_model = _model(battle, model.opponent)
    if enemy_model is None:
        return
    me = (regiment.identifier, model.uid)
    if enemy_model.opponent is None:
        enemy_model.opponent = me
        _wake(enemy_model)
    elif enemy_model.opponent == me and not enemy_model.arrived:
        _wake(enemy_model)


def grab(attacker: "Regiment", model: "ModelState", victim: "ModelState") -> None:
    """A model struck while it has no opponent is grabbed: paired with the striker, woken, no longer a reserve
    (notes/grid_gap_closing.md 4)."""
    if victim.opponent is None:
        victim.opponent = (attacker.identifier, model.uid)
        victim.reserve = False
        _wake(victim)


def unpair_survivor(model: "ModelState", was_its_opponent: bool) -> None:
    """A model whose opponent died (notes/grid_gap_closing.md 2.4): it is no longer paired or fighting and keeps its
    cell. If the dead model was fighting it back it is woken (it re-arrives and is searched again); a ganging
    attacker whose victim was fighting someone else stays at rest."""
    model.opponent = None
    model.arrived = False
    if was_its_opponent:
        _wake(model)


def _wake(model: "ModelState") -> None:
    model.at_rest = False
    model.arrived = False


def _model(battle: "Battle", owner: CellOwner) -> "ModelState | None":
    regiment = battle.regiments.get(owner[0])
    if regiment is None or not regiment.active:
        return None
    index = regiment.index_of(owner[1])
    return regiment.melee_models[index] if index is not None else None


def _owner_outnumbers(owner: "Regiment", members: Sequence["Regiment"]) -> bool:
    enemies = sum(r.models for r in members if r.camp != owner.camp)
    return enemies > 0 and owner.models * 2 > enemies * 3


def _drop_dead(battle: "Battle", grid: BattleGrid) -> None:
    """Free the cells of models that are gone, and unpair whoever still names one (deaths outside the strike path;
    the strike path unpairs at once, `combat.kill_models`)."""
    for cell, (regiment_id, uid) in list(grid.cells.items()):
        regiment = battle.regiments.get(regiment_id)
        if regiment is None or not regiment.active or regiment.index_of(uid) is None:
            grid.clear(cell)
    for regiment in battle.regiments.values():
        for model in regiment.melee_models:
            if model.opponent is not None and _model(battle, model.opponent) is None:
                unpair_survivor(model, was_its_opponent=True)


def _opponent_unit(regiment: "Regiment", members: Sequence["Regiment"]) -> list["Regiment"]:
    """The enemy unit whose models this unit pairs with: its attack target when that unit is on this grid, else
    every enemy unit on it (notes/grid_gap_closing.md 2.1 names "the current opponent unit"; PROVISIONAL: the engine
    keeps no per-unit melee opponent, so a unit without an attack target on the grid takes any enemy unit)."""
    enemies = [other for other in members if other.camp != regiment.camp and other.active]
    target = next((other for other in enemies if other.identifier == regiment.attack_target), None)
    if target is not None and any(model.cell is not None for model in target.melee_models):
        return [target]
    return enemies


def _enemy_models_on_grid(battle: "Battle", grid: BattleGrid, regiment: "Regiment",
                          members: Sequence["Regiment"]) -> list[EnemyModel]:
    """Every placed model of the unit's current opponent unit, with its index."""
    found: list[EnemyModel] = []
    for other in _opponent_unit(regiment, members):
        for index, model in enumerate(other.melee_models):
            if model.cell is not None:
                found.append((other, index, model))
    return found


def _pair_joiner(battle: "Battle", grid: BattleGrid, regiment: "Regiment", members: Sequence["Regiment"]) -> None:
    """The joining procedure (notes/grid_gap_closing.md 2.1): collect up to `frontage` models that are unpaired, not
    reserves and not pausing -- placed or not -- and serve every (model, enemy model) pair nearest first. A model's
    own cell counts as free in its own search. Models left unplaced become reserves beside a comrade."""
    enemies = _enemy_models_on_grid(battle, grid, regiment, members)
    if not enemies:
        return
    positions = regiment.model_positions()
    budget = max(1, regiment.front_rank_models())
    collected = [index for index, model in enumerate(regiment.melee_models)
                 if model.opponent is None and not model.reserve
                 and model.freeze_ticks <= 0 and model.rout_pause_ticks <= 0
                 and not model.pause_just_ended][:budget]
    if not collected:
        return
    # The owner switching to this procedure uses side A (the first candidate row).
    direction = 0 if regiment.identifier == grid.owner_id else None
    pairs = sorted(((math.hypot(*_delta(*positions[index], enemy, enemy_index)), index, enemy.identifier, enemy_index)
                    for index in collected for enemy, enemy_index, _ in enemies),
                   key=lambda item: (item[0], item[1], item[2], item[3]))
    by_id = {enemy.identifier: enemy for enemy, _, _ in enemies}
    placed: set[int] = set()
    for distance, index, enemy_id, enemy_index in pairs:
        if index in placed:
            continue
        enemy = by_id[enemy_id]
        enemy_model = enemy.melee_models[enemy_index]
        if enemy_model.cell is None:
            continue
        model = regiment.melee_models[index]
        side = direction if direction is not None else _direction_for(grid, regiment, enemy, *positions[index])
        if _try_place(grid, regiment, model, enemy, enemy_model, distance, side):
            placed.add(index)
    for index in collected:
        if index not in placed:
            _place_reserve(grid, regiment, index, positions, direction)


def _try_place(grid: BattleGrid, regiment: "Regiment", model: "ModelState", enemy: "Regiment",
               enemy_model: "ModelState", distance: float, side: int) -> bool:
    """Place `model` in the first free candidate cell beside `enemy_model` (its own cell counts as free) and pair
    it; the enemy model is paired back only if it has no opponent, and is not woken (notes/grid_gap_closing.md 2.1,
    4). A model that gets a new opponent is woken, as the report recommends over the original (section 6)."""
    if enemy_model.cell is None:
        return False
    for cell in _candidate_cells(enemy_model.cell, side, distance):
        if cell != model.cell and not grid.free(*cell):
            continue
        _take_cell(grid, regiment, model, cell)
        model.opponent = (enemy.identifier, enemy_model.uid)
        model.reserve = False
        _wake(model)
        if enemy_model.opponent is None:
            enemy_model.opponent = (regiment.identifier, model.uid)
        return True
    return False


def place_next_to_enemy(grid: BattleGrid, regiment: "Regiment", model: "ModelState", px: float, py: float,
                         enemies: Sequence[EnemyModel]) -> bool:
    """Place one model beside the nearest of `enemies` it can reach a candidate cell of (nearest first)."""
    ordered = sorted(enemies, key=lambda item: (
        math.hypot(*_delta(px, py, item[0], item[1])), item[0].identifier, item[1]))
    for enemy, enemy_index, enemy_model in ordered:
        distance = math.hypot(*_delta(px, py, enemy, enemy_index))
        side = _direction_for(grid, regiment, enemy, px, py)
        if _try_place(grid, regiment, model, enemy, enemy_model, distance, side):
            return True
    return False


def _take_cell(grid: BattleGrid, regiment: "Regiment", model: "ModelState", cell: Cell) -> None:
    """Move a model into `cell` (releasing its old one); a changed cell gives it a fresh walk."""
    if model.cell == cell:
        return
    if model.cell is not None:
        grid.clear(model.cell)
    grid.place(cell[0], cell[1], regiment.identifier, model.uid)
    model.cell = cell
    model.distance_budget = 0.0  # the new cell must replace any earlier heading
    _wake(model)


def _place_reserve(grid: BattleGrid, regiment: "Regiment", index: int, positions: Sequence[formation.Point],
                   direction: int | None) -> None:
    """An unplaced joiner model takes a free cell beside the nearest placed comrade that is paired or a reserve
    (a reserve counts 96 units farther) and walks there unpaired (notes/grid_gap_closing.md 2.1 step 5)."""
    model = regiment.melee_models[index]
    px, py = positions[index]
    comrades = sorted(
        ((math.hypot(cx - px, cy - py) + (96 if other.reserve else 0), other_index)
         for other_index, (other, (cx, cy)) in enumerate(zip(regiment.melee_models, positions))
         if other_index != index and other.cell is not None and (other.opponent is not None or other.reserve)),
        key=lambda item: item)
    side = direction if direction is not None else grid.direction_codes.get(regiment.identifier, 0)
    for distance, other_index in comrades:
        comrade_cell = regiment.melee_models[other_index].cell
        assert comrade_cell is not None
        for cell in _candidate_cells(comrade_cell, side, distance):
            if cell != model.cell and not grid.free(*cell):
                continue
            _take_cell(grid, regiment, model, cell)
            model.reserve = True
            return


def _beside_comrade_cells(model_cell: Cell, comrade_cell: Cell) -> list[Cell]:
    """Cells an unpaired owner model tries next to a comrade, the comrade's neighbours on the model's side first
    (notes/grid_gap_closing.md 2.2; rows grow backwards from the owner's front). The original offers nothing for a
    model in the same row on the comrade's lower-column side; this uses the symmetric rule, as the report advises."""
    row, col = comrade_cell
    model_row, model_col = model_cell
    if model_row > row:
        offsets = [(1, 0), (0, 1), (0, -1)] if model_col <= col else [(0, 1), (1, 0)]
    elif model_row < row:
        offsets = [(0, -1), (-1, 0)] if model_col <= col else [(0, 1), (-1, 0)]
    elif model_col > col:
        offsets = [(0, 1), (1, 0), (-1, 0)]
    else:
        offsets = [(0, -1), (-1, 0), (1, 0)]
    return [(row + d_row, col + d_col) for d_row, d_col in offsets]


def _pair_owner(battle: "Battle", grid: BattleGrid, regiment: "Regiment", members: Sequence["Regiment"]) -> None:
    """The grid owner's pass (notes/grid_gap_closing.md 2.2). Each placed, unpaired, non-reserve model, in model
    order, pairs with the first at-rest placed model of the current opponent unit orthogonally next to it (and is
    woken; the enemy is paired back if it has none). The others move beside the nearest paired, at-rest comrade:
    all (model, comrade) pairs nearest first, each model at most once per tick; it becomes a reserve, walking to
    the new cell or standing in its own."""
    enemies = {(enemy.identifier, model.uid): (enemy, model)
               for enemy in _opponent_unit(regiment, members) for model in enemy.melee_models}
    enemy_order = [key for enemy in _opponent_unit(regiment, members)
                   for key in ((enemy.identifier, model.uid) for model in enemy.melee_models)]
    unpaired: list[int] = []
    for index, model in enumerate(regiment.melee_models):
        if model.cell is None or model.opponent is not None or model.reserve:
            continue
        row, col = model.cell
        adjacent = {grid.occupant(row + d_row, col + d_col) for d_row, d_col in _NEIGHBOURS}
        choice = next((key for key in enemy_order if key in adjacent
                       and enemies[key][1].at_rest and enemies[key][1].cell is not None), None)
        if choice is None:
            unpaired.append(index)
            continue
        _, enemy_model = enemies[choice]
        model.opponent = choice
        _wake(model)
        if enemy_model.opponent is None:
            enemy_model.opponent = (regiment.identifier, model.uid)  # paired back, not woken
    if not unpaired:
        return
    positions = regiment.model_positions()
    comrades = [index for index, model in enumerate(regiment.melee_models)
                if model.opponent is not None and model.cell is not None and model.at_rest]
    pairs = sorted((math.hypot(positions[i][0] - positions[c][0], positions[i][1] - positions[c][1]), i, c)
                   for i in unpaired for c in comrades)
    moved: set[int] = set()
    for _, index, comrade in pairs:
        if index in moved:
            continue
        model = regiment.melee_models[index]
        comrade_cell = regiment.melee_models[comrade].cell
        assert model.cell is not None and comrade_cell is not None
        for cell in _beside_comrade_cells(model.cell, comrade_cell):
            if cell != model.cell and not grid.free(*cell):
                continue
            _take_cell(grid, regiment, model, cell)
            model.reserve = True
            moved.add(index)
            break


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
    fight = battle.fights.get(regiment.melee_group) if regiment.melee_group is not None else None
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
