"""A fleeing unit's figures mill as a mob behind the anchor (notes/flight_figure_movement.md)."""

import random
import unittest

from whshr import combat, formation
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class Draws(random.Random):
    """randrange(n) returns the queued raw rand() results modulo n."""

    def __init__(self, *draws):
        super().__init__(0)
        self.draws = list(draws)

    def randrange(self, start, *_):  # type: ignore[override]
        return self.draws.pop(0) % start


def edge(low, high):
    return {"name": "Edge", "status": ["bnd_ACTIVE", "bnd_BATTLEEDGE"],
            "lines": [[low, low, high, low], [high, low, high, high], [high, high, low, high], [low, high, low, low]]}


def flock(x=2500, y=1000, models=15, ranks=3, side=Side.NEUTRAL):
    return Regiment("s", "Flock", x, y, 0, side, models=models, ranks=ranks, speed_per_tick=1.0)


class ScatterRuleTests(unittest.TestCase):
    """Section 7 "Scatter (one axis)": d - trunc(d/2) + 3 * (trunc(n/2) - rand % n)."""

    def test_given_the_report_vectors_then_each_axis_scatters_as_listed(self):
        for before, n, raw, after in ((-12, 15, 3, 6), (7, 15, 14, -17), (-7, 15, 0, 17), (-1, 15, 7, -1),
                                      (0, 12, 11, -15), (0, 12, 0, 18), (0, 1, 123, 0)):
            with self.subTest(before=before, n=n, raw=raw):
                self.assertEqual(formation.scatter_flee_offset((before, 0), n, Draws(raw, n // 2))[0], after)

    def test_x_draws_before_y(self):
        self.assertEqual(formation.scatter_flee_offset((0, 0), 15, Draws(0, 14)), (21, -21))


class ShiftRuleTests(unittest.TestCase):
    """Section 7 "Shift": n back along the flight direction, each axis truncated toward zero."""

    def test_given_the_report_vectors_then_the_shift_is_as_listed(self):
        for heading, n, shift in ((0, 15, (0, -15)), (64, 15, (-10, -10)), (128, 15, (-15, 0)), (37, 12, (-5, -10))):
            with self.subTest(heading=heading, n=n):
                self.assertEqual(formation.flee_shift(heading, n), shift)


class RoutStartTests(unittest.TestCase):
    def test_given_a_rout_then_every_destination_is_scattered_once_from_its_slot_and_no_figure_moves(self):
        unit = flock(models=4, ranks=2)
        battle = Battle(5000, 5000, [unit], seed=1995)
        before = list(unit.model_positions())
        slots = battle.model_targets(unit)
        unit.melee_models[1].at_rest = False  # a walking figure is scattered too, but gets no pause
        battle.rng = Draws(*range(8), *([0] * 50))

        combat.start_rout(unit, battle)

        expected = [formation.scatter_flee_offset((int(sx - unit.x), int(sy - unit.y)), 4, Draws(2 * i, 2 * i + 1))
                    for i, (sx, sy) in enumerate(slots)]
        self.assertEqual([model.flee_offset for model in unit.melee_models], expected)
        self.assertEqual(unit.positions, before)
        self.assertEqual([model.flee_reaim_ticks > 0 for model in unit.melee_models], [True, False, True, True])


class OneFigureTimelineTests(unittest.TestCase):
    """Section 7 timeline: stagger & 7 = 5, at rest when the unit routs on tick T."""

    def test_given_stagger_5_then_it_moves_and_re_aims_on_t_plus_20_and_again_on_t_plus_74(self):
        unit = flock(models=1, ranks=1)
        battle = Battle(5000, 5000, [unit], seed=1995, boundaries=[edge(0, 5000)])
        unit.model_positions()
        model = unit.melee_models[0]
        model.stagger = 5
        combat.start_rout(unit, battle)
        self.assertEqual(model.rout_pause_ticks, 21)
        start = unit.positions[0]
        re_aims = []
        for tick in range(80):  # tick index 0 is T
            timer_before = model.flee_reaim_ticks
            battle.tick()
            if tick < 20:
                self.assertEqual(unit.positions[0], start)
            if model.flee_reaim_ticks > timer_before:
                re_aims.append(tick)
                self.assertEqual(model.flee_reaim_ticks, 54)
                self.assertEqual(model.current_speed, 0.0)
        self.assertEqual(re_aims, [20, 74])
        self.assertNotEqual(unit.positions[0], start)


class MobInvariantTests(unittest.TestCase):
    """Section 7 invariants for a 15-figure unit fleeing along heading 0 (+y)."""

    def setUp(self):
        self.unit = flock(side=Side.PLAYER)  # a player unit makes no rally attempt of its own: it keeps fleeing
        self.battle = Battle(5000, 5000, [self.unit], seed=1995, boundaries=[edge(0, 5000)])
        self.unit.model_positions()
        combat.start_rout(self.unit, self.battle)

    def run_flight(self, ticks):
        re_aims: dict[int, list[int]] = {}
        offsets = []
        for tick in range(ticks):
            timers = [model.flee_reaim_ticks for model in self.unit.melee_models]
            self.battle.tick()
            self.assertTrue(self.unit.routing)
            self.assertEqual(int(self.unit.direction) % 512, 0)
            for index, model in enumerate(self.unit.melee_models):
                if model.flee_reaim_ticks > timers[index]:
                    re_aims.setdefault(index, []).append(tick)
                    self.assertEqual(model.current_speed, 0.0)
                    if len(re_aims[index]) >= 4:
                        offsets.append(model.flee_offset)
        return re_aims, offsets

    def test_each_figure_re_aims_at_its_own_fixed_interval(self):
        re_aims, _ = self.run_flight(400)
        for index, ticks in re_aims.items():
            interval = ((self.unit.melee_models[index].stagger & 7) * 3 + 12) * 2
            self.assertEqual({b - a for a, b in zip(ticks, ticks[1:])}, {interval})

    def test_destinations_stay_in_the_cloud_bounds_about_2n_behind_the_anchor(self):
        _, offsets = self.run_flight(600)
        self.assertGreater(len(offsets), 30)
        for across, along in offsets:
            self.assertTrue(-43 <= across <= 43, (across, along))
            self.assertTrue(-73 <= along <= 13, (across, along))
        mean_along = sum(along for _, along in offsets) / len(offsets)
        self.assertTrue(-45 < mean_along < -15, mean_along)

    def test_the_flock_no_longer_holds_its_ranks(self):
        self.run_flight(300)
        slots = formation.place(self.unit.x, self.unit.y, self.unit.direction, self.unit.slots())
        far = sum(1 for (px, py), (sx, sy) in zip(self.unit.positions, slots) if abs(px - sx) + abs(py - sy) > 12)
        self.assertGreater(far, len(slots) // 2)


class TableEdgeTests(unittest.TestCase):
    def test_past_the_edge_every_figure_walks_to_the_halted_anchor_and_the_unit_leaves_once_all_arrived(self):
        unit = flock(x=2500, y=380, models=6, ranks=2)
        battle = Battle(5000, 5000, [unit], seed=1995, boundaries=[edge(0, 400)])
        unit.model_positions()
        combat.start_rout(unit, battle)
        for _ in range(400):
            battle.tick()
            if unit.flight_complete:
                break
        self.assertTrue(unit.flight_complete)
        self.assertEqual({model.flee_offset for model in unit.melee_models}, {(0, 0)})
        anchor = (unit.x, unit.y)
        while not unit.fled:
            self.assertEqual((unit.x, unit.y), anchor)
            battle.tick()
        self.assertTrue(all(model.flee_reaim_ticks == 0 for model in unit.melee_models))


class RallyTests(unittest.TestCase):
    def test_once_rallied_the_figures_walk_to_formation_slots_again(self):
        unit = flock(models=4, ranks=2)
        battle = Battle(5000, 5000, [unit], seed=1995, boundaries=[edge(0, 5000)])
        unit.model_positions()
        combat.start_rout(unit, battle)
        unit.routing = False
        slots = formation.place(unit.x, unit.y, unit.direction, unit.slots())
        self.assertEqual(battle.model_targets(unit), slots)


if __name__ == "__main__":
    unittest.main()
