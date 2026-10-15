"""War-machine figure animation (notes/machine_figure_animation.md): the machine figure uses its own sprite set's
table, holds one frame on actions 1-5, plays its family's locked shot, and leaves a wreck that keeps its facing.
Frames are first-frame group + phase x 8 + direction."""

import random
import unittest

from whshr import animation
from whshr.animation import DEAD, FIGHT, IDLE, SHOOT, STAND, WALK, WEAPON_READY
from whshr.engine import ModelState, Regiment
from whshr.rules import Side


class FixedEntry(random.Random):
    """Draws `entry` for every random entry."""

    def __init__(self, entry):
        super().__init__(0)
        self.entry = entry

    def randrange(self, *args, **kwargs):
        return self.entry


def frames(family, requests, entry=0, direction=0):
    """The frame shown on each tick for a list of per-tick requests."""
    model = ModelState(uid=0)
    shown, fires = [], []
    rng = FixedEntry(entry)
    for request in requests:
        group, phase = animation.step(model, request, rng, family)
        shown.append(group + phase * 8 + direction)
        fires.append(model.fire_event)
    return shown, fires


class MachineFamilyTests(unittest.TestCase):
    def test_the_machine_sets_select_the_machine_tables(self):
        for sprite, family in (("RockLobber", "thrower"), ("DoomDvrCatapult", "thrower"), ("Cannon", "gun"),
                               ("GrtCannon", "gun"), ("VolleyGun", "volley"), ("Mortar", "mortar")):
            with self.subTest(sprite=sprite):
                self.assertEqual(animation.family_for(sprite, 4), family)
        self.assertEqual(animation.family_for("OrcBoyz", 4), "standard_infantry")  # the crew

    def test_a_rock_lobber_in_melee_never_moves_its_arm(self):  # vectors 1, 2
        self.assertEqual(frames("thrower", [STAND, FIGHT, FIGHT, WEAPON_READY, STAND, FIGHT], direction=2)[0],
                         [2] * 6)

    def test_the_rock_lobber_shot(self):  # vectors 3, 4
        shown, fires = frames("thrower", [SHOOT] * 11)
        self.assertEqual(shown, [0, 0, 0, 0, 0, 8, 8, 16, 24, 0, 0])
        self.assertEqual(fires.index(True), 4)
        shown, fires = frames("thrower", [SHOOT] * 8, entry=3)
        self.assertEqual(shown, [0, 0, 8, 8, 16, 24, 0, 0])
        self.assertEqual(fires.index(True), 1)

    def test_a_request_during_the_shot_is_dropped_not_queued(self):  # vector 5
        shown, _ = frames("thrower", [SHOOT] * 6 + [FIGHT] * 4)
        self.assertEqual(shown[5:10], [8, 8, 16, 24, 0])
        model = ModelState(uid=0)
        rng = FixedEntry(0)
        for request in [SHOOT] * 6 + [FIGHT] * 4:
            animation.step(model, request, rng, "thrower")
            self.assertIsNone(model.pending_action)
        animation.step(model, SHOOT, rng, "thrower")
        self.assertEqual(model.action, STAND)  # the shot ends in stand, not in the dropped request

    def test_the_cannon_shot_keeps_its_frame(self):  # vector 6
        shown, fires = frames("gun", [SHOOT] * 11, entry=1, direction=4)
        self.assertEqual(shown, [12] * 11)
        self.assertEqual(fires.index(True), 5)

    def test_the_mortar_shot(self):  # vector 7
        shown, fires = frames("mortar", [SHOOT] * 12, direction=1)
        self.assertEqual(shown, [41, 41, 41, 41, 9, 17, 17, 25, 33, 33, 41, 41])
        self.assertEqual(fires.index(True), 6)
        self.assertEqual(frames("mortar", [STAND, FIGHT])[0], [40, 40])

    def test_machine_figures_face_the_unit_even_when_fighting(self):
        self.assertTrue(animation.family_table("thrower")[FIGHT].faces_unit)
        self.assertFalse(animation.family_table("standard_infantry")[FIGHT].faces_unit)


class DoomwheelTests(unittest.TestCase):
    """notes/machine_figure_animation.md 2.5 and vectors 11-13."""

    def test_the_wheel_sets_select_the_doomwheel_table(self):
        for sprite in ("DoomWheel", "DWHEEL"):
            self.assertEqual(animation.family_for(sprite, 4), "doomwheel")

    def test_stand_and_weapon_ready_hold_the_first_rolling_frame(self):
        self.assertEqual(frames("doomwheel", [STAND, WEAPON_READY, STAND], direction=3)[0], [11, 11, 11])

    def test_walking_rolls_a_flat_loop_with_no_random_entry(self):  # vector 11
        self.assertEqual(frames("doomwheel", [STAND] + [WALK] * 5, entry=3, direction=3)[0],
                         [11, 11, 19, 27, 35, 11])

    def test_changing_between_rolling_actions_restarts_the_loop(self):  # vector 12
        shown, fires = frames("doomwheel", [WALK, WALK, WALK, FIGHT, FIGHT, FIGHT, FIGHT, SHOOT, IDLE], direction=1)
        self.assertEqual(shown, [9, 17, 25, 9, 17, 25, 33, 9, 9])
        self.assertFalse(any(fires))  # no fire step

    def test_the_wheel_wreck_is_held_and_never_burns(self):  # vector 13
        self.assertEqual(frames("doomwheel", [WALK, WALK, DEAD, DEAD], direction=5)[0], [5 + 8, 5 + 16, 5, 5])
        self.assertFalse(animation.burns_on_death(animation.DEATH_FIRE, 4, "DoomWheel"))

    def test_rolling_faces_the_heading_but_standing_faces_the_unit(self):
        table = animation.family_table("doomwheel")
        self.assertEqual([table[action].faces_unit for action in (STAND, WEAPON_READY)], [True, True])
        for action in (IDLE, WALK, FIGHT, SHOOT):
            self.assertTrue(table[action].faces_heading)
            self.assertFalse(table[action].faces_unit)

    def test_the_drawn_facing_target_follows_the_heading_while_idle(self):
        from whshr.engine import Battle
        wheel = Regiment("w", "W", 0, 0, 96, Side.ENEMY, models=1, ranks=1, sprite="DoomWheel", has_leader=True)
        battle = Battle(5000, 5000, [wheel], seed=1995)
        wheel.model_positions()
        model = wheel.melee_models[0]
        model.action, model.heading_x, model.heading_y = IDLE, 1.0, 0.0
        self.assertEqual(battle._drawn_facing_target(wheel, model), 128)
        model.action = STAND
        self.assertEqual(battle._drawn_facing_target(wheel, model), wheel.direction)


class WreckTests(unittest.TestCase):
    def test_a_machine_wreck_keeps_its_facing_and_shows_the_wreck_group(self):
        lobber = Regiment("l", "L", 0, 0, 96, Side.ENEMY, models=3, ranks=1, sprite="OrcBoyz",
                          leader_sprite="RockLobber", hud_class="art", has_leader=True)
        lobber.model_positions()
        machine = next(model for model in lobber.melee_models if lobber.leader_model(model))
        machine.drawn_facing = 100
        corpse = animation.corpse_of(lobber, machine, 0, 0, random.Random(1))
        self.assertEqual((corpse.group, corpse.direction, corpse.sprite), (32, 100, "RockLobber"))

    def test_an_ordinary_corpse_still_falls_with_a_random_facing(self):
        boyz = Regiment("b", "B", 0, 0, 96, Side.ENEMY, models=3, ranks=1, sprite="OrcBoyz")
        boyz.model_positions()
        corpse = animation.corpse_of(boyz, boyz.melee_models[0], 0, 0, FixedEntry(77))
        self.assertEqual((corpse.group, corpse.direction), ("dead", 77))


class WarpfireThrowerTests(unittest.TestCase):
    """notes/machine_figure_animation.md 2.7 and vectors 14, 15."""

    def test_both_sprite_names_select_the_warpfire_table(self):
        for sprite in ("WARPFIRE", "WarpFireThrower"):
            self.assertEqual(animation.family_for(sprite, 1), "warpfire")

    def test_actions_1_4_5_hold_the_stand_frame_facing_the_unit(self):  # vector 14
        self.assertEqual(frames("warpfire", [STAND, FIGHT, WEAPON_READY, FIGHT], direction=6)[0], [62] * 4)
        for action in (STAND, FIGHT, WEAPON_READY):
            self.assertTrue(animation.family_table("warpfire")[action].faces_unit)

    def test_idle_loops_the_stand_group_without_random_entry(self):
        shown, _ = frames("warpfire", [animation.IDLE] * 11, entry=5)
        self.assertEqual(shown, [48, 48, 48, 56, 56, 64, 64, 64, 72, 72, 48])

    def test_walk_loops_group_0_with_a_random_entry_of_0_to_7(self):
        shown, _ = frames("warpfire", [animation.WALK] * 9)
        self.assertEqual(shown, [0, 0, 8, 8, 16, 16, 24, 24, 0])
        self.assertEqual(animation.family_table("warpfire")[animation.WALK].random_entry, 8)
        self.assertEqual(frames("warpfire", [animation.WALK] * 2, entry=2)[0], [8, 8])

    def test_the_shot_shows_group_40_for_ten_minus_r_ticks_then_stand(self):  # vector 15
        shown, fires = frames("warpfire", [SHOOT] * 8 + [STAND] * 2, entry=2, direction=3)
        self.assertEqual(shown, [43] * 8 + [59, 59])
        self.assertFalse(any(fires))  # no fire step
        shown, _ = frames("warpfire", [SHOOT] * 11, entry=0)
        self.assertEqual(shown, [40] * 10 + [56])

    def test_a_request_during_the_shot_is_dropped(self):
        shown, _ = frames("warpfire", [SHOOT, FIGHT, FIGHT, SHOOT, SHOOT], entry=2)
        self.assertEqual(shown, [40] * 5)

    def test_dead_is_the_corpse_group_with_a_random_facing(self):
        unit = Regiment("w", "W", 0, 0, 96, Side.ENEMY, models=1, ranks=1, sprite="WARPFIRE",
                        leader_sprite="WARPFIRE", unit_class=1)
        unit.model_positions()
        corpse = animation.corpse_of(unit, unit.melee_models[0], 0, 0, FixedEntry(5))
        self.assertEqual((corpse.group, corpse.direction), (32, 5))
        self.assertEqual(frames("warpfire", [DEAD] * 2, direction=0)[0], [32, 32])

    def test_a_fire_or_warpfire_kill_burns(self):
        for kind in (animation.DEATH_FIRE, animation.DEATH_WARPFIRE):
            self.assertTrue(animation.burns_on_death(kind, 1, "WARPFIRE"))


if __name__ == "__main__":
    unittest.main()
