"""Ctrl+click on a debrief troop-page row opens the roster book view only (issue #123,
notes/native-windows.md 9.3.5, notes/builtin_widgets.md 2.1)."""
import tempfile
import unittest
from pathlib import Path

from tests.test_debrief_scene import RESOURCES, campaign_with
from tests.test_debrief_screen import BF003_WON
from tests.test_troop_selection import regiment
from whshr.assets import AssetLocator
from whshr.cache import AssetCache
from whshr.campaign_scenes import ArmyRecordsScene
from whshr.catalog import build
from whshr.debrief_scene import DebriefScene
from whshr.debrief_screen import UnitOutcome
from whshr.glue_content import GlueContent
from whshr.glue_runtime import StartDebrief
from whshr.glue_scene import GlueScene
from whshr.payments import CashTerms
from whshr.scenes import SceneAssets, Transition

ROW_1_Y = 50 + 4 * 12 + 5  # inside the second P3 row (rows are 4 lines of the 12 px body font)


class DebriefRosterBookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(b"data")
        self.context = SceneAssets(AssetLocator(root), build(root), AssetCache(), {})
        self.context.glue = GlueContent.from_data(resources=RESOURCES)
        self.context.no_battle = False
        self.campaign = campaign_with(BF003_WON, terms=CashTerms(0))
        self.campaign.company = (regiment(2), regiment(5, models=12))
        self.campaign.march_units = {2, 5}
        self.campaign.march_order = (2, 5)
        self.campaign.battle_outcome = {5: UnitOutcome(6, 1, 5, kills=3, experience_gained=30)}
        self.scene = DebriefScene(GlueScene("DEBRIEFONLY", self.campaign), StartDebrief(1, 2, 1, False))
        self.scene.glue_scene.enter(self.context)
        self.scene.enter(self.context)

    def _troop_page(self):
        self.scene.handle("page:next", self.context)
        self.assertEqual(self.scene.screen.page, "p3")

    def test_given_the_troop_page_when_a_row_is_ctrl_clicked_then_the_book_opens_view_only_at_that_unit(self):
        self._troop_page()

        transition = self.scene.handle(("view-unit", ROW_1_Y), self.context)

        self.assertIsInstance(transition, Transition)
        book = transition.scene
        self.assertIsInstance(book, ArmyRecordsScene)
        self.assertTrue(book.view_only)
        self.assertEqual(book.whoami, 5)
        self.assertEqual(book.company_ids, (2, 5))  # the debrief's unit list, in its order

    def test_given_the_view_only_book_then_it_shows_the_regiment_as_the_debrief_reports_it(self):
        self._troop_page()

        book = self.scene.handle(("view-unit", ROW_1_Y), self.context).scene

        shown = book.model.company[5]
        self.assertEqual(shown.models, 7)  # standing plus routed, as the troop page counts them
        self.assertEqual(shown.experience, 30)
        self.assertEqual(book.model.ledger.wounded[5], 2)  # 4 lost at option dead 65
        self.assertFalse(book.model.ledger.has_offer(5))
        self.assertEqual(self.campaign.company[1].models, 12)  # the company itself is untouched

    def test_given_the_view_only_book_when_hire_abort_or_done_is_pressed_then_nothing_is_written(self):
        self._troop_page()
        book = self.scene.handle(("view-unit", ROW_1_Y), self.context).scene
        hired = dict(book.model.hired)

        self.assertIsNone(book.handle("book:hire-fire", self.context))
        self.assertIsNone(book.handle("book:abort", self.context))
        done = book.handle("book:done", self.context)

        self.assertEqual(book.model.hired, hired)
        self.assertIs(done.scene, self.scene)
        self.assertEqual(self.scene.screen.page, "p3")
        self.assertEqual(self.campaign.coffers, 500)  # Done of the book is not Done of the debrief

    def test_given_the_view_only_book_then_paging_walks_the_debrief_units(self):
        self._troop_page()
        book = self.scene.handle(("view-unit", ROW_1_Y), self.context).scene

        book.handle("book:previous", self.context)

        self.assertEqual(book.whoami, 2)

    def test_given_a_ctrl_click_below_the_last_row_or_off_the_troop_page_then_nothing_opens(self):
        self.assertIsNone(self.scene.handle(("view-unit", ROW_1_Y), self.context))  # still on P2
        self._troop_page()

        self.assertIsNone(self.scene.handle(("view-unit", 50 + 2 * 4 * 12 + 5), self.context))
        self.assertIsNone(self.scene.handle(("view-unit", 40), self.context))

