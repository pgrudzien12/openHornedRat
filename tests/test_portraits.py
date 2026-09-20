import struct
import tempfile
import unittest
from pathlib import Path

from whshr.portraits import dietrich_portrait, speaker_portrait


class DietrichPortraitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.binary = Path(self.temporary.name) / "FILE/BINARY"
        self.binary.mkdir(parents=True)
        palette = bytearray(256 * 4)
        for index in range(256):
            palette[index * 4:index * 4 + 4] = bytes((index, index, (index + 1) % 256, (index + 2) % 256))
        (self.binary / "STANDARD.PAL").write_bytes(palette)

    def tearDown(self):
        self.temporary.cleanup()

    def _write_sheet(self, name, frames):
        fol, bop = bytearray(), bytearray()
        for pixels in frames:
            offset = len(bop)
            fol += struct.pack("<hhhhIB", 0, 0, 2, 2, offset, 1) + b"\0\0\0"
            bop += bytes(pixels)
        (self.binary / f"{name}.FOL").write_bytes(fol)
        (self.binary / f"{name}.BOP").write_bytes(bop)

    def test_given_scribe_and_background_frames_then_the_scribe_overlays_nonzero_pixels(self):
        self._write_sheet("BACKALL", [(1, 1, 1, 1)] * 15 + [(2, 3, 4, 5)])
        self._write_sheet("SCRI", [(0, 9, 0, 10)])

        width, height, rgba = dietrich_portrait(self.temporary.name)

        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rgba, bytes((2, 3, 4, 255, 9, 10, 11, 255,
                                     4, 5, 6, 255, 10, 11, 12, 255)))

    def test_unknown_glue_portrait_index_is_not_silently_rendered_as_dietrich(self):
        with self.assertRaisesRegex(ValueError, "no verified portrait"):
            speaker_portrait(self.temporary.name, 99, 0)


if __name__ == "__main__":
    unittest.main()
