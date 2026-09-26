"""The caravan's Army Records: hire/fire with coffers, the reinforcement offer, regiments joining the company
and the housekeeping when a recruit caravan is left (notes/builtin_widgets.md §2, notes/campaign.md §2.4;
issue #145)."""
import tempfile
import unittest
from pathlib import Path

from whshr import script
from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign_scenes import ArmyRecordsScene
from whshr.campaign_state import CampaignState
from whshr.catalog import build
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.reinforcements import ReinforcementLedger
from whshr.roster import Regiment, RosterRow, load_company, with_models
from whshr.roster_book import RosterBook
from whshr.scenes import SceneAssets, SceneMachine


def regiment(whoami, hired=True, models=10, orgsize=None, for_hire=True, base_price=10):
    row = RosterRow(whoami, keep=False, for_hire=for_hire, wizard=False, artillery=False, base_price=base_price)
    return Regiment(whoami, f"Regiment{whoami}", hired, models, orgsize or models, 0, row)


def book(company, coffers=1000, reinforcements=None, pays=True):
    return RosterBook(company, coffers=coffers, reinforcements=reinforcements or {}, pays=pays)


class HireOnlyBookTests(unittest.TestCase):
    def test_given_a_regiment_for_hire_when_hired_then_its_price_leaves_the_coffers_and_it_joins_the_march(self):
        model = book([regiment(2, for_hire=False), regiment(5, hired=False, models=10, base_price=12)])

        self.assertTrue(model.toggle_hired(5))

        self.assertTrue(model.hired[5])
        self.assertEqual(model.coffers, 1000 - 120)
        self.assertEqual(model.selection, [2, 5])

    def test_given_a_regiment_hired_this_visit_when_fired_then_the_price_is_refunded(self):
        model = book([regiment(2, for_hire=False), regiment(5, hired=False, base_price=12)])
        model.toggle_hired(5)

        model.toggle_hired(5)

        self.assertFalse(model.hired[5])
        self.assertEqual(model.coffers, 1000)
        self.assertEqual(model.selection, [2])

    def test_given_a_regiment_already_hired_when_the_book_opened_then_it_cannot_be_fired(self):
        model = book([regiment(2, for_hire=False), regiment(6, hired=True)])

        self.assertFalse(model.hire_fire_enabled(6))
        self.assertFalse(model.toggle_hired(6))
        self.assertTrue(model.hired[6])

    def test_given_coffers_below_the_price_then_hiring_is_disabled_and_changes_nothing(self):
        model = book([regiment(2, for_hire=False), regiment(5, hired=False, base_price=12)], coffers=119)

        self.assertFalse(model.hire_fire_enabled(5))
        self.assertFalse(model.toggle_hired(5))
        self.assertEqual(model.coffers, 119)
        self.assertFalse(model.hired[5])

    def test_given_a_regiment_that_is_not_for_hire_then_it_can_never_be_hired(self):
        model = book([regiment(2, for_hire=False), regiment(7, hired=False, for_hire=False)])

        self.assertFalse(model.hire_fire_enabled(7))

    def test_given_the_money_free_book_then_hiring_costs_nothing_and_any_for_hire_regiment_can_be_toggled(self):
        model = book([regiment(2, for_hire=False), regiment(6, hired=True)], pays=False)

        self.assertTrue(model.hire_fire_enabled(6))
        model.toggle_hired(6)

        self.assertFalse(model.hired[6])
        self.assertEqual(model.coffers, 1000)

    def test_given_a_full_march_list_when_hiring_then_the_regiment_is_hired_but_not_marching(self):
        company = [regiment(2, for_hire=False)] + [regiment(whoami, hired=False) for whoami in range(3, 30)]
        model = RosterBook(company, coffers=10**6, reinforcements={}, pays=True, limit=8)
        for whoami in range(3, 12):
            model.toggle_hired(whoami)

        self.assertEqual(len(model.selection), 8)
        self.assertTrue(model.hired[11])
        self.assertNotIn(11, model.selection)

    def test_given_a_hire_when_the_book_is_aborted_then_the_flags_return_but_the_coffers_stay_spent(self):
        model = book([regiment(2, for_hire=False), regiment(5, hired=False, base_price=12)])
        model.toggle_hired(5)

        model.restore_book_hired(model.hired_at_open)

        self.assertFalse(model.hired[5])
        self.assertEqual(model.coffers, 1000 - 120)  # the original charged every click at once
        self.assertEqual(model.selection, [2])

    def test_given_nothing_changed_then_the_book_is_not_dirty(self):
        model = book([regiment(2, for_hire=False), regiment(5, hired=False)])

        self.assertFalse(model.dirty)
        model.toggle_hired(5)
        self.assertTrue(model.dirty)


class ReinforcementTests(unittest.TestCase):
    def _ledger(self, models, orgsize, pool):
        company = {5: regiment(5, models=models, orgsize=orgsize)}
        return ReinforcementLedger(company, {5: pool}), company

    def test_given_room_in_the_regiment_then_the_offer_is_the_pool_capped_by_the_missing_men(self):
        for models, orgsize, pool, offer in ((10, 16, 4, 4), (10, 16, 9, 6), (16, 16, 5, 0), (10, 16, 0, 0)):
            with self.subTest(models=models, pool=pool):
                ledger, _ = self._ledger(models, orgsize, pool)

                self.assertEqual(ledger.offered[5], offer)
                self.assertEqual(ledger.has_offer(5), offer > 0)

    def test_given_an_offer_when_a_man_is_added_then_the_regiment_grows_at_once_up_to_the_offer(self):
        ledger, company = self._ledger(10, 16, 2)

        self.assertTrue(ledger.increase(5))
        self.assertTrue(ledger.increase(5))
        self.assertFalse(ledger.increase(5))

        self.assertEqual(company[5].models, 12)
        self.assertEqual(ledger.offer_left(5), 0)
        self.assertEqual(company[5].price, 120)

    def test_given_men_taken_when_one_is_removed_then_the_regiment_shrinks_but_never_below_the_start(self):
        ledger, company = self._ledger(10, 16, 3)
        ledger.increase(5)

        self.assertTrue(ledger.decrease(5))
        self.assertFalse(ledger.decrease(5))

        self.assertEqual(company[5].models, 10)

    def test_given_men_taken_when_the_offer_is_answered_then_the_pool_keeps_the_untaken_rest(self):
        ledger, company = self._ledger(10, 16, 5)
        ledger.increase(5)
        ledger.increase(5)

        self.assertEqual(ledger.take(5), 2)

        self.assertEqual(ledger.available[5], 3)
        self.assertFalse(ledger.has_offer(5))
        self.assertEqual(company[5].models, 12)

    def test_given_an_abort_then_men_and_pool_return_to_the_opening_state(self):
        ledger, company = self._ledger(10, 16, 5)
        ledger.increase(5)
        ledger.take(5)

        ledger.revert()

        self.assertEqual(company[5].models, 10)
        self.assertEqual(ledger.available[5], 5)
        self.assertFalse(ledger.changed)

    def test_given_two_regiments_then_each_gets_its_own_offer(self):
        company = {5: regiment(5, models=8, orgsize=10), 6: regiment(6, models=10, orgsize=10)}

        ledger = ReinforcementLedger(company, {5: 7, 6: 7})

        self.assertEqual((ledger.offered[5], ledger.offered[6]), (2, 0))

    def test_given_a_regiment_read_from_a_script_when_its_size_changes_then_the_written_node_follows(self):
        text = "[MERCARMY]\n[UNITS]\naddunit:Some<Unit\nset:whoami=5\nset:hired=1\nsetstats:s_side=2,12,9,1\nendunit:\n[END]\n[END]\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "FILE/SCRIPT/STRTARMY.MRC"
            path.parent.mkdir(parents=True)
            path.write_text(text)
            row = RosterRow(5, keep=False, for_hire=True, wizard=False, artillery=False, base_price=10)
            (loaded,) = load_company(directory, roster={5: row})

            grown = with_models(loaded, 11)

            self.assertEqual(grown.models, 11)
            self.assertEqual(loaded.models, 9)
            unit = script.unit_view(grown.raw)
            self.assertEqual(unit["stats"]["s_side"], [2, 12, 11, 1])


class CampaignRosterTests(unittest.TestCase):
    def _campaign(self, company, master=(), save_dir=None, coffers=500):
        return CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP", coffers=coffers,
                             company=tuple(company), master=tuple(master), save_dir=save_dir)

    def test_given_pending_regiments_when_the_caravan_opens_then_they_join_hired_unless_for_hire(self):
        master = [regiment(whoami, for_hire=whoami == 9) for whoami in (2, 5, 9)]
        campaign = self._campaign([master[0]], master)
        campaign.mark_pending_join(5)
        campaign.mark_pending_join(9)

        merged = campaign.merge_pending_joins()

        self.assertEqual(merged, (5, 9))
        by_whoami = {r.whoami: r for r in campaign.company}
        self.assertTrue(by_whoami[5].hired)
        self.assertFalse(by_whoami[9].hired)  # waits in the recruit book
        self.assertEqual(campaign.pending_join, set())
        self.assertEqual(campaign.army_units, {2, 5})

    def test_given_a_pending_regiment_the_master_roster_lacks_then_it_stays_pending(self):
        campaign = self._campaign([regiment(2)], [regiment(2)])
        campaign.mark_pending_join(33)

        self.assertEqual(campaign.merge_pending_joins(), ())
        self.assertEqual(campaign.pending_join, {33})

    def test_given_a_regiment_already_in_the_company_then_a_second_join_does_not_reset_it(self):
        master = [regiment(5, models=16)]
        campaign = self._campaign([with_models(regiment(5, models=6, orgsize=16), 6)], master)
        campaign.mark_pending_join(5)

        campaign.merge_pending_joins()

        self.assertEqual([r.models for r in campaign.company], [6])

    def test_given_unitjoinmission_and_unitleavemission_then_the_company_and_march_follow(self):
        master = [regiment(whoami) for whoami in (2, 21)]
        campaign = self._campaign([master[0]], master)

        campaign.join_mission(21)
        self.assertEqual([r.whoami for r in campaign.company], [2, 21])
        self.assertEqual(campaign.march_units, {21})
        self.assertTrue(campaign.is_unit_in_army(21))

        campaign.leave_mission(21)
        self.assertEqual([r.whoami for r in campaign.company], [2])
        self.assertEqual(campaign.march_units, set())

    def test_given_leaving_a_recruit_caravan_then_unhired_regiments_go_and_reinforcements_are_cleared(self):
        campaign = self._campaign([regiment(2), regiment(5, hired=False), regiment(6)])
        campaign.add_reinforcements(6, 3)

        campaign.leave_caravan()

        self.assertEqual([r.whoami for r in campaign.company], [2, 6])
        self.assertEqual(campaign.reinforcements, {})

    def test_given_a_done_book_then_hires_coffers_march_and_reinforcements_reach_the_campaign(self):
        company = [regiment(2, for_hire=False), regiment(5, hired=False, base_price=12),
                   regiment(6, models=8, orgsize=12)]
        campaign = self._campaign(company)
        campaign.add_reinforcements(6, 3)
        model = RosterBook(campaign.company, coffers=campaign.coffers, reinforcements=campaign.reinforcements, pays=True)
        model.toggle_hired(5)
        model.ledger.increase(6)
        model.ledger.increase(6)
        model.ledger.take(6)

        campaign.apply_army_book(model)

        by_whoami = {r.whoami: r for r in campaign.company}
        self.assertTrue(by_whoami[5].hired)
        self.assertEqual(by_whoami[6].models, 10)
        self.assertEqual(campaign.coffers, 500 - 120)
        self.assertEqual(campaign.march_units, {2, 5})
        self.assertEqual(campaign.reinforcements, {6: 1})

    def test_given_an_aborted_paying_book_then_the_hire_is_undone_but_the_coffers_stay_charged(self):
        campaign = self._campaign([regiment(2, for_hire=False), regiment(5, hired=False, base_price=12)])
        model = RosterBook(campaign.company, coffers=campaign.coffers, reinforcements={}, pays=True)
        model.toggle_hired(5)
        model.restore_book_hired(model.hired_at_open)

        campaign.abort_army_book(model)

        self.assertFalse(any(r.hired for r in campaign.company if r.whoami == 5))
        self.assertEqual(campaign.coffers, 500 - 120)

    def test_given_a_save_dir_when_a_book_is_done_then_the_army_file_keeps_unhired_regiments(self):
        with tempfile.TemporaryDirectory() as directory:
            text = ("[MERCARMY]\n[UNITS]\n"
                    "addunit:A\nset:whoami=2\nset:hired=1\nsetstats:s_side=2,10,10,1\nendunit:\n"
                    "addunit:B\nset:whoami=5\nset:hired=0\nsetstats:s_side=2,10,10,1\nendunit:\n[END]\n[END]\n")
            path = Path(directory) / "game/FILE/SCRIPT/STRTARMY.MRC"
            path.parent.mkdir(parents=True)
            path.write_text(text)
            rows = {2: RosterRow(2, False, False, False, False, 10), 5: RosterRow(5, False, True, False, False, 10)}
            company = load_company(Path(directory) / "game", roster=rows)
            saves = Path(directory) / "saves"
            campaign = self._campaign(company, save_dir=saves)
            model = RosterBook(campaign.company, coffers=500, reinforcements={}, pays=False)
            model.toggle_hired(5)

            campaign.apply_army_book(model)

            written = script.units_of(script.parse(str(saves / "ARMY.MRC")))
            flags = {script.unit_view(u)["set"]["whoami"]: script.unit_view(u)["set"]["hired"] for u in written}
            self.assertEqual(flags, {2: 1, 5: 1})
            model2 = RosterBook(campaign.company, coffers=500, reinforcements={}, pays=False)
            model2.toggle_hired(5)  # fire again
            campaign.apply_army_book(model2)
            written = script.units_of(script.parse(str(saves / "ARMY.MRC")))
            flags = {script.unit_view(u)["set"]["whoami"]: script.unit_view(u)["set"]["hired"] for u in written}
            self.assertEqual(flags, {2: 1, 5: 0})


CARAVAN = "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\nset:palindex=3\n[END]\n" \
          "[HOTSPOT]\nset:x=1\nset:y=1\nset:vx=9\nset:vy=9\nscript:pop.wnd\nres:%s\n[END]"
TALKING = CARAVAN % "UnwindMission" + "\n[HOTSPOT]\nset:x=2\nset:y=2\nset:vx=9\nset:vy=9\nset:res=160\nset:clickres=%d\nset:clickrescnt=%d\n" \
                                    "script:null.wnd\nres:DietrichSpeech\n[END]"
RESOURCES = {
    "CARAVANRECRUITANDRESUME": CARAVAN % "PopAndResume",
    "AFTERWINDOW": "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=1\nset:vy=1\n[END]",
    "CARAVANAFTERMISSION": CARAVAN % "UnwindMission",
    "CARAVANAFTERMISSIONWITHRECRUIT": CARAVAN % "UnwindMission",
    "CARAVANAFTERENCOUNTER": CARAVAN % "UnwindMission",
    "CARAVANAFTERENCOUNTERWITHRECRUIT": CARAVAN % "UnwindMission",
    "INFOCARAVANTLK": TALKING % (931, 1),
    "INFOCARAVANONE": TALKING % (947, 0),
    "TALKSCRIPT": "[RUN]\n[START]\ngocaravan:infoTLK\n[END]",
    "ONESCRIPT": "[RUN]\n[START]\ngocaravan:infoONE\n[END]",
    "SELECTSCRIPT": "[RUN]\n[START]\ngocaravan:select\n[END]",
    "RESUMESCRIPT": "[RUN]\n[START]\ngocaravan:resume\n[END]",
    "RECRUITSCRIPT": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\ngocaravan:recruit\nopenwindow:res=AFTERWINDOW\n[END]",
}


class CaravanBookWiringTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(), {})
        self.context.glue = GlueContent.from_data(resources=RESOURCES)

    def _campaign(self, company, master=()):
        return CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP", coffers=500,
                             company=tuple(company), master=tuple(master))

    def _recruit_caravan(self, campaign):
        machine = SceneMachine(GlueScene("RECRUITSCRIPT", campaign), self.context)
        return machine, machine.active

    def test_given_a_recruit_caravan_when_its_army_book_hotspot_is_released_then_the_paying_book_opens(self):
        machine, _ = self._recruit_caravan(self._campaign([regiment(2, for_hire=False), regiment(5, hired=False)]))

        machine.handle(GlueInput("hotspot-release", "HireOnlyArmyBook"))

        self.assertIsInstance(machine.active, ArmyRecordsScene)
        self.assertTrue(machine.active.model.pays)
        self.assertEqual(machine.active.whoami, 2)

    def test_given_the_plain_army_book_hotspot_then_the_book_charges_nothing(self):
        machine, _ = self._recruit_caravan(self._campaign([regiment(2, for_hire=False), regiment(5, hired=False)]))

        machine.handle(GlueInput("hotspot-release", "ArmyBook"))

        self.assertIsInstance(machine.active, ArmyRecordsScene)
        self.assertFalse(machine.active.model.pays)

    def test_given_a_hire_when_the_book_is_done_then_the_same_caravan_is_shown_and_the_campaign_updated(self):
        for coffers_before, price_each in ((500, 12), (900, 30)):  # two different companies
            with self.subTest(price=price_each):
                campaign = self._campaign([regiment(2, for_hire=False), regiment(5, hired=False, base_price=price_each)])
                campaign.coffers = coffers_before
                machine, caravan = self._recruit_caravan(campaign)
                machine.handle(GlueInput("hotspot-release", "HireOnlyArmyBook"))
                machine.handle("book:next")
                machine.handle("book:hire-fire")

                machine.handle("book:done")

                self.assertIs(machine.active, caravan)
                self.assertEqual(caravan.runtime.state.pending.kind, "caravan")
                self.assertEqual(campaign.coffers, coffers_before - 10 * price_each)
                self.assertIn(5, campaign.army_units)

    def test_given_a_book_aborted_then_the_caravan_returns_with_the_flags_restored(self):
        campaign = self._campaign([regiment(2, for_hire=False), regiment(5, hired=False)])
        machine, caravan = self._recruit_caravan(campaign)
        machine.handle(GlueInput("hotspot-release", "HireOnlyArmyBook"))
        machine.handle("book:next")
        machine.handle("book:hire-fire")

        machine.handle("book:abort")

        self.assertIs(machine.active, caravan)
        self.assertFalse(next(r for r in campaign.company if r.whoami == 5).hired)

    def test_given_a_recruit_caravan_left_by_popandresume_then_regiments_not_hired_are_dropped(self):
        campaign = self._campaign([regiment(2, for_hire=False), regiment(5, hired=False)])
        campaign.add_reinforcements(2, 4)
        machine, _ = self._recruit_caravan(campaign)

        machine.handle(GlueInput("hotspot-release", "PopAndResume"))

        self.assertEqual([r.whoami for r in campaign.company], [2])
        self.assertEqual(campaign.reinforcements, {})

    def test_given_addunit_before_a_caravan_then_the_recruit_book_lists_the_regiment_for_hire(self):
        master = [regiment(2, for_hire=False), regiment(5, for_hire=True)]
        campaign = self._campaign([master[0]], master)
        campaign.mark_pending_join(5)

        machine, _ = self._recruit_caravan(campaign)
        machine.handle(GlueInput("hotspot-release", "HireOnlyArmyBook"))

        book_scene = machine.active
        self.assertEqual(book_scene.company_ids, (2, 5))
        self.assertTrue(book_scene.model.hire_fire_enabled(5))

    def test_given_reinforcements_when_taken_in_the_book_then_the_company_grows_and_the_pool_shrinks(self):
        campaign = self._campaign([regiment(2, models=8, orgsize=12, for_hire=False)])
        campaign.add_reinforcements(2, 3)
        machine, _ = self._recruit_caravan(campaign)
        machine.handle(GlueInput("hotspot-release", "ArmyBook"))
        for event in ("reinf:up", "reinf:up", "reinf:take", "book:done"):
            machine.handle(event)

        self.assertEqual(campaign.company[0].models, 10)
        self.assertEqual(campaign.reinforcements, {2: 1})

    def test_given_reinforcements_when_the_book_is_aborted_then_nothing_is_kept(self):
        campaign = self._campaign([regiment(2, models=8, orgsize=12, for_hire=False)])
        campaign.add_reinforcements(2, 3)
        machine, _ = self._recruit_caravan(campaign)
        machine.handle(GlueInput("hotspot-release", "ArmyBook"))
        for event in ("reinf:up", "reinf:take", "book:abort"):
            machine.handle(event)

        self.assertEqual(campaign.company[0].models, 8)
        self.assertEqual(campaign.reinforcements, {2: 3})

    def _caravan_for(self, script_name, campaign, resources=None):
        if resources is not None:
            self.context.glue = GlueContent.from_data(resources=resources)
        machine = SceneMachine(GlueScene(script_name, campaign), self.context)
        return [window.name for window in machine.active.runtime.state.windows]

    def test_given_a_regiment_for_hire_waiting_when_a_caravan_is_requested_then_the_with_recruit_window_opens(self):
        for script_name, plain, recruit in (("SELECTSCRIPT", "CARAVANAFTERMISSION", "CARAVANAFTERMISSIONWITHRECRUIT"),
                                            ("RESUMESCRIPT", "CARAVANAFTERENCOUNTER", "CARAVANAFTERENCOUNTERWITHRECRUIT")):
            with self.subTest(script=script_name):
                waiting = self._campaign([regiment(2, for_hire=False), regiment(5, hired=False)])
                self.assertEqual(self._caravan_for(script_name, waiting), [recruit])
                self.assertEqual(self._caravan_for(script_name, self._campaign([regiment(2, for_hire=False)])), [plain])

    def test_given_only_reinforcements_waiting_then_the_plain_window_opens_whether_or_not_there_is_room(self):
        for models in (8, 12):
            with self.subTest(models=models):
                campaign = self._campaign([regiment(2, for_hire=False), regiment(3, models=models, orgsize=12)])
                campaign.add_reinforcements(3, 5)

                self.assertEqual(self._caravan_for("SELECTSCRIPT", campaign), ["CARAVANAFTERMISSION"])

    def test_given_a_regiment_for_hire_already_hired_then_the_plain_window_opens(self):
        campaign = self._campaign([regiment(2, for_hire=False), regiment(5, hired=True)])

        self.assertEqual(self._caravan_for("SELECTSCRIPT", campaign), ["CARAVANAFTERMISSION"])

    def test_given_an_installation_without_the_with_recruit_window_then_the_plain_one_opens(self):
        resources = {k: v for k, v in RESOURCES.items() if not k.endswith("WITHRECRUIT")}
        campaign = self._campaign([regiment(2, for_hire=False), regiment(5, hired=False)])

        self.assertEqual(self._caravan_for("SELECTSCRIPT", campaign, resources), ["CARAVANAFTERMISSION"])

    def test_given_a_caravan_when_it_opens_then_dietrich_stays_silent_until_clicked(self):
        machine = SceneMachine(GlueScene("TALKSCRIPT", self._campaign([regiment(2)])), self.context)

        self.assertFalse(machine.active.runtime.state.speech_active)
        self.assertEqual(machine.active.runtime.state.dialogue_text, "")

    def test_given_dietrich_is_clicked_then_he_speaks_all_his_lines_in_red_in_the_caravan_window(self):
        for script_name, window, first, count, lines in (("TALKSCRIPT", "INFOCARAVANTLK", 931, 2, (932,)),
                                                          ("ONESCRIPT", "INFOCARAVANONE", 947, 1, ())):
            with self.subTest(script=script_name):
                machine = SceneMachine(GlueScene(script_name, self._campaign([regiment(2)])), self.context)
                state = machine.active.runtime.state

                machine.handle(GlueInput("hotspot-speech", f"{first}:{count}"))

                self.assertTrue(state.speech_active)
                self.assertEqual(state.speech_lines, lines)
                self.assertEqual(state.dialogue_line_colour, "red")
                self.assertEqual(state.dialogue_window_name, window)  # the view draws text of a window it shows

    def test_given_dietrich_is_still_talking_when_the_caravan_is_left_then_his_speech_stops(self):
        resources = {**RESOURCES, "TALKSCRIPT": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\ngocaravan:infoTLK\n[END]",
                     "INFOCARAVANTLK": (TALKING % (931, 1)).replace("UnwindMission", "PopAndResume")}
        self.context.glue = GlueContent.from_data(resources=resources)
        machine = SceneMachine(GlueScene("TALKSCRIPT", self._campaign([regiment(2)])), self.context)
        scene = machine.active
        machine.handle(GlueInput("hotspot-speech", "931:2"))
        self.assertTrue(scene.runtime.state.speech_active)

        machine.handle(GlueInput("hotspot-release", "PopAndResume"))

        self.assertFalse(scene.runtime.state.speech_active)
        self.assertEqual(scene.runtime.state.dialogue_text, "")

    def test_given_a_caravan_is_left_then_the_scripts_own_window_is_current_again(self):
        resources = {**RESOURCES, "TALKSCRIPT": "[RUN]\n[START]\nopenwindow:res=AFTERWINDOW\ngocaravan:infoTLK\n[END]",
                     "INFOCARAVANTLK": (TALKING % (931, 1)).replace("UnwindMission", "PopAndResume")}
        self.context.glue = GlueContent.from_data(resources=resources)
        machine = SceneMachine(GlueScene("TALKSCRIPT", self._campaign([regiment(2)])), self.context)
        scene = machine.active
        before = scene.runtime.state.context_stack[-1].current_window_name

        machine.handle(GlueInput("hotspot-release", "PopAndResume"))

        self.assertEqual(scene.runtime.state.current_window_name, before)


if __name__ == "__main__":
    unittest.main()
