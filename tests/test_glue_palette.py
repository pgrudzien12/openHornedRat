import unittest

from whshr.glue_palette import AppPalette, SYSTEM_COLOURS


class AppPaletteTests(unittest.TestCase):
    def setUp(self):
        self.tables = {
            "STANDARD": {10: (1, 2, 3), 105: (4, 5, 6), 106: (7, 8, 9), 245: (10, 11, 12)},
            "GLUEMAP": {10: (20, 21, 22), 105: (23, 24, 25), 106: (99, 99, 99)},
            "WINDMAP": {106: (30, 31, 32), 245: (33, 34, 35), 105: (88, 88, 88)},
        }

    def test_pair_selection_uses_each_half_and_never_overwrites_system_slots(self):
        palette = AppPalette.select(2, self.tables)

        self.assertEqual(palette.palette_id, 2)
        self.assertEqual(palette.colours[10], (20, 21, 22))
        self.assertEqual(palette.colours[105], (23, 24, 25))
        self.assertEqual(palette.colours[106], (30, 31, 32))
        self.assertEqual(palette.colours[245], (33, 34, 35))
        self.assertEqual(palette.colours[0], SYSTEM_COLOURS[0])

    def test_negative_id_uses_embedded_middle_entries_but_keeps_system_slots(self):
        palette = AppPalette.select(-1, self.tables, embedded={0: (99, 99, 99), 10: (40, 41, 42), 246: (9, 9, 9)})

        self.assertEqual(palette.palette_id, "embedded")
        self.assertEqual(palette.colours[10], (40, 41, 42))
        self.assertEqual(palette.colours[0], SYSTEM_COLOURS[0])
        self.assertNotEqual(palette.colours[246], (9, 9, 9))

    def test_rgba_is_headless_and_index_zero_is_transparent(self):
        palette = AppPalette.select(0, self.tables)

        self.assertEqual(palette.rgba(bytes((0, 10))), bytes((0, 0, 0, 0, 1, 2, 3, 255)))


if __name__ == "__main__":
    unittest.main()
