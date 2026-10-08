"""Push-apart rows of the collision pass (notes/script_behaviours.md 2.2)."""

import unittest
from unittest import mock

from tests.script_helpers import FakeDll, word
from whshr import behaviour
from whshr.engine import Battle, Regiment
from whshr.rules import Side

IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


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

    def test_only_the_pass_taker_moves_and_the_pair_separates_over_several_passes(self):
        # notes/script_behaviours.md 2.2 "Push apart, exactly": radii 30 + 30, centres 50 apart (o = -10).
        mover, friend = unit("A", 500, 500), unit("B", 550, 500)
        with mock.patch.object(Regiment, "bounding_radius", return_value=30):
            battle = Battle(2000, 2000, [mover, friend], seed=1995)
            mover.collision_recheck = True
            battle._resolve_collisions()  # A's pass: A moves 6 away; B (later in order) is flagged and moves 3 itself
            self.assertEqual((mover.x, friend.x), (494, 553))
            battle._resolve_collisions()  # B's push flagged A again: o = -1, A moves 1
            self.assertEqual((mover.x, friend.x), (493, 553))
            battle._resolve_collisions()  # overlap gone: nothing moves
            self.assertEqual((mover.x, friend.x), (493, 553))

    def test_one_friendly_push_per_pass_and_a_wagon_mover_is_never_moved(self):
        with mock.patch.object(Regiment, "bounding_radius", return_value=30):
            mover, left, right = unit("B", 500, 500), unit("A", 450, 500), unit("C", 550, 500)
            battle = Battle(2000, 2000, [mover, left, right], seed=1995)
            battle._push_apart_pass(mover, [left, mover, right])  # one unit's pass only
            moved = (mover.x != 500)
            self.assertTrue(moved)
            self.assertEqual((left.x, right.x), (450, 550))  # neither neighbour moved in the pass
            self.assertTrue(left.collision_recheck and right.collision_recheck)  # both only switched on
            cart = wagon("W", 500, 500)
            other = unit("O", 520, 500)
            battle = Battle(2000, 2000, [cart, other], seed=1995)
            cart.collision_recheck = True
            battle._resolve_collisions()
            self.assertEqual(cart.x, 500)
            self.assertTrue(other.collision_recheck)

    def test_a_push_ahead_of_a_charging_mover_ends_the_charge(self):
        with mock.patch.object(Regiment, "bounding_radius", return_value=30):
            charger, friend = unit("A", 500, 500), unit("B", 500, 540)  # B straight ahead (facing 0 = +y)
            enemy = unit("E", 500, 900, Side.ENEMY)
            battle = Battle(2000, 2000, [charger, friend, enemy], seed=1995)
            charger.attack_target = charger.charge_started_target = "E"
            charger.collision_recheck = True
            battle._resolve_collisions()
            self.assertIsNone(charger.attack_target)
            self.assertIn(0x09, [e.code for e in battle.event_bus.unit_states["E"].event_queue])

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

    def test_re_check_states_set_by_a_push_survive_the_scripted_contact_sweep(self):
        # Through the real tick with a script running: the contact sweep clears every visited unit's state, so
        # the final one-unit move of the 2.2 example (o = -1) only happens if the push's switch-ons are restored.
        with mock.patch.object(Regiment, "bounding_radius", return_value=30):
            mover, friend = unit("A", 500, 500), unit("B", 550, 500)
            battle = Battle(2000, 2000, [mover, friend], seed=1995, script_dll=FakeDll(IDLE))
            mover.collision_recheck = True
            battle.tick()
            self.assertEqual((mover.x, friend.x), (494, 553))
            self.assertTrue(mover.collision_recheck)
            battle.tick()
            self.assertEqual((mover.x, friend.x), (493, 553))

    def test_enemy_machine_with_overlapping_circles_gets_its_re_check_state_on(self):
        with mock.patch.object(Regiment, "bounding_radius", return_value=22.5):
            mover, cart = unit("A", 500, 500), wagon("W", 543, 500, Side.ENEMY)
            battle = Battle(2000, 2000, [mover, cart], seed=1995)
            battle._push_apart_pass(mover, [mover, cart])
            self.assertEqual((mover.x, cart.x), (500, 543))  # not pushed apart
            self.assertTrue(cart.collision_recheck)
            cart.collision_recheck = False  # the contact sweep visited it
            battle._restore_carried_rechecks()
            self.assertTrue(cart.collision_recheck)


if __name__ == "__main__":
    unittest.main()
