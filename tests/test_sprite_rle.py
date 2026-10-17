"""Type-4 sprite frames unpack the same on GOG and on the Steam edition's damaged files (notes/steam_edition.md §3)."""
import unittest

from whshr.sprites import decode_frame, fit_packed, unzero

WIDTH, HEIGHT = 64, 16
ROW_BYTES = WIDTH // 2
FRAME_BYTES = ROW_BYTES * HEIGHT


def packed_frame(segment: str) -> bytes:
    return fit_packed(unzero(bytes.fromhex(segment))[0], FRAME_BYTES)


def nonzero(packed: bytes) -> dict[tuple[int, int], int]:
    return {divmod(index, ROW_BYTES): value for index, value in enumerate(packed) if value}


class ZeroRunRepairTests(unittest.TestCase):
    """§3.4 vectors, frame 64 x 16 (32 packed bytes per row)."""

    def test_given_a_gog_shaped_long_gap_then_the_literal_lands_on_the_last_byte(self) -> None:
        self.assertEqual(len(unzero(bytes.fromhex("00FF00FF000112 0000"))[0]), FRAME_BYTES)
        self.assertEqual(nonzero(packed_frame("00FF00FF0001120000")), {(15, 31): 0x12})

    def test_given_a_damaged_first_run_then_it_counts_as_255(self) -> None:
        self.assertEqual(len(unzero(bytes.fromhex("00DF00FF0001120000"))[0]), FRAME_BYTES)
        self.assertEqual(nonzero(packed_frame("00DF00FF0001120000")), {(15, 31): 0x12})

    def test_given_a_damaged_second_run_then_it_counts_as_255(self) -> None:
        self.assertEqual(nonzero(packed_frame("00FF00CF0001120000")), {(15, 31): 0x12})

    def test_given_a_damaged_trailing_gap_then_the_image_is_unchanged(self) -> None:
        self.assertEqual(nonzero(packed_frame("1200FF00FF00010000")), {(0, 0): 0x12})
        self.assertEqual(nonzero(packed_frame("1200DF00FF00010000")), {(0, 0): 0x12})

    def test_given_a_short_run_followed_by_a_literal_then_it_is_not_repaired(self) -> None:
        self.assertEqual(nonzero(packed_frame("00DF1200FF21 0000".replace(" ", ""))),
                         {(6, 31): 0x12, (14, 31): 0x21})

    def test_given_a_short_run_followed_by_the_end_marker_then_it_is_not_repaired(self) -> None:
        self.assertEqual(unzero(bytes.fromhex("12000300 00".replace(" ", ""))), (b"\x12\x00\x00\x00", 5))

    def test_given_data_that_ends_early_then_the_rest_is_transparent(self) -> None:
        self.assertEqual(len(unzero(bytes.fromhex("123400100000"))[0]), 18)
        packed = packed_frame("123400100000")
        self.assertEqual(len(packed), FRAME_BYTES)
        self.assertEqual(nonzero(packed), {(0, 0): 0x12, (0, 1): 0x34})

    def test_given_a_segment_without_an_end_marker_then_unpacking_stops_at_its_end(self) -> None:
        self.assertEqual(unzero(bytes.fromhex("120004")), (b"\x12\x00\x00\x00\x00", 3))
        self.assertEqual(unzero(bytes.fromhex("1200")), (b"\x12", 1))


class DecodeFrameTests(unittest.TestCase):
    def test_given_a_short_type_4_frame_then_it_decodes_to_a_full_transparent_padded_image(self) -> None:
        segment = bytes.fromhex("123400100000")
        record = (0, 0, WIDTH, HEIGHT, 0, 4)
        pixels = decode_frame(segment, record, len(segment), [])
        self.assertEqual(len(pixels), WIDTH * HEIGHT)
        self.assertEqual(pixels[:4], [0x10, 0x20, 0x30, 0x40])
        self.assertTrue(all(value == 0 for value in pixels[4:]))

    def test_given_a_damaged_type_4_frame_then_it_decodes_like_the_undamaged_one(self) -> None:
        record = (0, 0, WIDTH, HEIGHT, 0, 4)
        good, damaged = bytes.fromhex("00FF00FF0001120000"), bytes.fromhex("00DF00FF0001120000")
        self.assertEqual(decode_frame(damaged, record, len(damaged), []), decode_frame(good, record, len(good), []))


if __name__ == "__main__":
    unittest.main()
