"""In-battle objectives and the battle end (notes/battle_end_objectives.md). Vectors follow section 10: segment
boundaries are battle ticks 19, 38, 57 ...; meeting a battle-ending letter decides the battle without ending it,
and the battle ends when the player leaves through the tent."""

import random
import unittest

from tests.script_helpers import FakeDll, word
from whshr import behaviour, combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.nodes import ScriptNode
from whshr.objectives import Objectives
from whshr.rules import Side

IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


def regiment(identifier, side, models=10, x=0.0, y=0.0, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=models, ranks=2, **extra)


def make(entries, *units, nodes=None, scenery=(), scripted=False):
    battle = Battle(3000, 3000, list(units), seed=1995, script_nodes=nodes, scenery=scenery,
                    script_dll=FakeDll(IDLE) if scripted else None)
    battle.objectives = Objectives.from_entries(entries)
    battle.objectives.load(battle)
    battle.phase = "battle"
    return battle


def at_boundary(battle, boundary=1):
    battle.tick_count = 19 * boundary
    assert battle.objectives is not None
    battle.objectives.segment(battle)


def kinds(battle, kind):
    return [event for event in battle.events if event.kind == kind]


class EvaluationListTests(unittest.TestCase):
    def test_z_comes_first_and_a_bts_z_line_is_ignored(self):
        objectives = Objectives.from_entries([["R", 1, 0], ["A", 32, 2], ["Z", 28, 2], ["B", 80, 12]])
        self.assertEqual([r.letter for r in objectives.records], ["Z", "R", "A", "B"])
        self.assertEqual(objectives.get("Z").values, [0, 0, 0, 0])

    def test_load_measures_a_and_z_including_hidden_units(self):
        battle = make([["A", 99, 99]], regiment("p", Side.PLAYER, 16), regiment("e", Side.ENEMY, 20),
                      regiment("w", Side.ENEMY, 12, hidden=True), regiment("dead", Side.ENEMY, 0))
        self.assertEqual(battle.objectives.get("A").values[:2], [32, 2])
        self.assertEqual(battle.objectives.get("Z").values[:2], [16, 1])


class EliminationTests(unittest.TestCase):
    def setUp(self):
        self.player = regiment("p", Side.PLAYER)
        self.stickers = regiment("s", Side.ENEMY)
        self.wolves = regiment("w", Side.ENEMY, 12, hidden=True)
        self.battle = make([["A", 32, 2]], self.player, self.stickers, self.wolves)

    def test_a_hidden_counted_enemy_keeps_a_open(self):
        self.stickers.models = 0
        at_boundary(self.battle, 3)
        self.assertFalse(self.battle.decided)

    def test_removing_the_last_enemy_decides_without_ending_the_battle(self):
        self.stickers.models = 0
        self.wolves.fled = True
        at_boundary(self.battle, 16)
        self.assertEqual(self.battle.objectives.decided, "A")
        self.assertIsNone(self.battle.result)
        self.assertTrue(self.battle.can_leave)
        self.assertEqual([e.data["text_id"] for e in kinds(self.battle, "message")], [1005])
        self.assertEqual([(e.data["packet"], e.data["effect"]) for e in kinds(self.battle, "sound")], [(5, 9)])

    def test_a_broken_enemy_that_can_still_rally_remains(self):
        self.wolves.fled = True
        self.stickers.original_models, self.stickers.models, self.stickers.routing = 12, 4, True  # 8 < 3 x 4
        at_boundary(self.battle)
        self.assertFalse(self.battle.decided)

    def test_a_broken_enemy_that_cannot_rally_is_gone_for_a(self):
        self.wolves.fled = True
        self.stickers.original_models, self.stickers.models, self.stickers.routing = 12, 3, True  # 9 >= 3 x 3
        at_boundary(self.battle)
        self.assertEqual(self.battle.objectives.decided, "A")

    def test_cant_rally_at_full_strength_is_out_of_action(self):
        self.wolves.fled = True
        self.stickers.routing, self.stickers.psychology = True, frozenset({"CantRally"})
        at_boundary(self.battle)
        self.assertEqual(self.battle.objectives.decided, "A")

    def test_f_needs_the_regiment_removed(self):
        battle = make([["F", 0, 0]], regiment("p", Side.PLAYER), enemy := regiment("e", Side.ENEMY, 3))
        enemy.original_models, enemy.routing = 12, True
        at_boundary(battle)
        self.assertFalse(battle.decided)
        enemy.fled = True  # fled off the table counts as gone
        at_boundary(battle, 2)
        self.assertEqual(battle.objectives.decided, "F")

    def test_units_spawned_after_load_are_not_counted(self):
        self.stickers.models, self.wolves.models = 0, 0
        self.battle.regiments["fanatic"] = regiment("fanatic", Side.ENEMY, 1)
        at_boundary(self.battle)
        self.assertEqual(self.battle.objectives.decided, "A")

    def test_z_is_checked_first_and_decides_a_loss(self):
        self.stickers.models, self.wolves.models, self.player.models = 0, 0, 0
        at_boundary(self.battle, 2)
        self.assertEqual(self.battle.objectives.decided, "Z")
        self.assertFalse(self.battle.objectives.get("A").met)
        self.assertEqual([(e.data["packet"], e.data["effect"]) for e in kinds(self.battle, "sound")], [(5, 15)])
        self.battle.leave()
        self.assertEqual(self.battle.result, "defeat")

    def test_the_outcome_cannot_flip_after_a_win(self):
        self.stickers.models, self.wolves.models = 0, 0
        at_boundary(self.battle, 20)
        self.player.models = 0
        at_boundary(self.battle, 27)
        self.assertFalse(self.battle.objectives.get("Z").met)
        self.battle.leave()
        self.assertEqual(self.battle.result, "victory")
        self.assertEqual(self.battle.objectives.get("Z").values, [10, 1, 1, 0])  # one regiment lost

    def test_escaping_kept_for_return_enemies_count_against_the_player(self):
        players = [regiment(f"p{i}", Side.PLAYER) for i in range(3)]
        escaper = regiment("x", Side.ENEMY)
        battle = make([["A", 0, 0]], *players, escaper, regiment("e", Side.ENEMY), scripted=True)
        battle.event_bus.unit_states["x"].unit_flags2 |= 0x1000
        escaper.fled = True
        players[0].models = players[1].models = 0
        at_boundary(battle)
        self.assertEqual(battle.objectives.decided, "Z")  # 2 lost + 1 escaper = 3


class TimingTests(unittest.TestCase):
    def test_a_removal_is_seen_at_the_next_segment_boundary(self):
        enemy = regiment("e", Side.ENEMY, x=2000, y=2000)
        battle = make([["A", 0, 0]], regiment("p", Side.PLAYER), enemy)
        battle.tick_count = 0
        for _ in range(37):
            battle.tick()
        enemy.models = 0  # removed during tick 37
        battle.tick()
        self.assertFalse(battle.decided)
        battle.tick()  # tick 38 starts with the check
        self.assertTrue(battle.decided)
        for _ in range(5):
            battle.tick()
        self.assertEqual((battle.tick_count, battle.result), (44, None))  # the simulation keeps running

    def test_the_tent_is_refused_before_the_decision(self):
        battle = make([["A", 0, 0]], regiment("p", Side.PLAYER), regiment("e", Side.ENEMY))
        with self.assertRaises(ValueError):
            battle.leave()


class NodeLetterTests(unittest.TestCase):
    def test_n_needs_a_player_regiment_inside_the_node(self):
        nodes = [ScriptNode(0.0, 0.0)] * 26 + [ScriptNode(1000.0, 1000.0, radius=32)]
        for distance, decided in ((30, "N"), (33, None)):
            with self.subTest(distance=distance):
                player = regiment("p", Side.PLAYER, x=1000, y=1000 + distance)
                battle = make([["N", 26, 0]], player, regiment("e", Side.ENEMY, 0), nodes=nodes)
                at_boundary(battle)
                self.assertEqual(battle.objectives.decided, decided)

    def test_item_pickup_after_the_decision(self):
        nodes = [ScriptNode(0.0, 0.0)] * 13 + [ScriptNode(500.0, 500.0, radius=40)]
        picker = regiment("p", Side.PLAYER, x=0, y=0, whoami=2, items=("ItemGrudgeBringer",))
        battle = make([["A", 0, 0], ["K", 13, 10]], picker, enemy := regiment("e", Side.ENEMY), nodes=nodes,
                      scripted=True)
        k = battle.objectives.get("K")
        self.assertEqual(k.values, [13, 10, 0, 39])
        enemy.models = 0
        at_boundary(battle)
        picker.x, picker.y = 500, 520
        at_boundary(battle, 2)
        self.assertTrue(k.met)
        self.assertEqual(picker.items, ("ItemGrudgeBringer", "ItemSwordOfMight"))
        self.assertEqual(k.values[2], 2)
        self.assertNotIn("K", battle.objectives.item_marks)

    def test_full_item_slots_refuse_the_pickup(self):
        nodes = [ScriptNode(500.0, 500.0, radius=40)]
        picker = regiment("p", Side.PLAYER, x=500, y=500, items=("a", "b", "c", "d", "e"))
        battle = make([["K", 0, 3]], picker, regiment("e", Side.ENEMY), nodes=nodes)
        at_boundary(battle)
        self.assertFalse(battle.objectives.get("K").met)

    def test_given_a_sword_of_might_picked_up_when_the_leader_next_attacks_then_it_strikes_at_plus_one_strength(self):
        # Given a leader at S 3 facing T 5, and the Sword of Might (K item 10) lying in its node
        nodes = [ScriptNode(500.0, 500.0, radius=40)]
        picker = regiment("p", Side.PLAYER, x=500, y=500, has_leader=True, strength=3)
        enemy = regiment("e", Side.ENEMY, toughness=5)
        battle = make([["K", 0, 10]], picker, enemy, nodes=nodes)
        before = self._leader_wound_need(picker, enemy)

        # When the item is picked up during this battle
        at_boundary(battle)

        # Then the bonus applies at once, not from the next battle
        self.assertIn("ItemSwordOfMight", picker.items)
        self.assertEqual(picker.displayed_leader_strength, 4)
        self.assertEqual((before, self._leader_wound_need(picker, enemy)), (6, 5))

    def test_given_a_drunk_potion_and_four_items_when_entering_an_item_node_then_the_potion_still_fills_a_slot(self):
        # Given five items, one of them a Potion of Strength already drunk this battle
        nodes = [ScriptNode(500.0, 500.0, radius=40)]
        picker = regiment("p", Side.PLAYER, x=500, y=500, has_leader=True,
                          items=("ItemPotionOfStrength", "a", "b", "c", "d"))
        battle = make([["K", 0, 10]], picker, regiment("e", Side.ENEMY), nodes=nodes)
        battle.arm_item("p", "ItemPotionOfStrength")

        # When it stands in the item's node
        at_boundary(battle)

        # Then all five slots are still full: no pickup, and the potion's bonus remains
        self.assertFalse(battle.objectives.get("K").met)
        self.assertNotIn("ItemSwordOfMight", picker.items)
        self.assertTrue(picker.potion_strength)

    def test_given_a_drunk_potion_and_a_free_slot_when_the_sword_is_picked_up_then_both_bonuses_stack(self):
        # Given a drunk potion (+3 S) and a free slot
        nodes = [ScriptNode(500.0, 500.0, radius=40)]
        picker = regiment("p", Side.PLAYER, x=500, y=500, has_leader=True, strength=3,
                          items=("ItemPotionOfStrength",))
        battle = make([["K", 0, 10]], picker, regiment("e", Side.ENEMY), nodes=nodes)
        battle.arm_item("p", "ItemPotionOfStrength")

        # When the Sword of Might is picked up
        at_boundary(battle)

        # Then it takes the slot after the potion and the leader shows S 3 + 3 + 1
        self.assertEqual(picker.items, ("ItemPotionOfStrength", "ItemSwordOfMight"))
        self.assertEqual(picker.displayed_leader_strength, 7)

    @staticmethod
    def _leader_wound_need(attacker, defender):
        attacker.model_positions()
        defender.model_positions()
        leader = attacker.living_leader_index
        assert leader is not None
        return combat._roll_model_attacks(attacker, defender, random.Random(1), model=attacker.melee_models[leader],
                                          defender_model=defender.melee_models[0])[1]["wound_need"]

    def test_an_unknown_item_number_is_never_met(self):
        nodes = [ScriptNode(500.0, 500.0, radius=40)]
        battle = make([["K", 0, 17]], regiment("p", Side.PLAYER, x=500, y=500), nodes=nodes)
        at_boundary(battle)
        self.assertFalse(battle.objectives.get("K").met)


class ImpossibleMissionTests(unittest.TestCase):
    def test_u_warns_one_more_regiment_per_turn_from_turn_a_and_shows_the_tent(self):
        units = [regiment("cmd", Side.PLAYER, whoami=2, race=0), regiment("p1", Side.PLAYER, race=0),
                 regiment("p2", Side.PLAYER, race=0), regiment("e", Side.ENEMY)]
        battle = make([["A", 0, 0], ["U", 4, 0]], *units, scripted=True)
        at_boundary(battle, 30)
        self.assertFalse(battle.can_leave)
        battle.tick_count = 589  # turn 4 begins at boundary 31
        battle.objectives.segment(battle)
        self.assertTrue(battle.can_leave)
        self.assertEqual([e.data["regiment"] for e in kinds(battle, "react")], ["p1"])
        battle.events.clear()
        at_boundary(battle, 41)
        self.assertEqual([e.data["regiment"] for e in kinds(battle, "react")], ["p2"])
        battle.leave()
        self.assertTrue(battle.objectives.get("Z").met)
        self.assertEqual(battle.result, "defeat")

    def test_no_mission_complete_message_in_u_battles(self):
        battle = make([["A", 0, 0], ["U", 4, 0]], regiment("p", Side.PLAYER), regiment("e", Side.ENEMY, 0))
        at_boundary(battle)
        self.assertEqual((battle.objectives.decided, kinds(battle, "message"), kinds(battle, "sound")), ("A", [], []))


class FinalPassTests(unittest.TestCase):
    def test_peasants_buildings_and_trees_on_leaving(self):
        peasants = regiment("v", Side.NEUTRAL, 12, race=6)
        scenery = [{"name": "Tudor2Stry"}, {"name": "Farm"}, {"name": "Pine"}, {"name": "SnwTriPineLrg"},
                   {"name": "Signpost"}]
        battle = make([["A", 0, 0], ["B", 80, 12], ["C", 80, 7], ["Q", 60, 0]], regiment("p", Side.PLAYER),
                      regiment("e", Side.ENEMY, 0), peasants, scenery=scenery)
        at_boundary(battle)
        peasants.models = 9
        battle.leave()
        self.assertEqual(battle.objectives.get("B").result(), (False, (80, 12, 75, 9)))
        self.assertEqual(battle.objectives.get("C").result(), (True, (80, 2, 100, 2)))
        self.assertEqual(battle.objectives.get("Q").result(), (True, (60, 2, 100, 2)))

    def test_fled_peasants_count_as_saved(self):
        peasants = regiment("v", Side.NEUTRAL, 12, race=6)
        battle = make([["A", 0, 0], ["B", 80, 0]], regiment("p", Side.PLAYER), regiment("e", Side.ENEMY, 0),
                      peasants)
        at_boundary(battle)
        peasants.models, peasants.fled = 10, True
        battle.leave()
        self.assertEqual(battle.objectives.get("B").result(), (True, (80, 12, 83, 10)))

    def test_e_adds_the_bts_b_and_counts_killed_models(self):
        enemy = regiment("e", Side.ENEMY, 10)
        battle = make([["A", 0, 0], ["E", 100, 69]], regiment("p", Side.PLAYER), enemy)
        self.assertEqual(battle.objectives.get("E").values[1], 79)
        enemy.models = 0
        at_boundary(battle)
        battle.leave()
        self.assertEqual(battle.objectives.get("E").result(), (False, (100, 79, 12, 10)))

    def test_stub_letters(self):
        battle = make([["A", 0, 0], ["S", 0, 0], ["M", 0, 0], ["R", 1, 0]], regiment("p", Side.PLAYER),
                      regiment("e", Side.ENEMY, 0))
        at_boundary(battle)
        battle.leave()
        self.assertEqual([(r.letter, r.met) for r in battle.objectives.records],
                         [("Z", False), ("A", True), ("S", True), ("M", False), ("R", False)])


class SiegeTests(unittest.TestCase):
    def test_nobody_left_outside_moves_state_4_to_5_and_meets_z(self):
        player, ally = regiment("p", Side.PLAYER), regiment("a", Side.NEUTRAL)
        battle = make([["A", 0, 0], ["H", 0, 0], ["G", 1, 4]], player, ally, regiment("e", Side.ENEMY),
                      scripted=True)
        battle.mission_state = 4
        player.fled = ally.fled = True
        at_boundary(battle)
        self.assertEqual((battle.objectives.decided, battle.mission_state), ("Z", 5))
        self.assertEqual([(e.data["packet"], e.data["effect"]) for e in kinds(battle, "sound")], [(11, 0), (5, 9)])
        self.assertIn(0x38, [e.code for e in battle.event_bus.unit_states["e"].event_queue])

    def test_h_decides_at_battle_state_7(self):
        battle = make([["A", 0, 0], ["H", 0, 0], ["G", 1, 4]], regiment("p", Side.PLAYER), regiment("e", Side.ENEMY))
        battle.mission_state = 7
        at_boundary(battle)
        self.assertEqual(battle.objectives.decided, "H")


class BookTests(unittest.TestCase):
    def test_bf003_objective_list(self):
        objectives = Objectives.from_entries([["Z", 28, 2], ["R", 1, 0], ["A", 32, 2], ["B", 80, 12], ["C", 80, 7],
                                              ["K", 13, 10]])
        self.assertEqual(objectives.book_text_ids(), [1004, 33000, 33026, 33030])
        objectives.decided = "A"
        self.assertEqual(objectives.book_text_ids(), [1005])


class BookAndSoundTests(unittest.TestCase):
    def test_the_book_lists_the_objectives_before_the_decision_and_repeats_the_message_after(self):
        battle = make([["R", 1, 0], ["A", 0, 0], ["B", 80, 0]], regiment("p", Side.PLAYER), regiment("e", Side.ENEMY))
        battle.open_book()
        self.assertEqual([e.data["text_id"] for e in battle.pending_feedback], [1004, 33000, 33026])
        battle.pending_feedback.clear()
        battle.regiments["e"].models = 0
        at_boundary(battle)
        battle.open_book()
        self.assertEqual([(e.kind, e.data.get("text_id"), e.data.get("effect")) for e in battle.pending_feedback],
                         [("message", 1005, None), ("sound", None, 9)])

    def test_the_charge_sound_stops_when_the_charge_ends(self):
        attacker = regiment("a", Side.PLAYER, unit_class=1)
        battle = make([["A", 0, 0]], attacker, regiment("e", Side.ENEMY, y=500), scripted=True)
        assert battle.interpreter is not None
        state = battle.event_bus.unit_states["a"]
        state.charge_sound = (2, 1)
        attacker.attack_target = "e"
        battle.interpreter.stop_ended_charge_sounds()
        self.assertEqual(kinds(battle, "sound"), [])
        attacker.in_melee = True  # contact ends the charge
        battle.interpreter.stop_ended_charge_sounds()
        self.assertEqual([(e.data["cue"], e.data["packet"], e.data["effect"]) for e in kinds(battle, "sound")],
                         [("charge_stop", 2, 1)])
        self.assertIsNone(state.charge_sound)


class ReactWrapperTests(unittest.TestCase):
    def test_react_outside_a_script_matches_the_opcode(self):
        battle = make([["A", 0, 0]], regiment("p", Side.PLAYER, race=0), scripted=True)
        battle.text_resources = {}
        battle.react("p", 16)
        assert battle.interpreter is not None
        self.assertEqual([e.data["code"] for e in kinds(battle, "react")], [16])
        self.assertIsInstance(battle.interpreter, interpreter.ScriptInterpreter)


if __name__ == "__main__":
    unittest.main()
