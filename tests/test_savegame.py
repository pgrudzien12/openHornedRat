"""Engine save games: the campaign round-trips through a slot file (notes/builtin_widgets.md §6; engine-own format)."""
import json
import tempfile
import unittest
from pathlib import Path

from whshr import roster
from whshr.campaign_state import CampaignState
from whshr.glue import MissionRef
from whshr.roster import RosterRow
from whshr.savegame import AUTOSAVE_SLOT, SaveError, SaveStore
from whshr.savegame import campaign_to_dict, restore_campaign
from whshr.troop_selection import Deployment
from tests.test_roster import MRC

ROWS = {
    2: RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=8),
    14: RosterRow(14, keep=False, for_hire=True, wizard=False, artillery=True, base_price=33),
}
GRAPH = {"flow_scripts": {}, "mission_windows": {}}


class MarchingOrderSaveTests(unittest.TestCase):
    def test_given_confirmed_marching_order_when_saved_and_restored_then_order_survives(self):
        campaign = CampaignState(GRAPH, mission_window="MAP", company=roster.parse_company(MRC, ROWS))
        campaign.commit_troop_selection(Deployment((14, 2), 0, frozenset((14, 2))))
        saved = campaign_to_dict(campaign)
        restored = CampaignState(GRAPH, mission_window="MAP", company=roster.parse_company(MRC, ROWS))
        restore_campaign(restored, saved)
        self.assertEqual(restored.ordered_march_units, (14, 2))
        self.assertEqual([item["set"]["whoami"] for item in restored.marching_army()["armies"][0]["units"]], [14, 2])


TWO_WINDOWS = {
    "flow_scripts": {"F": ({"action": "add_window", "window": "W1"}, {"action": "add_window", "window": "W2"})},
    "mission_windows": {"W1": [{"name_id": 601, "mission_ref": MissionRef("W1", 0)}],
                        "W2": [{"name_id": 602, "mission_ref": MissionRef("W2", 0)}]},
}
FIRST = MissionRef("W1", 0)


def committed_campaign():
    """The state after troop selection confirmed the only mission of W1: taken, but not yet released."""
    state = CampaignState(TWO_WINDOWS, flow="F", company=roster.parse_company(MRC, ROWS))
    state.taken_missions.add(FIRST)
    state.selected_mission = FIRST
    return state


def campaign(**fields):
    company = roster.parse_company(MRC, ROWS)
    return CampaignState(GRAPH, mission_window="MAP", company=company, master=company, **fields)


class SaveStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "saves"
        self.store = SaveStore(self.directory)

    def _played(self):
        state = campaign(flow="FLOWB", coffers=1234)
        state.flow_history = ["FLOWA", "FLOWB"]
        state.flow_step, state.tentpos, state.bonus_counter = 4, 3, -2
        state.completed = {601, 615}
        state.taken_missions = {MissionRef("mapa", 3), MissionRef("mapb", 0)}
        state.selected_mission = MissionRef("mapb", 0)
        state.army_units, state.march_units = {2, 14}, {14, 2}
        state.reinforcements = {2: 5}
        state.book_flags = {1: {26, 3}}
        state.pending_join = {14}
        state.objective_results = {"A": (True, (1, 2, 3, 4))}
        return state

    def test_given_a_played_campaign_when_saved_and_loaded_then_every_persistent_field_returns(self):
        played = self._played()
        self.store.write(1, "Before Nuln", played)
        fresh = campaign()

        self.store.load_into(1, fresh)

        for name in ("flow", "flow_history", "flow_step", "mission_window", "completed", "coffers", "army_units",
                     "march_units", "reinforcements", "selected_mission", "taken_missions", "book_flags", "tentpos",
                     "pending_join", "bonus_counter", "objective_results"):
            with self.subTest(name):
                self.assertEqual(getattr(fresh, name), getattr(played, name))

    def test_given_a_company_with_experience_and_a_fired_regiment_then_the_roster_round_trips(self):
        played = self._played()
        played.company = (roster.with_models(played.company[0], 7), roster.with_hired(played.company[1], False))
        self.store.write(0, "x", played)
        fresh = campaign()

        self.store.load_into(0, fresh)

        self.assertEqual([(r.whoami, r.models, r.hired, r.experience) for r in fresh.company],
                         [(2, 7, True, 77), (14, 3, False, 0)])

    def test_given_a_mission_in_progress_then_its_payment_terms_and_paid_flag_round_trip(self):
        from whshr.payments import CashTerms

        played = self._played()
        played.mission_cash, played.mission_paid = CashTerms(1, 100, 400, 5, 6, ("A", "B")), True
        self.store.write(0, "x", played)
        fresh = campaign()

        self.store.load_into(0, fresh)

        self.assertEqual((fresh.mission_cash, fresh.mission_paid), (played.mission_cash, True))

    def test_given_an_older_save_without_payment_terms_then_none_is_loaded(self):
        self.store.write(0, "x", self._played())
        data = json.loads(self.store.path(0).read_text())
        del data["campaign"]["mission_cash"], data["campaign"]["mission_paid"]
        self.store.path(0).write_text(json.dumps(data))
        fresh = campaign()

        self.store.load_into(0, fresh)

        self.assertEqual((fresh.mission_cash, fresh.mission_paid), (None, False))

    def test_given_a_march_order_then_it_is_saved_in_company_order(self):
        played = self._played()
        self.store.write(0, "x", played)

        self.assertEqual(json.loads(self.store.path(0).read_text())["campaign"]["march_units"], [2, 14])

    def test_given_an_empty_slot_then_the_listing_is_empty_and_loading_fails(self):
        self.assertIsNone(self.store.info(2))
        with self.assertRaises(SaveError):
            self.store.load_into(2, campaign())

    def test_given_a_saved_slot_then_the_listing_shows_its_description_cut_to_25_characters(self):
        self.store.write(3, "x" * 40, campaign())

        info = self.store.slots()[3]

        self.assertEqual(info.description, "x" * 25)
        self.assertTrue(info.saved_at)
        self.assertIsNone(self.store.slots()[AUTOSAVE_SLOT])

    def test_given_a_second_save_then_the_slot_is_replaced_and_no_temporary_file_stays(self):
        self.store.write(0, "first", campaign())
        self.store.write(0, "second", campaign())

        self.assertEqual(self.store.info(0).description, "second")
        self.assertEqual([path.name for path in self.directory.iterdir()], ["slot0.json"])

    def test_given_a_damaged_file_then_it_is_reported_and_listed_as_empty(self):
        self.directory.mkdir(parents=True)
        self.store.path(4).write_text("{not json")

        self.assertIsNone(self.store.info(4))
        with self.assertRaises(SaveError):
            self.store.load_into(4, campaign())

    def test_given_a_save_missing_a_field_then_loading_reports_damage_and_leaves_the_campaign_alone(self):
        self.store.write(0, "x", campaign(flow="SAVED"))
        data = json.loads(self.store.path(0).read_text())
        del data["campaign"]["tentpos"]
        self.store.path(0).write_text(json.dumps(data))
        fresh = campaign(flow="OTHER", coffers=77)

        with self.assertRaises(SaveError):
            self.store.load_into(0, fresh)

        self.assertEqual((fresh.flow, fresh.coffers), ("OTHER", 77))

    def test_given_a_save_that_kept_a_mission_taken_but_unreleased_then_loading_finishes_it(self):
        """The reported stall: a save from the after-mission caravan left the map with nothing to offer."""
        self.store.write(0, "old style", committed_campaign())
        loaded = CampaignState(TWO_WINDOWS, flow="F", company=committed_campaign().company)

        self.store.load_into(0, loaded)

        self.assertEqual(loaded.mission_window, "W2")
        self.assertTrue(loaded.missions)

    def test_given_a_mission_still_on_offer_then_loading_changes_nothing(self):
        state = CampaignState(TWO_WINDOWS, flow="F", company=roster.parse_company(MRC, ROWS))
        self.store.write(0, "fresh", state)
        loaded = CampaignState(TWO_WINDOWS, flow="F", company=state.company)

        self.store.load_into(0, loaded)

        self.assertEqual((loaded.mission_window, loaded.completed), ("W1", set()))

    def test_given_a_slot_number_outside_the_six_then_it_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.path(6)


if __name__ == "__main__":
    unittest.main()
