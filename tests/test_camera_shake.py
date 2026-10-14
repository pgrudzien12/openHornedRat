"""The battle camera shake (notes/camera_shake.md, GitHub #299): a stepped vertical eye bob, presentation only."""

import unittest

from tests.test_spell_effects import EffectTestCase
from whshr import animation, camera_shake, combat, spell_effects
from whshr.battle3d import Projection
from whshr.camera import BattleCamera
from whshr.camera_shake import MEDIUM, STRONG, CameraShake
from whshr.engine import Battle, Regiment
from whshr.rules import Side

STRONG_VIEW = [-1.0, 1.0, -1.0, 1.0, -1.0, 0.8, -0.8, 0.8, -0.8, 0.6, -0.6, 0.4, -0.4, 0.2, -0.2, 0.0]
MEDIUM_VIEW = [-0.6, 0.6, -0.6, 0.6, -0.6, 0.4, -0.4, 0.4, -0.4, 0.2, -0.2, 0.0]


def views(shake: CameraShake, first: int, last: int) -> list[float]:
    return [shake.offset(tick) for tick in range(first, last + 1)]


class CurveTests(unittest.TestCase):
    """Section 6: the offsets shown from the tick after the trigger N."""

    def test_the_strong_list(self):
        shake = CameraShake()
        shake.start(10, STRONG)
        self.assertEqual(shake.offset(10), 0.0)  # the trigger tick's view is as before
        self.assertEqual(views(shake, 11, 26), STRONG_VIEW)

    def test_the_medium_list(self):
        shake = CameraShake()
        shake.start(10, MEDIUM)
        self.assertEqual(views(shake, 11, 22), MEDIUM_VIEW)

    def test_a_complete_shake_alternates_from_minus_and_sums_to_its_first_value(self):
        for offsets, total in ((STRONG, -1.0), (MEDIUM, -0.6)):
            with self.subTest(len(offsets)):
                self.assertEqual(len(offsets), 15 if offsets is STRONG else 11)
                self.assertTrue(all((value < 0) == (index % 2 == 0) for index, value in enumerate(offsets)))
                self.assertAlmostEqual(sum(offsets), total)

    def test_no_shake_is_exactly_zero(self):
        self.assertEqual(views(CameraShake(), -1, 50), [0.0] * 52)


class RestartTests(unittest.TestCase):
    """Section 4 and the section 6 scenarios: a new trigger restarts the list with its own strength."""

    def test_a_giant_dying_during_a_strong_shake_restarts_the_medium_list(self):
        shake = CameraShake()
        shake.start(0, STRONG)
        shake.start(6, MEDIUM)
        self.assertEqual(shake.offset(6), 0.8)  # still the strong shake in the trigger tick's view
        self.assertEqual(views(shake, 7, 18), MEDIUM_VIEW)

    def test_conflagration_during_a_medium_shake_restarts_the_strong_list(self):
        shake = CameraShake()
        shake.start(0, MEDIUM)
        shake.start(3, STRONG)
        self.assertEqual(views(shake, 4, 19), STRONG_VIEW)

    def test_two_triggers_on_one_tick_act_as_one_with_the_later_strength(self):
        shake = CameraShake()
        shake.start(0, STRONG)
        shake.start(5, STRONG)
        shake.start(5, MEDIUM)
        self.assertEqual(shake.offset(5), -1.0)  # the shake from tick 0, not the overwritten one
        self.assertEqual(views(shake, 6, 17), MEDIUM_VIEW)


class TriggerTests(EffectTestCase):
    """Section 5: Da Krunch's stand and Conflagration's impact are strong shakes."""

    def step(self, times: int = 1) -> None:
        for _ in range(times):
            spell_effects.tick(self.battle)
            self.battle.tick_count += 1

    def shown(self) -> float:
        return self.battle.camera_shake_offset

    def test_da_krunch_shakes_from_the_tick_after_the_foot_stands(self):
        self.make()
        self.launch(spell_effects.DA_KRUNCH, 0, 400)
        self.step(spell_effects.KRUNCH_STAND)  # T .. T+9: no shake while the foot falls
        self.assertIsNone(self.battle.camera_shake.current)
        self.step()  # T+10: the foot stands
        self.assertEqual(self.shown(), 0.0)
        self.step()
        self.assertEqual(self.shown(), -1.0)
        offsets = [self.shown()]
        for _ in range(15):
            self.step()
            offsets.append(self.shown())
        self.assertEqual(offsets, STRONG_VIEW)

    def test_conflagration_shakes_from_the_tick_after_the_impact(self):
        self.make()
        self.dice(2)  # k = 3: the impact is at T + 9k + 10 = T + 37
        self.launch(spell_effects.CONFLAGRATION, 0, 400)
        self.step(37)  # the fuse and the fall: no shake
        self.assertIsNone(self.battle.camera_shake.current)
        self.step()  # T+37
        self.assertEqual(self.battle.camera_shake.current, camera_shake.Shake(38, STRONG))

    def test_an_enemy_cast_shakes_the_same(self):
        self.make(wizard_side=Side.ENEMY)
        self.launch(spell_effects.DA_KRUNCH, 0, 400)
        self.step(spell_effects.KRUNCH_STAND + 2)
        self.assertEqual(self.shown(), -1.0)


class GiantDeathTests(unittest.TestCase):
    def test_a_giant_death_blast_starts_a_medium_shake(self):
        giant = Regiment("giant", "giant", 100, 100, 0, Side.PLAYER, models=1, sprite="GIANT")
        battle = Battle(1000, 1000, [giant], seed=1995)
        combat.kill_models(giant, [0], battle, animation.DEATH_MISSILE)
        trigger = battle.tick_count
        battle.tick()
        self.assertEqual(battle.camera_shake.current, camera_shake.Shake(trigger + 1, MEDIUM))

    def test_an_ordinary_death_does_not_shake(self):
        unit = Regiment("u", "u", 100, 100, 0, Side.PLAYER, models=1)
        battle = Battle(1000, 1000, [unit], seed=1995)
        combat.kill_models(unit, [0], battle, animation.DEATH_MISSILE)
        battle.tick()
        self.assertIsNone(battle.camera_shake.current)


class PresentationTests(unittest.TestCase):
    def test_a_shake_draws_nothing_from_the_battle_random_stream(self):
        battle = Battle(1000, 1000, [], seed=1995)
        state = battle.rng.getstate()
        battle.shake_camera(STRONG)
        battle.tick()
        self.assertEqual(battle.rng.getstate(), state)

    def test_a_pause_freezes_the_shake(self):
        battle = Battle(1000, 1000, [], seed=1995)
        battle.phase = "battle"
        battle.shake_camera(STRONG)
        battle.tick()
        battle.tick()
        self.assertEqual(battle.camera_shake_offset, -1.0)
        battle.paused = True
        battle.tick()
        self.assertEqual(battle.camera_shake_offset, -1.0)

    def test_the_lift_translates_the_eye_without_re_aiming(self):
        camera = BattleCamera(800.0, 800.0)
        still: Projection = camera.projection(640, 480, 1600, 1600)
        shaken = camera.projection(640, 480, 1600, 1600, eye_lift=-1.0)
        self.assertAlmostEqual(shaken.eye[1], still.eye[1] - 1.0)
        self.assertEqual((shaken.eye[0], shaken.eye[2]), (still.eye[0], still.eye[2]))
        self.assertEqual((shaken.view_direction, shaken.up, shaken.right), (still.view_direction, still.up, still.right))


if __name__ == "__main__":
    unittest.main()
