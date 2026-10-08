"""Contact wiring with scripts running: the collision pass raises 0x0B, and only the contact handler (Query 8)
starts a fight (notes/script_behaviours.md part 2). Vectors follow the report's section 2.9."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side

IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


def regiment(identifier, x, y, side, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=10, ranks=2, **extra)


class ContactTestCase(unittest.TestCase):
    def make(self, *units):
        self.battle = Battle(2000, 2000, list(units), seed=1995, script_dll=FakeDll(IDLE))
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)

    def contact(self, unit_id, other_id):
        state = self.bus.unit_states[unit_id]
        state.contact_record = other_id
        self.interp.op_Query(state, 8, [word("Query"), 8], unit_id, 0, self.battle.rng)
        return state

    def codes(self, unit_id):
        return [(e.code, e.source) for e in self.bus.unit_states[unit_id].event_queue]


class ContactHandlerTests(ContactTestCase):
    def setUp(self):
        self.a = regiment("A", 0, 0, Side.PLAYER)
        self.u = regiment("U", 0, 40, Side.ENEMY)
        self.make(self.a, self.u)

    def test_idle_unit_without_target_targets_the_contact_and_warns_it(self):
        state = self.contact("A", "U")
        self.assertEqual((state.current_target, state.contact_latch, bool(state.cond_flags)), (("U", 0), False, False))
        self.assertEqual(self.codes("U"), [(0x07, "A")])
        self.assertEqual(self.battle.engage_requests, [])

    def test_contact_with_the_current_target_engages_with_a_charge_counter(self):
        self.bus.unit_states["A"].current_target = ("U", 0)
        state = self.contact("A", "U")
        self.assertEqual(self.battle.engage_requests, [("A", "U", int(1.5 * self.a.frontage))])
        self.assertTrue(state.contact_latch)
        self.assertEqual((self.codes("A"), self.codes("U")), ([(0x0A, "U")], [(0x0A, "A")]))

    def test_charging_into_the_target_also_sends_0x08(self):
        self.a.attack_target = "U"
        self.bus.unit_states["A"].current_target = ("U", 0)
        self.contact("A", "U")
        self.assertEqual([code for code, _ in self.codes("U")], [0x08, 0x0A])

    def test_charging_into_another_unit_redirects(self):
        c = regiment("C", 500, 500, Side.ENEMY)
        self.make(self.a, self.u, c)
        self.a.attack_target = "C"
        self.bus.unit_states["A"].current_target = ("C", 0)
        state = self.contact("A", "U")
        self.assertEqual((state.current_target, self.a.attack_target), (("U", 0), "U"))
        self.assertEqual((self.codes("C"), self.codes("U")), ([(0x1A, "A")], [(0x07, "A")]))
        self.assertEqual(self.battle.engage_requests, [])

    def test_a_new_contact_with_a_different_target_engages_at_once(self):
        c = regiment("C", 500, 500, Side.ENEMY)
        self.make(self.a, self.u, c)
        self.bus.unit_states["A"].current_target = ("C", 0)
        state = self.contact("A", "U")
        # ENGAGE_NEW(A, U): U fights nobody yet, so U joins A
        self.assertEqual([(j, o) for j, o, _ in self.battle.engage_requests], [("U", "A")])
        self.assertEqual((state.current_target, state.contact_latch), (("U", 0), False))

    def test_a_joiner_already_fighting_is_not_engaged_twice(self):
        self.a.in_melee = True
        self.bus.unit_states["A"].current_target = ("U", 0)
        self.contact("A", "U")
        # ENGAGE_NEW(U, A): A fights, so U joins A
        self.assertEqual([(j, o) for j, o, _ in self.battle.engage_requests], [("U", "A")])
        self.battle.engage_requests.clear()
        self.u.in_melee = True
        self.contact("A", "U")
        self.assertEqual(self.battle.engage_requests, [])

    def test_a_broken_contact_is_refused_with_flight_event(self):
        self.bus.unit_states["A"].current_target = ("U", 0)
        self.u.routing = True
        self.contact("A", "U")  # a routing footprint: nothing at all
        self.assertEqual(self.battle.engage_requests, [])

    def test_friendly_non_target_contact_releases_the_latch(self):
        f = regiment("F", 0, 40, Side.PLAYER)
        self.make(self.a, f)
        state = self.contact("A", "F")
        self.assertEqual((state.contact_latch, state.current_target), (False, None))


class CollisionPassTests(ContactTestCase):
    def test_moving_unit_gets_0x0b_and_a_touched_regiment_the_reciprocal(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        a.collision_recheck = True
        self.interp.raise_contacts([(a, u)])
        self.assertEqual((self.codes("A"), self.codes("U")), ([(0x0B, None)], [(0x0B, None)]))
        self.assertEqual(self.bus.unit_states["A"].contact_record, "U")

    def test_the_pass_clears_the_re_check_state_and_the_touched_unit_gets_its_own_pass_in_the_same_update(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)  # A is earlier in unit order than U
        a.collision_recheck = True
        self.interp.raise_contacts([(a, u)])
        # A's pass switched U on, U's later pass in the same update recorded and cleared it; both got 0x0B once.
        self.assertEqual((a.collision_recheck, u.collision_recheck), (False, False))
        self.assertEqual((self.codes("A"), self.codes("U")), ([(0x0B, None)], [(0x0B, None)]))

    def test_a_touched_unit_earlier_in_unit_order_keeps_its_re_check_for_the_next_update(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        u.collision_recheck = True  # U is later in the order; A (earlier) is touched by it
        self.interp.raise_contacts([(a, u)])
        self.assertEqual(self.codes("A"), [(0x0B, None)])  # the reciprocal
        self.assertFalse(a.collision_recheck)

    def test_latched_pass_taker_gets_no_event_and_its_re_check_state_is_cleared(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        a.collision_recheck = True
        self.bus.unit_states["A"].contact_latch = True
        self.interp.raise_contacts([(a, u)])
        self.assertEqual(self.codes("A"), [])
        self.assertFalse(a.collision_recheck)

    def test_stationary_touching_units_raise_nothing(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        self.interp.raise_contacts([(a, u)])
        self.assertEqual((self.codes("A"), self.codes("U")), ([], []))

    def test_latched_units_get_no_contact_event_and_are_released_when_clear(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        a.collision_recheck = True
        self.bus.unit_states["A"].contact_latch = True
        self.interp.raise_contacts([(a, u)])
        self.assertEqual(self.codes("A"), [])
        self.interp.raise_contacts([])
        self.assertFalse(self.bus.unit_states["A"].contact_latch)

    def test_marked_units_are_not_touched(self):
        a, u = regiment("A", 0, 0, Side.ENEMY), regiment("P", 0, 30, Side.NEUTRAL)
        self.make(a, u)
        a.collision_recheck = True
        self.bus.unit_states["P"].unit_flags |= interpreter.LEAVING_BATTLE_FLAG
        self.interp.raise_contacts([(a, u)])
        self.assertEqual(self.codes("A"), [])

    def test_touching_footprints_alone_start_no_fight_with_scripts_running(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 20, Side.ENEMY)
        self.make(a, u)
        combat.resolve_contacts(self.battle)
        self.assertFalse(a.in_melee or u.in_melee)
        self.battle.engage_requests.append(("A", "U", 7))
        combat.resolve_contacts(self.battle)
        self.assertTrue(a.in_melee and u.in_melee)
        self.assertEqual((a.melee_group, a.charge_counter), (u.melee_group, 7))


class BuildingContactTests(ContactTestCase):
    """notes/script_behaviours.md 2.9: contact with a building, from a charging unit; building_units.md 4-5."""

    def setUp(self):
        self.a = regiment("A", 1000, 1000, Side.PLAYER)
        self.enemy = regiment("E", 1000, 1800, Side.ENEMY)
        self.battle = Battle(3000, 3000, [self.a, self.enemy], seed=1995, script_dll=FakeDll(IDLE),
                             scenery=[{"name": "WoodShack", "x": 1000, "y": 1030}, {"name": "Farm", "x": 2000, "y": 2000}])
        self.battle.phase = "battle"
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)
        self.state = self.bus.unit_states["A"]

    def charge(self, target_id):
        self.a.attack_target = self.a.charge_started_target = target_id
        self.state.current_target = (target_id, 0)

    def test_a_charge_touching_a_building_raises_the_contact_event_and_does_not_push(self):
        self.charge("building:0")
        self.a.collision_recheck = True
        before = (self.a.x, self.a.y)
        self.battle._correct_buildings(self.a)
        self.assertEqual((self.codes("A"), self.state.contact_record), ([(0x0B, None)], "building:0"))
        self.assertEqual((self.a.x, self.a.y), before)

    def test_without_the_re_check_state_the_pass_does_not_run(self):
        self.charge("building:0")
        self.a.collision_recheck = False
        self.battle._correct_buildings(self.a)
        self.assertEqual(self.codes("A"), [])

    def test_a_walking_unit_is_pushed_clear_and_gets_no_contact(self):
        self.a.collision_recheck = True
        self.battle._correct_buildings(self.a)
        self.assertEqual(self.codes("A"), [])
        self.assertIsNone(self.battle.buildings[0].penetration(*self.battle.formation_centre(self.a),
                                                               self.a.bounding_radius() - 1))

    def test_contact_with_the_target_building_starts_the_assault_without_a_charge_counter(self):
        self.charge("building:0")
        self.state.contact_record = "building:0"
        self.interp.op_Query(self.state, 8, [word("Query"), 8], "A", 0, self.battle.rng)
        self.assertEqual((self.a.assaulting_building, self.a.attack_target, self.state.contact_latch),
                         ("building:0", None, True))
        self.assertEqual(self.codes("A"), [(0x0A, "building:0")])
        self.assertEqual(self.battle.engage_requests, [])

    def test_contact_with_another_building_ends_the_charge_and_keeps_the_latch(self):
        self.charge("E")
        self.state.contact_record = "building:0"
        self.interp.op_Query(self.state, 8, [word("Query"), 8], "A", 0, self.battle.rng)
        self.assertIsNone(self.a.attack_target)
        self.assertIsNone(self.a.assaulting_building)
        self.assertTrue(self.state.contact_latch)
        self.assertIn((0x09, "A"), self.codes("E"))

    def test_a_free_charge_touching_a_building_raises_contact_and_the_handler_halts_it(self):
        self.a.free_charging = True
        self.a.target_x, self.a.target_y = 1000.0, 1500.0
        self.a.collision_recheck = True
        self.battle._correct_buildings(self.a)
        self.assertEqual(self.codes("A"), [(0x0B, None)])
        self.interp.op_Query(self.state, 8, [word("Query"), 8], "A", 0, self.battle.rng)
        self.assertEqual((self.a.free_charging, self.a.target_x, self.state.contact_latch), (False, None, True))

    def test_a_unit_in_melee_touching_a_building_gets_the_contact_and_is_not_pushed(self):
        self.a.in_melee = True
        self.a.collision_recheck = True
        before = (self.a.x, self.a.y)
        self.battle._correct_buildings(self.a)
        self.assertEqual((self.codes("A"), (self.a.x, self.a.y)), ([(0x0B, None)], before))

    def test_a_scripted_walking_unit_is_pushed_only_while_its_re_check_state_is_on(self):
        before = (self.a.x, self.a.y)
        self.a.collision_recheck = False
        self.battle._correct_buildings(self.a)
        self.assertEqual((self.a.x, self.a.y), before)
        self.a.collision_recheck = True
        self.battle._correct_buildings(self.a)
        self.assertNotEqual((self.a.x, self.a.y), before)
        self.assertTrue(self.a.collision_recheck)  # a push switches the state back on

    def test_the_pass_is_consumed_once_for_every_building_overlap(self):
        self.battle.buildings = self.battle.buildings[:1] + self.battle.buildings[:1]
        self.charge("building:0")
        self.a.collision_recheck = True
        self.battle._correct_buildings(self.a)
        self.assertEqual(self.codes("A"), [(0x0B, None), (0x0B, None)])
        self.assertFalse(self.a.collision_recheck)

    def test_a_walking_unit_in_the_deployment_phase_is_still_pushed_clear(self):
        self.battle.phase = "deployment"
        self.a.collision_recheck = False
        self.battle._correct_buildings(self.a)
        self.assertFalse(self.battle.overlaps_building(self.a))

    def test_the_latch_set_on_ending_a_charge_lasts_while_the_building_still_overlaps(self):
        self.state.contact_latch = True
        self.interp.raise_contacts([])
        self.assertTrue(self.state.contact_latch)
        self.a.y = 1500  # clear of the shack
        self.interp.raise_contacts([])
        self.assertFalse(self.state.contact_latch)

    def test_a_latched_unit_stepping_into_a_building_is_rolled_back(self):
        self.state.contact_latch = True
        self.a.y = 1000
        snapshot = self.battle._latch_snapshot(self.a, self.state)
        self.a.y = 1010  # the step overlaps the shack
        self.assertTrue(self.battle._overlaps_anything(self.a))
        self.assertFalse(self.battle._resolve_latched_step(self.a, self.state, snapshot))
        self.assertEqual(self.a.y, 1000)


class WorkedExampleTests(ContactTestCase):
    """notes/script_behaviours.md 2.8: two hostile regiments marching into each other, tick by tick. Events are
    handled last in, first out; the standard handlers are reduced to what the example names (0x0B runs the contact
    handler, 0x07 and 0x0A change nothing here)."""

    def setUp(self):
        self.a = regiment("A", 0, 0, Side.PLAYER)
        self.b = regiment("B", 0, 30, Side.ENEMY)  # footprints overlap
        self.make(self.a, self.b)

    def handle_all(self, unit_id):
        """Dispatch the unit's queue as the handler would, newest event first; returns the codes handled."""
        state = self.bus.unit_states[unit_id]
        handled = []
        while state.event_queue:
            event = state.event_queue.pop()
            handled.append(event.code)
            if event.code == 0x0B:
                self.interp.op_Query(state, 8, [word("Query"), 8], unit_id, 0, self.battle.rng)
        return handled

    def test_tick_t_a_steps_first_and_both_units_get_the_contact_event(self):
        self.a.collision_recheck = True
        self.interp.raise_contacts([(self.a, self.b)])
        self.assertEqual((self.codes("A"), self.codes("B")), ([(0x0B, None)], [(0x0B, None)]))
        self.assertFalse(self.b.collision_recheck)

    def test_tick_t_b_takes_a_as_target_warns_it_and_raises_the_next_contacts(self):
        self.a.collision_recheck = True
        self.interp.raise_contacts([(self.a, self.b)])
        state_b = self.bus.unit_states["B"]
        self.handle_all("B")
        self.assertEqual((state_b.current_target, state_b.contact_latch, self.b.collision_recheck),
                         (("A", 0), False, True))
        self.interp.raise_contacts([(self.a, self.b)])  # B's own move and pass
        self.assertEqual(self.codes("A"), [(0x0B, None), (0x07, "B"), (0x0B, None)])
        self.assertEqual(self.codes("B"), [(0x0B, None)])

    def test_tick_t_plus_1_a_becomes_the_joiner_with_the_charge_counter_and_b_the_owner(self):
        self.a.collision_recheck = True
        self.interp.raise_contacts([(self.a, self.b)])
        self.handle_all("B")
        self.interp.raise_contacts([(self.a, self.b)])
        state_a = self.bus.unit_states["A"]
        self.handle_all("A")
        self.assertEqual(state_a.current_target, ("B", 0))
        self.assertTrue(state_a.contact_latch)
        self.assertEqual(self.battle.engage_requests, [("A", "B", int(1.5 * self.a.frontage))])
        self.assertEqual(self.codes("B"), [(0x0B, None), (0x07, "A"), (0x0A, "A")])
        self.interp.raise_contacts([(self.a, self.b)])  # A latched: no event for A; reciprocal 0x0B to B
        self.assertEqual(self.codes("B")[-1], (0x0B, None))
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.a.in_melee and self.b.in_melee)
        self.assertEqual((self.a.melee_group, self.a.charge_counter), (self.b.melee_group, int(1.5 * self.a.frontage)))

    def test_tick_t_plus_1_b_handles_the_engagement_again_without_changing_anything(self):
        self.a.collision_recheck = True
        self.interp.raise_contacts([(self.a, self.b)])
        self.handle_all("B")
        self.interp.raise_contacts([(self.a, self.b)])
        self.handle_all("A")
        self.interp.raise_contacts([(self.a, self.b)])
        combat.resolve_contacts(self.battle)
        counter = self.a.charge_counter
        self.handle_all("B")
        combat.resolve_contacts(self.battle)
        self.assertEqual((self.a.charge_counter, self.b.charge_counter, self.b.in_melee), (counter, 0, True))
        self.assertEqual(self.battle.engage_requests, [])


if __name__ == "__main__":
    unittest.main()
