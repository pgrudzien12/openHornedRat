"""BDD scenarios for the close-combat battle grid (whshr.battle_grid), per docs/testing.md.

The rules exercised here are the ones traced in notes/game_rules.md 5.7: cells carry a side and not a
unit, models must hold a cell and arrive in it before they fight, a joining unit places at most its
frontage per tick, and grids never interact with each other or with terrain.
"""
import unittest

from whshr import battle_grid, combat
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def _regiment(identifier, x, y, side, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    direction = kwargs.pop("direction", 0)
    kwargs.setdefault("speed_per_tick", 1.5)
    return Regiment(identifier, identifier, x, y, direction, side, models=models, ranks=ranks, **kwargs)


def _grid(battle, regiment):
    return battle.fights[regiment.melee_group]["grid"]


class GridSeedingTests(unittest.TestCase):
    def setUp(self):
        self.defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)

    def test_given_a_fresh_contact_when_the_grid_is_seeded_then_the_engaged_unit_holds_its_own_cells(self):
        self.battle.tick()

        grid = _grid(self.battle, self.defender)
        seeded = [identifier for identifier, _ in grid.cells.values()]
        self.assertEqual(seeded.count(grid.owner_id), self.battle.regiments[grid.owner_id].models)

    def test_given_a_seeded_owner_when_its_models_are_checked_then_they_hold_cells_at_rest_not_yet_fighting(self):
        # The grid is built around the owner's existing model positions, so they need no walk-in; but standing in
        # a cell is not fighting: an owner model fights only once woken (notes/grid_gap_closing.md 0, 3).
        self.battle.tick()

        owner = self.battle.regiments[_grid(self.battle, self.defender).owner_id]
        self.assertTrue(all(model.cell is not None and model.at_rest for model in owner.melee_models))
        self.assertFalse(any(model.arrived for model in owner.melee_models))

    def test_given_an_at_rest_owner_in_melee_when_its_slot_changes_then_it_stays_put(self):
        self.battle.tick()
        owner = self.battle.regiments[_grid(self.battle, self.defender).owner_id]
        model = owner.melee_models[0]
        self.assertTrue(model.at_rest)
        before = owner.positions[0]
        owner.x += 20

        self.battle._advance_models(owner, 1)

        self.assertEqual(owner.positions[0], before)
        self.assertTrue(model.at_rest)

    def test_given_a_grid_when_cells_are_stamped_then_they_identify_a_regiment_not_just_a_side(self):
        # The original stamps only the side; this engine keeps the regiment id so a model can be
        # found again, but two allied units must still share one undivided pool of cells.
        self.battle.tick()

        grid = _grid(self.battle, self.defender)
        for (row, col), (identifier, index) in grid.cells.items():
            self.assertTrue(battle_grid.in_bounds(row, col))
            self.assertLess(index, self.battle.regiments[identifier].models)


class JoiningTests(unittest.TestCase):
    def setUp(self):
        self.defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5, models=12, ranks=3)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)

    def test_given_a_joining_unit_when_one_tick_passes_then_at_most_its_frontage_is_placed(self):
        self.battle.tick()

        grid = _grid(self.battle, self.defender)
        joiner = self.attacker if grid.owner_id != self.attacker.identifier else self.defender
        placed = sum(1 for identifier, _ in grid.cells.values() if identifier == joiner.identifier)
        self.assertLessEqual(placed, joiner.front_rank_models())

    def test_given_a_joining_unit_when_it_has_not_reached_its_cell_then_it_does_not_fight(self):
        self.battle.tick()

        grid = _grid(self.battle, self.defender)
        joiner = self.attacker if grid.owner_id != self.attacker.identifier else self.defender
        self.assertEqual(battle_grid.fighting_models(self.battle, joiner), [])

    def test_given_a_joining_unit_when_enough_ticks_pass_then_its_models_arrive_and_pair(self):
        for _ in range(combat.SEGMENT_TICKS * 3):
            self.battle.tick()

        grid = _grid(self.battle, self.defender)
        joiner = self.attacker if grid.owner_id != self.attacker.identifier else self.defender
        self.assertTrue(battle_grid.fighting_models(self.battle, joiner))

    def test_given_a_fresh_cell_when_a_joiner_has_a_stale_heading_then_it_reaims(self):
        self.battle.tick()
        grid = _grid(self.battle, self.defender)
        joiner = self.attacker if grid.owner_id != self.attacker.identifier else self.defender
        owner = self.battle.regiments[grid.owner_id]
        index = next(i for i, model in enumerate(joiner.melee_models) if model.cell is None)
        model = joiner.melee_models[index]
        px, py = joiner.positions[index]
        model.at_rest = True
        model.current_speed = 5.0
        model.distance_budget = 100.0
        model.heading_x, model.heading_y = 1.0, 0.0

        placed = battle_grid.place_next_to_enemy(
            grid, joiner, model, px, py, [(owner, 0, owner.melee_models[0])])

        self.assertTrue(placed)
        self.assertFalse(model.at_rest)
        self.assertEqual(model.current_speed, 5.0)
        self.assertEqual(model.distance_budget, 0.0)
        target_x, target_y = grid.cell_world(*model.cell)
        distance = ((target_x - px) ** 2 + (target_y - py) ** 2) ** 0.5
        self.assertGreater(distance, 3)

        self.battle._advance_models(joiner, 1)

        self.assertAlmostEqual(model.heading_x, (target_x - px) / distance)
        self.assertAlmostEqual(model.heading_y, (target_y - py) / distance)


class RepairingTests(unittest.TestCase):
    """game_rules.md "Battle grid procedure" steps 4, 6 and 8: a placed model of either side whose opponent died
    takes an orthogonally adjacent enemy again, and a model holding a cell it has not reached walks to it."""

    def setUp(self):
        self.defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5, models=12, ranks=3)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)
        for _ in range(combat.SEGMENT_TICKS * 3):
            self.battle.tick()
        self.grid = _grid(self.battle, self.defender)
        self.owner = self.battle.regiments[self.grid.owner_id]
        self.joiner = self.attacker if self.owner is self.defender else self.defender

    def test_given_a_placed_joiner_model_without_opponent_when_an_enemy_is_adjacent_then_it_pairs_again(self):
        model = next(m for m in self.joiner.melee_models if m.cell is not None and m.opponent is not None)
        model.opponent = None

        battle_grid.update(self.battle, self.joiner.melee_group, self.grid, [self.owner, self.joiner])

        self.assertIsNotNone(model.opponent)
        enemy_id, enemy_uid = model.opponent
        enemy = self.battle.regiments[enemy_id]
        enemy_index = enemy.index_of(enemy_uid)
        assert enemy_index is not None
        enemy_model = enemy.melee_models[enemy_index]
        (row, col), (enemy_row, enemy_col) = model.cell, enemy_model.cell
        self.assertEqual(abs(row - enemy_row) + abs(col - enemy_col), 1)

    def test_given_a_model_at_rest_away_from_its_cell_when_nothing_wakes_it_then_it_is_not_re_tested(self):
        # notes/grid_gap_closing.md 0: at-rest models in a melee are not stepped or re-tested.
        index, model = next((i, m) for i, m in enumerate(self.owner.melee_models) if m.cell is not None)
        wx, wy = self.grid.cell_world(*model.cell)
        self.owner.positions[index] = (wx + 6.0, wy)
        model.at_rest = True

        self.battle._advance_models(self.owner, 1)

        self.assertEqual(self.owner.positions[index], (wx + 6.0, wy))


class ArrivalEventTests(unittest.TestCase):
    """notes/grid_gap_closing.md 0, 2.4, 3, 4 and the section 8 vectors: fighting starts with an arrival event;
    back-pairing does not wake; arrival, demotion and grabbing do."""

    def setUp(self):
        self.goblins = _regiment("gob", 0, 0, Side.ENEMY, models=1, ranks=1)
        self.cavalry = _regiment("cav", 0, 40, Side.PLAYER, models=2, ranks=1)
        self.battle = Battle(1000, 1000, [self.goblins, self.cavalry], seed=0)
        self.goblins.model_positions()
        self.cavalry.model_positions()
        self.grid = battle_grid.BattleGrid("gob", 0, 0, 0, 1)
        self.grid.seed(self.goblins)
        self.g1 = self.goblins.melee_models[0]
        self.c1, self.c2 = self.cavalry.melee_models

    def _place_c1(self):
        placed = battle_grid.place_next_to_enemy(self.grid, self.cavalry, self.c1, 0, 40,
                                                  [(self.goblins, 0, self.g1)])
        self.assertTrue(placed)

    def test_given_an_at_rest_defender_when_a_far_joiner_is_placed_beside_it_then_it_is_paired_back_but_not_fighting(self):
        self._place_c1()

        self.assertEqual(self.g1.opponent, ("cav", self.c1.uid))
        self.assertTrue(self.g1.at_rest)
        self.assertFalse(self.g1.arrived)
        self.assertEqual(battle_grid.fighting_models(self.battle, self.goblins), [])

    def test_given_a_walking_joiner_when_it_arrives_then_it_fights_and_wakes_its_opponent(self):
        self._place_c1()

        battle_grid.on_arrival(self.battle, self.cavalry, self.c1)

        self.assertTrue(self.c1.arrived)
        self.assertFalse(self.g1.at_rest)
        self.assertFalse(self.g1.arrived)  # it re-arrives in its cell on its next movement step

    def test_given_a_fighting_pair_when_one_dies_then_the_survivor_is_woken_unpaired_and_keeps_its_cell(self):
        self._place_c1()
        battle_grid.on_arrival(self.battle, self.cavalry, self.c1)
        self.g1.arrived = self.g1.at_rest = True
        cell = self.g1.cell

        combat.kill_models(self.cavalry, [0], battle=self.battle)

        self.assertIsNone(self.g1.opponent)
        self.assertFalse(self.g1.at_rest)
        self.assertFalse(self.g1.arrived)
        self.assertEqual(self.g1.cell, cell)

    def test_given_a_ganging_attacker_when_its_victim_dies_then_it_is_unpaired_but_stays_at_rest(self):
        self.c2.opponent = ("gob", self.g1.uid)
        self.c2.arrived = self.c2.at_rest = True
        self.g1.opponent = ("cav", self.c1.uid)  # the victim fights someone else

        combat.kill_models(self.goblins, [0], battle=self.battle)

        self.assertIsNone(self.c2.opponent)
        self.assertTrue(self.c2.at_rest)

    def test_given_an_unpaired_model_when_it_is_struck_then_it_is_grabbed_and_woken(self):
        self.g1.reserve = True

        battle_grid.grab(self.cavalry, self.c1, self.g1)

        self.assertEqual(self.g1.opponent, ("cav", self.c1.uid))
        self.assertFalse(self.g1.at_rest)
        self.assertFalse(self.g1.reserve)

    def test_given_a_reserve_when_it_arrives_then_it_stops_being_a_reserve_without_fighting(self):
        self.c2.reserve = True

        battle_grid.on_arrival(self.battle, self.cavalry, self.c2)

        self.assertFalse(self.c2.reserve)
        self.assertFalse(self.c2.arrived)


class GapClosingTests(unittest.TestCase):
    """notes/grid_gap_closing.md 2.2 and 2.3: the owner's unpaired models move beside paired comrades; a unit that
    loses a model releases its reserves."""

    def test_given_an_owner_model_behind_a_comrade_in_its_own_candidate_cell_then_it_stays_as_a_reserve(self):
        self.assertEqual(battle_grid._beside_comrade_cells((9, 8), (8, 8))[0], (9, 8))

    def test_given_an_owner_model_behind_on_the_higher_column_side_then_it_tries_the_side_cell_first(self):
        self.assertEqual(battle_grid._beside_comrade_cells((10, 9), (8, 8)), [(8, 9), (9, 8)])

    def test_given_an_owner_model_in_the_same_row_on_the_lower_column_side_then_it_gets_the_symmetric_cells(self):
        self.assertEqual(battle_grid._beside_comrade_cells((8, 6), (8, 8)), [(8, 7), (7, 8), (9, 8)])

    def test_given_a_unit_that_lost_a_model_when_the_grid_updates_then_its_reserves_are_released(self):
        defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5)
        attacker = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5, models=12, ranks=3)
        battle = Battle(1000, 1000, [defender, attacker], seed=0)
        battle.tick()
        grid = _grid(battle, defender)
        members = [defender, attacker]
        battle_grid.update(battle, defender.melee_group, grid, members)
        attacker.melee_models[-1].reserve = True
        combat.kill_models(attacker, [0], battle=battle)

        battle_grid._release_reserves(grid, members)

        self.assertFalse(any(model.reserve for model in attacker.melee_models))


class PileOnTests(unittest.TestCase):
    """game_rules.md 5.7: several units share one grid, one cell pool and one pair of tallies."""

    def setUp(self):
        self.enemy = _regiment("enemy", 0, 0, Side.ENEMY, initiative=5, models=20, ranks=4)
        self.first = _regiment("first", 0, 16, Side.PLAYER, initiative=5)
        self.second = _regiment("second", 16, 0, Side.PLAYER, initiative=5)
        self.battle = Battle(1000, 1000, [self.enemy, self.first, self.second], seed=0)
        for _ in range(combat.SEGMENT_TICKS * 3):
            self.battle.tick()

    def test_given_two_allies_touching_one_enemy_when_they_engage_then_they_share_one_grid(self):
        self.assertEqual(self.first.melee_group, self.second.melee_group)
        self.assertEqual(self.first.melee_group, self.enemy.melee_group)

    def test_given_allies_on_one_grid_when_cells_are_claimed_then_both_draw_from_the_same_pool(self):
        grid = _grid(self.battle, self.first)
        owners = {identifier for identifier, _ in grid.cells.values()}
        self.assertEqual(owners, {"enemy", "first", "second"})

    def test_given_a_defender_model_when_several_attackers_reach_it_then_only_one_is_its_opponent(self):
        # game_rules.md 5.2: several models may attack the same enemy model, but only the first to
        # reach it is its designated opponent (the one that fights without the ganging-up +1 WS).
        attackers_per_target = {}
        for regiment in (self.first, self.second):
            for index, model in enumerate(regiment.melee_models):
                if model.opponent is not None:
                    attackers_per_target.setdefault(model.opponent, []).append(
                        (regiment.identifier, index))

        self.assertTrue(attackers_per_target)
        for (target_id, target_index), attackers in attackers_per_target.items():
            back_pointer = self.battle.regiments[target_id].melee_models[target_index].opponent
            designated = [a for a in attackers if a == back_pointer]
            self.assertLessEqual(len(designated), 1)


class CasualtyIdentityTests(unittest.TestCase):
    def setUp(self):
        self.defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)
        self.battle.tick()

    def test_given_a_casualty_when_it_is_removed_then_the_survivors_keep_their_pairings(self):
        grid = _grid(self.battle, self.defender)
        owner = self.battle.regiments[grid.owner_id]
        before = [model.opponent for model in owner.melee_models[1:]]

        combat.kill_models(owner, [0], battle=self.battle)

        self.assertEqual([model.opponent for model in owner.melee_models], before)
        self.assertEqual(len(owner.melee_models), owner.models)

    def test_given_a_casualty_when_it_is_removed_then_its_cell_is_freed(self):
        grid = _grid(self.battle, self.defender)
        owner = self.battle.regiments[grid.owner_id]
        cell = owner.melee_models[0].cell

        combat.kill_models(owner, [0], battle=self.battle)

        self.assertNotIn(cell, grid.cells)

    def test_given_a_casualty_when_it_is_removed_then_enemies_stop_pointing_at_it(self):
        grid = _grid(self.battle, self.defender)
        owner = self.battle.regiments[grid.owner_id]
        dead_uid = owner.melee_models[0].uid

        combat.kill_models(owner, [0], battle=self.battle)

        self.assertIsNone(owner.index_of(dead_uid))
        for regiment in self.battle.regiments.values():
            for model in regiment.melee_models:
                if model.opponent and model.opponent[0] == owner.identifier:
                    self.assertIsNotNone(owner.index_of(model.opponent[1]))

    def test_given_a_model_killed_by_shooting_when_it_dies_then_its_attackers_are_released(self):
        # Shooting picks its victims at random rather than naming them, but a model shot out of a
        # melee still has to release whoever was fighting it.
        grid = _grid(self.battle, self.defender)
        owner = self.battle.regiments[grid.owner_id]

        combat.apply_casualties(owner, owner.models, self.battle.rng, self.battle)

        for regiment in self.battle.regiments.values():
            for model in regiment.melee_models:
                self.assertNotEqual(
                    model.opponent[0] if model.opponent else None, owner.identifier)

    def test_given_a_casualty_when_survivors_shift_down_then_their_pairings_still_name_the_same_models(self):
        # Pairings are stored by identity, not by list position, so removing an early model must not
        # silently re-point a survivor's pairing at its neighbour.
        grid = _grid(self.battle, self.defender)
        owner = self.battle.regiments[grid.owner_id]
        before = {model.uid: model.opponent for model in owner.melee_models[1:]}

        combat.kill_models(owner, [0], battle=self.battle)

        self.assertEqual({model.uid: model.opponent for model in owner.melee_models}, before)


class DirectionalCandidateCellTests(unittest.TestCase):
    """engagement_dispersal.md "Direction-indexed joiner candidate cells": the candidate cell order
    around a defending model is a fixed table selected by the joiner's approach direction, not a
    runtime distance sort."""

    def setUp(self):
        # A lone defending model, so its neighbouring cells start out empty and the candidate order
        # can be read off without any of the defender's own formation getting in the way.
        self.defender = _regiment("def", 0, 0, Side.ENEMY, initiative=5, direction=0, models=1, ranks=1)
        self.defender.model_positions()
        self.grid = battle_grid.BattleGrid(
            self.defender.identifier, self.defender.x, self.defender.y,
            self.defender.direction, self.defender.front_rank_models())
        self.grid.seed(self.defender)
        self.target_index = 0
        self.target = self.defender.melee_models[0]
        self.assertEqual(self.target.cell, (8, 8))

    def _joiner(self, approach_x, approach_y, identifier="joiner"):
        regiment = _regiment(identifier, approach_x, approach_y, Side.PLAYER, initiative=5, models=1, ranks=1)
        regiment.model_positions()
        return regiment

    def _place(self, approach_x, approach_y, identifier="joiner"):
        regiment = self._joiner(approach_x, approach_y, identifier)
        model = regiment.melee_models[0]
        placed = battle_grid.place_next_to_enemy(
            self.grid, regiment, model, approach_x, approach_y,
            [(self.defender, self.target_index, self.target)])
        self.assertTrue(placed)
        row, col = model.cell
        return row - 8, col - 8

    def test_given_a_front_approach_when_a_joiner_places_then_it_takes_the_cell_ahead_of_the_front_rank(self):
        self.assertEqual(self._place(0, 40), (-1, 0))

    def test_given_a_rear_approach_when_a_joiner_places_then_it_takes_the_cell_behind_the_rear_rank(self):
        self.assertEqual(self._place(0, -40), (1, 0))

    def test_given_one_flank_approach_when_a_joiner_places_then_it_takes_the_cell_on_that_side(self):
        self.assertEqual(self._place(40, 0), (0, 1))

    def test_given_the_other_flank_approach_when_a_joiner_places_then_it_takes_the_cell_on_that_side(self):
        self.assertEqual(self._place(-40, 0), (0, -1))

    def test_given_a_front_approach_when_the_first_cell_is_taken_then_it_falls_back_in_table_order(self):
        self.grid.place(7, 8, "blocker", 0)  # occupies the (-1, 0) cell ahead of the target

        self.assertEqual(self._place(0, 40), (0, -1))  # second entry of the dir-1 row

    def test_given_a_distant_joiner_when_the_first_two_cells_are_taken_then_it_finds_no_candidate(self):
        # Farther than NEAR_DISTANCE: only the row's first two entries are offered, so once both are
        # occupied placement fails even though the third entry would otherwise be free.
        self.grid.place(7, 8, "blocker_a", 0)  # dir 1, 1st entry (-1, 0)
        self.grid.place(8, 7, "blocker_b", 0)  # dir 1, 2nd entry (0, -1)
        regiment = self._joiner(0, 40)
        model = regiment.melee_models[0]

        placed = battle_grid.place_next_to_enemy(
            self.grid, regiment, model, 0, 40, [(self.defender, self.target_index, self.target)])

        self.assertFalse(placed)

    def test_given_a_near_joiner_when_the_first_two_cells_are_taken_then_it_still_finds_a_third(self):
        self.grid.place(7, 8, "blocker_a", 0)  # dir 1, 1st entry (-1, 0)
        self.grid.place(8, 7, "blocker_b", 0)  # dir 1, 2nd entry (0, -1)
        near_x, near_y = 0, 8  # well within NEAR_DISTANCE (18) of the target model
        regiment = self._joiner(near_x, near_y)
        model = regiment.melee_models[0]

        placed = battle_grid.place_next_to_enemy(
            self.grid, regiment, model, near_x, near_y, [(self.defender, self.target_index, self.target)])

        self.assertTrue(placed)
        row, col = model.cell
        self.assertEqual((row - 8, col - 8), (0, 1))  # dir 1's 3rd entry


class SeparateGridTests(unittest.TestCase):
    """game_rules.md 5.7: separate fights never check proximity to each other, even when their cell
    areas overlap in world space."""

    def test_given_two_fights_close_together_when_they_run_then_each_keeps_its_own_grid(self):
        # Far enough apart that the two fights never touch, but each pair engages on the spot.
        pairs = [
            _regiment("a1", 0, 0, Side.ENEMY, initiative=5, speed_per_tick=0.0),
            _regiment("a2", 0, 14, Side.PLAYER, initiative=5, speed_per_tick=0.0),
            _regiment("b1", 400, 0, Side.ENEMY, initiative=5, speed_per_tick=0.0),
            _regiment("b2", 400, 14, Side.PLAYER, initiative=5, speed_per_tick=0.0),
        ]
        battle = Battle(2000, 2000, pairs, seed=0)
        for _ in range(combat.SEGMENT_TICKS):
            battle.tick()

        groups = {regiment.melee_group for regiment in pairs if regiment.melee_group}
        self.assertEqual(len(groups), 2)
        first, second = (battle.fights[group]["grid"] for group in sorted(groups))
        self.assertIsNot(first, second)
        # Both grids index the same 0..16 cell space; they never consult one another.
        self.assertTrue(set(first.cells) & set(second.cells))


if __name__ == "__main__":
    unittest.main()


class EngagementAsymmetryTests(unittest.TestCase):
    """notes/game_rules.md "Why the charger disperses and the charged unit stands still"."""

    def setUp(self):
        self.defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5, models=12, ranks=3)
        self.attacker = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5, models=12, ranks=3)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)

    def _owner(self):
        return self.battle.regiments[_grid(self.battle, self.defender).owner_id]

    def _by_uid(self, regiment):
        return {model.uid: pos for model, pos in zip(regiment.melee_models, regiment.positions)}

    def test_given_a_defender_when_the_fight_continues_then_its_paired_models_never_move(self):
        # Paired owner models fight where they were seeded; only unpaired ones move up beside an engaged comrade
        # (notes/grid_gap_closing.md 2.2).
        self.battle.tick()
        owner = self._owner()
        before = self._by_uid(owner)
        always_paired = {model.uid for model in owner.melee_models}

        for _ in range(combat.SEGMENT_TICKS * 6):
            self.battle.tick()
            always_paired &= {model.uid for model in owner.melee_models if model.opponent is not None}
            now = self._by_uid(owner)
            for uid in always_paired:
                self.assertEqual(now[uid], before[uid])

        self.assertTrue(battle_grid.fighting_models(self.battle, owner))

    def test_given_a_charge_when_it_connects_then_the_charger_models_do_walk_to_new_cells(self):
        self.battle.tick()
        joiner = self.attacker if self._owner() is self.defender else self.defender
        before = self._by_uid(joiner)

        for _ in range(combat.SEGMENT_TICKS):
            self.battle.tick()

        self.assertNotEqual(self._by_uid(joiner), before)

    def test_given_the_same_blocked_cells_when_approached_from_different_sides_then_the_fallback_order_differs(self):
        fallbacks = set()
        for approach in ((0, 8), (0, -8), (8, 0), (-8, 0)):  # all within the near range
            defender = _regiment("def", 0, 0, Side.ENEMY, initiative=5, models=1, ranks=1)
            defender.model_positions()
            grid = battle_grid.BattleGrid("def", 0, 0, 0, 1)
            grid.seed(defender)
            target = defender.melee_models[0]
            chosen = []
            for n in range(4):
                joiner = _regiment("j%d" % n, approach[0], approach[1], Side.PLAYER, initiative=5, models=1, ranks=1)
                joiner.model_positions()
                model = joiner.melee_models[0]
                self.assertTrue(battle_grid.place_next_to_enemy(
                    grid, joiner, model, approach[0], approach[1], [(defender, 0, target)]))
                chosen.append((model.cell[0] - 8, model.cell[1] - 8))
            self.assertEqual(len(set(chosen)), 4)  # four distinct neighbouring cells
            fallbacks.add(tuple(chosen))

        self.assertEqual(len(fallbacks), 4)  # each approach direction wraps in its own order


class TimedPauseInMeleeTests(unittest.TestCase):
    """notes/bf003_playtest_fireball_grid_pursuit.md 4: the timed pause counts down every tick for every model."""

    def _melee_unit(self):
        regiment = _regiment("aaa_rest", 0, 0, Side.ENEMY, initiative=5)
        enemy = _regiment("bbb_foe", 0, 14, Side.PLAYER, initiative=5)
        battle = Battle(1000, 1000, [regiment, enemy], seed=0)
        regiment.model_positions()
        regiment.in_melee = True
        return battle, regiment

    def test_given_an_at_rest_model_in_melee_with_a_pause_when_a_tick_passes_then_the_pause_falls_by_one(self):
        battle, regiment = self._melee_unit()
        model = regiment.melee_models[0]
        model.at_rest, model.freeze_ticks = True, 3

        battle._advance_models(regiment, 1)

        self.assertEqual(model.freeze_ticks, 2)

    def test_given_an_at_rest_model_in_melee_with_a_pause_of_three_when_three_ticks_pass_then_it_is_no_longer_pausing(self):
        battle, regiment = self._melee_unit()
        model = regiment.melee_models[0]
        model.at_rest, model.freeze_ticks = True, 3

        for _ in range(3):
            battle._advance_models(regiment, 1)

        self.assertEqual(model.freeze_ticks, 0)
        self.assertTrue(model.at_rest)

    def test_given_an_at_rest_model_in_melee_with_a_rout_pause_when_ticks_pass_then_it_also_expires(self):
        battle, regiment = self._melee_unit()
        model = regiment.melee_models[0]
        model.at_rest, model.rout_pause_ticks = True, 2

        for _ in range(2):
            battle._advance_models(regiment, 1)

        self.assertEqual(model.rout_pause_ticks, 0)

    def test_given_a_unit_whose_models_pause_at_rest_in_melee_when_the_pauses_expire_then_every_model_is_placed(self):
        defender = _regiment("aaa_def", 0, 0, Side.ENEMY, initiative=5, models=9, ranks=3)
        charger = _regiment("bbb_att", 0, 14, Side.PLAYER, initiative=5, models=9, ranks=3)
        battle = Battle(1000, 1000, [defender, charger], seed=0)
        battle.tick()
        grid = _grid(battle, defender)
        joiner = charger if grid.owner_id != charger.identifier else defender
        self.assertTrue(joiner.in_melee)
        for number, model in enumerate(joiner.melee_models):
            model.at_rest, model.freeze_ticks = True, 2 + number % 6
            model.cell, model.opponent, model.reserve = None, None, False

        for _ in range(8 + combat.SEGMENT_TICKS):
            battle.tick()

        self.assertTrue(all(model.freeze_ticks == 0 for model in joiner.melee_models))
        self.assertTrue(all(model.cell is not None for model in joiner.melee_models))
