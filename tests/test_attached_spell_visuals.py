"""Spells drawn on their target's figures (notes/spell_attached_visuals.md): the Curse of Anraheir's spirits and the
Azure Blades / Ere We Go! / Mork Save Uz! sparkles. Vectors follow the report's section 6; frames are SPELLS frame
numbers and a directional sprite's frame is its first frame plus the camera-relative direction."""

import random
import unittest

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import spell_effects
from whshr.frontend.spell_visuals import (AttachedVisuals, Attachment, DirectionalSprite, Sprite, attached_effects,
                                          projectile_shots)
from whshr.rules import Side


class Remainders(random.Random):
    """Returns the listed values as `randrange` results (then 0), like the report's random remainders."""

    def __init__(self, values=()):
        super().__init__(0)
        self.values = list(values)
        self.draws = 0

    def randrange(self, start, stop=None, step=1):
        self.draws += 1
        return self.values.pop(0) if self.values else 0


def figures(count: int) -> tuple[tuple[float, float], ...]:
    return tuple((100.0 + 12 * index, 100.0) for index in range(count))


def curse(age: int, count: int = 1, facing: int = 0, serial: int = 1) -> Attachment:
    return Attachment(serial, spell_effects.CURSE, age, figures(count), facing)


def frames(visuals: AttachedVisuals, direction: int = 0) -> list[int]:
    return [sprite.first + direction if isinstance(sprite, DirectionalSprite) else sprite.frame
            for sprite in visuals.sprites()]


class CurseTests(unittest.TestCase):
    def test_given_a_new_curse_then_the_appearance_runs_one_phase_per_tick(self):
        visuals = AttachedVisuals()
        seen = []
        for age in range(4):
            visuals.advance([curse(age)])
            seen += frames(visuals, direction=2)
        self.assertEqual(seen, [231, 239, 247, 255])

    def test_given_remainder_0_at_the_loop_start_then_loop_phase_3_then_phase_0(self):
        visuals = AttachedVisuals(rng=Remainders([0]))
        visuals.advance([curse(4)])
        self.assertEqual(frames(visuals, direction=2), [287])
        visuals.advance([curse(5)])
        self.assertEqual(frames(visuals, direction=2), [263])

    def test_given_four_figures_then_each_draws_its_own_starting_phase_once(self):
        rng = Remainders([0, 1, 2, 3])
        visuals = AttachedVisuals(rng=rng)
        visuals.advance([curse(4, count=4)])
        self.assertEqual(frames(visuals), [285, 277, 269, 261])
        visuals.advance([curse(8, count=4)])
        self.assertEqual(frames(visuals), [285, 277, 269, 261])
        self.assertEqual(rng.draws, 4)

    def test_given_a_turn_then_the_direction_follows_the_unit_facing_without_restarting(self):
        visuals = AttachedVisuals(rng=Remainders([3]))
        visuals.advance([curse(6, facing=64)])  # start phase 0, two ticks on: phase 2
        sprite = visuals.sprites()[0]
        self.assertIsInstance(sprite, DirectionalSprite)
        self.assertEqual((sprite.first, sprite.bearing), (277, 64))
        visuals.advance([curse(7, facing=192)])
        sprite = visuals.sprites()[0]
        self.assertEqual((sprite.first, sprite.bearing), (285, 192))

    def test_given_casualties_then_only_the_surviving_figures_carry_spirits(self):
        visuals = AttachedVisuals()
        visuals.advance([curse(5, count=12)])
        visuals.advance([curse(6, count=10)])
        self.assertEqual(len(visuals.sprites()), 10)

    def test_given_the_curse_ended_then_its_spirits_are_gone_that_update(self):
        visuals = AttachedVisuals()
        visuals.advance([curse(5, count=3)])
        visuals.advance([])
        self.assertEqual(visuals.sprites(), [])
        self.assertEqual(visuals.phases, {})

    def test_given_ticks_passed_unseen_then_the_current_phase_is_shown_without_replaying_the_appearance(self):
        visuals = AttachedVisuals(rng=Remainders([3]))
        visuals.advance([curse(1)])
        visuals.advance([curse(9)])  # off-screen from T+2 to T+8: start phase 0, five ticks on -> phase 1
        self.assertEqual(frames(visuals), [269])

    def test_given_a_replacement_curse_then_the_new_one_starts_its_appearance(self):
        visuals = AttachedVisuals()
        visuals.advance([curse(20, serial=1)])
        visuals.advance([curse(0, serial=2)])
        self.assertEqual(frames(visuals), [229])

    def test_given_spirits_then_they_stand_at_each_figure_ground_point(self):
        visuals = AttachedVisuals()
        visuals.advance([curse(0, count=2)])
        self.assertEqual([(s.x, s.y, s.height) for s in visuals.sprites()], [(100.0, 100.0, 0.0), (112.0, 100.0, 0.0)])


class SparkleTests(unittest.TestCase):
    def sparkle(self, code: int, age: int, count: int = 3) -> list[Sprite]:
        visuals = AttachedVisuals()
        visuals.advance([Attachment(1, code, age, figures(count), 0)])
        return [sprite for sprite in visuals.sprites() if isinstance(sprite, Sprite)]

    def test_given_azure_blades_then_one_sparkle_per_figure_16_above_the_ground(self):
        sprites = self.sparkle(spell_effects.AZURE_BLADES, 0)
        self.assertEqual([(s.frame, s.height) for s in sprites], [(387, 16.0)] * 3)

    def test_given_azure_blades_at_t_plus_4_then_the_loop_is_back_at_its_first_frame(self):
        self.assertEqual({s.frame for s in self.sparkle(spell_effects.AZURE_BLADES, 4)}, {387})

    def test_given_ere_we_go_at_its_last_visible_tick_then_frame_473(self):
        self.assertEqual({s.frame for s in self.sparkle(spell_effects.ERE_WE_GO, 179)}, {473})

    def test_given_mork_save_uz_then_every_figure_shares_one_loop(self):
        seen = [{s.frame for s in self.sparkle(spell_effects.MORK_SAVE_UZ, age)} for age in range(5)]
        self.assertEqual(seen, [{486}, {487}, {488}, {489}, {486}])
        self.assertEqual({s.height for s in self.sparkle(spell_effects.MORK_SAVE_UZ, 0)}, {0.0})


class BattleEffectTests(unittest.TestCase):
    """The attached effects as the battle reports them after its effect update."""

    def setUp(self):
        self.wizard = Regiment("W", "W", 0, 0, 0, Side.PLAYER, models=1, ranks=1, has_leader=True)
        self.target = Regiment("T", "T", 0, 200, 0, Side.PLAYER, models=6, ranks=1, has_leader=True)
        self.battle = Battle(1000, 1000, [self.wizard, self.target], seed=1995)

    def cast(self, code: int) -> None:
        self.assertTrue(spell_effects.launch(self.battle, code, self.wizard, -1, 0, 200))
        spell_effects.tick(self.battle)  # the launch tick's update

    def test_given_mork_save_uz_after_its_launch_tick_then_age_0_on_every_figure(self):
        self.cast(spell_effects.MORK_SAVE_UZ)
        [seen] = attached_effects(self.battle)
        self.assertEqual((seen.code, seen.age, len(seen.figures)), (spell_effects.MORK_SAVE_UZ, 0, 6))

    def test_given_the_target_moves_then_the_sprites_follow_its_figures(self):
        self.cast(spell_effects.ERE_WE_GO)
        before = attached_effects(self.battle)[0].figures
        self.target.x += 12
        self.target.positions = [(x + 12, y) for x, y in self.target.model_positions()]
        after = attached_effects(self.battle)[0].figures
        self.assertEqual([x for x, _ in after], [x + 12 for x, _ in before])

    def test_given_the_effect_cancelled_then_nothing_is_attached(self):
        self.cast(spell_effects.AZURE_BLADES)
        spell_effects.cancel(self.battle, self.battle.spell_effects.active[0])
        self.assertEqual(attached_effects(self.battle), [])

    def test_given_dispel_magic_or_fists_of_gork_then_no_effect_art_is_drawn(self):
        for code in (spell_effects.DISPEL_MAGIC, spell_effects.FISTS):
            with self.subTest(code=code):
                self.setUp()
                self.cast(code)
                self.assertEqual(attached_effects(self.battle), [])
                shots, storms = projectile_shots(self.battle.spell_effects.active, {})
                self.assertEqual((list(shots), list(storms)), ([], []))


if __name__ == "__main__":
    unittest.main()
