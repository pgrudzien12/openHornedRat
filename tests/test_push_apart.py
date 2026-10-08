"""Push-apart rows of the collision pass (notes/script_behaviours.md 2.2)."""

import unittest

from whshr.engine import Battle, Regiment
from whshr.rules import Side


def unit(identifier, x, y, side=Side.PLAYER, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=extra.pop("models", 10), ranks=2, points=10, **extra)


def wagon(identifier, x, y, side=Side.PLAYER):
    return Regiment(identifier, identifier, x, y, 0, side, models=2, ranks=1, points=10, unit_class=7)


def gap(first, second):
    import math
    return math.hypot(first.x - second.x, first.y - second.y)


class PushApartTests(unittest.TestCase):
    def pass_for(self, mover, *others):
        battle = Battle(2000, 2000, [mover, *others], seed=1995)
        mover.collision_recheck = True
        battle._resolve_collisions()
        return battle

    def test_friends_are_pushed_apart_by_half_the_overlap_each_and_both_rechecked(self):
        mover, friend = unit("A", 500, 500), unit("B", 510, 500)
        needed = mover.bounding_radius() + friend.bounding_radius()
        self.pass_for(mover, friend)
        self.assertAlmostEqual(gap(mover, friend), needed)
        self.assertAlmostEqual(mover.x, 500 - (needed - 10) / 2)
        self.assertAlmostEqual(friend.x, 510 + (needed - 10) / 2)
        self.assertTrue(mover.collision_recheck and friend.collision_recheck)

    def test_no_pass_without_the_re_check_state(self):
        mover, friend = unit("A", 500, 500), unit("B", 510, 500)
        battle = Battle(2000, 2000, [mover, friend], seed=1995)
        battle._resolve_collisions()
        self.assertEqual((mover.x, friend.x), (500, 510))

    def test_nothing_moves_when_either_is_in_melee_broken_or_pursuing(self):
        for field in ("in_melee", "pursuing"):
            with self.subTest(field=field):
                mover, friend = unit("A", 500, 500), unit("B", 510, 500)
                setattr(friend, field, True)
                self.pass_for(mover, friend)
                self.assertEqual((mover.x, friend.x), (500, 510))
        mover, friend = unit("A", 500, 500), unit("B", 510, 500)
        mover.routing = True  # a broken mover pushes no friend
        self.pass_for(mover, friend)
        self.assertEqual((mover.x, friend.x), (500, 510))

    def test_a_routing_footprint_is_not_scanned(self):
        mover, router = unit("A", 500, 500), unit("B", 510, 500)
        router.routing = True
        self.pass_for(mover, router)
        self.assertEqual((mover.x, router.x), (500, 510))

    def test_enemy_regiments_are_not_pushed_apart(self):
        mover, enemy = unit("A", 500, 500), unit("B", 510, 500, Side.ENEMY)
        self.pass_for(mover, enemy)
        self.assertEqual((mover.x, enemy.x), (500, 510))

    def test_enemy_wagon_is_pushed_apart_only_when_the_mover_is_broken_or_in_a_walk_back_reform(self):
        mover, cart = unit("A", 500, 500), wagon("W", 506, 500, Side.ENEMY)
        self.pass_for(mover, cart)
        self.assertEqual((mover.x, cart.x), (500, 506))
        mover, cart = unit("A", 500, 500), wagon("W", 506, 500, Side.ENEMY)
        mover.routing = True
        self.pass_for(mover, cart)
        self.assertNotEqual((mover.x, cart.x), (500, 506))
        mover, cart = unit("A", 500, 500), wagon("W", 506, 500, Side.ENEMY)
        mover.reforming = mover.reform_walk_back = True
        self.pass_for(mover, cart)
        self.assertNotEqual((mover.x, cart.x), (500, 506))

    def test_friendly_wagon_is_pushed_apart_like_a_regiment(self):
        mover, cart = unit("A", 500, 500), wagon("W", 506, 500)
        self.pass_for(mover, cart)
        self.assertNotEqual((mover.x, cart.x), (500, 506))

    def test_marked_units_are_not_touched(self):
        from whshr import interpreter
        mover, friend = unit("A", 500, 500), unit("B", 510, 500)
        battle = Battle(2000, 2000, [mover, friend], seed=1995)
        battle.event_bus.unit_states["B"].unit_flags |= interpreter.LEAVING_BATTLE_FLAG
        mover.collision_recheck = True
        battle._resolve_collisions()
        self.assertEqual((mover.x, friend.x), (500, 510))

    def test_unscripted_battle_clears_the_re_check_states_after_the_tick(self):
        mover, friend = unit("A", 500, 500), unit("B", 700, 500)
        battle = Battle(2000, 2000, [mover, friend], seed=1995)
        mover.target_x, mover.target_y = 600, 500
        battle.tick()
        self.assertFalse(mover.collision_recheck or friend.collision_recheck)


if __name__ == "__main__":
    unittest.main()
