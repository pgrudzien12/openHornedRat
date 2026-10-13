"""War-machine figure animation (notes/machine_figure_animation.md): the machine figure uses its own sprite set's
table, holds one frame on actions 1-5, plays its family's locked shot, and leaves a wreck that keeps its facing.
Frames are first-frame group + phase x 8 + direction."""

import random
import unittest

from whshr import animation
from whshr.animation import DEAD, FIGHT, SHOOT, STAND, WEAPON_READY
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
                               ("GrtCannon", "gun"), ("VolleyGun", "gun"), ("Mortar", "mortar")):
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


if __name__ == "__main__":
    unittest.main()
