"""Battlefield passive items from notes/game_rules.md §5.6."""

import random
import unittest

from whshr import combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def unit(identifier, side, *, items=(), **stats):
    return Regiment(identifier, identifier, 0, 0, 0, side, models=3, ranks=1,
                    has_leader=True, items=items, **stats)


def leader_model(regiment):
    index = regiment.living_leader_index
    assert index is not None
    return regiment.melee_models[index]


class PassiveMeleeItemTests(unittest.TestCase):
    def setUp(self):
        self.enemy = unit("E", Side.ENEMY, ws=5, toughness=5)
        self.rng = random.Random(1)

    def roll(self, items, *, leader=True, enemy=None, **stats):
        attacker = unit("A", Side.PLAYER, items=items, ws=3, strength=3, **stats)
        attacker.model_positions()
        model = leader_model(attacker) if leader else attacker.melee_models[0]
        defender = enemy or self.enemy
        defender.model_positions()
        return combat._roll_model_attacks(attacker, defender, self.rng, model=model,
                                          defender_model=defender.melee_models[0])[1]

    def test_strength_and_skill_items_affect_only_the_leader(self):
        for item, key in (("ItemSwordOfMight", "wound_need"),
                          ("ItemSwordOfHeroes", "wound_need"),
                          ("ItemBannerOfMight", "hit_need")):
            with self.subTest(item=item):
                leader = self.roll((item,), leader_ws=5)
                ordinary = self.roll((item,), leader=False, leader_ws=5)
                baseline = self.roll((), leader_ws=5)
                self.assertLess(leader[key], baseline[key])
                self.assertEqual(ordinary[key], self.roll((), leader=False, leader_ws=5)[key])

    def test_sword_of_heroes_needs_toughness_five_and_rocksplitter_inanimate(self):
        self.assertEqual(self.roll(("ItemSwordOfHeroes",), enemy=unit("T", Side.ENEMY, toughness=4))[
            "wound_need"], self.roll((), enemy=unit("T", Side.ENEMY, toughness=4))["wound_need"])
        inanimate = unit("I", Side.ENEMY, toughness=5, unit_class=9)
        self.assertEqual(self.roll(("ItemRockSplitter",), enemy=inanimate)["wound_rolls"], 6)
        self.assertLess(self.roll(("ItemRockSplitter",), enemy=inanimate)["wound_need"],
                        self.roll((), enemy=inanimate)["wound_need"])
        self.assertEqual(self.roll(("ItemRockSplitter",))["wound_rolls"], 1)

    def test_extra_wound_rolls_and_parrying(self):
        self.assertEqual(self.roll(("ItemDragonBlade",))["wound_rolls"], 2)
        self.assertEqual(self.roll(("ItemSwordOfElior",),
                                   enemy=unit("D", Side.ENEMY, race=2))["wound_rolls"], 2)
        self.assertEqual(self.roll(("ItemSwordOfElior",))["wound_rolls"], 1)
        defender = unit("P", Side.ENEMY, items=("ItemParryingBlade",))
        defender.model_positions()
        attacker = unit("A", Side.PLAYER, leader_attacks=2)
        attacker.model_positions()
        leader = leader_model(attacker)
        ordinary = attacker.melee_models[0]
        target = leader_model(defender)
        self.assertEqual(combat._roll_model_attacks(attacker, defender, self.rng, model=leader,
                                                    defender_model=target)[1]["attacks"], 1)
        self.assertEqual(combat._roll_model_attacks(attacker, defender, self.rng, model=ordinary,
                                                    defender_model=target)[1]["attacks"], 1)

    def test_defensive_armour_items_only_protect_leader(self):
        bearer = unit("P", Side.PLAYER, armour=2, leader_armour=2,
                      items=("ItemShieldOfPtolos", "ItemArmourOfTheBeard"))
        bearer.model_positions()
        self.assertEqual(bearer.model_armour(leader_model(bearer)), 4)
        self.assertEqual(bearer.model_armour(bearer.melee_models[0]), 2)
        bearer.leader_armour = 4
        self.assertEqual(bearer.model_armour(leader_model(bearer)), 4)
        bearer.leader_armour = 5
        self.assertEqual(bearer.model_armour(leader_model(bearer)), 6)
        bearer.items = ("ItemArmourOfMeteoricIron",)
        self.assertEqual(bearer.model_armour(leader_model(bearer)), 13)

    def test_leader_armour_changes_the_actual_melee_save(self):
        attacker = unit("A", Side.PLAYER, strength=3)
        attacker.model_positions()
        defender = unit("P", Side.ENEMY, armour=2, items=("ItemShieldOfPtolos",))
        defender.model_positions()
        against_leader = combat._roll_model_attacks(
            attacker, defender, self.rng, model=leader_model(attacker),
            defender_model=leader_model(defender))[1]
        against_troop = combat._roll_model_attacks(
            attacker, defender, self.rng, model=leader_model(attacker),
            defender_model=defender.melee_models[0])[1]
        self.assertLess(against_leader["save_need"], against_troop["save_need"])

    def test_dread_banner_causes_fear_and_ignores_fear(self):
        bearer = unit("B", Side.PLAYER, items=("ItemDreadBanner",))
        enemy = unit("E", Side.ENEMY, leadership=1)
        battle = Battle(100, 100, [bearer, enemy])
        script = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        state = battle.event_bus.unit_states["E"]
        self.assertFalse(script._may_engage(enemy, bearer, state, random.Random(1)))
        enemy.psychology = frozenset({"CauseFear"})
        self.assertTrue(script._may_engage(bearer, enemy,
                                          battle.event_bus.unit_states["B"], random.Random(1)))


if __name__ == "__main__":
    unittest.main()
