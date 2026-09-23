"""Tests for the opcodes landed in Phase 2 item 2 (notes/interpreter_gameplay_integration.md):
target selection (AttackNearest* family), WaitUntilUnitFlags, the SwitchScript priority family,
and the morale-reaction trio (RoutAllowed/FleeFromTarget/FearWhenCharged).

These were picked because they are the specific opcodes the research doc verified as missing but
actually used by the BF003/BF005/BF010 walkthroughs -- see that document's "Verified: Bytecode
Actually Disassembled" section for the real script excerpts these opcodes come from.
"""

import unittest
from whshr import interpreter
from whshr.engine import Battle, Regiment


class TargetSelectionTests(unittest.TestCase):
    """AttackNearestEnemy family and the TargetNearestEnemy fix (it was previously a stub)."""

    def setUp(self):
        self.near = Regiment("player_near", "Near", 110, 100, 0, True, models=10, ranks=2)
        self.far = Regiment("player_far", "Far", 500, 100, 0, True, models=10, ranks=2)
        self.enemy = Regiment("enemy_1", "Enemy", 100, 100, 0, False, models=10, ranks=2)
        self.battle = Battle(1000, 1000, [self.near, self.far, self.enemy], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_target_nearest_enemy_actually_finds_the_nearest_one(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_TargetNearestEnemy(state, None, [], "enemy_1", 0, None)
        self.assertEqual(state.current_target, ("player_near", 0))
        self.assertEqual(state.cond_flags, 1)

    def test_target_nearest_enemy_fails_gracefully_with_no_enemies(self):
        battle = Battle(1000, 1000, [self.enemy], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["enemy_1"]
        interp.op_TargetNearestEnemy(state, None, [], "enemy_1", 0, None)
        self.assertIsNone(state.current_target)
        self.assertEqual(state.cond_flags, 0)

    def test_attack_nearest_enemy_sets_both_current_target_and_attack_target(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNearestEnemy(state, None, [], "enemy_1", 0, None)
        self.assertEqual(state.current_target, ("player_near", 0))
        self.assertEqual(self.enemy.attack_target, "player_near")
        self.assertEqual(state.cond_flags, 1)

    def test_attack_nearest_visible_enemy_behaves_like_attack_nearest_enemy(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNearestVisibleEnemy(state, None, [], "enemy_1", 0, None)
        self.assertEqual(self.enemy.attack_target, "player_near")

    def test_attack_nearest_flag40_unit_falls_back_to_nearest_enemy(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNearestFlag40Unit(state, None, [], "enemy_1", 0, None)
        self.assertEqual(self.enemy.attack_target, "player_near")

    def test_attack_nth_nearest_enemy_picks_the_second_closest(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNthNearestEnemy(state, 2, [], "enemy_1", 0, None)
        self.assertEqual(self.enemy.attack_target, "player_far")

    def test_attack_nth_nearest_enemy_fails_when_fewer_than_n_enemies_exist(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNthNearestEnemy(state, 5, [], "enemy_1", 0, None)
        self.assertEqual(state.cond_flags, 0)
        self.assertIsNone(self.enemy.attack_target)

    def test_attack_nearest_enemy_ignores_destroyed_regiments(self):
        self.near.models = 0  # destroyed: no longer .active
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNearestEnemy(state, None, [], "enemy_1", 0, None)
        self.assertEqual(self.enemy.attack_target, "player_far")


class WaitUntilUnitFlagsTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, False, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["t"]

    def test_blocks_yielding_while_flag_unset(self):
        result = self.interp.op_WaitUntilUnitFlags(self.state, 16, [], "t", 0, None)
        self.assertEqual(result, self.state.pc)  # same PC: still blocked
        self.assertTrue(self.interp._should_yield)

    def test_falls_through_once_flag_is_set(self):
        self.state.unit_flags = 16
        self.interp._should_yield = False
        result = self.interp.op_WaitUntilUnitFlags(self.state, 16, [], "t", 0, None)
        self.assertEqual(result, self.state.pc + 1)
        self.assertFalse(self.interp._should_yield)


class WaitForBattleStartYieldTests(unittest.TestCase):
    """Regression test: op_WaitForBattleStart used to block without setting _should_yield, so
    ScriptInterpreter.run's dispatch loop re-executed it up to max_iterations (10000) times in a
    single tick instead of properly ending the tick. Confirmed from a real BF003 trace: every unit
    burned ~9993-9997 identical WaitForBattleStart dispatches on tick 0 alone."""

    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, False, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["t"]

    def test_blocking_at_tick_zero_sets_should_yield(self):
        self.interp._should_yield = False
        result = self.interp.op_WaitForBattleStart(self.state, None, [], "t", 0, None)
        self.assertEqual(result, self.state.pc)  # same pc: still blocked
        self.assertTrue(self.interp._should_yield)

    def test_resuming_at_a_later_tick_does_not_yield(self):
        self.interp._should_yield = False
        result = self.interp.op_WaitForBattleStart(self.state, None, [], "t", 1, None)
        self.assertEqual(result, self.state.pc + 1)
        self.assertFalse(self.interp._should_yield)


class LoopPeeksNotPopsTests(unittest.TestCase):
    """Regression test: op_Loop popped the return stack (like a one-shot gosub return) instead of
    peeking it (like its siblings LoopIfTrue/LoopIfFalse already do correctly). PushPC runs once
    before a loop body; Loop is meant to jump back to it every iteration ("while true"), so popping
    destroyed the loop anchor after exactly one repetition. Confirmed as the real cause of NPC
    peasant regiments (BF003) scattering exactly twice, then freezing in place for the rest of the
    battle: PushPC/ScatterModelsToNode/SetWait/Wait/Loop is precisely this idiom."""

    def setUp(self):
        self.interp = interpreter.ScriptInterpreter(None, None, None)

    def test_loop_jumps_back_without_consuming_the_stack_entry(self):
        state = interpreter.UnitScriptState()
        state.pc = 10
        self.interp.op_PushPC(state, None, [], "t", 0, None)  # pushes (11,)
        self.assertEqual(len(state.return_stack), 1)

        state.pc = 20
        result = self.interp.op_Loop(state, None, [], "t", 0, None)
        self.assertEqual(result, 11)
        self.assertEqual(len(state.return_stack), 1)  # still there

    def test_loop_can_jump_back_more_than_once(self):
        """The actual bug: a second Loop call after the first must still jump back, not fall
        through to pc + 1 because the stack entry was already consumed."""
        state = interpreter.UnitScriptState()
        state.pc = 10
        self.interp.op_PushPC(state, None, [], "t", 0, None)  # pushes (11,)

        state.pc = 20
        first = self.interp.op_Loop(state, None, [], "t", 0, None)
        state.pc = 20  # simulate the loop body running again and reaching Loop a second time
        second = self.interp.op_Loop(state, None, [], "t", 0, None)

        self.assertEqual(first, 11)
        self.assertEqual(second, 11)  # previously: 21 (fell through, stack was already empty)


class SwitchScriptPriorityTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, False, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_if_switch_script_only_fills_an_empty_pending_slot(self):
        state = interpreter.UnitScriptState()
        self.interp.op_IfSwitchScript(state, 200, [], "t", 0, None)
        self.assertEqual(state.pending_switch, 200)
        self.interp.op_IfSwitchScript(state, 201, [], "t", 0, None)
        self.assertEqual(state.pending_switch, 200)  # unchanged: slot already filled

    def test_if_switch_script_high_always_overrides(self):
        state = interpreter.UnitScriptState()
        state.pending_switch = 200
        self.interp.op_IfSwitchScriptHigh(state, 164, [], "t", 0, None)
        self.assertEqual(state.pending_switch, 164)

    def test_if_not_switch_script_skips_when_already_running_that_script(self):
        state = interpreter.UnitScriptState(script_id=159)
        self.interp.op_IfNotSwitchScript(state, 159, [], "t", 0, None)
        self.assertIsNone(state.pending_switch)

    def test_if_not_switch_script_switches_when_running_a_different_script(self):
        state = interpreter.UnitScriptState(script_id=100)
        self.interp.op_IfNotSwitchScript(state, 159, [], "t", 0, None)
        self.assertEqual(state.pending_switch, 159)


class MoraleReactionTests(unittest.TestCase):
    def setUp(self):
        self.target = Regiment("target", "Target", 100, 100, 0, False, models=10, ranks=2, leadership=7)
        self.charger = Regiment("charger", "Charger", 110, 100, 0, True, models=10, ranks=2)
        self.battle = Battle(500, 500, [self.target, self.charger], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_rout_allowed_true_for_an_active_non_routing_unit(self):
        state = self.battle.event_bus.unit_states["target"]
        self.interp.op_RoutAllowed(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 1)

    def test_rout_allowed_false_once_already_routing(self):
        self.target.routing = True
        state = self.battle.event_bus.unit_states["target"]
        self.interp.op_RoutAllowed(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 0)

    def test_rout_allowed_false_for_cant_break(self):
        stubborn = Regiment("stubborn", "S", 0, 0, 0, False, models=5, ranks=1,
                             psychology=frozenset({"CantBreak"}))
        battle = Battle(500, 500, [stubborn], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["stubborn"]
        interp.op_RoutAllowed(state, None, [], "stubborn", 0, None)
        self.assertEqual(state.cond_flags, 0)

    def test_flee_from_target_starts_a_rout(self):
        state = self.battle.event_bus.unit_states["target"]
        self.interp.op_FleeFromTarget(state, None, [], "target", 0, None)
        self.assertTrue(self.target.routing)

    def test_fear_when_charged_with_no_event_source_is_a_safe_no_op(self):
        state = self.battle.event_bus.unit_states["target"]
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 0)

    def test_fear_when_charged_terror_always_triggers_without_immunity(self):
        self.charger.psychology = frozenset({"CauseTerror"})
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 1)

    def test_fear_when_charged_terror_is_ignored_with_frenzy(self):
        self.charger.psychology = frozenset({"CauseTerror"})
        self.target.psychology = frozenset({"Frenzy"})
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 0)

    def test_fear_when_charged_fear_is_ignored_with_cant_break(self):
        self.charger.psychology = frozenset({"CauseFear"})
        self.target.psychology = frozenset({"CantBreak"})
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 0)

    def test_fear_when_charged_fear_runs_a_leadership_test(self):
        self.charger.psychology = frozenset({"CauseFear"})
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        # Deterministic seed: just confirm it runs and produces a boolean-like cond_flags result,
        # without asserting a specific roll outcome (that belongs to whshr.combat's own tests).
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, self.battle.rng)
        self.assertIn(state.cond_flags, (0, 1))


class EventSourceIsARegimentIdentifierTests(unittest.TestCase):
    """Regression test for the Event.source bug: it used to be int(unit_id) if unit_id.isdigit()
    else 0, which was 0 for every real regiment identifier (e.g. "Goblin_Stickers")."""

    def setUp(self):
        self.sender = Regiment("Goblin_Stickers", "Stickers", 0, 0, 0, False, models=5, ranks=1)
        self.receiver = Regiment("Goblin_Wolfriders", "Wolfriders", 0, 0, 0, False, models=5, ranks=1)
        self.battle = Battle(500, 500, [self.sender, self.receiver], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_send_event_to_own_side_carries_the_real_sender_identifier(self):
        state = self.battle.event_bus.unit_states["Goblin_Stickers"]
        self.interp.op_SendEventToOwnSide(state, 0x11, [], "Goblin_Stickers", 0, None)
        received = self.battle.event_bus.unit_states["Goblin_Wolfriders"].event_queue[0]
        self.assertEqual(received.source, "Goblin_Stickers")

    def test_take_event_target_resolves_to_a_real_regiment(self):
        state = self.battle.event_bus.unit_states["Goblin_Wolfriders"]
        state.current_event = interpreter.Event(code=4, source="Goblin_Stickers")
        self.interp.op_TakeEventTarget(state, None, [], "Goblin_Wolfriders", 0, None)
        self.assertEqual(state.current_target, ("Goblin_Stickers", 0))
        self.assertEqual(state.cond_flags, 1)


if __name__ == "__main__":
    unittest.main()
