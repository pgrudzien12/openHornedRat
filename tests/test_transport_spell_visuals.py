"""Transport spell visuals (notes/spell_transport_visuals.md): the Flying Bower's vortex and dust, the Sapphire Arch's
scaling mesh and sparkles, Skitterleap's departure smoke. Vectors follow the report's section 5."""

import unittest

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import spell_effects
from whshr.frontend.transport_visuals import (TransportSpell, TransportVisuals, arch_scale, transport_effects,
                                              vortex_frame)
from whshr.rules import Side

AIM = (500.0, 900.0)


def frames(visuals: TransportVisuals) -> list[int]:
    return [sprite.frame for sprite in visuals.sprites()]


class FlyingBowerTests(unittest.TestCase):
    def test_given_take_off_then_the_vortex_forms_and_loops(self):
        self.assertEqual([vortex_frame(age) for age in range(9)], [186, 187, 188, 189, 190, 191, 192, 193, 191])

    def test_given_the_lift_then_the_flight_head_continues_with_its_phase_repeated(self):
        self.assertEqual([vortex_frame(age) for age in range(18, 24)], [192, 193, 193, 191, 192, 193])
        self.assertEqual(vortex_frame(73), 192)

    def test_given_landing_then_the_head_is_gone(self):
        visuals = TransportVisuals()
        visuals.advance([TransportSpell(1, spell_effects.FLYING_BOWER, 74, AIM)])
        self.assertEqual(visuals.sprites(), [])

    def test_given_dust_born_at_u_then_194_to_198_then_gone_at_u_plus_5(self):
        visuals = TransportVisuals()
        seen = []
        for age in range(40, 46):
            visuals.advance([TransportSpell(1, spell_effects.FLYING_BOWER, age, AIM, (0.0, 0.0),
                                            ((10.0, 10.0),), (40,))])
            seen.append([frame for frame in frames(visuals) if 194 <= frame <= 198])
        self.assertEqual(seen, [[194], [195], [196], [197], [198], []])

    def test_given_the_tail_after_landing_then_only_live_dust_is_drawn(self):
        visuals = TransportVisuals()
        visuals.advance([TransportSpell(1, spell_effects.FLYING_BOWER, 78, AIM, (0.0, 0.0),
                                        ((1.0, 1.0), (2.0, 2.0)), (70, 74))])
        self.assertEqual(frames(visuals), [198])


class SapphireArchTests(unittest.TestCase):
    def arch(self, age: int, caster=(500.0, 500.0)) -> TransportSpell:
        sparkles = tuple((AIM[0] + i, AIM[1], 20.0) for i in range(18))
        return TransportSpell(1, spell_effects.SAPPHIRE_ARCH, age, AIM, sparkles=sparkles, caster=caster)

    def test_given_the_arch_then_it_grows_holds_and_shrinks(self):
        self.assertEqual([round(arch_scale(age) * 100) for age in (0, 1, 17, 18, 161, 162, 179)],
                         [10, 15, 95, 100, 100, 95, 10])

    def test_given_the_arch_then_one_sapharch_mesh_at_the_aim_facing_away_from_the_caster(self):
        visuals = TransportVisuals()
        visuals.advance([self.arch(0)])
        [mesh] = visuals.meshes()
        self.assertEqual((mesh.name, mesh.x, mesh.y, mesh.dx, mesh.dy, mesh.scale), ("sapharch", *AIM, 0.0, 400.0, 0.1))

    def test_given_the_caster_moves_then_the_arch_keeps_its_launch_bearing(self):
        visuals = TransportVisuals()
        visuals.advance([self.arch(0)])
        visuals.advance([self.arch(1, caster=(100.0, 900.0))])
        self.assertEqual((visuals.meshes()[0].dx, visuals.meshes()[0].dy), (0.0, 400.0))

    def test_given_the_sparkles_then_eighteen_full_size_loop_558_to_561_from_t(self):
        visuals = TransportVisuals()
        seen = []
        for age in (0, 1, 2, 3, 4, 179):
            visuals.advance([self.arch(age)])
            sprites = visuals.sprites()
            self.assertEqual(len(sprites), 18)
            seen.append(sprites[0].frame)
        self.assertEqual(seen, [558, 559, 560, 561, 558, 561])

    def test_given_t_plus_180_or_a_cancel_then_mesh_and_sparkles_go_together(self):
        visuals = TransportVisuals()
        visuals.advance([self.arch(180)])
        self.assertEqual((visuals.meshes(), visuals.sprites()), ([], []))
        visuals.advance([self.arch(50)])
        visuals.advance([])
        self.assertEqual((visuals.meshes(), visuals.sprites()), ([], []))


class SkitterleapTests(unittest.TestCase):
    def leap(self, age: int, figures) -> TransportSpell:
        return TransportSpell(1, spell_effects.SKITTERLEAP, age, AIM, figures=tuple(figures))

    def test_given_a_leap_then_smoke_stays_at_the_departure_points_while_the_caster_moves(self):
        visuals = TransportVisuals()
        visuals.advance([self.leap(0, [(10.0, 10.0), (20.0, 10.0)])])
        visuals.advance([self.leap(2, [(60.0, 10.0), (70.0, 10.0)])])
        self.assertEqual([(s.frame, s.x, s.y) for s in visuals.sprites()], [(531, 10.0, 10.0), (531, 20.0, 10.0)])

    def test_given_t_plus_3_then_532_and_no_arrival_smoke_afterwards(self):
        visuals = TransportVisuals()
        visuals.advance([self.leap(0, [(10.0, 10.0)])])
        visuals.advance([self.leap(3, [(10.0, 10.0)])])
        self.assertEqual(frames(visuals), [532])
        visuals.advance([])
        self.assertEqual(frames(visuals), [])


class BattleEffectTests(unittest.TestCase):
    def setUp(self):
        self.caster = Regiment("W", "W", 500, 500, 0, Side.PLAYER, models=3, ranks=1, has_leader=True)
        self.battle = Battle(3000, 3000, [self.caster], seed=1995)

    def test_given_a_skitterleap_then_its_smoke_starts_on_every_caster_figure_and_ends_with_the_leap(self):
        self.assertTrue(spell_effects.launch(self.battle, spell_effects.SKITTERLEAP, self.caster, -1, 500, 900))
        spell_effects.tick(self.battle)
        [seen] = transport_effects(self.battle)
        self.assertEqual((seen.age, len(seen.figures)), (0, 3))
        for _ in range(4):
            spell_effects.tick(self.battle)
        self.assertEqual(transport_effects(self.battle), [])

    def test_given_a_bower_then_head_dust_and_births_come_from_the_battle(self):
        self.assertTrue(spell_effects.launch(self.battle, spell_effects.FLYING_BOWER, self.caster, -1, 500, 900))
        for _ in range(30):
            spell_effects.tick(self.battle)
        [seen] = transport_effects(self.battle)
        effect = self.battle.spell_effects.active[0]
        self.assertEqual((seen.head, seen.dust, seen.dust_births),
                         ((effect.x, effect.y), tuple(effect.trail), tuple(effect.trail_births)))
        self.assertGreater(len(seen.dust), 0)


if __name__ == "__main__":
    unittest.main()
