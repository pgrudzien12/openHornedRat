"""BDD scenarios for the per-model figure animation stepper (whshr.animation), per docs/testing.md."""

import random
import unittest

from whshr import animation, battlefield
from whshr.engine import Battle, ModelState, Regiment
from whshr.rules import Side


class SevenActionStepperTests(unittest.TestCase):
    """notes/game_rules.md "Figure animation": standard infantry's seven action scripts."""

    def test_given_stand_action_when_stepped_then_it_holds_a_single_phase_forever(self):
        model, rng = ModelState(), random.Random(0)

        results = [animation.step(model, animation.STAND, rng) for _ in range(5)]

        self.assertEqual(results, [("stand", 1)] * 5)

    def test_given_idle_action_when_stepped_then_it_plays_the_ten_tick_hold_pattern_without_randomising(self):
        model, rng = ModelState(), random.Random(0)

        phases = [animation.step(model, animation.IDLE, rng)[1] for _ in range(10)]

        self.assertEqual(phases, [0, 0, 0, 1, 1, 2, 2, 2, 3, 3])
        # The loop is not randomised: it always restarts at phase 0.
        self.assertEqual(animation.step(model, animation.IDLE, rng)[1], 0)

    def test_given_walk_action_when_it_first_changes_then_a_random_entry_point_is_drawn(self):
        model, rng = ModelState(), random.Random(1)
        expected_entry = random.Random(1).randrange(8)
        sequence = [0, 0, 1, 1, 2, 2, 3, 3]

        group, phase = animation.step(model, animation.WALK, rng)

        self.assertEqual(group, "move")
        self.assertEqual(phase, sequence[expected_entry])

    def test_given_a_model_walking_when_the_same_action_is_reissued_then_it_is_a_no_op(self):
        model, rng = ModelState(), random.Random(2)
        sequence = [0, 0, 1, 1, 2, 2, 3, 3]
        animation.step(model, animation.WALK, rng)  # first tick: draws the random entry point
        entry = model.action_entry

        # Reissuing the identical action many times must not redraw the entry point: the phases
        # keep advancing through the loop from where the first tick left off, forever.
        phases = [animation.step(model, animation.WALK, rng)[1] for _ in range(16)]

        expected = [sequence[(entry + tick) % 8] for tick in range(1, 17)]
        self.assertEqual(phases, expected)
        self.assertEqual(model.action_entry, entry)  # never redrawn

    def test_given_fight_action_when_it_changes_then_the_random_entry_is_drawn_from_a_narrower_range(self):
        model, rng = ModelState(), random.Random(3)

        animation.step(model, animation.FIGHT, rng)

        self.assertLess(model.action_entry, 10)  # random entry point 0..9, not the full 0..11 loop

    def test_given_weapon_ready_action_when_it_changes_then_one_of_two_phases_is_chosen_and_held(self):
        model, rng = ModelState(), random.Random(4)

        group, phase = animation.step(model, animation.WEAPON_READY, rng)

        self.assertEqual(group, "attack")
        self.assertIn(phase, (0, 2))
        held = [animation.step(model, animation.WEAPON_READY, rng)[1] for _ in range(5)]
        self.assertEqual(held, [phase] * 5)

    def test_given_dead_action_when_stepped_then_it_holds_the_single_corpse_frame(self):
        model, rng = ModelState(), random.Random(5)

        results = [animation.step(model, animation.DEAD, rng) for _ in range(4)]

        self.assertEqual(results, [("dead", 0)] * 4)

    def test_given_shoot_action_when_its_run_and_hold_finish_then_it_auto_switches_back_to_stand(self):
        model, rng = ModelState(), random.Random(6)

        groups = [animation.step(model, animation.SHOOT, rng)[0] for _ in range(6)]
        self.assertEqual(groups, ["shoot"] * 6)  # 4 running ticks + 2 held ticks

        group, phase = animation.step(model, animation.SHOOT, rng)

        self.assertEqual((group, phase), ("stand", 1))
        self.assertEqual(model.action, animation.STAND)

    def test_given_shoot_action_when_it_changes_then_all_four_phases_are_shown_regardless_of_entry(self):
        model, rng = ModelState(), random.Random(7)

        phases = [animation.step(model, animation.SHOOT, rng)[1] for _ in range(4)]

        self.assertEqual(sorted(phases), [0, 1, 2, 3])

    def test_given_an_undecoded_family_when_looked_up_then_it_falls_back_to_standard_infantry(self):
        self.assertIs(animation.family_table("some_future_family"), animation.STANDARD_INFANTRY)
        self.assertIs(animation.family_table(animation.DEFAULT_FAMILY), animation.STANDARD_INFANTRY)


class FrameSelectionWiringTests(unittest.TestCase):
    """notes/animations.md: frame = group_base + phase * 8 + direction, reused via
    whshr.battlefield.SpriteSheet.frame_index -- the animation stepper only supplies (group, phase)."""

    def _sheet(self):
        # move(4 phases)=frames 0-31, dead=32, attack(4 phases)=40-71, stand(4 phases)=72-103, shoot=104-111.
        groups = [(0, 32), (32, 8), (40, 32), (72, 32), (104, 8)]
        return battlefield.SpriteSheet("Test", frames=[None] * 112, groups=groups)

    def test_given_a_models_stepped_action_when_selecting_a_frame_then_it_uses_the_documented_formula(self):
        sheet = self._sheet()
        model, rng = ModelState(), random.Random(8)
        animation.step(model, animation.WALK, rng)
        group, phase = animation.current(model)

        index = sheet.frame_index(group, phase, direction=3)

        self.assertEqual(group, "move")
        self.assertEqual(index, 0 + phase * 8 + 3)  # move's group base is frame 0

    def test_given_a_model_fighting_when_selecting_a_frame_then_it_uses_the_attack_group_base(self):
        sheet = self._sheet()
        model, rng = ModelState(), random.Random(9)
        animation.step(model, animation.FIGHT, rng)
        group, phase = animation.current(model)

        self.assertEqual(group, "attack")
        self.assertEqual(sheet.frame_index(group, phase, direction=5), 40 + phase * 8 + 5)


class BattleAnimationWiringTests(unittest.TestCase):
    """whshr.engine.Battle steps each model's own action/program counter every tick, instead of one
    shared value per regiment (notes/engine_gaps/figure_animation.md)."""

    def test_given_a_regiment_ordered_to_move_when_ticked_then_its_models_desynchronise_across_the_walk_loop(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.PLAYER, models=8, ranks=2)
        battle = Battle(2000, 2000, [regiment], seed=42)
        battle.order_move("r", 0, 500)

        for _ in range(5):
            battle.tick()

        actions = {model.action for model in regiment.melee_models}
        self.assertEqual(actions, {animation.WALK})
        # Random entry per model (mechanism 1) means they are not all on the same phase.
        entries = {model.action_entry for model in regiment.melee_models}
        self.assertGreater(len(entries), 1)

    def test_given_a_regiment_not_moving_when_ticked_then_its_models_play_the_idle_action(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.PLAYER, models=4, ranks=1)
        battle = Battle(2000, 2000, [regiment], seed=1)

        battle.tick()

        self.assertTrue(all(model.action == animation.IDLE for model in regiment.melee_models))

    def test_given_an_inactive_regiment_when_ticked_then_its_models_are_not_stepped(self):
        regiment = Regiment("r", "R", 0, 0, 0, Side.PLAYER, models=0, ranks=1)  # destroyed -> inactive
        battle = Battle(2000, 2000, [regiment], seed=1)

        battle.tick()

        self.assertEqual(regiment.melee_models, [])
