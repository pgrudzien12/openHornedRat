"""War machine and wagon rules: anchor flag (#65) and re-form crew placement (#70).

game_rules.md "Turning, wheeling and reversing" and "Formation changes"."""
import math
import unittest

from whshr import combat, formation, interpreter
from whshr.engine import Battle, Regiment, speed_per_tick
from whshr.rules import Side


def _gun(**kwargs):
    kwargs.setdefault("models", 6)
    kwargs.setdefault("ranks", 2)
    gun = Regiment("gun", "Gun", 100, 100, 0, Side.PLAYER, speed_per_tick=speed_per_tick(4, 3), **kwargs)
    gun.hud_class = "art"
    return gun


class SingleModelTurnRateTests(unittest.TestCase):
    def _turn_after_one_tick(self, frontage):
        unit = Regiment("m", "M", 100, 100, 0, Side.PLAYER, models=1, ranks=1,
                        speed_per_tick=speed_per_tick(4, 3))
        unit.frontage = frontage
        battle = Battle(1000, 1000, [unit])
        battle.order_move("m", 500, 100)
        battle.tick()
        return unit

    def test_given_a_big_single_model_footprint_then_its_turn_rate_follows_the_ordinary_formula(self):
        small, big = self._turn_after_one_tick(1), self._turn_after_one_tick(8)
        s_rlmv = big.speed_per_tick * 16 / 1.8
        self.assertAlmostEqual(big.direction, s_rlmv * (144 - 8.5 ** 2) / 256)
        self.assertLess(big.direction, small.direction)

    def test_given_a_big_single_model_when_turning_then_it_still_pays_no_speed_penalty(self):
        big = self._turn_after_one_tick(8)
        self.assertAlmostEqual(math.hypot(big.x - 100, big.y - 100), big.speed_per_tick)


class AnchorFlagTests(unittest.TestCase):
    def _battle(self, **kwargs):
        gun = _gun(**kwargs)
        foe = Regiment("foe", "Foe", 400, 100, 0, Side.ENEMY, models=8, ranks=2)
        battle = Battle(1000, 1000, [gun, foe], nodes={1: (300.0, 300.0)})
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        return battle, gun, foe, interp, battle.event_bus.unit_states["gun"]

    def test_given_an_anchored_gun_then_move_and_charge_orders_are_refused(self):
        battle, gun, *_ = self._battle()
        with self.assertRaises(ValueError):
            battle.order_move("gun", 200, 200)
        with self.assertRaises(ValueError):
            battle.order_attack("gun", "foe")

    def test_given_an_anchored_gun_then_scripted_moves_charges_and_pursuit_are_ignored(self):
        battle, gun, foe, interp, state = self._battle()
        state.current_target = ("foe", 0)
        interp.op_MoveToNode(state, 1, [], "gun", 0, None)
        interp.op_ScatterModelsToNode(state, 1, [], "gun", 0, None)
        interp.op_ChargeTarget(state, None, [], "gun", 0, None)
        interp.op_StartPursuit(state, None, [], "gun", 0, None)
        interp.op_AttackNearestEnemy(state, None, [], "gun", 0, None)
        self.assertIsNone(gun.target_x)
        self.assertIsNone(gun.attack_target)
        battle.tick()
        self.assertEqual((gun.x, gun.y), (100, 100))

    def test_given_an_anchored_gun_then_a_scripted_turn_and_placement_do_nothing(self):
        battle, gun, foe, interp, state = self._battle()
        interp.op_FaceNode(state, 1, [], "gun", 0, None)
        interp.op_PlaceAtNode(state, 1, [], "gun", 0, None)
        self.assertEqual((gun.direction, gun.x, gun.y), (0, 100, 100))

    def test_given_an_anchored_gun_then_a_victorious_fight_does_not_start_a_pursuit(self):
        battle, gun, foe, *_ = self._battle()
        foe.routing = True
        combat._react_to_rout(foe, [gun], 1, battle)
        self.assertIsNone(gun.attack_target)

    def test_given_an_anchored_gun_then_halting_and_rank_changes_are_still_allowed(self):
        battle, gun, *_ = self._battle()
        battle.order_halt("gun")
        battle.order_reform("gun", 3)
        self.assertEqual(gun.ranks, 3)
        self.assertTrue(gun.anchored)  # none of the above frees it

    def test_given_an_anchored_gun_then_it_can_still_flee(self):
        battle, gun, *_ = self._battle()
        gun.routing = True
        gun.flee_x, gun.flee_y = 100.0, 900.0
        battle.tick()
        self.assertGreater(gun.y, 100)

    def test_given_an_anchored_gun_then_being_charged_still_leaves_the_attacker_engaged(self):
        battle, gun, foe, *_ = self._battle()
        foe.x, foe.y = 100, 110
        foe.attack_target = "gun"
        for _ in range(3):
            battle.tick()
        self.assertEqual(foe.attack_target, "gun")

    def test_given_a_misfire_explosion_then_the_anchor_is_cleared_and_orders_work(self):
        battle, gun, *_ = self._battle()
        gun.clear_anchor()
        self.assertFalse(gun.anchored)
        battle.order_move("gun", 200, 200)

    def test_given_a_non_artillery_unit_then_it_is_not_anchored(self):
        unit = _gun()
        unit.hud_class = "inf"
        self.assertFalse(unit.anchored)


class WarMachineReformTests(unittest.TestCase):
    def _battle(self, hud="art", models=8, ranks=2, **kwargs):
        unit = Regiment("u", "U", 0, 0, 0, Side.PLAYER, models=models, ranks=ranks,
                        speed_per_tick=speed_per_tick(4, 3), **kwargs)
        unit.hud_class = hud
        return Battle(1000, 1000, [unit]), unit

    def test_given_a_war_machine_reform_then_the_flat_mover_is_not_used_and_no_time_is_added(self):
        battle, gun = self._battle()
        gun.model_positions()
        battle.order_reform("u", 4)
        self.assertFalse(gun.reforming)
        self.assertEqual(gun.ranks, 4)
        for _ in range(100):
            battle.tick()
        self.assertTrue(all(model.at_rest for model in gun.melee_models))

    def test_given_a_war_machine_reform_then_it_is_refused_while_fleeing_held_or_charging(self):
        battle, gun = self._battle()
        for attribute, value, reset in (("routing", True, False), ("held", True, False),
                                        ("attack_target", "x", None)):
            setattr(gun, attribute, value)
            with self.assertRaises(ValueError):
                battle.order_reform("u", 4)
            setattr(gun, attribute, reset)

    def test_given_a_war_machine_reform_then_models_walk_at_rank_dependent_speeds(self):
        battle, gun = self._battle()
        gun.model_positions()
        battle.order_reform("u", 4)
        gun.y += 100  # anchor ahead so every model catches up
        before = list(gun.positions)
        battle._advance_models(gun, 1)
        steps = {round(b[1] - a[1], 6) for a, b in zip(before, gun.positions)}
        self.assertGreater(len(steps), 1)

    def test_given_a_war_machine_reform_then_crew_slots_take_the_farthest_model_and_the_machine_the_nearest(self):
        positions = [(0.0, 10.0), (0.0, 100.0), (0.0, 200.0), (0.0, 400.0)]
        slots = formation.reform_assignment(0, 0, 0, 4, 2, positions, farthest=True)
        order = formation.reform_slot_order(4, 2)
        targets = formation.place(0, 0, 0, order)
        nearest = min(range(4), key=lambda i: math.hypot(positions[i][0] - targets[0][0],
                                                          positions[i][1] - targets[0][1]))
        self.assertEqual(slots[nearest], order[0])  # machine slot filled directly (fallback convention)
        remaining = [i for i in range(4) if i != nearest]
        for offset, target in zip(order[1:], targets[1:]):
            far = max(remaining, key=lambda i: formation._octagonal_distance(*positions[i], *target))
            self.assertEqual(slots[far], offset)
            remaining.remove(far)

    def test_given_an_ordinary_block_then_slots_still_take_the_nearest_model(self):
        positions = [(0.0, 10.0), (0.0, 100.0), (0.0, 200.0), (0.0, 400.0)]
        near = formation.reform_assignment(0, 0, 0, 4, 2, positions)
        far = formation.reform_assignment(0, 0, 0, 4, 2, positions, farthest=True)
        self.assertNotEqual(near, far)

    def test_given_a_war_machine_reform_ordered_then_the_engine_permutes_models_farthest_first(self):
        battle, gun = self._battle(models=4, ranks=2)
        gun.model_positions()
        gun.positions = [(0.0, 10.0), (0.0, 100.0), (0.0, 200.0), (0.0, 400.0)]
        before = list(gun.positions)
        battle.order_reform("u", 2)
        expected = formation.reform_assignment(0, 0, 0, 4, 2, before, farthest=True)
        raster = {o: i for i, o in enumerate(formation.block_slots(4, 2))}
        for index, offset in enumerate(expected):
            self.assertEqual(gun.positions[raster[offset]], before[index])

    def test_given_a_wagon_reform_then_it_keeps_the_catch_up_walk_and_a_block_uses_the_flat_mover(self):
        battle, wagon = self._battle(hud=None, models=2, ranks=1)
        wagon.unit_class = 7
        wagon.model_positions()
        battle.order_reform("u", 2)
        self.assertFalse(wagon.reforming)
        battle, block = self._battle(hud="inf")
        block.model_positions()
        battle.order_reform("u", 4)
        self.assertTrue(block.reforming)


if __name__ == "__main__":
    unittest.main()
