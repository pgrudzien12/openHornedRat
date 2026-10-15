from pathlib import Path
import tempfile
import unittest

from whshr import script
from whshr.roster import COST_PERCENT, Regiment, RosterRow, load_company, rank_icon, scaled_price
from whshr.script import resource_name

MRC = """[MERCARMY]
[UNITS]
; Mercenary Army
addunit:Grudgebringer<Cavalry
set:whoami=2
set:hired=1
set:s_Exp=77
banner:COMM,0
setstats:s_side=2,12,12,4
setstats:s_pntval=13
setstats:s_armr=5
setstats:s_weponame=17
endunit:
addunit:Cannon<Crew
set:whoami=14
set:hired=1
setstats:s_side=15,3,3,1
setstats:s_pntval=25
endunit:
[END]
[END]
"""


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.save_dir = self.root / "saves"  # separate from self.root: never the "installation"
        path = self.root / "FILE/SCRIPT/STRTARMY.MRC"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MRC)
        self.roster = {
            2: RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=8),
            14: RosterRow(14, keep=False, for_hire=True, wizard=False, artillery=True, base_price=33),
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_given_a_starting_company_when_loaded_then_each_regiment_merges_its_mrc_and_roster_data(self):
        company = load_company(self.root, roster=self.roster)

        self.assertEqual(len(company), 2)
        cavalry = next(r for r in company if r.whoami == 2)
        self.assertEqual((cavalry.name, cavalry.hired, cavalry.models, cavalry.points), ("Grudgebringer Cavalry", True, 12, 13))
        self.assertEqual(cavalry.experience, 77)
        self.assertEqual((cavalry.weapon_name, cavalry.armour, cavalry.banner), (17, 5, "COMM,0"))
        self.assertEqual(resource_name(cavalry.banner), "COMM")
        self.assertEqual(cavalry.row.base_price, 8)

    def test_given_a_unit_with_no_matching_roster_row_then_it_is_skipped(self):
        company = load_company(self.root, roster={2: self.roster[2]})

        self.assertEqual([r.whoami for r in company], [2])

    def test_given_a_regiment_price_then_it_is_base_price_times_current_models(self):
        cannons = Regiment(14, "Cannon Crew", True, 3, 3, 25, self.roster[14])

        self.assertEqual(cannons.price, 99)
        self.assertEqual(cannons.retainer, 9)

    def test_given_a_static_price_when_a_campaign_starts_then_it_is_scaled_by_the_default_cost_of_200_percent(self):
        self.assertEqual(COST_PERCENT, 200)
        self.assertEqual(scaled_price(8), 16)
        self.assertEqual(scaled_price(4), 8)
        self.assertEqual(scaled_price(0), 0)

    def test_given_the_starting_company_at_default_cost_then_the_first_mission_leaves_280_crowns(self):
        """notes/campaign.md §2.2 worked check: 500 + 100 - (12 x 16 + 16 x 8) = 280."""
        cavalry_row = RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=scaled_price(8))
        infantry_row = RosterRow(3, keep=False, for_hire=True, wizard=False, artillery=False, base_price=scaled_price(4))
        cavalry = Regiment(2, "Cavalry", True, 12, 12, 13, cavalry_row)
        infantry = Regiment(3, "Infantry", True, 16, 16, 13, infantry_row)

        self.assertEqual((cavalry.price, cavalry.retainer), (192, 19))
        self.assertEqual((infantry.price, infantry.retainer), (128, 12))
        self.assertEqual(500 + 100 - cavalry.price - infantry.price, 280)

    def test_given_an_artillery_regiment_with_fewer_than_two_models_then_it_is_destroyed(self):
        cannons = Regiment(14, "Cannon Crew", True, 1, 3, 25, self.roster[14])

        self.assertTrue(cannons.destroyed)

    def test_given_an_infantry_regiment_with_zero_models_then_it_is_destroyed(self):
        cavalry = Regiment(2, "Grudgebringer Cavalry", True, 0, 12, 13, self.roster[2])

        self.assertTrue(cavalry.destroyed)



class RankIconTests(unittest.TestCase):
    """notes/troop_selection.md 3.2: the Skull<n> rank icon grows with s_pntval."""

    def test_given_point_values_below_31_when_ranked_then_the_original_steps_apply(self):
        self.assertEqual([rank_icon(p) for p in (0, 7, 8, 15, 16, 23, 24, 30, 31)], [0, 0, 1, 1, 2, 2, 3, 3, 4])

    def test_given_a_regiment_promoted_past_31_points_when_ranked_then_it_keeps_the_big_skull(self):
        self.assertEqual(rank_icon(38), 4)  # the original's 5-bit mask would wrap 38 back to Skull0
        self.assertEqual(rank_icon(66), 4)


if __name__ == "__main__":
    unittest.main()
