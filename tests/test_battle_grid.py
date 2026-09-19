"""BDD scenarios for the close-combat battle grid (whshr.battle_grid), per docs/testing.md.

The rules exercised here are the ones traced in notes/game_rules.md 5.7: cells carry a side and not a
unit, models must hold a cell and arrive in it before they fight, a joining unit places at most its
frontage per tick, and grids never interact with each other or with terrain.
"""
import unittest

from whshr import battle_grid, combat
from whshr.engine import Battle, Regiment


def _regiment(identifier, x, y, player, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    direction = kwargs.pop("direction", 0)
    kwargs.setdefault("speed_per_tick", 1.5)
    return Regiment(identifier, identifier, x, y, direction, player, models=models, ranks=ranks, **kwargs)


def _grid(battle, regiment):
    return battle.fights[regiment.melee_group]["grid"]


class GridSeedingTests(unittest.TestCase):
    def setUp(self):
        self.defender = _regiment("aaa_def", 0, 0, False, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, True, initiative=5)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)

    def test_given_a_fresh_contact_when_the_grid_is_seeded_then_the_engaged_unit_holds_its_own_cells(self):
        self.battle.tick()

        grid = _grid(self.battle, self.defender)
        seeded = [identifier for identifier, _ in grid.cells.values()]
        self.assertEqual(seeded.count(grid.owner_id), self.battle.regiments[grid.owner_id].models)

    def test_given_a_seeded_owner_when_its_models_are_checked_then_they_are_already_in_their_cells(self):
        # The grid is built around the owner's existing model positions, so they need no walk-in.
        self.battle.tick()

        owner = self.battle.regiments[_grid(self.battle, self.defender).owner_id]
        self.assertTrue(all(model.arrived for model in owner.melee_models))

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
        self.defender = _regiment("aaa_def", 0, 0, False, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, True, initiative=5, models=12, ranks=3)
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


class PileOnTests(unittest.TestCase):
    """game_rules.md 5.7: several units share one grid, one cell pool and one pair of tallies."""

    def setUp(self):
        self.enemy = _regiment("enemy", 0, 0, False, initiative=5, models=20, ranks=4)
        self.first = _regiment("first", 0, 16, True, initiative=5)
        self.second = _regiment("second", 16, 0, True, initiative=5)
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
        self.defender = _regiment("aaa_def", 0, 0, False, initiative=5)
        self.attacker = _regiment("bbb_att", 0, 14, True, initiative=5)
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

        combat.kill_models(owner, [0], battle=self.battle)

        for regiment in self.battle.regiments.values():
            for model in regiment.melee_models:
                if model.opponent and model.opponent[0] == owner.identifier:
                    self.assertLess(model.opponent[1], owner.models)


class SeparateGridTests(unittest.TestCase):
    """game_rules.md 5.7: separate fights never check proximity to each other, even when their cell
    areas overlap in world space."""

    def test_given_two_fights_close_together_when_they_run_then_each_keeps_its_own_grid(self):
        # Far enough apart that the two fights never touch, but each pair engages on the spot.
        pairs = [
            _regiment("a1", 0, 0, False, initiative=5, speed_per_tick=0.0),
            _regiment("a2", 0, 14, True, initiative=5, speed_per_tick=0.0),
            _regiment("b1", 400, 0, False, initiative=5, speed_per_tick=0.0),
            _regiment("b2", 400, 14, True, initiative=5, speed_per_tick=0.0),
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
