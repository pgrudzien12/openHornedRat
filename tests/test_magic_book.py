"""Magic Book visibility and paging from synthetic company data."""

import unittest
from types import SimpleNamespace

from whshr import script
from whshr.campaign_scenes import MagicBookScene
from whshr.glue_scene import GlueScene
from whshr.magic_book import ENTRIES, ITEM_IDS, known_entries
from whshr.roster import Regiment, RosterRow


def unit(whoami, spells=(), items=(), hired=True):
    commands = "".join(f"addspell:{name}\n" for name in spells)
    commands += "".join(f"addmagicitem:{name}\n" for name in items)
    root = script.parse_text(f"[ARMY]\n[UNITS]\n[addunit] name=Unit{whoami}\n{commands}"
                             "[END]\n[END]\n[END]", "synthetic")
    raw = root["children"][0]["children"][0]
    return Regiment(whoami, f"Unit{whoami}", hired, 1, 1, 0,
                    RosterRow(whoami, False, False, False, False, 0), raw=raw)


class MagicBookTests(unittest.TestCase):
    def test_starting_items_open_the_items_tab_on_the_first_known_entry(self):
        company = (unit(2, items=("ItemGrudgeBringer",)),
                   unit(3, items=("ItemPotionOfStrength",)))
        campaign = SimpleNamespace(company=company, book_flags={})
        scene = MagicBookScene(GlueScene("STARTCARAVAN", campaign), campaign)
        self.assertEqual(scene.known, ((), (6, 11)))
        self.assertEqual((scene.book, scene.entry, scene.page), (1, 6, 0))
        self.assertEqual(campaign.book_flags[1], set())
        self.assertEqual(campaign.book_flags[2], {6, 11})
        scene.set_next_start(None)
        self.assertTrue(scene.can_next)
        scene.handle("book:next", None)
        self.assertEqual((scene.entry, scene.page), (11, 0))
        scene.handle("book:back", None)
        self.assertEqual((scene.entry, scene.page), (6, 0))

    def test_college_filter_and_tab_state_remembered_across_switches(self):
        company = (unit(2, spells=("GeneralDispel", "BrightFireball"),
                        items=("ItemGrudgeBringer",), hired=False),)
        campaign = SimpleNamespace(company=company, book_flags={})
        scene = MagicBookScene(GlueScene("STARTCARAVAN", campaign), campaign)
        self.assertEqual(scene.known, ((1,), (6,)))
        self.assertEqual((scene.book, scene.entry), (0, 1))
        scene.set_next_start(123)
        scene.handle("book:next", None)
        self.assertEqual((scene.page, scene.page_start), (1, 123))
        scene.handle("book:items", None)
        self.assertEqual((scene.book, scene.entry, scene.page), (1, 6, 0))
        scene.handle("book:spells", None)
        self.assertEqual((scene.book, scene.entry, scene.page_start), (0, 1, 123))
        scene.handle("book:back", None)
        self.assertEqual((scene.page, scene.page_start), (0, 0))

    def test_non_college_spells_and_unknown_items_unlock_nothing(self):
        self.assertEqual(known_entries((unit(1, spells=("WaaaghGazeOfMork", "GeneralDispel"),
                                              items=("UnknownItem",)),)), ((), ()))
        self.assertEqual((len(ENTRIES[0]), len(ENTRIES[1]), len(ITEM_IDS)), (3, 17, 17))
