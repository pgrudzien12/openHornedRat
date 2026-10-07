"""Magic Book visibility and paging from synthetic company data."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from whshr import script
from whshr.battle_scene import BattleScene
from whshr.campaign_scenes import MagicBookScene
from whshr.campaign_state import CampaignState
from whshr.engine import Battle, Regiment as BattleRegiment
from whshr.glue_scene import GlueScene
from whshr.magic_book import ENTRIES, ITEM_IDS, known_entries
from whshr.roster import Regiment, RosterRow, with_items
from whshr.rules import Side


def unit(whoami, spells=(), items=(), hired=True):
    commands = "".join(f"addspell:{name}\n" for name in spells)
    commands += "".join(f"addmagicitem:{name}\n" for name in items)
    root = script.parse_text(f"[ARMY]\n[UNITS]\n[addunit] name=Unit{whoami}\n{commands}"
                             "[END]\n[END]\n[END]", "synthetic")
    raw = root["children"][0]["children"][0]
    return Regiment(whoami, f"Unit{whoami}", hired, 1, 1, 0,
                    RosterRow(whoami, False, False, False, False, 0), raw=raw)


class MagicBookTests(unittest.TestCase):
    def test_magic_book_recovers_a_pickup_recorded_in_an_older_save(self):
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP")
        campaign.company = (unit(2),)
        campaign.master = campaign.company
        campaign.objective_results = {"K": (True, (13, 10, 2, 39))}  # Sword of Might, whoami 2

        scene = MagicBookScene(GlueScene("STARTCARAVAN", campaign), campaign)

        self.assertEqual(scene.known[1], (14,))
        self.assertEqual(known_entries(campaign.master)[1], (14,))
        MagicBookScene(GlueScene("STARTCARAVAN", campaign), campaign)
        self.assertEqual(script.unit_view(campaign.company[0].raw)["items"], ["ItemSwordOfMight"])

    def test_battle_pickup_is_copied_to_the_company_before_debrief(self):
        record = unit(2, items=("ItemGrudgeBringer",))
        campaign = SimpleNamespace(company=(record,), ordered_march_units=(2,), mission_cash=None)
        field_unit = BattleRegiment("unit2", "Unit2", 0, 0, 0, Side.PLAYER, whoami=2,
                                    items=("ItemGrudgeBringer", "ItemSwordOfMight"))
        scene = BattleScene()
        scene.glue_scene = SimpleNamespace(campaign=campaign)
        scene.battle = Battle(100, 100, [field_unit])
        scene.battle.objectives = SimpleNamespace(results=lambda: ())
        scene.initial_models = {"unit2": field_unit.models}

        with patch("whshr.battle_scene.casualties.after_battle"):
            scene._store_played_results()

        self.assertEqual(known_entries(campaign.company)[1], (6, 14))

    def test_new_battle_pickup_is_visible_to_the_magic_book_and_saved_company_text(self):
        from whshr.roster import company_text

        found = with_items(unit(2, items=("ItemGrudgeBringer",)),
                           ("ItemGrudgeBringer", "ItemSwordOfMight"))
        self.assertEqual(known_entries((found,))[1], (6, 14))
        saved = script.parse_text(company_text((found,)), "saved company")
        restored_items = script.unit_view(saved["children"][0]["children"][0])["items"]
        self.assertEqual(restored_items, ["ItemGrudgeBringer", "ItemSwordOfMight"])

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
