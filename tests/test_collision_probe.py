"""What CheckCollisions answers (notes/collision_probe_result.md 3): the last per-footprint answer wins, and a wagon is
never moved by a push, so a wagon held only by friends answers false and restarts (the BF006 convoy jam)."""

import unittest

from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def wagon(identifier: str, x: float, y: float, side: Side = Side.NEUTRAL, models: int = 2) -> Regiment:
    return Regiment(identifier, identifier, x, y, 0, side, models=models, ranks=1, unit_class=7)


def infantry(identifier: str, x: float, y: float, side: Side = Side.PLAYER) -> Regiment:
    return Regiment(identifier, identifier, x, y, 256, side, models=10, ranks=2)


class ProbeTestCase(unittest.TestCase):
    def build(self, *regiments: Regiment) -> None:
        self.battle = Battle(1000, 1000, list(regiments), seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def probe(self, unit_id: str, latched: bool = False) -> interpreter.UnitScriptState:
        state = self.battle.event_bus.unit_states[unit_id]
        state.contact_latch = latched
        self.interp.op_CheckCollisions(state, None, [], unit_id, 0, self.battle.rng)
        return state

    @staticmethod
    def events(state: interpreter.UnitScriptState) -> list[int]:
        return [event.code for event in state.event_queue]


class WagonProbeTests(ProbeTestCase):
    def test_a_given_a_friendly_cart_overlapping_only_from_behind_then_the_lead_cart_is_free_to_restart(self):
        lead, rear = wagon("lead", 500, 520), wagon("rear", 500, 500)
        self.build(lead, rear)
        state = self.probe("lead", latched=True)
        self.assertFalse(state.cond_flags)
        self.assertFalse(state.contact_latch)
        self.assertEqual(self.events(state), [])
        self.assertTrue(rear.collision_recheck)
        self.assertEqual((lead.x, lead.y), (500, 520))

    def test_b_given_a_friendly_cart_overlapping_ahead_then_0x27_is_queued_but_the_answer_is_false(self):
        self.build(wagon("lead", 500, 520), wagon("rear", 500, 500))
        state = self.probe("rear")
        self.assertFalse(state.cond_flags)
        self.assertEqual(self.events(state), [0x27])

    def test_c_given_friendly_infantry_ahead_then_the_wagon_is_not_moved_and_answers_false(self):
        cart, foot = wagon("cart", 500, 500), infantry("foot", 500, 530)
        self.build(cart, foot)
        state = self.probe("cart")
        self.assertFalse(state.cond_flags)
        self.assertEqual(self.events(state), [0x27])
        self.assertEqual((cart.x, cart.y), (500, 500))
        self.assertTrue(foot.collision_recheck)

    def test_c_prime_given_friendly_infantry_ahead_in_melee_then_the_0x27_answer_stands(self):
        cart, foot = wagon("cart", 500, 500), infantry("foot", 500, 530)
        foot.in_melee = True
        self.build(cart, foot)
        state = self.probe("cart")
        self.assertTrue(state.cond_flags)
        self.assertEqual(self.events(state), [0x27])

    def test_d_given_nothing_overlapping_then_false_and_the_latch_is_cleared(self):
        self.build(wagon("cart", 500, 500), infantry("far", 800, 800))
        state = self.probe("cart", latched=True)
        self.assertFalse(state.cond_flags)
        self.assertFalse(state.contact_latch)

    def test_f_given_an_enemy_ahead_touching_the_wagon_then_true_without_engagement(self):
        self.build(wagon("cart", 500, 500), infantry("goblins", 500, 510, Side.ENEMY))
        state = self.probe("cart")
        self.assertTrue(state.cond_flags)
        self.assertEqual(self.events(state), [0x27])
        self.assertFalse(self.battle.regiments["cart"].in_melee)

    def test_g_given_solid_scenery_then_the_wagon_is_not_moved_and_answers_false(self):
        cart = wagon("cart", 500, 500)
        self.build(cart)
        self.battle.objects.append({"x": 500, "y": 450, "radius": 20, "status": ["os_active", "os_solid"]})
        state = self.probe("cart")
        self.assertFalse(state.cond_flags)
        self.assertEqual((cart.x, cart.y), (500, 500))

    def test_given_a_cart_that_lost_one_model_then_it_still_probes_as_a_wagon(self):
        self.build(wagon("lead", 500, 520, models=1), wagon("rear", 500, 500))
        state = self.probe("lead")
        self.assertTrue(self.battle.regiments["lead"].is_wagon)
        self.assertFalse(state.cond_flags)


class RegimentProbeTests(ProbeTestCase):
    def test_e_given_a_friendly_regiment_overlapping_then_the_mover_is_pushed_away_and_answers_true(self):
        mover, friend = infantry("mover", 500, 500), infantry("friend", 500, 515)
        self.build(mover, friend)
        state = self.probe("mover")
        self.assertTrue(state.cond_flags)
        self.assertLess(mover.y, 500)
        self.assertTrue(friend.collision_recheck)

    def test_e_prime_given_a_push_then_an_untouched_enemy_later_in_the_list_then_the_last_answer_wins(self):
        mover, friend = infantry("mover", 500, 500), infantry("friend", 500, 515)
        enemy = Regiment("enemy", "enemy", 500, 455, 256, Side.ENEMY, models=4, ranks=1)
        self.build(mover, friend, enemy)
        self.assertTrue(self.battle.circles_overlap(mover, enemy))
        self.assertFalse(self.battle.footprints_overlap(mover, enemy))
        state = self.probe("mover")
        self.assertFalse(state.cond_flags)


if __name__ == "__main__":
    unittest.main()
