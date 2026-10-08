"""Periodic behaviour codes, CaseEvent skipping and React N (notes/script_behaviours.md parts 1 and 3).

Vectors follow the report's tables: unit S at (0, 0), threat range 240 unless stated.
"""

import unittest

from tests.script_helpers import word
from whshr import behaviour, interpreter, ranged
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.nodes import ScriptNode
from whshr.rules import Side

END = behaviour.END


def unit(identifier, x, y, side=Side.PLAYER, worth=100, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=10, ranks=2, points=worth // 10, **extra)


class BehaviourTestCase(unittest.TestCase):
    def make(self, *units, nodes=None):
        self.battle = Battle(5000, 5000, list(units), seed=1995, script_nodes=nodes)
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)
        self.state = self.bus.unit_states[units[0].identifier]
        self.state.threat_range = 240

    def run_code(self, code):
        self.interp._run_behaviour(self.state_id(), self.state, code)

    def state_id(self):
        return next(k for k, v in self.bus.unit_states.items() if v is self.state)

    def queued(self, unit_id=None):
        return [(e.code, e.source) for e in self.bus.unit_states[unit_id or self.state_id()].event_queue]


class DetectThreatTests(BehaviourTestCase):
    def test_threat_targeting_the_unit_is_answered(self):
        self.make(unit("S", 0, 0), unit("E", 0, 100, Side.ENEMY))
        self.bus.unit_states["E"].current_target = ("S", 0)
        self.state.threat, self.state.cond_flags = "E", 1
        self.run_code(11)
        self.assertEqual((self.state.threat_score, self.queued()), (932, [(3, "E")]))
        self.assertTrue(self.state.cond_flags)  # a periodic run never writes the condition

    def test_threat_targeting_someone_else_is_ignored_unless_independent(self):
        self.make(unit("S", 0, 0), unit("E", 0, 100, Side.ENEMY))
        self.state.threat, self.state.threat_score = "E", 5
        self.run_code(11)
        self.assertEqual((self.queued(), self.state.threat_score), ([], 5))
        self.battle.regiments["S"].independent = True
        self.run_code(11)
        self.assertEqual((self.queued(), self.state.threat_score), ([(3, "E")], 233))

    def test_out_of_range_independent_unit_re_picks(self):
        self.make(unit("S", 0, 0, independent=True), unit("E", 0, 240, Side.ENEMY), unit("F", 0, 100, Side.ENEMY))
        self.state.threat = "E"
        self.run_code(11)
        self.assertEqual(self.state.threat, "F")

    def test_braced_unit_only_spots(self):
        self.make(unit("S", 0, 0, braced=True), unit("E", 0, 100, Side.ENEMY))
        self.bus.unit_states["E"].current_target = ("S", 0)
        self.state.threat = "E"
        self.run_code(11)
        self.assertEqual(self.queued(), [])

    def test_never_fills_an_empty_slot_for_a_non_independent_unit(self):
        self.make(unit("S", 0, 0), unit("E", 0, 100, Side.ENEMY))
        self.run_code(11)
        self.assertIsNone(self.state.threat)

    def test_spotting_reveals_hidden_enemies_in_view(self):
        self.make(unit("S", 0, 0), unit("H", 0, 300, Side.ENEMY, hidden=True))
        self.run_code(13)
        self.assertFalse(self.battle.regiments["H"].hidden)
        self.assertEqual((self.queued(), self.queued("H")), ([(0x1C, "H")], [(0x1D, "S")]))


class ObjectiveAndSiegeTests(BehaviourTestCase):
    def test_code_12_signals_inside_node_id_99_in_state_4(self):
        nodes = [ScriptNode(0.0, 0.0)] * 13 + [ScriptNode(1000.0, 1940.0, 99, 47)]
        for y, expected in ((1987, [(0x36, None)]), (1988, [])):
            with self.subTest(y=y):
                self.make(unit("S", 1000, y), nodes=nodes)
                self.battle.mission_state = 4
                self.run_code(12)
                self.assertEqual(self.queued(), expected)

    def test_codes_19_and_20_move_the_battle_to_state_5(self):
        nodes = [ScriptNode(0.0, 0.0)] * 14 + [ScriptNode(1000.0, 2290.0, 0, 16)]
        self.make(unit("S", 1000, 2306, routing=True), unit("O", 0, 0), nodes=nodes)
        self.battle.mission_state = 4
        self.run_code(19)
        self.assertEqual(self.battle.mission_state, 4)  # 19 refuses a broken unit
        self.run_code(20)
        self.assertEqual(self.battle.mission_state, 5)
        self.assertIn((0x38, None), self.queued("O"))


class SignalAndBombardTests(BehaviourTestCase):
    def test_code_16_signals_a_threat_in_range_even_when_braced(self):
        self.make(unit("S", 0, 0, braced=True), unit("E", 0, 100, Side.ENEMY))
        self.state.threat = "E"
        self.run_code(16)
        self.assertEqual(self.queued(), [(0x33, "E")])

    def test_code_21_breathes_at_the_nearest_non_allied_unit(self):
        self.make(unit("D", 0, 0, Side.ENEMY), unit("G", 0, 50, Side.NEUTRAL), unit("O", 60, 0, Side.ENEMY),
                  unit("P", 0, 100))
        self.state.threat_range = 120
        self.run_code(21)
        self.assertEqual([(e.code, e.x, e.y) for e in self.bus.unit_states["D"].event_queue], [(0x21, 60, 0)])

    def test_code_14_flees_from_a_visible_enemy_in_reach(self):
        self.make(unit("S", 0, 0), unit("E", 0, 100, Side.ENEMY, hidden=True))
        self.run_code(14)
        self.assertEqual(self.queued(), [])
        self.battle.regiments["E"].hidden = False
        self.run_code(14)
        self.assertEqual(self.queued(), [(0x03, None)])


class InnateWeaponTests(BehaviourTestCase):
    def test_pestilent_breath_partial_and_full_reloads(self):
        monks = unit("M", 0, 0, Side.ENEMY, initiative=0)  # reload (10 - 0) x 18 = 180
        monks.models = 24  # divisor 7
        self.make(monks)
        reload = int(ranged.reload_time(monks))
        self.assertEqual(reload, 180)
        breaths = []
        for elapsed in (25, 50, 200):
            monks.reload_ticks = reload + 1 - elapsed
            before = len(self.battle.events)
            self.run_code(27)
            breaths.append((len(self.battle.events) > before, monks.reload_ticks == reload + 1))
        self.assertEqual(breaths, [(False, False), (True, False), (True, True)])

    def test_innate_reload_clock_reads_the_leader_block(self):
        wheel = unit("W", 0, 0, Side.ENEMY, initiative=0)  # own block: (10 - 0) x 18 = 180
        wheel.leader_initiative = 5  # leader block: (10 - 5) x 18 = 90
        self.make(wheel)
        self.assertEqual((ranged.reload_time(wheel), ranged.reload_time(wheel, leader_block=True)), (180, 90))
        self.run_code(26)
        self.assertEqual(wheel.reload_ticks, 91)  # stamped with the leader block's time + 1

    def test_doomwheel_rider_runs_code_26_from_a_detect_threat_even_when_braced(self):
        wheel = unit("W", 0, 0, Side.ENEMY)
        wheel.leader_missile_code = 13
        wheel.braced = True
        self.make(wheel)
        self.run_code(11)
        self.assertEqual(len([e for e in self.battle.events if e.kind == "doomwheel_bolts"]), 1)
        plain = unit("P", 500, 500, Side.ENEMY)
        self.make(plain)
        self.run_code(11)
        self.assertEqual([e for e in self.battle.events if e.kind == "doomwheel_bolts"], [])

    def test_doomwheel_fires_three_bolts_when_reloaded(self):
        wheel = unit("W", 0, 0, Side.ENEMY)
        wheel.direction = 100
        self.make(wheel)
        self.run_code(26)
        self.assertEqual([e.data["headings"] for e in self.battle.events if e.kind == "doomwheel_bolts"],
                         [[100, 228, 484]])
        before = len(self.battle.events)
        self.run_code(26)  # just stamped: not ready
        self.assertEqual(len(self.battle.events), before)


class CaseEventTests(unittest.TestCase):
    def test_skip_lands_after_the_break_and_its_label(self):
        battle = Battle(500, 500, [unit("S", 0, 0)], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["S"]
        state.current_event = Event(code=7)
        words = [word("CaseEvent"), 10, word("Yield"), word("Break"), 0x1ABC, word("CaseEvent"), 7]
        state.pc = 0
        self.assertEqual(interp.op_CaseEvent(state, 10, words, "S", 0, None), 5)
        state.pc = 5
        self.assertEqual(interp.op_CaseEvent(state, 7, words, "S", 0, None), 7)


class ReactTests(BehaviourTestCase):
    def react(self, regiment, code):
        self.make(regiment)
        self.battle.text_resources = {34103: "Retreat text", 34002: "Charge text"}
        self.interp.op_React(self.state, code, [word("React"), code], regiment.identifier, 0, None)
        return [(e.data["text_id"], e.data["message"], e.data["expression"])
                for e in self.battle.events if e.kind == "react"]

    def test_player_human_unit(self):
        self.assertEqual(self.react(unit("H", 0, 0, race=0), 4), [(34103, "Retreat text", 4)])
        self.assertIn(("play", 5, 1), [(e.data["cue"], e.data["packet"], e.data["effect"])
                                       for e in self.battle.events if e.kind == "sound"])

    def test_enemy_units(self):
        self.assertEqual(self.react(unit("O", 0, 0, Side.ENEMY, race=4, hidden=True), 2), [])  # off screen
        self.assertEqual(self.react(unit("O", 0, 0, Side.ENEMY, race=4), 2), [(34002, "Charge text", 0)])
        self.assertEqual(self.react(unit("H", 0, 0, Side.ENEMY, race=0), 1), [])  # P-marked

    def test_no_text_means_nothing(self):
        self.assertEqual(self.react(unit("P", 0, 0, race=6), 2), [])


if __name__ == "__main__":
    unittest.main()
