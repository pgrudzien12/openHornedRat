"""Debrief screen (issue #123, notes/native-windows.md section 9, notes/debrief_evaluation.md section 4):
evaluators, text programs, page/button state machine and the drawing lists of P2, P3 and P4."""
import unittest

from whshr import debrief_rules
from whshr.debrief_rules import ENTRIES, evaluate
from whshr.debrief_screen import DebriefReport, DebriefScreen, DebriefUnit
from whshr.payments import CashTerms


def strings(table, text_id, *arguments):
    text = f"{table}{text_id}"
    return text + ("(" + ",".join(str(a) for a in arguments) + ")" if arguments else "")


def unit(whoami=2, name="Cavalry", models=10, routed=0, casualties=0, kills=0, experience=0, experience_start=0,
         orgsize=16, hired=True, artillery=False, points=0):
    return DebriefUnit(whoami, name, models, routed, casualties, kills, experience, experience_start, orgsize,
                       0, 0, points, None, hired, artillery)


def screen(mode=2, index=1, results=None, units=(), terms=None, coffers=280, **kwargs):
    report = DebriefReport(results or {}, tuple(units))
    return DebriefScreen(mode, report, index, terms, coffers, 5, strings, **kwargs)


BF003_WON = {"Z": (False, (28, 2, 0, 0)), "R": (False, (1, 0, 0, 0)), "A": (True, (32, 2, 0, 0)),
             "B": (True, (80, 12, 100, 12)), "C": (True, (80, 7, 100, 7)), "K": (False, (13, 10, 0, 39))}
BF003_TERMS = CashTerms(1, 100, 400, 50, 25, ("A",))


def at(layout, text, font=None):
    return next(item for item in layout.texts if item.text == text and (font is None or item.font == font))


class EvaluatorTests(unittest.TestCase):
    def test_given_the_table_then_it_has_41_rows_and_every_program_token_is_known(self):
        self.assertEqual(len(ENTRIES), 41)
        for entry in ENTRIES:
            for text in entry.lists:
                for kind, value in debrief_rules.parse_program(text or ""):
                    if kind == "measure":
                        self.assertIn(value, debrief_rules.MEASURES)

    def test_given_the_bf003_result_when_evaluated_by_its_entry_then_it_is_a_victory_with_list_a(self):
        evaluation = evaluate(1, BF003_WON)

        self.assertTrue(evaluation.victory)
        self.assertEqual(evaluation.list_name, "A")

    def test_given_z_met_when_evaluated_by_the_default_then_it_is_a_defeat_with_list_b(self):
        evaluation = evaluate(1, {**BF003_WON, "Z": (True, (28, 2, 2, 0))})

        self.assertFalse(evaluation.victory)
        self.assertEqual(evaluation.list_name, "B")

    def test_given_an_unmet_required_letter_when_evaluated_by_the_default_then_it_is_a_defeat(self):
        self.assertFalse(evaluate(1, {**BF003_WON, "B": (False, (80, 12, 50, 6))}).victory)

    def test_given_the_ignored_letters_when_unmet_then_the_default_evaluator_still_wins(self):
        self.assertTrue(evaluate(1, {"A": (True, (1, 1, 0, 0)), "K": (False, (0, 0, 0, 0)), "R": (False, (1, 0, 0, 0))}).victory)

    def test_given_no_survivor_in_the_slave_train_when_evaluated_then_it_is_a_defeat(self):
        results = {"Z": (False, (10, 1, 0, 0)), "B": (True, (0, 5, 0, 0))}

        self.assertFalse(evaluate(14, results).victory)
        self.assertTrue(evaluate(14, {**results, "B": (True, (0, 5, 40, 2))}).victory)

    def test_given_the_mole_machine_when_z_is_met_then_the_alternate_list_depends_on_the_protected_unit(self):
        lost = {"Z": (True, (10, 1, 1, 0))}

        self.assertEqual(evaluate(19, {**lost, "P": (False, (7, 0, 0, 0))}).list_name, "C")
        self.assertEqual(evaluate(19, {**lost, "P": (True, (7, 0, 0, 0))}).list_name, "B")
        self.assertEqual(evaluate(19, {"Z": (False, (10, 1, 0, 0))}).list_name, "A")

    def test_given_a_siege_when_the_gate_flag_is_met_then_the_assault_failed(self):
        self.assertFalse(evaluate(22, {"G": (True, (1, 4, 0, 0))}).victory)
        self.assertTrue(evaluate(22, {"G": (False, (1, 4, 0, 0))}).victory)

    def test_given_the_forest_mission_then_z_or_an_unmet_q_decides_the_list(self):
        self.assertEqual(evaluate(35, {"Z": (True, ())}).list_name, "C")
        self.assertEqual(evaluate(35, {"Z": (False, ()), "Q": (True, (60, 10, 80, 8))}).list_name, "A")
        self.assertEqual(evaluate(35, {"Z": (False, ()), "Q": (False, (60, 10, 30, 3))}).list_name, "B")

    def test_given_the_final_battle_then_c_decides_the_status_bits(self):
        won = evaluate(38, {"Z": (False, (1, 1, 0, 0)), "C": (True, ())})
        partial = evaluate(38, {"Z": (False, (1, 1, 0, 0)), "C": (False, ())})

        self.assertEqual((won.victory, won.list_name, won.status_bits), (True, "A", 0x4000))
        self.assertEqual((partial.victory, partial.list_name, partial.status_bits), (True, "C", 0x8000))
        self.assertFalse(evaluate(38, {"Z": (True, ()), "C": (True, ())}).victory)

    def test_given_a_battle_a_victory_shows_nothing_for_then_the_evaluation_has_no_program(self):
        self.assertIsNone(evaluate(16, {"Z": (False, (1, 1, 0, 0))}).program)
        self.assertIsNone(evaluate(5, {"Z": (True, (1, 1, 1, 0)), "A": (False, ())}).program)


class PageFlowTests(unittest.TestCase):
    def test_given_mode_2_when_paged_then_p2_p3_p4_and_back_with_the_documented_button_states(self):
        view = screen(mode=2, results=BF003_WON, units=[unit()])

        self.assertEqual((view.page, view.buttons().next, view.buttons().back), ("p2", True, False))
        view.next()
        self.assertEqual((view.page, view.buttons().next, view.buttons().back), ("p3", True, True))
        view.next()
        self.assertEqual((view.page, view.buttons().next, view.buttons().back), ("p4", False, True))
        view.back()
        self.assertEqual(view.page, "p3")

    def test_given_a_mode_6_debrief_with_three_unit_pages_when_paged_then_the_balance_page_is_unreachable(self):
        view = screen(mode=6, results=BF003_WON, units=[unit(whoami=n) for n in range(13)])

        view.next()
        view.next()
        view.next()

        self.assertEqual((view.page, view.unit_page), ("p3", 2))
        self.assertFalse(view.buttons().next)
        view.next()
        self.assertEqual(view.page, "p3")

    def test_given_mode_7_when_next_then_the_balance_page_shows_and_back_returns_to_the_verdict(self):
        view = screen(mode=7, results=BF003_WON, units=[unit()])

        view.next()
        self.assertEqual(view.page, "p4")
        self.assertEqual((view.buttons().next, view.buttons().back), (False, True))
        view.back()
        self.assertEqual(view.page, "p2")

    def test_given_mode_4_then_only_the_balance_page_shows_and_only_done_is_enabled(self):
        view = screen(mode=4, results=BF003_WON)

        self.assertEqual(view.page, "p4")
        self.assertEqual((view.buttons().next, view.buttons().back, view.buttons().done), (False, False, True))

    def test_given_a_mode_2_battle_whose_outcome_has_no_text_then_the_screen_is_skipped(self):
        lost_bf001 = {"Z": (True, (10, 1, 1, 0)), "A": (False, ())}

        self.assertTrue(screen(mode=2, index=5, results=lost_bf001).will_skip())
        self.assertFalse(screen(mode=4, index=5, results=lost_bf001).will_skip())
        self.assertFalse(screen(mode=2, index=1, results=BF003_WON).will_skip())

    def test_given_the_result_then_win_or_lose_music_plays_except_in_mode_4(self):
        lost = {**BF003_WON, "Z": (True, (28, 2, 2, 0))}

        self.assertEqual(screen(mode=2, results=BF003_WON).music(), "win")
        self.assertEqual(screen(mode=7, results=lost).music(), "lose")
        self.assertEqual(screen(mode=4, results=BF003_WON).music(), "tactical")

    def test_given_a_mode_that_is_never_requested_then_it_is_refused(self):
        with self.assertRaises(ValueError):
            screen(mode=3)


class VerdictPageTests(unittest.TestCase):
    def test_given_bf003_won_when_p2_is_drawn_then_the_first_line_is_the_heading_and_the_rest_follow_at_12_px(self):
        layout = screen(mode=2, results=BF003_WON, units=[unit()]).layout()

        first = at(layout, "BKTXT10008")
        self.assertEqual((first.font, first.y, first.align), (4, 146, "center"))
        self.assertEqual(at(layout, "BKTXT10009").y, 190 + 12)
        self.assertEqual(at(layout, "BKTXT10010(0,0)").y, 190 + 12 * 3)
        self.assertEqual(at(layout, "BKTXT403(BRTXT5)").y, 25)

    def test_given_a_met_pickup_when_p2_is_drawn_then_the_item_line_names_the_picker(self):
        results = {**BF003_WON, "K": (True, (13, 10, 2, 39))}
        view = screen(mode=2, results=results, units=[unit(whoami=2, name="Cavalry")],
                      item_name=lambda index: f"item{index}")

        line = next(item for item in view.layout().texts if item.text.startswith("BKTXT610"))

        self.assertEqual(line.text, "BKTXT610(Cavalry,item39)")


class TroopPageTests(unittest.TestCase):
    def test_given_seven_lost_models_when_p3_is_drawn_then_wounded_is_4_and_dead_3_and_only_gains_show(self):
        view = screen(mode=2, results=BF003_WON,
                      units=[unit(name="Infantry", models=9, casualties=7, kills=20, experience=180, experience_start=100)])
        view.next()

        layout = view.layout()
        row_numbers = {(item.x, item.text) for item in layout.texts if item.y == 62}

        self.assertIn((345, "20"), row_numbers)
        self.assertIn((405, "3"), row_numbers)
        self.assertIn((465, "4"), row_numbers)
        self.assertIn((530, "80"), row_numbers)
        self.assertIn((105, "Infantry 9 (16)"), row_numbers)

    def test_given_seven_regiments_when_paged_then_six_show_first_and_one_on_the_second_page(self):
        view = screen(mode=2, results=BF003_WON, units=[unit(whoami=n, name=f"U{n}") for n in range(7)])
        view.next()
        first = view.layout()
        view.next()
        second = view.layout()

        self.assertEqual(len(first.rows), 6)
        self.assertEqual([row.y for row in first.rows], [62, 110, 158, 206, 254, 302])
        self.assertEqual(len(second.rows), 1)

    def test_given_a_destroyed_or_unhired_regiment_then_its_lines_are_red_or_grey(self):
        view = screen(mode=2, results=BF003_WON, units=[unit(whoami=1, name="Gone", models=0),
                                                        unit(whoami=2, name="Away", hired=False)])
        view.next()

        layout = view.layout()

        self.assertEqual(at(layout, "Gone 0 (16)").colour, (255, 0, 0))
        self.assertEqual(at(layout, "Away 10 (16)").colour, (127, 127, 127))

    def test_given_z_met_then_the_wounded_lost_line_shows_below_the_last_row(self):
        results = {**BF003_WON, "Z": (True, (28, 2, 2, 0))}
        view = screen(mode=2, index=0, results=results, units=[unit()])
        view.next()

        note = at(view.layout(), "BKTXT611")

        self.assertEqual((note.x, note.y), (345, 50 + 4 * 12))


class BalancePageTests(unittest.TestCase):
    def sheet(self, **kwargs):
        view = screen(mode=4, results=BF003_WON, terms=BF003_TERMS, **kwargs)
        return view.layout()

    def test_given_the_bf003_program_when_p4_is_drawn_then_the_worked_example_lines_show_with_right_aligned_amounts(self):
        layout = self.sheet()

        self.assertEqual(at(layout, "BKTXT5005", 4).y, 50)
        initial = at(layout, "BKTXT5000")
        self.assertEqual((initial.x, initial.y), (45, 94))
        amount = next(item for item in layout.texts if item.y == 94 and item.align == "right")
        self.assertEqual((amount.text, amount.x), (" 100 BKTXT419", 390))
        self.assertEqual(next(item for item in layout.texts if item.y == 94 + 18 * 2 and item.align == "right").text,
                         " 500 BKTXT419")
        self.assertEqual(next(item for item in layout.texts if item.text == "-100 BKTXT419").y, 94 + 18 * 4)
        self.assertIn("-0 BKTXT419", [item.text for item in layout.texts])

    def test_given_the_worked_example_then_the_total_line_shows_coffers_plus_the_final_payment(self):
        layout = self.sheet(coffers=280)

        self.assertIn("BKTXT5008(680)", [item.text for item in layout.texts])
        final = at(layout, "BKTXT5003")
        self.assertEqual(final.y, 94 + 18 * 8)

    def test_given_an_armour_program_when_a_regiment_has_no_models_then_its_line_is_absent_and_takes_no_space(self):
        terms = CashTerms(11, 0, 500, 25, 0, ("A",))
        results = {"A": (True, (1, 1, 0, 0)), "Z": (False, (10, 1, 0, 0))}
        both = screen(mode=4, results=results, terms=terms,
                      units=[unit(whoami=4, name="Avengers"), unit(whoami=27, name="Crossbows")]).layout()
        one = screen(mode=4, results=results, terms=terms,
                     units=[unit(whoami=4, name="Avengers"), unit(whoami=27, name="Crossbows", models=0)]).layout()

        self.assertIn("BKTXT5022(Crossbows)", [item.text for item in both.texts])
        self.assertNotIn("BKTXT5022(Crossbows)", [item.text for item in one.texts])
        total_y = lambda layout: at(layout, "BKTXT5007").y
        self.assertEqual(total_y(both) - total_y(one), 18)

    def test_given_the_double_experience_program_then_the_multiplier_is_2_and_the_line_is_label_only(self):
        view = screen(mode=4, results=BF003_WON, terms=CashTerms(15))

        self.assertEqual(view.experience_multiplier, 2)
        self.assertEqual(screen(mode=4, results=BF003_WON, terms=BF003_TERMS).experience_multiplier, 1)
        self.assertNotIn("right", [item.align for item in view.layout().texts if item.text == "BKTXT5021"])


if __name__ == "__main__":
    unittest.main()
