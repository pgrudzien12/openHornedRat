"""Battle GMTXT markup is presentation data, not spoken words."""

import unittest

from whshr.frontend.battle_text import display_text, reaction_text


class BattleTextTests(unittest.TestCase):
    def test_regiment_shout_keeps_one_sender_and_readable_words(self):
        raw = "@@(f0)@@(c1)%s:@@(f1)Get_'em_lads!"
        self.assertEqual(reaction_text(raw), "Get 'em lads!")

    def test_combat_message_uses_spaces_after_substitution(self):
        raw = "@@(c2)Direct_hit_on_the_Grudgebringer_Cavalry!"
        self.assertEqual(display_text(raw), "Direct hit on the Grudgebringer Cavalry!")


if __name__ == "__main__":
    unittest.main()
