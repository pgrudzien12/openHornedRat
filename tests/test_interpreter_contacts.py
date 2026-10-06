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
        a.target_x, a.target_y = 0.0, 100.0
        self.interp.raise_contacts([(a, u)])
        self.assertEqual((self.codes("A"), self.codes("U")), ([(0x0B, None)], [(0x0B, None)]))
        self.assertEqual(self.bus.unit_states["A"].contact_record, "U")

    def test_stationary_touching_units_raise_nothing(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        self.interp.raise_contacts([(a, u)])
        self.assertEqual((self.codes("A"), self.codes("U")), ([], []))

    def test_latched_units_get_no_contact_event_and_are_released_when_clear(self):
        a, u = regiment("A", 0, 0, Side.PLAYER), regiment("U", 0, 30, Side.ENEMY)
        self.make(a, u)
        a.target_x, a.target_y = 0.0, 100.0
        self.bus.unit_states["A"].contact_latch = True
        self.interp.raise_contacts([(a, u)])
        self.assertEqual(self.codes("A"), [])
        self.interp.raise_contacts([])
        self.assertFalse(self.bus.unit_states["A"].contact_latch)

    def test_marked_units_are_not_touched(self):
        a, u = regiment("A", 0, 0, Side.ENEMY), regiment("P", 0, 30, Side.NEUTRAL)
        self.make(a, u)
        a.target_x, a.target_y = 0.0, 100.0
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


if __name__ == "__main__":
    unittest.main()
