"""User-requested linear descent of fading dragon trails, independent of projectile flight."""
import unittest

from whshr.frontend.spell_visuals import DragonFlameFlights, FireballVisuals, Flight, PUFF_FRAMES
from whshr.ranged import InnateProjectile


class DragonTrailDescentTests(unittest.TestCase):
    def setUp(self):
        self.flame = InnateProjectile('dragon', 14, 100, 200, 0, 200, x=100, y=200, z=40)
        self.adapter = DragonFlameFlights()
        self.visuals = FireballVisuals()

    def step(self, flames):
        self.visuals.advance(self.adapter.sample(flames, lambda x, y: 0))
        return self.visuals.sprites()

    def test_fading_puff_descends_linearly_from_its_birth_height_to_ground(self):
        shown = self.step([self.flame])
        heights = [shown[-1].height]
        for age in range(1, PUFF_FRAMES):
            shown = self.step([])
            puff = next(s for s in shown if s.frame == 125 + age)
            heights.append(puff.height)
            self.assertEqual((puff.x, puff.y), (100, 200))
        self.assertEqual(heights[0], 40)
        self.assertEqual(heights[-1], 0)
        for age, height in enumerate(heights):
            self.assertAlmostEqual(height, 40 * (1 - age / (PUFF_FRAMES - 1)))
        self.assertFalse(any(s.frame < 177 for s in self.step([])))

    def test_live_head_and_projectile_are_unchanged_while_old_trail_descends(self):
        self.step([self.flame])
        self.flame.x = 90
        shown = self.step([self.flame])
        head = next(s for s in shown if s.x == 90)
        puff = next(s for s in shown if s.x == 100)
        self.assertEqual(head.height, 40)
        self.assertLess(puff.height, 40)
        self.assertEqual((self.flame.x, self.flame.y, self.flame.z), (90, 200, 40))

    def test_cast_fireball_trail_keeps_its_existing_height_policy(self):
        visuals = FireballVisuals()
        visuals.advance([Flight(1, 100, 200, 40, True)])
        for age in range(1, PUFF_FRAMES):
            visuals.advance([])
            puff = next(s for s in visuals.sprites() if s.frame == 125 + age)
            self.assertEqual(puff.height, 40)
