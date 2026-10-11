"""The Flock of Doom and Conflagration of Doom (notes/spell_area_particle_visuals.md): the battle keeps the birds and the
bursts (their draws share the battle's stream and decide when Conflagration ends); the frontend turns them into frames.
Vectors follow the report's section 3."""

import unittest

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import spell_effects
from whshr.frontend.area_particle_visuals import (AreaSpell, area_effects, area_meshes, area_sprites,
                                                  falling_fire_base, flock_frame)
from whshr.rules import Side


class Draws:
    """Wraps the battle's randrange: replays `script` first, records every call's modulus."""

    def __init__(self, battle: Battle, script=()):
        self.original = battle.rng.randrange
        self.script = list(script)
        self.calls: list[int] = []
        battle.rng.randrange = self

    def __call__(self, *args):
        self.calls.append(args[0])
        return self.script.pop(0) if self.script else self.original(*args)


def battle_with_wizard() -> tuple[Battle, Regiment]:
    caster = Regiment("W", "W", 0, 0, 0, Side.PLAYER, models=1, ranks=1, has_leader=True)
    return Battle(4000, 4000, [caster], seed=1995), caster


class FlockTests(unittest.TestCase):
    def test_given_launch_draws_0_and_63_then_the_first_bird_stands_at_plus_32_minus_31(self):
        battle, caster = battle_with_wizard()
        Draws(battle, [0, 63])
        self.assertTrue(spell_effects.launch(battle, spell_effects.FLOCK, caster, -1, 1000, 1000))
        birds = battle.spell_effects.active[0].particles
        self.assertEqual((len(birds), birds[0]), (20, (1032, 969, 0.0)))

    def test_given_the_birds_then_approach_three_strike_cycles_and_fly_off_in_step(self):
        self.assertEqual([flock_frame(age) for age in range(11)], [*range(357, 367), 367])
        self.assertEqual([flock_frame(age) for age in (17, 18, 26, 33, 34, 37, 38)], [374, 367, 367, 374, 375, 378, None])

    def test_given_twenty_birds_then_every_one_shows_the_same_frame_at_its_own_point(self):
        birds = tuple((float(i), 0.0, 0.0) for i in range(20))
        sprites = area_sprites(AreaSpell(1, spell_effects.FLOCK, 12, (0.0, 0.0), birds))
        self.assertEqual({sprite.frame for sprite in sprites}, {369})
        self.assertEqual([sprite.x for sprite in sprites], [float(i) for i in range(20)])

    def test_given_the_flock_in_battle_then_it_is_drawn_from_t_and_gone_at_t_plus_38(self):
        battle, caster = battle_with_wizard()
        spell_effects.launch(battle, spell_effects.FLOCK, caster, -1, 0, 300)
        spell_effects.tick(battle)
        [seen] = area_effects(battle)
        self.assertEqual({sprite.frame for sprite in area_sprites(seen)}, {357})
        for _ in range(38):
            spell_effects.tick(battle)
        self.assertEqual(area_effects(battle), [])


class ConflagrationTests(unittest.TestCase):
    def setUp(self):
        self.battle, caster = battle_with_wizard()
        self.assertTrue(spell_effects.launch(self.battle, spell_effects.CONFLAGRATION, caster, -1, 2000, 2000))
        self.effect = self.battle.spell_effects.active[0]
        self.effect.value = 2  # k = 2: R = 24, base 96, at most 10 bursts

    def run_to(self, age: int) -> AreaSpell | None:
        """Run the effect updates up to and including tick T+age; the state seen after it."""
        while self.effect.elapsed <= age and not self.effect.ended:
            spell_effects.tick(self.battle)
        seen = area_effects(self.battle)
        return seen[0] if seen else None

    def frames(self, age: int) -> list[int]:
        spell = self.run_to(age)
        return [] if spell is None else [sprite.frame for sprite in area_sprites(spell)]

    def test_given_the_fuse_then_nothing_is_drawn(self):
        for age in range(17):
            self.assertEqual(self.frames(age), [])

    def test_given_the_fall_then_the_fire_drops_from_120_cycling_four_frames(self):
        seen = []
        for age in (18, 19, 20, 21, 22, 27):
            spell = self.run_to(age)
            [fire] = area_sprites(spell)
            seen.append((fire.frame, fire.height))
        self.assertEqual(seen, [(96, 120), (97, 106), (98, 93), (99, 80), (96, 66), (97, 0)])

    def test_given_the_impact_then_the_flash_then_bursts_3_3_3_1(self):
        self.assertEqual(self.frames(28), [108])
        self.assertIn(109, self.frames(29))
        counts = []
        for age in (29, 30, 31, 32, 33):
            spell = self.run_to(age)
            counts.append(sum(place is not None for place in spell.places))
        self.assertEqual(counts, [3, 6, 9, 10, 10])

    def test_given_a_burst_born_at_t_plus_29_then_it_becomes_a_flame_at_t_plus_38(self):
        spell = self.run_to(37)
        self.assertEqual(spell.places[0].phase, 0)
        spell = self.run_to(38)
        place = spell.places[0]
        self.assertIn(place.phase, (1, 2, 3, 4))
        self.assertTrue(-3 <= place.jitter[0] <= 4 and -3 <= place.jitter[1] <= 4)
        [mesh] = [mesh for mesh in area_meshes(spell) if mesh.ground_at == (place.x, place.y)]
        self.assertEqual(mesh.name, f"flames{place.phase}")

    def test_given_the_dying_down_then_5k_minus_c_picks_each_update(self):
        self.run_to(63)
        draws = Draws(self.battle)
        self.run_to(64)  # c = 9
        self.assertFalse(self.effect.ended)
        self.assertEqual(draws.calls.count(10), 1)
        self.run_to(71)
        draws.calls.clear()
        self.run_to(72)  # c = 1
        if not self.effect.ended:
            self.assertEqual(draws.calls.count(10), 9)

    def test_given_the_countdown_then_the_effect_ends_by_t_plus_73(self):
        self.run_to(37)
        self.assertFalse(self.effect.ended)
        self.run_to(73)
        self.assertTrue(self.effect.ended)
        self.assertEqual(area_effects(self.battle), [])

    def test_given_a_dispel_during_the_fall_then_everything_goes_at_once(self):
        self.run_to(20)
        spell_effects.cancel(self.battle, self.effect)
        self.assertEqual(area_effects(self.battle), [])

    def test_given_k_then_the_falling_fire_size(self):
        self.assertEqual([falling_fire_base(k) for k in range(1, 7)], [92, 96, 96, 100, 100, 104])


class ColourMapTests(unittest.TestCase):
    def test_given_the_alternative_burst_frames_then_they_decode_with_map_3(self):
        import struct
        from unittest import mock
        from whshr import battlefield
        fol = b"".join(struct.pack("<hhhhIB", 0, 0, 1, 1, index, 0x30).ljust(16, b"\0") for index in range(599))
        used: dict[int, int] = {}

        def decode(bop, record, end, maps, colour_map):
            used[record[4]] = colour_map
            return [0]

        with mock.patch.object(battlefield, "decode_frame", side_effect=decode):
            battlefield.read_sprite_sheet("SPELLS", fol, bytes(599))
        self.assertEqual({used[index] for index in range(541, 550)}, {3})


if __name__ == "__main__":
    unittest.main()
