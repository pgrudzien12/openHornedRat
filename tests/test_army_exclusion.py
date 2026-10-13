"""Army exclusion vectors from notes/exclude_from_army.md §§3–6."""
import unittest

from tests.test_objectives import at_boundary, make, regiment
from tests.script_helpers import FakeDll, word
from whshr import behaviour, interpreter
from whshr.battle_scene import BattleScene
from whshr.engine import Battle
from whshr.nodes import ScriptNode
from whshr.rules import Side


def exclude(battle, unit):
    state = battle.event_bus.unit_states[unit.identifier]
    return interpreter.ScriptInterpreter(battle, battle.event_bus, None).op_ExcludeFromArmy(
        state, None, [], unit.identifier, battle.tick_count, battle.rng)


class ArmyExclusionTests(unittest.TestCase):
    def test_repeated_exclusion_preserves_pending_credits_and_later_removal_pays_once(self):
        enemy, player = regiment('enemy', Side.ENEMY), regiment('player', Side.PLAYER)
        battle = make([['A', 0, 0]], player, enemy)
        enemy.model_positions()
        enemy.melee_models[0].credit = player.identifier
        enemy.attack_target = player.identifier
        enemy.reload_ticks = 12
        for _ in range(2):
            exclude(battle, enemy)
        self.assertTrue(enemy.active)
        self.assertTrue(enemy.visible_to_player)
        self.assertTrue(enemy.listed_for_removal)
        self.assertEqual(enemy.attack_target, player.identifier)
        self.assertEqual(enemy.reload_ticks, 12)
        self.assertEqual(enemy.melee_models[0].credit, player.identifier)
        self.assertEqual(player.kills, 0)
        self.assertFalse(enemy.removal_announced)
        self.assertEqual(battle.objectives.get('A').values[:2], [10, 1])
        self.assertFalse(battle.decided)
        at_boundary(battle)
        self.assertTrue(battle.decided)
        battle.remove_from_play(enemy)
        exclude(battle, enemy)
        battle.remove_from_play(enemy)
        self.assertFalse(enemy.active)
        self.assertEqual(player.kills, 1)

    def test_f_counts_an_active_excluded_enemy_as_gone(self):
        enemy = regiment('enemy', Side.ENEMY)
        battle = make([['F', 0, 0]], regiment('player', Side.PLAYER), enemy)
        exclude(battle, enemy)
        at_boundary(battle)
        self.assertTrue(battle.objectives.get('F').met)
        self.assertTrue(enemy.active)

    def test_n_still_requires_other_enemies_gone_and_arrival(self):
        dragon, orcs = regiment('Dragon', Side.ENEMY, 1), regiment('orcs', Side.ENEMY)
        player = regiment('player', Side.PLAYER)
        nodes = [ScriptNode(0, 0)] * 26 + [ScriptNode(1000, 1000, radius=32)]
        battle = make([['N', 26, 0]], player, dragon, orcs, nodes=nodes)
        exclude(battle, dragon)
        at_boundary(battle)
        self.assertFalse(battle.decided)
        battle.remove_from_play(orcs)
        at_boundary(battle, 2)
        self.assertFalse(battle.decided)
        player.x = player.y = 1000
        at_boundary(battle, 3)
        self.assertEqual(battle.objectives.decided, 'N')
        self.assertTrue(dragon.active)
        self.assertEqual(battle.objectives.enemy_start, 2)

    def test_excluded_dragon_continues_same_update_and_launches_breath(self):
        dragon = regiment('Dragon', Side.ENEMY, 1, shooting_code=14, unit_class=1)
        # The normal shooter handler consumes the fire-post event; here FireAtTarget uses the
        # already configured point, exercising exclusion and the actual innate launch together.
        words = [word('ExcludeFromArmy'), word('FireAtTarget'), word('Yield'), behaviour.END]
        battle = Battle(3000, 3000, [dragon], script_dll=FakeDll(words))
        state = battle.event_bus.unit_states[dragon.identifier]
        state.current_target = None
        state.aim_at_point = True
        state.target_point = (0, 100)
        battle.interpreter.run(dragon.identifier, state, 0, battle.rng)
        self.assertTrue(dragon.active)
        self.assertTrue(dragon.listed_for_removal)
        self.assertGreaterEqual(len(battle.innate_projectiles), 4)

    def test_excluded_player_can_trigger_z_while_active(self):
        player = regiment('player', Side.PLAYER)
        battle = make([], player)
        exclude(battle, player)
        at_boundary(battle)
        self.assertTrue(battle.objectives.get('Z').met)
        self.assertTrue(player.active)

    def test_g_discards_exited_kept_mortar_without_reactivating(self):
        mortar = regiment('mortar', Side.NEUTRAL, 2, unit_class=7)
        battle = make([['G', 0, 0]], regiment('player', Side.PLAYER), mortar)
        state = battle.event_bus.unit_states[mortar.identifier]
        state.unit_flags2 |= 0x1000  # kept for return, as in the BF017 exit script
        exclude(battle, mortar)
        self.assertTrue(mortar.active)
        battle.remove_from_play(mortar)
        self.assertTrue(mortar.listed_for_removal)
        battle.npc_regiments[mortar.identifier] = 16
        scene = BattleScene()
        scene.battle = battle
        scene.initial_models = {mortar.identifier: 2}
        self.assertIn(16, scene._npc_outcomes())
        battle.objectives.finish(battle)
        self.assertNotIn(16, scene._npc_outcomes())
        self.assertFalse(mortar.active)
        self.assertFalse(mortar.listed_for_removal)
        self.assertEqual(mortar.models, 2)

    def test_e_reads_existing_casualties_of_active_excluded_enemy(self):
        enemy = regiment('enemy', Side.ENEMY, 10)
        battle = make([['E', 20, 0]], regiment('player', Side.PLAYER), enemy)
        enemy.models = 8
        exclude(battle, enemy)
        battle.objectives.finish(battle)
        self.assertEqual(battle.objectives.get('E').values[3], 2)
        self.assertTrue(battle.objectives.get('E').met)
        self.assertTrue(enemy.active)
