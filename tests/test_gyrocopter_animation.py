"""Gyrocopter figure animation (notes/machine_figure_animation.md 2.9, airborne_units.md A3.2, A5): the action table's
loops and wreck, the take-off lap on top of them, and the steam gun and bomb, which never wait on an animation event
(notes/gyrocopter_steam_gun.md 3, 4, 6.1, 7)."""

import random
import unittest

from whshr import animation, flight, ranged
from whshr.animation import DEAD, FIGHT, IDLE, SHOOT, STAND, WALK, WEAPON_READY
from whshr.engine import Battle, ModelState
from whshr.flight import GYROCOPTER, FlightState
from whshr.rules import Side

from tests.test_gyrocopter import ScriptedRandom, gyrocopter, steam_effects, target

FAST = [0, 1, 2, 3, 1, 2]
SLOW = [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 1, 1, 1, 2, 2]


def phases(action: int, ticks: int) -> list[int]:
    model = ModelState(uid=0)
    rng = random.Random(1)
    return [animation.step(model, action, rng, "gyrocopter")[1] for _ in range(ticks)]


class FamilyTests(unittest.TestCase):
    def test_both_gyrocopter_sprite_names_select_the_table(self):
        for sprite in ("GyroCopt", "Gyrocopter"):
            with self.subTest(sprite):
                self.assertEqual(animation.family_for(sprite, 3), "gyrocopter")

    def test_the_table_and_the_flight_profile_agree(self):
        self.assertEqual(GYROCOPTER.air_phases, tuple(FAST))
        self.assertEqual(GYROCOPTER.rest_phases, tuple(SLOW))


class LoopTests(unittest.TestCase):
    def test_actions_2_3_and_7_loop_the_fast_rotor_in_6_ticks(self):
        for action in (IDLE, WALK, SHOOT):
            with self.subTest(action):
                self.assertEqual(phases(action, 12), FAST * 2)

    def test_actions_1_4_and_5_loop_the_slow_rotor_in_17_ticks(self):
        for action in (STAND, FIGHT, WEAPON_READY):
            with self.subTest(action):
                self.assertEqual(phases(action, 34), SLOW * 2)

    def test_there_is_no_random_entry_and_the_rotor_group_is_used(self):
        model = ModelState(uid=0)
        rng = random.Random(1)
        state = rng.getstate()
        self.assertEqual(animation.step(model, IDLE, rng, "gyrocopter")[0], "move")
        self.assertEqual(rng.getstate(), state)

    def test_the_shoot_action_has_no_fire_step(self):
        model = ModelState(uid=0)
        rng = random.Random(1)
        for _ in range(40):
            animation.step(model, SHOOT, rng, "gyrocopter")
            self.assertFalse(model.fire_event)
            self.assertFalse(model.extra_post)

    def test_the_shoot_pose_is_not_a_one_shot(self):
        model = ModelState(uid=0)
        animation.step(model, SHOOT, random.Random(1), "gyrocopter")
        self.assertFalse(animation.one_shot_running(model, "gyrocopter"))


class DeadTests(unittest.TestCase):
    def test_the_dead_action_holds_wreck_group_32(self):
        model = ModelState(uid=0)
        rng = random.Random(1)
        for _ in range(5):
            self.assertEqual(animation.step(model, DEAD, rng, "gyrocopter"), (32, 0))

    def test_a_grounded_craft_leaves_a_wreck_of_group_32_with_a_random_facing(self):
        craft = gyrocopter()
        battle = Battle(3000, 3000, [craft], seed=1)
        battle.tick()
        model = craft.melee_models[0]
        corpse = animation.corpse_of(craft, model, 10, 20, battle.rng)
        self.assertEqual(corpse.group, 32)
        self.assertFalse(animation.family_table("gyrocopter")[DEAD].keeps_facing)

    def test_the_wreck_never_burns(self):
        self.assertFalse(animation.burns_on_death(animation.DEATH_FIRE, 3, "GyroCopt"))


class TakeOffTests(unittest.TestCase):
    """The take-off and landing laps stay with the flight state (they depend on whether the craft is flying); the table
    supplies the loop that follows."""

    def test_the_take_off_lap_then_the_fast_loop(self):
        state = FlightState(GYROCOPTER)
        shown = []
        for _ in range(40):
            state.take_request(IDLE)
            state.step()
            shown.append(state.frame()[1])
        lap = [0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 1, 1, 1, 2, 2, 2]
        self.assertEqual(shown[:32], lap * 2)  # A3.3: both laps through tick 32, the loop from tick 33
        self.assertEqual(shown[32:38], FAST[2:] + FAST[:2])  # the loop runs on the flight tick count
        self.assertEqual(state.elevation, 32)

    def test_a_grounded_craft_shows_the_same_rest_frames_from_the_table_and_the_flight_state(self):
        state = FlightState(GYROCOPTER)
        model = ModelState(uid=0)
        rng = random.Random(1)
        for tick in range(20):
            shown = animation.step(model, STAND, rng, "gyrocopter")
            state.take_request(STAND)
            state.step()
            self.assertEqual(shown, state.frame())


class WeaponsIndependentOfTheAnimationTests(unittest.TestCase):
    def setUp(self):
        self.craft = gyrocopter()
        self.enemy = target("E", 1000, 1300)
        self.battle = Battle(3000, 3000, [self.craft, self.enemy], seed=1995)

    def test_the_steam_gun_fires_on_fire_while_the_shoot_pose_has_no_fire_step(self):
        self.craft.script_action = SHOOT
        self.craft.script_action_key = self.craft.activity_key()
        self.assertTrue(self.battle.fire_steam_gun("G", (1000, 1300)))
        for _ in range(3):
            self.battle.tick()
        self.assertEqual(len(steam_effects(self.battle)), 1)
        self.assertEqual(self.craft.melee_models[0].action, SHOOT)
        self.assertIsNone(self.craft.volley_countdown)
        self.assertEqual(self.craft.fire_posts, 0)

    def test_the_scripted_volley_of_a_non_shooter_class_craft_launches_at_once(self):
        infantry = gyrocopter("I", 500, 500, cls="inf")
        infantry.unit_class = 1
        battle = Battle(3000, 3000, [infantry, self.enemy], seed=1)
        self.assertEqual(ranged.launch_shot(battle, infantry, (500, 524), (1000, 1300)), "special")
        self.assertEqual(len(steam_effects(battle)), 1)

    def test_the_shoot_animation_leaves_the_battle_rng_draw_order_alone(self):
        left = Battle(3000, 3000, [gyrocopter(), target("E", 1000, 1300)], seed=7)
        right = Battle(3000, 3000, [gyrocopter(), target("E", 1000, 1300)], seed=7)
        right.regiments["G"].script_action = SHOOT
        right.regiments["G"].script_action_key = right.regiments["G"].activity_key()
        for _ in range(10):
            left.tick()
            right.tick()
        self.assertEqual(left.rng.getstate(), right.rng.getstate())

    def test_the_bomb_still_drops_from_a_craft_playing_any_rotor_program(self):
        self.craft.bs = 3
        self.battle.tick()
        self.craft.flight_state().elevation = 32
        self.craft.melee_models[0].action = IDLE
        self.battle.rng = ScriptedRandom([4, 5, 0, 2, 1])  # the dice of the existing airborne bomb test
        self.assertIsNone(self.battle.drop_bomb("G"))
        self.assertEqual(len(self.battle.projectiles), 1)
        self.assertGreater(self.craft.reload_ticks, 0)


if __name__ == "__main__":
    unittest.main()
