"""Phase 3 tests: combat, movement, unit effects, and tagging integration.

Tests verify that the interpreter can:
1. Order units to charge and shoot
2. Kill units and remove them from battle
3. Create and use unit tags for targeting
4. Manage morale/routing behavior
5. Halt and reform units
"""

import unittest
from whshr import engine, interpreter
from whshr.engine import Regiment, Battle
from whshr.rules import Side


class CombatIntegrationTests(unittest.TestCase):
    """Test combat-related opcode integration."""

    def setUp(self):
        """Set up a simple 1v1 battle."""
        self.player = Regiment(
            "player_1", "Player Unit", 100, 100, 0, Side.PLAYER,
            models=10, ranks=2, ws=3, bs=3, strength=3, toughness=3,
            wounds=1, initiative=3, attacks=1, leadership=7,
            missile_code=None, missile_range=None
        )
        self.enemy = Regiment(
            "enemy_1", "Enemy Unit", 200, 100, 0, Side.ENEMY,
            models=10, ranks=2, ws=3, bs=3, strength=3, toughness=3,
            wounds=1, initiative=3, attacks=1, leadership=7,
            missile_code=None, missile_range=None
        )
        self.battle = Battle(500, 500, [self.player, self.enemy], seed=1995)

    def test_charge_target_sets_attack_target(self):
        """Test that ChargeTarget sets attack_target on regiment."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["enemy_1"]

        # Set target and issue charge
        state.current_target = ("player_1", 0)
        interp.op_ChargeTarget(state, None, [], "enemy_1", 0, None)

        # Verify attack target is set
        self.assertEqual(self.enemy.attack_target, "player_1")

    def test_fire_at_target_never_sets_attack_target(self):
        """Regression test: FireAtTarget must NOT set regiment.attack_target, for any unit,
        regardless of missile range. attack_target means "melee charge target" to both
        Battle._advance_regiments (would charge the shooter into melee) and
        combat.resolve_shooting (explicitly skips any unit with attack_target set, since it already
        does its own independent targeting) -- a prior version set it here too, which silently
        broke scripted shooting orders entirely."""
        archer = Regiment(
            "archer_1", "Archer", 200, 100, 0, Side.ENEMY,
            models=10, ranks=2, ws=2, bs=4, strength=3, toughness=3,
            wounds=1, initiative=3, attacks=1, leadership=7,
            missile_code=1, missile_range=120.0  # archers have range
        )
        battle = Battle(500, 500, [self.player, archer], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["archer_1"]

        state.current_target = ("player_1", 0)
        interp.op_FireAtTarget(state, None, [], "archer_1", 0, None)

        self.assertIsNone(archer.attack_target)

        # Also true for a non-missile unit (no branching left in the opcode at all).
        interp2 = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state2 = self.battle.event_bus.unit_states["enemy_1"]
        state2.current_target = ("player_1", 0)
        interp2.op_FireAtTarget(state2, None, [], "enemy_1", 0, None)
        self.assertIsNone(self.enemy.attack_target)

    def test_kill_all_models_destroys_unit(self):
        """Test that KillAllModels removes all models from a unit."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["enemy_1"]

        # Verify unit has models before
        self.assertEqual(self.enemy.models, 10)

        # Kill all models
        interp.op_KillAllModels(state, None, [], "enemy_1", 0, None)

        # Verify unit is destroyed
        self.assertEqual(self.enemy.models, 0)
        self.assertTrue(self.enemy.destroyed)


class UnitEffectsTests(unittest.TestCase):
    """Test unit removal and effect opcodes."""

    def setUp(self):
        """Set up test battle."""
        self.unit = Regiment(
            "test_1", "Test Unit", 100, 100, 0, Side.ENEMY,
            models=10, ranks=2, leadership=7
        )
        self.battle = Battle(500, 500, [self.unit], seed=1995)

    def test_remove_from_battle_marks_fled(self):
        """Test that RemoveFromBattle removes unit from play."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        self.assertFalse(self.unit.fled)
        interp.op_RemoveFromBattle(state, None, [], "test_1", 0, None)
        self.assertTrue(self.unit.fled)

    def test_exclude_from_army_marks_fled(self):
        """Test that ExcludeFromArmy removes unit from army."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        self.assertFalse(self.unit.fled)
        interp.op_ExcludeFromArmy(state, None, [], "test_1", 0, None)
        self.assertTrue(self.unit.fled)

    def test_halt_and_reform_clears_orders(self):
        """Test that HaltAndReform cancels movement and attack orders."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        # Set orders
        self.unit.target_x = 200
        self.unit.target_y = 200
        self.unit.attack_target = "other"

        # Halt
        interp.op_HaltAndReform(state, None, [], "test_1", 0, None)

        # Verify orders cleared
        self.assertIsNone(self.unit.target_x)
        self.assertIsNone(self.unit.target_y)
        self.assertIsNone(self.unit.attack_target)


class UnitTaggingTests(unittest.TestCase):
    """Test unit tagging system for special targeting."""

    def setUp(self):
        """Set up test battle with tagged units."""
        self.cargo = Regiment(
            "cargo_1", "Cargo", 100, 100, 0, Side.ENEMY,
            models=5, ranks=1, leadership=7
        )
        self.hunter = Regiment(
            "hunter_1", "Hunter", 200, 100, 0, Side.ENEMY,
            models=10, ranks=2, leadership=7
        )
        self.battle = Battle(500, 500, [self.cargo, self.hunter], seed=1995)

    def test_set_tag_registers_unit(self):
        """Test that SetTag registers a unit with a tag."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["cargo_1"]

        # Tag the cargo
        tag = 0xABC0
        interp.op_SetTag(state, tag, [], "cargo_1", 0, None)

        # Verify tag registry exists and contains the mapping
        self.assertTrue(hasattr(self.battle, '_unit_tags'))
        self.assertEqual(self.battle._unit_tags[tag], "cargo_1")

    def test_attack_tagged_finds_and_targets_unit(self):
        """Test that AttackTagged finds a tagged unit and sets it as target."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

        # Tag the cargo
        cargo_state = self.battle.event_bus.unit_states["cargo_1"]
        tag = 0xABC0
        interp.op_SetTag(cargo_state, tag, [], "cargo_1", 0, None)

        # Hunter attacks the tagged cargo
        hunter_state = self.battle.event_bus.unit_states["hunter_1"]
        interp.op_AttackTagged(hunter_state, tag, [], "hunter_1", 0, None)

        # Verify hunter targets the cargo
        self.assertEqual(self.hunter.attack_target, "cargo_1")
        self.assertEqual(hunter_state.current_target[0], "cargo_1")

    def test_attack_tagged_fails_if_no_tag(self):
        """Test that AttackTagged fails gracefully if tag doesn't exist."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["hunter_1"]

        # Try to attack non-existent tag
        interp.op_AttackTagged(state, 0xDEAD, [], "hunter_1", 0, None)

        # Should fail gracefully and set cond_flags to 0
        self.assertEqual(state.cond_flags, 0)


class MoraleRoutingTests(unittest.TestCase):
    """Test morale and routing-related opcodes."""

    def setUp(self):
        """Set up test battle."""
        self.unit = Regiment(
            "test_1", "Test Unit", 100, 100, 0, Side.ENEMY,
            models=10, ranks=2, leadership=7
        )
        self.player = Regiment(
            "player_1", "Player", 100, 100, 0, Side.PLAYER,
            models=10, ranks=2, leadership=7
        )
        self.battle = Battle(500, 500, [self.unit, self.player], seed=1995)

    def test_if_routed_tests_routing_state(self):
        """Test that IfRouted checks if unit is routing."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        # Unit not routing
        interp.op_IfRouted(state, None, [], "test_1", 0, None)
        self.assertEqual(state.cond_flags, 0)

        # Start routing
        self.unit.routing = True
        interp.op_IfRouted(state, None, [], "test_1", 0, None)
        self.assertEqual(state.cond_flags, 1)

    def test_enemy_routed_detects_routing_enemies(self):
        """Test that EnemyRouted detects enemy units that are routing."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        # No enemies routing yet
        interp.op_EnemyRouted(state, None, [], "test_1", 0, None)
        self.assertEqual(state.cond_flags, 0)

        # Player unit starts routing
        self.player.routing = True
        interp.op_EnemyRouted(state, None, [], "test_1", 0, None)
        self.assertEqual(state.cond_flags, 1)

    def test_run_away_actually_starts_routing(self):
        """Test that RunAway calls combat._start_rout with the correct argument order.

        Regression test: an earlier draft called combat._start_rout(battle, regiment) instead of
        combat._start_rout(regiment, battle), which would raise AttributeError the moment
        _start_rout touched regiment.player on what was actually the Battle object.
        """
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        self.assertFalse(self.unit.routing)
        interp.op_RunAway(state, None, [], "test_1", 0, None)
        self.assertTrue(self.unit.routing)
        self.assertIsNotNone(self.unit.flee_x)
        self.assertIsNotNone(self.unit.flee_y)

    def test_run_away_respects_cant_break(self):
        """Test that RunAway does not rout a unit with the CantBreak psychology flag."""
        stubborn = Regiment(
            "stubborn_1", "Stubborn Unit", 100, 100, 0, Side.ENEMY,
            models=10, ranks=2, leadership=7, psychology=frozenset({"CantBreak"})
        )
        battle = Battle(500, 500, [stubborn, self.player], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["stubborn_1"]

        interp.op_RunAway(state, None, [], "stubborn_1", 0, None)
        self.assertFalse(stubborn.routing)

    def test_ready_to_fire_checks_reload_state(self):
        """Test that ReadyToFire checks if unit can shoot."""
        archer = Regiment(
            "archer_1", "Archer", 100, 100, 0, Side.ENEMY,
            models=10, ranks=2, missile_code=1, missile_range=120.0
        )
        battle = Battle(500, 500, [archer], seed=1995)
        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["archer_1"]

        # Ready to fire (reload_ticks at 0)
        interp.op_ReadyToFire(state, None, [], "archer_1", 0, None)
        self.assertEqual(state.cond_flags, 1)

        # Set reload counter
        archer.reload_ticks = 5.0
        interp.op_ReadyToFire(state, None, [], "archer_1", 0, None)
        self.assertEqual(state.cond_flags, 0)


class MovementOpcodeTests(unittest.TestCase):
    """Test movement-related opcodes against a battle with no [NODES] table (empty Battle.nodes):
    the opcodes must still record current_node and otherwise no-op gracefully, never raise."""

    def setUp(self):
        """Set up test battle."""
        self.unit = Regiment(
            "test_1", "Test Unit", 100, 100, 0, Side.ENEMY,
            models=10, ranks=2, leadership=7
        )
        self.battle = Battle(500, 500, [self.unit], seed=1995)

    def test_move_to_node_sets_current_node(self):
        """Test that MoveToNode sets the current node id."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        node_id = 5
        interp.op_MoveToNode(state, node_id, [], "test_1", 0, None)

        self.assertEqual(state.current_node, node_id)
        self.assertIsNone(self.unit.target_x)  # unknown node: no movement order issued

    def test_face_node_executes(self):
        """Test that FaceNode opcode executes without a known node (no-op, no error)."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        # Should execute without error
        result = interp.op_FaceNode(state, 3, [], "test_1", 0, None)
        self.assertEqual(result, 1)
        self.assertEqual(self.unit.direction, 0)  # unchanged

    def test_teleport_to_node_sets_current_node(self):
        """Test that TeleportToNode sets current node even when the node is unknown."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        interp.op_TeleportToNode(state, 7, [], "test_1", 0, None)
        self.assertEqual(state.current_node, 7)
        self.assertEqual(self.unit.x, 100)  # unknown node: position unchanged

    def test_place_at_node_sets_node(self):
        """Test that PlaceAtNode sets the node even when the node is unknown."""
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["test_1"]

        interp.op_PlaceAtNode(state, 9, [], "test_1", 0, None)
        self.assertEqual(state.current_node, 9)


class MovementOpcodeWithRealNodesTests(unittest.TestCase):
    """Test movement-related opcodes against a battle whose Battle.nodes is populated (the normal
    case: [NODES] data comes from whshr.script.load_battle via Battle.from_script)."""

    def setUp(self):
        self.unit = Regiment(
            "test_1", "Test Unit", 100, 100, 0, Side.ENEMY,
            models=10, ranks=2, leadership=7
        )
        self.battle = Battle(500, 500, [self.unit], seed=1995, nodes={5: (300.0, 200.0), 9: (100.0, 100.0)})
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["test_1"]

    def test_move_to_node_orders_an_ordinary_move_toward_the_nodes_coordinates(self):
        self.interp.op_MoveToNode(self.state, 5, [], "test_1", 0, None)
        self.assertEqual((self.unit.target_x, self.unit.target_y), (300.0, 200.0))
        self.assertTrue(self.unit.moving)

    def test_move_to_node_does_not_touch_an_existing_attack_target(self):
        self.unit.attack_target = "someone"
        self.interp.op_MoveToNode(self.state, 5, [], "test_1", 0, None)
        self.assertEqual(self.unit.attack_target, "someone")

    def test_face_node_turns_toward_the_node_without_moving(self):
        # Node 5 is at (300, 200): due east-ish of (100, 100) -- just confirm a turn happened and
        # no movement order was issued, without asserting the exact direction encoding here.
        self.interp.op_FaceNode(self.state, 5, [], "test_1", 0, None)
        self.assertNotEqual(self.unit.direction, 0)
        self.assertIsNone(self.unit.target_x)

    def test_face_node_is_a_noop_when_already_at_the_nodes_position(self):
        self.interp.op_FaceNode(self.state, 9, [], "test_1", 0, None)  # node 9 == unit's own (x, y)
        self.assertEqual(self.unit.direction, 0)

    def test_teleport_to_node_instantly_repositions_and_clears_any_move_order(self):
        self.unit.target_x, self.unit.target_y = 999.0, 999.0
        self.interp.op_TeleportToNode(self.state, 5, [], "test_1", 0, None)
        self.assertEqual((self.unit.x, self.unit.y), (300.0, 200.0))
        self.assertIsNone(self.unit.target_x)
        self.assertIsNone(self.unit.target_y)

    def test_place_at_node_instantly_repositions(self):
        self.interp.op_PlaceAtNode(self.state, 5, [], "test_1", 0, None)
        self.assertEqual((self.unit.x, self.unit.y), (300.0, 200.0))


class ScatterModelsToNodeTests(unittest.TestCase):
    """The actual opcode NPC 'patrol' scripts call (confirmed from a real BF003 trace), not
    MoveToNode -- peasant regiments never call MoveToNode at all."""

    def setUp(self):
        self.unit = Regiment("peasants", "Peasants", 100, 100, 0, False, models=5, ranks=1)
        self.battle = Battle(2000, 2000, [self.unit], seed=1995, nodes={2: (700.0, 600.0)})
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["peasants"]

    def test_orders_a_move_to_a_jittered_point_near_the_node(self):
        self.interp.op_ScatterModelsToNode(self.state, 2, [], "peasants", 0, self.battle.rng)
        self.assertTrue(self.unit.moving)
        dx = self.unit.target_x - 700.0
        dy = self.unit.target_y - 600.0
        self.assertLessEqual(abs(dx), interpreter.SCATTER_RADIUS)
        self.assertLessEqual(abs(dy), interpreter.SCATTER_RADIUS)

    def test_is_deterministic_for_a_given_seed(self):
        battle_a = Battle(2000, 2000, [Regiment("p", "P", 100, 100, 0, False, models=5, ranks=1)],
                           seed=42, nodes={2: (700.0, 600.0)})
        battle_b = Battle(2000, 2000, [Regiment("p", "P", 100, 100, 0, False, models=5, ranks=1)],
                           seed=42, nodes={2: (700.0, 600.0)})
        for battle in (battle_a, battle_b):
            interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
            state = battle.event_bus.unit_states["p"]
            interp.op_ScatterModelsToNode(state, 2, [], "p", 0, battle.rng)
        self.assertEqual(
            (battle_a.regiments["p"].target_x, battle_a.regiments["p"].target_y),
            (battle_b.regiments["p"].target_x, battle_b.regiments["p"].target_y))

    def test_unknown_node_is_a_safe_noop(self):
        self.interp.op_ScatterModelsToNode(self.state, 999, [], "peasants", 0, self.battle.rng)
        self.assertIsNone(self.unit.target_x)


class ArrivalFlagTests(unittest.TestCase):
    """ARRIVED_FLAG lets a WaitUntilUnitFlags(ARRIVED_FLAG) loop unblock once a script-issued
    MoveToNode/ScatterModelsToNode order completes -- confirmed as the real cause of Goblin
    Wolfriders freezing permanently mid-mission in a real BF003 playthrough: nothing previously
    ever set any bit checked by WaitUntilUnitFlags, so that wait never ended."""

    def setUp(self):
        self.unit = Regiment("wolfriders", "Wolfriders", 100, 100, 0, False, models=10, ranks=2)
        self.battle = Battle(2000, 2000, [self.unit], seed=1995, nodes={2: (110.0, 100.0)})
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["wolfriders"]

    def test_move_to_node_arms_pending_arrival_and_clears_the_flag(self):
        self.state.unit_flags = interpreter.ARRIVED_FLAG  # stale flag from an earlier order
        self.interp.op_MoveToNode(self.state, 2, [], "wolfriders", 0, None)
        self.assertTrue(self.state.pending_arrival)
        self.assertEqual(self.state.unit_flags & interpreter.ARRIVED_FLAG, 0)

    def test_flag_is_not_set_while_still_moving(self):
        self.interp.op_MoveToNode(self.state, 2, [], "wolfriders", 0, None)
        self.interp._update_arrival_flag("wolfriders", self.state)
        self.assertEqual(self.state.unit_flags & interpreter.ARRIVED_FLAG, 0)
        self.assertTrue(self.state.pending_arrival)

    def test_flag_is_set_once_the_regiment_stops_moving(self):
        self.interp.op_MoveToNode(self.state, 2, [], "wolfriders", 0, None)
        self.unit.target_x = self.unit.target_y = None  # simulate Battle._advance_toward arriving
        self.interp._update_arrival_flag("wolfriders", self.state)
        self.assertEqual(self.state.unit_flags & interpreter.ARRIVED_FLAG, interpreter.ARRIVED_FLAG)
        self.assertFalse(self.state.pending_arrival)

    def test_waituntilunitflags_unblocks_once_arrived(self):
        self.interp.op_MoveToNode(self.state, 2, [], "wolfriders", 0, None)
        result = self.interp.op_WaitUntilUnitFlags(self.state, 16, [], "wolfriders", 0, None)
        self.assertEqual(result, self.state.pc)  # still blocked: not arrived yet

        self.unit.target_x = self.unit.target_y = None
        self.interp._update_arrival_flag("wolfriders", self.state)
        result = self.interp.op_WaitUntilUnitFlags(self.state, 16, [], "wolfriders", 0, None)
        self.assertEqual(result, self.state.pc + 1)  # unblocked

    def test_teleport_to_node_sets_the_flag_immediately_no_pending_arrival(self):
        self.interp.op_TeleportToNode(self.state, 2, [], "wolfriders", 0, None)
        self.assertEqual(self.state.unit_flags & interpreter.ARRIVED_FLAG, interpreter.ARRIVED_FLAG)
        self.assertFalse(self.state.pending_arrival)

    def test_full_run_cycle_via_run_sets_the_flag_after_arrival(self):
        """End-to-end through ScriptInterpreter.run(), not calling _update_arrival_flag directly."""
        self.interp.op_MoveToNode(self.state, 2, [], "wolfriders", 0, None)
        self.assertTrue(self.state.pending_arrival)

        # The regiment "arrives" between ticks (Battle._advance_regiments' job, simulated here).
        self.unit.target_x = self.unit.target_y = None

        # A bare UnitScriptState with no script_dll makes run() return immediately after the
        # arrival check -- exactly what's being tested here.
        self.interp.run("wolfriders", self.state, 1, self.battle.rng)
        self.assertEqual(self.state.unit_flags & interpreter.ARRIVED_FLAG, interpreter.ARRIVED_FLAG)


if __name__ == '__main__':
    unittest.main()
