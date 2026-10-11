"""Battle-side rules that the spell visuals reports made gameplay-relevant: Wind Blast's trail spacing measured from the
newest trail sprite's jittered position (spell_area_effects.md 1.4, spell_obstacle_visuals.md 2.2), the Flying Bower's
take-off head, dust deposits and end tick (spell_transport_visuals.md 2), and the Sapphire Arch's sparkles (3.2)."""

import math
import unittest

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import spell_effects
from whshr.rules import Side


def wizard(x: float = 0, y: float = 0) -> Regiment:
    return Regiment("W", "W", x, y, 0, Side.PLAYER, models=1, ranks=1, has_leader=True)


class WindTrailTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(2000, 2000, [wizard()], seed=1995)
        self.effect = spell_effects.Effect(1, spell_effects.WIND_BLAST, "W", False, False, (0, 600))
        self.effect.elapsed, self.effect.flying = 60, False

    def update(self) -> None:
        spell_effects._update_wind_blast(self.battle, self.effect)

    def test_given_the_newest_sprite_shown_at_8_0_then_a_head_point_at_20_0_drops_no_disc(self):
        self.effect.trail, self.effect.trail_jitter, self.effect.previous = [(0.0, 0.0)], [(8, 0)], (20.0, 0.0)
        self.effect.elapsed = 30
        self.update()
        self.assertEqual(self.effect.trail, [(0.0, 0.0)])

    def test_given_the_newest_sprite_more_than_16_away_then_a_disc_drops(self):
        self.effect.trail, self.effect.trail_jitter, self.effect.previous = [(0.0, 0.0)], [(-8, 0)], (20.0, 0.0)
        self.effect.elapsed = 30
        self.update()
        self.assertEqual(self.effect.trail, [(0.0, 0.0), (20.0, 0.0)])

    def test_given_a_trail_then_every_sprite_gets_a_fresh_offset_from_minus_7_to_plus_8_each_update(self):
        self.effect.trail = [(0.0, 0.0), (40.0, 0.0), (80.0, 0.0)]
        self.effect.trail_jitter = [(0, 0)] * 3
        seen = set()
        for _ in range(300):
            self.update()
            self.assertEqual(len(self.effect.trail_jitter), 3)
            seen.update(self.effect.trail_jitter)
        values = {value for pair in seen for value in pair}
        self.assertEqual(values, set(range(-7, 9)))

    def test_given_n_sprites_then_the_update_takes_two_battle_draws_each(self):
        self.effect.trail = [(0.0, 0.0), (40.0, 0.0)]
        self.effect.trail_jitter = [(0, 0)] * 2
        calls = []
        original = self.battle.rng.randrange
        self.battle.rng.randrange = lambda *args: calls.append(args) or original(*args)
        self.update()
        self.assertEqual(calls, [(16,)] * 4)


class FlyingBowerTests(unittest.TestCase):
    def setUp(self):
        self.caster = wizard(500, 500)
        self.battle = Battle(3000, 3000, [self.caster], seed=1995)
        self.assertTrue(spell_effects.launch(self.battle, spell_effects.FLYING_BOWER, self.caster, -1, 500, 900))
        self.effect = self.battle.spell_effects.active[0]

    def run_to(self, elapsed: int) -> None:
        while self.effect.elapsed < elapsed and not self.effect.ended:
            spell_effects.tick(self.battle)

    def test_given_the_take_off_then_the_head_reaches_the_launch_centre_wobbling_0_to_3_at_t_plus_18(self):
        dest = self.effect.dest
        self.run_to(19)  # updates T..T+18 have run
        self.assertTrue(0 <= self.effect.x - dest[0] < 4 and 0 <= self.effect.y - dest[1] < 4)
        self.assertFalse(self.effect.flying)

    def test_given_the_flight_then_the_first_dust_is_at_t_plus_20_at_the_t_plus_19_head_point(self):
        self.run_to(20)
        head_t19 = (self.effect.x, self.effect.y)
        self.assertEqual(self.effect.trail, [])
        self.run_to(21)
        self.assertEqual((self.effect.trail[0], self.effect.trail_births[0]), (head_t19, 20))

    def test_given_the_last_deposit_then_the_effect_ends_at_t_plus_max_75_l_plus_6(self):
        self.run_to(75)
        last = self.effect.trail_births[-1]
        end = max(75, last + 6)
        self.run_to(end)
        self.assertFalse(self.effect.ended)
        spell_effects.tick(self.battle)
        self.assertTrue(self.effect.ended)

    def test_given_fewer_than_thirty_deposits_then_a_point_8_away_is_skipped(self):
        effect = spell_effects.Effect(1, spell_effects.FLYING_BOWER, "W", False, False, (0, 0))
        effect.trail, effect.trail_births = [(0.0, 0.0)], [20]
        effect.x, effect.y = 8.0, 0.0
        spell_effects._bower_dust(effect, 21)
        self.assertEqual(len(effect.trail), 1)
        effect.x = 9.0
        spell_effects._bower_dust(effect, 22)
        self.assertEqual(len(effect.trail), 2)

    def test_given_thirty_deposits_then_the_thirtieth_stays_the_reference(self):
        effect = spell_effects.Effect(1, spell_effects.FLYING_BOWER, "W", False, False, (0, 0))
        effect.trail = [(float(10 * index), 0.0) for index in range(30)]
        effect.trail_births = list(range(20, 50))
        for step in range(3):  # far from the 30th (290, 0), only 1 apart from each other
            effect.x, effect.y = 400.0 + step, 0.0
            spell_effects._bower_dust(effect, 50 + step)
        self.assertEqual(len(effect.trail), 33)


class SapphireArchTests(unittest.TestCase):
    def test_given_an_arch_then_eighteen_sparkles_around_the_aim_at_16_to_47(self):
        caster = wizard()
        battle = Battle(2000, 2000, [caster], seed=1995)
        self.assertTrue(spell_effects.launch(battle, spell_effects.SAPPHIRE_ARCH, caster, -1, 0, 300))
        particles = battle.spell_effects.active[0].particles
        self.assertEqual(len(particles), 18)
        for x, y, height in particles:
            self.assertTrue(-47 <= x <= 48 and -47 <= y - 300 <= 48 and 16 <= height <= 47)
        self.assertTrue(all(math.isfinite(value) for particle in particles for value in particle))


if __name__ == "__main__":
    unittest.main()
