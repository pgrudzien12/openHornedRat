"""The BF014 ground-fire event path (script_shooting.md §3; target_queries.md §§1–2)."""
import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.engine import Battle, Regiment
from whshr.nodes import ScriptNode
from whshr.rules import Side


class GroundPointRangeTests(unittest.TestCase):
    def setUp(self):
        self.unit = Regiment('dragon', 'Dragon', 1120, 600, 384, Side.ENEMY, models=1, ranks=1,
                             sprite='MeshDragon', shooting_code=14, missile_range=576, unit_class=1)
        self.battle = Battle(2000, 2000, [self.unit], script_nodes=[ScriptNode(900, 600)])
        self.runner = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states['dragon']

    def query(self, point):
        self.state.target_point = point
        self.runner.op_InArcAndRange(self.state, 1, [], 'dragon', 0, self.battle.rng)
        return bool(self.state.cond_flags)

    def test_ground_point_uses_the_same_strict_arc_range_and_validity_rules(self):
        for point, expected in (((900, 600), True), ((544, 600), False), ((545, 600), True),
                                ((1020, 700), False), ((1020, 699), True),
                                ((1120, 600), True), ((1200, 600), False),
                                ((-1, 600), False), (None, False)):
            with self.subTest(point=point):
                self.assertEqual(self.query(point), expected)

    def test_existing_target_unit_takes_precedence_over_point(self):
        target = Regiment('target', 'Target', 1200, 600, 0, Side.PLAYER, models=1, ranks=1)
        self.battle.regiments[target.identifier] = target
        self.state.current_target = ('target', 0)
        self.assertFalse(self.query((900, 600)))
        target.x = 900
        self.assertTrue(self.query((1200, 600)))

    def test_point_fallback_does_not_change_the_unit_only_arc_and_range_queries(self):
        self.state.target_point = (900, 600)
        for name in ('InArc', 'InRange'):
            getattr(self.runner, 'op_' + name)(self.state, 0, [], 'dragon', 0, self.battle.rng)
            self.assertFalse(self.state.cond_flags)

    def test_node_event_reaches_checked_volley_script_and_launches_without_target_unit(self):
        # A minimal independently authored version of the documented 154 -> 110 -> 115 path.
        dll = FakeDll({
            154: [word('TakeRangedEventTarget'), word('GosubScript'), 110, word('Yield'), behaviour.END],
            110: [word('ReadyToFire'), 1, word('If'), word('InArcAndRange'), 1, word('If'),
                  word('GosubScript'), 115, word('EndIf'), word('EndIf'), word('ReturnGosub'), behaviour.END],
            115: [word('FireAtTarget'), word('ReturnGosub'), behaviour.END],
        })
        self.runner = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, dll)
        self.runner.op_FireAtNode(self.state, 0, [], 'dragon', 0, self.battle.rng)
        self.assertFalse(self.battle.innate_projectiles)  # command queues, does not launch
        self.state.current_event = self.state.event_queue.pop()
        self.state.script_id = 154
        self.runner.run('dragon', self.state, 1, self.battle.rng)
        self.assertIsNone(self.state.current_target)
        self.assertEqual(self.state.target_point, (900, 600))
        self.assertGreaterEqual(len(self.battle.innate_projectiles), 4)
        self.assertEqual(self.unit.melee_models[0].action, 7)
