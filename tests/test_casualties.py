"""BDD scenarios for the post-battle casualty bookkeeping: wounded, healing and disbanding between battles
(notes/casualty_bookkeeping.md section 3, worked examples of 3.7)."""
import unittest

from whshr import casualties
from whshr.campaign_state import CampaignState
from whshr.debrief import complete_debrief
from whshr.debrief_screen import UnitOutcome
from whshr.glue_runtime import StartDebrief
from whshr.roster import Regiment, RosterRow
from whshr.savegame import campaign_to_dict, restore_campaign
from tests.test_savegame import campaign as save_campaign

GRAPH = {"flow_scripts": {}, "mission_windows": {}}


def _regiment(whoami, models, orgsize=20, keep=False, artillery=False, hired=True, experience=0):
    row = RosterRow(whoami, keep=keep, for_hire=True, wizard=False, artillery=artillery, base_price=8)
    return Regiment(whoami, f"Regiment {whoami}", hired, models, orgsize, 10, row, experience=experience)


def _campaign(*regiments, marching=None):
    company = tuple(regiments)
    campaign = CampaignState(GRAPH, mission_window="MAP", company=company, master=company)
    campaign.march_units = set(marching if marching is not None else (r.whoami for r in regiments))
    campaign.army_units = {r.whoami for r in regiments if r.hired}
    return campaign


def _battle(campaign, z_met=None, **outcomes):
    """A played battle: per-whoami (models on the field, routed, casualties) and, optionally, objective Z."""
    campaign.battle_outcome = {int(key[1:]): UnitOutcome(*value) for key, value in outcomes.items()}
    campaign.objective_results = {} if z_met is None else {"Z": (z_met, (0, 0, 0, 0))}
    casualties.after_battle(campaign)


def _models(campaign, whoami):
    return next(regiment.models for regiment in campaign.company if regiment.whoami == whoami)


class WorkedExampleTests(unittest.TestCase):
    """Report 3.7: one regiment of 20 loses 10 killed and 4 routed, then fights a battle without losses."""

    def test_given_ten_killed_and_four_routed_then_six_wounded_wait_and_the_routed_rejoin_at_done(self):
        campaign = _campaign(_regiment(5, 20))

        _battle(campaign, u5=(6, 4, 14))
        self.assertEqual((campaign.wounded_last, campaign.returning), ({5: 6}, {}))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 10)
        self.assertEqual(campaign.wounded_last, {5: 6})

    def test_given_the_next_battle_without_losses_then_the_six_wounded_return(self):
        campaign = _campaign(_regiment(5, 20))
        _battle(campaign, u5=(6, 4, 14))
        casualties.heal_and_disband(campaign)

        _battle(campaign, u5=(10, 0, 0))
        self.assertEqual((campaign.wounded_last, campaign.returning), ({5: 0}, {5: 6}))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 16)  # 4 dead for good
        self.assertEqual(campaign.returning, {})

    def test_given_returning_wounded_beyond_the_original_size_then_the_regiment_is_full_and_the_excess_lost(self):
        campaign = _campaign(_regiment(5, 18))
        campaign.wounded_last = {5: 6}

        _battle(campaign, u5=(18, 0, 0))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 20)

    def test_given_the_cap_reached_then_pending_routed_models_are_lost_too(self):
        campaign = _campaign(_regiment(5, 20))
        campaign.wounded_last = {5: 6}

        _battle(campaign, u5=(16, 3, 4))  # 1 killed, 3 routed; 16 + 6 returning > 20
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 20)

    def test_given_objective_z_met_then_this_battles_wounded_are_lost_but_the_returning_still_heal(self):
        campaign = _campaign(_regiment(5, 10))
        campaign.wounded_last = {5: 6}

        _battle(campaign, z_met=True, u5=(4, 0, 6))  # lost 6 -> 3 wounded, dropped by Z
        self.assertEqual((campaign.wounded_last, campaign.returning), ({}, {5: 6}))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 10)

    def test_given_objective_z_present_but_not_met_then_the_wounded_are_kept(self):
        campaign = _campaign(_regiment(5, 20))

        _battle(campaign, z_met=False, u5=(14, 0, 6))

        self.assertEqual(campaign.wounded_last, {5: 3})

    def test_given_the_text_page_commits_the_wounded_then_they_heal_at_this_done(self):
        campaign = _campaign(_regiment(5, 20))
        _battle(campaign, u5=(6, 4, 14))

        casualties.commit_wounded(campaign)
        casualties.commit_wounded(campaign)  # drawing the page again changes nothing
        self.assertEqual((campaign.wounded_last, campaign.returning), ({}, {5: 6}))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 16)

    def test_given_an_army_regiment_that_did_not_march_then_its_wounded_still_return(self):
        campaign = _campaign(_regiment(5, 10), _regiment(6, 20), marching={6})
        campaign.wounded_last = {5: 6}

        _battle(campaign, u6=(20, 0, 0))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 16)

    def test_given_a_regiment_in_the_recruit_book_then_it_is_neither_healed_nor_disbanded(self):
        campaign = _campaign(_regiment(5, 0, hired=False), _regiment(6, 20), marching={6})
        campaign.wounded_last = {5: 6}

        _battle(campaign, u6=(20, 0, 0))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 0)


class DisbandTests(unittest.TestCase):
    def test_given_a_wiped_out_regiment_then_it_is_disbanded_and_its_wounded_never_return(self):
        campaign = _campaign(_regiment(5, 20))

        _battle(campaign, u5=(0, 0, 20))
        self.assertEqual(campaign.wounded_last, {5: 13})
        _, disbanded = casualties.heal_and_disband(campaign)

        self.assertEqual(disbanded, ["Regiment 5"])
        self.assertEqual(campaign.company, ())
        self.assertNotIn(5, campaign.march_units)
        self.assertNotIn(5, campaign.army_units)

    def test_given_a_wiped_out_keep_regiment_then_it_stays_with_no_models_and_heals_next_time(self):
        campaign = _campaign(_regiment(5, 20, keep=True))

        _battle(campaign, u5=(0, 0, 20))
        casualties.heal_and_disband(campaign)
        self.assertEqual(_models(campaign, 5), 0)
        campaign.march_units = set()
        _battle(campaign)  # the next battle, fought without it
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 13)

    def test_given_a_keep_regiment_with_nobody_left_or_wounded_then_it_gets_one_model_back(self):
        campaign = _campaign(_regiment(5, 20, keep=True))

        _battle(campaign, u5=(0, 0, 1))  # lost 1 -> 0 wounded
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 5), 1)

    def test_given_the_disband_boundary_then_below_a_fifth_is_disbanded_and_a_fifth_is_kept(self):
        for present, kept in ((3, False), (4, True)):
            with self.subTest(present=present):
                campaign = _campaign(_regiment(5, 20))
                _battle(campaign, u5=(present, 0, 20 - present))
                casualties.heal_and_disband(campaign)
                self.assertEqual(any(r.whoami == 5 for r in campaign.company), kept)

    def test_given_a_tiny_regiment_then_the_limit_is_at_least_one_model(self):
        for present, kept in ((0, False), (1, True)):
            with self.subTest(present=present):
                campaign = _campaign(_regiment(5, 4, orgsize=4))
                _battle(campaign, u5=(present, 0, 4 - present))
                casualties.heal_and_disband(campaign)
                self.assertEqual(any(r.whoami == 5 for r in campaign.company), kept)


class CommanderTests(unittest.TestCase):
    def test_given_the_commanders_regiment_wiped_out_then_one_wounded_model_comes_back(self):
        campaign = _campaign(_regiment(2, 12))

        _battle(campaign, u2=(0, 0, 12))  # lost 12 -> 7 wounded

        self.assertEqual(campaign.battle_outcome[2].routed, 1)
        self.assertEqual(campaign.wounded_last, {2: 6})
        casualties.heal_and_disband(campaign)
        self.assertEqual(_models(campaign, 2), 1)

    def test_given_the_commanders_regiment_below_a_fifth_then_it_is_never_disbanded(self):
        campaign = _campaign(_regiment(2, 12))

        _battle(campaign, u2=(1, 0, 11))
        casualties.heal_and_disband(campaign)

        self.assertEqual(_models(campaign, 2), 1)

    def test_given_the_commanders_regiment_routed_off_the_map_then_no_model_is_added(self):
        campaign = _campaign(_regiment(2, 12))

        _battle(campaign, u2=(0, 5, 5))

        self.assertEqual(campaign.battle_outcome[2].routed, 5)


class MasterRosterTests(unittest.TestCase):
    def test_given_a_battle_then_the_master_roster_keeps_the_undoubled_result(self):
        campaign = _campaign(_regiment(5, 20, experience=100))

        campaign.battle_outcome = {5: UnitOutcome(6, 4, 14, kills=3, experience_gained=30)}
        casualties.after_battle(campaign)

        master = next(r for r in campaign.master if r.whoami == 5)
        self.assertEqual((master.models, master.experience), (10, 130))


class DebriefModeTests(unittest.TestCase):
    def test_given_a_post_battle_debrief_when_done_then_wounded_return_and_the_counters_clear(self):
        campaign = _campaign(_regiment(5, 10))
        campaign.wounded_last = {5: 6}
        _battle(campaign, u5=(10, 0, 0))

        applied, _ = complete_debrief(campaign, StartDebrief(1, 6, 0, False))

        self.assertEqual(_models(campaign, 5), 16)
        self.assertIn("Regiment 5: 6 wounded return", applied)
        self.assertEqual(campaign.returning, {})

    def test_given_a_glue_debrief_when_done_then_nobody_heals(self):
        campaign = _campaign(_regiment(5, 10))
        campaign.returning = {5: 6}

        complete_debrief(campaign, StartDebrief(1, 4, 0, False))

        self.assertEqual(_models(campaign, 5), 10)
        self.assertEqual(campaign.returning, {5: 6})

    def test_given_wounded_counters_when_saved_and_restored_then_they_survive(self):
        campaign = save_campaign()
        campaign.wounded_last, campaign.returning = {2: 6}, {14: 2}
        restored = save_campaign()

        restore_campaign(restored, campaign_to_dict(campaign))

        self.assertEqual((restored.wounded_last, restored.returning), ({2: 6}, {14: 2}))

    def test_given_a_battle_merged_into_the_master_roster_when_saved_and_restored_then_the_merge_survives(self):
        campaign = save_campaign()
        campaign.battle_outcome = {2: UnitOutcome(5, 0, 7, experience_gained=20)}
        casualties.after_battle(campaign)
        restored = save_campaign()

        restore_campaign(restored, campaign_to_dict(campaign))

        master = next(r for r in restored.master if r.whoami == 2)
        self.assertEqual((master.models, master.experience), (5, 97))

class CampaignOverTests(unittest.TestCase):
    """notes/debrief_evaluation.md 3.1: the test that precedes the debrief and every merge."""

    def _over(self, outcome, **objectives):
        campaign = _campaign(_regiment(2, 20))
        campaign.battle_outcome = {2: UnitOutcome(*outcome)}
        campaign.objective_results = {letter: (met, (0, 0, 0, 0)) for letter, met in objectives.items()}
        return casualties.campaign_over_movie(campaign)

    def test_given_a_surviving_commander_when_g_or_y_is_met_then_the_campaign_is_over_with_death02(self):
        self.assertEqual(self._over((10, 0, 10), G=True), "death02")
        self.assertEqual(self._over((10, 0, 10), Y=True), "death02")
        self.assertIsNone(self._over((10, 0, 10), G=False, Y=False))
        self.assertIsNone(self._over((10, 0, 10)))

    def test_given_a_surviving_commander_when_only_z_is_met_then_the_campaign_goes_on(self):
        self.assertIsNone(self._over((10, 0, 10), Z=True))

    def test_given_a_wiped_out_commander_when_z_is_met_then_the_campaign_is_over_with_death01(self):
        # Dead = no models, none routed and no wounded: at most one model lost (1 killed -> 0 wounded).
        self.assertEqual(self._over((0, 0, 1), Z=True), "death01")

    def test_given_a_wiped_out_commander_without_z_then_the_campaign_goes_on_even_if_g_is_met(self):
        self.assertIsNone(self._over((0, 0, 1), G=True))
        self.assertIsNone(self._over((0, 0, 1)))
        campaign = _campaign(_regiment(2, 1))
        _battle(campaign, z_met=False, u2=(0, 0, 1))  # the P1 fallback: one routed model, merged back
        self.assertEqual(_models(campaign, 2), 1)
        self.assertEqual(campaign.battle_outcome[2].routed, 1)

    def test_given_a_commander_regiment_with_wounded_left_then_it_is_not_dead_for_the_test(self):
        self.assertEqual(self._over((0, 0, 20), Z=True, G=True), "death02")  # 13 wounded survive: G applies
        self.assertIsNone(self._over((0, 0, 2), Z=True))  # 1 wounded survives: Z alone does not end it

    def test_given_no_outcome_for_the_commander_then_there_is_no_campaign_over(self):
        campaign = _campaign(_regiment(5, 20))
        campaign.objective_results = {"G": (True, (0, 0, 0, 0))}
        self.assertIsNone(casualties.campaign_over_movie(campaign))


if __name__ == "__main__":
    unittest.main()