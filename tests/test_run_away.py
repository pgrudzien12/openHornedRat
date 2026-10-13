"""RunAway (notes/runaway_routers_broken.md 1): one 256-unit point move away from the threat, sideways when an enemy is
seen behind, false when cornered; never a rout. Vectors of section 1.5: unit U at (0,0) facing 0 (+Y), threat range
240, threat T at (0,100)."""

import unittest
from unittest import mock

from whshr.engine import Battle, Regiment
from whshr.interpreter import ScriptInterpreter
from whshr.rules import Side


def unit(identifier, x, y, side, direction=0, **kwargs):
    return Regiment(identifier, identifier, x, y, direction, side, models=kwargs.pop("models", 1),
                    ranks=kwargs.pop("ranks", 1), **kwargs)


class RunAwayTests(unittest.TestCase):
    def setup(self, *others, facing=0, threat_slot=True):
        self.u = unit("u", 0, 0, Side.ENEMY, direction=facing)
        self.t = unit("t", 0, 100, Side.PLAYER, direction=256)
        self.battle = Battle(2000, 2000, [self.u, self.t, *others], seed=1995)
        self.battle.phase = "battle"
        self.interp = ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["u"]
        self.state.threat_range = 240
        if threat_slot:
            self.state.threat = "t"

    def run_away(self):
        goals = []
        with mock.patch.object(self.interp, "_start_point_move", lambda unit, goal: goals.append(goal)):
            self.interp.op_RunAway(self.state, None, [], "u", 0, None)
        return bool(self.state.cond_flags), goals

    def test_nobody_behind_runs_straight_away(self):
        self.setup()
        self.assertEqual(self.run_away(), (True, [(0, -256)]))
        self.assertFalse(self.u.routing)
        self.assertEqual(self.state.threat, "t")

    def test_an_enemy_behind_sends_it_to_the_right_then_the_left_then_it_is_cornered(self):
        behind = unit("e1", 0, -150, Side.PLAYER)
        right = unit("e2", 150, 0, Side.PLAYER)
        left = unit("e3", -150, 0, Side.PLAYER)
        self.setup(behind)
        self.assertEqual(self.run_away(), (True, [(236, -97)]))
        self.setup(behind, right)
        self.assertEqual(self.run_away(), (True, [(-236, -97)]))
        self.setup(behind, right, left)
        self.assertEqual(self.run_away(), (False, []))

    def test_the_threat_range_is_inclusive(self):
        self.setup(unit("e1", 0, -241, Side.PLAYER))
        self.assertEqual(self.run_away()[1], [(0, -256)])
        self.setup(unit("e1", 0, -240, Side.PLAYER))
        self.assertEqual(self.run_away()[1], [(236, -97)])

    def test_broken_enemies_count_hidden_and_friendly_units_do_not(self):
        broken = unit("e1", 0, -150, Side.PLAYER)
        broken.routing = True
        self.setup(broken)
        self.assertEqual(self.run_away()[1], [(236, -97)])
        self.setup(unit("e1", 0, -150, Side.PLAYER, hidden=True))
        self.assertEqual(self.run_away()[1], [(0, -256)])
        self.setup(unit("e1", 0, -150, Side.ENEMY))
        self.assertEqual(self.run_away()[1], [(0, -256)])

    def test_a_unit_facing_away_sees_the_threat_behind_and_steps_to_its_right(self):
        self.setup(facing=256)
        self.assertEqual(self.run_away(), (True, [(236, -97)]))

    def test_without_a_threat_it_runs_from_the_current_target(self):
        self.setup(threat_slot=False)
        self.state.current_target = ("t", 0)
        self.t.x, self.t.y = 100, 0
        self.assertEqual(self.run_away(), (True, [(-256, 0)]))
        self.state.current_target = None
        self.assertEqual(self.run_away(), (False, []))

    def test_refused_while_re_forming_anchored_or_held(self):
        for state in ("reforming", "held", "anchored"):
            with self.subTest(state=state):
                self.setup()
                if state == "anchored":
                    self.u.hud_class = "art"
                else:
                    setattr(self.u, state, True)
                self.assertEqual(self.run_away(), (False, []))

    def test_during_deployment_it_is_true_and_nothing_moves(self):
        self.setup()
        self.battle.phase = "deployment"
        self.assertEqual(self.run_away(), (True, []))


if __name__ == "__main__":
    unittest.main()
