"""Visible roster statistics layout from notes/native-windows.md §10.3.4."""
import unittest
from dataclasses import replace
from types import SimpleNamespace

from whshr.frontend.army_records_view import ArmyRecordsView
from whshr.roster import Regiment, RosterRow


class StatisticsPageTests(unittest.TestCase):
    def setUp(self):
        self.regiment = Regiment(
            2, "Test regiment", True, 12, 12, 0,
            RosterRow(2, False, False, False, False, 10),
            banner="TestBanner", profile=(4, 3, 3, 3, 3, 1, 3, 1, 7),
            leader_name="Test leader", leader_portrait="TestPortrait",
            leader_profile=(4, 4, 5, 4, 4, 2, 4, 2, 9))

    def render(self, regiment):
        view = ArmyRecordsView.__new__(ArmyRecordsView)
        view.info = False
        view.body_font = SimpleNamespace(font=SimpleNamespace(height=12))
        view.scene = SimpleNamespace(model=SimpleNamespace(ledger=SimpleNamespace(wounded={2: 2})))
        texts, pictures = {}, []
        view._label = lambda value, x, y, *_: texts.update({(x, y): value})
        view._center = lambda value, y, _, *, x, width: texts.update({(x + width // 2, y): value})
        view._string = lambda table, identifier, *args: f"{table}:{identifier}:{args}"
        view._sprite = lambda name, position: pictures.append((name, position))
        view._leader_box = lambda x, y, unit: pictures.append((unit.leader_portrait, (x, y)))
        view._bitmap_centered = lambda name, position: pictures.append((name, position))
        view._right_page(regiment)
        return texts, pictures

    def assert_profile(self, texts, profile, top):
        for index, value in enumerate(profile):
            y = top + 12 * index
            self.assertEqual(texts[(428, y)], f"BRTXT:{700 + 2 * index}:()")
            self.assertEqual(texts[(538, y)], f"BRTXT:{701 + 2 * index}:()")
            self.assertEqual(texts[(573, y)], str(value))

    def test_given_regiment_with_leader_when_statistics_open_then_both_profiles_flank_their_pictures(self):
        texts, pictures = self.render(self.regiment)
        self.assertEqual(texts[(350, 39)], "BKTXT:503:()")
        self.assertIn(("TestBanner", (350, 63)), pictures)
        self.assert_profile(texts, self.regiment.profile, 63)
        self.assertEqual(texts[(350, 179)], "Test leader")
        self.assertIn(("TestPortrait", (350, 191)), pictures)
        self.assert_profile(texts, self.regiment.leader_profile, 191)
        self.assertIn("BKTXT:502:(12, 2)", texts.values())

    def test_given_depleted_regiment_when_one_model_remains_then_it_keeps_both_profiles(self):
        texts, pictures = self.render(replace(self.regiment, models=1))
        self.assert_profile(texts, self.regiment.profile, 63)
        self.assert_profile(texts, self.regiment.leader_profile, 191)
        self.assertIn(("TestBanner", (350, 63)), pictures)

    def test_given_hero_when_statistics_open_then_only_leader_profile_is_shown_at_top(self):
        for models in (1, 0):
            with self.subTest(models=models):
                texts, pictures = self.render(replace(self.regiment, models=models, orgsize=1))
                self.assertEqual(texts[(350, 63)], "Test leader")
                self.assertIn(("TestPortrait", (350, 75)), pictures)
                self.assertFalse(any(name == "TestBanner" for name, _ in pictures))
                self.assert_profile(texts, self.regiment.leader_profile, 75)
                self.assertEqual(sum(x == 573 for x, _ in texts), 9)

    def test_given_no_leader_when_statistics_open_then_unit_profile_and_status_remain_visible(self):
        texts, pictures = self.render(replace(self.regiment, leader_name=None))
        self.assert_profile(texts, self.regiment.profile, 63)
        self.assertFalse(any(name == "TestPortrait" for name, _ in pictures))
        self.assertEqual(sum(x == 573 for x, _ in texts), 9)
        self.assertIn("BKTXT:502:(12, 2)", texts.values())
