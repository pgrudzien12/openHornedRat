"""Airborne units: the flying state, take-off and landing (notes/airborne_units.md Part A, GitHub #388)."""

import unittest

from whshr import flight, ranged
from whshr.animation import FIGHT, IDLE, SHOOT, STAND, WALK, WEAPON_READY
from whshr.engine import Battle, Regiment
from whshr.flight import GYROCOPTER, WYVERN, FlightState
from whshr.rules import Side


def run(state: FlightState, action: int, ticks: int) -> list[int]:
    """Request `action` every tick (as the engine does) for `ticks` ticks; the elevation after each."""
    elevations = []
    for _ in range(ticks):
        state.take_request(action)
        state.step()
        elevations.append(state.elevation)
    return elevations


def flying(profile=WYVERN, elevation=32, after: int = IDLE) -> FlightState:
    state = FlightState(profile)
    run(state, after, profile.program_ticks)
    state.elevation = elevation
    return state


class WhoFliesTests(unittest.TestCase):
    """A1: the figure's sprite set decides; every flier starts grounded."""

    def test_the_wyvern_and_both_gyrocopter_variants_fly(self):
        for sprite in ("Wyvern", "Gyrocopter", "GYROCOPT"):
            with self.subTest(sprite):
                self.assertIsNotNone(flight.profile_for(sprite))

    def test_the_dragon_doom_diver_and_giant_never_fly(self):
        for sprite in ("Dragon", "MeshDragon", "DoomDiver", "Giant", None):
            with self.subTest(sprite):
                self.assertIsNone(flight.profile_for(sprite))

    def test_a_flier_starts_on_the_ground(self):
        wyvern = Regiment("W", "Wyvern", 500, 500, 0, Side.ENEMY, models=1, ranks=1, sprite="Wyvern",
                          leader_sprite="Wyvern")
        self.assertEqual((wyvern.elevation, wyvern.airborne), (0, False))
        self.assertIsNotNone(wyvern.flight_state())

    def test_an_infantry_class_gyrocopter_flies_too(self):
        craft = Regiment("G", "Gyro", 500, 500, 0, Side.PLAYER, models=1, ranks=1, sprite="Gyrocopter",
                         hud_class="inf")
        self.assertIs(craft.flight_state().profile, GYROCOPTER)


class WyvernTests(unittest.TestCase):
    """A3.1 and vectors A1-A5."""

    def test_a_move_takes_off_in_40_ticks(self):
        elevations = run(FlightState(WYVERN), IDLE, 41)
        self.assertEqual(elevations[:4], [0, 0, 0, 0])
        self.assertEqual([elevations[t - 1] for t in (5, 10, 15, 20, 25, 30, 35, 40, 41)],
                         [4, 8, 12, 16, 20, 24, 28, 32, 32])
        self.assertEqual(elevations, [min(32, 4 * (t // 5)) for t in range(1, 42)])

    def test_the_flying_state_starts_with_the_first_climb_step(self):
        state = FlightState(WYVERN)
        run(state, IDLE, 4)
        self.assertFalse(state.airborne)
        run(state, IDLE, 1)
        self.assertTrue(state.airborne)

    def test_a_halt_lands_in_40_ticks(self):
        state = flying()
        elevations = run(state, STAND, 40)
        self.assertEqual([elevations[t - 1] for t in (5, 35, 40)], [28, 4, 0])
        self.assertFalse(state.airborne)

    def test_a_charge_or_a_target_lands_it(self):
        for action in (WALK, WEAPON_READY):
            with self.subTest(action):
                state = flying()
                self.assertEqual(run(state, action, 40)[-1], 0)

    def test_a_new_move_during_a_landing_does_not_climb_back(self):
        state = flying()
        run(state, STAND, 20)
        self.assertEqual(state.elevation, 16)
        self.assertEqual(run(state, IDLE, 60)[-1], 16)

    def test_fighting_and_casting_keep_the_height(self):
        for action in (FIGHT, SHOOT):
            with self.subTest(action):
                self.assertEqual(run(flying(), action, 50)[-1], 32)

    def test_after_a_cast_in_the_air_it_keeps_flying(self):
        state = flying()
        run(state, SHOOT, 9)
        self.assertEqual(run(state, STAND, 50)[-1], 32)
        self.assertEqual(state.action, IDLE)
        self.assertEqual(run(state, WALK, 40)[-1], 0)  # a later different request lands it

    def test_after_a_cast_on_the_ground_it_stands(self):
        state = FlightState(WYVERN)
        run(state, SHOOT, 9)
        run(state, STAND, 10)
        self.assertEqual((state.action, state.elevation), (STAND, 0))


class GyrocopterTests(unittest.TestCase):
    """A3.2 and vectors A6-A9."""

    def test_a_move_takes_off_in_32_ticks(self):
        elevations = run(FlightState(GYROCOPTER), IDLE, 33)
        self.assertEqual(elevations, [min(32, 4 * (t // 4)) for t in range(1, 34)])

    def test_charging_routing_and_shooting_take_off_too(self):
        for action in (WALK, SHOOT):
            with self.subTest(action):
                self.assertEqual(run(FlightState(GYROCOPTER), action, 32)[-1], 32)

    def test_the_first_rest_after_flying_hovers(self):
        state = flying(GYROCOPTER)
        self.assertEqual(run(state, STAND, 60)[-1], 32)
        self.assertTrue(state.hovering)

    def test_a_repeated_rest_request_lands_a_hovering_craft(self):
        state = flying(GYROCOPTER)
        run(state, STAND, 5)
        state.repeat = True
        elevations = run(state, STAND, 32)
        self.assertEqual((elevations[3], elevations[-1]), (28, 0))
        self.assertFalse(state.hovering)

    def test_a_changed_rest_action_lands_it(self):
        state = flying(GYROCOPTER)
        run(state, STAND, 5)
        self.assertEqual(run(state, WEAPON_READY, 32)[-1], 0)

    def test_fighting_straight_out_of_a_charge_hovers(self):
        state = flying(GYROCOPTER, after=WALK)
        self.assertEqual(run(state, FIGHT, 40)[-1], 32)


class FrameTests(unittest.TestCase):
    """A3.1 and A3.2: the program laps, then the flying or rest loop."""

    def test_the_wyvern_take_off_lap_repeats_a_frame_on_each_step_tick(self):
        state = FlightState(WYVERN)
        frames = []
        for _ in range(10):
            state.take_request(IDLE)
            state.step()
            frames.append(state.frame())
        self.assertEqual(frames, [("stand", phase) for phase in (0, 0, 1, 1, 1, 2, 2, 3, 3, 3)])

    def test_the_wyvern_flaps_fast_in_the_air_and_walks_on_its_own_frames(self):
        state = flying()
        state.take_request(IDLE)
        self.assertEqual(state.frame()[0], "stand")
        landed = FlightState(WYVERN)
        landed.take_request(WALK)
        self.assertIsNone(landed.frame())

    def test_the_gyrocopter_always_shows_its_rotor_group(self):
        state = FlightState(GYROCOPTER)
        for action in (STAND, IDLE, FIGHT, WEAPON_READY):
            with self.subTest(action):
                state.take_request(action)
                state.step()
                self.assertEqual(state.frame()[0], "move")


class BattleTests(unittest.TestCase):
    """The engine drives the program from the figure's action (A3)."""

    def test_a_moving_wyvern_takes_off_and_lands_when_it_halts(self):
        wyvern = Regiment("W", "Wyvern", 500, 500, 0, Side.PLAYER, models=1, ranks=1, sprite="Wyvern",
                          leader_sprite="Wyvern", speed_per_tick=1.0)
        battle = Battle(3000, 3000, [wyvern], seed=1995)
        battle.phase = "battle"
        battle.order_move("W", 500, 1500)
        for _ in range(45):
            battle.tick()
        self.assertEqual(wyvern.elevation, 32)
        battle.order_halt("W")
        for _ in range(60):  # the figure first walks to its slot, then lands over 40 ticks
            battle.tick()
        self.assertEqual(wyvern.elevation, 0)


class HeightTests(unittest.TestCase):
    """A2, vector A18: the missile hit band of a flier at E is E..E+16."""

    def test_the_band(self):
        craft = Regiment("G", "Gyro", 500, 500, 0, Side.PLAYER, models=1, ranks=1, sprite="Gyrocopter")
        craft.flight_state().elevation = 32
        self.assertEqual((craft.elevation, ranged.hit_band(craft)), (32, 16))


if __name__ == "__main__":
    unittest.main()
