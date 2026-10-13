"""User-requested straight dragon flame flight to ground, leaving a stationary fading trail."""
import unittest

from whshr import ranged
from whshr.engine import Battle, Regiment
from whshr.frontend.spell_visuals import DragonFlameFlights, FireballVisuals
from whshr.rules import Side


class DragonTrailFlightPathTests(unittest.TestCase):
    def launch(self, ground=lambda x, y: 0):
        unit = Regiment('dragon', 'Dragon', 1000, 1000, 384, Side.ENEMY, models=1, ranks=1,
                        sprite='MeshDragon', shooting_code=14, missile_range=576, unit_class=1)
        battle = Battle(2000, 2000, [unit])
        battle.ground_height = ground
        ranged.launch_shot(battle, unit, (unit.x, unit.y), (800, 1000))
        return battle

    def test_fireball_follows_straight_line_from_elevated_origin_to_target_ground(self):
        battle = self.launch()
        flame = battle.innate_projectiles[0]
        self.assertEqual((flame.z0, flame.z1), (40, 0))
        for step in range(1, 10):
            ranged._step_innate(battle)
            t = step / 9
            self.assertAlmostEqual(flame.x, flame.x0 + (flame.x1 - flame.x0) * t)
            self.assertAlmostEqual(flame.y, flame.y0 + (flame.y1 - flame.y0) * t)
            self.assertLess(abs(flame.z - (40 * (1 - t))), 1)  # integer height interpolation
        self.assertEqual(flame.z, 0)

    def test_target_ground_height_is_respected_on_uneven_terrain(self):
        battle = self.launch(lambda x, y: 8 if x >= 900 else 23)
        flame = battle.innate_projectiles[0]
        self.assertEqual((flame.z0, flame.z1), (48, 23))
        for _ in range(9):
            ranged._step_innate(battle)
        self.assertEqual(flame.z, 23)

    def test_trail_stays_on_recorded_flight_path_while_head_descends_and_puffs_fade(self):
        battle = self.launch()
        flame = battle.innate_projectiles[0]
        adapter, visuals = DragonFlameFlights(), FireballVisuals()
        visuals.advance(adapter.sample(battle.innate_projectiles, battle.ground_height))
        for tick in range(1, 15):
            ranged._step_innate(battle)
            visuals.advance(adapter.sample(battle.innate_projectiles, battle.ground_height))
            original_puffs = [s for s in visuals.sprites()
                              if (s.x, s.y, s.frame) == (flame.x0, flame.y0, 125 + tick)]
            self.assertTrue(original_puffs)
            self.assertTrue(all(s.height == 40 for s in original_puffs))
            if tick < 9:
                heads = [s for s in visuals.sprites() if (s.x, s.y) == (flame.x, flame.y)]
                self.assertTrue(any(s.height == flame.z for s in heads))
                self.assertLess(flame.z, 40)
