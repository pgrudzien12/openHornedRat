"""BDD scenarios for the Storm of Shemtek's storm sprite (notes/spell_storm_visuals.md), driven through the real
spell effect so the frame follows the effect's own wind-up, bolts and closing.

Given wizard W casting a Storm of 3 bolts (dice 2, 0 -> 2 + 1 bolts) with no other spell running, every bolt flying 20
ticks from its launch and nothing in the way.
"""
import unittest
from unittest import mock

from tests.test_spell_effects import EffectTestCase, unit
from whshr import spell_effects
from whshr.frontend.spell_visuals import ProjectileVisuals, projectile_shots, storm_frame


class StormSpriteTests(EffectTestCase):
    def setUp(self):
        self.make(unit("A", 0, 450))
        self.dice(0, 0)  # 2 + 1 = 3 bolts
        self.calls = 0

        def fly(battle, effect, bolt):
            self.calls += 1
            if self.calls == 20:
                self.calls = 0
                return True
            return False

        patcher = mock.patch.object(spell_effects, "_fly", fly)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.visuals, self.memory = ProjectileVisuals(), {}
        self.point = {"W": (100.0, 200.0)}

    def launch_storm(self):
        self.launch(spell_effects.STORM, 0, 400)

    def step(self):
        """One tick: the effect update, then the presentation."""
        self.update()
        shots, storms = projectile_shots(spell_effects.table(self.battle).active, self.memory)
        self.visuals.advance(shots)
        self.visuals.set_storms(storms, lambda owner: self.point.get(owner))

    def frames(self):
        return [(s.frame, s.x, s.y, s.height) for s in self.visuals.sprites() if 391 <= s.frame <= 400]

    def frame(self):
        [(frame, *_rest)] = self.frames()
        return frame

    def run_until_end(self):
        """Frames per tick (age from 0) until the sprite is gone."""
        out = []
        for _ in range(400):
            self.step()
            if not self.frames():
                break
            out.append(self.frame())
        return out

    def test_the_wind_up_shows_391_to_394_then_the_loop_starts_with_the_first_bolt(self):
        self.launch_storm()
        storm = self.effects()[0]
        seen = []
        for _ in range(6):
            self.step()
            seen.append((self.frame(), storm.flying))
        self.assertEqual(seen, [(391, False), (392, False), (393, False), (394, False), (395, True), (396, True)])

    def test_the_loop_runs_on_through_every_bolt_flash_and_release_without_restarting(self):
        self.launch_storm()
        frames = self.run_until_end()
        closing = frames[-2:]
        self.assertEqual(closing, [399, 400])
        body = frames[4:-2]
        self.assertEqual(body, [395 + age % 4 for age in range(4, 4 + len(body))])
        # bolt 2 leaves in the update that follows bolt 1's end + 7 ticks: the loop frame there is the plain one
        self.assertEqual(frames[4 + 31 - 4 + 0], 395 + 31 % 4)

    def test_the_closing_starts_seven_ticks_after_the_last_bolt_ends_and_the_sprite_goes_two_later(self):
        self.launch_storm()
        ends, was_flying = [], False
        storm = self.effects()[0]
        for tick in range(400):
            self.step()
            if was_flying and not storm.flying:
                ends.append(tick)
            was_flying = storm.flying
            if not self.frames():
                gone = tick
                break
        last = ends[-1]
        self.assertEqual(len(ends), 3)
        self.assertEqual(gone, last + 9)
        self.assertEqual(self.visuals.sprites(), [])

    def test_the_sprite_is_on_the_ground_at_the_first_figure_at_launch_and_does_not_follow(self):
        self.launch_storm()
        self.step()
        self.assertEqual(self.frames(), [(391, 100.0, 200.0, 0.0)])
        self.point["W"] = (160.0, 200.0)  # the wizard walks away
        for _ in range(30):
            self.step()
        self.assertEqual([(x, y) for _f, x, y, _h in self.frames()], [(100.0, 200.0)])

    def test_a_dispel_removes_the_sprite_in_that_update_without_a_closing(self):
        self.launch_storm()
        self.step()
        self.step()
        spell_effects._end(self.battle, self.effects()[0])
        self.step()
        self.assertEqual(self.frames(), [])

    def test_the_caster_being_removed_ends_the_sprite_at_once(self):
        self.launch_storm()
        for _ in range(10):
            self.step()
        self.battle.remove_from_play(self.battle.regiments["W"])
        self.step()
        self.assertEqual(self.frames(), [])

    def test_the_recorded_target_being_removed_ends_the_sprite_at_once(self):
        self.launch_storm()
        for _ in range(10):
            self.step()
        self.battle.remove_from_play(self.battle.regiments["A"])
        self.step()
        self.assertEqual(self.frames(), [])

    def test_the_caster_in_melee_does_not_end_it(self):
        self.launch_storm()
        for _ in range(10):
            self.step()
        self.battle.regiments["W"].in_melee = True
        self.step()
        self.assertEqual(len(self.frames()), 1)


class StormFrameTests(unittest.TestCase):
    def test_vectors_of_the_report(self):
        self.assertEqual([storm_frame(a, False, 0) for a in range(9)], [391, 392, 393, 394, 395, 396, 397, 398, 395])
        self.assertEqual(storm_frame(31, False, 0), 398)
        self.assertEqual(storm_frame(80, False, 0), 395)
        self.assertEqual((storm_frame(81, True, 1), storm_frame(82, True, 0)), (399, 400))


if __name__ == "__main__":
    unittest.main()
