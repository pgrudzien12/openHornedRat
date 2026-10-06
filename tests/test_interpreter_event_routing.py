"""Tags, parents, targeted event sends and SetSide (notes/threat_events_nodes.md, part B).

Vectors are the report's before/instruction/after tables.
"""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side

END = behaviour.END


class RoutingTestCase(unittest.TestCase):
    def setUp(self):
        self.a = Regiment("a", "A", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
        self.b = Regiment("b", "B", 100, 0, 0, Side.ENEMY, models=5, ranks=1)
        self.p = Regiment("p", "P", 0, 300, 0, Side.PLAYER, models=5, ranks=1)
        self.n = Regiment("n", "N", 300, 300, 0, Side.NEUTRAL, models=5, ranks=1)
        self.battle = Battle(1000, 1000, [self.a, self.b, self.p, self.n], seed=1995)
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)

    def state(self, unit):
        return self.bus.unit_states[unit]

    def call(self, unit, name, operand=None, words=()):
        state = self.state(unit)
        return getattr(self.interp, "op_" + name)(state, operand, list(words), unit, 0, None)

    def queue(self, unit):
        return [(event.code, event.source) for event in self.state(unit).event_queue]

    def remove(self, regiment):
        regiment.fled = True


class TagTests(RoutingTestCase):
    def test_set_tag_is_refused_while_a_live_unit_carries_it(self):
        self.call("a", "SetTag", 0xABC0)
        self.call("b", "SetTag", 0xABC0)
        self.assertEqual((self.state("a").tag, self.state("b").tag), (0xABC0, 0))

    def test_set_tag_replaces_the_units_older_tag(self):
        self.call("a", "SetTag", 0xABC0)
        self.call("a", "SetTag", 0xABC1)
        self.assertIsNone(self.bus.find_by_tag(0xABC0))
        self.assertEqual(self.bus.find_by_tag(0xABC1), "a")

    def test_removed_units_tag_is_free_again(self):
        self.call("a", "SetTag", 0xABC0)
        self.remove(self.a)
        self.assertIsNone(self.bus.find_by_tag(0xABC0))
        self.call("b", "SetTag", 0xABC0)
        self.assertEqual(self.bus.find_by_tag(0xABC0), "b")

    def test_tag_zero_never_matches(self):
        self.call("a", "IfTagExists", 0)
        self.assertFalse(self.state("a").cond_flags)

    def test_if_tag_and_if_tag_exists(self):
        self.call("a", "SetTag", 0xABC0)
        self.call("a", "IfTag", 0xABC0)
        self.assertTrue(self.state("a").cond_flags)
        self.call("b", "IfTag", 0xABC0)
        self.assertFalse(self.state("b").cond_flags)
        self.call("b", "IfTagExists", 0xABC0)
        self.assertTrue(self.state("b").cond_flags)

    def test_parent_is_a_stored_link_overwritten_with_none_on_a_failed_lookup(self):
        self.call("a", "SetTag", 0xABC0)
        self.call("b", "SetParentByTag", 0xABC0)
        self.assertEqual(self.state("b").parent_id, "a")
        self.call("a", "SetTag", 0xABC5)  # re-tagging does not move the link
        self.assertEqual(self.state("b").parent_id, "a")
        self.call("b", "SetParentByTag", 0xABC0)
        self.assertIsNone(self.state("b").parent_id)

    def test_set_target_by_tag_vectors(self):
        self.call("b", "SetTag", 0xABC1)
        self.state("a").current_target = ("p", 0)
        self.call("a", "SetTargetByTag", 0xABC1)
        self.assertEqual((self.state("a").current_target, self.state("a").cond_flags), (("b", 0), 1))
        self.remove(self.b)
        self.call("a", "SetTargetByTag", 0xABC1)
        self.assertEqual((self.state("a").current_target, self.state("a").cond_flags), (("b", 0), 0))

    def test_set_target_by_tag_finds_a_routed_unit(self):
        self.call("p", "SetTag", 0xABC0)
        self.p.routing = True
        self.call("a", "SetTargetByTag", 0xABC0)
        self.assertEqual(self.state("a").current_target, ("p", 0))

    def test_set_target_by_tag_writes_the_condition_inside_a_script(self):
        self.call("b", "SetTag", 0xABC1)
        state = self.state("a")
        state.script_id, state.pc = 1, 0
        state.script_dll = FakeDll([word("SetTargetByTag"), 0xABC1, word("SendEventSelfIfTrue"), 7, END])
        self.interp.run("a", state, 1, self.battle.rng)
        self.assertEqual(self.queue("a"), [(7, "a")])


class SendTests(RoutingTestCase):
    def test_send_event_to_parent(self):
        self.state("a").parent_id = "b"
        self.call("a", "SendEventToParent", 20)
        self.assertEqual(self.queue("b"), [(0x14, "a")])

    def test_send_event_to_parent_without_parent_or_to_a_removed_parent_does_nothing(self):
        self.call("a", "SendEventToParent", 20)
        self.state("a").parent_id = "b"
        self.remove(self.b)
        self.call("a", "SendEventToParent", 12)
        self.assertEqual(self.queue("b"), [])

    def test_send_event_to_parent_is_not_refused_in_deployment(self):
        self.battle.phase = "deployment"
        self.state("a").parent_id = "b"
        self.call("a", "SendEventToParent", 20)
        self.assertEqual(self.queue("b"), [(0x14, "a")])

    def test_send_event_to_tag_reaches_any_side_and_skips_three_words(self):
        self.call("p", "SetTag", 0xABC0)
        self.state("a").pc = 0
        next_pc = self.call("a", "SendEventToTag", 0xABC0, [word("SendEventToTag"), 0xABC0, 12])
        self.assertEqual((next_pc, self.queue("p")), (3, [(0x0C, "a")]))

    def test_send_event_to_tag_missing_or_in_deployment_does_nothing(self):
        self.call("a", "SendEventToTag", 0xABC0, [word("SendEventToTag"), 0xABC0, 12])
        self.call("p", "SetTag", 0xABC0)
        self.battle.phase = "deployment"
        self.call("a", "SendEventToTag", 0xABC0, [word("SendEventToTag"), 0xABC0, 12])
        self.assertEqual(self.queue("p"), [])

    def test_send_event_to_own_tag_is_the_next_event_taken(self):
        self.call("a", "SetTag", 0xABC1)
        self.state("a").event_queue.append(Event(code=3, source="b"))
        self.call("a", "SendEventToTag", 0xABC1, [word("SendEventToTag"), 0xABC1, 17])
        self.assertEqual(self.state("a").event_queue.pop().code, 0x11)  # LIFO head

    def test_send_event_to_unit_id_addresses_whoami_and_hidden_units(self):
        self.n.whoami, self.n.hidden = 24, True
        self.call("a", "SendEventToUnitId", 24, [word("SendEventToUnitId"), 24, 51])
        self.assertEqual(self.queue("n"), [(0x33, "a")])

    def test_send_event_to_unit_id_first_live_in_table_order(self):
        self.b.whoami = self.n.whoami = 24
        self.remove(self.b)
        self.call("a", "SendEventToUnitId", 24, [word("SendEventToUnitId"), 24, 51])
        self.assertEqual((self.queue("b"), self.queue("n")), ([], [(0x33, "a")]))

    def test_send_event_to_unit_id_with_no_match_does_nothing(self):
        self.call("a", "SendEventToUnitId", 24, [word("SendEventToUnitId"), 24, 51])
        self.assertTrue(all(not self.queue(unit) for unit in "abpn"))

    def test_side_broadcasts_put_neutral_units_on_the_players_side(self):
        self.call("p", "SendEventToOwnSide", 9)
        self.assertEqual([unit for unit in "abpn" if self.queue(unit)], ["p", "n"])
        self.call("n", "SendEventToEnemySide", 22)
        self.assertEqual([unit for unit in "ab" if (22, "n") in self.queue(unit)], ["a", "b"])

    def test_broadcasts_are_refused_in_deployment(self):
        self.battle.phase = "deployment"
        self.call("a", "SendEventToOwnSide", 9)
        self.assertEqual(self.queue("b"), [])


class ReacquireTests(RoutingTestCase):
    def setUp(self):
        super().setUp()
        self.state("p").current_target = ("a", 0)
        self.state("p").current_event = Event(code=0x09, source="a")

    def test_player_style_non_independent_unit_re_forms(self):
        self.call("p", "ReacquireEventSource", 1)
        self.assertEqual(self.queue("p"), [(0x39, "a")])

    def test_independent_unit_counter_attacks(self):
        self.p.independent = True
        self.call("p", "ReacquireEventSource", 1)
        self.assertEqual(self.queue("p"), [(0x04, "a")])

    def test_ai_style_always_attacks(self):
        self.call("p", "ReacquireEventSource", 0)
        self.assertEqual(self.queue("p"), [(0x04, "a")])

    def test_event_from_another_unit_does_nothing(self):
        self.state("p").current_target = ("b", 0)
        self.call("p", "ReacquireEventSource", 0)
        self.assertEqual(self.queue("p"), [])

    def test_busy_units_do_nothing(self):
        for busy in ("charging", "melee", "shooting", "casting"):
            with self.subTest(busy=busy):
                self.p.attack_target = "a" if busy == "charging" else None
                self.p.in_melee = busy == "melee"
                self.state("p").unit_flags2 = {"shooting": 4, "casting": 2}.get(busy, 0)
                self.call("p", "ReacquireEventSource", 0)
                self.assertEqual(self.queue("p"), [])

    def test_does_not_touch_the_condition(self):
        self.state("p").cond_flags = 1
        self.call("p", "ReacquireEventSource", 0)
        self.assertTrue(self.state("p").cond_flags)


class SetSideTests(RoutingTestCase):
    def test_set_side_64_makes_an_enemy_unit_neutral(self):
        self.state("a").current_target = ("p", 0)
        self.call("a", "SetSide", 64)
        self.assertEqual(self.a.side, Side.NEUTRAL)
        self.assertEqual(self.state("a").current_target, ("p", 0))

    def test_set_side_on_a_neutral_unit_changes_nothing(self):
        self.call("n", "SetSide", 64)
        self.assertEqual(self.n.side, Side.NEUTRAL)

    def test_player_unit_turned_neutral_stays_on_the_player_broadcast_side(self):
        self.call("p", "SetSide", 64)
        self.call("p", "SendEventToEnemySide", 22)
        self.assertEqual([unit for unit in "abn" if self.queue(unit)], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
