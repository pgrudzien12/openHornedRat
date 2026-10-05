"""Arc, range, broken and visibility queries (notes/target_queries.md, sections 1, 2 and 4).

The unit is at (0, 0) with a bow (range 576) unless stated otherwise; facing 0 = +Y, 128 = +X.
"""

import unittest
import unittest.mock

from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class TargetQueryTestCase(unittest.TestCase):
    def build(self, facing=0, target_at=(0, 100), range_=576, target_routing=False, with_target=True):
        self.unit = Regiment("u", "U", 0, 0, facing, Side.ENEMY, models=5, ranks=1)
        self.unit.missile_range = range_
        regiments = [self.unit]
        if with_target:
            self.target = Regiment("x", "X", target_at[0], target_at[1], 0, Side.PLAYER, models=5, ranks=1)
            self.target.routing = target_routing
            regiments.append(self.target)
        self.battle = Battle(2000, 2000, regiments, seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["u"]
        self.state.current_target = ("x", 0) if with_target else None

    def query(self, name, operand=None):
        pc = self.state.pc
        result = getattr(self.interp, "op_" + name)(self.state, operand, [], "u", 0, None)
        self.last_advance = result - pc
        return bool(self.state.cond_flags)


class ArcAndRangeTests(TargetQueryTestCase):
    def test_vectors_from_the_report(self):
        rows = [
            (128, (500, 0), "InArcAndRange", 0, True),
            (128, (576, 0), "InArcAndRange", 0, False),   # d = 576 is not < 576
            (0, (100, 99), "InArcAndRange", 1, False),    # bearing 64: outside the open arc
            (0, (99, 100), "InArc", 0, True),             # bearing 63
            (0, (0, -300), "InArc", 0, False),            # directly behind
            (256, (0, -575), "InRange", 0, True),         # range does not test the arc
        ]
        for facing, target_at, name, operand, expected in rows:
            self.build(facing=facing, target_at=target_at)
            self.assertEqual(self.query(name, operand), expected, (facing, target_at, name))
            self.assertEqual(self.last_advance, 2)

    def test_no_target_writes_false_for_every_query(self):
        for name in ("InArc", "InRange", "InArcAndRange"):
            self.build(with_target=False)
            self.state.cond_flags = True
            self.assertFalse(self.query(name, 0), name)

    def test_melee_unit_without_a_missile_weapon_is_never_in_range(self):
        self.build(facing=128, target_at=(10, 0), range_=None)
        self.assertFalse(self.query("InRange", 0))

    def test_target_exactly_on_the_unit_skips_the_arc_test_but_not_in_arc(self):
        self.build(facing=0, target_at=(0, 0))
        self.assertTrue(self.query("InArcAndRange", 0))  # arc skipped, d = 0 < range
        self.assertFalse(self.query("InArc", 0))         # bearing 256: behind a unit facing 0
        self.unit.direction = 256
        self.assertTrue(self.query("InArc", 0))

    def test_the_message_operand_never_changes_the_result(self):
        self.build(facing=0, target_at=(100, 99))
        self.assertEqual(self.query("InArcAndRange", 0), self.query("InArcAndRange", 1))

    def test_the_condition_is_overwritten_not_kept(self):
        self.build(facing=128, target_at=(500, 0))
        self.state.cond_flags = False
        self.assertTrue(self.query("InRange", 0))
        self.target.x = 700
        self.assertFalse(self.query("InRange", 0))


class BrokenTargetTests(TargetQueryTestCase):
    def test_broken_target_in_range_vectors(self):
        rows = [(False, (5000, 0), True), (True, (400, 0), True), (True, (700, 0), False)]
        for routing, target_at, expected in rows:
            self.build(target_at=target_at, target_routing=routing)
            self.assertEqual(self.query("BrokenTargetInRange"), expected, (routing, target_at))
            self.assertEqual(self.last_advance, 1)

    def test_if_target_not_broken(self):
        self.build(target_routing=True)
        self.assertFalse(self.query("IfTargetNotBroken"))
        self.build(target_routing=False)
        self.assertTrue(self.query("IfTargetNotBroken"))
        self.build(with_target=False)
        self.assertFalse(self.query("IfTargetNotBroken"))
        self.assertFalse(self.query("BrokenTargetInRange"))


class TargetVisibleTests(TargetQueryTestCase):
    def test_target_behind_the_unit_is_visible_when_the_line_is_clear(self):
        self.build(facing=0, target_at=(0, -300))
        self.assertTrue(self.query("IfTargetVisible"))

    def test_the_view_cone_is_ignored_and_scenery_decides(self):
        self.build(facing=0, target_at=(0, -300))
        with unittest.mock.patch.object(interpreter.visibility, "visible", return_value=False) as visible:
            self.assertFalse(self.query("IfTargetVisible"))
        facing_used, half_cone = visible.call_args.args[1], visible.call_args.args[4]
        self.assertAlmostEqual(facing_used, 256)  # the unit is treated as facing its target
        self.assertGreaterEqual(half_cone, 256)   # no cone can fail

    def test_no_target_is_false(self):
        self.build(with_target=False)
        self.assertFalse(self.query("IfTargetVisible"))


if __name__ == "__main__":
    unittest.main()
