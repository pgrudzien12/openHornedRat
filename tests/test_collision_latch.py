"""Re-form completion event 0x34 and the contact latch's movement rule (notes/movement_formation.md 1.2, 9;
notes/script_behaviours.md 2.5)."""

import unittest

from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def unit(identifier, x, y, facing=0, side=Side.PLAYER):
    return Regiment(identifier, identifier, x, y, facing, side, models=16, ranks=4, points=10)


def codes(battle, identifier):
    return [event.code for event in battle.event_bus.unit_states[identifier].event_queue]


class ReformCompletionTests(unittest.TestCase):
    def test_settled_reform_sends_event_0x34_to_the_unit(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        battle.reform_to_ranks(regiment, 2)
        self.assertTrue(regiment.reforming)
        for _ in range(400):
            battle.tick()
            if not regiment.reforming:
                break
        self.assertFalse(regiment.reforming)
        self.assertIn(0x34, codes(battle, "A"))

    def test_no_event_while_the_reform_is_still_running(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        battle.reform_to_ranks(regiment, 2)
        battle.tick()
        self.assertTrue(regiment.reforming)
        self.assertNotIn(0x34, codes(battle, "A"))

    def test_engagement_ending_a_reform_does_not_send_it(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        battle.reform_to_ranks(regiment, 2)
        battle.end_reform_for_engagement(regiment)
        self.assertNotIn(0x34, codes(battle, "A"))


class LatchMovementTests(unittest.TestCase):
    def make(self):
        # Two facing hostile blocks whose footprints overlap; A holds the latch.
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 500, 506, facing=256, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.event_bus.unit_states["A"].contact_latch = True
        return battle, a, b

    def test_latched_ordinary_move_that_still_overlaps_is_undone_and_halts(self):
        battle, a, b = self.make()
        before = (a.x, a.y)
        a.target_x, a.target_y = 500, 540  # further into B
        battle.tick()
        self.assertEqual((a.x, a.y), before)
        self.assertIsNone(a.target_x)
        self.assertTrue(a.reforming or not a.waypoints)
        self.assertTrue(battle.event_bus.unit_states["A"].contact_latch)

    def test_latched_charger_does_not_advance(self):
        battle, a, b = self.make()
        before = (a.x, a.y)
        a.attack_target = "B"
        for _ in range(3):
            battle.tick()
        self.assertEqual((a.x, a.y), before)
        self.assertEqual(a.attack_target, "B")

    def test_latched_move_that_steps_clear_stands_and_releases_the_latch(self):
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 500, 510, facing=256, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.event_bus.unit_states["A"].contact_latch = True
        # B is far enough away after one step only if the step is large; move A away and move B away too
        b.x, b.y = 500, 700
        a.target_x, a.target_y = 500, 300
        battle.tick()
        self.assertFalse(battle.event_bus.unit_states["A"].contact_latch)
        self.assertNotEqual((a.x, a.y), (500, 500))

    def test_unlatched_move_is_not_rolled_back(self):
        battle, a, b = self.make()
        battle.event_bus.unit_states["A"].contact_latch = False
        a.target_x, a.target_y = 500, 540
        battle.tick()
        self.assertNotEqual((a.x, a.y), (500, 500))


class WagonCollisionEventTests(unittest.TestCase):
    """Event 0x27: a wagon overlapping any footprint within +-45 degrees of its facing (script_behaviours.md 2.2)."""

    def make(self, other_y, other_side=Side.PLAYER, wagon_moving=True):
        wagon = Regiment("W", "W", 500, 500, 0, Side.PLAYER, models=2, ranks=1, points=10, unit_class=7)
        other = unit("O", 500, other_y, facing=256, side=other_side)
        battle = Battle(2000, 2000, [wagon, other], seed=1995)
        battle.interpreter = battle.interpreter or interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        wagon.collision_recheck = wagon_moving
        return battle, wagon

    def raise_once(self, battle):
        battle.interpreter.raise_wagon_collisions([r for r in battle.regiments.values() if r.active])

    def test_wagon_touching_a_friendly_unit_ahead_gets_0x27(self):
        battle, wagon = self.make(506)
        self.assertTrue(wagon.is_wagon)
        self.raise_once(battle)
        self.assertEqual(codes(battle, "W"), [0x27])

    def test_enemy_ahead_counts_too_and_the_event_has_no_source(self):
        battle, wagon = self.make(506, Side.ENEMY)
        self.raise_once(battle)
        event = battle.event_bus.unit_states["W"].event_queue[0]
        self.assertEqual((event.code, event.source), (0x27, None))

    def test_unit_behind_the_wagon_does_not_raise_it(self):
        battle, wagon = self.make(494)
        self.raise_once(battle)
        self.assertEqual(codes(battle, "W"), [])

    def test_no_overlap_no_event(self):
        battle, wagon = self.make(700)
        self.raise_once(battle)
        self.assertEqual(codes(battle, "W"), [])

    def test_stationary_wagon_runs_no_pass(self):
        battle, wagon = self.make(506, wagon_moving=False)
        self.raise_once(battle)
        self.assertEqual(codes(battle, "W"), [])

    def test_non_wagon_never_gets_it(self):
        battle, wagon = self.make(506)
        wagon.unit_class = None
        self.raise_once(battle)
        self.assertEqual(codes(battle, "W"), [])

    def test_event_is_refused_during_deployment(self):
        battle, wagon = self.make(506)
        battle.phase = "deployment"
        self.raise_once(battle)
        self.assertEqual(codes(battle, "W"), [])


class CollisionRecheckStateTests(unittest.TestCase):
    """The collision pass runs only for units whose re-check state is on (notes/script_behaviours.md 2.1, 2.6)."""

    def make(self):
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 1200, 1200, facing=0, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.interpreter = battle.interpreter or interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        return battle, a, b

    def test_two_enemies_that_overlap_but_never_move_do_not_engage_or_get_events(self):
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 500, 506, facing=256, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.interpreter = battle.interpreter or interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        for _ in range(3):
            battle.tick()
        self.assertEqual((codes(battle, "A"), codes(battle, "B")), ([], []))

    def test_a_mover_touching_a_stationary_enemy_raises_both_contacts(self):
        a = unit("A", 500, 500, facing=0)
        b = unit("B", 500, 506, facing=256, side=Side.ENEMY)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        battle.interpreter = battle.interpreter or interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        a.target_x, a.target_y = 500, 900
        for _ in range(60):
            battle.tick()
            if codes(battle, "A"):
                break
        self.assertIn(0x0B, codes(battle, "A"))
        self.assertIn(0x0B, codes(battle, "B"))

    def test_rally_switches_it_on(self):
        battle, a, b = self.make()
        battle.interpreter.op_Rally(battle.event_bus.unit_states["A"], None, [], "A", 0, None)
        self.assertTrue(a.collision_recheck)


class RecheckThrottleTests(unittest.TestCase):
    """notes/fanatic_collisions.md 5: a position step switches the re-check state on every 4th update of the unit."""

    def test_a_moving_unit_gets_its_pass_on_every_fourth_update_only(self):
        mover = unit("A", 100, 100)  # slot 0: counter 0, so its updates count 1, 2, 3, 4, ...
        other = unit("B", 1500, 1500, side=Side.ENEMY)
        battle = Battle(2000, 2000, [mover, other], seed=1995)
        battle.interpreter = battle.interpreter or interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        mover.target_x, mover.target_y = 600, 100
        raised = []
        for _ in range(8):
            mover.collision_recheck = False
            battle._advance_regiments(1.0, 0.1)
            raised.append(mover.collision_recheck)
        self.assertEqual(raised, [False, False, False, True, False, False, False, True])

    def test_slot_staggers_the_phase(self):
        a, b = unit("A", 100, 100), unit("B", 300, 100)
        battle = Battle(2000, 2000, [a, b], seed=1995)
        self.assertEqual((a.update_counter, b.update_counter), (0, 1))

    def test_a_re_form_switches_it_on_every_time(self):
        regiment = unit("A", 500, 500)
        battle = Battle(2000, 2000, [regiment], seed=1995)
        regiment.collision_recheck = False
        battle.reform_to_ranks(regiment, 2)
        self.assertTrue(regiment.collision_recheck)


class WagonEventScopeTests(unittest.TestCase):
    """notes/fanatic_collisions.md 4: the wagon's own pass, circle test only, once per footprint."""

    def make(self, *others):
        wagon = Regiment("W", "W", 500, 500, 0, Side.PLAYER, models=2, ranks=1, points=10, unit_class=7)
        battle = Battle(2000, 2000, [wagon, *others], seed=1995)
        battle.interpreter = battle.interpreter or interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        wagon.collision_recheck = True
        return battle, wagon

    def test_one_event_per_overlapping_footprint_ahead(self):
        battle, wagon = self.make(unit("X", 500, 506), unit("Y", 505, 506))
        battle.interpreter.raise_wagon_collisions(list(battle.regiments.values()))
        self.assertEqual(codes(battle, "W"), [0x27, 0x27])

    def test_another_units_pass_touching_the_wagon_is_not_enough(self):
        battle, wagon = self.make(unit("X", 500, 506))
        wagon.collision_recheck = False
        battle.interpreter.raise_wagon_collisions(list(battle.regiments.values()))
        self.assertEqual(codes(battle, "W"), [])


if __name__ == "__main__":
    unittest.main()
