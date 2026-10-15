"""Portrait mouth/eye overlays sit where their frame record says (notes/glue_portraits.md 3.1, notes/animations.md)."""

import struct
import unittest
from unittest import mock

from whshr import battlefield
from whshr.battlefield import SpriteFrame, SpriteSheet
from whshr.portraits import compose_talking_portrait


class PortraitOverlayTests(unittest.TestCase):
    def test_given_a_portrait_frame_record_then_its_position_inside_the_portrait_is_kept(self):
        # Cpt Fletcher's (XBOW) mouth: a 56x38 frame at (38, 74) inside the 120x152 face.
        fol = (struct.pack("<hhhhIB", 0, 0, 120, 152, 0, 0x10).ljust(16, b"\0")
               + struct.pack("<hhhhIB", 38, 74, 56, 38, 1, 0x10).ljust(16, b"\0"))
        with mock.patch.object(battlefield, "decode_frame", return_value=[0]):
            sheet = battlefield.read_sprite_sheet("XBOW", fol, bytes(2))

        self.assertEqual([(f.origin_x, f.origin_y) for f in sheet.frames], [(0, 0), (38, 74)])

    def test_given_any_portrait_set_then_the_talking_overlays_are_stamped_at_their_frame_positions(self):
        palette = [(0, 0, 0), (10, 20, 30), (200, 0, 0), (0, 200, 0)]
        background = SpriteFrame(4, 4, 0, 0, bytes([1] * 16))
        face = SpriteFrame(4, 4, 0, 0, bytes(16))
        mouth = SpriteFrame(2, 1, 0, 0, bytes([2, 2]), origin_x=1, origin_y=3)
        eyes = SpriteFrame(1, 1, 0, 0, bytes([3]), origin_x=2, origin_y=1)
        sheet = SpriteSheet("XBOW", [face, mouth, eyes], [(0, 3)])

        width, _, rgba = compose_talking_portrait(palette, background, face, sheet, mouth_frame=1, eye_frame=2)

        def pixel(x, y):
            return tuple(rgba[(y * width + x) * 4:(y * width + x) * 4 + 3])
        self.assertEqual((pixel(1, 3), pixel(2, 3), pixel(2, 1)), ((200, 0, 0), (200, 0, 0), (0, 200, 0)))
        self.assertEqual(pixel(0, 0), (10, 20, 30))  # the top-left corner is untouched


if __name__ == "__main__":
    unittest.main()
