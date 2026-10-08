"""Query cases, UnitScore, periodic threat tracking and the class/machine/objective/target tests
(notes/script_queries.md). Vectors are the report's tables: S at (0, 0), threat range 240 unless stated."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import combat, behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side

END = behaviour.END


def unit(identifier, x, y, side=Side.PLAYER, worth=100, **extra):
    """A regiment of 10 models whose worth (size x points) is `worth`."""
    return Regiment(identifier, identifier, x, y, 0, side, models=10, ranks=2, points=worth // 10,
                    unit_class=1, **extra)


class QueryTestCase(unittest.TestCase):
    def make(self, *others, searcher=None, phase="battle"):
        self.s = searcher or unit("S", 0, 0, Side.ENEMY)
        self.battle = Battle(5000, 5000, [self.s, *others], seed=1995)
        self.battle.phase = phase
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)
        self.state = self.bus.unit_states["S"]
        self.state.threat_range = 240

    def query(self, case, event=None):
        if event is not None:
            self.state.current_event = event
        self.interp.op_Query(self.state, case, [word("Query"), case], "S", 0, self.battle.rng)
        return bool(self.state.cond_flags)

    def score(self, other):
        return self.interp._threat_score(self.s, other, self.state.threat_range)

    def queued(self, unit_id="S"):
        return [(event.code, event.source) for event in self.bus.unit_states[unit_id].event_queue]


class UnitScoreTests(QueryTestCase):
    def test_octagonal_distance_rounds_the_half_up(self):
        self.make(unit("E", 31, 100))
        self.assertEqual(self.interp._octagonal(self.s, self.battle.regiments["E"]), 116)

    def test_score_vectors(self):
        e1, e2 = unit("E1", 0, 100), unit("E2", 31, 100)
        self.make(e1, e2)
        self.assertEqual((self.score(e1), self.score(e2)), (233, 206))
        e1.attack_target = "S"
        self.assertEqual(self.score(e1), 233 * 32)
        e1.attack_target = None
        self.bus.unit_states["E1"].current_target = ("S", 0)
        self.assertEqual(self.score(e1), 233 * 4)

    def test_sixteen_bit_wrap_of_a_close_charging_threat(self):
        threat = unit("T", 0, 10, worth=300, attack_target="S")
        self.make(threat)
        self.assertEqual(self.score(threat), -28736)

    def test_exclusions(self):
        for state in ("in_melee", "routing"):
            with self.subTest(state=state):
                other = unit("E", 0, 100, **{state: True})
                self.make(other)
                self.assertEqual(self.score(other), 0)
        self.make(unit("F", 0, 100, Side.ENEMY))
        self.assertEqual(self.score(self.battle.regiments["F"]), 0)  # not hostile
        hidden = unit("H", 0, 100, hidden=True)
        self.make(hidden)
        self.assertEqual(self.score(hidden), 233)  # hidden is filtered by the searches, not the score


class Query1Tests(QueryTestCase):
    def test_picks_the_best_threat(self):
        self.make(unit("E1", 0, 100), unit("E2", 31, 100))
        self.assertTrue(self.query(1))
        self.assertEqual((self.state.threat, self.state.threat_score, self.state.current_target), ("E1", 233, None))

    def test_range_edge_and_clearing(self):
        far = unit("E1", 0, 239)
        self.make(far)
        self.assertTrue(self.query(1))
        self.assertEqual(self.state.threat_score, 1)
        far.y = 240
        self.assertFalse(self.query(1))
        self.assertEqual((self.state.threat, self.state.threat_score), (None, 0))

    def test_ties_go_to_the_first_unit(self):
        self.make(unit("E1", 0, 100), unit("E2", 100, 0))
        self.query(1)
        self.assertEqual(self.state.threat, "E1")

    def test_hidden_and_marked_units_are_not_candidates(self):
        self.make(unit("E1", 0, 100, hidden=True), unit("E2", 0, 120))
        self.bus.unit_states["E2"].unit_flags |= interpreter.LEAVING_BATTLE_FLAG
        self.assertFalse(self.query(1))

    def test_deployment_writes_nothing(self):
        self.make(unit("E1", 0, 100), phase="deployment")
        self.state.threat = "E1"
        self.assertFalse(self.query(1))
        self.assertEqual(self.state.threat, "E1")


class EventQueryTests(QueryTestCase):
    def test_case_3_attacks_the_nearest_marked_unit(self):
        self.make(unit("V1", 0, 300, Side.NEUTRAL, hidden=True), unit("V2", 100, 250, Side.NEUTRAL))
        for victim in ("V1", "V2"):
            self.bus.unit_states[victim].unit_flags |= interpreter.LEAVING_BATTLE_FLAG
        self.assertTrue(self.query(3))
        self.assertEqual(self.queued(), [(4, "V1")])

    def test_case_3_is_true_even_when_deployment_refuses_the_event(self):
        self.make(unit("V1", 0, 300, Side.NEUTRAL), phase="deployment")
        self.bus.unit_states["V1"].unit_flags |= interpreter.LEAVING_BATTLE_FLAG
        self.assertTrue(self.query(3))
        self.assertEqual(self.queued(), [])

    def test_case_5_tells_the_target_and_is_false(self):
        self.make(unit("T", 0, 300))
        self.state.current_target = ("T", 0)
        self.assertFalse(self.query(5))
        self.assertEqual(self.queued("T"), [(5, "S")])

    def test_case_6_prefers_a_strictly_better_source(self):
        attacker = unit("E", 0, 100)
        self.make(attacker, unit("E2", 0, 100))
        self.bus.unit_states["E"].current_target = ("S", 0)
        self.assertTrue(self.query(6, Event(code=5, source="E")))
        self.assertEqual((self.state.threat, self.state.threat_score), ("E", 932))
        self.bus.unit_states["E2"].current_target = ("S", 0)
        self.assertFalse(self.query(6, Event(code=5, source="E2")))  # equal score does not switch

    def test_case_6_ignores_a_hidden_source(self):
        self.make(unit("E", 0, 100, hidden=True))
        self.assertFalse(self.query(6, Event(code=5, source="E")))

    def test_case_7_braces_once(self):
        self.make(unit("C", 0, 100))
        self.state.remembered_event = ("C", 0x07)
        self.assertTrue(self.query(7))
        self.assertEqual((self.state.current_target, self.s.braced), (("C", 0), True))
        self.assertFalse(self.query(7))

    def test_case_7_refuses_an_already_braced_unit(self):
        self.make(unit("C", 0, 100))
        self.s.braced = True
        self.state.remembered_event = ("C", 0x07)
        self.assertFalse(self.query(7))
        self.assertEqual(self.state.remembered_event, ("C", 0x07))

    def test_case_9_vectors(self):
        rows = [((0, 239), True), ((0, 240), False), ((31, 224), False)]
        for position, expected in rows:
            with self.subTest(position=position):
                self.make(unit("F", *position, Side.ENEMY), unit("E", 0, 2000))
                self.bus.unit_states["F"].current_target = ("E", 0)
                self.assertEqual(self.query(9, Event(code=0x13, source="F")), expected)
                self.assertEqual(self.queued(), [(4, "E")] if expected else [])

    def test_case_9_needs_no_own_target_and_a_friend_target(self):
        self.make(unit("F", 0, 100, Side.ENEMY), unit("E", 0, 2000))
        self.assertFalse(self.query(9, Event(code=0x13, source="F")))
        self.bus.unit_states["F"].current_target = ("E", 0)
        self.state.current_target = ("E", 0)
        self.assertFalse(self.query(9, Event(code=0x13, source="F")))

    def test_case_10_measures_to_the_friends_threat(self):
        self.make(unit("F", 0, 1000, Side.ENEMY), unit("E", 0, 200))
        self.bus.unit_states["F"].threat = "E"
        self.assertTrue(self.query(10, Event(code=0x15, source="F")))
        self.assertEqual(self.queued(), [(4, "E")])

    def test_case_22_forgets_a_removed_unit(self):
        self.make(unit("X", 0, 100), unit("Y", 0, 300))
        self.state.threat, self.state.current_target = "X", ("Y", 0)
        self.assertFalse(self.query(22, Event(code=0x16, source="X")))
        self.assertEqual((self.state.threat, self.state.current_target, self.queued()), (None, ("Y", 0), []))
        self.state.current_target = ("X", 0)
        self.query(22, Event(code=0x16, source="X"))
        self.assertEqual(self.queued(), [(0x19, None)])

    def test_case_17_turns_and_jumps(self):
        self.make()
        self.battle.rng.randrange = lambda n: 0
        self.query(17)
        self.assertEqual(self.s.direction, 128)
        self.assertAlmostEqual(self.s.x, 48.0)

    def test_always_false_cases(self):
        self.make(unit("E", 0, 100))
        for case in (0, 8, 18, 24, 99):
            with self.subTest(case=case):
                self.state.cond_flags = 1
                self.assertFalse(self.query(case))


class TrackThreatTests(QueryTestCase):
    def test_periodic_schedule_with_period_two(self):
        self.make()
        calls = []
        self.interp._track_threat = lambda unit_id, state: calls.append(True)
        self.state.script_id, self.state.pc = 1, 0
        self.state.script_dll = FakeDll([word("SetBehaviour"), 15, 2, word("PushPC"), word("Yield"), word("Loop"),
                                         END])
        for _ in range(5):
            self.interp.run("S", self.state, 1, self.battle.rng)
        # update 1 configures; due at updates 2 and 5 (P + 1 apart)
        self.assertEqual(len(calls), 2)

    def test_scenario(self):
        p1, p2 = unit("P1", 0, 200, worth=150), unit("P2", 100, 150, worth=100)
        self.make(p1, p2, searcher=unit("S", 0, 0, Side.ENEMY, worth=120))
        self.state.threat_range = 400
        self.interp._track_threat("S", self.state)
        self.assertEqual((self.state.threat, self.state.threat_score), ("P1", 300))
        p1.y = 150
        self.interp._track_threat("S", self.state)
        self.assertEqual((self.queued(), self.state.threat_score), ([(3, "P1")], 300))

    def test_re_pick_keeps_a_stale_threat_unless_beaten(self):
        p1, p2 = unit("P1", 0, 150, worth=150), unit("P2", 100, 150, worth=100)
        self.make(p1, p2, searcher=unit("S", 0, 0, Side.ENEMY, worth=100000))
        self.state.threat_range = 400
        self.state.threat = "P1"
        p1.in_melee = True
        self.interp._track_threat("S", self.state)
        self.assertEqual((self.state.threat, self.state.threat_score), ("P2", 200))

    def test_if_threat_outweighs_worth_reads_only_the_slot(self):
        self.make(unit("E", 0, 100))
        self.interp.op_IfThreatOutweighsWorth(self.state, None, [], "S", 0, None)
        self.assertFalse(self.state.cond_flags)  # empty slot: no scan
        self.state.threat = "E"
        self.interp.op_IfThreatOutweighsWorth(self.state, None, [], "S", 0, None)
        self.assertTrue(self.state.cond_flags)  # 233 > own worth 100


class UnitTestOpcodeTests(QueryTestCase):
    def call(self, name, operand=None):
        getattr(self.interp, "op_" + name)(self.state, operand, [word(name), operand or 0], "S", 0, None)
        return bool(self.state.cond_flags)

    def test_if_class_compares_the_class_code(self):
        self.make(searcher=unit("S", 0, 0, Side.ENEMY))
        self.s.unit_class = 4
        self.assertEqual((self.call("IfClass", 32), self.call("IfClass", 4)), (True, False))

    def test_set_class_turns_a_crew_into_infantry(self):
        self.make()
        self.s.unit_class = 4
        self.assertTrue(self.call("SetClass", 8))
        self.assertEqual((self.s.unit_class, self.s.anchored), (1, False))
        self.assertFalse(self.call("SetClass", 8))

    def test_if_machine_destroyed(self):
        self.make()
        self.assertTrue(self.call("IfMachineDestroyed"))  # no leader model
        self.s.has_leader = True
        self.assertFalse(self.call("IfMachineDestroyed"))

    def test_if_machine_destroyed_follows_the_leader_model_not_the_whole_unit(self):
        self.make()
        self.s.has_leader = True
        self.s.model_positions()
        self.s.leader_wounds = 3
        self.assertFalse(self.call("IfMachineDestroyed"))
        leader = self.s.melee_models[self.s.leader_model_index]
        leader.wounds_taken = 2
        self.assertFalse(self.call("IfMachineDestroyed"))  # wounded, still standing
        leader.wounds_taken = 3
        self.assertTrue(self.call("IfMachineDestroyed"))  # all its wounds taken
        leader.wounds_taken = 0
        combat.kill_models(self.s, [self.s.leader_model_index], self.battle)
        self.assertTrue(self.s.models > 0)
        self.assertTrue(self.call("IfMachineDestroyed"))  # the leader died, the unit did not

    def test_if_objective_tests_the_battle_file_letters(self):
        self.make()
        self.battle.objective_letters = frozenset("AG")
        self.assertEqual((self.call("IfObjective", 7), self.call("IfObjective", 2)), (True, False))

    def test_target_gone(self):
        self.make(unit("T", 0, 100))
        self.state.current_target = ("T", 0)
        self.state.current_event = Event(code=24, source="T")
        self.assertFalse(self.call("TargetGone"))
        self.assertEqual(self.queued(), [(0x19, None)])
        self.state.current_event = Event(code=24, source="U")
        self.state.event_queue.clear()
        self.assertFalse(self.call("TargetGone"))
        self.assertEqual(self.queued(), [])

    def test_target_valid(self):
        self.make(unit("T", 0, 400), unit("F", 0, 390, Side.ENEMY))
        self.assertFalse(self.call("TargetValid"))  # no target, no point
        self.state.current_target = ("T", 0)
        self.assertTrue(self.call("TargetValid"))
        self.s.independent = True
        self.assertFalse(self.call("TargetValid"))  # a friend stands next to the aim point
        self.s.independent, self.s.missile_code = False, 2
        self.assertFalse(self.call("TargetValid"))  # crossbow: the friend is on the line of fire


if __name__ == "__main__":
    unittest.main()
