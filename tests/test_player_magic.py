"""The player's Magic order: the spell click pays and selects, the target click gives the cast order
(game_rules.md "Winds of magic and casting"; notes/spell_lasting_effects.md 0.2, 5.4; notes/script_magic.md 4)."""

import unittest

from whshr import interpreter, magic, spell_effects
from whshr.engine import Battle, Regiment
from whshr.rules import Side

AMBER = ("AmberHuntingSpear", "AmberFlockOfDoom", "AmberCurseOfAnraheir", "GeneralDispel")
CELESTIAL = ("CelestialAzureBlades", "CelestialLightning")


def wizard(identifier: str = "W", side: Side = Side.PLAYER, spells: tuple[str, ...] = AMBER) -> Regiment:
    return Regiment(identifier, identifier, 100, 200, 0, side, models=1, ranks=1,
                    unit_class=interpreter.WIZARD_CLASS, spells=magic.spell_codes(spells))


class PlayerMagicCase(unittest.TestCase):
    def make(self, *units: Regiment, power: int = 4, deploy: bool = False) -> Battle:
        self.battle = Battle(5000, 5000, list(units) or [wizard()], seed=1995, deploy=deploy)
        self.battle.event_bus._power = magic.PowerPools(power, 8)
        return self.battle

    def queued(self, identifier: str = "W") -> list[interpreter.Event]:
        return list(self.battle.event_bus.unit_states[identifier].event_queue)


class SpellClickTests(PlayerMagicCase):
    def test_clicking_a_targeted_spell_pays_selects_and_waits_for_the_target(self):
        battle = self.make(power=4)
        spear = magic.SPELL_CODES["amberhuntingspear"]
        self.assertTrue(battle.select_spell("W", spear))
        self.assertEqual(battle.player_power, 4 - (magic.cost(spear) or 0))
        self.assertTrue(spell_effects.spell_selected(battle, "W", spear))
        self.assertEqual(self.queued(), [])

    def test_a_selected_spell_cannot_be_clicked_again(self):
        battle = self.make(power=8)
        spear = magic.SPELL_CODES["amberhuntingspear"]
        battle.select_spell("W", spear)
        self.assertFalse(battle.spell_usable("W", spear))
        with self.assertRaises(ValueError):
            battle.select_spell("W", spear)

    def test_a_spell_costing_more_than_the_pool_is_unusable(self):
        battle = self.make(power=2)
        curse = magic.SPELL_CODES["amberCurseOfAnraheir".casefold()]
        self.assertEqual(magic.cost(curse), 3)
        self.assertFalse(battle.spell_usable("W", curse))
        with self.assertRaises(ValueError):
            battle.select_spell("W", curse)
        self.assertEqual(battle.player_power, 2)

    def test_the_cost_may_empty_the_pool(self):
        battle = self.make(power=2)
        flock = magic.SPELL_CODES["amberflockofdoom"]
        battle.select_spell("W", flock)
        self.assertEqual(battle.player_power, 0)

    def test_only_a_player_caster_with_the_spell_may_click_it(self):
        enemy = wizard("E", Side.ENEMY)
        plain = Regiment("P", "P", 0, 0, 0, Side.PLAYER, models=5, ranks=1, spells=magic.spell_codes(AMBER))
        battle = self.make(wizard(), enemy, plain, power=8)
        spear = magic.SPELL_CODES["amberhuntingspear"]
        lightning = magic.SPELL_CODES["celestiallightning"]
        self.assertFalse(battle.spell_usable("E", spear))
        self.assertFalse(battle.spell_usable("P", spear))
        self.assertFalse(battle.spell_usable("W", lightning))

    def test_no_spell_click_during_deployment(self):
        battle = self.make(power=8, deploy=True)
        with self.assertRaises(ValueError):
            battle.select_spell("W", magic.SPELL_CODES["amberhuntingspear"])


class TargetClickTests(PlayerMagicCase):
    def test_the_target_click_clears_the_selection_and_queues_the_cast_order(self):
        battle = self.make(power=4)
        spear = magic.SPELL_CODES["amberhuntingspear"]
        battle.select_spell("W", spear)
        battle.order_cast("W", spear, 300.6, 900.2)
        self.assertFalse(spell_effects.spell_selected(battle, "W", spear))
        [event] = self.queued()
        self.assertEqual((event.code, event.parameter, event.x, event.y, event.source), (0x2B, spear, 300, 900, None))
        self.assertEqual(battle.player_power, 2)

    def test_a_target_click_without_a_selection_is_refused(self):
        battle = self.make(power=4)
        with self.assertRaises(ValueError):
            battle.order_cast("W", magic.SPELL_CODES["amberhuntingspear"], 0, 0)
        self.assertEqual(self.queued(), [])

    def test_cancelled_targeting_clears_the_selection_without_a_refund(self):
        battle = self.make(power=4)
        spear = magic.SPELL_CODES["amberhuntingspear"]
        battle.select_spell("W", spear)
        battle.cancel_spell_target("W", spear)
        self.assertFalse(spell_effects.spell_selected(battle, "W", spear))
        self.assertEqual(battle.player_power, 2)
        self.assertTrue(battle.spell_usable("W", spear))


class NoTargetSpellTests(PlayerMagicCase):
    def test_azure_blades_is_ordered_on_the_click_at_the_casters_position(self):
        battle = self.make(wizard(spells=CELESTIAL), power=1)
        blades = spell_effects.AZURE_BLADES
        self.assertFalse(battle.select_spell("W", blades))
        [event] = self.queued()
        self.assertEqual((event.code, event.parameter, event.x, event.y), (0x2B, blades, 100, 200))
        self.assertEqual(battle.player_power, 0)
        self.assertFalse(spell_effects.spell_selected(battle, "W", blades))

    def test_dispel_magic_stays_selected_for_the_battle_after_the_click(self):
        battle = self.make(power=8)
        dispel = spell_effects.DISPEL_MAGIC
        self.assertFalse(battle.select_spell("W", dispel))
        self.assertTrue(spell_effects.dispel_selected(battle, "W"))
        self.assertFalse(battle.spell_usable("W", dispel))


class CtrlClickTests(PlayerMagicCase):
    def test_ctrl_click_cancels_the_casters_effects_of_that_spell(self):
        target = Regiment("E", "E", 100, 500, 256, Side.ENEMY, models=5, ranks=1)
        battle = self.make(wizard(), target, power=8)
        curse = spell_effects.CURSE
        self.assertTrue(spell_effects.launch(battle, curse, battle.regiments["W"], -1, 100, 500))
        self.assertTrue(spell_effects.spell_active(battle, "W", curse))
        power = battle.player_power
        self.assertTrue(battle.cancel_spell_effects("W", curse))
        self.assertFalse(spell_effects.spell_active(battle, "W", curse))
        self.assertEqual(battle.player_power, power)
        self.assertFalse(battle.cancel_spell_effects("W", curse))


if __name__ == "__main__":
    unittest.main()
