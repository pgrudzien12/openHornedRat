"""The seam between behaviour scripts and ranged combat (notes/script_shooting.md).

With scripts running, the engine orders no volley of its own, player Fire orders become the shooter events the
scripts handle, and every ordinary projectile is launched by FireAtTarget / FireAt90PercentRange from the model
that posted the fire event.
"""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter, ranged
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.nodes import ScriptNode
from whshr.rules import Side

IDLE_SCRIPT = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


def shooter(name, x, y, side=Side.PLAYER, *, code=1, models=10, cls="arch", unit_class=3, facing=0):
    return Regiment(name, name, x, y, facing, side, models=models, ranks=2, hud_class=cls, unit_class=unit_class,
                    missile_code=code, shooting_code=code, missile_range=ranged.WEAPONS[code].reach,
                    bs=10, initiative=2, speed_per_tick=0)


class SeamTestCase(unittest.TestCase):
    def make(self, *units, scripted=True, nodes=None):
        self.battle = Battle(5000, 5000, list(units), seed=1995,
                             script_dll=FakeDll(IDLE_SCRIPT) if scripted else None, script_nodes=nodes)
        self.bus = self.battle.event_bus
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)

    def call(self, unit_id, name, operand=None, event=None):
        state = self.bus.unit_states[unit_id]
        if event is not None:
            state.current_event = event
        state.pc = 0
        getattr(self.interp, "op_" + name)(state, operand, [word(name), operand or 0], unit_id, 0, self.battle.rng)
        return bool(state.cond_flags)

    def aims(self):
        return [(p.x1, p.y1) for p in self.battle.projectiles]


class EngineGateTests(SeamTestCase):
    def test_scripted_battle_orders_no_engine_volley(self):
        bow, enemy = shooter("bow", 1000, 1000), shooter("e", 1000, 1300, Side.ENEMY)
        self.make(bow, enemy)
        bow.shooting_mode, bow.shooting_target = "target", "e"
        for _ in range(40):
            self.battle.tick()
        self.assertEqual(self.battle.projectiles, [])

    def test_scriptless_battle_keeps_the_engine_volley(self):
        bow, enemy = shooter("bow", 1000, 1000), shooter("e", 1000, 1300, Side.ENEMY)
        self.make(bow, enemy, scripted=False)
        self.battle.order_fire("bow", "e")
        for _ in range(10):
            self.battle.tick()
        self.assertTrue(self.battle.projectiles)


class FireOrderEventTests(SeamTestCase):
    def setUp(self):
        self.bow, self.enemy = shooter("bow", 1000, 1000), shooter("e", 1000, 1300, Side.ENEMY)
        self.make(self.bow, self.enemy)

    def queued(self):
        return [(e.code, e.source, e.x, e.y) for e in self.bus.unit_states["bow"].event_queue]

    def test_unit_ground_and_self_orders_become_events(self):
        self.assertEqual(self.battle.order_fire("bow", "e"), 2008)
        self.battle.order_fire("bow", point=(1100, 1400))
        self.battle.order_fire("bow", "bow")
        self.assertEqual(self.queued(), [(0x1F, "e", 0, 0), (0x21, None, 1100, 1400), (0x20, None, -1, -1)])
        self.assertIsNone(self.bow.shooting_mode)

    def test_independent_archers_get_the_hunt_events(self):
        self.bow.independent = True
        self.battle.order_fire("bow", "e")
        self.battle.order_fire("bow", "bow")
        self.assertEqual([code for code, *_ in self.queued()], [0x25, 0x24])


class FireAtTargetTests(SeamTestCase):
    def setUp(self):
        self.bow, self.enemy = shooter("bow", 1000, 1000), shooter("e", 1000, 1300, Side.ENEMY)
        self.make(self.bow, self.enemy)
        self.state = self.bus.unit_states["bow"]
        self.state.current_target = ("e", 0)

    def test_launches_from_the_posting_model_and_stamps_the_reload(self):
        origin = self.bow.model_positions()[3]
        self.bow.hidden = True
        self.assertTrue(self.call("bow", "FireAtTarget", event=Event(code=34, source="bow", model=3)))
        self.assertEqual([(p.x0, p.y0) for p in self.battle.projectiles], [origin])
        self.assertEqual(self.aims(), [(1000, 1300)])
        self.assertEqual((self.bow.reload_ticks, self.bow.hidden), (ranged.reload_time(self.bow) + 1, False))

    def test_no_event_launches_from_the_unit_centre(self):
        self.call("bow", "FireAtTarget")
        self.assertEqual([(p.x0, p.y0) for p in self.battle.projectiles], [(1000, 1000)])

    def test_flies_even_out_of_range_and_arc(self):
        self.enemy.x, self.enemy.y = 1000, -2000
        self.assertTrue(self.call("bow", "FireAtTarget"))
        self.assertEqual(self.aims(), [(1000, -2000)])

    def test_aim_at_point_wins_and_is_cleared_and_forgetting_drops_the_target(self):
        self.state.target_point, self.state.aim_at_point = (900.0, 1200.0), True
        self.state.unit_flags |= interpreter.CAST_ONLY_TARGET_FLAG
        self.call("bow", "FireAtTarget")
        self.assertEqual(self.aims(), [(900.0, 1200.0)])
        self.assertEqual((self.state.aim_at_point, self.state.current_target), (False, None))

    def test_dead_target_and_no_point_launch_nothing(self):
        self.enemy.models = 0
        self.assertFalse(self.call("bow", "FireAtTarget"))
        self.assertEqual(self.battle.projectiles, [])

    def test_a_non_shooter_class_fails(self):
        self.bow.unit_class, self.bow.hud_class = 1, "inf"
        self.assertFalse(self.call("bow", "FireAtTarget"))

    def test_full_pool_fails_without_stamping(self):
        for slot in range(32):
            self.battle.projectiles.append(ranged.Projectile("x", 1, 0, 0, 0, 0, 0, 0, 0, 3, 1, slot=slot))
        self.bow.reload_ticks = 0
        self.assertFalse(self.call("bow", "FireAtTarget"))
        self.assertEqual(self.bow.reload_ticks, 0)


class FireAt90Tests(SeamTestCase):
    """Unit at (1000, 1000) facing +Y with a bow (R 576 -> 518)."""

    def setUp(self):
        self.bow = shooter("bow", 1000, 1000)
        self.make(self.bow)
        self.state = self.bus.unit_states["bow"]

    def shot(self, point):
        self.battle.projectiles.clear()
        self.state.target_point = point
        return self.call("bow", "FireAt90PercentRange"), self.aims()

    def test_vectors(self):
        self.assertEqual(self.shot((1000.0, 2000.0)), (True, [(1000, 1518)]))
        self.assertEqual(self.shot((1300.0, 2000.0)), (True, [(1148, 1496)]))
        self.assertEqual(self.shot((2000.0, 1999.0)), (False, []))
        self.assertEqual(self.shot((1000.0, 1100.0)), (True, [(1000, 1518)]))

    def test_aim_at_point_is_ignored(self):
        target = shooter("t", 1000, 2000, Side.ENEMY)
        self.make(self.bow, target)
        self.state = self.bus.unit_states["bow"]
        self.state.current_target = ("t", 0)
        self.state.target_point, self.state.aim_at_point = (0.0, 0.0), True
        self.call("bow", "FireAt90PercentRange")
        self.assertEqual((self.aims(), self.state.aim_at_point), ([(1000, 1518)], True))


class NodeManningReadinessTests(SeamTestCase):
    def test_fire_at_node_queues_a_ground_fire_event(self):
        self.make(shooter("bow", 0, 0), nodes=[ScriptNode(0.0, 0.0)] * 17 + [ScriptNode(812.0, 1430.0)])
        self.assertTrue(self.call("bow", "FireAtNode", 17))
        self.assertEqual([(e.code, e.source, e.x, e.y) for e in self.bus.unit_states["bow"].event_queue],
                         [(0x21, None, 812, 1430)])

    def test_if_artillery_manned(self):
        gun = shooter("gun", 0, 0, code=11, models=3, cls="art", unit_class=4)
        self.make(gun, shooter("bow", 100, 0))
        self.bus.unit_states["gun"].tag = 0xABC8
        self.assertTrue(self.call("bow", "IfArtilleryManned", 0xABC8))
        gun.models = 1
        self.assertFalse(self.call("bow", "IfArtilleryManned", 0xABC8))
        gun.models, gun.machine_alive = 3, False
        self.assertFalse(self.call("gun", "IfArtilleryManned", 0xFFFF))
        self.assertFalse(self.call("bow", "IfArtilleryManned", -1 & 0xFFFF))  # self is not artillery

    def test_ready_to_fire_and_its_messages(self):
        gun = shooter("gun", 0, 0, code=11, models=3, cls="art", unit_class=4)
        self.make(gun)
        self.assertTrue(self.call("gun", "ReadyToFire", 0))
        gun.reload_ticks = 5
        self.assertFalse(self.call("gun", "ReadyToFire", 1))
        gun.reload_ticks, gun.machine_alive = 0, False
        self.assertFalse(self.call("gun", "ReadyToFire", 0))
        gun.machine_alive, gun.held = True, True
        self.assertFalse(self.call("gun", "ReadyToFire", 0))
        self.assertEqual([e.data["text_id"] for e in self.battle.events if e.kind == "message"], [2003, 2015])

    def test_stamp_reload_keeps_the_condition(self):
        bow = shooter("bow", 0, 0)
        self.make(bow)
        self.bus.unit_states["bow"].cond_flags = 1
        self.call("bow", "StampReload")
        self.assertEqual((bow.reload_ticks, bool(self.bus.unit_states["bow"].cond_flags)),
                         (ranged.reload_time(bow) + 1, True))


if __name__ == "__main__":
    unittest.main()
