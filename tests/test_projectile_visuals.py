"""BDD scenarios for the projectile spells' visuals other than the Fireball (notes/spell_visuals.md)."""
import unittest

from whshr import spell_effects
from whshr.frontend.spell_visuals import (DirectionalSprite, ProjectileVisuals, Shot, Sprite, bearing, breath_stage,
                                          projectile_shots)


def shot(code, x, y=0.0, height=8.0, start=(0.0, 0.0), dest=(1000.0, 0.0), remaining=0, steps=18, ending=False,
         key=(1, 0)):
    return Shot(key, code, x, y, height, start, dest, remaining, steps, ending)


def mesh_names(visuals):
    return [item.name for item in visuals.meshes()]


class HuntingSpearTest(unittest.TestCase):
    def test_the_head_cycles_the_four_spear_meshes_and_turns_to_each_leg(self):
        visuals = ProjectileVisuals()
        names, headings = [], []
        for tick in range(5):
            dest = (1000.0, 0.0) if tick < 2 else (0.0, 1000.0)  # a re-aim on the third tick
            visuals.advance([shot(spell_effects.HUNTING_SPEAR, 10.0 * tick, dest=dest)])
            [item] = visuals.meshes()
            names.append(item.name)
            headings.append((item.dx, item.dy))
        self.assertEqual(names, ["spear1", "spear2", "spear3", "spear4", "spear1"])
        self.assertEqual(headings[1], (1000.0, 0.0))
        self.assertEqual(headings[2], (0.0, 1000.0))

    def test_the_spear_vanishes_when_its_effect_is_gone(self):
        visuals = ProjectileVisuals()
        visuals.advance([shot(spell_effects.HUNTING_SPEAR, 0.0)])
        visuals.advance([])
        self.assertEqual((visuals.meshes(), visuals.sprites()), ([], []))


class BeamTest(unittest.TestCase):
    def fly(self, ticks, step=20.0, end_at=None):
        visuals = ProjectileVisuals()
        for tick in range(ticks):
            ending = end_at is not None and tick == end_at
            visuals.advance([shot(spell_effects.LIGHTNING, step * tick, dest=(step * end_at if end_at else 1000.0, 0.0),
                                  ending=ending)])
        return visuals

    def test_segments_are_left_about_every_32_units_and_loop_the_mesh_set(self):
        visuals = self.fly(5)  # head at 0, 20, 40, 60, 80
        segments = [item for item in visuals.meshes()][1:]
        self.assertEqual([item.x for item in segments], [0.0, 40.0])  # 20 is not more than 32 from 0
        self.assertEqual([item.name for item in segments], ["light1", "light2"])  # ages 4 and 1
        self.assertEqual(visuals.meshes()[0].name, "light1")  # the head on its fifth tick

    def test_arrival_leaves_a_last_segment_facing_back_then_flashes_and_clears(self):
        visuals = self.fly(4, end_at=3)  # ends at x 60 = the destination
        items = visuals.meshes()
        self.assertEqual((items[-1].x, items[-1].dx), (60.0, -60.0))
        self.assertNotIn("head", [item.name for item in items])
        flashes = [sprite.frame for sprite in visuals.sprites() if isinstance(sprite, Sprite)]
        self.assertEqual(flashes, [433])
        for _ in range(6):
            visuals.advance([])
        self.assertEqual([sprite.frame for sprite in visuals.sprites() if isinstance(sprite, Sprite)], [439])
        visuals.advance([])
        self.assertEqual((visuals.meshes(), visuals.sprites()), ([], []))

    def test_each_beam_has_its_own_flash(self):
        for code, first in ((spell_effects.WARP_LIGHTNING, 522), (spell_effects.GAZE, 464)):
            visuals = ProjectileVisuals()
            visuals.advance([shot(code, 0.0, dest=(10.0, 0.0), ending=True)])
            self.assertEqual([s.frame for s in visuals.sprites() if isinstance(s, Sprite)], [first])


class SpriteProjectileTest(unittest.TestCase):
    def test_the_burning_head_is_a_directional_skull_with_a_fire_trail(self):
        visuals = ProjectileVisuals()
        for tick in range(3):
            visuals.advance([shot(spell_effects.BURNING_HEAD, 10.0 * tick, start=(0.0, 0.0), dest=(0.0, 100.0))])
        heads = [s for s in visuals.sprites() if isinstance(s, DirectionalSprite)]
        puffs = sorted(s.frame for s in visuals.sprites() if isinstance(s, Sprite))
        self.assertEqual([(h.first, h.bearing) for h in heads], [(32, bearing(0.0, 100.0))])
        self.assertEqual(puffs, [40, 42])  # launch puff, then one at 10 (tick 1 still at the newest puff)

    def test_the_burning_head_stays_until_its_last_puff_fades(self):
        visuals = ProjectileVisuals()
        visuals.advance([shot(spell_effects.BURNING_HEAD, 0.0, ending=True)])
        for _ in range(19):
            visuals.advance([])
        self.assertEqual([s.frame for s in visuals.sprites()], [59])
        visuals.advance([])
        self.assertEqual(visuals.sprites(), [])

    def test_breath_stages_follow_the_report_table(self):
        # N = 18; the table's r is this tick's ticks left, the effect's remaining count + 1 after the step.
        stages = {r: breath_stage(r - 1, 18) for r in (18, 14, 13, 9, 8, 5, 4, 0)}
        self.assertEqual(stages, {18: 0, 14: 0, 13: 1, 9: 1, 8: 2, 5: 2, 4: 3, 0: 3})

    def test_breath_leaves_frozen_clouds_then_removes_them_oldest_first(self):
        visuals = ProjectileVisuals()
        for tick, remaining in enumerate((17, 16, 15)):
            visuals.advance([shot(spell_effects.PESTILENT_BREATH, 10.0 * tick, remaining=remaining)])
        clouds = [(s.frame, s.x) for s in visuals.sprites()][1:]
        self.assertEqual(clouds, [(533, 0.0), (533, 10.0)])
        visuals.advance([shot(spell_effects.PESTILENT_BREATH, 30.0, remaining=14, ending=True)])
        visuals.advance([])
        self.assertEqual([s.x for s in visuals.sprites()], [10.0, 20.0])


class EffectsToShotsTest(unittest.TestCase):
    def effect(self, code, **fields):
        effect = spell_effects.Effect(1, code, "W", False, False, (0.0, 0.0), elapsed=1, **fields)
        return effect

    def test_a_bolt_reports_its_flight_and_its_ending_once(self):
        memory = {}
        bolt = self.effect(spell_effects.LIGHTNING, x=40.0, start=(0.0, 0.0), dest=(100.0, 0.0), remaining=3,
                           steps=6, height=4.0)
        shots, _ = projectile_shots([bolt], memory)
        self.assertEqual([(s.code, s.x, s.ending) for s in shots], [(spell_effects.LIGHTNING, 40.0, False)])
        bolt.tail = 8
        self.assertEqual([s.ending for s in projectile_shots([bolt], memory)[0]], [True])
        bolt.tail = 7
        self.assertEqual(projectile_shots([bolt], memory)[0], [])

    def test_storm_bolts_are_lightning_shots_and_start_the_storm_sprite_runs(self):
        memory = {}
        storm = self.effect(spell_effects.STORM)
        shots, runs = projectile_shots([storm], memory)
        self.assertEqual((shots, runs), ([], [(1, "W", True)]))
        storm.flying = True
        shots, runs = projectile_shots([storm], memory)
        self.assertEqual(([(s.key, s.code) for s in shots], runs), ([((1, 1), spell_effects.LIGHTNING)], [(1, "W", False)]))
        storm.flying = False
        self.assertEqual([s.ending for s in projectile_shots([storm], memory)[0]], [True])
        storm.flying = True  # the next bolt, from the same start point
        shots, runs = projectile_shots([storm], memory)
        self.assertEqual(([s.key for s in shots], runs), ([(1, 2)], [(1, "W", False)]))


if __name__ == "__main__":
    unittest.main()
