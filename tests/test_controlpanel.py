import unittest

from whshr.controlpanel import button_y, control_panel, portrait_window_height


class ControlPanelTests(unittest.TestCase):
    def test_every_decoded_controlpanel_value_has_its_documented_panel_and_labels(self):
        expected = {
            0: ("FRAMEBOTTOM", ()), 1: ("FRAMEPANEL3", (311, 309, 310)),
            2: ("FRAMEPANEL3", (333, 309, 313)), 3: ("FRAMEPANEL1", (331,)),
            4: ("FRAMEPANEL2", (330, 329)), 5: ("FRAMEPANEL4", (311, 309, 332, 313)),
            6: ("FRAMEPANEL3", (311, 309, 310)), 7: ("FRAMEPANEL3", (338, 309, 313)),
            8: ("FRAMEPANEL1", (329,)), 9: ("FRAMEPANEL3", (333, 339, 310)),
            10: ("FRAMEPANEL3", (333, 309, 313)),
        }

        self.assertEqual({value: (control_panel(value).bitmap, control_panel(value).labels)
                          for value in expected}, expected)

    def test_three_button_panel_has_the_scribe_m_window_height_and_button_positions(self):
        self.assertEqual(portrait_window_height(2), 240)
        self.assertEqual(tuple(button_y(2, slot) for slot in range(3)), (208, 188, 168))
        self.assertEqual(control_panel(2).actions, ("return_to_caravan", "open_troop_select", "open_briefing"))

    def test_unknown_panel_is_the_no_button_panel(self):
        self.assertEqual(control_panel(99), control_panel(0))
        with self.assertRaises(ValueError):
            button_y(0, 0)


if __name__ == "__main__":
    unittest.main()
