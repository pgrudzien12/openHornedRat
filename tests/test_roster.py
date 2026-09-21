from pathlib import Path
import tempfile
import unittest

from whshr.roster import Regiment, RosterRow, load_company
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

    def test_given_an_artillery_regiment_with_fewer_than_two_models_then_it_is_destroyed(self):
        cannons = Regiment(14, "Cannon Crew", True, 1, 3, 25, self.roster[14])

        self.assertTrue(cannons.destroyed)

    def test_given_an_infantry_regiment_with_zero_models_then_it_is_destroyed(self):
        cavalry = Regiment(2, "Grudgebringer Cavalry", True, 0, 12, 13, self.roster[2])

        self.assertTrue(cavalry.destroyed)


if __name__ == "__main__":
    unittest.main()
