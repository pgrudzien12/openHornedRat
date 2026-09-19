"""BDD scenarios for the per-skirmish logger and its grid invariant checks (whshr.skirmish_log),
per docs/testing.md."""
import tempfile
import unittest
from pathlib import Path

from whshr import battle_grid, combat, skirmish_log
from whshr.engine import Battle, Regiment


def _regiment(identifier, x, y, player, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    direction = kwargs.pop("direction", 0)
    kwargs.setdefault("speed_per_tick", 1.5)
    kwargs.setdefault("initiative", 5)
    return Regiment(identifier, identifier, x, y, direction, player, models=models, ranks=ranks, **kwargs)


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.defender = _regiment("aaa_def", 0, 0, False)
        self.attacker = _regiment("bbb_att", 0, 14, True)
        self.battle = Battle(1000, 1000, [self.defender, self.attacker], seed=0)
        self.logger = skirmish_log.SkirmishLogger(self.directory, "BF001")

    def _run(self, ticks):
        for _ in range(ticks):
            self.battle.tick()
            self.logger.observe(self.battle)
        self.logger.close(self.battle)

    def _text(self):
        return "\n".join(path.read_text(encoding="utf-8") for path in sorted(self.directory.glob("*.log")))


class SkirmishFileTests(_Fixture):
    def test_given_a_fight_when_it_forms_then_one_file_is_written_for_it(self):
        self._run(combat.SEGMENT_TICKS * 2)

        files = sorted(self.directory.glob("*.log"))
        self.assertEqual(len(files), 1)
        self.assertIn("skirmish-", files[0].name)

    def test_given_a_skirmish_file_when_it_opens_then_it_names_the_build_and_the_participants(self):
        self._run(combat.SEGMENT_TICKS)

        text = self._text()
        self.assertIn("build:", text)
        self.assertIn("grid owner:", text)
        self.assertIn("aaa_def", text)
        self.assertIn("bbb_att", text)

    def test_given_a_fight_in_progress_when_logged_then_it_draws_the_cell_map(self):
        self._run(combat.SEGMENT_TICKS)

        text = self._text()
        self.assertIn("grid @ tick", text)
        self.assertIn("legend:", text)

    def test_given_a_strike_when_logged_then_every_fighting_model_has_its_rolls(self):
        self._run(combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 2)

        text = self._text()
        self.assertIn("strikes", text)
        self.assertIn("need ", text)  # the per-model target numbers line

    def test_given_a_clean_fight_when_it_is_logged_then_no_anomaly_is_reported(self):
        self._run(combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 3)

        self.assertEqual(self.logger.anomalies, 0)
        self.assertNotIn("ANOMALY", self._text())

    def test_given_no_log_directory_when_observing_then_nothing_is_written_and_nothing_fails(self):
        logger = skirmish_log.SkirmishLogger(None, "BF001")
        for _ in range(combat.SEGMENT_TICKS):
            self.battle.tick()
            logger.observe(self.battle)
        logger.close(self.battle)

        self.assertEqual(list(self.directory.glob("*.log")), [])


class GridCheckTests(_Fixture):
    """`check_grid` is the diagnostic that has to actually catch a broken grid, so each invariant is
    tested by breaking it deliberately."""

    def setUp(self):
        super().setUp()
        for _ in range(combat.SEGMENT_TICKS * 2):
            self.battle.tick()
        self.group = self.defender.melee_group
        self.grid = self.battle.fights[self.group]["grid"]
        self.members = [self.defender, self.attacker]

    def test_given_a_consistent_grid_when_checked_then_there_are_no_problems(self):
        self.assertEqual(skirmish_log.check_grid(self.battle, self.grid, self.members), [])

    def test_given_a_pairing_with_a_distant_model_when_checked_then_it_is_reported(self):
        paired = next(m for m in self.defender.melee_models if m.opponent is not None)
        far = next(m for m in self.attacker.melee_models
                   if m.cell is not None and m.uid != paired.opponent[1])
        paired.opponent = (self.attacker.identifier, far.uid)

        problems = skirmish_log.check_grid(self.battle, self.grid, self.members)

        self.assertTrue(any("Manhattan distance" in p for p in problems))

    def test_given_a_pairing_with_a_dead_model_when_checked_then_it_is_reported(self):
        paired = next(m for m in self.defender.melee_models if m.opponent is not None)
        paired.opponent = (self.attacker.identifier, 9999)

        problems = skirmish_log.check_grid(self.battle, self.grid, self.members)

        self.assertTrue(any("is dead" in p for p in problems))

    def test_given_a_model_that_arrived_without_a_cell_when_checked_then_it_is_reported(self):
        model = self.defender.melee_models[0]
        model.cell = None
        model.arrived = True

        problems = skirmish_log.check_grid(self.battle, self.grid, self.members)

        self.assertTrue(any("arrived without a cell" in p for p in problems))

    def test_given_two_models_in_one_cell_when_checked_then_it_is_reported(self):
        first, second = self.defender.melee_models[0], self.defender.melee_models[1]
        second.cell = first.cell

        problems = skirmish_log.check_grid(self.battle, self.grid, self.members)

        self.assertTrue(any("claimed by both" in p for p in problems))

    def test_given_a_pairing_with_a_friendly_model_when_checked_then_it_is_reported(self):
        model = self.defender.melee_models[0]
        model.opponent = (self.defender.identifier, self.defender.melee_models[1].uid)

        problems = skirmish_log.check_grid(self.battle, self.grid, self.members)

        self.assertTrue(any("friendly" in p for p in problems))


class LetterStabilityTests(unittest.TestCase):
    def test_given_a_unit_joining_later_when_letters_are_assigned_then_the_existing_ones_do_not_move(self):
        first = _regiment("aaa", 0, 0, False)
        second = _regiment("bbb", 0, 14, True)
        third = _regiment("ccc", 14, 0, True)

        letters = skirmish_log.assign_letters([first, second])
        grown = skirmish_log.assign_letters([first, second, third], letters)

        self.assertEqual(letters["aaa"], grown["aaa"])
        self.assertEqual(letters["bbb"], grown["bbb"])
        self.assertNotIn(grown["ccc"], (grown["aaa"], grown["bbb"]))


if __name__ == "__main__":
    unittest.main()
