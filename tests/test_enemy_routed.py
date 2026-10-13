"""Rout broadcasts and reactions: game_rules.md 'Opcode 0x53 in full' and
runaway_routers_broken.md 'What the charger does when its target routs'."""
import unittest

from whshr import behaviour, combat
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side
from tests.script_helpers import FakeDll, word


def handler(reaction):
    words = [word('PushPC'), word('GetEvent')]
    for code, body in [(15, reaction), (27, [word('TargetGone')]),
                       (25, [word('DropTarget'), word('SwitchScript'), 163])]:
        words += [word('CaseEvent'), code, *body, word('Break'), behaviour.BREAK_LABEL]
    return words + [behaviour.LABEL, word('ConsumeEvent'), word('LoopIfTrue'), word('ReturnInterrupt'), behaviour.END]


SCRIPTS = {
    100: [word('Wait'), behaviour.END],
    151: handler([word('EnemyRouted'), word('IfSwitchScriptHigh'), 164]),
    158: [word('MoveToTarget'), word('Wait'), behaviour.END],
    163: [word('Rally'), word('Yield'), word('Wait'), behaviour.END],
    164: [word('LeaveSharedGrid'), word('ReformToScriptRanks'), word('StartPursuit'), word('Wait'), behaviour.END],
}


class EnemyRoutedTests(unittest.TestCase):
    def setUp(self):
        self.router = Regiment('router', 'Router', 700, 500, 0, Side.PLAYER, models=4)
        self.unit = Regiment('enemy', 'Enemy', 200, 500, 128, Side.ENEMY, models=4)
        self.other = Regiment('other', 'Other', 800, 800, 0, Side.PLAYER, models=4)
        self.battle = Battle(1000, 1000, [self.router, self.unit, self.other], seed=1995,
                            boundaries=[{'status': ['bnd_ACTIVE', 'bnd_BATTLEEDGE'],
                                         'lines': [[0, 0, 1000, 0], [1000, 0, 1000, 1000],
                                                   [1000, 1000, 0, 1000], [0, 1000, 0, 0]]}],
                            script_dll=FakeDll(SCRIPTS), script_ids={'router': 100, 'enemy': 100, 'other': 100})
        self.state = self.battle.event_bus.unit_states['enemy']
        self.state.interrupt_script = 151
        self.state.current_target = ('router', 0)

    def react(self, source='router'):
        self.state.current_event = Event(code=15, source=source)
        self.state.cond_flags = True
        self.battle.interpreter.op_EnemyRouted(self.state, None, [], 'enemy', 0, self.battle.rng)
        return bool(self.state.cond_flags)

    def test_given_rout_when_started_then_only_enemy_side_hears_source(self):
        combat.start_rout(self.router, self.battle)
        self.assertEqual([(e.code, e.source) for e in self.state.event_queue], [(15, 'router')])
        for name in ('router', 'other'):
            self.assertFalse(self.battle.event_bus.unit_states[name].event_queue)
        self.assertFalse(self.unit.pursuing)

    def test_given_approach_when_target_routs_then_target_is_dropped_and_walk_stops(self):
        self.state.script_id = 158
        self.battle.tick()
        self.assertTrue(self.unit.moving)
        combat.start_rout(self.router, self.battle)
        self.battle.tick()
        self.assertIsNone(self.state.current_target)
        self.assertFalse(self.unit.moving)
        self.assertFalse(self.unit.pursuing)
        self.assertEqual(self.state.script_id, 163)

    def test_given_charge_when_target_routs_then_script_starts_pursuit(self):
        self.unit.attack_target = 'router'
        combat.start_rout(self.router, self.battle)
        self.battle.tick()
        self.assertTrue(self.unit.pursuing)
        self.assertFalse(self.unit.charging)
        self.assertEqual(self.unit.attack_target, 'router')
        self.assertEqual(len([e for e in self.battle.events if e.kind == 'pursuit_start']), 1)

    def test_given_another_source_or_no_target_then_no_reaction(self):
        self.router.routing = True
        self.unit.attack_target = 'router'
        self.assertFalse(self.react('other'))
        self.state.current_target = None
        self.assertFalse(self.react())
        self.assertFalse(self.state.event_queue)

    def test_given_busy_wizard_then_no_reaction(self):
        self.unit.unit_class = 5
        self.state.channelling = True
        self.unit.attack_target = 'router'
        self.assertFalse(self.react())
        self.assertFalse(self.state.event_queue)

    def test_given_free_charge_at_current_target_then_pursuit_condition(self):
        self.unit.free_charging = True
        self.assertTrue(self.react())

    def test_given_melee_with_another_enemy_then_switch_and_unpair_only_router(self):
        for unit in (self.unit, self.other):
            unit.in_melee, unit.melee_group = True, 'fight'
        self.unit.model_positions()
        self.unit.melee_models[0].opponent = ('router', 0)
        self.unit.melee_models[1].opponent = ('other', 0)
        self.assertFalse(self.react())
        self.assertEqual(self.state.current_target, ('other', 0))
        self.assertIsNone(self.unit.melee_models[0].opponent)
        self.assertEqual(self.unit.melee_models[1].opponent, ('other', 0))

    def test_given_melee_without_another_enemy_then_pursuit_condition(self):
        self.unit.in_melee, self.unit.melee_group = True, 'fight'
        self.assertTrue(self.react())

    def test_given_unpaired_other_enemy_then_melee_still_selects_pursuit(self):
        for unit in (self.unit, self.other):
            unit.in_melee, unit.melee_group = True, 'fight'
        self.assertTrue(self.react())

    def test_given_non_target_melee_opponent_when_rout_starts_then_no_engine_pursuit(self):
        self.state.current_target = ('other', 0)
        for unit in (self.unit, self.router):
            unit.in_melee, unit.melee_group = True, 'fight'
        combat.start_rout(self.router, self.battle)
        self.battle.interpreter.run('enemy', self.state, 0, self.battle.rng)
        self.assertFalse(self.unit.pursuing)
        self.assertEqual(self.state.current_target, ('other', 0))

    def test_given_anchored_router_then_no_rout_broadcast(self):
        self.router.hud_class = 'art'
        combat.start_rout(self.router, self.battle)
        self.assertFalse(self.router.routing)
        self.assertFalse(self.state.event_queue)

    def test_given_held_pursuer_then_start_pursuit_does_nothing(self):
        self.unit.held = True
        self.battle.interpreter.op_StartPursuit(self.state, None, [], 'enemy', 0, self.battle.rng)
        self.assertFalse(self.unit.pursuing)

    def test_given_class_handler_then_rout_uses_its_alternative_to_pursuit(self):
        for class_handler, destination in ((155, 148), (156, 127)):
            for independent in (False, True):
                with self.subTest(handler=class_handler, independent=independent):
                    self.setUp()
                    # Synthetic form of the published handlers, not an installation fixture.
                    reaction = [word('EnemyRouted'), word('If'), word('TestUnitFlags'), 0x8000000,
                                word('If'), word('IfSwitchScriptHigh'), destination, word('Else'),
                                word('SendEventSelf'), 25, word('EndIf'), word('EndIf')]
                    scripts = {**SCRIPTS, class_handler: handler(reaction),
                               destination: [word('LeaveSharedGrid'), word('Rally'), word('Wait'), behaviour.END]}
                    self.state.script_dll = FakeDll(scripts)
                    self.state.interrupt_script = class_handler
                    self.unit.independent = independent
                    self.unit.in_melee, self.unit.melee_group = True, 'fight'
                    self.unit.missile_range = 120
                    combat.start_rout(self.router, self.battle)
                    self.battle.interpreter.run('enemy', self.state, 0, self.battle.rng)
                    self.assertFalse(self.unit.pursuing)
                    self.assertEqual(self.state.script_id, destination if independent else 163)
                    if not independent:
                        self.assertIsNone(self.state.current_target)

    def test_given_static_handler_then_rout_unbraces_without_pursuit_or_restart(self):
        reaction = [word('EnemyRoutedStatic'), word('If'), word('LeaveSharedGrid'), word('Rally'), word('EndIf')]
        self.state.script_dll = FakeDll({**SCRIPTS, 154: handler(reaction)})
        self.state.interrupt_script = 154
        self.unit.braced = True
        self.unit.hud_class = 'art'
        combat.start_rout(self.router, self.battle)
        self.battle.interpreter.run('enemy', self.state, 0, self.battle.rng)
        self.assertFalse(self.unit.braced)
        self.assertFalse(self.unit.pursuing)
        self.assertEqual(self.state.script_id, 100)

    def test_given_two_full_approachers_when_cavalry_routs_then_both_drop_it_and_reform(self):
        first = Regiment('slaves1', 'Slaves 1', 200, 400, 128, Side.ENEMY, models=26, ranks=4)
        second = Regiment('slaves2', 'Slaves 2', 200, 600, 128, Side.ENEMY, models=27, ranks=4)
        battle = Battle(1000, 1000, [first, second, self.router], seed=1995,
                        script_dll=FakeDll(SCRIPTS),
                        script_ids={'slaves1': 158, 'slaves2': 158, 'router': 100})
        states = [battle.event_bus.unit_states[unit.identifier] for unit in (first, second)]
        for state in states:
            state.current_target = ('router', 0)
            state.interrupt_script = 151
        for unit, state in zip((first, second), states):
            battle.interpreter.run(unit.identifier, state, 0, battle.rng)
            self.assertTrue(unit.moving)
        combat.start_rout(self.router, battle)
        for unit, state in zip((first, second), states):
            battle.interpreter.run(unit.identifier, state, 1, battle.rng)
            self.assertIsNone(state.current_target)
            self.assertFalse(unit.moving)
            self.assertTrue(unit.reforming)
            self.assertFalse(unit.pursuing)
            self.assertEqual(state.script_id, 163)

    def test_given_rout_request_then_enemies_wait_until_flight_actually_starts(self):
        combat.request_rout(self.battle, self.router)
        self.assertFalse(self.router.routing)
        self.assertFalse(self.state.event_queue)
        router_state = self.battle.event_bus.unit_states['router']
        self.assertEqual([e.code for e in router_state.event_queue], [12])
        self.battle.interpreter.op_FleeAhead(router_state, None, [], 'router', 0, self.battle.rng)
        self.assertTrue(self.router.routing)
        self.assertEqual([(e.code, e.source) for e in self.state.event_queue], [(15, 'router')])
