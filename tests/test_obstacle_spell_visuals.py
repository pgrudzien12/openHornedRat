"""Spells that leave battlefield obstacles (notes/spell_obstacle_visuals.md): Wind Blast, Tangling Thorn, Da Krunch and
Flamestorm. Vectors follow the report's section 6; frames are SPELLS frame numbers, ages count from the launch tick."""

import random
import struct
import unittest
from unittest import mock

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import battlefield, spell_effects
from whshr.frontend.obstacle_visuals import (ObstacleSpell, ObstacleVisuals, column_phase, krunch_height,
                                             obstacle_effects)
from whshr.rules import Side

AIM = (500.0, 500.0)


def wind(age: int, trail=(), gust=(510.0, 520.0), jitter=None) -> ObstacleSpell:
    jitter = tuple(jitter) if jitter is not None else tuple((0, 0) for _ in trail)
    return ObstacleSpell(1, spell_effects.WIND_BLAST, age, AIM, "W", gust, tuple(trail), trail_jitter=jitter)


def spell(code: int, age: int, caster=(500.0, 300.0), serial: int = 1) -> ObstacleSpell:
    return ObstacleSpell(serial, code, age, AIM, "W", caster=caster)


def run(visuals: ObstacleVisuals, make, ages) -> None:
    for age in ages:
        visuals.advance([make(age)])


class WindBlastTests(unittest.TestCase):
    def head(self, age: int) -> list[int]:
        visuals = ObstacleVisuals()
        visuals.advance([wind(age)])
        return [sprite.frame for sprite in visuals.sprites()]

    def test_given_the_gust_then_five_forming_frames_then_the_three_frame_loop(self):
        self.assertEqual([self.head(age)[0] for age in range(9)], [379, 380, 381, 382, 383, 384, 385, 386, 384])

    def test_given_t_plus_55_then_the_head_is_gone(self):
        self.assertEqual(len(self.head(54)), 1)
        self.assertEqual(self.head(55), [])

    def test_given_a_deposit_born_at_u_then_its_loop_runs_from_its_birth(self):
        visuals = ObstacleVisuals()
        deposit = [(480.0, 470.0)]
        visuals.advance([wind(60, trail=())])
        seen = []
        for age in range(61, 65):
            visuals.advance([wind(age, trail=deposit)])
            seen.append(visuals.sprites()[-1].frame)
        self.assertEqual(seen, [384, 385, 386, 384])

    def test_given_a_trail_sprite_then_it_is_drawn_at_the_battle_jitter_on_its_deposit_ground(self):
        visuals = ObstacleVisuals()
        deposit = (480.0, 470.0)
        visuals.advance([wind(60, trail=[deposit], jitter=[(-7, 8)])])
        sprite = visuals.sprites()[-1]
        self.assertEqual((sprite.x, sprite.y, sprite.ground_at), (473.0, 478.0, deposit))

    def test_given_the_head_finished_then_the_trail_stays_and_animates(self):
        visuals = ObstacleVisuals()
        visuals.advance([wind(54, trail=[(1.0, 1.0), (40.0, 1.0)])])
        visuals.advance([wind(500, trail=[(1.0, 1.0), (40.0, 1.0)])])
        self.assertEqual(len(visuals.sprites()), 2)

    def test_given_the_spell_cancelled_then_head_and_trail_are_gone(self):
        visuals = ObstacleVisuals()
        visuals.advance([wind(20, trail=[(1.0, 1.0)])])
        visuals.advance([])
        self.assertEqual(visuals.sprites(), [])


class TanglingThornTests(unittest.TestCase):
    def test_given_a_thorn_then_twenty_fixed_sprites_grow_and_hold_the_last_frame(self):
        visuals = ObstacleVisuals()
        frames, positions = [], []
        for age in range(8):
            visuals.advance([spell(spell_effects.TANGLING_THORN, age)])
            sprites = visuals.sprites()
            self.assertEqual(len(sprites), 20)
            self.assertEqual(len({sprite.frame for sprite in sprites}), 1)
            frames.append(sprites[0].frame)
            positions.append([(sprite.x, sprite.y) for sprite in sprites])
        self.assertEqual(frames, [199, 200, 201, 202, 203, 204, 204, 204])
        self.assertTrue(all(points == positions[0] for points in positions))

    def test_given_the_scatter_then_each_axis_spans_minus_31_to_plus_32_around_the_aim(self):
        visuals = ObstacleVisuals()
        for serial in range(1, 40):
            visuals.advance([spell(spell_effects.TANGLING_THORN, 0, serial=serial)])
            for sprite in visuals.sprites():
                self.assertTrue(-31 <= sprite.x - AIM[0] <= 32 and -31 <= sprite.y - AIM[1] <= 32)


class DaKrunchTests(unittest.TestCase):
    def test_given_the_foot_then_it_falls_stands_and_lifts_by_the_table(self):
        self.assertEqual([krunch_height(age) for age in range(10)], [120, 106, 93, 80, 66, 53, 40, 26, 13, 0])
        self.assertEqual({krunch_height(age) for age in range(10, 47)}, {0})
        self.assertEqual([krunch_height(age) for age in range(47, 57)], [0, 14, 27, 40, 54, 67, 80, 94, 107, 120])

    def test_given_t_plus_10_then_twelve_dust_sprites_play_474_to_479_once(self):
        visuals = ObstacleVisuals()
        seen = []
        for age in range(9, 18):
            visuals.advance([spell(spell_effects.DA_KRUNCH, age)])
            seen.append(sorted({sprite.frame for sprite in visuals.sprites()}))
            if 10 <= age <= 15:
                self.assertEqual(len(visuals.sprites()), 12)
        self.assertEqual(seen, [[], [474], [475], [476], [477], [478], [479], [], []])

    def test_given_the_foot_then_one_dakrunch_mesh_at_the_aim_facing_away_from_the_caster(self):
        visuals = ObstacleVisuals()
        visuals.advance([spell(spell_effects.DA_KRUNCH, 0, caster=(500.0, 300.0))])
        [mesh] = visuals.meshes()
        self.assertEqual((mesh.name, mesh.x, mesh.y, mesh.height, mesh.dx, mesh.dy), ("dakrunch", *AIM, 120, 0.0, 200.0))

    def test_given_the_caster_moved_then_the_lift_takes_a_new_bearing(self):
        visuals = ObstacleVisuals()
        visuals.advance([spell(spell_effects.DA_KRUNCH, 46, caster=(500.0, 300.0))])
        visuals.advance([spell(spell_effects.DA_KRUNCH, 47, caster=(300.0, 500.0))])
        [mesh] = visuals.meshes()
        self.assertEqual((mesh.dx, mesh.dy, mesh.height), (200.0, 0.0, 0))
        visuals.advance([spell(spell_effects.DA_KRUNCH, 48, caster=(500.0, 900.0))])
        self.assertEqual((visuals.meshes()[0].dx, visuals.meshes()[0].dy), (200.0, 0.0))

    def test_given_t_plus_57_then_the_foot_is_gone(self):
        visuals = ObstacleVisuals()
        visuals.advance([spell(spell_effects.DA_KRUNCH, 57)])
        self.assertEqual(visuals.meshes(), [])


class FlamestormTests(unittest.TestCase):
    def sparks(self, visuals: ObstacleVisuals) -> list[int]:
        return [sprite.frame for sprite in visuals.sprites() if 121 <= sprite.frame <= 124]

    def test_given_ignition_then_three_sparks_a_tick_up_to_twelve_each_advancing(self):
        visuals = ObstacleVisuals()
        counts = []
        for age in range(6):
            visuals.advance([spell(spell_effects.FLAMESTORM, age)])
            counts.append(len(self.sparks(visuals)))
        self.assertEqual(counts, [3, 6, 9, 12, 12, 12])
        self.assertEqual(sorted(self.sparks(visuals)), [121] * 3 + [122] * 3 + [123] * 3 + [124] * 3)

    def test_given_the_column_then_its_phase_follows_the_period_rule(self):
        frames = {age: 595 + column_phase(age)[0] for age in (18, 19, 20, 21, 36, 37, 38, 55, 56, 57)}
        self.assertEqual(frames, {18: 597, 19: 597, 20: 598, 21: 595, 36: 598, 37: 595, 38: 595, 55: 596,
                                  56: 597, 57: 597})
        self.assertEqual([column_phase(age)[1] for age in (18, 19, 36, 37)], [-40, -37, 0, 0])

    def test_given_a_shift_cast_then_the_large_column_rises_from_minus_40(self):
        visuals = ObstacleVisuals(shift_casts={"W"})
        columns = []
        for age in range(20):
            visuals.advance([spell(spell_effects.FLAMESTORM, age)])
            columns += [(sprite.frame, sprite.height) for sprite in visuals.sprites() if 117 <= sprite.frame <= 120]
        self.assertEqual(columns, [(119, -40), (119, -37)])
        self.assertEqual(visuals.shift_casts, set())

    def test_given_a_normal_cast_then_the_595_column_and_mesh_flames(self):
        visuals = ObstacleVisuals()
        run(visuals, lambda age: spell(spell_effects.FLAMESTORM, age), range(40))
        self.assertIn(595 + column_phase(39)[0], [sprite.frame for sprite in visuals.sprites()])
        meshes = visuals.meshes()
        self.assertTrue(0 < len(meshes) <= 8)
        self.assertTrue({mesh.name for mesh in meshes} <= {"fire1", "fire2", "fire3", "fire4"})

    def test_given_t_plus_37_then_every_ignition_spark_is_gone(self):
        visuals = ObstacleVisuals()
        run(visuals, lambda age: spell(spell_effects.FLAMESTORM, age), range(38))
        self.assertEqual(self.sparks(visuals), [])

    def test_given_mesh_births_then_early_heights_are_absolute_and_later_on_the_aim_ground(self):
        visuals = ObstacleVisuals()
        births = {}
        for age in range(19, 80):
            visuals.advance([spell(spell_effects.FLAMESTORM, age)])
            for flame in visuals.states[1].flames:
                births.setdefault(id(flame), (age, flame))
        for age, flame in births.values():
            self.assertTrue(0 <= flame.z < 64)
            self.assertEqual(flame.on_aim_ground, age >= 38)
        later = [mesh for mesh in visuals.meshes()]
        self.assertTrue(all(mesh.ground_at == AIM and not mesh.absolute for mesh in later))


class FixedCoin(random.Random):
    """randrange(2) always returns `coin` (0: an early-removal test removes the spark); other draws return 0."""

    def __init__(self, coin: int):
        super().__init__(0)
        self.coin = coin

    def randrange(self, start, stop=None, step=1):
        return self.coin if start == 2 and stop is None else 0


class FlamestormHandOverTests(unittest.TestCase):
    """Section 5.5: the last twelve ignition sparks hand over to eight mesh-flame sequences."""

    def counts(self, coin: int) -> tuple[list[int], list[int]]:
        visuals = ObstacleVisuals(rng=FixedCoin(coin))
        meshes, sparks = [], []
        for age in range(38):
            visuals.advance([spell(spell_effects.FLAMESTORM, age)])
            if 19 <= age <= 23:
                meshes.append(len(visuals.meshes()))
            if age in (23, 36, 37):
                sparks.append(len(visuals.states[1].sparks))
        return meshes, sparks

    def test_given_every_test_keeps_its_spark_then_meshes_2_2_5_8_8_and_four_frozen_sparks_until_t37(self):
        self.assertEqual(self.counts(1), ([2, 2, 5, 8, 8], [4, 4, 0]))

    def test_given_every_test_removes_its_spark_then_meshes_0_2_4_6_8_and_no_spark_after_t22(self):
        self.assertEqual(self.counts(0), ([0, 2, 4, 6, 8], [0, 0, 0]))

    def test_given_eight_sequences_then_exactly_eight_flames_for_good(self):
        visuals = ObstacleVisuals()
        for age in range(200):
            visuals.advance([spell(spell_effects.FLAMESTORM, age)])
            if age >= 23:
                self.assertEqual(len(visuals.meshes()), 8)

    def test_given_the_t16_and_t17_sparks_then_they_advance_after_the_freeze(self):
        visuals = ObstacleVisuals(rng=FixedCoin(1))
        frames = {}
        for age in range(21):
            visuals.advance([spell(spell_effects.FLAMESTORM, age)])
            frames[age] = sorted(sprite.frame for sprite in visuals.sprites() if 121 <= sprite.frame <= 124)
        self.assertEqual(frames[18], frames[17])
        self.assertEqual(frames[19], [122, 122, 122, 123, 123, 123, 123, 123, 123, 124])
        self.assertEqual(frames[20], [123, 123, 123, 123, 123, 123, 124, 124, 124, 124])


class BattleEffectTests(unittest.TestCase):
    def setUp(self):
        self.wizard = Regiment("W", "W", 0, 0, 0, Side.PLAYER, models=1, ranks=1, has_leader=True)
        self.battle = Battle(2000, 2000, [self.wizard], seed=1995)

    def test_given_a_thorn_cast_on_empty_ground_then_it_is_seen_at_its_aim_from_age_0(self):
        self.assertTrue(spell_effects.launch(self.battle, spell_effects.TANGLING_THORN, self.wizard, -1, 0, 300))
        spell_effects.tick(self.battle)
        [seen] = obstacle_effects(self.battle)
        self.assertEqual((seen.code, seen.age, seen.aim), (spell_effects.TANGLING_THORN, 0, (0, 300)))

    def test_given_a_wind_blast_then_its_gust_and_trail_are_reported_and_outlive_the_flight(self):
        self.assertTrue(spell_effects.launch(self.battle, spell_effects.WIND_BLAST, self.wizard, -1, 0, 600))
        for _ in range(70):
            spell_effects.tick(self.battle)
        [seen] = obstacle_effects(self.battle)
        self.assertGreater(len(seen.trail), 0)
        self.assertEqual(seen.age, 69)

    def test_given_a_dispelled_effect_then_nothing_is_reported(self):
        spell_effects.launch(self.battle, spell_effects.FLAMESTORM, self.wizard, -1, 0, 300)
        spell_effects.tick(self.battle)
        spell_effects.cancel(self.battle, self.battle.spell_effects.active[0])
        self.assertEqual(obstacle_effects(self.battle), [])


class ColourMapTests(unittest.TestCase):
    def test_given_spells_frames_595_to_598_then_they_decode_with_map_10(self):
        fol = b"".join(struct.pack("<hhhhIB", 0, 0, 1, 1, index, 0xF0).ljust(16, b"\0") for index in range(599))
        used: dict[int, int] = {}

        def decode(bop, record, end, maps, colour_map):
            used[record[4]] = colour_map
            return [0]

        with mock.patch.object(battlefield, "decode_frame", side_effect=decode):
            battlefield.read_sprite_sheet("SPELLS", fol, bytes(599))
        self.assertEqual([used[index] for index in range(595, 599)], [10, 10, 10, 10])
        self.assertNotEqual(used[594], 10)


if __name__ == "__main__":
    unittest.main()
