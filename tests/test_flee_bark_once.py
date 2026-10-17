"""Flight from fear or a failed break test shouts once per handler pass: the unit is broken by the end of the tick in
which it handles its first 0x0D/0x0C (notes/terror_contact_charge.md section 8, issue #343)."""
import unittest

from whshr import behaviour
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side
from tests.script_helpers import FakeDll, word


def flee_arm(code, react):
    return [word('CaseEvent'), code, word('RoutAllowed'), word('If'), word('React'), react,
            word('SwitchScript'), 162, word('EndIf'), word('Break'), behaviour.BREAK_LABEL]


SCRIPTS = {
    100: [word('Wait'), behaviour.END],
    101: [word('PushPC'), word('GetEvent'), *flee_arm(12, 4), *flee_arm(13, 6),
          word('CaseEvent'), 10, word('SwitchScript'), 165, word('Break'), behaviour.BREAK_LABEL,
          word('CaseEvent'), 21, word('RoutAllowed'), word('Break'), behaviour.BREAK_LABEL, behaviour.LABEL,
          word('ConsumeEvent'), word('LoopIfTrue'), word('ReturnInterrupt'), behaviour.END],
    162: [word('FleeFromTarget'), word('Yield'), word('Wait'), behaviour.END],
    165: [word('PushPC'), word('Yield'), word('Loop'), behaviour.END],
}


class FleeShoutTests(unittest.TestCase):
    def setUp(self):
        self.unit = Regiment('cavalry', 'Cavalry', 300, 500, 0, Side.PLAYER, models=4)
        self.foe = Regiment('wyvern', 'Wyvern', 700, 500, 256, Side.ENEMY, models=1)
        self.battle = Battle(1000, 1000, [self.unit, self.foe], seed=1995, script_dll=FakeDll(SCRIPTS),
                             script_ids={'cavalry': 100, 'wyvern': 100})
        self.state = self.battle.event_bus.unit_states['cavalry']
        self.state.interrupt_script = 101
        self.state.current_target = ('wyvern', 0)

    def queue(self, *codes):
        for code in reversed(codes):  # listed head first, as in the report
            self.state.event_queue.append(Event(code=code, source='wyvern'))

    def run_unit(self, tick):
        self.battle.interpreter.run('cavalry', self.state, tick, self.battle.rng)

    def shouts(self):
        return [event.data['code'] for event in self.battle.events if event.kind == 'react']

    def test_given_flee_event_when_handled_then_one_shout_and_broken_in_the_same_run(self):
        self.queue(0x0D)
        self.run_unit(0)
        self.assertEqual(self.shouts(), [6])
        self.assertTrue(self.unit.routing)
        self.assertEqual(self.state.script_id, 162)

    def test_given_leftover_flee_event_on_the_next_tick_then_no_second_shout(self):
        self.queue(0x0D)
        self.run_unit(0)
        self.queue(0x0D)
        self.run_unit(1)
        self.assertEqual(self.shouts(), [6])
        self.assertTrue(self.unit.routing)

    def test_given_two_flee_events_in_one_pass_then_both_shout(self):
        self.queue(0x0D, 0x0D)
        self.run_unit(0)
        self.assertEqual(self.shouts(), [6, 6])
        self.assertTrue(self.unit.routing)

    def test_given_rout_then_flee_event_in_one_pass_then_retreat_and_flee_are_shouted(self):
        self.queue(0x0C, 0x0D)
        self.run_unit(0)
        self.assertEqual(self.shouts(), [4, 6])
        self.assertTrue(self.unit.routing)

    def test_given_broken_unit_when_rout_event_arrives_later_then_silent(self):
        self.queue(0x0C)
        self.run_unit(0)
        self.queue(0x0C)
        self.run_unit(1)
        self.assertEqual(self.shouts(), [4])

    def test_given_battle_tick_when_flee_handled_then_unit_routs_before_its_collision_pass(self):
        self.queue(0x0D)
        self.battle.tick()
        self.assertTrue(self.unit.routing)
        self.assertEqual(self.shouts(), [6])
        self.assertFalse([event for event in self.state.event_queue if event.code == 0x0D])


    def test_given_flight_then_engagement_in_one_pass_then_the_flight_stands(self):
        # The BF026 order of our phased tick (notes/tick_order_divergence.md 3): the flee event is handled before
        # the "engaged" event whose SwitchScript 165 would otherwise replace the switch to 162.
        self.queue(0x0D, 0x0A)
        self.run_unit(0)
        self.assertEqual(self.shouts(), [6])
        self.assertTrue(self.unit.routing)
        self.assertEqual(self.state.script_id, 162)

    def test_given_engagement_then_flight_in_one_pass_then_the_flight_replaces_the_melee_script(self):
        self.queue(0x0A, 0x0D)
        self.run_unit(0)
        self.assertTrue(self.unit.routing)
        self.assertEqual(self.state.script_id, 162)

    def test_given_no_flight_then_engagement_switches_to_melee(self):
        self.queue(0x0A)
        self.run_unit(0)
        self.assertFalse(self.unit.routing)
        self.assertEqual(self.state.script_id, 165)

    def test_given_cant_break_unit_then_engagement_is_not_blocked(self):
        self.unit.psychology = {'CantBreak'}
        self.queue(0x0D, 0x0A)
        self.run_unit(0)
        self.assertFalse(self.unit.routing)
        self.assertEqual(self.state.script_id, 165)

    def test_given_rout_check_without_a_switch_in_an_earlier_run_then_a_later_switch_is_ordinary(self):
        self.queue(0x15)
        self.run_unit(0)
        self.queue(0x0A)
        self.run_unit(1)
        self.assertEqual(self.state.script_id, 165)
        self.queue(0x0D)
        self.run_unit(2)
        self.assertEqual(self.state.script_id, 162)


if __name__ == '__main__':
    unittest.main()
