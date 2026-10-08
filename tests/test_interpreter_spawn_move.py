"""SpawnUnit, FollowParent, the squig hop, ReformBlock and the scatter formula (notes/script_spawn_move.md)."""

import random
import unittest
from unittest import mock

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter, nodes
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.nodes import ScriptNode
from whshr.rules import Side


class Draws(random.Random):
    """A random source that returns scripted `randrange` values in order."""

    def __init__(self, *values):
        super().__init__(0)
        self.values = list(values)

    def randrange(self, *args, **kwargs):
        return self.values.pop(0)


class MoveTestCase(unittest.TestCase):
    def make(self, *units):
        self.battle = Battle(5000, 5000, list(units), seed=1995)
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)

    def call(self, unit_id, name, *operands, rng=None):
        state = self.bus.unit_states[unit_id]
        state.pc = 0
        words = [word(name), *operands]
        return getattr(self.interp, "op_" + name)(state, operands[0] if operands else None, words, unit_id, 0,
                                                  rng or self.battle.rng)


class ReformBlockTests(MoveTestCase):
    def test_rank_table(self):
        for models, ranks in ((1, 1), (5, 1), (8, 2), (11, 2), (12, 3), (16, 3), (20, 3), (22, 4), (32, 4)):
            with self.subTest(models=models):
                unit = Regiment("u", "U", 500, 500, 0, Side.ENEMY, models=models, ranks=1)
                self.make(unit)
                self.call("u", "ReformBlock")
                state = self.bus.unit_states["u"]
                self.assertEqual(unit.ranks, 1)  # queued until the script update ends
                self.assertEqual(state.pending_reform_ranks, ranks)
                state.script_dll = FakeDll([behaviour.END])
                self.interp.run("u", state, 1, self.battle.rng)
                self.assertEqual(unit.ranks, ranks)

    def test_refused_while_charging_and_condition_kept(self):
        unit = Regiment("u", "U", 500, 500, 0, Side.ENEMY, models=12, ranks=1, attack_target="x")
        self.make(unit)
        self.bus.unit_states["u"].cond_flags = 1
        self.call("u", "ReformBlock")
        self.assertEqual((unit.ranks, bool(self.bus.unit_states["u"].cond_flags)), (1, True))


class FollowParentTests(MoveTestCase):
    def test_vectors(self):
        rows = [((500, 1000), 128, 72, (572, 1000)), ((500, 1000), 0, 72, (500, 1072)), ((0, 0), 64, 36, (25, 25))]
        for at, facing, distance, expected in rows:
            with self.subTest(facing=facing):
                parent = Regiment("p", "P", *at, facing, Side.ENEMY, models=5, ranks=1)
                child = Regiment("c", "C", 900, 900, 0, Side.NEUTRAL, models=5, ranks=1)
                self.make(parent, child)
                self.bus.unit_states["c"].parent_id = "p"
                self.call("c", "FollowParent", distance)
                self.assertEqual(((child.x, child.y), child.direction, child.script_action), (expected, facing, 2))

    def test_no_parent_does_nothing(self):
        child = Regiment("c", "C", 900, 900, 0, Side.NEUTRAL, models=5, ranks=1)
        self.make(child)
        self.bus.unit_states["c"].cond_flags = 1
        self.call("c", "FollowParent", 72)
        self.assertEqual(((child.x, child.y), bool(self.bus.unit_states["c"].cond_flags)), ((900, 900), True))


class SpawnUnitTests(MoveTestCase):
    def setUp(self):
        self.template = Regiment("fan", "Fanatic", 50, 50, 0, Side.ENEMY, models=1, ranks=1, hidden=True,
                                 psychology=frozenset({"CantMelee"}))
        self.parent = Regiment("p", "P", 500, 1000, 128, Side.ENEMY, models=10, ranks=2)
        self.threat = Regiment("t", "T", 800, 1000, 0, Side.PLAYER, models=10, ranks=2)
        self.make(self.template, self.parent, self.threat)
        self.bus.unit_states["fan"].tag = 0xABC0
        self.bus.unit_states["p"].current_event = Event(code=0x33, source="t")

    def spawn(self, offset, draw):
        self.call("p", "SpawnUnit", 0xABC0, 28, 1, offset & 0xFFFF, rng=Draws(draw))
        return self.battle.regiments[list(self.battle.regiments)[-1]]

    def test_vectors(self):
        for offset, draw, position, facing in ((0, 0, (548, 1000), 128), (-20, 0, (546, 1021), 108),
                                               (20, 3, (581, 969), 148)):
            with self.subTest(offset=offset):
                copy = self.spawn(offset, draw)
                self.assertEqual(((copy.x, copy.y), copy.direction), (position, facing))
        state = self.bus.unit_states[copy.identifier]
        self.assertEqual((state.script_id, state.parent_id, state.tag, copy.hidden), (28, "p", 0, False))
        self.assertTrue(copy.reforming)
        self.assertTrue(self.bus.unit_states["p"].cond_flags)

    def test_without_a_template_nothing_happens(self):
        self.bus.unit_states["fan"].tag = 0
        before = len(self.battle.regiments)
        self.call("p", "SpawnUnit", 0xABC0, 28, 1, 0)
        self.assertEqual((len(self.battle.regiments), bool(self.bus.unit_states["p"].cond_flags)), (before, False))

    def test_the_copy_takes_the_next_slot_as_its_collision_throttle_phase(self):
        self.template.update_counter = 99
        slot = len(self.battle.regiments)
        copy = self.spawn(0, 0)
        self.assertEqual(copy.update_counter, slot)

    def test_the_copy_runs_from_the_next_tick(self):
        self.spawn(0, 0)
        self.battle.tick()  # iterating the script states must survive a unit added mid-tick


class SquigHopTests(MoveTestCase):
    def setUp(self):
        self.squig = Regiment("s", "S", 500, 1000, 0, Side.ENEMY, models=5, ranks=1)
        self.target = Regiment("t", "T", 500, 1300, 0, Side.PLAYER, models=5, ranks=1)
        self.make(self.squig, self.target)
        self.state = self.bus.unit_states["s"]
        self.state.current_target = ("t", 0)

    def hop(self, operand, *draws):
        self.call("s", "FanaticJump", operand, rng=Draws(*draws))
        return (self.squig.x, self.squig.y), self.squig.direction

    def test_vectors(self):
        self.assertEqual(self.hop(4, 2, 3, 32), ((500, 1056), 0))
        self.assertEqual(self.state.hop_counter, 4)
        self.setUp()
        self.assertEqual(self.hop(0, 2, 3, 0), ((460, 1039), 448))
        self.setUp()
        self.assertEqual(self.hop(0, 2, 3, 63), ((538, 1040), 62))

    def test_double_or_no_target_hops_randomly(self):
        self.assertEqual(self.hop(0, 5, 5, 300)[1], 300)
        self.setUp()
        self.state.current_target = None
        self.assertEqual(self.hop(0, 1, 4, 0)[1], 0)

    def test_release_counts_misses_down_and_calls_with_no_target(self):
        self.state.hop_counter = 2
        self.state.current_target = None
        self.call("s", "FanaticRelease")
        self.assertEqual((self.state.hop_counter, bool(self.state.cond_flags)), (1, True))
        self.call("s", "FanaticRelease")
        self.assertEqual((self.state.hop_counter, bool(self.state.cond_flags)), (0, False))
        self.assertEqual([event.code for event in self.state.event_queue], [1, 1])


class SquigLandingTests(MoveTestCase):
    """notes/script_spawn_move.md 5: the landing collision, with the report's five rows."""

    def setUp(self):
        self.hopper = Regiment("s", "S", 500, 1000, 0, Side.ENEMY, models=5, ranks=1, strength=4)
        self.victim = Regiment("v", "V", 502, 1000, 0, Side.PLAYER, models=2, ranks=1, toughness=3, armour=0)
        self.make(self.hopper, self.victim)
        self.state = self.bus.unit_states["s"]
        self.state.current_target = ("v", 0)

    def release(self, counter, *dice):
        self.state.hop_counter = counter
        with mock.patch.object(self.battle.rng, "randint", side_effect=list(dice)):
            self.call("s", "FanaticRelease")
        return self.state.hop_counter, bool(self.state.cond_flags)

    def test_a_landing_that_wounds_keeps_the_counter_and_is_true(self):
        self.assertEqual(self.release(4, 6, 1, 6, 1), (4, True))  # two models: wound 6, save 1 (no armour)
        self.assertEqual(self.victim.models, 0)
        self.assertEqual(self.hopper.models, 5)  # the hopper never dies

    def test_nothing_within_reach_counts_a_miss(self):
        self.victim.x = 900
        self.assertEqual(self.release(4), (3, True))
        self.assertEqual(self.release(1), (0, False))

    def test_a_failed_wound_roll_or_a_save_is_a_miss(self):
        self.assertEqual(self.release(1, 1, 1), (0, False))  # wound rolls 1 and 1: need 3
        self.victim.armour = 4  # save 3 + (4 - 3) = 4
        self.assertEqual(self.release(1, 6, 6, 6, 6), (0, False))  # wounds 6, saves 6 >= 4: saved
        self.assertEqual(self.victim.models, 2)

    def test_a_miss_with_no_target_calls_the_unit_to_itself(self):
        self.victim.x = 900
        self.state.current_target = None
        self.assertEqual(self.release(2), (1, True))
        self.assertEqual([event.code for event in self.state.event_queue], [1])

    def test_touching_rolling_stock_or_scenery_counts_without_damage(self):
        wagon = Regiment("w", "W", 505, 1000, 0, Side.PLAYER, models=2, ranks=1, unit_class=7)
        self.make(self.hopper, wagon)
        self.state = self.bus.unit_states["s"]
        self.assertEqual(self.release(4), (4, True))
        self.assertEqual(wagon.models, 2)
        self.make(self.hopper)
        self.state = self.bus.unit_states["s"]
        self.battle.objects.append({"x": 505, "y": 1000, "radius": 30, "status": ["os_active"]})
        self.assertEqual(self.release(4), (4, True))

    def test_artillery_is_touched_even_when_the_crew_rolls_fail_and_its_machine_is_not_rolled_for(self):
        gun = Regiment("g", "G", 505, 1000, 0, Side.PLAYER, models=3, ranks=1, unit_class=4, hud_class="art",
                       toughness=3, has_leader=True)
        self.make(self.hopper, gun)
        self.state = self.bus.unit_states["s"]
        gun.model_positions()
        machine = gun.leader_model_index
        assert machine is not None
        self.assertEqual(self.release(4, 1, 1), (4, True))  # the crew models in reach roll 1: no wound, still a touch
        self.assertEqual((gun.models, gun.melee_models[machine].wounds_taken), (3, 0))

    def test_a_special_unit_is_touched_not_wounded(self):
        special = Regiment("x", "X", 505, 1000, 0, Side.PLAYER, models=3, ranks=1, unit_class=8, toughness=3)
        self.make(self.hopper, special)
        self.state = self.bus.unit_states["s"]
        self.assertEqual(self.release(4), (4, True))
        self.assertEqual(special.models, 3)

    def test_the_reach_follows_the_target_class(self):
        for unit_class, wounded in ((1, False), (2, True), (6, True)):
            with self.subTest(unit_class=unit_class):
                far = Regiment("f", "F", 500, 1012, 0, Side.PLAYER, models=2, ranks=1, unit_class=unit_class,
                               toughness=3)
                self.make(self.hopper, far)
                self.state = self.bus.unit_states["s"]
                # its two models stand 13.4 from the hopper: outside 12, inside 18 and 24
                self.release(4, *((6, 1, 6, 1) if wounded else ()))
                self.assertEqual(far.models, 0 if wounded else 2)

    def test_a_multi_wound_model_survives_a_single_wound(self):
        self.victim.wounds = 2
        self.assertEqual(self.release(4, 6, 1, 6, 1), (4, True))
        self.assertEqual(self.victim.models, 2)  # wounded, not dead


class ScatterFormulaTests(unittest.TestCase):
    def test_destination_uses_cos_for_x_and_negated_sin_for_y(self):
        node = ScriptNode(100.0, 100.0, 7, 40)
        (_index, point), = nodes.scatter_destinations([node], 7, 1, Draws(20, 128))
        self.assertEqual(point, (100.0, 80.0))  # a = 128: COS 0, SIN 256 -> (0, -20)


if __name__ == "__main__":
    unittest.main()
