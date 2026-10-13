"""Charging a terror or fear causer (notes/terror_contact_charge.md): a targeted charge (ChargeTarget) at a terror
causer is refused at its start; a charger that flees on contact leaves the causer alone on the new grid, which the
causer leaves on "alone" (0x30) from the next segment, or pursues the charger when it was the causer's target."""

import unittest
from unittest import mock

from whshr import behaviour, combat
from whshr.combat import ALONE_ON_GRID_EVENT, SEGMENT_TICKS
from whshr.engine import Battle, Regiment
from whshr.interpreter import FEAR_THE_BEAST_REACTION
from whshr.rules import Side
from tests.script_helpers import FakeDll, word
from tests.test_enemy_routed import SCRIPTS as ROUT_SCRIPTS

MAIN = 100
SCRIPTS = {**ROUT_SCRIPTS, MAIN: [word("Wait"), behaviour.END]}


def unit(identifier, x, y, side, direction=128, **kwargs):
    return Regiment(identifier, identifier, x, y, direction, side, models=kwargs.pop("models", 8),
                    ranks=kwargs.pop("ranks", 2), **kwargs)


class Case(unittest.TestCase):
    def setUp(self):
        self.charger = unit("cavalry", 100, 500, Side.PLAYER)
        self.causer = unit("wyvern", 400, 500, Side.ENEMY, direction=384, models=1, ranks=1,
                           psychology=frozenset({"CauseTerror"}))
        self.battle = Battle(1000, 1000, [self.charger, self.causer], seed=1995, script_dll=FakeDll(SCRIPTS),
                             script_ids={"cavalry": MAIN, "wyvern": MAIN})
        self.interp = self.battle.interpreter
        self.charger_state = self.battle.event_bus.unit_states["cavalry"]
        self.causer_state = self.battle.event_bus.unit_states["wyvern"]
        self.causer_state.interrupt_script = 151

    def charge_target(self):
        self.charger_state.current_target = ("wyvern", 0)
        reacts = []
        with mock.patch.object(self.interp, "react", lambda identifier, code: reacts.append((identifier, code))):
            self.interp.op_ChargeTarget(self.charger_state, None, [], "cavalry", 0, self.battle.rng)
        return reacts

    def queued(self, state):
        return [event.code for event in state.event_queue]


class ChargeTargetFearTests(Case):
    def test_a_targeted_charge_at_a_terror_causer_is_refused_at_its_start(self):
        reacts = self.charge_target()

        self.assertEqual(reacts, [("cavalry", FEAR_THE_BEAST_REACTION)])
        self.assertFalse(self.charger_state.cond_flags)
        self.assertIsNone(self.charger.attack_target)
        self.assertNotIn(0x07, self.queued(self.causer_state))

    def test_frenzy_or_psychology_immune_units_charge_a_terror_causer(self):
        for immunity in ("Frenzy", "PsyImmune"):
            with self.subTest(immunity=immunity):
                self.setUp()
                self.charger.psychology = frozenset({immunity})
                self.assertEqual(self.charge_target(), [])
                self.assertTrue(self.charger_state.cond_flags)
                self.assertEqual(self.charger.attack_target, "wyvern")

    def test_a_fear_causer_is_charged_on_a_passed_test_which_spares_the_contact_test(self):
        self.causer.psychology = frozenset({"CauseFear"})
        with mock.patch.object(combat, "leadership_test", return_value=True):
            self.assertEqual(self.charge_target(), [])
        self.assertTrue(self.charger_state.cond_flags)
        self.assertTrue(self.charger_state.fear_passed)
        self.assertEqual(self.charger.attack_target, "wyvern")

    def test_a_failed_fear_test_refuses_the_charge(self):
        self.causer.psychology = frozenset({"CauseFear"})
        with mock.patch.object(combat, "leadership_test", return_value=False):
            self.assertEqual(self.charge_target(), [("cavalry", FEAR_THE_BEAST_REACTION)])
        self.assertFalse(self.charger_state.cond_flags)
        self.assertIsNone(self.charger.attack_target)

    def test_an_ordinary_enemy_is_charged(self):
        self.causer.psychology = frozenset()
        self.assertEqual(self.charge_target(), [])
        self.assertTrue(self.charger_state.cond_flags)
        self.assertEqual(self.charger.attack_target, "wyvern")


class FleeingChargerTests(Case):
    """The charger engages the causer, then routs in the same handler pass (report section 5)."""

    def engage_then_rout(self):
        self.charger.attack_target = "wyvern"
        self.assertTrue(self.interp._engage(self.charger, self.causer))
        self.causer_state.event_queue.clear()
        combat.start_rout(self.charger, self.battle)
        combat.resolve_contacts(self.battle)

    def test_the_causer_is_left_alone_in_melee_and_hears_nothing_in_the_creation_segment(self):
        self.engage_then_rout()

        self.assertTrue(self.causer.in_melee)
        self.assertTrue(self.battle.fights[self.causer.melee_group]["alone"])
        self.assertNotIn(ALONE_ON_GRID_EVENT, self.queued(self.causer_state))

    def test_from_the_next_segment_the_causer_hears_alone_every_tick_until_it_leaves(self):
        self.engage_then_rout()
        self.battle.tick_count += SEGMENT_TICKS
        for _ in range(2):
            combat.resolve_contacts(self.battle)
        self.assertEqual(self.queued(self.causer_state).count(ALONE_ON_GRID_EVENT), 2)

        self.interp.op_LeaveSharedGrid(self.causer_state, None, [], "wyvern", 0, self.battle.rng)
        self.causer_state.event_queue.clear()
        combat.resolve_contacts(self.battle)

        self.assertTrue(self.causer_state.cond_flags)
        self.assertFalse(self.causer.in_melee)
        self.assertEqual(self.battle.fights, {})
        self.assertEqual(self.queued(self.causer_state), [])

    def test_a_causer_targeting_the_charger_pursues_it_instead(self):
        self.causer_state.current_target = ("cavalry", 0)
        self.engage_then_rout()

        self.interp.run("wyvern", self.causer_state, 1, self.battle.rng)
        combat.resolve_contacts(self.battle)
        self.assertTrue(self.causer.pursuing)
        self.assertEqual(self.causer.attack_target, "cavalry")
        self.assertFalse(self.causer.in_melee)
        self.assertEqual(self.battle.fights, {})

    def test_a_causer_busy_casting_stays_alone_instead_of_pursuing(self):
        self.causer_state.current_target = ("cavalry", 0)
        self.causer.unit_class = 5
        self.causer_state.channelling = True
        self.engage_then_rout()
        self.interp.run("wyvern", self.causer_state, 1, self.battle.rng)

        self.assertFalse(self.causer.pursuing)
        self.assertTrue(self.causer.in_melee)


if __name__ == "__main__":
    unittest.main()
