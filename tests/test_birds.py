"""Ambient battlefield birds (notes/battle_birds.md): born at the 1st, 9th, 17th and 25th deaths, each circling the
latest corpse of its own every-32nd-death sequence, on a fixed 52-tick flap/glide program."""

import unittest

from whshr import animation, birds, combat
from whshr.birds import Bird, Flock
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def deaths(flock: Flock, count: int, at: tuple[float, float] = (0.0, 0.0)) -> None:
    for _ in range(count):
        flock.record_death(*at)


class PopulationTests(unittest.TestCase):
    def test_given_no_deaths_then_no_birds(self):
        flock = Flock()
        flock.tick()
        self.assertEqual(flock.birds, [])

    def test_given_first_death_then_one_bird_at_the_corpse_high_above_the_terrain(self):
        flock = Flock()
        flock.record_death(500, 700)
        (bird,) = flock.birds
        self.assertEqual((bird.x, bird.y, bird.height), (500, 700, birds.BIRTH_HEIGHT))
        self.assertEqual((bird.goal_x, bird.goal_y), (500, 700))
        self.assertFalse(bird.clockwise)

    def test_given_ninth_death_then_a_second_bird_circles_that_corpse(self):
        flock = Flock()
        deaths(flock, 8, (500, 700))
        flock.record_death(900, 300)
        self.assertEqual(len(flock.birds), 2)
        self.assertEqual((flock.birds[1].goal_x, flock.birds[1].goal_y), (900, 300))
        self.assertFalse(flock.birds[1].clockwise)

    def test_given_many_deaths_then_at_most_four_birds_and_the_later_two_turn_clockwise(self):
        flock = Flock()
        deaths(flock, 200)
        self.assertEqual([bird.birth for bird in flock.birds], [0, 8, 16, 24])
        self.assertEqual([bird.clockwise for bird in flock.birds], [False, False, True, True])

    def test_given_nobirds_then_deaths_create_no_birds(self):
        flock = Flock(enabled=False)
        deaths(flock, 40)
        self.assertEqual(flock.birds, [])


class GoalTests(unittest.TestCase):
    def test_given_33rd_death_then_the_first_bird_moves_on_to_it(self):
        flock = Flock()
        flock.record_death(500, 700)
        deaths(flock, 31, (1, 1))
        flock.record_death(1200, 400)
        first = flock.birds[0]
        self.assertEqual((first.goal_x, first.goal_y), (1200, 400))
        self.assertEqual([(bird.goal_x, bird.goal_y) for bird in flock.birds[1:]], [(1, 1)] * 3)

    def test_given_a_new_goal_then_the_bird_aims_at_it_only_on_its_next_aim(self):
        flock = Flock()
        flock.record_death(0, 0)
        flock.tick()  # birth aim
        deaths(flock, 31)
        flock.record_death(0, -1000)  # straight down -Y: bearing 256
        bird = flock.birds[0]
        aimed = bird.wanted
        for _ in range(15):
            flock.tick()
        self.assertEqual(bird.wanted, aimed)  # ticks 1-15: still the stale bearing
        flock.tick()  # tick 16 aims
        self.assertEqual(bird.wanted, 256)


class SteeringTests(unittest.TestCase):
    def bird(self, heading: int, wanted: int, birth: int = 0) -> Bird:
        return Bird(birth, 0, 0, birds.BIRTH_HEIGHT, heading, 0, 0, wanted=wanted)

    def test_given_an_anticlockwise_bird_far_off_its_bearing_then_it_turns_the_long_way(self):
        bird = self.bird(0, 200)
        bird.steer()
        self.assertEqual(bird.heading, 504)

    def test_given_a_clockwise_bird_far_off_its_bearing_then_it_turns_clockwise(self):
        bird = self.bird(0, 300, birth=16)
        bird.steer()
        self.assertEqual(bird.heading, 8)

    def test_given_a_bird_within_eight_of_its_bearing_then_the_heading_is_kept(self):
        bird = self.bird(100, 105)
        bird.steer()
        self.assertEqual(bird.heading, 100)

    def test_given_a_bird_at_birth_height_then_it_sinks_one_and_a_half_per_tick(self):
        bird = self.bird(0, 0)
        bird.steer()
        self.assertEqual(bird.dz, -1.5)

    def test_given_cardinal_and_diagonal_headings_then_the_speed_is_about_two_units(self):
        self.assertEqual(birds.velocity(0), (0.0, 2.0))
        self.assertEqual(birds.velocity(128), (2.0, 0.0))
        self.assertEqual(birds.velocity(256), (0.0, -2.0))
        self.assertEqual(birds.velocity(64), (1.25, 1.25))  # 181 >> 5 = 5

    def test_given_bearings_then_they_follow_the_usual_convention(self):
        self.assertEqual(birds.bearing(0, 0, 0, 10), 0)
        self.assertEqual(birds.bearing(0, 0, 10, 0), 128)
        self.assertEqual(birds.bearing(0, 0, 0, -10), 256)
        self.assertEqual(birds.bearing(0, 0, -10, 0), 384)


class ProgramTests(unittest.TestCase):
    def test_given_a_new_bird_then_the_first_tick_aims_without_moving(self):
        flock = Flock()
        flock.record_death(300, 300)
        flock.tick()
        bird = flock.birds[0]
        self.assertEqual((bird.x, bird.y, bird.height, bird.phase), (300, 300, birds.BIRTH_HEIGHT, 0))

    def test_given_a_round_then_its_wing_phases_follow_the_program(self):
        flock = Flock()
        flock.record_death(0, 0)
        phases = []
        for _ in range(birds.ROUND_TICKS):
            flock.tick()
            phases.append(flock.birds[0].phase)
        self.assertEqual(phases, [0, 1, 2, 3] * 4 + [0] * 17 + [1, 2, 3] + [0, 1, 2, 3] * 4)

    def test_given_a_long_flight_then_the_bird_settles_near_cruise_height_and_stays_near_its_corpse(self):
        flock = Flock()
        flock.record_death(1000, 1000)
        for _ in range(2000):
            flock.tick()
        bird = flock.birds[0]
        self.assertEqual(int(bird.height), birds.CRUISE_HEIGHT)
        self.assertLess(abs(bird.x - 1000) + abs(bird.y - 1000), 300)

    def test_given_many_rounds_then_about_a_fifth_of_them_call(self):
        flock = Flock()
        flock.record_death(0, 0)
        calls = [call for _ in range(birds.ROUND_TICKS * 500) for call in flock.tick()]
        self.assertTrue(50 < len(calls) < 150)
        self.assertEqual({call.effect for call in calls}, set(birds.CALL_EFFECTS))


class BattleTests(unittest.TestCase):
    def build(self) -> tuple[Battle, Regiment]:
        unit = Regiment("R", "Clanrats", 500, 500, 0, Side.ENEMY, models=16, ranks=4)
        battle = Battle(1000, 1000, [unit], seed=1995)
        battle.phase = "battle"
        return battle, unit

    def test_given_a_killed_model_then_a_bird_appears_where_it_fell(self):
        battle, unit = self.build()
        combat.kill_models(unit, range(1), battle, animation.DEATH_MISSILE, killer="S")
        for _ in range(5):
            battle.tick()
        (bird,) = battle.birds.birds
        self.assertLess(abs(bird.goal_x - 500) + abs(bird.goal_y - 500), 100)

    def test_given_birds_then_the_gameplay_random_stream_is_untouched(self):
        with_birds, unit_a = self.build()
        without, unit_b = self.build()
        without.birds.enabled = False
        for battle, unit in ((with_birds, unit_a), (without, unit_b)):
            combat.kill_models(unit, range(3), battle, animation.DEATH_MISSILE, killer="S")
            for _ in range(60):
                battle.tick()
        self.assertEqual(with_birds.rng.random(), without.rng.random())
        self.assertEqual(len(with_birds.birds.birds), 1)


if __name__ == "__main__":
    unittest.main()
