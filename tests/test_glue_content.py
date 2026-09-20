import struct
import unittest

from whshr.assets import AssetId
from whshr.glue import GlueProgram, WindowDefinition
from whshr.glue_content import GlueContent, IndexedBitmap, decode_indexed_dib


def dib_2x2(top_down=False):
    height = -2 if top_down else 2
    header = struct.pack("<IiiHHIIiiII", 40, 2, height, 1, 8, 0, 8, 0, 0, 2, 0)
    palette = bytes((0, 0, 0, 0, 30, 20, 10, 0))
    # DIB rows have four-byte stride. Bottom-up stores the lower row first.
    top = bytes((1, 0, 0, 0))
    bottom = bytes((0, 1, 0, 0))
    pixels = top + bottom if top_down else bottom + top
    return header + palette + pixels


class GlueContentTests(unittest.TestCase):
    def test_given_an_8_bit_bottom_up_dib_when_decoded_then_indexed_pixels_are_top_down(self):
        bitmap = decode_indexed_dib(dib_2x2(), "Map")

        self.assertEqual(bitmap, IndexedBitmap(
            width=2,
            height=2,
            pixels=bytes((1, 0, 0, 1)),
            palette=((0, 0, 0), (10, 20, 30)),
        ))

    def test_given_a_top_down_dib_when_decoded_then_its_row_order_is_not_reversed(self):
        bitmap = decode_indexed_dib(dib_2x2(top_down=True), "Map")

        self.assertEqual(bitmap.pixels, bytes((1, 0, 0, 1)))

    def test_given_synthetic_glue_content_when_requested_repeatedly_then_models_and_bitmaps_are_cached(self):
        content = GlueContent.from_data(
            resources={
                "Menu": "[WINDOW]\n[BITMAP]\nsetbitmap:Map\n[END]\n[END]",
                "Flow": "[RUN]\nopenwindow:res=Menu\n[END]",
            },
            bitmaps={"Map": dib_2x2()},
            strings={"brtxt": {7: "hint"}},
        )

        self.assertIsInstance(content.window("menu"), WindowDefinition)
        self.assertIsInstance(content.program("flow"), GlueProgram)
        self.assertIs(content.bitmap_data("map"), content.bitmap_data("MAP"))
        self.assertEqual(content.string("BRTXT", 7), "hint")
        self.assertEqual(content.bitmap("Map"), AssetId("vanilla", "bitmap", "map"))
        self.assertEqual(content.string_asset("BRTXT"), AssetId("vanilla", "string", "brtxt"))
        self.assertEqual(content.portrait(4, 15), (
            AssetId("vanilla", "portrait", "scri"),
            AssetId("vanilla", "portrait", "backall.15"),
        ))

    def test_given_an_overlay_when_one_window_and_bitmap_are_replaced_then_other_base_content_remains(self):
        base = GlueContent.from_data(
            resources={
                "Menu": "[WINDOW]\n[BITMAP]\nsetbitmap:Old\n[END]\n[END]",
                "Flow": "[RUN]\nreturn:\n[END]",
            },
            bitmaps={"Map": dib_2x2()},
        )
        replacement = IndexedBitmap(1, 1, b"\x00", ((1, 2, 3),))

        modded = base.overlay(
            resources={"Menu": "[WINDOW]\n[BITMAP]\nsetbitmap:New\n[END]\n[END]"},
            bitmaps={"Map": replacement},
        )

        self.assertEqual(modded.window("menu").records[0].values["setbitmap"], "New")
        self.assertEqual(base.window("menu").records[0].values["setbitmap"], "Old")
        self.assertIs(modded.program("flow"), base.program("flow"))
        self.assertIs(modded.bitmap_data("map"), replacement)

    def test_given_palette_overrides_when_requested_then_they_merge_without_an_installation(self):
        base = GlueContent.from_data(palettes={"STANDARD": {10: (1, 2, 3)}})
        modded = base.overlay(palettes={"GLUEMAP": {10: (4, 5, 6)}})

        self.assertEqual(modded.palette_tables(), {
            "STANDARD": {10: (1, 2, 3)}, "GLUEMAP": {10: (4, 5, 6)},
        })

    def test_given_an_unsupported_dib_when_decoded_then_the_resource_name_is_diagnostic(self):
        data = bytearray(dib_2x2())
        struct.pack_into("<H", data, 14, 4)

        with self.assertRaisesRegex(ValueError, "unsupported glue bitmap 'Odd': 4 bpp"):
            decode_indexed_dib(data, "Odd")


if __name__ == "__main__":
    unittest.main()
