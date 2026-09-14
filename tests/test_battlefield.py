import unittest

from whshr.battlefield import SpriteFrame, SpriteSheet, build_atlas, sprite_direction, texture_layers


def _sheet(name, group_sizes, width=2, height=3):
    frames, groups, start = [], [], 0
    for count in group_sizes:
        groups.append((start, count))
        frames += [SpriteFrame(width, height, 1, 2, bytes([start + index + 1]) * (width * height))
                   for index in range(count)]
        start += count
    return SpriteSheet(name, frames, groups)


class SpriteFrameSelectionTests(unittest.TestCase):
    def test_given_standard_unit_set_when_standing_frame_requested_then_it_is_group_start_plus_phase_and_direction(self):
        sheet = _sheet("UNIT", [32, 8, 32, 32])

        self.assertEqual(sheet.frame_index("stand", 1, 3), 72 + 8 + 3)
        self.assertEqual(sheet.frame_index("move", 5, 7), 1 * 8 + 7)
        self.assertEqual(sheet.frame_index("dead", 2, 4), 32 + 4)

    def test_given_set_without_a_group_for_an_action_when_requested_then_the_longest_group_is_used(self):
        sheet = _sheet("MONSTER", [16, 8])

        self.assertEqual(sheet.frame_index("stand", 1, 2), 8 + 2)

    def test_given_camera_looking_north_when_units_face_the_four_script_directions_then_frames_turn_counter_clockwise(self):
        frames = [sprite_direction(180, script_dir) for script_dir in (0, 128, 256, 384)]

        # dir 0 faces away (N), 128 east (E profile, frame 6), 256 toward the viewer (S), 384 west (W).
        self.assertEqual(frames, [0, 6, 4, 2])

    def test_given_camera_turned_to_look_east_when_unit_faces_east_then_it_is_seen_from_behind(self):
        self.assertEqual(sprite_direction(270, 128), 0)


class AtlasTests(unittest.TestCase):
    def test_given_frames_of_several_sheets_when_packed_then_each_rectangle_holds_its_own_pixels_without_overlap(self):
        sheets = [_sheet("A", [8], width=3, height=2), _sheet("B", [8], width=5, height=4)]

        (width, height), atlas = build_atlas(sheets, width=16)

        rects = [(sheet, index, rect) for sheet in sheets for index, rect in enumerate(sheet.rects)]
        covered = set()
        for sheet, index, (x, y, w, h) in rects:
            self.assertLessEqual(x + w, width)
            self.assertLessEqual(y + h, height)
            cells = {(x + column, y + row) for column in range(w) for row in range(h)}
            self.assertFalse(covered & cells)
            covered |= cells
            self.assertEqual({atlas[cy * width + cx] for cx, cy in cells}, {sheet.frames[index].pixels[0]})


class TextureLayerTests(unittest.TestCase):
    def test_given_smaller_scenery_texture_when_layered_then_texels_repeat_and_black_is_transparent(self):
        texture = {"name": "t", "w": 2, "h": 1, "pixels": bytes([0, 1]), "palette": [(0, 0, 0), (10, 20, 30)]}

        (layer,) = texture_layers([texture], (4, 2), transparent_black=True)

        transparent, colour = bytes((0, 0, 0, 0)), bytes((10, 20, 30, 255))
        self.assertEqual(layer, (transparent * 2 + colour * 2) * 2)

    def test_given_texture_that_does_not_tile_the_layer_when_layered_then_it_is_rejected(self):
        texture = {"name": "odd", "w": 3, "h": 1, "pixels": bytes(3), "palette": [(1, 2, 3)]}

        with self.assertRaisesRegex(ValueError, "does not tile"):
            texture_layers([texture], (4, 4))


if __name__ == "__main__":
    unittest.main()
