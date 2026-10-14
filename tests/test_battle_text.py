"""Battle GMTXT markup is presentation data, not spoken words."""

import unittest

from whshr.frontend.battle_text import SPELL_NAME_TEXT_BASE, display_text, fill_message, reaction_text


class BattleTextTests(unittest.TestCase):
    def test_regiment_shout_keeps_one_sender_and_readable_words(self):
        raw = "@@(f0)@@(c1)%s:@@(f1)Get_'em_lads!"
        self.assertEqual(reaction_text(raw), "Get 'em lads!")

    def test_combat_message_uses_spaces_after_substitution(self):
        raw = "@@(c2)Direct_hit_on_the_Grudgebringer_Cavalry!"
        self.assertEqual(display_text(raw), "Direct hit on the Grudgebringer Cavalry!")


class BattleMessageArgumentTests(unittest.TestCase):
    """Battle messages fill every `%s` slot from the event (templates here are invented, not game text)."""

    TEXTS = {SPELL_NAME_TEXT_BASE + 5: "Fire_Ball"}

    @staticmethod
    def unit_name(identifier):
        return {"W": "Grey Wizard", "G": "Bearers"}.get(identifier)

    def test_a_two_slot_failure_names_the_caster_and_the_spell(self):
        data = {"regiment": "W", "text_args": [["unit", "W"], ["spell", 5]]}
        self.assertEqual(fill_message("The_%s_tried_%s.", data, self.TEXTS, self.unit_name),
                         "The_Grey Wizard_tried_Fire Ball.")

    def test_slots_follow_the_argument_order(self):
        data = {"text_args": [["spell", 5], ["unit", "W"]]}
        self.assertEqual(fill_message("%s undone by %s", data, self.TEXTS, self.unit_name),
                         "Fire Ball undone by Grey Wizard")

    def test_an_item_is_named_like_a_spell(self):
        data = {"text_args": [["unit", "G"], ["item", "ItemGrudgeBringer"]]}
        self.assertEqual(fill_message("%s / %s", data, {}, self.unit_name), "Bearers / GrudgeBringer")

    def test_a_unit_gone_from_the_battle_shows_its_id(self):
        data = {"text_args": [["unit", "X"]]}
        self.assertEqual(fill_message("%s!", data, {}, self.unit_name), "X!")

    def test_a_one_slot_message_without_arguments_names_its_regiment(self):
        self.assertEqual(fill_message("Hit the %s!", {"regiment": "W"}, {}, self.unit_name), "Hit the Grey Wizard!")

    def test_a_target_name_wins_over_the_regiment(self):
        data = {"regiment": "W", "target_name": "barn"}
        self.assertEqual(fill_message("Hit the %s!", data, {}, self.unit_name), "Hit the barn!")

    def test_slots_that_cannot_all_be_filled_leave_the_message_unchanged(self):
        self.assertEqual(fill_message("%s and %s", {"regiment": "W"}, {}, self.unit_name), "%s and %s")


if __name__ == "__main__":
    unittest.main()
