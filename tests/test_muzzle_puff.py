"""A gun's muzzle puff at each puff of its shot (notes/machine_figure_animation.md 2.1, notes/volley_gun_shot.md 4,
GitHub #342)."""

import unittest

from whshr.engine import MUZZLE_PUFF_TICKS, Battle, Regiment
from whshr import ranged
from whshr.rules import Side

ARTILLERY = 4  # s_race class


def machine(sprite, direction):
    return Regiment("G", "G", 100, 100, direction, Side.PLAYER, models=3, ranks=1, unit_class=ARTILLERY,
                    hud_class="art", sprite="Crew", leader_sprite=sprite, has_leader=True, missile_code=11,
                    shooting_code=11, missile_range=ranged.WEAPONS[11].reach, bs=3)


def fire(sprite="ImpCanon", direction=128, point=(1000, 100)):
    """A machine at (100, 100) ordered to fire at a ground point straight ahead (no turn before the shot)."""
    gun = machine(sprite, direction)
    battle = Battle(3000, 3000, [gun], seed=1995)
    battle.phase = "battle"
    battle.order_fire("G", point=point)
    return battle, gun


def run_until_puff(battle, limit=30):
    for _ in range(limit):
        battle.tick()
        if battle.muzzle_puffs:
            return battle.muzzle_puffs[0]
    return None


class MuzzlePuffTests(unittest.TestCase):
    def test_a_cannon_shot_spawns_one_puff_24_ahead_of_the_unit_position(self):
        battle, _ = fire(direction=128)  # a quarter turn clockwise from +Y: facing +X
        puff = run_until_puff(battle)
        self.assertEqual((puff.x, puff.y), (124, 100))  # not ahead of the machine figure (volley_gun_shot.md 4)
        self.assertEqual(len(battle.muzzle_puffs), 1)

    def test_the_puff_is_turned_by_the_unit_facing(self):
        battle, _ = fire(direction=0, point=(100, 1000))  # facing +Y
        self.assertEqual((run_until_puff(battle).x, run_until_puff(battle).y), (100, 124))

    def test_the_offset_uses_truncated_x256_direction_values(self):
        battle, _ = fire(direction=64, point=(500, 500))  # an eighth turn: SIN = COS = trunc(256 x 0.7071) = 181
        puff = run_until_puff(battle)
        self.assertEqual((puff.x, puff.y), (116, 116))  # trunc(24 x 181 / 256) = 16

    def test_the_puff_shows_four_frames_one_per_tick_then_ends(self):
        battle, _ = fire()
        puff = run_until_puff(battle)
        frames = [puff.frame(battle.tick_count)]
        for _ in range(MUZZLE_PUFF_TICKS):
            battle.tick()
            frames.append(puff.frame(battle.tick_count))
        self.assertEqual(frames, [0, 1, 2, 3, None])
        battle.tick()
        self.assertEqual(battle.muzzle_puffs, [])

    def test_a_great_cannon_and_a_volley_gun_puff_but_a_rock_lobber_does_not(self):
        for sprite, puffs in (("GrtCanon", True), ("VoleyGun", True), ("RockLob", False)):
            with self.subTest(sprite=sprite):
                battle, _ = fire(sprite)
                self.assertEqual(run_until_puff(battle) is not None, puffs)


if __name__ == "__main__":
    unittest.main()
