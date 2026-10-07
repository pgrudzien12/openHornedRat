import unittest
from dataclasses import replace
from unittest.mock import patch

import pygame

from whshr.frontend.troop_selection_view import TroopSelectionView
from whshr.roster import Regiment, RosterRow
from whshr.troop_selection import TroopSelection, STATUS_AVAILABLE, STATUS_DESTROYED, STATUS_EXCLUDED, STATUS_NOT_HIRED


def regiment(whoami, hired=True, models=10, for_hire=True, artillery=False, base_price=10, points=0):
    row = RosterRow(whoami, keep=False, for_hire=for_hire, wizard=False, artillery=artillery, base_price=base_price)
    return Regiment(whoami, f"Regiment{whoami}", hired, models, models, points, row)


class TroopSelectionTests(unittest.TestCase):
    def test_selection_book_reserves_room_for_wounded(self):
        cavalry = replace(regiment(2, models=10), orgsize=12)
        selection = TroopSelection([cavalry], reinforcements={2: 5}, wounded={2: 1})

        self.assertEqual(selection.ledger.offered[2], 1)

    def test_given_the_always_forced_commander_when_opened_then_it_is_hired_and_selected(self):
        selection = TroopSelection([regiment(2)], coffers=1000)

        row = selection.row(2)
        self.assertTrue(row.selected)
        self.assertFalse(row.toggleable)

    def test_given_a_destroyed_forced_regiment_then_it_is_not_selected(self):
        selection = TroopSelection([regiment(2, models=0)], coffers=1000)

        self.assertNotIn(2, selection.selection)
        self.assertEqual(selection.status(2), STATUS_DESTROYED)

    def test_given_a_hired_regiment_when_clicked_then_it_toggles_into_the_selection(self):
        selection = TroopSelection([regiment(2), regiment(5)], coffers=1000)

        selection.toggle(5)

        self.assertEqual(selection.selection, [2, 5])
        self.assertEqual(selection.status(5), STATUS_AVAILABLE)

    def test_given_a_selected_regiment_when_clicked_again_then_it_is_removed(self):
        selection = TroopSelection([regiment(2), regiment(5)], coffers=1000)
        selection.toggle(5)

        selection.toggle(5)

        self.assertEqual(selection.selection, [2])

    def test_given_a_not_hired_regiment_then_it_cannot_be_toggled(self):
        selection = TroopSelection([regiment(2), regiment(5, hired=False)], coffers=1000)

        refused = selection.toggle(5)

        self.assertFalse(refused)
        self.assertEqual(selection.status(5), STATUS_NOT_HIRED)
        self.assertNotIn(5, selection.selection)

    def test_given_the_selection_is_full_when_toggling_an_unselected_row_then_it_is_refused(self):
        company = [regiment(2)] + [regiment(w) for w in range(3, 16)]  # 2 forced + 13 more (one spare)
        selection = TroopSelection(company, coffers=100000, limit=13)
        for whoami in range(3, 15):  # 12 toggles: forced(1) + 12 = limit 13
            selection.toggle(whoami)
        self.assertTrue(selection.roster_full)

        refused = selection.toggle(15)

        self.assertTrue(refused)
        self.assertNotIn(15, selection.selection)

    def test_given_an_excluded_regiment_then_it_shows_excluded_status_and_cannot_toggle(self):
        selection = TroopSelection([regiment(2), regiment(29)], excluded=(29,), coffers=1000)

        self.assertEqual(selection.status(29), STATUS_EXCLUDED)
        self.assertFalse(selection.toggleable(29))

    def test_given_selected_and_unselected_hired_regiments_then_total_cost_sums_price_and_retainer(self):
        selection = TroopSelection([regiment(2, base_price=10, models=10), regiment(5, base_price=10, models=10)],
                                   coffers=1000)
        # whoami 2 forced+selected: price 100; whoami 5 hired, not selected: retainer 10
        self.assertEqual(selection.total_cost, 110)

    def test_given_a_hired_excluded_regiment_then_its_retainer_is_still_in_the_total(self):
        selection = TroopSelection([regiment(2, base_price=10, models=10), regiment(29, base_price=10, models=10)],
                                   excluded=(29,), coffers=1000)
        # notes/native-windows.md 11.3.5: whoami 2 selected (100) + whoami 29 excluded but hired (retainer 10)
        self.assertEqual(selection.total_cost, 110)

    def test_given_the_default_limit_then_it_is_thirteen(self):
        selection = TroopSelection([regiment(2)], coffers=1000)

        self.assertEqual(selection.limit, 13)

    def test_given_a_limit_outside_the_valid_range_then_it_is_clamped(self):
        self.assertEqual(TroopSelection([regiment(2)], coffers=1, limit=1).limit, 8)
        self.assertEqual(TroopSelection([regiment(2)], coffers=1, limit=100).limit, 38)

    def test_given_coffers_that_cannot_cover_the_forced_regiment_then_it_is_bankrupt(self):
        selection = TroopSelection([regiment(2, base_price=1000, models=10)], coffers=0, prepaid=0)

        self.assertTrue(selection.bankrupt)
        self.assertEqual(selection.forced_cost, 10_000)

    def test_given_enough_coffers_then_it_is_not_bankrupt(self):
        selection = TroopSelection([regiment(2, base_price=10, models=10)], coffers=1000)

        self.assertFalse(selection.bankrupt)

    def test_given_a_reordered_selection_when_moved_then_the_others_keep_their_relative_order(self):
        selection = TroopSelection([regiment(2), regiment(5), regiment(6)], coffers=1000)
        selection.toggle(5)
        selection.toggle(6)
        self.assertEqual(selection.selection, [2, 5, 6])

        selection.move(6, 0)

        self.assertEqual(selection.selection, [6, 2, 5])

    def test_given_an_affordable_selection_when_confirmed_then_the_deployment_matches_selection_order(self):
        selection = TroopSelection([regiment(2, base_price=10, models=10)], coffers=500, prepaid=100)

        deployment = selection.confirm()

        self.assertEqual(deployment.units, (2,))
        self.assertEqual(deployment.money_delta, 0)  # prepaid 100 - total_cost 100
        self.assertEqual(deployment.hired, frozenset({2}))

    def test_given_an_unaffordable_total_when_checked_then_affordable_is_false(self):
        selection = TroopSelection([regiment(2, base_price=1000, models=10)], coffers=0, prepaid=0)

        self.assertFalse(selection.affordable)

    def test_given_book_hiring_at_the_selection_limit_then_it_hires_without_selecting_or_refusing(self):
        company = [regiment(2)] + [regiment(w, hired=False) for w in range(3, 16)]
        selection = TroopSelection(company, coffers=1000, limit=13)
        for whoami in range(3, 15):
            selection.hired[whoami] = True
            selection.selection.append(whoami)

        changed = selection.set_hired_from_book(15, True)

        self.assertTrue(changed)
        self.assertTrue(selection.hired[15])
        self.assertNotIn(15, selection.selection)

    def test_given_a_hired_selected_book_regiment_when_fired_then_it_is_deselected(self):
        selection = TroopSelection([regiment(2), regiment(5)], coffers=1000)
        selection.toggle(5)

        selection.set_hired_from_book(5, False)

        self.assertFalse(selection.hired[5])
        self.assertNotIn(5, selection.selection)

    def test_ctrl_click_routes_a_select_row_to_the_book_without_a_toggle(self):
        view = TroopSelectionView.__new__(TroopSelectionView)
        view.scene = type("Scene", (), {"phase": "select"})()
        view.rows, view.buttons, view.pressed_button = [(pygame.Rect(0, 0, 100, 100), 5)], [], None
        view.scroll_direction = view.scroll_elapsed = None
        view._native_point = lambda _position: (10, 10)
        view.refresh = lambda: None

        event = type("Event", (), {"type": pygame.MOUSEBUTTONUP, "button": 1, "pos": (10, 10)})()
        with patch("whshr.frontend.troop_selection_view.pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            self.assertEqual(view.events(event), ("book:5",))

    def test_march_order_row_picks_up_on_mouse_down_not_mouse_up(self):
        # notes/troop_selection.md §5.2: "pressing on a row picks that regiment up".
        view = TroopSelectionView.__new__(TroopSelectionView)
        view.scene = type("Scene", (), {"phase": "march_order", "picked_whoami": None})()
        view.rows, view.buttons, view.pressed_button = [(pygame.Rect(0, 0, 100, 100), 5)], [], None
        view.scroll_direction = view.scroll_elapsed = None
        view._native_point = lambda _position: (10, 10)
        view._scroll_direction_at = lambda _point: None
        view._set_cursor = lambda _name: None
        view.refresh = lambda: None

        with patch("whshr.frontend.troop_selection_view.pygame.key.get_mods", return_value=0):
            down = view.events(type("Event", (), {"type": pygame.MOUSEBUTTONDOWN, "button": 1, "pos": (10, 10)})())
            self.assertEqual(down, ("pickup:5",))

            up = view.events(type("Event", (), {"type": pygame.MOUSEBUTTONUP, "button": 1, "pos": (10, 10)})())
            self.assertEqual(up, ())  # not fired again on release of the same click


if __name__ == "__main__":
    unittest.main()
