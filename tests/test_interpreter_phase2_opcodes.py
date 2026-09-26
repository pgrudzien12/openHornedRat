"""Tests for the opcodes landed in Phase 2 item 2 (notes/interpreter_gameplay_integration.md):
target selection (AttackNearest* family), WaitUntilUnitFlags, the SwitchScript priority family,
and the morale-reaction trio (RoutAllowed/FleeFromTarget/FearWhenCharged).

These were picked because they are the specific opcodes the research doc verified as missing but
actually used by the BF003/BF005/BF010 walkthroughs -- see that document's "Verified: Bytecode
Actually Disassembled" section for the real script excerpts these opcodes come from.
"""

import math
import unittest
import unittest.mock
from whshr import interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class TargetSelectionTests(unittest.TestCase):
    """AttackNearestEnemy family and the TargetNearestEnemy fix (it was previously a stub)."""

    def setUp(self):
        self.near = Regiment("player_near", "Near", 110, 100, 0, Side.PLAYER, models=10, ranks=2)
        self.far = Regiment("player_far", "Far", 500, 100, 0, Side.PLAYER, models=10, ranks=2)
        self.enemy = Regiment("enemy_1", "Enemy", 100, 100, 0, Side.ENEMY, models=10, ranks=2)
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

    def test_attack_nearest_flag40_unit_targets_the_neutral_side_specifically(self):
        # notes/neutral_units.md: side flag 0x40 is the neutral/NPC side, now a real third Side value
        # rather than folded into "enemy" -- this opcode must find a neutral regiment, not just the
        # nearest non-self side, and must not find one when there isn't one on the field.
        peasant = Regiment("peasant_1", "Peasants", 105, 100, 0, Side.NEUTRAL, models=8, ranks=1)
        battle = Battle(1000, 1000, [self.near, self.far, self.enemy, peasant], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["enemy_1"]

        interp.op_AttackNearestFlag40Unit(state, None, [], "enemy_1", 0, None)

        self.assertEqual(self.enemy.attack_target, "peasant_1")

    def test_attack_nearest_flag40_unit_fails_gracefully_with_no_neutral_units(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        self.interp.op_AttackNearestFlag40Unit(state, None, [], "enemy_1", 0, None)
        self.assertIsNone(self.enemy.attack_target)
        self.assertEqual(state.cond_flags, 0)

    def test_attack_nth_nearest_enemy_picks_the_second_closest(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        state.threat_range = 500  # the far regiment is 400 away, beyond the fallback range
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
        state.threat_range = 500  # the far regiment is 400 away, beyond the fallback range
        self.interp.op_AttackNearestEnemy(state, None, [], "enemy_1", 0, None)
        self.assertEqual(self.enemy.attack_target, "player_far")


class WaitUntilUnitFlagsTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, Side.ENEMY, models=5, ranks=1)], seed=1995)
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
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, Side.ENEMY, models=5, ranks=1)], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["t"]

    def test_blocking_at_tick_zero_sets_should_yield(self):
        self.battle.phase = "deployment"
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
        self.battle = Battle(500, 500, [Regiment("t", "T", 0, 0, 0, Side.ENEMY, models=5, ranks=1)], seed=1995)
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
        self.target = Regiment("target", "Target", 100, 100, 0, Side.ENEMY, models=10, ranks=2, leadership=7)
        self.charger = Regiment("charger", "Charger", 110, 100, 0, Side.PLAYER, models=10, ranks=2)
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
        stubborn = Regiment("stubborn", "S", 0, 0, 0, Side.ENEMY, models=5, ranks=1,
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

    def test_fear_when_charged_pass_braces_the_unit_against_the_charger(self):
        # game_rules.md "Braced": no fear/terror rule applies here, so the test passes outright and
        # the target halts, dropping any order in flight, and records the charger.
        self.target.target_x, self.target.target_y = 400.0, 400.0
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 0)
        self.assertTrue(self.target.braced)
        self.assertEqual(self.target.braced_target, "charger")
        self.assertIsNone(self.target.target_x)
        self.assertIsNone(self.target.target_y)
        self.assertIsNone(self.target.attack_target)

    def test_fear_when_charged_pass_turns_to_face_the_charger(self):
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        # charger sits due east (+x) of target -- 0 = north/+Y, clockwise, so east is 128.
        self.assertEqual(self.target.direction, 128)

    def test_fear_when_charged_fail_does_not_brace(self):
        self.charger.psychology = frozenset({"CauseTerror"})
        state = self.battle.event_bus.unit_states["target"]
        state.current_event = interpreter.Event(code=0x07, source="charger")
        self.interp.op_FearWhenCharged(state, None, [], "target", 0, None)
        self.assertEqual(state.cond_flags, 1)
        self.assertFalse(self.target.braced)
        self.assertIsNone(self.target.braced_target)


class EventSourceIsARegimentIdentifierTests(unittest.TestCase):
    """Regression test for the Event.source bug: it used to be int(unit_id) if unit_id.isdigit()
    else 0, which was 0 for every real regiment identifier (e.g. "Goblin_Stickers")."""

    def setUp(self):
        self.sender = Regiment("Goblin_Stickers", "Stickers", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
        self.receiver = Regiment("Goblin_Wolfriders", "Wolfriders", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
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


class EventHandlerFrameTests(unittest.TestCase):
    """The handler frame `GetEvent; ...; ConsumeEvent; LoopIfTrue; ReturnInterrupt` must drain the queue
    and then fall through, even when a persistent condition bit (the event-17 gate, 16) is set.

    Regression: the gate bit shared a register with the loop result, so the frame looped forever,
    every unit spun to the iteration cap (BF001: 2-3 FPS) and never left its handler (reinforcements
    and Sleaquit never woke).
    """

    def setUp(self):
        self.interp = interpreter.ScriptInterpreter(None, None, None)
        self.state = interpreter.UnitScriptState()
        self.state.return_stack.append((3,))

    def _end_of_pass(self):
        self.interp.op_GetEvent(self.state, None, [], "t", 0, None)
        return self.interp.op_LoopIfTrue(self.state, None, [], "t", 0, None)

    def test_empty_queue_falls_through_despite_persistent_bit(self):
        self.interp.op_SetCondFlags(self.state, 16, [], "t", 0, None)
        self.assertEqual(self._end_of_pass(), self.state.pc + 1)

    def test_queued_event_loops_back(self):
        self.state.event_queue.append(interpreter.Event(code=7))
        self.assertEqual(self._end_of_pass(), 3)

    def test_persistent_bits_survive_tests_and_are_testable(self):
        self.interp.op_SetCondFlags(self.state, 16, [], "t", 0, None)
        self.interp.op_GetEvent(self.state, None, [], "t", 0, None)
        self.interp.op_TestCondFlags(self.state, 16, [], "t", 0, None)
        self.assertTrue(self.state.cond_flags)
        self.interp.op_ClearCondFlags(self.state, 16, [], "t", 0, None)
        self.interp.op_TestCondFlags(self.state, 16, [], "t", 0, None)
        self.assertFalse(self.state.cond_flags)


class AttackSearchRangeTests(unittest.TestCase):
    """`Attack*Enemy` only sees enemies within the unit's own SetThreatRange (300 if it set none), so a
    script's `AttackNearestEnemy; ...IfTrue; LoopIfFalse` gate waits until an enemy comes close (BF001's
    Hiln's Guard, whose event 17 wakes the reinforcements)."""

    def _attack(self, distance, threat_range):
        guard = Regiment("guard", "Guard", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
        player = Regiment("player", "Player", distance, 0, 0, Side.PLAYER, models=5, ranks=1)
        battle = Battle(2000, 2000, [guard, player], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["guard"]
        state.threat_range = threat_range
        interp.op_AttackNearestEnemy(state, None, [], "guard", 0, None)
        return state.cond_flags, guard.attack_target

    def test_enemy_inside_the_units_own_range_is_attacked(self):
        self.assertEqual(self._attack(distance=200, threat_range=240), (1, "player"))

    def test_enemy_beyond_the_units_own_range_is_not(self):
        self.assertEqual(self._attack(distance=300, threat_range=240), (0, None))

    def test_a_unit_without_a_threat_range_falls_back_to_the_default(self):
        self.assertEqual(self._attack(distance=290, threat_range=0), (1, "player"))
        self.assertEqual(self._attack(distance=310, threat_range=0), (0, None))

    def test_distance_is_octagonal(self):
        # 200 along each axis is 300 octagonal (200 + 100), though only 283 Euclidean.
        guard = Regiment("guard", "Guard", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
        player = Regiment("player", "Player", 200, 200, 0, Side.PLAYER, models=5, ranks=1)
        battle = Battle(2000, 2000, [guard, player], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["guard"]
        state.threat_range = 290
        interp.op_AttackNearestEnemy(state, None, [], "guard", 0, None)
        self.assertEqual(state.cond_flags, 0)


class MeleeFlagMirrorTests(unittest.TestCase):
    """Script unit flag 0x200 ("in melee") follows the regiment: Otto Hiln's `TestUnitFlags 512;
    KillAllModels` and the wizards' "no casting while engaged" both read it."""

    def test_flag_follows_in_melee(self):
        unit = Regiment("u", "U", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
        battle = Battle(500, 500, [unit], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["u"]
        unit.in_melee = True
        interp._mirror_engine_flags("u", state)
        self.assertTrue(state.unit_flags & interpreter.IN_MELEE_FLAG)
        unit.in_melee = False
        interp._mirror_engine_flags("u", state)
        self.assertFalse(state.unit_flags & interpreter.IN_MELEE_FLAG)

    def test_other_flags_are_left_alone(self):
        unit = Regiment("u", "U", 0, 0, 0, Side.ENEMY, models=5, ranks=1)
        battle = Battle(500, 500, [unit], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["u"]
        state.unit_flags = interpreter.ARRIVED_FLAG
        interp._mirror_engine_flags("u", state)
        self.assertEqual(state.unit_flags, interpreter.ARRIVED_FLAG)


class ScriptedTargetAndFlightOpcodeTests(unittest.TestCase):
    """notes/game_rules.md, "Scripted target and flight opcodes"."""

    def setUp(self):
        self.unit = Regiment("u", "U", 500, 500, 100, Side.ENEMY, models=6, ranks=2, speed_per_tick=0.0)
        self.foe = Regiment("foe", "Foe", 500, 600, 0, Side.PLAYER, models=6, ranks=2, speed_per_tick=0.0)
        self.battle = Battle(2000, 2000, [self.unit, self.foe], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["u"]

    def _run(self, name, *args):
        return getattr(self.interp, "op_" + name)(self.state, None, [], "u", 0, self.battle.rng)

    # DropTarget
    def test_drop_target_clears_target_and_bracing_and_is_true(self):
        self.unit.attack_target = "foe"
        self.state.current_target = ("foe", 0)
        self.unit.braced, self.unit.braced_target = True, "foe"
        self._run("DropTarget")
        self.assertIsNone(self.unit.attack_target)
        self.assertIsNone(self.state.current_target)
        self.assertFalse(self.unit.braced)
        self.assertEqual(self.state.cond_flags, 1)

    def test_drop_target_without_a_target_does_nothing_and_is_false(self):
        self._run("DropTarget")
        self.assertEqual(self.state.cond_flags, 0)

    def test_drop_target_on_a_broken_unit_does_nothing_and_is_false(self):
        self.unit.attack_target = "foe"
        self.unit.routing = True
        self._run("DropTarget")
        self.assertEqual(self.unit.attack_target, "foe")
        self.assertEqual(self.state.cond_flags, 0)

    def test_drop_target_does_not_leave_a_melee(self):
        self.unit.attack_target = "foe"
        self.unit.in_melee, self.unit.melee_group = True, "g"
        self._run("DropTarget")
        self.assertTrue(self.unit.in_melee)
        self.assertEqual(self.unit.melee_group, "g")

    # FleeAhead
    def test_flee_ahead_breaks_the_unit_and_runs_along_its_facing(self):
        self.unit.attack_target = "foe"
        facing = self.unit.direction
        self._run("FleeAhead")
        self.assertTrue(self.unit.routing)
        self.assertIsNone(self.unit.attack_target)
        self.assertEqual(self.unit.direction, facing)
        self.assertEqual(self.state.cond_flags, 1)
        angle = facing * math.tau / 512
        bearing = math.atan2(self.unit.flee_x - self.unit.x, self.unit.flee_y - self.unit.y)
        self.assertAlmostEqual(bearing, math.atan2(math.sin(angle), math.cos(angle)), places=3)

    def test_flee_ahead_ignores_cant_break(self):
        self.unit.psychology = frozenset({"CantBreak"})
        self._run("FleeAhead")
        self.assertTrue(self.unit.routing)

    def test_flee_ahead_is_refused_by_an_anchored_war_machine_but_clears_its_target(self):
        self.unit.anchor_cleared = False
        with unittest.mock.patch.object(Regiment, "anchored", new_callable=unittest.mock.PropertyMock, return_value=True):
            self.unit.attack_target = "foe"
            self._run("FleeAhead")
        self.assertFalse(self.unit.routing)
        self.assertIsNone(self.unit.attack_target)

    def test_flee_ahead_alerts_the_enemy_side_that_it_routed(self):
        self._run("FleeAhead")
        self.assertTrue(any(e.kind == "rout_start" for e in self.battle.events))

    # StoreEventInfo
    def test_store_event_info_remembers_sender_and_code_and_overwrites(self):
        self.state.current_event = interpreter.Event(code=7, source="foe")
        self._run("StoreEventInfo")
        self.assertEqual(self.state.remembered_event, ("foe", 7))
        self.state.current_event = interpreter.Event(code=9, source="other")
        self._run("StoreEventInfo")
        self.assertEqual(self.state.remembered_event, ("other", 9))

    def test_the_remembered_event_outlives_the_event(self):
        self.state.current_event = interpreter.Event(code=7, source="foe")
        self._run("StoreEventInfo")
        self.state.current_event = interpreter.Event()
        self.assertEqual(self.state.remembered_event, ("foe", 7))

    # FaceModelsToTarget
    def test_face_models_with_no_target_does_nothing_and_is_false(self):
        self._run("FaceModelsToTarget")
        self.assertEqual(self.state.cond_flags, 0)

    def test_face_models_turns_resting_models_once_then_reports_done(self):
        self.unit.attack_target = "foe"
        facing = self.unit.direction
        self._run("FaceModelsToTarget")
        self.assertEqual(self.state.cond_flags, 1)
        for model in self.unit.melee_models:
            self.assertEqual((model.heading_x, model.heading_y), (0.0, 1.0))  # foe is straight ahead in y
        self._run("FaceModelsToTarget")
        self.assertEqual(self.state.cond_flags, 0)
        self.assertEqual(self.unit.direction, facing)  # the regiment itself does not turn

    def test_face_models_leaves_walking_models_alone_and_reports_not_finished(self):
        self.unit.attack_target = "foe"
        self.unit.model_positions()
        walker = self.unit.melee_models[0]
        walker.at_rest = False
        self._run("FaceModelsToTarget")
        self.assertEqual(self.state.cond_flags, 1)
        self.assertEqual((walker.heading_x, walker.heading_y), (0.0, 0.0))


class OpponentGoneEventTests(unittest.TestCase):
    """A unit whose opponent dies leaves the fight and gets event 0x19 "opponent gone" (game_rules.md event
    table); BF001's assassin runs off on it. A routing opponent is not gone: the rout event decides."""

    def _duel(self):
        killer = Regiment("killer", "K", 0, 0, 0, Side.ENEMY, models=1, ranks=1, speed_per_tick=0.0)
        victim = Regiment("victim", "V", 0, 6, 0, Side.PLAYER, models=1, ranks=1, speed_per_tick=0.0)
        battle = Battle(500, 500, [killer, victim], seed=1995)
        battle.tick()
        self.assertTrue(killer.in_melee)
        battle.event_bus.unit_states["killer"].event_queue.clear()
        return battle, killer, victim

    def test_a_dead_opponent_sends_event_0x19(self):
        battle, killer, victim = self._duel()
        victim.models = 0
        battle.tick()
        codes = [e.code for e in battle.event_bus.unit_states["killer"].event_queue]
        self.assertIn(0x19, codes)

    def test_a_routing_opponent_does_not(self):
        battle, killer, victim = self._duel()
        victim.routing = True
        battle.tick()
        codes = [e.code for e in battle.event_bus.unit_states["killer"].event_queue]
        self.assertNotIn(0x19, codes)


class BreakJumpsToItsLabelTests(unittest.TestCase):
    """`Break` (operand 0x1ABC) jumps to the next 0x0ABC label, so a matched `CaseEvent` body skips the rest
    of the chain and the default handler after it (behaviour.py header)."""

    LABEL, BREAK = 0x0ABC, 0x1ABC

    def _interp(self):
        return interpreter.ScriptInterpreter(None, None, None)

    def test_break_lands_on_the_next_label_word(self):
        words = [0x6B, self.BREAK, 0x11, 153, self.LABEL, 0x69]  # Break; GosubScript 153; L: ConsumeEvent
        state = interpreter.UnitScriptState()
        state.pc = 0
        self.assertEqual(self._interp().op_Break(state, self.BREAK, words, "t", 0, None), 4)

    def test_break_without_a_label_falls_through(self):
        state = interpreter.UnitScriptState()
        state.pc = 0
        self.assertEqual(self._interp().op_Break(state, self.BREAK, [0x6B, self.BREAK, 0x69], "t", 0, None), 2)


class NestedLoopStackTests(unittest.TestCase):
    """A conditional loop that ends drops its PushPC entry, so an enclosing `Loop` returns to its own start.
    BF001's patrol scripts nest `PushPC; ..; PushPC; ..; LoopIfFalse; ..; Loop`: with the inner entry left
    behind, `Loop` re-entered the inner wait forever and the patrol never turned round."""

    def setUp(self):
        self.interp = interpreter.ScriptInterpreter(None, None, None)
        self.state = interpreter.UnitScriptState()

    def _push(self, at):
        self.state.pc = at - 1
        self.interp.op_PushPC(self.state, None, [], "t", 0, None)

    def test_a_finished_conditional_loop_pops_its_entry_so_the_outer_loop_returns_to_the_outer_start(self):
        self._push(10)   # outer loop start = 10
        self._push(20)   # inner loop start = 20
        self.state.pc, self.state.cond_flags = 30, 1  # LoopIfFalse with a true condition: the loop ends
        self.assertEqual(self.interp.op_LoopIfFalse(self.state, None, [], "t", 0, None), 31)
        self.state.pc = 40
        self.assertEqual(self.interp.op_Loop(self.state, None, [], "t", 0, None), 10)

    def test_a_repeating_conditional_loop_keeps_its_entry(self):
        self._push(20)
        self.state.pc, self.state.cond_flags = 30, 0
        self.assertEqual(self.interp.op_LoopIfFalse(self.state, None, [], "t", 0, None), 20)
        self.assertEqual(len(self.state.return_stack), 1)

    def test_an_unconditional_loop_still_keeps_its_entry(self):
        self._push(10)
        self.state.pc = 40
        self.interp.op_Loop(self.state, None, [], "t", 0, None)
        self.interp.op_Loop(self.state, None, [], "t", 0, None)
        self.assertEqual(len(self.state.return_stack), 1)
